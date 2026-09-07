import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import pipeline as p
import validate_depth as d
from test_depth import fixture


class InputFormatsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_missing_pdf_library_does_not_stop_txt_docx(self):
        txt = self.root / "contract.txt"
        txt.write_text("甲方向乙方交付货物。", encoding="utf-8")
        word = self.root / "attachment.docx"
        with zipfile.ZipFile(word, "w") as z:
            z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>附件约定质量标准。</w:t></w:r></w:p></w:body></w:document>')
        pdf = self.root / "sensitive-name.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        run = self.root / "run"
        result = subprocess.run([sys.executable, "-S", str(Path(p.__file__)), "prepare", "--run", str(run), "--input", str(pdf), "--input", str(txt), "--input", str(word)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("sensitive-name", result.stdout + result.stderr)
        bundle = p.read_json(run / "private/candidate.json")
        self.assertEqual(len(bundle["documents"]), 2)
        self.assertEqual(bundle["input_gaps"], [{"source_index": 1, "code": "PDF_REQUIRES_LOCAL_PYPDF"}])
        self.assertFalse((run / "public").exists())

    def test_all_unsupported_creates_no_candidate(self):
        path = self.root / "legacy.doc"
        path.write_bytes(b"old-format")
        run = self.root / "run"
        result = subprocess.run([sys.executable, str(Path(p.__file__)), "prepare", "--run", str(run), "--input", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse((run / "private/candidate.json").exists())
        self.assertTrue((run / "private/input-errors.json").exists())

    def test_preflight_is_read_only_with_optional_pdf(self):
        pdf = self.root / "input.pdf"
        pdf.touch()
        before = set(self.root.iterdir())
        data = p.input_capabilities([pdf, self.root / "missing.docx"], pdf_available=False)
        self.assertEqual(data["ready_count"], 0)
        self.assertEqual(data["files"][0]["status"], "PDF_REQUIRES_LOCAL_PYPDF")
        self.assertEqual(data["files"][1]["status"], "INPUT_NOT_FOUND")
        self.assertEqual(set(self.root.iterdir()), before)

    def test_input_gap_blocks_depth_completion(self):
        bundle, depth = fixture()
        bundle["input_gaps"] = [{"source_index": 2, "code": "PDF_REQUIRES_LOCAL_PYPDF"}]
        bundle["input_digest"] = p.digest({k:v for k,v in bundle.items() if k != "input_digest"})
        depth["input_digest"] = bundle["input_digest"]
        result = d.assess(bundle, depth)
        self.assertEqual(result["status"], "PARTIAL_AUDIT")
        self.assertIn("INPUTS_NOT_PROCESSED", result["blockers"])


if __name__ == "__main__":
    unittest.main()
