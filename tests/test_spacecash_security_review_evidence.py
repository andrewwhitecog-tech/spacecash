import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spacecash_core import protocol  # noqa: E402
from tests.test_spacecash_core import TMP_ROOT  # noqa: E402
from tools.spacecash_security_review_evidence import (  # noqa: E402
    REQUIRED_REVIEW_TOPICS,
    validate_security_review_evidence,
    write_security_review_evidence_template,
)


class SecurityReviewEvidenceTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.out_path = TMP_ROOT / f"test_spacecash_security_review_evidence_{protocol.hash_text(id(self))[:12]}.json"

    def tearDown(self):
        if self.out_path.exists():
            self.out_path.unlink()

    def complete_evidence(self):
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
            "closed_at": "2026-04-26T00:00:00Z",
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

    def test_security_review_template_is_valid_but_not_ready(self):
        payload = write_security_review_evidence_template(self.out_path)

        self.assertTrue(self.out_path.exists())
        disk = json.loads(self.out_path.read_text(encoding="utf-8"))
        self.assertEqual(disk, payload)
        self.assertEqual(payload["chain_id"], protocol.CHAIN_ID)
        self.assertEqual(len(payload["scope"]["topics"]), len(REQUIRED_REVIEW_TOPICS))

        result = validate_security_review_evidence(payload)
        self.assertTrue(result["ok"])
        self.assertFalse(result["external_security_review_ready"])
        self.assertIn("scope_topics_not_closed", result["blockers"])
        self.assertIn("manual_gate_not_complete", result["blockers"])

    def test_complete_security_review_evidence_passes_require_complete(self):
        result = validate_security_review_evidence(self.complete_evidence(), require_complete=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["external_security_review_ready"])
        self.assertEqual(result["reviewed_topic_count"], len(REQUIRED_REVIEW_TOPICS))
        self.assertEqual(result["critical_high_open_count"], 0)
        self.assertEqual(result["blockers"], [])

    def test_require_complete_rejects_empty_template(self):
        result = validate_security_review_evidence(write_security_review_evidence_template(), require_complete=True)

        self.assertFalse(result["ok"])
        self.assertFalse(result["external_security_review_ready"])
        self.assertIn("External security review evidence is not complete.", result["errors"])

    def test_open_high_finding_blocks_completion(self):
        payload = self.complete_evidence()
        payload["findings"][0]["status"] = "open"
        payload["remediation"]["all_critical_high_closed"] = False

        result = validate_security_review_evidence(payload, require_complete=True)

        self.assertFalse(result["ok"])
        self.assertFalse(result["external_security_review_ready"])
        self.assertIn("critical_high_findings_open", result["blockers"])
        self.assertIn("open_findings", result["blockers"])


if __name__ == "__main__":
    unittest.main()
