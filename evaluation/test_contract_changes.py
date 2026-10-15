import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from contract_changes import load_cases, load_predictions, score, validate_data

ROOT = Path(__file__).parent / "datasets" / "contract-changes-v1"


class ContractChangesTests(unittest.TestCase):
    def test_validate_synthetic_dataset(self):
        result = validate_data(ROOT / "changes.jsonl", ROOT / "manifest.json")
        self.assertEqual(result["status"], "VALID")
        self.assertEqual(result["rows"], 28)

    def test_prediction_validation_rejects_unknown_and_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            cases = load_cases(ROOT / "changes.jsonl")
            ids = {row["id"] for row in cases}
            unknown = tmp_path / "unknown.jsonl"
            unknown.write_text(json.dumps({"id": "NOPE", "risk_codes": []}) + "\n")
            with self.assertRaisesRegex(ValueError, "UNKNOWN_PREDICTION_ID"):
                load_predictions(unknown, ids)
            duplicate = tmp_path / "duplicate.jsonl"
            row = {"id": next(iter(ids)), "risk_codes": []}
            duplicate.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n")
            with self.assertRaisesRegex(ValueError, "DUPLICATE_PREDICTION_ID"):
                load_predictions(duplicate, ids)

    def test_negative_normalizes_to_empty_risk_and_mixed_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            cases = load_cases(ROOT / "changes.jsonl")
            pred = tmp_path / "predictions.jsonl"
            pred.write_text("".join(json.dumps({"id": row["id"], "risk_codes": []}) + "\n" for row in cases))
            loaded = load_predictions(pred, {row["id"] for row in cases})
            self.assertEqual(loaded["CCV1-025"], set())
            mixed = tmp_path / "mixed.jsonl"
            mixed.write_text(json.dumps({"id": "CCV1-025", "risk_codes": ["no_substantive_change", "tax"]}) + "\n")
            with self.assertRaisesRegex(ValueError, "INVALID_PREDICTED_RISKS_MIXED_NEGATIVE"):
                load_predictions(mixed, {"CCV1-025"})

    def test_empty_and_non_string_inputs_raise_value_error(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            empty = tmp_path / "empty.jsonl"
            empty.write_text("")
            with self.assertRaisesRegex(ValueError, "EMPTY_DATASET"):
                load_cases(empty)
            bad = tmp_path / "bad.jsonl"
            bad.write_text(json.dumps({"id": "x", "before": "a", "after": "b", "expected_risks": [["tax"]]}) + "\n")
            with self.assertRaisesRegex(ValueError, "INVALID_EXPECTED_RISKS"):
                load_cases(bad)

    def test_score_fixture_and_bind_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            cases = load_cases(ROOT / "changes.jsonl")
            pred = tmp_path / "predictions.jsonl"
            pred.write_text("".join(json.dumps({"id": row["id"], "risk_codes": row["expected_risks"]}) + "\n" for row in cases))
            model = tmp_path / "model-manifest.json"
            model.write_text('{"model_id":"fixture","base_repo":"synthetic","base_revision":"r1","base_weights_sha256":"' + "0" * 64 + '","adapter_sha256":"' + "1" * 64 + '"}\n')
            out = tmp_path / "out"
            score(ROOT / "changes.jsonl", pred, model, out)
            result = json.loads((out / "metrics.json").read_text())
            self.assertEqual(result["micro_precision"], 1.0)
            self.assertEqual(result["micro_recall"], 1.0)
            self.assertFalse(result["production_qualified"])
            self.assertTrue(result["scoring_code_sha256"])


if __name__ == "__main__":
    unittest.main()
