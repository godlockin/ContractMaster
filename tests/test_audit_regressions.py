"""Boundary regressions on synthetic inputs; no external calls."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import random
import re
import tempfile
import unittest

from audit import reproduce_findings as checks
from audit import recheck_boundaries as second


class AuditRegressions(unittest.TestCase):
    def test_report_revisions_preserve_evidence_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            root = Path(folder)
            run, bundle, results = checks.released(root)
            paths = checks.save_results(root, results)
            args = checks.argparse.Namespace(run=run, results=paths, plan=None, depth=None, revision=1)
            checks.p.report(args)
            first = run / "reports/versions/v000001"
            original = (first / "report.md").read_bytes()
            manifest = checks.p.read_json(first / "manifest.json")
            self.assertEqual(manifest["input_digest"], bundle["input_digest"])
            self.assertEqual(manifest["results_digest"], checks.p.digest(checks.p.read_json(first / "results.json")))
            self.assertEqual(manifest["report_sha256"], checks.hashlib.sha256(original).hexdigest())
            self.assertEqual(manifest["legal_signoff"], "NOT_ATTESTED")
            with self.assertRaisesRegex(checks.p.GateError, "REPORT_REVISION_EXISTS"):
                checks.p.report(args)
            results[0]["global_note"] = "Synthetic second review"
            paths[0].write_text(json.dumps(results[0]))
            args.revision = 2
            checks.p.report(args)
            self.assertEqual((first / "report.md").read_bytes(), original)
            self.assertNotEqual(checks.p.read_json(run / "reports/versions/v000002/manifest.json")["results_digest"], manifest["results_digest"])
            args.revision = -1
            with self.assertRaisesRegex(checks.p.GateError, "REPORT_REVISION_INVALID"):
                checks.p.report(args)

    def test_report_revision_audit_failure_can_retry(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            root = Path(folder)
            run, _bundle, results = checks.released(root)
            args = checks.argparse.Namespace(run=run, results=checks.save_results(root, results), plan=None, depth=None, revision=1)
            audit = run / "audit.jsonl"
            audit.rename(run / "saved-audit.jsonl")
            audit.mkdir()
            with self.assertRaises(IsADirectoryError):
                checks.p.report(args)
            self.assertFalse((run / "reports/versions/v000001").exists())
            audit.rmdir()
            checks.p.report(args)
            self.assertTrue((run / "reports/versions/v000001/manifest.json").is_file())

    def test_second_pass_boundaries(self):
        for probe in (second.source_snapshot_race, second.invalid_verified_basis,
                      second.failed_download_loses_pin, second.release_audit_failure):
            with self.subTest(probe=probe.__name__), tempfile.TemporaryDirectory() as folder:
                with contextlib.redirect_stdout(io.StringIO()):
                    probe(Path(folder))

    def test_segmentation_offsets_and_tokens_across_boundaries(self):
        for prefix in (2989, 2990, 2995, 2999, 3000, 3001):
            text = "x" * prefix + "⟦ORG_0001⟧\r\n" + "⟦ORG_0001⟧  " * 1000
            segments = checks.p.segments_for("DOC1", text)
            self.assertEqual("".join(s["text"] for s in segments), text)
            self.assertEqual(sum(len(checks.p.TOKEN.findall(s["text"])) for s in segments), 1001)
            cursor = 0
            for segment in segments:
                self.assertEqual(segment["start"], cursor)
                self.assertEqual(text[segment["start"]:segment["end"]], segment["text"])
                cursor = segment["end"]

    def test_markdown_placeholders_remain_restorable(self):
        token = "⟦ORG_0001⟧"
        value = "![" + token + "](https://example.invalid)\n# fake\n<script>bad</script>"
        escaped = checks.p.markdown_text(value)
        self.assertEqual([m.group() for m in checks.p.TOKEN.finditer(escaped)], [token])
        self.assertNotIn("\n", escaped)
        self.assertNotIn("<script>", escaped)
        self.assertNotIn("https://", escaped)

    def test_report_and_processing_boundaries(self):
        for probe in (checks.malformed_docx, checks.markdown_injection, checks.unvalidated_resolution,
                      checks.omitted_active_plan, checks.wrong_cross_report):
            with self.subTest(probe=probe.__name__), tempfile.TemporaryDirectory() as folder:
                with contextlib.redirect_stdout(io.StringIO()):
                    probe(Path(folder))

    def test_unknown_evidence_stays_pending_without_depth(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            root = Path(folder)
            run, bundle, results = checks.released(root)
            item = checks.finding(bundle)
            item.update(questions=["Confirm?"], question_resolutions=[{
                "question": "Confirm?", "status": "resolved", "reason": "Synthetic reason",
                "evidence_refs": ["NONEXISTENT_SOURCE"]}])
            results[0]["findings"] = [item]
            checks.p.report(checks.argparse.Namespace(run=run, results=checks.save_results(root, results), plan=None, depth=None))
            report = (run / "reports/report.md").read_text()
            self.assertIn("待确认：Confirm?", report)
            self.assertNotIn("声明已解决", report)

    def test_redaction_preserves_longest_first_selection(self):
        rng = random.Random(614)
        for _ in range(150):
            text = "".join(rng.choices("ABCD", k=100))
            entities = [(text[start:start + rng.randint(1, 12)], "ORG")
                        for start in rng.sample(range(90), 30)]
            candidates = [(m.start(), m.end()) for literal, _kind in entities
                          for m in re.finditer(re.escape(literal), text)]
            expected = []
            for start, end in sorted(candidates, key=lambda pair: (-(pair[1] - pair[0]), pair[0])):
                if all(end <= left or right <= start for left, right in expected):
                    expected.append((start, end))
            registry = {}
            redacted, occurrences = checks.p.redact(text, entities, registry, "DOC1")
            self.assertEqual(sorted(expected), [(s["original_start"], s["original_end"]) for s in occurrences])
            lookup = {entry["token"]: entry["value"] for entry in registry.values()}
            self.assertEqual(checks.p.TOKEN.sub(lambda m: lookup[m.group()], redacted), text)

    def test_fresh_clone_rehydrates_every_missing_case_and_normalizes_paths(self):
        spec = importlib.util.spec_from_file_location("corpus_downloader", checks.ROOT / "research/public-contracts/download_corpus.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            root = Path(folder)
            cases = [(f"P{i:02d}",) for i in range(1, 9)]
            records = [{"id": case[0], "download_status": "DOWNLOADED",
                        "original_path": f"/old-machine/{case[0]}.pdf"} for case in cases]
            (root / "manifest.json").write_text(json.dumps({"cases": records}))
            def fake_fetch(case):
                ident = case[0]
                original, sanitized = b"synthetic PDF", b"synthetic text"
                (root / "originals" / f"{ident}.pdf").write_bytes(original)
                for name in ("text", "sanitized"):
                    (root / name / f"{ident}.txt").write_bytes(sanitized)
                (root / "private" / f"{ident}-mapping.json").write_text("{}")
                return {"id": ident, "download_status": "DOWNLOADED",
                        "sha256": checks.hashlib.sha256(original).hexdigest(),
                        "sanitized_sha256": checks.hashlib.sha256(sanitized).hexdigest()}
            module.main(root, cases, fake_fetch)
            saved = json.loads((root / "manifest.json").read_text())["cases"]
            self.assertEqual(len(saved), 8)
            self.assertTrue(all(module.locally_ready(root, record) for record in saved))
            self.assertTrue(all(not Path(record["original_path"]).is_absolute() for record in saved))
            def unexpected_fetch(case):
                raise AssertionError("Ready corpus unnecessarily fetched")
            module.main(root, cases, unexpected_fetch)
            (root / "sanitized/P01.txt").unlink()
            self.assertFalse(module.locally_ready(root, saved[0]))
            module.main(root, cases, fake_fetch)
            self.assertTrue(module.locally_ready(root, saved[0]))


if __name__ == "__main__":
    unittest.main()
