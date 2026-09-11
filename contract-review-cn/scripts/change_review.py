"""Offline text-version comparison and conservative semantic change screening.

Alerts are review priorities, never legal findings. All coordinates are Unicode
code points into the released documents. No normalization of evidence text.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
import re

import pipeline as p

MAX_ALIGNMENT_PRODUCT = 2_000_000
MAX_DETAIL_PRODUCT = 4_000_000
CHINESE_DIGITS = {char: value for value, char in enumerate("零一二三四五六七八九")}
NUMBER = r"(?:[+-]?\d+(?:,\d{3})*(?:\.\d+)?|[零一二三四五六七八九十百两]+)"
MONEY = re.compile(r"(?<![\d.])(" + NUMBER + r")(亿|万|千)?(美元|欧元|港元|人民币|元)?")
PERIOD = re.compile(r"[/／]\s*(?:年|月|日|天|人|次|项目|件)|每(?:年|月|日|天|人|次|项目|件)")
TERM = re.compile(r"(" + NUMBER + r")\s*年")
CURRENCIES = {"人民币": "CNY", "元": "CNY", "RMB": "CNY", "CNY": "CNY", "￥": "CNY", "¥": "CNY",
              "美元": "USD", "美金": "USD", "USD": "USD", "欧元": "EUR", "EUR": "EUR", "€": "EUR",
              "港元": "HKD", "HKD": "HKD", "$": "$"}
CURRENCY_PREFIX = re.compile(r"(人民币|美元|美金|欧元|港元|RMB|CNY|USD|EUR|HKD|[$¥￥€])\s*$")
LEXICONS = {
    "NEGATION_OR_EXCEPTION": r"不得|不予|不承担|不包含|不包括|除非|除外|不|无",
    "OBLIGATION_STRENGTH": r"应当|必须|保证|尽力|可以|有权|应|须|可",
    "SCOPE_OR_CAP": r"累计|每次|全部损失|直接损失|间接损失|不超过|至少|至多|仅限|包含|包括",
    "CONDITION_OR_NOTICE": r"验收合格|验收|交付|双方同意|双方书面同意|协商一致|通知|发出|收到",
    "TIME_OR_DEADLINE": r"工作日|自然日|届满|到期|提前|之内|以内|之后|之前|起算",
    "CONNECTIVE": r"并且|或者|以及|且|或|及",
}


def number(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation:
        pass
    value = value.replace("两", "二")
    if len(value) == 1 and value in CHINESE_DIGITS:
        return Decimal(CHINESE_DIGITS[value])
    if "十" in value and value.count("十") == 1 and "百" not in value:
        left, right = value.split("十")
        if (not left or left in CHINESE_DIGITS) and (not right or right in CHINESE_DIGITS):
            return Decimal(CHINESE_DIGITS.get(left, 1) * 10 + CHINESE_DIGITS.get(right, 0))
    return None


def amounts(text: str) -> list[dict]:
    result = []
    for match in MONEY.finditer(text):
        numeric, scale, currency = match.groups()
        prefix = CURRENCY_PREFIX.search(text[max(0, match.start() - 12):match.start()])
        if not scale and not currency and prefix is None:
            continue
        value = number(numeric)
        if value is None:
            continue
        value *= {None: 1, "千": 1000, "万": 10000, "亿": 100000000}[scale]
        suffix_currency = CURRENCIES.get(currency)
        prefix_currency = CURRENCIES[prefix.group(1)] if prefix else None
        detected = ("conflict" if suffix_currency and prefix_currency and suffix_currency != prefix_currency
                    else suffix_currency or prefix_currency or "unspecified")
        result.append({"value": str(value), "currency": detected, "text": match.group()})
    return result


def semantic_alerts(before: str, after: str) -> list[dict]:
    if before == after:
        return []
    alerts = []
    def add(code: str, **details) -> None:
        alerts.append({"code": code, "priority": "high_review_priority", "requires_context_review": True, **details})
    def periods(text: str) -> Counter:
        return Counter(re.sub(r"\s+", "", value).replace("／", "/").replace("/", "每") for value in PERIOD.findall(text))
    old_periods, new_periods = periods(before), periods(after)
    if old_periods != new_periods:
        add("PRICING_BASIS_CHANGED", before=dict(old_periods), after=dict(new_periods))
    old_money, new_money = amounts(before), amounts(after)
    if [(m["value"], m["currency"]) for m in old_money] != [(m["value"], m["currency"]) for m in new_money]:
        add("AMOUNT_OR_CURRENCY_CHANGED", before=old_money, after=new_money)
    # Scenario arithmetic only: one explicit amount and one unchanged year term.
    old_terms, new_terms = TERM.findall(before), TERM.findall(after)
    if (len(old_money) == len(new_money) == len(old_terms) == len(new_terms) == 1 and
            old_money[0]["currency"] == new_money[0]["currency"] and
            old_money[0]["currency"] != "conflict" and
            number(old_terms[0]) == number(new_terms[0]) and number(old_terms[0]) is not None and
            number(old_terms[0]) > 0 and
            not re.search(r"不|上限|最多|至少|至多|预计|暂定|选择|或|除|原则上", before + after) and
            len(old_periods) == 1 and next(iter(old_periods)) in {"/年", "／年", "每年"} and not new_periods):
        annual = Decimal(old_money[0]["value"]) * number(old_terms[0])
        lump_sum = Decimal(new_money[0]["value"])
        add("ANNUAL_TO_TERM_TOTAL_SCENARIO", years=str(number(old_terms[0])),
            old_total_if_annual=str(annual), new_total_if_term_lump_sum=str(lump_sum),
            possible_reduction=str(annual - lump_sum), currency=old_money[0]["currency"],
            assumption="仅在旧文为每年支付、新文为全期总额且无其他调整时成立；需核对总价、付款计划及税费。")
    for code, pattern in LEXICONS.items():
        old, new = Counter(re.findall(pattern, before)), Counter(re.findall(pattern, after))
        if old != new:
            add(code, before=dict(old), after=dict(new))
    if Counter(re.findall(NUMBER, before)) != Counter(re.findall(NUMBER, after)):
        add("NUMBER_OR_REFERENCE_CHANGED")
    if Counter(re.findall(r"\d+(?:\.\d+)?\s*[%％]", before)) != Counter(re.findall(r"\d+(?:\.\d+)?\s*[%％]", after)):
        add("PERCENTAGE_CHANGED")
    if not before or not after:
        add("CLAUSE_ADDED_OR_DELETED")
    return alerts


def source_text(documents: list[dict], source_index: int | None) -> tuple[str, list[tuple[int, int, dict]]]:
    offset = 0
    spans = []
    for doc in documents:
        if source_index is not None and doc["source_index"] == source_index:
            spans.append((offset, offset + len(doc["text"]), doc))
            offset += len(doc["text"])
    return "".join(doc["text"] for _, _, doc in spans), spans


def evidence(text: str, spans: list[tuple[int, int, dict]], start: int, end: int) -> dict:
    ranges = []
    for left, right, doc in spans:
        a, b = max(start, left), min(end, right)
        if a < b:
            ranges.append({"document_id": doc["id"], "start": a - left, "end": b - left,
                           "quote": doc["text"][a - left:b - left]})
    return {"start": start, "end": end, "text": text[start:end], "ranges": ranges}


def chunks(text: str) -> tuple[list[str], list[int]]:
    # Sentence/line delimiters retain all punctuation, spacing and line endings.
    units = [m.group() for m in re.finditer(r"[^。；\n]*(?:[。；\n]|$)", text) if m.group()]
    offsets = [0]
    for unit in units:
        offsets.append(offsets[-1] + len(unit))
    p.require("".join(units) == text, "COMPARISON_CHUNK_LOSS")
    return units, offsets


def compare(documents: list[dict], pairs: list[dict], gaps: list[dict]) -> dict:
    changes, pair_records, blockers = [], [], []
    if gaps:
        blockers.append("COMPARISON_INPUTS_INCOMPLETE")
    for index, pair in enumerate(pairs, 1):
        before, before_spans = source_text(documents, pair["before"])
        after, after_spans = source_text(documents, pair["after"])
        old, oi = chunks(before)
        new, ni = chunks(after)
        coarse = len(old) * len(new) > MAX_ALIGNMENT_PRODUCT
        if coarse:
            operations = [("equal" if before == after else "replace", 0, len(old), 0, len(new))]
        else:
            operations = SequenceMatcher(None, old, new, autojunk=False).get_opcodes()
        pair_id = f"PAIR{index:04d}"
        ledger = []
        for tag, i, j, a, b in operations:
            entry = {"op": tag, "before_start": oi[i], "before_end": oi[j], "after_start": ni[a], "after_end": ni[b]}
            if tag != "equal":
                old_text, new_text = before[oi[i]:oi[j]], after[ni[a]:ni[b]]
                cid = f"CHG{len(changes) + 1:06d}"
                entry["change_id"] = cid
                detail_coarse = len(old_text) * len(new_text) > MAX_DETAIL_PRODUCT
                detail = []
                if not detail_coarse:
                    detail = [{"op": op, "before_start": x, "before_end": y, "after_start": u, "after_end": v}
                              for op, x, y, u, v in SequenceMatcher(None, old_text, new_text, autojunk=False).get_opcodes()
                              if op != "equal"]
                else:
                    blockers.append("COARSE_CHANGE_REQUIRES_PARTITIONED_REVIEW")
                changes.append({"id": cid, "pair_id": pair_id, "kind": tag,
                    "before": evidence(before, before_spans, oi[i], oi[j]),
                    "after": evidence(after, after_spans, ni[a], ni[b]), "edits": detail,
                    "coarse": coarse or detail_coarse, "alerts": semantic_alerts(old_text, new_text)})
            ledger.append(entry)
        if coarse and before != after:
            blockers.append("COARSE_CHANGE_REQUIRES_PARTITIONED_REVIEW")
        # Exact unique delete/insert pairs are movement candidates, never declared harmless.
        deleted, inserted = {}, {}
        for change in changes:
            if change["pair_id"] == pair_id:
                if change["kind"] == "delete":
                    deleted.setdefault(change["before"]["text"], []).append(change)
                if change["kind"] == "insert":
                    inserted.setdefault(change["after"]["text"], []).append(change)
        for text in deleted.keys() & inserted.keys():
            if len(deleted[text]) == len(inserted[text]) == 1:
                left, right = deleted[text][0], inserted[text][0]
                left["move_peer"], right["move_peer"] = right["id"], left["id"]
        pair_records.append({"id": pair_id, **pair, "before_length": len(before), "after_length": len(after), "operations": ledger})
    result = {"schema_version": 1, "pairs": pair_records, "changes": changes, "blockers": sorted(set(blockers)),
              "scope": "extracted_text_only", "legal_effect_certified": False}
    result["comparison_digest"] = p.digest(result)
    return result


def check(comparison: dict, documents: list[dict], gaps: list[dict] | None = None) -> None:
    p.require(comparison.get("schema_version") == 1, "COMPARISON_SCHEMA")
    p.require(comparison.get("comparison_digest") == p.digest({k: v for k, v in comparison.items() if k != "comparison_digest"}),
              "COMPARISON_DIGEST_MISMATCH")
    changes = {change["id"]: change for change in comparison["changes"]}
    p.require(len(changes) == len(comparison["changes"]), "COMPARISON_DUPLICATE_CHANGE")
    pairs = comparison["pairs"]
    p.require(len({pair["id"] for pair in pairs}) == len(pairs), "COMPARISON_DUPLICATE_PAIR")
    source_indices = [pair[side] for pair in pairs for side in ("before", "after") if pair[side] is not None]
    p.require(all(type(index) is int and index > 0 for index in source_indices) and
              len(source_indices) == len(set(source_indices)) and
              {doc["source_index"] for doc in documents} <= set(source_indices), "COMPARISON_SOURCE_COVERAGE")
    if gaps:
        p.require("COMPARISON_INPUTS_INCOMPLETE" in comparison["blockers"], "COMPARISON_GAPS_HIDDEN")
    if any(change["coarse"] for change in changes.values()):
        p.require("COARSE_CHANGE_REQUIRES_PARTITIONED_REVIEW" in comparison["blockers"], "COMPARISON_COARSE_HIDDEN")
    seen = set()
    for pair in comparison["pairs"]:
        before, bs = source_text(documents, pair["before"])
        after, ns = source_text(documents, pair["after"])
        p.require(pair["before"] is not None or pair["after"] is not None, "COMPARISON_EMPTY_PAIR")
        p.require(pair["before_length"] == len(before) and pair["after_length"] == len(after), "COMPARISON_LENGTH_MISMATCH")
        cursor_old = cursor_new = 0
        for op in pair["operations"]:
            start, end, a, b = (op[k] for k in ("before_start", "before_end", "after_start", "after_end"))
            p.require(all(type(n) is int for n in (start, end, a, b)) and start == cursor_old and a == cursor_new
                      and start <= end <= len(before) and a <= b <= len(after), "COMPARISON_COVERAGE_GAP")
            p.require(op["op"] in {"equal", "replace", "insert", "delete"}, "COMPARISON_OPERATION_INVALID")
            p.require((op["op"] != "insert" or start == end) and (op["op"] != "delete" or a == b),
                      "COMPARISON_OPERATION_BOUNDS")
            if op["op"] == "equal":
                p.require(before[start:end] == after[a:b], "COMPARISON_FALSE_EQUAL")
            else:
                cid = op.get("change_id")
                p.require(cid in changes and cid not in seen, "COMPARISON_CHANGE_MISSING")
                seen.add(cid)
                change = changes[cid]
                p.require(change["pair_id"] == pair["id"] and change["kind"] == op["op"] and
                          change["before"] == evidence(before, bs, start, end) and
                          change["after"] == evidence(after, ns, a, b), "COMPARISON_EVIDENCE_MISMATCH")
            cursor_old, cursor_new = end, b
        p.require(cursor_old == len(before) and cursor_new == len(after), "COMPARISON_TAIL_MISSING")
    p.require(seen == set(changes), "COMPARISON_ORPHAN_CHANGE")


def validate_reviews(bundle: dict, result: dict) -> None:
    comparison = bundle.get("comparison")
    if comparison is None:
        return
    p.require(result.get("comparison_digest") == comparison["comparison_digest"], "CHANGE_REVIEW_STALE")
    expected = {change["id"] for change in comparison["changes"]}
    segments = {segment["id"] for segment in bundle["segments"]}
    reviews = result.get("change_reviews")
    p.require(isinstance(reviews, list), "CHANGE_REVIEWS_REQUIRED")
    seen = set()
    for review in reviews:
        p.require(isinstance(review, dict) and isinstance(review.get("change_id"), str) and
                  review["change_id"] in expected and review["change_id"] not in seen, "CHANGE_REVIEW_ID")
        seen.add(review["change_id"])
        p.require(review.get("classification") in {"material", "nonmaterial", "uncertain"} and
                  review.get("decision") in {"accept", "conditional", "reject", "clarify"} and
                  type(review.get("unresolved")) is bool and
                  all(p.nonempty(review.get(k)) for k in ("analysis", "context_note")), "CHANGE_REVIEW_FIELDS")
        p.require((review["classification"] != "uncertain" and review["decision"] != "clarify") or
                  review["unresolved"], "CHANGE_UNCERTAINTY_HIDDEN")
        refs = review.get("related_segment_ids")
        p.require(isinstance(refs, list) and all(isinstance(ref, str) for ref in refs) and
                  len(refs) == len(set(refs)) and set(refs) <= segments, "CHANGE_CONTEXT_REFERENCE")
    p.require(seen == expected, "CHANGE_REVIEW_COVERAGE")


def depth_blockers(bundle: dict, results: list[dict] | None) -> list[str]:
    comparison = bundle.get("comparison")
    if comparison is None:
        return []
    blockers = list(comparison["blockers"])
    if results is None:
        return [*blockers, "CHANGE_RESULTS_MISSING"]
    for result in results:
        validate_reviews(bundle, result)
        if any(review["unresolved"] for review in result["change_reviews"]):
            blockers.append("CHANGE_ISSUES_UNRESOLVED")
    return blockers


def report_lines(bundle: dict, results: list[dict]) -> list[str]:
    if "comparison" not in bundle:
        return []
    lines = ["", "## 合同版本修改专项审核", "", "以下为提取文本差异；计算为条件情景，不自动认定法律效果。"]
    changes = bundle["comparison"]["changes"]
    if not changes:
        lines.append("提取文本一致；不证明版式、签章、图片或原件完全一致。")
    for change in sorted(changes, key=lambda row: (not bool(row["alerts"]), row["id"])):
        lines.extend(["", f"### {change['id']}（{change['kind']}）", "",
                      "- V1：" + p.markdown_text(change["before"]["text"]),
                      "- V2：" + p.markdown_text(change["after"]["text"])])
        for side in ("before", "after"):
            for quote in change[side]["ranges"]:
                lines.append(f"- {side}定位：{quote['document_id']} [{quote['start']},{quote['end']})")
        for alert in change["alerts"]:
            if alert["code"] == "ANNUAL_TO_TERM_TOTAL_SCENARIO":
                def amount_label(key: str) -> str:
                    value = Decimal(alert[key])
                    return f"{value / 10000:f}万" if abs(value) >= 10000 else str(value)
                lines.append("- 条件情景：" + amount_label("old_total_if_annual") + " → " +
                             amount_label("new_total_if_term_lump_sum") + "，可能减少" + amount_label("possible_reduction") +
                             "；币种：" + p.markdown_text(alert["currency"]) + "。" + p.markdown_text(alert["assumption"]))
            else:
                labels = {"PRICING_BASIS_CHANGED": "计费单位或周期变化", "AMOUNT_OR_CURRENCY_CHANGED": "金额或币种变化",
                          "NEGATION_OR_EXCEPTION": "否定或例外变化", "OBLIGATION_STRENGTH": "义务强度变化",
                          "SCOPE_OR_CAP": "范围或责任上限变化", "CONDITION_OR_NOTICE": "条件或通知机制变化",
                          "TIME_OR_DEADLINE": "时点或期限规则变化", "CONNECTIVE": "逻辑连接词变化",
                          "NUMBER_OR_REFERENCE_CHANGED": "数字或条款引用变化", "PERCENTAGE_CHANGED": "比例变化",
                          "CLAUSE_ADDED_OR_DELETED": "条款新增或删除"}
                lines.append("- 优先复核提示：" + labels.get(alert["code"], alert["code"]))
        if change.get("move_peer"):
            lines.append("- 可能的条款移动，对应：" + change["move_peer"])
        for result in results:
            review = next(row for row in result["change_reviews"] if row["change_id"] == change["id"])
            decision = {"accept": "建议接受", "conditional": "附条件接受", "reject": "建议拒绝", "clarify": "需澄清"}[review["decision"]]
            lines.append("- " + p.markdown_text(result["role"]) + "：" + decision +
                         ("（仍有未决事项）" if review["unresolved"] else "") + "；" + p.markdown_text(review["analysis"]) +
                         "；全文关联：" + p.markdown_text(review["context_note"]) +
                         "；关联片段：" + p.markdown_text(review["related_segment_ids"]))
    return lines
