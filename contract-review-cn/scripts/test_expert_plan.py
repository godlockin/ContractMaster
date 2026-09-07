"""Planning invariants; synthetic declarations are not real agent execution."""
import copy
import unittest
import argparse
import contextlib
import io
import json
import tempfile
from pathlib import Path

import expert_plan as e
import pipeline as p
import validate_depth as d
from test_depth import fixture, plan_fixture


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.bundle, self.depth = fixture()
        self.plan = plan_fixture(self.bundle, ["security"])
        self.depth["plan_digest"] = p.digest(self.plan)
        for row in list(self.depth["rounds"]):
            if row["role"] == "compliance":
                self.depth["rounds"].append({**copy.deepcopy(row), "role": "security"})

    def test_dynamic_expert_is_required_in_every_round(self):
        self.assertEqual(d.assess(self.bundle, self.depth, self.plan, [])["round_role_records"], 28)
        self.depth["rounds"].pop()
        with self.assertRaisesRegex(d.DepthError, "ROUND_COVERAGE"):
            d.assess(self.bundle, self.depth, self.plan, [])

    def test_unready_tools_and_unknown_scope_block(self):
        self.plan["experts"][-1]["tools"] = [{"name": "official_search", "purpose": "Verify sources",
            "required": True, "available": False, "data_scope": "public_abstract_query"}]
        self.plan["coverage"][0]["status"] = "applicable"
        self.plan["coverage"][1]["status"] = "unknown"
        self.depth["legal_domains"][1]["status"] = "unknown"
        self.depth["plan_digest"] = p.digest(self.plan)
        report = d.assess(self.bundle, self.depth, self.plan, [])
        self.assertEqual(report["status"], "PARTIAL_AUDIT")
        self.assertIn("REQUIRED_TOOL_UNAVAILABLE", report["blockers"])
        self.assertIn("PLAN_SCOPE_UNKNOWN", report["blockers"])

    def test_old_plan_and_missing_cross_reviewer_rejected(self):
        self.plan["revision"] += 1
        with self.assertRaisesRegex(d.DepthError, "STALE_PLAN"):
            d.assess(self.bundle, self.depth, self.plan, [])
        self.plan["coverage"][0]["challengers"] = ["legal"]
        with self.assertRaisesRegex(p.GateError, "CROSS_REVIEW"):
            e.assess(self.bundle, self.plan)

    def test_legacy_depth_cannot_claim_new_plan_complete(self):
        bundle, depth = fixture()
        report = d.assess(bundle, depth)
        self.assertIn("EXPERT_PLAN_NOT_VALIDATED", report["blockers"])

    def test_decoded_strings_and_keys_cannot_hide_private_values(self):
        for secret in ['客户"甲', '客户\\甲', '客户\n甲']:
            for data in [{"nested": [{"value": secret}]}, {"nested": [{secret: "value"}]}]:
                parsed = json.loads(json.dumps(data))
                self.assertTrue(p.contains_private_value(parsed, [secret]))
            self.assertFalse(p.contains_private_value({"value": "⟦ORG_0001⟧"}, [secret]))

    def test_plan_dynamic_scope_and_status_must_match_depth(self):
        self.plan["coverage"].append({"angle": "nuclear_safety", "status": "applicable", "reason": "Synthetic domain",
                                     "owners": ["compliance"], "challengers": ["security"]})
        self.depth["plan_digest"] = p.digest(self.plan)
        with self.assertRaisesRegex(d.DepthError, "DOMAIN_SCOPE_MISMATCH"):
            d.assess(self.bundle, self.depth, self.plan, [])
        self.depth["legal_domains"].append({"id": "nuclear_safety", "status": "not_applicable", "reason": "Mismatch", "source_ids": []})
        with self.assertRaisesRegex(d.DepthError, "APPLICABILITY_MISMATCH"):
            d.assess(self.bundle, self.depth, self.plan, [])
        self.depth["legal_domains"][-1]["status"] = "applicable"
        self.assertIn("APPLICABLE_DOMAIN_WITHOUT_SOURCE", d.assess(self.bundle, self.depth, self.plan, [])["blockers"])
        self.depth["legal_domains"][-1]["source_ids"] = ["S1"]
        self.assertEqual(d.assess(self.bundle, self.depth, self.plan, [])["status"], "DECLARED_DEPTH_COMPLETE")

    def test_actual_finding_unverified_basis_and_questions_block(self):
        finding = {"basis": [{"status": "unverified"}], "questions": ["Is authority confirmed?"]}
        result = d.assess(self.bundle, self.depth, self.plan, [{"findings": [finding]}])
        self.assertIn("FINDING_BASIS_UNVERIFIED", result["blockers"])
        self.assertIn("FINDING_QUESTIONS_UNRESOLVED", result["blockers"])
        finding["basis"] = []
        finding["question_resolutions"] = [{"question": finding["questions"][0], "status": "resolved",
             "reason": "Synthetic evidence confirmation", "evidence_refs": ["S1"]}]
        self.assertEqual(d.assess(self.bundle, self.depth, self.plan, [{"findings": [finding]}])["status"], "DECLARED_DEPTH_COMPLETE")
        finding["question_resolutions"][0]["evidence_refs"] = ["MISSING"]
        with self.assertRaisesRegex(d.DepthError, "QUESTION_RESOLUTION_INVALID"):
            d.assess(self.bundle, self.depth, self.plan, [{"findings": [finding]}])

    def test_active_plan_rejects_rollback_even_when_new_plan_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "private").mkdir()
            with self.assertRaisesRegex(p.GateError, "NOT_ACTIVATED"):
                e.check_active(run, self.bundle, self.plan)
            e.activate(run, self.bundle, self.plan)
            e.check_active(run, self.bundle, self.plan)
            updated = copy.deepcopy(self.plan)
            updated["revision"] = 2
            updated["experts"][-1]["readiness"] = "blocked"
            e.activate(run, self.bundle, updated)
            e.check_active(run, self.bundle, updated)
            with self.assertRaisesRegex(p.GateError, "NOT_ACTIVE"):
                e.check_active(run, self.bundle, self.plan)
            with self.assertRaisesRegex(p.GateError, "NOT_ADVANCING"):
                e.activate(run, self.bundle, self.plan)

    def test_missing_actual_results_cannot_claim_complete(self):
        self.assertIn("EXPERT_RESULTS_NOT_LINKED", d.assess(self.bundle, self.depth, self.plan)["blockers"])

    def test_results_accept_planned_extra_but_reject_missing_or_stale(self):
        results = [{"role": x["role"], "input_digest": self.bundle["input_digest"], "plan_digest": p.digest(self.plan),
                    "global_context_reviewed": True, "global_note": "Synthetic full context",
                    "reviews": [{"segment_id": s["id"], "levels": p.LEVELS, "review_note": "Synthetic review"}
                                for s in self.bundle["segments"]], "findings": []} for x in self.plan["experts"]]
        self.assertEqual(p.validate_results(self.bundle, results, self.plan)["roles"], 7)
        with self.assertRaisesRegex(p.GateError, "ROLE_COVERAGE"):
            p.validate_results(self.bundle, results[:-1], self.plan)
        results[-1]["plan_digest"] = "old"
        with self.assertRaisesRegex(p.GateError, "STALE_PLAN"):
            p.validate_results(self.bundle, results, self.plan)

    def test_released_run_loads_plan_and_blocks_private_plan_values(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source, entities, run = folder / "input.txt", folder / "entities.json", folder / "run"
            secret = '客户"甲'
            source.write_text("甲方：" + secret + "\n乙方交付服务。", encoding="utf-8")
            entities.write_text(json.dumps({"entities": [{"type": "ORG", "value": secret}]}, ensure_ascii=False), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                p.prepare(argparse.Namespace(input=[source], entities=entities, run=run))
                p.release(argparse.Namespace(run=run, attest_extraction_reviewed=True, attest_privacy_reviewed=True))
            bundle = p.read_json(run / "public/bundle.json")
            plan = plan_fixture(bundle, ["security"])
            plan_path = run / "reports/plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            e.activate(run, bundle, plan)
            paths = []
            for expert in plan["experts"]:
                result = {"role": expert["role"], "input_digest": bundle["input_digest"], "plan_digest": p.digest(plan),
                          "global_context_reviewed": True, "global_note": "Synthetic only", "findings": [],
                          "reviews": [{"segment_id": s["id"], "levels": p.LEVELS, "review_note": "Synthetic"} for s in bundle["segments"]]}
                path = run / "reports" / (expert["role"] + ".json")
                path.write_text(json.dumps(result), encoding="utf-8")
                paths.append(path)
            args = argparse.Namespace(run=run, plan=plan_path, results=paths)
            self.assertEqual(p.load_results(args)[2]["roles"], 7)
            candidate = p.read_json(paths[0])
            segment = bundle["segments"][0]
            candidate["findings"] = [{"id": "F1", "severity": "high", "confidence": "low", "risk": "Synthetic issue",
                "impact": "Synthetic impact", "suggestion": "Verify", "category": "law", "basis": [{"status": "unverified"}],
                "questions": ["Unresolved fact"], "evidence": [{"segment_id": segment["id"], "start": segment["start"],
                    "end": segment["end"], "quote": segment["text"]}]}]
            paths[0].write_text(json.dumps(candidate), encoding="utf-8")
            depth = copy.deepcopy(self.depth)
            depth.update(input_digest=bundle["input_digest"], plan_digest=p.digest(plan), relations=[], chains=[])
            for row in depth["rounds"]:
                row.update(segment_ids=[x["id"] for x in bundle["segments"]], relation_ids=[])
            args.depth = run / "reports/depth.json"
            args.depth.write_text(json.dumps(depth), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                p.report(args)
            rendered = (run / "reports/report.md").read_text()
            self.assertIn("深度审核状态：PARTIAL_AUDIT", rendered)
            self.assertIn("FINDING_BASIS_UNVERIFIED", rendered)
            self.assertIn("FINDING_QUESTIONS_UNRESOLVED", rendered)
            plan["change_log"].append(secret)
            plan["revision"] += 1
            e.activate(run, bundle, plan)
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            for path in paths:
                result = p.read_json(path)
                result["plan_digest"] = p.digest(plan)
                path.write_text(json.dumps(result), encoding="utf-8")
            with self.assertRaisesRegex(p.GateError, "PRIVATE_VALUE"):
                p.load_results(args)


if __name__ == "__main__":
    unittest.main()
