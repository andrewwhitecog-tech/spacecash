"""spacecash_provenance — chain-anchored, vacuum-seeded certificates for artifacts & relics.

Implements CYPHERPUNK_POSTURE.md uses 1 & 2: every certificate binds
  (artifact identity + canon-art hash + holder label)
to
  (devnet chain tip anchor + ANU vacuum-fluctuation entropy + UTC time)
and lands as canonical JSON in docs/spacecash/provenance_registry/ with an
index. Certificates are honors/notarization only — never financial instruments
(no sale, no redemption, soulbound posture; see the charter).

Usage:
  python tools/spacecash_provenance.py mint --artifact "Prism Drift" \
      --kind relic --relic-class lore --edition "001" \
      --art-sha256 <hash-or-file> --holder "andre" [--nfc-uid <uid>] \
      [--physical-twin "vorath_tokens/prism_drift.stl"]
  python tools/spacecash_provenance.py list
  python tools/spacecash_provenance.py verify <certificate.json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from spacecash_core.quantum_entropy import generate as quantum_generate  # noqa: E402

DB_PATH = Path(os.environ.get("NS_PRIME_SPACECASH_DB", str(ROOT / "spacecash_devnet.sqlite3")))
REGISTRY = ROOT / "docs" / "spacecash" / "provenance_registry"
INDEX = REGISTRY / "INDEX.json"
CHARTER = "docs/spacecash/CYPHERPUNK_POSTURE.md"


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def chain_tip() -> dict:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        row = conn.execute(
            "SELECT height, block_hash FROM blocks ORDER BY height DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    if not row:
        raise SystemExit("no blocks in devnet ledger; start the chain first")
    return {"height": row[0], "block_hash": row[1], "db": DB_PATH.name}


def resolve_art_hash(value: str) -> tuple[str, str]:
    p = Path(value)
    if p.exists():
        return hashlib.sha256(p.read_bytes()).hexdigest(), p.name
    v = value.lower().strip()
    if len(v) == 64 and all(c in "0123456789abcdef" for c in v):
        return v, "(hash supplied)"
    raise SystemExit(f"--art-sha256 must be a file path or 64-hex sha256, got: {value}")


def load_index() -> list:
    if INDEX.exists():
        return json.loads(INDEX.read_text(encoding="utf-8"))
    return []


def mint(a) -> int:
    REGISTRY.mkdir(parents=True, exist_ok=True)
    art_hash, art_name = resolve_art_hash(a.art_sha256)
    tip = chain_tip()
    index = load_index()
    serial = len(index) + 1
    context = f"spacecash-provenance-{serial:05d}-{a.artifact}"
    entropy, prov = quantum_generate(32, context=context)

    cert = {
        "schema": "spacecash-provenance-v1",
        "serial": serial,
        "kind": a.kind,                      # artifact | relic
        "artifact": a.artifact,
        "edition": a.edition,
        "relic_class": a.relic_class,        # patron|founder|lore|agent|None
        "holder": a.holder,
        "soulbound": True,
        "non_financial_notice": (
            "This certificate is a notarization/honor. It is not money, store "
            "credit, an investment, or a claim on goods or services. See " + CHARTER),
        "art_sha256": art_hash,
        "art_source_name": art_name,
        "nfc_uid": a.nfc_uid,
        "physical_twin": a.physical_twin,
        "chain_anchor": tip,                 # proves cert made at/after this block
        "quantum_seed_hex": entropy.hex(),
        "quantum_provenance": prov.__dict__,
        "minted_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    cert["certificate_sha256"] = hashlib.sha256(canonical(cert)).hexdigest()

    slug = "".join(c if c.isalnum() else "_" for c in a.artifact.lower())
    path = REGISTRY / f"{serial:05d}_{slug}.json"
    path.write_text(json.dumps(cert, indent=2, ensure_ascii=False), encoding="utf-8")

    index.append({"serial": serial, "artifact": a.artifact, "kind": a.kind,
                  "relic_class": a.relic_class, "holder": a.holder,
                  "file": path.name, "certificate_sha256": cert["certificate_sha256"],
                  "chain_height": tip["height"], "minted_at_utc": cert["minted_at_utc"],
                  "quantum_source": prov.source})
    INDEX.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"minted #{serial:05d}: {a.artifact} ({a.kind}/{a.relic_class or '-'})")
    print(f"  cert: {path}")
    print(f"  cert sha256: {cert['certificate_sha256']}")
    print(f"  anchored to block {tip['height']} {tip['block_hash'][:16]}…")
    print(f"  quantum source: {prov.source}")
    return 0


def verify(path: str) -> int:
    cert = json.loads(Path(path).read_text(encoding="utf-8"))
    claimed = cert.pop("certificate_sha256", None)
    actual = hashlib.sha256(canonical(cert)).hexdigest()
    ok = claimed == actual
    print(f"certificate hash: {'OK' if ok else 'MISMATCH'}")
    print(f"  claimed: {claimed}\n  actual:  {actual}")
    tip = chain_tip()
    anch = cert.get("chain_anchor", {})
    print(f"anchor block {anch.get('height')} vs current tip {tip['height']} "
          f"({'plausible' if anch.get('height', 0) <= tip['height'] else 'IMPOSSIBLE'})")
    return 0 if ok else 1


def list_certs() -> int:
    for e in load_index():
        print(f"#{e['serial']:05d} {e['artifact']:<30} {e['kind']}/{e.get('relic_class') or '-':<8} "
              f"holder={e['holder']:<12} block={e['chain_height']} q={e['quantum_source']}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="SpaceCash provenance registry")
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mint")
    m.add_argument("--artifact", required=True)
    m.add_argument("--kind", choices=["artifact", "relic"], default="artifact")
    m.add_argument("--relic-class", choices=["patron", "founder", "lore", "agent"], default=None)
    m.add_argument("--edition", default="1")
    m.add_argument("--art-sha256", required=True, help="file path or 64-hex sha256")
    m.add_argument("--holder", default="unassigned")
    m.add_argument("--nfc-uid", default=None)
    m.add_argument("--physical-twin", default=None)
    v = sub.add_parser("verify")
    v.add_argument("path")
    sub.add_parser("list")
    a = p.parse_args()
    if a.cmd == "mint":
        return mint(a)
    if a.cmd == "verify":
        return verify(a.path)
    return list_certs()


if __name__ == "__main__":
    raise SystemExit(main())
