"""Assemble new training data with explicit development isolation and provenance."""
from pathlib import Path
import argparse
import json
from common import rows, spans, messages, digest


def assemble(train_paths: list[Path], dev_paths: list[Path], output: Path, tokenizer_path: Path | None = None) -> None:
    def collect(paths: list[Path]) -> list[dict]:
        result = {}
        for path in paths:
            for row in rows(path):
                spans(row['text'], row['entities'])
                if row['text'] in result and result[row['text']]['entities'] != row['entities']:
                    raise ValueError('CONFLICTING_LABELS')
                result[row['text']] = row
        return list(result.values())
    development = collect(dev_paths)
    dev_texts = {r['text'] for r in development}
    training = [r for r in collect(train_paths) if r['text'] not in dev_texts]
    excluded_long = 0
    if tokenizer_path:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_path), local_files_only=True, trust_remote_code=False)
        def fits(row):
            return len(tokenizer.apply_chat_template(messages(row), tokenize=True, enable_thinking=False)) <= 1024
        eligible = [r for r in training if fits(r)]
        excluded_long = len(training) - len(eligible)
        training = eligible
        if not all(fits(r) for r in development):
            raise ValueError('DEVELOPMENT_INPUT_TOO_LONG')
    if not training or not development:
        raise ValueError('EMPTY_SPLIT')
    output.mkdir(parents=True, exist_ok=False)
    (output/'mlx').mkdir()
    for name, records in [('train', training), ('dev', development)]:
        (output/f'{name}.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in records))
        mlx_name = 'train' if name == 'train' else 'valid'
        (output/'mlx'/f'{mlx_name}.jsonl').write_text(''.join(json.dumps({'messages':messages(r)}, ensure_ascii=False)+'\n' for r in records))
    manifest = {'train_count':len(training), 'dev_count':len(development), 'train_digest':digest(training),
                'dev_digest':digest(development), 'train_sources':[str(p) for p in train_paths],
                'dev_sources':[str(p) for p in dev_paths], 'test_loaded':False,
                'excluded_over_1024_tokens':excluded_long}
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--train', type=Path, action='append', required=True)
    parser.add_argument('--dev', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tokenizer', type=Path)
    args = parser.parse_args()
    assemble(args.train, args.dev, args.output, args.tokenizer)
