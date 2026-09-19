"""Local-only text redaction entry point using the qualified controlled candidate."""
from __future__ import annotations
import argparse, hashlib, json, os, sys
from pathlib import Path

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'contract-review-cn' / 'scripts'))
import pipeline as contract_pipeline
from common import parse_tolerant, spans, digest, system_prompt
from common import TYPES
from guardrails import filter_items, resolve
from evaluate import rule_entities
from model_status import check_model


def write_new(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(content)


def _custom_entities(config: Path | None, entities: Path | None) -> list[dict]:
    """Read local policy files; values never leave this process."""
    paths = [path for path in (config, entities) if path is not None]
    result: list[dict] = []
    for path in paths:
        try:
            if path.stat().st_mode & 0o777 != 0o600:
                raise ValueError("ENTITY_FILE_PERMISSION_MUST_BE_600")
            if path.parent.stat().st_mode & 0o777 != 0o700:
                raise ValueError("ENTITY_DIRECTORY_PERMISSION_MUST_BE_700")
        except OSError as exc:
            raise ValueError("ENTITY_FILE_UNREADABLE") from exc
        value = json.loads(path.read_text(encoding="utf-8"))
        items = value.get("entities") if isinstance(value, dict) else None
        if not isinstance(items, list):
            raise ValueError("ENTITY_SCHEMA")
        for item in items:
            literal = item.get("value") if isinstance(item, dict) else None
            kind = item.get("type") if isinstance(item, dict) else None
            if (not isinstance(literal, str) or not literal.strip() or
                    not isinstance(kind, str) or kind not in TYPES):
                raise ValueError("ENTITY_SCHEMA")
            candidate = {"text": literal, "type": kind}
            if candidate not in result:
                result.append(candidate)
    return result


def _rule_redact(text: str, custom: list[dict]) -> dict:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("EMPTY_TEXT")
    predicted = resolve(text, filter_items(text, rule_entities(text) + custom, None))
    spans(text, predicted)
    registry: dict[str, dict] = {}
    redacted, occurrences = contract_pipeline.redact(text, [(x["text"], x["type"]) for x in predicted], registry, "LOCAL")
    return {"redacted_text": redacted, "mapping": list(registry.values()),
            "occurrences": occurrences, "entity_count": len(predicted),
            "dropped_model_items": 0, "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "policy_digest": digest("local-privacy-v1")}


def redact_text(text: str, model, tokenizer, generate, custom: list[dict] | None = None,
                max_input: int = 2048, max_output: int = 512) -> dict:
    if not isinstance(text, str) or not text.strip():
        raise ValueError('EMPTY_TEXT')
    prompt = tokenizer.apply_chat_template([
        {'role': 'system', 'content': system_prompt({})},
        {'role': 'user', 'content': text}], tokenize=False, add_generation_prompt=True, enable_thinking=False)
    if len(tokenizer.encode(prompt)) > max_input:
        raise ValueError('INPUT_TOO_LONG_REQUIRES_PARTITION')
    response = generate(model, tokenizer, prompt=prompt, max_tokens=max_output, verbose=False)
    try:
        predicted, dropped = parse_tolerant(text, response)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError('MODEL_OUTPUT_BLOCKED') from exc
    predicted = resolve(text, filter_items(text, predicted + rule_entities(text) + (custom or []), None))
    # Verify every emitted literal before invoking replacement.
    spans(text, predicted)
    registry: dict[str, dict] = {}
    redacted, occurrences = contract_pipeline.redact(text, [(x['text'], x['type']) for x in predicted], registry, 'LOCAL')
    return {'redacted_text': redacted, 'mapping': list(registry.values()),
            'occurrences': occurrences, 'entity_count': len(predicted),
            'dropped_model_items': dropped, 'source_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'policy_digest': digest('local-privacy-v1')}


def main(args: argparse.Namespace) -> None:
    text = args.input.read_text(encoding='utf-8')
    custom = _custom_entities(args.config, args.entities)
    model_path = args.model
    adapter_path = args.adapter
    if not model_path.is_absolute() and not model_path.exists():
        bundled = ROOT / model_path
        if bundled.exists():
            model_path = bundled
    if not adapter_path.is_absolute() and not adapter_path.exists():
        bundled = ROOT / adapter_path
        if bundled.exists():
            adapter_path = bundled
    status = check_model(model_path, adapter_path, self_test=args.self_test)
    backend = args.backend
    if backend == "local" and status["status"] != "AVAILABLE":
        raise RuntimeError(status["reason"] or status["status"])
    used_backend = "rules"
    fallback_reason = None
    if backend in {"auto", "local"} and status["status"] == "AVAILABLE":
        try:
            from mlx_lm import load, generate
            model, tokenizer = load(str(model_path), adapter_path=str(adapter_path),
                                    tokenizer_config={'trust_remote_code': False})
            result = redact_text(text, model, tokenizer, generate, custom, args.max_input, args.max_output)
            used_backend = "local-model"
        except Exception as exc:
            if backend == "local":
                raise RuntimeError("LOCAL_MODEL_FAILED") from exc
            if isinstance(exc, ValueError) and str(exc) in {
                    "EMPTY_TEXT", "INPUT_TOO_LONG_REQUIRES_PARTITION",
                    "MODEL_OUTPUT_BLOCKED", "ENTITY_NOT_IN_SOURCE", "OUTPUT_TOO_LARGE"}:
                # Safety validation failures are not availability failures.
                raise RuntimeError(str(exc)) from exc
            fallback_reason = "LOCAL_MODEL_FAILED"
            result = _rule_redact(text, custom)
    else:
        fallback_reason = status["reason"] or status["status"]
        result = _rule_redact(text, custom)
    args.output.mkdir(parents=True, exist_ok=False)
    write_new(args.output / 'redacted.txt', result.pop('redacted_text'))
    write_new(args.output / 'mapping.json', json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'LOCAL_REDACTION_COMPLETE', 'backend': used_backend,
                      'fallback_reason': fallback_reason, 'model_status': status["status"],
                      'output': str(args.output), 'entity_count': result['entity_count'],
                      'dropped_model_items': result['dropped_model_items']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', type=Path, default=Path('artifacts/privacy/models/qwen3-1.7b-4bit'))
    parser.add_argument('--adapter', type=Path, default=Path('artifacts/privacy/adapters/v4-step160'))
    parser.add_argument('--backend', choices=('auto', 'local', 'rules'), default='auto',
                        help='auto=local model then safe local rules; local=fail if unavailable; rules=rules only')
    parser.add_argument('--config', type=Path, help='case-local privacy-policy.json')
    parser.add_argument('--entities', type=Path, help='case-local entity dictionary')
    parser.add_argument('--self-test', action='store_true', help='run one local model smoke test before use')
    parser.add_argument('--max-input', type=int, default=2048)
    parser.add_argument('--max-output', type=int, default=512)
    main(parser.parse_args())
