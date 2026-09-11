"""Declared two-team independence and challenge coverage, not host attestation."""
import pipeline as p


def assess(bundle, plan, depth, results, domains, sources, source_kinds):
    p.require(results is not None, "DUAL_TEAM_RESULTS_REQUIRED")
    p.validate_results(bundle, results, plan)
    teams = {expert["role"]: expert["team"] for expert in plan["experts"]}
    by_role = {result["role"]: result for result in results}
    findings = {finding["id"]: result["role"] for result in results for finding in result["findings"]}
    segments = {segment["id"] for segment in bundle["segments"]}
    blockers = []
    dossiers = depth.get("team_passes")
    p.require(isinstance(dossiers, list) and len(dossiers) == 2, "TEAM_PASSES_REQUIRED")
    seen = set()
    for dossier in dossiers:
        p.require(isinstance(dossier, dict), "TEAM_PASS_SCHEMA")
        team = dossier.get("team")
        p.require(isinstance(team, str) and team in {"A", "B"} and team not in seen, "TEAM_PASS_DUPLICATE")
        seen.add(team)
        expected = {role: p.digest(result["first_pass"]) for role, result in by_role.items() if teams[role] == team}
        p.require(dossier.get("first_pass_digests") == expected, "TEAM_PASS_STALE")
        for field, expected_ids in (("domain_checks", set(domains)), ("source_checks", set(source_kinds))):
            rows = dossier.get(field)
            p.require(isinstance(rows, list), "TEAM_CHECKS_REQUIRED")
            ids = set()
            for row in rows:
                p.require(isinstance(row, dict) and isinstance(row.get("id"), str) and
                          row["id"] in expected_ids and row["id"] not in ids, "TEAM_CHECK_INVALID")
                ids.add(row["id"])
                p.require(row.get("status") in {"reviewed", "not_applicable", "unknown"} and
                          p.nonempty(row.get("reason")), "TEAM_CHECK_STATUS")
                if row["status"] == "unknown":
                    blockers.append("TEAM_SCOPE_UNKNOWN")
            p.require(ids == expected_ids, "TEAM_CHECK_COVERAGE")
    for row in depth["rounds"]:
        if row["round"] == 1:
            p.require(row.get("first_pass_digest") == p.digest(by_role[row["role"]]["first_pass"]), "ROUND_FIRST_PASS_STALE")
    challenges = depth.get("cross_challenges")
    p.require(isinstance(challenges, list), "CROSS_CHALLENGES_REQUIRED")
    covered, challenged, ids = set(), set(), set()
    change_ids = {change["id"] for change in bundle.get("comparison", {}).get("changes", [])}
    change_coverage = set()
    for item in challenges:
        p.require(isinstance(item, dict) and p.nonempty(item.get("id")) and item["id"] not in ids, "CHALLENGE_ID")
        ids.add(item["id"])
        author, target = item.get("author"), item.get("target")
        p.require(isinstance(author, str) and isinstance(target, str) and author in teams and target in teams
                  and teams[author] != teams[target], "CHALLENGE_NOT_CROSS_TEAM")
        angle = item.get("angle")
        p.require(isinstance(angle, str) and angle in domains, "CHALLENGE_ANGLE")
        p.require(all(p.nonempty(item.get(key)) for key in ("question", "response", "reason")), "CHALLENGE_ARGUMENTS")
        p.require(item.get("status") in {"resolved", "unresolved"} and
                  item.get("outcome") in {"upheld", "corrected", "rejected", "open"}, "CHALLENGE_STATUS")
        p.require((item["status"] == "unresolved") == (item["outcome"] == "open"), "CHALLENGE_OUTCOME")
        refs = item.get("evidence_refs")
        p.require(isinstance(refs, list) and refs and all(isinstance(ref, str) for ref in refs)
                  and len(refs) == len(set(refs)) and set(refs) <= segments | set(sources), "CHALLENGE_EVIDENCE")
        targets = item.get("finding_ids")
        p.require(isinstance(targets, list) and all(isinstance(fid, str) and fid in findings
                  and teams[findings[fid]] == teams[target] for fid in targets)
                  and len(targets) == len(set(targets)), "CHALLENGE_FINDING_INVALID")
        challenged.update(targets)
        if "comparison" in bundle:
            changes = item.get("change_ids")
            p.require(isinstance(changes, list) and all(isinstance(cid, str) and cid in change_ids for cid in changes)
                      and len(changes) == len(set(changes)), "CHALLENGE_CHANGE_INVALID")
            change_coverage.update((cid, teams[author], teams[target]) for cid in changes)
        covered.add((angle, teams[author], teams[target]))
        if item["status"] == "unresolved":
            blockers.append("CROSS_CHALLENGE_UNRESOLVED")
    required = {(angle, author, target) for angle, row in domains.items() if row["status"] == "applicable"
                for author, target in (("A", "B"), ("B", "A"))}
    if not required <= covered:
        blockers.append("CROSS_TEAM_ANGLE_COVERAGE")
    if set(findings) - challenged:
        blockers.append("FINDINGS_NOT_CROSS_CHALLENGED")
    if not {(cid, author, target) for cid in change_ids for author, target in (("A", "B"), ("B", "A"))} <= change_coverage:
        blockers.append("CHANGES_NOT_CROSS_CHALLENGED")
    return blockers
