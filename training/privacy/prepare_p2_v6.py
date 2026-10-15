"""Build immutable P2 train/dev projection from reviewed4 plus legal replay."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from common import messages


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(output: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    reviewed = root / "artifacts/privacy/data/reviewed4"
    replay_paths = [
        root / "artifacts/privacy/data/v6/mlx/train.jsonl",
        root / "artifacts/privacy/data/v3/mlx/train.jsonl",
        root / "artifacts/privacy/data/v2/mlx/train.jsonl",
    ]
    if output.exists():
        raise FileExistsError(output)
    reviewed_train = load_jsonl(reviewed / "train.jsonl")
    reviewed_dev = load_jsonl(reviewed / "dev.jsonl")
    # Stable 100-row slices per ancestor; no dev/test/holdout files are touched.
    replay: list[dict] = []
    replay_counts: dict[str, int] = {}
    for path in replay_paths:
        rows = load_jsonl(path)
        selected = rows[:100]
        replay.extend(selected)
        replay_counts[str(path.relative_to(root))] = len(selected)
    train_rows = [
        {"messages": messages(row)} for row in reviewed_train
    ] + replay
    dev_rows = [{"messages": messages(row)} for row in reviewed_dev]
    output.mkdir(parents=True)
    (output / "mlx").mkdir()
    for name, rows in (("train", train_rows), ("valid", dev_rows)):
        (output / "mlx" / f"{name}.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
    source_paths = [reviewed / "train.jsonl", reviewed / "dev.jsonl", *replay_paths]
    manifest = {
        "schema_version": 1,
        "recipe": "reviewed4-train400-plus-legal-ancestor-replay-100x3",
        "train_rows": len(train_rows),
        "dev_rows": len(dev_rows),
        "reviewed4_rows": {"train": len(reviewed_train), "dev": len(reviewed_dev)},
        "replay_rows": replay_counts,
        "test_loaded": False,
        "holdout_loaded": False,
        "source_sha256": {str(p.relative_to(root)): sha256(p) for p in source_paths},
        "mlx_sha256": {
            "train": sha256(output / "mlx/train.jsonl"),
            "valid": sha256(output / "mlx/valid.jsonl"),
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "BUILT", "train_rows": len(train_rows), "dev_rows": len(dev_rows)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    main(parser.parse_args().output)
