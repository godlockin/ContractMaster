"""Offline capability and integrity probe for the optional local redaction model.

The probe never reads contract text.  It only checks model metadata, adapter
provenance and local runtime availability, then emits machine readable status.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


STATES = {"AVAILABLE", "NOT_INSTALLED", "DEPENDENCY_MISSING", "INTEGRITY_FAILED",
          "ADAPTER_MISMATCH", "SELF_TEST_FAILED"}


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def check_model(model: Path, adapter: Path, self_test: bool = False) -> dict:
    """Return a safe status object; exceptions are converted to stable codes."""
    result = {"status": "NOT_INSTALLED", "backend": "local-model", "model": str(model),
              "adapter": str(adapter), "reason": None}
    manifest_path = model / "verified-download.json"
    if not model.is_dir() or not adapter.is_dir() or not manifest_path.is_file():
        result["reason"] = "MODEL_OR_ADAPTER_NOT_FOUND"
        return result
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        records = manifest.get("files")
        if not isinstance(records, list) or not manifest.get("revision"):
            raise ValueError("MANIFEST_SCHEMA")
        for record in records:
            path = model / str(record["file"])
            if not path.is_file() or path.stat().st_size != int(record["bytes"]):
                result.update(status="INTEGRITY_FAILED", reason="MODEL_FILE_SIZE_MISMATCH")
                return result
            if _sha256(path) != record["sha256"]:
                result.update(status="INTEGRITY_FAILED", reason="MODEL_FILE_CHECKSUM_MISMATCH")
                return result
        provenance_path = adapter / "provenance.json"
        adapter_file = adapter / "adapters.safetensors"
        config_file = adapter / "adapter_config.json"
        if not all(path.is_file() for path in (provenance_path, adapter_file, config_file)):
            result.update(status="INTEGRITY_FAILED", reason="ADAPTER_FILES_MISSING")
            return result
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        model_info = provenance.get("model", {})
        if model_info.get("revision") != manifest.get("revision"):
            result.update(status="ADAPTER_MISMATCH", reason="ADAPTER_MODEL_REVISION_MISMATCH")
            return result
        if "adapter_sha256" in provenance and _sha256(adapter_file) != provenance["adapter_sha256"]:
            result.update(status="INTEGRITY_FAILED", reason="ADAPTER_CHECKSUM_MISMATCH")
            return result
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        result.update(status="INTEGRITY_FAILED", reason="MODEL_METADATA_INVALID")
        return result
    if not _has_module("mlx_lm") or not _has_module("mlx.core"):
        result.update(status="DEPENDENCY_MISSING", reason="MLX_RUNTIME_NOT_IMPORTABLE")
        return result
    if self_test:
        try:
            from mlx_lm import generate, load
            model_obj, tokenizer = load(str(model), adapter_path=str(adapter),
                                        tokenizer_config={"trust_remote_code": False})
            prompt = tokenizer.apply_chat_template(
                [{"role": "user", "content": "测试：联系人张三。仅输出JSON数组。"}],
                tokenize=False, add_generation_prompt=True, enable_thinking=False)
            output = generate(model_obj, tokenizer, prompt=prompt, max_tokens=64, verbose=False)
            json.loads(output.strip())
        except Exception:  # never expose model/runtime details or input text
            result.update(status="SELF_TEST_FAILED", reason="LOCAL_MODEL_SELF_TEST_FAILED")
            return result
    result["status"] = "AVAILABLE"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe local privacy model without contract input")
    parser.add_argument("--model", type=Path, default=Path("artifacts/privacy/models/qwen3-1.7b-4bit"))
    parser.add_argument("--adapter", type=Path, default=Path("artifacts/privacy/adapters/v4-step160"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    # Resolve bundled defaults when invoked from a user's case directory.
    if not args.model.is_absolute() and not args.model.exists():
        bundled = Path(__file__).resolve().parents[2] / args.model
        if bundled.exists():
            args.model = bundled
    if not args.adapter.is_absolute() and not args.adapter.exists():
        bundled = Path(__file__).resolve().parents[2] / args.adapter
        if bundled.exists():
            args.adapter = bundled
    print(json.dumps(check_model(args.model, args.adapter, args.self_test), ensure_ascii=False))


if __name__ == "__main__":
    main()
