import json
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spacecash_core import protocol  # noqa: E402
from tests.test_spacecash_core import TMP_ROOT  # noqa: E402
from tools.spacecash_consensus_spec import write_consensus_spec  # noqa: E402


class ConsensusSpecTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.out_path = TMP_ROOT / f"test_spacecash_consensus_{protocol.hash_text(id(self))[:12]}.json"

    def tearDown(self):
        if self.out_path.exists():
            self.out_path.unlink()
        if self.out_path.parent.exists() and self.out_path.parent != TMP_ROOT:
            shutil.rmtree(self.out_path.parent)

    def test_consensus_spec_is_deterministic_and_written(self):
        spec = write_consensus_spec(self.out_path)

        self.assertTrue(self.out_path.exists())
        disk = json.loads(self.out_path.read_text(encoding="utf-8"))
        self.assertEqual(disk, spec)
        self.assertEqual(spec["id"], protocol.CONSENSUS_SPEC_ID)
        self.assertEqual(spec["version"], protocol.CONSENSUS_SPEC_VERSION)
        self.assertEqual(spec["spec_hash"], protocol.consensus_spec_hash())
        self.assertFalse(spec["fork_choice"]["automatic_reorgs"])
        self.assertIn("public testnet evidence", spec["mainnet_gaps"])


if __name__ == "__main__":
    unittest.main()
