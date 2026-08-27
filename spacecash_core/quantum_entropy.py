"""spacecash_core.quantum_entropy — ceremony entropy born from the quantum vacuum.

The ANU QRNG measures zero-point fluctuations of the electromagnetic vacuum
(homodyne detection of the vacuum state). Those bits are genuinely
indeterminate before measurement — information created, not copied. This
module fetches vacuum-fluctuation bytes and mixes them with local OS entropy
to produce auditable "birth certificate" entropy for SpaceCash ceremonies
(genesis seeds, ceremony nonces, commemorative wallet IDs).

Security invariants (do not weaken):
  1. Remote entropy is NEVER used alone. Output = SHA-512 chain over
     (local os.urandom(64) || vacuum bytes || context). Even a fully
     adversarial/observed QRNG cannot weaken the output below local strength.
  2. NOT for consensus. Consensus stays deterministic (see CONSENSUS_SPEC).
     This is ceremony/identity entropy only.
  3. Offline-honest: if the vacuum source is unreachable, provenance says
     "local_only" — it never pretends bits came from the vacuum.

CLI:
  python -m spacecash_core.quantum_entropy --bytes 32
  python -m spacecash_core.quantum_entropy --bytes 64 --birth-certificate cert.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

# Legacy free endpoint (rate-limited ~1 req/min). For volume, set
# SPACECASH_QRNG_API_KEY and we use the keyed api.quantumnumbers.anu.edu.au.
ANU_FREE_URL = "https://qrng.anu.edu.au/API/jsonI.php"
ANU_KEYED_URL = "https://api.quantumnumbers.anu.edu.au"
SOURCE_DESCRIPTION = (
    "ANU QRNG: homodyne measurement of electromagnetic vacuum-state "
    "zero-point fluctuations"
)


@dataclass
class VacuumProvenance:
    source: str                 # "anu_vacuum_fluctuation" | "local_only"
    description: str
    fetched_at_utc: str
    vacuum_sha256: str | None   # hash of the raw vacuum bytes (bytes not stored)
    vacuum_bytes: int
    mix_spec: str
    output_sha256: str          # hash of the produced entropy (commitment)


def _fetch_vacuum_bytes(n: int, timeout: float = 15.0) -> bytes | None:
    """Fetch n bytes of vacuum-fluctuation entropy from ANU. None on failure."""
    if requests is None:
        return None
    n = max(1, min(n, 1024))
    api_key = os.environ.get("SPACECASH_QRNG_API_KEY", "").strip()
    try:
        if api_key:
            r = requests.get(
                ANU_KEYED_URL,
                params={"length": n, "type": "hex8", "size": 1},
                headers={"x-api-key": api_key},
                timeout=timeout,
            )
        else:
            r = requests.get(
                ANU_FREE_URL,
                params={"length": n, "type": "hex16", "size": 1},
                timeout=timeout,
            )
        r.raise_for_status()
        j = r.json()
        if not j.get("success", True):
            return None
        data = j.get("data", [])
        raw = bytes.fromhex("".join(data))
        return raw[:n] if len(raw) >= n else (raw or None)
    except Exception:
        return None


def _mix(local: bytes, vacuum: bytes | None, context: str, out_len: int) -> bytes:
    """SHA-512 expand over local || vacuum || context. Local always present."""
    out = b""
    counter = 0
    seed = local + (vacuum or b"") + context.encode("utf-8")
    while len(out) < out_len:
        out += hashlib.sha512(seed + counter.to_bytes(4, "big")).digest()
        counter += 1
    return out[:out_len]


def generate(out_len: int = 32, context: str = "spacecash-ceremony",
             want_vacuum: int = 64) -> tuple[bytes, VacuumProvenance]:
    """Produce ceremony entropy + provenance. Never blocks consensus paths."""
    local = os.urandom(64)
    vacuum = _fetch_vacuum_bytes(want_vacuum)
    entropy = _mix(local, vacuum, context, out_len)
    prov = VacuumProvenance(
        source="anu_vacuum_fluctuation" if vacuum else "local_only",
        description=SOURCE_DESCRIPTION if vacuum else
        "vacuum source unreachable; local OS entropy only (honest fallback)",
        fetched_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        vacuum_sha256=hashlib.sha256(vacuum).hexdigest() if vacuum else None,
        vacuum_bytes=len(vacuum) if vacuum else 0,
        mix_spec="sha512-expand(local_urandom64 || vacuum || context || ctr32)",
        output_sha256=hashlib.sha256(entropy).hexdigest(),
    )
    return entropy, prov


def main() -> int:
    p = argparse.ArgumentParser(description="SpaceCash quantum-vacuum ceremony entropy")
    p.add_argument("--bytes", type=int, default=32, dest="n")
    p.add_argument("--context", default="spacecash-ceremony")
    p.add_argument("--birth-certificate", default=None,
                   help="write provenance JSON here")
    a = p.parse_args()
    entropy, prov = generate(a.n, a.context)
    print("entropy_hex:", entropy.hex())
    print(json.dumps(asdict(prov), indent=2))
    if a.birth_certificate:
        with open(a.birth_certificate, "w", encoding="utf-8") as f:
            json.dump({"entropy_hex": entropy.hex(), "provenance": asdict(prov)}, f, indent=2)
        print("birth certificate ->", a.birth_certificate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
