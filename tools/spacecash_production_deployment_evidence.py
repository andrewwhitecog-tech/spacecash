"""Create and verify SpaceCash production deployment approval evidence."""

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


EVIDENCE_MODE = "spacecash-production-deployment-evidence-v1"
EVIDENCE_VERSION = 1
HASH_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
STATUS_VALUES = ("not_started", "in_review", "blocked", "approved")
DECISION_STATUSES = ("not_reviewed", "approved", "approved_with_conditions", "blocked", "not_applicable")
READY_DECISION_STATUSES = ("approved", "approved_with_conditions", "not_applicable")

REQUIRED_DECISIONS = (
    {"id": "source_freeze", "title": "Source Freeze And Reviewed Source Hash"},
    {"id": "release_bundle_archive", "title": "Release Bundle Archive And Checksum Verification"},
    {"id": "approved_genesis_allocation", "title": "Approved Genesis Allocation And Migration Boundary"},
    {"id": "node_setup", "title": "Node Setup Instructions And Bootstrap Peer Plan"},
    {"id": "validator_rollout", "title": "Validator Rollout And Checkpoint Quorum Plan"},
    {"id": "http_hardening", "title": "Production HTTP Controls"},
    {"id": "monitoring_alerting", "title": "Monitoring, Alerting, And On-Call Coverage"},
    {"id": "backup_restore", "title": "Backup, Snapshot, And Restore Rehearsal"},
    {"id": "rollback_plan", "title": "Rollback Procedure"},
    {"id": "incident_response", "title": "Incident Response And Public Status Procedure"},
    {"id": "post_deploy_audit", "title": "Post-Deploy Audit And Readiness Verification"},
)

REQUIRED_CONTROL_FIELDS = (
    "release_manifest_path",
    "release_bundle_path",
    "sha256sums_path",
    "deployment_runbook_path",
    "node_setup_instructions_path",
    "bootstrap_peer_plan_path",
    "validator_rollout_plan_path",
    "production_http_controls_path",
    "monitoring_plan_path",
    "backup_restore_rehearsal_path",
    "rollback_plan_path",
    "incident_response_plan_path",
    "post_deploy_audit_plan_path",
)

REQUIRED_READINESS_HASHES = (
    "public_testnet_evidence_sha256",
    "security_review_evidence_sha256",
    "legal_compliance_evidence_sha256",
    "wallet_custody_evidence_sha256",
    "genesis_allocation_check_sha256",
)

CONTROL_WORKPAPERS = {
    "release_manifest_path": ("deployment/controls/release_manifest_review.md", "Release Manifest Review"),
    "release_bundle_path": ("deployment/controls/release_bundle_archive.md", "Release Bundle Archive"),
    "sha256sums_path": ("deployment/controls/sha256sums_verification.md", "SHA256SUMS Verification"),
    "deployment_runbook_path": ("deployment/controls/deployment_runbook.md", "Deployment Runbook"),
    "node_setup_instructions_path": ("deployment/controls/node_setup_instructions.md", "Node Setup Instructions"),
    "bootstrap_peer_plan_path": ("deployment/controls/bootstrap_peer_plan.md", "Bootstrap Peer Plan"),
    "validator_rollout_plan_path": ("deployment/controls/validator_rollout_plan.md", "Validator Rollout Plan"),
    "production_http_controls_path": ("deployment/controls/production_http_controls.md", "Production HTTP Controls"),
    "monitoring_plan_path": ("deployment/controls/monitoring_plan.md", "Monitoring Plan"),
    "backup_restore_rehearsal_path": ("deployment/controls/backup_restore_rehearsal.md", "Backup Restore Rehearsal"),
    "rollback_plan_path": ("deployment/controls/rollback_plan.md", "Rollback Plan"),
    "incident_response_plan_path": ("deployment/controls/incident_response_plan.md", "Incident Response Plan"),
    "post_deploy_audit_plan_path": ("deployment/controls/post_deploy_audit_plan.md", "Post-Deploy Audit Plan"),
}

DECISION_QUESTIONS = {
    "source_freeze": [
        "Which source hash is frozen for production review?",
        "What changes are forbidden after source freeze without a new bundle?",
    ],
    "release_bundle_archive": [
        "Where is the release bundle archived and how are checksums verified?",
        "Who can approve a replacement bundle?",
    ],
    "approved_genesis_allocation": [
        "Does the approved allocation file pass the allocation verifier in require-approved mode?",
        "Does the deployment plan preserve the devnet-to-mainnet migration boundary?",
    ],
    "node_setup": [
        "Can a fresh operator reproduce node setup from the documented steps?",
        "Are bootstrap peer addresses and trust assumptions documented?",
    ],
    "validator_rollout": [
        "How are validators registered, started, monitored, and replaced?",
        "What confirms checkpoint quorum before public use?",
    ],
    "http_hardening": [
        "Which public routes are read-only, authenticated, rate-limited, and logged?",
        "What CORS, TLS, abuse, and write-route controls are required before launch?",
    ],
    "monitoring_alerting": [
        "Which metrics and alert thresholds define degraded SpaceCash service?",
        "Who is on call for ledger, validator, node, and product-payment failures?",
    ],
    "backup_restore": [
        "When was backup/restore rehearsed and which artifacts prove it?",
        "What snapshot, database, and peer metadata must be retained?",
    ],
    "rollback_plan": [
        "What exact steps disable writes, preserve evidence, restore service, and communicate status?",
        "Who owns rollback approval during the launch window?",
    ],
    "incident_response": [
        "What public status and customer-support workflow is used during incidents?",
        "What evidence is retained for post-incident review?",
    ],
    "post_deploy_audit": [
        "Which audit/readiness commands must pass after deployment?",
        "What result blocks launch continuation after deploy?",
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
    return ROOT / "_tmp" / f"spacecash_production_deployment_workbench_{stamp}_{secrets.token_hex(4)}"


def safe_reset_dir(path):
    path = Path(path).resolve()
    tmp_root = (ROOT / "_tmp").resolve()
    if path == tmp_root or tmp_root not in path.parents:
        raise ValueError("Refusing to overwrite a production deployment workbench outside the project _tmp directory.")
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
        _artifact("docs/spacecash/PRODUCTION_DEPLOYMENT_RUNBOOK.md"),
        _artifact("docs/spacecash/MAINNET_GATE.md"),
        _artifact("docs/spacecash/MANUAL_GATES.md"),
        _artifact("docs/spacecash/THREAT_MODEL.md"),
    ]


def _empty_decision(definition):
    return {
        "id": definition["id"],
        "title": definition["title"],
        "status": "not_reviewed",
        "owner": "",
        "evidence": "",
        "notes": "",
    }


def _empty_controls():
    controls = {}
    for field in REQUIRED_CONTROL_FIELDS:
        controls[field] = ""
        controls[field.replace("_path", "_sha256")] = ""
    return controls


def production_deployment_evidence_template():
    return {
        "mode": EVIDENCE_MODE,
        "version": EVIDENCE_VERSION,
        "chain_id": protocol.CHAIN_ID,
        "status": "not_started",
        "reviewed_source_hash": "",
        "release_bundle_sha256": "",
        "security_review_packet_sha256": "",
        "approved_genesis_allocation_sha256": "",
        "artifacts": _default_artifacts(),
        "reviewer": {
            "name": "",
            "role": "",
            "contact": "",
            "reviewed_at": "",
            "change_ticket": "",
        },
        "environment": {
            "production_domain": "",
            "deployment_target": "",
            "bootstrap_peers": [],
            "validator_count": 0,
            "validator_quorum": 0,
            "monitoring_endpoints": [],
            "incident_contact": "",
        },
        "readiness_inputs": {field: "" for field in REQUIRED_READINESS_HASHES},
        "decisions": [_empty_decision(definition) for definition in REQUIRED_DECISIONS],
        "controls": _empty_controls(),
        "final_approval": {
            "approved": False,
            "approved_at": "",
            "approver": "",
            "statement": "",
            "launch_window_approved": False,
            "write_route_controls_approved": False,
            "monitoring_owner_confirmed": False,
            "rollback_owner_confirmed": False,
            "backup_restore_rehearsed": False,
            "release_artifacts_archived": False,
            "post_deploy_audit_required": True,
        },
        "manual_gate": {
            "id": "production_deployment_runbook_complete",
            "status": "not_complete",
            "reason": "Reproducible deployment, monitoring, rollback, incident response, archived artifacts, and post-deploy audit plan require approval.",
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


def _validate_hash_field(container, field, errors, blockers, require_complete, prefix=""):
    value = str(container.get(field) or "").strip()
    name = f"{prefix}{field}"
    if not value:
        blockers.append(f"{field}_missing")
        if require_complete:
            errors.append(f"{name} is required.")
    elif not HASH_RE.fullmatch(value):
        errors.append(f"{name} must be a 64-character SHA-256 hash.")


def _validate_reviewer(reviewer, errors, blockers, require_complete):
    if not isinstance(reviewer, dict):
        errors.append("reviewer must be an object.")
        reviewer = {}
    required = ("name", "role", "contact", "reviewed_at", "change_ticket")
    missing = [field for field in required if not _non_empty(reviewer.get(field))]
    if missing:
        blockers.append("reviewer_missing")
        if require_complete:
            errors.append(f"reviewer missing required fields: {', '.join(missing)}.")


def _validate_environment(environment, errors, blockers, require_complete):
    if not isinstance(environment, dict):
        errors.append("environment must be an object.")
        environment = {}
    for field in ("production_domain", "deployment_target", "incident_contact"):
        if not _non_empty(environment.get(field)):
            blockers.append(f"{field}_missing")
            if require_complete:
                errors.append(f"environment.{field} is required.")
    for field in ("bootstrap_peers", "monitoring_endpoints"):
        value = environment.get(field)
        if not isinstance(value, list):
            errors.append(f"environment.{field} must be a list.")
            value = []
        if not value:
            blockers.append(f"{field}_missing")
            if require_complete:
                errors.append(f"environment.{field} is required.")
    for field in ("validator_count", "validator_quorum"):
        value = environment.get(field)
        if not isinstance(value, int) or value <= 0:
            blockers.append(f"{field}_invalid")
            if require_complete:
                errors.append(f"environment.{field} must be a positive integer.")
    count = environment.get("validator_count")
    quorum = environment.get("validator_quorum")
    if isinstance(count, int) and isinstance(quorum, int) and count > 0 and quorum > count:
        errors.append("environment.validator_quorum cannot exceed validator_count.")


def _validate_readiness_inputs(readiness_inputs, errors, blockers, require_complete):
    if not isinstance(readiness_inputs, dict):
        errors.append("readiness_inputs must be an object.")
        readiness_inputs = {}
    for field in REQUIRED_READINESS_HASHES:
        _validate_hash_field(readiness_inputs, field, errors, blockers, require_complete, prefix="readiness_inputs.")


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
            errors.append(f"{prefix}.id is not a required production deployment decision.")
            continue
        if decision_id in by_id:
            errors.append(f"{prefix}.id duplicates an earlier deployment decision.")
            continue
        by_id[decision_id] = decision
        if decision.get("title") != required[decision_id]["title"]:
            errors.append(f"{decision_id}.title does not match the v1 deployment schema.")
        if decision.get("status") not in DECISION_STATUSES:
            errors.append(f"{decision_id}.status must be one of {', '.join(DECISION_STATUSES)}.")
        if decision.get("status") == "blocked":
            blockers.append(f"{decision_id}_blocked")
        if decision.get("status") in READY_DECISION_STATUSES:
            ready.append(decision_id)
        if require_complete or decision.get("status") in READY_DECISION_STATUSES + ("blocked",):
            if not _non_empty(decision.get("owner")):
                errors.append(f"{decision_id}.owner is required.")
            if not _non_empty(decision.get("evidence")):
                errors.append(f"{decision_id}.evidence is required.")
    for decision_id in required:
        if decision_id not in by_id:
            errors.append(f"Missing production deployment decision {decision_id}.")
            blockers.append(f"{decision_id}_missing")
        elif by_id[decision_id].get("status") not in READY_DECISION_STATUSES:
            blockers.append(f"{decision_id}_not_approved")
    if len(ready) < len(required):
        blockers.append("deployment_decisions_not_approved")
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
    for field in (
        "launch_window_approved",
        "write_route_controls_approved",
        "monitoring_owner_confirmed",
        "rollback_owner_confirmed",
        "backup_restore_rehearsed",
        "release_artifacts_archived",
        "post_deploy_audit_required",
    ):
        if final_approval.get(field) is not True:
            blockers.append(f"{field}_not_confirmed")
            if require_complete:
                errors.append(f"final_approval.{field} must be true.")


def validate_production_deployment_evidence(data, require_complete=False):
    errors = []
    warnings = []
    blockers = []

    if not isinstance(data, dict):
        return {
            "ok": False,
            "deployment_ready": False,
            "errors": ["Production deployment evidence must be a JSON object."],
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

    for field in (
        "reviewed_source_hash",
        "release_bundle_sha256",
        "security_review_packet_sha256",
        "approved_genesis_allocation_sha256",
    ):
        _validate_hash_field(data, field, errors, blockers, require_complete)

    verified_artifacts = _validate_artifacts(data.get("artifacts") or [], errors, warnings)
    _validate_reviewer(data.get("reviewer"), errors, blockers, require_complete)
    _validate_environment(data.get("environment"), errors, blockers, require_complete)
    _validate_readiness_inputs(data.get("readiness_inputs"), errors, blockers, require_complete)
    approved_decisions = _validate_decisions(data.get("decisions") or [], errors, blockers, require_complete)
    _validate_controls(data.get("controls"), errors, blockers, require_complete)
    _validate_final_approval(data.get("final_approval"), errors, blockers, require_complete)

    manual_gate = data.get("manual_gate") if isinstance(data.get("manual_gate"), dict) else {}
    manual_gate_complete = (
        manual_gate.get("id") == "production_deployment_runbook_complete"
        and manual_gate.get("status") == "complete"
    )
    if not manual_gate_complete:
        blockers.append("manual_gate_not_complete")
        if require_complete:
            errors.append("manual_gate production_deployment_runbook_complete must be complete.")

    if require_complete or data.get("status") == "approved":
        if data.get("status") != "approved":
            errors.append("status must be approved for production deployment completion.")

    blockers = sorted(set(blockers))
    deployment_ready = bool(
        not errors
        and not blockers
        and data.get("status") == "approved"
        and manual_gate_complete
    )
    if require_complete and not deployment_ready:
        errors.append("Production deployment evidence is not complete.")

    return {
        "ok": not errors,
        "deployment_ready": deployment_ready,
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


def write_production_deployment_workpapers(out_dir):
    decision_paths = []
    for definition in REQUIRED_DECISIONS:
        decision_id = definition["id"]
        path = Path("deployment") / "decisions" / f"{decision_id}.md"
        questions = "\n".join(f"- [ ] {question}" for question in DECISION_QUESTIONS.get(decision_id, []))
        write_text(out_dir / path, "\n".join([
            f"# SpaceCash Deployment Decision: {definition['title']}",
            "",
            f"- Decision ID: `{decision_id}`",
            "- Status: `not_reviewed`",
            "- Owner:",
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
            "- Related artifacts:",
            "",
            "## Decision Notes",
            "",
            "- Decision: `not_reviewed`",
            "- Conditions:",
            "- Operational-control changes:",
            "- Launch-window restrictions:",
            "",
        ]))
        decision_paths.append(path.as_posix())

    control_paths = {}
    for field, (rel, title) in CONTROL_WORKPAPERS.items():
        write_text(out_dir / rel, "\n".join([
            f"# SpaceCash {title}",
            "",
            "Draft production deployment control input. This is not deployment approval.",
            "",
            "## Required Artifact Or Procedure",
            "",
            "- Path or archive location:",
            "- Owner:",
            "- Verification command:",
            "- Expected result:",
            "",
            "## Launch Boundary",
            "",
            "- Preconditions:",
            "- Stop conditions:",
            "- Evidence to retain:",
            "",
            "## Reviewer Notes",
            "",
            "- Required changes:",
            "- Hash after final edits:",
            "",
        ]))
        control_paths[field] = rel

    reviewer_ticket_path = Path("deployment") / "reviewer" / "change_ticket_template.md"
    write_text(out_dir / reviewer_ticket_path, "\n".join([
        "# SpaceCash Production Deployment Change Ticket Template",
        "",
        "- Reviewer name:",
        "- Role:",
        "- Contact:",
        "- Reviewed at:",
        "- Change ticket:",
        "- Reviewed source hash:",
        "- Release bundle SHA256:",
        "- Security review packet SHA256:",
        "- Approved genesis allocation SHA256:",
        "",
        "## Scope Acceptance",
        "",
        "The reviewer accepts the production deployment scope in",
        "`docs/spacecash/PRODUCTION_DEPLOYMENT_RUNBOOK.md` and the workpapers in this package.",
        "",
    ]))

    environment_path = Path("deployment") / "environment_template.md"
    write_text(out_dir / environment_path, "\n".join([
        "# SpaceCash Production Environment Template",
        "",
        "- Production domain:",
        "- Deployment target:",
        "- Bootstrap peers:",
        "- Validator count:",
        "- Validator quorum:",
        "- Monitoring endpoints:",
        "- Incident contact:",
        "",
        "Do not copy placeholder values into final evidence. Fill the actual production environment.",
        "",
    ]))

    readiness_path = Path("deployment") / "readiness_inputs_template.md"
    write_text(out_dir / readiness_path, "\n".join([
        "# SpaceCash Deployment Readiness Inputs",
        "",
        "Record the SHA-256 hash for each completed gate-specific evidence file.",
        "",
        "- Public testnet evidence SHA256:",
        "- Security review evidence SHA256:",
        "- Legal/compliance evidence SHA256:",
        "- Wallet custody evidence SHA256:",
        "- Genesis allocation check SHA256:",
        "",
    ]))

    final_approval_path = Path("deployment") / "final_approval_template.md"
    write_text(out_dir / final_approval_path, "\n".join([
        "# SpaceCash Production Deployment Final Approval Template",
        "",
        "- Approved: `false`",
        "- Approved at:",
        "- Approver:",
        "- Reviewed source hash:",
        "- Release bundle SHA256:",
        "",
        "## Required Confirmations",
        "",
        "- [ ] Launch window approved.",
        "- [ ] Write-route controls approved.",
        "- [ ] Monitoring owner confirmed.",
        "- [ ] Rollback owner confirmed.",
        "- [ ] Backup/restore rehearsed.",
        "- [ ] Release artifacts archived.",
        "- [ ] Post-deploy audit required.",
        "",
        "## Approval Statement",
        "",
        "",
        "## Required Gate Note",
        "",
        "Do not mark `production_deployment_runbook_complete` complete until the",
        "final production deployment evidence JSON passes `--require-complete` and",
        "the manual gate is explicitly approved.",
        "",
    ]))

    return {
        "decision_workpapers": decision_paths,
        "control_workpapers": control_paths,
        "review_ticket_template": reviewer_ticket_path.as_posix(),
        "environment_template": environment_path.as_posix(),
        "readiness_inputs_template": readiness_path.as_posix(),
        "final_approval_template": final_approval_path.as_posix(),
    }


def write_production_deployment_evidence_workbench(
    out_dir,
    workpapers,
    reviewed_source_hash="",
    release_bundle_sha256="",
    security_review_packet_sha256="",
    approved_genesis_allocation_sha256="",
):
    payload = production_deployment_evidence_template()
    payload["status"] = "not_started"
    payload["reviewed_source_hash"] = reviewed_source_hash or ""
    payload["release_bundle_sha256"] = release_bundle_sha256 or ""
    payload["security_review_packet_sha256"] = security_review_packet_sha256 or ""
    payload["approved_genesis_allocation_sha256"] = approved_genesis_allocation_sha256 or ""
    payload["reviewer"]["change_ticket"] = workpapers["review_ticket_template"]

    decision_paths = {Path(path).stem: path for path in workpapers.get("decision_workpapers", [])}
    for decision in payload["decisions"]:
        decision["evidence"] = decision_paths.get(decision["id"], "")

    for field, rel in workpapers.get("control_workpapers", {}).items():
        payload["controls"][field] = rel
        payload["controls"][field.replace("_path", "_sha256")] = _hash_relative(out_dir, rel)

    payload["final_approval"]["statement"] = f"Use {workpapers['final_approval_template']} for final production deployment approval."
    write_json(out_dir / "production_deployment_evidence_workbench.json", payload)
    return payload


def write_workbench_readme(out_dir, summary):
    write_text(out_dir / "README.md", "\n".join([
        "# SpaceCash Production Deployment Workbench",
        "",
        "This package prepares production deployment review evidence. It is not deployment approval.",
        "",
        f"- Chain: `{summary['chain_id']}`",
        f"- Source hash: `{summary['reviewed_source_hash'] or 'not set'}`",
        f"- Release bundle SHA256: `{summary['release_bundle_sha256'] or 'not set'}`",
        f"- Deployment ready: `{summary['deployment_ready']}`",
        f"- Decisions: `{summary['decision_count']}`",
        f"- Manual gate: `{summary['manual_gate']['status']}`",
        "",
        "Reviewer order:",
        "",
        "1. Verify `SHA256SUMS.txt`.",
        "2. Review `production_deployment_evidence_workbench.json` and `production_deployment_evidence_workbench_check.json`.",
        "3. Fill `deployment/reviewer/change_ticket_template.md` with actual reviewer/change-ticket details.",
        "4. Fill `deployment/environment_template.md` and transfer final values into the evidence JSON.",
        "5. Complete every `deployment/decisions/*.md` workpaper.",
        "6. Finalize the controls under `deployment/controls/` and update their hashes in the evidence JSON.",
        "7. Fill `deployment/readiness_inputs_template.md` after completed upstream gate evidence exists.",
        "8. Fill `deployment/final_approval_template.md` and then complete the final evidence JSON.",
        "9. Do not mark `production_deployment_runbook_complete` complete until `--require-complete` passes.",
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


def build_production_deployment_workbench(
    out_dir=None,
    reviewed_source_hash="",
    release_bundle_sha256="",
    security_review_packet_sha256="",
    approved_genesis_allocation_sha256="",
    force=False,
):
    out_dir = Path(out_dir or default_workbench_dir())
    if out_dir.exists():
        if not force:
            raise ValueError(f"Production deployment workbench already exists: {out_dir}")
        safe_reset_dir(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    workpapers = write_production_deployment_workpapers(out_dir)
    evidence = write_production_deployment_evidence_workbench(
        out_dir,
        workpapers,
        reviewed_source_hash=reviewed_source_hash,
        release_bundle_sha256=release_bundle_sha256,
        security_review_packet_sha256=security_review_packet_sha256,
        approved_genesis_allocation_sha256=approved_genesis_allocation_sha256,
    )
    check = validate_production_deployment_evidence(evidence)
    write_json(out_dir / "production_deployment_evidence_workbench_check.json", check)

    summary = {
        "ok": bool(check.get("ok") and not check.get("deployment_ready")),
        "mode": "spacecash-production-deployment-workbench-v1",
        "generated_at": protocol.utc_now(),
        "chain_id": protocol.CHAIN_ID,
        "out_dir": str(out_dir.resolve()),
        "reviewed_source_hash": evidence.get("reviewed_source_hash"),
        "release_bundle_sha256": evidence.get("release_bundle_sha256"),
        "security_review_packet_sha256": evidence.get("security_review_packet_sha256"),
        "approved_genesis_allocation_sha256": evidence.get("approved_genesis_allocation_sha256"),
        "deployment_ready": check.get("deployment_ready"),
        "approved_decision_count": check.get("approved_decision_count"),
        "required_decision_count": check.get("required_decision_count"),
        "decision_count": len(workpapers.get("decision_workpapers") or []),
        "blockers": check.get("blockers") or [],
        "review_workpapers": workpapers,
        "required_outputs": [
            "deployment reviewer/change ticket",
            "production environment values",
            "completed upstream gate evidence hashes",
            "release bundle archive and checksum verification",
            "node setup and bootstrap peer plan",
            "validator rollout plan",
            "production HTTP controls",
            "monitoring and incident response plan",
            "backup restore rehearsal",
            "rollback plan",
            "post-deploy audit plan",
            "final production deployment approval",
        ],
        "manual_gate": {
            "id": "production_deployment_runbook_complete",
            "status": "not_complete",
            "reason": "Production deployment review and final approval are still required.",
        },
    }
    write_json(out_dir / "production_deployment_workbench_summary.json", summary)
    write_workbench_readme(out_dir, summary)
    files = write_checksums(out_dir)
    result = dict(summary)
    result["files"] = files
    return result


def write_production_deployment_evidence_template(out_path=None):
    payload = production_deployment_evidence_template()
    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def load_production_deployment_evidence(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_parser():
    parser = argparse.ArgumentParser(description="Create or verify SpaceCash production deployment evidence")
    parser.add_argument("--template-out", type=Path, help="Optional path to write the production deployment evidence template")
    parser.add_argument("--verify", type=Path, help="Production deployment evidence JSON file to verify")
    parser.add_argument("--require-complete", action="store_true", help="Fail unless the production deployment gate is complete")
    parser.add_argument("--workbench-out-dir", type=Path, help="Write a production deployment review workbench packet")
    parser.add_argument("--reviewed-source-hash", default="", help="Optional reviewed source hash to seed into the workbench")
    parser.add_argument("--release-bundle-sha256", default="", help="Optional release bundle SHA-256 to seed into the workbench")
    parser.add_argument("--security-review-packet-sha256", default="", help="Optional security review packet SHA-256 to seed into the workbench")
    parser.add_argument("--approved-genesis-allocation-sha256", default="", help="Optional approved genesis allocation SHA-256 to seed into the workbench")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing workbench directory under _tmp")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.verify:
        result = validate_production_deployment_evidence(
            load_production_deployment_evidence(args.verify),
            require_complete=args.require_complete,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") and (not args.require_complete or result.get("deployment_ready")) else 2
    if args.workbench_out_dir:
        try:
            result = build_production_deployment_workbench(
                out_dir=args.workbench_out_dir,
                reviewed_source_hash=args.reviewed_source_hash,
                release_bundle_sha256=args.release_bundle_sha256,
                security_review_packet_sha256=args.security_review_packet_sha256,
                approved_genesis_allocation_sha256=args.approved_genesis_allocation_sha256,
                force=args.force,
            )
        except ValueError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 2
    payload = write_production_deployment_evidence_template(args.template_out)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
