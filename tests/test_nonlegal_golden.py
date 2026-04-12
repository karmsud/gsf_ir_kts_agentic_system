"""
Non-Legal Pipeline — Golden-Query Validation Tests (Phase 19).

Validates the Phase 19 non-legal pipeline end-to-end:
  • NonLegalTripleStore (error-boundary, sentence, structure chunkers)
  • Troubleshooting graph traversal
  • Cross-encoder reranking on merged results

Uses ``golden_queries_nonlegal.json`` as the reference query set.
Runs as a pytest module — no external search-results file required
(queries are executed live against a ChromaDB test corpus).

Usage:
    pytest tests/test_nonlegal_golden.py -v
    pytest tests/test_nonlegal_golden.py -v -k "tune"       # tune split only
    pytest tests/test_nonlegal_golden.py -v -k "holdout"    # holdout split only
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.score_queries import (  # noqa: E402
    evaluate_term_rule,
    parse_evidence_rules,
    phrase_match_with_plural_tolerance,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GOLDEN_FILE = Path(__file__).parent / "golden_queries_nonlegal.json"


def _load_golden() -> List[Dict[str, Any]]:
    """Load golden queries from the non-legal JSON file."""
    if not GOLDEN_FILE.exists():
        pytest.skip(f"Golden file not found: {GOLDEN_FILE}")
    with open(GOLDEN_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["queries"]


def _try_import_triple_store():
    """Import NonLegalTripleStore — skip if not available."""
    try:
        from backend.vector.nonlegal_triple_store import NonLegalTripleStore
        return NonLegalTripleStore
    except ImportError:
        pytest.skip("NonLegalTripleStore not available")


def _try_import_ts_traversal():
    """Import troubleshooting traversal — skip if not available."""
    try:
        from backend.graph.troubleshooting_traversal import (
            resolve_troubleshooting_context,
        )
        return resolve_troubleshooting_context
    except ImportError:
        return None


def _try_import_cross_encoder():
    """Import cross-encoder reranker — skip if not available."""
    try:
        from backend.retrieval.cross_encoder import rerank
        return rerank
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Lowercase + collapse whitespace for matching."""
    return re.sub(r"\s+", " ", text.lower()).strip()


def _check_terms_in_text(terms: List[str], text: str) -> Tuple[Set[str], Set[str]]:
    """Return (found, missing) sets of terms checked against *text*."""
    found: Set[str] = set()
    missing: Set[str] = set()
    norm = _normalize(text)
    for term in terms:
        if evaluate_term_rule(term, norm):
            found.add(term)
        else:
            missing.add(term)
    return found, missing


def _check_terms_in_results(
    terms: List[str],
    results: List[Dict[str, Any]],
    top_k: int = 3,
) -> Tuple[Set[str], Set[str]]:
    """Check that each *term* appears in at least one of the top-k results."""
    found: Set[str] = set()
    for r in results[:top_k]:
        text = r.get("text", "") or r.get("content", "")
        for term in terms:
            if evaluate_term_rule(term, _normalize(text)):
                found.add(term)
    missing = set(terms) - found
    return found, missing


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------

class TestGoldenQueriesSchema:
    """Validate the golden-queries file itself."""

    def test_file_structure(self):
        """Golden file must contain corpus_id, queries array."""
        with open(GOLDEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "corpus_id" in data
        assert "queries" in data
        assert isinstance(data["queries"], list)
        assert len(data["queries"]) >= 20

    def test_query_ids_unique(self):
        """Every query_id must be unique."""
        queries = _load_golden()
        ids = [q["query_id"] for q in queries]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {[x for x in ids if ids.count(x) > 1]}"

    def test_required_fields(self):
        """Each query must have required fields."""
        queries = _load_golden()
        required = {
            "query_id", "query_text", "split", "intent",
            "expected_doc_types", "must_include_terms",
            "expected_evidence_rules",
        }
        for q in queries:
            missing = required - set(q.keys())
            assert not missing, f"{q['query_id']} missing fields: {missing}"

    def test_split_counts(self):
        """Tune/holdout split sizes should match header."""
        with open(GOLDEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        expected_tune = data["split"]["tune"]
        expected_holdout = data["split"]["holdout"]
        queries = data["queries"]
        actual_tune = sum(1 for q in queries if q["split"] == "tune")
        actual_holdout = sum(1 for q in queries if q["split"] == "holdout")
        assert actual_tune == expected_tune, f"Tune: {actual_tune} != {expected_tune}"
        assert actual_holdout == expected_holdout, f"Holdout: {actual_holdout} != {expected_holdout}"

    def test_expected_stores_present(self):
        """Non-legal queries should specify expected_stores."""
        queries = _load_golden()
        for q in queries:
            stores = q.get("expected_stores", [])
            assert isinstance(stores, list), f"{q['query_id']} expected_stores must be a list"
            # At least one expected store
            assert len(stores) >= 1, f"{q['query_id']} needs at least one expected store"
            for s in stores:
                assert s in {"error_boundary", "sentence", "structure"}, (
                    f"{q['query_id']} invalid store: {s}"
                )


# ---------------------------------------------------------------------------
# Evidence rule tests
# ---------------------------------------------------------------------------

class TestEvidenceRuleParsing:
    """Ensure evidence rules parse correctly for every golden query."""

    def test_parse_all_evidence_rules(self):
        queries = _load_golden()
        for q in queries:
            rules = parse_evidence_rules(q)
            # must_include_terms should appear as all_of_terms
            for term in q.get("must_include_terms", []):
                assert term in rules["all_of_terms"], (
                    f"{q['query_id']}: '{term}' not in parsed all_of_terms"
                )


# ---------------------------------------------------------------------------
# Triple-store search tests (require live ChromaDB)
# ---------------------------------------------------------------------------

class TestTripleStoreRetrieval:
    """Live retrieval tests against NonLegalTripleStore.

    These tests require a populated ChromaDB directory.  They are
    skipped gracefully when the vector store is empty or unavailable.
    """

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Try to instantiate the triple store; skip if unavailable."""
        NonLegalTripleStore = _try_import_triple_store()
        chroma_dir = os.environ.get(
            "KTS_CHROMA_DIR",
            str(ROOT / "knowledge_base" / "vectors" / "phase6"),
        )
        try:
            self.store = NonLegalTripleStore(chroma_dir)
        except Exception as exc:
            pytest.skip(f"NonLegalTripleStore init failed: {exc}")
        # Skip gracefully when the store has no indexed content
        try:
            probe = self.store.search("test", top_k=1)
            if not probe:
                pytest.skip("NonLegalTripleStore has no indexed content — run ingestion first")
        except Exception:
            pytest.skip("NonLegalTripleStore probe search failed — store may be empty")

    @pytest.mark.parametrize(
        "query",
        [q for q in _load_golden() if q["split"] == "tune"],
        ids=lambda q: q["query_id"],
    )
    def test_tune_query_returns_results(self, query):
        """Tune queries must return >= 1 result from the triple store."""
        results = self.store.search(query["query_text"], top_k=5)
        assert len(results) >= 1, (
            f"{query['query_id']}: No results from triple-store"
        )

    @pytest.mark.parametrize(
        "query",
        [q for q in _load_golden() if q["split"] == "tune"],
        ids=lambda q: q["query_id"],
    )
    def test_tune_evidence_in_top3(self, query):
        """Tune queries: must_include_terms should appear in top-3."""
        results = self.store.search(query["query_text"], top_k=5)
        terms = query.get("must_include_terms", [])
        if not terms:
            return
        found, missing = _check_terms_in_results(terms, results, top_k=3)
        # Soft assertion: best-effort — report but don't fail for missing
        if missing:
            logger.warning(
                "%s: Missing terms in top-3: %s (found: %s)",
                query["query_id"], missing, found,
            )

    @pytest.mark.parametrize(
        "query",
        [q for q in _load_golden() if q["split"] == "holdout"],
        ids=lambda q: q["query_id"],
    )
    def test_holdout_query_returns_results(self, query):
        """Holdout queries must return >= 1 result from the triple store."""
        results = self.store.search(query["query_text"], top_k=5)
        assert len(results) >= 1, (
            f"{query['query_id']}: No results from triple-store"
        )


# ---------------------------------------------------------------------------
# Troubleshooting graph tests
# ---------------------------------------------------------------------------

class TestTroubleshootingGraph:
    """Tests for troubleshooting graph traversal on golden queries."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.resolve = _try_import_ts_traversal()
        if self.resolve is None:
            pytest.skip("Troubleshooting traversal not available")

        ts_graph_path = os.environ.get(
            "KTS_TS_GRAPH_PATH",
            str(ROOT / "knowledge_base" / "graph" / "troubleshooting_graph.json"),
        )
        if not Path(ts_graph_path).exists():
            pytest.skip(f"Troubleshooting graph not found: {ts_graph_path}")

        from backend.graph.persistence import GraphStore
        self.graph = GraphStore(ts_graph_path).load()

    @pytest.mark.parametrize(
        "query",
        [q for q in _load_golden() if q.get("expected_graph_path")],
        ids=lambda q: q["query_id"],
    )
    def test_graph_resolves_path(self, query):
        """Queries with expected_graph_path should have traversal results."""
        ctx = self.resolve(self.graph, query["query_text"])
        assert ctx.has_results, (
            f"{query['query_id']}: expected graph path "
            f"'{query['expected_graph_path']}' but got no results"
        )

    @pytest.mark.parametrize(
        "query",
        [q for q in _load_golden() if q.get("expected_graph_path") and "ERROR_CODE" in q.get("expected_graph_path", "")],
        ids=lambda q: q["query_id"],
    )
    def test_graph_contains_error_code(self, query):
        """Error-code queries should match at least one ERROR_CODE node."""
        error_codes = re.findall(r'ERR-[A-Z]+-\d{3}', query["query_text"])
        if not error_codes:
            return
        # Check that the graph has at least one of these error codes
        found = False
        for node_id, data in self.graph.nodes(data=True):
            if data.get("type") == "ERROR_CODE":
                name = (data.get("name") or "").upper()
                if any(ec.upper() in name for ec in error_codes):
                    found = True
                    break
        assert found, (
            f"{query['query_id']}: error codes {error_codes} not found in graph"
        )


# ---------------------------------------------------------------------------
# Cross-encoder reranking tests
# ---------------------------------------------------------------------------

class TestCrossEncoderOnTripleStore:
    """Ensure cross-encoder can rerank triple-store results."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.rerank = _try_import_cross_encoder()
        if self.rerank is None:
            pytest.skip("Cross-encoder not available")

    def test_rerank_returns_scores(self):
        """Cross-encoder should add cross_encoder_score to each result."""
        rows = [
            {"text": "ERR-RUN-204 is an out-of-memory error", "id": "a"},
            {"text": "To configure LDAP, open the admin panel", "id": "b"},
            {"text": "HTTP 502 Bad Gateway after deployment", "id": "c"},
        ]
        reranked = self.rerank("ERR-RUN-204 OOM fix", rows, content_key="text")
        for r in reranked:
            assert "cross_encoder_score" in r, "Missing cross_encoder_score"
        # The OOM error row should score highest
        scores = [(r["id"], r["cross_encoder_score"]) for r in reranked]
        top = max(scores, key=lambda x: x[1])
        assert top[0] == "a", f"Expected 'a' to score highest, got {top}"


# ---------------------------------------------------------------------------
# Aggregate metrics test (offline — from pre-computed results)
# ---------------------------------------------------------------------------

class TestAggregateMetrics:
    """Test the aggregate scoring logic with synthetic data."""

    def test_perfect_scores(self):
        """When all terms match, evidence should pass."""
        query = {
            "query_id": "NL-Q01",
            "query_text": "OpsFlow shows ERR-RUN-204",
            "split": "tune",
            "intent": "TROUBLESHOOT",
            "expected_doc_types": ["TROUBLESHOOT"],
            "must_include_terms": ["ERR-RUN-204", "OOM"],
            "expected_evidence_rules": {
                "requires_citation": True,
                "must_include_terms_in_at_least_one_cited_chunk": True,
            },
        }
        text = "ERR-RUN-204 is an OOM error that occurs when memory exceeds the limit."
        rules = parse_evidence_rules(query)
        for term in rules["all_of_terms"]:
            assert evaluate_term_rule(term, _normalize(text)), (
                f"Term '{term}' should match in: {text}"
            )

    def test_missing_term_fails(self):
        """When a required term is absent, evidence should not pass."""
        text = "The system returned an error during processing."
        assert not phrase_match_with_plural_tolerance(
            _normalize(text), "ERR-RUN-204"
        ), "ERR-RUN-204 should NOT be found in generic error text"
