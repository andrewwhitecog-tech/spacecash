import shutil
import sys
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spacecash_core import SpaceCashLedger, protocol  # noqa: E402


TMP_ROOT = ROOT / "_tmp"


def make_wallet(ledger, label="Test Wallet"):
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_numbers = private_key.public_key().public_numbers()
    public_jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": protocol.b64url_encode(public_numbers.x.to_bytes(32, "big")),
        "y": protocol.b64url_encode(public_numbers.y.to_bytes(32, "big")),
    }
    wallet = ledger.register_wallet(public_jwk, label)
    return wallet, private_key


def sign_payload(private_key, payload):
    signature_der = private_key.sign(
        protocol.canonical_json(payload).encode("utf-8"),
        ec.ECDSA(hashes.SHA256()),
    )
    r, s = utils.decode_dss_signature(signature_der)
    return protocol.b64url_encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


def signed_transfer(private_key, sender, recipient, amount, memo="", nonce="test-nonce-123456"):
    payload = {
        "chain_id": protocol.CHAIN_ID,
        "version": protocol.SIGNED_PAYLOAD_VERSION,
        "action": "transfer",
        "sender": sender,
        "recipient": recipient,
        "amount": amount,
        "memo": memo,
        "nonce": nonce,
    }
    return {"auth_payload": payload, "signature": sign_payload(private_key, payload)}


class LedgerTestCase(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.paths = []
        self.db_path = TMP_ROOT / f"test_spacecash_{protocol.hash_text(id(self))[:12]}.sqlite3"
        self.paths.append(self.db_path)
        self.ledger = SpaceCashLedger(self.db_path)

    def tearDown(self):
        for path in self.paths:
            for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
                if candidate.exists():
                    candidate.unlink()

    def copy_ledger(self, filename="peer.sqlite3"):
        self.ledger.ensure_schema()
        peer_path = TMP_ROOT / f"test_spacecash_{protocol.hash_text(filename + str(id(self)))[:12]}.sqlite3"
        self.paths.append(peer_path)
        shutil.copy2(self.db_path, peer_path)
        return SpaceCashLedger(peer_path)


class ProtocolConfigTests(unittest.TestCase):
    def test_protocol_config_exposes_security_versions(self):
        config = protocol.chain_config()
        self.assertEqual(config["chain_id"], protocol.CHAIN_ID)
        self.assertEqual(config["wallet_export_cipher"], "AES-256-GCM")
        self.assertEqual(config["wallet_export_kdf"], "PBKDF2-SHA256-250000")
        self.assertEqual(config["fork_choice_policy"], protocol.FORK_CHOICE_POLICY)
        self.assertEqual(config["producer_policy_version"], protocol.PRODUCER_POLICY_VERSION)
        self.assertEqual(config["validator_policy_version"], protocol.VALIDATOR_POLICY_VERSION)
        self.assertEqual(config["consensus_spec_id"], protocol.CONSENSUS_SPEC_ID)
        self.assertEqual(config["consensus_spec_hash"], protocol.consensus_spec_hash())
        self.assertEqual(config["monetary_policy_id"], protocol.MONETARY_POLICY_ID)
        self.assertEqual(config["monetary_policy_hash"], protocol.monetary_policy_hash())
        self.assertEqual(config["genesis_plan_id"], protocol.GENESIS_PLAN_ID)
        self.assertEqual(config["genesis_plan_hash"], protocol.genesis_plan_hash())
        self.assertEqual(config["supply_cap_units"], protocol.GENESIS_UNITS)
        self.assertEqual(config["wallet_policy_id"], protocol.WALLET_POLICY_ID)
        self.assertEqual(config["wallet_policy_hash"], protocol.wallet_policy_hash())
        self.assertEqual(config["address_version"], protocol.ADDRESS_VERSION)
        spec = protocol.consensus_spec()
        self.assertEqual(spec["spec_hash"], protocol.consensus_spec_hash())
        self.assertFalse(spec["fork_choice"]["automatic_reorgs"])
        self.assertEqual(spec["ledger"]["monetary_policy"]["hash"], protocol.monetary_policy_hash())
        self.assertEqual(spec["ledger"]["genesis_plan"]["hash"], protocol.genesis_plan_hash())
        self.assertIn("external audit closure", spec["mainnet_gaps"])
        monetary = protocol.monetary_policy()
        self.assertEqual(monetary["policy_hash"], protocol.monetary_policy_hash())
        self.assertEqual(monetary["supply"]["supply_cap_units"], protocol.GENESIS_UNITS)
        self.assertEqual(monetary["issuance"]["block_reward_units"], 0)
        self.assertFalse(monetary["issuance"]["mint_route_available"])
        genesis = protocol.genesis_plan()
        self.assertEqual(genesis["plan_hash"], protocol.genesis_plan_hash())
        self.assertFalse(genesis["source_of_truth"]["devnet_history_carried_to_mainnet"])
        self.assertFalse(genesis["allocation_boundary"]["candidate_private_keys_allowed"])
        policy = protocol.wallet_policy()
        self.assertEqual(policy["policy_hash"], protocol.wallet_policy_hash())
        self.assertEqual(policy["manual_gate"]["status"], "not_complete")
        self.assertFalse(policy["custody"]["custodial_operations_allowed"])

    def test_merkle_proof_verifies_inclusion_and_rejects_tampering(self):
        txids = ["SCTX-AAA", "SCTX-BBB", "SCTX-CCC"]
        proof = protocol.merkle_proof(txids, "sctx-bbb")
        self.assertEqual(proof["index"], 1)
        self.assertEqual(proof["total"], 3)
        self.assertEqual(proof["root"], protocol.merkle_root(txids))
        self.assertTrue(protocol.verify_merkle_proof("SCTX-BBB", proof["proof"], proof["root"]))
        self.assertFalse(protocol.verify_merkle_proof("SCTX-BBB", proof["proof"], "0" * 64))
        with self.assertRaisesRegex(ValueError, "not included"):
            protocol.merkle_proof(txids, "SCTX-NOT-THERE")


class SignedMempoolTests(LedgerTestCase):
    def test_signed_transfer_mines_once_and_rejects_nonce_reuse(self):
        alice, alice_key = make_wallet(self.ledger, "Alice")
        bob, _ = make_wallet(self.ledger, "Bob")
        self.ledger.faucet(alice["address"], "20")

        first = signed_transfer(alice_key, alice["address"], bob["address"], "5", "first", "nonce-fixed-123456")
        queued = self.ledger.submit_transfer(first)
        self.assertTrue(queued["accepted"])

        duplicate = self.ledger.submit_transfer(first)
        self.assertFalse(duplicate["accepted"])
        self.assertTrue(duplicate["duplicate"])

        second_same_nonce = signed_transfer(alice_key, alice["address"], bob["address"], "4", "second", "nonce-fixed-123456")
        with self.assertRaisesRegex(ValueError, "already queued"):
            self.ledger.submit_transfer(second_same_nonce)

        mined = self.ledger.mine_pending_transactions()
        self.assertEqual(mined["mined_count"], 1)
        self.assertGreaterEqual(int(mined["block"]["block_version"]), 2)

        after_mine_same_nonce = signed_transfer(alice_key, alice["address"], bob["address"], "3", "third", "nonce-fixed-123456")
        with self.assertRaisesRegex(ValueError, "already been mined"):
            self.ledger.submit_transfer(after_mine_same_nonce)

        self.assertEqual(self.ledger.wallet_summary(bob["address"])["balance"], "5")
        self.assertTrue(self.ledger.audit()["valid"])

    def test_transaction_inclusion_proof_for_batched_block(self):
        alice, alice_key = make_wallet(self.ledger, "Proof Alice")
        bob, _ = make_wallet(self.ledger, "Proof Bob")
        carol, _ = make_wallet(self.ledger, "Proof Carol")
        self.ledger.faucet(alice["address"], "20")

        self.ledger.submit_transfer(signed_transfer(
            alice_key,
            alice["address"],
            bob["address"],
            "3",
            "proof one",
            "proof-nonce-1",
        ))
        self.ledger.submit_transfer(signed_transfer(
            alice_key,
            alice["address"],
            carol["address"],
            "4",
            "proof two",
            "proof-nonce-2",
        ))

        mined = self.ledger.mine_pending_transactions()
        self.assertEqual(mined["mined_count"], 2)
        self.assertEqual(mined["block"]["tx_count"], 2)

        for mined_tx in mined["mined"]:
            proof = self.ledger.transaction_proof(mined_tx["txid"])
            self.assertTrue(proof["included"])
            self.assertTrue(proof["verified"])
            self.assertEqual(proof["total"], 2)
            self.assertEqual(proof["block"]["hash"], mined["block"]["block_hash"])
            self.assertEqual(proof["merkle_root"], mined["block"]["merkle_root"])
            self.assertTrue(protocol.verify_merkle_proof(mined_tx["txid"], proof["proof"], proof["merkle_root"]))

        self.assertIsNone(self.ledger.transaction_proof("SCTX-NOT-FOUND"))


class CheckpointVoteTests(LedgerTestCase):
    def test_registered_validator_vote_reaches_quorum_and_tamper_rejected(self):
        validator, validator_key = make_wallet(self.ledger, "Validator")
        self.ledger.add_validator(validator["address"])

        payload = self.ledger.checkpoint_vote_payload(validator["address"])
        result = self.ledger.submit_checkpoint_vote({
            "auth_payload": payload,
            "signature": sign_payload(validator_key, payload),
        })
        self.assertTrue(result["quorum"]["quorum_reached"])

        tampered = dict(payload)
        tampered["chain_digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "chain_digest"):
            self.ledger.submit_checkpoint_vote({
                "auth_payload": tampered,
                "signature": sign_payload(validator_key, tampered),
            })

        with self.assertRaisesRegex(ValueError, "registered validator"):
            self.ledger.checkpoint_vote_payload("SPACE-1234567890ABCDEF")

        self.assertTrue(self.ledger.audit()["valid"])


class MainnetReadinessTests(LedgerTestCase):
    def test_readiness_reports_automated_and_manual_blockers(self):
        readiness = self.ledger.mainnet_readiness()
        self.assertFalse(readiness["mainnet_ready"])
        self.assertFalse(readiness["automated_release_candidate"])
        self.assertTrue(readiness["audit"]["valid"])
        self.assertIn("validators_configured", readiness["automated_blockers"])
        self.assertIn("checkpoint_quorum_reached", readiness["automated_blockers"])
        self.assertIn("bootstrap_peers_configured", readiness["automated_blockers"])
        self.assertIn("public_testnet_complete", readiness["manual_blockers"])

    def test_readiness_allows_clean_automated_candidate_but_keeps_manual_gates(self):
        alice, alice_key = make_wallet(self.ledger, "Alice Validator")
        bob, _ = make_wallet(self.ledger, "Bob")
        self.ledger.faucet(alice["address"], "20")
        self.ledger.submit_transfer(signed_transfer(
            alice_key,
            alice["address"],
            bob["address"],
            "2",
            "readiness signed spend",
            "readiness-nonce-123456",
        ))
        self.ledger.mine_pending_transactions()
        self.ledger.add_validator(alice["address"])
        checkpoint_payload = self.ledger.checkpoint_vote_payload(alice["address"])
        self.ledger.submit_checkpoint_vote({
            "auth_payload": checkpoint_payload,
            "signature": sign_payload(alice_key, checkpoint_payload),
        })
        self.ledger.set_bootstrap_peers([{
            "url": "http://127.0.0.1:8876",
            "label": "local-test-bootstrap",
            "notes": "Regression-test bootstrap peer.",
        }])

        readiness = self.ledger.mainnet_readiness()
        self.assertTrue(readiness["automated_release_candidate"])
        self.assertFalse(readiness["mainnet_ready"])
        self.assertEqual(readiness["automated_blockers"], [])
        self.assertEqual(readiness["audit"]["warning_count"], 0)
        self.assertIn("external_security_review_complete", readiness["manual_blockers"])


class StripeCreditPurchaseTests(LedgerTestCase):
    def test_stripe_credit_purchase_posts_one_way_idempotent_credit(self):
        wallet, _ = make_wallet(self.ledger, "Stripe Credit Wallet")

        first = self.ledger.stripe_credit_purchase("cs_test_spacecash_123456", wallet["address"], "10", usd_amount="10.00")
        self.assertEqual("10", first["balance"])
        self.assertTrue(first["stripe_credit"]["credited"])
        self.assertFalse(first["stripe_credit"]["idempotent"])

        second = self.ledger.stripe_credit_purchase("cs_test_spacecash_123456", wallet["address"], "10", usd_amount="10.00")
        self.assertEqual(first["txid"], second["txid"])
        self.assertEqual("10", second["balance"])
        self.assertFalse(second["stripe_credit"]["credited"])
        self.assertTrue(second["stripe_credit"]["idempotent"])

        other, _ = make_wallet(self.ledger, "Other Stripe Wallet")
        with self.assertRaisesRegex(ValueError, "already credited"):
            self.ledger.stripe_credit_purchase("cs_test_spacecash_123456", other["address"], "10", usd_amount="10.00")

        tx = self.ledger.transaction(first["txid"])
        self.assertEqual("stripe_credit_purchase", tx["kind"])
        self.assertEqual("stripe_spacecash", tx["related_source"])
        self.assertEqual("cs_test_spacecash_123456", tx["related_id"])
        audit = self.ledger.audit()
        self.assertTrue(audit["valid"])
        self.assertEqual(0, audit["counts"]["legacy_unsigned_spends"])



class SnapshotSyncPolicyTests(LedgerTestCase):
    def test_append_only_peer_snapshot_imports_when_policy_allows(self):
        peer = self.copy_ledger()
        wallet, _ = make_wallet(peer, "Peer Wallet")
        peer.faucet(wallet["address"], "3")

        snapshot = peer.chain_snapshot(include_service_data=False)
        evaluation = self.ledger.evaluate_chain_snapshot(snapshot)
        self.assertEqual(evaluation["status"], "peer_ahead_candidate")
        self.assertTrue(evaluation["fork_choice"]["import_allowed"])

        result = self.ledger.import_chain_snapshot(snapshot, backup=False)
        self.assertTrue(result["imported"])
        self.assertEqual(self.ledger.wallet_summary(wallet["address"])["balance"], "3")
        self.assertTrue(self.ledger.audit()["valid"])

    def test_disallowed_producer_snapshot_is_rejected(self):
        peer = self.copy_ledger()
        wallet, _ = make_wallet(peer, "Rogue Producer Target")

        conn = peer.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            txid = peer._record_tx_locked(
                conn,
                "faucet",
                protocol.TREASURY,
                wallet["address"],
                protocol.amount_to_units("2"),
                "rogue producer faucet",
                mine=False,
            )
            height = peer._mine_block_batch(conn, [txid], producer_id="rogue-producer-1")
            conn.execute("UPDATE transactions SET block_height = ? WHERE txid = ?", (height, txid))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        snapshot = peer.chain_snapshot(include_service_data=False)
        evaluation = self.ledger.evaluate_chain_snapshot(snapshot)
        self.assertEqual(evaluation["status"], "producer_policy_rejected")
        self.assertFalse(evaluation["producer_policy"]["valid"])
        self.assertFalse(evaluation["fork_choice"]["import_allowed"])

        result = self.ledger.import_chain_snapshot(snapshot, backup=False)
        self.assertFalse(result["imported"])
        self.assertIn("producer", result["reason"].lower())


if __name__ == "__main__":
    unittest.main()
