"""Create and verify SpaceCash wallet recovery/custody approval evidence."""

import argparse
import hashlib
import json
import re
import secrets
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = Path(__file__).resolve().parent
for candidate in (ROOT, TOOLS_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from spacecash_core import protocol  # noqa: E402


EVIDENCE_MODE = "spacecash-wallet-recovery-custody-evidence-v1"
EVIDENCE_VERSION = 1
HASH_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
STATUS_VALUES = ("not_started", "in_review", "blocked", "approved")
DECISION_STATUSES = ("not_reviewed", "approved", "approved_with_conditions", "blocked", "not_applicable")
READY_DECISION_STATUSES = ("approved", "approved_with_conditions", "not_applicable")

REQUIRED_DECISIONS = (
    {"id": "recovery_standard", "title": "Recovery Phrase Or Deterministic Recovery Standard"},
    {"id": "address_versioning", "title": "Address Versioning And Migration Boundary"},
    {"id": "backup_rotation", "title": "Encrypted Backup Rotation Policy"},
    {"id": "lost_key_procedure", "title": "Lost-Key Procedure And User Warning"},
    {"id": "compromised_key_procedure", "title": "Compromised-Key Procedure"},
    {"id": "hardware_wallet_or_custody", "title": "Hardware Wallet Or Custody Position"},
    {"id": "user_backup_verification", "title": "User Backup Verification Flow"},
    {"id": "private_key_handling", "title": "Private-Key Handling And Logging Boundary"},
    {"id": "development_key_exclusion", "title": "Development Candidate Key Exclusion"},
    {"id": "support_escalation", "title": "Support Escalation And Irrecoverable-Loss Messaging"},
)

REQUIRED_CONTROL_FIELDS = (
    "recovery_standard_path",
    "address_versioning_path",
    "backup_rotation_path",
    "lost_key_procedure_path",
    "compromised_key_procedure_path",
    "hardware_or_custody_plan_path",
    "backup_verification_flow_path",
    "private_key_handling_policy_path",
)

CONTROL_WORKPAPERS = {
    "recovery_standard_path": ("wallet/controls/recovery_standard.md", "Recovery Standard"),
    "address_versioning_path": ("wallet/controls/address_versioning.md", "Address Versioning"),
    "backup_rotation_path": ("wallet/controls/backup_rotation.md", "Backup Rotation"),
    "lost_key_procedure_path": ("wallet/controls/lost_key_procedure.md", "Lost-Key Procedure"),
    "compromised_key_procedure_path": ("wallet/controls/compromised_key_procedure.md", "Compromised-Key Procedure"),
    "hardware_or_custody_plan_path": ("wallet/controls/hardware_or_custody_plan.md", "Hardware Or Custody Plan"),
    "backup_verification_flow_path": ("wallet/controls/backup_verification_flow.md", "Backup Verification Flow"),
    "private_key_handling_policy_path": ("wallet/controls/private_key_handling_policy.md", "Private-Key Handling Policy"),
}

DECISION_QUESTIONS = {
    "recovery_standard": [
        "What recovery standard is approved for production wallets?",
        "What user-facing backup warning must ship before real-money use?",
    ],
    "address_versioning": [
        "Does the address format make chain and version boundaries explicit enough for migration?",
        "What migration or replay warnings are required before launch?",
    ],
    "backup_rotation": [
        "When must users rotate encrypted wallet backups?",
        "What backup retention and stale-backup warnings are required?",
    ],
    "lost_key_procedure": [
        "How is permanent loss of access explained to users?",
        "What support response is allowed when a user loses keys?",
    ],
    "compromised_key_procedure": [
        "What operator and user actions are required after suspected key compromise?",
        "What can and cannot be reversed by support?",
    ],
    "hardware_wallet_or_custody": [
        "Is hardware-wallet support required before launch?",
        "Are custodial operations explicitly out of scope for this release?",
    ],
    "user_backup_verification": [
        "How does the user prove a backup is usable before relying on it?",
        "Where are backup verification warnings displayed?",
    ],
    "private_key_handling": [
        "Can any server route, log, report, bundle, or support workflow expose private keys?",
        "What tests or reviewer checks prove development keys are excluded by default?",
    ],
    "development_key_exclusion": [
        "Are generated candidate keys excluded from normal release and testnet bundles?",
        "Are any explicit development key exports labeled unsafe for custody?",
    ],
    "support_escalation": [
        "What support escalation text is approved for lost keys and compromised backups?",
        "What records should support retain without collecting private keys?",
    ],
}


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def default_workbench_dir():
    stamp = protocol.utc_now().replace(":", "").replace("-", "").replace("Z", "Z")
    return ROOT / "_tmp" / f"spacecash_wallet_custody_workbench_{stamp}_{secrets.token_hex(4)}"


def safe_reset_dir(path):
    path = Path(path).resolve()
    tmp_root = (ROOT / "_tmp").resolve()
    if path == tmp_root or tmp_root not in path.parents:
        raise ValueError("Refusing to overwrite a wallet custody workbench outside the project _tmp directory.")
    if path.exists():
        shutil.rmtree(path)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _hash_relative(out_dir, rel):
    return file_hash(Path(out_dir) / rel)


def _non_empty(value):
    return isinstance(value, str) and bool(value.strip())


def _artifact(rel):
    path = ROOT / rel
    return {
        "path": rel,
        "exists": path.exists(),
        "sha256": file_hash(path) if path.exists() else "",
    }


def _default_artifacts():
    return [
        _artifact("docs/spacecash/WALLET_RECOVERY_CUSTODY_POLICY.md"),
        _artifact("docs/spacecash/MAINNET_GATE.md"),
        _artifact("docs/spacecash/THREAT_MODEL.md"),
    ]


def _empty_decision(definition):
    return {
        "id": definition["id"],
        "title": definition["title"],
        "status": "not_reviewed",
        "reviewer": "",
        "evidence": "",
        "notes": "",
    }


def wallet_custody_evidence_template():
    return {
        "mode": EVIDENCE_MODE,
        "version": EVIDENCE_VERSION,
        "chain_id": protocol.CHAIN_ID,
        "status": "not_started",
        "reviewed_source_hash": "",
        "release_bundle_sha256": "",
        "wallet_policy_hash": protocol.wallet_policy_hash(),
        "artifacts": _default_artifacts(),
        "reviewer": {
            "name": "",
            "role": "",
            "contact": "",
            "reviewed_at": "",
            "engagement_or_ticket": "",
        },
        "decisions": [_empty_decision(definition) for definition in REQUIRED_DECISIONS],
        "controls": {
            "recovery_standard_path": "",
            "recovery_standard_sha256": "",
            "address_versioning_path": "",
            "address_versioning_sha256": "",
            "backup_rotation_path": "",
            "backup_rotation_sha256": "",
            "lost_key_procedure_path": "",
            "lost_key_procedure_sha256": "",
            "compromised_key_procedure_path": "",
            "compromised_key_procedure_sha256": "",
            "hardware_or_custody_plan_path": "",
            "hardware_or_custody_plan_sha256": "",
            "backup_verification_flow_path": "",
            "backup_verification_flow_sha256": "",
            "private_key_handling_policy_path": "",
            "private_key_handling_policy_sha256": "",
        },
        "final_approval": {
            "approved": False,
            "approved_at": "",
            "approver": "",
            "statement": "",
            "server_private_key_storage_allowed": False,
            "custodial_operations_allowed": False,
            "development_keys_excluded": False,
            "lost_key_warning_approved": False,
            "backup_passphrase_warning_approved": False,
        },
        "manual_gate": {
            "id": "wallet_recovery_custody_policy_complete",
            "status": "not_complete",
            "reason": "Recovery standard, address versioning, backup rotation, lost-key and compromised-key procedures, and custody posture require approval.",
        },
    }


def _validate_artifacts(artifacts, errors, warnings):
    if not isinstance(artifacts, list):
        errors.append("artifacts must be a list.")
        return []
    verified = []
    for index, artifact in enumerate(artifacts):
        prefix = f"artifacts[{index}]"
        if not isinstance(artifact, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        rel = artifact.get("path")
        if not _non_empty(rel):
            errors.append(f"{prefix}.path is required.")
            continue
        path = ROOT / rel
        exists = path.exists()
        claimed = str(artifact.get("sha256") or "").strip().upper()
        if artifact.get("exists") is True and not exists:
            errors.append(f"{prefix}.exists is true but the file is missing.")
        if exists and claimed:
            actual = file_hash(path)
            if actual != claimed:
                errors.append(f"{prefix}.sha256 does not match {rel}.")
            else:
                verified.append(rel)
        elif not exists:
            warnings.append(f"{rel} is not present yet.")
    return verified


def _validate_reviewer(reviewer, errors, blockers, require_complete):
    if not isinstance(reviewer, dict):
        errors.append("reviewer must be an object.")
        reviewer = {}
    required = ("name", "role", "contact", "reviewed_at", "engagement_or_ticket")
    missing = [field for field in required if not _non_empty(reviewer.get(field))]
    if missing:
        blockers.append("reviewer_missing")
        if require_complete:
            errors.append(f"reviewer missing required fields: {', '.join(missing)}.")


def _validate_decisions(decisions, errors, blockers, require_complete):
    if not isinstance(decisions, list):
        errors.append("decisions must be a list.")
        decisions = []
    required = {decision["id"]: decision for decision in REQUIRED_DECISIONS}
    by_id = {}
    ready = []
    for index, decision in enumerate(decisions):
        prefix = f"decisions[{index}]"
        if not isinstance(decision, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        decision_id = decision.get("id")
        if decision_id not in required:
            errors.append(f"{prefix}.id is not a required wallet/custody decision.")
            continue
        if decision_id in by_id:
            errors.append(f"{prefix}.id duplicates an earlier wallet/custody decision.")
            continue
        by_id[decision_id] = decision
        if decision.get("title") != required[decision_id]["title"]:
            errors.append(f"{decision_id}.title does not match the v1 wallet/custody schema.")
        if decision.get("status") not in DECISION_STATUSES:
            errors.append(f"{decision_id}.status must be one of {', '.join(DECISION_STATUSES)}.")
        if decision.get("status") == "blocked":
            blockers.append(f"{decision_id}_blocked")
        if decision.get("status") in READY_DECISION_STATUSES:
            ready.append(decision_id)
        if require_complete or decision.get("status") in READY_DECISION_STATUSES + ("blocked",):
            if not _non_empty(decision.get("reviewer")):
                errors.append(f"{decision_id}.reviewer is required.")
            if not _non_empty(decision.get("evidence")):
                errors.append(f"{decision_id}.evidence is required.")
    for decision_id in required:
        if decision_id not in by_id:
            errors.append(f"Missing wallet/custody decision {decision_id}.")
            blockers.append(f"{decision_id}_missing")
        elif by_id[decision_id].get("status") not in READY_DECISION_STATUSES:
            blockers.append(f"{decision_id}_not_approved")
    if len(ready) < len(required):
        blockers.append("wallet_decisions_not_approved")
    return ready


def _validate_controls(controls, errors, blockers, require_complete):
    if not isinstance(controls, dict):
        errors.append("controls must be an object.")
        controls = {}
    for field in REQUIRED_CONTROL_FIELDS:
        if not _non_empty(controls.get(field)):
            blockers.append(f"{field}_missing")
            if require_complete:
                errors.append(f"controls.{field} is required.")
    for field, value in controls.items():
        if field.endswith("_sha256") and value and not HASH_RE.fullmatch(str(value).strip()):
            errors.append(f"controls.{field} must be a 64-character SHA-256 hash.")
    if require_complete:
        for field in REQUIRED_CONTROL_FIELDS:
            hash_field = field.replace("_path", "_sha256")
            if _non_empty(controls.get(field)) and not _non_empty(controls.get(hash_field)):
                errors.append(f"controls.{hash_field} is required when {field} is set.")


def _validate_final_approval(final_approval, errors, blockers, require_complete):
    if not isinstance(final_approval, dict):
        errors.append("final_approval must be an object.")
        final_approval = {}
    if final_approval.get("approved") is not True:
        blockers.append("final_approval_not_approved")
        if require_complete:
            errors.append("final_approval.approved must be true.")
    for field in ("approved_at", "approver", "statement"):
        if not _non_empty(final_approval.get(field)):
            blockers.append(f"final_approval_{field}_missing")
            if require_complete:
                errors.append(f"final_approval.{field} is required.")
    if final_approval.get("server_private_key_storage_allowed") is not False:
        errors.append("final_approval.server_private_key_storage_allowed must be false for this release boundary.")
    if final_approval.get("custodial_operations_allowed") is not False:
        errors.append("final_approval.custodial_operations_allowed must be false for this release boundary.")
    for field in ("development_keys_excluded", "lost_key_warning_approved", "backup_passphrase_warning_approved"):
        if final_approval.get(field) is not True:
            blockers.append(f"{field}_not_confirmed")
            if require_complete:
                errors.append(f"final_approval.{field} must be true.")


def validate_wallet_custody_evidence(data, require_complete=False):
    errors = []
    warnings = []
    blockers = []

    if not isinstance(data, dict):
        return {
            "ok": False,
            "wallet_custody_ready": False,
            "errors": ["Wallet custody evidence must be a JSON object."],
            "warnings": [],
            "blockers": ["schema"],
        }

    if data.get("mode") != EVIDENCE_MODE:
        errors.append(f"mode must equal {EVIDENCE_MODE!r}.")
    if data.get("version") != EVIDENCE_VERSION:
        errors.append(f"version must equal {EVIDENCE_VERSION}.")
    if data.get("chain_id") != protocol.CHAIN_ID:
        errors.append(f"chain_id must equal {protocol.CHAIN_ID!r}.")
    if data.get("status") not in STATUS_VALUES:
        errors.append(f"status must be one of {', '.join(STATUS_VALUES)}.")
    if data.get("wallet_policy_hash") != protocol.wallet_policy_hash():
        errors.append(f"wallet_policy_hash must equal {protocol.wallet_policy_hash()}.")

    for field in ("reviewed_source_hash", "release_bundle_sha256"):
        value = str(data.get(field) or "").strip()
        if not value:
            blockers.append(f"{field}_missing")
            if require_complete:
                errors.append(f"{field} is required.")
        elif not HASH_RE.fullmatch(value):
            errors.append(f"{field} must be a 64-character SHA-256 hash.")

    verified_artifacts = _validate_artifacts(data.get("artifacts") or [], errors, warnings)
    _validate_reviewer(data.get("reviewer"), errors, blockers, require_complete)
    approved_decisions = _validate_decisions(data.get("decisions") or [], errors, blockers, require_complete)
    _validate_controls(data.get("controls"), errors, blockers, require_complete)
    _validate_final_approval(data.get("final_approval"), errors, blockers, require_complete)

    manual_gate = data.get("manual_gate") if isinstance(data.get("manual_gate"), dict) else {}
    manual_gate_complete = (
        manual_gate.get("id") == "wallet_recovery_custody_policy_complete"
        and manual_gate.get("status") == "complete"
    )
    if not manual_gate_complete:
        blockers.append("manual_gate_not_complete")
        if require_complete:
            errors.append("manual_gate wallet_recovery_custody_policy_complete must be complete.")

    if require_complete or data.get("status") == "approved":
        if data.get("status") != "approved":
            errors.append("status must be approved for wallet/custody completion.")

    blockers = sorted(set(blockers))
    wallet_custody_ready = bool(
        not errors
        and not blockers
        and data.get("status") == "approved"
        and manual_gate_complete
    )
    if require_complete and not wallet_custody_ready:
        errors.append("Wallet recovery/custody evidence is not complete.")

    return {
        "ok": not errors,
        "wallet_custody_ready": wallet_custody_ready,
        "mode": EVIDENCE_MODE,
        "chain_id": data.get("chain_id"),
        "status": data.get("status"),
        "approved_decision_count": len(approved_decisions),
        "required_decision_count": len(REQUIRED_DECISIONS),
        "verified_artifacts": verified_artifacts,
        "blockers": blockers,
        "manual_gate_status": manual_gate.get("status"),
        "errors": errors,
        "warnings": warnings,
    }


def write_wallet_custody_workpapers(out_dir):
    decision_paths = []
    for definition in REQUIRED_DECISIONS:
        decision_id = definition["id"]
        path = Path("wallet") / "decisions" / f"{decision_id}.md"
        questions = "\n".join(f"- [ ] {question}" for question in DECISION_QUESTIONS.get(decision_id, []))
        write_text(out_dir / path, "\n".join([
            f"# SpaceCash Wallet/Custody Decision: {definition['title']}",
            "",
            f"- Decision ID: `{decision_id}`",
            "- Status: `not_reviewed`",
            "- Reviewer:",
            "- Reviewed at:",
            "",
            "## Review Questions",
            "",
            questions,
            "",
            "## Evidence Reviewed",
            "",
            "- Source hash:",
            "- Release bundle SHA256:",
            "- Wallet policy hash:",
            "- Files reviewed:",
            "",
            "## Decision Notes",
            "",
            "- Decision: `not_reviewed`",
            "- Conditions:",
            "- User-facing copy changes:",
            "- Operational-control changes:",
            "",
        ]))
        decision_paths.append(path.as_posix())

    control_paths = {}
    for field, (rel, title) in CONTROL_WORKPAPERS.items():
        write_text(out_dir / rel, "\n".join([
            f"# SpaceCash {title}",
            "",
            "Draft input for wallet recovery/custody review. This is not approval.",
            "",
            "## Current Position",
            "",
            "- Draft control:",
            "- Owner:",
            "- Evidence location:",
            "",
            "## Required User Warning",
            "",
            "",
            "## Required Operator Procedure",
            "",
            "",
            "## Reviewer Notes",
            "",
            "- Required changes:",
            "- Hash after final edits:",
            "",
        ]))
        control_paths[field] = rel

    reviewer_ticket_path = Path("wallet") / "reviewer" / "review_ticket_template.md"
    write_text(out_dir / reviewer_ticket_path, "\n".join([
        "# SpaceCash Wallet/Custody Review Ticket Template",
        "",
        "- Reviewer name:",
        "- Role:",
        "- Contact:",
        "- Reviewed at:",
        "- Reviewed source hash:",
        "- Release bundle SHA256:",
        "- Wallet policy hash:",
        "",
        "## Scope Acceptance",
        "",
        "The reviewer accepts the wallet recovery/custody scope in",
        "`docs/spacecash/WALLET_RECOVERY_CUSTODY_POLICY.md` and the workpapers in this package.",
        "",
        "## Review Boundary",
        "",
        "- Server private-key storage allowed: `false`",
        "- Custodial operations allowed: `false`",
        "- Development keys excluded from release/testnet bundles: `pending`",
        "",
    ]))

    final_approval_path = Path("wallet") / "final_approval_template.md"
    write_text(out_dir / final_approval_path, "\n".join([
        "# SpaceCash Wallet/Custody Final Approval Template",
        "",
        "- Approved: `false`",
        "- Approved at:",
        "- Approver:",
        "- Reviewed source hash:",
        "- Release bundle SHA256:",
        "",
        "## Required Confirmations",
        "",
        "- [ ] Server private-key storage remains disallowed.",
        "- [ ] Custodial operations remain disallowed for this release boundary.",
        "- [ ] Development keys are excluded from normal release/testnet bundles.",
        "- [ ] Lost-key warning is approved.",
        "- [ ] Backup passphrase warning is approved.",
        "",
        "## Approval Statement",
        "",
        "",
        "## Required Gate Note",
        "",
        "Do not mark `wallet_recovery_custody_policy_complete` complete until the",
        "final wallet custody evidence JSON passes `--require-complete` and the",
        "manual gate is explicitly approved.",
        "",
    ]))

    return {
        "decision_workpapers": decision_paths,
        "control_workpapers": control_paths,
        "review_ticket_template": reviewer_ticket_path.as_posix(),
        "final_approval_template": final_approval_path.as_posix(),
    }


def write_wallet_custody_evidence_workbench(out_dir, workpapers, reviewed_source_hash="", release_bundle_sha256=""):
    payload = wallet_custody_evidence_template()
    payload["status"] = "not_started"
    payload["reviewed_source_hash"] = reviewed_source_hash or ""
    payload["release_bundle_sha256"] = release_bundle_sha256 or ""
    payload["reviewer"]["engagement_or_ticket"] = workpapers["review_ticket_template"]

    decision_paths = {Path(path).stem: path for path in workpapers.get("decision_workpapers", [])}
    for decision in payload["decisions"]:
        decision["evidence"] = decision_paths.get(decision["id"], "")

    for field, rel in workpapers.get("control_workpapers", {}).items():
        payload["controls"][field] = rel
        payload["controls"][field.replace("_path", "_sha256")] = _hash_relative(out_dir, rel)

    payload["final_approval"]["statement"] = f"Use {workpapers['final_approval_template']} for final wallet/custody approval."
    write_json(out_dir / "wallet_custody_evidence_workbench.json", payload)
    return payload


def write_workbench_readme(out_dir, summary):
    write_text(out_dir / "README.md", "\n".join([
        "# SpaceCash Wallet Recovery/Custody Workbench",
        "",
        "This package prepares wallet recovery/custody review evidence. It is not custody approval.",
        "",
        f"- Chain: `{summary['chain_id']}`",
        f"- Source hash: `{summary['reviewed_source_hash'] or 'not set'}`",
        f"- Release bundle SHA256: `{summary['release_bundle_sha256'] or 'not set'}`",
        f"- Wallet custody ready: `{summary['wallet_custody_ready']}`",
        f"- Decisions: `{summary['decision_count']}`",
        f"- Manual gate: `{summary['manual_gate']['status']}`",
        "",
        "Reviewer order:",
        "",
        "1. Verify `SHA256SUMS.txt`.",
        "2. Review `wallet_custody_evidence_workbench.json` and `wallet_custody_evidence_workbench_check.json`.",
        "3. Fill `wallet/reviewer/review_ticket_template.md` with the actual reviewer details.",
        "4. Complete every `wallet/decisions/*.md` workpaper.",
        "5. Finalize the controls under `wallet/controls/` and update their hashes in the evidence JSON.",
        "6. Fill `wallet/final_approval_template.md` and then complete the final evidence JSON.",
        "7. Do not mark `wallet_recovery_custody_policy_complete` complete until `--require-complete` passes.",
        "",
    ]))


def write_checksums(out_dir):
    artifact_paths = sorted(
        path for path in out_dir.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS.txt"
    )
    lines = []
    files = []
    for path in artifact_paths:
        digest = file_hash(path)
        rel = path.relative_to(out_dir).as_posix()
        lines.append(f"{digest}  {rel}")
        files.append({"path": rel, "bytes": path.stat().st_size, "sha256": digest})
    sums = out_dir / "SHA256SUMS.txt"
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")
    files.append({"path": "SHA256SUMS.txt", "bytes": sums.stat().st_size, "sha256": file_hash(sums)})
    return files


def build_wallet_custody_workbench(out_dir=None, reviewed_source_hash="", release_bundle_sha256="", force=False):
    out_dir = Path(out_dir or default_workbench_dir())
    if out_dir.exists():
        if not force:
            raise ValueError(f"Wallet custody workbench already exists: {out_dir}")
        safe_reset_dir(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    workpapers = write_wallet_custody_workpapers(out_dir)
    evidence = write_wallet_custody_evidence_workbench(
        out_dir,
        workpapers,
        reviewed_source_hash=reviewed_source_hash,
        release_bundle_sha256=release_bundle_sha256,
    )
    check = validate_wallet_custody_evidence(evidence)
    write_json(out_dir / "wallet_custody_evidence_workbench_check.json", check)

    summary = {
        "ok": bool(check.get("ok") and not check.get("wallet_custody_ready")),
        "mode": "spacecash-wallet-custody-workbench-v1",
        "generated_at": protocol.utc_now(),
        "chain_id": protocol.CHAIN_ID,
        "out_dir": str(out_dir.resolve()),
        "reviewed_source_hash": evidence.get("reviewed_source_hash"),
        "release_bundle_sha256": evidence.get("release_bundle_sha256"),
        "wallet_policy_hash": evidence.get("wallet_policy_hash"),
        "wallet_custody_ready": check.get("wallet_custody_ready"),
        "approved_decision_count": check.get("approved_decision_count"),
        "required_decision_count": check.get("required_decision_count"),
        "decision_count": len(workpapers.get("decision_workpapers") or []),
        "blockers": check.get("blockers") or [],
        "review_workpapers": workpapers,
        "required_outputs": [
            "reviewer ticket or engagement",
            "recovery standard",
            "address versioning plan",
            "backup rotation policy",
            "lost-key procedure",
            "compromised-key procedure",
            "hardware wallet or custody position",
            "backup verification flow",
            "private-key handling policy",
            "final wallet/custody approval",
        ],
        "manual_gate": {
            "id": "wallet_recovery_custody_policy_complete",
            "status": "not_complete",
            "reason": "Wallet recovery/custody review and final approval are still required.",
        },
    }
    write_json(out_dir / "wallet_custody_workbench_summary.json", summary)
    write_workbench_readme(out_dir, summary)
    files = write_checksums(out_dir)
    result = dict(summary)
    result["files"] = files
    return result


def write_wallet_custody_evidence_template(out_path=None):
    payload = wallet_custody_evidence_template()
    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def load_wallet_custody_evidence(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_parser():
    parser = argparse.ArgumentParser(description="Create or verify SpaceCash wallet recovery/custody evidence")
    parser.add_argument("--template-out", type=Path, help="Optional path to write the wallet custody evidence template")
    parser.add_argument("--verify", type=Path, help="Wallet custody evidence JSON file to verify")
    parser.add_argument("--require-complete", action="store_true", help="Fail unless the wallet recovery/custody gate is complete")
    parser.add_argument("--workbench-out-dir", type=Path, help="Write a wallet recovery/custody review workbench packet")
    parser.add_argument("--reviewed-source-hash", default="", help="Optional reviewed source hash to seed into the workbench")
    parser.add_argument("--release-bundle-sha256", default="", help="Optional release bundle SHA-256 to seed into the workbench")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing workbench directory under _tmp")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.verify:
        result = validate_wallet_custody_evidence(
            load_wallet_custody_evidence(args.verify),
            require_complete=args.require_complete,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") and (not args.require_complete or result.get("wallet_custody_ready")) else 2
    if args.workbench_out_dir:
        try:
            result = build_wallet_custody_workbench(
                out_dir=args.workbench_out_dir,
                reviewed_source_hash=args.reviewed_source_hash,
                release_bundle_sha256=args.release_bundle_sha256,
                force=args.force,
            )
        except ValueError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 2
    payload = write_wallet_custody_evidence_template(args.template_out)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
