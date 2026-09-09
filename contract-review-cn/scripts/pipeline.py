#!/usr/bin/env python3
"""Offline preparation and declared-coverage validation. No model/network calls."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
from datetime import date, datetime, timezone
from urllib.parse import urlparse
import tempfile
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


def extract(path: Path, data: bytes | None = None) -> tuple[list[tuple[str, str]], list[str]]:
    data = path.read_bytes() if data is None else data
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return [("text", data.decode("utf-8"))], []
    if suffix == ".docx":
        parts: list[tuple[str, str]] = []
        warnings = ["DOCX_VISUAL_LAYOUT_REQUIRES_LOCAL_REVIEW"]
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            require(sum(i.file_size for i in archive.infolist()) < 100_000_000,
                    "DOCX_TOO_LARGE")
            names = archive.namelist()
            require("word/document.xml" in names, "DOCX_MAIN_MISSING")
            targets = ["word/document.xml"] + sorted(n for n in names if re.fullmatch(
                r"word/(?:header\d+|footer\d+|footnotes|endnotes|comments)\.xml", n))
            for name in targets:
                raw = archive.read(name)
                require(b"<!DOCTYPE" not in raw and b"<!ENTITY" not in raw, "XML_DTD_REJECTED")
                try:
                    root = ET.fromstring(raw)
                except ET.ParseError as exc:
                    raise GateError("DOCX_XML_PARSE_FAILED") from exc
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
            reader = PdfReader(io.BytesIO(data))
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


def load_entities(path: Path | None, data: bytes | None = None) -> list[tuple[str, str]]:
    if path is None:
        return []
    value = json.loads((path.read_bytes() if data is None else data).decode("utf-8"))
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
    coordinates = {value: index for index, value in enumerate(sorted(
        {position for match in matches for position in match[:2]}))}
    starts = [0] * (len(coordinates) + 1)
    ends = [0] * (len(coordinates) + 1)

    def prefix(tree: list[int], stop: int) -> int:
        total = 0
        while stop:
            total += tree[stop]
            stop -= stop & -stop
        return total

    def add(tree: list[int], index: int) -> None:
        index += 1
        while index < len(tree):
            tree[index] += 1
            index += index & -index

    for item in sorted(matches, key=lambda m: (-(m[1] - m[0]), m[0])):
        start_index, end_index = coordinates[item[0]], coordinates[item[1]]
        # Half-open intervals overlap iff starts before end exceed ends at/before start.
        if prefix(starts, end_index) == prefix(ends, start_index + 1):
            selected.append(item)
            add(starts, start_index)
            add(ends, end_index)
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
        start = 0
        tokens = iter(TOKEN.finditer(line))
        token = next(tokens, None)
        while start < len(line):
            end = min(start + 3000, len(line))
            while token is not None and token.end() <= end:
                token = next(tokens, None)
            if token is not None and token.start() < end < token.end():
                end = token.end()
            part = line[start:end]
            result.append({"id": f"{doc_id}-S{len(result)+1:05d}", "document_id": doc_id,
                           "start": cursor, "end": cursor + len(part), "text": part})
            cursor += len(part)
            start = end
    require("".join(s["text"] for s in result) == text, "SEGMENT_LOSS")
    return result


def prepare(args: argparse.Namespace) -> None:
    run = args.run
    require(not run.exists(), "RUN_ALREADY_EXISTS")
    entity_data = args.entities.read_bytes() if args.entities else None
    entities = load_entities(args.entities, entity_data)
    run.mkdir(mode=0o700, parents=True)
    for sub in ("private", "reports"):
        (run / sub).mkdir(mode=0o700)
    registry: dict[str, dict] = {}
    occurrences: list[dict] = []
    documents, segments, sources = [], [], []
    gaps = []
    for source_index, path in enumerate(args.input, 1):
        try:
            source_data = path.read_bytes()
            parts, warnings = extract(path, source_data)
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
                        "sha256": hashlib.sha256(source_data).hexdigest(), "warnings": warnings})
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
                   "sha256": hashlib.sha256(entity_data).hexdigest()}
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
    # No public artifact until all fallible preparation and audit writes succeed.
    # The receipt moves atomically with the bundle and is the commit record.
    with tempfile.TemporaryDirectory(prefix="release-", dir=run / "private") as temporary:
        staged = Path(temporary) / "public"
        staged.mkdir(mode=0o700)
        write_json(staged / "bundle.json", bundle)
        write_json(staged / "release.json", {"status": "RELEASED", "input_digest": bundle["input_digest"]})
        event(run, "RELEASE_COMMIT_READY", input_digest=bundle["input_digest"],
              extraction_reviewed=True, privacy_reviewed=True)
        staged.rename(run / "public")
    print('{"status":"RELEASED"}')


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def valid_date(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def https(value: object) -> bool:
    if not isinstance(value, str) or any(char.isspace() for char in value):
        return False
    try:
        parsed = urlparse(value)
        return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and parsed.port != 0
    except ValueError:
        return False


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
    teams = assess_plan(bundle, plan)["teams"] if plan is not None else {}
    contexts: set[str] = set()
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
        if teams:
            require(result.get("team") == teams[role], "RESULT_TEAM_MISMATCH")
            first = result.get("first_pass")
            require(isinstance(first, dict), "FIRST_PASS_REQUIRED")
            context_id = first.get("context_id")
            require(nonempty(context_id) and context_id not in contexts, "FIRST_PASS_CONTEXT_NOT_INDEPENDENT")
            contexts.add(context_id)
            require(first.get("other_results_read") == [], "FIRST_PASS_CONTAMINATED")
            require(first.get("input_digest") == bundle["input_digest"] and
                    first.get("plan_digest") == digest(plan), "FIRST_PASS_STALE")
            ids = first.get("segment_ids")
            require(isinstance(ids, list) and all(isinstance(s, str) for s in ids) and
                    len(ids) == len(set(ids)) and set(ids) == set(segments), "FIRST_PASS_COVERAGE")
            require(nonempty(first.get("summary")), "FIRST_PASS_SUMMARY_REQUIRED")
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
                    require(https(basis["url"]), "BASIS_URL_INVALID")
                    require(valid_date(basis["checked_at"]), "BASIS_DATE_INVALID")
            require(isinstance(finding.get("questions"), list) and all(nonempty(q) for q in finding["questions"]), "QUESTIONS_SCHEMA")
            validate_question_resolutions(finding)
    require(roles == expected_roles, "ROLE_COVERAGE_MISSING")
    return {"status": "VALIDATED_DECLARED_COVERAGE", "roles": len(roles), "segments": len(segments),
            "checks": len(roles) * len(segments) * len(LEVELS), "findings": len(finding_ids)}


def validate_question_resolutions(finding: dict, allowed_refs: set[str] | None = None) -> set[str]:
    resolutions = finding.get("question_resolutions", [])
    require(isinstance(resolutions, list), "QUESTION_RESOLUTIONS_SCHEMA")
    resolved: set[str] = set()
    for resolution in resolutions:
        require(isinstance(resolution, dict), "QUESTION_RESOLUTION_INVALID")
        question, refs = resolution.get("question"), resolution.get("evidence_refs")
        require(nonempty(question) and question in finding.get("questions", []) and question not in resolved
                and resolution.get("status") == "resolved" and nonempty(resolution.get("reason"))
                and isinstance(refs, list) and refs and all(nonempty(ref) for ref in refs)
                and len(refs) == len(set(refs)), "QUESTION_RESOLUTION_INVALID")
        if allowed_refs is not None:
            require(set(refs) <= allowed_refs, "QUESTION_RESOLUTION_INVALID")
        resolved.add(question)
    return resolved


def markdown_text(value: object) -> str:
    """Render untrusted data as one inert Markdown text field."""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    # Keep generated placeholders byte-identical so local restore still works.
    def escape(fragment: str) -> str:
        return re.sub(r"([\\`*_{}\[\]()<>#+.!|&~=:])", r"\\\1", fragment)

    parts = []
    cursor = 0
    for token in TOKEN.finditer(text):
        parts.append(escape(text[cursor:token.start()]))
        parts.append(token.group())
        cursor = token.end()
    parts.append(escape(text[cursor:]))
    return "".join(parts).replace("\n", " ⏎ ")


def load_results(args: argparse.Namespace) -> tuple[dict, list[dict], dict]:
    bundle = read_json(args.run / "public" / "bundle.json")
    require(digest(bundle) == read_json(args.run / "private" / "extraction.json")["candidate_digest"], "RELEASED_BUNDLE_CHANGED")
    results = [read_json(path) for path in args.results]
    plan_path = getattr(args, "plan", None)
    require(plan_path is not None or not (args.run / "private/active-plan.json").exists(),
            "ACTIVE_PLAN_REQUIRED")
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
    depth = None
    if depth_path is not None:
        from validate_depth import load_depth
        depth = read_json(depth_path)
        depth_summary = load_depth(args.run, depth_path, bundle,
                                   read_json(args.plan) if getattr(args, "plan", None) else None, results, depth)
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
            lines.append(f"- {markdown_text(doc['id'])}: {markdown_text(warning)}")
    for gap in bundle.get("input_gaps", []):
        lines.append(f"- 未处理输入 #{gap['source_index']}：{markdown_text(gap['code'])}；本报告不覆盖此文件及其可能影响。")
    ranks = {level: i for i, level in enumerate(("critical", "high", "medium", "low", "info"))}
    findings = [(r["role"], f) for r in results for f in r["findings"]]
    for role, finding in sorted(findings, key=lambda pair: ranks[pair[1]["severity"]]):
        lines.extend(["", f"## {markdown_text(finding['id'])} [{finding['severity']}] ({role})", ""])
        for evidence in finding["evidence"]:
            lines.append(f"- 证据 {markdown_text(evidence['segment_id'])} [{evidence['start']},{evidence['end']}): {markdown_text(evidence['quote'])}")
        for key, label in (("risk", "风险"), ("impact", "后果"), ("suggestion", "建议"), ("confidence", "置信度")):
            lines.append(f"- {label}：{markdown_text(finding[key])}")
        for basis in finding["basis"]:
            lines.append(f"- 依据（{basis['status']}）：{markdown_text(basis.get('title', ''))} {markdown_text(basis.get('article', ''))} {markdown_text(basis.get('url', ''))}；核实日 {markdown_text(basis.get('checked_at', ''))}；{markdown_text(basis.get('applicability', ''))}")
        for question in finding["questions"]:
            resolutions = finding.get("question_resolutions", [])
            resolved = next((r for r in resolutions if r.get("question") == question and r.get("status") == "resolved"), None)
            if resolved is not None and (depth_path is not None or
                    set(resolved["evidence_refs"]) <= {s["id"] for s in bundle["segments"]}):
                lines.append(f"- 声明已解决：{markdown_text(question)}；{markdown_text(resolved['reason'])}；证据 {markdown_text(resolved['evidence_refs'])}")
            else:
                lines.append(f"- 待确认：{markdown_text(question)}")
    lines.extend(["", "## 全文复核记录", ""])
    for result in results:
        lines.append(f"- {result['role']}: {markdown_text(result['global_note'])}")
    if depth and depth.get("cross_challenges"):
        lines.extend(["", "## 双组交叉质询", ""])
        for item in depth["cross_challenges"]:
            if not isinstance(item, dict):
                continue
            lines.append("- " + markdown_text(item.get("id", "")) + "：" +
                         markdown_text(item.get("author", "")) + " → " + markdown_text(item.get("target", "")))
            for key, label in (("angle", "领域"), ("question", "质询"), ("response", "回应"),
                               ("outcome", "裁定"), ("reason", "理由"), ("evidence_refs", "证据")):
                lines.append(f"  - {label}：{markdown_text(item.get(key, ''))}")
    if not findings:
        lines.extend(["", "本轮未报告风险，不构成无风险或可签署结论。"])
    text = "\n".join(lines) + "\n"
    revision = getattr(args, "revision", None)
    if revision is None:
        output = args.run / "reports" / "report.md"
        write_new(output, text)
        event(args.run, "DRAFT_REPORT_CREATED", findings=len(findings))
    else:
        require(type(revision) is int and 1 <= revision <= 999999, "REPORT_REVISION_INVALID")
        versions = args.run / "reports" / "versions"
        require(not versions.is_symlink(), "REPORT_VERSIONS_SYMLINK")
        versions.mkdir(mode=0o700, exist_ok=True)
        destination = versions / f"v{revision:06d}"
        require(not destination.exists(), "REPORT_REVISION_EXISTS")
        manifest = {"schema_version": 1, "revision": revision, "input_digest": bundle["input_digest"],
                    "results_digest": digest(results),
                    "plan_digest": results[0].get("plan_digest") if getattr(args, "plan", None) else None,
                    "depth_digest": depth_summary.get("depth_digest"),
                    "declared_depth_status": depth_summary["status"], "blockers": depth_summary["blockers"],
                    "report_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "created_at": datetime.now(timezone.utc).isoformat(), "legal_signoff": "NOT_ATTESTED"}
        with tempfile.TemporaryDirectory(prefix="report-", dir=args.run / "private") as temporary:
            staged = Path(temporary) / "version"
            staged.mkdir(mode=0o700)
            write_new(staged / "report.md", text)
            write_json(staged / "results.json", results)
            write_json(staged / "manifest.json", manifest)
            event(args.run, "REPORT_COMMIT_READY", revision=revision, report_sha256=manifest["report_sha256"])
            staged.rename(destination)
        output = destination / "report.md"
    print(json.dumps({"status": "DRAFT_REPORT_CREATED", "report": output.relative_to(args.run).as_posix()}))


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
            sub.add_argument("--revision", type=int, help="Write an immutable numbered report bundle for re-review")
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
