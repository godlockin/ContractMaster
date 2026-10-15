#!/usr/bin/env python3
"""Create and verify privacy-safe, model-agnostic experiment snapshots.

Snapshots contain metadata and SHA-256 inventories. They never embed data,
credentials, virtual environments, or model weights unless explicitly asked.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Iterable

SCHEMA_VERSION = "1.0"
DEFAULT_CODE = tuple([f"training/privacy/{p}" for p in ("*.py", "*.json", "requirements-lock.txt")] + [
    "contract-review-cn/SKILL.md", "contract-review-cn/**/*.md", "contract-review-cn/scripts/*.py",
    "scripts/verify.py", "requirements*.txt", "docs/**/*.md"])
FORBIDDEN_PARTS = {".git", ".venv", "venv", "__pycache__", "secrets", "private", "runs"}
WEIGHT_SUFFIXES = {".safetensors", ".bin", ".gguf", ".ggml", ".pt", ".pth", ".ckpt"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe(path: Path) -> bool:
    if any(part.lower() in FORBIDDEN_PARTS or part.lower().startswith(".env") or part.lower().startswith("credentials") for part in path.parts):
        return False
    return True


def inventory(paths: Iterable[Path], root: Path, include_weights: bool = False) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for candidate in paths:
        if not candidate.exists():
            continue
        files = [candidate] if candidate.is_file() else sorted(p for p in candidate.rglob("*") if p.is_file())
        for path in files:
            try:
                rel_raw = path.resolve().relative_to(root.resolve())
            except ValueError as exc:
                raise ValueError("EXTERNAL_PATH_REJECTED") from exc
            if not safe(rel_raw):
                continue
            if path.suffix.lower() in WEIGHT_SUFFIXES and not include_weights:
                continue
            try:
                rel = path.resolve().relative_to(root.resolve())
            except ValueError as exc:
                raise ValueError("EXTERNAL_PATH_REJECTED") from exc
            found.append({"path": str(rel), "absolute_path": str(path.resolve()), "bytes": path.stat().st_size,
                          "sha256": sha256(path), "kind": classify(path)})
    return found


def classify(path: Path) -> str:
    text = str(path).lower()
    if "canonical" in text:
        return "canonical_data"
    if any(x in text for x in ("mlx", "projection", "token", "tokenized")):
        return "training_projection"
    if path.suffix.lower() == ".jsonl":
        return "dataset_or_evaluation"
    return "runtime_or_config"


def data_status(paths: Iterable[Path]) -> dict[str, int]:
    result = {"rows": 0, "accepted": 0, "rejected": 0, "unknown": 0}
    for base in paths:
        files = [base] if base.is_file() else sorted(base.rglob("*.jsonl")) if base.exists() else []
        for file in files:
            if not safe(file):
                continue
            for line in file.open(encoding="utf-8"):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    result["unknown"] += 1
                    continue
                result["rows"] += 1
                status = str(row.get("status", row.get("decision", "unknown"))).lower()
                if status in {"reject", "rejected", "deny", "denied", "holdout_rejected"} or row.get("rejected") is True:
                    result["rejected"] += 1
                elif status in {"accept", "accepted", "approved", "ok"} and row.get("train_admission") is True and isinstance(row.get("registry_hash"), str):
                    result["accepted"] += 1
                else:
                    result["unknown"] += 1
    return result


def package_versions() -> dict[str, str]:
    names = {"mlx", "mlx-lm", "pypdf", "numpy", "tokenizers", "transformers", "PyYAML"}
    return {name: importlib.metadata.version(name) for name in sorted(names) if _has_dist(name)}


def _has_dist(name: str) -> bool:
    try:
        importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_adapter_chain(adapter: Path, model_manifest: Path) -> None:
    """Fail closed unless every parent adapter and base identity is evidenced."""
    model = load_json(model_manifest)
    if not isinstance(model, dict) or not model.get("revision") or not (model.get("repo") or model.get("files")):
        raise ValueError("MODEL_IDENTITY_INCOMPLETE")
    for item in model.get("files", []):
        target = model_manifest.parent / str(item["file"])
        if not target.is_file() or sha256(target) != item.get("sha256"):
            raise ValueError("MODEL_FILE_HASH_MISMATCH")
    seen: set[Path] = set()
    current: Path | None = adapter.resolve()
    while current:
        if current in seen:
            raise ValueError("ADAPTER_PARENT_CYCLE")
        seen.add(current)
        provenance_path = current.parent / "provenance.json"
        if not provenance_path.is_file():
            raise ValueError("ADAPTER_PROVENANCE_MISSING")
        provenance = load_json(provenance_path)
        if not isinstance(provenance, dict) or provenance.get("adapter_sha256") != sha256(current):
            raise ValueError("ADAPTER_HASH_PROVENANCE_MISMATCH")
        identity = provenance.get("model", {})
        if identity.get("revision") != model.get("revision") or (model.get("repo") and identity.get("repo") != model.get("repo")):
            raise ValueError("ADAPTER_BASE_IDENTITY_MISMATCH")
        config_path = current.parent / "adapter_config.json"
        config = load_json(config_path) if config_path.is_file() else {}
        parent = provenance.get("parent_adapter") or provenance.get("initial_adapter") or config.get("resume_adapter_file")
        parent_hash = provenance.get("initial_adapter_sha256") or config.get("initial_adapter_sha256")
        if not parent and parent_hash:
            for candidate in adapter.parent.parent.rglob("adapters.safetensors"):
                if candidate != current and safe(candidate) and sha256(candidate) == parent_hash:
                    parent = str(candidate); break
            if not parent:
                raise ValueError("ADAPTER_PARENT_NOT_FOUND")
        if parent and parent_hash:
            parent_path = Path(parent)
            if not parent_path.is_file() or sha256(parent_path) != parent_hash:
                raise ValueError("ADAPTER_PARENT_HASH_MISMATCH")
        current = Path(parent).resolve() if parent else None


def preflight(args: argparse.Namespace) -> None:
    validate_adapter_chain(args.adapter, args.model_manifest)
    print(json.dumps({"status": "PREFLIGHT_OK", "adapter": str(args.adapter)}))


def snapshot(args: argparse.Namespace) -> dict[str, object]:
    root = args.root.resolve()
    configs = [Path(p) for p in args.config]
    data_paths = [Path(p) for p in args.data]
    code_paths = []
    for pattern in DEFAULT_CODE:
        code_paths.extend(sorted(root.glob(pattern)))
    declared = configs + data_paths + code_paths + [Path(args.lock)]
    profile_path = Path(args.model_profile) if args.model_profile else (Path(args.model) / "verified-download.json" if args.model else None)
    model_profile = load_json(profile_path) if profile_path and profile_path.is_file() else {
        "path": str(Path(args.model).resolve()) if args.model else None,
        "framework": args.framework, "source": args.model_source, "revision": args.model_revision,
        "quantization": args.quantization, "tokenizer": args.tokenizer, "adapter_parent": args.adapter_parent,
        "adapter_reuse_policy": "data pipeline reusable; LoRA weights require matching base model and tokenizer"
    }
    manifest = {
        "schema_version": SCHEMA_VERSION, "snapshot_type": "local-reproducibility",
        "created_by": "training/privacy/reproducibility.py", "root": str(root),
        "environment": {"python": sys.version, "os": platform.platform(), "machine": platform.machine(),
                         "packages": package_versions(), "requirements_lock": next((x["sha256"] for x in inventory([Path(args.lock)], root) if x["path"] == str(Path(args.lock))), None)},
        "model_profile": {**model_profile, "quantization": args.quantization or model_profile.get("quantization", "4bit"), "tokenizer": args.tokenizer or model_profile.get("tokenizer", "tokenizer.json")},
        "model_profiles": [load_json(p / "verified-download.json") for p in (root / "artifacts/privacy/models/qwen3-1.7b-4bit", root / "artifacts/privacy/models/qwen3-4b-4bit") if (p / "verified-download.json").is_file()],
        "experiments": [{"config": str(p.resolve()), "config_sha256": sha256(p)} for p in configs if p.is_file()],
        "data": {"status_counts": data_status(data_paths), "paths": inventory(data_paths, root)},
        "runtime_code": inventory(code_paths, root),
        "files": inventory(declared + ([Path(args.model)] if args.model else []), root, args.include_weights),
        "rebuild": ["python3 -m venv .venv", "python3 -m pip install -r training/privacy/requirements-lock.txt (offline wheelhouse or network required; lock has no hashes)",
                     "python3 training/privacy/reproducibility.py restore-check --snapshot snapshot.json",
                     "select model profile and tokenizer; regenerate training projection from canonical data",
                     "train from base model; resume LoRA only when base revision/tokenizer match"],
        "privacy": {"contents_embedded": bool(data_paths), "weights_embedded": bool(args.include_weights),
                    "excluded": sorted(FORBIDDEN_PARTS), "local_path_inventory_only": True,
                    "rejected_data_training_policy": "retained and counted; must never enter training projection"},
    }
    unique = {}
    for item in manifest["files"]:
        unique.setdefault(item["path"], item)
    manifest["files"] = list(unique.values())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    payload = output / "payload"
    payload.mkdir()
    for item in manifest["files"]:
        source = Path(str(item["absolute_path"]))
        target = payload / str(item["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        item["snapshot_path"] = str(target.relative_to(output))
        item.pop("absolute_path", None)
    manifest["snapshot_policy"] = "copied payload; no symlinks; local only, not offsite backup"
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def restore_check(path: Path) -> None:
    manifest = load_json(path)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("INVALID_SNAPSHOT_SCHEMA")
    entries = manifest.get("files", [])
    if not entries or any("snapshot_path" not in item for item in entries):
        raise ValueError("SNAPSHOT_NOT_SELF_CONTAINED")
    checked = 0
    for item in entries:
        relative = Path(str(item["snapshot_path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("SNAPSHOT_PATH_UNSAFE")
        target = path.parent / relative
        if any((path.parent / parent).is_symlink() for parent in (relative, *relative.parents) if str(parent) != "."):
            raise ValueError("SNAPSHOT_PAYLOAD_SYMLINK")
        if not target.is_file() or sha256(target) != item["sha256"]:
            raise ValueError("SNAPSHOT_HASH_MISMATCH:" + str(item.get("path")))
        checked += 1
    print(json.dumps({"status": "RESTORE_CHECK_OK", "files_checked": checked}))

def restore(snapshot: Path, output: Path) -> None:
    """Restore only relative payload paths into a new directory."""
    manifest = load_json(snapshot)
    if not isinstance(manifest, dict): raise ValueError("INVALID_SNAPSHOT_SCHEMA")
    restore_check(snapshot)
    output = output.resolve(); output.mkdir(parents=True, exist_ok=False)
    for item in manifest["files"]:
        rel = Path(str(item["path"]))
        if rel.is_absolute() or ".." in rel.parts or not safe(rel): raise ValueError("SNAPSHOT_PATH_UNSAFE")
        target = output / rel; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snapshot.parent / item["snapshot_path"], target)
    print(json.dumps({"status":"RESTORE_OK", "output":str(output), "files":len(manifest["files"])}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("snapshot")
    make.add_argument("--root", type=Path, default=Path(".")); make.add_argument("--output", type=Path, required=True)
    make.add_argument("--lock", type=Path, default=Path("training/privacy/requirements-lock.txt"))
    make.add_argument("--config", action="append", default=[]); make.add_argument("--data", action="append", default=[])
    make.add_argument("--model"); make.add_argument("--model-profile"); make.add_argument("--framework", default="unknown")
    make.add_argument("--model-source"); make.add_argument("--model-revision"); make.add_argument("--quantization")
    make.add_argument("--tokenizer"); make.add_argument("--adapter-parent"); make.add_argument("--include-weights", "--include-models", action="store_true")
    check = sub.add_parser("restore-check"); check.add_argument("--snapshot", type=Path, required=True)
    restore_cmd = sub.add_parser("restore"); restore_cmd.add_argument("--snapshot", type=Path, required=True); restore_cmd.add_argument("--output", type=Path, required=True)
    pre = sub.add_parser("preflight", help="validate base model identity and complete adapter provenance chain")
    pre.add_argument("--adapter", type=Path, required=True); pre.add_argument("--model-manifest", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "snapshot":
        manifest = snapshot(args); print(json.dumps({"status": "SNAPSHOT_OK", "files": len(manifest["files"]), "output": str(args.output.resolve())}))
    elif args.command == "preflight":
        preflight(args)
    elif args.command == "restore":
        restore(args.snapshot, args.output)
    else:
        restore_check(args.snapshot)


if __name__ == "__main__":
    main()
