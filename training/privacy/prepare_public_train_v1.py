"""Prepare a deduplicated training-only public corpus.

Reads only the pinned OpenPII *train* cache and the original fictional edge
corpus. Validation, test, blind, and user-contract paths are rejected.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import digest, rows


def prepare(source: Path, edge: Path, output: Path, limit: int = 2000) -> None:
    if source.name != "train.jsonl" or any(part.lower() in {"test", "validation", "blind"} for part in source.parts):
        raise ValueError("EVAL_SOURCE_FORBIDDEN")
    upstream_manifest_path = source.parent / "manifest.json"
    upstream = json.loads(upstream_manifest_path.read_text(encoding="utf-8"))
    if upstream.get("repo") != "ai4privacy/pii-masking-openpii-1.5m" or upstream.get("split") != "train":
        raise ValueError("UPSTREAM_MANIFEST_MISMATCH")
    source_rows = rows(source)
    edge_rows = rows(edge)
    selected = []
    seen = set()
    for row in source_rows + edge_rows:
        key = row.get("text")
        if not isinstance(key, str) or not key or key in seen:
            continue
        seen.add(key)
        selected.append(row)
        if len(selected) >= limit:
            break
    if not selected:
        raise ValueError("EMPTY_TRAINING_CORPUS")
    output.mkdir(parents=True, exist_ok=False)
    (output / "train.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected), encoding="utf-8")
    edge_manifest = json.loads((edge.parent / "manifest.json").read_text(encoding="utf-8"))
    manifest = {"dataset": "public-train-v2", "sources": [{"path": str(source), "repo": upstream["repo"], "revision": upstream["revision_observed_before_and_after"], "url": "https://huggingface.co/datasets/ai4privacy/pii-masking-openpii-1.5m", "license": upstream["license"], "attribution": upstream["attribution"], "split": "train", "source_row_digest": upstream["row_digest"]}, {"path": str(edge), "source": "original-fictional-project-v2", "url": "local project artifact", "license": "CC0-1.0", "attribution": "this project", "split": "train", "source_row_digest": edge_manifest["row_digest"]}], "source_policy": "OpenPII pinned train cache plus original fictional CC0 corpus; no validation/test/blind rows", "license": ["CC-BY-4.0 for OpenPII source", "CC0-1.0 for fictional source"], "rows": len(selected), "unique_texts": len(seen), "row_digest": digest(selected), "limit": limit}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "SOURCE-README.md").write_text("# Public train v1\n\nTraining-only deduplicated subset. OpenPII attribution: Ai4Privacy / Ai Suisse SA, CC BY 4.0, pinned source manifest in the upstream cache. Fictional contract edge cases are authored by this project under CC0-1.0. No validation, test, blind, or user contract data is included.\n", encoding="utf-8")
    print(json.dumps({"status": "PUBLIC_TRAIN_PREPARED", "rows": len(selected), "digest": manifest["row_digest"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("artifacts/privacy/data/openpii-train-v4/train.jsonl"))
    parser.add_argument("--edge", type=Path, default=Path("artifacts/privacy/data/contract-edge-v2/train.jsonl"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=2000)
    args = parser.parse_args()
    prepare(args.source, args.edge, args.output, args.limit)
