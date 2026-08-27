"""Create and verify SpaceCash external security-review closure evidence."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = Path(__file__).resolve().parent
for candidate in (ROOT, TOOLS_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from spacecash_core import protocol  # noqa: E402
from spacecash_genesis_allocation import genesis_allocation_template  # noqa: E402


EVIDENCE_MODE = "spacecash-external-security-review-evidence-v1"
EVIDENCE_VERSION = 1
HASH_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
STATUS_VALUES = ("not_started", "in_review", "remediation", "closed")
TOPIC_STATUSES = ("not_reviewed", "pass", "finding", "accepted_risk")
FINDING_SEVERITIES = ("critical", "high", "medium", "low", "informational")
FINDING_STATUSES = ("open", "fixed", "accepted_risk", "duplicate", "invalid", "closed")
FINAL_FINDING_STATUSES = ("accepted_risk", "duplicate", "invalid", "closed")

REQUIRED_REVIEW_TOPICS = (
    {"id": "signature_payload_binding", "severity_if_failed": "critical"},
    {"id": "nonce_and_mempool_replay", "severity_if_failed": "critical"},
    {"id": "ledger_supply_and_blocks", "severity_if_failed": "critical"},
    {"id": "snapshot_sync_import", "severity_if_failed": "high"},
    {"id": "consensus_spec_integrity", "severity_if_failed": "high"},
    {"id": "monetary_policy_integrity", "severity_if_failed": "high"},
    {"id": "genesis_allocation_boundary", "severity_if_failed": "high"},
    {"id": "genesis_allocation_schema", "severity_if_failed": "high"},
    {"id": "wallet_recovery_custody_boundary", "severity_if_failed": "high"},
    {"id": "checkpoint_quorum", "severity_if_failed": "high"},
    {"id": "daemon_exposure", "severity_if_failed": "high"},
)


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def _non_empty(value):
    return isinstance(value, str) and bool(value.strip())


def _hash_or_empty(value):
    text = str(value or "").strip()
    return not text or HASH_RE.fullmatch(text) is not None


def _artifact(rel):
    path = ROOT / rel
    return {
        "path": rel,
        "exists": path.exists(),
        "sha256": file_hash(path) if path.exists() else "",
    }


def _default_artifacts():
    return [
        _artifact("docs/spacecash/SECURITY_AUDIT_SCOPE.md"),
        _artifact("docs/spacecash/THREAT_MODEL.md"),
        _artifact("docs/spacecash/MAINNET_GATE.md"),
    ]


def _empty_topic(definition):
    return {
        "id": definition["id"],
        "severity_if_failed": definition["severity_if_failed"],
        "status": "not_reviewed",
        "reviewer": "",
        "evidence": "",
        "notes": "",
    }


def security_review_evidence_template():
    return {
        "mode": EVIDENCE_MODE,
        "version": EVIDENCE_VERSION,
        "chain_id": protocol.CHAIN_ID,
        "status": "not_started",
        "reviewed_source_hash": "",
        "security_packet_sha256": "",
        "protocol_hashes": {
            "consensus_spec_hash": protocol.consensus_spec_hash(),
            "monetary_policy_hash": protocol.monetary_policy_hash(),
            "genesis_plan_hash": protocol.genesis_plan_hash(),
            "genesis_allocation_hash": genesis_allocation_template().get("allocation_hash"),
            "wallet_policy_hash": protocol.wallet_policy_hash(),
        },
        "artifacts": _default_artifacts(),
        "auditor": {
            "name": "",
            "firm": "",
            "contact": "",
            "independence_statement": "",
            "signed_scope_path": "",
            "signed_scope_sha256": "",
        },
        "scope": {
            "topics": [_empty_topic(definition) for definition in REQUIRED_REVIEW_TOPICS],
        },
        "findings": [],
        "remediation": {
            "all_critical_high_closed": False,
            "reviewed_remediation_hash": "",
            "evidence_paths": [],
            "notes": "",
        },
        "closure": {
            "status": "not_started",
            "closed_at": "",
            "auditor_statement": "",
            "approved_for_release": False,
            "accepted_risks": [],
        },
        "manual_gate": {
            "id": "external_security_review_complete",
            "status": "not_complete",
            "reason": "External auditor findings, remediation evidence, accepted-risk record, and final closure are required.",
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


def _validate_auditor(auditor, errors, blockers, require_complete):
    if not isinstance(auditor, dict):
        errors.append("auditor must be an object.")
        auditor = {}
    required_fields = ("name", "firm", "contact", "independence_statement", "signed_scope_path")
    missing = [field for field in required_fields if not _non_empty(auditor.get(field))]
    if missing:
        blockers.append("auditor_missing")
        if require_complete:
            errors.append(f"auditor missing required fields: {', '.join(missing)}.")
    signed_scope_sha256 = str(auditor.get("signed_scope_sha256") or "").strip()
    if not signed_scope_sha256:
        blockers.append("signed_scope_missing")
        if require_complete:
            errors.append("auditor.signed_scope_sha256 is required.")
    elif not HASH_RE.fullmatch(signed_scope_sha256):
        errors.append("auditor.signed_scope_sha256 must be a 64-character SHA-256 hash.")


def _validate_topics(scope, errors, blockers, require_complete):
    if not isinstance(scope, dict):
        errors.append("scope must be an object.")
        scope = {}
    topics = scope.get("topics")
    if not isinstance(topics, list):
        errors.append("scope.topics must be a list.")
        topics = []
    required = {topic["id"]: topic for topic in REQUIRED_REVIEW_TOPICS}
    by_id = {}
    reviewed = []
    for index, topic in enumerate(topics):
        prefix = f"scope.topics[{index}]"
        if not isinstance(topic, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        topic_id = topic.get("id")
        if topic_id not in required:
            errors.append(f"{prefix}.id is not a required security review topic.")
            continue
        if topic_id in by_id:
            errors.append(f"{prefix}.id duplicates an earlier topic.")
            continue
        by_id[topic_id] = topic
        if topic.get("severity_if_failed") != required[topic_id]["severity_if_failed"]:
            errors.append(f"{topic_id}.severity_if_failed does not match the v1 review scope.")
        if topic.get("status") not in TOPIC_STATUSES:
            errors.append(f"{topic_id}.status must be one of {', '.join(TOPIC_STATUSES)}.")
        if topic.get("status") in ("pass", "accepted_risk"):
            reviewed.append(topic_id)

    for topic_id in required:
        topic = by_id.get(topic_id)
        if not topic:
            errors.append(f"Missing security review topic {topic_id}.")
            blockers.append(f"{topic_id}_missing")
            continue
        if topic.get("status") not in ("pass", "accepted_risk"):
            blockers.append(f"{topic_id}_not_closed")
        if require_complete or topic.get("status") in ("pass", "accepted_risk", "finding"):
            if not _non_empty(topic.get("reviewer")):
                errors.append(f"{topic_id}.reviewer is required.")
            if not _non_empty(topic.get("evidence")):
                errors.append(f"{topic_id}.evidence is required.")
    if len(reviewed) < len(required):
        blockers.append("scope_topics_not_closed")
    return reviewed


def _validate_findings(findings, errors, blockers, require_complete):
    if not isinstance(findings, list):
        errors.append("findings must be a list.")
        return []
    parsed = []
    open_findings = []
    critical_high_open = []
    seen = set()
    for index, finding in enumerate(findings):
        prefix = f"findings[{index}]"
        if not isinstance(finding, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        finding_id = finding.get("id") or f"finding[{index}]"
        if not _non_empty(finding.get("id")):
            if require_complete:
                errors.append(f"{prefix}.id is required.")
        elif finding["id"] in seen:
            errors.append(f"{prefix}.id duplicates an earlier finding.")
        else:
            seen.add(finding["id"])
        severity = finding.get("severity")
        status = finding.get("status")
        if severity not in FINDING_SEVERITIES:
            errors.append(f"{finding_id}.severity must be one of {', '.join(FINDING_SEVERITIES)}.")
        if status not in FINDING_STATUSES:
            errors.append(f"{finding_id}.status must be one of {', '.join(FINDING_STATUSES)}.")
        for field in ("component", "summary"):
            if require_complete and not _non_empty(finding.get(field)):
                errors.append(f"{finding_id}.{field} is required.")
        if status in ("open", "fixed"):
            open_findings.append(finding_id)
            if severity in ("critical", "high"):
                critical_high_open.append(finding_id)
        if require_complete and status in ("closed", "fixed") and not _non_empty(finding.get("remediation")):
            errors.append(f"{finding_id}.remediation is required for fixed or closed findings.")
        if require_complete and status == "closed" and not _non_empty(finding.get("closure_evidence")):
            errors.append(f"{finding_id}.closure_evidence is required for closed findings.")
        if require_complete and status == "accepted_risk" and not _non_empty(finding.get("accepted_risk_justification")):
            errors.append(f"{finding_id}.accepted_risk_justification is required for accepted risks.")
        parsed.append({
            "id": finding_id,
            "severity": severity,
            "status": status,
        })
    if open_findings:
        blockers.append("open_findings")
    if critical_high_open:
        blockers.append("critical_high_findings_open")
    if require_complete:
        unfinished = [row["id"] for row in parsed if row["status"] not in FINAL_FINDING_STATUSES]
        if unfinished:
            errors.append("All findings must be closed, accepted_risk, duplicate, or invalid before audit closure.")
    return parsed


def _validate_remediation(remediation, findings, errors, blockers, require_complete):
    if not isinstance(remediation, dict):
        errors.append("remediation must be an object.")
        remediation = {}
    reviewed_hash = str(remediation.get("reviewed_remediation_hash") or "").strip()
    if reviewed_hash and not HASH_RE.fullmatch(reviewed_hash):
        errors.append("remediation.reviewed_remediation_hash must be a 64-character SHA-256 hash.")
    evidence_paths = remediation.get("evidence_paths")
    if not isinstance(evidence_paths, list):
        errors.append("remediation.evidence_paths must be a list.")
        evidence_paths = []
    high_or_critical = [row for row in findings if row.get("severity") in ("critical", "high")]
    if remediation.get("all_critical_high_closed") is not True:
        if high_or_critical or require_complete:
            blockers.append("critical_high_remediation_not_confirmed")
            if require_complete:
                errors.append("remediation.all_critical_high_closed must be true.")
    if require_complete and findings and not evidence_paths:
        errors.append("remediation.evidence_paths is required when findings are present.")


def _validate_closure(closure, errors, blockers, require_complete):
    if not isinstance(closure, dict):
        errors.append("closure must be an object.")
        closure = {}
    if closure.get("status") != "closed":
        blockers.append("closure_not_closed")
        if require_complete:
            errors.append("closure.status must be closed.")
    if closure.get("approved_for_release") is not True:
        blockers.append("closure_not_approved")
        if require_complete:
            errors.append("closure.approved_for_release must be true.")
    for field in ("closed_at", "auditor_statement"):
        if not _non_empty(closure.get(field)):
            blockers.append(f"closure_{field}_missing")
            if require_complete:
                errors.append(f"closure.{field} is required.")
    accepted_risks = closure.get("accepted_risks")
    if not isinstance(accepted_risks, list):
        errors.append("closure.accepted_risks must be a list.")


def validate_security_review_evidence(data, require_complete=False):
    errors = []
    warnings = []
    blockers = []

    if not isinstance(data, dict):
        return {
            "ok": False,
            "external_security_review_ready": False,
            "errors": ["Security review evidence must be a JSON object."],
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

    expected_hashes = security_review_evidence_template()["protocol_hashes"]
    hashes = data.get("protocol_hashes") if isinstance(data.get("protocol_hashes"), dict) else {}
    for field, expected in expected_hashes.items():
        if hashes.get(field) != expected:
            errors.append(f"protocol_hashes.{field} must equal {expected}.")

    reviewed_source_hash = str(data.get("reviewed_source_hash") or "").strip()
    security_packet_sha256 = str(data.get("security_packet_sha256") or "").strip()
    if not reviewed_source_hash:
        blockers.append("reviewed_source_hash_missing")
        if require_complete:
            errors.append("reviewed_source_hash is required.")
    elif not _hash_or_empty(reviewed_source_hash):
        errors.append("reviewed_source_hash must be a 64-character SHA-256 hash.")
    if not security_packet_sha256:
        blockers.append("security_packet_sha256_missing")
        if require_complete:
            errors.append("security_packet_sha256 is required.")
    elif not _hash_or_empty(security_packet_sha256):
        errors.append("security_packet_sha256 must be a 64-character SHA-256 hash.")

    verified_artifacts = _validate_artifacts(data.get("artifacts") or [], errors, warnings)
    _validate_auditor(data.get("auditor"), errors, blockers, require_complete)
    reviewed_topics = _validate_topics(data.get("scope"), errors, blockers, require_complete)
    findings = _validate_findings(data.get("findings") or [], errors, blockers, require_complete)
    _validate_remediation(data.get("remediation"), findings, errors, blockers, require_complete)
    _validate_closure(data.get("closure"), errors, blockers, require_complete)

    manual_gate = data.get("manual_gate") if isinstance(data.get("manual_gate"), dict) else {}
    manual_gate_complete = (
        manual_gate.get("id") == "external_security_review_complete"
        and manual_gate.get("status") == "complete"
    )
    if not manual_gate_complete:
        blockers.append("manual_gate_not_complete")
        if require_complete:
            errors.append("manual_gate external_security_review_complete must be complete.")

    if require_complete or data.get("status") == "closed":
        if data.get("status") != "closed":
            errors.append("status must be closed for external security review evidence.")

    blockers = sorted(set(blockers))
    external_security_review_ready = bool(
        not errors
        and not blockers
        and data.get("status") == "closed"
        and manual_gate_complete
    )
    if require_complete and not external_security_review_ready:
        errors.append("External security review evidence is not complete.")

    return {
        "ok": not errors,
        "external_security_review_ready": external_security_review_ready,
        "mode": EVIDENCE_MODE,
        "chain_id": data.get("chain_id"),
        "status": data.get("status"),
        "reviewed_topic_count": len(reviewed_topics),
        "required_topic_count": len(REQUIRED_REVIEW_TOPICS),
        "finding_count": len(findings),
        "critical_high_open_count": len([row for row in findings if row.get("severity") in ("critical", "high") and row.get("status") not in FINAL_FINDING_STATUSES]),
        "verified_artifacts": verified_artifacts,
        "blockers": blockers,
        "manual_gate_status": manual_gate.get("status"),
        "errors": errors,
        "warnings": warnings,
    }


def write_security_review_evidence_template(out_path=None):
    payload = security_review_evidence_template()
    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def load_security_review_evidence(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_parser():
    parser = argparse.ArgumentParser(description="Create or verify SpaceCash external security-review closure evidence")
    parser.add_argument("--template-out", type=Path, help="Optional path to write the security-review evidence template")
    parser.add_argument("--verify", type=Path, help="Security-review evidence JSON file to verify")
    parser.add_argument("--require-complete", action="store_true", help="Fail unless the external security review gate is complete")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.verify:
        result = validate_security_review_evidence(
            load_security_review_evidence(args.verify),
            require_complete=args.require_complete,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") and (not args.require_complete or result.get("external_security_review_ready")) else 2
    payload = write_security_review_evidence_template(args.template_out)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
