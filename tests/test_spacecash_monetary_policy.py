import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spacecash_core import protocol  # noqa: E402
from tests.test_spacecash_core import TMP_ROOT  # noqa: E402
from tools.spacecash_monetary_policy import write_monetary_policy  # noqa: E402


class MonetaryPolicyTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.out_path = TMP_ROOT / f"test_spacecash_monetary_policy_{protocol.hash_text(id(self))[:12]}.json"

    def tearDown(self):
        if self.out_path.exists():
            self.out_path.unlink()

    def test_monetary_policy_is_deterministic_and_written(self):
        policy = write_monetary_policy(self.out_path)

        self.assertTrue(self.out_path.exists())
        disk = json.loads(self.out_path.read_text(encoding="utf-8"))
        self.assertEqual(disk, policy)
        self.assertEqual(policy["id"], protocol.MONETARY_POLICY_ID)
        self.assertEqual(policy["version"], protocol.MONETARY_POLICY_VERSION)
        self.assertEqual(policy["policy_hash"], protocol.monetary_policy_hash())
        self.assertEqual(policy["supply"]["genesis_units"], protocol.GENESIS_UNITS)
        self.assertEqual(policy["supply"]["supply_cap_units"], protocol.GENESIS_UNITS)
        self.assertEqual(policy["issuance"]["block_reward_units"], 0)
        self.assertFalse(policy["issuance"]["mint_route_available"])
        self.assertEqual(policy["manual_gate"]["status"], "not_complete")


if __name__ == "__main__":
    unittest.main()
