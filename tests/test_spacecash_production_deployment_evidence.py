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
from tools.spacecash_production_deployment_evidence import (  # noqa: E402
    REQUIRED_DECISIONS,
    build_production_deployment_workbench,
    file_hash,
    validate_production_deployment_evidence,
    write_production_deployment_evidence_template,
)


class ProductionDeploymentEvidenceTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.out_path = TMP_ROOT / f"test_spacecash_production_deployment_evidence_{protocol.hash_text(id(self))[:12]}.json"
        self.workbench_dir = TMP_ROOT / f"test_spacecash_deployment_workbench_{protocol.hash_text(id(self))[:12]}"

    def tearDown(self):
        if self.out_path.exists():
            self.out_path.unlink()
        if self.workbench_dir.exists():
            shutil.rmtree(self.workbench_dir)

    def complete_evidence(self):
        payload = write_production_deployment_evidence_template()
        payload["status"] = "approved"
        payload["reviewed_source_hash"] = "A" * 64
        payload["release_bundle_sha256"] = "B" * 64
        payload["security_review_packet_sha256"] = "C" * 64
        payload["approved_genesis_allocation_sha256"] = "D" * 64
        payload["reviewer"] = {
            "name": "Deployment Reviewer",
            "role": "release_manager",
            "contact": "deploy-review@example.test",
            "reviewed_at": "2026-04-29T00:00:00Z",
            "change_ticket": "DEPLOY-001",
        }
        payload["environment"] = {
            "production_domain": "spacecash.example.test",
            "deployment_target": "three-node production launch rehearsal",
            "bootstrap_peers": ["https://node-01.example.test", "https://node-02.example.test"],
            "validator_count": 3,
            "validator_quorum": 2,
            "monitoring_endpoints": ["https://status.example.test/spacecash"],
            "incident_contact": "ops@example.test",
        }
        payload["readiness_inputs"] = {
            "public_testnet_evidence_sha256": "E" * 64,
            "security_review_evidence_sha256": "F" * 64,
            "legal_compliance_evidence_sha256": "1" * 64,
            "wallet_custody_evidence_sha256": "2" * 64,
            "genesis_allocation_check_sha256": "3" * 64,
        }
        for decision in payload["decisions"]:
            decision["status"] = "approved"
            decision["owner"] = "Deployment Reviewer"
            decision["evidence"] = f"deployment/{decision['id']}.md"
            decision["notes"] = "Unit-test deployment approval fixture."
        payload["controls"] = {
            "release_manifest_path": "deployment/release_manifest.json",
            "release_manifest_sha256": "4" * 64,
            "release_bundle_path": "deployment/release_bundle.zip",
            "release_bundle_sha256": "5" * 64,
            "sha256sums_path": "deployment/SHA256SUMS.txt",
            "sha256sums_sha256": "6" * 64,
            "deployment_runbook_path": "deployment/runbook.md",
            "deployment_runbook_sha256": "7" * 64,
            "node_setup_instructions_path": "deployment/node-setup.md",
            "node_setup_instructions_sha256": "8" * 64,
            "bootstrap_peer_plan_path": "deployment/bootstrap-peers.md",
            "bootstrap_peer_plan_sha256": "9" * 64,
            "validator_rollout_plan_path": "deployment/validators.md",
            "validator_rollout_plan_sha256": "A" * 64,
            "production_http_controls_path": "deployment/http-controls.md",
            "production_http_controls_sha256": "B" * 64,
            "monitoring_plan_path": "deployment/monitoring.md",
            "monitoring_plan_sha256": "C" * 64,
            "backup_restore_rehearsal_path": "deployment/backup-restore.md",
            "backup_restore_rehearsal_sha256": "D" * 64,
            "rollback_plan_path": "deployment/rollback.md",
            "rollback_plan_sha256": "E" * 64,
            "incident_response_plan_path": "deployment/incident-response.md",
            "incident_response_plan_sha256": "F" * 64,
            "post_deploy_audit_plan_path": "deployment/post-deploy-audit.md",
            "post_deploy_audit_plan_sha256": "1" * 64,
        }
        payload["final_approval"] = {
            "approved": True,
            "approved_at": "2026-04-29T00:00:00Z",
            "approver": "Deployment Reviewer",
            "statement": "Unit-test production deployment approval fixture.",
            "launch_window_approved": True,
            "write_route_controls_approved": True,
            "monitoring_owner_confirmed": True,
            "rollback_owner_confirmed": True,
            "backup_restore_rehearsed": True,
            "release_artifacts_archived": True,
            "post_deploy_audit_required": True,
        }
        payload["manual_gate"] = {
            "id": "production_deployment_runbook_complete",
            "status": "complete",
            "reason": "Unit-test production deployment approval fixture.",
        }
        return payload

    def test_production_deployment_template_is_valid_but_not_ready(self):
        payload = write_production_deployment_evidence_template(self.out_path)

        self.assertTrue(self.out_path.exists())
        disk = json.loads(self.out_path.read_text(encoding="utf-8"))
        self.assertEqual(disk, payload)
        self.assertEqual(payload["chain_id"], protocol.CHAIN_ID)
        self.assertEqual(len(payload["decisions"]), len(REQUIRED_DECISIONS))

        result = validate_production_deployment_evidence(payload)
        self.assertTrue(result["ok"])
        self.assertFalse(result["deployment_ready"])
        self.assertIn("deployment_decisions_not_approved", result["blockers"])
        self.assertIn("manual_gate_not_complete", result["blockers"])

    def test_complete_production_deployment_evidence_passes_require_complete(self):
        result = validate_production_deployment_evidence(self.complete_evidence(), require_complete=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["deployment_ready"])
        self.assertEqual(result["approved_decision_count"], len(REQUIRED_DECISIONS))
        self.assertEqual(result["blockers"], [])

    def test_require_complete_rejects_empty_template(self):
        result = validate_production_deployment_evidence(write_production_deployment_evidence_template(), require_complete=True)

        self.assertFalse(result["ok"])
        self.assertFalse(result["deployment_ready"])
        self.assertIn("Production deployment evidence is not complete.", result["errors"])

    def test_validator_quorum_cannot_exceed_validator_count(self):
        payload = self.complete_evidence()
        payload["environment"]["validator_quorum"] = 4

        result = validate_production_deployment_evidence(payload, require_complete=True)

        self.assertFalse(result["ok"])
        self.assertFalse(result["deployment_ready"])
        self.assertIn("environment.validator_quorum cannot exceed validator_count.", result["errors"])

    def test_production_deployment_workbench_writes_review_inputs_and_checksums(self):
        result = build_production_deployment_workbench(
            out_dir=self.workbench_dir,
            reviewed_source_hash="A" * 64,
            force=True,
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["deployment_ready"])
        self.assertEqual(result["manual_gate"]["status"], "not_complete")
        self.assertEqual(result["decision_count"], len(REQUIRED_DECISIONS))
        self.assertIn("manual_gate_not_complete", result["blockers"])
        self.assertIn("deployment_decisions_not_approved", result["blockers"])
        self.assertIn("release_bundle_sha256_missing", result["blockers"])
        self.assertIn("final_approval_not_approved", result["blockers"])

        self.assertTrue((self.workbench_dir / "README.md").exists())
        self.assertTrue((self.workbench_dir / "production_deployment_workbench_summary.json").exists())
        self.assertTrue((self.workbench_dir / "production_deployment_evidence_workbench.json").exists())
        self.assertTrue((self.workbench_dir / "production_deployment_evidence_workbench_check.json").exists())
        self.assertTrue((self.workbench_dir / "deployment" / "reviewer" / "change_ticket_template.md").exists())
        self.assertTrue((self.workbench_dir / "deployment" / "environment_template.md").exists())
        self.assertTrue((self.workbench_dir / "deployment" / "readiness_inputs_template.md").exists())
        self.assertTrue((self.workbench_dir / "deployment" / "decisions" / "source_freeze.md").exists())
        self.assertTrue((self.workbench_dir / "deployment" / "decisions" / "post_deploy_audit.md").exists())
        self.assertTrue((self.workbench_dir / "deployment" / "controls" / "release_manifest_review.md").exists())
        self.assertTrue((self.workbench_dir / "deployment" / "controls" / "production_http_controls.md").exists())
        self.assertTrue((self.workbench_dir / "deployment" / "controls" / "rollback_plan.md").exists())
        self.assertTrue((self.workbench_dir / "deployment" / "final_approval_template.md").exists())

        payload = json.loads((self.workbench_dir / "production_deployment_evidence_workbench.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["reviewed_source_hash"], "A" * 64)
        self.assertEqual(payload["release_bundle_sha256"], "")
        self.assertEqual(payload["reviewer"]["change_ticket"], "deployment/reviewer/change_ticket_template.md")
        self.assertEqual(
            payload["controls"]["release_manifest_sha256"],
            file_hash(self.workbench_dir / payload["controls"]["release_manifest_path"]),
        )
        self.assertEqual(
            payload["controls"]["production_http_controls_sha256"],
            file_hash(self.workbench_dir / payload["controls"]["production_http_controls_path"]),
        )

        check = json.loads((self.workbench_dir / "production_deployment_evidence_workbench_check.json").read_text(encoding="utf-8"))
        self.assertTrue(check["ok"])
        self.assertFalse(check["deployment_ready"])

        sums = (self.workbench_dir / "SHA256SUMS.txt").read_text(encoding="utf-8")
        self.assertIn("production_deployment_workbench_summary.json", sums)
        self.assertIn("production_deployment_evidence_workbench.json", sums)
        self.assertIn("deployment/reviewer/change_ticket_template.md", sums)
        self.assertIn("deployment/decisions/source_freeze.md", sums)
        self.assertIn("deployment/controls/release_manifest_review.md", sums)
        self.assertIn("deployment/controls/production_http_controls.md", sums)
        self.assertIn("deployment/final_approval_template.md", sums)
        for line in sums.splitlines():
            digest, rel = line.split("  ", 1)
            self.assertEqual(file_hash(self.workbench_dir / rel), digest)


if __name__ == "__main__":
    unittest.main()
