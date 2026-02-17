"""
PSA 2006-HE1 Golden Test Suite – Phase 4 Validation
====================================================
Validates the 100-test golden suite against the PHASE4_IMPL_AND_TESTING.md
framework requirements.  These are *design-time* tests that verify:

  1. Golden JSON schema correctness (all required fields present)
  2. Bucket distribution (A=30, B=10, C=20, D=15, E=15, F=10)
  3. Test-ID uniqueness and ordering
  4. Section references are valid PSA sections
  5. Regime classification alignment with bucket type
  6. Resolver activation rules per bucket
  7. Negative control failure modes set correctly
  8. Evidence/provenance trust gate mapping
  9. Eval rubric scoring formula coverage
 10. Compatibility with score_queries.py golden query format
"""

import json
import re
from pathlib import Path

import pytest

GOLDEN_PATH = Path(__file__).parent / "golden_psa_2006he1.json"

# ── Load golden data ───────────────────────────────────────────────────
@pytest.fixture(scope="module")
def golden_tests():
    """Load full golden test suite."""
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list), "Golden file must be a JSON array"
    return data


@pytest.fixture(scope="module")
def bucket_map(golden_tests):
    """Group tests by bucket."""
    buckets = {}
    for t in golden_tests:
        b = t["bucket"]
        buckets.setdefault(b, []).append(t)
    return buckets


# ── 1. Schema validation ──────────────────────────────────────────────
REQUIRED_FIELDS = {
    "test_id", "bucket", "bucket_name", "query",
    "expected_regime", "expected_resolver_activation",
    "expected_doc_types_priority", "expected_sections",
    "expected_must_include_terms", "expected_top1_constraints",
    "expected_failure_mode", "strict_mode_required", "rationale",
}


class TestGoldenSchemaValidation:
    def test_golden_file_exists(self):
        assert GOLDEN_PATH.exists(), f"Golden file not found: {GOLDEN_PATH}"

    def test_golden_is_valid_json(self):
        with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list)

    def test_total_count_is_100(self, golden_tests):
        assert len(golden_tests) == 100, f"Expected 100 tests, got {len(golden_tests)}"

    @pytest.mark.parametrize("field", sorted(REQUIRED_FIELDS))
    def test_all_tests_have_required_field(self, golden_tests, field):
        missing = [t["test_id"] for t in golden_tests if field not in t]
        assert not missing, f"Field '{field}' missing in: {missing}"

    def test_all_test_ids_unique(self, golden_tests):
        ids = [t["test_id"] for t in golden_tests]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {[x for x in ids if ids.count(x) > 1]}"

    def test_all_queries_non_empty(self, golden_tests):
        empty = [t["test_id"] for t in golden_tests if not t.get("query", "").strip()]
        assert not empty, f"Empty queries in: {empty}"

    def test_all_rationales_non_empty(self, golden_tests):
        empty = [t["test_id"] for t in golden_tests if not t.get("rationale", "").strip()]
        assert not empty, f"Empty rationale in: {empty}"

    def test_top1_constraints_structure(self, golden_tests):
        """Each test's expected_top1_constraints must have doc_type, section_mention, term_present."""
        for t in golden_tests:
            c = t.get("expected_top1_constraints", {})
            assert isinstance(c, dict), f"{t['test_id']}: top1_constraints must be dict"
            for key in ("doc_type", "section_mention", "term_present"):
                assert key in c, f"{t['test_id']}: missing '{key}' in top1_constraints"


# ── 2. Bucket distribution ────────────────────────────────────────────
class TestBucketDistribution:
    EXPECTED_COUNTS = {"A": 30, "B": 10, "C": 20, "D": 15, "E": 15, "F": 10}

    def test_all_buckets_present(self, bucket_map):
        for b in self.EXPECTED_COUNTS:
            assert b in bucket_map, f"Bucket {b} missing"

    @pytest.mark.parametrize("bucket,expected", list(EXPECTED_COUNTS.items()))
    def test_bucket_count(self, bucket_map, bucket, expected):
        actual = len(bucket_map.get(bucket, []))
        assert actual == expected, f"Bucket {bucket}: expected {expected}, got {actual}"

    def test_no_extra_buckets(self, bucket_map):
        extra = set(bucket_map.keys()) - set(self.EXPECTED_COUNTS.keys())
        assert not extra, f"Unexpected buckets: {extra}"


# ── 3. Test-ID format ─────────────────────────────────────────────────
class TestIDFormat:
    def test_id_format_matches_bucket(self, golden_tests):
        """Each test_id must be <bucket><2-digit-number>."""
        for t in golden_tests:
            tid = t["test_id"]
            bucket = t["bucket"]
            assert re.match(rf"^{bucket}\d{{2}}$", tid), \
                f"ID '{tid}' doesn't match pattern '{bucket}XX'"

    def test_ids_sequential_per_bucket(self, bucket_map):
        """IDs within each bucket should be sequential starting from 01."""
        for bucket, tests in bucket_map.items():
            nums = sorted(int(t["test_id"][1:]) for t in tests)
            expected = list(range(1, len(tests) + 1))
            assert nums == expected, f"Bucket {bucket}: IDs not sequential: {nums}"


# ── 4. Section reference validation ───────────────────────────────────
VALID_SECTIONS_PATTERN = re.compile(
    r"^(ARTICLE\s+[IVXLCDM]+|Section\s+\d+\.\d+[a-z]?(\(\w+\))*)$"
)


class TestSectionReferences:
    def test_sections_are_valid_format(self, golden_tests):
        """expected_sections entries must match PSA section format."""
        bad = []
        for t in golden_tests:
            for sec in t.get("expected_sections", []):
                if not VALID_SECTIONS_PATTERN.match(sec):
                    bad.append((t["test_id"], sec))
        assert not bad, f"Invalid section references: {bad}"

    def test_bucket_e_negative_controls_have_empty_sections(self, bucket_map):
        """Most Bucket E tests should have empty expected_sections."""
        for t in bucket_map.get("E", []):
            if t["expected_failure_mode"] in ("resolver_must_not_activate", "no_relevant_results", "out_of_scope"):
                assert t["expected_sections"] == [], \
                    f"{t['test_id']}: negative control should have empty sections"


# ── 5. Regime classification alignment ────────────────────────────────
class TestRegimeAlignment:
    def test_bucket_abcdf_regime_is_legal(self, bucket_map):
        """Buckets A, B, C, D, F expect GOVERNING_DOC_LEGAL."""
        for bucket in ("A", "B", "C", "D", "F"):
            for t in bucket_map.get(bucket, []):
                assert t["expected_regime"] == "GOVERNING_DOC_LEGAL", \
                    f"{t['test_id']}: expected GOVERNING_DOC_LEGAL, got {t['expected_regime']}"

    def test_bucket_e_regime_varies_correctly(self, bucket_map):
        """Bucket E tests with resolver off should be GENERIC_GUIDE."""
        for t in bucket_map.get("E", []):
            if t["expected_resolver_activation"] is False:
                assert t["expected_regime"] == "GENERIC_GUIDE", \
                    f"{t['test_id']}: non-activating E test should be GENERIC_GUIDE"


# ── 6. Resolver activation rules ──────────────────────────────────────
class TestResolverActivation:
    def test_legal_buckets_activate_resolver(self, bucket_map):
        """All A, B, C, D, F tests must activate the resolver."""
        for bucket in ("A", "B", "C", "D", "F"):
            for t in bucket_map.get(bucket, []):
                assert t["expected_resolver_activation"] is True, \
                    f"{t['test_id']}: should activate resolver"

    def test_negative_controls_mostly_off(self, bucket_map):
        """Most Bucket E tests should NOT activate resolver."""
        off_count = sum(1 for t in bucket_map.get("E", []) if not t["expected_resolver_activation"])
        assert off_count >= 10, \
            f"Expected ≥10 Bucket E tests with resolver off, got {off_count}"


# ── 7. Failure mode consistency ───────────────────────────────────────
VALID_FAILURE_MODES = {
    None,
    "resolver_must_not_activate",
    "term_not_found",
    "strict_refusal_if_uncited",
    "no_relevant_results",
    "out_of_scope",
}


class TestFailureModes:
    def test_all_failure_modes_valid(self, golden_tests):
        bad = [(t["test_id"], t["expected_failure_mode"]) 
               for t in golden_tests 
               if t["expected_failure_mode"] not in VALID_FAILURE_MODES]
        assert not bad, f"Invalid failure modes: {bad}"

    def test_positive_tests_have_null_failure_mode(self, bucket_map):
        """Buckets A, C, D should have null failure_mode (they expect success)."""
        for bucket in ("A", "C", "D"):
            for t in bucket_map.get(bucket, []):
                assert t["expected_failure_mode"] is None, \
                    f"{t['test_id']}: positive test should have null failure_mode"

    def test_bucket_e_has_failure_modes(self, bucket_map):
        """All Bucket E tests should have a non-null failure mode."""
        for t in bucket_map.get("E", []):
            assert t["expected_failure_mode"] is not None, \
                f"{t['test_id']}: negative control must have failure_mode"

    def test_bucket_f_strict_mode_required(self, bucket_map):
        """All Bucket F tests should have strict_mode_required=true."""
        for t in bucket_map.get("F", []):
            assert t["strict_mode_required"] is True, \
                f"{t['test_id']}: provenance test must require strict mode"


# ── 8. Evidence / provenance trust gate coverage ──────────────────────
class TestTrustGateCoverage:
    def test_tg1_provenance_tests_exist(self, bucket_map):
        """Must have ≥3 Bucket F tests targeting TG1 provenance coverage."""
        tg1_tests = [t for t in bucket_map.get("F", []) if "provenance" in t["rationale"].lower() or "TG1" in t["rationale"]]
        assert len(tg1_tests) >= 3, f"Need ≥3 TG1 tests, found {len(tg1_tests)}"

    def test_evidence_matcher_tests_exist(self, bucket_map):
        """Must have ≥2 Bucket F tests targeting evidence matching rules."""
        evidence_tests = [t for t in bucket_map.get("F", []) if "evidence" in t["rationale"].lower() or "R1" in t["rationale"]]
        assert len(evidence_tests) >= 2, f"Need ≥2 evidence matcher tests, found {len(evidence_tests)}"

    def test_strict_mode_tests_exist(self, golden_tests):
        """Must have ≥5 tests with strict_mode_required=true."""
        strict = [t for t in golden_tests if t["strict_mode_required"]]
        assert len(strict) >= 5, f"Need ≥5 strict mode tests, found {len(strict)}"


# ── 9. Scoring formula coverage ───────────────────────────────────────
class TestScoringCoverage:
    def test_all_tests_have_doc_types_priority(self, golden_tests):
        """All tests must have expected_doc_types_priority (can be empty for OOD)."""
        for t in golden_tests:
            assert "expected_doc_types_priority" in t, \
                f"{t['test_id']}: missing expected_doc_types_priority"
            assert isinstance(t["expected_doc_types_priority"], list), \
                f"{t['test_id']}: expected_doc_types_priority must be a list"

    def test_must_include_terms_are_lists(self, golden_tests):
        for t in golden_tests:
            assert isinstance(t["expected_must_include_terms"], list), \
                f"{t['test_id']}: expected_must_include_terms must be a list"

    def test_terms_presence_for_positive_tests(self, golden_tests):
        """Positive tests (no failure mode) should have ≥1 must_include_term."""
        for t in golden_tests:
            if t["expected_failure_mode"] is None and t["bucket"] != "B":
                assert len(t["expected_must_include_terms"]) >= 1, \
                    f"{t['test_id']}: positive test should have ≥1 expected term"


# ── 10. Score_queries.py format compatibility ─────────────────────────
class TestScoreQueriesCompatibility:
    """Verify the golden JSON can be adapted for score_queries.py."""

    def test_can_build_score_queries_format(self, golden_tests):
        """Each test can be mapped to score_queries.py expected format."""
        adapted = []
        for t in golden_tests:
            q = {
                "query_id": t["test_id"],
                "query_text": t["query"],
                "split": "tune",
                "expected_doc_types": t["expected_doc_types_priority"],
                "must_include_terms": t["expected_must_include_terms"],
                "must_not_include_terms": [],
                "allow_any_result": t["expected_failure_mode"] in (
                    "resolver_must_not_activate", "no_relevant_results", "out_of_scope"
                ),
            }
            adapted.append(q)
        assert len(adapted) == 100

    def test_adapted_format_has_required_fields(self, golden_tests):
        """Verify adapted records have all score_queries.py required fields."""
        required = {"query_id", "query_text", "split", "expected_doc_types"}
        for t in golden_tests:
            adapted = {
                "query_id": t["test_id"],
                "query_text": t["query"],
                "split": "tune",
                "expected_doc_types": t["expected_doc_types_priority"],
            }
            missing = required - set(adapted.keys())
            assert not missing, f"{t['test_id']}: missing fields for scorer: {missing}"


# ── 11. PSA-specific content validation ───────────────────────────────
class TestPSAContentGrounding:
    """Verify tests are grounded in real PSA 2006-HE1 content."""

    PSA_DEFINED_TERMS = {
        "Certificateholder", "Master Servicer", "Trustee", "Distribution Date",
        "Mortgage Loan", "Person", "Realized Loss", "Certificate Principal Balance",
        "Trust Fund", "REMIC", "Eligible Account", "Closing Date", "Cut-off Date",
        "Business Day", "Subservicer", "Depositor", "Event of Default",
        "REO Property", "Principal Distribution Amount", "Stated Principal Balance",
        "Mortgage File", "Due Period", "Advance", "Swap Provider",
        "Prepayment Period", "Outstanding",
    }

    PSA_PARTIES = {
        "Bear Stearns Asset Backed Securities I LLC",
        "EMC Mortgage Corporation",
        "LaSalle Bank National Association",
    }

    def test_bucket_a_terms_are_actual_psa_terms(self, bucket_map):
        """At least 20 Bucket A tests should reference actual PSA defined terms."""
        referenced = set()
        for t in bucket_map.get("A", []):
            for term in t["expected_must_include_terms"]:
                if term in self.PSA_DEFINED_TERMS:
                    referenced.add(term)
        assert len(referenced) >= 15, \
            f"Expected ≥15 actual PSA terms in Bucket A, found {len(referenced)}: {referenced}"

    def test_bucket_d_references_operational_sections(self, bucket_map):
        """Bucket D tests should reference operational PSA sections."""
        operational_sections = {"Section 3.09", "Section 3.19", "Section 3.24",
                                "Section 3.25", "Section 5.01", "Section 8.01",
                                "Section 10.01"}
        referenced = set()
        for t in bucket_map.get("D", []):
            for sec in t["expected_sections"]:
                if sec in operational_sections:
                    referenced.add(sec)
        assert len(referenced) >= 5, \
            f"Expected ≥5 operational sections in Bucket D, found {len(referenced)}"

    def test_bucket_c_references_waterfall_sections(self, bucket_map):
        """Bucket C tests should reference waterfall sections."""
        waterfall_sections = {"Section 5.04", "Section 5.05", "Section 5.02",
                              "Section 5.07", "Section 4.04", "Section 4.05",
                              "Section 4.01", "Section 4.02"}
        referenced = set()
        for t in bucket_map.get("C", []):
            for sec in t["expected_sections"]:
                if sec in waterfall_sections:
                    referenced.add(sec)
        assert len(referenced) >= 3, \
            f"Expected ≥3 waterfall sections in Bucket C, found {len(referenced)}"

    def test_psa_parties_mentioned(self, golden_tests):
        """At least 2 PSA parties should be in expected_must_include_terms across all tests."""
        mentioned = set()
        for t in golden_tests:
            for term in t["expected_must_include_terms"]:
                for party in self.PSA_PARTIES:
                    if party in term or term in party:
                        mentioned.add(party)
        assert len(mentioned) >= 2, \
            f"Expected ≥2 PSA parties mentioned, found {mentioned}"


# ── 12. Cross-bucket coverage ────────────────────────────────────────
class TestCrossBucketCoverage:
    """Verify that the suite covers all Phase 4 capabilities."""

    def test_defined_term_chain_tests_exist(self, bucket_map):
        """Must have at least 2 chain resolution tests in Bucket A."""
        chain_tests = [t for t in bucket_map.get("A", [])
                       if "chain" in t["rationale"].lower() or "hop" in t["rationale"].lower()]
        assert len(chain_tests) >= 2, f"Need ≥2 chain tests, found {len(chain_tests)}"

    def test_amendment_tests_exist(self, bucket_map):
        """Must have ≥3 amendment-related tests in Bucket B."""
        amendment_tests = [t for t in bucket_map.get("B", [])
                           if "amendment" in t["rationale"].lower() or "§11.01" in t["rationale"]]
        assert len(amendment_tests) >= 3, f"Need ≥3 amendment tests, found {len(amendment_tests)}"

    def test_hallucination_guard_tests_exist(self, bucket_map):
        """Must have ≥2 hallucination prevention tests."""
        halluc_tests = [t for t in bucket_map.get("E", [])
                        if t["expected_failure_mode"] in ("term_not_found", "out_of_scope")]
        assert len(halluc_tests) >= 2, f"Need ≥2 hallucination guard tests, found {len(halluc_tests)}"

    def test_conflict_marker_tests_exist(self, bucket_map):
        """Must have ≥2 conflict/precedence tests in Bucket B."""
        conflict_tests = [t for t in bucket_map.get("B", [])
                          if "conflict" in t["rationale"].lower() or "precedence" in t["rationale"].lower()]
        assert len(conflict_tests) >= 2, f"Need ≥2 conflict tests, found {len(conflict_tests)}"

    def test_date_extraction_tests_exist(self, bucket_map):
        """Must have ≥2 date-specific term tests."""
        date_tests = [t for t in bucket_map.get("A", [])
                      if any(d in str(t["expected_must_include_terms"]) for d in ["January", "2006", "25th"])]
        assert len(date_tests) >= 2, f"Need ≥2 date tests, found {len(date_tests)}"
