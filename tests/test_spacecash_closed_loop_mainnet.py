import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ClosedLoopMainnetTests(unittest.TestCase):
    def run_mainnet(self, source):
        env = os.environ.copy()
        env.update({
            "PYTHONPATH": str(ROOT),
            "SPACECASH_NETWORK_PROFILE": "closed-loop-mainnet",
            "SPACECASH_MAINNET_ACK": "closed-loop-nonmonetary-v1",
            "SPACECASH_DEPLOYMENT_ACK": "monitored-rollback-v1",
        })
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(source)],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    def test_mainnet_genesis_is_deterministic_and_commerce_paths_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="spacecash-mainnet-") as temp_dir:
            payload = self.run_mainnet(f"""
                import json
                from pathlib import Path
                from spacecash_core import SpaceCashLedger, protocol

                root = Path({temp_dir!r})
                ledgers = [SpaceCashLedger(root / name) for name in ("a.sqlite3", "b.sqlite3")]
                for ledger in ledgers:
                    ledger.ensure_schema()
                failures = {{}}
                for name, call in {{
                    "legacy_wallet": lambda: ledgers[0].create_wallet("unsafe"),
                    "faucet": lambda: ledgers[0].faucet("SPACE-TESTMAINNET0001", "1"),
                    "fiat_purchase": lambda: ledgers[0].stripe_credit_purchase(
                        "cs_mainnet_forbidden", "SPACE-TESTMAINNET0001", "1", "1.00"
                    ),
                    "physical_redemption": lambda: ledgers[0].product_redeem({{}}, {{}}),
                }}.items():
                    try:
                        call()
                    except ValueError as exc:
                        failures[name] = str(exc)
                manifests = [ledger.chain_manifest() for ledger in ledgers]
                print(json.dumps({{
                    "chain_id": protocol.CHAIN_ID,
                    "same_genesis": manifests[0]["genesis_hash"] == manifests[1]["genesis_hash"],
                    "genesis_txid": protocol.deterministic_genesis_txid(),
                    "failures": failures,
                    "commitments": protocol.network_policy()["commitments"],
                }}))
            """)
        self.assertEqual(payload["chain_id"], "spacecash-mainnet-1")
        self.assertTrue(payload["same_genesis"])
        self.assertEqual(set(payload["failures"]), {
            "legacy_wallet", "faucet", "fiat_purchase", "physical_redemption"
        })
        self.assertFalse(payload["commitments"]["fiat_purchases_allowed"])
        self.assertFalse(payload["commitments"]["physical_redemption_allowed"])

    def test_mainnet_candidate_can_pass_automated_closed_loop_gates(self):
        with tempfile.TemporaryDirectory(prefix="spacecash-mainnet-candidate-") as temp_dir:
            payload = self.run_mainnet(f"""
                import json
                from pathlib import Path
                from tools.spacecash_candidate import build_candidate

                result = build_candidate(
                    Path({temp_dir!r}) / "candidate.sqlite3",
                    validator_count=3,
                    validator_quorum=2,
                )
                print(json.dumps({{
                    "ok": result["ok"],
                    "chain_id": result["chain_id"],
                    "checkpoint_quorum": result["checkpoint_quorum"],
                    "readiness": result["readiness"],
                }}))
            """)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["chain_id"], "spacecash-mainnet-1")
        self.assertTrue(payload["checkpoint_quorum"])
        self.assertTrue(payload["readiness"]["mainnet_ready"])
        self.assertFalse(payload["readiness"]["automated_blockers"])

    def test_mainnet_peer_urls_are_https_allowlisted_and_ssrf_safe(self):
        with tempfile.TemporaryDirectory(prefix="spacecash-mainnet-peer-policy-") as temp_dir:
            payload = self.run_mainnet(f"""
                import json
                from pathlib import Path
                from spacecash_core import SpaceCashLedger

                ledger = SpaceCashLedger(Path({temp_dir!r}) / "policy.sqlite3")
                accepted = ledger._normalize_peer_url(
                    "https://app.northstarprime.net/api/spacecash/chain/manifest"
                )
                rejected = {{}}
                for url in (
                    "http://app.northstarprime.net",
                    "https://example.com",
                    "https://user:pass@app.northstarprime.net",
                    "https://app.northstarprime.net?redirect=127.0.0.1",
                    "https://app.northstarprime.net:444",
                ):
                    try:
                        ledger._normalize_peer_url(url)
                    except ValueError as exc:
                        rejected[url] = str(exc)
                try:
                    ledger._validate_peer_destination("https://127.0.0.1")
                except ValueError as exc:
                    private_destination = str(exc)
                print(json.dumps({{
                    "accepted": accepted,
                    "rejected": rejected,
                    "private_destination": private_destination,
                }}))
            """)
        self.assertEqual(
            payload["accepted"],
            "https://app.northstarprime.net/api/spacecash/chain/manifest",
        )
        self.assertEqual(len(payload["rejected"]), 5)
        self.assertIn("non-public address", payload["private_destination"])

    def test_mainnet_rejects_unauthenticated_peer_snapshot_import(self):
        with tempfile.TemporaryDirectory(prefix="spacecash-mainnet-import-policy-") as temp_dir:
            payload = self.run_mainnet(f"""
                import json
                from pathlib import Path
                from spacecash_core import SpaceCashLedger
                from tools.spacecash_candidate import build_candidate

                root = Path({temp_dir!r})
                local = SpaceCashLedger(root / "local.sqlite3")
                local.ensure_schema()
                build_candidate(root / "peer.sqlite3", validator_count=3, validator_quorum=2)
                peer = SpaceCashLedger(root / "peer.sqlite3")
                snapshot = peer.chain_snapshot(include_service_data=False)
                evaluation = local.evaluate_chain_snapshot(snapshot)
                imported = local.import_chain_snapshot(snapshot, backup=False)
                print(json.dumps({{
                    "status": evaluation["status"],
                    "import_allowed": evaluation["fork_choice"]["import_allowed"],
                    "next_action": evaluation["fork_choice"]["next_action"],
                    "imported": imported["imported"],
                    "reason": imported["reason"],
                }}))
            """)
        self.assertEqual(payload["status"], "peer_ahead_candidate")
        self.assertFalse(payload["import_allowed"])
        self.assertEqual(payload["next_action"], "reject")
        self.assertFalse(payload["imported"])
        self.assertIn("producer seals", payload["reason"])


if __name__ == "__main__":
    unittest.main()
