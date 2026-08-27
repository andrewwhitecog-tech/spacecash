import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spacecash_core import protocol  # noqa: E402
from tests.test_spacecash_core import TMP_ROOT  # noqa: E402
from tools.spacecash_wallet_policy import write_wallet_policy  # noqa: E402


class WalletPolicyTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.out_path = TMP_ROOT / f"test_spacecash_wallet_policy_{protocol.hash_text(id(self))[:12]}.json"

    def tearDown(self):
        if self.out_path.exists():
            self.out_path.unlink()

    def test_wallet_policy_is_deterministic_and_written(self):
        policy = write_wallet_policy(self.out_path)

        self.assertTrue(self.out_path.exists())
        disk = json.loads(self.out_path.read_text(encoding="utf-8"))
        self.assertEqual(disk, policy)
        self.assertEqual(policy["id"], protocol.WALLET_POLICY_ID)
        self.assertEqual(policy["version"], protocol.WALLET_POLICY_VERSION)
        self.assertEqual(policy["policy_hash"], protocol.wallet_policy_hash())
        self.assertEqual(policy["addressing"]["address_version"], protocol.ADDRESS_VERSION)
        self.assertEqual(policy["encrypted_backup"]["minimum_passphrase_length"], protocol.MIN_BACKUP_PASSPHRASE_LENGTH)
        self.assertFalse(policy["custody"]["custodial_operations_allowed"])
        self.assertEqual(policy["manual_gate"]["status"], "not_complete")


if __name__ == "__main__":
    unittest.main()
