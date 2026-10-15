"""Build a deterministic, openly licensed fictional contract privacy corpus.

All values are invented by this project.  The corpus contains no user documents,
third party text, or generated secrets.  It is intended to exercise context and
boundary cases that are easy to miss in ordinary PII datasets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import TYPES, digest


TEMPLATES = (
    ("联系人", "甲方联系人{name}，手机{phone}，邮箱{email}。"),
    ("收款", "乙方收款账户为{account}，开户机构为{org}，开户地址为{address}。"),
    ("项目", "双方就内部项目“{project}”合作，项目负责人为{name}。"),
    ("签署", "本协议由{org}（地址：{address}）与{name}签署，通知发送至{email}。"),
    ("保密", "甲方披露的技术资料“{secret}”及项目代号{project}属于保密信息。"),
    ("混合", "如需联系{name}请拨打{phone}；合同金额300万元/年、期限三年，项目为{project}。"),
    ("边界", "甲方名称为{org}，甲方称谓、履约日期2027年3月1日、税率6%和300万元/年报价按原文保留。"),
    ("重复", "联系人{name}邮箱{email}；后文再次确认{name}的邮箱仍为{email}。"),
    ("分隔", "联系：{phone}；备用电话：{phone2}。账号 {account} 不得写入公开版本。"),
    ("编码", "项目编号{project}，技术秘密为{secret}。金额合计900万元，分三年支付。"),
)
TRAIN_TEMPLATE_NAMES = {"联系人", "收款", "项目", "签署", "保密", "混合", "边界"}

VALUES = (
    {"name": "林知远", "phone": "138-0000-1001", "phone2": "010 5555 2001", "email": "zhi.yuan@example.invalid", "account": "622202000000100001", "org": "澄明（虚构）科技有限公司", "address": "海州市云杉路1号A座", "project": "青岚-ALPHA-01", "secret": "蓝鲸算法内部底价"},
    {"name": "周若安", "phone": "13900001002", "phone2": "021-5555-2002", "email": "ruoan@example.invalid", "account": "621700000000100002", "org": "远岑（虚构）咨询事务所", "address": "江城新区松涛街2号", "project": "星垂-BETA-02", "secret": "赤道配方测试参数"},
    {"name": "顾明川", "phone": "+86 137 0000 1003", "phone2": "0755 5555 2003", "email": "mingchuan@example.invalid", "account": "622848000000100003", "org": "白露（虚构）供应链公司", "address": "南岭市环湖路3号", "project": "云梯-GAMMA-03", "secret": "银杏模型未公开权重"},
    {"name": "沈嘉禾", "phone": "136-0000-1004", "phone2": "400-555-2004", "email": "jiahe@example.invalid", "account": "621226000000100004", "org": "砚台（虚构）数据服务中心", "address": "东浦区临江大道4号", "project": "海隅-DELTA-04", "secret": "白塔客户底价表"},
)


def values_for(index: int) -> dict[str, str]:
    """Create unique, fictional values without resembling real identifiers."""
    n = index + 1
    return {"name": f"林知远{n:03d}", "phone": f"138-0000-{1000+n:04d}", "phone2": f"010 5555 {2000+n:04d}", "email": f"zhi.yuan{n:03d}@example.invalid", "account": f"622202000000{100000+n:06d}", "org": f"澄明{n:03d}（虚构）科技有限公司", "address": f"海州市云杉路{n}号A座", "project": f"青岚-ALPHA-{n:03d}", "secret": f"蓝鲸算法内部底价{n:03d}"}


def entities(values: dict[str, str], template_name: str, template: str) -> list[dict[str, str]]:
    keys = {"name": "PERSON", "phone": "PHONE", "phone2": "PHONE", "email": "EMAIL", "account": "ACCOUNT", "org": "ORG", "address": "ADDRESS", "project": "PROJECT", "secret": "SECRET"}
    text = template.format(**values)
    result = []
    for key, kind in keys.items():
        value = values[key]
        if value in text and {"text": value, "type": kind} not in result:
            result.append({"text": value, "type": kind})
    return result


def build(output: Path, count: int = 240) -> None:
    if count < len(TEMPLATES):
        raise ValueError("COUNT_TOO_SMALL")
    records = []
    cut = int(count * 0.8)
    train_templates = [item for item in TEMPLATES if item[0] in TRAIN_TEMPLATE_NAMES]
    dev_templates = [item for item in TEMPLATES if item[0] not in TRAIN_TEMPLATE_NAMES]
    for index in range(count):
        template_pool = train_templates if index < cut else dev_templates
        template_name, template = template_pool[index % len(template_pool)]
        values = values_for(index)
        text = template.format(**values)
        records.append({"id": f"fictional-contract-v2-{index:04d}", "family": f"contract-edge-{template_name}", "text": text, "entities": entities(values, template_name, template), "source": "original-fictional-project-v2", "license": "CC0-1.0", "evaluated_types": sorted(TYPES)})
    output.mkdir(parents=True, exist_ok=False)
    (output / "train.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records[:cut]), encoding="utf-8")
    (output / "dev.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records[cut:]), encoding="utf-8")
    (output / "SOURCE-README.md").write_text("# Contract edge corpus v1\n\nOriginal fictional Chinese contract sentences authored by this project. No user or third-party text is included. Values use reserved `.invalid` email domains and invented organizations. License: CC0-1.0. Use for training and development evaluation only; it is not legal advice and does not represent real contracts.\n", encoding="utf-8")
    train_families = {row["family"] for row in records[:cut]}
    dev_families = {row["family"] for row in records[cut:]}
    if len({row["text"] for row in records}) != count or train_families & dev_families:
        raise ValueError("SPLIT_LEAKAGE")
    (output / "manifest.json").write_text(json.dumps({"dataset": "contract-edge-v2", "source": "original-fictional-project-v2", "license": "CC0-1.0", "rows": count, "train_rows": cut, "dev_rows": count - cut, "unique_texts": len({row["text"] for row in records}), "train_families": sorted(train_families), "dev_families": sorted(dev_families), "family_intersection": sorted(train_families & dev_families), "row_digest": digest(records), "limitations": ["template-generated and small", "does not measure legal-domain recall", "no real personal data", "dev is deterministic and should not be reused as a hidden test"]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "FICTIONAL_PUBLIC_CORPUS_PREPARED", "rows": count, "train": cut, "dev": count - cut}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=240)
    args = parser.parse_args()
    build(args.output, args.count)
