#!/usr/bin/env python3
"""Offline preparation and declared-coverage validation. No model/network calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
import zipfile
import importlib.util
import xml.etree.ElementTree as ET

ROLES = ["legal", "dispute", "finance", "business", "compliance", "language"]
LEVELS = ["char", "word", "sentence", "paragraph", "context"]
TOKEN = re.compile(r"⟦[A-Z][A-Z0-9_]*_\d{4,}⟧")
RULES = [
    ("ID", re.compile(r"(?<![0-9A-Za-z])\d{17}[0-9Xx](?![0-9A-Za-z])")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+86[- ]?)?1[3-9]\d{9}(?!\d)")),
    ("EMAIL", re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("CREDIT", re.compile(r"(?<![0-9A-Z])[159Y][1239]\d{6}[0-9A-HJ-NPQRTUWXY]{10}(?![0-9A-Z])")),
    ("ACCOUNT", re.compile(r"(?<!\d)\d{12,19}(?!\d)")),
]
NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def input_capabilities(paths: list[Path], pdf_available: bool | None = None) -> dict:
    """Metadata-only preflight. Never install software or read contract content."""
    if pdf_available is None:
        pdf_available = importlib.util.find_spec("pypdf") is not None
    files = []
    for index, path in enumerate(paths, 1):
        suffix = path.suffix.lower()
        if not path.is_file():
            status, action = "INPUT_NOT_FOUND", "provide_existing_local_file"
        elif suffix in {".txt", ".md", ".docx"}:
            status, action = "READY", "local_extract_then_review"
        elif suffix == ".pdf":
            status, action = ("READY", "text_layer_only_then_visual_review") if pdf_available else ("PDF_REQUIRES_LOCAL_PYPDF", "offer_pypdf_or_local_export_to_docx_txt")
        else:
            status, action = "LOCAL_CONVERSION_REQUIRED", "export_locally_to_docx_or_utf8_txt"
        files.append({"source_index": index, "format": suffix if suffix in {".txt", ".md", ".docx", ".pdf", ".doc", ".rtf", ".odt", ".png", ".jpg", ".jpeg"} else "other", "status": status, "action": action})
    return {"python": sys.version.split()[0], "python_executable": sys.executable,
            "pypdf_available": pdf_available, "files": files,
            "ready_count": sum(f["status"] == "READY" for f in files),
            "note": "Preflight checks format/dependencies only; no automatic install or completeness certification."}


def doctor(args: argparse.Namespace) -> None:
    print(json.dumps(input_capabilities(args.input or [])))


class GateError(Exception):
    """Only static error codes are exposed to logs."""


def require(condition: object, code: str) -> None:
    if not condition:
        raise GateError(code)


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path: Path, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
        stream.write(text)


def write_json(path: Path, value: object) -> None:
    write_new(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def event(run: Path, stage: str, **counts: object) -> None:
    path = run / "audit.jsonl"
    require(not path.is_symlink(), "AUDIT_SYMLINK")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as stream:
        stream.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(),
                                 "stage": stage, **counts}) + "\n")


def xml_text(root: ET.Element) -> str:
    out: list[str] = []
    # Paragraph descendants contain table cells, including nested tables.
    # Walk once to avoid double-emitting text inside nested text boxes.
    def walk(node: ET.Element) -> None:
        if node.tag in {NS + "t", NS + "delText", NS + "instrText"}:
            out.append(node.text or "")
        elif node.tag == NS + "tab":
            out.append("\t")
        elif node.tag in {NS + "br", NS + "cr"}:
            out.append("\n")
        for child in node:
            walk(child)
        if node.tag == NS + "p":
            out.append("\n")
        elif node.tag == NS + "tc":
            out.append("\t")
    walk(root)
    return "".join(out)


def extract(path: Path) -> tuple[list[tuple[str, str]], list[str]]:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return [("text", path.read_bytes().decode("utf-8"))], []
    if suffix == ".docx":
        parts: list[tuple[str, str]] = []
        warnings = ["DOCX_VISUAL_LAYOUT_REQUIRES_LOCAL_REVIEW"]
        with zipfile.ZipFile(path) as archive:
            require(sum(i.file_size for i in archive.infolist()) < 100_000_000,
                    "DOCX_TOO_LARGE")
            names = archive.namelist()
            require("word/document.xml" in names, "DOCX_MAIN_MISSING")
            targets = ["word/document.xml"] + sorted(n for n in names if re.fullmatch(
                r"word/(?:header\d+|footer\d+|footnotes|endnotes|comments)\.xml", n))
            for name in targets:
                raw = archive.read(name)
                require(b"<!DOCTYPE" not in raw and b"<!ENTITY" not in raw, "XML_DTD_REJECTED")
                root = ET.fromstring(raw)
                flags = {n.tag.rsplit("}", 1)[-1] for n in root.iter()}
                if flags & {"drawing", "pict", "object", "txbxContent", "ins", "del",
                            "fldChar", "instrText", "altChunk", "vanish"}:
                    warnings.append("DOCX_IMAGES_REVISIONS_FIELDS_OR_HIDDEN_CONTENT")
                value = xml_text(root)
                if value.strip():
                    parts.append((name, value))
        return parts, sorted(set(warnings))
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise GateError("PDF_REQUIRES_LOCAL_PYPDF") from exc
        from pypdf.errors import PyPdfError
        try:
            reader = PdfReader(path)
            require(not reader.is_encrypted, "PDF_ENCRYPTED")
            parts = []
            for index, page in enumerate(reader.pages, 1):
                value = page.extract_text() or ""
                require(value.strip(), "PDF_EMPTY_PAGE_LOCAL_OCR_OR_REVIEW_REQUIRED")
                parts.append((f"page:{index}", value))
        except PyPdfError as exc:
            raise GateError("PDF_PARSE_FAILED") from exc
        return parts, ["PDF_TEXT_LAYER_VISUAL_REVIEW_REQUIRED"]
    raise GateError("UNSUPPORTED_FORMAT_LOCAL_CONVERSION_REQUIRED")


def load_entities(path: Path | None) -> list[tuple[str, str]]:
    if path is None:
        return []
    value = read_json(path)
    require(isinstance(value, dict) and isinstance(value.get("entities"), list), "ENTITY_SCHEMA")
    entities: dict[str, str] = {}
    for item in value["entities"]:
        require(isinstance(item, dict), "ENTITY_SCHEMA")
        literal, kind = item.get("value"), item.get("type")
        require(isinstance(literal, str) and literal.strip(), "ENTITY_EMPTY")
        require(isinstance(kind, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,30}", kind), "ENTITY_TYPE")
        require(literal not in entities or entities[literal] == kind, "ENTITY_TYPE_CONFLICT")
        entities[literal] = kind
    return list(entities.items())


def redact(text: str, entities: list[tuple[str, str]], registry: dict[str, dict],
           doc_id: str) -> tuple[str, list[dict]]:
    require(not TOKEN.search(text), "SOURCE_TOKEN_COLLISION")
    matches: list[tuple[int, int, str, str]] = []
    for literal, kind in entities:
        for match in re.finditer(re.escape(literal), text):
            matches.append((match.start(), match.end(), kind, literal))
    for kind, regex in RULES:
        for match in regex.finditer(text):
            matches.append((match.start(), match.end(), kind, match.group()))
    # Select longest first even where a shorter match begins earlier.
    selected: list[tuple[int, int, str, str]] = []
    for item in sorted(matches, key=lambda m: (-(m[1] - m[0]), m[0])):
        if not any(item[0] < previous[1] and previous[0] < item[1] for previous in selected):
            selected.append(item)
    output: list[str] = []
    occurrences: list[dict] = []
    cursor, size = 0, 0
    for start, end, kind, literal in sorted(selected):
        output.append(text[cursor:start])
        size += start - cursor
        if literal not in registry:
            registry[literal] = {"token": f"⟦{kind}_{len(registry) + 1:04d}⟧", "value": literal, "type": kind}
        token = registry[literal]["token"]
        output.append(token)
        occurrences.append({"document_id": doc_id, "token": token, "original_start": start,
                            "original_end": end, "redacted_start": size,
                            "redacted_end": size + len(token)})
        cursor, size = end, size + len(token)
    output.append(text[cursor:])
    return "".join(output), occurrences


def segments_for(doc_id: str, text: str) -> list[dict]:
    result: list[dict] = []
    cursor = 0
    for line in text.splitlines(keepends=True):
        remaining = line
        while remaining:
            end = min(3000, len(remaining))
            for match in TOKEN.finditer(remaining):
                if match.start() < end < match.end():
                    end = match.end()
                    break
            part = remaining[:end]
            result.append({"id": f"{doc_id}-S{len(result)+1:05d}", "document_id": doc_id,
                           "start": cursor, "end": cursor + len(part), "text": part})
            cursor += len(part)
            remaining = remaining[end:]
    require("".join(s["text"] for s in result) == text, "SEGMENT_LOSS")
    return result


def prepare(args: argparse.Namespace) -> None:
    run = args.run
    require(not run.exists(), "RUN_ALREADY_EXISTS")
    entities = load_entities(args.entities)
    run.mkdir(mode=0o700, parents=True)
    for sub in ("private", "reports"):
        (run / sub).mkdir(mode=0o700)
    registry: dict[str, dict] = {}
    occurrences: list[dict] = []
    documents, segments, sources = [], [], []
    gaps = []
    for source_index, path in enumerate(args.input, 1):
        try:
            parts, warnings = extract(path)
            require(parts and all(original.strip() for _, original in parts), "EMPTY_DOCUMENT")
        except (GateError, OSError, ValueError, zipfile.BadZipFile) as exc:
            code = str(exc) if isinstance(exc, GateError) else "INPUT_UNREADABLE_OR_MALFORMED"
            gaps.append({"source_index": source_index, "code": code})
            continue
        for label, original in parts:
            require(original.strip(), "EMPTY_DOCUMENT")
            doc_id = f"DOC{len(documents)+1:04d}"
            redacted, spans = redact(original, entities, registry, doc_id)
            occurrences.extend(spans)
            write_new(run / "private" / f"source-{len(documents)+1:04d}.txt", original)
            documents.append({"id": doc_id, "source_index": source_index,
                              "part": label, "text": redacted, "warnings": warnings})
            segments.extend(segments_for(doc_id, redacted))
        sources.append({"source_index": source_index, "path": str(path.resolve()),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "warnings": warnings})
    bundle = {"schema_version": 1, "roles": ROLES, "levels": LEVELS,
              "documents": documents, "segments": segments}
    if gaps:
        write_json(run / "private" / "input-errors.json", [{**gap, "path": str(args.input[gap["source_index"] - 1].resolve())} for gap in gaps])
        bundle["input_gaps"] = gaps
    require(documents, "NO_PROCESSABLE_INPUTS_SEE_LOCAL_INPUT_ERRORS")
    bundle["input_digest"] = digest(bundle)
    write_json(run / "private" / "candidate.json", bundle)
    mapping = {"entities": list(registry.values()), "occurrences": occurrences}
    write_json(run / "private" / "mapping.json", mapping)
    write_json(run / "private" / "extraction.json", {"sources": sources,
               "candidate_digest": digest(bundle), "mapping_digest": digest(mapping),
               "entity_source": ({"path": str(args.entities.resolve()),
                   "sha256": hashlib.sha256(args.entities.read_bytes()).hexdigest()}
                   if args.entities else None), "requires_local_review": True})
    event(run, "PREPARED_PRIVATE", documents=len(documents), segments=len(segments), entities=len(registry))
    print(json.dumps({"status": "PREPARED_PRIVATE", "documents": len(documents),
                      "segments": len(segments), "entities": len(registry), "local_review_required": True,
                      "unprocessed_inputs": len(gaps)}))


def check_bundle(bundle: dict) -> None:
    require(isinstance(bundle, dict), "BUNDLE_SCHEMA")
    payload = {key: value for key, value in bundle.items() if key != "input_digest"}
    require(bundle.get("input_digest") == digest(payload), "BUNDLE_DIGEST_MISMATCH")
    require(bundle.get("roles") == ROLES and bundle.get("levels") == LEVELS, "BUNDLE_POLICY_MISMATCH")
    require(bundle.get("documents") and bundle.get("segments"), "EMPTY_BUNDLE")
    require(isinstance(bundle.get("input_gaps", []), list) and all(isinstance(g, dict) and type(g.get("source_index")) is int
            and g["source_index"] > 0 and nonempty(g.get("code")) for g in bundle.get("input_gaps", [])), "INPUT_GAPS_SCHEMA")


def release(args: argparse.Namespace) -> None:
    require(args.attest_extraction_reviewed and args.attest_privacy_reviewed, "LOCAL_REVIEW_REQUIRED")
    run = args.run
    bundle = read_json(run / "private" / "candidate.json")
    check_bundle(bundle)
    meta = read_json(run / "private" / "extraction.json")
    require(meta["candidate_digest"] == digest(bundle), "CANDIDATE_CHANGED_REPREPARE")
    for source in meta["sources"] + ([meta["entity_source"]] if meta["entity_source"] else []):
        require(hashlib.sha256(Path(source["path"]).read_bytes()).hexdigest() == source["sha256"],
                "SOURCE_CHANGED_REPREPARE")
    require(digest(read_json(run / "private" / "mapping.json")) == meta["mapping_digest"],
            "MAPPING_CHANGED_REPREPARE")
    require(not (run / "public").exists(), "ALREADY_RELEASED")
    (run / "public").mkdir(mode=0o700)
    write_json(run / "public" / "bundle.json", bundle)
    event(run, "RELEASED", input_digest=bundle["input_digest"], extraction_reviewed=True, privacy_reviewed=True)
    print('{"status":"RELEASED"}')


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def contains_private_value(value: object, literals: list[str]) -> bool:
    """Inspect decoded JSON strings, including keys; serialized escapes hide literals."""
    if isinstance(value, str):
        return any(literal in value for literal in literals)
    if isinstance(value, dict):
        return any(contains_private_value(key, literals) or contains_private_value(item, literals)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(contains_private_value(item, literals) for item in value)
    return False


def validate_results(bundle: dict, results: list[dict], plan: dict | None = None) -> dict:
    check_bundle(bundle)
    from expert_plan import assess as assess_plan
    expected_roles = set(ROLES if plan is None else assess_plan(bundle, plan)["roles"])
    segments = {s["id"]: s for s in bundle["segments"]}
    documents = {d["id"]: d["text"] for d in bundle["documents"]}
    require(len(segments) == len(bundle["segments"]), "DUPLICATE_BUNDLE_SEGMENT")
    roles: set[str] = set()
    finding_ids: set[str] = set()
    for result in results:
        require(isinstance(result, dict), "RESULT_SCHEMA")
        role = result.get("role")
        require(isinstance(role, str) and role in expected_roles and role not in roles, "ROLE_INVALID_OR_DUPLICATE")
        roles.add(role)
        if plan is not None:
            require(result.get("plan_digest") == digest(plan), "RESULT_STALE_PLAN")
        require(result.get("input_digest") == bundle["input_digest"], "STALE_RESULT")
        require(result.get("global_context_reviewed") is True and nonempty(result.get("global_note")), "GLOBAL_REVIEW_MISSING")
        require(isinstance(result.get("reviews"), list), "REVIEWS_SCHEMA")
        reviewed: set[str] = set()
        for review in result["reviews"]:
            require(isinstance(review, dict), "REVIEW_SCHEMA")
            sid = review.get("segment_id")
            require(isinstance(sid, str) and sid in segments and sid not in reviewed, "SEGMENT_INVALID_OR_DUPLICATE")
            reviewed.add(sid)
            require(isinstance(review.get("levels"), list) and sorted(review["levels"]) == sorted(LEVELS), "LEVEL_COVERAGE_MISSING")
            require(nonempty(review.get("review_note")), "REVIEW_NOTE_MISSING")
        require(reviewed == set(segments), "SEGMENT_COVERAGE_MISSING")
        require(isinstance(result.get("findings"), list), "FINDINGS_SCHEMA")
        for finding in result["findings"]:
            require(isinstance(finding, dict), "FINDING_SCHEMA")
            fid = finding.get("id")
            require(nonempty(fid) and fid not in finding_ids, "FINDING_ID_INVALID")
            finding_ids.add(fid)
            require(finding.get("severity") in {"critical", "high", "medium", "low", "info"}, "SEVERITY_INVALID")
            require(finding.get("confidence") in {"high", "medium", "low"}, "CONFIDENCE_INVALID")
            require(all(nonempty(finding.get(key)) for key in ("risk", "impact", "suggestion", "category")), "FINDING_FIELDS_MISSING")
            evidence = finding.get("evidence")
            require(isinstance(evidence, list) and evidence, "EVIDENCE_MISSING")
            for quote in evidence:
                require(isinstance(quote, dict), "EVIDENCE_SCHEMA")
                sid = quote.get("segment_id")
                require(isinstance(sid, str) and sid in segments, "EVIDENCE_SEGMENT_INVALID")
                start, end = quote.get("start"), quote.get("end")
                seg = segments[sid]
                require(type(start) is int and type(end) is int and seg["start"] <= start < end <= seg["end"], "EVIDENCE_OFFSET_INVALID")
                require(quote.get("quote") == documents[seg["document_id"]][start:end], "EVIDENCE_QUOTE_MISMATCH")
            require(isinstance(finding.get("basis"), list), "BASIS_SCHEMA")
            for basis in finding["basis"]:
                require(isinstance(basis, dict) and basis.get("status") in {"verified", "unverified", "not_applicable"}, "BASIS_STATUS_INVALID")
                if basis["status"] == "verified":
                    require(all(nonempty(basis.get(k)) for k in ("title", "article", "url", "checked_at", "applicability")), "BASIS_FIELDS_MISSING")
                    require(basis["url"].startswith("https://"), "BASIS_URL_INVALID")
            require(isinstance(finding.get("questions"), list) and all(nonempty(q) for q in finding["questions"]), "QUESTIONS_SCHEMA")
    require(roles == expected_roles, "ROLE_COVERAGE_MISSING")
    return {"status": "VALIDATED_DECLARED_COVERAGE", "roles": len(roles), "segments": len(segments),
            "checks": len(roles) * len(segments) * len(LEVELS), "findings": len(finding_ids)}


def load_results(args: argparse.Namespace) -> tuple[dict, list[dict], dict]:
    bundle = read_json(args.run / "public" / "bundle.json")
    require(digest(bundle) == read_json(args.run / "private" / "extraction.json")["candidate_digest"], "RELEASED_BUNDLE_CHANGED")
    results = [read_json(path) for path in args.results]
    plan_path = getattr(args, "plan", None)
    plan = read_json(plan_path) if plan_path is not None else None
    if plan is not None:
        from expert_plan import check_active
        check_active(args.run, bundle, plan)
    summary = validate_results(bundle, results, plan)
    mapping = read_json(args.run / "private" / "mapping.json")
    require(digest(mapping) == read_json(args.run / "private" / "extraction.json")["mapping_digest"],
            "MAPPING_CHANGED_REPREPARE")
    require(not contains_private_value([results, plan], [item["value"] for item in mapping["entities"]]),
            "RESULT_CONTAINS_KNOWN_PRIVATE_VALUE")
    return bundle, results, summary


def validate(args: argparse.Namespace) -> None:
    _, _, summary = load_results(args)
    event(args.run, "RESULTS_VALIDATED", **summary)
    print(json.dumps(summary))


def report(args: argparse.Namespace) -> None:
    bundle, results, summary = load_results(args)
    depth_path = getattr(args, "depth", None)
    if depth_path is not None:
        from validate_depth import load_depth
        depth_summary = load_depth(args.run, depth_path, bundle,
                                   read_json(args.plan) if getattr(args, "plan", None) else None, results)
    else:
        depth_summary = {"status": "PARTIAL_AUDIT", "blockers": ["DEPTH_NOT_VALIDATED"]}
    lines = ["# 合同审核初稿（脱敏）", "", "状态：待主 agent 交叉核验、争议裁决及法源核实。",
             "深度审核状态：" + depth_summary["status"],
             "深度审核缺口：" + (", ".join(depth_summary["blockers"]) or "申报门禁无缺口；不证明法律或风险穷尽。"),
             "", f"输入摘要：{bundle['input_digest']}",
             f"声明覆盖：{summary['roles']} 角色 × {summary['segments']} 片段 × 5 层。",
             "覆盖表示提交了审阅记录，不保证风险零遗漏。", "",
             "## 提取与脱敏局限", "", "真实主体已隐藏，资质及关联关系待本地核实；遮盖数字不得用于猜测计算。"]
    for doc in bundle["documents"]:
        for warning in doc["warnings"]:
            lines.append(f"- {doc['id']}: {warning}")
    for gap in bundle.get("input_gaps", []):
        lines.append(f"- 未处理输入 #{gap['source_index']}：{gap['code']}；本报告不覆盖此文件及其可能影响。")
    ranks = {level: i for i, level in enumerate(("critical", "high", "medium", "low", "info"))}
    findings = [(r["role"], f) for r in results for f in r["findings"]]
    for role, finding in sorted(findings, key=lambda pair: ranks[pair[1]["severity"]]):
        lines.extend(["", f"## {finding['id']} [{finding['severity']}] ({role})", ""])
        for evidence in finding["evidence"]:
            lines.append(f"- 证据 {evidence['segment_id']} [{evidence['start']},{evidence['end']}): {evidence['quote']}")
        for key, label in (("risk", "风险"), ("impact", "后果"), ("suggestion", "建议"), ("confidence", "置信度")):
            lines.append(f"- {label}：{finding[key]}")
        for basis in finding["basis"]:
            lines.append(f"- 依据（{basis['status']}）：{basis.get('title', '')} {basis.get('article', '')} {basis.get('url', '')}；核实日 {basis.get('checked_at', '')}；{basis.get('applicability', '')}")
        for question in finding["questions"]:
            resolutions = finding.get("question_resolutions", [])
            resolved = next((r for r in resolutions if r.get("question") == question and r.get("status") == "resolved"), None)
            if resolved is not None:
                lines.append(f"- 声明已解决：{question}；{resolved.get('reason', '')}；证据 {resolved.get('evidence_refs', [])}")
            else:
                lines.append(f"- 待确认：{question}")
    lines.extend(["", "## 全文复核记录", ""])
    for result in results:
        lines.append(f"- {result['role']}: {result['global_note']}")
    if not findings:
        lines.extend(["", "本轮未报告风险，不构成无风险或可签署结论。"])
    write_new(args.run / "reports" / "report.md", "\n".join(lines) + "\n")
    event(args.run, "DRAFT_REPORT_CREATED", findings=len(findings))
    print('{"status":"DRAFT_REPORT_CREATED"}')


def restore(args: argparse.Namespace) -> None:
    private = (args.run / "private").resolve()
    require(args.output.parent.resolve() == private, "RESTORE_OUTPUT_MUST_BE_PRIVATE")
    mapping = read_json(private / "mapping.json")
    require(digest(mapping) == read_json(private / "extraction.json")["mapping_digest"],
            "MAPPING_CHANGED_REPREPARE")
    lookup = {item["token"]: item["value"] for item in mapping["entities"]}
    value = args.input.read_bytes().decode("utf-8")
    require(all(m.group() in lookup for m in TOKEN.finditer(value)), "UNKNOWN_RESTORE_TOKEN")
    restored = TOKEN.sub(lambda match: lookup[match.group()], value)
    write_new(args.output, restored)
    event(args.run, "RESTORED_LOCAL_COPY")
    print('{"status":"RESTORED_LOCAL_COPY"}')


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    probe = commands.add_parser("doctor", help="Read-only optional dependencies and input format check")
    probe.add_argument("--input", type=Path, action="append")
    for name in ("prepare", "release", "validate", "report", "restore"):
        sub = commands.add_parser(name)
        sub.add_argument("--run", type=Path, required=True)
        if name == "prepare":
            sub.add_argument("--input", type=Path, action="append", required=True)
            sub.add_argument("--entities", type=Path)
        if name == "release":
            sub.add_argument("--attest-extraction-reviewed", action="store_true")
            sub.add_argument("--attest-privacy-reviewed", action="store_true")
        if name in {"validate", "report"}:
            sub.add_argument("--results", type=Path, nargs="+", required=True)
            sub.add_argument("--plan", type=Path)
        if name == "report":
            sub.add_argument("--depth", type=Path)
        if name == "restore":
            sub.add_argument("--input", type=Path, required=True)
            sub.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        globals()[args.command](args)
        return 0
    except GateError as exc:
        print(json.dumps({"status": "FAILED", "code": str(exc)}), file=sys.stderr)
        return 2
    except Exception:
        # Exception messages can contain raw text, filenames, and private values.
        print('{"status":"FAILED","code":"LOCAL_IO_OR_SCHEMA_ERROR"}', file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
