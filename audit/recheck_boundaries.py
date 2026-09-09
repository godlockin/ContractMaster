"""Second-pass regression probes; success confirms the audited boundaries hold."""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "contract-review-cn/scripts"))
import pipeline as p
import validate_depth as d
from test_depth import fixture, plan_fixture


def source_snapshot_race(root):
    source = root / "input.txt"
    source.write_text("合成旧版本：付款100元。", encoding="utf-8")
    extract = p.extract
    def changing_extract(path, data=None):
        parts = extract(path, data)
        # Deterministic simulation of an editor saving after extraction, before hashing.
        path.write_text("合成新版本：付款200元。", encoding="utf-8")
        return parts
    p.extract = changing_extract
    try:
        p.prepare(argparse.Namespace(run=root / "run", input=[source], entities=None))
    finally:
        p.extract = extract
    try:
        p.release(argparse.Namespace(run=root / "run", attest_extraction_reviewed=True, attest_privacy_reviewed=True))
    except p.GateError as exc:
        assert str(exc) == "SOURCE_CHANGED_REPREPARE"
    else:
        raise AssertionError("Mixed source versions accepted")
    bundle = p.read_json(root / "run/private/candidate.json")
    assert "100元" in bundle["documents"][0]["text"] and "200元" in source.read_text()
    assert not (root / "run/public").exists()
    return {"mixed_source_versions_rejected": True}


def invalid_verified_basis(_root):
    bundle, depth = fixture()
    plan = plan_fixture(bundle)
    depth["plan_digest"] = p.digest(plan)
    results = [{"role": role, "input_digest": bundle["input_digest"], "plan_digest": p.digest(plan),
                "global_context_reviewed": True, "global_note": "Synthetic",
                "reviews": [{"segment_id": s["id"], "levels": p.LEVELS, "review_note": "Synthetic"}
                            for s in bundle["segments"]], "findings": []} for role in p.ROLES]
    seg = bundle["segments"][0]
    results[0]["findings"] = [{"id": "F1", "severity": "medium", "confidence": "high", "risk": "Synthetic",
        "impact": "Synthetic", "suggestion": "Synthetic", "category": "legal", "questions": [],
        "evidence": [{"segment_id": seg["id"], "start": seg["start"], "end": seg["end"], "quote": seg["text"]}],
        "basis": [{"status": "verified", "title": "Synthetic unrelated source", "article": "X",
                   "url": "https://", "checked_at": "not-a-date", "applicability": "Synthetic"}]}]
    basis = results[0]["findings"][0]["basis"][0]
    for url, date, error in (("https://", "2026-09-07", "BASIS_URL_INVALID"),
                             ("https://example.invalid/source", "not-a-date", "BASIS_DATE_INVALID")):
        basis.update(url=url, checked_at=date)
        try:
            p.validate_results(bundle, results, plan)
        except p.GateError as exc:
            assert str(exc) == error
        else:
            raise AssertionError("Malformed verified basis accepted")
    basis.update(checked_at="2026-09-07")
    p.validate_results(bundle, results, plan)
    assert "FINDING_BASIS_SOURCE_NOT_LINKED" in d.assess(bundle, depth, plan, results)["blockers"]
    basis["source_id"] = "S1"
    assert "FINDING_BASIS_SOURCE_MISMATCH" in d.assess(bundle, depth, plan, results)["blockers"]
    basis.update(title=depth["sources"][0]["title"], article="fixture-1")
    assert d.assess(bundle, depth, plan, results)["status"] == "PARTIAL_AUDIT"
    return {"malformed_basis_rejected": True, "source_binding_checked": True}


def failed_download_loses_pin(root):
    spec = importlib.util.spec_from_file_location("recheck_downloader", ROOT / "research/public-contracts/download_corpus.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    p.write_json(root / "manifest.json", {"cases": [{"id": "P01", "download_status": "DOWNLOADED", "sha256": "PINNED"}]})
    expected_hashes = []
    def unavailable_fetch(case, root, expected_sha256):
        expected_hashes.append(expected_sha256)
        # Same failure shape as fetch's exception handler; no requests made.
        return {"id": case[0], "download_status": "FAILED", "error": "Synthetic offline failure"}
    module.fetch = unavailable_fetch
    exit_codes = [module.main(root, [("P01",)]) for _ in range(2)]
    assert expected_hashes == ["PINNED", "PINNED"]
    assert exit_codes == [2, 2]
    return {"hash_pin_on_first_attempt": expected_hashes[0], "hash_pin_on_retry": expected_hashes[1],
            "failure_exit_codes": exit_codes}


def release_audit_failure(root):
    source = root / "input.txt"
    source.write_text("合成合同。", encoding="utf-8")
    run = root / "run"
    p.prepare(argparse.Namespace(run=run, input=[source], entities=None))
    audit = run / "audit.jsonl"
    audit.rename(run / "old-audit.jsonl")
    audit.mkdir()  # Deterministic filesystem failure when event tries appending.
    args = argparse.Namespace(run=run, attest_extraction_reviewed=True, attest_privacy_reviewed=True)
    try:
        p.release(args)
    except IsADirectoryError:
        pass
    else:
        raise AssertionError("Expected audit write failure")
    assert not (run / "public").exists()
    audit.rmdir()
    p.release(args)
    assert (run / "public/bundle.json").is_file()
    receipt = p.read_json(run / "public/release.json")
    assert receipt["status"] == "RELEASED"
    assert receipt["input_digest"] == p.read_json(run / "public/bundle.json")["input_digest"]
    return {"published_despite_failure": False, "retry": "RELEASED"}


def profile_segments():
    samples = []
    for count in (10000, 20000, 40000):
        # 12-character units align with 3000-character cuts: no crossing token
        # causes the inner scanner to stop early.
        text = "⟦ORG_0001⟧  " * count
        start = time.perf_counter()
        segments = p.segments_for("DOC1", text)
        elapsed = time.perf_counter() - start
        assert "".join(s["text"] for s in segments) == text
        samples.append({"tokens": count, "seconds": round(elapsed, 4)})
    return samples


def main():
    findings = []
    for probe in (source_snapshot_race, invalid_verified_basis, failed_download_loses_pin, release_audit_failure):
        with tempfile.TemporaryDirectory(prefix="contract-recheck-") as folder, contextlib.redirect_stdout(io.StringIO()):
            result = probe(Path(folder))
        findings.append({"probe": probe.__name__, **result})
    findings.append({"probe": "segmentation_performance", "samples": profile_segments()})
    print(json.dumps(findings, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
