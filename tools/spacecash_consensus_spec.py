"""Write the deterministic SpaceCash devnet consensus specification."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spacecash_core import protocol  # noqa: E402


def write_consensus_spec(out_path=None):
    spec = protocol.consensus_spec()
    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return spec


def build_parser():
    parser = argparse.ArgumentParser(description="Write the SpaceCash consensus specification JSON")
    parser.add_argument("--out", type=Path, help="Optional output JSON path")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    spec = write_consensus_spec(args.out)
    print(json.dumps(spec, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
