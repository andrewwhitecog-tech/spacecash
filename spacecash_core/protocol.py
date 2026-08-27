"""SpaceCash devnet protocol constants and deterministic helpers.

This module intentionally has no Flask dependency. It is the starting point for
moving SpaceCash toward a daemon/package boundary while the site keeps using the
existing integration.
"""

import base64
import hashlib
import json
import re
import secrets
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

SYMBOL = "SPACE"
UNIT = 1_000_000
DECIMALS = 6
CHAIN_ID = "spacecash-devnet-1"
SIGNED_PAYLOAD_VERSION = 1
WALLET_EXPORT_VERSION = 1
WALLET_EXPORT_KDF = "PBKDF2-SHA256-250000"
WALLET_EXPORT_CIPHER = "AES-256-GCM"
MONETARY_POLICY_VERSION = 1
MONETARY_POLICY_ID = "spacecash-devnet-monetary-policy-v1"
GENESIS_PLAN_VERSION = 1
GENESIS_PLAN_ID = "spacecash-devnet-genesis-plan-v1"
WALLET_POLICY_VERSION = 1
WALLET_POLICY_ID = "spacecash-devnet-wallet-policy-v1"
ADDRESS_VERSION = 1
ADDRESS_PREFIX = "SPACE"
MIN_BACKUP_PASSPHRASE_LENGTH = 12
BLOCK_VERSION = 2
PRODUCER_ID = "spacecash-devnet-producer-1"
NODE_PROTOCOL_VERSION = 1
CONSENSUS_SPEC_VERSION = 1
CONSENSUS_SPEC_ID = "spacecash-devnet-consensus-v1"
SYMBOLIC_VALUE_VERSION = 1
SYMBOLIC_VALUE_ID = "spacecash-vorath-symbolic-value-v1"
FORK_CHOICE_POLICY = "spacecash-devnet-append-only-v1"
PRODUCER_POLICY_VERSION = 1
DEFAULT_ALLOWED_PRODUCERS = (PRODUCER_ID,)
DEFAULT_BOOTSTRAP_PEERS = ()
VALIDATOR_POLICY_VERSION = 1
DEFAULT_VALIDATOR_QUORUM = 1
TREASURY = "SPACE-TREASURY"
GENESIS_UNITS = 1_000_000_000 * UNIT
FAUCET_UNITS = 250 * UNIT
USD_RATE = Decimal("1.00")
VORATH_VOID_CODE = "000"
VORATH_OVERLOAD_CODE = "999"
VORATH_COLLAPSE_CODE = "000999"
VORATH_COLLAPSE_INTEGER = int("999", 16)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def amount_to_units(amount):
    try:
        dec = Decimal(str(amount).strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError("Enter a valid SpaceCash amount.") from exc
    if dec <= 0:
        raise ValueError("SpaceCash amount must be greater than zero.")
    units = int((dec * UNIT).to_integral_value(rounding=ROUND_HALF_UP))
    if units <= 0:
        raise ValueError("SpaceCash amount is too small.")
    return units


def units_to_amount(units):
    dec = Decimal(int(units or 0)) / Decimal(UNIT)
    text = f"{dec:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def product_cost_units(price):
    price_dec = Decimal(str(price or 0))
    if price_dec <= 0:
        return 0
    return amount_to_units(price_dec / USD_RATE)


def valid_address(address):
    return bool(re.fullmatch(r"SPACE-[A-Z0-9-]{8,48}", address or ""))


def canonical_json(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def hash_text(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest().upper()


def payload_hash(data):
    return hash_text(canonical_json(data))


def merkle_root(txids):
    layer = [hash_text(txid) for txid in txids if txid]
    if not layer:
        return hash_text("")
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])
        layer = [hash_text(layer[i] + layer[i + 1]) for i in range(0, len(layer), 2)]
    return layer[0]


def merkle_proof(txids, target_txid):
    normalized = [str(txid).strip().upper() for txid in txids if str(txid or "").strip()]
    target = str(target_txid or "").strip().upper()
    if target not in normalized:
        raise ValueError("Transaction is not included in the supplied Merkle tree.")
    index = normalized.index(target)
    proof = []
    layer = [hash_text(txid) for txid in normalized]
    current_index = index
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])
        sibling_index = current_index ^ 1
        proof.append({
            "position": "left" if sibling_index < current_index else "right",
            "hash": layer[sibling_index],
        })
        current_index //= 2
        layer = [hash_text(layer[i] + layer[i + 1]) for i in range(0, len(layer), 2)]
    return {
        "txid": target,
        "index": index,
        "total": len(normalized),
        "leaf_hash": hash_text(target),
        "root": layer[0] if layer else hash_text(""),
        "proof": proof,
    }


def verify_merkle_proof(txid, proof, merkle_root_value):
    digest = hash_text(str(txid or "").strip().upper())
    for step in proof or []:
        position = str(step.get("position") or "").strip().lower()
        sibling = str(step.get("hash") or "").strip().upper()
        if not re.fullmatch(r"[0-9A-F]{64}", sibling):
            return False
        if position == "left":
            digest = hash_text(sibling + digest)
        elif position == "right":
            digest = hash_text(digest + sibling)
        else:
            return False
    return digest == str(merkle_root_value or "").strip().upper()


def txid(kind, sender, recipient, units):
    seed = f"{kind}|{sender}|{recipient}|{units}|{utc_now()}|{secrets.token_hex(16)}"
    return "SCTX-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24].upper()


def b64url_decode(value):
    text = str(value or "").strip()
    if not text:
        raise ValueError("Missing base64url value.")
    padding = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode((text + padding).encode("ascii"))
    except Exception as exc:
        raise ValueError("Invalid base64url value.") from exc


def b64url_encode(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def normalize_public_jwk(jwk):
    if isinstance(jwk, str):
        try:
            jwk = json.loads(jwk)
        except json.JSONDecodeError as exc:
            raise ValueError("Public key must be a JWK object.") from exc
    if not isinstance(jwk, dict):
        raise ValueError("Public key must be a JWK object.")
    normalized = {
        "crv": str(jwk.get("crv") or ""),
        "kty": str(jwk.get("kty") or ""),
        "x": str(jwk.get("x") or ""),
        "y": str(jwk.get("y") or ""),
    }
    if normalized["kty"] != "EC" or normalized["crv"] != "P-256":
        raise ValueError("SpaceCash signed wallets require an ECDSA P-256 public key.")
    x_bytes = b64url_decode(normalized["x"])
    y_bytes = b64url_decode(normalized["y"])
    if len(x_bytes) != 32 or len(y_bytes) != 32:
        raise ValueError("SpaceCash public key coordinates must be 32 bytes each.")
    return normalized


def address_from_public_jwk(jwk):
    normalized = normalize_public_jwk(jwk)
    digest = hashlib.sha256(canonical_json(normalized).encode("utf-8")).hexdigest().upper()
    return ADDRESS_PREFIX + "-" + digest[:32]


def block_hash(height, created_at, previous_hash, merkle_root, block_txid, tx_count):
    return hash_text(f"{int(height)}|{created_at}|{previous_hash}|{merkle_root}|{block_txid or ''}|{int(tx_count)}")


def symbolic_value():
    """Return the non-monetary VORATH easter-egg value artifact.

    This is intentionally outside ledger accounting. It is metadata for art,
    proofs, UI marks, and SpaceCash lore; it must never be used as spendable
    supply, exchange value, or a redemption promise.
    """
    sigma = VORATH_COLLAPSE_INTEGER
    artifact = {
        "id": SYMBOLIC_VALUE_ID,
        "version": SYMBOLIC_VALUE_VERSION,
        "chain_id": CHAIN_ID,
        "name": "Valueless Value",
        "scope": "Non-monetary symbolic layer for VORATH and SpaceCash artwork.",
        "axiom": "000 = 999",
        "recursive_time_mark": "retroactivelyforwardhencew()RTH",
        "canonical_expression": "SpaceCash_value = v + i*sigma",
        "accounting_rule": "ledger_value = Re(v + i*sigma) = v",
        "redemption_rule": "cash_value(i*sigma) = 0",
        "actual_value_component": {
            "symbol": "v",
            "meaning": "spendable ledger units only",
            "source": "SpaceCash transaction and balance tables",
        },
        "imaginary_value_component": {
            "symbol": "i*sigma",
            "meaning": "hidden symbolic signal; non-spendable, non-redeemable, non-financial",
            "sigma": sigma,
        },
        "encodings": {
            "void": VORATH_VOID_CODE,
            "overload": VORATH_OVERLOAD_CODE,
            "collapse": VORATH_COLLAPSE_CODE,
            "hex": "0x000999",
            "decimal": sigma,
            "binary": format(sigma, "012b"),
            "binary_24": format(sigma, "024b"),
            "octal": format(sigma, "o"),
            "base36": "1W9",
            "digital_root_decimal": 9,
            "digital_root_999": 9,
            "ascii_phrase_decimal": "48 48 48 61 57 57 57",
            "ascii_phrase_hex": "30 30 30 3D 39 39 39",
        },
        "fractal_embedding_rules": [
            "Embed 000999 in serial numbers, bill guilloche paths, coin rim ticks, metadata, filenames, and manifest hashes as an easter egg.",
            "Never present the symbolic component as spendable balance, market value, investment value, or redemption value.",
            "When a display can carry both values, show real ledger value normally and encode imaginary value only as sigil, metadata, or microtext.",
            "Retain the formula v + i*sigma in creator-facing docs so future assets preserve the real/imaginary boundary.",
            "Use retroactivelyforwardhencew()RTH as the creator-facing cue that old and new VORATH assets can inherit the same code without changing monetary accounting.",
        ],
        "vorath_formula": "000 = 999; VORATH = K(R(000)); SPACE = v + i*0x000999",
    }
    artifact["artifact_hash"] = hash_text(canonical_json({k: v for k, v in artifact.items() if k != "artifact_hash"}))
    return artifact


def symbolic_value_hash():
    return symbolic_value()["artifact_hash"]


def consensus_spec():
    spec = {
        "id": CONSENSUS_SPEC_ID,
        "version": CONSENSUS_SPEC_VERSION,
        "chain_id": CHAIN_ID,
        "mode": "local signed devnet",
        "node_protocol_version": NODE_PROTOCOL_VERSION,
        "scope": "Defines the current reviewable devnet consensus envelope. It is not a public mainnet consensus protocol.",
        "ledger": {
            "storage": "SQLite local ledger",
            "supply_units": GENESIS_UNITS,
            "treasury": TREASURY,
            "supply_invariant": "sum(wallet balances) must equal genesis supply after every audited transaction set",
            "monetary_policy": {
                "id": MONETARY_POLICY_ID,
                "version": MONETARY_POLICY_VERSION,
                "hash": monetary_policy_hash(),
            },
            "genesis_plan": {
                "id": GENESIS_PLAN_ID,
                "version": GENESIS_PLAN_VERSION,
                "hash": genesis_plan_hash(),
            },
        },
        "transactions": {
            "signed_payload_version": SIGNED_PAYLOAD_VERSION,
            "wallet_auth": "ECDSA P-256 over canonical JSON",
            "replay_domain": ["chain_id", "version", "action", "sender", "recipient/product_id", "amount", "nonce"],
            "nonce_rule": "settled signed spends and pending mempool entries must be unique per sender nonce",
            "mempool_rule": "pending spends reserve sender balance before mining",
        },
        "blocks": {
            "current_block_version": BLOCK_VERSION,
            "accepted_block_versions": [1, BLOCK_VERSION],
            "producer_id": PRODUCER_ID,
            "merkle_rule": "ordered txids are committed through a SHA-256 Merkle root",
            "hash_rule": "height, created_at, previous_hash, merkle_root, block_txid, and tx_count define the block hash",
        },
        "producer_policy": {
            "version": PRODUCER_POLICY_VERSION,
            "default_allowed_producers": list(DEFAULT_ALLOWED_PRODUCERS),
            "rule": "new versioned blocks must be produced by a locally allowed producer id",
            "legacy_devnet_compatibility": "legacy v1 blocks are audit-compatible on devnet but block mainnet readiness",
        },
        "fork_choice": {
            "id": FORK_CHOICE_POLICY,
            "rule": "higher validated height is importable only when the peer extends the local tip exactly",
            "automatic_reorgs": False,
            "diverged_peer_rule": "higher-scoring diverged peers are reported but not imported",
            "import_safety": ["snapshot verification", "producer allowlist", "append-only check", "pre-import backup", "post-import audit"],
        },
        "validator_checkpoints": {
            "version": VALIDATOR_POLICY_VERSION,
            "default_quorum": DEFAULT_VALIDATOR_QUORUM,
            "rule": "checkpoint votes must be signed by locally registered validator wallets",
            "payload_binding": ["chain_id", "height", "block_hash", "chain_digest", "validator"],
            "current_status": "checkpoint quorum is local evidence, not full Byzantine-fault-tolerant finality",
        },
        "network": {
            "bootstrap_peers": list(DEFAULT_BOOTSTRAP_PEERS),
            "peer_discovery": "configured/bootstrap peer gossip only",
            "sync_boundary": "peer HTTP APIs are untrusted until manifest, snapshot, producer policy, and append-only checks pass",
        },
        "mainnet_gaps": [
            "public validator enrollment and rotation",
            "slashing or removal rules",
            "authenticated peer identity and network abuse controls",
            "economic finality or BFT consensus",
            "automatic reorg policy",
            "public testnet evidence",
            "external audit closure",
        ],
    }
    spec["spec_hash"] = hash_text(canonical_json({k: v for k, v in spec.items() if k != "spec_hash"}))
    return spec


def consensus_spec_hash():
    return consensus_spec()["spec_hash"]


def wallet_policy():
    policy = {
        "id": WALLET_POLICY_ID,
        "version": WALLET_POLICY_VERSION,
        "chain_id": CHAIN_ID,
        "mode": "local signed devnet",
        "scope": "Defines the current wallet recovery and custody boundary. It is not a production custody approval.",
        "addressing": {
            "address_version": ADDRESS_VERSION,
            "address_prefix": ADDRESS_PREFIX,
            "address_rule": ADDRESS_PREFIX + "-" + "SHA256(canonical public JWK)[:32]",
            "chain_specific_replay_protection": "signed spends bind chain_id and payload version",
            "mainnet_gap": "final public mainnet address version and migration policy require review",
        },
        "signing": {
            "algorithm": "ECDSA P-256",
            "payload_format": "canonical JSON",
            "server_private_key_required": False,
            "server_private_key_storage_allowed": False,
            "registered_public_key_required_for_signed_spends": True,
        },
        "encrypted_backup": {
            "envelope_type": "spacecash-encrypted-wallet-backup",
            "wallet_export_version": WALLET_EXPORT_VERSION,
            "kdf": WALLET_EXPORT_KDF,
            "cipher": WALLET_EXPORT_CIPHER,
            "minimum_passphrase_length": MIN_BACKUP_PASSPHRASE_LENGTH,
            "private_key_material": "private JWK is allowed only inside encrypted browser backup JSON",
            "backup_rotation_status": "manual_user_export_only",
            "server_backup_storage_allowed": False,
        },
        "recovery": {
            "current_recovery_method": "encrypted browser wallet backup JSON",
            "recovery_phrase_standard": "not_implemented",
            "lost_key_policy": "no server recovery for lost browser private keys",
            "compromised_key_policy": "create a new wallet, stop using the compromised key, and record operational review before production",
            "user_backup_verification_status": "manual_export_import_flow_only",
        },
        "custody": {
            "current_model": "non_custodial_browser_devnet",
            "production_custody_status": "not_approved",
            "hardware_wallet_support": "not_implemented",
            "custodial_operations_allowed": False,
            "development_candidate_keys": "unsafe_for_custody",
        },
        "mainnet_gaps": [
            "recovery phrase or deterministic recovery standard",
            "final address version and migration policy",
            "backup rotation and verification workflow",
            "lost-key and compromised-key operating procedures",
            "hardware wallet or custody plan",
            "legal and operational custody review",
        ],
        "manual_gate": {
            "id": "wallet_recovery_custody_policy_complete",
            "status": "not_complete",
            "reason": "Production recovery, address versioning, backup rotation, hardware/custody, and operating procedures still require approval.",
        },
    }
    policy["policy_hash"] = hash_text(canonical_json({k: v for k, v in policy.items() if k != "policy_hash"}))
    return policy


def wallet_policy_hash():
    return wallet_policy()["policy_hash"]


def monetary_policy():
    policy = {
        "id": MONETARY_POLICY_ID,
        "version": MONETARY_POLICY_VERSION,
        "chain_id": CHAIN_ID,
        "mode": "local signed devnet",
        "scope": "Defines current SpaceCash devnet supply, issuance, fee, and treasury rules. It is not a public mainnet tokenomics approval.",
        "unit": {
            "symbol": SYMBOL,
            "decimals": DECIMALS,
            "base_unit": "micros",
            "units_per_coin": UNIT,
        },
        "symbolic_value_overlay": {
            "id": SYMBOLIC_VALUE_ID,
            "version": SYMBOLIC_VALUE_VERSION,
            "artifact_hash": symbolic_value_hash(),
            "formula": "SpaceCash_value = v + i*sigma",
            "sigma": VORATH_COLLAPSE_INTEGER,
            "canonical_code": "0x000999",
            "accounting_effect": "none",
            "redemption_value": 0,
            "disclosure": "The symbolic imaginary component is an art/lore easter egg, not spendable supply, market value, or a redemption promise.",
        },
        "supply": {
            "genesis_units": GENESIS_UNITS,
            "genesis_supply": units_to_amount(GENESIS_UNITS),
            "supply_cap_units": GENESIS_UNITS,
            "supply_cap": units_to_amount(GENESIS_UNITS),
            "supply_cap_rule": "Current protocol policy has no minting path after genesis.",
            "treasury": TREASURY,
        },
        "issuance": {
            "genesis_allocation": "100% of current devnet supply is allocated to the devnet treasury at genesis.",
            "block_reward_units": 0,
            "staking_reward_units": 0,
            "mining_enabled": False,
            "mint_route_available": False,
            "emission_schedule": "fixed genesis allocation only",
            "faucet_source": "treasury transfer only",
            "faucet_units": FAUCET_UNITS,
            "faucet_amount": units_to_amount(FAUCET_UNITS),
        },
        "fees": {
            "protocol_transfer_fee_units": 0,
            "protocol_transfer_fee": units_to_amount(0),
            "fee_market": "not_implemented",
            "burn_policy": "not_implemented",
            "checkout_reference_rate": f"1 {SYMBOL} = {USD_RATE} USD for devnet product checkout accounting",
            "mainnet_gap": "Final fees, burns, exchange-rate language, and market disclosures require legal/product review.",
        },
        "treasury_controls": {
            "current_treasury_model": "single devnet treasury address",
            "treasury_spend_path": "faucet and signed treasury transfers only",
            "multisig_status": "not_implemented",
            "vesting_or_distribution_schedule": "not_approved",
            "production_status": "not_approved",
        },
        "audit_controls": [
            "audit recomputes balances from transaction history",
            "audit checks total stored units equal genesis units",
            "release candidate requires zero legacy unsigned spends",
            "candidate builder proves fixed-supply accounting on a clean signed ledger",
        ],
        "mainnet_gaps": [
            "public distribution plan",
            "treasury governance or multisig controls",
            "fee/burn/reward policy",
            "market, tax, and legal disclosures",
            "exchange-rate and product-pricing policy",
            "mainnet genesis allocation approval",
        ],
        "manual_gate": {
            "id": "legal_compliance_review_complete",
            "status": "not_complete",
            "reason": "Public tokenomics, distribution, treasury controls, fee policy, and market disclosures still require legal/compliance/product approval.",
        },
    }
    policy["policy_hash"] = hash_text(canonical_json({k: v for k, v in policy.items() if k != "policy_hash"}))
    return policy


def monetary_policy_hash():
    return monetary_policy()["policy_hash"]


def genesis_plan():
    plan = {
        "id": GENESIS_PLAN_ID,
        "version": GENESIS_PLAN_VERSION,
        "chain_id": CHAIN_ID,
        "mode": "local signed devnet",
        "scope": "Defines the current reviewed boundary between historical devnet state, clean candidates, and any future mainnet genesis. It is not a mainnet allocation approval.",
        "source_of_truth": {
            "current_devnet_db": "spacecash_devnet.sqlite3 is historical local devnet state only",
            "release_candidate_db": "tools/spacecash_candidate.py builds a fresh signed-only candidate ledger for automated gate proof",
            "mainnet_genesis_source": "fresh reviewed genesis allocation file, not a mutation of historical devnet state",
            "devnet_history_carried_to_mainnet": False,
        },
        "allocation_boundary": {
            "supply_cap_units": GENESIS_UNITS,
            "supply_cap": units_to_amount(GENESIS_UNITS),
            "treasury_address": TREASURY,
            "allocation_file_status": "not_approved",
            "public_distribution_status": "not_approved",
            "treasury_governance_status": "not_approved",
            "devnet_wallet_balances_auto_migrate": False,
            "candidate_private_keys_allowed": False,
        },
        "required_mainnet_inputs": [
            "reviewed allocation file with address, amount, label, and basis",
            "allocation total exactly equals approved supply cap",
            "public distribution and treasury governance approval",
            "wallet address version and recovery policy approval",
            "legal/compliance approval for token/payment use",
            "release manifest source hash and bundle checksums",
        ],
        "migration_policy": {
            "legacy_unsigned_spends": "must not appear in a mainnet candidate",
            "devnet_orders": "historical product-order records are evidence only and do not create mainnet balances",
            "devnet_claim_tokens": "legacy claim-token compatibility is not accepted for mainnet allocation",
            "operator_action": "create a fresh reviewed candidate instead of editing historical devnet rows",
        },
        "review_checks": [
            "candidate ledger automated readiness has no blockers",
            "release bundle SHA256SUMS verifies",
            "monetary_policy.json hash matches protocol config",
            "wallet_policy.json hash matches protocol config",
            "allocation file totals match supply cap",
            "manual gates are signed off before any mainnet claim",
        ],
        "mainnet_gaps": [
            "approved allocation file",
            "allocation reviewer signoff",
            "public distribution plan",
            "treasury governance or multisig setup",
            "final mainnet chain id and address version",
            "legal/compliance approval",
        ],
        "manual_gate": {
            "id": "production_deployment_runbook_complete",
            "status": "not_complete",
            "reason": "A fresh reviewed genesis allocation, deployment archive, and rollback procedure are required before launch.",
        },
    }
    plan["plan_hash"] = hash_text(canonical_json({k: v for k, v in plan.items() if k != "plan_hash"}))
    return plan


def genesis_plan_hash():
    return genesis_plan()["plan_hash"]


def chain_config():
    return {
        "chain_id": CHAIN_ID,
        "symbol": SYMBOL,
        "decimals": DECIMALS,
        "signed_payload_version": SIGNED_PAYLOAD_VERSION,
        "wallet_export_version": WALLET_EXPORT_VERSION,
        "wallet_export_kdf": WALLET_EXPORT_KDF,
        "wallet_export_cipher": WALLET_EXPORT_CIPHER,
        "monetary_policy_id": MONETARY_POLICY_ID,
        "monetary_policy_version": MONETARY_POLICY_VERSION,
        "monetary_policy_hash": monetary_policy_hash(),
        "genesis_plan_id": GENESIS_PLAN_ID,
        "genesis_plan_version": GENESIS_PLAN_VERSION,
        "genesis_plan_hash": genesis_plan_hash(),
        "wallet_policy_id": WALLET_POLICY_ID,
        "wallet_policy_version": WALLET_POLICY_VERSION,
        "wallet_policy_hash": wallet_policy_hash(),
        "address_version": ADDRESS_VERSION,
        "base_unit": "micros",
        "supply_units": GENESIS_UNITS,
        "supply": units_to_amount(GENESIS_UNITS),
        "supply_cap_units": GENESIS_UNITS,
        "supply_cap": units_to_amount(GENESIS_UNITS),
        "treasury": TREASURY,
        "wallet_auth": "ECDSA P-256 over canonical JSON",
        "address_rule": ADDRESS_PREFIX + "-" + "SHA256(canonical public JWK)[:32]",
        "block_version": BLOCK_VERSION,
        "block_rule": "deterministic append-only local devnet batches with producer identity",
        "producer_id": PRODUCER_ID,
        "node_protocol_version": NODE_PROTOCOL_VERSION,
        "consensus_spec_id": CONSENSUS_SPEC_ID,
        "consensus_spec_version": CONSENSUS_SPEC_VERSION,
        "consensus_spec_hash": consensus_spec_hash(),
        "symbolic_value_id": SYMBOLIC_VALUE_ID,
        "symbolic_value_version": SYMBOLIC_VALUE_VERSION,
        "symbolic_value_hash": symbolic_value_hash(),
        "symbolic_value_code": "0x000999",
        "symbolic_value_rule": "SpaceCash ledger value is the real component v; the imaginary component i*0x000999 is non-monetary VORATH metadata.",
        "fork_choice_policy": FORK_CHOICE_POLICY,
        "producer_policy_version": PRODUCER_POLICY_VERSION,
        "validator_policy_version": VALIDATOR_POLICY_VERSION,
        "default_allowed_producers": list(DEFAULT_ALLOWED_PRODUCERS),
        "default_bootstrap_peers": list(DEFAULT_BOOTSTRAP_PEERS),
        "default_validator_quorum": DEFAULT_VALIDATOR_QUORUM,
        "snapshot_rule": "blocks, transactions, and registered wallet public keys are digested together",
        "fork_choice_rule": "higher validated height is only importable when the peer chain is an append-only extension of the local tip",
        "producer_policy_rule": "new versioned blocks must be produced by a locally allowed producer id",
        "validator_policy_rule": "checkpoint votes must be signed by locally registered validator wallets",
        "mode": "local signed devnet",
    }
