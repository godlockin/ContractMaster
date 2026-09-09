"""Build an offline, evidence-checked human adjudication package, without model calls."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
from pathlib import Path


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def records(value: object, key: str) -> list[dict]:
    selected = value.get(key) if isinstance(value, dict) else value
    if not isinstance(selected, list) or not all(isinstance(row, dict) for row in selected):
        raise ValueError(f"Expected list of objects: {key}")
    return selected


def local_path(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("Missing local path")
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Path escapes corpus root")
    if not path.is_file():
        raise ValueError(f"Missing file: {path.name}")
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def coverage_text(value: object) -> str:
    if not isinstance(value, dict):
        return str(value)
    parts = [str(value[key]) for key in ("status", "detail", "note", "limitations") if value.get(key)]
    for key, label in (("read_pages", "本批已读页"), ("unread_pages", "本批未读页"), ("cumulative_read_pages_with_prior_batch", "与前批累计已读页")):
        pages = value.get(key)
        if isinstance(pages, list) and pages and all(type(page) is int for page in pages):
            ordered = sorted(set(pages))
            span = f"{ordered[0]}–{ordered[-1]}" if ordered == list(range(ordered[0], ordered[-1] + 1)) else ", ".join(str(page) for page in ordered)
            parts.append(f"{label}：{span}")
    return "；".join(parts) or json.dumps(value, ensure_ascii=False)


def build(root: Path) -> dict:
    root = root.resolve()
    cases = records(read_json(root / "manifest.json"), "cases")
    by_id = {case["id"]: case for case in cases}
    if len(by_id) != len(cases):
        raise ValueError("Duplicate case ID")
    reviews: list[dict] = []
    for path in sorted((root / "reviews").glob("*.json")):
        reviews.extend(records(read_json(path), "reviews"))
    seen: set[str] = set()
    finding_cases: dict[str, str] = {}
    rows: list[dict] = []
    case_reviews: dict[str, list[dict]] = {key: [] for key in by_id}
    for review in reviews:
        case_id = review["case_id"]
        if case_id not in by_id:
            raise ValueError(f"Unknown case: {case_id}")
        source = local_path(root, by_id[case_id]["sanitized_path"])
        if review.get("prior_review_path"):
            prior = local_path(root, review["prior_review_path"])
            if digest(prior) != review.get("prior_review_sha256"):
                raise ValueError(f"Stale continuation: {case_id}")
        if review.get("input_sha256") != digest(source):
            raise ValueError(f"Stale review: {case_id}")
        text = source.read_text(encoding="utf-8")
        for finding in records(review, "findings"):
            fid = finding["id"]
            if fid in seen:
                raise ValueError(f"Duplicate finding: {fid}")
            seen.add(fid)
            finding_cases[fid] = case_id
            evidence = records(finding, "evidence")
            if not evidence:
                raise ValueError(f"Missing evidence: {fid}")
            for entry in evidence:
                quote = entry.get("quote")
                start, end = entry.get("start"), entry.get("end")
                if not isinstance(quote, str) or not quote or quote not in text:
                    raise ValueError(f"Quote mismatch: {fid}")
                if start is None and end is None:
                    occurrences = text.count(quote)
                    if occurrences != 1:
                        raise ValueError(f"Ambiguous quote requires offsets: {fid}")
                    start = text.index(quote)
                    end = start + len(quote)
                if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
                    raise ValueError(f"Invalid coordinates: {fid}")
                if text[start:end] != quote:
                    raise ValueError(f"Coordinate mismatch: {fid}")
                entry["start"], entry["end"] = start, end
            rows.append({
                "case_id": case_id, "finding_id": fid,
                "perspective": finding.get("perspective", ""),
                "ai_severity": finding.get("severity", ""),
                "ai_issue": finding.get("risk", ""),
                "evidence": " | ".join(entry["quote"] for entry in evidence),
                "reviewer": "", "decision": "", "human_severity": "",
                "legal_source": "", "correction": "", "notes": "",
            })
        case_reviews[case_id].append(review)
    challenges: dict[str, list[dict]] = {}
    report_digests: dict[str, dict[str, set[str]]] = {}
    for path in (root / "reviews").glob("*.json"):
        report_cases: dict[str, set[str]] = {}
        for review in records(read_json(path), "reviews"):
            report_cases.setdefault(review["case_id"], set()).update(f["id"] for f in records(review, "findings"))
        report_digests[digest(path)] = report_cases
    cross_files = sorted((root / "cross-review").glob("*.json"))
    for path in cross_files:
        cross = read_json(path)
        if not isinstance(cross, dict) or cross.get("case_id") not in by_id:
            raise ValueError("Unknown cross-review case")
        case_id = cross["case_id"]
        if case_id not in report_digests.get(cross.get("reviewed_report_sha256"), set()):
            raise ValueError("Stale cross-review report")
        source = local_path(root, by_id[case_id]["sanitized_path"])
        if cross.get("input_sha256") != digest(source):
            raise ValueError("Stale cross-review input")
        text = source.read_text(encoding="utf-8")
        for judgment in records(cross, "judgments"):
            fid = judgment.get("finding_id")
            if finding_cases.get(fid) != case_id:
                raise ValueError("Unknown cross-review finding")
            if fid not in report_digests[cross["reviewed_report_sha256"]][case_id]:
                raise ValueError("Cross-review finding not in referenced report")
            for entry in records(judgment, "counterevidence"):
                start, end, quote = entry.get("start"), entry.get("end"), entry.get("quote")
                if type(start) is not int or type(end) is not int or not isinstance(quote, str) or not quote or not 0 <= start < end <= len(text) or text[start:end] != quote:
                    raise ValueError("Invalid counterevidence")
            challenges.setdefault(fid, []).append({**judgment, "scope": cross.get("scope", "未声明")})
    output = root / "human-review"
    output.mkdir(exist_ok=True)
    columns = ["case_id", "finding_id", "perspective", "ai_severity", "ai_issue", "evidence", "ai_cross_decision", "ai_cross_reason", "ai_cross_correction", "reviewer", "decision", "human_severity", "legal_source", "correction", "notes"]
    with (output / "adjudication-template.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        # Protect spreadsheet users from formula injection in externally sourced cells.
        for row in rows:
            cross_items = challenges.get(row["finding_id"], [])
            row = {**row, "ai_cross_decision": " | ".join(c["decision"] for c in cross_items), "ai_cross_reason": " | ".join(c["reason"] for c in cross_items), "ai_cross_correction": " | ".join(c.get("suggested_correction", "") for c in cross_items)}
            writer.writerow({key: ("'" + str(value) if str(value).lstrip().startswith(("=", "+", "-", "@")) else value) for key, value in row.items()})
    esc = lambda value: html.escape(" / ".join(str(x) for x in value) if isinstance(value, list) else str(value), quote=True)
    sections: list[str] = []
    for case in cases:
        case_id = case["id"]
        original = local_path(root, case["original_path"])
        sanitized = local_path(root, case["sanitized_path"])
        if case.get("sha256") and case["sha256"] != digest(original):
            raise ValueError(f"Changed original: {case_id}")
        if case.get("sanitized_sha256") and case["sanitized_sha256"] != digest(sanitized):
            raise ValueError(f"Changed sanitized input: {case_id}")
        reviews_here = case_reviews[case_id]
        cards: list[str] = []
        for review in reviews_here:
            cards.append(f'<p class="status">审核模式：{esc(review.get("review_mode", "unspecified"))} · 覆盖声明：{esc(coverage_text(review.get("coverage", "未声明")))}</p>')
            for finding in review["findings"]:
                evidence_html = "".join(f'<blockquote>{esc(entry["quote"])}<small>脱敏文本字符 [{entry["start"]}, {entry["end"]})</small></blockquote>' for entry in finding["evidence"])
                challenge_html = "".join(f'<aside><h4>独立 AI 交叉质询：{esc(c["decision"])}</h4><p>{esc(c["reason"])}</p><p>修正建议：{esc(c.get("suggested_correction", ""))}</p>' + "".join(f'<blockquote>{esc(e["quote"])}<small>反证 [{e["start"]}, {e["end"]})</small></blockquote>' for e in c["counterevidence"]) + f'<details><summary>本轮范围及限制</summary>{esc(c["scope"])}</details></aside>' for c in challenges.get(finding["id"], []))
                cards.append(f'''<article data-finding="{esc(finding['id'])}" data-case="{esc(case_id)}">
<h3>{esc(finding['id'])} · {esc(finding.get('severity',''))} · {esc(finding.get('perspective',''))}</h3>
<p>{esc(finding.get('risk',''))}</p>{evidence_html}
<p><b>影响：</b>{esc(finding.get('impact',''))}</p>
<p><b>修改方向：</b>{esc(finding.get('suggestion',''))}</p>
<p><b>依据及待核实：</b>{esc(json.dumps(finding.get('basis', []), ensure_ascii=False))}</p>
<p><b>事实问题：</b>{esc(json.dumps(finding.get('questions', []), ensure_ascii=False))}</p>
{challenge_html}
<label>人工裁定 <select data-field="decision"><option value="">未裁定</option><option>支持</option><option>部分支持</option><option>不支持</option><option>待补事实</option></select></label>
<label>人工风险等级 <select data-field="severity"><option value="">未裁定</option><option>critical</option><option>high</option><option>medium</option><option>low</option><option>info</option></select></label>
<label>法源、修正意见与理由<textarea data-field="notes"></textarea></label></article>''')
        sections.append(f'''<section id="{esc(case_id)}"><h2>{esc(case_id)} — {esc(case.get('title',''))}</h2>
<p>{esc(case.get('domain',''))} · {esc(case.get('language',''))} · {esc(case.get('scope',''))}</p>
<p><a href="../{esc(original.relative_to(root).as_posix())}">原始公开文件</a> · <a href="../{esc(sanitized.relative_to(root).as_posix())}">审核所用脱敏文本</a></p>
<p>原件 SHA256：<code>{digest(original)}</code></p>
{''.join(cards) if cards else '<p class="status">尚未执行 AI 审核；不能视作无风险。</p>'}
<label>人工新增遗漏、整体评价、附件/提取问题<textarea data-case-note="{esc(case_id)}"></textarea></label></section>''')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>公开合同 · 人类专家复核台</title><style>
body{max-width:1100px;margin:35px auto;padding:0 22px;font:16px/1.65 system-ui;color:#172638;background:#f5f7fa}h1,h2,h3{line-height:1.35}section,header{background:white;padding:24px;margin:24px 0;border-radius:12px}article{border-top:2px solid #dbe3ec;padding:20px 0}blockquote{border-left:4px solid #527ba4;margin:12px 0;padding:12px;background:#f1f5fa;white-space:pre-wrap}small{display:block;color:#53677d}label{display:block;margin:12px 0}textarea{display:block;width:98%;min-height:85px}select,input,button{font:inherit;padding:7px}button{cursor:pointer;background:#173f6c;color:white;border:0;border-radius:6px}.status{color:#875114}code{word-break:break-all}a{color:#174f8b}
</style><header><h1>公开合同 · 人类专家复核台</h1>
<p>AI 初评待专业裁定。公开示范文本不自动构成适合当前交易的完整合同；空白和待选项不应一律判为缺陷。请核对原件、我方立场、适用日期和附件。</p>
<p>本页离线运行，不向服务器发送数据。编辑内容只保留在当前页面内存，刷新前请导出。可先独立审阅原件，再阅读 AI 意见，减少锚定偏差。</p>
<label>复核人代号 <input id="reviewer" placeholder="不必填写真实姓名"></label><button id="export">导出人工裁定 JSON</button>
<p>建议两位专家分别导出，随后仲裁分歧。未填项保持未裁定；页面不会自动计算法律准确率。</p></header>'''
    script = '''<script>
document.getElementById('export').addEventListener('click',()=>{
 const judgments=[...document.querySelectorAll('article[data-finding]')].map(el=>({case_id:el.dataset.case,finding_id:el.dataset.finding,...Object.fromEntries([...el.querySelectorAll('[data-field]')].map(x=>[x.dataset.field,x.value]))}));
 const case_notes=[...document.querySelectorAll('[data-case-note]')].map(el=>({case_id:el.dataset.caseNote,notes:el.value}));
 const report={schema_version:1,reviewer:document.getElementById('reviewer').value,exported_at:new Date().toISOString(),package_manifest:PACKAGE,judgments,case_notes};
 const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='human-adjudication.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});</script></html>'''
    manifest = {"schema_version": 1, "cases": len(cases), "review_records": len(reviews), "findings": len(rows), "cross_reviewed_findings": len(challenges), "quote_validation": "passed", "human_adjudication": "pending", "manifest_sha256": digest(root / "manifest.json"), "review_files": {path.name: digest(path) for path in sorted((root / "reviews").glob("*.json"))}, "cross_review_files": {path.name: digest(path) for path in cross_files}}
    script = script.replace("PACKAGE", json.dumps(manifest).replace("<", "\\u003c"))
    nav = '<nav>跳转合同：' + ' · '.join(f'<a href="#{esc(case["id"])}">{esc(case["id"])} {esc(case.get("domain", ""))}</a>' for case in cases) + '</nav>'
    (output / "index.html").write_text(page + nav + "".join(sections) + script, encoding="utf-8")
    (output / "validation.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(build(args.root.resolve()), ensure_ascii=False))
