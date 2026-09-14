"""Pinned local QLoRA experiments. No remote code, telemetry, or test-set loading."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import types

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
from common import dump, rows, digest


def verify_model(path):
    manifest = json.loads((path / "verified-download.json").read_text())
    for item in manifest["files"]:
        checksum = hashlib.sha256()
        with (path / item["file"]).open("rb") as stream:
            while chunk := stream.read(1024*1024):
                checksum.update(chunk)
        if checksum.hexdigest() != item["sha256"]:
            raise ValueError("LOCAL_MODEL_CHANGED")
    return manifest


def main(config_path):
    import mlx.core as mx
    import numpy as np
    from mlx_lm import load
    from mlx_lm.lora import CONFIG_DEFAULTS, train_model
    from mlx_lm.tuner.datasets import ChatDataset
    from mlx_lm.tuner.callbacks import TrainingCallback

    config = json.loads(config_path.read_text())
    model_manifest = verify_model(Path(config["model"]))
    parent_adapter = config.get("resume_adapter_file")
    parent_checksum = None
    if parent_adapter:
        parent = Path(parent_adapter)
        prior = json.loads((parent.parent / "provenance.json").read_text())
        if prior["model"]["revision"] != model_manifest["revision"]:
            raise ValueError("RESUME_BASE_MODEL_MISMATCH")
        parent_checksum = hashlib.sha256(parent.read_bytes()).hexdigest()
    output = Path(config["adapter_path"])
    output.mkdir(parents=True, exist_ok=False)
    data_root = Path(config["data"])
    training, validation = rows(data_root / "train.jsonl"), rows(data_root / "valid.jsonl")
    if {digest(x) for x in training} & {digest(x) for x in validation}:
        raise ValueError("TRAIN_VALIDATION_OVERLAP")
    args = types.SimpleNamespace(**{**CONFIG_DEFAULTS, **config})
    np.random.seed(args.seed)
    mx.random.seed(args.seed)
    started = time.perf_counter()

    class LocalMetrics(TrainingCallback):
        def write(self, stage, info):
            record = {"stage": stage, **info, "elapsed_seconds": time.perf_counter()-started}
            with (output / "losses.jsonl").open("a") as stream:
                stream.write(json.dumps(record) + "\n")
            if mx.get_peak_memory() > 36e9:
                raise RuntimeError("MEMORY_BUDGET_EXCEEDED")
            if time.perf_counter()-started > 3600:
                raise RuntimeError("EXPERIMENT_TIME_BUDGET_EXCEEDED")
        def on_train_loss_report(self, info):
            self.write("train", info)
        def on_val_loss_report(self, info):
            self.write("validation", info)

    model, tokenizer = load(args.model, tokenizer_config={"trust_remote_code": False})

    class NonThinkingTokenizer:
        def __getattr__(self, name):
            return getattr(tokenizer, name)
        def apply_chat_template(self, messages, **kwargs):
            return tokenizer.apply_chat_template(messages, **{**kwargs, "enable_thinking": False})

    wrapped = NonThinkingTokenizer()
    train_set = ChatDataset(training, wrapped, mask_prompt=True)
    valid_set = ChatDataset(validation, wrapped, mask_prompt=True)
    lengths = [len(ds.process(r)[0]) for ds in (train_set, valid_set) for r in ds._data]
    if max(lengths) > args.max_seq_length:
        raise ValueError("TRAINING_TRUNCATION_FORBIDDEN")
    dump(output / "provenance.json", {"model": model_manifest, "train_digest": digest(training),
         "validation_digest": digest(validation), "max_tokens": max(lengths), "thinking": False,
         "mask_prompt": True, "test_loaded": False, "config": config,
         "initial_adapter_sha256": parent_checksum,
         "resume_semantics": "weights-only warm start, new optimizer/schedule" if parent_adapter else "base model"})
    try:
        train_model(args, model, train_set, valid_set, LocalMetrics())
    except Exception:
        dump(output / "status.json", {"status": "FAILED", "elapsed_seconds": time.perf_counter()-started})
        raise
    dump(output / "status.json", {"status": "TRAINED_NOT_YET_QUALIFIED", "elapsed_seconds": time.perf_counter()-started,
                                 "peak_memory_gb": mx.get_peak_memory()/1e9})
    print(json.dumps({"status": "TRAINED_NOT_YET_QUALIFIED", "seconds": time.perf_counter()-started,
                      "peak_memory_gb": mx.get_peak_memory()/1e9}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    main(parser.parse_args().config)
