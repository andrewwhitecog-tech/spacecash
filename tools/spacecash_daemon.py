"""SpaceCash devnet daemon.

This exposes the extracted `spacecash_core` ledger and shared catalog boundary
over HTTP without importing the NorthStar Flask app.
"""

import argparse
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spacecash_core import SpaceCashLedger  # noqa: E402
from spacecash_core import protocol  # noqa: E402
from northstar_catalog import NorthStarCatalog, ProductNotEligible, ProductNotFound  # noqa: E402
from tools.spacecash_genesis_allocation import genesis_allocation_template, validate_allocation  # noqa: E402
from tools.spacecash_legal_compliance_evidence import legal_compliance_evidence_template, validate_legal_compliance_evidence  # noqa: E402
from tools.spacecash_mainnet_decision import mainnet_decision_template, validate_mainnet_decision  # noqa: E402
from tools.spacecash_production_deployment_evidence import production_deployment_evidence_template, validate_production_deployment_evidence  # noqa: E402
from tools.spacecash_security_review_evidence import security_review_evidence_template, validate_security_review_evidence  # noqa: E402
from tools.spacecash_wallet_custody_evidence import wallet_custody_evidence_template, validate_wallet_custody_evidence  # noqa: E402


def default_db_path():
    app_data = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return Path(os.environ.get("SPACECASH_DB", str(app_data / "SpaceCash" / "spacecash_devnet.sqlite3")))


def default_vault_dir():
    return Path(os.environ.get("SPACECASH_CATALOG_DIR", str(Path.home() / ".spacecash" / "catalog")))


def default_prime_db_path():
    return Path(os.environ.get("NS_PRIME_DB", str(default_vault_dir() / "data" / "northstar_prime.db")))


def default_chromatic_db_path():
    return Path(os.environ.get("NS_PRIME_CHROMATIC_DB", str(default_vault_dir() / "data" / "chromatic_store.db")))


def json_bytes(payload):
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")


class SpaceCashDaemonHandler(BaseHTTPRequestHandler):
    server_version = "SpaceCashDaemon/0.3"

    def log_message(self, fmt, *args):
        try:
            sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))
        except (AttributeError, OSError, ValueError):
            pass

    @property
    def ledger(self):
        return self.server.ledger

    @property
    def catalog(self):
        return self.server.catalog

    def send_json(self, payload, status=200):
        body = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def not_found(self):
        self.send_json({"error": "SpaceCash daemon route not found."}, 404)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Request body must be valid JSON.") from exc

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        try:
            if path == "/":
                self.send_json({
                    "service": "spacecash-daemon",
                    "chain_id": protocol.CHAIN_ID,
                    "routes": [
                        "/health",
                        "/config",
                        "/consensus/spec",
                        "/monetary/policy",
                        "/genesis/plan",
                        "/genesis/allocation/template",
                        "/genesis/allocation/check",
                        "/security/review/evidence/template",
                        "/security/review/evidence/check",
                        "/legal/compliance/evidence/template",
                        "/legal/compliance/evidence/check",
                        "/wallet/custody/evidence/template",
                        "/wallet/custody/evidence/check",
                        "/deployment/evidence/template",
                        "/deployment/evidence/check",
                        "/mainnet/decision/template",
                        "/mainnet/decision/check",
                        "/wallet/policy",
                        "/status",
                        "/node",
                        "/policy",
                        "/validators",
                        "/checkpoint/quorum",
                        "/checkpoint/votes",
                        "/chain/manifest",
                        "/chain/snapshot",
                        "/audit",
                        "/readiness",
                        "/blocks?limit=25",
                        "/block/<height-or-hash>",
                        "/tx/<txid>",
                        "/tx/<txid>/proof",
                        "/wallet/<address>",
                        "/mempool?status=pending",
                        "/mempool/<pending_id>",
                        "/peers",
                        "/bootstrap-peers",
                        "/sync-candidates?status=peer_ahead_candidate",
                        "/sync-candidate/<candidate_id>",
                        "/sync-imports",
                        "/orders?wallet=<address>&status=pending_review",
                        "/order/<receipt_id>",
                        "/order/<receipt_id>/events",
                        "POST /node/label",
                        "POST /policy/producers",
                        "POST /policy/producers/add",
                        "POST /validators",
                        "POST /validators/add",
                        "POST /validators/quorum",
                        "POST /checkpoint/payload",
                        "POST /checkpoint/vote",
                        "POST /bootstrap-peers",
                        "POST /bootstrap-peers/add",
                        "POST /bootstrap-peers/load",
                        "POST /chain/verify",
                        "POST /chain/fork-choice",
                        "POST /peers",
                        "POST /peers/record",
                        "POST /peers/check",
                        "POST /peers/check-all",
                        "POST /peers/gossip",
                        "POST /peers/fork-choice",
                        "POST /peers/sync-preview",
                        "POST /peers/sync-preview-all",
                        "POST /peers/sync-import",
                        "POST /wallet/new",
                        "POST /wallet/register",
                        "POST /faucet",
                        "POST /transfer",
                        "POST /redeem",
                        "POST /pay",
                        "POST /mempool/transfer",
                        "POST /mempool/redeem",
                        "POST /mempool/pay",
                        "POST /mempool/mine",
                        "POST /orders/backfill",
                        "POST /order/<receipt_id>/status",
                    ],
                })
                return
            if path == "/health":
                self.send_json({
                    "ok": True,
                    "service": "spacecash-daemon",
                    "chain_id": protocol.CHAIN_ID,
                    "time": time.time(),
                })
                return
            if path == "/config":
                self.send_json(protocol.chain_config())
                return
            if path == "/consensus/spec":
                self.send_json(protocol.consensus_spec())
                return
            if path == "/monetary/policy":
                self.send_json(protocol.monetary_policy())
                return
            if path == "/genesis/plan":
                self.send_json(protocol.genesis_plan())
                return
            if path == "/genesis/allocation/template":
                self.send_json(genesis_allocation_template())
                return
            if path == "/genesis/allocation/check":
                self.send_json(validate_allocation(genesis_allocation_template()))
                return
            if path == "/security/review/evidence/template":
                self.send_json(security_review_evidence_template())
                return
            if path == "/security/review/evidence/check":
                self.send_json(validate_security_review_evidence(security_review_evidence_template()))
                return
            if path == "/legal/compliance/evidence/template":
                self.send_json(legal_compliance_evidence_template())
                return
            if path == "/legal/compliance/evidence/check":
                self.send_json(validate_legal_compliance_evidence(legal_compliance_evidence_template()))
                return
            if path == "/wallet/custody/evidence/template":
                self.send_json(wallet_custody_evidence_template())
                return
            if path == "/wallet/custody/evidence/check":
                self.send_json(validate_wallet_custody_evidence(wallet_custody_evidence_template()))
                return
            if path == "/deployment/evidence/template":
                self.send_json(production_deployment_evidence_template())
                return
            if path == "/deployment/evidence/check":
                self.send_json(validate_production_deployment_evidence(production_deployment_evidence_template()))
                return
            if path == "/mainnet/decision/template":
                self.send_json(mainnet_decision_template())
                return
            if path == "/mainnet/decision/check":
                self.send_json(validate_mainnet_decision(mainnet_decision_template(), verify_checksum_manifests=False))
                return
            if path == "/wallet/policy":
                self.send_json(protocol.wallet_policy())
                return
            if path == "/status":
                self.send_json(self.ledger.status())
                return
            if path == "/node":
                self.send_json(self.ledger.node_status())
                return
            if path == "/policy":
                self.send_json(self.ledger.consensus_policy())
                return
            if path == "/validators":
                self.send_json(self.ledger.validator_policy())
                return
            if path == "/checkpoint/quorum":
                self.send_json(self.ledger.checkpoint_quorum())
                return
            if path == "/checkpoint/votes":
                status = (query.get("status") or [None])[0]
                height = (query.get("height") or [None])[0]
                block_hash = (query.get("block_hash") or [None])[0]
                limit = int((query.get("limit") or ["50"])[0])
                self.send_json({"votes": self.ledger.checkpoint_votes(status, height, block_hash, limit)})
                return
            if path == "/chain/manifest":
                self.send_json(self.ledger.chain_manifest())
                return
            if path == "/chain/snapshot":
                include_service_data = (query.get("service_data") or ["1"])[0] not in ("0", "false", "False", "no")
                self.send_json(self.ledger.chain_snapshot(include_service_data))
                return
            if path == "/audit":
                result = self.ledger.audit()
                self.send_json(result, 200 if result["valid"] else 500)
                return
            if path == "/readiness":
                self.send_json(self.ledger.mainnet_readiness())
                return
            if path == "/blocks":
                limit = int((query.get("limit") or ["25"])[0])
                self.send_json({"blocks": self.ledger.recent_blocks(limit)})
                return
            if path.startswith("/block/"):
                ref = path.removeprefix("/block/")
                result = self.ledger.block(ref)
                if not result:
                    self.send_json({"error": "SpaceCash block not found."}, 404)
                    return
                self.send_json(result)
                return
            if path.startswith("/tx/") and path.endswith("/proof"):
                txid = path.removeprefix("/tx/").removesuffix("/proof").strip("/")
                try:
                    result = self.ledger.transaction_proof(txid)
                except ValueError as exc:
                    self.send_json({"error": str(exc)}, 500)
                    return
                if not result:
                    self.send_json({"error": "SpaceCash transaction not found."}, 404)
                    return
                self.send_json(result, 200 if result.get("verified") else 409)
                return
            if path.startswith("/tx/"):
                txid = path.removeprefix("/tx/")
                result = self.ledger.transaction(txid)
                if not result:
                    self.send_json({"error": "SpaceCash transaction not found."}, 404)
                    return
                self.send_json(result)
                return
            if path.startswith("/wallet/"):
                address = path.removeprefix("/wallet/")
                try:
                    result = self.ledger.wallet_summary(address)
                except ValueError as exc:
                    self.send_json({"error": str(exc)}, 404)
                    return
                self.send_json(result)
                return
            if path == "/mempool":
                status = (query.get("status") or ["pending"])[0]
                sender = (query.get("sender") or [None])[0]
                limit = int((query.get("limit") or ["25"])[0])
                self.send_json({"pending": self.ledger.pending_transactions(status, sender, limit)})
                return
            if path == "/peers":
                status = (query.get("status") or [None])[0]
                limit = int((query.get("limit") or ["100"])[0])
                self.send_json({"peers": self.ledger.peers(status, limit)})
                return
            if path == "/bootstrap-peers":
                self.send_json(self.ledger.bootstrap_peers())
                return
            if path == "/sync-candidates":
                status = (query.get("status") or [None])[0]
                limit = int((query.get("limit") or ["25"])[0])
                self.send_json({"candidates": self.ledger.sync_candidates(status, limit)})
                return
            if path.startswith("/sync-candidate/"):
                candidate_id = path.removeprefix("/sync-candidate/")
                result = self.ledger.sync_candidate(candidate_id)
                if not result:
                    self.send_json({"error": "SpaceCash sync candidate not found."}, 404)
                    return
                self.send_json(result)
                return
            if path == "/sync-imports":
                status = (query.get("status") or [None])[0]
                limit = int((query.get("limit") or ["25"])[0])
                self.send_json({"imports": self.ledger.sync_imports(status, limit)})
                return
            if path.startswith("/mempool/"):
                pending_id = path.removeprefix("/mempool/")
                result = self.ledger.pending_transaction(pending_id)
                if not result:
                    self.send_json({"error": "SpaceCash pending transaction not found."}, 404)
                    return
                self.send_json(result)
                return
            if path == "/orders":
                wallet = (query.get("wallet") or [None])[0]
                status = (query.get("status") or [None])[0]
                limit = int((query.get("limit") or ["25"])[0])
                self.send_json({"orders": self.ledger.product_orders(wallet, status, limit)})
                return
            if path.startswith("/order/"):
                receipt_id = path.removeprefix("/order/")
                if receipt_id.endswith("/events"):
                    receipt_id = receipt_id.removesuffix("/events").strip("/")
                    limit = int((query.get("limit") or ["50"])[0])
                    self.send_json({"events": self.ledger.product_order_events(receipt_id, limit)})
                    return
                result = self.ledger.product_order(receipt_id)
                if not result:
                    self.send_json({"error": "SpaceCash product order not found."}, 404)
                    return
                self.send_json(result)
                return
            self.not_found()
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)
        except Exception as exc:
            self.send_json({"error": f"SpaceCash daemon error: {exc}"}, 500)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            payload = self.read_json()
            if path == "/node/label":
                self.send_json(self.ledger.set_node_label(payload.get("label") or "SpaceCash Local Devnet Node"))
                return
            if path == "/policy/producers":
                producers = payload.get("producers") if isinstance(payload, dict) else payload
                self.send_json(self.ledger.set_allowed_producers(producers or []))
                return
            if path == "/policy/producers/add":
                self.send_json(self.ledger.add_allowed_producer(payload.get("producer_id") or payload.get("producer")))
                return
            if path == "/validators":
                validators = payload.get("validators") if isinstance(payload, dict) else payload
                quorum = payload.get("quorum") if isinstance(payload, dict) else None
                self.send_json(self.ledger.set_validators(validators or [], quorum))
                return
            if path == "/validators/add":
                self.send_json(self.ledger.add_validator(payload.get("address") or payload.get("validator")))
                return
            if path == "/validators/quorum":
                self.send_json(self.ledger.set_validator_quorum(payload.get("quorum")))
                return
            if path == "/checkpoint/payload":
                self.send_json(self.ledger.checkpoint_vote_payload(payload.get("validator") or payload.get("address")))
                return
            if path == "/checkpoint/vote":
                self.send_json(self.ledger.submit_checkpoint_vote(payload))
                return
            if path == "/bootstrap-peers":
                peers = payload.get("peers") if isinstance(payload, dict) else payload
                self.send_json(self.ledger.set_bootstrap_peers(peers or []))
                return
            if path == "/bootstrap-peers/add":
                self.send_json(self.ledger.add_bootstrap_peer(
                    payload.get("url"),
                    payload.get("label") or "bootstrap",
                    payload.get("notes") or "Configured bootstrap peer.",
                ))
                return
            if path == "/bootstrap-peers/load":
                self.send_json(self.ledger.load_bootstrap_peers(
                    check=bool(payload.get("check")),
                    timeout=payload.get("timeout") or 5,
                    snapshot=bool(payload.get("snapshot") or payload.get("verify_snapshot")),
                ))
                return
            if path == "/chain/verify":
                snapshot = payload.get("snapshot") if isinstance(payload, dict) and "snapshot" in payload else payload
                result = self.ledger.verify_chain_snapshot(snapshot)
                self.send_json(result, 200 if result["valid"] else 400)
                return
            if path == "/chain/fork-choice":
                snapshot = payload.get("snapshot") if isinstance(payload, dict) and "snapshot" in payload else payload
                result = self.ledger.evaluate_chain_snapshot(snapshot)
                self.send_json(result, 200 if result.get("snapshot_valid") else 400)
                return
            if path == "/peers":
                self.send_json(self.ledger.add_peer(
                    payload.get("url"),
                    payload.get("label") or "",
                    payload.get("notes") or "",
                ))
                return
            if path == "/peers/record":
                self.send_json(self.ledger.record_peer_manifest(
                    payload.get("url"),
                    payload.get("manifest") or {},
                    payload.get("status") or "seen",
                ))
                return
            if path == "/peers/check":
                self.send_json(self.ledger.check_peer(
                    payload.get("url"),
                    payload.get("timeout") or 5,
                    bool(payload.get("snapshot") or payload.get("verify_snapshot")),
                ))
                return
            if path == "/peers/check-all":
                self.send_json(self.ledger.check_peers(
                    payload.get("timeout") or 5,
                    bool(payload.get("snapshot") or payload.get("verify_snapshot")),
                ))
                return
            if path == "/peers/gossip":
                self.send_json(self.ledger.gossip_peers(
                    timeout=payload.get("timeout") or 5,
                    check=bool(payload.get("check")),
                    snapshot=bool(payload.get("snapshot") or payload.get("verify_snapshot")),
                    max_new=payload.get("max_new") or payload.get("limit") or 100,
                ))
                return
            if path == "/peers/fork-choice":
                self.send_json(self.ledger.peer_sync_preview(
                    payload.get("url"),
                    payload.get("timeout") or 5,
                    store=False,
                ))
                return
            if path == "/peers/sync-preview":
                self.send_json(self.ledger.peer_sync_preview(
                    payload.get("url"),
                    payload.get("timeout") or 5,
                    store=payload.get("store", True) is not False,
                ))
                return
            if path == "/peers/sync-preview-all":
                self.send_json(self.ledger.peers_sync_preview(
                    payload.get("timeout") or 5,
                    store=payload.get("store", True) is not False,
                ))
                return
            if path == "/peers/sync-import":
                result = self.ledger.peer_sync_import(
                    payload.get("url"),
                    payload.get("timeout") or 5,
                    confirm=bool(payload.get("confirm") or payload.get("yes") or payload.get("apply")),
                    backup=payload.get("backup", True) is not False,
                    allow_legacy_unsigned=bool(payload.get("allow_legacy_unsigned")),
                )
                status = 200 if result.get("imported") or not result.get("requires_confirmation") else 202
                self.send_json(result, status)
                return
            if path == "/wallet/new":
                self.send_json(self.ledger.create_wallet(payload.get("label") or "Browser Wallet"))
                return
            if path == "/wallet/register":
                self.send_json(self.ledger.register_wallet(payload.get("public_key_jwk") or payload.get("jwk"), payload.get("label") or "Signed Browser Wallet"))
                return
            if path == "/faucet":
                self.send_json(self.ledger.faucet(payload.get("address"), payload.get("amount")))
                return
            if path == "/transfer":
                self.send_json(self.ledger.transfer(payload))
                return
            if path == "/redeem":
                self.send_json(self.ledger.redeem(payload))
                return
            if path == "/pay":
                source_payload = self.ledger._spend_source(payload)
                source = str(source_payload.get("source") or "").strip().lower()
                product_id = int(source_payload.get("product_id") or source_payload.get("id") or 0)
                product = self.catalog.require_spacecash_product(source, product_id)
                self.send_json(self.ledger.product_redeem(payload, product))
                return
            if path == "/mempool/transfer":
                self.send_json(self.ledger.submit_transfer(payload))
                return
            if path == "/mempool/redeem":
                self.send_json(self.ledger.submit_redeem(payload))
                return
            if path == "/mempool/pay":
                source_payload = self.ledger._spend_source(payload)
                source = str(source_payload.get("source") or "").strip().lower()
                product_id = int(source_payload.get("product_id") or source_payload.get("id") or 0)
                product = self.catalog.require_spacecash_product(source, product_id)
                self.send_json(self.ledger.submit_product_redeem(payload, product))
                return
            if path == "/mempool/mine":
                self.send_json(self.ledger.mine_pending_transactions(payload.get("limit") or 25))
                return
            if path == "/orders/backfill":
                self.send_json(self.ledger.backfill_product_orders(
                    product_lookup=self.catalog.lookup_checkout_product,
                    actor=payload.get("actor") or "operator",
                ))
                return
            if path.startswith("/order/") and path.endswith("/status"):
                receipt_id = path.removeprefix("/order/").removesuffix("/status").strip("/")
                self.send_json(self.ledger.update_product_order(
                    receipt_id,
                    payload.get("status"),
                    payload.get("fulfillment_status"),
                    payload.get("contact_status"),
                    payload.get("notes") or "",
                    payload.get("actor") or "operator",
                ))
                return
            self.not_found()
        except ProductNotFound as exc:
            self.send_json({"error": str(exc)}, 404)
        except ProductNotEligible as exc:
            self.send_json({"error": str(exc)}, 400)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)
        except Exception as exc:
            self.send_json({"error": f"SpaceCash daemon error: {exc}"}, 500)


class SpaceCashHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address, handler_class, ledger, catalog):
        super().__init__(server_address, handler_class)
        self.ledger = ledger
        self.catalog = catalog


def build_parser():
    parser = argparse.ArgumentParser(description="Run the SpaceCash devnet daemon")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8876, help="Bind port")
    parser.add_argument("--db", default=str(default_db_path()), help="Path to SpaceCash SQLite ledger")
    parser.add_argument("--prime-db", default=str(default_prime_db_path()), help="Path to NorthStar Prime catalog SQLite DB")
    parser.add_argument("--chromatic-db", default=str(default_chromatic_db_path()), help="Path to Chromatic catalog SQLite DB")
    parser.add_argument("--ignore-interrupt", action="store_true", help="Keep serving if a detached launch receives a console interrupt")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    Path(args.db).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    ledger = SpaceCashLedger(args.db)
    catalog = NorthStarCatalog(args.prime_db, args.chromatic_db)
    ledger.ensure_schema()
    server = SpaceCashHTTPServer((args.host, args.port), SpaceCashDaemonHandler, ledger, catalog)
    try:
        print(f"SpaceCash daemon on http://{args.host}:{args.port} using {Path(args.db).resolve()}", flush=True)
    except (AttributeError, OSError, ValueError):
        pass
    try:
        while True:
            try:
                server.serve_forever()
                break
            except KeyboardInterrupt:
                if not args.ignore_interrupt:
                    break
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
