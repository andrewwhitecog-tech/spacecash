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
from tools.spacecash_wallet_custody_evidence import (  # noqa: E402
    REQUIRED_DECISIONS,
    build_wallet_custody_workbench,
    file_hash,
    validate_wallet_custody_evidence,
    write_wallet_custody_evidence_template,
)


class WalletCustodyEvidenceTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.out_path = TMP_ROOT / f"test_spacecash_wallet_custody_evidence_{protocol.hash_text(id(self))[:12]}.json"
        self.workbench_dir = TMP_ROOT / f"test_spacecash_wallet_workbench_{protocol.hash_text(id(self))[:12]}"

    def tearDown(self):
        if self.out_path.exists():
            self.out_path.unlink()
        if self.workbench_dir.exists():
            shutil.rmtree(self.workbench_dir)

    def complete_evidence(self):
        payload = write_wallet_custody_evidence_template()
        payload["status"] = "approved"
        payload["reviewed_source_hash"] = "A" * 64
        payload["release_bundle_sha256"] = "B" * 64
        payload["reviewer"] = {
            "name": "Wallet Reviewer",
            "role": "security_operations",
            "contact": "wallet-review@example.test",
            "reviewed_at": "2026-04-27T00:00:00Z",
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
            "approved_at": "2026-04-27T00:00:00Z",
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

    def test_wallet_custody_template_is_valid_but_not_ready(self):
        payload = write_wallet_custody_evidence_template(self.out_path)

        self.assertTrue(self.out_path.exists())
        disk = json.loads(self.out_path.read_text(encoding="utf-8"))
        self.assertEqual(disk, payload)
        self.assertEqual(payload["chain_id"], protocol.CHAIN_ID)
        self.assertEqual(payload["wallet_policy_hash"], protocol.wallet_policy_hash())
        self.assertEqual(len(payload["decisions"]), len(REQUIRED_DECISIONS))

        result = validate_wallet_custody_evidence(payload)
        self.assertTrue(result["ok"])
        self.assertFalse(result["wallet_custody_ready"])
        self.assertIn("wallet_decisions_not_approved", result["blockers"])
        self.assertIn("manual_gate_not_complete", result["blockers"])

    def test_complete_wallet_custody_evidence_passes_require_complete(self):
        result = validate_wallet_custody_evidence(self.complete_evidence(), require_complete=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["wallet_custody_ready"])
        self.assertEqual(result["approved_decision_count"], len(REQUIRED_DECISIONS))
        self.assertEqual(result["blockers"], [])

    def test_require_complete_rejects_empty_template(self):
        result = validate_wallet_custody_evidence(write_wallet_custody_evidence_template(), require_complete=True)

        self.assertFalse(result["ok"])
        self.assertFalse(result["wallet_custody_ready"])
        self.assertIn("Wallet recovery/custody evidence is not complete.", result["errors"])

    def test_server_private_key_storage_is_never_allowed(self):
        payload = self.complete_evidence()
        payload["final_approval"]["server_private_key_storage_allowed"] = True

        result = validate_wallet_custody_evidence(payload, require_complete=True)

        self.assertFalse(result["ok"])
        self.assertFalse(result["wallet_custody_ready"])
        self.assertIn("final_approval.server_private_key_storage_allowed must be false for this release boundary.", result["errors"])

    def test_wallet_custody_workbench_writes_review_inputs_and_checksums(self):
        result = build_wallet_custody_workbench(
            out_dir=self.workbench_dir,
            reviewed_source_hash="A" * 64,
            force=True,
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["wallet_custody_ready"])
        self.assertEqual(result["manual_gate"]["status"], "not_complete")
        self.assertEqual(result["decision_count"], len(REQUIRED_DECISIONS))
        self.assertIn("manual_gate_not_complete", result["blockers"])
        self.assertIn("wallet_decisions_not_approved", result["blockers"])
        self.assertIn("release_bundle_sha256_missing", result["blockers"])
        self.assertIn("final_approval_not_approved", result["blockers"])

        self.assertTrue((self.workbench_dir / "README.md").exists())
        self.assertTrue((self.workbench_dir / "wallet_custody_workbench_summary.json").exists())
        self.assertTrue((self.workbench_dir / "wallet_custody_evidence_workbench.json").exists())
        self.assertTrue((self.workbench_dir / "wallet_custody_evidence_workbench_check.json").exists())
        self.assertTrue((self.workbench_dir / "wallet" / "reviewer" / "review_ticket_template.md").exists())
        self.assertTrue((self.workbench_dir / "wallet" / "decisions" / "recovery_standard.md").exists())
        self.assertTrue((self.workbench_dir / "wallet" / "decisions" / "support_escalation.md").exists())
        self.assertTrue((self.workbench_dir / "wallet" / "controls" / "recovery_standard.md").exists())
        self.assertTrue((self.workbench_dir / "wallet" / "controls" / "private_key_handling_policy.md").exists())
        self.assertTrue((self.workbench_dir / "wallet" / "final_approval_template.md").exists())

        payload = json.loads((self.workbench_dir / "wallet_custody_evidence_workbench.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["reviewed_source_hash"], "A" * 64)
        self.assertEqual(payload["release_bundle_sha256"], "")
        self.assertEqual(payload["reviewer"]["engagement_or_ticket"], "wallet/reviewer/review_ticket_template.md")
        self.assertEqual(
            payload["controls"]["recovery_standard_sha256"],
            file_hash(self.workbench_dir / payload["controls"]["recovery_standard_path"]),
        )
        self.assertEqual(
            payload["controls"]["private_key_handling_policy_sha256"],
            file_hash(self.workbench_dir / payload["controls"]["private_key_handling_policy_path"]),
        )

        check = json.loads((self.workbench_dir / "wallet_custody_evidence_workbench_check.json").read_text(encoding="utf-8"))
        self.assertTrue(check["ok"])
        self.assertFalse(check["wallet_custody_ready"])

        sums = (self.workbench_dir / "SHA256SUMS.txt").read_text(encoding="utf-8")
        self.assertIn("wallet_custody_workbench_summary.json", sums)
        self.assertIn("wallet_custody_evidence_workbench.json", sums)
        self.assertIn("wallet/reviewer/review_ticket_template.md", sums)
        self.assertIn("wallet/decisions/recovery_standard.md", sums)
        self.assertIn("wallet/controls/recovery_standard.md", sums)
        self.assertIn("wallet/final_approval_template.md", sums)
        for line in sums.splitlines():
            digest, rel = line.split("  ", 1)
            self.assertEqual(file_hash(self.workbench_dir / rel), digest)


if __name__ == "__main__":
    unittest.main()
