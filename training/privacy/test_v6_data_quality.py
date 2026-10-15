"""Tests for the independent v6 data auditor (no builder assertions involved)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from validate_v6_data_quality import audit_dataset, inverse
from common import messages


def _row(pair: str, mini: str, role: str, variant: str, name: str, secret: str | None) -> dict:
    text = f"联系人{name}签署服务协议；"
    entities = [{"text": name, "type": "PERSON"}]
    if secret:
        text += f"内部底价为{secret}万元。"
        entities.append({"text": f"{secret}万元", "type": "SECRET"})
    else:
        text += "公开报价为300万元。"
    if variant == "attack":
        text = text.replace("120", "１２０")
        text = text.replace("。", "．")
        entities = [{**entity, "text": entity["text"].replace("120", "１２０")} for entity in entities]
    spans = []
    for entity in entities:
        start = text.find(entity["text"])
        spans.append({"start": start, "end": start + len(entity["text"]), "text": entity["text"], "type": entity["type"]})
    return {"id": f"RV6-{pair}-{variant}", "pair_id": pair, "minimal_pair_id": mini,
            "variant": variant, "pair_role": role, "attack_type": "semantic",
            "industry": "procurement", "template_id": f"t{name[-1]}", "text": text,
            "entities": entities, "gold_spans": spans, "scoring_scope": [0, len(text)],
            "preserve_literals": [],
            "source_kind": "synthetic", "train_allowed": True,
            "provenance": {"generator": "fixture"},
            "preserve_text": text if role == "negative" and not entities[1:] else None}


def _fixture(tmp_path: Path) -> Path:
    rows_by_split = {}
    for split, suffix in (("train", "A"), ("dev", "B"), ("holdout", "C")):
        rows = []
        # A positive and negative pair share PERSON; attack changes formatting.
        for role, secret in (("positive", {"A": "120", "B": "121", "C": "122"}[suffix]), ("negative", None)):
            pair = f"p{suffix}{role[0]}"
            for variant in ("clean", "attack"):
                rows.append(_row(pair, f"m{suffix}", role, variant, f"姓名{suffix}", secret))
        for row in rows:
            row["train_allowed"] = split != "holdout"
        rows_by_split[split] = rows
        (tmp_path / f"{split}.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    (tmp_path / "mlx").mkdir()
    for split, filename in (("train", "train.jsonl"), ("dev", "valid.jsonl")):
        projected = [{"messages": messages(r)} for r in rows_by_split[split]]
        (tmp_path / "mlx" / filename).write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in projected) + "\n", encoding="utf-8")
    return tmp_path


class V6DataQualityTests(unittest.TestCase):
    def test_inverse_preserves_entities(self) -> None:
        self.assertEqual(inverse("K-\\u0037\\u0037"), "K-77")
        self.assertEqual(inverse("6222 8800 1234"), "622288001234")
        self.assertEqual(inverse("１２０万元"), "120万元")

    def test_valid_fixture_passes(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(audit_dataset(_fixture(Path(directory))), [])

    def test_auditor_rejects_bad_gold_slice(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = _fixture(Path(directory)); path = root / "train.jsonl"
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            rows[0]["gold_spans"][0]["text"] = "错误"
            path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
            self.assertTrue(any("gold_slice" in error or "gold_mismatch" in error for error in audit_dataset(root)))

    def test_auditor_rejects_mlx_drift(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = _fixture(Path(directory)); path = root / "mlx" / "train.jsonl"
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            rows[0]["messages"][1]["content"] = "漂移"
            path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
            self.assertTrue(any("mlx:train[0]" in error for error in audit_dataset(root)))
