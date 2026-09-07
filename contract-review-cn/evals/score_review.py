"""Validate explicit evaluator judgments and score detection separately from legal QA."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    manifest = json.loads((ROOT / "oracle/manifest.json").read_text())
    review_path = ROOT / "results/blind-review.json"
    review = json.loads(review_path.read_text())
    judgments = json.loads((ROOT / "oracle/pilot-judgments.json").read_text())
    if hashlib.sha256(review_path.read_bytes()).hexdigest() != judgments["review_sha256"]:
        raise ValueError("REVIEW_CHANGED_REJUDGE")
    cases = {c["case_id"]: c for c in review["cases"]}
    if len(cases) != len(manifest["cases"]) or len(cases) != len(review["cases"]):
        raise ValueError("CASE_COVERAGE_INVALID")
    all_expected = {e["id"] for c in manifest["cases"] for e in c["expected"]}
    if set(judgments["matches"]) != all_expected:
        raise ValueError("JUDGMENT_COVERAGE_INVALID")
    quotes, matched = 0, 0
    for case in manifest["cases"]:
        result = cases[case["id"]]
        bundle = json.loads((ROOT / "results/bundles" / f"{case['id']}.json").read_text())
        if result["input_digest"] != bundle["input_digest"]:
            raise ValueError("STALE_REVIEW")
        segments = {s["id"]: s["text"] for s in bundle["segments"]}
        findings = {f["id"]: f for f in result["findings"]}
        if len(findings) != len(result["findings"]):
            raise ValueError("DUPLICATE_FINDING")
        for finding in findings.values():
            if not finding["evidence"] or not finding["risk"] or not finding["suggestion"]:
                raise ValueError("FINDING_INCOMPLETE")
            for evidence in finding["evidence"]:
                if not evidence["quote"] or evidence["quote"] not in segments[evidence["segment_id"]]:
                    raise ValueError("QUOTE_MISMATCH")
                quotes += 1
        for expected in case["expected"]:
            judgment = judgments["matches"][expected["id"]]
            if not judgment["reason"]:
                raise ValueError("REASON_REQUIRED")
            if judgment["finding_id"] is not None:
                if judgment["finding_id"] not in findings:
                    raise ValueError("JUDGMENT_FINDING_MISSING")
                matched += 1
        forbidden = judgments["forbidden_checks"][case["id"]]
        if len(forbidden) != len(case["forbidden"]) or any(v not in {"pass", "fail", "unassessed"} for v in forbidden):
            raise ValueError("FORBIDDEN_JUDGMENT_INVALID")
    statuses = [v for values in judgments["forbidden_checks"].values() for v in values]
    output = {"scope": "single-agent development-set pilot; AI-adjudicated provisional labels",
              "date": "2026-09-07", "model": "unknown", "submissions": 1,
              "review_sha256": judgments["review_sha256"], "expected_count": len(all_expected),
              "matched_count": matched, "detection_recall": matched / len(all_expected),
              "verified_quotes": quotes, "forbidden_pass": statuses.count("pass"),
              "forbidden_fail": statuses.count("fail"), "forbidden_unassessed": statuses.count("unassessed"),
              "precision": None, "precision_note": "No independently lawyer-adjudicated finding labels",
              "legal_citation_verification": "NOT_COMPLETED", "six_expert_e2e": "NOT_RUN",
              "severity_calibration": "NOT_SCORED", "production_acceptance": "NOT_PASSED"}
    (ROOT / "results/evaluation.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    lines = ["# 合同审核样例报告", "", "单-agent盲审试验；AI初评，非律师法律意见。法源尚未核验。", "",
             f"六案例；预期风险命中 {matched}/{len(all_expected)}；证据引文 {quotes} 条经原片段匹配。",
             "此结果不代表真实合同准确率或六专家工作流验收通过。"]
    for case in manifest["cases"]:
        result = cases[case["id"]]
        lines.extend(["", f"## {case['id']} {case['name']}", ""])
        if not result["findings"]:
            lines.append("本例范围内未发现具体风险，不推定完整合同无风险。")
        for finding in result["findings"]:
            lines.extend(["", f"### {finding['id']}", "", finding["risk"], "", "证据："])
            lines.extend(f"- {e['segment_id']}：{e['quote']}" for e in finding["evidence"])
            lines.extend(["", "建议：" + finding["suggestion"]])
        lines.extend(["", "局限："] + ["- " + value for value in result["limitations"]])
    (ROOT / "results/blind-review.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
