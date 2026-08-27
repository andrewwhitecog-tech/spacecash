"""Repeatable SpaceCash devnet smoke checks.

This intentionally uses a temporary SQLite ledger under the project `_tmp`
directory so it does not mutate the live `spacecash_devnet.sqlite3` file.
"""

import argparse
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils

ROOT = Path(__file__).resolve().parents[1]

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spacecash_core import SpaceCashLedger, protocol  # noqa: E402


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def make_wallet(ledger, label):
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_numbers = private_key.public_key().public_numbers()
    public_jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": protocol.b64url_encode(public_numbers.x.to_bytes(32, "big")),
        "y": protocol.b64url_encode(public_numbers.y.to_bytes(32, "big")),
    }
    wallet = ledger.register_wallet(public_jwk, label)
    return wallet, private_key


def sign_payload(private_key, payload):
    signature_der = private_key.sign(
        protocol.canonical_json(payload).encode("utf-8"),
        ec.ECDSA(hashes.SHA256()),
    )
    r, s = utils.decode_dss_signature(signature_der)
    return protocol.b64url_encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


def signed_transfer_payload(private_key, sender, recipient, amount, memo):
    payload = {
        "chain_id": protocol.CHAIN_ID,
        "version": protocol.SIGNED_PAYLOAD_VERSION,
        "action": "transfer",
        "sender": sender,
        "recipient": recipient,
        "amount": amount,
        "memo": memo,
        "nonce": secrets.token_urlsafe(18),
    }
    return {"auth_payload": payload, "signature": sign_payload(private_key, payload)}


class GossipHandler(BaseHTTPRequestHandler):
    advertised_peer_url = ""

    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        if self.path.startswith("/peers"):
            body = json.dumps({
                "peers": [
                    {"url": self.advertised_peer_url, "label": "smoke-discovered"},
                    {"url": "not-a-spacecash-url"},
                ],
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()


def run_gossip_smoke(ledger):
    discovered_port = 18000 + secrets.randbelow(20000)
    GossipHandler.advertised_peer_url = f"http://127.0.0.1:{discovered_port}"
    server = ThreadingHTTPServer(("127.0.0.1", 0), GossipHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    source_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        ledger.add_peer(source_url, "smoke-source", "SpaceCash smoke peer source")
        result = ledger.gossip_peers(timeout=3, max_new=10)
        assert_true(result["source_count"] >= 1, "gossip should have at least one source")
        assert_true(result["added_count"] == 1, "gossip should add the advertised peer once")
        assert_true(result["skipped_invalid"] == 1, "gossip should reject the invalid peer URL")
        repeat = ledger.gossip_peers(timeout=3, max_new=10)
        assert_true(repeat["added_count"] == 0, "repeat gossip should not duplicate peers")
        return {
            "source_url": source_url,
            "discovered_url": GossipHandler.advertised_peer_url,
            "added_count": result["added_count"],
            "repeat_added_count": repeat["added_count"],
        }
    finally:
        server.shutdown()
        thread.join(timeout=3)


def run_smoke(db_path):
    ledger = SpaceCashLedger(db_path)
    alice, alice_key = make_wallet(ledger, "Smoke Alice")
    bob, _ = make_wallet(ledger, "Smoke Bob")

    faucet = ledger.faucet(alice["address"], "25")
    assert_true(faucet["balance"] == "25", "faucet balance should settle")

    transfer = ledger.submit_transfer(
        signed_transfer_payload(alice_key, alice["address"], bob["address"], "7", "smoke transfer")
    )
    assert_true(transfer["accepted"], "signed transfer should enter the mempool")

    mined = ledger.mine_pending_transactions(limit=10)
    assert_true(mined["mined_count"] == 1, "mempool mine should settle one transfer")
    assert_true(mined["block"] and int(mined["block"]["block_version"]) >= 2, "mempool mine should produce a versioned block")

    bob_summary = ledger.wallet_summary(bob["address"])
    assert_true(bob_summary["balance"] == "7", "recipient should receive the mined transfer")

    ledger.add_validator(alice["address"])
    checkpoint_payload = ledger.checkpoint_vote_payload(alice["address"])
    checkpoint_vote = {
        "auth_payload": checkpoint_payload,
        "signature": sign_payload(alice_key, checkpoint_payload),
    }
    vote = ledger.submit_checkpoint_vote(checkpoint_vote)
    assert_true(vote["quorum"]["quorum_reached"], "single-validator checkpoint quorum should pass")

    snapshot = ledger.chain_snapshot(include_service_data=False)
    snapshot_check = ledger.verify_chain_snapshot(snapshot)
    assert_true(snapshot_check["valid"], "chain snapshot should verify")

    gossip = run_gossip_smoke(ledger)
    audit = ledger.audit()
    assert_true(audit["valid"], "final smoke audit should pass")

    return {
        "ok": True,
        "db_path": str(db_path),
        "alice": alice["address"],
        "bob": bob["address"],
        "mined_block": mined["block"]["height"],
        "checkpoint_quorum": vote["quorum"]["quorum_reached"],
        "gossip": gossip,
        "audit": {
            "valid": audit["valid"],
            "blocks": audit["counts"]["blocks"],
            "transactions": audit["counts"]["transactions"],
            "validators": audit["counts"]["validators"],
        },
    }


def default_db_path():
    tmp_dir = ROOT / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return tmp_dir / f"spacecash_smoke_{secrets.token_hex(8)}.sqlite3"


def main():
    parser = argparse.ArgumentParser(description="Run SpaceCash smoke checks against a temporary ledger")
    parser.add_argument("--db", type=Path, default=None, help="Optional SQLite path to use")
    parser.add_argument("--keep-db", action="store_true", help="Do not delete the temporary smoke ledger")
    args = parser.parse_args()
    db_path = args.db or default_db_path()
    result = run_smoke(db_path)
    if not args.keep_db and args.db is None:
        resolved = db_path.resolve()
        tmp_root = (ROOT / "_tmp").resolve()
        if tmp_root in resolved.parents and resolved.exists():
            resolved.unlink()
            result["db_removed"] = True
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
