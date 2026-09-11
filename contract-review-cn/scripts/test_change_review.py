"""Synthetic contract-version comparisons; no model or private inputs."""
import argparse
import contextlib
import copy
import io
import json
import random
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import change_review as c
import pipeline as p
import expert_plan as e
import validate_depth as d
from test_dual_team import dual_fixture


class ChangeReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def prepare(self, old="未来三年300万/年。\n验收后付款。\n双方协商。\n", new="未来三年300万。\n验收后付款。\n双方协商。\n"):
        before, after = self.root / "v1.txt", self.root / "v2.txt"
        before.write_text(old, encoding="utf-8")
        after.write_text(new, encoding="utf-8")
        run = self.root / "run"
        with contextlib.redirect_stdout(io.StringIO()):
            p.prepare_change(argparse.Namespace(run=run, before=[before], after=[after], entities=None))
        return run, p.read_json(run / "private/candidate.json")

    def reviewed(self, bundle):
        bundle, plan, depth, results = dual_fixture(bundle)
        comparison = bundle["comparison"]
        for result in results:
            result["comparison_digest"] = comparison["comparison_digest"]
            result["change_reviews"] = [{"change_id": change["id"], "classification": "material", "decision": "reject",
                "unresolved": False, "analysis": "Synthetic: annual basis removed; commercial exposure needs negotiation.",
                "context_note": "Synthetic: cross-check payment and acceptance clauses.",
                "related_segment_ids": [bundle["segments"][0]["id"]]} for change in comparison["changes"]]
        for challenge in depth["cross_challenges"]:
            challenge["change_ids"] = [change["id"] for change in comparison["changes"]]
        return plan, depth, results

    def test_annual_basis_removal_computes_conditional_exposure(self):
        for old, new in (("未来三年 300万/年", "未来三年 300万"),
                         ("未来3年每年300万元", "未来3年300万元"),
                         ("未来三年300万／年", "未来三年300万")):
            alerts = c.semantic_alerts(old, new)
            scenario = next(a for a in alerts if a["code"] == "ANNUAL_TO_TERM_TOTAL_SCENARIO")
            self.assertEqual(scenario["old_total_if_annual"], "9000000")
            self.assertEqual(scenario["new_total_if_term_lump_sum"], "3000000")
            self.assertEqual(scenario["possible_reduction"], "6000000")
            self.assertTrue(scenario["requires_context_review"])

    def test_no_unjustified_total_for_multiple_amounts_or_month_basis(self):
        for old, new in (("未来三年300万/月", "未来三年300万"),
                         ("未来三年300万元/年，总额900万元", "未来三年300万元，总额900万元"),
                         ("未来三年300万美元/年", "未来三年300万欧元")):
            self.assertNotIn("ANNUAL_TO_TERM_TOTAL_SCENARIO", {a["code"] for a in c.semantic_alerts(old, new)})
        self.assertEqual(c.semantic_alerts("未来三年300万/年", "未来三年300万/年"), [])

    def test_currency_prefix_and_qualification_prevent_misleading_totals(self):
        for before, after in (("未来三年USD300万/年", "未来三年RMB300万"),
                              ("未来三年不支付300万/年", "未来三年不支付300万"),
                              ("未来三年上限300万/年", "未来三年上限300万")):
            self.assertNotIn("ANNUAL_TO_TERM_TOTAL_SCENARIO", {a["code"] for a in c.semantic_alerts(before, after)})
        self.assertEqual(c.amounts("USD300万")[0]["currency"], "USD")
        self.assertEqual(c.amounts("人民币300万")[0]["currency"], "CNY")
        self.assertNotIn("PRICING_BASIS_CHANGED", {a["code"] for a in c.semantic_alerts("300万/年", "300万／ 年")})

    def test_random_edit_ledger_reconstructs_new_version(self):
        rng = random.Random(911)
        for _ in range(80):
            before = "".join(rng.choices("甲乙丙。；\r\n /年300万", k=80))
            left, right = sorted(rng.sample(range(len(before)), 2))
            after = before[:left] + "".join(rng.choices("甲乙不得且或。", k=rng.randint(0, 12))) + before[right:]
            docs = [{"id": "D1", "source_index": 1, "text": before}, {"id": "D2", "source_index": 2, "text": after}]
            result = c.compare(docs, [{"before": 1, "after": 2}], [])
            c.check(result, docs)
            changes = {row["id"]: row for row in result["changes"]}
            reconstructed = "".join(before[op["before_start"]:op["before_end"]] if op["op"] == "equal"
                                    else changes[op["change_id"]]["after"]["text"] for op in result["pairs"][0]["operations"])
            self.assertEqual(reconstructed, after)

    def test_omitted_source_pair_rejected_even_with_fresh_digest(self):
        docs = [{"id": "D1", "source_index": 1, "text": "正文。"}, {"id": "D2", "source_index": 2, "text": "附件。"},
                {"id": "D3", "source_index": 3, "text": "正文。"}]
        result = c.compare(docs, [{"before": 1, "after": 3}, {"before": 2, "after": None}], [])
        result["pairs"].pop()
        result["comparison_digest"] = p.digest({k: v for k, v in result.items() if k != "comparison_digest"})
        with self.assertRaisesRegex(p.GateError, "COMPARISON_SOURCE_COVERAGE"):
            c.check(result, docs)

    def test_micro_changes_receive_review_priority(self):
        cases = [("甲方应当付款", "甲方可以付款", "OBLIGATION_STRENGTH"),
                 ("不得转让", "得转让", "NEGATION_OR_EXCEPTION"),
                 ("累计不超过100万元", "每次不超过100万元", "SCOPE_OR_CAP"),
                 ("验收合格后付款", "交付后付款", "CONDITION_OR_NOTICE"),
                 ("收到通知起10个工作日", "发出通知起10个自然日", "TIME_OR_DEADLINE"),
                 ("A且B", "A或B", "CONNECTIVE"), ("违约金10%", "违约金1%", "PERCENTAGE_CHANGED"),
                 ("10天", "5天", "NUMBER_OR_REFERENCE_CHANGED")]
        for before, after, code in cases:
            with self.subTest(code=code):
                self.assertIn(code, {a["code"] for a in c.semantic_alerts(before, after)})

    def test_shared_mapping_and_exact_change_coordinates(self):
        run, bundle = self.prepare("电话13800138000\r\n未来三年300万/年。", "电话13800138000\r\n未来三年300万。")
        comparison = bundle["comparison"]
        c.check(comparison, bundle["documents"])
        self.assertEqual(len(comparison["changes"]), 1)
        change = comparison["changes"][0]
        self.assertIn("/年", change["before"]["text"])
        self.assertEqual(len(p.read_json(run / "private/mapping.json")["entities"]), 1)
        self.assertNotIn("13800138000", json.dumps(bundle))
        for side in ("before", "after"):
            self.assertEqual("".join(r["quote"] for r in change[side]["ranges"]), change[side]["text"])
        self.assertTrue(any(edit["op"] == "delete" for edit in change["edits"]))
        self.assertFalse((run / "public").exists())

    def test_add_delete_move_and_identical(self):
        for before, after in (("A。B。C。", "C。A。B。"), ("A。B。", "A。"), ("A。", "A。B。"), ("A。", "A。")):
            docs = [{"id": "D1", "source_index": 1, "text": before}, {"id": "D2", "source_index": 2, "text": after}]
            result = c.compare(docs, [{"before": 1, "after": 2}], [])
            c.check(result, docs)
            if before == after:
                self.assertEqual(result["changes"], [])
            elif len(before) == len(after):
                self.assertTrue(any(change.get("move_peer") for change in result["changes"]))
            else:
                self.assertTrue(result["changes"])

    def test_missing_attachment_and_incomplete_source_remain_visible(self):
        docs = [{"id": "D1", "source_index": 1, "text": "正文。"}, {"id": "D2", "source_index": 2, "text": "附件。"},
                {"id": "D3", "source_index": 3, "text": "正文。"}]
        result = c.compare(docs, [{"before": 1, "after": 3}, {"before": 2, "after": None}], [])
        self.assertEqual(result["changes"][0]["kind"], "delete")
        c.check(result, docs)
        result = c.compare(docs, [{"before": 1, "after": 3}, {"before": 2, "after": 4}], [{"source_index": 4, "code": "FAILED"}])
        self.assertIn("COMPARISON_INPUTS_INCOMPLETE", result["blockers"])

    def test_word_tracked_changes_use_final_projection(self):
        path = self.root / "revised.docx"
        ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
        xml = f'<w:document {ns}><w:body><w:p><w:r><w:t>未来三年300万</w:t></w:r><w:del><w:r><w:delText>/年</w:delText></w:r></w:del><w:ins><w:r><w:t>。</w:t></w:r></w:ins></w:p></w:body></w:document>'
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("word/document.xml", xml)
        self.assertIn("/年", p.extract(path)[0][0][1])
        parts, warnings = p.extract(path, docx_view="final")
        self.assertEqual(parts[0][1], "未来三年300万。\n")
        self.assertIn("DOCX_FINAL_TEXT_PROJECTION_REQUIRES_LOCAL_REVIEW", warnings)

    def test_omitted_change_or_stale_digest_cannot_validate(self):
        _, bundle = self.prepare()
        plan, depth, results = self.reviewed(bundle)
        p.validate_results(bundle, results, plan)
        results[0]["change_reviews"] = []
        with self.assertRaisesRegex(p.GateError, "CHANGE_REVIEW_COVERAGE"):
            p.validate_results(bundle, results, plan)
        plan, depth, results = self.reviewed(bundle)
        results[-1]["comparison_digest"] = "stale"
        with self.assertRaisesRegex(p.GateError, "CHANGE_REVIEW_STALE"):
            p.validate_results(bundle, results, plan)

    def test_unresolved_or_one_sided_change_challenge_blocks_complete(self):
        _, bundle = self.prepare()
        plan, depth, results = self.reviewed(bundle)
        self.assertEqual(d.assess(bundle, depth, plan, results)["status"], "DECLARED_DEPTH_COMPLETE")
        results[0]["change_reviews"][0]["unresolved"] = True
        self.assertIn("CHANGE_ISSUES_UNRESOLVED", d.assess(bundle, depth, plan, results)["blockers"])
        results[0]["change_reviews"][0]["unresolved"] = False
        depth["cross_challenges"][0]["change_ids"] = []
        self.assertIn("CHANGES_NOT_CROSS_CHALLENGED", d.assess(bundle, depth, plan, results)["blockers"])

    def test_report_contains_delta_and_comparison_digest(self):
        run, bundle = self.prepare()
        plan, depth, results = self.reviewed(bundle)
        with contextlib.redirect_stdout(io.StringIO()):
            p.release(argparse.Namespace(run=run, attest_extraction_reviewed=True, attest_privacy_reviewed=True))
            e.activate(run, bundle, plan)
            pp, dp = run / "reports/plan.json", run / "reports/depth.json"
            p.write_json(pp, plan)
            p.write_json(dp, depth)
            paths = []
            for result in results:
                path = run / "reports" / (result["role"] + ".json")
                p.write_json(path, result)
                paths.append(path)
            p.report(argparse.Namespace(run=run, plan=pp, depth=dp, results=paths, revision=1))
        report = run / "reports/versions/v000001"
        text = (report / "report.md").read_text()
        self.assertIn("可能减少600万", text)
        self.assertIn("计费单位或周期变化", text)
        self.assertEqual(p.read_json(report / "manifest.json")["comparison_digest"], bundle["comparison"]["comparison_digest"])

    def test_coarse_alignment_is_partial_and_ledger_tamper_rejected(self):
        docs = [{"id": "D1", "source_index": 1, "text": "a" * 2100}, {"id": "D2", "source_index": 2, "text": "b" * 2100}]
        result = c.compare(docs, [{"before": 1, "after": 2}], [])
        self.assertIn("COARSE_CHANGE_REQUIRES_PARTITIONED_REVIEW", result["blockers"])
        c.check(result, docs)
        result["pairs"][0]["operations"][0]["before_start"] = 1
        result["comparison_digest"] = p.digest({k: v for k, v in result.items() if k != "comparison_digest"})
        with self.assertRaisesRegex(p.GateError, "COMPARISON_COVERAGE_GAP"):
            c.check(result, docs)

    def test_cli_prepares_only_private_comparison(self):
        before, after = self.root / "v1.txt", self.root / "v2.txt"
        before.write_text("未来三年300万/年")
        after.write_text("未来三年300万")
        run = self.root / "run"
        result = subprocess.run([sys.executable, str(Path(p.__file__)), "prepare-change", "--run", str(run),
                                 "--before", str(before), "--after", str(after)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("300万", result.stdout + result.stderr)
        self.assertTrue((run / "private/candidate.json").exists())
        self.assertFalse((run / "public").exists())


if __name__ == "__main__":
    unittest.main()
