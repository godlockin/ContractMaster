"""Conservative local fallback extractors for high-risk literals.

These rules supplement the model; they never send text elsewhere and only emit
literal substrings that can be verified against the source.
"""
from __future__ import annotations
import re
from common import TYPES


def _add(out: list[dict], text: str, kind: str, allowed: set[str]) -> None:
    if kind == "ADDRESS":
        for cue in ("送交", "送至", "投递到", "投递至", "地址：", "地址:", "地点：", "地点:"):
            if cue in text:
                text = text.rsplit(cue, 1)[-1]
        text = text.strip()
    if kind == "ORG":
        # Regex context may include a preceding Chinese cue; retain company literal.
        for cue in ("为", "是", "由", "与", "：", ":", "；", ";", "。", "，", ","):
            if cue in text:
                text = text.rsplit(cue, 1)[-1]
        text = text.strip()
    if kind not in allowed or not text:
        return
    if not any(x["text"] == text and x["type"] == kind for x in out):
        out.append({"text": text, "type": kind})


def entities(text: str, allowed: set[str] | None = None) -> list[dict]:
    scope = TYPES if allowed is None else set(allowed)
    out: list[dict] = []
    # Formats with separators and international prefixes.
    for m in re.finditer(r"(?<![\w])\+?\d[\d -]{7,20}\d(?!\w)", text):
        value = m.group().strip()
        digits = re.sub(r"\D", "", value)
        left = text[max(0, m.start()-10):m.start()]
        phone_cue = re.search(r"电话|手机|联系|拨|热线|tel", left, re.I)
        if 10 <= len(digits) <= 15 and (digits.startswith('1') and len(digits) == 11 or phone_cue) and ("PHONE" in scope):
            _add(out, value, "PHONE", scope)
    for m in re.finditer(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
        _add(out, m.group(), "EMAIL", scope)
    for m in re.finditer(r"(?<![A-Za-z0-9])(?:[A-Z]{1,4}\d{5,}|\d{6,}[A-Z][A-Z0-9]{0,4})(?![A-Za-z0-9])", text):
        value = m.group()
        if not re.fullmatch(r"[159Y][1239]\d{6}[0-9A-HJ-NPQRTUWXY]{10}", value):
            _add(out, value, "ID", scope)
    for m in re.finditer(r"(?<![A-Za-z0-9])\d{12,19}(?![A-Za-z0-9])", text):
        value = m.group()
        # 18-digit mainland identity numbers are handled as ID, never ACCOUNT.
        if len(value) == 18 and re.fullmatch(r"\d{17}[0-9Xx]", value):
            continue
        left = text[max(0, m.start()-12):m.start()]
        if re.search(r"账号|账户|银行卡|信用卡|汇入|付款|account", left, re.I) or value.startswith(('62', '4')):
            _add(out, value, "ACCOUNT", scope)
    # Chinese address phrases; require a location marker to avoid ordinary numbers.
    address = r"(?:[\u4e00-\u9fff]{2,12}(?:市|省|自治区))?[\u4e00-\u9fff]{1,12}(?:区|县|街道|镇|乡)[\u4e00-\u9fff0-9A-Za-z-]{0,20}(?:路|街|道)[\u4e00-\u9fff0-9A-Za-z-]{0,12}(?:号|弄|巷)\s*[\u4e00-\u9fff0-9A-Za-z-]{0,8}"
    for m in re.finditer(address, text):
        _add(out, m.group().strip(" ，,。；;"), "ADDRESS", scope)
    # Company names and explicit person fields. Cues limit over-redaction.
    for m in re.finditer(r"[\u4e00-\u9fffA-Za-z0-9]{2,30}(?:有限公司|股份有限公司|咨询公司|设备有限公司|数智服务有限公司)", text):
        _add(out, m.group(), "ORG", scope)
    for m in re.finditer(r"(?:联系人|收件人|签字人|授权代表|负责人|经办人|姓名)\s*[：:]?\s*(?:为|是)?\s*((?!手机|邮箱|地址|办公)[\u4e00-\u9fff]{2,4})", text):
        _add(out, m.group(1), "PERSON", scope)
    # Project labels need an explicit cue; distinguish from ordinary legal text.
    for m in re.finditer(r"(?:项目(?:代号|名称|名)|内部代号|检索名称)\s*[：:为是]?\s*[“\"『]?([\u4e00-\u9fffA-Za-z0-9_-]{2,30})", text):
        _add(out, m.group(1).strip("”\"』。；;"), "PROJECT", scope)
    for m in re.finditer(r"以\s*([\u4e00-\u9fffA-Za-z0-9_-]{2,30})\s*为检索名称", text):
        _add(out, m.group(1), "PROJECT", scope)
    secret_cue = r"(?:保密|机密|秘密|内部|谈判|最低可接受|底价|不公开)[^。；;\n]{0,24}"
    amount = r"(?:人民币[壹贰叁肆伍陆柒捌玖拾佰仟万亿零〇一二三四五六七八九十百千万亿点\.]+[元圆万元]|(?<![\d.])\d+(?:\.\d+)?\s*万元)"
    for m in re.finditer(secret_cue + "(" + amount + ")", text):
        _add(out, m.group(1).strip(), "SECRET", scope)
    return out


def resolve(text: str, predicted: list[dict]) -> list[dict]:
    """Normalize conflicts while preserving only grounded literal predictions."""
    project_literals = {x['text'] for x in predicted if x['type'] == 'PROJECT'}
    result: list[dict] = []
    for item in predicted:
        if item in result:
            continue
        literal, kind = item.get('text'), item.get('type')
        if kind == 'SECRET' and literal in project_literals:
            continue
        if kind == 'SECRET' and any(cue in text[max(0, text.find(literal)-24):text.find(literal)] for cue in ('公开法律条文', '普通服务费', '年度报价', '合同总额', '公开报价')):
            continue
        result.append(item)
    return result


def filter_items(text: str, predicted: list[dict], allowed: set[str] | None = None) -> list[dict]:
    """Drop structurally implausible model spans before they can cause over-redaction."""
    scope = TYPES if allowed is None else set(allowed)
    result: list[dict] = []
    for item in predicted:
        literal, kind = item.get('text'), item.get('type')
        if kind not in scope or not isinstance(literal, str):
            continue
        digits = re.sub(r'\D', '', literal)
        left = text[max(0, text.find(literal)-16):text.find(literal)] if literal in text else ''
        if kind == 'ID':
            if not (len(literal) >= 8 and any(c.isalpha() for c in literal) or
                    (len(digits) in {17, 18} and literal[-1:] in 'Xx')):
                continue
            if literal.isdigit() and not re.search(r'证件|身份证|护照|驾照|税号|社会保险|编号|代码', left):
                continue
        elif kind == 'ACCOUNT':
            if len(digits) < 12 or not (re.search(r'账号|账户|银行卡|信用卡|汇入|付款|account', left, re.I) or literal.startswith(('62', '4'))):
                continue
        elif kind == 'PHONE':
            if not (10 <= len(digits) <= 15 and (len(digits) == 11 and digits.startswith('1') or re.search(r'电话|手机|联系|拨|热线|tel', left, re.I))):
                continue
        elif kind == 'ADDRESS':
            if not re.search(r'市|省|区|县|街道|路|街|号|邮编|zipcode', literal, re.I):
                continue
        if item not in result:
            result.append(item)
    return result
