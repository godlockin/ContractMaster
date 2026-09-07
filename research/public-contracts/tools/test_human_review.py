import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from build_human_review import build


class HumanReviewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "reviews").mkdir()
        (self.root / "original.txt").write_text("公开原件", encoding="utf-8")
        self.text = "验收后付款。<script>bad</script>重复重复"
        (self.root / "sanitized.txt").write_text(self.text, encoding="utf-8")
        self.case = {"id": "T01", "title": "公开模板", "original_path": "original.txt", "sanitized_path": "sanitized.txt"}
        self.write_manifest()
        self.review = {"case_id": "T01", "input_sha256": hashlib.sha256(self.text.encode()).hexdigest(), "review_mode": "pilot", "findings": [{"id": "T01-1", "risk": "=1+1", "evidence": [{"quote": "验收后付款。"}]}]}

    def write_manifest(self):
        (self.root / "manifest.json").write_text(json.dumps({"cases": [self.case]}), encoding="utf-8")

    def write_review(self):
        (self.root / "reviews/r.json").write_text(json.dumps({"reviews": [self.review]}), encoding="utf-8")

    def test_missing_review_is_pending(self):
        result = build(self.root)
        self.assertEqual(result["review_records"], 0)
        self.assertIn("尚未执行", (self.root / "human-review/index.html").read_text())

    def test_valid_evidence_and_formula_escape(self):
        self.review["findings"][0]["evidence"] = [{"quote": "<script>bad</script>"}]
        self.write_review()
        self.assertEqual(build(self.root)["findings"], 1)
        self.assertIn("&lt;script&gt;bad", (self.root / "human-review/index.html").read_text())
        self.assertIn("'=1+1", (self.root / "human-review/adjudication-template.csv").read_text())

    def test_stale_input_rejected(self):
        self.review["input_sha256"] = "stale"
        self.write_review()
        with self.assertRaisesRegex(ValueError, "Stale"):
            build(self.root)

    def test_ambiguous_or_wrong_quote_rejected(self):
        for quote in ["重复", "不存在"]:
            self.review["findings"][0]["evidence"] = [{"quote": quote}]
            self.write_review()
            with self.assertRaises(ValueError):
                build(self.root)

    def test_path_escape_rejected(self):
        self.case["original_path"] = "../outside.txt"
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "escapes"):
            build(self.root)

    def test_cross_review_binding_and_evidence(self):
        self.write_review()
        directory = self.root / "cross-review"
        directory.mkdir()
        cross = {"case_id": "T01", "input_sha256": self.review["input_sha256"],
                 "reviewed_report_sha256": hashlib.sha256((self.root / "reviews/r.json").read_bytes()).hexdigest(),
                 "judgments": [{"finding_id": "T01-1", "decision": "partial", "reason": "反证",
                                "counterevidence": [{"quote": "验收后付款。", "start": 0, "end": 6}]}]}
        path = directory / "T01.json"
        path.write_text(json.dumps(cross))
        self.assertEqual(build(self.root)["cross_reviewed_findings"], 1)
        cross["reviewed_report_sha256"] = "stale"
        path.write_text(json.dumps(cross))
        with self.assertRaisesRegex(ValueError, "Stale cross-review report"):
            build(self.root)


if __name__ == "__main__":
    unittest.main()
