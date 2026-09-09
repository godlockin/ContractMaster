"""Synthetic regression probes. PASS means the documented defect is blocked.

No network calls, private contracts, or changes to production code.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "contract-review-cn/scripts"))
sys.path.insert(0, str(ROOT / "research/public-contracts/tools"))
import pipeline as p
import expert_plan as e
from test_depth import plan_fixture
from build_human_review import build


def released(root: Path, text: str = "交付后付款。\n"):
    source = root / "input.txt"
    source.write_text(text, encoding="utf-8")
    run = root / "run"
    p.prepare(argparse.Namespace(run=run, input=[source], entities=None))
    p.release(argparse.Namespace(run=run, attest_extraction_reviewed=True, attest_privacy_reviewed=True))
    bundle = p.read_json(run / "public/bundle.json")
    results = [{"role": role, "input_digest": bundle["input_digest"],
                "global_context_reviewed": True, "global_note": "Synthetic review",
                "reviews": [{"segment_id": s["id"], "levels": p.LEVELS,
                             "review_note": "Synthetic review"} for s in bundle["segments"]],
                "findings": []} for role in p.ROLES]
    return run, bundle, results


def save_results(root: Path, results: list[dict]) -> list[Path]:
    paths = []
    for i, result in enumerate(results):
        path = root / f"result-{i}.json"
        p.write_json(path, result)
        paths.append(path)
    return paths


def finding(bundle: dict) -> dict:
    seg = bundle["segments"][0]
    return {"id": "F1", "severity": "medium", "confidence": "high", "category": "business",
            "risk": "Synthetic risk", "impact": "Synthetic impact", "suggestion": "Synthetic suggestion",
            "evidence": [{"segment_id": seg["id"], "start": seg["start"], "end": seg["end"], "quote": seg["text"]}],
            "basis": [], "questions": []}


def malformed_docx(root: Path) -> dict:
    bad = root / "bad.docx"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("word/document.xml", "<broken>")
    good = root / "good.txt"
    good.write_text("有效合成合同。", encoding="utf-8")
    p.prepare(argparse.Namespace(run=root / "run", input=[bad, good], entities=None))
    bundle = p.read_json(root / "run/private/candidate.json")
    assert bundle["input_gaps"] == [{"source_index": 1, "code": "DOCX_XML_PARSE_FAILED"}]
    assert bundle["documents"][0]["text"] == "有效合成合同。"
    return {"valid_txt_processed": True}


def markdown_injection(root: Path) -> dict:
    payload = "![synthetic](https://example.invalid/audit-pixel)"
    run, bundle, results = released(root, payload + "\n")
    results[0]["findings"] = [finding(bundle)]
    p.report(argparse.Namespace(run=run, results=save_results(root, results), plan=None, depth=None))
    report = (run / "reports/report.md").read_text()
    assert payload not in report and r"\!\[synthetic\]" in report
    return {"active_markdown_preserved": False, "network_requested": False}


def unvalidated_resolution(root: Path) -> dict:
    run, bundle, results = released(root)
    item = finding(bundle)
    item["questions"] = ["授权是否已确认？"]
    item["question_resolutions"] = [{"question": item["questions"][0], "status": "resolved"}]
    results[0]["findings"] = [item]
    try:
        p.report(argparse.Namespace(run=run, results=save_results(root, results), plan=None, depth=None))
    except p.GateError as exc:
        assert str(exc) == "QUESTION_RESOLUTION_INVALID"
        return {"invalid_resolution_rejected": True}
    raise AssertionError("Invalid resolution accepted")


def omitted_active_plan(root: Path) -> dict:
    run, bundle, results = released(root)
    plan = plan_fixture(bundle, ["security"])
    e.activate(run, bundle, plan)
    try:
        p.load_results(argparse.Namespace(run=run, results=save_results(root, results), plan=None))
    except p.GateError as exc:
        assert str(exc) == "ACTIVE_PLAN_REQUIRED"
        return {"omitted_active_plan_rejected": True}
    raise AssertionError("Active plan omitted")


def wrong_cross_report(root: Path) -> dict:
    (root / "reviews").mkdir()
    (root / "cross-review").mkdir()
    text = "验收后付款。"
    for name in ("original.txt", "sanitized.txt"):
        (root / name).write_text(text, encoding="utf-8")
    p.write_json(root / "manifest.json", {"cases": [{"id": "T1", "original_path": "original.txt", "sanitized_path": "sanitized.txt"}]})
    sha = hashlib.sha256(text.encode()).hexdigest()
    review = {"case_id": "T1", "input_sha256": sha,
              "findings": [{"id": "A1", "evidence": [{"quote": text}]}]}
    p.write_json(root / "reviews/a.json", {"reviews": [review]})
    second = copy.deepcopy(review)
    second["findings"][0]["id"] = "B1"
    p.write_json(root / "reviews/b.json", {"reviews": [second]})
    p.write_json(root / "cross-review/c.json", {"case_id": "T1", "input_sha256": sha,
        "reviewed_report_sha256": hashlib.sha256((root / "reviews/a.json").read_bytes()).hexdigest(),
        "judgments": [{"finding_id": "B1", "decision": "support", "reason": "Synthetic", "counterevidence": []}]})
    try:
        build(root)
    except ValueError as exc:
        assert str(exc) == "Cross-review finding not in referenced report"
        return {"wrong_report_binding_rejected": True}
    raise AssertionError("Wrong report binding accepted")


def profile_redaction() -> dict:
    samples = []
    for count in (2000, 4000, 8000):
        text = "13800138000\n" * count
        start = time.perf_counter()
        _, occurrences = p.redact(text, [], {}, "DOC0001")
        elapsed = time.perf_counter() - start
        assert len(occurrences) == count
        samples.append({"matches": count, "seconds": round(elapsed, 4)})
    return {"samples": samples, "fourfold_input_time_ratio": round(samples[-1]["seconds"] / samples[0]["seconds"], 2)}


def main() -> None:
    output = []
    for probe in (malformed_docx, markdown_injection, unvalidated_resolution, omitted_active_plan, wrong_cross_report):
        with tempfile.TemporaryDirectory(prefix="contract-audit-") as directory, contextlib.redirect_stdout(io.StringIO()):
            evidence = probe(Path(directory))
        output.append({"probe": probe.__name__, "fixed": True, **evidence})
    output.append({"probe": "redaction_performance", **profile_redaction()})
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
