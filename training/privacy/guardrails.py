"""Conservative local fallback extractors for high-risk literals.

These rules supplement the model; they never send text elsewhere and only emit
literal substrings that can be verified against the source.
"""
from __future__ import annotations
import re
from common import TYPES


def _secret_amount_context(text: str, start: int) -> bool:
    """Require local confidential context; public minimum prices stay clear."""
    left = text[max((text.rfind(mark, 0, start) for mark in '。；;，,\n'), default=-1) + 1:start]
    # Confidential cues win: “不公开” contains 公开, and public/standard
    # wording may describe a separate amount in the same clause.
    if re.search(r'保密|机密|秘密|不公开', left):
        return True
    # Explicit public labels apply to this amount even when a surrounding
    # clause mentions internal review.
    if re.search(r'公开(?:报价|价格|金额|标准|底价)|市场(?:报价|价格|标准)', left):
        return False
    if re.search(r'内部[^。；;，,\n]{0,12}(?:底价|最低(?:价格|价|成交))', left):
        return True
    if re.search(r'谈判[^。；;，,\n]{0,12}(?:底价|最低(?:价格|价|成交))', left):
        return True
    return bool(re.search(r'最低(?:价格|可接受|成交)', left) and re.search(r'内部|谈判|保密|秘密', left))


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
        text = re.sub(r'^(?:甲方|乙方|收款机构|供货方|供应商|受托方|委托方)', '', text)
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
    for m in re.finditer(r"(?:内部(?:课题|研发(?:代号|项目)?|项目(?:代号|名称)?)|研发代号)\s*[：:为是]?\s*[“\"『]?([\u4e00-\u9fffA-Za-z0-9_-]{2,30})", text):
        _add(out, m.group(1).strip("”\"』。；;"), "PROJECT", scope)
    for m in re.finditer(r"以\s*([\u4e00-\u9fffA-Za-z0-9_-]{2,30})\s*为检索名称", text):
        _add(out, m.group(1), "PROJECT", scope)
    amount = r"(?:人民币[壹贰叁肆伍陆柒捌玖拾佰仟万亿零〇一二三四五六七八九十百千万亿点\.]+[元圆万元]|(?<![\d.])\d+(?:\.\d+)?\s*万元)"
    amount_re = re.compile(amount)
    secret_re = re.compile(r"保密|机密|秘密|内部|谈判|最低(?:价格|可接受|成交)|底价|不公开")
    for segment in re.split(r"[。；;\n]", text):
        for match in amount_re.finditer(segment):
            if _secret_amount_context(segment, match.start()):
                _add(out, match.group().strip(), "SECRET", scope)
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
        if kind == 'SECRET':
            positions = [match.start() for match in re.finditer(re.escape(literal), text)]
            contexts = [_secret_amount_context(text, position) for position in positions]
            if positions and any(contexts) and not all(contexts):
                raise ValueError('AMBIGUOUS_ENTITY_OCCURRENCE')
            if positions and not any(contexts) and any(re.search(r'公开法律条文|普通服务费|年度报价|合同总额|公开报价',
                                            text[max((text.rfind(mark, 0, position) for mark in '。；;，,\n'), default=-1) + 1:position])
                                   for position in positions):
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
        if literal in {'甲方','乙方','双方','合同','协议','总价','报价','联系人','签署人','付款方','供应商','受让方'}:
            continue
        digits = re.sub(r'\D', '', literal)
        occurrences = list(re.finditer(re.escape(literal), text)) if literal in text else []
        left = text[max(0, occurrences[0].start()-32):occurrences[0].start()] if occurrences else ''
        # Numeric commercial terms are not identities. Only explicit nearby
        # confidential-price cues permit a monetary SECRET, never an invented type.
        quantity = re.fullmatch(r'(?:人民币|￥|¥|USD|RMB)?\s*(?:\d+(?:[.,]\d+)*|[壹贰叁肆伍陆柒捌玖拾佰仟万亿零〇一二三四五六七八九十百千万亿点]+)\s*(?:万?元|万元|亿元|%|％|美元|年|月|日|天|个月)(?:/[年月日天])?|\d{1,6}(?:\.\d+)?', literal, re.I)
        if quantity:
            contexts = [_secret_amount_context(text, m.start()) or bool(re.search(
                        r'密码|密钥|secret|confidential', text[max(0, m.start()-24):m.start()], re.I))
                        for m in re.finditer(re.escape(literal), text)]
            if kind == 'SECRET' and any(contexts) and not all(contexts):
                raise ValueError('AMBIGUOUS_ENTITY_OCCURRENCE')
            if kind != 'SECRET' or not contexts or not all(contexts):
                continue
        if kind == 'ID':
            if not (len(literal) >= 8 and any(c.isalpha() for c in literal) or
                    (len(digits) in {17, 18} and literal[-1:] in '0123456789Xx')):
                continue
            if re.search(r'合同编号|订单号|运单号|批次号|条款编号', left):
                continue
            if literal.isdigit() and not re.search(r'证件|身份证|护照|驾照|税号|社会保险|编号|代码', left):
                continue
        elif kind == 'PROJECT':
            # Transaction identifiers are ordinary business references. Models
            # sometimes label PO/waybill/contract numbers as projects; keep
            # explicit local dictionary entries handled by the caller while
            # rejecting only the nearest identifier-field context.
            identifier_re = re.compile(
                r'(?:合同|订单|运单|批次|条款)\s*(?:编号|号码|号)|'
                r'(?:合同编号|订单编号|订单号|运单号|批次号|条款编号)')
            def nearest_context(occurrence: re.Match[str]) -> str:
                start = max((text.rfind(mark, 0, occurrence.start()) for mark in '。；;\n'), default=-1) + 1
                return text[start:occurrence.start()][-32:]
            identifier_flags = [bool(identifier_re.search(nearest_context(occurrence)))
                for occurrence in occurrences]
            if any(identifier_flags) and not all(identifier_flags):
                raise ValueError('AMBIGUOUS_ENTITY_OCCURRENCE')
            if identifier_flags and all(identifier_flags):
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


def contextual_entities(text: str, known: list[dict]) -> list[dict]:
    """Rescue explicit masks, aliases, filename fields and secret URL values."""
    out = []
    for match in re.finditer(r'(?:证件(?:编号|号)?|身份证(?:号)?|护照(?:号)?)[：:\s]*([A-Za-z0-9*Xx_-]{6,30})', text):
        _add(out, match[1], 'ID', TYPES)
    for match in re.finditer(r'(?:账户|账号)(?:前\d+位|后\d+位)?[：:\s]*([0-9* -]{4,30})', text):
        if '*' in match[1] or re.search(r'前\d+位|后\d+位', match[0]):
            _add(out, match[1].strip(), 'ACCOUNT', TYPES)
    for match in re.finditer(r'[?&](?:api[_-]?key|key|token|secret|password)=([^&\s，。；;<>]+)', text, re.I):
        _add(out, match[1], 'SECRET', TYPES)
    surnames = '赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛范彭郎鲁韦马苗方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于傅齐康伍余元顾孟平黄和穆萧尹姚邵汪祁毛禹狄米贝明臧计伏成戴宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯管卢莫房裘解应宗丁宣贲邓郁单杭洪包诸左石崔吉龚程邢裴陆荣翁荀羊甄曲封芮储靳段富巫乌焦巴牧山谷车侯宓蓬全班仰秋仲伊宫宁仇栾甘厉戎祖武符刘景詹束龙叶幸司黎薄印宿白怀蒲邰从鄂索咸赖卓蔺屠蒙池乔阳郁胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰雍桑桂牛寿通边扈燕冀浦尚农温庄晏瞿茹习艾鱼容向古易慎戈廖庾终居衡步都耿满弘匡国文寇广禄阙东欧沃利蔚越夔隆师巩聂晁勾敖融冷訾辛阚那简饶曾沙须丰巢关蒯相查后荆红游竺权逯盖益桓公'
    for match in re.finditer(r'(?:文件名(?:字段)?|附件名称)[：:\s]*(['+surnames+r'][\u4e00-\u9fff]{1,2})(?=[_-])', text):
        _add(out, match[1], 'PERSON', TYPES)
    candidates = known + out
    for match in re.finditer(r'(?:以下简称|下称|简称|别名|曾用名)[：:\s]*[“"‘（(]?([\u4e00-\u9fffA-Za-z0-9_-]{2,20})', text):
        preceding = [(text.rfind(item['text'], max(0,match.start()-120), match.start()), item)
                     for item in candidates if item['type'] in {'PERSON','ORG','PROJECT'}]
        preceding = [(pos,item) for pos,item in preceding if pos >= 0]
        if preceding:
            position, owner = max(preceding, key=lambda pair: pair[0]+len(pair[1]['text']))
            gap = text[position+len(owner['text']):match.start()]
            if not re.search(r'[。!?！？]|本合同|本协议|合同金额|总价|价款|税率', gap):
                _add(out, match[1], owner['type'], TYPES)
    return out
