"""Create and verify SpaceCash public-testnet exit evidence."""

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


EVIDENCE_MODE = "spacecash-public-testnet-exit-evidence-v1"
EVIDENCE_VERSION = 1
HASH_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$")
REQUIRED_SCENARIOS = (
    "node_health_and_readiness",
    "signed_transfer",
    "product_payment",
    "checkpoint_quorum",
    "peer_gossip",
    "sync_preview",
    "guarded_import",
    "node_restart_recovery",
    "incident_response",
)
REQUIRED_NODE_REPORTS = (
    "health_report",
    "readiness_report",
    "audit_report",
    "chain_manifest",
    "checkpoint_report",
    "peer_report",
)

SCENARIO_REVIEW_QUESTIONS = {
    "node_health_and_readiness": [
        "Did every independently operated node expose health, readiness, audit, and manifest output?",
        "Did every node remain an automated release candidate while reporting mainnet_ready false?",
    ],
    "signed_transfer": [
        "Was at least one signed wallet transfer accepted and visible in audit output?",
        "Were sender, recipient, amount, txid, and signed payload archived?",
    ],
    "product_payment": [
        "Was a product-payment flow exercised with request, signed payload, receipt, and order status?",
        "Were any refund, failure, or fulfillment edge cases documented?",
    ],
    "checkpoint_quorum": [
        "Did validator checkpoint votes reach quorum after the scenario?",
        "Were votes and quorum output archived from multiple nodes?",
    ],
    "peer_gossip": [
        "Did peer discovery, peer checks, and gossip produce expected peer visibility?",
        "Were unreachable, duplicate, or divergent peers recorded?",
    ],
    "sync_preview": [
        "Did sync-preview classify same, ahead, behind, and diverged peer states when available?",
        "Were unsafe imports rejected or documented for guarded import review?",
    ],
    "guarded_import": [
        "Was append-only guarded import rehearsed from an approved peer candidate?",
        "Were pre-import backup, import result, and post-import audit archived?",
    ],
    "node_restart_recovery": [
        "Did every node restart and recover health/readiness/audit/checkpoint output?",
        "Were restart windows, operator actions, and recovery notes archived?",
    ],
    "incident_response": [
        "Were incidents opened, triaged, and closed or explicitly accepted-risk?",
        "Did reviewer notes identify any unresolved launch blockers?",
    ],
}

NODE_REPORT_REVIEW_QUESTIONS = {
    "health_report": ["Does /health show the expected node identity and service status?"],
    "readiness_report": ["Does /readiness preserve automated release status while keeping mainnet_ready false?"],
    "audit_report": ["Does /audit show no integrity errors, no legacy unsigned spends, and no warning drift?"],
    "chain_manifest": ["Does /chain/manifest match the reviewed source and candidate chain hash expectations?"],
    "checkpoint_report": ["Do checkpoint quorum and votes meet the validator quorum requirement?"],
    "peer_report": ["Do peer checks and gossip output document expected bootstrap and discovered peers?"],
}


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def default_workbench_dir():
    stamp = protocol.utc_now().replace(":", "").replace("-", "").replace("Z", "Z")
    return ROOT / "_tmp" / f"spacecash_public_testnet_workbench_{stamp}_{secrets.token_hex(4)}"


def safe_reset_dir(path):
    path = Path(path).resolve()
    tmp_root = (ROOT / "_tmp").resolve()
    if path == tmp_root or tmp_root not in path.parents:
        raise ValueError("Refusing to overwrite a public-testnet workbench outside the project _tmp directory.")
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


def _artifact(rel):
    path = ROOT / rel
    return {
        "path": rel,
        "exists": path.exists(),
        "sha256": file_hash(path) if path.exists() else "",
    }


def _default_artifacts():
    return [
        _artifact("_tmp/spacecash_release_bundle/SHA256SUMS.txt"),
        _artifact("_tmp/spacecash_release_bundle/testnet/testnet_plan.json"),
        _artifact("_tmp/spacecash_release_bundle/testnet/operator_checklist.md"),
        _artifact("_tmp/spacecash_release_bundle/testnet/incident_log.md"),
        _artifact("_tmp/spacecash_release_bundle/testnet_rehearsal/rehearsal_report.json"),
        _artifact("docs/spacecash/PUBLIC_TESTNET_RUNBOOK.md"),
    ]


def _empty_node(index):
    return {
        "node_id": f"node-{index + 1:02d}",
        "operator": "",
        "operator_contact": "",
        "url": "",
        "independently_operated": False,
        "reports": {name: "" for name in REQUIRED_NODE_REPORTS},
    }


def public_testnet_evidence_template(node_count=3):
    node_count = max(3, int(node_count or 3))
    return {
        "mode": EVIDENCE_MODE,
        "version": EVIDENCE_VERSION,
        "chain_id": protocol.CHAIN_ID,
        "status": "not_run",
        "minimums": {
            "nodes": 3,
            "independent_operators": 3,
            "duration_days": 7,
        },
        "protocol_hashes": {
            "consensus_spec_hash": protocol.consensus_spec_hash(),
            "monetary_policy_hash": protocol.monetary_policy_hash(),
            "genesis_plan_hash": protocol.genesis_plan_hash(),
            "wallet_policy_hash": protocol.wallet_policy_hash(),
        },
        "artifacts": _default_artifacts(),
        "duration_days": 0,
        "nodes": [_empty_node(index) for index in range(node_count)],
        "scenarios": [
            {"id": scenario, "status": "not_run", "evidence": "", "notes": ""}
            for scenario in REQUIRED_SCENARIOS
        ],
        "incidents": [],
        "final_report": {
            "path": "",
            "sha256": "",
            "reviewer": "",
            "reviewed_at": "",
            "decision": "not_reviewed",
            "notes": "",
        },
        "manual_gate": {
            "id": "public_testnet_complete",
            "status": "not_complete",
            "reason": "Independently operated public nodes, scenario evidence, incident closure, and final reviewer approval are required.",
        },
    }


def _non_empty(value):
    return isinstance(value, str) and bool(value.strip())


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


def validate_public_testnet_evidence(data, require_complete=False):
    errors = []
    warnings = []
    blockers = []

    if not isinstance(data, dict):
        return {
            "ok": False,
            "public_testnet_ready": False,
            "errors": ["Public testnet evidence must be a JSON object."],
            "warnings": [],
            "blockers": ["schema"],
        }

    if data.get("mode") != EVIDENCE_MODE:
        errors.append(f"mode must equal {EVIDENCE_MODE!r}.")
    if data.get("version") != EVIDENCE_VERSION:
        errors.append(f"version must equal {EVIDENCE_VERSION}.")
    if data.get("chain_id") != protocol.CHAIN_ID:
        errors.append(f"chain_id must equal {protocol.CHAIN_ID!r}.")

    expected_hashes = public_testnet_evidence_template()["protocol_hashes"]
    hashes = data.get("protocol_hashes") if isinstance(data.get("protocol_hashes"), dict) else {}
    for field, expected in expected_hashes.items():
        if hashes.get(field) != expected:
            errors.append(f"protocol_hashes.{field} must equal {expected}.")

    verified_artifacts = _validate_artifacts(data.get("artifacts") or [], errors, warnings)

    minimums = data.get("minimums") if isinstance(data.get("minimums"), dict) else {}
    min_nodes = int(minimums.get("nodes") or 3)
    min_operators = int(minimums.get("independent_operators") or 3)
    min_duration = int(minimums.get("duration_days") or 7)
    duration_days = data.get("duration_days")
    if not isinstance(duration_days, int) or isinstance(duration_days, bool) or duration_days < 0:
        errors.append("duration_days must be a non-negative integer.")
        duration_days = 0

    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        errors.append("nodes must be a list.")
        nodes = []
    if len(nodes) < min_nodes:
        blockers.append("not_enough_nodes")

    operators = set()
    node_count_ready = 0
    for index, node in enumerate(nodes):
        prefix = f"nodes[{index}]"
        if not isinstance(node, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        if not _non_empty(node.get("node_id")):
            errors.append(f"{prefix}.node_id is required.")
        if _non_empty(node.get("operator")):
            operators.add(str(node.get("operator")).strip().lower())
        if not URL_RE.fullmatch(str(node.get("url") or "")):
            if require_complete or data.get("status") == "complete":
                errors.append(f"{prefix}.url must be an http(s) URL.")
        if node.get("independently_operated") is not True:
            blockers.append(f"{prefix}.not_independently_operated")
        reports = node.get("reports") if isinstance(node.get("reports"), dict) else {}
        missing_reports = [name for name in REQUIRED_NODE_REPORTS if not _non_empty(reports.get(name))]
        if missing_reports and (require_complete or data.get("status") == "complete"):
            errors.append(f"{prefix}.reports missing: {', '.join(missing_reports)}.")
        if not missing_reports and node.get("independently_operated") is True and _non_empty(node.get("operator")):
            node_count_ready += 1

    if len(operators) < min_operators:
        blockers.append("not_enough_independent_operators")
    if duration_days < min_duration:
        blockers.append("duration_below_minimum")

    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list):
        errors.append("scenarios must be a list.")
        scenarios = []
    scenarios_by_id = {}
    for index, scenario in enumerate(scenarios):
        prefix = f"scenarios[{index}]"
        if not isinstance(scenario, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        scenario_id = scenario.get("id")
        if scenario_id not in REQUIRED_SCENARIOS:
            errors.append(f"{prefix}.id is not a required testnet scenario.")
            continue
        if scenario_id in scenarios_by_id:
            errors.append(f"{prefix}.id duplicates an earlier scenario.")
            continue
        scenarios_by_id[scenario_id] = scenario
    for scenario_id in REQUIRED_SCENARIOS:
        scenario = scenarios_by_id.get(scenario_id)
        if not scenario:
            errors.append(f"Missing scenario {scenario_id}.")
            blockers.append(f"{scenario_id}_missing")
            continue
        if scenario.get("status") != "pass":
            blockers.append(f"{scenario_id}_not_passed")
        if (require_complete or data.get("status") == "complete") and not _non_empty(scenario.get("evidence")):
            errors.append(f"{scenario_id}.evidence is required.")

    incidents = data.get("incidents")
    if not isinstance(incidents, list):
        errors.append("incidents must be a list.")
        incidents = []
    unresolved = [
        incident.get("id") or f"incident[{index}]"
        for index, incident in enumerate(incidents)
        if isinstance(incident, dict) and incident.get("status") not in ("closed", "accepted_risk")
    ]
    if unresolved:
        blockers.append("unresolved_incidents")

    final_report = data.get("final_report") if isinstance(data.get("final_report"), dict) else {}
    final_report_complete = (
        _non_empty(final_report.get("path"))
        and HASH_RE.fullmatch(str(final_report.get("sha256") or "").strip()) is not None
        and _non_empty(final_report.get("reviewer"))
        and _non_empty(final_report.get("reviewed_at"))
        and final_report.get("decision") in ("approved", "approved_with_conditions")
    )
    if not final_report_complete:
        blockers.append("final_report_not_approved")
        if require_complete or data.get("status") == "complete":
            errors.append("final_report must include path, sha256, reviewer, reviewed_at, and approved decision.")

    manual_gate = data.get("manual_gate") if isinstance(data.get("manual_gate"), dict) else {}
    manual_gate_complete = (
        manual_gate.get("id") == "public_testnet_complete"
        and manual_gate.get("status") == "complete"
    )
    if not manual_gate_complete:
        blockers.append("manual_gate_not_complete")

    if require_complete or data.get("status") == "complete":
        if data.get("status") != "complete":
            errors.append("status must be complete for public testnet exit evidence.")
        if not manual_gate_complete:
            errors.append("manual_gate public_testnet_complete must be complete.")

    public_testnet_ready = bool(not errors and not blockers and data.get("status") == "complete" and manual_gate_complete)
    if require_complete and not public_testnet_ready:
        errors.append("Public testnet evidence is not complete.")

    return {
        "ok": not errors,
        "public_testnet_ready": public_testnet_ready,
        "mode": EVIDENCE_MODE,
        "chain_id": data.get("chain_id"),
        "duration_days": duration_days,
        "node_count": len(nodes),
        "ready_node_count": node_count_ready,
        "independent_operators": len(operators),
        "scenario_count": len(scenarios_by_id),
        "verified_artifacts": verified_artifacts,
        "unresolved_incidents": unresolved,
        "blockers": sorted(set(blockers)),
        "errors": errors,
        "warnings": warnings,
    }


def write_public_testnet_workpapers(out_dir):
    scenario_paths = []
    for scenario_id in REQUIRED_SCENARIOS:
        rel = Path("testnet") / "scenarios" / f"{scenario_id}.md"
        questions = "\n".join(f"- [ ] {question}" for question in SCENARIO_REVIEW_QUESTIONS.get(scenario_id, []))
        write_text(out_dir / rel, "\n".join([
            f"# SpaceCash Public Testnet Scenario: {scenario_id.replace('_', ' ').title()}",
            "",
            f"- Scenario ID: `{scenario_id}`",
            "- Status: `not_run`",
            "- Operator:",
            "- Started at:",
            "- Finished at:",
            "- Reviewer:",
            "- Review decision: `not_reviewed`",
            "",
            "## Review Questions",
            "",
            questions,
            "",
            "## Evidence",
            "",
            "- Source hash:",
            "- Release bundle SHA256:",
            "- Node IDs:",
            "- Artifacts:",
            "- Incident references:",
            "",
            "## Notes",
            "",
            "- Conditions:",
            "- Follow-up required:",
            "",
        ]))
        scenario_paths.append(rel.as_posix())

    report_paths = []
    for report_type in REQUIRED_NODE_REPORTS:
        rel = Path("testnet") / "node_reports" / f"{report_type}.md"
        questions = "\n".join(f"- [ ] {question}" for question in NODE_REPORT_REVIEW_QUESTIONS.get(report_type, []))
        write_text(out_dir / rel, "\n".join([
            f"# SpaceCash Node Report Review: {report_type.replace('_', ' ').title()}",
            "",
            f"- Report type: `{report_type}`",
            "- Status: `not_collected`",
            "- Nodes covered:",
            "- Reviewer:",
            "- Reviewed at:",
            "",
            "## Review Questions",
            "",
            questions,
            "",
            "## Required Attachments",
            "",
            "- node-01 report path:",
            "- node-02 report path:",
            "- node-03 report path:",
            "- Hashes:",
            "",
        ]))
        report_paths.append(rel.as_posix())

    operator_roster_path = Path("testnet") / "operators" / "operator_roster_review.md"
    write_text(out_dir / operator_roster_path, "\n".join([
        "# SpaceCash Public Testnet Operator Roster Review",
        "",
        "- Status: `not_reviewed`",
        "- Reviewer:",
        "- Reviewed at:",
        "",
        "## Required Checks",
        "",
        "- [ ] At least three independent operators are identified.",
        "- [ ] Every operator completed `operator_intake.json`.",
        "- [ ] Every operator verified release bundle checksums.",
        "- [ ] Every operator has an escalation contact and availability window.",
        "- [ ] Every node has a completed evidence manifest.",
        "- [ ] `tools\\nsp_python.cmd tools\\spacecash_operator_onboarding.py --require-complete` passes.",
        "",
    ]))

    incident_review_path = Path("testnet") / "incidents" / "incident_response_review.md"
    write_text(out_dir / incident_review_path, "\n".join([
        "# SpaceCash Public Testnet Incident Response Review",
        "",
        "- Status: `not_reviewed`",
        "- Reviewer:",
        "- Reviewed at:",
        "",
        "## Required Checks",
        "",
        "- [ ] Every incident has an owner, severity, opened time, and resolution.",
        "- [ ] Incidents are closed or explicitly accepted-risk.",
        "- [ ] Any unresolved issue is listed as a launch blocker.",
        "- [ ] Final report includes incident summary and reviewer decision.",
        "",
    ]))

    reviewer_ticket_path = Path("testnet") / "reviewer" / "review_ticket_template.md"
    write_text(out_dir / reviewer_ticket_path, "\n".join([
        "# SpaceCash Public Testnet Review Ticket Template",
        "",
        "- Reviewer name:",
        "- Role:",
        "- Contact:",
        "- Reviewed source hash:",
        "- Release bundle SHA256:",
        "- Reviewed at:",
        "",
        "## Scope Acceptance",
        "",
        "The reviewer accepts the public-testnet scope in",
        "`docs/spacecash/PUBLIC_TESTNET_RUNBOOK.md` and the workpapers in this package.",
        "",
    ]))

    final_report_path = Path("testnet") / "final_public_testnet_report_template.md"
    write_text(out_dir / final_report_path, "\n".join([
        "# SpaceCash Final Public Testnet Report Template",
        "",
        "- Status: `not_reviewed`",
        "- Duration days:",
        "- Reviewer:",
        "- Reviewed at:",
        "- Decision: `not_reviewed`",
        "- Reviewed source hash:",
        "- Release bundle SHA256:",
        "",
        "## Required Summary",
        "",
        "- Nodes and operators:",
        "- Scenario results:",
        "- Incidents and accepted risks:",
        "- Final blockers:",
        "- Required follow-up:",
        "",
        "## Gate Note",
        "",
        "Do not mark `public_testnet_complete` complete until the final public-testnet",
        "evidence JSON passes `--require-complete` and the manual gate is explicitly approved.",
        "",
    ]))

    return {
        "scenario_workpapers": scenario_paths,
        "node_report_workpapers": report_paths,
        "operator_roster_review": operator_roster_path.as_posix(),
        "incident_response_review": incident_review_path.as_posix(),
        "review_ticket_template": reviewer_ticket_path.as_posix(),
        "final_report_template": final_report_path.as_posix(),
    }


def write_public_testnet_evidence_workbench(out_dir, workpapers, reviewed_source_hash="", release_bundle_sha256=""):
    payload = public_testnet_evidence_template(node_count=3)
    payload["status"] = "not_run"
    payload["reviewed_source_hash"] = reviewed_source_hash or ""
    payload["release_bundle_sha256"] = release_bundle_sha256 or ""
    payload["duration_days"] = 0
    for node in payload["nodes"]:
        node_id = node["node_id"]
        node["url"] = f"http://127.0.0.1:{18875 + int(node_id.split('-')[-1])}"
        node["reports"] = {
            report_type: f"reports/{node_id}/{report_type}.json"
            for report_type in REQUIRED_NODE_REPORTS
        }
    scenario_paths = {Path(path).stem: path for path in workpapers.get("scenario_workpapers", [])}
    for scenario in payload["scenarios"]:
        scenario["evidence"] = scenario_paths.get(scenario["id"], "")
    payload["final_report"]["path"] = workpapers["final_report_template"]
    payload["final_report"]["sha256"] = _hash_relative(out_dir, workpapers["final_report_template"])
    payload["final_report"]["notes"] = "Seeded from the public-testnet workbench template; not yet approved."
    write_json(out_dir / "public_testnet_evidence_workbench.json", payload)
    return payload


def write_workbench_readme(out_dir, summary):
    write_text(out_dir / "README.md", "\n".join([
        "# SpaceCash Public Testnet Workbench",
        "",
        "This package prepares public-testnet review evidence. It is not public-testnet completion approval.",
        "",
        f"- Chain: `{summary['chain_id']}`",
        f"- Source hash: `{summary['reviewed_source_hash'] or 'not set'}`",
        f"- Release bundle SHA256: `{summary['release_bundle_sha256'] or 'not set'}`",
        f"- Public testnet ready: `{summary['public_testnet_ready']}`",
        f"- Ready nodes: `{summary['ready_node_count']}`",
        f"- Scenario count: `{summary['scenario_count']}`",
        f"- Manual gate: `{summary['manual_gate']['status']}`",
        "",
        "Reviewer order:",
        "",
        "1. Verify `SHA256SUMS.txt`.",
        "2. Review `public_testnet_evidence_workbench.json` and `public_testnet_evidence_workbench_check.json`.",
        "3. Complete `testnet/operators/operator_roster_review.md` after operator onboarding passes.",
        "4. Complete every `testnet/node_reports/*.md` workpaper.",
        "5. Complete every `testnet/scenarios/*.md` workpaper.",
        "6. Complete `testnet/incidents/incident_response_review.md`.",
        "7. Fill `testnet/final_public_testnet_report_template.md` and complete the final evidence JSON.",
        "8. Do not mark `public_testnet_complete` complete until `--require-complete` passes.",
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


def build_public_testnet_workbench(out_dir=None, reviewed_source_hash="", release_bundle_sha256="", force=False):
    out_dir = Path(out_dir or default_workbench_dir())
    if out_dir.exists():
        if not force:
            raise ValueError(f"Public-testnet workbench already exists: {out_dir}")
        safe_reset_dir(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    workpapers = write_public_testnet_workpapers(out_dir)
    evidence = write_public_testnet_evidence_workbench(
        out_dir,
        workpapers,
        reviewed_source_hash=reviewed_source_hash,
        release_bundle_sha256=release_bundle_sha256,
    )
    check = validate_public_testnet_evidence(evidence)
    write_json(out_dir / "public_testnet_evidence_workbench_check.json", check)

    summary = {
        "ok": bool(check.get("ok") and not check.get("public_testnet_ready")),
        "mode": "spacecash-public-testnet-workbench-v1",
        "generated_at": protocol.utc_now(),
        "chain_id": protocol.CHAIN_ID,
        "out_dir": str(out_dir.resolve()),
        "reviewed_source_hash": evidence.get("reviewed_source_hash"),
        "release_bundle_sha256": evidence.get("release_bundle_sha256"),
        "public_testnet_ready": check.get("public_testnet_ready"),
        "ready_node_count": check.get("ready_node_count"),
        "node_count": check.get("node_count"),
        "independent_operators": check.get("independent_operators"),
        "scenario_count": check.get("scenario_count"),
        "blockers": check.get("blockers") or [],
        "review_workpapers": workpapers,
        "required_outputs": [
            "operator onboarding approval",
            "node health/readiness/audit/manifest/checkpoint/peer reports",
            "signed transfer scenario evidence",
            "product-payment scenario evidence",
            "checkpoint quorum evidence",
            "peer gossip evidence",
            "sync preview and guarded import evidence",
            "node restart recovery evidence",
            "incident response evidence",
            "final public-testnet report",
        ],
        "manual_gate": {
            "id": "public_testnet_complete",
            "status": "not_complete",
            "reason": "Independent operators, scenario evidence, incident closure, and final public-testnet approval are still required.",
        },
    }
    write_json(out_dir / "public_testnet_workbench_summary.json", summary)
    write_workbench_readme(out_dir, summary)
    files = write_checksums(out_dir)
    result = dict(summary)
    result["files"] = files
    return result


def write_public_testnet_evidence_template(out_path=None, node_count=3):
    payload = public_testnet_evidence_template(node_count)
    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def load_public_testnet_evidence(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_parser():
    parser = argparse.ArgumentParser(description="Create or verify SpaceCash public-testnet exit evidence JSON")
    parser.add_argument("--template-out", type=Path, help="Optional path to write the public-testnet evidence template")
    parser.add_argument("--verify", type=Path, help="Public-testnet evidence JSON file to verify")
    parser.add_argument("--nodes", type=int, default=3, help="Number of node slots in the generated template")
    parser.add_argument("--require-complete", action="store_true", help="Fail unless the public testnet gate is complete")
    parser.add_argument("--workbench-out-dir", type=Path, help="Write a public-testnet review workbench packet")
    parser.add_argument("--reviewed-source-hash", default="", help="Optional reviewed source hash to seed into the workbench")
    parser.add_argument("--release-bundle-sha256", default="", help="Optional release bundle SHA-256 to seed into the workbench")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing workbench directory under _tmp")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.verify:
        result = validate_public_testnet_evidence(
            load_public_testnet_evidence(args.verify),
            require_complete=args.require_complete,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") and (not args.require_complete or result.get("public_testnet_ready")) else 2
    if args.workbench_out_dir:
        try:
            result = build_public_testnet_workbench(
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
    payload = write_public_testnet_evidence_template(args.template_out, args.nodes)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
