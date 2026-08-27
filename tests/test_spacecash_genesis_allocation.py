import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spacecash_core import protocol  # noqa: E402
from tests.test_spacecash_core import TMP_ROOT  # noqa: E402
from tools.spacecash_genesis_allocation import allocation_hash, validate_allocation, write_allocation_template  # noqa: E402


class GenesisAllocationTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.out_path = TMP_ROOT / f"test_spacecash_genesis_allocation_{protocol.hash_text(id(self))[:12]}.json"

    def tearDown(self):
        if self.out_path.exists():
            self.out_path.unlink()

    def approved_allocation(self):
        allocation = write_allocation_template()
        allocation["status"] = "approved"
        allocation["allocations"] = [{
            "address": protocol.TREASURY,
            "amount_units": protocol.GENESIS_UNITS,
            "label": "Reviewed treasury allocation",
            "basis": "Full fixed supply held by reviewed treasury controls for test approval.",
            "reviewer": "test-reviewer",
        }]
        allocation["approval"] = {
            "approved": True,
            "approved_by": "test-reviewer",
            "approved_at": "2026-04-26T00:00:00Z",
            "reviewed_source_hash": "A" * 64,
            "notes": "Unit-test approval fixture.",
        }
        allocation["manual_gate"] = {
            "id": "legal_compliance_review_complete",
            "status": "complete",
            "reason": "Unit-test approval fixture.",
        }
        allocation["allocation_hash"] = allocation_hash(allocation)
        return allocation

    def test_template_is_written_and_structurally_valid_but_not_ready(self):
        allocation = write_allocation_template(self.out_path)

        self.assertTrue(self.out_path.exists())
        disk = json.loads(self.out_path.read_text(encoding="utf-8"))
        self.assertEqual(disk, allocation)
        self.assertEqual(allocation["chain_id"], protocol.CHAIN_ID)
        self.assertEqual(allocation["genesis_plan_hash"], protocol.genesis_plan_hash())
        self.assertEqual(allocation["monetary_policy_hash"], protocol.monetary_policy_hash())
        self.assertEqual(allocation["supply_cap_units"], protocol.GENESIS_UNITS)

        result = validate_allocation(allocation)
        self.assertTrue(result["ok"])
        self.assertFalse(result["allocation_ready"])
        self.assertEqual(result["total_units"], 0)
        self.assertIn("allocation total does not match the supply cap.", result["warnings"])

    def test_approved_full_supply_allocation_is_ready(self):
        allocation = self.approved_allocation()
        result = validate_allocation(allocation, require_approved=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["allocation_ready"])
        self.assertEqual(result["allocation_hash"], result["computed_allocation_hash"])
        self.assertEqual(result["total_units"], protocol.GENESIS_UNITS)
        self.assertEqual(result["allocation_count"], 1)

    def test_duplicate_address_and_invalid_amount_are_rejected(self):
        allocation = write_allocation_template()
        allocation["allocations"] = [
            {
                "address": protocol.TREASURY,
                "amount_units": 1,
                "label": "first",
                "basis": "test",
                "reviewer": "reviewer",
            },
            {
                "address": protocol.TREASURY,
                "amount_units": 0,
                "label": "second",
                "basis": "test",
                "reviewer": "reviewer",
            },
        ]
        allocation["allocation_hash"] = allocation_hash(allocation)

        result = validate_allocation(allocation)
        self.assertFalse(result["ok"])
        self.assertIn(protocol.TREASURY, result["duplicate_addresses"])
        self.assertTrue(any("duplicates" in error for error in result["errors"]))
        self.assertTrue(any("positive integer" in error for error in result["errors"]))

    def test_require_approved_rejects_unapproved_supply_complete_file(self):
        allocation = write_allocation_template()
        allocation["allocations"] = [{
            "address": protocol.TREASURY,
            "amount_units": protocol.GENESIS_UNITS,
            "label": "Treasury",
            "basis": "Supply-complete but not approved.",
            "reviewer": "reviewer",
        }]
        allocation["allocation_hash"] = allocation_hash(allocation)

        result = validate_allocation(allocation, require_approved=True)
        self.assertFalse(result["ok"])
        self.assertFalse(result["allocation_ready"])
        self.assertTrue(any("status must be approved" in error for error in result["errors"]))
        self.assertTrue(any("manual_gate" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
