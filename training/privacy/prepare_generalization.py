"""Generate fictitious contract-like generalization cases.

This module is deliberately self-contained: it never reads existing datasets or
user documents.  Train/dev use disjoint wording families and disjoint literal
inventories.  Public quantities, legal names and commercial semantics remain
visible; only privacy-sensitive literals are gold-labelled.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from common import digest, messages, spans

KINDS = ("PERSON", "ORG", "PROJECT", "PHONE", "EMAIL", "ID", "ACCOUNT", "CREDIT", "ADDRESS", "SECRET")

FAMILIES = {
    "train": [
        ("money", "服务费为{amount}万元，按{period}支付，共计{total}万元，含税。", ()),
        ("ratio", "履约保证金按合同总价的{ratio}计取；逾期违约金上限为{cap}。", ()),
        ("term", "本协议期限为{term}，每月结算一次，每年复核一次。", ()),
        ("negative", "除非法律另有规定，甲方不得向{person}之外的人员披露{project}。", ("person", "project")),
        ("legal", "双方依照《中华人民共和国民法典》及《中华人民共和国个人信息保护法》履行。", ()),
        ("person_alias", "授权代表姓名：{person}（别名：{alias}），负责项目交接。", ("person", "alias")),
        ("org_project", "{org}负责内部项目“{project}”；项目资料保存至验收后两年。", ("org", "project")),
        ("contact", "通知发送至{email}，电话{phone}；送达地址为{address}。", ("email", "phone", "address")),
        ("mixed_ids", "收款账户{account}对应证件号{id}，社会信用代码{credit}，仅作核验。", ("account", "id", "credit")),
        ("ocr_space", "OCR摘录：收款 账 户 {account_spaced}；证 件 编 号 {id_spaced}。", ("account_spaced", "id_spaced")),
        ("secret", "内部最低成交价为{secret}，公开报价仍为{amount}万元；保密期限三年。", ("secret",)),
        ("bounds", "价格下限{floor}、价格上限{ceiling}，总额不得超过{total}元。", ()),
    ],
    "dev": [
        ("money_alt", "价款（人民币）{amount}万元/年，分{period}支付；三年总额{total}万元。", ()),
        ("ratio_alt", "质保金比例为{ratio}，责任承担比例最高不超过{cap}。", ()),
        ("term_alt", "服务自签署日起持续{term}，费用按年支付、按月提供发票。", ()),
        ("negative_alt", "不得将{project}发送给{person}以外任何第三方，法律强制披露除外。", ("project", "person")),
        ("law_alt", "适用《中华人民共和国网络安全法》；争议解决依《中华人民共和国仲裁法》。", ()),
        ("alias_alt", "签约人{alias}，曾用名{person}，两者为同一授权代表。", ("alias", "person")),
        ("company_alt", "登记企业：{org}；其研发代号为{project}，不得对外宣传。", ("org", "project")),
        ("contact_alt", "电子送达：{email}；备用热线：{phone}；履约地点：{address}。", ("email", "phone", "address")),
        ("identity_alt", "付款账户为{account}，开户主体证件{id}，统一代码{credit}。", ("account", "id", "credit")),
        ("linebreak_ocr", "账户字段\n{account_spaced}\n证件字段\n{id_spaced}\n请人工复核。", ("account_spaced", "id_spaced")),
        ("secret_alt", "谈判底价{secret}不得外传，合同公开金额为{amount}万元。", ("secret",)),
        ("bounds_alt", "最低结算额{floor}万元，最高结算额{ceiling}万元，币种为美元。", ()),
    ],
}


def _values(split: str, index: int) -> dict[str, str]:
    key = 17 if split == "train" else 29
    rng = random.Random(20260915 + key * 100_000 + index)
    prefix = "岚港" if split == "train" else "镜河"
    serial = (1 if split == "train" else 7) * 100_000 + index
    train_names = ("云舟", "若宁", "景川", "知远", "安澜", "明澈", "星河", "书言", "嘉木", "闻溪")
    dev_names = ("清禾", "映雪", "砚秋", "怀瑾", "舒宁", "予安", "初阳", "芷晴", "亦航", "南乔")
    surnames = ("顾", "林", "沈", "周", "陆") if split == "train" else ("唐", "许", "韩", "苏", "秦")
    given = (train_names if split == "train" else dev_names)[index % 10]
    account = f"622299{serial:013d}"
    birth_year = "1992" if split == "train" else "1987"
    ident = f"110101{birth_year}{(index % 12) + 1:02d}{(index % 27) + 1:02d}{serial % 1000:03d}X"
    # 18-character ASCII placeholder shaped like a unified social credit code.
    credit = ("91" if split == "train" else "92") + f"{serial:016d}"[:16]
    return {
        "amount": str(rng.randint(18, 86)),
        "period": "每年" if index % 2 == 0 else "每月",
        "total": str(rng.randint(90, 360)),
        "currency": "人民币" if index % 3 else "美元",
        "ratio": f"{rng.randint(3, 18)}%",
        "cap": f"{rng.randint(20, 80)}万元",
        "term": f"{rng.randint(6, 36)}个月",
        "floor": str(rng.randint(20, 60)),
        "ceiling": str(rng.randint(120, 480)),
        "secret": f"{rng.randint(8, 39) if split == 'train' else rng.randint(48, 79)}.{rng.randint(1, 9)}万元",
        "person": surnames[index % len(surnames)] + given,
        "alias": surnames[index % len(surnames)] + (("小" + given[-1]) if split == "train" else ("阿" + given[-1])),
        "org": f"{prefix}{serial}数智有限公司",
        "project": f"{prefix}-澄明-{serial}",
        "email": f"notice{serial}@{('fiction' if split == 'train' else 'sample')}.invalid",
        "phone": f"138{serial:08d}",
        "address": f"虚构市{prefix}区星河路{serial}号{index % 9 + 1}室",
        "id": ident,
        "account": account,
        "credit": credit,
        "account_spaced": " ".join(account[i:i + 4] for i in range(0, len(account), 4)),
        "id_spaced": " ".join(ident[i:i + 4] for i in range(0, len(ident), 4)),
    }


def _gold(text: str, values: dict[str, str], fields: tuple[str, ...]) -> list[dict]:
    field_types = {"person": "PERSON", "alias": "PERSON", "org": "ORG", "project": "PROJECT",
                   "email": "EMAIL", "phone": "PHONE", "address": "ADDRESS", "id": "ID",
                   "id_spaced": "ID", "account": "ACCOUNT", "account_spaced": "ACCOUNT", "credit": "CREDIT",
                   "secret": "SECRET"}
    result = [{"text": values[field], "type": field_types[field]} for field in fields]
    result.sort(key=lambda item: text.index(item["text"]))
    spans(text, result)
    return result


def build(output: Path, train_count: int = 720, dev_count: int = 240) -> None:
    if train_count <= 0 or dev_count <= 0:
        raise ValueError("COUNTS_MUST_BE_POSITIVE")
    output.mkdir(parents=True, exist_ok=False)
    records_by_split: dict[str, list[dict]] = {}
    family_counts: dict[str, dict[str, int]] = {}
    type_counts: dict[str, dict[str, int]] = {}
    seen: set[str] = set()
    for split, count in (("train", train_count), ("dev", dev_count)):
        records: list[dict] = []
        templates = FAMILIES[split]
        for index in range(count):
            family, _, fields = templates[index % len(templates)]
            values = _values(split, index)
            template = templates[index % len(templates)][1]
            # Ordinary commercial quantity keeps rows unique without an ID-like reference.
            text = template.format(**values) + f" 本批次数量为{index + 1}件。"
            entities = _gold(text, values, fields)
            text_digest = digest(text)
            if text_digest in seen:
                raise ValueError("DUPLICATE_CASE")
            seen.add(text_digest)
            records.append({"id": f"generalization-{split}-{index:05d}", "source": "fictitious-generalization-v1",
                            "family": family, "text": text, "entities": entities,
                            "gold_spans": [[a, b, kind] for a, b, kind in sorted(spans(text, entities))],
                            "variant": "ocr_or_whitespace" if "ocr" in family or "space" in family or "linebreak" in family else "plain"})
        records_by_split[split] = records
        family_counts[split] = dict(Counter(r["family"] for r in records))
        type_counts[split] = dict(Counter(e["type"] for r in records for e in r["entities"]))
        (output / f"{split}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
        mlx_name = "train.jsonl" if split == "train" else "valid.jsonl"
        (output / "mlx").mkdir(exist_ok=True)
        (output / "mlx" / mlx_name).write_text("".join(json.dumps({"messages": messages(r)}, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    report = {"categories": list(KINDS), "counts_by_split": type_counts,
              "families_by_split": family_counts,
              "variants": {"plain": "ordinary spacing", "ocr_or_whitespace": "line breaks or grouped OCR-like fields"},
              "limitations": ["All text and identities are fictitious; no user contract or existing blind/test set was read.",
                              "Family and literal inventory separation reduces leakage but is not independent human annotation.",
                              "Legal names and amounts are retained as ordinary semantics; business-secret status follows explicit template cues.",
                              "OCR cases represent spacing and line breaks only, not image recognition or handwritten text."],
              "annotation": "Exact literal entities plus UTF-8 half-open character spans; repeated literals would be expanded by spans()."}
    (output / "category-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"schema": 2, "source": "fictitious-generalization-v1", "seed": 20260915,
                "split_method": "disjoint template families and literal inventories; train/dev only",
                "test_loaded": False, "families": {k: [x[0] for x in FAMILIES[k]] for k in FAMILIES},
                "files": {k: {"rows": len(v), "digest": digest(v)} for k, v in records_by_split.items()},
                "category_report": "category-report.json"}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "GENERALIZATION_DATA_PREPARED", "counts": {k: len(v) for k, v in records_by_split.items()}, "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-count", type=int, default=720)
    parser.add_argument("--dev-count", type=int, default=240)
    args = parser.parse_args()
    build(args.output, args.train_count, args.dev_count)
