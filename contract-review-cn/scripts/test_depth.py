"""Synthetic gate tests, not legal quality or real-agent attestations."""
import copy
import unittest

import pipeline as p
import validate_depth as d


def plan_fixture(bundle, extra_roles=()):
    return {"schema_version": 1, "revision": 1, "input_digest": bundle["input_digest"],
            "profile": {k: "Synthetic only" for k in ("transaction", "party_position", "jurisdictions", "industry", "data_flow", "documents")},
            "experts": [{"role": r, "trigger": "Fixture trigger", "mandate": "Fixture mandate", "escalation": "Unknown facts",
                         "context_strategy": "Full bundle and reference retrieval", "full_text": True, "independent_first": True,
                         "readiness": "ready", "tools": []} for r in [*p.ROLES, *extra_roles]],
            "coverage": [{"angle": a, "status": "applicable" if a == "civil_contract" else "not_applicable", "reason": "Fixture scope",
                          "owners": ["legal"], "challengers": ["dispute"]} for a in d.DOMAINS],
            "open_issues": [], "change_log": ["Initial fixture plan"]}


def fixture():
    text = "甲\n乙\n丙\n"
    bundle = {"schema_version": 1, "roles": p.ROLES, "levels": p.LEVELS,
              "documents": [{"id": "DOC0001", "text": text}],
              "segments": p.segments_for("DOC0001", text)}
    bundle["input_digest"] = p.digest(bundle)
    ids = [s["id"] for s in bundle["segments"]]
    depth = {"schema_version": 1, "input_digest": bundle["input_digest"],
             "scope": {k: {"status": "confirmed", "value": "Synthetic fixture only"} for k in d.SCOPE},
             "scope_uncertainties": [], "chain_frontier": [], "open_issues": [],
             "source_searches": [{"kind": k, "status": "not_applicable", "query": "", "urls": [],
                                  "checked_at": "2026-09-07", "reason": "Schema fixture exclusion"} for k in d.SOURCE_KINDS],
             "sources": [{"id": "S1", "title": "Synthetic law, not a real authority", "issuer": "Fixture",
                          "kind": "law", "url": "https://example.invalid/source", "version": "fixture-v1",
                          "effective_from": "2026-01-01", "effective_to": None, "checked_at": "2026-09-07",
                          "articles": ["fixture-1"], "applicability": "Schema test only", "status": "verified"}],
             "legal_domains": [{"id": k, "status": "not_applicable", "reason": "Fixture-only exclusion", "source_ids": []} for k in d.DOMAINS],
             "security_checks": [{"id": k, "status": "not_applicable", "outcome": "not_applicable",
                                  "reason": "Fixture-only exclusion", "segment_ids": []} for k in d.SECURITY],
             "relations": [{"id": "E1", "from": ids[0], "to": ids[1], "type": "definition", "status": "resolved", "summary": "Fixture relation one"},
                           {"id": "E2", "from": ids[1], "to": ids[2], "type": "exception", "status": "resolved", "summary": "Fixture relation two"}],
             "chains": [{"id": "P1", "edge_ids": ["E1", "E2"], "status": "resolved", "summary": "Fixture chain, not legal inference"}],
             "rounds": [{"round": n, "role": role, "segment_ids": ids,
                         "relation_ids": [] if n == 1 else ["E1", "E2"],
                         "review_note": f"Synthetic {role} round {n}, not an actual review"} for n in range(1, 5) for role in p.ROLES]}
    depth["source_searches"][0].update(status="searched", query="synthetic source", urls=["https://example.invalid/search"])
    depth["legal_domains"][0].update(status="applicable", source_ids=["S1"])
    return bundle, depth


class DepthTests(unittest.TestCase):
    def setUp(self):
        self.bundle, self.depth = fixture()
        self.plan = plan_fixture(self.bundle)
        self.depth["plan_digest"] = p.digest(self.plan)

    def assess(self, bundle=None, depth=None):
        return d.assess(bundle or self.bundle, depth or self.depth, self.plan, [])

    def test_declared_complete_is_not_legal_certificate(self):
        result = self.assess()
        self.assertEqual(result["status"], "DECLARED_DEPTH_COMPLETE")
        self.assertEqual(result["characters"], 6)
        self.assertEqual(result["round_role_records"], 24)
        self.assertFalse(result["certifies_all_laws_or_risks"])

    def test_unknown_security_outcome_blocks_even_if_reviewed(self):
        row = self.depth["security_checks"][0]
        row.update(status="reviewed", outcome="unknown", segment_ids=[self.bundle["segments"][0]["id"]])
        result = self.assess()
        self.assertEqual(result["status"], "PARTIAL_AUDIT")
        self.assertIn("SECURITY_UNKNOWN", result["blockers"])

    def test_known_missing_safeguard_can_be_reported_as_risk(self):
        self.depth["security_checks"][0].update(status="reviewed", outcome="missing",
            segment_ids=[self.bundle["segments"][0]["id"]])
        self.assertEqual(self.assess()["status"], "DECLARED_DEPTH_COMPLETE")

    def test_unverified_source_and_uncertain_facts_block(self):
        self.depth["sources"][0]["status"] = "unverified"
        self.depth["scope"]["locations"]["status"] = "assumed"
        self.depth["open_issues"] = ["Synthetic unresolved question"]
        blockers = self.assess()["blockers"]
        self.assertIn("SOURCE_UNVERIFIED", blockers)
        self.assertIn("SCOPE_NOT_CONFIRMED", blockers)
        self.assertIn("OPEN_ISSUES", blockers)

    def test_missing_hop_and_unreviewed_extension_block(self):
        self.depth["chains"] = []
        self.depth["chain_frontier"] = ["Unreviewed continuation"]
        blockers = self.assess()["blockers"]
        self.assertIn("MULTIHOP_COVERAGE_MISSING", blockers)
        self.assertIn("CHAIN_FRONTIER", blockers)

    def test_disconnected_chain_rejected(self):
        self.depth["chains"][0]["edge_ids"] = ["E2", "E1"]
        with self.assertRaisesRegex(d.DepthError, "DISCONNECTED"):
            self.assess()

    def test_missing_role_round_or_character_review_rejected(self):
        for mutation in (lambda x: x["rounds"].pop(),
                         lambda x: x["rounds"][0].update(segment_ids=[]),
                         lambda x: x["rounds"][-1].update(relation_ids=[])):
            candidate = copy.deepcopy(self.depth)
            mutation(candidate)
            with self.assertRaises(d.DepthError):
                self.assess(depth=candidate)

    def test_character_gap_rejected_even_with_fresh_digest(self):
        self.bundle["segments"][1]["start"] += 1
        self.bundle["input_digest"] = p.digest({k: v for k, v in self.bundle.items() if k != "input_digest"})
        self.depth["input_digest"] = self.bundle["input_digest"]
        with self.assertRaisesRegex(d.DepthError, "CHARACTER_GAP"):
            self.assess()

    def test_legal_category_missing_or_all_inapplicable_rejected(self):
        self.depth["legal_domains"].pop()
        with self.assertRaisesRegex(d.DepthError, "REQUIRED_ROWS"):
            self.assess()
        self.setUp()
        self.depth["legal_domains"][0]["status"] = "not_applicable"
        with self.assertRaisesRegex(d.DepthError, "CORE_CONTRACT"):
            self.assess()

    def test_expansion_limit_never_reports_complete(self):
        previous = d.MAX_TWO_HOP_PAIRS
        self.addCleanup(setattr, d, "MAX_TWO_HOP_PAIRS", previous)
        d.MAX_TWO_HOP_PAIRS = 0
        result = self.assess()
        self.assertEqual(result["status"], "PARTIAL_AUDIT")
        self.assertIn("RELATION_EXPANSION_LIMIT_REQUIRES_PARTITIONED_REVIEW", result["blockers"])


if __name__ == "__main__":
    unittest.main()
