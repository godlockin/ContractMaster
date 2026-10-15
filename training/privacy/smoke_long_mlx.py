"""Opt-in synthetic long-document MLX smoke; never reads contract fixtures."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

from redact_local import redact_text
from model_status import check_model


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--adapter', type=Path, required=True)
    parser.add_argument('--max-input', type=int, default=2048)
    parser.add_argument('--max-output', type=int, default=512)
    parser.add_argument('--max-total', type=int, default=100000)
    args = parser.parse_args()
    status = check_model(args.model, args.adapter)
    if status.get('status') != 'AVAILABLE':
        raise RuntimeError(status.get('reason', 'MODEL_UNAVAILABLE'))
    from mlx_lm import load, generate as mlx_generate
    model, tokenizer = load(str(args.model), adapter_path=str(args.adapter),
                            tokenizer_config={'trust_remote_code': False})
    phrase = "合成背景文本。普通金额300万元应保留。"
    repeat = 1
    while repeat < 1000:
        candidate = phrase * repeat + "联络电话：13800138000；canary-秘密项目"
        prompt = tokenizer.apply_chat_template([
            {'role': 'system', 'content': 'synthetic smoke'},
            {'role': 'user', 'content': candidate}], tokenize=False,
            add_generation_prompt=True, enable_thinking=False)
        if len(tokenizer.encode(prompt)) > args.max_input * 2:
            break
        repeat += 1
    source = candidate
    original_prompt_tokens = len(tokenizer.encode(prompt))
    prompts: list[int] = []
    def counted_generate(model_obj, tok, prompt, max_tokens, verbose=False):
        prompts.append(len(tok.encode(prompt)))
        return mlx_generate(model_obj, tok, prompt=prompt, max_tokens=max_tokens, verbose=verbose)
    result = redact_text(source, model, tokenizer, counted_generate,
                         custom=[{'text': 'canary-秘密项目', 'type': 'PROJECT'}],
                         max_input=args.max_input, max_output=args.max_output,
                         max_total=args.max_total)
    restored = result['redacted_text']
    mapping = {item['token']: item['value'] for item in result['mapping']}
    for occurrence in reversed(result['occurrences']):
        token = occurrence['token']
        restored = (restored[:occurrence['redacted_start']] + mapping[token] +
                    restored[occurrence['redacted_end']:])
    if restored != source:
        raise RuntimeError('RESTORE_HASH_MISMATCH')
    expected_amounts = source.count('300万元')
    if len(prompts) <= 1:
        raise RuntimeError('LONG_INPUT_NOT_PARTITIONED')
    if any(value > args.max_input for value in prompts):
        raise RuntimeError('PROMPT_OVER_BUDGET')
    if sum(value + args.max_output for value in prompts) > args.max_total:
        raise RuntimeError('TOTAL_BUDGET_OVERFLOW')
    if 'canary-秘密项目' in result['redacted_text']:
        raise RuntimeError('CANARY_LEAK')
    if '13800138000' in result['redacted_text']:
        raise RuntimeError('PHONE_LEAK')
    if result['redacted_text'].count('300万元') != expected_amounts:
        raise RuntimeError('PUBLIC_AMOUNT_CHANGED')
    print(json.dumps({'status': 'LONG_MLX_SMOKE_PASS', 'generate_calls': len(prompts),
                      'max_prompt_tokens': max(prompts, default=0),
                      'original_prompt_tokens': original_prompt_tokens,
                      'prompt_tokens': prompts,
                      'reserved_total_tokens': sum(value + args.max_output for value in prompts),
                      'public_amount_count': result['redacted_text'].count('300万元'),
                      'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                      'restored_sha256': hashlib.sha256(restored.encode()).hexdigest(),
                      'entity_count': result['entity_count']}))


if __name__ == '__main__':
    main()
