import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spacecash_core import SpaceCashLedger, protocol  # noqa: E402
from tests.test_spacecash_core import TMP_ROOT, make_wallet, sign_payload  # noqa: E402
from tools.spacecash_daemon import SpaceCashDaemonHandler, SpaceCashHTTPServer  # noqa: E402


class FakeCatalog:
    def __init__(self):
        self.product = {
            "source": "prime",
            "id": 101,
            "name": "Daemon Test Product",
            "price": 4.25,
            "restricted": False,
        }

    def require_spacecash_product(self, source, product_id):
        if str(source).lower() == self.product["source"] and int(product_id) == self.product["id"]:
            return dict(self.product)
        raise ValueError("SpaceCash product not found.")

    def lookup_checkout_product(self, source, product_id):
        try:
            return self.require_spacecash_product(source, product_id)
        except ValueError:
            return None


class QuietSpaceCashDaemonHandler(SpaceCashDaemonHandler):
    def log_message(self, fmt, *args):
        return None


def signed_product_redeem(private_key, sender, product, nonce="daemon-product-nonce-1", extra=None):
    cost_units = protocol.product_cost_units(product["price"])
    payload = {
        "chain_id": protocol.CHAIN_ID,
        "version": protocol.SIGNED_PAYLOAD_VERSION,
        "action": "product_redeem",
        "sender": sender,
        "source": product["source"],
        "product_id": product["id"],
        "amount": protocol.units_to_amount(cost_units),
        "nonce": nonce,
    }
    if extra:
        payload.update(extra)
    return {"auth_payload": payload, "signature": sign_payload(private_key, payload)}


class SpaceCashDaemonTestCase(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.db_path = TMP_ROOT / f"test_spacecash_daemon_{protocol.hash_text(id(self))[:12]}.sqlite3"
        self.ledger = SpaceCashLedger(self.db_path)
        self.catalog = FakeCatalog()
        self.server = SpaceCashHTTPServer(("127.0.0.1", 0), QuietSpaceCashDaemonHandler, self.ledger, self.catalog)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        for candidate in (self.db_path, Path(str(self.db_path) + "-wal"), Path(str(self.db_path) + "-shm")):
            if candidate.exists():
                candidate.unlink()

    def get_json(self, path):
        with urllib.request.urlopen(f"{self.base_url}{path}", timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def post_json(self, path, payload):
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))


class DaemonRouteTests(SpaceCashDaemonTestCase):
    def test_health_config_status_and_audit_routes(self):
        status, health = self.get_json("/health")
        self.assertEqual(status, 200)
        self.assertTrue(health["ok"])
        self.assertEqual(health["chain_id"], protocol.CHAIN_ID)

        _, config = self.get_json("/config")
        self.assertEqual(config["wallet_export_cipher"], "AES-256-GCM")
        self.assertEqual(config["fork_choice_policy"], protocol.FORK_CHOICE_POLICY)
        self.assertEqual(config["consensus_spec_hash"], protocol.consensus_spec_hash())
        self.assertEqual(config["monetary_policy_hash"], protocol.monetary_policy_hash())
        self.assertEqual(config["genesis_plan_hash"], protocol.genesis_plan_hash())

        _, consensus = self.get_json("/consensus/spec")
        self.assertEqual(consensus["id"], protocol.CONSENSUS_SPEC_ID)
        self.assertEqual(consensus["spec_hash"], protocol.consensus_spec_hash())
        self.assertIn("economic finality or BFT consensus", consensus["mainnet_gaps"])

        _, monetary_policy = self.get_json("/monetary/policy")
        self.assertEqual(monetary_policy["id"], protocol.MONETARY_POLICY_ID)
        self.assertEqual(monetary_policy["policy_hash"], protocol.monetary_policy_hash())
        self.assertEqual(monetary_policy["supply"]["supply_cap_units"], protocol.GENESIS_UNITS)
        self.assertEqual(monetary_policy["manual_gate"]["status"], "not_complete")

        _, genesis_plan = self.get_json("/genesis/plan")
        self.assertEqual(genesis_plan["id"], protocol.GENESIS_PLAN_ID)
        self.assertEqual(genesis_plan["plan_hash"], protocol.genesis_plan_hash())
        self.assertFalse(genesis_plan["source_of_truth"]["devnet_history_carried_to_mainnet"])
        self.assertEqual(genesis_plan["manual_gate"]["status"], "not_complete")

        _, genesis_allocation = self.get_json("/genesis/allocation/template")
        self.assertEqual(genesis_allocation["chain_id"], protocol.CHAIN_ID)
        self.assertEqual(genesis_allocation["genesis_plan_hash"], protocol.genesis_plan_hash())
        self.assertEqual(genesis_allocation["monetary_policy_hash"], protocol.monetary_policy_hash())
        self.assertEqual(genesis_allocation["status"], "template_only_not_approved")

        _, genesis_allocation_check = self.get_json("/genesis/allocation/check")
        self.assertTrue(genesis_allocation_check["ok"])
        self.assertFalse(genesis_allocation_check["allocation_ready"])
        self.assertEqual(genesis_allocation_check["total_units"], 0)

        _, security_evidence = self.get_json("/security/review/evidence/template")
        self.assertEqual(security_evidence["chain_id"], protocol.CHAIN_ID)
        self.assertEqual(security_evidence["manual_gate"]["id"], "external_security_review_complete")
        self.assertEqual(security_evidence["manual_gate"]["status"], "not_complete")

        _, security_evidence_check = self.get_json("/security/review/evidence/check")
        self.assertTrue(security_evidence_check["ok"])
        self.assertFalse(security_evidence_check["external_security_review_ready"])
        self.assertIn("manual_gate_not_complete", security_evidence_check["blockers"])

        _, legal_evidence = self.get_json("/legal/compliance/evidence/template")
        self.assertEqual(legal_evidence["chain_id"], protocol.CHAIN_ID)
        self.assertEqual(legal_evidence["manual_gate"]["id"], "legal_compliance_review_complete")
        self.assertEqual(legal_evidence["manual_gate"]["status"], "not_complete")

        _, legal_evidence_check = self.get_json("/legal/compliance/evidence/check")
        self.assertTrue(legal_evidence_check["ok"])
        self.assertFalse(legal_evidence_check["legal_compliance_ready"])
        self.assertIn("manual_gate_not_complete", legal_evidence_check["blockers"])

        _, wallet_custody_evidence = self.get_json("/wallet/custody/evidence/template")
        self.assertEqual(wallet_custody_evidence["chain_id"], protocol.CHAIN_ID)
        self.assertEqual(wallet_custody_evidence["manual_gate"]["id"], "wallet_recovery_custody_policy_complete")
        self.assertEqual(wallet_custody_evidence["manual_gate"]["status"], "not_complete")

        _, wallet_custody_evidence_check = self.get_json("/wallet/custody/evidence/check")
        self.assertTrue(wallet_custody_evidence_check["ok"])
        self.assertFalse(wallet_custody_evidence_check["wallet_custody_ready"])
        self.assertIn("manual_gate_not_complete", wallet_custody_evidence_check["blockers"])

        _, deployment_evidence = self.get_json("/deployment/evidence/template")
        self.assertEqual(deployment_evidence["chain_id"], protocol.CHAIN_ID)
        self.assertEqual(deployment_evidence["manual_gate"]["id"], "production_deployment_runbook_complete")
        self.assertEqual(deployment_evidence["manual_gate"]["status"], "not_complete")

        _, deployment_evidence_check = self.get_json("/deployment/evidence/check")
        self.assertTrue(deployment_evidence_check["ok"])
        self.assertFalse(deployment_evidence_check["deployment_ready"])
        self.assertIn("manual_gate_not_complete", deployment_evidence_check["blockers"])

        _, mainnet_decision = self.get_json("/mainnet/decision/template")
        self.assertEqual(mainnet_decision["chain_id"], protocol.CHAIN_ID)
        self.assertEqual(mainnet_decision["mode"], "spacecash-mainnet-decision-v1")

        _, mainnet_decision_check = self.get_json("/mainnet/decision/check")
        self.assertTrue(mainnet_decision_check["ok"])
        self.assertFalse(mainnet_decision_check["mainnet_decision_ready"])
        self.assertIn("launch_authorization_not_approved", mainnet_decision_check["blockers"])

        _, wallet_policy = self.get_json("/wallet/policy")
        self.assertEqual(wallet_policy["id"], protocol.WALLET_POLICY_ID)
        self.assertEqual(wallet_policy["policy_hash"], protocol.wallet_policy_hash())
        self.assertEqual(wallet_policy["manual_gate"]["status"], "not_complete")

        _, status_payload = self.get_json("/status")
        self.assertEqual(status_payload["chain_id"], protocol.CHAIN_ID)

        audit_status, audit = self.get_json("/audit")
        self.assertEqual(audit_status, 200)
        self.assertTrue(audit["valid"])

        _, readiness = self.get_json("/readiness")
        self.assertFalse(readiness["mainnet_ready"])
        self.assertIn("validators_configured", readiness["automated_blockers"])
        self.assertIn("public_testnet_complete", readiness["manual_blockers"])

    def test_signed_product_payment_mines_receipt_and_blocks_nonce_reuse(self):
        wallet, private_key = make_wallet(self.ledger, "Daemon Buyer")
        self.post_json("/faucet", {"address": wallet["address"], "amount": "20"})

        signed = signed_product_redeem(private_key, wallet["address"], self.catalog.product)
        queued_status, queued = self.post_json("/mempool/pay", signed)
        self.assertEqual(queued_status, 200)
        self.assertTrue(queued["accepted"])
        self.assertEqual(queued["pending"]["kind"], "product_redeem")

        mine_status, mined = self.post_json("/mempool/mine", {"limit": 5})
        self.assertEqual(mine_status, 200)
        self.assertEqual(mined["mined_count"], 1)
        self.assertEqual(len(mined["mined"]), 1)

        _, order_list = self.get_json(f"/orders?wallet={wallet['address']}")
        self.assertEqual(len(order_list["orders"]), 1)
        receipt_id = order_list["orders"][0]["receipt_id"]

        _, order = self.get_json(f"/order/{receipt_id}")
        self.assertEqual(order["receipt_id"], receipt_id)
        self.assertEqual(order["wallet_address"], wallet["address"])
        self.assertEqual(order["source"], "prime")
        self.assertEqual(order["product_id"], "101")
        self.assertEqual(order["status"], "pending_review")

        _, proof = self.get_json(f"/tx/{mined['mined'][0]['txid']}/proof")
        self.assertTrue(proof["included"])
        self.assertTrue(proof["verified"])
        self.assertEqual(proof["transaction"]["txid"], mined["mined"][0]["txid"])

        _, events = self.get_json(f"/order/{receipt_id}/events")
        self.assertTrue(events["events"])
        self.assertEqual(events["events"][0]["event_type"], "created")

        _, duplicate = self.post_json("/mempool/pay", signed)
        self.assertFalse(duplicate["accepted"])
        self.assertTrue(duplicate["duplicate"])

        same_nonce_new_payload = signed_product_redeem(
            private_key,
            wallet["address"],
            self.catalog.product,
            extra={"client_note": "same nonce with a different payload hash"},
        )
        with self.assertRaises(urllib.error.HTTPError) as failure:
            self.post_json("/mempool/pay", same_nonce_new_payload)
        self.assertEqual(failure.exception.code, 400)
        error_body = json.loads(failure.exception.read().decode("utf-8"))
        failure.exception.close()
        self.assertIn("nonce", error_body["error"].lower())

        _, audit = self.get_json("/audit")
        self.assertTrue(audit["valid"])


if __name__ == "__main__":
    unittest.main()
