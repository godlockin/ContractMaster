"""Offline model evaluation. Raw synthetic/public outputs remain in ignored artifacts."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
from common import TYPES, SYSTEM, system_prompt, rows, parse_tolerant, spans, dump, digest
from guardrails import entities as fallback_entities, resolve, filter_items

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "contract-review-cn" / "scripts"))
import pipeline as p


def rule_entities(text, allowed=None):
    registry = {}
    p.redact(text, [], registry, "SYNTHETIC")
    result = [{"text": item["value"], "type": item["type"]} for item in registry.values()]
    # Public rows need broad format rescue; synthetic contract rows keep
    # conservative semantic rescue to avoid reducing precision on easy cases.
    fallback_scope = allowed if allowed is not None else {"ADDRESS", "PROJECT", "SECRET"}
    return resolve(text, result + fallback_entities(text, fallback_scope))


def characters(items, allowed):
    return {(i, kind) for start, end, kind in items if kind in allowed for i in range(start, end)}


def score(records):
    tp = fp = fn = complete = bad = exact = total = 0
    entity_count = entity_covered = 0
    by_type = {kind: {"tp": 0, "fp": 0, "fn": 0} for kind in sorted(TYPES)}
    for r in records:
        gold_spans = r.get("gold_spans", spans(r["text"], r["entities"]))
        gold = characters(gold_spans, r.get("evaluated_types", TYPES))
        predicted = characters(spans(r["text"], r["predicted"]), r.get("evaluated_types", TYPES))
        for start, end, kind in gold_spans:
            if kind in r.get('evaluated_types', TYPES):
                entity_count += 1
                entity_covered += all((i, kind) in predicted for i in range(start, end))
        correct, extra, missed = gold & predicted, predicted - gold, gold - predicted
        tp += len(correct); fp += len(extra); fn += len(missed)
        complete += not missed
        exact += gold == predicted
        total += 1
        bad += bool(r.get("error"))
        for key, values in (("tp", correct), ("fp", extra), ("fn", missed)):
            for _, kind in values:
                by_type[kind][key] += 1
    recall = tp / (tp + fn) if tp + fn else 1.0
    precision = tp / (tp + fp) if tp + fp else (1.0 if not fn else 0.0)
    latencies = [r["seconds"] for r in records]
    result = {"rows": total, "char_precision": precision, "char_recall": recall,
              "gold_entity_count": entity_count, "fully_covered_entity_count": entity_covered,
              "entity_full_coverage_recall": entity_covered / entity_count if entity_count else 1.0,
              "document_no_miss_rate": complete / total, "document_exact_rate": exact / total,
              "invalid_output_count": bad, "valid_output_rate": 1-bad/total,
              "latency_p50_seconds": statistics.median(latencies),
              "latency_p95_seconds": sorted(latencies)[min(total-1, int(total*.95))], "by_type": by_type}
    result["gate"] = "PASS_CONTROLLED_BENCHMARK" if recall >= .99 and precision >= .95 and bad == 0 else "NOT_QUALIFIED"
    result["certifies_zero_leakage"] = False
    return result


def main(args):
    source = rows(args.data)
    if args.limit:
        source = source[:args.limit]
    if not source:
        raise ValueError("EMPTY_EVALUATION")
    args.output.mkdir(parents=True, exist_ok=False)
    model = tokenizer = generate = sampler = mx = None
    if args.mode != "rules":
        from train import verify_model
        manifest = verify_model(args.model)
        if args.adapter:
            provenance = json.loads((args.adapter / "provenance.json").read_text())
            if provenance["model"]["revision"] != manifest["revision"]:
                raise ValueError("ADAPTER_MODEL_MISMATCH")
        import mlx.core as mx
        from mlx_lm import load, generate
        from mlx_lm.sample_utils import make_sampler
        model, tokenizer = load(str(args.model), adapter_path=str(args.adapter) if args.adapter else None,
                                tokenizer_config={"trust_remote_code": False})
        sampler = make_sampler(temp=0.0)
    records = []
    # Resume by using a new immutable eval directory, never overwrite test results.
    with (args.output / "predictions.jsonl").open("x", encoding="utf-8") as stream:
        for row in source:
            started = time.perf_counter()
            error = None
            dropped = 0
            response = ""
            predicted = []
            if args.mode != "rules":
                prompt = tokenizer.apply_chat_template([{"role": "system", "content": system_prompt(row)},
                          {"role": "user", "content": row["text"]}], tokenize=False,
                          add_generation_prompt=True, enable_thinking=False)
                if len(tokenizer.encode(prompt)) > args.max_input:
                    error = "INPUT_TOO_LONG_REQUIRES_PARTITION"
                else:
                    response = generate(model, tokenizer, prompt=prompt, max_tokens=args.max_output,
                                        sampler=sampler, verbose=False)
                    try:
                        predicted, dropped = parse_tolerant(row["text"], response)
                    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                        error = "INVALID_OR_UNGROUNDED_OUTPUT"
            if args.mode in {"rules", "hybrid"}:
                scope = set(row.get('evaluated_types', [])) or None
                predicted = filter_items(row["text"], predicted + rule_entities(row["text"], scope), scope)
                predicted = resolve(row["text"], predicted)
            else:
                predicted = filter_items(row["text"], predicted, set(row.get('evaluated_types', [])) or None)
                predicted = resolve(row["text"], predicted)
            entry = {**row, "predicted": predicted, "error": error, "dropped_predictions": dropped, "response": response,
                     "seconds": time.perf_counter()-started}
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
            stream.flush()
            records.append(entry)
    result = score(records)
    result.update({"mode": args.mode, "data_digest": digest(source), "adapter": str(args.adapter) if args.adapter else None,
                   "adapter_sha256": hashlib.sha256((args.adapter / 'adapters.safetensors').read_bytes()).hexdigest() if args.adapter else None,
                   "policy_digest": digest(SYSTEM),
                   "peak_memory_gb": mx.get_peak_memory()/1e9 if mx else None,
                   "model_path": str(args.model), "max_input": args.max_input, "max_output": args.max_output})
    dump(args.output / "metrics.json", result)
    print(json.dumps({key: value for key, value in result.items() if key != "by_type"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=Path("artifacts/privacy/models/qwen3-1.7b-4bit"))
    parser.add_argument("--adapter", type=Path)
    parser.add_argument("--mode", choices=["rules", "model", "hybrid"], default="hybrid")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-input", type=int, default=2048)
    parser.add_argument("--max-output", type=int, default=512)
    main(parser.parse_args())
