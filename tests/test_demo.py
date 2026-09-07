from pathlib import Path
import shutil
import tempfile
import unittest

import demo


class OfflineDemoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_replay_and_refuse_overwrite(self):
        output = self.root / "run"
        result = demo.run_demo(output)
        self.assertEqual(result["model_calls"], 0)
        self.assertFalse(result["new_legal_review"])
        self.assertEqual(result["archived_findings"], 3)
        report = (output / "REPORT.md").read_bytes()
        with self.assertRaises((demo.pipeline.GateError, FileExistsError)):
            demo.run_demo(output)
        self.assertEqual((output / "REPORT.md").read_bytes(), report)

    def test_changed_fixture_rejected(self):
        target = self.root / "contract-review-cn/evals"
        shutil.copytree(demo.ROOT / "contract-review-cn/evals", target)
        with (target / "inputs/C01.txt").open("a") as stream:
            stream.write("changed")
        with self.assertRaisesRegex(demo.pipeline.GateError, "DEMO_FIXTURE_CHANGED"):
            demo.run_demo(self.root / "run", self.root)

    def test_changed_archive_rejected(self):
        target = self.root / "contract-review-cn/evals"
        shutil.copytree(demo.ROOT / "contract-review-cn/evals", target)
        with (target / "results/blind-review.json").open("a") as stream:
            stream.write(" ")
        with self.assertRaisesRegex(demo.pipeline.GateError, "DEMO_ARCHIVED_REVIEW_CHANGED"):
            demo.run_demo(self.root / "run", self.root)


if __name__ == "__main__":
    unittest.main()
