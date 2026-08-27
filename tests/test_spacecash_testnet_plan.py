import hashlib
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spacecash_core import protocol  # noqa: E402
from tests.test_spacecash_core import TMP_ROOT  # noqa: E402
from tools.spacecash_testnet_plan import build_testnet_package  # noqa: E402


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class TestnetPlanTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.out_dir = TMP_ROOT / f"test_spacecash_testnet_{protocol.hash_text(id(self))[:12]}"

    def tearDown(self):
        if self.out_dir.exists():
            shutil.rmtree(self.out_dir)

    def test_testnet_package_writes_nodes_evidence_and_checksums(self):
        result = build_testnet_package(
            out_dir=self.out_dir,
            node_count=3,
            base_port=19000,
            validator_count=3,
            validator_quorum=2,
            force=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["node_count"], 3)
        self.assertEqual(len(result["validators"]), 3)
        self.assertEqual(result["validator_quorum"], 2)
        self.assertTrue(result["candidate"]["automated_release_candidate"])
        self.assertFalse(result["candidate"]["mainnet_ready"])
        self.assertFalse(result["dev_keys_included"])
        self.assertTrue((self.out_dir / "testnet_plan.json").exists())
        self.assertTrue((self.out_dir / "candidate_summary.json").exists())
        self.assertTrue((self.out_dir / "operator_checklist.md").exists())
        self.assertTrue((self.out_dir / "operators" / "README.md").exists())
        self.assertTrue((self.out_dir / "operators" / "contact_roster_template.md").exists())
        self.assertTrue((self.out_dir / "operators" / "evidence_intake_checklist.md").exists())
        self.assertTrue((self.out_dir / "operators" / "operator_commitment_template.md").exists())
        self.assertTrue((self.out_dir / "operators" / "node-01" / "operator_intake.json").exists())
        self.assertTrue((self.out_dir / "operators" / "node-01" / "node_runbook.md").exists())
        self.assertTrue((self.out_dir / "operators" / "node-01" / "evidence_manifest_template.json").exists())
        self.assertTrue((self.out_dir / "operator_onboarding_check.json").exists())
        self.assertTrue((self.out_dir / "daily_report_template.md").exists())
        self.assertTrue((self.out_dir / "incident_log.md").exists())
        self.assertTrue((self.out_dir / "manual_gate_evidence.json").exists())
        self.assertTrue((self.out_dir / "public_testnet_exit_evidence_template.json").exists())
        self.assertTrue((self.out_dir / "reports" / "node-01" / "health_report.json").exists())
        self.assertTrue((self.out_dir / "reports" / "node-01" / "readiness_report.json").exists())
        self.assertTrue((self.out_dir / "reports" / "node-01" / "audit_report.json").exists())
        self.assertTrue((self.out_dir / "reports" / "node-01" / "chain_manifest.json").exists())
        self.assertTrue((self.out_dir / "reports" / "node-01" / "checkpoint_report.json").exists())
        self.assertTrue((self.out_dir / "reports" / "node-01" / "peer_report.json").exists())
        self.assertTrue((self.out_dir / "evidence" / "scenarios" / "signed_transfer.json").exists())
        self.assertTrue((self.out_dir / "evidence" / "scenarios" / "product_payment.json").exists())
        self.assertTrue((self.out_dir / "nodes" / "node-01" / "node_config.json").exists())
        self.assertTrue((self.out_dir / "nodes" / "node-01" / "spacecash_testnet.sqlite3").exists())
        self.assertFalse((self.out_dir / "testnet_dev_keys.json").exists())
        self.assertEqual(len(result["evidence_templates"]["node_reports"]), 18)
        self.assertEqual(len(result["evidence_templates"]["scenarios"]), 9)
        self.assertEqual(result["operator_packet"]["path"], "operators")
        self.assertEqual(result["operator_packet"]["node_count"], 3)
        self.assertEqual(result["operator_packet"]["status"], "intake_template_only")
        self.assertEqual(result["operator_packet"]["check_path"], "operator_onboarding_check.json")
        self.assertFalse(result["operator_packet"]["ready"])
        self.assertIn("not_enough_independent_operators", result["operator_packet"]["blockers"])
        self.assertEqual(len(result["evidence_templates"]["operator_onboarding"]), 13)

        sums = (self.out_dir / "SHA256SUMS.txt").read_text(encoding="utf-8")
        self.assertIn("testnet_plan.json", sums)
        self.assertIn("nodes/node-01/node_config.json", sums)
        self.assertIn("operators/README.md", sums)
        self.assertIn("operators/contact_roster_template.md", sums)
        self.assertIn("operators/node-01/operator_intake.json", sums)
        self.assertIn("operators/node-01/node_runbook.md", sums)
        self.assertIn("operators/node-01/evidence_manifest_template.json", sums)
        self.assertIn("operator_onboarding_check.json", sums)
        self.assertIn("manual_gate_evidence.json", sums)
        self.assertIn("public_testnet_exit_evidence_template.json", sums)
        self.assertIn("reports/node-01/health_report.json", sums)
        self.assertIn("evidence/scenarios/signed_transfer.json", sums)
        for line in sums.splitlines():
            digest, rel = line.split("  ", 1)
            self.assertEqual(file_hash(self.out_dir / rel), digest)


if __name__ == "__main__":
    unittest.main()
