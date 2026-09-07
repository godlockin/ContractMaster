"""Synthetic invariant tests; no confidential contracts or cloud services."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import pipeline as p


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "input.txt"
        self.source.write_bytes("甲方：示例星辰公司\r\n电话：13800138000\r\n价款100元。\n".encode())
        self.entities = self.root / "entities.json"
        self.entities.write_text(json.dumps({"entities": [{"value": "示例星辰公司", "type": "ORG"}]}))
        self.run = self.root / "run"
        p.prepare(argparse.Namespace(run=self.run, input=[self.source], entities=self.entities))
        self.bundle = p.read_json(self.run / "private/candidate.json")

    def release(self, **kwargs):
        p.release(argparse.Namespace(run=self.run, attest_extraction_reviewed=kwargs.get("extraction", True),
                                     attest_privacy_reviewed=kwargs.get("privacy", True)))

    def results(self):
        return [{"role": role, "input_digest": self.bundle["input_digest"],
                 "global_context_reviewed": True, "global_note": "合成样例：核对付款和违约关系。",
                 "reviews": [{"segment_id": s["id"], "levels": list(p.LEVELS),
                              "review_note": "合成样例：检查否定词、主体和金额。"}
                             for s in self.bundle["segments"]], "findings": []} for role in p.ROLES]

    def test_private_gate_and_roundtrip(self):
        self.assertFalse((self.run / "public").exists())
        with self.assertRaisesRegex(p.GateError, "LOCAL_REVIEW_REQUIRED"):
            self.release(privacy=False)
        self.release()
        text = self.bundle["documents"][0]["text"]
        self.assertNotIn("示例星辰公司", text)
        self.assertNotIn("13800138000", text)
        self.assertIn("100元", text)
        self.assertIn("\r\n", text)
        self.assertEqual("".join(s["text"] for s in self.bundle["segments"]), text)
        review = self.run / "reports/test.txt"
        review.write_bytes(text.encode())
        target = self.run / "private/restored.txt"
        p.restore(argparse.Namespace(run=self.run, input=review, output=target))
        self.assertEqual(target.read_bytes(), self.source.read_bytes())
        self.assertEqual((self.run.stat().st_mode & 0o777), 0o700)
        self.assertEqual(((self.run / "private/mapping.json").stat().st_mode & 0o777), 0o600)

    def test_source_and_dictionary_change_block_release(self):
        for path in (self.source, self.entities):
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            with self.assertRaisesRegex(p.GateError, "SOURCE_CHANGED_REPREPARE"):
                self.release()
            path.write_bytes(original)

    def test_candidate_and_map_integrity(self):
        candidate_path = self.run / "private/candidate.json"
        original = candidate_path.read_bytes()
        changed = copy.deepcopy(self.bundle)
        changed["documents"][0]["text"] += "修改"
        candidate_path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(p.GateError, "DIGEST_MISMATCH"):
            self.release()
        candidate_path.write_bytes(original)
        mapping = self.run / "private/mapping.json"
        mapping.write_text('{"entities": [], "occurrences": []}')
        with self.assertRaisesRegex(p.GateError, "MAPPING_CHANGED"):
            self.release()

    def test_missing_roles_segments_levels_and_stale_input(self):
        valid = self.results()
        self.assertEqual(p.validate_results(self.bundle, valid)["roles"], 6)
        mutations = [lambda r: r.pop(), lambda r: r[0]["reviews"].pop(),
                     lambda r: r[0]["reviews"][0]["levels"].pop(),
                     lambda r: r[0].update(input_digest="stale"),
                     lambda r: r[0].update(global_context_reviewed=False)]
        for mutation in mutations:
            results = copy.deepcopy(valid)
            mutation(results)
            with self.assertRaises(p.GateError):
                p.validate_results(self.bundle, results)

    def test_quote_bounds_and_report(self):
        self.release()
        results = self.results()
        seg = self.bundle["segments"][0]
        finding = {"id": "legal-001", "severity": "medium", "category": "text", "confidence": "high",
                   "risk": "合成风险", "impact": "合成影响", "suggestion": "合成建议", "basis": [], "questions": [],
                   "evidence": [{"segment_id": seg["id"], "start": seg["start"],
                                 "end": seg["end"], "quote": seg["text"]}]}
        results[0]["findings"] = [finding]
        self.assertEqual(p.validate_results(self.bundle, results)["findings"], 1)
        finding["evidence"][0]["quote"] = "伪造引用"
        with self.assertRaisesRegex(p.GateError, "QUOTE_MISMATCH"):
            p.validate_results(self.bundle, results)
        finding["evidence"][0]["quote"] = seg["text"]
        paths = []
        for result in results:
            path = self.run / "reports" / f"{result['role']}.json"
            p.write_json(path, result)
            paths.append(path)
        p.report(argparse.Namespace(run=self.run, results=paths))
        report_text = (self.run / "reports/report.md").read_text()
        self.assertIn("legal-001", report_text)
        self.assertIn("PARTIAL_AUDIT", report_text)
        self.assertIn("DEPTH_NOT_VALIDATED", report_text)

    def test_longest_match_and_token_boundary(self):
        registry = {}
        text, spans = p.redact("甲公司甲公司", [("甲", "PERSON"), ("甲公司", "ORG")], registry, "D")
        self.assertEqual(len(registry), 1)
        self.assertEqual(len(spans), 2)
        self.assertEqual(text, "⟦ORG_0001⟧⟦ORG_0001⟧")
        long_text = "字" * 2995 + text + "。"
        segments = p.segments_for("D", long_text)
        self.assertEqual("".join(s["text"] for s in segments), long_text)
        self.assertTrue(segments[0]["text"].endswith("⟦ORG_0001⟧"))

    def test_docx_table_footnote_and_revision_warning(self):
        path = self.root / "sample.docx"
        prefix = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("word/document.xml", prefix + '<w:body><w:p><w:r><w:t>正文</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格</w:t></w:r></w:p></w:tc></w:tr></w:tbl><w:del><w:r><w:delText>删除内容</w:delText></w:r></w:del></w:body></w:document>')
            archive.writestr("word/footnotes.xml", prefix + '<w:p><w:r><w:t>脚注</w:t></w:r></w:p></w:document>')
        parts, warnings = p.extract(path)
        self.assertIn("表格", parts[0][1])
        self.assertIn("删除内容", parts[0][1])
        self.assertIn("脚注", parts[1][1])
        self.assertTrue(any("REVISIONS" in warning for warning in warnings))

    def test_pdf_text_and_empty_page_gate(self):
        try:
            from pypdf import PdfWriter
            from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
        except ImportError:
            self.skipTest("Optional local pypdf unavailable")
        path = self.root / "sample.pdf"
        writer = PdfWriter()
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"):
            DictionaryObject({NameObject("/F1"): font})})
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 10 100 Td (Payment 100) Tj ET")
        page[NameObject("/Contents")] = stream
        with path.open("wb") as target:
            writer.write(target)
        parts, _ = p.extract(path)
        self.assertIn("Payment 100", parts[0][1])
        writer.add_blank_page(width=300, height=300)
        with path.open("wb") as target:
            writer.write(target)
        with self.assertRaisesRegex(p.GateError, "PDF_EMPTY_PAGE"):
            p.extract(path)


if __name__ == "__main__":
    unittest.main()
