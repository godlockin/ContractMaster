#!/usr/bin/env python3
"""Create and validate a case-local sensitive information policy.

Values stay in the selected case directory.  This command prints only status
and error codes, never entity values.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


DEFAULT = {
    "policy_version": 1,
    "default_sensitive_types": ["PERSON", "ORG", "ADDRESS", "PHONE", "EMAIL", "ID", "ACCOUNT", "PROJECT", "SECRET"],
    "preserve_by_default": ["DATE", "PERCENT", "LEGAL_NAME", "PARTY_ROLE"],
    "entities": [],
    "sensitive_business_rules": {
        "internal_prices": True, "technical_formulas": True,
        "bank_accounts": True, "contract_amounts": "ask_before_release"
    }
}
ALLOWED = {"PERSON", "ORG", "ADDRESS", "PROJECT", "SECRET", "PHONE", "EMAIL", "ID", "ACCOUNT", "CREDIT"}


def _secure_dir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def _write_new(path: Path, text: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(text)


def validate(path: Path) -> dict:
    try:
        if not path.is_file():
            return {"status": "INVALID", "reason": "CONFIG_NOT_FOUND"}
        mode = path.stat().st_mode & 0o777
        if mode != 0o600:
            return {"status": "INVALID", "reason": "CONFIG_PERMISSION_MUST_BE_600"}
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("policy_version") != 1 or not isinstance(value.get("entities"), list):
            raise ValueError("CONFIG_SCHEMA")
        seen: dict[str, str] = {}
        for item in value["entities"]:
            literal, kind = item.get("value"), item.get("type")
            if not isinstance(literal, str) or not literal.strip() or kind not in ALLOWED:
                raise ValueError("ENTITY_SCHEMA")
            if literal in seen and seen[literal] != kind:
                raise ValueError("ENTITY_TYPE_CONFLICT")
            seen[literal] = kind
        return {"status": "VALID", "entity_count": len(seen), "path": str(path)}
    except (OSError, ValueError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        reason = str(exc) if str(exc).startswith(("CONFIG_", "ENTITY_")) else "CONFIG_SCHEMA"
        return {"status": "INVALID", "reason": reason}


def init(root: Path) -> dict:
    _secure_dir(root)
    target = root / "privacy-policy.json"
    if target.exists():
        return {"status": "ALREADY_EXISTS", "path": str(target)}
    _write_new(target, json.dumps(DEFAULT, ensure_ascii=False, indent=2) + "\n")
    os.chmod(target, 0o600)
    return {"status": "INITIALIZED", "path": str(target), "next": "EDIT_LOCALLY_THEN_RUN_CHECK"}


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    init_parser = sub.add_parser("init")
    init_parser.add_argument("--root", type=Path, required=True)
    check_parser = sub.add_parser("check")
    check_parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = init(args.root) if args.command == "init" else validate(args.config)
    print(json.dumps(result, ensure_ascii=False))
    if result["status"] == "INVALID":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
