"""Run a local multi-node SpaceCash public-testnet rehearsal."""

import argparse
import hashlib
import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = Path(__file__).resolve().parent
for candidate in (ROOT, TOOLS_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from spacecash_core import SpaceCashLedger, protocol  # noqa: E402
from spacecash_testnet_plan import build_testnet_package  # noqa: E402
from tools.spacecash_daemon import SpaceCashDaemonHandler, SpaceCashHTTPServer  # noqa: E402


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def default_out_dir():
    stamp = protocol.utc_now().replace(":", "").replace("-", "").replace("Z", "Z")
    return ROOT / "_tmp" / f"spacecash_testnet_rehearsal_{stamp}"


class QuietSpaceCashDaemonHandler(SpaceCashDaemonHandler):
    def log_message(self, fmt, *args):
        return None


class RehearsalCatalog:
    def require_spacecash_product(self, source, product_id):
        raise ValueError("Rehearsal catalog does not expose product-payment fixtures.")

    def lookup_checkout_product(self, source, product_id):
        return None


def port_available(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def find_free_base_port(host, node_count, start=19000, end=52000):
    for base in range(int(start), int(end) - int(node_count)):
        if all(port_available(host, base + offset) for offset in range(int(node_count))):
            return base
    raise ValueError("Could not find a free consecutive port range for testnet rehearsal.")


def http_json(url, method="GET", payload=None, timeout=10):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return {"ok": True, "status": response.status, "json": json.loads(body) if body else None}
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
            parsed = json.loads(body) if body else None
        finally:
            exc.close()
        return {"ok": False, "status": exc.code, "json": parsed}
    except Exception as exc:
        return {"ok": False, "status": None, "error": str(exc)}


def wait_for_health(nodes, timeout=10):
    deadline = time.time() + timeout
    pending = {node["node_name"]: node for node in nodes}
    last = {}
    while pending and time.time() < deadline:
        for name, node in list(pending.items()):
            result = http_json(f"{node['url']}/health", timeout=2)
            last[name] = result
            if result.get("ok") and (result.get("json") or {}).get("ok"):
                pending.pop(name, None)
        if pending:
            time.sleep(0.2)
    return not pending, last


def start_servers(package_dir, nodes):
    servers = []
    for node in nodes:
        db_path = package_dir / node["db"]
        ledger = SpaceCashLedger(db_path)
        ledger.ensure_schema()
        server = SpaceCashHTTPServer(
            (node["host"], int(node["port"])),
            QuietSpaceCashDaemonHandler,
            ledger,
            RehearsalCatalog(),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append({"server": server, "thread": thread, "node": node})
    return servers


def stop_servers(servers):
    for item in servers:
        item["server"].shutdown()
    for item in servers:
        item["thread"].join(timeout=5)
        item["server"].server_close()


def collect_node_evidence(node, timeout=5):
    evidence = {
        "node_name": node["node_name"],
        "url": node["url"],
        "health": http_json(f"{node['url']}/health", timeout=timeout),
        "status": http_json(f"{node['url']}/status", timeout=timeout),
        "readiness": http_json(f"{node['url']}/readiness", timeout=timeout),
        "manifest": http_json(f"{node['url']}/chain/manifest", timeout=timeout),
        "audit": http_json(f"{node['url']}/audit", timeout=timeout),
        "checkpoint_quorum": http_json(f"{node['url']}/checkpoint/quorum", timeout=timeout),
    }
    evidence["bootstrap_load"] = http_json(
        f"{node['url']}/bootstrap-peers/load",
        method="POST",
        payload={"check": True, "snapshot": True, "timeout": timeout},
        timeout=max(10, timeout * 4),
    )
    evidence["peer_check_all"] = http_json(
        f"{node['url']}/peers/check-all",
        method="POST",
        payload={"snapshot": True, "timeout": timeout},
        timeout=max(10, timeout * 4),
    )
    evidence["peer_gossip"] = http_json(
        f"{node['url']}/peers/gossip",
        method="POST",
        payload={"check": True, "snapshot": True, "timeout": timeout, "max_new": 20},
        timeout=max(10, timeout * 4),
    )
    evidence["sync_preview_all"] = http_json(
        f"{node['url']}/peers/sync-preview-all",
        method="POST",
        payload={"store": True, "timeout": timeout},
        timeout=max(10, timeout * 4),
    )
    evidence["peers"] = http_json(f"{node['url']}/peers", timeout=timeout)
    return evidence


def summarize_evidence(plan, evidence):
    chain_digests = []
    failures = []
    for item in evidence:
        name = item["node_name"]
        health_json = (item.get("health") or {}).get("json") or {}
        readiness_json = (item.get("readiness") or {}).get("json") or {}
        audit_json = (item.get("audit") or {}).get("json") or {}
        manifest_json = (item.get("manifest") or {}).get("json") or {}
        quorum_json = (item.get("checkpoint_quorum") or {}).get("json") or {}
        chain_digest = manifest_json.get("chain_digest")
        if chain_digest:
            chain_digests.append(chain_digest)
        if not health_json.get("ok"):
            failures.append(f"{name} health failed")
        if not readiness_json.get("automated_release_candidate"):
            failures.append(f"{name} automated readiness failed")
        if readiness_json.get("mainnet_ready"):
            failures.append(f"{name} unexpectedly reports mainnet_ready")
        if not audit_json.get("valid") or audit_json.get("warnings"):
            failures.append(f"{name} audit is not clean")
        if not quorum_json.get("quorum_reached"):
            failures.append(f"{name} checkpoint quorum failed")
        for key in ("bootstrap_load", "peer_check_all", "peer_gossip", "sync_preview_all"):
            if not (item.get(key) or {}).get("ok"):
                failures.append(f"{name} {key} request failed")
    if len(set(chain_digests)) != 1:
        failures.append("node manifests do not agree on chain_digest")
    return {
        "ok": not failures,
        "chain_id": protocol.CHAIN_ID,
        "node_count": len(evidence),
        "validators": len(plan.get("validators") or []),
        "validator_quorum": plan.get("validator_quorum"),
        "chain_digest": chain_digests[0] if chain_digests else None,
        "failures": failures,
        "manual_gate_status": "local_rehearsal_only",
    }


def write_report(out_dir, report):
    report_path = out_dir / "rehearsal_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = file_hash(report_path)
    checksum_path = out_dir / "REHEARSAL_SHA256SUMS.txt"
    checksum_path.write_text(f"{digest}  rehearsal_report.json\n", encoding="utf-8")
    return {
        "report": str(report_path.resolve()),
        "report_sha256": digest,
        "checksum_file": str(checksum_path.resolve()),
    }


def run_rehearsal(out_dir=None, node_count=3, host="127.0.0.1", base_port=0, force=False, timeout=5):
    out_dir = Path(out_dir or default_out_dir())
    if base_port in (0, None):
        base_port = find_free_base_port(host, node_count)
    package = build_testnet_package(
        out_dir=out_dir,
        node_count=node_count,
        host=host,
        base_port=base_port,
        validator_count=3,
        validator_quorum=2,
        force=force,
    )
    plan = json.loads((out_dir / "testnet_plan.json").read_text(encoding="utf-8"))
    servers = []
    started_at = protocol.utc_now()
    try:
        servers = start_servers(out_dir, plan["nodes"])
        healthy, health_attempts = wait_for_health(plan["nodes"], timeout=max(5, timeout))
        evidence = [collect_node_evidence(node, timeout=timeout) for node in plan["nodes"]] if healthy else []
        summary = summarize_evidence(plan, evidence) if healthy else {
            "ok": False,
            "chain_id": protocol.CHAIN_ID,
            "node_count": node_count,
            "validators": len(plan.get("validators") or []),
            "validator_quorum": plan.get("validator_quorum"),
            "failures": ["one or more rehearsal nodes failed to start"],
            "manual_gate_status": "local_rehearsal_only",
        }
        report = {
            "mode": "public-testnet-local-rehearsal-v1",
            "started_at": started_at,
            "finished_at": protocol.utc_now(),
            "package": {
                "out_dir": str(out_dir.resolve()),
                "ok": package.get("ok"),
                "base_port": base_port,
                "node_count": package.get("node_count"),
                "candidate": package.get("candidate"),
            },
            "health_attempts": health_attempts,
            "summary": summary,
            "nodes": evidence,
        }
    finally:
        if servers:
            stop_servers(servers)
    artifacts = write_report(out_dir, report)
    result = {
        **report["summary"],
        "out_dir": str(out_dir.resolve()),
        "base_port": base_port,
        "report": artifacts["report"],
        "report_sha256": artifacts["report_sha256"],
        "checksum_file": artifacts["checksum_file"],
    }
    return result


def build_parser():
    parser = argparse.ArgumentParser(description="Run a local SpaceCash public-testnet rehearsal")
    parser.add_argument("--out-dir", type=Path, default=default_out_dir(), help="Output directory under _tmp")
    parser.add_argument("--nodes", type=int, default=3, help="Number of temporary nodes")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--base-port", type=int, default=0, help="First port; 0 picks a free range")
    parser.add_argument("--timeout", type=int, default=5, help="HTTP timeout per request")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing output directory under _tmp")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = run_rehearsal(
            out_dir=args.out_dir,
            node_count=args.nodes,
            host=args.host,
            base_port=args.base_port,
            force=args.force,
            timeout=args.timeout,
        )
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
