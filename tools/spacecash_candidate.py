"""Build a clean signed-only SpaceCash candidate ledger.

This creates a fresh local candidate database that can satisfy automated
readiness gates without rewriting the historical devnet database.
"""

import argparse
import json
import secrets
import sys
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spacecash_core import SpaceCashLedger, protocol  # noqa: E402


def public_jwk(private_key):
    public_numbers = private_key.public_key().public_numbers()
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": protocol.b64url_encode(public_numbers.x.to_bytes(32, "big")),
        "y": protocol.b64url_encode(public_numbers.y.to_bytes(32, "big")),
    }


def private_jwk(private_key):
    numbers = private_key.private_numbers()
    jwk = public_jwk(private_key)
    jwk["d"] = protocol.b64url_encode(numbers.private_value.to_bytes(32, "big"))
    return jwk


def generate_signed_wallet(ledger, label):
    private_key = ec.generate_private_key(ec.SECP256R1())
    wallet = ledger.register_wallet(public_jwk(private_key), label)
    return wallet, private_key


def sign_payload(private_key, payload):
    signature_der = private_key.sign(
        protocol.canonical_json(payload).encode("utf-8"),
        ec.ECDSA(hashes.SHA256()),
    )
    r, s = utils.decode_dss_signature(signature_der)
    return protocol.b64url_encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


def signed_transfer(private_key, sender, recipient, amount, memo):
    payload = {
        "chain_id": protocol.CHAIN_ID,
        "version": protocol.SIGNED_PAYLOAD_VERSION,
        "action": "transfer",
        "sender": sender,
        "recipient": recipient,
        "amount": str(amount),
        "memo": memo,
        "nonce": f"candidate-{secrets.token_hex(16)}",
    }
    return {"auth_payload": payload, "signature": sign_payload(private_key, payload)}


def remove_candidate_db(db_path):
    for candidate in (db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")):
        if candidate.exists():
            candidate.unlink()


def build_candidate(db_path, bootstrap_peers=None, keys_out=None, force=False, validator_count=1, validator_quorum=None):
    db_path = Path(db_path)
    if db_path.exists() and not force:
        raise ValueError(f"Candidate DB already exists: {db_path}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if force:
        remove_candidate_db(db_path)

    validator_count = max(1, int(validator_count or 1))
    validator_quorum = int(validator_quorum or min(validator_count, protocol.DEFAULT_VALIDATOR_QUORUM))
    if validator_quorum < 1 or validator_quorum > validator_count:
        raise ValueError("Validator quorum must be between 1 and validator_count.")

    ledger = SpaceCashLedger(db_path)
    validators = []
    for index in range(validator_count):
        validator, validator_key = generate_signed_wallet(ledger, f"Candidate Validator {index + 1}")
        validators.append({"wallet": validator, "key": validator_key})
    primary_validator = validators[0]
    recipient, recipient_key = generate_signed_wallet(ledger, "Candidate Recipient")

    ledger.faucet(primary_validator["wallet"]["address"], "25")
    queued = ledger.submit_transfer(signed_transfer(
        primary_validator["key"],
        primary_validator["wallet"]["address"],
        recipient["address"],
        "1",
        "Candidate signed transfer",
    ))
    mined = ledger.mine_pending_transactions()

    for validator in validators:
        ledger.add_validator(validator["wallet"]["address"])
    ledger.set_validator_quorum(validator_quorum)

    checkpoint = None
    checkpoint_votes = []
    for validator in validators:
        checkpoint_payload = ledger.checkpoint_vote_payload(validator["wallet"]["address"])
        checkpoint = ledger.submit_checkpoint_vote({
            "auth_payload": checkpoint_payload,
            "signature": sign_payload(validator["key"], checkpoint_payload),
        })
        checkpoint_votes.append((checkpoint.get("vote") or {}).get("vote_id"))

    peers = bootstrap_peers or ["http://127.0.0.1:8876"]
    ledger.set_bootstrap_peers([
        {
            "url": url,
            "label": "candidate-bootstrap",
            "notes": "Candidate readiness bootstrap peer.",
        }
        for url in peers
    ])

    audit = ledger.audit()
    readiness = ledger.mainnet_readiness()
    manifest = ledger.chain_manifest()

    if keys_out:
        keys_out = Path(keys_out)
        keys_out.parent.mkdir(parents=True, exist_ok=True)
        keys_out.write_text(json.dumps({
            "warning": "Development candidate keys. Do not use these keys for mainnet custody.",
            "chain_id": protocol.CHAIN_ID,
            "validators": [
                {
                    "address": validator["wallet"]["address"],
                    "private_jwk": private_jwk(validator["key"]),
                }
                for validator in validators
            ],
            "recipient": {
                "address": recipient["address"],
                "private_jwk": private_jwk(recipient_key),
            },
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "ok": bool(audit.get("valid") and readiness.get("automated_release_candidate")),
        "db_path": str(db_path.resolve()),
        "chain_id": protocol.CHAIN_ID,
        "validator": primary_validator["wallet"]["address"],
        "validators": [validator["wallet"]["address"] for validator in validators],
        "validator_quorum": validator_quorum,
        "recipient": recipient["address"],
        "queued": {
            "accepted": queued.get("accepted"),
            "pending_id": (queued.get("pending") or {}).get("pending_id"),
        },
        "mined": {
            "mined_count": mined.get("mined_count"),
            "block_height": (mined.get("block") or {}).get("height"),
        },
        "checkpoint_quorum": bool((checkpoint.get("quorum") or {}).get("quorum_reached")),
        "checkpoint_votes": checkpoint_votes,
        "manifest": {
            "height": manifest.get("height"),
            "tip_hash": manifest.get("tip_hash"),
            "chain_digest": manifest.get("chain_digest"),
            "versioned_blocks": manifest.get("versioned_blocks"),
        },
        "audit": {
            "valid": audit.get("valid"),
            "warning_count": len(audit.get("warnings") or []),
            "counts": audit.get("counts"),
        },
        "readiness": {
            "mainnet_ready": readiness.get("mainnet_ready"),
            "automated_release_candidate": readiness.get("automated_release_candidate"),
            "automated_blockers": readiness.get("automated_blockers"),
            "manual_blockers": readiness.get("manual_blockers"),
        },
    }


def build_parser():
    parser = argparse.ArgumentParser(description="Build a clean signed-only SpaceCash candidate ledger")
    parser.add_argument("--db", type=Path, default=ROOT / "_tmp" / "spacecash_candidate.sqlite3", help="Output candidate SQLite DB")
    parser.add_argument("--bootstrap-peer", action="append", dest="bootstrap_peers", help="Bootstrap peer URL; may be repeated")
    parser.add_argument("--keys-out", type=Path, help="Optional development private-key JSON output")
    parser.add_argument("--validators", type=int, default=1, help="Number of signed validator wallets to create")
    parser.add_argument("--quorum", type=int, help="Validator checkpoint quorum")
    parser.add_argument("--force", action="store_true", help="Overwrite the candidate DB if it already exists")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = build_candidate(
            args.db,
            bootstrap_peers=args.bootstrap_peers,
            keys_out=args.keys_out,
            force=args.force,
            validator_count=args.validators,
            validator_quorum=args.quorum,
        )
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
