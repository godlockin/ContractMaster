"""Score semantic contract-change risk labels; label matching only."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

RISK_CODES = frozenset({
    "economic_total", "tax", "liability_cap", "liability_allocation",
    "logic_operator", "obligation_strength", "deadline", "renewal",
    "jurisdiction", "acceptance", "ip_ownership", "payment_condition",
    "no_substantive_change",
})


def normalize_risks(value: object, field: str) -> set[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value) or len(value) != len(set(value)):
        raise ValueError(f"INVALID_{field.upper()}")
    risks = set(value)
    if not risks <= RISK_CODES:
        raise ValueError(f"INVALID_{field.upper()}")
    if "no_substantive_change" in risks and len(risks) > 1:
        raise ValueError(f"INVALID_{field.upper()}_MIXED_NEGATIVE")
    return set() if risks == {"no_substantive_change"} else risks


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cases(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError("EMPTY_DATASET")
    ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
            raise ValueError("INVALID_CASE")
        if row["id"] in ids:
            raise ValueError("DUPLICATE_CASE_ID")
        ids.add(row["id"])
        for field in ("before", "after"):
            if not isinstance(row.get(field), str) or not row[field]:
                raise ValueError("INVALID_CASE_FIELDS")
        normalize_risks(row.get("expected_risks"), "expected_risks")
    return rows


def load_predictions(path: Path, case_ids: set[str]) -> dict[str, set[str]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    result: dict[str, set[str]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
            raise ValueError("INVALID_PREDICTION")
        ident = row["id"]
        if ident not in case_ids:
            raise ValueError("UNKNOWN_PREDICTION_ID")
        if ident in result:
            raise ValueError("DUPLICATE_PREDICTION_ID")
        result[ident] = normalize_risks(row.get("risk_codes"), "predicted_risks")
    missing = case_ids - result.keys()
    if missing:
        raise ValueError("MISSING_PREDICTION_ID")
    return result


def validate_data(data: Path, manifest: Path) -> dict:
    cases = load_cases(data)
    declared = json.loads(manifest.read_text(encoding="utf-8"))
    if declared.get("status") != "challenge_only_unreviewed" or declared.get("rows") != len(cases):
        raise ValueError("MANIFEST_MISMATCH")
    if declared.get("changes_sha256") != digest(data):
        raise ValueError("DATA_SHA256_MISMATCH")
    if set(declared.get("risk_enum", [])) != RISK_CODES:
        raise ValueError("RISK_ENUM_MISMATCH")
    if any(row.get("source") != "synthetic" for row in cases):
        raise ValueError("NON_SYNTHETIC_CASE")
    return {"status": "VALID", "rows": len(cases), "data_sha256": digest(data), "manifest_sha256": digest(manifest)}


def validate_model_manifest(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    required = ("model_id", "base_repo", "base_revision", "base_weights_sha256", "adapter_sha256")
    if not isinstance(value, dict) or any(not isinstance(value.get(k), str) or not value[k] for k in required):
        raise ValueError("INVALID_MODEL_MANIFEST")
    for field in ("base_weights_sha256", "adapter_sha256"):
        if re.fullmatch(r"[0-9a-f]{64}", value[field]) is None:
            raise ValueError("INVALID_MODEL_MANIFEST_HASH")
    return value


def score(data: Path, predictions: Path, model_manifest: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(output)
    validate_data(data, data.parent / "manifest.json")
    model = validate_model_manifest(model_manifest)
    cases = load_cases(data)
    predicted = load_predictions(predictions, {row["id"] for row in cases})
    gold = {row["id"]: normalize_risks(row["expected_risks"], "expected_risks") for row in cases}
    tp = sum(len(gold[i] & predicted[i]) for i in gold)
    fp = sum(len(predicted[i] - gold[i]) for i in gold)
    fn = sum(len(gold[i] - predicted[i]) for i in gold)
    errors = [{"id": i, "missed": sorted(gold[i] - predicted[i]), "extra": sorted(predicted[i] - gold[i])}
              for i in gold if gold[i] != predicted[i]]
    missed_cases = [x for x in errors if x["missed"]]
    false_alarm_cases = [x for x in errors if x["extra"]]
    dataset_manifest = data.parent / "manifest.json"
    result = {
        "status": "SCORED",
        "production_qualified": False,
        "rows": len(cases),
        "micro_precision": tp / (tp + fp) if tp + fp else 1.0,
        "micro_recall": tp / (tp + fn) if tp + fn else 1.0,
        "true_positive_codes": tp, "false_positive_codes": fp, "false_negative_codes": fn,
        "mismatched_cases": errors,
        "missed_cases": missed_cases,
        "false_alarm_cases": false_alarm_cases,
        "missed_case_count": len(missed_cases),
        "false_alarm_case_count": len(false_alarm_cases),
        "no_substantive_change_as_empty_risk": True,
        "interpretation": "Label matching only; does not assess explanation or legal correctness.",
        "data_sha256": digest(data), "predictions_sha256": digest(predictions),
        "dataset_manifest_sha256": digest(dataset_manifest),
        "model_manifest_sha256": digest(model_manifest),
        "model_manifest": model,
        "scoring_code_sha256": digest(Path(__file__)),
    }
    output.mkdir(parents=True)
    (output / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("status", "rows", "micro_precision", "micro_recall", "false_negative_codes")}))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate-data")
    check.add_argument("--data", type=Path, required=True)
    check.add_argument("--manifest", type=Path, required=True)
    run = sub.add_parser("score")
    run.add_argument("--data", type=Path, required=True)
    run.add_argument("--predictions", type=Path, required=True)
    run.add_argument("--model-manifest", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "validate-data":
        print(json.dumps(validate_data(args.data, args.manifest), ensure_ascii=False))
    else:
        score(args.data, args.predictions, args.model_manifest, args.output)


if __name__ == "__main__":
    main()
