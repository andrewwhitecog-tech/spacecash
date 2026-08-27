"""Create and verify SpaceCash manual mainnet-gate evidence files."""

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


EVIDENCE_MODE = "spacecash-mainnet-gate-evidence-v1"
EVIDENCE_VERSION = 1
HASH_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
GATE_STATUSES = ("blocked", "in_progress", "complete", "accepted_risk")


GATE_DEFINITIONS = (
    {
        "id": "public_testnet_complete",
        "title": "Public Testnet",
        "required_evidence": (
            "reviewed_source_hash",
            "release_bundle_sha256",
            "node_operator_list",
            "bootstrap_peer_report",
            "incident_log",
            "final_testnet_report",
        ),
    },
    {
        "id": "external_security_review_complete",
        "title": "External Security Review",
        "required_evidence": (
            "reviewed_source_hash",
            "security_packet_sha256",
            "auditor_or_firm",
            "signed_audit_scope",
            "findings_log",
            "remediation_evidence",
            "auditor_closure_statement",
        ),
    },
    {
        "id": "legal_compliance_review_complete",
        "title": "Legal And Compliance Review",
        "required_evidence": (
            "reviewed_source_hash",
            "genesis_allocation_hash",
            "allocation_verifier_output",
            "approved_use_case",
            "prohibited_use_cases",
            "required_disclosures",
            "tax_and_payment_position",
            "final_decision",
        ),
    },
    {
        "id": "wallet_recovery_custody_policy_complete",
        "title": "Wallet Recovery And Custody Policy",
        "required_evidence": (
            "wallet_policy_hash",
            "recovery_standard",
            "address_versioning_decision",
            "backup_rotation_policy",
            "lost_key_procedure",
            "compromised_key_procedure",
            "custody_or_hardware_wallet_decision",
        ),
    },
    {
        "id": "production_deployment_runbook_complete",
        "title": "Production Deployment Runbook",
        "required_evidence": (
            "reviewed_source_hash",
            "release_manifest_sha256",
            "release_bundle_sha256",
            "deployment_runbook",
            "monitoring_plan",
            "rollback_procedure",
            "incident_response_plan",
        ),
    },
)


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def _default_artifacts():
    candidates = (
        "_tmp/spacecash_release_manifest.json",
        "_tmp/spacecash_release_bundle/SHA256SUMS.txt",
        "_tmp/spacecash_security_review_packet/SHA256SUMS.txt",
        "docs/spacecash/MAINNET_GATE.md",
        "docs/spacecash/MANUAL_GATES.md",
        "docs/spacecash/PUBLIC_TESTNET_RUNBOOK.md",
        "docs/spacecash/SECURITY_AUDIT_SCOPE.md",
        "docs/spacecash/LEGAL_COMPLIANCE_GATE.md",
        "docs/spacecash/WALLET_RECOVERY_CUSTODY_POLICY.md",
        "docs/spacecash/PRODUCTION_DEPLOYMENT_RUNBOOK.md",
    )
    artifacts = []
    for rel in candidates:
        path = ROOT / rel
        artifacts.append({
            "path": rel,
            "sha256": file_hash(path) if path.exists() else "",
            "exists": path.exists(),
        })
    return artifacts


def _empty_gate(definition):
    return {
        "id": definition["id"],
        "title": definition["title"],
        "status": "blocked",
        "required_evidence": list(definition["required_evidence"]),
        "evidence": {field: "" for field in definition["required_evidence"]},
        "review": {
            "reviewer": "",
            "role": "",
            "reviewed_at": "",
            "decision": "not_reviewed",
            "notes": "",
        },
    }


def gate_evidence_template():
    template = {
        "mode": EVIDENCE_MODE,
        "version": EVIDENCE_VERSION,
        "chain_id": protocol.CHAIN_ID,
        "status": "blocked",
        "protocol_hashes": {
            "consensus_spec_hash": protocol.consensus_spec_hash(),
            "monetary_policy_hash": protocol.monetary_policy_hash(),
            "genesis_plan_hash": protocol.genesis_plan_hash(),
            "genesis_allocation_hash": genesis_allocation_template().get("allocation_hash"),
            "wallet_policy_hash": protocol.wallet_policy_hash(),
        },
        "artifacts": _default_artifacts(),
        "gates": [_empty_gate(definition) for definition in GATE_DEFINITIONS],
        "mainnet_rule": "All gates must be complete with reviewed evidence before SpaceCash can be described as mainnet.",
    }
    return template


def _is_non_empty(value):
    return isinstance(value, str) and bool(value.strip())


def _looks_like_hash_field(field):
    return field.endswith("_hash") or field.endswith("_sha256") or field == "reviewed_source_hash"


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
        if not _is_non_empty(rel):
            errors.append(f"{prefix}.path is required.")
            continue
        path = ROOT / rel
        claimed = str(artifact.get("sha256") or "").strip().upper()
        exists = path.exists()
        if artifact.get("exists") is True and not exists:
            errors.append(f"{prefix}.exists is true but the file is missing.")
        if exists and claimed:
            actual = file_hash(path)
            if claimed != actual:
                errors.append(f"{prefix}.sha256 does not match {rel}.")
            else:
                verified.append(rel)
        elif not exists:
            warnings.append(f"{rel} is not present yet.")
    return verified


def validate_gate_evidence(data, require_complete=False):
    errors = []
    warnings = []
    complete_gates = []
    blocker_gates = []
    expected_ids = [definition["id"] for definition in GATE_DEFINITIONS]
    definitions = {definition["id"]: definition for definition in GATE_DEFINITIONS}

    if not isinstance(data, dict):
        return {
            "ok": False,
            "mainnet_manual_ready": False,
            "errors": ["Gate evidence document must be a JSON object."],
            "warnings": [],
            "complete_gates": [],
            "blocker_gates": expected_ids,
        }

    if data.get("mode") != EVIDENCE_MODE:
        errors.append(f"mode must equal {EVIDENCE_MODE!r}.")
    if data.get("version") != EVIDENCE_VERSION:
        errors.append(f"version must equal {EVIDENCE_VERSION}.")
    if data.get("chain_id") != protocol.CHAIN_ID:
        errors.append(f"chain_id must equal {protocol.CHAIN_ID!r}.")

    expected_hashes = gate_evidence_template()["protocol_hashes"]
    hashes = data.get("protocol_hashes")
    if not isinstance(hashes, dict):
        errors.append("protocol_hashes must be an object.")
        hashes = {}
    for field, expected in expected_hashes.items():
        if hashes.get(field) != expected:
            errors.append(f"protocol_hashes.{field} must equal {expected}.")

    verified_artifacts = _validate_artifacts(data.get("artifacts") or [], errors, warnings)

    gates = data.get("gates")
    if not isinstance(gates, list):
        errors.append("gates must be a list.")
        gates = []
    by_id = {}
    for index, gate in enumerate(gates):
        prefix = f"gates[{index}]"
        if not isinstance(gate, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        gate_id = gate.get("id")
        if gate_id not in definitions:
            errors.append(f"{prefix}.id is not a known manual gate.")
            continue
        if gate_id in by_id:
            errors.append(f"{prefix}.id duplicates an earlier manual gate.")
            continue
        by_id[gate_id] = gate

    for gate_id in expected_ids:
        definition = definitions[gate_id]
        gate = by_id.get(gate_id)
        if gate is None:
            errors.append(f"Missing gate {gate_id}.")
            blocker_gates.append(gate_id)
            continue
        status = gate.get("status")
        if status not in GATE_STATUSES:
            errors.append(f"{gate_id}.status must be one of {', '.join(GATE_STATUSES)}.")
        evidence = gate.get("evidence") if isinstance(gate.get("evidence"), dict) else {}
        review = gate.get("review") if isinstance(gate.get("review"), dict) else {}
        required = list(definition["required_evidence"])
        if gate.get("required_evidence") != required:
            errors.append(f"{gate_id}.required_evidence does not match the v1 gate schema.")

        gate_errors = []
        must_be_complete = require_complete or status == "complete"
        if must_be_complete:
            for field in required:
                value = evidence.get(field)
                if not _is_non_empty(value):
                    gate_errors.append(f"{gate_id}.evidence.{field} is required.")
                elif _looks_like_hash_field(field) and not HASH_RE.fullmatch(str(value).strip()):
                    gate_errors.append(f"{gate_id}.evidence.{field} must be a 64-character SHA-256 hash.")
            for field in ("reviewer", "role", "reviewed_at"):
                if not _is_non_empty(review.get(field)):
                    gate_errors.append(f"{gate_id}.review.{field} is required.")
            if review.get("decision") not in ("approved", "approved_with_conditions"):
                gate_errors.append(f"{gate_id}.review.decision must be approved or approved_with_conditions.")
        if gate_errors:
            errors.extend(gate_errors)

        if status == "complete" and not gate_errors:
            complete_gates.append(gate_id)
        else:
            blocker_gates.append(gate_id)
            if status != "complete":
                warnings.append(f"{gate_id} is not complete.")

    mainnet_manual_ready = bool(not errors and not blocker_gates and len(complete_gates) == len(expected_ids))
    if require_complete and not mainnet_manual_ready:
        errors.append("Manual gate evidence is not complete.")
    return {
        "ok": not errors,
        "mainnet_manual_ready": mainnet_manual_ready,
        "mode": EVIDENCE_MODE,
        "chain_id": data.get("chain_id"),
        "complete_gates": complete_gates,
        "blocker_gates": blocker_gates,
        "verified_artifacts": verified_artifacts,
        "artifact_count": len(data.get("artifacts") or []),
        "errors": errors,
        "warnings": warnings,
    }


def write_gate_evidence_template(out_path=None):
    payload = gate_evidence_template()
    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def load_gate_evidence(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_parser():
    parser = argparse.ArgumentParser(description="Create or verify SpaceCash manual mainnet-gate evidence JSON")
    parser.add_argument("--template-out", type=Path, help="Optional path to write the evidence template")
    parser.add_argument("--verify", type=Path, help="Gate evidence JSON file to verify")
    parser.add_argument("--require-complete", action="store_true", help="Fail unless every manual gate is complete")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.verify:
        result = validate_gate_evidence(load_gate_evidence(args.verify), require_complete=args.require_complete)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") and (not args.require_complete or result.get("mainnet_manual_ready")) else 2
    payload = write_gate_evidence_template(args.template_out)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
