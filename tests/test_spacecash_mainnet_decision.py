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
from tools.spacecash_genesis_allocation import allocation_hash, genesis_allocation_template  # noqa: E402
from tools.spacecash_gate_evidence import write_gate_evidence_template  # noqa: E402
from tools.spacecash_legal_compliance_evidence import write_legal_compliance_evidence_template  # noqa: E402
from tools.spacecash_mainnet_decision import (  # noqa: E402
    build_mainnet_decision_workbench,
    file_hash,
    validate_mainnet_decision,
    write_mainnet_decision_template,
)
from tools.spacecash_production_deployment_evidence import write_production_deployment_evidence_template  # noqa: E402
from tools.spacecash_public_testnet_evidence import REQUIRED_NODE_REPORTS, write_public_testnet_evidence_template  # noqa: E402
from tools.spacecash_security_review_evidence import write_security_review_evidence_template  # noqa: E402
from tools.spacecash_wallet_custody_evidence import write_wallet_custody_evidence_template  # noqa: E402


class MainnetDecisionTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.out_dir = TMP_ROOT / f"test_spacecash_mainnet_decision_{protocol.hash_text(id(self))[:12]}"
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.out_dir.exists():
            shutil.rmtree(self.out_dir)

    def write_json(self, name, payload):
        path = self.out_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def checksum_manifest(self, dirname):
        folder = self.out_dir / dirname
        folder.mkdir(parents=True, exist_ok=True)
        payload = folder / "artifact.txt"
        payload.write_text(f"{dirname} artifact\n", encoding="utf-8")
        digest = file_hash(payload)
        sums = folder / "SHA256SUMS.txt"
        sums.write_text(f"{digest}  artifact.txt\n", encoding="utf-8")
        return sums

    def approved_allocation(self):
        payload = genesis_allocation_template()
        payload["status"] = "approved"
        payload["allocations"] = [{
            "address": "SPACE-UNITTEST01",
            "amount_units": protocol.GENESIS_UNITS,
            "label": "Unit Test Supply",
            "basis": "Unit-test approved launch allocation.",
            "reviewer": "Test Counsel",
        }]
        payload["approval"] = {
            "approved": True,
            "approved_by": "Test Counsel",
            "approved_at": "2026-04-29T00:00:00Z",
            "reviewed_source_hash": "A" * 64,
            "notes": "Unit-test allocation approval fixture.",
        }
        payload["manual_gate"] = {
            "id": "legal_compliance_review_complete",
            "status": "complete",
            "reason": "Unit-test legal/compliance approval fixture.",
        }
        payload["allocation_hash"] = allocation_hash(payload)
        return payload

    def complete_manual_gate_evidence(self):
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
                "reviewed_at": "2026-04-29T00:00:00Z",
                "decision": "approved",
                "notes": "Unit-test approval fixture.",
            }
        return payload

    def complete_public_testnet_evidence(self):
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
            "reviewed_at": "2026-04-29T00:00:00Z",
            "decision": "approved",
            "notes": "Unit-test approval fixture.",
        }
        payload["manual_gate"] = {
            "id": "public_testnet_complete",
            "status": "complete",
            "reason": "Unit-test approval fixture.",
        }
        return payload

    def complete_security_review_evidence(self):
        payload = write_security_review_evidence_template()
        payload["status"] = "closed"
        payload["reviewed_source_hash"] = "A" * 64
        payload["security_packet_sha256"] = "B" * 64
        payload["auditor"] = {
            "name": "Test Auditor",
            "firm": "Independent Security Lab",
            "contact": "auditor@example.test",
            "independence_statement": "No financial interest in SpaceCash.",
            "signed_scope_path": "audit/signed_scope.pdf",
            "signed_scope_sha256": "C" * 64,
        }
        for topic in payload["scope"]["topics"]:
            topic["status"] = "pass"
            topic["reviewer"] = "Test Auditor"
            topic["evidence"] = f"audit/topics/{topic['id']}.md"
            topic["notes"] = "Reviewed in unit-test fixture."
        payload["findings"] = [{
            "id": "SCAUD-001",
            "severity": "high",
            "component": "daemon_exposure",
            "summary": "Unit-test finding fixture.",
            "status": "closed",
            "remediation": "Documented hardening requirement before public deployment.",
            "closure_evidence": "audit/findings/SCAUD-001-closure.md",
            "accepted_risk_justification": "",
        }]
        payload["remediation"] = {
            "all_critical_high_closed": True,
            "reviewed_remediation_hash": "D" * 64,
            "evidence_paths": ["audit/findings/SCAUD-001-closure.md"],
            "notes": "Unit-test remediation fixture.",
        }
        payload["closure"] = {
            "status": "closed",
            "closed_at": "2026-04-29T00:00:00Z",
            "auditor_statement": "The reviewed fixture is approved for release gates.",
            "approved_for_release": True,
            "accepted_risks": [],
        }
        payload["manual_gate"] = {
            "id": "external_security_review_complete",
            "status": "complete",
            "reason": "Unit-test closure fixture.",
        }
        return payload

    def complete_legal_compliance_evidence(self):
        payload = write_legal_compliance_evidence_template()
        payload["status"] = "approved"
        payload["reviewed_source_hash"] = "A" * 64
        payload["release_bundle_sha256"] = "B" * 64
        payload["reviewer"] = {
            "name": "Test Counsel",
            "firm": "Independent Legal Review LLP",
            "contact": "counsel@example.test",
            "role": "outside_counsel",
            "engagement_letter_path": "legal/engagement-letter.pdf",
            "engagement_letter_sha256": "C" * 64,
        }
        payload["scope"] = {
            "intended_use_cases": ["closed-loop product payments"],
            "prohibited_use_cases": ["investment marketing", "legal tender claims"],
            "allowed_jurisdictions": ["test jurisdiction"],
            "blocked_jurisdictions": ["unsupported jurisdiction"],
            "product_payment_reviewed": True,
            "public_distribution_reviewed": True,
            "treasury_controls_reviewed": True,
        }
        for area in payload["review_areas"]:
            area["status"] = "approved"
            area["reviewer"] = "Test Counsel"
            area["evidence"] = f"legal/review/{area['id']}.md"
            area["decision"] = "approved"
            area["notes"] = "Unit-test approval fixture."
        payload["documents"] = {
            "approved_use_case": "legal/approved-use-case.md",
            "prohibited_use_cases": "legal/prohibited-use-cases.md",
            "required_disclosures": "legal/disclosures.md",
            "required_operational_controls": "legal/operational-controls.md",
            "terms_path": "legal/terms.md",
            "terms_sha256": "D" * 64,
            "privacy_policy_path": "legal/privacy.md",
            "privacy_policy_sha256": "E" * 64,
            "refund_policy_path": "legal/refunds.md",
            "refund_policy_sha256": "F" * 64,
            "restricted_product_policy_path": "legal/restricted-products.md",
            "restricted_product_policy_sha256": "1" * 64,
            "tax_position_path": "legal/tax-position.md",
            "tax_position_sha256": "2" * 64,
        }
        payload["distribution"] = {
            "genesis_allocation_hash": "3" * 64,
            "allocation_verifier_output_path": "legal/allocation-verifier-output.json",
            "allocation_verifier_output_sha256": "4" * 64,
            "treasury_controls_path": "legal/treasury-controls.md",
            "treasury_controls_sha256": "5" * 64,
            "fee_policy_path": "legal/fee-policy.md",
            "fee_policy_sha256": "6" * 64,
        }
        payload["final_decision"] = {
            "decision": "approved",
            "decided_at": "2026-04-29T00:00:00Z",
            "reviewer_statement": "Unit-test legal/compliance approval fixture.",
            "conditions": [],
            "no_investment_claims_confirmed": True,
            "no_legal_tender_claims_confirmed": True,
            "no_exchange_listing_claims_confirmed": True,
            "real_money_use_authorized": True,
        }
        payload["manual_gate"] = {
            "id": "legal_compliance_review_complete",
            "status": "complete",
            "reason": "Unit-test legal/compliance approval fixture.",
        }
        return payload

    def complete_wallet_custody_evidence(self):
        payload = write_wallet_custody_evidence_template()
        payload["status"] = "approved"
        payload["reviewed_source_hash"] = "A" * 64
        payload["release_bundle_sha256"] = "B" * 64
        payload["reviewer"] = {
            "name": "Wallet Reviewer",
            "role": "security_operations",
            "contact": "wallet-review@example.test",
            "reviewed_at": "2026-04-29T00:00:00Z",
            "engagement_or_ticket": "WALLET-REVIEW-001",
        }
        for decision in payload["decisions"]:
            decision["status"] = "approved"
            decision["reviewer"] = "Wallet Reviewer"
            decision["evidence"] = f"wallet/{decision['id']}.md"
            decision["notes"] = "Unit-test approval fixture."
        payload["controls"] = {
            "recovery_standard_path": "wallet/recovery-standard.md",
            "recovery_standard_sha256": "C" * 64,
            "address_versioning_path": "wallet/address-versioning.md",
            "address_versioning_sha256": "D" * 64,
            "backup_rotation_path": "wallet/backup-rotation.md",
            "backup_rotation_sha256": "E" * 64,
            "lost_key_procedure_path": "wallet/lost-key.md",
            "lost_key_procedure_sha256": "F" * 64,
            "compromised_key_procedure_path": "wallet/compromised-key.md",
            "compromised_key_procedure_sha256": "1" * 64,
            "hardware_or_custody_plan_path": "wallet/hardware-custody.md",
            "hardware_or_custody_plan_sha256": "2" * 64,
            "backup_verification_flow_path": "wallet/backup-verification.md",
            "backup_verification_flow_sha256": "3" * 64,
            "private_key_handling_policy_path": "wallet/private-key-handling.md",
            "private_key_handling_policy_sha256": "4" * 64,
        }
        payload["final_approval"] = {
            "approved": True,
            "approved_at": "2026-04-29T00:00:00Z",
            "approver": "Wallet Reviewer",
            "statement": "Unit-test wallet/custody approval fixture.",
            "server_private_key_storage_allowed": False,
            "custodial_operations_allowed": False,
            "development_keys_excluded": True,
            "lost_key_warning_approved": True,
            "backup_passphrase_warning_approved": True,
        }
        payload["manual_gate"] = {
            "id": "wallet_recovery_custody_policy_complete",
            "status": "complete",
            "reason": "Unit-test wallet/custody approval fixture.",
        }
        return payload

    def complete_production_deployment_evidence(self):
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

    def complete_decision(self):
        source_hash = "A" * 64
        artifacts = {
            "release_manifest": self.write_json("release_manifest.json", {
                "chain_id": protocol.CHAIN_ID,
                "checks": {"units": {"ok": True}},
                "checks_ok": True,
                "source_hash": source_hash,
            }),
            "release_bundle_sha256s": self.checksum_manifest("release_bundle"),
            "security_review_packet_sha256s": self.checksum_manifest("security_review_packet"),
            "genesis_allocation": self.write_json("genesis_allocation.json", self.approved_allocation()),
            "manual_gate_evidence": self.write_json("manual_gate_evidence.json", self.complete_manual_gate_evidence()),
            "public_testnet_evidence": self.write_json("public_testnet_evidence.json", self.complete_public_testnet_evidence()),
            "security_review_evidence": self.write_json("security_review_evidence.json", self.complete_security_review_evidence()),
            "legal_compliance_evidence": self.write_json("legal_compliance_evidence.json", self.complete_legal_compliance_evidence()),
            "wallet_custody_evidence": self.write_json("wallet_custody_evidence.json", self.complete_wallet_custody_evidence()),
            "production_deployment_evidence": self.write_json("production_deployment_evidence.json", self.complete_production_deployment_evidence()),
        }
        payload = write_mainnet_decision_template()
        payload["status"] = "approved"
        payload["reviewed_source_hash"] = source_hash
        payload["launch_authorization"] = {
            "approved": True,
            "approver": "Release Manager",
            "approved_at": "2026-04-29T00:00:00Z",
            "statement": "Unit-test mainnet decision approval fixture.",
            "conditions": [],
        }
        for artifact_id, path in artifacts.items():
            payload["artifacts"][artifact_id]["path"] = str(path)
            payload["artifacts"][artifact_id]["sha256"] = file_hash(path)
            payload["artifacts"][artifact_id]["exists"] = True
        return payload

    def test_template_is_valid_but_not_ready(self):
        out_path = self.out_dir / "mainnet_decision_template.json"
        payload = write_mainnet_decision_template(out_path)

        self.assertTrue(out_path.exists())
        self.assertEqual(json.loads(out_path.read_text(encoding="utf-8")), payload)
        self.assertEqual(payload["chain_id"], protocol.CHAIN_ID)

        result = validate_mainnet_decision(payload)
        self.assertTrue(result["ok"])
        self.assertFalse(result["mainnet_decision_ready"])
        self.assertIn("reviewed_source_hash_missing", result["blockers"])
        self.assertIn("launch_authorization_not_approved", result["blockers"])

    def test_complete_decision_passes_require_complete(self):
        result = validate_mainnet_decision(self.complete_decision(), require_complete=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["mainnet_decision_ready"])
        self.assertEqual(result["complete_gate_count"], result["required_gate_count"])
        self.assertEqual(result["blockers"], [])

    def test_require_complete_rejects_empty_template(self):
        result = validate_mainnet_decision(write_mainnet_decision_template(), require_complete=True)

        self.assertFalse(result["ok"])
        self.assertFalse(result["mainnet_decision_ready"])
        self.assertIn("Mainnet decision evidence is not complete.", result["errors"])

    def test_build_mainnet_decision_workbench_writes_blocked_review_packet(self):
        workbench_dir = self.out_dir / "mainnet_decision_workbench"
        artifact_paths = {
            "release_manifest": self.out_dir / "missing_release_manifest.json",
            "release_bundle_sha256s": self.out_dir / "missing_release_bundle" / "SHA256SUMS.txt",
            "security_review_packet_sha256s": self.out_dir / "missing_security_packet" / "SHA256SUMS.txt",
            "genesis_allocation": self.out_dir / "missing_genesis_allocation.json",
            "manual_gate_evidence": self.out_dir / "missing_manual_gate_evidence.json",
            "public_testnet_evidence": self.out_dir / "missing_public_testnet_evidence.json",
            "security_review_evidence": self.out_dir / "missing_security_review_evidence.json",
            "legal_compliance_evidence": self.out_dir / "missing_legal_compliance_evidence.json",
            "wallet_custody_evidence": self.out_dir / "missing_wallet_custody_evidence.json",
            "production_deployment_evidence": self.out_dir / "missing_production_deployment_evidence.json",
        }

        summary = build_mainnet_decision_workbench(
            out_dir=workbench_dir,
            reviewed_source_hash="A" * 64,
            artifact_paths=artifact_paths,
            force=True,
        )

        self.assertTrue(summary["ok"])
        self.assertFalse(summary["mainnet_decision_ready"])
        self.assertEqual(summary["manual_gate"]["status"], "not_complete")
        self.assertEqual(summary["reviewed_source_hash"], "A" * 64)
        self.assertIn("launch_authorization_not_approved", summary["blockers"])
        self.assertIn("release_manifest_file_missing", summary["blockers"])
        self.assertTrue((workbench_dir / "README.md").exists())
        self.assertTrue((workbench_dir / "mainnet_decision_workbench_summary.json").exists())
        self.assertTrue((workbench_dir / "mainnet_decision_workbench.json").exists())
        self.assertTrue((workbench_dir / "mainnet_decision_workbench_check.json").exists())
        self.assertTrue((workbench_dir / "decision" / "artifacts" / "release_manifest.md").exists())
        self.assertTrue((workbench_dir / "decision" / "artifacts" / "production_deployment_evidence.md").exists())
        self.assertTrue((workbench_dir / "decision" / "gates" / "production_deployment_runbook_complete.md").exists())
        self.assertTrue((workbench_dir / "decision" / "checksums" / "release_bundle_sha256s_review.md").exists())
        self.assertTrue((workbench_dir / "decision" / "reviewer" / "source_freeze_template.md").exists())
        self.assertTrue((workbench_dir / "decision" / "reviewer" / "final_launch_authorization_template.md").exists())
        sums = (workbench_dir / "SHA256SUMS.txt").read_text(encoding="utf-8")
        self.assertIn("mainnet_decision_workbench_summary.json", sums)
        self.assertIn("mainnet_decision_workbench.json", sums)
        self.assertIn("decision/artifacts/release_manifest.md", sums)
        for line in sums.splitlines():
            digest, rel = line.split("  ", 1)
            self.assertEqual(file_hash(workbench_dir / rel), digest)


if __name__ == "__main__":
    unittest.main()
