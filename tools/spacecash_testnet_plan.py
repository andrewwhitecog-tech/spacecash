"""Build a reproducible SpaceCash public-testnet planning package."""

import argparse
import hashlib
import json
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
from spacecash_candidate import build_candidate  # noqa: E402
from spacecash_operator_onboarding import validate_operator_onboarding_packet  # noqa: E402
from spacecash_public_testnet_evidence import (  # noqa: E402
    REQUIRED_NODE_REPORTS,
    REQUIRED_SCENARIOS,
    public_testnet_evidence_template,
)


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


NODE_REPORT_ENDPOINTS = {
    "health_report": ["GET /health"],
    "readiness_report": ["GET /readiness"],
    "audit_report": ["GET /audit"],
    "chain_manifest": ["GET /chain/manifest"],
    "checkpoint_report": ["GET /checkpoint/quorum", "GET /checkpoint/votes"],
    "peer_report": ["GET /peers", "POST /peers/check-all", "POST /peers/gossip"],
}

SCENARIO_EVIDENCE_HINTS = {
    "node_health_and_readiness": [
        "Collect health_report and readiness_report for every node.",
        "Confirm every node reports automated_release_candidate true and mainnet_ready false.",
    ],
    "signed_transfer": [
        "Run one signed wallet transfer and archive sender, recipient, amount, txid, and proof.",
        "Confirm the transfer is visible in audit and transaction lookup output.",
    ],
    "product_payment": [
        "Run one catalog-backed product payment or a documented product-payment fixture.",
        "Archive payment request, signed payload, txid, receipt, and order status.",
    ],
    "checkpoint_quorum": [
        "Collect checkpoint quorum and checkpoint votes from every node.",
        "Confirm eligible votes meet or exceed validator quorum after the scenario.",
    ],
    "peer_gossip": [
        "Run peer checks and gossip discovery across the testnet.",
        "Archive peer registry output and any newly discovered peers.",
    ],
    "sync_preview": [
        "Run sync-preview or sync-preview-all against peers.",
        "Archive classifications for same, ahead, behind, and diverged snapshots when available.",
    ],
    "guarded_import": [
        "Run a guarded append-only import rehearsal against an approved peer candidate.",
        "Archive pre-import backup path, import result, and post-import audit.",
    ],
    "node_restart_recovery": [
        "Restart every node at least once.",
        "Archive health, readiness, audit, and checkpoint quorum after restart.",
    ],
    "incident_response": [
        "Open, triage, and close or explicitly accept-risk every incident.",
        "Archive incident_log.md and reviewer notes.",
    ],
}


def default_out_dir():
    stamp = protocol.utc_now().replace(":", "").replace("-", "").replace("Z", "Z")
    return ROOT / "_tmp" / f"spacecash_testnet_plan_{stamp}_{secrets.token_hex(4)}"


def safe_reset_dir(path):
    path = Path(path).resolve()
    tmp_root = (ROOT / "_tmp").resolve()
    if path == tmp_root or tmp_root not in path.parents:
        raise ValueError("Refusing to overwrite a testnet package outside the project _tmp directory.")
    if path.exists():
        shutil.rmtree(path)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def node_url(host, port):
    return f"http://{host}:{int(port)}"


def build_node_configs(node_count, host, base_port, bootstrap_urls, validator_addresses, quorum):
    configs = []
    for index in range(node_count):
        port = int(base_port) + index
        node_name = f"node-{index + 1:02d}"
        node_db = f"nodes/{node_name}/spacecash_testnet.sqlite3"
        configs.append({
            "node_name": node_name,
            "label": f"SpaceCash Public Testnet {node_name}",
            "host": host,
            "port": port,
            "url": node_url(host, port),
            "db": node_db,
            "bootstrap_peers": [url for url in bootstrap_urls if url != node_url(host, port)],
            "validators": validator_addresses,
            "validator_quorum": quorum,
            "start_command": f"tools\\nsp_python.cmd tools\\spacecash_daemon.py --host {host} --port {port} --db {node_db}",
            "readiness_url": f"{node_url(host, port)}/readiness",
            "manifest_url": f"{node_url(host, port)}/chain/manifest",
        })
    return configs


def write_readme(out_dir, plan):
    commands = "\n".join(f"- `{node['start_command']}`" for node in plan["nodes"])
    write_text(out_dir / "README.md", "\n".join([
        "# SpaceCash Public Testnet Package",
        "",
        "This package is public-testnet preparation evidence, not a mainnet launch approval.",
        "",
        f"- Chain: `{plan['chain_id']}`",
        f"- Nodes: `{plan['node_count']}`",
        f"- Validators: `{len(plan['validators'])}`",
        f"- Validator quorum: `{plan['validator_quorum']}`",
        f"- Candidate automated release: `{plan['candidate']['automated_release_candidate']}`",
        f"- Candidate mainnet ready: `{plan['candidate']['mainnet_ready']}`",
        "",
        "Start commands:",
        "",
        commands,
        "",
        "Required operator evidence:",
        "",
        "1. Fill `operator_checklist.md` before launch.",
        "2. Append daily reports from `daily_report_template.md`.",
        "3. Record all incidents in `incident_log.md`.",
        "4. Fill node report templates under `reports/<node-id>/`.",
        "5. Fill scenario evidence templates under `evidence/scenarios/`.",
        "6. Complete `public_testnet_exit_evidence_template.json` only after real operators run the testnet.",
        "7. Do not mark `public_testnet_complete` until reviewers accept the evidence.",
        "",
    ]) + "\n")


def write_operator_checklist(out_dir, plan):
    lines = [
        "# SpaceCash Public Testnet Operator Checklist",
        "",
        "## Preflight",
        "",
        "- [ ] Verify `SHA256SUMS.txt`.",
        "- [ ] Review `testnet_plan.json`.",
        "- [ ] Confirm every node operator can start from the same source hash.",
        "- [ ] Confirm bootstrap peer URLs are reachable.",
        "- [ ] Confirm validator wallets and quorum policy are reviewed.",
        "- [ ] Confirm incident contact path is active.",
        "",
        "## Launch",
        "",
    ]
    for node in plan["nodes"]:
        lines.append(f"- [ ] Start `{node['node_name']}` with `{node['start_command']}`.")
    lines.extend([
        "- [ ] Run `/health`, `/status`, `/readiness`, and `/chain/manifest` on each node.",
        "- [ ] Run peer checks and gossip discovery.",
        "- [ ] Submit checkpoint votes and verify quorum.",
        "- [ ] Run signed transfer, product payment, snapshot, sync-preview, and guarded import scenarios.",
        "- [ ] Fill every `reports/<node-id>/*.json` report template.",
        "- [ ] Fill every `evidence/scenarios/*.json` scenario evidence template.",
        "",
        "## Exit Review",
        "",
        "- [ ] No unresolved audit errors.",
        "- [ ] No unsigned spend compatibility in the candidate chain.",
        "- [ ] Checkpoint quorum survived node restarts.",
        "- [ ] Peer classifications were archived.",
        "- [ ] Incidents are closed or explicitly accepted by reviewers.",
        "- [ ] Final report is attached to release bundle.",
        "- [ ] `public_testnet_exit_evidence_template.json` has been copied to the final evidence path, completed, reviewed, and verified with `--require-complete`.",
        "",
    ])
    write_text(out_dir / "operator_checklist.md", "\n".join(lines))


def write_operator_onboarding_packet(out_dir, plan):
    operator_paths = []
    write_text(out_dir / "operators" / "README.md", "\n".join([
        "# SpaceCash Public Testnet Operator Packet",
        "",
        "This packet collects operator-facing public-testnet evidence. It does not approve",
        "`public_testnet_complete` and it is not a mainnet launch authorization.",
        "",
        "Required operator files:",
        "",
        "- `contact_roster_template.md`",
        "- `evidence_intake_checklist.md`",
        "- `operator_commitment_template.md`",
        "- `node-*/operator_intake.json`",
        "- `node-*/node_runbook.md`",
        "- `node-*/evidence_manifest_template.json`",
        "",
        "Each operator should complete their node folder before the public testnet starts,",
        "then update the evidence manifest throughout the run.",
        "",
    ]))
    operator_paths.append("operators/README.md")

    write_text(out_dir / "operators" / "contact_roster_template.md", "\n".join([
        "# SpaceCash Public Testnet Contact Roster",
        "",
        "| Node | Operator | Organization | Contact | Timezone | Escalation Contact |",
        "| --- | --- | --- | --- | --- | --- |",
        "| node-01 | | | | | |",
        "| node-02 | | | | | |",
        "| node-03 | | | | | |",
        "",
        "## Incident Channel",
        "",
        "- Primary channel:",
        "- Backup channel:",
        "- Status-page owner:",
        "- Reviewer contact:",
        "",
    ]))
    operator_paths.append("operators/contact_roster_template.md")

    write_text(out_dir / "operators" / "evidence_intake_checklist.md", "\n".join([
        "# SpaceCash Public Testnet Evidence Intake Checklist",
        "",
        "- [ ] Operator intake JSON completed for every node.",
        "- [ ] Contact roster completed and shared with reviewers.",
        "- [ ] Source hash and release bundle hash recorded.",
        "- [ ] Node start command tested by every operator.",
        "- [ ] Daily report owner assigned for every day of the run.",
        "- [ ] Health, readiness, audit, chain manifest, checkpoint, and peer reports collected for every node.",
        "- [ ] Scenario evidence collected for every required scenario.",
        "- [ ] Incident log updated and reviewed daily.",
        "- [ ] Final public-testnet report drafted and reviewed.",
        "- [ ] `public_testnet_exit_evidence_template.json` copied to the final evidence path and completed after the real run.",
        "",
    ]))
    operator_paths.append("operators/evidence_intake_checklist.md")

    write_text(out_dir / "operators" / "operator_commitment_template.md", "\n".join([
        "# SpaceCash Public Testnet Operator Commitment Template",
        "",
        "- Operator name:",
        "- Organization:",
        "- Node ID:",
        "- Contact:",
        "- Timezone:",
        "- Reviewed source hash:",
        "- Release bundle SHA256:",
        "",
        "## Operator Commitments",
        "",
        "- [ ] I can start the node from the published package.",
        "- [ ] I will not modify consensus, wallet, or daemon code during the evidence run.",
        "- [ ] I will report outages, data loss, peer divergence, and validator issues immediately.",
        "- [ ] I will collect required node reports and scenario evidence.",
        "- [ ] I understand this testnet evidence does not approve mainnet launch.",
        "",
        "- Signature or approval reference:",
        "- Approved at:",
        "",
    ]))
    operator_paths.append("operators/operator_commitment_template.md")

    for node in plan["nodes"]:
        node_name = node["node_name"]
        node_dir = Path("operators") / node_name
        intake_path = node_dir / "operator_intake.json"
        runbook_path = node_dir / "node_runbook.md"
        manifest_path = node_dir / "evidence_manifest_template.json"
        write_json(out_dir / intake_path, {
            "mode": "spacecash-public-testnet-operator-intake-v1",
            "chain_id": protocol.CHAIN_ID,
            "node_id": node_name,
            "node_url": node["url"],
            "node_config": f"nodes/{node_name}/node_config.json",
            "operator": {
                "name": "",
                "organization": "",
                "contact": "",
                "timezone": "",
                "independent_operator": False,
                "availability_window": "",
                "escalation_contact": "",
            },
            "preflight": {
                "source_hash": "",
                "release_bundle_sha256": "",
                "sha256sums_verified": False,
                "start_command_tested": False,
                "backup_plan_recorded": False,
                "incident_channel_confirmed": False,
            },
            "review": {
                "reviewer": "",
                "reviewed_at": "",
                "decision": "not_reviewed",
                "notes": "",
            },
        })
        write_text(out_dir / runbook_path, "\n".join([
            f"# SpaceCash Public Testnet Node Runbook: {node_name}",
            "",
            f"- Node URL: `{node['url']}`",
            f"- Node config: `nodes/{node_name}/node_config.json`",
            f"- DB path: `{node['db']}`",
            f"- Start command: `{node['start_command']}`",
            "",
            "## Preflight",
            "",
            "- [ ] Verify package checksums.",
            "- [ ] Complete `operator_intake.json`.",
            "- [ ] Confirm bootstrap peers are reachable.",
            "- [ ] Start the node and capture `/health`.",
            "- [ ] Capture `/readiness` and confirm `mainnet_ready` is false.",
            "- [ ] Capture `/chain/manifest`.",
            "",
            "## Daily Evidence",
            "",
            "- [ ] Append to `daily_report_template.md` or daily report copy.",
            "- [ ] Update `evidence_manifest_template.json` with collected files.",
            "- [ ] Report incidents in `incident_log.md`.",
            "",
            "## Stop Conditions",
            "",
            "- Ledger audit integrity error.",
            "- Unexpected unsigned spend compatibility.",
            "- Checkpoint quorum failure that cannot be explained.",
            "- Peer divergence or unsafe sync import result.",
            "- Lost key, corrupted DB, or unrecoverable operator state.",
            "",
        ]))
        write_json(out_dir / manifest_path, {
            "mode": "spacecash-public-testnet-operator-evidence-manifest-v1",
            "chain_id": protocol.CHAIN_ID,
            "node_id": node_name,
            "operator": "",
            "operator_contact": "",
            "reviewed_source_hash": "",
            "release_bundle_sha256": "",
            "reports": {
                report_type: {
                    "path": f"reports/{node_name}/{report_type}.json",
                    "sha256": "",
                    "collected_at": "",
                    "accepted": False,
                }
                for report_type in REQUIRED_NODE_REPORTS
            },
            "daily_reports": [],
            "scenario_artifacts": [],
            "incidents": [],
            "review": {
                "reviewer": "",
                "reviewed_at": "",
                "decision": "not_reviewed",
                "notes": "",
            },
        })
        operator_paths.extend([intake_path.as_posix(), runbook_path.as_posix(), manifest_path.as_posix()])
    return operator_paths


def write_daily_report_template(out_dir):
    write_text(out_dir / "daily_report_template.md", "\n".join([
        "# SpaceCash Public Testnet Daily Report",
        "",
        "- Date:",
        "- Operators present:",
        "- Source hash:",
        "- Candidate DB hash:",
        "- Nodes online:",
        "- Validator quorum status:",
        "- Audit status:",
        "- Readiness status:",
        "- Peer gossip summary:",
        "- Sync-preview summary:",
        "- Product-payment test summary:",
        "- Incidents opened:",
        "- Incidents closed:",
        "- Reviewer notes:",
        "",
    ]))


def write_incident_log(out_dir):
    write_text(out_dir / "incident_log.md", "\n".join([
        "# SpaceCash Public Testnet Incident Log",
        "",
        "| ID | Opened | Severity | Component | Summary | Status | Resolution |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        "| SCTN-001 | | | | | open | |",
        "",
    ]))


def write_node_report_templates(out_dir, plan):
    reports = []
    for node in plan["nodes"]:
        node_name = node["node_name"]
        for report_type in REQUIRED_NODE_REPORTS:
            rel_path = Path("reports") / node_name / f"{report_type}.json"
            payload = {
                "mode": "spacecash-public-testnet-node-report-template-v1",
                "chain_id": protocol.CHAIN_ID,
                "generated_at": protocol.utc_now(),
                "node_id": node_name,
                "node_url": node["url"],
                "report_type": report_type,
                "status": "not_collected",
                "operator": "",
                "operator_contact": "",
                "collected_at": "",
                "source": {
                    "endpoints": NODE_REPORT_ENDPOINTS.get(report_type, []),
                    "node_config": f"nodes/{node_name}/node_config.json",
                },
                "summary": "",
                "observations": {},
                "attachments": [],
                "review": {
                    "reviewer": "",
                    "reviewed_at": "",
                    "decision": "not_reviewed",
                    "notes": "",
                },
            }
            write_json(out_dir / rel_path, payload)
            reports.append(rel_path.as_posix())
    return reports


def write_scenario_evidence_templates(out_dir, plan):
    evidence_files = []
    node_ids = [node["node_name"] for node in plan["nodes"]]
    for scenario_id in REQUIRED_SCENARIOS:
        rel_path = Path("evidence") / "scenarios" / f"{scenario_id}.json"
        payload = {
            "mode": "spacecash-public-testnet-scenario-evidence-template-v1",
            "chain_id": protocol.CHAIN_ID,
            "generated_at": protocol.utc_now(),
            "scenario_id": scenario_id,
            "status": "not_run",
            "node_ids": node_ids,
            "operator": "",
            "started_at": "",
            "finished_at": "",
            "evidence_summary": "",
            "acceptance_checks": [
                {"check": hint, "status": "not_reviewed", "notes": ""}
                for hint in SCENARIO_EVIDENCE_HINTS.get(scenario_id, [])
            ],
            "artifacts": [],
            "incidents": [],
            "review": {
                "reviewer": "",
                "reviewed_at": "",
                "decision": "not_reviewed",
                "notes": "",
            },
        }
        write_json(out_dir / rel_path, payload)
        evidence_files.append(rel_path.as_posix())
    return evidence_files


def write_public_testnet_exit_evidence_seed(out_dir, plan):
    payload = public_testnet_evidence_template(node_count=len(plan["nodes"]))
    payload["status"] = "not_run"
    payload["duration_days"] = 0
    payload["nodes"] = []
    for node in plan["nodes"]:
        node_name = node["node_name"]
        payload["nodes"].append({
            "node_id": node_name,
            "operator": "",
            "operator_contact": "",
            "url": node["url"],
            "independently_operated": False,
            "reports": {
                report_type: f"reports/{node_name}/{report_type}.json"
                for report_type in REQUIRED_NODE_REPORTS
            },
        })
    for scenario in payload["scenarios"]:
        scenario["evidence"] = f"evidence/scenarios/{scenario['id']}.json"
    write_json(out_dir / "public_testnet_exit_evidence_template.json", payload)
    return "public_testnet_exit_evidence_template.json"


def write_manual_evidence(out_dir):
    write_json(out_dir / "manual_gate_evidence.json", {
        "chain_id": protocol.CHAIN_ID,
        "mode": "public-testnet-evidence-template-v1",
        "generated_at": protocol.utc_now(),
        "gates": {
            "public_testnet_complete": {
                "status": "pending_review",
                "required_artifacts": [
                    "operator_checklist.md",
                    "daily reports",
                    "incident_log.md",
                    "node readiness reports",
                    "peer and checkpoint reports",
                ],
                "reviewer": "",
                "reviewed_at": "",
                "notes": "",
            },
            "external_security_review_complete": {
                "status": "not_started",
                "required_artifacts": ["SECURITY_AUDIT_SCOPE.md", "audit report", "finding remediation log"],
                "reviewer": "",
                "reviewed_at": "",
                "notes": "",
            },
            "legal_compliance_review_complete": {
                "status": "not_started",
                "required_artifacts": ["LEGAL_COMPLIANCE_GATE.md", "legal/compliance approval memo"],
                "reviewer": "",
                "reviewed_at": "",
                "notes": "",
            },
            "wallet_recovery_custody_policy_complete": {
                "status": "not_started",
                "required_artifacts": ["WALLET_RECOVERY_CUSTODY_POLICY.md", "approved custody policy"],
                "reviewer": "",
                "reviewed_at": "",
                "notes": "",
            },
            "production_deployment_runbook_complete": {
                "status": "not_started",
                "required_artifacts": ["PRODUCTION_DEPLOYMENT_RUNBOOK.md", "deployment rehearsal report"],
                "reviewer": "",
                "reviewed_at": "",
                "notes": "",
            },
        },
    })


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


def build_testnet_package(
    out_dir=None,
    node_count=3,
    host="127.0.0.1",
    base_port=18876,
    validator_count=3,
    validator_quorum=2,
    include_dev_keys=False,
    force=False,
):
    out_dir = Path(out_dir or default_out_dir())
    if out_dir.exists():
        if not force:
            raise ValueError(f"Testnet package already exists: {out_dir}")
        safe_reset_dir(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    node_count = max(1, int(node_count or 1))
    validator_count = max(1, int(validator_count or 1))
    validator_quorum = int(validator_quorum or min(2, validator_count))
    if validator_quorum < 1 or validator_quorum > validator_count:
        raise ValueError("Validator quorum must be between 1 and validator_count.")

    bootstrap_urls = [node_url(host, int(base_port) + index) for index in range(node_count)]
    candidate_db = out_dir / "spacecash_testnet_candidate.sqlite3"
    keys_out = out_dir / "testnet_dev_keys.json" if include_dev_keys else None
    candidate = build_candidate(
        candidate_db,
        bootstrap_peers=bootstrap_urls,
        keys_out=keys_out,
        force=True,
        validator_count=validator_count,
        validator_quorum=validator_quorum,
    )

    nodes = build_node_configs(
        node_count,
        host,
        base_port,
        bootstrap_urls,
        candidate.get("validators") or [candidate.get("validator")],
        validator_quorum,
    )
    for node in nodes:
        node_dir = out_dir / Path(node["db"]).parent
        node_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate_db, out_dir / node["db"])
        write_json(node_dir / "node_config.json", node)

    write_json(out_dir / "candidate_summary.json", candidate)
    plan = {
        "ok": bool(candidate.get("ok") and candidate.get("readiness", {}).get("automated_release_candidate")),
        "chain_id": protocol.CHAIN_ID,
        "mode": "public-testnet-plan-v1",
        "generated_at": protocol.utc_now(),
        "node_count": node_count,
        "host": host,
        "base_port": int(base_port),
        "bootstrap_peers": bootstrap_urls,
        "validators": candidate.get("validators") or [candidate.get("validator")],
        "validator_quorum": validator_quorum,
        "candidate": {
            "db": "spacecash_testnet_candidate.sqlite3",
            "automated_release_candidate": candidate.get("readiness", {}).get("automated_release_candidate"),
            "mainnet_ready": candidate.get("readiness", {}).get("mainnet_ready"),
            "automated_blockers": candidate.get("readiness", {}).get("automated_blockers") or [],
            "manual_blockers": candidate.get("readiness", {}).get("manual_blockers") or [],
            "chain_digest": candidate.get("manifest", {}).get("chain_digest"),
            "tip_hash": candidate.get("manifest", {}).get("tip_hash"),
        },
        "nodes": nodes,
        "dev_keys_included": bool(keys_out),
        "manual_gate_status": "evidence_template_only",
    }
    write_json(out_dir / "testnet_plan.json", plan)
    write_readme(out_dir, plan)
    write_operator_checklist(out_dir, plan)
    operator_onboarding_files = write_operator_onboarding_packet(out_dir, plan)
    write_daily_report_template(out_dir)
    write_incident_log(out_dir)
    write_manual_evidence(out_dir)
    node_report_templates = write_node_report_templates(out_dir, plan)
    scenario_evidence_templates = write_scenario_evidence_templates(out_dir, plan)
    exit_evidence_template = write_public_testnet_exit_evidence_seed(out_dir, plan)
    operator_onboarding_check = validate_operator_onboarding_packet(out_dir)
    write_json(out_dir / "operator_onboarding_check.json", operator_onboarding_check)
    plan["evidence_templates"] = {
        "node_reports": node_report_templates,
        "scenarios": scenario_evidence_templates,
        "exit_evidence": exit_evidence_template,
        "operator_onboarding": operator_onboarding_files,
    }
    plan["operator_packet"] = {
        "path": "operators",
        "file_count": len(operator_onboarding_files),
        "node_count": len(nodes),
        "status": "intake_template_only",
        "check_path": "operator_onboarding_check.json",
        "ready": operator_onboarding_check.get("operator_onboarding_ready"),
        "blockers": operator_onboarding_check.get("blockers") or [],
    }
    write_json(out_dir / "testnet_plan.json", plan)
    files = write_checksums(out_dir)
    result = dict(plan)
    result["out_dir"] = str(out_dir.resolve())
    result["files"] = files
    return result


def build_parser():
    parser = argparse.ArgumentParser(description="Build a SpaceCash public-testnet planning package")
    parser.add_argument("--out-dir", type=Path, default=default_out_dir(), help="Output directory under _tmp")
    parser.add_argument("--nodes", type=int, default=3, help="Number of testnet node configs")
    parser.add_argument("--host", default="127.0.0.1", help="Node host for generated URLs")
    parser.add_argument("--base-port", type=int, default=18876, help="First node port")
    parser.add_argument("--validators", type=int, default=3, help="Number of candidate validators")
    parser.add_argument("--quorum", type=int, default=2, help="Validator checkpoint quorum")
    parser.add_argument("--include-dev-keys", action="store_true", help="Include generated development private keys")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing output directory under _tmp")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = build_testnet_package(
            out_dir=args.out_dir,
            node_count=args.nodes,
            host=args.host,
            base_port=args.base_port,
            validator_count=args.validators,
            validator_quorum=args.quorum,
            include_dev_keys=args.include_dev_keys,
            force=args.force,
        )
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
