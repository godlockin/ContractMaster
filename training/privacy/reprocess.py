"""Re-score saved local predictions with current safety guardrails, no model call."""
import argparse
import json
from pathlib import Path
from common import rows, parse_tolerant, dump, digest
from evaluate import score, rule_entities
from guardrails import resolve, filter_items


def main(source_dir: Path, output: Path) -> None:
    if output.exists():
        raise ValueError('OUTPUT_EXISTS')
    source = rows(source_dir / 'predictions.jsonl')
    rebuilt = []
    for row in source:
        predicted, dropped = [], 0
        error = None
        if row.get('response'):
            try:
                predicted, dropped = parse_tolerant(row['text'], row['response'])
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                error = 'INVALID_JSON_OUTPUT'
        scope = set(row.get('evaluated_types', [])) or None
        predicted = resolve(row['text'], filter_items(row['text'], predicted + rule_entities(row['text'], scope), scope))
        rebuilt.append({**row, 'predicted': predicted, 'error': error,
                       'dropped_predictions': dropped})
    output.mkdir(parents=True)
    (output / 'predictions.jsonl').write_text(''.join(json.dumps(x, ensure_ascii=False)+'\n' for x in rebuilt), encoding='utf-8')
    result = score(rebuilt)
    result.update({'mode': 'offline-reprocess', 'source_evaluation': str(source_dir),
                   'data_digest': digest(rebuilt), 'adapter': source[0].get('adapter') if source else None})
    dump(output / 'metrics.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'by_type'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    main(args.source, args.output)
