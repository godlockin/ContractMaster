"""Bounded production-v6 fault acceptance using synthetic local cases only."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import pipeline as p


CANARY = "CANARY-PRIVATE-9917"
PYTHON = Path(os.environ.get("PYTHON", os.sys.executable))


class ProductionFaultAcceptance(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _worker(self, mode: str = "ok") -> Path:
        worker = self.root / f"worker-{mode}.py"
        script = r'''
import json, pathlib, sys, time
a = sys.argv
src = pathlib.Path(a[a.index('--input') + 1])
out = pathlib.Path(a[a.index('--output') + 1])
text = src.read_text(encoding='utf-8')
mode = MODE
if mode == 'timeout':
    print('synthetic failure ' + 'CANARY-PRIVATE-9917', file=sys.stderr)
    time.sleep(2)
if mode == 'ordinary':
    value = 'CANARY-PRIVATE-9917'
elif mode == 'overlap':
    value = 'CANARY-PRIVATE-9917'
elif mode == 'missing-token':
    value = 'CANARY-PRIVATE-9917'
else:
    value = 'CANARY-PRIVATE-9917'
pos = text.find(value)
out.mkdir()
redacted = text.replace(value, '⟦SECRET_0001⟧')
mapping = [{'token': '⟦SECRET_0001⟧', 'type': 'SECRET', 'value': value}]
occ = [{'token': '⟦SECRET_0001⟧', 'original_start': m.start(),
        'original_end': m.end()} for m in __import__('re').finditer(__import__('re').escape(value), text)]
if mode == 'overlap':
    value2 = 'PRIVATE-9917'
    pos2 = text.find(value2)
    mapping.append({'token': '⟦SECRET_0002⟧', 'type': 'SECRET', 'value': value2})
    redacted = redacted.replace('⟦SECRET_0001⟧', '⟦SECRET_0001⟧⟦SECRET_0002⟧', 1)
    occ.append({'token': '⟦SECRET_0002⟧', 'original_start': pos2,
                'original_end': pos2 + len(value2)})
if mode == 'ordinary':
    redacted = redacted.replace('100元', '200元')
if mode == 'missing-token':
    redacted = text
if mode == 'malformed':
    mapping = [{'token': '⟦SECRET_0001⟧', 'type': 'SECRET'}]
(out / 'redacted.txt').write_text(redacted, encoding='utf-8')
(out / 'mapping.json').write_text(json.dumps({'mapping': mapping, 'occurrences': occ}), encoding='utf-8')
print(json.dumps({'status': 'LOCAL_REDACTION_COMPLETE', 'backend': 'rules'}))
'''.replace("MODE", repr(mode))
        worker.write_text(script, encoding="utf-8")
        return worker

    def _case(self, name: str = "case", text: str | None = None,
              docx: bool = False) -> tuple[Path, Path]:
        case = self.root / name
        case.mkdir(mode=0o700)
        source = case / ("input.docx" if docx else "input.txt")
        if docx:
            ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xml = (f'<w:document xmlns:w="{ns}"><w:body><w:p><w:r><w:t>正文{CANARY}</w:t>'
                   f'</w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格{CANARY}</w:t>'
                   f'</w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
            foot = (f'<w:footnotes xmlns:w="{ns}"><w:footnote w:id="1"><w:p><w:r>'
                    f'<w:t>脚注{CANARY}</w:t></w:r></w:p></w:footnote></w:footnotes>')
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("word/document.xml", xml)
                archive.writestr("word/footnotes.xml", foot)
        else:
            source.write_text(text or f"普通金额100元，私密标识{CANARY}。", encoding="utf-8")
        run = case / "run"
        p.prepare(argparse.Namespace(run=run, input=[source], entities=None))
        return case, run

    def _redact(self, case: Path, run: Path, mode: str = "ok", **kwargs: object) -> None:
        args = argparse.Namespace(run=run, redactor=kwargs.get("redactor", self._worker(mode)), python=PYTHON,
                                  backend=kwargs.get("backend", "rules"), timeout=kwargs.get("timeout", 10),
                                  model=kwargs.get("model"), adapter=kwargs.get("adapter"),
                                  policy=kwargs.get("policy"))
        p.redact_run(args)

    @staticmethod
    def _release(run: Path) -> None:
        p.release(argparse.Namespace(run=run, attest_extraction_reviewed=True,
                                     attest_privacy_reviewed=True))

    def test_valid_baseline_and_synthetic_canary_never_leaks(self) -> None:
        case, run = self._case()
        with io.StringIO() as out, io.StringIO() as err, patch("sys.stdout", out), patch("sys.stderr", err):
            self._redact(case, run)
            self._release(run)
            stdout = out.getvalue()
            stderr = err.getvalue()
        public = (run / "public/bundle.json").read_text(encoding="utf-8")
        self.assertNotIn(CANARY, stdout)
        self.assertNotIn(CANARY, stderr)
        self.assertNotIn(CANARY, public)
        self.assertNotIn(CANARY, (run / "public/release.json").read_text())

    def test_each_artifact_byte_change_has_exact_release_gate(self) -> None:
        for kind in ("model", "adapter", "policy"):
            with self.subTest(kind=kind):
                case, run = self._case(kind)
                artifact = case / kind
                if kind == "policy":
                    artifact.write_text(json.dumps({"policy_version": 1, "entities": []}), encoding="utf-8")
                    os.chmod(artifact, 0o600)
                else:
                    artifact.write_bytes(b"synthetic-artifact-v1")
                kwargs = {kind: artifact}
                self._redact(case, run, **kwargs)
                artifact.write_bytes(b"synthetic-artifact-v2")
                with self.assertRaisesRegex(p.GateError, f"{kind.upper()}_CHANGED"):
                    self._release(run)
                self.assertFalse((run / "public").exists())

    def test_failed_redaction_cannot_be_released(self) -> None:
        for mode, redact_expected, release_expected, timeout in (
                ("timeout", "LOCAL_REDACTION_TIMEOUT", "REDACTION_NOT_ATTACHED", .05),
                ("ordinary", "REDACTION_SOURCE_RECONSTRUCTION_MISMATCH", "REDACTION_NOT_ATTACHED", 10)):
            with self.subTest(mode=mode):
                case, run = self._case(mode)
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    with self.assertRaisesRegex(p.GateError, redact_expected) as failure:
                        self._redact(case, run, mode, timeout=timeout)
                self.assertNotIn(CANARY, str(failure.exception) + out.getvalue() + err.getvalue())
                with self.assertRaisesRegex(p.GateError, release_expected):
                    self._release(run)
                self.assertFalse((run / "public").exists())

    def test_second_stage_replace_failure_is_partial_but_not_releaseable_and_new_run_recovers(self) -> None:
        case, run = self._case("replace-failure")
        original = p.os.replace
        count = 0

        def fail_second(src: Path, dst: Path) -> None:
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("synthetic second replace failure")
            original(src, dst)

        with patch.object(p.os, "replace", side_effect=fail_second):
            with self.assertRaises(OSError):
                self._redact(case, run)
        with self.assertRaises(p.GateError):
            self._release(run)
        self.assertFalse((run / "public").exists())

        fresh_case, fresh_run = self._case("replace-recovery")
        self._redact(fresh_case, fresh_run)
        self._release(fresh_run)
        self.assertTrue((fresh_run / "public").exists())

    def test_mapping_faults_are_rejected_individually(self) -> None:
        for mode, expected in (("overlap", "REDACTION_OCCURRENCE_OVERLAP"),
                               ("missing-token", "REDACTION_TOKEN_MISMATCH"),
                               ("malformed", "REDACTION_OCCURRENCE_MISMATCH")):
            with self.subTest(mode=mode):
                case, run = self._case(mode)
                with self.assertRaisesRegex(p.GateError, expected):
                    self._redact(case, run, mode)
                self.assertFalse((run / "public").exists())

    def test_released_run_rejects_second_redact(self) -> None:
        case, run = self._case("released")
        self._redact(case, run)
        self._release(run)
        with self.assertRaisesRegex(p.GateError, "ALREADY_RELEASED"):
            self._redact(case, run)

    def test_docx_multipart_is_actually_redacted(self) -> None:
        case, run = self._case("docx", docx=True)
        self._redact(case, run)
        self._release(run)
        bundle = p.read_json(run / "public/bundle.json")
        self.assertGreaterEqual(len(bundle["documents"]), 2)
        self.assertTrue(all(CANARY not in doc["text"] for doc in bundle["documents"]))
        self.assertGreaterEqual(sum(doc["text"].count("⟦SECRET_0001⟧") for doc in bundle["documents"]), 3)

    def test_skill_only_rules_release_and_force_local_requires_artifacts(self) -> None:
        skill_copy = self.root / "skill-copy"
        shutil.copytree(Path(__file__).parents[2] / "contract-review-cn", skill_copy)
        case = self.root / "skill-only"
        case.mkdir(mode=0o700)
        source = case / "input.txt"
        source.write_text("普通合同金额100元。", encoding="utf-8")
        run = case / "run"
        pipe = skill_copy / "scripts/pipeline.py"
        prep = subprocess.run([str(PYTHON), str(pipe), "prepare", "--run", str(run), "--input", str(source)],
                              capture_output=True, text=True, check=False)
        self.assertEqual(prep.returncode, 0, prep.stderr)
        released = subprocess.run([str(PYTHON), str(pipe), "release", "--run", str(run),
                                    "--attest-extraction-reviewed", "--attest-privacy-reviewed"],
                                   capture_output=True, text=True, check=False)
        self.assertEqual(released.returncode, 0, released.stderr)
        self.assertTrue((run / "public").exists())

        local_case, local_run = self._case("force-local")
        missing_model = local_case / "missing-model"
        missing_adapter = local_case / "missing-adapter"
        with self.assertRaisesRegex(p.GateError, "LOCAL_REDACTION_FAILED"):
            self._redact(local_case, local_run, mode="ok", backend="local",
                         model=missing_model, adapter=missing_adapter,
                         redactor=Path(__file__).with_name("redact_local.py"))


if __name__ == "__main__":
    unittest.main()
