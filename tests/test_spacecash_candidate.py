import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spacecash_core import protocol  # noqa: E402
from tests.test_spacecash_core import TMP_ROOT  # noqa: E402
from tools.spacecash_candidate import build_candidate  # noqa: E402


class CandidateBuilderTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.db_path = TMP_ROOT / f"test_spacecash_candidate_{protocol.hash_text(id(self))[:12]}.sqlite3"

    def tearDown(self):
        for candidate in (self.db_path, Path(str(self.db_path) + "-wal"), Path(str(self.db_path) + "-shm")):
            if candidate.exists():
                candidate.unlink()

    def test_candidate_builder_creates_clean_automated_release_candidate(self):
        result = build_candidate(
            self.db_path,
            bootstrap_peers=["http://127.0.0.1:8876"],
            force=True,
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["audit"]["valid"])
        self.assertEqual(result["audit"]["warning_count"], 0)
        self.assertGreater(result["audit"]["counts"]["versioned_blocks"], 0)
        self.assertEqual(result["audit"]["counts"]["legacy_unsigned_spends"], 0)
        self.assertTrue(result["checkpoint_quorum"])
        self.assertTrue(result["readiness"]["automated_release_candidate"])
        self.assertFalse(result["readiness"]["mainnet_ready"])
        self.assertEqual(result["readiness"]["automated_blockers"], [])
        self.assertIn("public_testnet_complete", result["readiness"]["manual_blockers"])

    def test_candidate_builder_supports_multi_validator_quorum(self):
        result = build_candidate(
            self.db_path,
            bootstrap_peers=["http://127.0.0.1:8876", "http://127.0.0.1:8877"],
            validator_count=3,
            validator_quorum=2,
            force=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(len(result["validators"]), 3)
        self.assertEqual(result["validator_quorum"], 2)
        self.assertEqual(result["audit"]["counts"]["validators"], 3)
        self.assertEqual(result["audit"]["counts"]["checkpoint_votes"], 3)
        self.assertTrue(result["checkpoint_quorum"])
        self.assertEqual(result["readiness"]["automated_blockers"], [])


if __name__ == "__main__":
    unittest.main()
