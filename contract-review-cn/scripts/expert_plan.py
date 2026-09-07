"""Validate declared expert readiness, never expert competence or OS isolation."""
import re
import argparse
import json
import os
import tempfile
from pathlib import Path

import pipeline as p


def activate(run: Path, bundle: dict, plan: dict) -> None:
    """Advance the run's plan monotonically, including blocked plans."""
    assess(bundle, plan)
    path = run / "private/active-plan.json"
    current = p.read_json(path) if path.exists() else None
    if current is not None:
        p.require(current["input_digest"] == bundle["input_digest"], "ACTIVE_PLAN_STALE_INPUT")
        if current["revision"] == plan["revision"] and current["plan_digest"] == p.digest(plan):
            return
        p.require(plan["revision"] > current["revision"], "PLAN_REVISION_NOT_ADVANCING")
    record = {"input_digest": bundle["input_digest"], "revision": plan["revision"], "plan_digest": p.digest(plan)}
    fd, temporary = tempfile.mkstemp(prefix=".active-plan-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    p.event(run, "EXPERT_PLAN_ACTIVATED", revision=plan["revision"], plan_digest=record["plan_digest"])


def check_active(run: Path, bundle: dict, plan: dict) -> None:
    path = run / "private/active-plan.json"
    p.require(path.exists(), "EXPERT_PLAN_NOT_ACTIVATED")
    current = p.read_json(path)
    p.require(current.get("input_digest") == bundle["input_digest"] and
              current.get("revision") == plan["revision"] and current.get("plan_digest") == p.digest(plan),
              "EXPERT_PLAN_NOT_ACTIVE")


def assess(bundle: dict, plan: dict) -> dict:
    p.require(isinstance(plan, dict) and plan.get("schema_version") == 1, "PLAN_SCHEMA")
    p.require(plan.get("input_digest") == bundle["input_digest"], "PLAN_STALE_INPUT")
    p.require(type(plan.get("revision")) is int and plan["revision"] > 0, "PLAN_REVISION")
    p.require(isinstance(plan.get("profile"), dict) and all(p.nonempty(plan["profile"].get(k)) for k in
        ("transaction", "party_position", "jurisdictions", "industry", "data_flow", "documents")), "PLAN_PROFILE")
    roles = set()
    blockers = []
    p.require(isinstance(plan.get("experts"), list), "PLAN_EXPERTS_SCHEMA")
    for expert in plan["experts"]:
        p.require(isinstance(expert, dict), "PLAN_EXPERT_SCHEMA")
        role = expert.get("role")
        p.require(isinstance(role, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", role) is not None
                  and role not in roles, "PLAN_ROLE_INVALID_OR_DUPLICATE")
        roles.add(role)
        p.require(all(p.nonempty(expert.get(k)) for k in ("trigger", "mandate", "escalation", "context_strategy")), "PLAN_MANDATE")
        p.require(expert.get("full_text") is True and expert.get("independent_first") is True, "PLAN_REVIEW_SCOPE")
        p.require(expert.get("readiness") in {"ready", "blocked"}, "PLAN_READINESS")
        if expert["readiness"] != "ready":
            blockers.append("EXPERT_NOT_READY")
        tools = expert.get("tools")
        p.require(isinstance(tools, list), "PLAN_TOOLS")
        for tool in tools:
            p.require(isinstance(tool, dict) and p.nonempty(tool.get("name")) and p.nonempty(tool.get("purpose"))
                      and type(tool.get("required")) is bool and type(tool.get("available")) is bool
                      and tool.get("data_scope") in {"public_abstract_query", "released_bundle", "local_no_model"}, "PLAN_TOOL_POLICY")
            if tool["required"] and not tool["available"]:
                blockers.append("REQUIRED_TOOL_UNAVAILABLE")
    p.require(set(p.ROLES) <= roles, "PLAN_BASE_ROLES_MISSING")
    matrix = plan.get("coverage")
    p.require(isinstance(matrix, list) and matrix, "PLAN_COVERAGE")
    ids = set()
    for row in matrix:
        p.require(isinstance(row, dict) and p.nonempty(row.get("angle")) and row["angle"] not in ids,
                  "PLAN_ANGLE_INVALID_OR_DUPLICATE")
        ids.add(row["angle"])
        p.require(row.get("status") in {"applicable", "not_applicable", "unknown"}
                  and p.nonempty(row.get("reason")), "PLAN_APPLICABILITY")
        owners, challengers = row.get("owners"), row.get("challengers")
        p.require(isinstance(owners, list) and isinstance(challengers, list)
                  and all(isinstance(r, str) and r in roles for r in owners + challengers), "PLAN_OWNER_UNKNOWN")
        if row["status"] == "applicable":
            p.require(owners and challengers and not set(owners) & set(challengers), "PLAN_CROSS_REVIEW_MISSING")
        elif row["status"] == "unknown":
            blockers.append("PLAN_SCOPE_UNKNOWN")
    from validate_depth import DOMAINS
    p.require(set(DOMAINS) <= ids, "PLAN_BASE_ANGLES_MISSING")
    for key in ("open_issues", "change_log"):
        p.require(isinstance(plan.get(key), list) and all(p.nonempty(x) for x in plan[key]), "PLAN_RECORDS")
    if plan["open_issues"]:
        blockers.append("PLAN_OPEN_ISSUES")
    return {"roles": sorted(roles), "blockers": sorted(set(blockers)),
            "status": "DECLARED_PLAN_READY" if not blockers else "PARTIAL_AUDIT", "plan_digest": p.digest(plan)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--activate", action="store_true", help="Register this revision as the active run plan")
    args = parser.parse_args()
    try:
        bundle = p.read_json(args.run / "public/bundle.json")
        p.check_bundle(bundle)
        extraction = p.read_json(args.run / "private/extraction.json")
        p.require(p.digest(bundle) == extraction["candidate_digest"], "RELEASED_BUNDLE_CHANGED")
        plan = p.read_json(args.plan)
        mapping = p.read_json(args.run / "private/mapping.json")
        p.require(p.digest(mapping) == extraction["mapping_digest"], "MAPPING_CHANGED_REPREPARE")
        p.require(not p.contains_private_value(plan, [x["value"] for x in mapping["entities"]]), "PLAN_PRIVATE_VALUE_LEAK")
        result = assess(bundle, plan)
        if args.activate:
            activate(args.run, bundle, plan)
        print(json.dumps(result))
        return 0 if result["status"] == "DECLARED_PLAN_READY" else 2
    except p.GateError as exc:
        print(json.dumps({"status": "FAILED", "code": str(exc)}))
        return 2
    except Exception:
        print('{"status":"FAILED","code":"PLAN_LOCAL_IO_OR_SCHEMA_ERROR"}')
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
