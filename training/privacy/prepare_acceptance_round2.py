"""Frozen hand-authored synthetic acceptance cases; never training input."""
from pathlib import Path
import json
from common import spans, digest


def build(output: Path) -> None:
    # Different narrative structures from the training generator; no real data.
    cases = [
        ("通知应送达陶映舟本人；不得仅通知代理人。", [("陶映舟", "PERSON")]),
        ("签约时使用简称“辰谷”，其全称为辰谷器材有限公司。", [("辰谷器材有限公司", "ORG")]),
        ("项目代号：Mist-42；代号变更不影响原保密义务。", [("Mist-42", "PROJECT")]),
        ("保密底价为78万元，公开报价为95万元。", [("78万元", "SECRET")]),
        ("付款凭证请发至 receipt+case@sample.invalid，勿抄送外部人员。", [("receipt+case@sample.invalid", "EMAIL")]),
        ("联系人：江稚秋；联系方式另行提供，不属于本合同附件。", [("江稚秋", "PERSON")]),
        ("送至杭州市清原区杉林路18号2层；退货地址不变。", [("杭州市清原区杉林路18号2层", "ADDRESS")]),
        ("账户：6222000000000034567。开户行资料以纸质通知为准。", [("6222000000000034567", "ACCOUNT")]),
        ("电话：13900001234；该号码仅用于本次验收。", [("13900001234", "PHONE")]),
        ("身份证号：11010119920202001X；复印件不得提供给第三方。", [("11010119920202001X", "ID")]),
    ]
    preserved = [
        "未来三年300万元/年。", "未来三年共计300万元。",
        "按季度支付75万元，全年共计300万元。", "每月支付人民币25万元，服务期36个月。",
        "每年最低采购300万元，不代表三年总额上限。", "三年采购总额不超过300万元。",
        "赔偿以每次违约金额的20%为限。", "累计赔偿不超过已付服务费。",
        "服务费为300万美元/年，汇率按付款日确定。", "人民币300万元含税，税率6%。",
        "报价300万元不含税，增值税另计。", "付款期限为收到发票后30个工作日。",
        "期限为30个自然日，不含法定节假日的表述应删除。",
        "逾期利息每日万分之三，非每月万分之三。", "单价300元/人/月，不包含实施费。",
        "每次不超过300万元，累计不超过900万元。", "合同编号202609150001，与银行账号无关。",
        "项目管理服务费300万元，不含可选模块。", "技术服务应符合《中华人民共和国民法典》。",
        "甲方不得转委托，但经乙方事先书面同意的除外。",
    ]
    cases += [(text, []) for text in preserved]
    result = []
    for i, (text, entities) in enumerate(cases):
        items = [{"text": value, "type": kind} for value, kind in entities]
        spans(text, items)
        result.append({"id": f"ACCEPT2-{i:03d}", "text": text, "entities": items,
                       "family": "independent-hand-authored-acceptance", "source": "original-synthetic",
                       "preserve_text": text if not entities else None})
    output.mkdir(parents=True, exist_ok=False)
    (output / "test.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False)+"\n" for row in result))
    (output / "manifest.json").write_text(json.dumps({"rows": len(result), "digest": digest(result),
        "purpose": "final acceptance only; not training or model selection", "human_annotated": False}))
    print(json.dumps({"status": "FROZEN", "rows": len(result)}))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args().output)
