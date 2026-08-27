"""SpaceCash standalone devnet CLI."""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spacecash_core import SpaceCashLedger  # noqa: E402
from spacecash_core import protocol  # noqa: E402
from tools.spacecash_genesis_allocation import load_allocation, genesis_allocation_template, validate_allocation  # noqa: E402
from tools.spacecash_legal_compliance_evidence import load_legal_compliance_evidence, legal_compliance_evidence_template, validate_legal_compliance_evidence  # noqa: E402
from tools.spacecash_mainnet_decision import load_mainnet_decision, mainnet_decision_template, validate_mainnet_decision  # noqa: E402
from tools.spacecash_production_deployment_evidence import load_production_deployment_evidence, production_deployment_evidence_template, validate_production_deployment_evidence  # noqa: E402
from tools.spacecash_security_review_evidence import load_security_review_evidence, security_review_evidence_template, validate_security_review_evidence  # noqa: E402
from tools.spacecash_wallet_custody_evidence import load_wallet_custody_evidence, wallet_custody_evidence_template, validate_wallet_custody_evidence  # noqa: E402


def default_db_path():
    app_data = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return Path(os.environ.get("SPACECASH_DB", str(app_data / "SpaceCash" / "spacecash_devnet.sqlite3")))


def print_json(data):
    print(json.dumps(data, indent=2, sort_keys=True))


def load_json_arg(value):
    if not value:
        return {}
    text = str(value)
    if text.startswith("@"):
        text = Path(text[1:]).read_text(encoding="utf-8")
    return json.loads(text)


def build_parser():
    parser = argparse.ArgumentParser(description="SpaceCash devnet ledger CLI")
    parser.add_argument("--db", default=str(default_db_path()), help="Path to SpaceCash SQLite ledger")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("config", help="Show protocol config")
    sub.add_parser("consensus-spec", help="Show the deterministic consensus specification")
    sub.add_parser("monetary-policy", help="Show the deterministic monetary policy")
    sub.add_parser("genesis-plan", help="Show the deterministic genesis/allocation boundary plan")
    genesis_allocation = sub.add_parser("genesis-allocation", help="Show or verify a genesis allocation file")
    genesis_allocation.add_argument("--verify", type=Path, help="Allocation JSON file to verify")
    genesis_allocation.add_argument("--require-approved", action="store_true", help="Fail unless the allocation is approved and supply-complete")
    security_review_evidence = sub.add_parser("security-review-evidence", help="Show or verify external security-review closure evidence")
    security_review_evidence.add_argument("--verify", type=Path, help="Security-review evidence JSON file to verify")
    security_review_evidence.add_argument("--require-complete", action="store_true", help="Fail unless the external security review gate is complete")
    legal_compliance_evidence = sub.add_parser("legal-compliance-evidence", help="Show or verify legal/compliance review evidence")
    legal_compliance_evidence.add_argument("--verify", type=Path, help="Legal/compliance evidence JSON file to verify")
    legal_compliance_evidence.add_argument("--require-complete", action="store_true", help="Fail unless the legal/compliance gate is complete")
    wallet_custody_evidence = sub.add_parser("wallet-custody-evidence", help="Show or verify wallet recovery/custody evidence")
    wallet_custody_evidence.add_argument("--verify", type=Path, help="Wallet recovery/custody evidence JSON file to verify")
    wallet_custody_evidence.add_argument("--require-complete", action="store_true", help="Fail unless the wallet recovery/custody gate is complete")
    production_deployment_evidence = sub.add_parser("production-deployment-evidence", help="Show or verify production deployment evidence")
    production_deployment_evidence.add_argument("--verify", type=Path, help="Production deployment evidence JSON file to verify")
    production_deployment_evidence.add_argument("--require-complete", action="store_true", help="Fail unless the production deployment gate is complete")
    mainnet_decision = sub.add_parser("mainnet-decision", help="Show or verify final mainnet decision evidence")
    mainnet_decision.add_argument("--verify", type=Path, help="Mainnet decision evidence JSON file to verify")
    mainnet_decision.add_argument("--require-complete", action="store_true", help="Fail unless the final mainnet decision is complete")
    sub.add_parser("wallet-policy", help="Show the deterministic wallet recovery/custody policy")
    sub.add_parser("status", help="Show ledger status")
    sub.add_parser("node", help="Show node identity and chain manifest")
    node_label = sub.add_parser("node-label", help="Set local node label")
    node_label.add_argument("label")
    sub.add_parser("policy", help="Show local consensus, producer, and bootstrap policy")
    producers = sub.add_parser("producers", help="Show allowed block producers")
    producers_set = sub.add_parser("producers-set", help="Replace allowed block producers")
    producers_set.add_argument("producers", nargs="*", help="Producer ids")
    producers_set.add_argument("--json", help="JSON list or @path")
    producer_add = sub.add_parser("producer-add", help="Add one allowed block producer")
    producer_add.add_argument("producer_id")
    sub.add_parser("validators", help="Show validator checkpoint voting policy")
    validators_set = sub.add_parser("validators-set", help="Replace validator wallet addresses")
    validators_set.add_argument("validators", nargs="*", help="Validator SpaceCash wallet addresses")
    validators_set.add_argument("--json", help="JSON list or @path")
    validators_set.add_argument("--quorum", type=int)
    validator_add = sub.add_parser("validator-add", help="Add one validator wallet address")
    validator_add.add_argument("address")
    validator_quorum = sub.add_parser("validator-quorum", help="Set validator checkpoint quorum")
    validator_quorum.add_argument("quorum", type=int)
    checkpoint_payload = sub.add_parser("checkpoint-payload", help="Build the current-tip checkpoint vote payload for a validator")
    checkpoint_payload.add_argument("validator")
    checkpoint_vote = sub.add_parser("checkpoint-vote", help="Submit a signed checkpoint vote JSON body")
    checkpoint_vote.add_argument("--json", required=True, help="JSON body or @path")
    checkpoint_votes = sub.add_parser("checkpoint-votes", help="List signed checkpoint votes")
    checkpoint_votes.add_argument("--status")
    checkpoint_votes.add_argument("--height", type=int)
    checkpoint_votes.add_argument("--block-hash")
    checkpoint_votes.add_argument("--limit", type=int, default=50)
    sub.add_parser("checkpoint-quorum", help="Show current-tip checkpoint vote quorum")
    bootstrap = sub.add_parser("bootstrap-peers", help="Show configured bootstrap peers")
    bootstrap_set = sub.add_parser("bootstrap-set", help="Replace configured bootstrap peers")
    bootstrap_set.add_argument("urls", nargs="*", help="Bootstrap peer URLs")
    bootstrap_set.add_argument("--json", help="JSON list or @path")
    bootstrap_add = sub.add_parser("bootstrap-add", help="Add and register one bootstrap peer")
    bootstrap_add.add_argument("url")
    bootstrap_add.add_argument("--label", default="bootstrap")
    bootstrap_add.add_argument("--notes", default="Configured bootstrap peer.")
    bootstrap_load = sub.add_parser("bootstrap-load", help="Register configured bootstrap peers")
    bootstrap_load.add_argument("--check", action="store_true", help="Check bootstrap peers after registering")
    bootstrap_load.add_argument("--snapshot", action="store_true", help="Fetch snapshots during bootstrap checks")
    bootstrap_load.add_argument("--timeout", type=int, default=5)
    sub.add_parser("chain-manifest", help="Show chain sync manifest")
    snapshot = sub.add_parser("chain-snapshot", help="Export full chain snapshot")
    snapshot.add_argument("--no-service-data", action="store_true")
    verify = sub.add_parser("chain-verify", help="Verify a chain snapshot JSON body")
    verify.add_argument("--json", required=True, help="JSON body or @path")
    fork_choice = sub.add_parser("fork-choice", help="Evaluate fork-choice policy for a chain snapshot")
    fork_choice.add_argument("--json", required=True, help="Snapshot JSON body or @path")
    fork_choice.add_argument("--full", action="store_true", help="Print the full snapshot evaluation")
    sub.add_parser("audit", help="Run integrity audit")
    readiness = sub.add_parser("readiness", help="Show mainnet readiness gates and blockers")
    readiness.add_argument("--require-mainnet", action="store_true", help="Exit non-zero unless every automated and manual gate is clear")
    blocks = sub.add_parser("blocks", help="Show recent blocks")
    blocks.add_argument("--limit", type=int, default=25)
    block = sub.add_parser("block", help="Show one block by height or hash")
    block.add_argument("ref")
    tx = sub.add_parser("tx", help="Show one transaction")
    tx.add_argument("txid")
    tx_proof = sub.add_parser("tx-proof", help="Show a transaction Merkle inclusion proof")
    tx_proof.add_argument("txid")
    mempool = sub.add_parser("mempool", help="Show pending mempool transactions")
    mempool.add_argument("--status", default="pending")
    mempool.add_argument("--sender")
    mempool.add_argument("--limit", type=int, default=25)
    pending = sub.add_parser("mempool-tx", help="Show one pending mempool transaction")
    pending.add_argument("pending_id")
    mine = sub.add_parser("mempool-mine", help="Mine pending mempool transactions")
    mine.add_argument("--limit", type=int, default=25)
    submit_transfer = sub.add_parser("mempool-transfer", help="Queue a signed transfer JSON payload")
    submit_transfer.add_argument("--json", required=True, help="JSON body or @path")
    submit_redeem = sub.add_parser("mempool-redeem", help="Queue a signed redemption JSON payload")
    submit_redeem.add_argument("--json", required=True, help="JSON body or @path")
    peers = sub.add_parser("peers", help="List registered node peers")
    peers.add_argument("--status")
    peers.add_argument("--limit", type=int, default=100)
    peer_add = sub.add_parser("peer-add", help="Register a node peer URL")
    peer_add.add_argument("url")
    peer_add.add_argument("--label", default="")
    peer_add.add_argument("--notes", default="")
    peer_seen = sub.add_parser("peer-record", help="Record a peer manifest JSON body")
    peer_seen.add_argument("url")
    peer_seen.add_argument("--json", required=True, help="Manifest JSON body or @path")
    peer_seen.add_argument("--status", default="seen")
    peer_check = sub.add_parser("peer-check", help="Fetch and compare a peer manifest")
    peer_check.add_argument("url")
    peer_check.add_argument("--timeout", type=int, default=5)
    peer_check.add_argument("--snapshot", action="store_true", help="Also fetch and verify peer snapshot")
    peers_check = sub.add_parser("peers-check", help="Fetch and compare all registered peers")
    peers_check.add_argument("--timeout", type=int, default=5)
    peers_check.add_argument("--snapshot", action="store_true", help="Also fetch and verify peer snapshots")
    peer_gossip = sub.add_parser("peer-gossip", help="Discover and register peers advertised by known peers")
    peer_gossip.add_argument("--timeout", type=int, default=5)
    peer_gossip.add_argument("--check", action="store_true", help="Check newly discovered peers after registering")
    peer_gossip.add_argument("--snapshot", action="store_true", help="Fetch snapshots when checking newly discovered peers")
    peer_gossip.add_argument("--max-new", type=int, default=100)
    sync_candidates = sub.add_parser("sync-candidates", help="List recorded peer snapshot sync previews")
    sync_candidates.add_argument("--status")
    sync_candidates.add_argument("--limit", type=int, default=25)
    sync_candidate = sub.add_parser("sync-candidate", help="Show one recorded peer snapshot sync preview")
    sync_candidate.add_argument("candidate_id")
    peer_sync = sub.add_parser("peer-sync-preview", help="Fetch, verify, and evaluate a peer snapshot without importing it")
    peer_sync.add_argument("url")
    peer_sync.add_argument("--timeout", type=int, default=5)
    peer_sync.add_argument("--no-store", action="store_true", help="Do not record a sync candidate row")
    peer_fork = sub.add_parser("peer-fork-choice", help="Fetch a peer snapshot and show fork-choice policy")
    peer_fork.add_argument("url")
    peer_fork.add_argument("--timeout", type=int, default=5)
    peer_fork.add_argument("--full", action="store_true", help="Print the full peer sync preview")
    peers_sync = sub.add_parser("peers-sync-preview", help="Evaluate all registered peer snapshots without importing them")
    peers_sync.add_argument("--timeout", type=int, default=5)
    peers_sync.add_argument("--no-store", action="store_true", help="Do not record sync candidate rows")
    sync_imports = sub.add_parser("sync-imports", help="List guarded peer snapshot imports")
    sync_imports.add_argument("--status")
    sync_imports.add_argument("--limit", type=int, default=25)
    peer_import = sub.add_parser("peer-sync-import", help="Import a verified append-only peer snapshot")
    peer_import.add_argument("url")
    peer_import.add_argument("--timeout", type=int, default=5)
    peer_import.add_argument("--yes", action="store_true", help="Actually import if the peer is a verified append-only candidate")
    peer_import.add_argument("--no-backup", action="store_true", help="Disable pre-import SQLite backup")
    peer_import.add_argument("--allow-legacy-unsigned", action="store_true", help="Allow legacy unsigned spend imports for devnet catch-up only")
    orders = sub.add_parser("orders", help="Show product redemption receipt records")
    orders.add_argument("--wallet")
    orders.add_argument("--status")
    orders.add_argument("--limit", type=int, default=25)
    order = sub.add_parser("order", help="Show one product redemption receipt")
    order.add_argument("receipt_id")
    events = sub.add_parser("order-events", help="Show product redemption receipt events")
    events.add_argument("receipt_id")
    events.add_argument("--limit", type=int, default=50)
    backfill = sub.add_parser("orders-backfill", help="Create missing product redemption receipt records")
    backfill.add_argument("--actor", default="operator")
    update = sub.add_parser("order-update", help="Update a product redemption receipt")
    update.add_argument("receipt_id")
    update.add_argument("--status")
    update.add_argument("--fulfillment-status")
    update.add_argument("--contact-status")
    update.add_argument("--notes", default="")
    update.add_argument("--actor", default="operator")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    Path(args.db).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    ledger = SpaceCashLedger(args.db)
    if args.command == "config":
        print_json(protocol.chain_config())
        return 0
    if args.command == "consensus-spec":
        print_json(protocol.consensus_spec())
        return 0
    if args.command == "monetary-policy":
        print_json(protocol.monetary_policy())
        return 0
    if args.command == "genesis-plan":
        print_json(protocol.genesis_plan())
        return 0
    if args.command == "genesis-allocation":
        if args.verify:
            result = validate_allocation(load_allocation(args.verify), require_approved=args.require_approved)
            print_json(result)
            return 0 if result.get("ok") and (not args.require_approved or result.get("allocation_ready")) else 2
        print_json(genesis_allocation_template())
        return 0
    if args.command == "security-review-evidence":
        if args.verify:
            result = validate_security_review_evidence(
                load_security_review_evidence(args.verify),
                require_complete=args.require_complete,
            )
            print_json(result)
            return 0 if result.get("ok") and (not args.require_complete or result.get("external_security_review_ready")) else 2
        print_json(security_review_evidence_template())
        return 0
    if args.command == "legal-compliance-evidence":
        if args.verify:
            result = validate_legal_compliance_evidence(
                load_legal_compliance_evidence(args.verify),
                require_complete=args.require_complete,
            )
            print_json(result)
            return 0 if result.get("ok") and (not args.require_complete or result.get("legal_compliance_ready")) else 2
        print_json(legal_compliance_evidence_template())
        return 0
    if args.command == "wallet-custody-evidence":
        if args.verify:
            result = validate_wallet_custody_evidence(
                load_wallet_custody_evidence(args.verify),
                require_complete=args.require_complete,
            )
            print_json(result)
            return 0 if result.get("ok") and (not args.require_complete or result.get("wallet_custody_ready")) else 2
        print_json(wallet_custody_evidence_template())
        return 0
    if args.command == "production-deployment-evidence":
        if args.verify:
            result = validate_production_deployment_evidence(
                load_production_deployment_evidence(args.verify),
                require_complete=args.require_complete,
            )
            print_json(result)
            return 0 if result.get("ok") and (not args.require_complete or result.get("deployment_ready")) else 2
        print_json(production_deployment_evidence_template())
        return 0
    if args.command == "mainnet-decision":
        if args.verify:
            result = validate_mainnet_decision(
                load_mainnet_decision(args.verify),
                require_complete=args.require_complete,
            )
            print_json(result)
            return 0 if result.get("ok") and (not args.require_complete or result.get("mainnet_decision_ready")) else 2
        print_json(mainnet_decision_template())
        return 0
    if args.command == "wallet-policy":
        print_json(protocol.wallet_policy())
        return 0
    if args.command == "status":
        print_json(ledger.status())
        return 0
    if args.command == "node":
        print_json(ledger.node_status())
        return 0
    if args.command == "node-label":
        print_json(ledger.set_node_label(args.label))
        return 0
    if args.command == "policy":
        print_json(ledger.consensus_policy())
        return 0
    if args.command == "producers":
        print_json({"allowed_producers": ledger.consensus_policy()["allowed_producers"]})
        return 0
    if args.command == "producers-set":
        try:
            producers = load_json_arg(args.json) if args.json else args.producers
            print_json(ledger.set_allowed_producers(producers))
            return 0
        except (json.JSONDecodeError, ValueError) as exc:
            print_json({"error": str(exc)})
            return 1
    if args.command == "producer-add":
        try:
            print_json(ledger.add_allowed_producer(args.producer_id))
            return 0
        except ValueError as exc:
            print_json({"error": str(exc)})
            return 1
    if args.command == "validators":
        print_json(ledger.validator_policy())
        return 0
    if args.command == "validators-set":
        try:
            validators = load_json_arg(args.json) if args.json else args.validators
            print_json(ledger.set_validators(validators, args.quorum))
            return 0
        except (json.JSONDecodeError, ValueError) as exc:
            print_json({"error": str(exc)})
            return 1
    if args.command == "validator-add":
        try:
            print_json(ledger.add_validator(args.address))
            return 0
        except ValueError as exc:
            print_json({"error": str(exc)})
            return 1
    if args.command == "validator-quorum":
        try:
            print_json(ledger.set_validator_quorum(args.quorum))
            return 0
        except ValueError as exc:
            print_json({"error": str(exc)})
            return 1
    if args.command == "checkpoint-payload":
        try:
            print_json(ledger.checkpoint_vote_payload(args.validator))
            return 0
        except ValueError as exc:
            print_json({"error": str(exc)})
            return 1
    if args.command == "checkpoint-vote":
        try:
            print_json(ledger.submit_checkpoint_vote(load_json_arg(args.json)))
            return 0
        except (json.JSONDecodeError, ValueError) as exc:
            print_json({"error": str(exc)})
            return 1
    if args.command == "checkpoint-votes":
        print_json({"votes": ledger.checkpoint_votes(args.status, args.height, args.block_hash, args.limit)})
        return 0
    if args.command == "checkpoint-quorum":
        print_json(ledger.checkpoint_quorum())
        return 0
    if args.command == "bootstrap-peers":
        print_json(ledger.bootstrap_peers())
        return 0
    if args.command == "bootstrap-set":
        try:
            peers = load_json_arg(args.json) if args.json else args.urls
            print_json(ledger.set_bootstrap_peers(peers))
            return 0
        except (json.JSONDecodeError, ValueError) as exc:
            print_json({"error": str(exc)})
            return 1
    if args.command == "bootstrap-add":
        try:
            print_json(ledger.add_bootstrap_peer(args.url, args.label, args.notes))
            return 0
        except ValueError as exc:
            print_json({"error": str(exc)})
            return 1
    if args.command == "bootstrap-load":
        print_json(ledger.load_bootstrap_peers(args.check, args.timeout, args.snapshot))
        return 0
    if args.command == "chain-manifest":
        print_json(ledger.chain_manifest())
        return 0
    if args.command == "chain-snapshot":
        print_json(ledger.chain_snapshot(include_service_data=not args.no_service_data))
        return 0
    if args.command == "chain-verify":
        try:
            result = ledger.verify_chain_snapshot(load_json_arg(args.json))
            print_json(result)
            return 0 if result["valid"] else 2
        except json.JSONDecodeError as exc:
            print_json({"error": str(exc)})
            return 1
    if args.command == "fork-choice":
        try:
            result = ledger.evaluate_chain_snapshot(load_json_arg(args.json))
            print_json(result if args.full else result.get("fork_choice"))
            return 0 if result.get("snapshot_valid") else 2
        except (json.JSONDecodeError, ValueError) as exc:
            print_json({"error": str(exc)})
            return 1
    if args.command == "audit":
        result = ledger.audit()
        print_json(result)
        return 0 if result["valid"] else 2
    if args.command == "readiness":
        result = ledger.mainnet_readiness()
        print_json(result)
        return 0 if (not args.require_mainnet or result["mainnet_ready"]) else 2
    if args.command == "blocks":
        print_json({"blocks": ledger.recent_blocks(args.limit)})
        return 0
    if args.command == "block":
        result = ledger.block(args.ref)
        if not result:
            print_json({"error": "SpaceCash block not found."})
            return 1
        print_json(result)
        return 0
    if args.command == "tx":
        result = ledger.transaction(args.txid)
        if not result:
            print_json({"error": "SpaceCash transaction not found."})
            return 1
        print_json(result)
        return 0
    if args.command == "tx-proof":
        try:
            result = ledger.transaction_proof(args.txid)
        except ValueError as exc:
            print_json({"error": str(exc)})
            return 2
        if not result:
            print_json({"error": "SpaceCash transaction not found."})
            return 1
        print_json(result)
        return 0 if result.get("verified") else 2
    if args.command == "mempool":
        print_json({"pending": ledger.pending_transactions(args.status, args.sender, args.limit)})
        return 0
    if args.command == "mempool-tx":
        result = ledger.pending_transaction(args.pending_id)
        if not result:
            print_json({"error": "SpaceCash pending transaction not found."})
            return 1
        print_json(result)
        return 0
    if args.command == "mempool-mine":
        print_json(ledger.mine_pending_transactions(args.limit))
        return 0
    if args.command == "mempool-transfer":
        try:
            print_json(ledger.submit_transfer(load_json_arg(args.json)))
            return 0
        except (json.JSONDecodeError, ValueError) as exc:
            print_json({"error": str(exc)})
            return 1
    if args.command == "mempool-redeem":
        try:
            print_json(ledger.submit_redeem(load_json_arg(args.json)))
            return 0
        except (json.JSONDecodeError, ValueError) as exc:
            print_json({"error": str(exc)})
            return 1
    if args.command == "peers":
        print_json({"peers": ledger.peers(args.status, args.limit)})
        return 0
    if args.command == "peer-add":
        try:
            print_json(ledger.add_peer(args.url, args.label, args.notes))
            return 0
        except ValueError as exc:
            print_json({"error": str(exc)})
            return 1
    if args.command == "peer-record":
        try:
            print_json(ledger.record_peer_manifest(args.url, load_json_arg(args.json), args.status))
            return 0
        except (json.JSONDecodeError, ValueError) as exc:
            print_json({"error": str(exc)})
            return 1
    if args.command == "peer-check":
        try:
            print_json(ledger.check_peer(args.url, args.timeout, args.snapshot))
            return 0
        except ValueError as exc:
            print_json({"error": str(exc)})
            return 1
    if args.command == "peers-check":
        print_json(ledger.check_peers(args.timeout, args.snapshot))
        return 0
    if args.command == "peer-gossip":
        print_json(ledger.gossip_peers(args.timeout, args.check, args.snapshot, args.max_new))
        return 0
    if args.command == "sync-candidates":
        print_json({"candidates": ledger.sync_candidates(args.status, args.limit)})
        return 0
    if args.command == "sync-candidate":
        result = ledger.sync_candidate(args.candidate_id)
        if not result:
            print_json({"error": "SpaceCash sync candidate not found."})
            return 1
        print_json(result)
        return 0
    if args.command == "peer-sync-preview":
        try:
            print_json(ledger.peer_sync_preview(args.url, args.timeout, store=not args.no_store))
            return 0
        except ValueError as exc:
            print_json({"error": str(exc)})
            return 1
    if args.command == "peer-fork-choice":
        try:
            result = ledger.peer_sync_preview(args.url, args.timeout, store=False)
            print_json(result if args.full else result.get("evaluation", {}).get("fork_choice"))
            return 0 if result.get("evaluation", {}).get("snapshot_valid") else 2
        except ValueError as exc:
            print_json({"error": str(exc)})
            return 1
    if args.command == "peers-sync-preview":
        print_json(ledger.peers_sync_preview(args.timeout, store=not args.no_store))
        return 0
    if args.command == "sync-imports":
        print_json({"imports": ledger.sync_imports(args.status, args.limit)})
        return 0
    if args.command == "peer-sync-import":
        try:
            result = ledger.peer_sync_import(
                args.url,
                args.timeout,
                confirm=args.yes,
                backup=not args.no_backup,
                allow_legacy_unsigned=args.allow_legacy_unsigned,
            )
            print_json(result)
            if result.get("imported") or result.get("status") in ("same", "peer_behind") or result.get("requires_confirmation"):
                return 0
            return 2
        except ValueError as exc:
            print_json({"error": str(exc)})
            return 1
    if args.command == "orders":
        print_json({"orders": ledger.product_orders(args.wallet, args.status, args.limit)})
        return 0
    if args.command == "order":
        result = ledger.product_order(args.receipt_id)
        if not result:
            print_json({"error": "SpaceCash product order not found."})
            return 1
        print_json(result)
        return 0
    if args.command == "order-events":
        print_json({"events": ledger.product_order_events(args.receipt_id, args.limit)})
        return 0
    if args.command == "orders-backfill":
        print_json(ledger.backfill_product_orders(actor=args.actor))
        return 0
    if args.command == "order-update":
        try:
            print_json(ledger.update_product_order(
                args.receipt_id,
                args.status,
                args.fulfillment_status,
                args.contact_status,
                args.notes,
                args.actor,
            ))
            return 0
        except ValueError as exc:
            print_json({"error": str(exc)})
            return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
