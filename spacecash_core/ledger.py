"""SQLite-backed SpaceCash devnet ledger and audit interface."""

import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import protocol

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, utils as crypto_utils
except ImportError:
    InvalidSignature = None
    hashes = None
    ec = None
    crypto_utils = None


class _SpaceCashNoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects so a validated peer cannot bounce into an internal service."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Peer redirects are not allowed.", headers, fp)


class SpaceCashLedger:
    """Standalone reader/auditor for the SpaceCash SQLite ledger."""

    ORDER_STATUSES = {"pending_review", "approved", "rejected", "cancelled", "completed"}
    FULFILLMENT_STATUSES = {"pending_review", "queued", "in_progress", "fulfilled", "blocked", "cancelled"}
    CONTACT_STATUSES = {"not_contacted", "contact_needed", "contacted", "responded", "not_required"}

    def __init__(self, db_path):
        self.db_path = Path(db_path)

    def connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self.connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS wallets (
                    address TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    claim_token TEXT,
                    public_key_jwk TEXT,
                    auth_scheme TEXT
                )
            """)
            wallet_cols = {row[1] for row in conn.execute("PRAGMA table_info(wallets)").fetchall()}
            for col in ("claim_token", "public_key_jwk", "auth_scheme"):
                if col not in wallet_cols:
                    conn.execute(f"ALTER TABLE wallets ADD COLUMN {col} TEXT")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS balances (
                    address TEXT PRIMARY KEY,
                    units INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    txid TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    sender TEXT,
                    recipient TEXT,
                    amount_units INTEGER NOT NULL,
                    memo TEXT,
                    related_source TEXT,
                    related_id TEXT,
                    payload_hash TEXT,
                    signature TEXT,
                    signed_payload TEXT,
                    block_height INTEGER
                )
            """)
            tx_cols = {row[1] for row in conn.execute("PRAGMA table_info(transactions)").fetchall()}
            for col in ("payload_hash", "signature", "signed_payload"):
                if col not in tx_cols:
                    conn.execute(f"ALTER TABLE transactions ADD COLUMN {col} TEXT")
            if "block_height" not in tx_cols:
                conn.execute("ALTER TABLE transactions ADD COLUMN block_height INTEGER")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nonces (
                    address TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(address, nonce)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS blocks (
                    height INTEGER PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    txid TEXT,
                    tx_count INTEGER NOT NULL,
                    merkle_root TEXT NOT NULL,
                    block_hash TEXT NOT NULL UNIQUE
                )
            """)
            block_cols = {row[1] for row in conn.execute("PRAGMA table_info(blocks)").fetchall()}
            block_additions = {
                "txids_json": "TEXT",
                "producer_id": "TEXT",
                "producer_seal": "TEXT",
                "block_version": "INTEGER",
            }
            for col, col_type in block_additions.items():
                if col not in block_cols:
                    conn.execute(f"ALTER TABLE blocks ADD COLUMN {col} {col_type}")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS product_orders (
                    receipt_id TEXT PRIMARY KEY,
                    txid TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    wallet_address TEXT NOT NULL,
                    source TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    amount_units INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    fulfillment_status TEXT NOT NULL,
                    contact_status TEXT NOT NULL,
                    notes TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS product_order_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    receipt_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    status TEXT,
                    fulfillment_status TEXT,
                    contact_status TEXT,
                    notes TEXT,
                    FOREIGN KEY(receipt_id) REFERENCES product_orders(receipt_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mempool_transactions (
                    pending_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    recipient TEXT,
                    amount_units INTEGER NOT NULL,
                    memo TEXT,
                    related_source TEXT,
                    related_id TEXT,
                    payload_hash TEXT NOT NULL UNIQUE,
                    nonce TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    signed_payload TEXT NOT NULL,
                    product_snapshot TEXT,
                    status TEXT NOT NULL,
                    error TEXT,
                    txid TEXT,
                    UNIQUE(sender, nonce)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS node_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS node_peers (
                    peer_id TEXT PRIMARY KEY,
                    url TEXT NOT NULL UNIQUE,
                    label TEXT,
                    added_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_seen_at TEXT,
                    status TEXT NOT NULL,
                    chain_id TEXT,
                    last_height INTEGER,
                    last_hash TEXT,
                    notes TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chain_sync_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    peer_id TEXT,
                    url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    recommended_action TEXT NOT NULL,
                    snapshot_valid INTEGER NOT NULL,
                    local_height INTEGER,
                    local_tip_hash TEXT,
                    peer_height INTEGER,
                    peer_tip_hash TEXT,
                    common_height INTEGER,
                    common_hash TEXT,
                    importable_blocks INTEGER NOT NULL DEFAULT 0,
                    fork_depth INTEGER NOT NULL DEFAULT 0,
                    local_chain_digest TEXT,
                    peer_chain_digest TEXT,
                    manifest_json TEXT NOT NULL,
                    verification_json TEXT NOT NULL,
                    evaluation_json TEXT NOT NULL,
                    notes TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chain_sync_imports (
                    import_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    peer_id TEXT,
                    url TEXT NOT NULL,
                    candidate_id TEXT,
                    status TEXT NOT NULL,
                    local_height_before INTEGER,
                    local_tip_before TEXT,
                    imported_height INTEGER,
                    imported_tip_hash TEXT,
                    imported_blocks INTEGER NOT NULL DEFAULT 0,
                    imported_transactions INTEGER NOT NULL DEFAULT 0,
                    backup_path TEXT,
                    evaluation_json TEXT NOT NULL,
                    errors_json TEXT NOT NULL,
                    notes TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoint_votes (
                    vote_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    validator_address TEXT NOT NULL,
                    height INTEGER NOT NULL,
                    block_hash TEXT NOT NULL,
                    chain_digest TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    signed_payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    notes TEXT,
                    UNIQUE(validator_address, height, block_hash, chain_digest)
                )
            """)
            now = protocol.utc_now()
            stored_chain = conn.execute("SELECT value FROM node_config WHERE key = 'chain_id'").fetchone()
            if stored_chain and stored_chain["value"] != protocol.CHAIN_ID:
                raise ValueError(
                    f"Ledger belongs to {stored_chain['value']}; refusing to open it as {protocol.CHAIN_ID}."
                )
            if not stored_chain:
                existing_transactions = int(conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
                if protocol.IS_CLOSED_LOOP_MAINNET and existing_transactions:
                    raise ValueError(
                        "Refusing to relabel an existing unbound ledger as mainnet; use a fresh mainnet database."
                    )
                conn.execute(
                    "INSERT INTO node_config(key, value, updated_at) VALUES(?,?,?)",
                    ("chain_id", protocol.CHAIN_ID, now),
                )
            stored_profile = conn.execute("SELECT value FROM node_config WHERE key = 'network_profile'").fetchone()
            if stored_profile and stored_profile["value"] != protocol.NETWORK_PROFILE:
                raise ValueError(
                    f"Ledger uses profile {stored_profile['value']}; refusing profile {protocol.NETWORK_PROFILE}."
                )
            if not stored_profile:
                conn.execute(
                    "INSERT INTO node_config(key, value, updated_at) VALUES(?,?,?)",
                    ("network_profile", protocol.NETWORK_PROFILE, now),
                )
            if not conn.execute("SELECT 1 FROM node_config WHERE key = 'node_id'").fetchone():
                node_id = "SCNODE-" + protocol.hash_text(secrets.token_hex(32))[:24]
                conn.execute("INSERT INTO node_config(key, value, updated_at) VALUES(?,?,?)", ("node_id", node_id, now))
            if not conn.execute("SELECT 1 FROM node_config WHERE key = 'node_label'").fetchone():
                default_label = "SpaceCash NSP Mainnet Node" if protocol.IS_CLOSED_LOOP_MAINNET else "SpaceCash Local Devnet Node"
                conn.execute("INSERT INTO node_config(key, value, updated_at) VALUES(?,?,?)", ("node_label", default_label, now))
            if not conn.execute("SELECT 1 FROM node_config WHERE key = 'allowed_producers_json'").fetchone():
                conn.execute(
                    "INSERT INTO node_config(key, value, updated_at) VALUES(?,?,?)",
                    ("allowed_producers_json", protocol.canonical_json(list(protocol.DEFAULT_ALLOWED_PRODUCERS)), now),
                )
            if not conn.execute("SELECT 1 FROM node_config WHERE key = 'bootstrap_peers_json'").fetchone():
                conn.execute(
                    "INSERT INTO node_config(key, value, updated_at) VALUES(?,?,?)",
                    ("bootstrap_peers_json", protocol.canonical_json(list(protocol.DEFAULT_BOOTSTRAP_PEERS)), now),
                )
            if not conn.execute("SELECT 1 FROM node_config WHERE key = 'validator_policy_json'").fetchone():
                conn.execute(
                    "INSERT INTO node_config(key, value, updated_at) VALUES(?,?,?)",
                    (
                        "validator_policy_json",
                        protocol.canonical_json({"validators": [], "quorum": protocol.DEFAULT_VALIDATOR_QUORUM}),
                        now,
                    ),
                )
            exists = conn.execute("SELECT 1 FROM wallets WHERE address = ?", (protocol.TREASURY,)).fetchone()
            if not exists:
                now = protocol.GENESIS_TIMESTAMP or protocol.utc_now()
                genesis_txid = protocol.deterministic_genesis_txid() or protocol.txid(
                    "genesis", None, protocol.TREASURY, protocol.GENESIS_UNITS
                )
                conn.execute(
                    "INSERT INTO wallets(address, label, created_at, claim_token, auth_scheme) VALUES(?,?,?,?,?)",
                    (
                        protocol.TREASURY,
                        "SpaceCash Closed-Loop Reward Treasury" if protocol.IS_CLOSED_LOOP_MAINNET else "SpaceCash Devnet Treasury",
                        now,
                        None,
                        "treasury",
                    ),
                )
                conn.execute(
                    "INSERT INTO balances(address, units, updated_at) VALUES(?,?,?)",
                    (protocol.TREASURY, protocol.GENESIS_UNITS, now),
                )
                conn.execute("""
                    INSERT INTO transactions(txid, created_at, kind, sender, recipient, amount_units, memo)
                    VALUES(?,?,?,?,?,?,?)
                """, (
                    genesis_txid,
                    now,
                    "genesis",
                    None,
                    protocol.TREASURY,
                    protocol.GENESIS_UNITS,
                    "Initial SpaceCash closed-loop mainnet allocation" if protocol.IS_CLOSED_LOOP_MAINNET else "Initial SpaceCash devnet allocation",
                ))
            self._backfill_blocks(conn)
            conn.commit()
        finally:
            conn.close()

    def _block_payload(self, txids, producer_id, block_version=None):
        return protocol.canonical_json({
            "version": int(block_version or protocol.BLOCK_VERSION),
            "producer_id": producer_id or protocol.PRODUCER_ID,
            "txids": list(txids),
        })

    def _producer_seal(self, block_hash, txids_json, producer_id):
        return protocol.hash_text(f"{protocol.CHAIN_ID}|{producer_id or protocol.PRODUCER_ID}|{block_hash}|{txids_json or '[]'}")

    def _mine_block_batch(self, conn, txids, created_at=None, producer_id=None):
        txids = [str(txid).strip().upper() for txid in txids if str(txid or "").strip()]
        if not txids:
            raise ValueError("Cannot mine an empty SpaceCash block.")
        previous = conn.execute("SELECT height, block_hash FROM blocks ORDER BY height DESC LIMIT 1").fetchone()
        height = int(previous["height"]) + 1 if previous else 0
        previous_hash = previous["block_hash"] if previous else ("0" * 64)
        created_at = created_at or protocol.utc_now()
        producer_id = producer_id or protocol.PRODUCER_ID
        txids_json = protocol.canonical_json(txids)
        merkle_root = protocol.merkle_root(txids)
        block_payload = self._block_payload(txids, producer_id, protocol.BLOCK_VERSION)
        block_digest = protocol.block_hash(height, created_at, previous_hash, merkle_root, block_payload, len(txids))
        producer_seal = self._producer_seal(block_digest, txids_json, producer_id)
        conn.execute("""
            INSERT INTO blocks(
                height, created_at, previous_hash, txid, tx_count, merkle_root,
                block_hash, txids_json, producer_id, producer_seal, block_version
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """, (
            height,
            created_at,
            previous_hash,
            txids[0],
            len(txids),
            merkle_root,
            block_digest,
            txids_json,
            producer_id,
            producer_seal,
            protocol.BLOCK_VERSION,
        ))
        return height

    def _mine_block(self, conn, block_txid, created_at=None):
        return self._mine_block_batch(conn, [block_txid], created_at, protocol.PRODUCER_ID)

    def _backfill_blocks(self, conn):
        rows = conn.execute("""
            SELECT txid, created_at
            FROM transactions
            WHERE block_height IS NULL
            ORDER BY created_at, txid
        """).fetchall()
        for row in rows:
            height = self._mine_block(conn, row["txid"], row["created_at"])
            conn.execute("UPDATE transactions SET block_height = ? WHERE txid = ?", (height, row["txid"]))

    def _get_balance(self, conn, address):
        row = conn.execute("SELECT units FROM balances WHERE address = ?", (address,)).fetchone()
        return int(row["units"]) if row else 0

    def _node_config(self, conn, key, default=""):
        row = conn.execute("SELECT value FROM node_config WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def _set_node_config(self, conn, key, value):
        conn.execute("""
            INSERT INTO node_config(key, value, updated_at)
            VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """, (key, str(value), protocol.utc_now()))

    def _node_json_config(self, conn, key, default):
        raw = self._node_config(conn, key, "")
        if not raw:
            return default
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return default
        return parsed if parsed is not None else default

    def _normalize_producer_id(self, producer_id):
        text = str(producer_id or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{3,120}", text):
            raise ValueError("Producer id must be 3-120 URL-safe characters.")
        return text

    def _allowed_producers_locked(self, conn):
        producers = self._node_json_config(conn, "allowed_producers_json", list(protocol.DEFAULT_ALLOWED_PRODUCERS))
        if not isinstance(producers, list):
            producers = list(protocol.DEFAULT_ALLOWED_PRODUCERS)
        normalized = []
        for producer in producers + [protocol.PRODUCER_ID]:
            try:
                producer_id = self._normalize_producer_id(producer)
            except ValueError:
                continue
            if producer_id not in normalized:
                normalized.append(producer_id)
        return normalized or [protocol.PRODUCER_ID]

    def _bootstrap_peers_locked(self, conn):
        peers = self._node_json_config(conn, "bootstrap_peers_json", list(protocol.DEFAULT_BOOTSTRAP_PEERS))
        if not isinstance(peers, list):
            peers = list(protocol.DEFAULT_BOOTSTRAP_PEERS)
        normalized = []
        seen = set()
        for item in peers:
            if isinstance(item, dict):
                raw_url = item.get("url")
                label = str(item.get("label") or "bootstrap")[:120]
                notes = str(item.get("notes") or "Configured bootstrap peer.")[:500]
            else:
                raw_url = item
                label = "bootstrap"
                notes = "Configured bootstrap peer."
            try:
                url = self._normalize_peer_url(raw_url)
            except ValueError:
                continue
            if url in seen:
                continue
            seen.add(url)
            normalized.append({"url": url, "label": label, "notes": notes})
        return normalized

    def _normalize_validator_address(self, address):
        text = str(address or "").strip().upper()
        if not protocol.valid_address(text):
            raise ValueError("Validator must be a SpaceCash wallet address.")
        return text

    def _normalize_validator_quorum(self, quorum):
        try:
            value = int(quorum)
        except (TypeError, ValueError) as exc:
            raise ValueError("Validator quorum must be a positive integer.") from exc
        if value < 1 or value > 500:
            raise ValueError("Validator quorum must be between 1 and 500.")
        return value

    def _validator_policy_locked(self, conn):
        raw = self._node_json_config(
            conn,
            "validator_policy_json",
            {"validators": [], "quorum": protocol.DEFAULT_VALIDATOR_QUORUM},
        )
        if not isinstance(raw, dict):
            raw = {"validators": [], "quorum": protocol.DEFAULT_VALIDATOR_QUORUM}
        validators = []
        for item in raw.get("validators") or []:
            try:
                address = self._normalize_validator_address(item)
            except ValueError:
                continue
            if address not in validators:
                validators.append(address)
        try:
            quorum = self._normalize_validator_quorum(raw.get("quorum") or protocol.DEFAULT_VALIDATOR_QUORUM)
        except ValueError:
            quorum = protocol.DEFAULT_VALIDATOR_QUORUM
        return {"validators": validators, "quorum": quorum}

    def _checkpoint_vote_id(self, validator_address, height, block_hash, chain_digest):
        seed = f"{protocol.CHAIN_ID}|{validator_address}|{int(height)}|{block_hash}|{chain_digest}"
        return "SCVOTE-" + protocol.hash_text(seed)[:24]

    def _checkpoint_vote_from_row(self, row):
        if not row:
            return None
        data = dict(row)
        try:
            data["signed_payload"] = json.loads(data["signed_payload"])
        except (TypeError, json.JSONDecodeError):
            data["signed_payload"] = data.get("signed_payload")
        data["signature_present"] = bool(data.get("signature"))
        return data

    def _peer_id(self, url):
        return "SCPR-" + protocol.hash_text(str(url).strip().lower())[:24]

    def _normalize_peer_url(self, url):
        text = str(url or "").strip().rstrip("/")
        if not re.fullmatch(r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]{3,240}", text):
            raise ValueError("Peer URL must be an http(s) URL.")
        parsed = urllib.parse.urlsplit(text)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Peer URL must include an http(s) host.")
        if parsed.username or parsed.password or parsed.fragment:
            raise ValueError("Peer URL cannot contain credentials or a fragment.")
        if parsed.query:
            raise ValueError("Peer base URL cannot contain a query string.")
        hostname = parsed.hostname.rstrip(".").lower()
        if protocol.IS_CLOSED_LOOP_MAINNET:
            allowed_hosts = {
                item.strip().rstrip(".").lower()
                for item in os.environ.get(
                    "SPACECASH_MAINNET_PEER_HOSTS",
                    "app.northstarprime.net",
                ).split(",")
                if item.strip()
            }
            if parsed.scheme != "https" or hostname not in allowed_hosts or parsed.port not in {None, 443}:
                raise ValueError("Closed-loop mainnet peers must use an approved HTTPS host on port 443.")
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))

    def _validate_peer_destination(self, url):
        parsed = urllib.parse.urlsplit(url)
        hostname = str(parsed.hostname or "").rstrip(".").lower()
        if not hostname:
            raise ValueError("Peer URL host is missing.")
        allow_private = (
            not protocol.IS_CLOSED_LOOP_MAINNET
            and os.environ.get("SPACECASH_ALLOW_PRIVATE_PEERS", "").strip() == "1"
        )
        try:
            addresses = {
                item[4][0]
                for item in socket.getaddrinfo(
                    hostname,
                    parsed.port or (443 if parsed.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                )
            }
        except socket.gaierror as exc:
            raise ValueError("Peer host could not be resolved.") from exc
        if not addresses:
            raise ValueError("Peer host did not resolve to an address.")
        if allow_private:
            return
        for raw_address in addresses:
            address = ipaddress.ip_address(raw_address)
            if not address.is_global:
                raise ValueError(
                    "Peer destination resolves to a private, local, reserved, or otherwise non-public address."
                )

    def _peer_endpoint(self, url, path):
        return self._normalize_peer_url(url) + "/" + str(path or "").lstrip("/")

    def _fetch_peer_json(self, url, timeout=5, max_bytes=5_000_000):
        timeout = max(1, min(30, int(timeout or 5)))
        self._validate_peer_destination(url)
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": f"SpaceCashNode/{protocol.NODE_PROTOCOL_VERSION}",
            },
        )
        try:
            opener = urllib.request.build_opener(_SpaceCashNoRedirectHandler())
            with opener.open(req, timeout=timeout) as resp:
                content_type = resp.headers.get("Content-Type", "")
                raw = resp.read(max_bytes + 1)
        except urllib.error.URLError as exc:
            raise ValueError(f"Peer request failed: {exc}") from exc
        if len(raw) > max_bytes:
            raise ValueError("Peer response is too large.")
        if "json" not in content_type.lower() and content_type:
            raise ValueError("Peer response is not JSON.")
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Peer response JSON is invalid.") from exc

    def node_identity(self):
        self.ensure_schema()
        conn = self.connect()
        try:
            return {
                "node_id": self._node_config(conn, "node_id"),
                "label": self._node_config(
                    conn,
                    "node_label",
                    "SpaceCash NSP Mainnet Node" if protocol.IS_CLOSED_LOOP_MAINNET else "SpaceCash Local Devnet Node",
                ),
                "chain_id": protocol.CHAIN_ID,
                "node_protocol_version": protocol.NODE_PROTOCOL_VERSION,
                "block_version": protocol.BLOCK_VERSION,
                "address_version": protocol.ADDRESS_VERSION,
                "monetary_policy": {
                    "id": protocol.MONETARY_POLICY_ID,
                    "version": protocol.MONETARY_POLICY_VERSION,
                    "hash": protocol.monetary_policy_hash(),
                },
                "genesis_plan": {
                    "id": protocol.GENESIS_PLAN_ID,
                    "version": protocol.GENESIS_PLAN_VERSION,
                    "hash": protocol.genesis_plan_hash(),
                },
                "wallet_policy": {
                    "id": protocol.WALLET_POLICY_ID,
                    "version": protocol.WALLET_POLICY_VERSION,
                    "hash": protocol.wallet_policy_hash(),
                },
                "consensus_spec_id": protocol.CONSENSUS_SPEC_ID,
                "consensus_spec_version": protocol.CONSENSUS_SPEC_VERSION,
                "consensus_spec_hash": protocol.consensus_spec_hash(),
                "fork_choice_policy": protocol.FORK_CHOICE_POLICY,
                "producer_policy_version": protocol.PRODUCER_POLICY_VERSION,
                "producer_id": protocol.PRODUCER_ID,
                "mode": protocol.NETWORK_MODE,
                "network_profile": protocol.NETWORK_PROFILE,
            }
        finally:
            conn.close()

    def set_node_label(self, label):
        self.ensure_schema()
        default_label = "SpaceCash NSP Mainnet Node" if protocol.IS_CLOSED_LOOP_MAINNET else "SpaceCash Local Devnet Node"
        label = str(label or "").strip()[:120] or default_label
        conn = self.connect()
        try:
            self._set_node_config(conn, "node_label", label)
            conn.commit()
            return self.node_identity()
        finally:
            conn.close()

    def consensus_policy(self):
        self.ensure_schema()
        conn = self.connect()
        try:
            validator_policy = self._validator_policy_locked(conn)
            return {
                "chain_id": protocol.CHAIN_ID,
                "node_protocol_version": protocol.NODE_PROTOCOL_VERSION,
                "consensus_spec": {
                    "id": protocol.CONSENSUS_SPEC_ID,
                    "version": protocol.CONSENSUS_SPEC_VERSION,
                    "hash": protocol.consensus_spec_hash(),
                },
                "monetary_policy": {
                    "id": protocol.MONETARY_POLICY_ID,
                    "version": protocol.MONETARY_POLICY_VERSION,
                    "hash": protocol.monetary_policy_hash(),
                },
                "genesis_plan": {
                    "id": protocol.GENESIS_PLAN_ID,
                    "version": protocol.GENESIS_PLAN_VERSION,
                    "hash": protocol.genesis_plan_hash(),
                },
                "fork_choice_policy": protocol.FORK_CHOICE_POLICY,
                "producer_policy_version": protocol.PRODUCER_POLICY_VERSION,
                "validator_policy_version": protocol.VALIDATOR_POLICY_VERSION,
                "local_producer_id": protocol.PRODUCER_ID,
                "allowed_producers": self._allowed_producers_locked(conn),
                "validators": validator_policy["validators"],
                "validator_quorum": validator_policy["quorum"],
                "accepted_block_versions": [1, protocol.BLOCK_VERSION],
                "legacy_blocks_allowed": True,
                "append_only_imports_only": True,
                "automatic_reorgs": False,
                "bootstrap_peers": self._bootstrap_peers_locked(conn),
                "rules": [
                    "Verify snapshot digest, block hashes, supply, and signatures before considering sync.",
                    "Import only verified peer-ahead snapshots that extend the local tip exactly.",
                    "Reject new versioned blocks from producer ids not present in allowed_producers.",
                    "Accept checkpoint votes only from locally registered validator wallets.",
                    "Report higher-scoring diverged peers, but do not reorg automatically.",
                ],
            }
        finally:
            conn.close()

    def set_allowed_producers(self, producers):
        self.ensure_schema()
        if isinstance(producers, str):
            producers = [part.strip() for part in producers.split(",") if part.strip()]
        if not isinstance(producers, list):
            raise ValueError("Allowed producers must be a list.")
        normalized = []
        for producer in producers + [protocol.PRODUCER_ID]:
            producer_id = self._normalize_producer_id(producer)
            if producer_id not in normalized:
                normalized.append(producer_id)
        conn = self.connect()
        try:
            self._set_node_config(conn, "allowed_producers_json", protocol.canonical_json(normalized))
            conn.commit()
            return self.consensus_policy()
        finally:
            conn.close()

    def add_allowed_producer(self, producer_id):
        self.ensure_schema()
        producer_id = self._normalize_producer_id(producer_id)
        conn = self.connect()
        try:
            producers = self._allowed_producers_locked(conn)
            if producer_id not in producers:
                producers.append(producer_id)
            self._set_node_config(conn, "allowed_producers_json", protocol.canonical_json(producers))
            conn.commit()
            return self.consensus_policy()
        finally:
            conn.close()

    def _require_validator_wallet_locked(self, conn, address):
        address = self._normalize_validator_address(address)
        row = conn.execute("SELECT public_key_jwk FROM wallets WHERE address = ?", (address,)).fetchone()
        if not row or not row["public_key_jwk"]:
            raise ValueError("Validator must be registered as a signed SpaceCash wallet.")
        public_jwk = protocol.normalize_public_jwk(row["public_key_jwk"])
        if protocol.address_from_public_jwk(public_jwk) != address:
            raise ValueError("Validator wallet public key does not derive to its address.")
        return public_jwk

    def validator_policy(self):
        self.ensure_schema()
        conn = self.connect()
        try:
            policy = self._validator_policy_locked(conn)
        finally:
            conn.close()
        return {
            "chain_id": protocol.CHAIN_ID,
            "validator_policy_version": protocol.VALIDATOR_POLICY_VERSION,
            "validators": policy["validators"],
            "quorum": policy["quorum"],
            "checkpoint": self.checkpoint_quorum(),
            "rules": [
                "Validators are registered signed SpaceCash wallets.",
                "Checkpoint votes sign chain_id, height, block_hash, and chain_digest.",
                "A checkpoint reaches local quorum when enough current validators sign the same current tip.",
            ],
        }

    def set_validators(self, validators, quorum=None):
        self.ensure_schema()
        if isinstance(validators, str):
            validators = [part.strip() for part in validators.split(",") if part.strip()]
        if not isinstance(validators, list):
            raise ValueError("Validators must be a list of SpaceCash wallet addresses.")
        conn = self.connect()
        try:
            current = self._validator_policy_locked(conn)
            normalized = []
            for item in validators:
                address = self._normalize_validator_address(item)
                self._require_validator_wallet_locked(conn, address)
                if address not in normalized:
                    normalized.append(address)
            next_quorum = self._normalize_validator_quorum(quorum) if quorum is not None else current["quorum"]
            if normalized and next_quorum > len(normalized):
                raise ValueError("Validator quorum cannot exceed the validator count.")
            self._set_node_config(
                conn,
                "validator_policy_json",
                protocol.canonical_json({"validators": normalized, "quorum": next_quorum}),
            )
            conn.commit()
            return self.validator_policy()
        finally:
            conn.close()

    def add_validator(self, address):
        self.ensure_schema()
        address = self._normalize_validator_address(address)
        conn = self.connect()
        try:
            self._require_validator_wallet_locked(conn, address)
            policy = self._validator_policy_locked(conn)
            validators = policy["validators"]
            if address not in validators:
                validators.append(address)
            if validators and policy["quorum"] > len(validators):
                policy["quorum"] = len(validators)
            self._set_node_config(
                conn,
                "validator_policy_json",
                protocol.canonical_json({"validators": validators, "quorum": policy["quorum"]}),
            )
            conn.commit()
            return self.validator_policy()
        finally:
            conn.close()

    def set_validator_quorum(self, quorum):
        self.ensure_schema()
        quorum = self._normalize_validator_quorum(quorum)
        conn = self.connect()
        try:
            policy = self._validator_policy_locked(conn)
            if policy["validators"] and quorum > len(policy["validators"]):
                raise ValueError("Validator quorum cannot exceed the validator count.")
            self._set_node_config(
                conn,
                "validator_policy_json",
                protocol.canonical_json({"validators": policy["validators"], "quorum": quorum}),
            )
            conn.commit()
            return self.validator_policy()
        finally:
            conn.close()

    def checkpoint_vote_payload(self, validator_address):
        validator_address = self._normalize_validator_address(validator_address)
        self.ensure_schema()
        conn = self.connect()
        try:
            policy = self._validator_policy_locked(conn)
            if validator_address not in policy["validators"]:
                raise ValueError("Checkpoint vote payload requires a registered validator wallet.")
            self._require_validator_wallet_locked(conn, validator_address)
        finally:
            conn.close()
        manifest = self.chain_manifest()
        return {
            "chain_id": protocol.CHAIN_ID,
            "version": protocol.SIGNED_PAYLOAD_VERSION,
            "action": "checkpoint_vote",
            "validator": validator_address,
            "height": manifest.get("height"),
            "block_hash": manifest.get("tip_hash"),
            "chain_digest": manifest.get("chain_digest"),
        }

    def _validate_checkpoint_vote_payload(self, signed_payload):
        if not isinstance(signed_payload, dict):
            raise ValueError("Checkpoint vote requires a signed payload.")
        validator = self._normalize_validator_address(signed_payload.get("validator"))
        expected = self.checkpoint_vote_payload(validator)
        comparisons = {
            "chain_id": str(expected["chain_id"]),
            "version": str(expected["version"]),
            "action": expected["action"],
            "validator": expected["validator"],
            "height": str(expected["height"]),
            "block_hash": expected["block_hash"],
            "chain_digest": expected["chain_digest"],
        }
        for key, wanted in comparisons.items():
            actual_value = signed_payload.get(key)
            actual = "" if actual_value is None else str(actual_value).strip()
            if key == "validator":
                actual = actual.upper()
            if actual != str(wanted):
                raise ValueError(f"Checkpoint vote {key} does not match the current local tip.")
        return expected

    def submit_checkpoint_vote(self, payload):
        payload = payload or {}
        signed_payload = self._request_auth_payload(payload)
        signature = payload.get("signature") if isinstance(payload, dict) else None
        if not signed_payload or not signature:
            raise ValueError("Checkpoint vote requires a signed payload and signature.")
        expected = self._validate_checkpoint_vote_payload(signed_payload)
        validator = expected["validator"]
        self._verify_signature(validator, signed_payload, signature)
        self.ensure_schema()
        conn = self.connect()
        try:
            policy = self._validator_policy_locked(conn)
            if validator not in policy["validators"]:
                raise ValueError("Checkpoint vote signer is not in the local validator set.")
            self._require_validator_wallet_locked(conn, validator)
            payload_hash = protocol.payload_hash(signed_payload)
            vote_id = self._checkpoint_vote_id(validator, expected["height"], expected["block_hash"], expected["chain_digest"])
            now = protocol.utc_now()
            conn.execute("""
                INSERT INTO checkpoint_votes(
                    vote_id, created_at, updated_at, validator_address, height,
                    block_hash, chain_digest, payload_hash, signature,
                    signed_payload, status, notes
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(validator_address, height, block_hash, chain_digest) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    payload_hash = excluded.payload_hash,
                    signature = excluded.signature,
                    signed_payload = excluded.signed_payload,
                    status = excluded.status,
                    notes = excluded.notes
            """, (
                vote_id,
                now,
                now,
                validator,
                int(expected["height"]),
                expected["block_hash"],
                expected["chain_digest"],
                payload_hash,
                str(signature)[:512],
                protocol.canonical_json(signed_payload),
                "valid",
                "Signed local checkpoint vote.",
            ))
            conn.commit()
            row = conn.execute("SELECT * FROM checkpoint_votes WHERE vote_id = ?", (vote_id,)).fetchone()
            return {"vote": self._checkpoint_vote_from_row(row), "quorum": self.checkpoint_quorum()}
        finally:
            conn.close()

    def checkpoint_votes(self, status=None, height=None, block_hash=None, limit=50):
        self.ensure_schema()
        limit = max(1, min(500, int(limit or 50)))
        clauses = []
        params = []
        if status:
            clauses.append("status = ?")
            params.append(str(status).strip().lower())
        if height is not None:
            clauses.append("height = ?")
            params.append(int(height))
        if block_hash:
            clauses.append("block_hash = ?")
            params.append(str(block_hash).strip().upper())
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        conn = self.connect()
        try:
            rows = conn.execute(f"""
                SELECT *
                FROM checkpoint_votes
                {where}
                ORDER BY updated_at DESC, vote_id
                LIMIT ?
            """, (*params, limit)).fetchall()
            return [self._checkpoint_vote_from_row(row) for row in rows]
        finally:
            conn.close()

    def checkpoint_quorum(self, height=None, block_hash=None, chain_digest=None):
        manifest = self.chain_manifest()
        height = int(height if height is not None else manifest.get("height"))
        block_hash = str(block_hash or manifest.get("tip_hash") or "").strip().upper()
        chain_digest = str(chain_digest or manifest.get("chain_digest") or "").strip().upper()
        self.ensure_schema()
        conn = self.connect()
        try:
            policy = self._validator_policy_locked(conn)
            rows = conn.execute("""
                SELECT *
                FROM checkpoint_votes
                WHERE status = 'valid'
                  AND height = ?
                  AND block_hash = ?
                  AND chain_digest = ?
                ORDER BY updated_at DESC, vote_id
            """, (height, block_hash, chain_digest)).fetchall()
            votes = []
            voted = []
            for row in rows:
                vote = self._checkpoint_vote_from_row(row)
                validator = vote["validator_address"]
                if validator not in policy["validators"] or validator in voted:
                    continue
                voted.append(validator)
                votes.append(vote)
            missing = [address for address in policy["validators"] if address not in voted]
            return {
                "chain_id": protocol.CHAIN_ID,
                "validator_policy_version": protocol.VALIDATOR_POLICY_VERSION,
                "height": height,
                "block_hash": block_hash,
                "chain_digest": chain_digest,
                "validators": policy["validators"],
                "quorum": policy["quorum"],
                "eligible_votes": len(voted),
                "voted_validators": voted,
                "missing_validators": missing,
                "quorum_reached": bool(policy["validators"]) and len(voted) >= policy["quorum"],
                "votes": votes,
            }
        finally:
            conn.close()

    def set_bootstrap_peers(self, peers):
        self.ensure_schema()
        if isinstance(peers, str):
            peers = [part.strip() for part in peers.split(",") if part.strip()]
        if not isinstance(peers, list):
            raise ValueError("Bootstrap peers must be a list.")
        normalized = []
        seen = set()
        for item in peers:
            if isinstance(item, dict):
                url = self._normalize_peer_url(item.get("url"))
                label = str(item.get("label") or "bootstrap")[:120]
                notes = str(item.get("notes") or "Configured bootstrap peer.")[:500]
            else:
                url = self._normalize_peer_url(item)
                label = "bootstrap"
                notes = "Configured bootstrap peer."
            if url in seen:
                continue
            seen.add(url)
            normalized.append({"url": url, "label": label, "notes": notes})
        conn = self.connect()
        try:
            self._set_node_config(conn, "bootstrap_peers_json", protocol.canonical_json(normalized))
            conn.commit()
            return {"bootstrap_peers": normalized, "count": len(normalized)}
        finally:
            conn.close()

    def add_bootstrap_peer(self, url, label="bootstrap", notes="Configured bootstrap peer."):
        self.ensure_schema()
        url = self._normalize_peer_url(url)
        conn = self.connect()
        try:
            peers = self._bootstrap_peers_locked(conn)
            if url not in {peer["url"] for peer in peers}:
                peers.append({"url": url, "label": str(label or "bootstrap")[:120], "notes": str(notes or "Configured bootstrap peer.")[:500]})
            self._set_node_config(conn, "bootstrap_peers_json", protocol.canonical_json(peers))
            conn.commit()
        finally:
            conn.close()
        registered = self.add_peer(url, label or "bootstrap", notes or "Configured bootstrap peer.")
        return {"bootstrap_peers": self.consensus_policy()["bootstrap_peers"], "registered": registered}

    def bootstrap_peers(self):
        self.ensure_schema()
        conn = self.connect()
        try:
            return {"bootstrap_peers": self._bootstrap_peers_locked(conn)}
        finally:
            conn.close()

    def load_bootstrap_peers(self, check=False, timeout=5, snapshot=False):
        self.ensure_schema()
        peers = self.bootstrap_peers()["bootstrap_peers"]
        results = []
        for peer in peers:
            registered = self.add_peer(peer["url"], peer.get("label") or "bootstrap", peer.get("notes") or "Configured bootstrap peer.")
            result = {"url": peer["url"], "registered": registered}
            if check:
                try:
                    result["check"] = self.check_peer(peer["url"], timeout=timeout, verify_snapshot=snapshot)
                except Exception as exc:
                    result["error"] = str(exc)
            results.append(result)
        return {"count": len(results), "results": results}

    def _tx_from_row(self, row):
        data = dict(row)
        data["amount"] = protocol.units_to_amount(row["amount_units"])
        data["signature_present"] = bool(row["signature"])
        return data

    def _ledger_transactions(self, conn):
        rows = conn.execute("""
            SELECT txid, created_at, kind, sender, recipient, amount_units, memo,
                   related_source, related_id, payload_hash, signature,
                   signed_payload, block_height
            FROM transactions
            ORDER BY COALESCE(block_height, -1), created_at, txid
        """).fetchall()
        return [self._tx_from_row(row) for row in rows]

    def _ledger_wallet_keys(self, conn):
        rows = conn.execute("""
            SELECT address, public_key_jwk, auth_scheme
            FROM wallets
            WHERE public_key_jwk IS NOT NULL AND TRIM(public_key_jwk) != ''
            ORDER BY address
        """).fetchall()
        wallet_keys = []
        for row in rows:
            try:
                public_key = protocol.normalize_public_jwk(row["public_key_jwk"])
            except ValueError:
                public_key = {"invalid": row["public_key_jwk"]}
            wallet_keys.append({
                "address": row["address"],
                "public_key_jwk": public_key,
                "auth_scheme": row["auth_scheme"] or "ecdsa-p256",
            })
        return wallet_keys

    def _digest_block(self, block):
        data = dict(block)
        return {
            "height": data.get("height"),
            "created_at": data.get("created_at"),
            "previous_hash": data.get("previous_hash"),
            "txid": data.get("txid"),
            "tx_count": data.get("tx_count"),
            "merkle_root": data.get("merkle_root"),
            "block_hash": data.get("block_hash"),
            "txids_json": data.get("txids_json"),
            "producer_id": data.get("producer_id"),
            "producer_seal": data.get("producer_seal"),
            "block_version": data.get("block_version"),
        }

    def _digest_tx(self, tx):
        data = dict(tx)
        return {
            "txid": data.get("txid"),
            "created_at": data.get("created_at"),
            "kind": data.get("kind"),
            "sender": data.get("sender"),
            "recipient": data.get("recipient"),
            "amount_units": data.get("amount_units"),
            "memo": data.get("memo"),
            "related_source": data.get("related_source"),
            "related_id": data.get("related_id"),
            "payload_hash": data.get("payload_hash"),
            "signature": data.get("signature"),
            "signed_payload": data.get("signed_payload"),
            "block_height": data.get("block_height"),
        }

    def _digest_wallet_key(self, wallet):
        data = dict(wallet)
        public_key = data.get("public_key_jwk")
        try:
            public_key = protocol.normalize_public_jwk(public_key)
        except ValueError:
            public_key = public_key or {}
        return {
            "address": str(data.get("address") or "").strip().upper(),
            "public_key_jwk": public_key,
            "auth_scheme": data.get("auth_scheme") or "ecdsa-p256",
        }

    def chain_digest(self, blocks, transactions, wallet_keys=None):
        return protocol.payload_hash({
            "chain_id": protocol.CHAIN_ID,
            "blocks": [self._digest_block(block) for block in blocks],
            "transactions": [self._digest_tx(tx) for tx in transactions],
            "wallet_keys": [self._digest_wallet_key(wallet) for wallet in (wallet_keys or [])],
        })

    def chain_manifest(self):
        self.ensure_schema()
        conn = self.connect()
        try:
            blocks = [self._block_from_row(row) for row in conn.execute("SELECT * FROM blocks ORDER BY height").fetchall()]
            transactions = self._ledger_transactions(conn)
            wallet_keys = self._ledger_wallet_keys(conn)
            tip = blocks[-1] if blocks else None
            return {
                "chain_id": protocol.CHAIN_ID,
                "symbol": protocol.SYMBOL,
                "node": {
                    "node_id": self._node_config(conn, "node_id"),
                    "label": self._node_config(conn, "node_label", "SpaceCash Local Devnet Node"),
                    "node_protocol_version": protocol.NODE_PROTOCOL_VERSION,
                },
                "block_version": protocol.BLOCK_VERSION,
                "producer_id": protocol.PRODUCER_ID,
                "fork_choice_policy": protocol.FORK_CHOICE_POLICY,
                "producer_policy_version": protocol.PRODUCER_POLICY_VERSION,
                "validator_policy_version": protocol.VALIDATOR_POLICY_VERSION,
                "height": tip["height"] if tip else None,
                "tip_hash": tip["block_hash"] if tip else None,
                "genesis_hash": blocks[0]["block_hash"] if blocks else None,
                "blocks": len(blocks),
                "transactions": len(transactions),
                "wallet_keys": len(wallet_keys),
                "versioned_blocks": len([block for block in blocks if int(block.get("block_version") or 1) >= 2]),
                "batched_blocks": len([block for block in blocks if int(block.get("tx_count") or 0) > 1]),
                "chain_digest": self.chain_digest(blocks, transactions, wallet_keys),
                "generated_at": protocol.utc_now(),
            }
        finally:
            conn.close()

    def chain_snapshot(self, include_service_data=True):
        self.ensure_schema()
        conn = self.connect()
        try:
            blocks = [self._block_from_row(row) for row in conn.execute("SELECT * FROM blocks ORDER BY height").fetchall()]
            transactions = self._ledger_transactions(conn)
            wallet_keys = self._ledger_wallet_keys(conn)
            snapshot = {
                "manifest": {
                    "chain_id": protocol.CHAIN_ID,
                    "symbol": protocol.SYMBOL,
                    "block_version": protocol.BLOCK_VERSION,
                    "producer_id": protocol.PRODUCER_ID,
                    "fork_choice_policy": protocol.FORK_CHOICE_POLICY,
                    "producer_policy_version": protocol.PRODUCER_POLICY_VERSION,
                    "validator_policy_version": protocol.VALIDATOR_POLICY_VERSION,
                    "height": blocks[-1]["height"] if blocks else None,
                    "tip_hash": blocks[-1]["block_hash"] if blocks else None,
                    "genesis_hash": blocks[0]["block_hash"] if blocks else None,
                    "blocks": len(blocks),
                    "transactions": len(transactions),
                    "wallet_keys": len(wallet_keys),
                    "versioned_blocks": len([block for block in blocks if int(block.get("block_version") or 1) >= 2]),
                    "batched_blocks": len([block for block in blocks if int(block.get("tx_count") or 0) > 1]),
                    "chain_digest": self.chain_digest(blocks, transactions, wallet_keys),
                    "generated_at": protocol.utc_now(),
                },
                "node": {
                    "node_id": self._node_config(conn, "node_id"),
                    "label": self._node_config(conn, "node_label", "SpaceCash Local Devnet Node"),
                    "node_protocol_version": protocol.NODE_PROTOCOL_VERSION,
                },
                "blocks": blocks,
                "transactions": transactions,
                "wallet_keys": wallet_keys,
            }
            if include_service_data:
                snapshot["product_orders"] = [self._order_from_row(row) for row in conn.execute("SELECT * FROM product_orders ORDER BY created_at, receipt_id").fetchall()]
            return snapshot
        finally:
            conn.close()

    def _verify_snapshot_tx_signature(self, tx, wallet_keys_by_address, errors, warnings):
        if not isinstance(tx, dict):
            return False
        signature = tx.get("signature")
        kind = tx.get("kind")
        if not signature:
            if kind in ("transfer", "redeem", "product_redeem"):
                warnings.append(f"{tx.get('txid')} is a legacy unsigned snapshot spend.")
            return False
        if not tx.get("signed_payload"):
            errors.append(f"{tx.get('txid')} has a signature but no signed payload.")
            return True
        try:
            signed_payload = json.loads(tx.get("signed_payload"))
            payload_digest = protocol.payload_hash(signed_payload)
            if payload_digest != tx.get("payload_hash"):
                errors.append(f"{tx.get('txid')} signed payload hash does not match stored payload_hash.")
            sender = str(signed_payload.get("sender") or "").strip().upper()
            if sender != str(tx.get("sender") or "").strip().upper():
                errors.append(f"{tx.get('txid')} signed sender does not match transaction sender.")
            expected_action = self._signed_action_for_kind(kind)
            if expected_action and signed_payload.get("action") != expected_action:
                errors.append(f"{tx.get('txid')} signed action does not match transaction kind.")
            signed_chain_id = signed_payload.get("chain_id")
            if signed_chain_id is not None and signed_chain_id != protocol.CHAIN_ID:
                errors.append(f"{tx.get('txid')} signed chain_id does not match this devnet.")
            signed_version = signed_payload.get("version")
            if signed_version is not None and int(signed_version) != protocol.SIGNED_PAYLOAD_VERSION:
                errors.append(f"{tx.get('txid')} signed payload version is not supported.")
            if protocol.amount_to_units(signed_payload.get("amount")) != int(tx.get("amount_units") or 0):
                errors.append(f"{tx.get('txid')} signed amount does not match transaction amount.")
            if kind == "transfer":
                signed_recipient = str(signed_payload.get("recipient") or "").strip().upper()
                if signed_recipient != str(tx.get("recipient") or "").strip().upper():
                    errors.append(f"{tx.get('txid')} signed recipient does not match transaction recipient.")
            if kind == "product_redeem":
                if str(signed_payload.get("source") or "").strip().lower() != str(tx.get("related_source") or "").strip().lower():
                    errors.append(f"{tx.get('txid')} signed source does not match transaction source.")
                if str(int(signed_payload.get("product_id"))) != str(tx.get("related_id") or ""):
                    errors.append(f"{tx.get('txid')} signed product id does not match transaction product id.")
            public_jwk = wallet_keys_by_address.get(sender)
            if not public_jwk:
                errors.append(f"{tx.get('txid')} cannot verify snapshot signature because sender has no exported public key.")
                return True
            self._verify_payload_with_jwk(public_jwk, signed_payload, signature)
            return True
        except Exception as exc:
            errors.append(f"{tx.get('txid')} snapshot signature audit failed: {exc}")
            return True

    def verify_chain_snapshot(self, snapshot):
        snapshot = snapshot or {}
        manifest = snapshot.get("manifest") if isinstance(snapshot, dict) else None
        blocks = snapshot.get("blocks") if isinstance(snapshot, dict) else None
        transactions = snapshot.get("transactions") if isinstance(snapshot, dict) else None
        wallet_keys = snapshot.get("wallet_keys") if isinstance(snapshot, dict) else None
        errors = []
        warnings = []
        if not isinstance(manifest, dict):
            errors.append("Snapshot manifest is missing.")
            manifest = {}
        if not isinstance(blocks, list):
            errors.append("Snapshot blocks must be a list.")
            blocks = []
        if not isinstance(transactions, list):
            errors.append("Snapshot transactions must be a list.")
            transactions = []
        if wallet_keys is None:
            wallet_keys = []
        if not isinstance(wallet_keys, list):
            errors.append("Snapshot wallet_keys must be a list.")
            wallet_keys = []
        if manifest.get("chain_id") and manifest.get("chain_id") != protocol.CHAIN_ID:
            errors.append("Snapshot chain_id does not match this node.")
        wallet_keys_by_address = {}
        for wallet in wallet_keys:
            if not isinstance(wallet, dict):
                errors.append("Snapshot contains a non-object wallet key.")
                continue
            address = str(wallet.get("address") or "").strip().upper()
            try:
                public_key = protocol.normalize_public_jwk(wallet.get("public_key_jwk"))
            except ValueError as exc:
                errors.append(f"Snapshot wallet key for {address or 'unknown'} is invalid: {exc}")
                continue
            if protocol.address_from_public_jwk(public_key) != address:
                errors.append(f"Snapshot wallet key does not derive to {address}.")
                continue
            wallet_keys_by_address[address] = public_key
        digest = self.chain_digest(blocks, transactions, wallet_keys)
        if manifest.get("chain_digest") and digest != manifest.get("chain_digest"):
            errors.append("Snapshot chain_digest does not match blocks, transactions, and wallet keys.")

        tx_by_id = {tx.get("txid"): tx for tx in transactions if isinstance(tx, dict)}
        tx_by_height = {}
        for tx in transactions:
            if not isinstance(tx, dict):
                errors.append("Snapshot contains a non-object transaction.")
                continue
            if tx.get("block_height") is not None:
                tx_by_height.setdefault(int(tx["block_height"]), []).append(tx)

        expected_prev = "0" * 64
        for expected_height, block in enumerate(blocks):
            if not isinstance(block, dict):
                errors.append("Snapshot contains a non-object block.")
                continue
            height = int(block["height"]) if block.get("height") is not None else -1
            if height != expected_height:
                errors.append(f"Expected snapshot block height {expected_height}, found {height}.")
            if block.get("previous_hash") != expected_prev:
                errors.append(f"Snapshot block {height} previous hash does not match.")
            block_txs = tx_by_height.get(height, [])
            tx_count = int(block.get("tx_count") or 0)
            if len(block_txs) != tx_count:
                errors.append(f"Snapshot block {height} tx_count does not match attached transactions.")
            block_version = int(block.get("block_version") or 1)
            if block_version >= 2:
                try:
                    txids = json.loads(block.get("txids_json") or "[]")
                except json.JSONDecodeError:
                    txids = []
                    errors.append(f"Snapshot block {height} txids_json is invalid.")
                if len(txids) != tx_count:
                    errors.append(f"Snapshot block {height} txids_json length does not match tx_count.")
                if set(txids) != {tx.get("txid") for tx in block_txs}:
                    errors.append(f"Snapshot block {height} txids_json does not match attached transactions.")
                expected_merkle = protocol.merkle_root(txids)
                if block.get("merkle_root") != expected_merkle:
                    errors.append(f"Snapshot block {height} merkle root does not match.")
                producer_id = block.get("producer_id") or protocol.PRODUCER_ID
                expected_payload = self._block_payload(txids, producer_id, block_version)
                expected_hash = protocol.block_hash(height, block.get("created_at"), block.get("previous_hash"), block.get("merkle_root"), expected_payload, tx_count)
                if block.get("block_hash") != expected_hash:
                    errors.append(f"Snapshot block {height} hash does not match.")
                expected_seal = self._producer_seal(block.get("block_hash"), block.get("txids_json"), producer_id)
                if block.get("producer_seal") != expected_seal:
                    errors.append(f"Snapshot block {height} producer seal does not match.")
            else:
                txid = block.get("txid")
                if txid not in tx_by_id:
                    errors.append(f"Snapshot block {height} references missing transaction {txid}.")
                expected_merkle = protocol.hash_text(txid or "")
                if block.get("merkle_root") != expected_merkle:
                    errors.append(f"Snapshot block {height} legacy merkle root does not match.")
                expected_hash = protocol.block_hash(height, block.get("created_at"), block.get("previous_hash"), block.get("merkle_root"), txid, tx_count)
                if block.get("block_hash") != expected_hash:
                    errors.append(f"Snapshot block {height} legacy hash does not match.")
            expected_prev = block.get("block_hash")

        balances = {}
        for tx in transactions:
            if not isinstance(tx, dict):
                continue
            units = int(tx.get("amount_units") or 0)
            if units <= 0:
                errors.append(f"{tx.get('txid')} has a non-positive amount.")
            if tx.get("sender"):
                balances[tx["sender"]] = balances.get(tx["sender"], 0) - units
            if tx.get("recipient"):
                balances[tx["recipient"]] = balances.get(tx["recipient"], 0) + units
            if tx.get("block_height") is None:
                errors.append(f"{tx.get('txid')} has no block assignment.")
            self._verify_snapshot_tx_signature(tx, wallet_keys_by_address, errors, warnings)
        if sum(balances.values()) != protocol.GENESIS_UNITS:
            errors.append("Snapshot transaction supply does not match genesis supply.")

        tip = blocks[-1] if blocks else None
        if manifest.get("tip_hash") and tip and manifest.get("tip_hash") != tip.get("block_hash"):
            errors.append("Snapshot tip hash does not match manifest.")
        if manifest.get("blocks") is not None and int(manifest.get("blocks") or 0) != len(blocks):
            errors.append("Snapshot block count does not match manifest.")
        if manifest.get("transactions") is not None and int(manifest.get("transactions") or 0) != len(transactions):
            errors.append("Snapshot transaction count does not match manifest.")
        if manifest.get("wallet_keys") is not None and int(manifest.get("wallet_keys") or 0) != len(wallet_keys):
            errors.append("Snapshot wallet key count does not match manifest.")
        return {
            "valid": not errors,
            "errors": errors[:100],
            "warnings": warnings[:100],
            "chain_id": manifest.get("chain_id") or protocol.CHAIN_ID,
            "chain_digest": digest,
            "tip": {
                "height": tip.get("height") if tip else None,
                "hash": tip.get("block_hash") if tip else None,
            },
            "counts": {
                "blocks": len(blocks),
                "transactions": len(transactions),
            },
        }

    def node_status(self):
        manifest = self.chain_manifest()
        self.ensure_schema()
        conn = self.connect()
        try:
            return {
                "node": self.node_identity(),
                "policy": self.consensus_policy(),
                "chain": manifest,
                "peers": {
                    "count": conn.execute("SELECT COUNT(*) AS n FROM node_peers").fetchone()["n"],
                    "active": conn.execute("SELECT COUNT(*) AS n FROM node_peers WHERE status = 'active'").fetchone()["n"],
                },
            }
        finally:
            conn.close()

    def peers(self, status=None, limit=100):
        self.ensure_schema()
        limit = max(1, min(500, int(limit)))
        clauses = []
        params = []
        if status:
            clauses.append("status = ?")
            params.append(str(status).strip().lower())
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        conn = self.connect()
        try:
            rows = conn.execute(f"""
                SELECT *
                FROM node_peers
                {where}
                ORDER BY updated_at DESC, peer_id
                LIMIT ?
            """, (*params, limit)).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def add_peer(self, url, label="", notes=""):
        self.ensure_schema()
        url = self._normalize_peer_url(url)
        peer_id = self._peer_id(url)
        now = protocol.utc_now()
        conn = self.connect()
        try:
            conn.execute("""
                INSERT INTO node_peers(peer_id, url, label, added_at, updated_at, status, notes)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(url) DO UPDATE SET
                    label = COALESCE(NULLIF(excluded.label, ''), node_peers.label),
                    updated_at = excluded.updated_at,
                    status = 'active',
                    notes = COALESCE(NULLIF(excluded.notes, ''), node_peers.notes)
            """, (peer_id, url, str(label or "")[:120], now, now, "active", str(notes or "")[:500]))
            conn.commit()
            return dict(conn.execute("SELECT * FROM node_peers WHERE url = ?", (url,)).fetchone())
        finally:
            conn.close()

    def record_peer_manifest(self, url, manifest, status="seen"):
        self.ensure_schema()
        url = self._normalize_peer_url(url)
        if not isinstance(manifest, dict):
            raise ValueError("Peer manifest must be a JSON object.")
        peer = self.add_peer(url)
        conn = self.connect()
        try:
            conn.execute("""
                UPDATE node_peers
                SET updated_at = ?, last_seen_at = ?, status = ?, chain_id = ?,
                    last_height = ?, last_hash = ?
                WHERE peer_id = ?
            """, (
                protocol.utc_now(),
                protocol.utc_now(),
                str(status or "seen").strip().lower()[:40],
                manifest.get("chain_id"),
                manifest.get("height"),
                manifest.get("tip_hash"),
                peer["peer_id"],
            ))
            conn.commit()
            return dict(conn.execute("SELECT * FROM node_peers WHERE peer_id = ?", (peer["peer_id"],)).fetchone())
        finally:
            conn.close()

    def compare_peer_manifest(self, manifest):
        if not isinstance(manifest, dict):
            raise ValueError("Peer manifest must be a JSON object.")
        local = self.chain_manifest()
        errors = []
        warnings = []
        status = "unknown"
        peer_chain_id = manifest.get("chain_id")
        peer_height = int(manifest.get("height")) if manifest.get("height") is not None else None
        local_height = int(local.get("height")) if local.get("height") is not None else None
        if peer_chain_id != protocol.CHAIN_ID:
            status = "chain_mismatch"
            errors.append("Peer chain_id does not match local chain.")
        elif manifest.get("genesis_hash") != local.get("genesis_hash"):
            status = "genesis_mismatch"
            errors.append("Peer genesis hash does not match local genesis.")
        elif manifest.get("chain_digest") == local.get("chain_digest"):
            status = "same"
        elif peer_height is not None and local_height is not None and peer_height > local_height:
            status = "peer_ahead"
            warnings.append("Peer advertises a higher tip; snapshot verification is required before import.")
        elif peer_height is not None and local_height is not None and peer_height < local_height:
            status = "peer_behind"
        elif manifest.get("tip_hash") == local.get("tip_hash"):
            status = "same_tip_digest_mismatch"
            errors.append("Peer tip matches but chain digest differs.")
        else:
            status = "diverged"
            errors.append("Peer chain does not match local tip or digest.")
        return {
            "status": status,
            "compatible": not errors and peer_chain_id == protocol.CHAIN_ID and manifest.get("genesis_hash") == local.get("genesis_hash"),
            "errors": errors,
            "warnings": warnings,
            "local": {
                "chain_id": local.get("chain_id"),
                "height": local_height,
                "tip_hash": local.get("tip_hash"),
                "genesis_hash": local.get("genesis_hash"),
                "chain_digest": local.get("chain_digest"),
            },
            "peer": {
                "chain_id": peer_chain_id,
                "height": peer_height,
                "tip_hash": manifest.get("tip_hash"),
                "genesis_hash": manifest.get("genesis_hash"),
                "chain_digest": manifest.get("chain_digest"),
                "node": manifest.get("node") or {},
            },
        }

    def check_peer(self, url, timeout=5, verify_snapshot=False):
        self.ensure_schema()
        url = self._normalize_peer_url(url)
        manifest_url = self._peer_endpoint(url, "/chain/manifest")
        manifest = self._fetch_peer_json(manifest_url, timeout=timeout)
        comparison = self.compare_peer_manifest(manifest)
        status = comparison["status"]
        peer = self.record_peer_manifest(url, manifest, status)
        result = {
            "url": url,
            "manifest_url": manifest_url,
            "manifest": manifest,
            "comparison": comparison,
            "peer": peer,
        }
        if verify_snapshot:
            snapshot_url = self._peer_endpoint(url, "/chain/snapshot?service_data=0")
            snapshot = self._fetch_peer_json(snapshot_url, timeout=timeout, max_bytes=25_000_000)
            verification = self.verify_chain_snapshot(snapshot)
            snapshot_manifest = snapshot.get("manifest") if isinstance(snapshot, dict) else {}
            if isinstance(snapshot_manifest, dict) and snapshot_manifest.get("chain_digest") != manifest.get("chain_digest"):
                verification = dict(verification)
                verification["valid"] = False
                verification["errors"] = list(verification.get("errors") or []) + ["Snapshot digest does not match fetched peer manifest."]
            result["snapshot_url"] = snapshot_url
            result["snapshot_verification"] = verification
            if not verification.get("valid"):
                peer = self.record_peer_manifest(url, manifest, "snapshot_invalid")
                result["peer"] = peer
        return result

    def check_peers(self, timeout=5, verify_snapshot=False):
        results = []
        for peer in self.peers(limit=500):
            try:
                results.append(self.check_peer(peer["url"], timeout=timeout, verify_snapshot=verify_snapshot))
            except Exception as exc:
                self.record_peer_manifest(peer["url"], {
                    "chain_id": peer.get("chain_id") or protocol.CHAIN_ID,
                    "height": peer.get("last_height"),
                    "tip_hash": peer.get("last_hash"),
                }, "unreachable")
                results.append({
                    "url": peer["url"],
                    "error": str(exc),
                    "comparison": {"status": "unreachable", "compatible": False, "errors": [str(exc)], "warnings": []},
                })
        return {"count": len(results), "results": results}

    def gossip_peers(self, timeout=5, check=False, snapshot=False, max_new=100):
        self.ensure_schema()
        max_new = max(0, min(500, int(max_new or 100)))
        registered_peers = self.peers(limit=500)
        bootstrap_peers = self.bootstrap_peers()["bootstrap_peers"]
        sources = []
        source_seen = set()
        known_urls = set()
        for peer in bootstrap_peers + registered_peers:
            try:
                url = self._normalize_peer_url(peer.get("url") if isinstance(peer, dict) else peer)
            except ValueError:
                continue
            known_urls.add(url)
            if url in source_seen:
                continue
            source_seen.add(url)
            sources.append(url)
        results = []
        added = []
        skipped_existing = 0
        skipped_invalid = 0
        skipped_limit = 0
        for source_url in sources:
            endpoint = self._peer_endpoint(source_url, "/peers?limit=500")
            source_result = {
                "url": source_url,
                "endpoint": endpoint,
                "discovered": 0,
                "added": 0,
                "skipped_existing": 0,
                "skipped_invalid": 0,
                "skipped_limit": 0,
            }
            try:
                payload = self._fetch_peer_json(endpoint, timeout=timeout, max_bytes=2_000_000)
                entries = payload.get("peers") if isinstance(payload, dict) else payload
                if not isinstance(entries, list):
                    raise ValueError("Peer gossip response must contain a peers list.")
            except Exception as exc:
                source_result["error"] = str(exc)
                results.append(source_result)
                continue
            for entry in entries:
                source_result["discovered"] += 1
                if isinstance(entry, dict):
                    raw_url = entry.get("url")
                    label = str(entry.get("label") or "gossip")[:120]
                    notes = str(entry.get("notes") or f"Discovered from {source_url}.")[:500]
                else:
                    raw_url = entry
                    label = "gossip"
                    notes = f"Discovered from {source_url}."
                try:
                    url = self._normalize_peer_url(raw_url)
                except ValueError:
                    skipped_invalid += 1
                    source_result["skipped_invalid"] += 1
                    continue
                if url in known_urls:
                    skipped_existing += 1
                    source_result["skipped_existing"] += 1
                    continue
                if len(added) >= max_new:
                    skipped_limit += 1
                    source_result["skipped_limit"] += 1
                    continue
                peer = self.add_peer(url, label, notes)
                known_urls.add(url)
                item = {"url": url, "peer": peer, "source_url": source_url}
                if check:
                    try:
                        item["check"] = self.check_peer(url, timeout=timeout, verify_snapshot=snapshot)
                    except Exception as exc:
                        item["check_error"] = str(exc)
                added.append(item)
                source_result["added"] += 1
            results.append(source_result)
        return {
            "source_count": len(sources),
            "added_count": len(added),
            "skipped_existing": skipped_existing,
            "skipped_invalid": skipped_invalid,
            "skipped_limit": skipped_limit,
            "added": added,
            "results": results,
        }

    def _int_or_none(self, value):
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _chain_score(self, blocks, transactions):
        blocks = [block for block in (blocks or []) if isinstance(block, dict)]
        transactions = [tx for tx in (transactions or []) if isinstance(tx, dict)]
        height = self._int_or_none(blocks[-1].get("height")) if blocks else None
        versioned_blocks = len([block for block in blocks if int(block.get("block_version") or 1) >= 2])
        batched_blocks = len([block for block in blocks if int(block.get("tx_count") or 0) > 1])
        signed_spends = len([
            tx for tx in transactions
            if tx.get("kind") in ("transfer", "redeem", "product_redeem") and tx.get("signature")
        ])
        score = [
            int(height if height is not None else -1),
            versioned_blocks,
            signed_spends,
            len(transactions),
        ]
        return {
            "policy": protocol.FORK_CHOICE_POLICY,
            "score": score,
            "height": height,
            "blocks": len(blocks),
            "transactions": len(transactions),
            "versioned_blocks": versioned_blocks,
            "batched_blocks": batched_blocks,
            "signed_spends": signed_spends,
            "rule": "height, then versioned blocks, signed spends, and transaction count",
        }

    def _score_winner(self, local_score, peer_score):
        local_tuple = tuple(local_score.get("score") or [])
        peer_tuple = tuple(peer_score.get("score") or [])
        if peer_tuple > local_tuple:
            return "peer"
        if peer_tuple < local_tuple:
            return "local"
        return "tie"

    def _producer_policy_for_blocks(self, blocks, from_height=0):
        policy = self.consensus_policy()
        allowed = set(policy.get("allowed_producers") or [])
        errors = []
        warnings = []
        checked = 0
        rejected = []
        legacy = 0
        for block in blocks or []:
            if not isinstance(block, dict):
                continue
            height = self._int_or_none(block.get("height"))
            if height is None or height < int(from_height or 0):
                continue
            block_version = int(block.get("block_version") or 1)
            if block_version < 2:
                legacy += 1
                if not policy.get("legacy_blocks_allowed"):
                    errors.append(f"Block {height} is legacy v{block_version}, which this policy does not accept.")
                continue
            checked += 1
            producer_id = str(block.get("producer_id") or "").strip()
            if producer_id not in allowed:
                rejected.append({"height": height, "producer_id": producer_id or "missing"})
                errors.append(f"Block {height} producer {producer_id or 'missing'} is not in allowed_producers.")
        if legacy:
            warnings.append(f"{legacy} legacy block(s) are accepted by compatibility policy.")
        return {
            "policy_version": protocol.PRODUCER_POLICY_VERSION,
            "valid": not errors,
            "allowed_producers": sorted(allowed),
            "checked_versioned_blocks": checked,
            "legacy_blocks": legacy,
            "rejected_blocks": rejected,
            "errors": errors[:100],
            "warnings": warnings[:100],
        }

    def _fork_choice(self, status, snapshot_valid, local_score, peer_score, common_height, fork_depth, producer_policy=None):
        score_winner = self._score_winner(local_score, peer_score)
        producer_policy = producer_policy or {"valid": True, "errors": [], "warnings": []}
        producer_policy_valid = bool(producer_policy.get("valid"))
        import_allowed = status == "peer_ahead_candidate" and snapshot_valid and producer_policy_valid
        if protocol.IS_CLOSED_LOOP_MAINNET:
            import_allowed = False
        reorg_required = status == "diverged" and score_winner == "peer"
        reorg_allowed = False
        selected_chain = "local"
        next_action = "none"
        reason = "Local chain remains selected."
        safety_notes = [
            "This policy does not perform automatic fork reorgs.",
            "A peer can only be imported when its verified snapshot extends the local tip exactly.",
        ]
        if protocol.IS_CLOSED_LOOP_MAINNET:
            safety_notes.append(
                "Closed-loop mainnet peer import is disabled until blocks carry cryptographic producer authentication; public manifests are informational only."
            )
        if not snapshot_valid:
            selected_chain = "reject"
            next_action = "reject"
            reason = "Snapshot is invalid under local verification rules."
        elif not producer_policy_valid:
            selected_chain = "reject"
            next_action = "reject"
            reason = "Peer contains versioned blocks from producer ids this node does not allow."
        elif status == "same":
            selected_chain = "tie"
            reason = "Local and peer snapshots have the same digest and tip."
        elif protocol.IS_CLOSED_LOOP_MAINNET and status == "peer_ahead_candidate":
            selected_chain = "reject"
            next_action = "reject"
            reason = "Closed-loop mainnet peer import is disabled until producer seals are cryptographically authenticated."
        elif import_allowed:
            selected_chain = "peer"
            next_action = "append_import"
            reason = "Peer is a verified append-only extension of the local tip."
        elif status == "peer_behind":
            selected_chain = "local"
            reason = "Peer is a valid prefix behind the local chain."
        elif status == "diverged":
            selected_chain = "local"
            next_action = "manual_review"
            if reorg_required:
                reason = "Peer scores higher, but reorg import is disabled by policy."
            else:
                reason = "Peer diverges from local history and is not importable by append-only policy."
        elif status == "same_tip_digest_mismatch":
            selected_chain = "local"
            next_action = "manual_review"
            reason = "Peer tip matches local tip, but digest differs."
        elif status in ("chain_mismatch", "genesis_mismatch", "snapshot_invalid"):
            selected_chain = "reject"
            next_action = "reject"
            reason = "Peer is not compatible with this chain."
        return {
            "policy": protocol.FORK_CHOICE_POLICY,
            "selected_chain": selected_chain,
            "score_winner": score_winner,
            "import_allowed": import_allowed,
            "reorg_allowed": reorg_allowed,
            "reorg_required": reorg_required,
            "next_action": next_action,
            "reason": reason,
            "common_height": common_height,
            "fork_depth": int(fork_depth or 0),
            "local_score": local_score,
            "peer_score": peer_score,
            "producer_policy": producer_policy,
            "safety_notes": safety_notes,
        }

    def evaluate_chain_snapshot(self, snapshot, peer_manifest=None):
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        snapshot_manifest = snapshot.get("manifest") if isinstance(snapshot.get("manifest"), dict) else {}
        manifest = peer_manifest if isinstance(peer_manifest, dict) and peer_manifest else snapshot_manifest
        blocks = snapshot.get("blocks") if isinstance(snapshot.get("blocks"), list) else []
        transactions = snapshot.get("transactions") if isinstance(snapshot.get("transactions"), list) else []
        verification = self.verify_chain_snapshot(snapshot)
        snapshot_errors = list(verification.get("errors") or [])
        errors = list(snapshot_errors)
        warnings = list(verification.get("warnings") or [])

        fetched_digest = manifest.get("chain_digest")
        snapshot_digest = snapshot_manifest.get("chain_digest")
        if fetched_digest and snapshot_digest and fetched_digest != snapshot_digest:
            snapshot_errors.append("Fetched peer manifest digest does not match snapshot manifest digest.")
            errors.append("Fetched peer manifest digest does not match snapshot manifest digest.")

        self.ensure_schema()
        conn = self.connect()
        try:
            local_blocks = [self._block_from_row(row) for row in conn.execute("SELECT * FROM blocks ORDER BY height").fetchall()]
            local_transactions = self._ledger_transactions(conn)
            local_wallet_keys = self._ledger_wallet_keys(conn)
        finally:
            conn.close()

        local_manifest = {
            "chain_id": protocol.CHAIN_ID,
            "height": local_blocks[-1]["height"] if local_blocks else None,
            "tip_hash": local_blocks[-1]["block_hash"] if local_blocks else None,
            "genesis_hash": local_blocks[0]["block_hash"] if local_blocks else None,
            "blocks": len(local_blocks),
            "transactions": len(local_transactions),
            "wallet_keys": len(local_wallet_keys),
            "chain_digest": self.chain_digest(local_blocks, local_transactions, local_wallet_keys),
        }
        peer_height = self._int_or_none(verification.get("tip", {}).get("height"))
        peer_tip_hash = verification.get("tip", {}).get("hash") or manifest.get("tip_hash")
        peer_genesis_hash = manifest.get("genesis_hash") or (blocks[0].get("block_hash") if blocks else None)
        peer_digest = fetched_digest or snapshot_digest or verification.get("chain_digest")
        local_height = self._int_or_none(local_manifest.get("height"))

        status = "snapshot_invalid"
        recommended_action = "reject"
        compatible = False
        common_height = None
        common_hash = None
        importable_blocks = 0
        fork_depth = 0

        snapshot_valid = bool(verification.get("valid") and not snapshot_errors)

        if not snapshot_valid:
            status = "snapshot_invalid"
            recommended_action = "reject"
        elif (manifest.get("chain_id") or verification.get("chain_id")) != protocol.CHAIN_ID:
            status = "chain_mismatch"
            recommended_action = "reject"
            errors.append("Peer chain_id does not match local chain.")
        elif peer_genesis_hash and peer_genesis_hash != local_manifest.get("genesis_hash"):
            status = "genesis_mismatch"
            recommended_action = "reject"
            errors.append("Peer genesis hash does not match local genesis.")
        else:
            compatible = True
            local_hashes = [block.get("block_hash") for block in local_blocks]
            peer_hashes = [block.get("block_hash") for block in blocks if isinstance(block, dict)]
            common_index = -1
            for idx, (local_hash, peer_hash) in enumerate(zip(local_hashes, peer_hashes)):
                if local_hash != peer_hash:
                    break
                common_index = idx
            if common_index >= 0:
                common_height = common_index
                common_hash = local_hashes[common_index]

            local_is_prefix = local_height is not None and common_index == local_height
            peer_is_prefix = peer_height is not None and common_index == peer_height
            same_digest = peer_digest == local_manifest.get("chain_digest")
            same_tip = peer_tip_hash == local_manifest.get("tip_hash")

            if same_digest and same_tip:
                status = "same"
                recommended_action = "none"
            elif local_is_prefix and peer_height is not None and local_height is not None and peer_height > local_height:
                status = "peer_ahead_candidate"
                recommended_action = "candidate_import"
                importable_blocks = peer_height - local_height
                common_height = local_height
                common_hash = local_manifest.get("tip_hash")
                warnings.append("Peer snapshot is a valid append-only extension candidate. Chain import is not enabled by this preview.")
            elif peer_is_prefix and peer_height is not None and local_height is not None and peer_height < local_height:
                status = "peer_behind"
                recommended_action = "none"
            elif same_tip:
                status = "same_tip_digest_mismatch"
                recommended_action = "manual_review"
                errors.append("Peer tip matches local tip but chain digest differs.")
            else:
                status = "diverged"
                recommended_action = "manual_review"
                if local_height is not None:
                    fork_depth = local_height - common_index if common_index >= 0 else local_height + 1
                errors.append("Peer snapshot is valid, but it is not an append-only extension of the local chain.")

        policy_from_height = int(common_height) + 1 if common_height is not None else 0
        producer_policy = self._producer_policy_for_blocks(blocks, from_height=policy_from_height)
        if snapshot_valid and not producer_policy.get("valid"):
            errors.extend(producer_policy.get("errors") or [])
            if status in ("peer_ahead_candidate", "diverged"):
                status = "producer_policy_rejected"
                recommended_action = "reject"

        local_score = self._chain_score(local_blocks, local_transactions)
        peer_score = self._chain_score(blocks, transactions)
        fork_choice = self._fork_choice(status, snapshot_valid, local_score, peer_score, common_height, fork_depth, producer_policy)
        if fork_choice.get("next_action") == "append_import":
            recommended_action = "candidate_import"
        elif fork_choice.get("next_action") in ("manual_review", "reject"):
            recommended_action = fork_choice["next_action"]

        return {
            "status": status,
            "compatible": compatible and status not in {"snapshot_invalid", "chain_mismatch", "genesis_mismatch"},
            "snapshot_valid": snapshot_valid,
            "mutates_chain": False,
            "recommended_action": recommended_action,
            "fork_choice": fork_choice,
            "producer_policy": producer_policy,
            "importable_blocks": int(importable_blocks),
            "fork_depth": int(fork_depth),
            "common_height": common_height,
            "common_hash": common_hash,
            "errors": errors[:100],
            "warnings": warnings[:100],
            "local": local_manifest,
            "peer": {
                "chain_id": manifest.get("chain_id") or verification.get("chain_id"),
                "height": peer_height,
                "tip_hash": peer_tip_hash,
                "genesis_hash": peer_genesis_hash,
                "blocks": self._int_or_none(manifest.get("blocks")) if manifest.get("blocks") is not None else len(blocks),
                "transactions": self._int_or_none(manifest.get("transactions")),
                "chain_digest": peer_digest,
                "node": manifest.get("node") or {},
            },
            "verification": {
                **verification,
                "valid": snapshot_valid,
                "errors": snapshot_errors[:100],
                "warnings": warnings[:100],
            },
        }

    def _sync_candidate_id(self, url, evaluation):
        seed = "|".join([
            protocol.CHAIN_ID,
            str(url or ""),
            str(evaluation.get("local", {}).get("chain_digest") or ""),
            str(evaluation.get("peer", {}).get("chain_digest") or ""),
            protocol.utc_now(),
            secrets.token_hex(12),
        ])
        return "SCSC-" + protocol.hash_text(seed)[:24]

    def _sync_candidate_from_row(self, row):
        if not row:
            return None
        data = dict(row)
        data["snapshot_valid"] = bool(data.get("snapshot_valid"))
        for key in ("manifest_json", "verification_json", "evaluation_json"):
            try:
                data[key.removesuffix("_json")] = json.loads(data.get(key) or "{}")
            except json.JSONDecodeError:
                data[key.removesuffix("_json")] = {"raw": data.get(key)}
            data.pop(key, None)
        return data

    def record_sync_candidate(self, url, manifest, evaluation, peer=None, notes=""):
        self.ensure_schema()
        url = self._normalize_peer_url(url)
        manifest = manifest if isinstance(manifest, dict) else {}
        evaluation = evaluation if isinstance(evaluation, dict) else {}
        peer = peer or self.add_peer(url)
        now = protocol.utc_now()
        candidate_id = self._sync_candidate_id(url, evaluation)
        local = evaluation.get("local") or {}
        remote = evaluation.get("peer") or {}
        conn = self.connect()
        try:
            conn.execute("""
                INSERT INTO chain_sync_candidates(
                    candidate_id, created_at, updated_at, peer_id, url, status,
                    recommended_action, snapshot_valid, local_height, local_tip_hash,
                    peer_height, peer_tip_hash, common_height, common_hash,
                    importable_blocks, fork_depth, local_chain_digest,
                    peer_chain_digest, manifest_json, verification_json,
                    evaluation_json, notes
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                candidate_id,
                now,
                now,
                peer.get("peer_id"),
                url,
                str(evaluation.get("status") or "unknown")[:60],
                str(evaluation.get("recommended_action") or "manual_review")[:60],
                1 if evaluation.get("snapshot_valid") else 0,
                self._int_or_none(local.get("height")),
                local.get("tip_hash"),
                self._int_or_none(remote.get("height")),
                remote.get("tip_hash"),
                self._int_or_none(evaluation.get("common_height")),
                evaluation.get("common_hash"),
                int(evaluation.get("importable_blocks") or 0),
                int(evaluation.get("fork_depth") or 0),
                local.get("chain_digest"),
                remote.get("chain_digest"),
                protocol.canonical_json(manifest),
                protocol.canonical_json(evaluation.get("verification") or {}),
                protocol.canonical_json(evaluation),
                str(notes or "")[:1000],
            ))
            conn.commit()
            return self._sync_candidate_from_row(conn.execute(
                "SELECT * FROM chain_sync_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone())
        finally:
            conn.close()

    def sync_candidates(self, status=None, limit=25):
        self.ensure_schema()
        limit = max(1, min(200, int(limit)))
        clauses = []
        params = []
        if status:
            clauses.append("status = ?")
            params.append(str(status).strip().lower())
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        conn = self.connect()
        try:
            rows = conn.execute(f"""
                SELECT *
                FROM chain_sync_candidates
                {where}
                ORDER BY created_at DESC, candidate_id DESC
                LIMIT ?
            """, (*params, limit)).fetchall()
            return [self._sync_candidate_from_row(row) for row in rows]
        finally:
            conn.close()

    def sync_candidate(self, candidate_id):
        self.ensure_schema()
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT * FROM chain_sync_candidates WHERE candidate_id = ?",
                (str(candidate_id or "").strip().upper(),),
            ).fetchone()
            return self._sync_candidate_from_row(row)
        finally:
            conn.close()

    def peer_sync_preview(self, url, timeout=5, store=True):
        self.ensure_schema()
        url = self._normalize_peer_url(url)
        manifest_url = self._peer_endpoint(url, "/chain/manifest")
        snapshot_url = self._peer_endpoint(url, "/chain/snapshot?service_data=0")
        manifest = self._fetch_peer_json(manifest_url, timeout=timeout)
        comparison = self.compare_peer_manifest(manifest)
        peer = self.record_peer_manifest(url, manifest, comparison["status"])
        snapshot = self._fetch_peer_json(snapshot_url, timeout=timeout, max_bytes=25_000_000)
        evaluation = self.evaluate_chain_snapshot(snapshot, manifest)
        peer_status = evaluation.get("status") or comparison["status"]
        peer = self.record_peer_manifest(url, manifest, peer_status)
        result = {
            "url": url,
            "manifest_url": manifest_url,
            "snapshot_url": snapshot_url,
            "manifest": manifest,
            "comparison": comparison,
            "evaluation": evaluation,
            "peer": peer,
        }
        if store:
            result["candidate"] = self.record_sync_candidate(url, manifest, evaluation, peer)
        return result

    def peers_sync_preview(self, timeout=5, store=True):
        results = []
        for peer in self.peers(limit=500):
            try:
                results.append(self.peer_sync_preview(peer["url"], timeout=timeout, store=store))
            except Exception as exc:
                self.record_peer_manifest(peer["url"], {
                    "chain_id": peer.get("chain_id") or protocol.CHAIN_ID,
                    "height": peer.get("last_height"),
                    "tip_hash": peer.get("last_hash"),
                }, "sync_unreachable")
                results.append({
                    "url": peer["url"],
                    "error": str(exc),
                    "evaluation": {
                        "status": "sync_unreachable",
                        "compatible": False,
                        "snapshot_valid": False,
                        "mutates_chain": False,
                        "recommended_action": "retry",
                        "errors": [str(exc)],
                        "warnings": [],
                    },
                })
        return {"count": len(results), "results": results}

    def _sync_import_id(self, url, evaluation):
        seed = "|".join([
            protocol.CHAIN_ID,
            str(url or ""),
            str(evaluation.get("local", {}).get("chain_digest") or ""),
            str(evaluation.get("peer", {}).get("chain_digest") or ""),
            protocol.utc_now(),
            secrets.token_hex(12),
        ])
        return "SCSI-" + protocol.hash_text(seed)[:24]

    def _db_backup_path(self, import_id):
        stamp = protocol.utc_now().replace(":", "").replace("-", "").replace("Z", "Z")
        filename = f"{self.db_path.stem}.{stamp}.{import_id}.backup.sqlite3"
        return self.db_path.with_name(filename)

    def create_backup(self, import_id=None):
        self.ensure_schema()
        import_id = import_id or ("manual-" + secrets.token_hex(6))
        backup_path = self._db_backup_path(import_id)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        source = self.connect()
        dest = sqlite3.connect(str(backup_path))
        try:
            source.backup(dest)
        finally:
            dest.close()
            source.close()
        return str(backup_path)

    def restore_backup(self, backup_path):
        backup_path = Path(backup_path)
        if not backup_path.exists():
            raise ValueError("SpaceCash backup file not found.")
        shutil.copy2(str(backup_path), str(self.db_path))
        return {"restored": True, "backup_path": str(backup_path)}

    def _chain_manifest_locked(self, conn):
        blocks = [self._block_from_row(row) for row in conn.execute("SELECT * FROM blocks ORDER BY height").fetchall()]
        transactions = self._ledger_transactions(conn)
        wallet_keys = self._ledger_wallet_keys(conn)
        tip = blocks[-1] if blocks else None
        return {
            "chain_id": protocol.CHAIN_ID,
            "height": tip["height"] if tip else None,
            "tip_hash": tip["block_hash"] if tip else None,
            "genesis_hash": blocks[0]["block_hash"] if blocks else None,
            "blocks": len(blocks),
            "transactions": len(transactions),
            "wallet_keys": len(wallet_keys),
            "chain_digest": self.chain_digest(blocks, transactions, wallet_keys),
        }

    def _record_sync_import_locked(self, conn, url, evaluation, status, candidate_id=None, peer_id=None,
                                   imported_blocks=0, imported_transactions=0, backup_path=None,
                                   errors=None, notes=""):
        import_id = self._sync_import_id(url, evaluation)
        local = evaluation.get("local") or {}
        remote = evaluation.get("peer") or {}
        conn.execute("""
            INSERT INTO chain_sync_imports(
                import_id, created_at, peer_id, url, candidate_id, status,
                local_height_before, local_tip_before, imported_height,
                imported_tip_hash, imported_blocks, imported_transactions,
                backup_path, evaluation_json, errors_json, notes
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            import_id,
            protocol.utc_now(),
            peer_id,
            self._normalize_peer_url(url) if url else "",
            candidate_id,
            str(status or "unknown")[:60],
            self._int_or_none(local.get("height")),
            local.get("tip_hash"),
            self._int_or_none(remote.get("height")),
            remote.get("tip_hash"),
            int(imported_blocks or 0),
            int(imported_transactions or 0),
            backup_path,
            protocol.canonical_json(evaluation),
            protocol.canonical_json(errors or []),
            str(notes or "")[:1000],
        ))
        row = conn.execute("SELECT * FROM chain_sync_imports WHERE import_id = ?", (import_id,)).fetchone()
        return dict(row)

    def sync_imports(self, status=None, limit=25):
        self.ensure_schema()
        limit = max(1, min(200, int(limit)))
        clauses = []
        params = []
        if status:
            clauses.append("status = ?")
            params.append(str(status).strip().lower())
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        conn = self.connect()
        try:
            rows = conn.execute(f"""
                SELECT *
                FROM chain_sync_imports
                {where}
                ORDER BY created_at DESC, import_id DESC
                LIMIT ?
            """, (*params, limit)).fetchall()
            imports = []
            for row in rows:
                data = dict(row)
                for key in ("evaluation_json", "errors_json"):
                    try:
                        data[key.removesuffix("_json")] = json.loads(data.get(key) or ("[]" if key == "errors_json" else "{}"))
                    except json.JSONDecodeError:
                        data[key.removesuffix("_json")] = {"raw": data.get(key)}
                    data.pop(key, None)
                imports.append(data)
            return imports
        finally:
            conn.close()

    def _snapshot_wallet_keys_by_address(self, snapshot):
        keys = {}
        for wallet in (snapshot.get("wallet_keys") or []):
            if not isinstance(wallet, dict):
                continue
            address = str(wallet.get("address") or "").strip().upper()
            public_key = protocol.normalize_public_jwk(wallet.get("public_key_jwk"))
            if protocol.address_from_public_jwk(public_key) != address:
                raise ValueError(f"Snapshot wallet key does not derive to {address}.")
            keys[address] = public_key
        return keys

    def _import_wallet_keys_locked(self, conn, wallet_keys_by_address):
        for address, public_key in wallet_keys_by_address.items():
            self._ensure_wallet(conn, address, "Imported Signed SpaceCash Wallet", None, public_key, "ecdsa-p256")

    def _signed_payload_for_import(self, tx):
        if not tx.get("signature"):
            return None
        if not tx.get("signed_payload"):
            raise ValueError(f"{tx.get('txid')} has a signature but no signed payload.")
        try:
            signed_payload = json.loads(tx.get("signed_payload"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{tx.get('txid')} has invalid signed payload JSON.") from exc
        if protocol.payload_hash(signed_payload) != tx.get("payload_hash"):
            raise ValueError(f"{tx.get('txid')} signed payload hash does not match.")
        nonce = str(signed_payload.get("nonce") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{8,128}", nonce):
            raise ValueError(f"{tx.get('txid')} signed nonce is missing or invalid.")
        return signed_payload

    def _apply_imported_tx_locked(self, conn, tx, wallet_keys_by_address, allow_legacy_unsigned=False):
        txid = str(tx.get("txid") or "").strip().upper()
        if not re.fullmatch(r"SCTX-[A-F0-9]{24}", txid):
            raise ValueError("Imported transaction has an invalid txid.")
        if conn.execute("SELECT 1 FROM transactions WHERE txid = ?", (txid,)).fetchone():
            raise ValueError(f"Imported transaction {txid} already exists locally.")
        kind = str(tx.get("kind") or "").strip()
        sender = str(tx.get("sender") or "").strip().upper() or None
        recipient = str(tx.get("recipient") or "").strip().upper() or None
        amount_units = int(tx.get("amount_units") or 0)
        if amount_units <= 0:
            raise ValueError(f"Imported transaction {txid} has a non-positive amount.")
        if kind in ("transfer", "redeem", "product_redeem") and not tx.get("signature") and not allow_legacy_unsigned:
            raise ValueError(f"Imported transaction {txid} is an unsigned spend.")
        signed_payload = self._signed_payload_for_import(tx)
        if signed_payload:
            public_key = wallet_keys_by_address.get(sender)
            if not public_key:
                raise ValueError(f"Imported transaction {txid} has no exported sender public key.")
            self._verify_payload_with_jwk(public_key, signed_payload, tx.get("signature"))
            nonce = str(signed_payload.get("nonce") or "").strip()
            if conn.execute("SELECT 1 FROM nonces WHERE address = ? AND nonce = ?", (sender, nonce)).fetchone():
                raise ValueError(f"Imported transaction {txid} reuses a mined nonce.")
            conn.execute("""
                INSERT INTO nonces(address, nonce, payload_hash, created_at)
                VALUES(?,?,?,?)
            """, (sender, nonce, tx.get("payload_hash"), tx.get("created_at") or protocol.utc_now()))

        if sender:
            self._ensure_wallet(conn, sender, "Imported SpaceCash Wallet")
            if self._get_balance(conn, sender) < amount_units:
                raise ValueError(f"Imported transaction {txid} would make {sender} negative.")
        if recipient:
            self._ensure_wallet(conn, recipient, "Imported SpaceCash Wallet")
        if sender:
            conn.execute("UPDATE balances SET units = units - ?, updated_at = ? WHERE address = ?", (amount_units, protocol.utc_now(), sender))
        if recipient:
            conn.execute("UPDATE balances SET units = units + ?, updated_at = ? WHERE address = ?", (amount_units, protocol.utc_now(), recipient))

        conn.execute("""
            INSERT INTO transactions(
                txid, created_at, kind, sender, recipient, amount_units, memo,
                related_source, related_id, payload_hash, signature, signed_payload,
                block_height
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            txid,
            tx.get("created_at") or protocol.utc_now(),
            kind,
            sender,
            recipient,
            amount_units,
            (tx.get("memo") or "")[:240],
            tx.get("related_source"),
            str(tx.get("related_id")) if tx.get("related_id") is not None else None,
            tx.get("payload_hash"),
            tx.get("signature"),
            tx.get("signed_payload"),
            self._int_or_none(tx.get("block_height")),
        ))
        if tx.get("payload_hash"):
            conn.execute("""
                UPDATE mempool_transactions
                SET status = 'mined', updated_at = ?, txid = ?, error = NULL
                WHERE status = 'pending' AND payload_hash = ?
            """, (protocol.utc_now(), txid, tx.get("payload_hash")))
        if signed_payload and sender:
            conn.execute("""
                UPDATE mempool_transactions
                SET status = 'rejected', updated_at = ?, error = ?
                WHERE status = 'pending' AND sender = ? AND nonce = ? AND payload_hash != ?
            """, (
                protocol.utc_now(),
                "Rejected because sync imported another transaction with this nonce.",
                sender,
                str(signed_payload.get("nonce") or "").strip(),
                tx.get("payload_hash"),
            ))

    def import_chain_snapshot(self, snapshot, peer_manifest=None, url="", candidate_id=None,
                              backup=True, allow_legacy_unsigned=False, notes=""):
        self.ensure_schema()
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        manifest = peer_manifest if isinstance(peer_manifest, dict) and peer_manifest else snapshot.get("manifest")
        evaluation = self.evaluate_chain_snapshot(snapshot, manifest)
        fork_choice = evaluation.get("fork_choice") or {}
        if not fork_choice.get("import_allowed"):
            return {
                "imported": False,
                "status": evaluation.get("status"),
                "reason": fork_choice.get("reason") or "Only verified append-only peer_ahead_candidate snapshots can be imported.",
                "evaluation": evaluation,
            }
        pre_audit = self.audit()
        if not pre_audit.get("valid"):
            raise ValueError("Local SpaceCash audit must be valid before sync import.")

        import_id = self._sync_import_id(url, evaluation)
        backup_path = self.create_backup(import_id) if backup else None
        wallet_keys_by_address = self._snapshot_wallet_keys_by_address(snapshot)
        local_height = self._int_or_none(evaluation.get("local", {}).get("height"))
        blocks = [block for block in snapshot.get("blocks", []) if int(block.get("height")) > int(local_height)]
        transactions = [
            tx for tx in snapshot.get("transactions", [])
            if tx.get("block_height") is not None and int(tx.get("block_height")) > int(local_height)
        ]
        txs_by_height = {}
        for tx in transactions:
            txs_by_height.setdefault(int(tx.get("block_height")), []).append(tx)

        conn = self.connect()
        committed = False
        try:
            conn.execute("BEGIN IMMEDIATE")
            current = self._chain_manifest_locked(conn)
            expected_local = evaluation.get("local") or {}
            if current.get("chain_digest") != expected_local.get("chain_digest"):
                raise ValueError("Local chain changed after sync preview; rerun preview before importing.")
            self._import_wallet_keys_locked(conn, wallet_keys_by_address)
            previous_hash = current.get("tip_hash")
            imported_tx_count = 0
            for block in sorted(blocks, key=lambda item: int(item.get("height"))):
                height = int(block.get("height"))
                if height != int(local_height) + len([b for b in blocks if int(b.get("height")) < height]) + 1:
                    raise ValueError(f"Imported block {height} is not the next append-only height.")
                if block.get("previous_hash") != previous_hash:
                    raise ValueError(f"Imported block {height} does not extend the local tip.")
                height_txs = {str(tx.get("txid") or "").strip().upper(): tx for tx in txs_by_height.get(height, [])}
                if int(block.get("block_version") or 1) >= 2:
                    ordered_txids = json.loads(block.get("txids_json") or "[]")
                else:
                    ordered_txids = [block.get("txid")]
                for txid in ordered_txids:
                    tx = height_txs.get(str(txid or "").strip().upper())
                    if not tx:
                        raise ValueError(f"Imported block {height} references missing transaction {txid}.")
                    self._apply_imported_tx_locked(conn, tx, wallet_keys_by_address, allow_legacy_unsigned)
                    imported_tx_count += 1
                conn.execute("""
                    INSERT INTO blocks(
                        height, created_at, previous_hash, txid, tx_count, merkle_root,
                        block_hash, txids_json, producer_id, producer_seal, block_version
                    )
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    height,
                    block.get("created_at"),
                    block.get("previous_hash"),
                    block.get("txid"),
                    int(block.get("tx_count") or 0),
                    block.get("merkle_root"),
                    block.get("block_hash"),
                    block.get("txids_json"),
                    block.get("producer_id"),
                    block.get("producer_seal"),
                    int(block.get("block_version") or 1),
                ))
                previous_hash = block.get("block_hash")
            import_row = self._record_sync_import_locked(
                conn,
                url,
                evaluation,
                "imported",
                candidate_id,
                None,
                len(blocks),
                imported_tx_count,
                backup_path,
                [],
                notes,
            )
            conn.commit()
            committed = True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        post_audit = self.audit()
        if not post_audit.get("valid"):
            if backup_path:
                self.restore_backup(backup_path)
            return {
                "imported": False,
                "status": "restored_after_audit_failure",
                "backup_path": backup_path,
                "audit": post_audit,
                "evaluation": evaluation,
            }
        return {
            "imported": committed,
            "status": "imported",
            "import": import_row,
            "backup_path": backup_path,
            "imported_blocks": len(blocks),
            "imported_transactions": len(transactions),
            "audit": post_audit,
            "evaluation": evaluation,
        }

    def peer_sync_import(self, url, timeout=5, confirm=False, backup=True, allow_legacy_unsigned=False):
        self.ensure_schema()
        url = self._normalize_peer_url(url)
        manifest_url = self._peer_endpoint(url, "/chain/manifest")
        snapshot_url = self._peer_endpoint(url, "/chain/snapshot?service_data=0")
        manifest = self._fetch_peer_json(manifest_url, timeout=timeout)
        comparison = self.compare_peer_manifest(manifest)
        peer = self.record_peer_manifest(url, manifest, comparison["status"])
        snapshot = self._fetch_peer_json(snapshot_url, timeout=timeout, max_bytes=25_000_000)
        evaluation = self.evaluate_chain_snapshot(snapshot, manifest)
        peer = self.record_peer_manifest(url, manifest, evaluation.get("status") or comparison["status"])
        candidate = self.record_sync_candidate(url, manifest, evaluation, peer)
        result = {
            "url": url,
            "manifest_url": manifest_url,
            "snapshot_url": snapshot_url,
            "comparison": comparison,
            "evaluation": evaluation,
            "candidate": candidate,
            "peer": peer,
            "requires_confirmation": not confirm,
            "imported": False,
        }
        if not confirm:
            return result
        import_result = self.import_chain_snapshot(
            snapshot,
            manifest,
            url=url,
            candidate_id=candidate.get("candidate_id"),
            backup=backup,
            allow_legacy_unsigned=allow_legacy_unsigned,
            notes="Imported from peer sync.",
        )
        result.update(import_result)
        result["requires_confirmation"] = False
        return result

    def _pending_id(self, payload_hash):
        return "SCPX-" + protocol.hash_text(f"{protocol.CHAIN_ID}|{payload_hash}")[:24]

    def _pending_reserved_units(self, conn, address):
        row = conn.execute("""
            SELECT COALESCE(SUM(amount_units), 0) AS units
            FROM mempool_transactions
            WHERE sender = ? AND status = 'pending'
        """, (address,)).fetchone()
        return int(row["units"] or 0)

    def _pending_from_row(self, row, include_payload=False):
        if not row:
            return None
        data = {
            "pending_id": row["pending_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "kind": row["kind"],
            "sender": row["sender"],
            "recipient": row["recipient"],
            "amount_units": int(row["amount_units"]),
            "amount": protocol.units_to_amount(row["amount_units"]),
            "symbol": protocol.SYMBOL,
            "memo": row["memo"] or "",
            "related_source": row["related_source"],
            "related_id": row["related_id"],
            "payload_hash": row["payload_hash"],
            "nonce": row["nonce"],
            "signature_present": bool(row["signature"]),
            "status": row["status"],
            "error": row["error"] or "",
            "txid": row["txid"],
        }
        if row["product_snapshot"]:
            try:
                data["product"] = json.loads(row["product_snapshot"])
            except json.JSONDecodeError:
                data["product"] = {"raw": row["product_snapshot"]}
        if include_payload:
            try:
                data["signed_payload"] = json.loads(row["signed_payload"])
            except json.JSONDecodeError:
                data["signed_payload"] = row["signed_payload"]
            data["signature"] = row["signature"]
        return data

    def pending_transactions(self, status="pending", sender=None, limit=25):
        self.ensure_schema()
        limit = max(1, min(200, int(limit)))
        clauses = []
        params = []
        if status:
            clauses.append("status = ?")
            params.append(str(status).strip().lower())
        if sender:
            clauses.append("sender = ?")
            params.append(str(sender).strip().upper())
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        conn = self.connect()
        try:
            rows = conn.execute(f"""
                SELECT *
                FROM mempool_transactions
                {where}
                ORDER BY created_at DESC, pending_id DESC
                LIMIT ?
            """, (*params, limit)).fetchall()
            return [self._pending_from_row(row) for row in rows]
        finally:
            conn.close()

    def pending_transaction(self, pending_id):
        self.ensure_schema()
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT * FROM mempool_transactions WHERE pending_id = ?",
                (str(pending_id or "").strip().upper(),),
            ).fetchone()
            return self._pending_from_row(row, include_payload=True)
        finally:
            conn.close()

    def status(self):
        self.ensure_schema()
        conn = self.connect()
        try:
            latest_block = conn.execute("SELECT height, block_hash FROM blocks ORDER BY height DESC LIMIT 1").fetchone()
            treasury_units = self._get_balance(conn, protocol.TREASURY)
            return {
                "chain_id": protocol.CHAIN_ID,
                "symbol": protocol.SYMBOL,
                "unit_name": "SpaceCash",
                "mode": protocol.NETWORK_MODE,
                "network_profile": protocol.NETWORK_PROFILE,
                "decimals": protocol.DECIMALS,
                "signed_payload_version": protocol.SIGNED_PAYLOAD_VERSION,
                "block_version": protocol.BLOCK_VERSION,
                "producer_id": protocol.PRODUCER_ID,
                "wallets": conn.execute("SELECT COUNT(*) AS n FROM wallets").fetchone()["n"],
                "transactions": conn.execute("SELECT COUNT(*) AS n FROM transactions").fetchone()["n"],
                "blocks": conn.execute("SELECT COUNT(*) AS n FROM blocks").fetchone()["n"],
                "product_orders": conn.execute("SELECT COUNT(*) AS n FROM product_orders").fetchone()["n"],
                "mempool_pending": conn.execute("SELECT COUNT(*) AS n FROM mempool_transactions WHERE status = 'pending'").fetchone()["n"],
                "mempool_total": conn.execute("SELECT COUNT(*) AS n FROM mempool_transactions").fetchone()["n"],
                "latest_block": latest_block["height"] if latest_block else None,
                "latest_block_hash": latest_block["block_hash"] if latest_block else None,
                "treasury": protocol.units_to_amount(treasury_units),
                "faucet": None if protocol.IS_CLOSED_LOOP_MAINNET else protocol.units_to_amount(protocol.FAUCET_UNITS),
                "distribution": "earned NSP participation rewards only" if protocol.IS_CLOSED_LOOP_MAINNET else "development faucet",
            }
        finally:
            conn.close()

    def recent_blocks(self, limit=25):
        self.ensure_schema()
        limit = max(1, min(100, int(limit)))
        conn = self.connect()
        try:
            rows = conn.execute("""
                SELECT *
                FROM blocks
                ORDER BY height DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [self._block_from_row(row) for row in rows]
        finally:
            conn.close()

    def _block_from_row(self, row):
        if not row:
            return None
        data = dict(row)
        if data.get("txids_json"):
            try:
                data["txids"] = json.loads(data["txids_json"])
            except json.JSONDecodeError:
                data["txids"] = []
        else:
            data["txids"] = [data["txid"]] if data.get("txid") else []
        data["block_version"] = int(data.get("block_version") or 1)
        data["producer_id"] = data.get("producer_id") or "legacy-local-miner"
        return data

    def transaction(self, txid):
        self.ensure_schema()
        conn = self.connect()
        try:
            row = conn.execute("""
                SELECT t.*, b.block_hash
                FROM transactions t
                LEFT JOIN blocks b ON b.height = t.block_height
                WHERE t.txid = ?
            """, (str(txid).strip().upper(),)).fetchone()
            if not row:
                return None
            data = dict(row)
            data["amount"] = protocol.units_to_amount(row["amount_units"])
            data["signature_present"] = bool(row["signature"])
            if data.get("signature"):
                data["signature"] = data["signature"][:24] + "..."
            return data
        finally:
            conn.close()

    def transaction_proof(self, txid):
        self.ensure_schema()
        txid = str(txid or "").strip().upper()
        conn = self.connect()
        try:
            row = conn.execute("""
                SELECT t.*, b.created_at AS block_created_at, b.previous_hash,
                       b.tx_count, b.merkle_root, b.block_hash, b.txids_json,
                       b.producer_id, b.producer_seal, b.block_version
                FROM transactions t
                LEFT JOIN blocks b ON b.height = t.block_height
                WHERE t.txid = ?
            """, (txid,)).fetchone()
            if not row:
                return None
            tx = dict(row)
            if tx.get("block_height") is None or not tx.get("block_hash"):
                return {
                    "chain_id": protocol.CHAIN_ID,
                    "txid": txid,
                    "included": False,
                    "verified": False,
                    "reason": "Transaction has no block assignment.",
                }
            block_version = int(tx.get("block_version") or 1)
            if block_version >= 2 and tx.get("txids_json"):
                try:
                    txids = json.loads(tx["txids_json"])
                except json.JSONDecodeError as exc:
                    raise ValueError("Block txids_json is invalid; cannot build inclusion proof.") from exc
            else:
                txids = [txid]
            proof = protocol.merkle_proof(txids, txid)
            verified = protocol.verify_merkle_proof(txid, proof["proof"], tx["merkle_root"])
            return {
                "chain_id": protocol.CHAIN_ID,
                "txid": txid,
                "included": True,
                "verified": bool(verified),
                "index": proof["index"],
                "total": proof["total"],
                "leaf_hash": proof["leaf_hash"],
                "merkle_root": tx["merkle_root"],
                "proof": proof["proof"],
                "block": {
                    "height": tx["block_height"],
                    "hash": tx["block_hash"],
                    "created_at": tx["block_created_at"],
                    "previous_hash": tx["previous_hash"],
                    "tx_count": tx["tx_count"],
                    "block_version": block_version,
                    "producer_id": tx.get("producer_id") or "legacy-local-miner",
                    "producer_seal": tx.get("producer_seal"),
                },
                "transaction": {
                    "txid": txid,
                    "created_at": tx["created_at"],
                    "kind": tx["kind"],
                    "sender": tx["sender"],
                    "recipient": tx["recipient"],
                    "amount_units": int(tx["amount_units"]),
                    "amount": protocol.units_to_amount(tx["amount_units"]),
                    "payload_hash": tx["payload_hash"],
                },
            }
        finally:
            conn.close()

    def block(self, ref):
        self.ensure_schema()
        conn = self.connect()
        try:
            if str(ref).isdigit():
                block = conn.execute("SELECT * FROM blocks WHERE height = ?", (int(ref),)).fetchone()
            else:
                block = conn.execute("SELECT * FROM blocks WHERE block_hash = ?", (str(ref).strip().upper(),)).fetchone()
            if not block:
                return None
            txs = conn.execute("""
                SELECT txid, created_at, kind, sender, recipient, amount_units, memo, related_source, related_id, payload_hash, signature
                FROM transactions
                WHERE block_height = ?
                ORDER BY created_at, txid
            """, (block["height"],)).fetchall()
            return {
                "block": self._block_from_row(block),
                "transactions": [
                    {
                        **dict(tx),
                        "amount": protocol.units_to_amount(tx["amount_units"]),
                        "signature_present": bool(tx["signature"]),
                    }
                    for tx in txs
                ],
            }
        finally:
            conn.close()

    def _receipt_id(self, txid):
        return "SCOR-" + protocol.hash_text(f"{protocol.CHAIN_ID}|{txid}")[:24]

    def _order_from_row(self, row):
        if not row:
            return None
        return {
            "receipt_id": row["receipt_id"],
            "txid": row["txid"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "wallet_address": row["wallet_address"],
            "source": row["source"],
            "product_id": row["product_id"],
            "product_name": row["product_name"],
            "amount_units": int(row["amount_units"]),
            "amount": protocol.units_to_amount(row["amount_units"]),
            "symbol": protocol.SYMBOL,
            "status": row["status"],
            "fulfillment_status": row["fulfillment_status"],
            "contact_status": row["contact_status"],
            "notes": row["notes"] or "",
        }

    def _event_from_row(self, row):
        if not row:
            return None
        return {
            "id": row["id"],
            "receipt_id": row["receipt_id"],
            "created_at": row["created_at"],
            "event_type": row["event_type"],
            "actor": row["actor"],
            "status": row["status"],
            "fulfillment_status": row["fulfillment_status"],
            "contact_status": row["contact_status"],
            "notes": row["notes"] or "",
        }

    def product_order(self, receipt_id):
        self.ensure_schema()
        conn = self.connect()
        try:
            row = conn.execute("SELECT * FROM product_orders WHERE receipt_id = ?", (str(receipt_id or "").strip().upper(),)).fetchone()
            return self._order_from_row(row)
        finally:
            conn.close()

    def product_orders(self, wallet_address=None, status=None, limit=25):
        self.ensure_schema()
        limit = max(1, min(100, int(limit)))
        clauses = []
        params = []
        if wallet_address:
            clauses.append("wallet_address = ?")
            params.append(str(wallet_address).strip().upper())
        if status:
            clauses.append("status = ?")
            params.append(str(status).strip().lower())
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        conn = self.connect()
        try:
            rows = conn.execute(f"""
                SELECT *
                FROM product_orders
                {where}
                ORDER BY created_at DESC, receipt_id DESC
                LIMIT ?
            """, (*params, limit)).fetchall()
            return [self._order_from_row(row) for row in rows]
        finally:
            conn.close()

    def product_order_events(self, receipt_id, limit=50):
        self.ensure_schema()
        receipt_id = str(receipt_id or "").strip().upper()
        limit = max(1, min(200, int(limit)))
        conn = self.connect()
        try:
            rows = conn.execute("""
                SELECT *
                FROM product_order_events
                WHERE receipt_id = ?
                ORDER BY id DESC
                LIMIT ?
            """, (receipt_id, limit)).fetchall()
            return [self._event_from_row(row) for row in rows]
        finally:
            conn.close()

    def _insert_order_event(self, conn, receipt_id, event_type, actor="daemon", status=None, fulfillment_status=None, contact_status=None, notes=""):
        conn.execute("""
            INSERT INTO product_order_events(
                receipt_id, created_at, event_type, actor, status,
                fulfillment_status, contact_status, notes
            )
            VALUES(?,?,?,?,?,?,?,?)
        """, (
            receipt_id,
            protocol.utc_now(),
            str(event_type or "updated")[:80],
            str(actor or "daemon")[:80],
            status,
            fulfillment_status,
            contact_status,
            (notes or "")[:1000],
        ))

    def _product_snapshot_from_tx(self, tx, product_lookup=None):
        source = str(tx["related_source"] or "").strip().lower() or "unknown"
        product_id = str(tx["related_id"] or "").strip() or "0"
        product_name = ""
        lookup_warning = None
        if callable(product_lookup) and source != "unknown" and product_id:
            try:
                product = product_lookup(source, int(product_id))
                if product:
                    product_name = str(product.get("name") or "").strip()
            except Exception as exc:
                lookup_warning = str(exc)
        if not product_name:
            memo = str(tx["memo"] or "").strip()
            match = re.match(r"Product redemption:\s*(.+)", memo, re.IGNORECASE)
            if match:
                product_name = match.group(1).strip()
        return {
            "source": source,
            "id": product_id,
            "name": (product_name or "Historical Product Redemption")[:160],
        }, lookup_warning

    def _create_product_order_locked(self, conn, txid, wallet_address, product, amount_units, event_type="created", actor="spacecash_daemon", notes=None):
        source = str(product.get("source") or "").strip().lower()
        product_id = str(product.get("id") or product.get("product_id") or "0").strip()
        product_id = str(int(product_id)) if product_id.isdigit() else product_id
        receipt_id = self._receipt_id(txid)
        now = protocol.utc_now()
        order_notes = notes or "Created by SpaceCash daemon product redemption."
        cursor = conn.execute("""
            INSERT OR IGNORE INTO product_orders(
                receipt_id, txid, created_at, updated_at, wallet_address, source,
                product_id, product_name, amount_units, status, fulfillment_status,
                contact_status, notes
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            receipt_id,
            txid,
            now,
            now,
            wallet_address,
            source,
            product_id,
            str(product.get("name") or "NorthStar Product")[:160],
            int(amount_units),
            "pending_review",
            "pending_review",
            "not_contacted",
            order_notes,
        ))
        if cursor.rowcount:
            self._insert_order_event(
                conn,
                receipt_id,
                event_type,
                actor,
                "pending_review",
                "pending_review",
                "not_contacted",
                order_notes,
            )
        row = conn.execute("SELECT * FROM product_orders WHERE receipt_id = ?", (receipt_id,)).fetchone()
        return self._order_from_row(row)

    def _create_product_order(self, txid, wallet_address, product, amount_units, event_type="created", actor="spacecash_daemon", notes=None):
        self.ensure_schema()
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            order = self._create_product_order_locked(conn, txid, wallet_address, product, amount_units, event_type, actor, notes)
            conn.commit()
            return order
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create_product_order(self, txid, wallet_address, product, amount_units):
        return self._create_product_order(txid, wallet_address, product, amount_units)

    def backfill_product_orders(self, product_lookup=None, actor="operator"):
        self.ensure_schema()
        actor = str(actor or "operator")[:80]
        created_receipts = []
        lookup_warnings = []
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("""
                SELECT tx.*
                FROM transactions tx
                LEFT JOIN product_orders po ON po.txid = tx.txid
                WHERE tx.kind = 'product_redeem'
                  AND po.txid IS NULL
                ORDER BY tx.created_at, tx.txid
            """).fetchall()
            for tx in rows:
                product, warning = self._product_snapshot_from_tx(tx, product_lookup)
                if warning:
                    lookup_warnings.append({"txid": tx["txid"], "warning": warning})
                receipt_id = self._receipt_id(tx["txid"])
                now = protocol.utc_now()
                notes = "Backfilled from historical SpaceCash product redemption."
                cursor = conn.execute("""
                    INSERT OR IGNORE INTO product_orders(
                        receipt_id, txid, created_at, updated_at, wallet_address, source,
                        product_id, product_name, amount_units, status, fulfillment_status,
                        contact_status, notes
                    )
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    receipt_id,
                    tx["txid"],
                    tx["created_at"] or now,
                    now,
                    tx["sender"],
                    product["source"],
                    product["id"],
                    product["name"],
                    int(tx["amount_units"]),
                    "pending_review",
                    "pending_review",
                    "not_contacted",
                    notes,
                ))
                if cursor.rowcount:
                    self._insert_order_event(
                        conn,
                        receipt_id,
                        "backfilled",
                        actor,
                        "pending_review",
                        "pending_review",
                        "not_contacted",
                        notes,
                    )
                    created_receipts.append(receipt_id)
            conn.commit()
            created = []
            for receipt_id in created_receipts:
                row = conn.execute("SELECT * FROM product_orders WHERE receipt_id = ?", (receipt_id,)).fetchone()
                created.append(self._order_from_row(row))
            return {
                "count": len(created),
                "created": created,
                "warnings": lookup_warnings,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def update_product_order(self, receipt_id, status=None, fulfillment_status=None, contact_status=None, notes="", actor="operator"):
        self.ensure_schema()
        receipt_id = str(receipt_id or "").strip().upper()
        status = str(status).strip().lower() if status is not None else None
        fulfillment_status = str(fulfillment_status).strip().lower() if fulfillment_status is not None else None
        contact_status = str(contact_status).strip().lower() if contact_status is not None else None
        if status and status not in self.ORDER_STATUSES:
            raise ValueError("Unsupported SpaceCash order status.")
        if fulfillment_status and fulfillment_status not in self.FULFILLMENT_STATUSES:
            raise ValueError("Unsupported SpaceCash fulfillment status.")
        if contact_status and contact_status not in self.CONTACT_STATUSES:
            raise ValueError("Unsupported SpaceCash contact status.")
        if not any((status, fulfillment_status, contact_status, notes)):
            raise ValueError("Provide at least one SpaceCash order update field.")
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM product_orders WHERE receipt_id = ?", (receipt_id,)).fetchone()
            if not row:
                raise ValueError("SpaceCash product order not found.")
            new_status = status or row["status"]
            new_fulfillment = fulfillment_status or row["fulfillment_status"]
            new_contact = contact_status or row["contact_status"]
            existing_notes = row["notes"] or ""
            merged_notes = existing_notes
            if notes:
                merged_notes = (existing_notes + "\n" if existing_notes else "") + str(notes).strip()
            conn.execute("""
                UPDATE product_orders
                SET updated_at = ?,
                    status = ?,
                    fulfillment_status = ?,
                    contact_status = ?,
                    notes = ?
                WHERE receipt_id = ?
            """, (protocol.utc_now(), new_status, new_fulfillment, new_contact, merged_notes[:2000], receipt_id))
            self._insert_order_event(conn, receipt_id, "updated", actor, new_status, new_fulfillment, new_contact, notes)
            conn.commit()
            updated = conn.execute("SELECT * FROM product_orders WHERE receipt_id = ?", (receipt_id,)).fetchone()
            result = self._order_from_row(updated)
            result["events"] = self.product_order_events(receipt_id)
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_wallet(self, conn, address, label="SpaceCash Wallet", claim_token=None, public_key_jwk=None, auth_scheme=None):
        if not protocol.valid_address(address):
            raise ValueError("Invalid SpaceCash address.")
        now = protocol.utc_now()
        public_key_text = protocol.canonical_json(protocol.normalize_public_jwk(public_key_jwk)) if public_key_jwk is not None else None
        if not conn.execute("SELECT 1 FROM wallets WHERE address = ?", (address,)).fetchone():
            conn.execute("""
                INSERT INTO wallets(address, label, created_at, claim_token, public_key_jwk, auth_scheme)
                VALUES(?,?,?,?,?,?)
            """, (address, label[:80] or "SpaceCash Wallet", now, claim_token, public_key_text, auth_scheme))
        else:
            if public_key_text is not None or auth_scheme is not None:
                conn.execute("""
                    UPDATE wallets
                    SET public_key_jwk = COALESCE(?, public_key_jwk),
                        auth_scheme = COALESCE(?, auth_scheme)
                    WHERE address = ?
                """, (public_key_text, auth_scheme, address))
            if claim_token is not None:
                conn.execute("UPDATE wallets SET claim_token = COALESCE(claim_token, ?) WHERE address = ?", (claim_token, address))
        if not conn.execute("SELECT 1 FROM balances WHERE address = ?", (address,)).fetchone():
            conn.execute("INSERT INTO balances(address, units, updated_at) VALUES(?,?,?)", (address, 0, now))

    def wallet_summary(self, address, limit=12, include_claim=False):
        self.ensure_schema()
        address = (address or "").strip().upper()
        if not protocol.valid_address(address):
            raise ValueError("Invalid SpaceCash address.")
        conn = self.connect()
        try:
            wallet = conn.execute("SELECT * FROM wallets WHERE address = ?", (address,)).fetchone()
            if not wallet:
                raise ValueError("SpaceCash wallet not found.")
            balance_units = self._get_balance(conn, address)
            rows = conn.execute("""
                SELECT txid, created_at, kind, sender, recipient, amount_units, memo, related_source, related_id, payload_hash, block_height
                FROM transactions
                WHERE sender = ? OR recipient = ?
                ORDER BY COALESCE(block_height, -1) DESC, created_at DESC
                LIMIT ?
            """, (address, address, int(limit))).fetchall()
            txs = []
            for row in rows:
                txs.append({
                    "txid": row["txid"],
                    "created_at": row["created_at"],
                    "kind": row["kind"],
                    "sender": row["sender"],
                    "recipient": row["recipient"],
                    "amount": protocol.units_to_amount(row["amount_units"]),
                    "memo": row["memo"] or "",
                    "related_source": row["related_source"],
                    "related_id": row["related_id"],
                    "payload_hash": row["payload_hash"],
                    "block_height": row["block_height"],
                    "explorer_url": f"/tx/{row['txid']}",
                    "direction": "in" if row["recipient"] == address else "out",
                })
            summary = {
                "address": address,
                "label": wallet["label"],
                "created_at": wallet["created_at"],
                "auth_scheme": wallet["auth_scheme"] or ("claim-token" if wallet["claim_token"] else "watch-only"),
                "public_key_registered": bool(wallet["public_key_jwk"]),
                "balance_units": balance_units,
                "balance": protocol.units_to_amount(balance_units),
                "symbol": protocol.SYMBOL,
                "transactions": txs,
            }
            if include_claim and wallet["claim_token"]:
                summary["claim_token"] = wallet["claim_token"]
            return summary
        finally:
            conn.close()

    def create_wallet(self, label="Browser Wallet"):
        if protocol.IS_CLOSED_LOOP_MAINNET:
            raise ValueError("Mainnet requires a self-custodied signed wallet; register a public key instead.")
        self.ensure_schema()
        address = "SPACE-" + secrets.token_hex(16).upper()
        claim_token = secrets.token_urlsafe(32)
        conn = self.connect()
        try:
            self._ensure_wallet(conn, address, label or "Browser Wallet", claim_token)
            conn.commit()
            return self.wallet_summary(address, include_claim=True)
        finally:
            conn.close()

    def register_wallet(self, public_key_jwk, label="Signed Browser Wallet"):
        normalized = protocol.normalize_public_jwk(public_key_jwk)
        address = protocol.address_from_public_jwk(normalized)
        self.ensure_schema()
        conn = self.connect()
        try:
            self._ensure_wallet(conn, address, label or "Signed Browser Wallet", None, normalized, "ecdsa-p256")
            conn.commit()
            wallet = self.wallet_summary(address)
            wallet["public_key_jwk"] = normalized
            return wallet
        finally:
            conn.close()

    def _require_claim(self, address, claim_token):
        self.ensure_schema()
        address = (address or "").strip().upper()
        conn = self.connect()
        try:
            wallet = conn.execute("SELECT claim_token FROM wallets WHERE address = ?", (address,)).fetchone()
            expected = wallet["claim_token"] if wallet else None
            if not expected or not claim_token or not secrets.compare_digest(str(expected), str(claim_token)):
                raise ValueError("Wallet authorization failed. Create or load the wallet in this browser.")
        finally:
            conn.close()

    def _request_auth_payload(self, payload):
        for key in ("auth_payload", "signed_payload", "payload"):
            raw = payload.get(key) if isinstance(payload, dict) else None
            if isinstance(raw, dict):
                return raw
            if isinstance(raw, str) and raw.strip():
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    return parsed
        return None

    def _spend_source(self, payload):
        return self._request_auth_payload(payload) or payload

    def _compare_signed_fields(self, signed_payload, expected):
        for key, expected_value in expected.items():
            actual_value = signed_payload.get(key)
            if key == "amount":
                if protocol.amount_to_units(actual_value) != protocol.amount_to_units(expected_value):
                    raise ValueError("Signed SpaceCash amount does not match the request.")
                continue
            if key in ("sender", "recipient"):
                actual = str(actual_value or "").strip().upper()
                wanted = str(expected_value or "").strip().upper()
            elif key == "source":
                actual = str(actual_value or "").strip().lower()
                wanted = str(expected_value or "").strip().lower()
            elif key in ("product_id", "version"):
                actual = str(int(actual_value)) if str(actual_value or "").strip() else ""
                wanted = str(int(expected_value)) if str(expected_value or "").strip() else ""
            else:
                actual = str(actual_value or "").strip()
                wanted = str(expected_value or "").strip()
            if actual != wanted:
                raise ValueError(f"Signed SpaceCash {key} does not match the request.")

    def _verify_signature(self, address, signed_payload, signature_b64url):
        address = (address or "").strip().upper()
        if not protocol.valid_address(address):
            raise ValueError("Invalid SpaceCash address.")
        self.ensure_schema()
        conn = self.connect()
        try:
            wallet = conn.execute("SELECT public_key_jwk FROM wallets WHERE address = ?", (address,)).fetchone()
        finally:
            conn.close()
        if not wallet or not wallet["public_key_jwk"]:
            raise ValueError("This SpaceCash wallet has no registered signing key.")
        public_jwk = protocol.normalize_public_jwk(wallet["public_key_jwk"])
        if protocol.address_from_public_jwk(public_jwk) != address:
            raise ValueError("SpaceCash public key does not match the wallet address.")
        return self._verify_payload_with_jwk(public_jwk, signed_payload, signature_b64url)

    def _authorize_spend(self, address, request_payload, expected, require_signature=False):
        signed_payload = self._request_auth_payload(request_payload)
        signature = request_payload.get("signature") if isinstance(request_payload, dict) else None
        if signed_payload or signature:
            if not signed_payload or not signature:
                raise ValueError("Signed SpaceCash spend requires a payload and signature.")
            address = (address or "").strip().upper()
            sender = str(signed_payload.get("sender") or "").strip().upper()
            if sender != address:
                raise ValueError("Signed SpaceCash sender does not match the wallet.")
            self._compare_signed_fields(signed_payload, expected)
            nonce = str(signed_payload.get("nonce") or "").strip()
            if not re.fullmatch(r"[A-Za-z0-9_.:-]{8,128}", nonce):
                raise ValueError("Signed SpaceCash nonce is missing or invalid.")
            payload_digest = self._verify_signature(address, signed_payload, signature)
            return {
                "nonce": nonce,
                "payload_hash": payload_digest,
                "signature": str(signature)[:512],
                "payload": signed_payload,
            }
        if require_signature or protocol.IS_CLOSED_LOOP_MAINNET:
            raise ValueError("Mempool submissions require a signed SpaceCash payload.")
        self._require_claim(address, request_payload.get("claim_token") or request_payload.get("token"))
        return None

    def _record_tx_locked(self, conn, kind, sender, recipient, amount_units, memo="", related_source=None, related_id=None, auth_info=None, mine=True):
        amount_units = int(amount_units)
        if amount_units <= 0:
            raise ValueError("SpaceCash amount must be greater than zero.")
        if sender:
            self._ensure_wallet(conn, sender, "SpaceCash Wallet")
            if self._get_balance(conn, sender) < amount_units:
                raise ValueError("Insufficient SpaceCash balance.")
        if recipient:
            self._ensure_wallet(conn, recipient, "SpaceCash Wallet")

        now = protocol.utc_now()
        if auth_info and sender:
            try:
                conn.execute("""
                    INSERT INTO nonces(address, nonce, payload_hash, created_at)
                    VALUES(?,?,?,?)
                """, (sender, auth_info["nonce"], auth_info["payload_hash"], now))
            except sqlite3.IntegrityError as exc:
                raise ValueError("Signed SpaceCash nonce has already been used.") from exc
        if sender:
            conn.execute("UPDATE balances SET units = units - ?, updated_at = ? WHERE address = ?", (amount_units, now, sender))
        if recipient:
            conn.execute("UPDATE balances SET units = units + ?, updated_at = ? WHERE address = ?", (amount_units, now, recipient))
        new_txid = protocol.txid(kind, sender, recipient, amount_units)
        signed_payload = protocol.canonical_json(auth_info["payload"]) if auth_info and auth_info.get("payload") else None
        conn.execute("""
            INSERT INTO transactions(txid, created_at, kind, sender, recipient, amount_units, memo, related_source, related_id, payload_hash, signature, signed_payload)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            new_txid,
            now,
            kind,
            sender,
            recipient,
            amount_units,
            (memo or "")[:240],
            related_source,
            str(related_id) if related_id is not None else None,
            auth_info.get("payload_hash") if auth_info else None,
            auth_info.get("signature") if auth_info else None,
            signed_payload,
        ))
        if mine:
            block_height = self._mine_block(conn, new_txid, now)
            conn.execute("UPDATE transactions SET block_height = ? WHERE txid = ?", (block_height, new_txid))
        return new_txid

    def _record_tx(self, kind, sender, recipient, amount_units, memo="", related_source=None, related_id=None, auth_info=None):
        self.ensure_schema()
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            new_txid = self._record_tx_locked(conn, kind, sender, recipient, amount_units, memo, related_source, related_id, auth_info)
            conn.commit()
            return new_txid
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _auth_info_from_pending(self, row):
        try:
            signed_payload = json.loads(row["signed_payload"])
        except json.JSONDecodeError as exc:
            raise ValueError("Pending SpaceCash transaction has invalid signed payload JSON.") from exc
        return {
            "nonce": row["nonce"],
            "payload_hash": row["payload_hash"],
            "signature": row["signature"],
            "payload": signed_payload,
        }

    def _expected_for_pending(self, row):
        expected = {
            "chain_id": protocol.CHAIN_ID,
            "version": protocol.SIGNED_PAYLOAD_VERSION,
            "action": self._signed_action_for_kind(row["kind"]),
            "sender": row["sender"],
            "amount": protocol.units_to_amount(row["amount_units"]),
        }
        if row["kind"] == "transfer":
            expected["recipient"] = row["recipient"]
            expected["memo"] = row["memo"] or ""
        elif row["kind"] == "redeem":
            expected["memo"] = row["memo"] or ""
            expected["source"] = row["related_source"] or ""
            expected["id"] = row["related_id"] or ""
        elif row["kind"] == "product_redeem":
            expected["source"] = row["related_source"] or ""
            expected["product_id"] = row["related_id"] or ""
        else:
            raise ValueError("Unsupported pending SpaceCash transaction kind.")
        return expected

    def _verify_pending_row(self, conn, row):
        auth_info = self._auth_info_from_pending(row)
        signed_payload = auth_info["payload"]
        if protocol.payload_hash(signed_payload) != row["payload_hash"]:
            raise ValueError("Pending SpaceCash payload hash does not match.")
        self._compare_signed_fields(signed_payload, self._expected_for_pending(row))
        sender = str(signed_payload.get("sender") or "").strip().upper()
        if sender != row["sender"]:
            raise ValueError("Pending SpaceCash sender does not match signed payload.")
        wallet = conn.execute("SELECT public_key_jwk FROM wallets WHERE address = ?", (row["sender"],)).fetchone()
        if not wallet or not wallet["public_key_jwk"]:
            raise ValueError("Pending SpaceCash sender has no registered public key.")
        public_jwk = protocol.normalize_public_jwk(wallet["public_key_jwk"])
        if protocol.address_from_public_jwk(public_jwk) != row["sender"]:
            raise ValueError("Pending SpaceCash public key does not derive to sender address.")
        self._verify_payload_with_jwk(public_jwk, signed_payload, row["signature"])
        return auth_info

    def _queue_pending_tx(self, kind, sender, recipient, amount_units, memo="", related_source=None, related_id=None, auth_info=None, product=None):
        self.ensure_schema()
        if not auth_info or not auth_info.get("payload") or not auth_info.get("signature"):
            raise ValueError("Mempool submissions require a signed SpaceCash payload.")
        sender = str(sender or "").strip().upper()
        recipient = str(recipient or "").strip().upper() if recipient else None
        amount_units = int(amount_units)
        if not protocol.valid_address(sender):
            raise ValueError("Invalid SpaceCash sender address.")
        if recipient and not protocol.valid_address(recipient):
            raise ValueError("Invalid SpaceCash recipient address.")
        if amount_units <= 0:
            raise ValueError("SpaceCash amount must be greater than zero.")
        payload_hash = auth_info["payload_hash"]
        pending_id = self._pending_id(payload_hash)
        nonce = str(auth_info.get("nonce") or "").strip()
        product_snapshot = protocol.canonical_json({
            "source": str((product or {}).get("source") or related_source or "").strip().lower(),
            "id": str((product or {}).get("id") or (product or {}).get("product_id") or related_id or "0"),
            "name": str((product or {}).get("name") or "NorthStar Product")[:160],
        }) if product else None
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT * FROM mempool_transactions WHERE payload_hash = ?", (payload_hash,)).fetchone()
            if existing:
                conn.commit()
                return {
                    "accepted": False,
                    "duplicate": True,
                    "pending": self._pending_from_row(existing),
                }
            if conn.execute("SELECT 1 FROM nonces WHERE address = ? AND nonce = ?", (sender, nonce)).fetchone():
                raise ValueError("Signed SpaceCash nonce has already been mined.")
            if conn.execute("SELECT 1 FROM mempool_transactions WHERE sender = ? AND nonce = ?", (sender, nonce)).fetchone():
                raise ValueError("Signed SpaceCash nonce is already queued in the mempool.")
            self._ensure_wallet(conn, sender, "SpaceCash Wallet")
            if recipient:
                self._ensure_wallet(conn, recipient, "SpaceCash Wallet")
            available_units = self._get_balance(conn, sender) - self._pending_reserved_units(conn, sender)
            if available_units < amount_units:
                raise ValueError("Insufficient available SpaceCash balance after pending spends.")
            now = protocol.utc_now()
            conn.execute("""
                INSERT INTO mempool_transactions(
                    pending_id, created_at, updated_at, kind, sender, recipient,
                    amount_units, memo, related_source, related_id, payload_hash,
                    nonce, signature, signed_payload, product_snapshot, status, error, txid
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                pending_id,
                now,
                now,
                kind,
                sender,
                recipient,
                amount_units,
                (memo or "")[:240],
                related_source,
                str(related_id) if related_id is not None else None,
                payload_hash,
                nonce,
                auth_info["signature"],
                protocol.canonical_json(auth_info["payload"]),
                product_snapshot,
                "pending",
                None,
                None,
            ))
            row = conn.execute("SELECT * FROM mempool_transactions WHERE pending_id = ?", (pending_id,)).fetchone()
            conn.commit()
            return {
                "accepted": True,
                "duplicate": False,
                "pending": self._pending_from_row(row),
                "available_balance": protocol.units_to_amount(available_units - amount_units),
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def submit_transfer(self, payload):
        payload = payload or {}
        source = self._spend_source(payload)
        sender = (source.get("sender") or "").strip().upper()
        recipient = (source.get("recipient") or "").strip().upper()
        amount_text = str(source.get("amount") or "").strip()
        memo = str(source.get("memo") or "").strip()
        auth_info = self._authorize_spend(sender, payload, {
            "chain_id": protocol.CHAIN_ID,
            "version": protocol.SIGNED_PAYLOAD_VERSION,
            "action": "transfer",
            "sender": sender,
            "recipient": recipient,
            "amount": amount_text,
            "memo": memo,
        }, require_signature=True)
        return self._queue_pending_tx("transfer", sender, recipient, protocol.amount_to_units(amount_text), memo, auth_info=auth_info)

    def submit_redeem(self, payload):
        payload = payload or {}
        source = self._spend_source(payload)
        sender = (source.get("sender") or source.get("address") or "").strip().upper()
        amount_text = str(source.get("amount") or "").strip()
        memo = str(source.get("memo") or "").strip()
        related_source = str(source.get("source") or "").strip()
        related_id = str(source.get("id") or "").strip()
        if protocol.IS_CLOSED_LOOP_MAINNET and related_source.lower() not in {
            "nsp_digital", "nsp_game", "nsp_idr", "nsp_profile", "nsp_relic"
        }:
            raise ValueError(
                "Closed-loop mainnet redemption is limited to approved NorthStar digital-only sinks."
            )
        auth_info = self._authorize_spend(sender, payload, {
            "chain_id": protocol.CHAIN_ID,
            "version": protocol.SIGNED_PAYLOAD_VERSION,
            "action": "redeem",
            "sender": sender,
            "amount": amount_text,
            "memo": memo,
            "source": related_source,
            "id": related_id,
        }, require_signature=True)
        return self._queue_pending_tx("redeem", sender, protocol.TREASURY, protocol.amount_to_units(amount_text), memo, related_source, related_id, auth_info=auth_info)

    def submit_product_redeem(self, payload, product):
        if not protocol.PHYSICAL_REDEMPTION_ALLOWED:
            raise ValueError("Closed-loop mainnet forbids redemption for physical products, services, discounts, or money.")
        payload = payload or {}
        product = product or {}
        source_payload = self._spend_source(payload)
        product_source = str(product.get("source") or "").strip().lower()
        product_id = int(product.get("id") or 0)
        requested_source = str(source_payload.get("source") or "").strip().lower()
        requested_id = int(source_payload.get("product_id") or source_payload.get("id") or 0)
        if requested_source != product_source or requested_id != product_id:
            raise ValueError("Signed SpaceCash product does not match the validated catalog product.")
        if product.get("restricted"):
            raise ValueError("This product requires compliance review before checkout.")
        price = float(product.get("price") or 0)
        if price <= 0:
            raise ValueError("This product does not require SpaceCash payment.")
        cost_units = protocol.product_cost_units(price)
        cost_amount = protocol.units_to_amount(cost_units)
        sender = (source_payload.get("sender") or source_payload.get("address") or "").strip().upper()
        auth_info = self._authorize_spend(sender, payload, {
            "chain_id": protocol.CHAIN_ID,
            "version": protocol.SIGNED_PAYLOAD_VERSION,
            "action": "product_redeem",
            "sender": sender,
            "source": product_source,
            "product_id": product_id,
            "amount": cost_amount,
        }, require_signature=True)
        name = product.get("name") or "NorthStar Product"
        return self._queue_pending_tx(
            "product_redeem",
            sender,
            protocol.TREASURY,
            cost_units,
            f"Product redemption: {name}",
            product_source,
            product_id,
            auth_info=auth_info,
            product=product,
        )

    def mine_pending_transactions(self, limit=25):
        self.ensure_schema()
        limit = max(1, min(100, int(limit)))
        mined = []
        rejected = []
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("""
                SELECT *
                FROM mempool_transactions
                WHERE status = 'pending'
                ORDER BY created_at, pending_id
                LIMIT ?
            """, (limit,)).fetchall()
            batch_txids = []
            for row in rows:
                conn.execute("SAVEPOINT mine_pending_tx")
                try:
                    auth_info = self._verify_pending_row(conn, row)
                    if conn.execute("SELECT 1 FROM nonces WHERE address = ? AND nonce = ?", (row["sender"], row["nonce"])).fetchone():
                        raise ValueError("Signed SpaceCash nonce has already been mined.")
                    txid = self._record_tx_locked(
                        conn,
                        row["kind"],
                        row["sender"],
                        row["recipient"],
                        row["amount_units"],
                        row["memo"] or "",
                        row["related_source"],
                        row["related_id"],
                        auth_info=auth_info,
                        mine=False,
                    )
                    if row["kind"] == "product_redeem":
                        product = json.loads(row["product_snapshot"]) if row["product_snapshot"] else {
                            "source": row["related_source"],
                            "id": row["related_id"],
                            "name": "NorthStar Product",
                        }
                        self._create_product_order_locked(
                            conn,
                            txid,
                            row["sender"],
                            product,
                            row["amount_units"],
                            actor="spacecash_mempool",
                            notes="Created by SpaceCash mempool settlement.",
                        )
                    conn.execute("""
                        UPDATE mempool_transactions
                        SET status = 'mined', updated_at = ?, txid = ?, error = NULL
                        WHERE pending_id = ?
                    """, (protocol.utc_now(), txid, row["pending_id"]))
                    conn.execute("RELEASE SAVEPOINT mine_pending_tx")
                    batch_txids.append(txid)
                    mined.append({"pending_id": row["pending_id"], "txid": txid})
                except Exception as exc:
                    conn.execute("ROLLBACK TO SAVEPOINT mine_pending_tx")
                    conn.execute("RELEASE SAVEPOINT mine_pending_tx")
                    message = str(exc)[:500]
                    conn.execute("""
                        UPDATE mempool_transactions
                        SET status = 'rejected', updated_at = ?, error = ?
                        WHERE pending_id = ?
                    """, (protocol.utc_now(), message, row["pending_id"]))
                    rejected.append({"pending_id": row["pending_id"], "error": message})
            block = None
            if batch_txids:
                block_height = self._mine_block_batch(conn, batch_txids, producer_id=protocol.PRODUCER_ID)
                conn.execute(
                    f"UPDATE transactions SET block_height = ? WHERE txid IN ({','.join('?' for _ in batch_txids)})",
                    (block_height, *batch_txids),
                )
                block = self._block_from_row(conn.execute("SELECT * FROM blocks WHERE height = ?", (block_height,)).fetchone())
            conn.commit()
            return {
                "mined_count": len(mined),
                "rejected_count": len(rejected),
                "mined": mined,
                "rejected": rejected,
                "block": block,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


    def stripe_credit_purchase(self, session_id, address, amount, usd_amount=None):
        if not protocol.FIAT_PURCHASES_ALLOWED:
            raise ValueError("Closed-loop mainnet forbids buying SPACE with fiat or crypto.")
        self.ensure_schema()
        session_id = str(session_id or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{8,160}", session_id):
            raise ValueError("Stripe session id is required for SpaceCash credit purchases.")
        address = (address or "").strip().upper()
        if not protocol.valid_address(address):
            raise ValueError("Invalid SpaceCash address.")
        amount_units = protocol.amount_to_units(amount)
        amount_text = protocol.units_to_amount(amount_units)
        usd_text = str(usd_amount if usd_amount is not None else amount_text).strip() or amount_text
        conn = self.connect()
        try:
            existing = conn.execute("""
                SELECT txid, recipient, amount_units
                FROM transactions
                WHERE kind = 'stripe_credit_purchase'
                  AND related_source = 'stripe_spacecash'
                  AND related_id = ?
            """, (session_id,)).fetchone()
            if existing:
                if existing["recipient"] != address:
                    raise ValueError("Stripe session was already credited to another SpaceCash wallet.")
                wallet = self.wallet_summary(address)
                wallet["txid"] = existing["txid"]
                wallet["stripe_credit"] = {
                    "credited": False,
                    "idempotent": True,
                    "amount": protocol.units_to_amount(existing["amount_units"]),
                    "usd_amount": usd_text,
                    "related_source": "stripe_spacecash",
                    "related_id": session_id,
                }
                return wallet
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("""
                SELECT txid, recipient, amount_units
                FROM transactions
                WHERE kind = 'stripe_credit_purchase'
                  AND related_source = 'stripe_spacecash'
                  AND related_id = ?
            """, (session_id,)).fetchone()
            if existing:
                conn.rollback()
                if existing["recipient"] != address:
                    raise ValueError("Stripe session was already credited to another SpaceCash wallet.")
                wallet = self.wallet_summary(address)
                wallet["txid"] = existing["txid"]
                wallet["stripe_credit"] = {
                    "credited": False,
                    "idempotent": True,
                    "amount": protocol.units_to_amount(existing["amount_units"]),
                    "usd_amount": usd_text,
                    "related_source": "stripe_spacecash",
                    "related_id": session_id,
                }
                return wallet
            txid = self._record_tx_locked(
                conn,
                "stripe_credit_purchase",
                protocol.TREASURY,
                address,
                amount_units,
                f"Stripe closed-loop SpaceCash credit purchase: {amount_text} SPACE for USD {usd_text}",
                "stripe_spacecash",
                session_id,
            )
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()
        wallet = self.wallet_summary(address)
        wallet["txid"] = txid
        wallet["stripe_credit"] = {
            "credited": True,
            "idempotent": False,
            "amount": amount_text,
            "usd_amount": usd_text,
            "related_source": "stripe_spacecash",
            "related_id": session_id,
        }
        return wallet

    def faucet(self, address, amount=None):
        if not protocol.PUBLIC_FAUCET_ALLOWED:
            raise ValueError("The public faucet is disabled on closed-loop mainnet; SPACE is earned through NorthStar participation.")
        address = (address or "").strip().upper()
        amount_units = protocol.amount_to_units(amount or protocol.units_to_amount(protocol.FAUCET_UNITS))
        if amount_units > protocol.FAUCET_UNITS:
            raise ValueError(f"Faucet limit is {protocol.units_to_amount(protocol.FAUCET_UNITS)} {protocol.SYMBOL} per request.")
        txid = self._record_tx("faucet", protocol.TREASURY, address, amount_units, "SpaceCash devnet faucet")
        wallet = self.wallet_summary(address)
        wallet["txid"] = txid
        return wallet

    def grant_reward(self, address, amount, event_id, reason="NorthStar participation reward"):
        """Distribute an earned-only reward from treasury with idempotent event evidence."""
        if not protocol.IS_CLOSED_LOOP_MAINNET:
            raise ValueError("Earned reward grants are reserved for the closed-loop mainnet profile.")
        address = str(address or "").strip().upper()
        if not protocol.valid_address(address) or address == protocol.TREASURY:
            raise ValueError("A valid non-treasury SpaceCash reward address is required.")
        event_id = str(event_id or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{8,160}", event_id):
            raise ValueError("A stable NorthStar reward event id is required.")
        reason = str(reason or "").strip()[:160]
        if not reason:
            raise ValueError("A reward reason is required.")
        amount_units = protocol.amount_to_units(amount)
        if amount_units > protocol.MAX_REWARD_UNITS:
            raise ValueError(
                f"Reward exceeds the per-event limit of {protocol.units_to_amount(protocol.MAX_REWARD_UNITS)} {protocol.SYMBOL}."
            )
        self.ensure_schema()
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT txid, recipient, amount_units
                FROM transactions
                WHERE kind = 'reward' AND related_source = 'nsp_reward' AND related_id = ?
                """,
                (event_id,),
            ).fetchone()
            if existing:
                if existing["recipient"] != address or int(existing["amount_units"]) != amount_units:
                    raise ValueError("Reward event id is already bound to a different grant.")
                conn.commit()
                wallet = self.wallet_summary(address)
                wallet["txid"] = existing["txid"]
                wallet["reward"] = {"granted": False, "idempotent": True, "event_id": event_id}
                return wallet
            txid = self._record_tx_locked(
                conn,
                "reward",
                protocol.TREASURY,
                address,
                amount_units,
                reason,
                "nsp_reward",
                event_id,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        wallet = self.wallet_summary(address)
        wallet["txid"] = txid
        wallet["reward"] = {
            "granted": True,
            "idempotent": False,
            "event_id": event_id,
            "reason": reason,
            "amount": protocol.units_to_amount(amount_units),
        }
        return wallet

    def transfer(self, payload):
        payload = payload or {}
        source = self._spend_source(payload)
        sender = (source.get("sender") or "").strip().upper()
        recipient = (source.get("recipient") or "").strip().upper()
        amount_text = str(source.get("amount") or "").strip()
        memo = str(source.get("memo") or "").strip()
        auth_info = self._authorize_spend(sender, payload, {
            "chain_id": protocol.CHAIN_ID,
            "version": protocol.SIGNED_PAYLOAD_VERSION,
            "action": "transfer",
            "sender": sender,
            "recipient": recipient,
            "amount": amount_text,
            "memo": memo,
        })
        amount_units = protocol.amount_to_units(amount_text)
        txid = self._record_tx("transfer", sender, recipient, amount_units, memo or "SpaceCash transfer", auth_info=auth_info)
        wallet = self.wallet_summary(sender)
        wallet["txid"] = txid
        return wallet

    def redeem(self, payload):
        payload = payload or {}
        source = self._spend_source(payload)
        sender = (source.get("sender") or source.get("address") or "").strip().upper()
        amount_text = str(source.get("amount") or "").strip()
        memo = str(source.get("memo") or "").strip()
        related_source = str(source.get("source") or "").strip()
        related_id = str(source.get("id") or "").strip()
        if protocol.IS_CLOSED_LOOP_MAINNET and related_source.lower() not in {
            "nsp_digital", "nsp_game", "nsp_idr", "nsp_profile", "nsp_relic"
        }:
            raise ValueError(
                "Closed-loop mainnet redemption is limited to approved NorthStar digital-only sinks."
            )
        auth_info = self._authorize_spend(sender, payload, {
            "chain_id": protocol.CHAIN_ID,
            "version": protocol.SIGNED_PAYLOAD_VERSION,
            "action": "redeem",
            "sender": sender,
            "amount": amount_text,
            "memo": memo,
            "source": related_source,
            "id": related_id,
        })
        amount_units = protocol.amount_to_units(amount_text)
        txid = self._record_tx("redeem", sender, protocol.TREASURY, amount_units, memo or "SpaceCash redemption", related_source, related_id, auth_info=auth_info)
        wallet = self.wallet_summary(sender)
        wallet["txid"] = txid
        return wallet

    def product_redeem(self, payload, product):
        if not protocol.PHYSICAL_REDEMPTION_ALLOWED:
            raise ValueError("Closed-loop mainnet forbids redemption for physical products, services, discounts, or money.")
        payload = payload or {}
        product = product or {}
        source_payload = self._spend_source(payload)
        product_source = str(product.get("source") or "").strip().lower()
        product_id = int(product.get("id") or 0)
        requested_source = str(source_payload.get("source") or "").strip().lower()
        requested_id = int(source_payload.get("product_id") or source_payload.get("id") or 0)
        if requested_source != product_source or requested_id != product_id:
            raise ValueError("Signed SpaceCash product does not match the validated catalog product.")
        if product.get("restricted"):
            raise ValueError("This product requires compliance review before checkout.")
        price = float(product.get("price") or 0)
        if price <= 0:
            raise ValueError("This product does not require SpaceCash payment.")
        cost_units = protocol.product_cost_units(price)
        cost_amount = protocol.units_to_amount(cost_units)
        sender = (source_payload.get("sender") or source_payload.get("address") or "").strip().upper()
        auth_info = self._authorize_spend(sender, payload, {
            "chain_id": protocol.CHAIN_ID,
            "version": protocol.SIGNED_PAYLOAD_VERSION,
            "action": "product_redeem",
            "sender": sender,
            "source": product_source,
            "product_id": product_id,
            "amount": cost_amount,
        })
        name = product.get("name") or "NorthStar Product"
        txid = self._record_tx("product_redeem", sender, protocol.TREASURY, cost_units, f"Product redemption: {name}", product_source, product_id, auth_info=auth_info)
        receipt = self._create_product_order(txid, sender, product, cost_units)
        wallet = self.wallet_summary(sender)
        wallet["txid"] = txid
        wallet["product"] = {
            "source": product_source,
            "id": product_id,
            "name": name,
            "amount": cost_amount,
        }
        wallet["receipt"] = receipt
        return wallet

    def _public_key_from_jwk(self, jwk):
        if ec is None:
            raise ValueError("Signed SpaceCash wallets require the server cryptography package.")
        normalized = protocol.normalize_public_jwk(jwk)
        x_num = int.from_bytes(protocol.b64url_decode(normalized["x"]), "big")
        y_num = int.from_bytes(protocol.b64url_decode(normalized["y"]), "big")
        try:
            return ec.EllipticCurvePublicNumbers(x_num, y_num, ec.SECP256R1()).public_key()
        except ValueError as exc:
            raise ValueError("Invalid SpaceCash public key.") from exc

    def _verify_payload_with_jwk(self, public_jwk, signed_payload, signature_b64url):
        if ec is None or crypto_utils is None or hashes is None or InvalidSignature is None:
            raise ValueError("Signed SpaceCash wallets require the server cryptography package.")
        public_key = self._public_key_from_jwk(public_jwk)
        signature = protocol.b64url_decode(signature_b64url)
        if len(signature) == 64:
            r = int.from_bytes(signature[:32], "big")
            s = int.from_bytes(signature[32:], "big")
            signature = crypto_utils.encode_dss_signature(r, s)
        canonical = protocol.canonical_json(signed_payload).encode("utf-8")
        try:
            public_key.verify(signature, canonical, ec.ECDSA(hashes.SHA256()))
        except InvalidSignature as exc:
            raise ValueError("SpaceCash wallet signature failed.") from exc
        except ValueError as exc:
            raise ValueError("Invalid SpaceCash signature.") from exc
        return protocol.payload_hash(signed_payload)

    def _signed_action_for_kind(self, kind):
        return {
            "transfer": "transfer",
            "redeem": "redeem",
            "product_redeem": "product_redeem",
        }.get(kind)

    def _audit_signed_tx(self, conn, tx, errors, warnings):
        signature = tx["signature"]
        if not signature:
            if tx["kind"] in ("transfer", "redeem", "product_redeem"):
                warnings.append(f"{tx['txid']} is a legacy unsigned spend accepted by claim-token compatibility.")
            return False
        if not tx["signed_payload"]:
            warnings.append(f"{tx['txid']} has a signature but no stored signed payload; it predates payload retention.")
            return False
        try:
            signed_payload = json.loads(tx["signed_payload"])
            payload_digest = protocol.payload_hash(signed_payload)
            if payload_digest != tx["payload_hash"]:
                errors.append(f"{tx['txid']} signed payload hash does not match stored payload_hash.")
            sender = str(signed_payload.get("sender") or "").strip().upper()
            if sender != (tx["sender"] or ""):
                errors.append(f"{tx['txid']} signed sender does not match transaction sender.")
            expected_action = self._signed_action_for_kind(tx["kind"])
            if expected_action and signed_payload.get("action") != expected_action:
                errors.append(f"{tx['txid']} signed action does not match transaction kind.")
            signed_chain_id = signed_payload.get("chain_id")
            if signed_chain_id is None:
                warnings.append(f"{tx['txid']} signed payload predates chain_id binding.")
            elif signed_chain_id != protocol.CHAIN_ID:
                errors.append(f"{tx['txid']} signed chain_id does not match this devnet.")
            signed_version = signed_payload.get("version")
            if signed_version is None:
                warnings.append(f"{tx['txid']} signed payload predates version binding.")
            elif int(signed_version) != protocol.SIGNED_PAYLOAD_VERSION:
                errors.append(f"{tx['txid']} signed payload version is not supported.")
            if protocol.amount_to_units(signed_payload.get("amount")) != int(tx["amount_units"]):
                errors.append(f"{tx['txid']} signed amount does not match transaction amount.")
            if tx["kind"] == "transfer":
                signed_recipient = str(signed_payload.get("recipient") or "").strip().upper()
                if signed_recipient != (tx["recipient"] or ""):
                    errors.append(f"{tx['txid']} signed recipient does not match transaction recipient.")
            if tx["kind"] == "product_redeem":
                if str(signed_payload.get("source") or "").strip().lower() != str(tx["related_source"] or "").strip().lower():
                    errors.append(f"{tx['txid']} signed source does not match transaction source.")
                if str(int(signed_payload.get("product_id"))) != str(tx["related_id"] or ""):
                    errors.append(f"{tx['txid']} signed product id does not match transaction product id.")
            wallet = conn.execute("SELECT public_key_jwk FROM wallets WHERE address = ?", (tx["sender"],)).fetchone()
            if not wallet or not wallet["public_key_jwk"]:
                errors.append(f"{tx['txid']} cannot verify signature because sender has no registered public key.")
                return True
            public_jwk = protocol.normalize_public_jwk(wallet["public_key_jwk"])
            if protocol.address_from_public_jwk(public_jwk) != tx["sender"]:
                errors.append(f"{tx['txid']} sender public key does not derive to the sender address.")
                return True
            self._verify_payload_with_jwk(public_jwk, signed_payload, signature)
            return True
        except Exception as exc:
            errors.append(f"{tx['txid']} signature audit failed: {exc}")
            return True

    def _audit_checkpoint_vote(self, conn, vote, validators, errors, warnings):
        try:
            if vote["status"] != "valid":
                errors.append(f"{vote['vote_id']} checkpoint vote has unsupported status {vote['status']}.")
            signed_payload = json.loads(vote["signed_payload"])
            payload_hash = protocol.payload_hash(signed_payload)
            if payload_hash != vote["payload_hash"]:
                errors.append(f"{vote['vote_id']} checkpoint vote payload hash does not match.")
            validator = self._normalize_validator_address(signed_payload.get("validator"))
            if validator != vote["validator_address"]:
                errors.append(f"{vote['vote_id']} checkpoint vote validator does not match.")
            if signed_payload.get("action") != "checkpoint_vote":
                errors.append(f"{vote['vote_id']} checkpoint vote action is invalid.")
            if signed_payload.get("chain_id") != protocol.CHAIN_ID:
                errors.append(f"{vote['vote_id']} checkpoint vote chain_id does not match this devnet.")
            if int(signed_payload.get("version") or 0) != protocol.SIGNED_PAYLOAD_VERSION:
                errors.append(f"{vote['vote_id']} checkpoint vote payload version is not supported.")
            if int(signed_payload.get("height")) != int(vote["height"]):
                errors.append(f"{vote['vote_id']} checkpoint vote height does not match.")
            if str(signed_payload.get("block_hash") or "").strip().upper() != vote["block_hash"]:
                errors.append(f"{vote['vote_id']} checkpoint vote block hash does not match.")
            if str(signed_payload.get("chain_digest") or "").strip().upper() != vote["chain_digest"]:
                errors.append(f"{vote['vote_id']} checkpoint vote chain digest does not match.")
            block = conn.execute("SELECT block_hash FROM blocks WHERE height = ?", (vote["height"],)).fetchone()
            if not block or block["block_hash"] != vote["block_hash"]:
                errors.append(f"{vote['vote_id']} checkpoint vote references an unknown local block.")
            if validator not in validators:
                warnings.append(f"{vote['vote_id']} checkpoint vote is signed by a wallet outside the current validator set.")
            wallet = conn.execute("SELECT public_key_jwk FROM wallets WHERE address = ?", (validator,)).fetchone()
            if not wallet or not wallet["public_key_jwk"]:
                errors.append(f"{vote['vote_id']} checkpoint vote signer has no registered public key.")
                return
            public_jwk = protocol.normalize_public_jwk(wallet["public_key_jwk"])
            if protocol.address_from_public_jwk(public_jwk) != validator:
                errors.append(f"{vote['vote_id']} checkpoint vote public key does not derive to signer.")
                return
            self._verify_payload_with_jwk(public_jwk, signed_payload, vote["signature"])
        except Exception as exc:
            errors.append(f"{vote['vote_id']} checkpoint vote audit failed: {exc}")

    def audit(self):
        self.ensure_schema()
        conn = self.connect()
        errors = []
        warnings = []
        try:
            blocks = conn.execute("""
                SELECT *
                FROM blocks
                ORDER BY height
            """).fetchall()
            txs = conn.execute("""
                SELECT txid, created_at, kind, sender, recipient, amount_units, memo, related_source, related_id, payload_hash, signature, signed_payload, block_height
                FROM transactions
                ORDER BY COALESCE(block_height, -1), created_at, txid
            """).fetchall()
            tx_by_id = {tx["txid"]: tx for tx in txs}
            tx_by_height = {}
            for tx in txs:
                if tx["block_height"] is not None:
                    tx_by_height.setdefault(int(tx["block_height"]), []).append(tx)

            expected_prev = "0" * 64
            for expected_height, block in enumerate(blocks):
                height = int(block["height"])
                if height != expected_height:
                    errors.append(f"Expected block height {expected_height}, found {height}.")
                if block["previous_hash"] != expected_prev:
                    errors.append(f"Block {height} previous hash does not match the prior block.")
                block_txs = tx_by_height.get(height, [])
                if len(block_txs) != int(block["tx_count"]):
                    errors.append(f"Block {height} tx_count does not match attached transactions.")
                block_version = int(block["block_version"] or 1)
                if block_version >= 2:
                    try:
                        expected_txids = json.loads(block["txids_json"] or "[]")
                    except json.JSONDecodeError:
                        expected_txids = []
                        errors.append(f"Block {height} has invalid txids_json.")
                    if len(expected_txids) != int(block["tx_count"]):
                        errors.append(f"Block {height} txids_json length does not match tx_count.")
                    for txid in expected_txids:
                        tx = tx_by_id.get(txid)
                        if not tx:
                            errors.append(f"Block {height} references missing transaction {txid}.")
                        elif tx["block_height"] != height:
                            errors.append(f"Block {height} transaction height mismatch for {txid}.")
                    actual_txids = {tx["txid"] for tx in block_txs}
                    if set(expected_txids) != actual_txids:
                        errors.append(f"Block {height} txids_json does not match attached transactions.")
                    expected_merkle = protocol.merkle_root(expected_txids)
                    if block["merkle_root"] != expected_merkle:
                        errors.append(f"Block {height} merkle root does not match its ordered transactions.")
                    producer_id = block["producer_id"] or protocol.PRODUCER_ID
                    expected_payload = self._block_payload(expected_txids, producer_id, block_version)
                    expected_hash = protocol.block_hash(height, block["created_at"], block["previous_hash"], block["merkle_root"], expected_payload, block["tx_count"])
                    if block["block_hash"] != expected_hash:
                        errors.append(f"Block {height} hash does not match versioned block contents.")
                    expected_seal = self._producer_seal(block["block_hash"], block["txids_json"], producer_id)
                    if block["producer_seal"] != expected_seal:
                        errors.append(f"Block {height} producer seal does not match.")
                else:
                    expected_merkle = protocol.hash_text(block["txid"] or "")
                    if block["merkle_root"] != expected_merkle:
                        errors.append(f"Block {height} merkle root does not match its txid.")
                    expected_hash = protocol.block_hash(height, block["created_at"], block["previous_hash"], block["merkle_root"], block["txid"], block["tx_count"])
                    if block["block_hash"] != expected_hash:
                        errors.append(f"Block {height} hash does not match block contents.")
                    if block["txid"] not in tx_by_id:
                        errors.append(f"Block {height} references missing transaction {block['txid']}.")
                    elif tx_by_id[block["txid"]]["block_height"] != height:
                        errors.append(f"Block {height} transaction height mismatch.")
                expected_prev = block["block_hash"]

            for tx in txs:
                if tx["block_height"] is None:
                    errors.append(f"{tx['txid']} has no block assignment.")

            ledger_balances = {}
            for tx in txs:
                units = int(tx["amount_units"])
                if units <= 0:
                    errors.append(f"{tx['txid']} has a non-positive amount.")
                if tx["sender"]:
                    ledger_balances[tx["sender"]] = ledger_balances.get(tx["sender"], 0) - units
                if tx["recipient"]:
                    ledger_balances[tx["recipient"]] = ledger_balances.get(tx["recipient"], 0) + units

            stored_balances = {
                row["address"]: int(row["units"])
                for row in conn.execute("SELECT address, units FROM balances").fetchall()
            }
            for address in sorted(set(ledger_balances) | set(stored_balances)):
                if ledger_balances.get(address, 0) != stored_balances.get(address, 0):
                    errors.append(f"{address} balance table does not match transaction history.")
                if stored_balances.get(address, 0) < 0:
                    errors.append(f"{address} has a negative balance.")

            total_units = sum(stored_balances.values())
            if total_units != protocol.GENESIS_UNITS:
                errors.append("Total stored SpaceCash supply does not match genesis supply.")

            signed_spends = 0
            spend_count = 0
            for tx in txs:
                if tx["kind"] in ("transfer", "redeem", "product_redeem"):
                    spend_count += 1
                    if self._audit_signed_tx(conn, tx, errors, warnings):
                        signed_spends += 1

            order_rows = conn.execute("SELECT * FROM product_orders").fetchall()
            orders_by_txid = {row["txid"]: row for row in order_rows}
            for tx in txs:
                if tx["kind"] == "product_redeem" and tx["txid"] not in orders_by_txid:
                    warnings.append(f"{tx['txid']} product redemption has no fulfillment receipt record.")
            for row in order_rows:
                tx = tx_by_id.get(row["txid"])
                if not tx:
                    errors.append(f"{row['receipt_id']} references missing transaction {row['txid']}.")
                    continue
                if tx["kind"] != "product_redeem":
                    errors.append(f"{row['receipt_id']} references a non-product transaction.")
                if int(row["amount_units"]) != int(tx["amount_units"]):
                    errors.append(f"{row['receipt_id']} amount does not match its SpaceCash transaction.")
                if row["wallet_address"] != tx["sender"]:
                    errors.append(f"{row['receipt_id']} wallet does not match transaction sender.")

            mempool_rows = conn.execute("SELECT * FROM mempool_transactions ORDER BY created_at, pending_id").fetchall()
            valid_mempool_statuses = {"pending", "mined", "rejected"}
            pending_reserved = {}
            for row in mempool_rows:
                if row["status"] not in valid_mempool_statuses:
                    errors.append(f"{row['pending_id']} has unsupported mempool status {row['status']}.")
                if row["status"] == "mined":
                    if not row["txid"] or row["txid"] not in tx_by_id:
                        errors.append(f"{row['pending_id']} is marked mined but does not reference a ledger transaction.")
                if row["status"] != "pending":
                    continue
                try:
                    self._verify_pending_row(conn, row)
                except Exception as exc:
                    errors.append(f"{row['pending_id']} pending signature audit failed: {exc}")
                if conn.execute("SELECT 1 FROM nonces WHERE address = ? AND nonce = ?", (row["sender"], row["nonce"])).fetchone():
                    errors.append(f"{row['pending_id']} pending nonce is already mined.")
                sender = row["sender"]
                amount_units = int(row["amount_units"])
                available_units = stored_balances.get(sender, 0) - pending_reserved.get(sender, 0)
                if available_units < amount_units:
                    errors.append(f"{row['pending_id']} exceeds available balance after earlier pending spends.")
                pending_reserved[sender] = pending_reserved.get(sender, 0) + amount_units

            validator_policy = self._validator_policy_locked(conn)
            vote_rows = conn.execute("SELECT * FROM checkpoint_votes ORDER BY created_at, vote_id").fetchall()
            for row in vote_rows:
                self._audit_checkpoint_vote(conn, row, validator_policy["validators"], errors, warnings)

            latest_block = blocks[-1] if blocks else None
            return {
                "chain_id": protocol.CHAIN_ID,
                "valid": not errors,
                "errors": errors[:100],
                "warnings": warnings[:100],
                "checks": {
                    "block_hash_chain": not any("Block " in e or "height" in e for e in errors),
                    "supply_invariant": total_units == protocol.GENESIS_UNITS,
                    "balances_match_transactions": not any("balance table" in e for e in errors),
                    "no_negative_balances": not any("negative balance" in e for e in errors),
                    "mempool_valid": not any("pending" in e or "mempool" in e for e in errors),
                    "checkpoint_votes_valid": not any("checkpoint vote" in e for e in errors),
                },
                "counts": {
                    "wallets": conn.execute("SELECT COUNT(*) AS n FROM wallets").fetchone()["n"],
                    "transactions": len(txs),
                    "blocks": len(blocks),
                    "versioned_blocks": len([block for block in blocks if int(block["block_version"] or 1) >= 2]),
                    "batched_blocks": len([block for block in blocks if int(block["tx_count"]) > 1]),
                    "product_orders": len(order_rows),
                    "mempool_pending": len([row for row in mempool_rows if row["status"] == "pending"]),
                    "mempool_total": len(mempool_rows),
                    "validators": len(validator_policy["validators"]),
                    "checkpoint_votes": len(vote_rows),
                    "signed_spends": signed_spends,
                    "spends": spend_count,
                    "legacy_unsigned_spends": max(0, spend_count - signed_spends),
                },
                "supply": {
                    "genesis_units": protocol.GENESIS_UNITS,
                    "stored_units": total_units,
                    "genesis": protocol.units_to_amount(protocol.GENESIS_UNITS),
                    "stored": protocol.units_to_amount(total_units),
                },
                "tip": {
                    "height": latest_block["height"] if latest_block else None,
                    "hash": latest_block["block_hash"] if latest_block else None,
                },
            }
        finally:
            conn.close()

    def mainnet_readiness(self):
        audit = self.audit()
        policy = self.consensus_policy()
        validator_policy = self.validator_policy()
        counts = audit.get("counts") or {}
        warnings = audit.get("warnings") or []
        checkpoint = validator_policy.get("checkpoint") or {}
        bootstrap_peers = policy.get("bootstrap_peers") or []
        allowed_producers = policy.get("allowed_producers") or []

        def automated_gate(gate_id, passed, detail, evidence=None):
            return {
                "id": gate_id,
                "status": "pass" if passed else "fail",
                "severity": "blocker",
                "detail": detail,
                "evidence": evidence or {},
            }

        automated_gates = [
            automated_gate(
                "audit_valid",
                bool(audit.get("valid")),
                "Ledger audit must have no integrity errors.",
                {"error_count": len(audit.get("errors") or [])},
            ),
            automated_gate(
                "no_audit_warnings",
                not warnings,
                "Ledger audit must have no compatibility or fulfillment warnings.",
                {"warning_count": len(warnings), "warnings": warnings[:10]},
            ),
            automated_gate(
                "no_legacy_unsigned_spends",
                int(counts.get("legacy_unsigned_spends") or 0) == 0,
                "Mainnet candidate must not depend on legacy unsigned spend compatibility.",
                {"legacy_unsigned_spends": counts.get("legacy_unsigned_spends") or 0},
            ),
            automated_gate(
                "no_pending_mempool",
                int(counts.get("mempool_pending") or 0) == 0,
                "Candidate ledger should not carry pending mempool transactions.",
                {"mempool_pending": counts.get("mempool_pending") or 0},
            ),
            automated_gate(
                "versioned_blocks_present",
                int(counts.get("versioned_blocks") or 0) > 0,
                "Candidate chain should contain current versioned blocks.",
                {"versioned_blocks": counts.get("versioned_blocks") or 0},
            ),
            automated_gate(
                "producer_allowlist_configured",
                protocol.PRODUCER_ID in allowed_producers,
                "Local producer must be present in the producer allowlist.",
                {"allowed_producers": allowed_producers},
            ),
            automated_gate(
                "validators_configured",
                len(validator_policy.get("validators") or []) > 0,
                "At least one registered validator wallet must be configured.",
                {"validators": len(validator_policy.get("validators") or [])},
            ),
            automated_gate(
                "checkpoint_quorum_reached",
                bool(checkpoint.get("quorum_reached")),
                "Current chain tip must have signed validator checkpoint quorum.",
                {
                    "eligible_votes": checkpoint.get("eligible_votes") or 0,
                    "quorum": checkpoint.get("quorum") or 0,
                },
            ),
            automated_gate(
                "bootstrap_peers_configured",
                len(bootstrap_peers) > 0,
                "Candidate network must define monitored bootstrap peers.",
                {"bootstrap_peers": len(bootstrap_peers)},
            ),
        ]
        manual_gates = [
            {
                "id": "public_testnet_complete",
                "status": "manual_blocker",
                "severity": "blocker",
                "detail": "Run a public testnet with reproducible node setup and monitored bootstrap peers.",
            },
            {
                "id": "external_security_review_complete",
                "status": "manual_blocker",
                "severity": "blocker",
                "detail": "Complete an outside security review of wallet and sync behavior.",
            },
            {
                "id": "legal_compliance_review_complete",
                "status": "manual_blocker",
                "severity": "blocker",
                "detail": "Complete legal, tax, and product-payment review before real-money use.",
            },
            {
                "id": "wallet_recovery_custody_policy_complete",
                "status": "manual_blocker",
                "severity": "blocker",
                "detail": "Define recovery phrase, address versioning, backup rotation, hardware wallet, and custody policy.",
            },
            {
                "id": "production_deployment_runbook_complete",
                "status": "manual_blocker",
                "severity": "blocker",
                "detail": "Produce launch, monitoring, archive, and rollback procedures.",
            },
        ]
        if protocol.IS_CLOSED_LOOP_MAINNET:
            genesis_tx = self.transaction(protocol.deterministic_genesis_txid())
            commitments = protocol.network_policy()["commitments"]
            closed_loop_enforced = all(
                commitments[key] is False
                for key in (
                    "fiat_purchases_allowed",
                    "physical_redemption_allowed",
                    "cash_redemption_allowed",
                    "custodial_wallets_allowed",
                    "exchange_integration_allowed",
                    "investment_marketing_allowed",
                    "public_faucet_allowed",
                )
            )
            automated_gates.extend([
                automated_gate(
                    "closed_loop_mainnet_profile",
                    protocol.CHAIN_ID == "spacecash-mainnet-1",
                    "The process must run the explicit closed-loop mainnet network profile.",
                    {"network_profile": protocol.NETWORK_PROFILE, "chain_id": protocol.CHAIN_ID},
                ),
                automated_gate(
                    "deterministic_mainnet_genesis",
                    bool(genesis_tx and genesis_tx.get("created_at") == protocol.GENESIS_TIMESTAMP),
                    "Mainnet must start from the fixed published genesis transaction and timestamp.",
                    {
                        "txid": protocol.deterministic_genesis_txid(),
                        "timestamp": protocol.GENESIS_TIMESTAMP,
                    },
                ),
                automated_gate(
                    "closed_loop_boundaries_enforced",
                    closed_loop_enforced,
                    "Fiat purchase, real-world redemption, custody, exchange, investment marketing, and public faucet paths must be disabled.",
                    commitments,
                ),
                automated_gate(
                    "operator_mainnet_acknowledged",
                    protocol.MAINNET_ACKNOWLEDGED,
                    "The operator must explicitly acknowledge the non-monetary mainnet charter.",
                    {"acknowledged": protocol.MAINNET_ACKNOWLEDGED},
                ),
            ])
            manual_gates = [
                {
                    "id": "public_testnet_complete",
                    "status": "advisory_pending",
                    "severity": "advisory",
                    "detail": "Independent public-node testing remains strongly recommended and is required before any commerce re-entry.",
                },
                {
                    "id": "external_security_review_complete",
                    "status": "advisory_pending",
                    "severity": "advisory",
                    "detail": "External review remains recommended and becomes a blocker before any monetary, custody, or real-world redemption use.",
                },
                {
                    "id": "legal_compliance_review_complete",
                    "status": "pass",
                    "severity": "blocker",
                    "detail": "Dormant only while executable closed-loop commitments remain enforced; any commerce re-entry trigger restores this gate.",
                },
                {
                    "id": "wallet_recovery_custody_policy_complete",
                    "status": "pass",
                    "severity": "blocker",
                    "detail": "Server custody is prohibited; only self-managed signed wallets are accepted on mainnet.",
                },
                {
                    "id": "production_deployment_runbook_complete",
                    "status": "pass" if protocol.DEPLOYMENT_ACKNOWLEDGED else "manual_blocker",
                    "severity": "blocker",
                    "detail": "A monitored deployment, archived backup, recovery test, and rollback acknowledgement are required.",
                },
            ]
        automated_blockers = [gate["id"] for gate in automated_gates if gate["status"] != "pass"]
        manual_blockers = [
            gate["id"]
            for gate in manual_gates
            if gate.get("severity") == "blocker" and gate["status"] != "pass"
        ]
        automated_release_candidate = not automated_blockers
        mainnet_ready = protocol.IS_CLOSED_LOOP_MAINNET and automated_release_candidate and not manual_blockers
        next_actions = [
            gate["detail"]
            for gate in automated_gates + manual_gates
            if gate["status"] != "pass"
        ]
        return {
            "chain_id": protocol.CHAIN_ID,
            "mode": "mainnet-readiness-v1",
            "network_profile": protocol.NETWORK_PROFILE,
            "network_policy": protocol.network_policy(),
            "mainnet_ready": mainnet_ready,
            "automated_release_candidate": automated_release_candidate,
            "automated_blockers": automated_blockers,
            "manual_blockers": manual_blockers,
            "audit": {
                "valid": bool(audit.get("valid")),
                "warning_count": len(warnings),
                "counts": counts,
                "tip": audit.get("tip"),
            },
            "gates": {
                "automated": automated_gates,
                "manual": manual_gates,
            },
            "next_actions": next_actions,
        }
