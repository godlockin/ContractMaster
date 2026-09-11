#!/usr/bin/env python3
"""Verify declared audit depth. Does not certify legal completeness or reasoning quality."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pipeline as p

DOMAINS = (
    "civil_contract", "entity_authority", "procedure_evidence", "tax_accounting",
    "labor_social", "consumer_product", "competition_integrity", "licensing_industry",
    "finance_payments", "ip_trade_secret", "personal_information", "data_cybersecurity",
    "cross_border", "real_estate_construction", "environment_safety", "public_procurement",
    "local_special", "standards_contractual",
)
SOURCE_KINDS = ("law", "administrative_regulation", "local_regulation", "department_rule",
                "local_rule", "judicial_interpretation", "normative_document", "standard", "treaty_foreign")
SECURITY = ("data_scope", "access_control", "encryption_keys", "logging_audit", "vulnerability_change",
            "incident_response", "backup_recovery", "subcontractors", "retention_deletion",
            "transfer_location", "verification_liability")
SCOPE = ("jurisdiction", "locations", "dates", "party_roles", "industry", "transaction")
MAX_TWO_HOP_PAIRS = 50_000


class DepthError(Exception):
    pass


def check(condition: object, code: str) -> None:
    if not condition:
        raise DepthError(code)


def strings(value: object) -> bool:
    return isinstance(value, list) and all(p.nonempty(item) for item in value)


def unique_strings(value: object) -> bool:
    return strings(value) and len(value) == len(set(value))


def rows(value: object, key: str, required: tuple[str, ...] = ()) -> dict:
    check(isinstance(value, list), "DEPTH_ROWS_SCHEMA")
    result = {}
    for row in value:
        check(isinstance(row, dict) and p.nonempty(row.get(key)), "DEPTH_ROW_SCHEMA")
        check(row[key] not in result, "DEPTH_DUPLICATE_ID")
        result[row[key]] = row
    check(set(required) <= set(result), "DEPTH_REQUIRED_ROWS_MISSING")
    return result


def valid_date(value: object) -> bool:
    return p.valid_date(value)


def https(value: object) -> bool:
    return p.https(value)


def assess(bundle: dict, depth: dict, plan: dict | None = None, results: list[dict] | None = None) -> dict:
    p.check_bundle(bundle)
    check(isinstance(depth, dict) and depth.get("schema_version") == 1, "DEPTH_SCHEMA_VERSION")
    check(depth.get("input_digest") == bundle["input_digest"], "DEPTH_STALE_INPUT")
    docs = rows(bundle["documents"], "id")
    segments = rows(bundle["segments"], "id")
    check(all(s.get("document_id") in docs for s in segments.values()), "DEPTH_ORPHAN_SEGMENT")
    characters = 0
    for doc_id, doc in docs.items():
        cursor = 0
        ordered = [s for s in bundle["segments"] if s["document_id"] == doc_id]
        for seg in ordered:
            check(type(seg.get("start")) is int and type(seg.get("end")) is int and
                  seg["start"] == cursor and seg["end"] > cursor, "DEPTH_CHARACTER_GAP_OR_OVERLAP")
            check(doc["text"][cursor:seg["end"]] == seg["text"], "DEPTH_SEGMENT_TEXT_MISMATCH")
            cursor = seg["end"]
        check(cursor == len(doc["text"]), "DEPTH_CHARACTER_TAIL_MISSING")
        characters += cursor

    blockers: list[str] = []
    if bundle.get("input_gaps"):
        blockers.append("INPUTS_NOT_PROCESSED")
    expected_roles = p.ROLES
    if plan is None:
        blockers.append("EXPERT_PLAN_NOT_VALIDATED")
    else:
        from expert_plan import assess as assess_plan
        planning = assess_plan(bundle, plan)
        expected_roles = planning["roles"]
        blockers.extend(planning["blockers"])
        check(depth.get("plan_digest") == planning["plan_digest"], "DEPTH_STALE_PLAN")
    scope = depth.get("scope")
    check(isinstance(scope, dict) and set(SCOPE) <= set(scope), "DEPTH_SCOPE_MISSING")
    for key in SCOPE:
        item = scope[key]
        check(isinstance(item, dict) and item.get("status") in {"confirmed", "assumed", "unknown"}
              and p.nonempty(item.get("value")), "DEPTH_SCOPE_SCHEMA")
        if item["status"] != "confirmed":
            blockers.append("SCOPE_NOT_CONFIRMED")
    for key in ("scope_uncertainties", "chain_frontier", "open_issues"):
        check(strings(depth.get(key)), "DEPTH_UNRESOLVED_LIST_SCHEMA")
        if depth[key]:
            blockers.append(key.upper())

    searches = rows(depth.get("source_searches"), "kind", SOURCE_KINDS)
    for row in searches.values():
        check(row.get("status") in {"searched", "not_applicable", "unavailable"} and
              p.nonempty(row.get("reason")) and valid_date(row.get("checked_at")), "DEPTH_SEARCH_SCHEMA")
        check(strings(row.get("urls")), "DEPTH_SEARCH_URLS_SCHEMA")
        if row["status"] == "searched":
            check(p.nonempty(row.get("query")) and row["urls"] and all(https(u) for u in row["urls"]), "DEPTH_SEARCH_EVIDENCE_MISSING")
        if row["status"] == "unavailable":
            blockers.append("SOURCE_SEARCH_UNAVAILABLE")

    sources = rows(depth.get("sources"), "id")
    for source in sources.values():
        check(source.get("status") in {"verified", "unverified"} and p.nonempty(source.get("title")), "DEPTH_SOURCE_SCHEMA")
        if source["status"] == "unverified":
            blockers.append("SOURCE_UNVERIFIED")
            continue
        check(all(p.nonempty(source.get(k)) for k in ("issuer", "version", "applicability", "kind")), "DEPTH_SOURCE_METADATA_MISSING")
        check(source["kind"] in searches and searches[source["kind"]]["status"] == "searched", "DEPTH_SOURCE_SEARCH_INCONSISTENT")
        check(https(source.get("url")) and valid_date(source.get("effective_from")) and
              valid_date(source.get("checked_at")), "DEPTH_SOURCE_URL_OR_DATE_INVALID")
        check("effective_to" in source and (source["effective_to"] is None or
              (valid_date(source["effective_to"]) and source["effective_to"] >= source["effective_from"])), "DEPTH_EFFECTIVE_PERIOD_INVALID")
        check(unique_strings(source.get("articles")) and source["articles"], "DEPTH_SOURCE_ARTICLES_MISSING")

    domains = rows(depth.get("legal_domains"), "id", DOMAINS)
    check(domains["civil_contract"].get("status") == "applicable", "DEPTH_CORE_CONTRACT_DOMAIN_REQUIRED")
    if plan is not None:
        planned = {row["angle"]: row for row in plan["coverage"]}
        check(set(domains) == set(planned), "DEPTH_PLAN_DOMAIN_SCOPE_MISMATCH")
        check(all(domain.get("status") == planned[key]["status"] for key, domain in domains.items()),
              "DEPTH_PLAN_APPLICABILITY_MISMATCH")
    for domain in domains.values():
        check(domain.get("status") in {"applicable", "not_applicable", "unknown"} and p.nonempty(domain.get("reason")), "DEPTH_DOMAIN_SCHEMA")
        check(unique_strings(domain.get("source_ids")) and set(domain["source_ids"]) <= set(sources), "DEPTH_DOMAIN_SOURCE_INVALID")
        if domain["status"] == "applicable" and not domain["source_ids"]:
            blockers.append("APPLICABLE_DOMAIN_WITHOUT_SOURCE")
        if domain["status"] == "unknown":
            blockers.append("DOMAIN_UNKNOWN")
    for row in rows(depth.get("security_checks"), "id", SECURITY).values():
        check(row.get("status") in {"reviewed", "not_applicable", "unknown"} and p.nonempty(row.get("reason")), "DEPTH_SECURITY_SCHEMA")
        check(row.get("outcome") in {"satisfied", "missing", "unknown", "not_applicable"}, "DEPTH_SECURITY_OUTCOME_REQUIRED")
        check((row["status"] == "not_applicable") == (row["outcome"] == "not_applicable"), "DEPTH_SECURITY_OUTCOME_INCONSISTENT")
        check(unique_strings(row.get("segment_ids")) and set(row["segment_ids"]) <= set(segments), "DEPTH_SECURITY_SEGMENT_INVALID")
        if row["status"] == "reviewed":
            check(row["segment_ids"], "DEPTH_SECURITY_EVIDENCE_MISSING")
        if row["status"] == "unknown" or row["outcome"] == "unknown":
            blockers.append("SECURITY_UNKNOWN")

    edges = rows(depth.get("relations"), "id")
    for edge in edges.values():
        check(edge.get("from") in segments and edge.get("to") in segments and
              p.nonempty(edge.get("type")) and p.nonempty(edge.get("summary")), "DEPTH_RELATION_SCHEMA")
        check(edge.get("status") in {"resolved", "unresolved"}, "DEPTH_RELATION_STATUS")
        if edge["status"] == "unresolved":
            blockers.append("RELATION_UNRESOLVED")
    # The machine-checkable minimum is every discovered directed two-hop pair.
    # Longer meaningful chains are reviewed by agents; unresolved extensions go in chain_frontier.
    outgoing: dict[str, list[str]] = {}
    for edge_id, edge in edges.items():
        outgoing.setdefault(edge["from"], []).append(edge_id)
    required_pairs = set()
    expansion_limited = False
    for left, edge in edges.items():
        for right in outgoing.get(edge["to"], []):
            if left != right and edge["from"] != edges[right]["to"]:
                if len(required_pairs) >= MAX_TWO_HOP_PAIRS:
                    expansion_limited = True
                    break
                required_pairs.add((left, right))
        if expansion_limited:
            blockers.append("RELATION_EXPANSION_LIMIT_REQUIRES_PARTITIONED_REVIEW")
            break
    covered_pairs = set()
    chains = rows(depth.get("chains"), "id")
    for chain in chains.values():
        ids = chain.get("edge_ids")
        check(unique_strings(ids) and len(ids) >= 2 and set(ids) <= set(edges), "DEPTH_CHAIN_EDGES_INVALID")
        check(chain.get("status") in {"resolved", "unresolved"} and p.nonempty(chain.get("summary")), "DEPTH_CHAIN_SCHEMA")
        for left, right in zip(ids, ids[1:]):
            check(edges[left]["to"] == edges[right]["from"], "DEPTH_CHAIN_DISCONNECTED")
            covered_pairs.add((left, right))
        if chain["status"] == "unresolved":
            blockers.append("CHAIN_UNRESOLVED")
    if not required_pairs <= covered_pairs:
        blockers.append("MULTIHOP_COVERAGE_MISSING")

    check(isinstance(depth.get("rounds"), list), "DEPTH_ROUNDS_SCHEMA")
    completed = set()
    for row in depth["rounds"]:
        check(isinstance(row, dict), "DEPTH_ROUND_SCHEMA")
        number, role = row.get("round"), row.get("role")
        check(type(number) is int and number in range(1, 5) and isinstance(role, str) and
              role in expected_roles and (number, role) not in completed, "DEPTH_ROUND_INVALID_OR_DUPLICATE")
        completed.add((number, role))
        check(unique_strings(row.get("segment_ids")) and set(row["segment_ids"]) == set(segments), "DEPTH_ROUND_SEGMENT_GAP")
        check(unique_strings(row.get("relation_ids")) and set(row["relation_ids"]) <= set(edges), "DEPTH_ROUND_RELATION_INVALID")
        if number > 1:
            check(set(row["relation_ids"]) == set(edges), "DEPTH_ROUND_RELATION_GAP")
        check(p.nonempty(row.get("review_note")), "DEPTH_ROUND_NOTE_MISSING")
    check(completed == {(n, role) for n in range(1, 5) for role in expected_roles}, "DEPTH_ROUND_COVERAGE_MISSING")
    if results is None:
        blockers.append("EXPERT_RESULTS_NOT_LINKED")
    else:
        for result in results:
            for finding in result.get("findings", []):
                if any(b.get("status") == "unverified" for b in finding.get("basis", [])):
                    blockers.append("FINDING_BASIS_UNVERIFIED")
                for basis in finding.get("basis", []):
                    if basis.get("status") != "verified":
                        continue
                    source_id = basis.get("source_id")
                    source = sources.get(source_id) if isinstance(source_id, str) else None
                    if source is None:
                        blockers.append("FINDING_BASIS_SOURCE_NOT_LINKED")
                    elif (source.get("status") != "verified" or
                          any(basis.get(key) != source.get(key) for key in ("title", "url", "checked_at")) or
                          basis.get("article") not in source.get("articles", [])):
                        blockers.append("FINDING_BASIS_SOURCE_MISMATCH")
                try:
                    resolved = p.validate_question_resolutions(finding, set(sources) | set(segments))
                except p.GateError as exc:
                    raise DepthError("DEPTH_" + str(exc)) from exc
                if set(finding.get("questions", [])) - resolved:
                    blockers.append("FINDING_QUESTIONS_UNRESOLVED")
    if "comparison" in bundle:
        from change_review import depth_blockers
        try:
            blockers.extend(depth_blockers(bundle, results))
        except p.GateError as exc:
            raise DepthError(str(exc)) from exc
    if plan is not None and plan.get("schema_version") == 2:
        from dual_team import assess as assess_dual
        try:
            blockers.extend(assess_dual(bundle, plan, depth, results, domains, sources, SOURCE_KINDS))
        except p.GateError as exc:
            raise DepthError(str(exc)) from exc
    return {"status": "DECLARED_DEPTH_COMPLETE" if not blockers else "PARTIAL_AUDIT",
            "input_digest": bundle["input_digest"], "characters": characters, "segments": len(segments),
            "round_role_records": len(completed), "domains": len(domains), "security_checks": len(SECURITY),
            "relations": len(edges), "chains": len(chains), "required_two_hop_pairs": len(required_pairs),
            "blockers": sorted(set(blockers)), "certifies_all_laws_or_risks": False}


def load_depth(run: Path, path: Path, bundle: dict, plan: dict | None = None, results: list[dict] | None = None,
               depth: dict | None = None) -> dict:
    depth = p.read_json(path) if depth is None else depth
    mapping = p.read_json(run / "private/mapping.json")
    check(not p.contains_private_value([depth, plan, results], [item["value"] for item in mapping["entities"]]),
          "DEPTH_PRIVATE_VALUE_LEAK")
    if plan is not None:
        from expert_plan import check_active
        check_active(run, bundle, plan)
    return {**assess(bundle, depth, plan, results), "depth_digest": p.digest(depth)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--depth", type=Path, required=True)
    parser.add_argument("--results", type=Path, nargs="+", required=True)
    parser.add_argument("--plan", type=Path)
    args = parser.parse_args()
    try:
        bundle, results, _ = p.load_results(args)
        summary = load_depth(args.run, args.depth, bundle, p.read_json(args.plan) if args.plan else None, results)
        print(json.dumps(summary))
        return 0 if summary["status"] == "DECLARED_DEPTH_COMPLETE" else 2
    except (DepthError, p.GateError) as exc:
        print(json.dumps({"status": "FAILED", "code": str(exc)}))
        return 2
    except Exception:
        print('{"status":"FAILED","code":"DEPTH_LOCAL_IO_OR_SCHEMA_ERROR"}')
        return 3


if __name__ == "__main__":
    sys.exit(main())
