"""Regression checks binding published reports to exact evaluation evidence."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from core import evaluate, load_jsonl, sha256_file


def normalize_runtime(value):
    return {key.split("/evalrun/", 1)[-1]: digest for key, digest in value.items()}


class ReportBindingsTests(unittest.TestCase):
    def setUp(self):
        self.data = ROOT / "datasets/reviewed4-dev128/dev.jsonl"
        self.data_manifest = ROOT / "datasets/reviewed4-dev128/manifest.json"
        self.reports = {name: ROOT / f"reports/{name}.json" for name in ("baseline-v4", "candidate-p2")}
        self.models = {name: ROOT / f"models/{name}" for name in self.reports}

    def test_manifests_and_profiles_are_consistent(self):
        manifests = {name: json.loads((path / "core-manifest.json").read_text()) for name, path in self.models.items()}
        profiles = {name: json.loads((path / "base-model-profile.json").read_text()) for name, path in self.models.items()}
        for name, manifest in manifests.items():
            report = json.loads(self.reports[name].read_text())
            self.assertEqual(report["manifest"], manifest)
            self.assertEqual(report["manifest_sha256"], sha256_file(self.models[name] / "core-manifest.json"))
            self.assertEqual(manifest["dataset_sha256"], sha256_file(self.data))
            self.assertEqual(manifest["predictions_sha256"], sha256_file(self.models[name] / "predictions.jsonl"))
            metrics = json.loads((self.models[name] / "metrics.json").read_text())
            self.assertEqual(manifest["adapter_sha256"], metrics["adapter_sha256"])
            self.assertEqual(normalize_runtime(manifest["runtime_sha256"]), metrics["runtime_sha256_start"])
            self.assertEqual(normalize_runtime(manifest["runtime_sha256"]), metrics["runtime_sha256_end"])
            self.assertEqual(manifest["base_repo"], profiles[name]["repo"])
            self.assertEqual(manifest["base_revision"], profiles[name]["revision"])
            model_file = next(item for item in profiles[name]["files"] if item["file"] == "model.safetensors")
            self.assertEqual(manifest["base_weights_sha256"], model_file["sha256"])
        self.assertEqual(manifests["baseline-v4"]["base_repo"], manifests["candidate-p2"]["base_repo"])
        self.assertEqual(manifests["baseline-v4"]["base_revision"], manifests["candidate-p2"]["base_revision"])

    def test_reports_recompute_from_exact_original_predictions(self):
        data_rows = load_jsonl(self.data)
        for name, model_path in self.models.items():
            manifest = json.loads((model_path / "core-manifest.json").read_text())
            predictions = load_jsonl(model_path / "predictions.jsonl")
            recomputed = evaluate(data_rows, predictions, manifest["protocol"])
            report = json.loads(self.reports[name].read_text())
            for key in ("rows", "blocked", "gold_chars", "covered_chars", "extra_chars", "char_recall", "char_precision", "blocked_rate", "delivered_with_residual", "preservation_failed", "production_qualified"):
                self.assertEqual(report[key], recomputed[key], f"{name}:{key}")
            self.assertEqual(report["records"], recomputed["records"])
            self.assertEqual(report["dataset_sha256"], sha256_file(self.data))
            self.assertEqual(report["predictions_sha256"], sha256_file(model_path / "predictions.jsonl"))

    def test_runtime_and_scorer_hashes_are_current(self):
        manifests = [json.loads((path / "core-manifest.json").read_text()) for path in self.models.values()]
        self.assertEqual(manifests[0]["runtime_sha256"], manifests[1]["runtime_sha256"])
        for name, report_path in self.reports.items():
            report = json.loads(report_path.read_text())
            self.assertEqual(report["manifest"]["runtime_sha256"], manifests[0]["runtime_sha256"])
            for file_path, expected in report["scorer_files_sha256"].items():
                current = ROOT / Path(file_path).name
                self.assertTrue(current.exists(), file_path)
                self.assertEqual(sha256_file(current), expected, file_path)

    def test_expected_preservation_and_production_gate(self):
        expected = {"baseline-v4": 24, "candidate-p2": 0}
        for name, report_path in self.reports.items():
            report = json.loads(report_path.read_text())
            self.assertEqual(report["preservation_failed"], expected[name])
            self.assertFalse(report["production_qualified"])


if __name__ == "__main__":
    unittest.main()
