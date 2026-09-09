"""Synthetic two-team contracts; no real expert execution is claimed."""
import copy
import argparse
import contextlib
import io
import tempfile
from pathlib import Path
import unittest
import pipeline as p
import expert_plan as e
import validate_depth as d
from test_depth import fixture, plan_fixture


def dual_fixture(actual_bundle=None):
    bundle, depth = fixture()
    if actual_bundle is not None:
        bundle = actual_bundle
        depth["input_digest"] = bundle["input_digest"]
    plan = plan_fixture(bundle, sorted(e.REVERSE_ROLES))
    plan["schema_version"] = 2
    for expert in plan["experts"]:
        expert["team"] = "B" if expert["role"] in e.REVERSE_ROLES else "A"
    for angle in plan["coverage"]:
        angle["challengers"] = ["reverse_legal"]
    pd = p.digest(plan)
    depth["plan_digest"] = pd
    segment_ids = [s["id"] for s in bundle["segments"]]
    results = []
    for expert in plan["experts"]:
        role = expert["role"]
        first = {"context_id": "isolated-" + role, "other_results_read": [], "input_digest": bundle["input_digest"],
                 "plan_digest": pd, "segment_ids": segment_ids, "summary": "Synthetic independent review"}
        results.append({"role": role, "team": expert["team"], "input_digest": bundle["input_digest"],
                        "plan_digest": pd, "first_pass": first, "global_context_reviewed": True,
                        "global_note": "Synthetic", "reviews": [{"segment_id": sid, "levels": p.LEVELS,
                        "review_note": "Synthetic"} for sid in segment_ids], "findings": []})
    depth["rounds"] = [{"role": r["role"], "round": n, "segment_ids": segment_ids,
                        "relation_ids": [] if n == 1 else ["E1", "E2"], "review_note": "Synthetic",
                        "first_pass_digest": p.digest(r["first_pass"])} for r in results for n in range(1, 5)]
    depth["team_passes"] = [{"team": team, "first_pass_digests": {r["role"]: p.digest(r["first_pass"])
        for r in results if r["team"] == team},
        "domain_checks": [{"id": row["id"], "status": "reviewed", "reason": "Synthetic independent scope"} for row in depth["legal_domains"]],
        "source_checks": [{"id": kind, "status": "reviewed", "reason": "Synthetic independent source check"} for kind in d.SOURCE_KINDS]}
        for team in ("A", "B")]
    depth["cross_challenges"] = [{"id": str(n), "author": author, "target": target, "angle": "civil_contract",
        "question": "Synthetic counterexample?", "response": "Synthetic response", "reason": "Synthetic resolution",
        "status": "resolved", "outcome": "upheld", "evidence_refs": [segment_ids[0]], "finding_ids": []}
        for n, (author, target) in enumerate((("legal", "reverse_legal"), ("reverse_legal", "legal")))]
    return bundle, plan, depth, results


class DualTeamTests(unittest.TestCase):
    def test_dual_report_version_integration(self):
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            root = Path(temporary)
            source = root / "input.txt"
            source.write_text("甲\n乙\n丙\n")
            run = root / "run"
            p.prepare(argparse.Namespace(run=run, input=[source], entities=None))
            p.release(argparse.Namespace(run=run, attest_extraction_reviewed=True, attest_privacy_reviewed=True))
            bundle, plan, depth, results = dual_fixture(p.read_json(run / "public/bundle.json"))
            e.activate(run, bundle, plan)
            plan_path, depth_path = run / "reports/plan.json", run / "reports/depth.json"
            p.write_json(plan_path, plan)
            p.write_json(depth_path, depth)
            paths = []
            for result in results:
                path = run / "reports" / (result["role"] + ".json")
                p.write_json(path, result)
                paths.append(path)
            p.report(argparse.Namespace(run=run, results=paths, plan=plan_path, depth=depth_path, revision=1))
            output = run / "reports/versions/v000001"
            self.assertIn("双组交叉质询", (output / "report.md").read_text())
            manifest = p.read_json(output / "manifest.json")
            self.assertEqual(manifest["declared_depth_status"], "DECLARED_DEPTH_COMPLETE")
            self.assertEqual(manifest["depth_digest"], p.digest(depth))

    def setUp(self):
        self.bundle, self.plan, self.depth, self.results = dual_fixture()

    def assess(self):
        return d.assess(self.bundle, self.depth, self.plan, self.results)

    def test_complete_nine_role_four_round_declarations(self):
        result = self.assess()
        self.assertEqual(result["status"], "DECLARED_DEPTH_COMPLETE")
        self.assertEqual(result["round_role_records"], 36)

    def test_legacy_never_complete(self):
        bundle, depth = fixture()
        plan = plan_fixture(bundle)
        depth["plan_digest"] = p.digest(plan)
        result = d.assess(bundle, depth, plan, [])
        self.assertIn("DUAL_TEAM_PLAN_REQUIRED", result["blockers"])

    def test_missing_reverse_team_or_wrong_challenger(self):
        self.plan["experts"].pop()
        with self.assertRaisesRegex(p.GateError, "REVERSE_ROLES"):
            e.assess(self.bundle, self.plan)
        self.setUp()
        self.plan["coverage"][0]["challengers"] = ["dispute"]
        with self.assertRaisesRegex(p.GateError, "CROSS_TEAM"):
            e.assess(self.bundle, self.plan)

    def test_context_reuse_or_other_answers_rejected(self):
        for mutate in (lambda r: r[-1]["first_pass"].update(context_id=r[0]["first_pass"]["context_id"]),
                       lambda r: r[-1]["first_pass"].update(other_results_read=["legal"])):
            results = copy.deepcopy(self.results)
            mutate(results)
            with self.assertRaises(p.GateError):
                p.validate_results(self.bundle, results, self.plan)

    def test_missing_result_or_round_or_dossier_rejected(self):
        self.results.pop()
        with self.assertRaises((p.GateError, d.DepthError)):
            self.assess()
        self.setUp()
        self.depth["rounds"].pop()
        with self.assertRaises(d.DepthError):
            self.assess()
        self.setUp()
        self.depth["team_passes"].pop()
        with self.assertRaisesRegex(d.DepthError, "TEAM_PASSES"):
            self.assess()

    def test_stale_first_pass_and_unknown_scope(self):
        self.depth["rounds"][0]["first_pass_digest"] = "stale"
        with self.assertRaisesRegex(d.DepthError, "FIRST_PASS_STALE"):
            self.assess()
        self.setUp()
        self.depth["team_passes"][1]["domain_checks"][0]["status"] = "unknown"
        self.assertIn("TEAM_SCOPE_UNKNOWN", self.assess()["blockers"])

    def test_bidirectional_challenge_and_unresolved_gate(self):
        self.depth["cross_challenges"].pop()
        self.assertIn("CROSS_TEAM_ANGLE_COVERAGE", self.assess()["blockers"])
        self.setUp()
        self.depth["cross_challenges"][0].update(status="unresolved", outcome="open")
        self.assertIn("CROSS_CHALLENGE_UNRESOLVED", self.assess()["blockers"])

    def test_each_finding_requires_opposing_challenge(self):
        seg = self.bundle["segments"][0]
        self.results[0]["findings"] = [{"id": "F1", "severity": "low", "confidence": "low", "category": "text",
            "risk": "Synthetic", "impact": "Synthetic", "suggestion": "Synthetic", "questions": [], "basis": [],
            "evidence": [{"segment_id": seg["id"], "start": seg["start"], "end": seg["end"], "quote": seg["text"]}]}]
        self.assertIn("FINDINGS_NOT_CROSS_CHALLENGED", self.assess()["blockers"])
        self.depth["cross_challenges"][1]["finding_ids"] = ["F1"]
        self.assertEqual(self.assess()["status"], "DECLARED_DEPTH_COMPLETE")
        self.depth["cross_challenges"][0]["finding_ids"] = ["F1"]
        with self.assertRaisesRegex(d.DepthError, "FINDING_INVALID"):
            self.assess()
