"""Deterministic acceptance checks, not LLM risk detection scoring."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "scripts"))
import pipeline as p


def check(condition, code):
    if not condition:
        raise RuntimeError(code)


def main():
    manifest = p.read_json(ROOT / "oracle/manifest.json")
    output = ROOT / "results"
    bundles = output / "bundles"
    bundles.mkdir(parents=True, exist_ok=True)
    cases = []
    for case in manifest["cases"]:
        source = ROOT / "inputs" / f"{case['id']}.txt"
        original = source.read_bytes().decode("utf-8")
        check(hashlib.sha256(source.read_bytes()).hexdigest() == case["sha256"], "FIXTURE_CHANGED")
        for expected in case["expected"]:
            check(expected["anchor"] in original, "EXPECTED_ANCHOR_MISSING")
        with tempfile.TemporaryDirectory(prefix="contract-acceptance-") as temp:
            run = Path(temp) / "run"
            with contextlib.redirect_stdout(io.StringIO()):
                p.prepare(argparse.Namespace(run=run, input=[source], entities=ROOT / "inputs/entities.json"))
                try:
                    p.release(argparse.Namespace(run=run, attest_extraction_reviewed=False,
                                                 attest_privacy_reviewed=False))
                except p.GateError as exc:
                    check(str(exc) == "LOCAL_REVIEW_REQUIRED", "WRONG_GATE")
                else:
                    raise RuntimeError("UNREVIEWED_RELEASE_ALLOWED")
                # Explicit test-only attestation: all inputs are authored synthetic fixtures.
                p.release(argparse.Namespace(run=run, attest_extraction_reviewed=True,
                                             attest_privacy_reviewed=True))
            bundle = p.read_json(run / "public/bundle.json")
            mapping = p.read_json(run / "private/mapping.json")
            text = bundle["documents"][0]["text"]
            check("".join(s["text"] for s in bundle["segments"]) == text, "CHARACTER_LOSS")
            check(not p.contains_private_value(bundle, [entity["value"] for entity in mapping["entities"]]), "PRIVACY_LEAK")
            lookup = {item["token"]: item["value"] for item in mapping["entities"]}
            check(p.TOKEN.sub(lambda m: lookup[m.group()], text) == original, "ROUNDTRIP_LOSS")
            for span in mapping["occurrences"]:
                check(text[span["redacted_start"]:span["redacted_end"]] == span["token"], "BAD_REDACTED_SPAN")
                check(original[span["original_start"]:span["original_end"]] == lookup[span["token"]], "BAD_ORIGINAL_SPAN")
            # Synthetic acknowledgments test schema only; these are NEVER counted as model reviews.
            results = [{"role": role, "input_digest": bundle["input_digest"],
                        "global_context_reviewed": True, "global_note": "schema-only fixture",
                        "reviews": [{"segment_id": s["id"], "levels": p.LEVELS,
                                     "review_note": "schema-only fixture"} for s in bundle["segments"]],
                        "findings": []} for role in p.ROLES]
            summary = p.validate_results(bundle, results)
            results[0]["reviews"].pop()
            try:
                p.validate_results(bundle, results)
            except p.GateError:
                pass
            else:
                raise RuntimeError("MISSING_SEGMENT_ACCEPTED")
            (bundles / f"{case['id']}.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n")
            cases.append({"case_id": case["id"], "input_digest": bundle["input_digest"],
                          "status": "PASS", "segments": summary["segments"],
                          "redactions": len(mapping["occurrences"]),
                          "assertions": ["source_hash", "expected_anchors", "release_gate", "full_text",
                                         "known_privacy", "roundtrip", "mapping_offsets", "schema", "missing_segment_gate"]})
    report = {"scope": "deterministic pipeline only; no legal-quality score", "cases": cases,
              "status": "PASS", "model_quality": "NOT_MEASURED_BY_THIS_RUNNER"}
    (output / "pipeline-acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "cases": len(cases), "scope": report["scope"]}))


if __name__ == "__main__":
    main()
