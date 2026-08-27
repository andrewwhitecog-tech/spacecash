"""Write the deterministic SpaceCash symbolic value artifact."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spacecash_core import protocol  # noqa: E402


def write_symbolic_value(out_path=None):
    artifact = protocol.symbolic_value()
    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def build_parser():
    parser = argparse.ArgumentParser(description="Write the SpaceCash non-monetary symbolic value JSON")
    parser.add_argument("--out", type=Path, help="Optional output JSON path")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    artifact = write_symbolic_value(args.out)
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
