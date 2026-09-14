"""Fetch a bounded, pinned Chinese sample with explicit train/validation provenance."""
import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path
from common import dump, digest

REPO = "ai4privacy/pii-masking-openpii-1.5m"
REVISION = "a785eb528e28be2693c3718a27e066970de5dadb"
LABELS = {"GIVENNAME": "PERSON", "SURNAME": "PERSON", "LASTNAME": "PERSON", "FULLNAME": "PERSON",
          "TELEPHONENUM": "PHONE", "EMAIL": "EMAIL", "IDCARDNUM": "ID", "PASSPORTNUM": "ID",
          "SOCIALNUM": "ID", "DRIVERLICENSENUM": "ID", "STREET": "ADDRESS", "CITY": "ADDRESS",
          "BUILDINGNUM": "ADDRESS", "ZIPCODE": "ADDRESS", "STATE": "ADDRESS", "COUNTRY": "ADDRESS",
          "IBAN": "ACCOUNT", "ACCOUNTNUM": "ACCOUNT", "CREDITCARDNUMBER": "ACCOUNT"}


def request(url):
    with urllib.request.urlopen(url, timeout=90) as response:
        return response.read().decode("utf-8")


def main(output, split="validation", limit=100):
    if split not in {"train", "validation"} or limit <= 0:
        raise ValueError("INVALID_PUBLIC_DATA_REQUEST")
    output.mkdir(parents=True, exist_ok=False)
    api = f"https://huggingface.co/api/datasets/{REPO}"
    if json.loads(request(api))["sha"] != REVISION:
        raise ValueError("DATASET_REVISION_CHANGED_REVIEW_LICENSE")
    card = request(f"https://huggingface.co/datasets/{REPO}/raw/{REVISION}/README.md")
    (output / "SOURCE-README.md").write_text(card, encoding="utf-8")
    selected_rows = []
    scanned = 0
    # The row/filter service may be unavailable. Stream a bounded prefix of the pinned original.
    url = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/data/{split}.jsonl"
    with urllib.request.urlopen(url, timeout=90) as response:
        for _ in range(limit * 60):
            line = response.readline(1_000_000)
            if not line:
                break
            scanned += 1
            row = json.loads(line)
            if row["language"] == "zh":
                selected_rows.append({"row": row})
            if len(selected_rows) >= limit:
                break
    raw = {"rows": selected_rows, "source_rows_scanned": scanned}
    selected, rejected, labels = [], 0, set()
    for entry in raw["rows"]:
        row = entry["row"]
        if row["language"] != "zh":
            raise ValueError("NON_CHINESE_ROW")
        text = row["source_text"]
        entities = []
        gold_spans = []
        for item in row["privacy_mask"]:
            labels.add(item["label"])
            if text[item["start"]:item["end"]] != item["value"]:
                rejected += 1
                break
            if item["label"] in LABELS:
                entity = {"text": item["value"], "type": LABELS[item["label"]]}
                gold_spans.append([item["start"], item["end"], LABELS[item["label"]]])
                if entity not in entities:
                    entities.append(entity)
        else:
            if entities:
                selected.append({"id": f"openpii-{row['uid']}", "family": "public-zh-" + split,
                                 "text": text, "entities": entities, "source": REPO,
                                 "gold_spans": gold_spans,
                                 "evaluated_types": sorted(set(LABELS.values()))})
    if not selected or json.loads(request(api))["sha"] != REVISION:
        raise ValueError("PUBLIC_DATA_NOT_VERIFIED")
    dump(output / "raw.json", raw)
    (output / ("train.jsonl" if split == "train" else "test.jsonl")).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in selected), encoding="utf-8")
    dump(output / "manifest.json", {"repo": REPO, "revision_observed_before_and_after": REVISION,
         "license": "CC-BY-4.0 stated in dataset card; no standalone license file", "attribution": "Ai4Privacy / Ai Suisse SA",
         "split": split, "purpose": "training" if split == "train" else "external evaluation only; original vendor labels, not independently verified",
         "rows": len(selected), "rejected_bad_offsets": rejected, "labels": sorted(labels),
         "row_digest": digest(selected), "raw_digest": digest(raw), "label_mapping": LABELS})
    print(json.dumps({"status": "PUBLIC_DATA_PREPARED", "split": split, "rows": len(selected), "rejected": rejected, "labels": sorted(labels)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=["train", "validation"], default="validation")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    main(args.output, args.split, args.limit)
