import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spacecash_core import protocol  # noqa: E402
from tests.test_spacecash_core import TMP_ROOT  # noqa: E402
from tools.spacecash_genesis_plan import write_genesis_plan  # noqa: E402


class GenesisPlanTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.out_path = TMP_ROOT / f"test_spacecash_genesis_plan_{protocol.hash_text(id(self))[:12]}.json"

    def tearDown(self):
        if self.out_path.exists():
            self.out_path.unlink()

    def test_genesis_plan_is_deterministic_and_written(self):
        plan = write_genesis_plan(self.out_path)

        self.assertTrue(self.out_path.exists())
        disk = json.loads(self.out_path.read_text(encoding="utf-8"))
        self.assertEqual(disk, plan)
        self.assertEqual(plan["id"], protocol.GENESIS_PLAN_ID)
        self.assertEqual(plan["version"], protocol.GENESIS_PLAN_VERSION)
        self.assertEqual(plan["plan_hash"], protocol.genesis_plan_hash())
        self.assertFalse(plan["source_of_truth"]["devnet_history_carried_to_mainnet"])
        self.assertFalse(plan["allocation_boundary"]["devnet_wallet_balances_auto_migrate"])
        self.assertFalse(plan["allocation_boundary"]["candidate_private_keys_allowed"])
        self.assertEqual(plan["manual_gate"]["status"], "not_complete")


if __name__ == "__main__":
    unittest.main()
