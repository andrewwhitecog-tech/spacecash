import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spacecash_core import protocol  # noqa: E402
from tests.test_spacecash_core import TMP_ROOT  # noqa: E402
from tools.spacecash_gate_evidence import validate_gate_evidence, write_gate_evidence_template  # noqa: E402


class GateEvidenceTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.out_path = TMP_ROOT / f"test_spacecash_gate_evidence_{protocol.hash_text(id(self))[:12]}.json"

    def tearDown(self):
        if self.out_path.exists():
            self.out_path.unlink()

    def complete_evidence(self):
        payload = write_gate_evidence_template()
        for gate in payload["gates"]:
            gate["status"] = "complete"
            for field in gate["required_evidence"]:
                if field.endswith("_hash") or field.endswith("_sha256") or field == "reviewed_source_hash":
                    gate["evidence"][field] = "A" * 64
                else:
                    gate["evidence"][field] = f"reviewed {field}"
            gate["review"] = {
                "reviewer": "test reviewer",
                "role": "unit test",
                "reviewed_at": "2026-04-26T00:00:00Z",
                "decision": "approved",
                "notes": "Unit-test approval fixture.",
            }
        return payload

    def test_gate_evidence_template_is_written_and_valid_but_not_complete(self):
        payload = write_gate_evidence_template(self.out_path)

        self.assertTrue(self.out_path.exists())
        disk = json.loads(self.out_path.read_text(encoding="utf-8"))
        self.assertEqual(disk, payload)
        self.assertEqual(payload["chain_id"], protocol.CHAIN_ID)
        self.assertEqual(len(payload["gates"]), 5)

        result = validate_gate_evidence(payload)
        self.assertTrue(result["ok"])
        self.assertFalse(result["mainnet_manual_ready"])
        self.assertEqual(len(result["blocker_gates"]), 5)
        self.assertIn("public_testnet_complete", result["blocker_gates"])

    def test_complete_gate_evidence_can_pass_require_complete(self):
        result = validate_gate_evidence(self.complete_evidence(), require_complete=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["mainnet_manual_ready"])
        self.assertEqual(len(result["complete_gates"]), 5)
        self.assertEqual(result["blocker_gates"], [])

    def test_require_complete_rejects_empty_template(self):
        result = validate_gate_evidence(write_gate_evidence_template(), require_complete=True)

        self.assertFalse(result["ok"])
        self.assertFalse(result["mainnet_manual_ready"])
        self.assertIn("Manual gate evidence is not complete.", result["errors"])


if __name__ == "__main__":
    unittest.main()
