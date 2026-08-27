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
from tools.spacecash_public_testnet_evidence import (  # noqa: E402
    REQUIRED_NODE_REPORTS,
    REQUIRED_SCENARIOS,
    build_public_testnet_workbench,
    file_hash,
    validate_public_testnet_evidence,
    write_public_testnet_evidence_template,
)


class PublicTestnetEvidenceTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.out_path = TMP_ROOT / f"test_spacecash_public_testnet_evidence_{protocol.hash_text(id(self))[:12]}.json"
        self.workbench_dir = TMP_ROOT / f"test_spacecash_public_testnet_workbench_{protocol.hash_text(id(self))[:12]}"

    def tearDown(self):
        if self.out_path.exists():
            self.out_path.unlink()
        if self.workbench_dir.exists():
            shutil.rmtree(self.workbench_dir)

    def complete_evidence(self):
        payload = write_public_testnet_evidence_template(node_count=3)
        payload["status"] = "complete"
        payload["duration_days"] = 7
        for index, node in enumerate(payload["nodes"]):
            node["operator"] = f"operator-{index + 1}"
            node["operator_contact"] = f"operator-{index + 1}@example.test"
            node["url"] = f"http://testnet-node-{index + 1}.example.test:8876"
            node["independently_operated"] = True
            node["reports"] = {name: f"reports/{node['node_id']}/{name}.json" for name in REQUIRED_NODE_REPORTS}
        for scenario in payload["scenarios"]:
            scenario["status"] = "pass"
            scenario["evidence"] = f"evidence/{scenario['id']}.json"
        payload["incidents"] = [{"id": "SCTN-001", "status": "closed", "resolution": "No launch blocker."}]
        payload["final_report"] = {
            "path": "reports/public_testnet_final.md",
            "sha256": "B" * 64,
            "reviewer": "test reviewer",
            "reviewed_at": "2026-04-26T00:00:00Z",
            "decision": "approved",
            "notes": "Unit-test approval fixture.",
        }
        payload["manual_gate"] = {
            "id": "public_testnet_complete",
            "status": "complete",
            "reason": "Unit-test approval fixture.",
        }
        return payload

    def test_public_testnet_template_is_valid_but_not_ready(self):
        payload = write_public_testnet_evidence_template(self.out_path)

        self.assertTrue(self.out_path.exists())
        disk = json.loads(self.out_path.read_text(encoding="utf-8"))
        self.assertEqual(disk, payload)
        self.assertEqual(payload["chain_id"], protocol.CHAIN_ID)
        self.assertEqual(len(payload["nodes"]), 3)
        self.assertEqual(len(payload["scenarios"]), len(REQUIRED_SCENARIOS))

        result = validate_public_testnet_evidence(payload)
        self.assertTrue(result["ok"])
        self.assertFalse(result["public_testnet_ready"])
        self.assertIn("duration_below_minimum", result["blockers"])
        self.assertIn("manual_gate_not_complete", result["blockers"])

    def test_complete_public_testnet_evidence_passes_require_complete(self):
        result = validate_public_testnet_evidence(self.complete_evidence(), require_complete=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["public_testnet_ready"])
        self.assertEqual(result["ready_node_count"], 3)
        self.assertEqual(result["independent_operators"], 3)
        self.assertEqual(result["blockers"], [])

    def test_require_complete_rejects_empty_template(self):
        result = validate_public_testnet_evidence(write_public_testnet_evidence_template(), require_complete=True)

        self.assertFalse(result["ok"])
        self.assertFalse(result["public_testnet_ready"])
        self.assertIn("Public testnet evidence is not complete.", result["errors"])

    def test_public_testnet_workbench_writes_review_inputs_and_checksums(self):
        result = build_public_testnet_workbench(
            out_dir=self.workbench_dir,
            reviewed_source_hash="A" * 64,
            force=True,
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["public_testnet_ready"])
        self.assertEqual(result["manual_gate"]["status"], "not_complete")
        self.assertEqual(result["node_count"], 3)
        self.assertEqual(result["scenario_count"], len(REQUIRED_SCENARIOS))
        self.assertIn("manual_gate_not_complete", result["blockers"])
        self.assertIn("final_report_not_approved", result["blockers"])
        self.assertIn("duration_below_minimum", result["blockers"])

        self.assertTrue((self.workbench_dir / "README.md").exists())
        self.assertTrue((self.workbench_dir / "public_testnet_workbench_summary.json").exists())
        self.assertTrue((self.workbench_dir / "public_testnet_evidence_workbench.json").exists())
        self.assertTrue((self.workbench_dir / "public_testnet_evidence_workbench_check.json").exists())
        self.assertTrue((self.workbench_dir / "testnet" / "reviewer" / "review_ticket_template.md").exists())
        self.assertTrue((self.workbench_dir / "testnet" / "operators" / "operator_roster_review.md").exists())
        self.assertTrue((self.workbench_dir / "testnet" / "node_reports" / "health_report.md").exists())
        self.assertTrue((self.workbench_dir / "testnet" / "scenarios" / "signed_transfer.md").exists())
        self.assertTrue((self.workbench_dir / "testnet" / "incidents" / "incident_response_review.md").exists())
        self.assertTrue((self.workbench_dir / "testnet" / "final_public_testnet_report_template.md").exists())

        payload = json.loads((self.workbench_dir / "public_testnet_evidence_workbench.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["reviewed_source_hash"], "A" * 64)
        self.assertEqual(payload["release_bundle_sha256"], "")
        self.assertEqual(payload["final_report"]["path"], "testnet/final_public_testnet_report_template.md")
        self.assertEqual(
            payload["final_report"]["sha256"],
            file_hash(self.workbench_dir / payload["final_report"]["path"]),
        )
        self.assertIn("testnet/scenarios/signed_transfer.md", {scenario["evidence"] for scenario in payload["scenarios"]})

        check = json.loads((self.workbench_dir / "public_testnet_evidence_workbench_check.json").read_text(encoding="utf-8"))
        self.assertTrue(check["ok"])
        self.assertFalse(check["public_testnet_ready"])

        sums = (self.workbench_dir / "SHA256SUMS.txt").read_text(encoding="utf-8")
        self.assertIn("public_testnet_workbench_summary.json", sums)
        self.assertIn("public_testnet_evidence_workbench.json", sums)
        self.assertIn("testnet/scenarios/signed_transfer.md", sums)
        self.assertIn("testnet/node_reports/health_report.md", sums)
        self.assertIn("testnet/final_public_testnet_report_template.md", sums)
        for line in sums.splitlines():
            digest, rel = line.split("  ", 1)
            self.assertEqual(file_hash(self.workbench_dir / rel), digest)


if __name__ == "__main__":
    unittest.main()
