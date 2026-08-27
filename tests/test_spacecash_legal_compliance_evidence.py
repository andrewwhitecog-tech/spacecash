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
from tools.spacecash_genesis_allocation import genesis_allocation_template  # noqa: E402
from tools.spacecash_legal_compliance_evidence import (  # noqa: E402
    REQUIRED_REVIEW_AREAS,
    build_legal_compliance_workbench,
    file_hash,
    validate_legal_compliance_evidence,
    write_legal_compliance_evidence_template,
)


class LegalComplianceEvidenceTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.out_path = TMP_ROOT / f"test_spacecash_legal_compliance_evidence_{protocol.hash_text(id(self))[:12]}.json"
        self.workbench_dir = TMP_ROOT / f"test_spacecash_legal_workbench_{protocol.hash_text(id(self))[:12]}"

    def tearDown(self):
        if self.out_path.exists():
            self.out_path.unlink()
        if self.workbench_dir.exists():
            shutil.rmtree(self.workbench_dir)

    def complete_evidence(self):
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
            "decided_at": "2026-04-27T00:00:00Z",
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

    def test_legal_compliance_template_is_valid_but_not_ready(self):
        payload = write_legal_compliance_evidence_template(self.out_path)

        self.assertTrue(self.out_path.exists())
        disk = json.loads(self.out_path.read_text(encoding="utf-8"))
        self.assertEqual(disk, payload)
        self.assertEqual(payload["chain_id"], protocol.CHAIN_ID)
        self.assertEqual(len(payload["review_areas"]), len(REQUIRED_REVIEW_AREAS))

        result = validate_legal_compliance_evidence(payload)
        self.assertTrue(result["ok"])
        self.assertFalse(result["legal_compliance_ready"])
        self.assertIn("review_areas_not_approved", result["blockers"])
        self.assertIn("manual_gate_not_complete", result["blockers"])

    def test_complete_legal_compliance_evidence_passes_require_complete(self):
        result = validate_legal_compliance_evidence(self.complete_evidence(), require_complete=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["legal_compliance_ready"])
        self.assertEqual(result["approved_area_count"], len(REQUIRED_REVIEW_AREAS))
        self.assertEqual(result["blockers"], [])

    def test_require_complete_rejects_empty_template(self):
        result = validate_legal_compliance_evidence(write_legal_compliance_evidence_template(), require_complete=True)

        self.assertFalse(result["ok"])
        self.assertFalse(result["legal_compliance_ready"])
        self.assertIn("Legal/compliance evidence is not complete.", result["errors"])

    def test_template_allocation_hash_cannot_complete_legal_gate(self):
        payload = self.complete_evidence()
        payload["distribution"]["genesis_allocation_hash"] = genesis_allocation_template()["allocation_hash"]

        result = validate_legal_compliance_evidence(payload, require_complete=True)

        self.assertFalse(result["ok"])
        self.assertFalse(result["legal_compliance_ready"])
        self.assertIn("launch_allocation_not_approved", result["blockers"])

    def test_legal_compliance_workbench_writes_review_inputs_and_checksums(self):
        result = build_legal_compliance_workbench(
            out_dir=self.workbench_dir,
            reviewed_source_hash="A" * 64,
            force=True,
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["legal_compliance_ready"])
        self.assertEqual(result["manual_gate"]["status"], "not_complete")
        self.assertEqual(result["review_area_count"], len(REQUIRED_REVIEW_AREAS))
        self.assertIn("manual_gate_not_complete", result["blockers"])
        self.assertIn("review_areas_not_approved", result["blockers"])
        self.assertIn("release_bundle_sha256_missing", result["blockers"])
        self.assertIn("launch_allocation_not_approved", result["blockers"])

        self.assertTrue((self.workbench_dir / "README.md").exists())
        self.assertTrue((self.workbench_dir / "legal_compliance_workbench_summary.json").exists())
        self.assertTrue((self.workbench_dir / "legal_compliance_evidence_workbench.json").exists())
        self.assertTrue((self.workbench_dir / "legal_compliance_evidence_workbench_check.json").exists())
        self.assertTrue((self.workbench_dir / "legal" / "reviewer" / "engagement_letter_template.md").exists())
        self.assertTrue((self.workbench_dir / "legal" / "review_areas" / "token_payment_classification.md").exists())
        self.assertTrue((self.workbench_dir / "legal" / "review_areas" / "terms_of_service.md").exists())
        self.assertTrue((self.workbench_dir / "legal" / "documents" / "terms.md").exists())
        self.assertTrue((self.workbench_dir / "legal" / "documents" / "privacy_policy.md").exists())
        self.assertTrue((self.workbench_dir / "legal" / "distribution" / "allocation_verifier_output_placeholder.json").exists())
        self.assertTrue((self.workbench_dir / "legal" / "distribution" / "treasury_controls.md").exists())
        self.assertTrue((self.workbench_dir / "legal" / "final_decision_template.md").exists())

        payload = json.loads((self.workbench_dir / "legal_compliance_evidence_workbench.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["reviewed_source_hash"], "A" * 64)
        self.assertEqual(payload["release_bundle_sha256"], "")
        self.assertEqual(
            payload["reviewer"]["engagement_letter_sha256"],
            file_hash(self.workbench_dir / payload["reviewer"]["engagement_letter_path"]),
        )
        self.assertEqual(
            payload["documents"]["terms_sha256"],
            file_hash(self.workbench_dir / payload["documents"]["terms_path"]),
        )
        self.assertEqual(
            payload["distribution"]["treasury_controls_sha256"],
            file_hash(self.workbench_dir / payload["distribution"]["treasury_controls_path"]),
        )

        check = json.loads((self.workbench_dir / "legal_compliance_evidence_workbench_check.json").read_text(encoding="utf-8"))
        self.assertTrue(check["ok"])
        self.assertFalse(check["legal_compliance_ready"])

        sums = (self.workbench_dir / "SHA256SUMS.txt").read_text(encoding="utf-8")
        self.assertIn("legal_compliance_workbench_summary.json", sums)
        self.assertIn("legal_compliance_evidence_workbench.json", sums)
        self.assertIn("legal/review_areas/token_payment_classification.md", sums)
        self.assertIn("legal/reviewer/engagement_letter_template.md", sums)
        self.assertIn("legal/documents/terms.md", sums)
        self.assertIn("legal/distribution/treasury_controls.md", sums)
        for line in sums.splitlines():
            digest, rel = line.split("  ", 1)
            self.assertEqual(file_hash(self.workbench_dir / rel), digest)


if __name__ == "__main__":
    unittest.main()
