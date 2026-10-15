"""Structural integrity checks only; never presented as legal or model accuracy review."""

import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parent / "datasets" / "legal-workflow-v1"
CASES = ROOT / "cases.jsonl"
MANIFEST = ROOT / "manifest.json"


class LegalWorkflowDatasetTest(unittest.TestCase):
    def test_schema_ids_hash_and_coverage(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        lines = CASES.read_bytes().splitlines()
        rows = [json.loads(line) for line in lines]
        self.assertEqual(manifest["rows"], len(rows))
        self.assertEqual(
            manifest["cases_sha256"], hashlib.sha256(CASES.read_bytes()).hexdigest()
        )
        ids = [row["id"] for row in rows]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(re.fullmatch(r"LWF1-\d{3}", case_id) for case_id in ids))
        required = {"id", "source", "request", "expected_actions", "forbidden_actions"}
        self.assertTrue(all(required <= row.keys() for row in rows))
        self.assertEqual(sum(bool(row.get("negative")) for row in rows), 3)
        self.assertTrue(all(row["source_type"] == "synthetic" for row in rows))
        for row in rows:
            self.assertTrue(row["source"].strip())
            self.assertGreaterEqual(len(row["expected_actions"]), 2)
            self.assertGreaterEqual(len(row["forbidden_actions"]), 2)


if __name__ == "__main__":
    unittest.main()
