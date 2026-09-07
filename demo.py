"""Offline demonstration on one fixed, authored synthetic contract; no model calls."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "contract-review-cn/scripts"))
import pipeline as pipeline


def run_demo(output: Path, project_root: Path = ROOT) -> dict:
    evaluation = project_root / "contract-review-cn/evals"
    source = evaluation / "inputs/C01.txt"
    manifest = pipeline.read_json(evaluation / "oracle/manifest.json")
    case = next(c for c in manifest["cases"] if c["id"] == "C01")
    pipeline.require(hashlib.sha256(source.read_bytes()).hexdigest() == case["sha256"], "DEMO_FIXTURE_CHANGED")
    # This attestation applies only to the fixed, authored synthetic input above.
    # No arbitrary --input option: real contracts must use the skill's privacy gate.
    with contextlib.redirect_stdout(io.StringIO()):
        pipeline.prepare(argparse.Namespace(run=output, input=[source], entities=evaluation / "inputs/entities.json"))
        pipeline.release(argparse.Namespace(run=output, attest_extraction_reviewed=True, attest_privacy_reviewed=True))
    bundle = pipeline.read_json(output / "public/bundle.json")
    mapping = pipeline.read_json(output / "private/mapping.json")
    archived_path = evaluation / "results/blind-review.json"
    judgments = pipeline.read_json(evaluation / "oracle/pilot-judgments.json")
    pipeline.require(hashlib.sha256(archived_path.read_bytes()).hexdigest() == judgments["review_sha256"], "DEMO_ARCHIVED_REVIEW_CHANGED")
    archived = pipeline.read_json(archived_path)
    review = next(c for c in archived["cases"] if c["case_id"] == "C01")
    pipeline.require(review["input_digest"] == bundle["input_digest"], "DEMO_ARCHIVED_REVIEW_STALE")
    segments = {s["id"]: s["text"] for s in bundle["segments"]}
    quote_count = 0
    for finding in review["findings"]:
        for evidence in finding["evidence"]:
            pipeline.require(evidence["quote"] in segments[evidence["segment_id"]], "DEMO_QUOTE_MISMATCH")
            quote_count += 1
    text = "".join(d["text"] for d in bundle["documents"])
    pipeline.require("".join(s["text"] for s in bundle["segments"]) == text, "DEMO_CHARACTER_GAP")
    pipeline.require(not pipeline.contains_private_value(bundle, [e["value"] for e in mapping["entities"]]), "DEMO_PRIVACY_LEAK")
    summary = {"case_id": "C01", "mode": "offline_processing_and_historical_review_replay",
               "model_calls": 0, "input_sha256": case["sha256"], "input_digest": bundle["input_digest"],
               "segments": len(segments), "redacted_characters": len(text),
               "masked_occurrences": len(mapping["occurrences"]), "archived_findings": len(review["findings"]),
               "verified_quotes": quote_count, "new_legal_review": False, "six_expert_four_round_acceptance": "NOT_RUN"}
    pipeline.write_json(output / "summary.json", summary)
    pipeline.write_new(output / "redacted.txt", text)
    lines = ["# 采购合同演示结果", "", "本次执行了本地提取、脱敏、发布及证据校验；下面回放已保存的单agent试审，不是新运行的AI法律审核。", "",
             "输入为项目原创虚构合同；演示自动确认不能用于真实客户合同。", "",
             f"片段 {len(segments)}；脱敏出现 {len(mapping['occurrences'])} 次；历史意见 {len(review['findings'])} 项；核对引文 {quote_count} 段。", "",
             "[处理后文本](redacted.txt) · [结构化处理结果](summary.json)"]
    for finding in review["findings"]:
        lines.extend(["", "## " + finding["id"], "", finding["risk"], "", "证据："])
        lines.extend("- " + e["segment_id"] + "：" + e["quote"] for e in finding["evidence"])
        lines.extend(["", "建议：" + finding["suggestion"]])
    lines.extend(["", "## 局限", ""] + ["- " + note for note in review["limitations"]])
    pipeline.write_new(output / "REPORT.md", "\n".join(lines) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="New output directory; existing directories are never overwritten")
    args = parser.parse_args()
    out = args.out or ROOT / "review-runs" / datetime.now(timezone.utc).strftime("demo-%Y%m%d-%H%M%S-%f")
    try:
        summary = run_demo(out.resolve())
        print(json.dumps({"status": "PASS", "report": str(out.resolve() / "REPORT.md"), **summary}, ensure_ascii=False))
        return 0
    except pipeline.GateError as exc:
        print(json.dumps({"status": "FAILED", "code": str(exc)}))
        return 2
    except (OSError, ValueError, KeyError, StopIteration):
        print('{"status":"FAILED","code":"DEMO_IO_OR_DATA_ERROR"}')
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
