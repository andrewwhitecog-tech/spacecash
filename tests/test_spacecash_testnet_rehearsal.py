import hashlib
import json
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spacecash_core import protocol  # noqa: E402
from tests.test_spacecash_core import TMP_ROOT  # noqa: E402
from tools.spacecash_testnet_rehearsal import run_rehearsal  # noqa: E402


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class TestnetRehearsalTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.out_dir = TMP_ROOT / f"test_spacecash_rehearsal_{protocol.hash_text(id(self))[:12]}"

    def tearDown(self):
        if self.out_dir.exists():
            shutil.rmtree(self.out_dir)

    def test_rehearsal_runs_nodes_and_writes_report(self):
        result = run_rehearsal(
            out_dir=self.out_dir,
            node_count=3,
            base_port=0,
            force=True,
            timeout=3,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["node_count"], 3)
        self.assertEqual(result["validators"], 3)
        self.assertEqual(result["validator_quorum"], 2)
        self.assertEqual(result["manual_gate_status"], "local_rehearsal_only")
        report_path = Path(result["report"])
        self.assertTrue(report_path.exists())
        self.assertEqual(file_hash(report_path), result["report_sha256"])
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertTrue(report["summary"]["ok"])
        self.assertEqual(len(report["nodes"]), 3)
        self.assertFalse(report["summary"]["failures"])
        for node in report["nodes"]:
            self.assertTrue(node["health"]["json"]["ok"])
            self.assertTrue(node["readiness"]["json"]["automated_release_candidate"])
            self.assertFalse(node["readiness"]["json"]["mainnet_ready"])
            self.assertTrue(node["checkpoint_quorum"]["json"]["quorum_reached"])
            self.assertTrue(node["audit"]["json"]["valid"])


if __name__ == "__main__":
    unittest.main()
