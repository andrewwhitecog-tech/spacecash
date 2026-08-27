"""Verify SpaceCash public-testnet operator onboarding evidence."""

import argparse
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
from spacecash_public_testnet_evidence import REQUIRED_NODE_REPORTS, REQUIRED_SCENARIOS  # noqa: E402


CHECK_MODE = "spacecash-public-testnet-operator-onboarding-check-v1"
INTAKE_MODE = "spacecash-public-testnet-operator-intake-v1"
MANIFEST_MODE = "spacecash-public-testnet-operator-evidence-manifest-v1"
HASH_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$")
REQUIRED_SHARED_FILES = (
    "README.md",
    "contact_roster_template.md",
    "evidence_intake_checklist.md",
    "operator_commitment_template.md",
)
REQUIRED_PREFLIGHT_FLAGS = (
    "sha256s_verified",
    "start_command_tested",
    "backup_plan_recorded",
    "incident_channel_confirmed",
)
APPROVED_DECISIONS = ("approved", "approved_with_conditions")


def _non_empty(value):
    return isinstance(value, str) and bool(value.strip())


def _hash(value):
    return HASH_RE.fullmatch(str(value or "").strip()) is not None


def _resolve_operators_dir(path):
    path = Path(path)
    if path.name == "operators":
        return path
    return path / "operators"


def _load_json(path, errors):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"{path.as_posix()} could not be read: {exc}.")
    except json.JSONDecodeError as exc:
        errors.append(f"{path.as_posix()} is not valid JSON: {exc}.")
    return {}


def _review_complete(review):
    if not isinstance(review, dict):
        return False
    return (
        _non_empty(review.get("reviewer"))
        and _non_empty(review.get("reviewed_at"))
        and review.get("decision") in APPROVED_DECISIONS
    )


def _validate_intake(node_id, intake, errors, blockers, require_complete):
    if not isinstance(intake, dict):
        errors.append(f"{node_id}.operator_intake must be a JSON object.")
        return False, ""
    if intake.get("mode") != INTAKE_MODE:
        errors.append(f"{node_id}.operator_intake.mode must equal {INTAKE_MODE!r}.")
    if intake.get("chain_id") != protocol.CHAIN_ID:
        errors.append(f"{node_id}.operator_intake.chain_id must equal {protocol.CHAIN_ID!r}.")
    if intake.get("node_id") != node_id:
        errors.append(f"{node_id}.operator_intake.node_id must equal {node_id!r}.")
    node_url = str(intake.get("node_url") or "")
    if not URL_RE.fullmatch(node_url):
        errors.append(f"{node_id}.operator_intake.node_url must be an http(s) URL.")

    operator = intake.get("operator") if isinstance(intake.get("operator"), dict) else {}
    required_operator_fields = ("name", "contact", "timezone", "availability_window", "escalation_contact")
    missing_operator_fields = [field for field in required_operator_fields if not _non_empty(operator.get(field))]
    if missing_operator_fields:
        blockers.append(f"{node_id}.operator_identity_incomplete")
        if require_complete:
            errors.append(f"{node_id}.operator fields missing: {', '.join(missing_operator_fields)}.")
    if operator.get("independent_operator") is not True:
        blockers.append(f"{node_id}.not_independent_operator")
        if require_complete:
            errors.append(f"{node_id}.operator.independent_operator must be true.")

    preflight = intake.get("preflight") if isinstance(intake.get("preflight"), dict) else {}
    missing_preflight = []
    if not _hash(preflight.get("source_hash")):
        missing_preflight.append("source_hash")
    if not _hash(preflight.get("release_bundle_sha256")):
        missing_preflight.append("release_bundle_sha256")
    missing_preflight.extend(flag for flag in REQUIRED_PREFLIGHT_FLAGS if preflight.get(flag) is not True)
    if missing_preflight:
        blockers.append(f"{node_id}.preflight_incomplete")
        if require_complete:
            errors.append(f"{node_id}.preflight incomplete: {', '.join(missing_preflight)}.")

    if not _review_complete(intake.get("review")):
        blockers.append(f"{node_id}.operator_intake_not_approved")
        if require_complete:
            errors.append(f"{node_id}.operator_intake review must be approved.")

    ready = bool(
        not missing_operator_fields
        and operator.get("independent_operator") is True
        and not missing_preflight
        and _review_complete(intake.get("review"))
    )
    operator_key = str(operator.get("contact") or operator.get("name") or "").strip().lower()
    return ready, operator_key


def _validate_manifest(node_id, manifest, errors, blockers, require_complete):
    if not isinstance(manifest, dict):
        errors.append(f"{node_id}.evidence_manifest must be a JSON object.")
        return False
    if manifest.get("mode") != MANIFEST_MODE:
        errors.append(f"{node_id}.evidence_manifest.mode must equal {MANIFEST_MODE!r}.")
    if manifest.get("chain_id") != protocol.CHAIN_ID:
        errors.append(f"{node_id}.evidence_manifest.chain_id must equal {protocol.CHAIN_ID!r}.")
    if manifest.get("node_id") != node_id:
        errors.append(f"{node_id}.evidence_manifest.node_id must equal {node_id!r}.")

    missing_identity = []
    for field in ("operator", "operator_contact"):
        if not _non_empty(manifest.get(field)):
            missing_identity.append(field)
    for field in ("reviewed_source_hash", "release_bundle_sha256"):
        if not _hash(manifest.get(field)):
            missing_identity.append(field)
    if missing_identity:
        blockers.append(f"{node_id}.evidence_manifest_identity_incomplete")
        if require_complete:
            errors.append(f"{node_id}.evidence manifest fields missing: {', '.join(missing_identity)}.")

    reports = manifest.get("reports") if isinstance(manifest.get("reports"), dict) else {}
    missing_reports = []
    for report_type in REQUIRED_NODE_REPORTS:
        report = reports.get(report_type) if isinstance(reports.get(report_type), dict) else {}
        if (
            not _non_empty(report.get("path"))
            or not _hash(report.get("sha256"))
            or not _non_empty(report.get("collected_at"))
            or report.get("accepted") is not True
        ):
            missing_reports.append(report_type)
    if missing_reports:
        blockers.append(f"{node_id}.node_reports_incomplete")
        if require_complete:
            errors.append(f"{node_id}.reports incomplete: {', '.join(missing_reports)}.")

    daily_reports = manifest.get("daily_reports")
    if not isinstance(daily_reports, list) or not daily_reports:
        blockers.append(f"{node_id}.daily_reports_missing")
        if require_complete:
            errors.append(f"{node_id}.daily_reports must contain at least one report.")

    scenario_artifacts = manifest.get("scenario_artifacts")
    scenario_ids = {
        item.get("scenario_id") or item.get("id")
        for item in scenario_artifacts
        if isinstance(item, dict)
    } if isinstance(scenario_artifacts, list) else set()
    missing_scenarios = [scenario for scenario in REQUIRED_SCENARIOS if scenario not in scenario_ids]
    if missing_scenarios:
        blockers.append(f"{node_id}.scenario_artifacts_incomplete")
        if require_complete:
            errors.append(f"{node_id}.scenario artifacts missing: {', '.join(missing_scenarios)}.")

    unresolved = [
        incident.get("id") or f"incident[{index}]"
        for index, incident in enumerate(manifest.get("incidents") or [])
        if isinstance(incident, dict) and incident.get("status") not in ("closed", "accepted_risk")
    ]
    if unresolved:
        blockers.append(f"{node_id}.unresolved_incidents")
        if require_complete:
            errors.append(f"{node_id}.incidents unresolved: {', '.join(unresolved)}.")

    if not _review_complete(manifest.get("review")):
        blockers.append(f"{node_id}.evidence_manifest_not_approved")
        if require_complete:
            errors.append(f"{node_id}.evidence_manifest review must be approved.")

    return bool(
        not missing_identity
        and not missing_reports
        and isinstance(daily_reports, list)
        and bool(daily_reports)
        and not missing_scenarios
        and not unresolved
        and _review_complete(manifest.get("review"))
    )


def validate_operator_onboarding_packet(packet_dir, require_complete=False):
    errors = []
    warnings = []
    blockers = []
    operators_dir = _resolve_operators_dir(packet_dir)

    if not operators_dir.exists():
        return {
            "ok": False,
            "operator_onboarding_ready": False,
            "mode": CHECK_MODE,
            "chain_id": protocol.CHAIN_ID,
            "packet_path": "operators",
            "node_count": 0,
            "ready_node_count": 0,
            "independent_operators": 0,
            "blockers": ["operators_dir_missing"],
            "errors": [f"{operators_dir.as_posix()} is missing."],
            "warnings": [],
            "manual_gate": {
                "id": "public_testnet_complete",
                "status": "not_complete",
                "reason": "Operator onboarding packet is missing.",
            },
        }

    for rel in REQUIRED_SHARED_FILES:
        if not (operators_dir / rel).exists():
            errors.append(f"operators/{rel} is missing.")
            blockers.append(f"{rel}_missing")

    node_dirs = sorted(path for path in operators_dir.glob("node-*") if path.is_dir())
    if len(node_dirs) < 3:
        blockers.append("not_enough_operator_nodes")
        if require_complete:
            errors.append("At least three operator node folders are required.")

    ready_nodes = 0
    operator_keys = set()
    for node_dir in node_dirs:
        node_id = node_dir.name
        intake_path = node_dir / "operator_intake.json"
        manifest_path = node_dir / "evidence_manifest_template.json"
        if not intake_path.exists():
            errors.append(f"operators/{node_id}/operator_intake.json is missing.")
            blockers.append(f"{node_id}.operator_intake_missing")
            continue
        if not manifest_path.exists():
            errors.append(f"operators/{node_id}/evidence_manifest_template.json is missing.")
            blockers.append(f"{node_id}.evidence_manifest_missing")
            continue
        intake_ready, operator_key = _validate_intake(
            node_id,
            _load_json(intake_path, errors),
            errors,
            blockers,
            require_complete,
        )
        manifest_ready = _validate_manifest(
            node_id,
            _load_json(manifest_path, errors),
            errors,
            blockers,
            require_complete,
        )
        if operator_key:
            operator_keys.add(operator_key)
        if intake_ready and manifest_ready:
            ready_nodes += 1

    if len(operator_keys) < 3:
        blockers.append("not_enough_independent_operators")
        if require_complete:
            errors.append("At least three distinct independent operators are required.")

    operator_onboarding_ready = bool(not errors and not blockers and ready_nodes >= 3 and len(operator_keys) >= 3)
    if require_complete and not operator_onboarding_ready:
        errors.append("Operator onboarding packet is not complete.")

    return {
        "ok": not errors,
        "operator_onboarding_ready": operator_onboarding_ready,
        "mode": CHECK_MODE,
        "chain_id": protocol.CHAIN_ID,
        "packet_path": "operators",
        "node_count": len(node_dirs),
        "ready_node_count": ready_nodes,
        "independent_operators": len(operator_keys),
        "required_node_count": 3,
        "required_report_count": len(REQUIRED_NODE_REPORTS),
        "required_scenario_count": len(REQUIRED_SCENARIOS),
        "blockers": sorted(set(blockers)),
        "errors": errors,
        "warnings": warnings,
        "manual_gate": {
            "id": "public_testnet_complete",
            "status": "complete" if operator_onboarding_ready else "not_complete",
            "reason": (
                "Operator onboarding intakes, evidence manifests, and reviews are complete."
                if operator_onboarding_ready
                else "Operator intakes, preflight confirmations, evidence manifests, and reviews are required."
            ),
        },
    }


def write_operator_onboarding_check(packet_dir, out_path=None, require_complete=False):
    result = validate_operator_onboarding_packet(packet_dir, require_complete=require_complete)
    if out_path:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def build_parser():
    parser = argparse.ArgumentParser(description="Verify SpaceCash public-testnet operator onboarding packet")
    parser.add_argument("--verify", type=Path, required=True, help="Testnet package directory or operators directory to verify")
    parser.add_argument("--out", type=Path, help="Optional JSON path for the onboarding check result")
    parser.add_argument("--require-complete", action="store_true", help="Fail unless operator onboarding is complete")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    result = write_operator_onboarding_check(args.verify, args.out, require_complete=args.require_complete)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") and (not args.require_complete or result.get("operator_onboarding_ready")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
