"""Shared schema for policy controls actually supported by local runtime."""
from __future__ import annotations

SUPPORTED_TYPES = {"PERSON", "ORG", "ADDRESS", "PROJECT", "SECRET", "PHONE", "EMAIL", "ID", "ACCOUNT", "CREDIT"}
DEFAULT_TYPES = SUPPORTED_TYPES - {"CREDIT"}
DEFAULT_PRESERVE = ["DATE", "PERCENT", "LEGAL_NAME", "PARTY_ROLE"]
DEFAULT_RULES = {"internal_prices": True, "technical_formulas": True,
                 "bank_accounts": True, "contract_amounts": "ask_before_release"}


def validate_controls(value: dict) -> None:
    if "default_sensitive_types" in value:
        types = value["default_sensitive_types"]
        if not isinstance(types, list) or set(types) != DEFAULT_TYPES:
            raise ValueError("POLICY_UNSUPPORTED_SENSITIVE_TYPES")
    if "preserve_by_default" in value and value["preserve_by_default"] != DEFAULT_PRESERVE:
        raise ValueError("POLICY_UNSUPPORTED_PRESERVE_RULES")
    if "sensitive_business_rules" in value and value["sensitive_business_rules"] != DEFAULT_RULES:
        raise ValueError("POLICY_UNSUPPORTED_BUSINESS_RULES")
