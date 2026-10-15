"""Local-only text redaction entry point using the qualified controlled candidate."""
from __future__ import annotations
import argparse, hashlib, json, os, re, sys
from pathlib import Path

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'contract-review-cn' / 'scripts'))
import pipeline as contract_pipeline
from privacy_policy_schema import validate_controls
from common import parse_tolerant, spans, digest, system_prompt
from common import TYPES
from guardrails import filter_items, resolve, contextual_entities
from normalized_view import View, canonical_view, project
from evaluate import rule_entities
from model_status import check_model
from partition import PartitionError, occurrence_in_core, partition_view


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
        if not isinstance(value, dict):
            raise ValueError("ENTITY_SCHEMA")
        validate_controls(value)
        items = value.get("entities")
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


def _predictions(text: str, view: View, model_items: list[dict], custom: list[dict]) -> list[dict]:
    predicted = resolve(view.text, filter_items(view.text, model_items + rule_entities(view.text, TYPES), None))
    predicted.extend(item for item in contextual_entities(view.text, predicted) if item not in predicted)
    source_items = project(text, view, predicted)
    # Policy also matches normalized surfaces, including an inserted alias clause.
    remove = set()
    for match in re.finditer(r'[（(](?:以下简称|简称|下称)[^）)\n]{1,30}[）)]', view.text):
        remove.update(range(match.start(), match.end()))
    policy_view = View(''.join(c for i,c in enumerate(view.text) if i not in remove),
                       tuple(p for i,p in enumerate(view.positions) if i not in remove))
    for item in custom:
        normalized = canonical_view(item['text']).text
        if not normalized:
            continue
        for candidate in project(text, policy_view, [{'text':normalized,'type':item['type']}]):
            if candidate not in source_items:
                source_items.append(candidate)
    return source_items


def _render(text: str, predicted: list[dict]) -> dict:
    spans(text, predicted)
    registry: dict[str, dict] = {}
    redacted, occurrences = contract_pipeline.redact(text, [(x["text"], x["type"]) for x in predicted], registry, "LOCAL", include_rules=False)
    return {"redacted_text": redacted, "mapping": list(registry.values()),
            "occurrences": occurrences, "entity_count": len(predicted),
            "dropped_model_items": 0, "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "policy_digest": digest("local-privacy-v5-normalized-source-ranges")}


def _recover_explicit_split_names(view_text: str, response: str) -> list[dict]:
    """Recover only model names split by slash in an explicit name field."""
    try:
        value = json.loads(response.strip())
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(value, list):
        return []
    fields = list(re.finditer(
        r'(?:登记)?(?:姓名|联系人|签约人|授权代表)\s*[：:]?\s*([\u4e00-\u9fff]\s*[/／]\s*'
        r'[\u4e00-\u9fff](?:\s*[/／]\s*[\u4e00-\u9fff]){0,3})', view_text))
    recovered = []
    for item in value:
        if not isinstance(item, dict) or item.get('type') != 'PERSON':
            continue
        literal = item.get('text')
        if not isinstance(literal, str) or literal in view_text:
            continue
        for field in fields:
            split = field.group(1)
            compact = re.sub(r'\s*[/／]\s*', '', split)
            if compact == literal:
                candidate = {'text': split, 'type': 'PERSON'}
                if candidate not in recovered:
                    recovered.append(candidate)
    return recovered


def _rule_redact(text: str, custom: list[dict]) -> dict:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("EMPTY_TEXT")
    return _render(text, _predictions(text, canonical_view(text), [], custom))


def _redact_partitioned(text: str, view: View, model, tokenizer, generate,
                        custom: list[dict], max_input: int, max_output: int,
                        max_total: int | None, max_chunks: int) -> dict:
    parts = partition_view(view, tokenizer, system_prompt({}), max_input=max_input,
                           max_output=max_output, max_total=max_total,
                           max_chunks=max_chunks)
    selected: list[tuple[int, int, str, str]] = []
    for part in parts:
        prompt = tokenizer.apply_chat_template([
            {'role': 'system', 'content': system_prompt({})},
            {'role': 'user', 'content': part.text}], tokenize=False,
            add_generation_prompt=True, enable_thinking=False)
        if len(tokenizer.encode(prompt)) > max_input:
            raise ValueError('PARTITION_PROMPT_OVER_BUDGET')
        response = generate(model, tokenizer, prompt=prompt,
                            max_tokens=max_output, verbose=False)
        if len(tokenizer.encode(response)) >= max_output:
            raise ValueError('MODEL_OUTPUT_TRUNCATED')
        try:
            predicted, dropped = parse_tolerant(part.text, response)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError('MODEL_OUTPUT_BLOCKED') from exc
        if dropped:
            recovered = _recover_explicit_split_names(part.text, response)
            if dropped != len(recovered):
                raise ValueError('MODEL_ITEMS_UNGROUNDED')
            predicted.extend(recovered)
        for item in predicted:
            # Apply same conservative semantic filters as short-text path
            # before converting model literals into source occurrences.
            safe_items = resolve(view.text, filter_items(view.text, [item], None))
            if not any(x.get('text') == item.get('text') and
                       x.get('type') == item.get('type') for x in safe_items):
                continue
            for match in re.finditer(re.escape(item['text']), part.text):
                if not occurrence_in_core(part, match.start(), match.end()):
                    continue
                # A match cut by an outer context edge may be a partial entity.
                if ((match.start() == 0 and part.view.positions[0][0] > 0) or
                        (match.end() == len(part.text) and
                         part.view.positions[-1][1] < len(text))):
                    raise ValueError('ENTITY_CROSSES_PARTITION_BOUNDARY')
                start = part.view.positions[match.start()][0]
                end = part.view.positions[match.end() - 1][1]
                selected.append((start, end, item['type'], text[start:end]))
    # Preserve deterministic coverage on normalized windows (full-width and
    # escaped forms map back through View.positions).
    for part in parts:
        for item in rule_entities(part.text, TYPES):
            for match in re.finditer(re.escape(item['text']), part.text):
                if not occurrence_in_core(part, match.start(), match.end()):
                    continue
                start = part.view.positions[match.start()][0]
                end = part.view.positions[match.end() - 1][1]
                selected.append((start, end, item['type'], text[start:end]))
    # Policy dictionary uses canonical matching and is projected to exact
    # source ranges, including inserted alias clauses.
    for item in _predictions(text, view, [], custom):
        for match in re.finditer(re.escape(item['text']), text):
            selected.append((match.start(), match.end(), item['type'], item['text']))
    # Resolve semantic ambiguity against every source occurrence before writing
    # anything; a public/secret collision must fail as one transaction.
    checks = []
    for _, _, kind, value in selected:
        item = {'text': value, 'type': kind}
        if item not in checks:
            checks.append(item)
    _predictions(text, view, checks, custom)
    return _render_selected(text, selected, custom)


def _render_selected(text: str, selected: list[tuple[int, int, str, str]],
                     custom: list[dict]) -> dict:
    """Render only occurrence ranges returned by bounded windows."""
    for item in custom:
        literal, kind = item.get('text'), item.get('type')
        if isinstance(literal, str) and isinstance(kind, str):
            selected.extend((m.start(), m.end(), kind, literal)
                            for m in re.finditer(re.escape(literal), text))
    registry: dict[tuple[str, str], str] = {}
    counters: dict[str, int] = {}
    unique: dict[tuple[int, int], tuple[str, str, str]] = {}
    for start, end, kind, value in selected:
        if not (0 <= start < end <= len(text)) or text[start:end] != value:
            raise ValueError('ENTITY_NOT_IN_SOURCE')
        key = (kind, value)
        token = registry.get(key)
        if token is None:
            counters[kind] = counters.get(kind, 0) + 1
            token = f'⟦{kind}_{counters[kind]:04d}⟧'
            registry[key] = token
        prior = unique.get((start, end))
        if prior is not None and prior[0] != kind:
            raise ValueError('AMBIGUOUS_ENTITY_OCCURRENCE')
        unique[(start, end)] = (kind, token, value)
    ordered = sorted(unique.items())
    for ((start, end), _left), ((next_start, _next_end), _right) in zip(ordered, ordered[1:]):
        if next_start < end:  # defensive overlap gate
            raise ValueError('AMBIGUOUS_ENTITY_OCCURRENCE')
    out, occurrences, cursor = [], [], 0
    for (start, end), (kind, token, value) in ordered:
        out.append(text[cursor:start]); red_start = sum(len(x) for x in out)
        out.append(token); red_end = red_start + len(token)
        occurrences.append({'token': token, 'type': kind, 'value': value,
                            'original_start': start, 'original_end': end,
                            'redacted_start': red_start, 'redacted_end': red_end})
        cursor = end
    out.append(text[cursor:]); redacted = ''.join(out)
    return {'redacted_text': redacted,
            'mapping': [{'token': token, 'type': kind, 'value': value}
                        for (kind, value), token in registry.items()],
            'occurrences': occurrences, 'entity_count': len(occurrences),
            'dropped_model_items': 0,
            'source_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'policy_digest': digest('local-privacy-v5-normalized-source-ranges')}


def redact_text(text: str, model, tokenizer, generate, custom: list[dict] | None = None,
                max_input: int = 2048, max_output: int = 512,
                max_total: int | None = None, max_chunks: int = 64) -> dict:
    if not isinstance(text, str) or not text.strip():
        raise ValueError('EMPTY_TEXT')
    if any(isinstance(x, bool) or not isinstance(x, int) or x <= 0 for x in (max_input, max_output, max_chunks)):
        raise ValueError('INVALID_PARTITION_BUDGET')
    if max_total is not None and (isinstance(max_total, bool) or not isinstance(max_total, int) or max_total <= 0):
        raise ValueError('INVALID_PARTITION_BUDGET')
    view = canonical_view(text)
    prompt = tokenizer.apply_chat_template([
        {'role': 'system', 'content': system_prompt({})},
        {'role': 'user', 'content': view.text}], tokenize=False, add_generation_prompt=True, enable_thinking=False)
    prompt_tokens = len(tokenizer.encode(prompt))
    if prompt_tokens > max_input:
        try:
            return _redact_partitioned(text, view, model, tokenizer, generate,
                                      custom or [], max_input, max_output,
                                      max_total, max_chunks)
        except PartitionError as exc:
            raise ValueError(str(exc)) from exc
    if max_total is not None and prompt_tokens + max_output > max_total:
        raise ValueError('TOTAL_BUDGET_EXCEEDED')
    response = generate(model, tokenizer, prompt=prompt, max_tokens=max_output, verbose=False)
    if len(tokenizer.encode(response)) >= max_output:
        raise ValueError('MODEL_OUTPUT_TRUNCATED')
    try:
        predicted, dropped = parse_tolerant(view.text, response)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError('MODEL_OUTPUT_BLOCKED') from exc
    if dropped:
        recovered = _recover_explicit_split_names(view.text, response)
        if dropped != len(recovered):
            raise ValueError('MODEL_ITEMS_UNGROUNDED')
        predicted.extend(recovered)
    return _render(text, _predictions(text, view, predicted, custom or []))


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
    backend = args.backend
    # Rules mode is deliberately independent of optional model artifacts and
    # MLX probing; this keeps deterministic offline fallback usable.
    status = ({"status": "NOT_CHECKED", "reason": "RULES_BACKEND"}
              if backend == "rules" else check_model(model_path, adapter_path, self_test=args.self_test))
    if backend == "local" and status["status"] != "AVAILABLE":
        raise RuntimeError(status["reason"] or status["status"])
    used_backend = "rules"
    fallback_reason = None
    if backend in {"auto", "local"} and status["status"] == "AVAILABLE":
        try:
            from mlx_lm import load, generate
            model, tokenizer = load(str(model_path), adapter_path=str(adapter_path),
                                    tokenizer_config={'trust_remote_code': False})
            result = redact_text(text, model, tokenizer, generate, custom, args.max_input,
                                 args.max_output, getattr(args, 'max_total', None),
                                 getattr(args, 'max_chunks', 64))
            used_backend = "local-model"
        except Exception as exc:
            if backend == "local":
                raise RuntimeError("LOCAL_MODEL_FAILED") from exc
            if isinstance(exc, ValueError) and str(exc) in {
                    "EMPTY_TEXT", "INPUT_TOO_LONG_REQUIRES_PARTITION", "TOTAL_BUDGET_EXCEEDED",
                    "PARTITION_INPUT_TOO_LARGE", "MAX_CHUNKS_EXCEEDED", "INVALID_PARTITION_BUDGET",
                    "PARTITION_PROMPT_OVER_BUDGET", "ENTITY_CROSSES_PARTITION_BOUNDARY",
                    "MODEL_OUTPUT_TRUNCATED",
                    "MODEL_OUTPUT_BLOCKED", "MODEL_ITEMS_UNGROUNDED", "AMBIGUOUS_ENTITY_OCCURRENCE", "ENTITY_NOT_IN_SOURCE", "OUTPUT_TOO_LARGE"}:
                # Safety validation failures are not availability failures.
                raise RuntimeError(str(exc)) from exc
            fallback_reason = "LOCAL_MODEL_FAILED"
            result = _rule_redact(text, custom)
    else:
        fallback_reason = status["reason"] or status["status"]
        result = _rule_redact(text, custom)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(args.output, 0o700)
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
    parser.add_argument('--max-total', type=int, default=None)
    parser.add_argument('--max-chunks', type=int, default=64)
    try:
        main(parser.parse_args())
    except Exception as exc:
        # CLI boundary emits stable codes only; never print exception chains or
        # model/input content into logs.
        code = str(exc)
        allowed = {'EMPTY_TEXT', 'INPUT_TOO_LONG_REQUIRES_PARTITION', 'MODEL_OUTPUT_BLOCKED', 'MODEL_ITEMS_UNGROUNDED', 'AMBIGUOUS_ENTITY_OCCURRENCE',
                   'ENTITY_NOT_IN_SOURCE', 'OUTPUT_TOO_LARGE', 'LOCAL_MODEL_FAILED',
                   'MLX_RUNTIME_NOT_IMPORTABLE', 'ENTITY_SCHEMA', 'ENTITY_FILE_UNREADABLE',
                   'ENTITY_FILE_PERMISSION_MUST_BE_600', 'ENTITY_DIRECTORY_PERMISSION_MUST_BE_700',
                   'MODEL_OR_ADAPTER_NOT_FOUND', 'ADAPTER_CHECKSUM_MISSING', 'ADAPTER_CHECKSUM_MISMATCH',
                   'TOTAL_BUDGET_EXCEEDED', 'PARTITION_INPUT_TOO_LARGE', 'MAX_CHUNKS_EXCEEDED',
                   'INVALID_PARTITION_BUDGET', 'TOKENIZER_NOT_COUNTABLE',
                   'PARTITION_PROMPT_OVER_BUDGET', 'ENTITY_CROSSES_PARTITION_BOUNDARY',
                   'MODEL_OUTPUT_TRUNCATED',
                   'POLICY_UNSUPPORTED_SENSITIVE_TYPES', 'POLICY_UNSUPPORTED_PRESERVE_RULES',
                   'POLICY_UNSUPPORTED_BUSINESS_RULES', 'POLICY_SCHEMA'}
        safe = code if code in allowed else 'LOCAL_RUNTIME_FAILED'
        print(json.dumps({'status': 'LOCAL_REDACTION_FAILED', 'reason': safe}, ensure_ascii=False))
        raise SystemExit(2)
