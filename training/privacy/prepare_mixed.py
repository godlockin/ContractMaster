"""Mix supplier TRAIN split with original data, keeping all eval UIDs/text out."""
import argparse
import json
import random
from pathlib import Path
from common import rows, messages, spans, digest, dump


def main(output):
    source = Path("artifacts/privacy/data/v3")
    original = rows(source / "train.jsonl")
    public = rows(Path("artifacts/privacy/data/openpii-train/train.jsonl"))
    external = rows(Path("artifacts/privacy/data/openpii-zh-v4/test.jsonl"))
    dev, test = rows(source / "dev.jsonl"), rows(source / "test.jsonl")
    forbidden_ids = {r["id"] for r in [*dev, *test, *external]}
    forbidden_text = {digest(r["text"]) for r in [*dev, *test, *external]}
    selected, rejected = [], []
    seen = set()
    for r in public:
        key = digest(r["text"])
        if r["id"] in forbidden_ids or key in forbidden_text or key in seen:
            rejected.append(r["id"])
            continue
        spans(r["text"], r["entities"])
        seen.add(key)
        selected.append(r)
    output.mkdir(parents=True, exist_ok=False)
    # Oversample the public domain; repeated UIDs stay in training only.
    address_examples = [r for r in original if any(e["type"] == "ADDRESS" for e in r["entities"])]
    combined = [*original, *selected, *selected, *selected, *selected,
                *address_examples, *address_examples, *address_examples]
    random.Random(20260916).shuffle(combined)
    (output / "mlx").mkdir()
    for name, records in (("train", combined), ("valid", dev)):
        (output / "mlx" / (name + ".jsonl")).write_text("".join(json.dumps({"messages": messages(r)}, ensure_ascii=False)+"\n" for r in records), encoding="utf-8")
    dump(output / "manifest.json", {"recipe": "original-expanded-v2-plus-openpii-train-x4-address-x4",
         "original_rows": len(original), "public_unique_rows": len(selected), "public_rejected_overlap": rejected,
         "training_rows": len(combined), "training_digest": digest(combined), "validation_digest": digest(dev),
         "address_extra_rows": 3 * len(address_examples),
         "protected_eval_ids": sorted(forbidden_ids), "license_source": "../openpii-train/manifest.json",
         "note": "supplier-generated labels, not independently verified; mixed task scopes are explicit system policy"})
    print(json.dumps({"status": "MIXED_DATA_PREPARED", "training_rows": len(combined), "public_unique": len(selected), "rejected": len(rejected)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    main(parser.parse_args().output)
