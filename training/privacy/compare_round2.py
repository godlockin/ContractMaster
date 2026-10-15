"""Sequential GPU evaluation; only completed aggregate results go to stdout."""
from pathlib import Path
import subprocess
import sys
import json

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    runs = [
        ('old-dev', 'evaluate.py', 'artifacts/privacy/data/generalization-v2-ready/dev.jsonl', 'v4-step160'),
        ('new-dev', 'evaluate.py', 'artifacts/privacy/data/generalization-v2-ready/dev.jsonl', 'generalization-round2'),
        ('old-acceptance', 'validate_runtime_round2.py', 'artifacts/privacy/data/acceptance-round2/test.jsonl', 'v4-step160'),
        ('new-acceptance', 'validate_runtime_round2.py', 'artifacts/privacy/data/acceptance-round2/test.jsonl', 'generalization-round2'),
        ('old-public', 'evaluate.py', 'artifacts/privacy/data/openpii-zh-v4/test.jsonl', 'v4-step160'),
        ('new-public', 'evaluate.py', 'artifacts/privacy/data/openpii-zh-v4/test.jsonl', 'generalization-round2'),
    ]
    outcomes = []
    for name, script, data, adapter in runs:
        output = ROOT/'artifacts/privacy/evals'/f'round2-{name}'
        command = [sys.executable, str(ROOT/'training/privacy'/script), '--data', data,
                   '--adapter', str(Path('artifacts/privacy/adapters')/adapter), '--output', str(output)]
        # Immutable completed runs support resuming the comparison without rerunning the GPU.
        if not (output/'metrics.json').is_file():
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=1800)
            if result.returncode:
                print(json.dumps({'status':'FAILED', 'run':name, 'code':result.returncode}))
                print((result.stdout+result.stderr)[-2000:])  # only synthetic/public input
                raise SystemExit(1)
        value = json.loads((output/'metrics.json').read_text())
        outcomes.append({'run':name, **{k:v for k,v in value.items() if k!='by_type'}})
    report = ROOT/'artifacts/privacy/evals/round2-comparison.json'
    report.write_text(json.dumps(outcomes, indent=2))
    print(json.dumps({'status':'COMPARED', 'runs':outcomes}))


if __name__ == '__main__':
    main()
