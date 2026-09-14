"""Audit literal masking coverage separately from typed extraction accuracy."""
import argparse
from pathlib import Path
from common import rows, spans, TYPES, dump


def audit(records):
    gold_count = missed_count = complete = 0
    for row in records:
        gold_spans = row.get('gold_spans', spans(row['text'], row['entities']))
        gold = {i for start, end, kind in gold_spans
                if kind in row.get('evaluated_types', TYPES) for i in range(start, end)}
        masked = {i for start, end, _ in spans(row['text'], row['predicted']) for i in range(start, end)}
        missing = gold - masked
        gold_count += len(gold)
        missed_count += len(missing)
        complete += not missing
    return {'rows': len(records), 'sensitive_characters': gold_count, 'unmasked_characters': missed_count,
            'untyped_coverage_recall': 1 - missed_count / gold_count if gold_count else 1.0,
            'document_no_unmasked_gold_rate': complete / len(records) if records else 0,
            'scope': 'literal coverage only; wrong entity type can still mask text; does not change qualification',
            'certifies_zero_leakage': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--evaluation', type=Path, required=True)
    args = parser.parse_args()
    destination = args.evaluation / 'coverage-audit.json'
    if destination.exists():
        raise ValueError('AUDIT_ALREADY_EXISTS')
    dump(destination, audit(rows(args.evaluation / 'predictions.jsonl')))
