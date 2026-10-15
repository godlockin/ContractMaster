"""Acceptance through the deployed redactor, including preserved legal wording."""
import argparse
import json
import hashlib
import os
from pathlib import Path
import time

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
from common import rows, digest
from evaluate import score
from redact_local import redact_text
from model_status import check_model


def main(data: Path, model_path: Path, adapter: Path, output: Path) -> None:
    status = check_model(model_path, adapter)
    if status['status'] != 'AVAILABLE':
        raise ValueError(status['reason'])
    from mlx_lm import load, generate
    from mlx_lm.sample_utils import make_sampler
    model, tokenizer = load(str(model_path), adapter_path=str(adapter), tokenizer_config={'trust_remote_code': False})
    sampler = make_sampler(temp=0.0)
    def deterministic(*args, **kwargs):
        return generate(*args, **kwargs, sampler=sampler)
    source = rows(data)
    records = []
    preserved = passed = dropped = 0
    output.mkdir(parents=True, exist_ok=False)
    for row in source:
        started = time.perf_counter()
        try:
            result = redact_text(row['text'], model, tokenizer, deterministic)
            predicted = [{'text':x['value'], 'type':x['type']} for x in result['mapping']]
            dropped += result['dropped_model_items']
            if row.get('preserve_text') is not None:
                preserved += 1
                passed += result['redacted_text'] == row['preserve_text']
            error = None
        except Exception:
            predicted = []
            error = 'RUNTIME_BLOCKED'
            if row.get('preserve_text') is not None:
                preserved += 1
        records.append({**row, 'predicted':predicted, 'error':error, 'seconds':time.perf_counter()-started})
    metrics = score(records)
    metrics.update(data_digest=digest(source), adapter=str(adapter), preservation_cases=preserved,
                   preservation_passed=passed, dropped_model_items=dropped,
                   accepted=metrics['gate']=='PASS_CONTROLLED_BENCHMARK' and passed==preserved and dropped==0)
    metrics['adapter_sha256'] = hashlib.sha256((adapter/'adapters.safetensors').read_bytes()).hexdigest()
    (output/'predictions.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in records))
    (output/'metrics.json').write_text(json.dumps(metrics, indent=2))
    print(json.dumps({k:v for k,v in metrics.items() if k!='by_type'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--adapter', type=Path, required=True)
    parser.add_argument('--model', type=Path, default=Path('artifacts/privacy/models/qwen3-1.7b-4bit'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    main(args.data, args.model, args.adapter, args.output)
