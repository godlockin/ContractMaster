"""Independent repair-v6 data quality audit.

This module deliberately does not import any v6 builder.  It checks rendered
JSONL and MLX projections as an external consumer would see them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Iterable
from common import TYPES, messages

REQUIRED = {"id", "pair_id", "minimal_pair_id", "variant", "pair_role", "text",
            "entities", "gold_spans", "scoring_scope", "preserve_literals",
            "source_kind", "train_allowed", "template_id"}
SPLITS = ("train", "dev", "holdout")


def inverse(value: str) -> str:
    """Canonicalize lossless presentation attacks, without changing meaning."""
    value = value.replace("／", "/").replace("．", ".")
    value = value.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    value = re.sub(r"(?i)\\u([0-9a-f]{4})", lambda m: chr(int(m.group(1), 16)), value)
    value = re.sub(r"(?<=\d)[ \u3000](?=\d)", "", value)
    return unicodedata.normalize("NFKC", value)


def inverse_entity(value: str, kind: str) -> str:
    value = inverse(value)
    if kind == "PERSON":
        value = re.sub(r"(?<=[\u3400-\u9fff])[ /／]+(?=[\u3400-\u9fff])", "", value)
    return value


def _entity_key(item: dict) -> tuple[str, str]:
    return (inverse_entity(item["text"], item["type"]), item["type"])


def _span_key(item: dict) -> tuple[int, int, str, str]:
    return (item["start"], item["end"], item["text"], item["type"])


def audit_dataset(root: Path, spec: Path | None = None) -> list[str]:
    errors: list[str] = []
    split_rows: dict[str, list[dict]] = {}
    for split in SPLITS:
        path = root / f"{split}.jsonl"
        if not path.exists():
            errors.append(f"{split}:missing_file")
            continue
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        split_rows[split] = rows
        for index, row in enumerate(rows):
            where = f"{split}[{index}]"
            errors.extend(_audit_row(where, row, split))
    errors.extend(_audit_pairs(split_rows))
    errors.extend(_audit_cross_split(split_rows))
    errors.extend(_audit_mlx(root, split_rows))
    if spec is not None:
        errors.extend(audit_spec(spec))
    return errors


def audit_spec(path: Path) -> list[str]:
    """Audit template metadata and rendered prose constraints independently."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    templates = payload.get("templates", [])
    ids: dict[str, str] = {}
    hashes: dict[str, str] = {}
    forbidden = re.compile(r"仅[^。；，,]{0,30}(?:属于|是)敏感|不代表敏感|标签不代表|字节(?:长度|阈值)")
    for index, template in enumerate(templates):
        where = f"spec.templates[{index}]"
        tid, split = template.get("template_id", template.get("id")), template.get("split")
        prose_values = ([template.get("text_template", "")] if "text_template" in template else
                        [template.get("positive", ""), template.get("negative", "")])
        if not isinstance(tid, str) or not isinstance(split, str) or not all(isinstance(prose, str) and prose for prose in prose_values):
            errors.append(f"{where}:schema")
        if tid in ids and ids[tid] != split: errors.append(f"{where}:template_id_reused")
        ids[tid] = split
        for prose in prose_values:
            digest = json.dumps(prose, ensure_ascii=False)
            if digest in hashes and hashes[digest] != split: errors.append(f"{where}:template_prose_reused")
            hashes[digest] = split
            if forbidden.search(prose): errors.append(f"{where}:meta_instruction_or_fake_boundary")
    if payload.get("template_count") != len(templates): errors.append("spec:template_count")
    return errors


def _audit_row(where: str, row: dict, split: str) -> list[str]:
    out: list[str] = []
    missing = REQUIRED - set(row)
    if missing:
        out.append(f"{where}:schema_missing:{','.join(sorted(missing))}")
    expected_train_allowed = split != "holdout"
    if row.get("source_kind") != "synthetic" or row.get("train_allowed") is not expected_train_allowed:
        out.append(f"{where}:source_policy")
    if row.get("variant") not in {"clean", "attack"} or row.get("pair_role") not in {"positive", "negative"}:
        out.append(f"{where}:variant_role")
    if re.search(r"(?:样本|sample)(?:train|dev|holdout)[-_]", str(row.get("text", "")), re.I):
        out.append(f"{where}:split_prefix_in_text")
    text = row.get("text")
    if not isinstance(text, str) or not text:
        return out + [f"{where}:text"]
    entities = row.get("entities", [])
    spans = row.get("gold_spans", [])
    if not isinstance(entities, list) or not isinstance(spans, list):
        return out + [f"{where}:entity_schema"]
    entity_keys = []
    for item in entities:
        if not isinstance(item, dict) or set(item) != {"text", "type"} or not item.get("text") or not isinstance(item.get("type"), str):
            out.append(f"{where}:entity_schema")
        else:
            if item["type"] not in TYPES:
                out.append(f"{where}:unknown_entity_type:{item['type']}")
            entity_keys.append(_entity_key(item))
            if item["text"] not in text:
                out.append(f"{where}:entity_not_in_text:{item['text']}")
    if len(entity_keys) != len(set(entity_keys)):
        out.append(f"{where}:duplicate_entity")
    expected = {(m.start(), m.end(), item["type"], item["text"])
               for item in entities if isinstance(item, dict) and "text" in item and "type" in item
               for m in re.finditer(re.escape(item["text"]), text)}
    actual = set()
    for span in spans:
        if not isinstance(span, dict) or not {"start", "end", "text", "type"} <= set(span):
            out.append(f"{where}:gold_schema"); continue
        a, b = span["start"], span["end"]
        if not isinstance(a, int) or not isinstance(b, int) or not (0 <= a < b <= len(text)):
            out.append(f"{where}:gold_bounds"); continue
        if text[a:b] != span["text"]:
            out.append(f"{where}:gold_slice")
        actual.add((a, b, span["type"], span["text"]))
    if actual != expected:
        out.append(f"{where}:gold_mismatch")
    ordered = sorted((s["start"], s["end"]) for s in spans if isinstance(s, dict) and isinstance(s.get("start"), int))
    if any(b > c for (_, b), (c, _) in zip(ordered, ordered[1:])):
        out.append(f"{where}:gold_overlap")
    for literal in row.get("preserve_literals", []):
        if not isinstance(literal, str) or literal not in text:
            out.append(f"{where}:preserve_missing")
            continue
        start = text.find(literal); end = start + len(literal)
        if any(start < s["end"] and end > s["start"] for s in spans if isinstance(s, dict) and isinstance(s.get("start"), int)):
            out.append(f"{where}:preserve_gold_overlap")
    if row.get("pair_role") == "negative" and not entities and row.get("preserve_text") != text:
        out.append(f"{where}:negative_preserve_text")
    return out


def _audit_pairs(split_rows: dict[str, list[dict]]) -> list[str]:
    out: list[str] = []
    for split, rows in split_rows.items():
        groups: dict[str, list[dict]] = defaultdict(list)
        for row in rows: groups[row.get("pair_id", "")].append(row)
        for pair, items in groups.items():
            if len(items) != 2 or {r.get("variant") for r in items} != {"clean", "attack"}:
                out.append(f"{split}:{pair}:pair_shape")
                continue
            clean, attack = sorted(items, key=lambda r: r["variant"])
            if clean["text"] == attack["text"]:
                out.append(f"{split}:{pair}:attack_not_changed")
            if {(_entity_key(e)) for e in clean["entities"]} != {(_entity_key(e)) for e in attack["entities"]}:
                out.append(f"{split}:{pair}:attack_entity_not_lossless")
        minis: dict[str, set[str]] = defaultdict(set)
        for row in rows: minis[row.get("minimal_pair_id", "")].add(row.get("pair_role", ""))
        for mini, roles in minis.items():
            if roles != {"positive", "negative"}:
                out.append(f"{split}:{mini}:positive_negative_missing")
            else:
                by_role = {role: [r for r in rows if r.get("minimal_pair_id") == mini and r.get("pair_role") == role] for role in roles}
                for variant in ("clean", "attack"):
                    positive = next((r for r in by_role["positive"] if r.get("variant") == variant), None)
                    negative = next((r for r in by_role["negative"] if r.get("variant") == variant), None)
                    if positive is None or negative is None:
                        out.append(f"{split}:{mini}:{variant}:role_pair_missing")
                        continue
                    common = {_entity_key(e) for e in positive.get("entities", [])} & {_entity_key(e) for e in negative.get("entities", [])}
                    # Only positive entities that literally remain in negative text
                    # are required to remain gold; pure negatives are legal.
                    invariant = set(positive.get("invariant_components", []))
                    expected = {_entity_key(e) for e in positive.get("entities", [])
                                if e.get("type") in invariant and e.get("text") in negative.get("text", "")}
                    actual = {_entity_key(e) for e in negative.get("entities", [])}
                    if not expected <= actual:
                        out.append(f"{split}:{mini}:{variant}:retained_entity_missing_gold")
                common_clean = {_entity_key(e) for e in next((r for r in by_role["positive"] if r.get("variant") == "clean"), {}).get("entities", [])} & {_entity_key(e) for e in next((r for r in by_role["negative"] if r.get("variant") == "clean"), {}).get("entities", [])}
                common_attack = {_entity_key(e) for e in next((r for r in by_role["positive"] if r.get("variant") == "attack"), {}).get("entities", [])} & {_entity_key(e) for e in next((r for r in by_role["negative"] if r.get("variant") == "attack"), {}).get("entities", [])}
                if common_clean != common_attack:
                    out.append(f"{split}:{mini}:common_entity_not_retained")
    return out


def _audit_cross_split(split_rows: dict[str, list[dict]], ancestor_rows: list[dict] | None = None) -> list[str]:
    out: list[str] = []
    seen_templates: dict[str, str] = {}
    seen_text: dict[str, str] = {}
    seen_entities: dict[tuple[str, str], str] = {}
    all_entities: list[tuple[str, str, str]] = []
    for split, rows in split_rows.items():
        for row in rows:
            tid = row.get("template_id")
            if tid in seen_templates and seen_templates[tid] != split: out.append(f"template_reused:{tid}")
            seen_templates[tid] = split
            canon_text = inverse(row.get("text", ""))
            if canon_text in seen_text and seen_text[canon_text] != split: out.append(f"text_leak:{split}:{seen_text[canon_text]}")
            seen_text[canon_text] = split
            for entity in row.get("entities", []):
                key = _entity_key(entity)
                if key in seen_entities and seen_entities[key] != split: out.append(f"ancestor_entity_leak:{key[1]}:{key[0]}")
                seen_entities[key] = split
                all_entities.append((key[0], key[1], split))
    for value, kind, split in all_entities:
        for other, other_kind, other_split in all_entities:
            if split != other_split and kind == other_kind and value != other and min(len(value), len(other)) >= 3 and (value in other or other in value):
                out.append(f"ancestor_entity_leak:{kind}:{value}:{other}")
    if ancestor_rows is not None:
        ancestor_entities = [_entity_key(e) for row in ancestor_rows for e in row.get("entities", []) if isinstance(e, dict)]
        for split, rows in split_rows.items():
            for row in rows:
                for entity in row.get("entities", []):
                    if _entity_key(entity) in ancestor_entities:
                        out.append(f"ancestor_training_entity_leak:{split}:{_entity_key(entity)[1]}:{_entity_key(entity)[0]}")
    return out


def _audit_mlx(root: Path, split_rows: dict[str, list[dict]]) -> list[str]:
    out: list[str] = []
    for split, filename in (("train", "train.jsonl"), ("dev", "valid.jsonl")):
        path = root / "mlx" / filename
        if not path.exists(): out.append(f"mlx:{split}:missing_file"); continue
        projected = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        expected = [{"messages": messages(r)} for r in split_rows.get(split, [])]
        if len(projected) != len(expected): out.append(f"mlx:{split}:row_count")
        for index, (got, want) in enumerate(zip(projected, expected)):
            if got.get("messages") != want["messages"]: out.append(f"mlx:{split}[{index}]:content_mismatch")

    if (root / "mlx").exists() and any(p.name.lower().startswith(("test", "holdout")) for p in (root / "mlx").glob("*.jsonl")): out.append("mlx:holdout_or_test_present")
    return out


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--ancestor", type=Path, action="append", help="prior training JSONL or dataset directory; repeatable")
    args = parser.parse_args(argv)
    ancestor_rows = None
    ancestor_digest = None
    if args.ancestor:
        files = [f for target in args.ancestor for f in (sorted(target.glob("*.jsonl")) if target.is_dir() else [target])]
        ancestor_rows = []
        for path in files:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip(): continue
                item = json.loads(line)
                if isinstance(item.get("entities"), list): ancestor_rows.append(item)
                elif isinstance(item.get("messages"), list):
                    text = next((m.get("content") for m in item["messages"] if m.get("role") == "user"), None)
                    answer = next((m.get("content") for m in item["messages"] if m.get("role") == "assistant"), None)
                    try: entities = json.loads(answer) if isinstance(answer, str) else None
                    except json.JSONDecodeError: entities = None
                    if not isinstance(text, str) or not isinstance(entities, list): raise ValueError(f"ANCESTOR_FORMAT:{path}")
                    ancestor_rows.append({"text": text, "entities": entities})
                else: raise ValueError(f"ANCESTOR_FORMAT:{path}")
        if not ancestor_rows: raise ValueError("ANCESTOR_EMPTY")
        ancestor_digest = hashlib.sha256(b"".join(path.read_bytes() for path in files)).hexdigest()
    errors = audit_dataset(args.dataset, args.spec)
    if ancestor_rows is not None:
        errors.extend(_audit_cross_split({split: [json.loads(line) for line in (args.dataset / f"{split}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()] for split in SPLITS if (args.dataset / f"{split}.jsonl").exists()}, ancestor_rows))
    print(json.dumps({"ok": not errors, "errors": errors, "error_count": len(errors), "ancestor_files_sha256": ancestor_digest}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
