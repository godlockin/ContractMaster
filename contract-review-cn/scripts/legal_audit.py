#!/usr/bin/env python3
"""Offline, conservative legal-audit ledger.

This module records review decisions; it does not decide legal validity,
calculate statutory dates, verify signatures, or contact external services.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import hashlib
import html
import os
import stat
import sys
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
WORKFLOW_READY = "WORKFLOW_READY"
PARTIAL = "PARTIAL"
_STATUSES = {"draft", "signed", "effective", "terminated"}
_FINDING_CATEGORIES = {"legal", "commercial", "text", "evidence"}
_SEVERITIES = {"low", "medium", "high", "critical"}
_DECISIONS = {"open", "accepted", "rejected", "approved", "deferred"}
_OBLIGATION_STATUSES = {"open", "in_progress", "fulfilled", "waived", "disputed"}
_APPROVAL_STATES = {"none", "pending", "approved", "rejected"}
_POSITIONS = {"buyer", "seller", "employer", "employee", "licensor", "licensee", "neutral", "other"}
_STAGES = {"intake", "pre-sign", "post-sign", "renewal", "termination", "dispute", "negotiation", "performance", "archive"}
_SYSTEM_ALIASES = {"/tmp", "/var", "/private", "/private/tmp", "/private/var"}


def _obj(value: object, name: str, errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{name}: expected object")
        return None
    return value


def _list(value: object, name: str, errors: list[str]) -> list[Any] | None:
    if not isinstance(value, list):
        errors.append(f"{name}: expected array")
        return None
    return value


def _str(value: object, name: str, errors: list[str], required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or (required and not value.strip()):
        errors.append(f"{name}: expected non-empty string")
        return None
    return value


def _date(value: object, name: str, errors: list[str], required: bool = False) -> None:
    if value is None and not required:
        return
    if not isinstance(value, str):
        errors.append(f"{name}: expected YYYY-MM-DD or null")
        return
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        errors.append(f"{name}: invalid ISO date")
        return
    try:
        _dt.date.fromisoformat(value)
    except ValueError:
        errors.append(f"{name}: invalid ISO date")


def _ids(items: list[Any], path: str, errors: list[str]) -> set[str]:
    result: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{path}[{index}]: expected object")
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            errors.append(f"{path}[{index}].id: required")
        elif item_id in result:
            errors.append(f"{path}: duplicate id {item_id}")
        else:
            result.add(item_id)
    return result


def _string_list(value: object, name: str, errors: list[str], required: bool = False) -> list[str]:
    if value is None and not required:
        return []
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        errors.append(f"{name}: expected array of non-empty strings")
        return []
    return list(value)


def _enum(value: object, allowed: set[str], name: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or value not in allowed:
        errors.append(f"{name}: invalid enum")
        return False
    return True


def validate(record: object) -> dict[str, Any]:
    """Return compact validation result. No legal conclusion is produced."""
    errors: list[str] = []
    warnings: list[str] = []
    root = _obj(record, "root", errors)
    if root is None:
        return {"status": PARTIAL, "errors": errors, "warnings": warnings, "counts": {}}

    if root.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version: expected {SCHEMA_VERSION}")
    for field in ("case_id", "snapshot_digest", "playbook_version"):
        _str(root.get(field), field, errors)
    digest = root.get("snapshot_digest")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
        errors.append("snapshot_digest: expected 64 hexadecimal characters")
    _enum(root.get("review_status"), {"complete", "partial"}, "review_status", errors)
    input_digest = root.get("input_digest")
    if not isinstance(input_digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", input_digest):
        errors.append("input_digest: expected 64 hexadecimal characters")
    context = _obj(root.get("context"), "context", errors) or {}
    for field in ("our_position", "jurisdiction", "audit_stage"):
        _str(context.get(field), f"context.{field}", errors)
    _enum(context.get("our_position"), _POSITIONS, "context.our_position", errors)
    _enum(context.get("audit_stage"), _STAGES, "context.audit_stage", errors)
    known_gaps = _string_list(context.get("known_gaps"), "context.known_gaps", errors)
    if known_gaps:
        warnings.append("known facts/gaps remain unresolved")

    playbook = _list(root.get("playbook"), "playbook", errors) or []
    playbook_ids = _ids(playbook, "playbook", errors)
    playbook_by_id: dict[str, dict[str, Any]] = {}
    for i, item in enumerate(playbook):
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if isinstance(item_id, str):
            playbook_by_id[item_id] = item
        for field in ("id", "side", "preferred", "fallback", "red_line", "approval_role"):
            _str(item.get(field), f"playbook[{i}].{field}", errors)
        _enum(item.get("side"), _POSITIONS, f"playbook[{i}].side", errors)
        if not isinstance(item.get("exception_allowed", False), bool):
            errors.append(f"playbook[{i}].exception_allowed: expected boolean")
        if isinstance(item.get("side"), str) and isinstance(context.get("our_position"), str) and item.get("side") not in {context.get("our_position"), "neutral"}:
            warnings.append(f"playbook[{i}]: side differs from context.our_position; partial review")

    chain = _list(root.get("document_chain"), "document_chain", errors) or []
    doc_ids = _ids(chain, "document_chain", errors)
    doc_by_id: dict[str, dict[str, Any]] = {}
    for i, item in enumerate(chain):
        if not isinstance(item, dict):
            continue
        doc_id = _str(item.get("id"), f"document_chain[{i}].id", errors)
        if doc_id:
            doc_by_id[doc_id] = item
        for field in ("version", "status"):
            _str(item.get(field), f"document_chain[{i}].{field}", errors)
        _enum(item.get("status"), _STATUSES, f"document_chain[{i}].status", errors)
        _date(item.get("effective_date"), f"document_chain[{i}].effective_date", errors)
        supersedes = item.get("supersedes")
        if supersedes is not None and not isinstance(supersedes, str):
            errors.append(f"document_chain[{i}].supersedes: expected id or null")
        _string_list(item.get("evidence_refs"), f"document_chain[{i}].evidence_refs", errors)
    for doc_id, item in doc_by_id.items():
        parent = item.get("supersedes")
        if isinstance(parent, str):
            if parent not in doc_ids:
                errors.append(f"document_chain.{doc_id}.supersedes: dangling id {parent}")
            elif item.get("status") != "effective" and doc_by_id[parent].get("status") == "effective":
                warnings.append(f"document_chain.{doc_id}: needs_review; non-effective document supersedes effective; not controlling")
                scope = item.get("supersedes_scope")
                if not isinstance(scope, list) or not scope or any(not isinstance(ref, str) or not ref.strip() for ref in scope):
                    warnings.append(f"document_chain.{doc_id}: supersedes_scope required for partial replacement")
        if item.get("status") == "effective" and not item.get("effective_date"):
            warnings.append(f"document_chain.{doc_id}: effective document lacks effective_date")
        if not item.get("evidence_refs"):
            warnings.append(f"document_chain.{doc_id}: evidence_refs empty")
    effective_by_parent: dict[str | None, list[str]] = {}
    for doc_id, item in doc_by_id.items():
        if item.get("status") == "effective":
            parent = item.get("supersedes") if isinstance(item.get("supersedes"), str) else None
            effective_by_parent.setdefault(parent, []).append(doc_id)
    for parent, docs in effective_by_parent.items():
        if parent is not None and len(docs) > 1:
            warnings.append(f"document_chain: competing effective documents for parent {parent or '(root)'}")
    # Supersession graph must be acyclic.
    for start in doc_by_id:
        seen: set[str] = set()
        current: str | None = start
        while current and current in doc_by_id:
            if current in seen:
                errors.append(f"document_chain: supersession cycle at {current}")
                break
            seen.add(current)
            parent = doc_by_id[current].get("supersedes")
            current = parent if isinstance(parent, str) else None

    findings = _list(root.get("findings"), "findings", errors) or []
    finding_ids = _ids(findings, "findings", errors)
    unresolved_major = False
    for i, item in enumerate(findings):
        if not isinstance(item, dict):
            continue
        for field in ("id", "clause", "category", "severity", "risk", "impact", "proposed_text", "fallback", "decision", "unresolved", "rule_id", "exception_approval"):
            if field not in item:
                errors.append(f"findings[{i}].{field}: required")
        _string_list(item.get("doc_refs"), f"findings[{i}].doc_refs", errors, required=True)
        _enum(item.get("category"), _FINDING_CATEGORIES, f"findings[{i}].category", errors)
        _enum(item.get("severity"), _SEVERITIES, f"findings[{i}].severity", errors)
        _enum(item.get("decision"), _DECISIONS, f"findings[{i}].decision", errors)
        if not isinstance(item.get("unresolved"), bool):
            errors.append(f"findings[{i}].unresolved: expected boolean")
        rule_id = item.get("rule_id")
        if rule_id is not None and (not isinstance(rule_id, str) or rule_id not in playbook_ids):
            errors.append(f"findings[{i}].rule_id: dangling id")
        for field in ("clause", "risk", "impact", "proposed_text", "fallback"):
            if not isinstance(item.get(field), str):
                errors.append(f"findings[{i}].{field}: expected string")
        for field in ("clause", "risk", "impact"):
            if isinstance(item.get(field), str) and not item[field].strip():
                errors.append(f"findings[{i}].{field}: expected non-empty string")
        _enum(item.get("exception_approval"), _APPROVAL_STATES, f"findings[{i}].exception_approval", errors)
        severity = item.get("severity")
        decision = item.get("decision")
        if isinstance(severity, str) and severity in {"high", "critical"} and (item.get("unresolved") or (isinstance(decision, str) and decision in {"open", "deferred"})):
            unresolved_major = True
        approval_refs = _string_list(item.get("approval_evidence_refs"), f"findings[{i}].approval_evidence_refs", errors)
        if item.get("exception_approval") == "approved" and (not approval_refs or not isinstance(item.get("approval_scope"), str) or not item.get("approval_scope") or item.get("approval_version") != root.get("playbook_version") or item.get("approval_snapshot_digest") != root.get("snapshot_digest")):
            errors.append(f"findings[{i}].approval: approved requires evidence refs, scope, version, snapshot binding")
        if item.get("exception_approval") == "approved":
            rule = playbook_by_id.get(rule_id) if isinstance(rule_id, str) else None
            if not isinstance(rule, dict) or rule.get("exception_allowed", False) is not True:
                warnings.append(f"findings[{i}]: approved exception not allowed by rule; red_line cannot be bypassed")
        exception_approval = item.get("exception_approval")
        if isinstance(exception_approval, str) and exception_approval in {"pending", "rejected"}:
            unresolved_major = True
        if item.get("unresolved") or (isinstance(decision, str) and decision in {"open", "deferred"}):
            unresolved_major = True
        for ref in _string_list(item.get("doc_refs"), f"findings[{i}].doc_refs", errors):
            if ref not in doc_ids:
                errors.append(f"findings[{i}].doc_refs: dangling document {ref}")

    obligations = _list(root.get("obligations"), "obligations", errors) or []
    obligation_ids = _ids(obligations, "obligations", errors)
    for i, item in enumerate(obligations):
        if not isinstance(item, dict):
            continue
        for field in ("id", "doc_id", "clause", "due_date", "notice_method", "day_basis", "owner", "status"):
            if field not in item:
                errors.append(f"obligations[{i}].{field}: required")
        doc_id = item.get("doc_id")
        if not isinstance(doc_id, str) or doc_id not in doc_ids:
            errors.append(f"obligations[{i}].doc_id: dangling document")
        _date(item.get("due_date"), f"obligations[{i}].due_date", errors)
        _enum(item.get("status"), _OBLIGATION_STATUSES, f"obligations[{i}].status", errors)
        for field in ("clause", "notice_method", "day_basis", "owner"):
            _str(item.get(field), f"obligations[{i}].{field}", errors)
        if item.get("due_date") is None:
            warnings.append(f"obligations[{i}].due_date is unconfirmed")

    if not root.get("evidence_disclaimer"):
        warnings.append("approval evidence is self-reported and not signature-verified")
    if not playbook:
        warnings.append("playbook is not configured; neutral review remains partial")
    if not doc_ids:
        warnings.append("document_chain is empty; no controlling document recorded")
    if root.get("review_status") != "complete":
        warnings.append("review_status is not complete")
    status = PARTIAL if errors or warnings or unresolved_major else WORKFLOW_READY
    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "counts": {"playbook": len(playbook_ids), "documents": len(doc_ids), "findings": len(finding_ids), "obligations": len(obligation_ids)},
    }


def template() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": "",
        "snapshot_digest": "",
        "playbook_version": "",
        "review_status": "partial",
        "input_digest": "",
        "context": {"our_position": "", "jurisdiction": "", "audit_stage": "", "known_gaps": []},
        "playbook": [],
        "document_chain": [],
        "findings": [],
        "obligations": [],
        "evidence_disclaimer": "Approval evidence is self-reported; no signature verification or legal-effect determination.",
    }


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValueError("non-finite JSON number")


def _parse_json_bytes(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_nonfinite)
    if not isinstance(value, dict):
        raise ValueError("input JSON root must be object")
    return value


def _load_input(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    return _parse_json_bytes(raw), raw


def _write_exclusive_file(path: Path, value: object) -> None:
    _secure_parent(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _write_exclusive_text(path: Path, value: str) -> None:
    _secure_parent(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(value)
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _secure_parent(parent: Path) -> None:
    absolute = parent.absolute()
    for candidate in (absolute, *absolute.parents):
        if candidate.is_symlink() and str(candidate) not in _SYSTEM_ALIASES:
            raise OSError("symlink parent rejected")
    current = absolute
    missing: list[Path] = []
    while not current.exists():
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
        directory.chmod(stat.S_IRWXU)


def _new_dir(path: Path) -> None:
    absolute = path.absolute()
    for candidate in (absolute.parent, *absolute.parent.parents):
        if candidate.is_symlink() and str(candidate) not in _SYSTEM_ALIASES:
            raise OSError("symlink parent rejected")
    path.mkdir(mode=0o700, parents=False, exist_ok=False)
    path.chmod(stat.S_IRWXU)


def run_init(output: str | None) -> int:
    data = template()
    if output:
        _write_exclusive_file(Path(output), data)
        print(f"OK {PARTIAL} output={output}")
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def run_check(input_path: str, output: str) -> int:
    record, _ = _load_input(Path(input_path))
    result = validate(record)
    directory = Path(output)
    _new_dir(directory)
    _write_exclusive_file(directory / "check.json", result)
    print(f"OK {result['status']} errors={len(result['errors'])} warnings={len(result['warnings'])} output={directory}")
    return 0 if result["status"] == WORKFLOW_READY else 2


def run_report(input_path: str, output: str) -> int:
    record, input_bytes = _load_input(Path(input_path))
    result = validate(record)
    directory = Path(output)
    _new_dir(directory)
    _write_exclusive_file(directory / "report.json", {"status": result["status"], "validation": result, "record": record})
    counts = result["counts"]
    raw_findings = record.get("findings")
    finding_rows = [item for item in raw_findings if isinstance(item, dict)] if isinstance(raw_findings, list) else []
    raw_obligations = record.get("obligations")
    obligation_rows = [item for item in raw_obligations if isinstance(item, dict)] if isinstance(raw_obligations, list) else []
    def safe_text(value: object) -> str:
        escaped = html.escape(str(value), quote=True)
        for character in ("\\", "`", "*", "_", "|", "{", "}", "[", "]", "(", ")", "#", "+", "-", ".", "!", ">"):
            escaped = escaped.replace(character, "\\" + character)
        return escaped

    def refs_text(item: dict[str, Any]) -> str:
        refs = item.get("doc_refs")
        return ", ".join(safe_text(ref) for ref in refs) if isinstance(refs, list) and all(isinstance(ref, str) for ref in refs) else "（无效引用）"
    lines = [
        "# 本地合同审计台账报告",
        "",
        f"状态：`{result['status']}`",
        "",
        "本私有报告仅记录台账结构与流程状态，不是法律效力意见、验签结果或可签署建议。必须回到现有 contract-review pipeline 复核、脱敏后才可对外使用。",
        "",
        f"记录数量：文档 {counts.get('documents', 0)}；风险 {counts.get('findings', 0)}；义务 {counts.get('obligations', 0)}。",
        "",
        "## 主要风险",
        "",
        *([f"- {safe_text(item.get('id'))}: 严重度={safe_text(item.get('severity'))}；类别={safe_text(item.get('category'))}；条款={safe_text(item.get('clause'))}；文档={refs_text(item)}；风险={safe_text(item.get('risk', '（未提供）'))}；影响={safe_text(item.get('impact', '（未提供）'))}" for item in finding_rows] or ["- 未记录风险。"]),
        "",
        "## 证据缺口与校验问题",
        "",
        *([f"- 错误：{safe_text(item)}" for item in result["errors"]] or ["- 未发现结构错误。"]),
        *([f"- {safe_text(item)}" for item in result["warnings"]] or ["- 未记录。"]),
        "",
        "## 替换建议与退让方案",
        "",
        *([f"- {safe_text(item.get('id'))}: 建议={safe_text(item.get('proposed_text') or '（无）')}；退让={safe_text(item.get('fallback') or '（无）')}" for item in finding_rows] or ["- 未记录替换建议。"]),
        "",
        "## 审批与履约",
        "",
        *([f"- 风险 {safe_text(item.get('id'))}：例外审批={safe_text(item.get('exception_approval'))}；批准范围={safe_text(item.get('approval_scope', '（无）'))}；批准版本={safe_text(item.get('approval_version', '（无）'))}" for item in finding_rows] or ["- 未记录审批。"]),
        *([f"- 义务 {safe_text(item.get('id'))}：文档={safe_text(item.get('doc_id'))}；条款={safe_text(item.get('clause'))}；到期日={safe_text(item.get('due_date') or '（未核定）')}；送达方式={safe_text(item.get('notice_method'))}；日期口径={safe_text(item.get('day_basis'))}；负责人={safe_text(item.get('owner'))}；状态={safe_text(item.get('status'))}" for item in obligation_rows] or ["- 未记录义务。"]),
        "",
        "审批证据仅为自报，未验签。日期为输入声明，未验证起算、节假日或送达依据。input_digest 只表示关联声明，无法证明真实输入包完整。",
        "",
        "不得将本报告的 WORKFLOW_READY 解释为现有 pipeline 审核通过。",
    ]
    _write_exclusive_text(directory / "report.md", "\n".join(lines) + "\n")
    tool_bytes = Path(__file__).read_bytes()
    _write_exclusive_file(directory / "manifest.json", {"input_sha256": hashlib.sha256(input_bytes).hexdigest(), "tool_sha256": hashlib.sha256(tool_bytes).hexdigest(), "status": result["status"]})
    print(f"OK {result['status']} output={directory}")
    return 0 if result["status"] == WORKFLOW_READY else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline contract audit ledger")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--output", help="new JSON file; omit to print conservative template")
    for name in ("check", "report"):
        command = sub.add_parser(name)
        command.add_argument("--input", required=True)
        command.add_argument("--output", required=True, help="new output directory")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            return run_init(args.output)
        if args.command == "check":
            return run_check(args.input, args.output)
        return run_report(args.input, args.output)
    except (OSError, ValueError, json.JSONDecodeError):
        print("FAILED INPUT_OR_OUTPUT_ERROR", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
