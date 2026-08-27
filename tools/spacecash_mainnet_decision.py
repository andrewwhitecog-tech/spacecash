"""Create and verify the final SpaceCash mainnet decision evidence file."""

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
from spacecash_gate_evidence import load_gate_evidence, validate_gate_evidence  # noqa: E402
from spacecash_genesis_allocation import load_allocation, validate_allocation  # noqa: E402
from spacecash_legal_compliance_evidence import load_legal_compliance_evidence, validate_legal_compliance_evidence  # noqa: E402
from spacecash_production_deployment_evidence import load_production_deployment_evidence, validate_production_deployment_evidence  # noqa: E402
from spacecash_public_testnet_evidence import load_public_testnet_evidence, validate_public_testnet_evidence  # noqa: E402
from spacecash_security_review_evidence import load_security_review_evidence, validate_security_review_evidence  # noqa: E402
from spacecash_wallet_custody_evidence import load_wallet_custody_evidence, validate_wallet_custody_evidence  # noqa: E402


DECISION_MODE = "spacecash-mainnet-decision-v1"
DECISION_VERSION = 1
HASH_RE = re.compile(r"^[0-9A-Fa-f]{64}$")

ARTIFACTS = (
    ("release_manifest", "_tmp/spacecash_release_manifest.json", "release manifest"),
    ("release_bundle_sha256s", "_tmp/spacecash_release_bundle/SHA256SUMS.txt", "release bundle checksums"),
    ("security_review_packet_sha256s", "_tmp/spacecash_security_review_packet/SHA256SUMS.txt", "security review packet checksums"),
    ("genesis_allocation", "_tmp/spacecash_genesis_allocation.json", "approved genesis allocation"),
    ("manual_gate_evidence", "_tmp/spacecash_manual_gate_evidence.json", "manual gate evidence"),
    ("public_testnet_evidence", "_tmp/spacecash_public_testnet_evidence.json", "public testnet exit evidence"),
    ("security_review_evidence", "_tmp/spacecash_security_review_evidence.json", "external security review evidence"),
    ("legal_compliance_evidence", "_tmp/spacecash_legal_compliance_evidence.json", "legal/compliance evidence"),
    ("wallet_custody_evidence", "_tmp/spacecash_wallet_custody_evidence.json", "wallet recovery/custody evidence"),
    ("production_deployment_evidence", "_tmp/spacecash_production_deployment_evidence.json", "production deployment evidence"),
)

RELEASE_BUNDLE_ARTIFACT_PATHS = {
    "release_manifest": "_tmp/spacecash_release_bundle/release_manifest.json",
    "release_bundle_sha256s": "_tmp/spacecash_release_bundle/SHA256SUMS.txt",
    "security_review_packet_sha256s": "_tmp/spacecash_release_bundle/security_review/SHA256SUMS.txt",
    "genesis_allocation": "_tmp/spacecash_release_bundle/genesis_allocation_template.json",
    "manual_gate_evidence": "_tmp/spacecash_release_bundle/manual_gate_evidence_template.json",
    "public_testnet_evidence": "_tmp/spacecash_release_bundle/public_testnet_evidence_template.json",
    "security_review_evidence": "_tmp/spacecash_release_bundle/security_review_evidence_template.json",
    "legal_compliance_evidence": "_tmp/spacecash_release_bundle/legal_compliance_evidence_template.json",
    "wallet_custody_evidence": "_tmp/spacecash_release_bundle/wallet_custody_evidence_template.json",
    "production_deployment_evidence": "_tmp/spacecash_release_bundle/production_deployment_evidence_template.json",
}

MANUAL_GATE_WORKPAPERS = (
    (
        "public_testnet_complete",
        "Public Testnet Complete",
        "Public testnet exit evidence, node reports, scenario evidence, incident closure, and final report approval.",
    ),
    (
        "external_security_review_complete",
        "External Security Review Complete",
        "Independent security review scope, findings, remediation evidence, and auditor closure.",
    ),
    (
        "legal_compliance_review_complete",
        "Legal And Compliance Review Complete",
        "Use-case, distribution, disclosures, restricted-product policy, tax/payment, and final counsel decision.",
    ),
    (
        "wallet_recovery_custody_policy_complete",
        "Wallet Recovery And Custody Policy Complete",
        "Recovery, backup, lost-key, compromised-key, custody, and private-key handling approvals.",
    ),
    (
        "production_deployment_runbook_complete",
        "Production Deployment Runbook Complete",
        "Source freeze, release archive, node rollout, HTTP controls, monitoring, backup, rollback, and incident response.",
    ),
)

ARTIFACT_REVIEW_QUESTIONS = {
    "release_manifest": [
        "Does release_manifest.source_hash match the reviewed source hash?",
        "Are all release manifest checks acceptable for a final mainnet decision?",
    ],
    "release_bundle_sha256s": [
        "Does the release bundle SHA256SUMS file verify every file in the final archived bundle?",
        "Has the final archive been frozen after checksum generation?",
    ],
    "security_review_packet_sha256s": [
        "Does the security-review packet checksum file verify every external-review workpaper?",
        "Is the packet the same packet referenced by the completed security evidence?",
    ],
    "genesis_allocation": [
        "Does the approved allocation pass the allocation verifier in require-approved mode?",
        "Does the allocation preserve the devnet-to-mainnet migration boundary?",
    ],
    "manual_gate_evidence": [
        "Are all manual gates complete with reviewer, timestamp, and evidence references?",
        "Do the manual gate decisions match the gate-specific evidence files?",
    ],
    "public_testnet_evidence": [
        "Does the public testnet evidence pass require-complete validation?",
        "Are independent operators, node reports, scenarios, incidents, and final report complete?",
    ],
    "security_review_evidence": [
        "Does the external security review evidence pass require-complete validation?",
        "Are all critical and high findings closed or explicitly accepted under policy?",
    ],
    "legal_compliance_evidence": [
        "Does legal/compliance evidence pass require-complete validation?",
        "Are launch copy, product-payment posture, restricted uses, and jurisdictions approved?",
    ],
    "wallet_custody_evidence": [
        "Does wallet recovery/custody evidence pass require-complete validation?",
        "Are private-key handling and custody boundaries approved for launch?",
    ],
    "production_deployment_evidence": [
        "Does production deployment evidence pass require-complete validation?",
        "Are rollout, monitoring, rollback, incident response, archive, and post-deploy audit approved?",
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
    return ROOT / "_tmp" / f"spacecash_mainnet_decision_workbench_{stamp}_{secrets.token_hex(4)}"


def safe_reset_dir(path):
    path = Path(path).resolve()
    tmp_root = (ROOT / "_tmp").resolve()
    if path == tmp_root or tmp_root not in path.parents:
        raise ValueError("Refusing to overwrite a mainnet decision workbench outside the project _tmp directory.")
    if path.exists():
        shutil.rmtree(path)


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _resolve_path(path):
    raw = Path(path)
    if raw.is_absolute():
        return raw
    return ROOT / raw


def _relative_to_root(path):
    raw = Path(path)
    if raw.is_absolute():
        try:
            return raw.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            return str(raw)
    return raw.as_posix()


def _artifact(path, label):
    resolved = _resolve_path(path)
    return {
        "path": path,
        "label": label,
        "sha256": file_hash(resolved) if resolved.exists() else "",
        "exists": resolved.exists(),
    }


def _artifact_path_map(overrides=None):
    paths = {artifact_id: path for artifact_id, path, _ in ARTIFACTS}
    for artifact_id, path in (overrides or {}).items():
        if artifact_id in paths:
            paths[artifact_id] = _relative_to_root(path)
    return paths


def _source_hash_from_manifest(path):
    resolved = _resolve_path(path)
    if not resolved.exists():
        return ""
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ""
    source_hash = _hash_value(data.get("source_hash"))
    return source_hash if HASH_RE.fullmatch(source_hash) else ""


def mainnet_decision_template():
    return {
        "mode": DECISION_MODE,
        "version": DECISION_VERSION,
        "chain_id": protocol.CHAIN_ID,
        "status": "blocked",
        "reviewed_source_hash": "",
        "artifacts": {
            artifact_id: _artifact(path, label)
            for artifact_id, path, label in ARTIFACTS
        },
        "launch_authorization": {
            "approved": False,
            "approver": "",
            "approved_at": "",
            "statement": "",
            "conditions": [],
        },
        "mainnet_rule": "Mainnet requires approved genesis allocation, complete manual gates, complete gate-specific evidence, verified release checksums, and explicit launch authorization.",
    }


def _non_empty(value):
    return isinstance(value, str) and bool(value.strip())


def _hash_value(value):
    return str(value or "").strip().upper()


def _load_json_artifact(path, errors, artifact_id):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{artifact_id}_json_invalid: {exc}")
    except OSError as exc:
        errors.append(f"{artifact_id}_read_failed: {exc}")
    return None


def _verify_sha256s(path):
    errors = []
    checked = 0
    root = Path(path).resolve().parent
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return {"ok": False, "checked": 0, "errors": [f"sha256s_read_failed: {exc}"]}
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2 or not HASH_RE.fullmatch(parts[0].strip()):
            errors.append(f"line_{index + 1}_invalid")
            continue
        expected = parts[0].strip().upper()
        rel = parts[1].strip()
        target = (root / rel).resolve()
        if root not in target.parents and target != root:
            errors.append(f"{rel}_outside_checksum_root")
            continue
        if not target.exists():
            errors.append(f"{rel}_missing")
            continue
        actual = file_hash(target)
        checked += 1
        if actual != expected:
            errors.append(f"{rel}_sha256_mismatch")
    return {"ok": not errors and checked > 0, "checked": checked, "errors": errors}


def _validate_artifact(artifact_id, artifact, errors, blockers):
    if not isinstance(artifact, dict):
        errors.append(f"artifacts.{artifact_id} must be an object.")
        return None
    raw_path = str(artifact.get("path") or "").strip()
    claimed_hash = _hash_value(artifact.get("sha256"))
    if not raw_path:
        blockers.append(f"{artifact_id}_path_missing")
        return None
    resolved = _resolve_path(raw_path)
    result = {
        "path": raw_path,
        "exists": resolved.exists(),
        "sha256": "",
        "claimed_sha256": claimed_hash,
        "verified": False,
    }
    if not resolved.exists():
        blockers.append(f"{artifact_id}_file_missing")
        return result
    actual_hash = file_hash(resolved)
    result["sha256"] = actual_hash
    if not claimed_hash:
        blockers.append(f"{artifact_id}_sha256_missing")
        return result
    if not HASH_RE.fullmatch(claimed_hash):
        errors.append(f"artifacts.{artifact_id}.sha256 must be a 64-character SHA-256 hash.")
        return result
    if claimed_hash != actual_hash:
        errors.append(f"artifacts.{artifact_id}.sha256 does not match the file.")
        return result
    result["verified"] = True
    return result


def _validate_release_manifest(path, reviewed_source_hash, errors, blockers, require_complete):
    data = _load_json_artifact(path, errors, "release_manifest")
    if data is None:
        return {"ok": False, "source_hash": "", "checks_ok": False}
    source_hash = _hash_value(data.get("source_hash"))
    checks_ok = data.get("checks_ok", True) is True
    if not source_hash:
        blockers.append("release_manifest_source_hash_missing")
    elif reviewed_source_hash and reviewed_source_hash != source_hash:
        errors.append("reviewed_source_hash does not match release_manifest.source_hash.")
    if not checks_ok:
        blockers.append("release_manifest_checks_not_ok")
        if require_complete:
            errors.append("release_manifest.checks_ok must be true.")
    return {
        "ok": bool(source_hash and checks_ok),
        "source_hash": source_hash,
        "checks_ok": checks_ok,
        "check_count": len(data.get("checks") or {}),
    }


def _run_gate_validator(artifact_id, path, require_complete):
    if artifact_id == "genesis_allocation":
        result = validate_allocation(load_allocation(path), require_approved=require_complete)
        return "allocation_ready", result
    if artifact_id == "manual_gate_evidence":
        result = validate_gate_evidence(load_gate_evidence(path), require_complete=require_complete)
        return "mainnet_manual_ready", result
    if artifact_id == "public_testnet_evidence":
        result = validate_public_testnet_evidence(load_public_testnet_evidence(path), require_complete=require_complete)
        return "public_testnet_ready", result
    if artifact_id == "security_review_evidence":
        result = validate_security_review_evidence(load_security_review_evidence(path), require_complete=require_complete)
        return "external_security_review_ready", result
    if artifact_id == "legal_compliance_evidence":
        result = validate_legal_compliance_evidence(load_legal_compliance_evidence(path), require_complete=require_complete)
        return "legal_compliance_ready", result
    if artifact_id == "wallet_custody_evidence":
        result = validate_wallet_custody_evidence(load_wallet_custody_evidence(path), require_complete=require_complete)
        return "wallet_custody_ready", result
    if artifact_id == "production_deployment_evidence":
        result = validate_production_deployment_evidence(load_production_deployment_evidence(path), require_complete=require_complete)
        return "deployment_ready", result
    raise KeyError(artifact_id)


def _validate_launch_authorization(data, errors, blockers, require_complete):
    authorization = data.get("launch_authorization")
    if not isinstance(authorization, dict):
        errors.append("launch_authorization must be an object.")
        return {"approved": False}
    if authorization.get("approved") is not True:
        blockers.append("launch_authorization_not_approved")
    for field in ("approver", "approved_at", "statement"):
        if not _non_empty(authorization.get(field)):
            blockers.append(f"launch_authorization_{field}_missing")
    if require_complete and any(blocker.startswith("launch_authorization_") for blocker in blockers):
        errors.append("Launch authorization is not complete.")
    return {
        "approved": authorization.get("approved") is True,
        "approver": authorization.get("approver") or "",
        "approved_at": authorization.get("approved_at") or "",
        "condition_count": len(authorization.get("conditions") or []),
    }


def validate_mainnet_decision(data, require_complete=False, verify_checksum_manifests=True):
    errors = []
    warnings = []
    blockers = []
    gate_results = {}
    artifact_results = {}
    verified_artifacts = []

    expected_ids = [artifact_id for artifact_id, _, _ in ARTIFACTS]
    if not isinstance(data, dict):
        return {
            "ok": False,
            "mainnet_decision_ready": False,
            "errors": ["Mainnet decision document must be a JSON object."],
            "warnings": [],
            "blockers": expected_ids,
        }

    if data.get("mode") != DECISION_MODE:
        errors.append(f"mode must equal {DECISION_MODE!r}.")
    if data.get("version") != DECISION_VERSION:
        errors.append(f"version must equal {DECISION_VERSION}.")
    if data.get("chain_id") != protocol.CHAIN_ID:
        errors.append(f"chain_id must equal {protocol.CHAIN_ID!r}.")

    reviewed_source_hash = _hash_value(data.get("reviewed_source_hash"))
    if not reviewed_source_hash:
        blockers.append("reviewed_source_hash_missing")
    elif not HASH_RE.fullmatch(reviewed_source_hash):
        errors.append("reviewed_source_hash must be a 64-character SHA-256 hash.")

    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict):
        errors.append("artifacts must be an object.")
        artifacts = {}

    for artifact_id in expected_ids:
        artifact_result = _validate_artifact(artifact_id, artifacts.get(artifact_id), errors, blockers)
        if artifact_result is None:
            continue
        artifact_results[artifact_id] = artifact_result
        if artifact_result.get("verified"):
            verified_artifacts.append(artifact_id)
        if artifact_id == "release_manifest" and artifact_result.get("exists"):
            artifact_result["manifest"] = _validate_release_manifest(
                _resolve_path(artifact_result["path"]),
                reviewed_source_hash,
                errors,
                blockers,
                require_complete,
            )
        elif artifact_id in ("release_bundle_sha256s", "security_review_packet_sha256s") and artifact_result.get("verified"):
            if not verify_checksum_manifests and not require_complete:
                artifact_result["checksum_manifest"] = {
                    "ok": False,
                    "checked": 0,
                    "skipped": True,
                    "errors": [],
                }
                warnings.append(f"{artifact_id}_entries_not_checked")
                continue
            checksum_result = _verify_sha256s(_resolve_path(artifact_result["path"]))
            artifact_result["checksum_manifest"] = checksum_result
            if not checksum_result.get("ok"):
                blockers.append(f"{artifact_id}_entries_not_verified")
                errors.extend(f"{artifact_id}_{err}" for err in checksum_result.get("errors") or [])
        elif artifact_id not in ("release_manifest", "release_bundle_sha256s", "security_review_packet_sha256s") and artifact_result.get("exists"):
            try:
                ready_key, gate_result = _run_gate_validator(
                    artifact_id,
                    _resolve_path(artifact_result["path"]),
                    require_complete=require_complete,
                )
            except (json.JSONDecodeError, OSError, ValueError) as exc:
                errors.append(f"{artifact_id}_validation_failed: {exc}")
                continue
            gate_ready = bool(gate_result.get(ready_key))
            gate_results[artifact_id] = {
                "ok": bool(gate_result.get("ok")),
                "ready": gate_ready,
                "ready_key": ready_key,
                "blockers": gate_result.get("blockers") or gate_result.get("blocker_gates") or [],
                "errors": gate_result.get("errors") or [],
            }
            if not gate_result.get("ok"):
                errors.extend(f"{artifact_id}: {err}" for err in gate_result.get("errors") or [])
            if not gate_ready:
                blockers.append(f"{artifact_id}_not_ready")

    authorization = _validate_launch_authorization(data, errors, blockers, require_complete)

    gate_artifacts = {
        "genesis_allocation",
        "manual_gate_evidence",
        "public_testnet_evidence",
        "security_review_evidence",
        "legal_compliance_evidence",
        "wallet_custody_evidence",
        "production_deployment_evidence",
    }
    complete_gate_count = sum(1 for artifact_id in gate_artifacts if gate_results.get(artifact_id, {}).get("ready"))
    checksum_artifacts_ready = all(
        artifact_results.get(artifact_id, {}).get("checksum_manifest", {}).get("ok")
        for artifact_id in ("release_bundle_sha256s", "security_review_packet_sha256s")
    )
    manifest_ready = bool(artifact_results.get("release_manifest", {}).get("manifest", {}).get("ok"))
    all_artifacts_verified = all(artifact_results.get(artifact_id, {}).get("verified") for artifact_id in expected_ids)
    blockers = sorted(set(blockers))

    mainnet_decision_ready = bool(
        not errors
        and not blockers
        and complete_gate_count == len(gate_artifacts)
        and checksum_artifacts_ready
        and manifest_ready
        and all_artifacts_verified
        and authorization.get("approved")
    )
    if require_complete and not mainnet_decision_ready:
        errors.append("Mainnet decision evidence is not complete.")

    return {
        "ok": not errors,
        "mainnet_decision_ready": mainnet_decision_ready,
        "mode": DECISION_MODE,
        "chain_id": data.get("chain_id"),
        "status": data.get("status"),
        "reviewed_source_hash": reviewed_source_hash,
        "required_artifact_count": len(expected_ids),
        "verified_artifact_count": len(verified_artifacts),
        "required_gate_count": len(gate_artifacts),
        "complete_gate_count": complete_gate_count,
        "launch_authorization": authorization,
        "artifacts": artifact_results,
        "gate_results": gate_results,
        "blockers": blockers,
        "errors": errors,
        "warnings": warnings,
    }


def write_mainnet_decision_workpapers(out_dir, artifact_paths=None):
    artifact_paths = artifact_paths or _artifact_path_map()
    artifact_workpapers = {}
    for artifact_id, _, label in ARTIFACTS:
        path = artifact_paths.get(artifact_id, "")
        artifact = _artifact(path, label) if path else {"exists": False, "sha256": ""}
        questions = "\n".join(
            f"- [ ] {question}"
            for question in ARTIFACT_REVIEW_QUESTIONS.get(artifact_id, ["Has this artifact been reviewed and accepted?"])
        )
        workpaper_path = Path("decision") / "artifacts" / f"{artifact_id}.md"
        write_text(out_dir / workpaper_path, "\n".join([
            f"# SpaceCash Mainnet Artifact Review: {label.title()}",
            "",
            f"- Artifact ID: `{artifact_id}`",
            f"- Current path: `{path or 'not set'}`",
            f"- Current SHA256: `{artifact.get('sha256') or 'not available'}`",
            f"- Exists now: `{artifact.get('exists')}`",
            "- Review status: `not_verified`",
            "- Reviewer:",
            "- Reviewed at:",
            "",
            "## Review Questions",
            "",
            questions,
            "",
            "## Decision Notes",
            "",
            "- Accepted: `false`",
            "- Required changes:",
            "- Replacement artifact path:",
            "- Replacement artifact SHA256:",
            "",
        ]))
        artifact_workpapers[artifact_id] = workpaper_path.as_posix()

    gate_workpapers = {}
    for gate_id, title, evidence_scope in MANUAL_GATE_WORKPAPERS:
        workpaper_path = Path("decision") / "gates" / f"{gate_id}.md"
        write_text(out_dir / workpaper_path, "\n".join([
            f"# SpaceCash Mainnet Gate Review: {title}",
            "",
            f"- Gate ID: `{gate_id}`",
            "- Gate status: `not_complete`",
            "- Reviewer:",
            "- Reviewed at:",
            "",
            "## Evidence Scope",
            "",
            evidence_scope,
            "",
            "## Required Checks",
            "",
            "- [ ] Gate-specific evidence JSON passes `--require-complete`.",
            "- [ ] Manual gate evidence references the same artifact hash.",
            "- [ ] Reviewer, timestamp, and final decision are present.",
            "- [ ] No conflicting blocker remains in the launch status report.",
            "",
            "## Decision Notes",
            "",
            "- Accepted: `false`",
            "- Conditions:",
            "- Follow-up owner:",
            "",
        ]))
        gate_workpapers[gate_id] = workpaper_path.as_posix()

    release_bundle_review = Path("decision") / "checksums" / "release_bundle_sha256s_review.md"
    write_text(out_dir / release_bundle_review, "\n".join([
        "# SpaceCash Release Bundle Checksum Review",
        "",
        "The top-level release bundle checksum file is generated after bundle contents are complete.",
        "Do not mark the final mainnet decision ready until the archived final bundle and its",
        "`SHA256SUMS.txt` have been verified together.",
        "",
        "- Bundle archive path:",
        "- SHA256SUMS path:",
        "- Verification command:",
        "- Verification result:",
        "- Archive location:",
        "- Reviewer:",
        "",
    ]))

    security_packet_review = Path("decision") / "checksums" / "security_review_packet_sha256s_review.md"
    write_text(out_dir / security_packet_review, "\n".join([
        "# SpaceCash Security Review Packet Checksum Review",
        "",
        "- Security-review packet path:",
        "- SHA256SUMS path:",
        "- Verification command:",
        "- Verification result:",
        "- Auditor packet reference:",
        "- Reviewer:",
        "",
    ]))

    source_freeze = Path("decision") / "reviewer" / "source_freeze_template.md"
    write_text(out_dir / source_freeze, "\n".join([
        "# SpaceCash Mainnet Source Freeze Template",
        "",
        "- Reviewed source hash:",
        "- Release manifest path:",
        "- Release manifest SHA256:",
        "- Freeze timestamp:",
        "- Change-control ticket:",
        "- Reviewer:",
        "",
        "## Freeze Rule",
        "",
        "Any source, configuration, manifest, or bundle change after this point requires a new",
        "release bundle, new checksums, and a new mainnet decision review.",
        "",
    ]))

    authorization = Path("decision") / "reviewer" / "final_launch_authorization_template.md"
    write_text(out_dir / authorization, "\n".join([
        "# SpaceCash Final Launch Authorization Template",
        "",
        "- Approved: `false`",
        "- Approver:",
        "- Approved at:",
        "- Reviewed source hash:",
        "- Release bundle SHA256:",
        "- Security review packet SHA256:",
        "- Conditions:",
        "",
        "## Required Statement",
        "",
        "The approver authorizes SpaceCash mainnet launch only after every upstream gate-specific",
        "evidence artifact passes require-complete validation and all checksums verify.",
        "",
        "## Stop Conditions",
        "",
        "- [ ] Any manual gate remains incomplete.",
        "- [ ] Any artifact hash is missing or mismatched.",
        "- [ ] Any release manifest check is not acceptable.",
        "- [ ] Any unresolved launch blocker appears in the launch status report.",
        "",
    ]))

    matrix = Path("decision") / "mainnet_go_no_go_matrix.md"
    write_text(out_dir / matrix, "\n".join([
        "# SpaceCash Mainnet Go/No-Go Matrix",
        "",
        "| Area | Current status | Required before go | Owner |",
        "| --- | --- | --- | --- |",
        "| Release manifest | not verified | source hash accepted and checks ok | |",
        "| Release bundle | not verified | final archive checksum verified | |",
        "| Genesis allocation | not approved | require-approved verifier passes | |",
        "| Manual gates | not complete | all manual gates complete | |",
        "| Public testnet | not complete | require-complete verifier passes | |",
        "| Security review | not complete | require-complete verifier passes | |",
        "| Legal/compliance | not complete | require-complete verifier passes | |",
        "| Wallet custody | not complete | require-complete verifier passes | |",
        "| Production deployment | not complete | require-complete verifier passes | |",
        "| Launch authorization | not approved | final approver signs authorization | |",
        "",
    ]))

    return {
        "artifact_workpapers": artifact_workpapers,
        "gate_workpapers": gate_workpapers,
        "release_bundle_checksum_review": release_bundle_review.as_posix(),
        "security_review_packet_checksum_review": security_packet_review.as_posix(),
        "source_freeze_template": source_freeze.as_posix(),
        "final_authorization_template": authorization.as_posix(),
        "go_no_go_matrix": matrix.as_posix(),
    }


def write_mainnet_decision_workbench(out_dir, workpapers, reviewed_source_hash="", artifact_paths=None):
    artifact_paths = artifact_paths or _artifact_path_map()
    payload = mainnet_decision_template()
    payload["status"] = "blocked"
    manifest_path = artifact_paths.get("release_manifest") or ""
    payload["reviewed_source_hash"] = reviewed_source_hash or _source_hash_from_manifest(manifest_path)
    for artifact_id, _, label in ARTIFACTS:
        artifact = _artifact(artifact_paths.get(artifact_id, ""), label)
        if artifact_id == "release_bundle_sha256s":
            artifact["sha256"] = ""
        payload["artifacts"][artifact_id] = artifact
    payload["launch_authorization"]["statement"] = (
        f"Use {workpapers['final_authorization_template']} for final mainnet launch authorization."
    )
    write_json(out_dir / "mainnet_decision_workbench.json", payload)
    return payload


def write_workbench_readme(out_dir, summary):
    write_text(out_dir / "README.md", "\n".join([
        "# SpaceCash Mainnet Decision Workbench",
        "",
        "This packet prepares final launch-decision review. It is not mainnet approval.",
        "",
        f"- Chain: `{summary['chain_id']}`",
        f"- Reviewed source hash: `{summary['reviewed_source_hash'] or 'not set'}`",
        f"- Mainnet decision ready: `{summary['mainnet_decision_ready']}`",
        f"- Verified artifacts: `{summary['verified_artifact_count']}` of `{summary['required_artifact_count']}`",
        f"- Complete gate artifacts: `{summary['complete_gate_count']}` of `{summary['required_gate_count']}`",
        f"- Manual gate: `{summary['manual_gate']['status']}`",
        "",
        "Reviewer order:",
        "",
        "1. Verify `SHA256SUMS.txt` for this workbench.",
        "2. Review `mainnet_decision_workbench.json` and `mainnet_decision_workbench_check.json`.",
        "3. Review every `decision/artifacts/*.md` file and replace template paths with completed evidence artifacts when they exist.",
        "4. Review every `decision/gates/*.md` file against completed manual gate evidence.",
        "5. Verify the release bundle and security packet checksum workpapers under `decision/checksums/`.",
        "6. Fill `decision/reviewer/source_freeze_template.md` after final source freeze.",
        "7. Fill `decision/reviewer/final_launch_authorization_template.md` only after every upstream gate is complete.",
        "8. Do not run a final approval with `--require-complete` until all blockers are gone.",
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


def build_mainnet_decision_workbench(out_dir=None, reviewed_source_hash="", artifact_paths=None, force=False):
    out_dir = Path(out_dir or default_workbench_dir())
    if out_dir.exists():
        if not force:
            raise ValueError(f"Mainnet decision workbench already exists: {out_dir}")
        safe_reset_dir(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    artifact_paths = _artifact_path_map(artifact_paths)
    workpapers = write_mainnet_decision_workpapers(out_dir, artifact_paths=artifact_paths)
    evidence = write_mainnet_decision_workbench(
        out_dir,
        workpapers,
        reviewed_source_hash=reviewed_source_hash,
        artifact_paths=artifact_paths,
    )
    check = validate_mainnet_decision(evidence)
    write_json(out_dir / "mainnet_decision_workbench_check.json", check)

    summary = {
        "ok": bool(check.get("ok") and not check.get("mainnet_decision_ready")),
        "mode": "spacecash-mainnet-decision-workbench-v1",
        "generated_at": protocol.utc_now(),
        "chain_id": protocol.CHAIN_ID,
        "out_dir": str(out_dir.resolve()),
        "reviewed_source_hash": evidence.get("reviewed_source_hash"),
        "mainnet_decision_ready": check.get("mainnet_decision_ready"),
        "verified_artifact_count": check.get("verified_artifact_count"),
        "required_artifact_count": check.get("required_artifact_count"),
        "complete_gate_count": check.get("complete_gate_count"),
        "required_gate_count": check.get("required_gate_count"),
        "launch_authorization": check.get("launch_authorization") or {},
        "blockers": check.get("blockers") or [],
        "errors": check.get("errors") or [],
        "warnings": check.get("warnings") or [],
        "artifact_paths": artifact_paths,
        "review_workpapers": workpapers,
        "required_outputs": [
            "completed public testnet evidence",
            "completed external security review evidence",
            "completed legal/compliance evidence",
            "completed wallet recovery/custody evidence",
            "completed production deployment evidence",
            "approved genesis allocation",
            "complete manual gate evidence",
            "verified release bundle checksums",
            "verified security-review packet checksums",
            "source freeze record",
            "final launch authorization",
        ],
        "manual_gate": {
            "id": "final_mainnet_decision",
            "status": "not_complete",
            "reason": "Final launch authorization and upstream gate evidence are still required.",
        },
    }
    write_json(out_dir / "mainnet_decision_workbench_summary.json", summary)
    write_workbench_readme(out_dir, summary)
    files = write_checksums(out_dir)
    result = dict(summary)
    result["files"] = files
    return result


def write_mainnet_decision_template(out_path=None):
    payload = mainnet_decision_template()
    if out_path:
        write_json(out_path, payload)
    return payload


def load_mainnet_decision(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_parser():
    parser = argparse.ArgumentParser(description="Create or verify SpaceCash final mainnet decision evidence JSON")
    parser.add_argument("--template-out", type=Path, help="Optional path to write the mainnet decision template")
    parser.add_argument("--verify", type=Path, help="Mainnet decision JSON file to verify")
    parser.add_argument("--require-complete", action="store_true", help="Fail unless the complete mainnet decision is approved")
    parser.add_argument("--workbench-out-dir", type=Path, help="Write a final mainnet decision review workbench packet")
    parser.add_argument("--reviewed-source-hash", default="", help="Optional reviewed source hash to seed into the workbench")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing workbench directory under _tmp")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.verify:
        result = validate_mainnet_decision(load_mainnet_decision(args.verify), require_complete=args.require_complete)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") and (not args.require_complete or result.get("mainnet_decision_ready")) else 2
    if args.workbench_out_dir:
        try:
            result = build_mainnet_decision_workbench(
                out_dir=args.workbench_out_dir,
                reviewed_source_hash=args.reviewed_source_hash,
                force=args.force,
            )
        except ValueError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 2
    payload = write_mainnet_decision_template(args.template_out)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
