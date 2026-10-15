#!/usr/bin/env python3
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from legal_audit import PARTIAL, WORKFLOW_READY, main, template, validate


def ready_record() -> dict:
    value = template()
    value.update({"case_id": "CASE-1", "snapshot_digest": "a" * 64, "playbook_version": "PB-1", "review_status": "complete", "input_digest": "b" * 64})
    value["context"] = {"our_position": "buyer", "jurisdiction": "CN", "audit_stage": "pre-sign", "known_gaps": []}
    value["playbook"] = [{"id": "R-1", "side": "buyer", "preferred": "text A", "fallback": "text B", "red_line": "no", "approval_role": "legal", "exception_allowed": False}]
    value["document_chain"] = [{"id": "D-1", "version": "1", "status": "effective", "effective_date": "2026-01-01", "supersedes": None, "evidence_refs": ["E-1"]}]
    value["findings"] = [{"id": "F-1", "clause": "2.1", "doc_refs": ["D-1"], "category": "commercial", "severity": "low", "risk": "price ambiguity", "impact": "margin uncertainty", "proposed_text": "", "fallback": "", "decision": "accepted", "unresolved": False, "rule_id": "R-1", "exception_approval": "none"}]
    value["obligations"] = [{"id": "O-1", "doc_id": "D-1", "clause": "3.1", "due_date": "2026-02-01", "notice_method": "email", "day_basis": "calendar days", "owner": "buyer", "status": "open"}]
    return value


class LegalAuditTests(unittest.TestCase):
    def test_ready_and_unknown_gap_gate(self) -> None:
        self.assertEqual(validate(ready_record())["status"], WORKFLOW_READY)
        value = ready_record()
        value["context"]["known_gaps"] = ["missing annex"]
        self.assertEqual(validate(value)["status"], PARTIAL)

    def test_duplicate_dangling_cycle_and_date(self) -> None:
        value = ready_record()
        value["document_chain"] = [
            {"id": "D-1", "version": "1", "status": "effective", "effective_date": "2026-01-99", "supersedes": "D-2", "evidence_refs": []},
            {"id": "D-1", "version": "2", "status": "signed", "effective_date": None, "supersedes": "D-1", "evidence_refs": []},
        ]
        value["findings"][0]["doc_refs"] = ["D-404"]
        result = validate(value)
        self.assertEqual(result["status"], PARTIAL)
        joined = " ".join(result["errors"])
        self.assertIn("duplicate id", joined)
        self.assertIn("invalid ISO date", joined)
        self.assertIn("dangling document", joined)
        self.assertIn("cycle", joined)

    def test_draft_cannot_supersede_effective(self) -> None:
        value = ready_record()
        value["document_chain"] = [
            value["document_chain"][0],
            {"id": "D-2", "version": "2", "status": "draft", "effective_date": None, "supersedes": "D-1", "evidence_refs": []},
        ]
        result = validate(value)
        self.assertEqual(result["status"], PARTIAL)
        self.assertTrue(any("not controlling" in item for item in result["warnings"]))

    def test_strict_digest_context_and_strings(self) -> None:
        value = ready_record()
        value["snapshot_digest"] = "short"
        value["context"]["our_position"] = "unknown-role"
        value["findings"][0]["clause"] = 7
        value["findings"][0]["proposed_text"] = None
        result = validate(value)
        self.assertEqual(result["status"], PARTIAL)
        joined = " ".join(result["errors"])
        self.assertIn("64 hexadecimal", joined)
        self.assertIn("invalid enum", joined)
        self.assertIn("expected string", joined)

    def test_approved_exception_requires_bound_evidence(self) -> None:
        value = ready_record()
        value["findings"][0]["exception_approval"] = "approved"
        result = validate(value)
        self.assertEqual(result["status"], PARTIAL)
        self.assertTrue(any("evidence refs" in item for item in result["errors"]))
        value["findings"][0].update({"approval_evidence_refs": ["APP-1"], "approval_scope": "F-1", "approval_version": "PB-1", "approval_snapshot_digest": "a" * 64})
        value["playbook"][0]["exception_allowed"] = True
        self.assertEqual(validate(value)["status"], WORKFLOW_READY)

    def test_empty_playbook_and_effective_competition_are_partial(self) -> None:
        value = ready_record()
        value["playbook"] = []
        value["document_chain"].append({"id": "D-2", "version": "2", "status": "effective", "effective_date": "2026-02-01", "supersedes": None, "evidence_refs": ["E-2"]})
        result = validate(value)
        self.assertEqual(result["status"], PARTIAL)
        self.assertTrue(any("playbook" in item for item in result["warnings"]))

    def test_unresolved_any_severity_and_rejected_exception_gate(self) -> None:
        value = ready_record()
        value["findings"][0].update({"severity": "low", "unresolved": True, "exception_approval": "rejected"})
        self.assertEqual(validate(value)["status"], PARTIAL)

    def test_invalid_status_enums_are_partial(self) -> None:
        value = ready_record()
        value["document_chain"][0]["status"] = "unknown"
        value["findings"][0]["category"] = "other"
        value["obligations"][0]["status"] = "unknown"
        result = validate(value)
        self.assertEqual(result["status"], PARTIAL)
        self.assertGreaterEqual(sum("invalid enum" in item for item in result["errors"]), 3)

    def test_dangling_obligation_and_bad_due_date(self) -> None:
        value = ready_record()
        value["obligations"][0].update({"doc_id": "D-404", "due_date": "2026-02-31"})
        result = validate(value)
        self.assertTrue(any("dangling document" in item for item in result["errors"]))
        self.assertTrue(any("invalid ISO date" in item for item in result["errors"]))

    def test_effective_missing_date_and_evidence_are_partial(self) -> None:
        value = ready_record()
        value["document_chain"][0].update({"effective_date": None, "evidence_refs": []})
        result = validate(value)
        self.assertEqual(result["status"], PARTIAL)
        self.assertTrue(any("effective_date" in item for item in result["warnings"]))
        self.assertTrue(any("evidence_refs" in item for item in result["warnings"]))

    def test_multiple_effective_root_documents_warn(self) -> None:
        value = ready_record()
        value["document_chain"][0]["supersedes"] = "D-0"
        value["document_chain"].extend([
            {"id": "D-0", "version": "0", "status": "signed", "effective_date": None, "supersedes": None, "evidence_refs": ["E-0"]},
            {"id": "D-2", "version": "2", "status": "effective", "effective_date": "2026-02-01", "supersedes": "D-0", "evidence_refs": ["E-2"]},
        ])
        result = validate(value)
        self.assertTrue(any("competing effective" in item for item in result["warnings"]))

    def test_missing_required_root_is_partial(self) -> None:
        result = validate({})
        self.assertEqual(result["status"], PARTIAL)
        self.assertTrue(result["errors"])

    def test_empty_chain_and_input_digest_are_partial(self) -> None:
        value = ready_record()
        value["document_chain"] = []
        value["input_digest"] = ""
        result = validate(value)
        self.assertEqual(result["status"], PARTIAL)
        self.assertTrue(any("input_digest" in item for item in result["errors"]))
        self.assertTrue(any("document_chain is empty" in item for item in result["warnings"]))

    def test_malicious_enum_types_do_not_raise(self) -> None:
        value = ready_record()
        value["review_status"] = {}
        value["context"]["audit_stage"] = []
        value["document_chain"][0]["status"] = {}
        value["findings"][0]["category"] = []
        value["findings"][0]["decision"] = {}
        value["obligations"][0]["status"] = []
        result = validate(value)
        self.assertEqual(result["status"], PARTIAL)
        self.assertGreaterEqual(len(result["errors"]), 5)

    def test_malicious_obligation_doc_id_types_do_not_raise(self) -> None:
        for bad in ([], {}):
            value = ready_record()
            value["obligations"][0]["doc_id"] = bad
            result = validate(value)
            self.assertEqual(result["status"], PARTIAL)
            self.assertTrue(any("obligations[0].doc_id" in item for item in result["errors"]))

    def test_playbook_side_mismatch_is_partial(self) -> None:
        value = ready_record()
        value["playbook"][0]["side"] = "seller"
        self.assertEqual(validate(value)["status"], PARTIAL)

    def test_exception_cannot_bypass_rule_without_allowance(self) -> None:
        value = ready_record()
        value["findings"][0].update({"exception_approval": "approved", "approval_evidence_refs": ["APP-1"], "approval_scope": "F-1", "approval_version": "PB-1", "approval_snapshot_digest": "a" * 64})
        result = validate(value)
        self.assertEqual(result["status"], PARTIAL)
        self.assertTrue(any("not allowed by rule" in item for item in result["warnings"]))

    def test_strict_date_rejects_compact_form(self) -> None:
        value = ready_record()
        value["document_chain"][0]["effective_date"] = "20261015"
        result = validate(value)
        self.assertTrue(any("effective_date" in item and "invalid ISO date" in item for item in result["errors"]))

    def test_symlink_parent_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            real = root_path / "real"
            real.mkdir()
            link = root_path / "link"
            link.symlink_to(real, target_is_directory=True)
            input_path = root_path / "audit.json"
            input_path.write_text(json.dumps(ready_record()), encoding="utf-8")
            self.assertNotEqual(main(["report", "--input", str(input_path), "--output", str(link / "out")]), 0)

    def test_major_and_pending_exception_gate(self) -> None:
        value = ready_record()
        value["findings"][0].update({"severity": "critical", "unresolved": True, "exception_approval": "pending"})
        self.assertEqual(validate(value)["status"], PARTIAL)

    def test_cli_permissions_and_no_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            input_path = root_path / "audit.json"
            input_path.write_text(json.dumps(ready_record()), encoding="utf-8")
            output = root_path / "report"
            self.assertEqual(main(["report", "--input", str(input_path), "--output", str(output)]), 0)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((output / "report.json").stat().st_mode), 0o600)
            self.assertNotEqual(main(["report", "--input", str(input_path), "--output", str(output)]), 0)

    def test_init_file_is_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "audit.json"
            self.assertEqual(main(["init", "--output", str(path)]), 0)
            self.assertNotEqual(main(["init", "--output", str(path)]), 0)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema_version"], "1.0")

    def test_report_markdown_is_text_and_contains_records(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            input_path = root_path / "audit.json"
            input_path.write_text(json.dumps(ready_record()), encoding="utf-8")
            output = root_path / "report"
            self.assertEqual(main(["report", "--input", str(input_path), "--output", str(output)]), 0)
            report = (output / "report.md").read_text(encoding="utf-8")
            self.assertIn("F\\-1", report)
            self.assertIn("O\\-1", report)
            self.assertTrue(report.startswith("# 本地合同审计台账报告"))

    def test_report_escapes_user_markdown_and_html(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            value = ready_record()
            value["findings"][0].update({"risk": "<img src=\"https://evil.example/x\">", "impact": "![x](https://evil.example/y)", "proposed_text": "[外链](https://evil.example/z)"})
            input_path = root_path / "audit.json"
            input_path.write_text(json.dumps(value), encoding="utf-8")
            output = root_path / "report"
            self.assertEqual(main(["report", "--input", str(input_path), "--output", str(output)]), 0)
            report = (output / "report.md").read_text(encoding="utf-8")
            self.assertNotIn("<img", report)
            self.assertNotIn("![", report)
            self.assertNotIn("](https://evil.example", report)
            self.assertIn("evil\\.example", report)
            self.assertIn("送达方式=email", report)
            self.assertIn("日期口径=calendar days", report)

    def test_cli_check_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            input_path = root_path / "duplicate.json"
            input_path.write_text('{"schema_version":"1.0","schema_version":"1.0"}', encoding="utf-8")
            output = root_path / "check"
            self.assertEqual(main(["check", "--input", str(input_path), "--output", str(output)]), 1)
            self.assertFalse(output.exists())

    def test_cli_report_rejects_nonfinite_json_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            input_path = root_path / "nonfinite.json"
            input_path.write_text('{"value":NaN}', encoding="utf-8")
            output = root_path / "report"
            self.assertEqual(main(["report", "--input", str(input_path), "--output", str(output)]), 1)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
