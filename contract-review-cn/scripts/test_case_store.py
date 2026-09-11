"""Synthetic case lifecycle and storage boundary regression tests."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import case_store as c
import pipeline as p


class CaseStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "cases"
        c.initialize(self.root)
        c.create_case(self.root, "C001")

    def put(self, contract, version, text="未来三年300万/年。", parent=None):
        source = self.base / "机密客户名称.txt"
        source.write_text(text, encoding="utf-8")
        c.import_version(self.root, "C001", contract, version, source, parent)
        return source

    def test_immutable_copy_branch_and_private_index(self):
        source = self.put("D001", "V1")
        source.write_text("external edit", encoding="utf-8")
        _, copied = c.version(self.root, "C001", "D001", "V1")
        self.assertEqual(copied.read_text(), "未来三年300万/年。")
        with self.assertRaises(p.GateError):
            self.put("D001", "V2")
        self.put("D001", "V2", parent="V1")
        self.put("D001", "V3", parent="V1")
        with self.assertRaises(p.GateError):
            self.put("D001", "V2", parent="V1")
        result = c.index(self.root)
        versions = result["cases"][0]["contracts"][0]["versions"]
        self.assertEqual([v["parent"] for v in versions], [None, "V1", "V1"])
        self.assertNotIn("机密", json.dumps(result, ensure_ascii=False))
        self.assertEqual(copied.stat().st_mode & 0o777, 0o600)

    def test_stable_identity_pairs_missing_middle_attachment(self):
        self.put("D001", "V1")
        self.put("D002", "V1", "附件中段。")
        self.put("D003", "V1", "附件末段。")
        self.put("D001", "V2", "未来三年300万。", "V1")
        c.make_snapshot(self.root, "C001", "S1", ["D001=V1", "D002=V1", "D003=V1"])
        c.make_snapshot(self.root, "C001", "S2", ["D003=V1", "D001=V2"], parent="S1")
        result = c.prepare_review(self.root, "C001", "S2", "R1", "S1")
        run = Path(result["run"])
        bundle = p.read_json(run / "private" / "candidate.json")
        p.check_bundle(bundle)
        pairs = bundle["comparison"]["pairs"]
        self.assertEqual([(v["before"], v["after"]) for v in pairs], [(1, 4), (2, None), (3, 5)])
        self.assertFalse((run / "public").exists())
        self.assertEqual(c.index(self.root)["cases"][0]["reviews"][0]["baseline_id"], "S1")
        with contextlib.redirect_stdout(io.StringIO()):
            p.release(type("Args", (), {"run": run, "attest_extraction_reviewed": True,
                                       "attest_privacy_reviewed": True})())
        self.assertTrue((run / "public" / "bundle.json").is_file())

    def test_snapshot_tamper_and_original_tamper_rejected(self):
        self.put("D001", "V1")
        c.make_snapshot(self.root, "C001", "S1", ["D001=V1"])
        _, source = c.version(self.root, "C001", "D001", "V1")
        source.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(p.GateError, "ORIGINAL_CHANGED"):
            c.prepare_review(self.root, "C001", "S1", "R1")
        self.assertFalse((c.case_path(self.root, "C001") / "reviews" / "R1").exists())

    def test_invalid_members_and_cross_group_rejected(self):
        self.put("D001", "V1")
        for members in (["D001=V1", "D001=V1"], ["D001=missing"], []):
            with self.assertRaises((p.GateError, OSError)):
                c.make_snapshot(self.root, "C001", "bad", members)
        c.make_snapshot(self.root, "C001", "S1", ["D001=V1"], group="G1")
        c.make_snapshot(self.root, "C001", "S2", ["D001=V1"], group="G2")
        with self.assertRaisesRegex(p.GateError, "GROUP_MISMATCH"):
            c.prepare_review(self.root, "C001", "S2", "R1", "S1")
        with self.assertRaises(FileExistsError):
            c.make_snapshot(self.root, "C001", "S1", ["D001=V1"])

    def test_symlink_traversal_and_busy_lock(self):
        with self.assertRaises(p.GateError):
            c.create_case(self.root, "../escape")
        folder = c.case_path(self.root, "C001") / "contracts"
        folder.rmdir()
        folder.symlink_to(self.base, target_is_directory=True)
        with self.assertRaisesRegex(p.GateError, "SYMLINK"):
            self.put("D001", "V1")
        (self.root / ".write-lock").mkdir()
        with self.assertRaisesRegex(p.GateError, "STORE_BUSY"):
            c.create_case(self.root, "C002")
        (self.root / ".write-lock").rmdir()

    def test_failed_prepare_cleans_up_and_retry_works(self):
        self.put("D001", "V1")
        c.make_snapshot(self.root, "C001", "S1", ["D001=V1"])
        with self.assertRaises(OSError):
            c.prepare_review(self.root, "C001", "S1", "R1", entities=self.base / "missing.json")
        folder = c.case_path(self.root, "C001") / "reviews"
        self.assertEqual(list(folder.iterdir()), [])
        result = c.prepare_review(self.root, "C001", "S1", "R1")
        self.assertTrue(Path(result["run"]).is_dir())
        with self.assertRaises(p.GateError):
            c.prepare_review(self.root, "C001", "S1", "R1")

    def test_cli_default_root_and_errors_do_not_log_private_paths(self):
        command = [sys.executable, str(Path(c.__file__).resolve())]
        result = subprocess.run([*command, "init"], cwd=self.base, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((self.base / "contract-cases" / "store.json").is_file())
        result = subprocess.run([*command, "--root", str(self.root), "import", "--case", "C001",
                                 "--contract", "D001", "--version", "V1", "--input",
                                 str(self.base / "机密文件.txt")], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("机密", result.stdout + result.stderr)

    def test_binding_and_snapshot_are_checked_on_index(self):
        self.put("D001", "V1")
        c.make_snapshot(self.root, "C001", "S1", ["D001=V1"])
        result = c.prepare_review(self.root, "C001", "S1", "R1")
        path = Path(result["run"]).parent / "binding.json"
        data = p.read_json(path)
        data["input_digest"] = "stale"
        data["digest"] = p.digest({k: v for k, v in data.items() if k != "digest"})
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(p.GateError, "REVIEW_INPUT_CHANGED"):
            c.index(self.root)

    def test_report_index_verifies_input_and_content(self):
        self.put("D001", "V1")
        c.make_snapshot(self.root, "C001", "S1", ["D001=V1"])
        result = c.prepare_review(self.root, "C001", "S1", "R1")
        run = Path(result["run"])
        binding = c.read(run.parent / "binding.json")
        folder = run / "reports" / "versions" / "v000001"
        folder.mkdir(parents=True)
        report = folder / "report.md"
        report.write_text("Synthetic integrity fixture only.", encoding="utf-8")
        p.write_json(folder / "results.json", [])
        manifest = {"revision": 1, "input_digest": binding["input_digest"],
                    "results_digest": p.digest([]), "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                    "declared_depth_status": "PARTIAL_AUDIT", "legal_signoff": "NOT_ATTESTED"}
        p.write_json(folder / "manifest.json", manifest)
        entry = c.index(self.root)["cases"][0]["reviews"][0]
        self.assertEqual(entry["reports"][0]["revision"], 1)
        self.assertFalse(entry["published_bundle_present"])
        report.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(p.GateError, "REPORT_CONTENT_CHANGED"):
            c.index(self.root)


if __name__ == "__main__":
    unittest.main()
