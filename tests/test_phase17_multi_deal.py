"""Phase 17 — Multi-Deal Parallel Execution tests (Step 7)."""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── helpers ──────────────────────────────────────────────────

def _run(coro):
    """Run an async coroutine synchronously (no pytest-asyncio needed)."""
    return asyncio.run(coro)


def _make_config(**overrides) -> MagicMock:
    """Return a minimal mock config accepted by RetrievalService.__init__."""
    cfg = MagicMock()
    cfg.chroma_persist_dir = "mock_chroma"
    cfg.graph_path = "mock_graph.json"
    cfg.session_memory_enabled = False
    cfg.query_rewriting_enabled = False
    cfg.temporal_reasoning_enabled = False
    cfg.hyde_enabled = False
    cfg.extraction_mode_enabled = False
    cfg.summary_mode_enabled = False
    cfg.comparison_mode_enabled = False
    cfg.audit_mode_enabled = False
    cfg.definition_mode_enabled = False
    cfg.contradiction_detection_enabled = False
    cfg.baseline_corpus_enabled = False
    cfg.anomaly_detection_enabled = False
    cfg.deal_catalog_enabled = False
    cfg.phase17_max_parallel_scopes = 5
    cfg.phase17_multi_scope_timeout_ms = 30000
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _make_agent_result(results: list[dict], success: bool = True) -> MagicMock:
    """Build a mock AgentResult with a payload containing ``results``."""
    ar = MagicMock()
    ar.success = success
    ar.payload = {"results": results}
    ar.data = {"results": results}
    return ar


def _hit(score: float, text: str = "chunk", **extra) -> dict:
    """Shorthand for a single result hit dict."""
    d = {"score": score, "text": text}
    d.update(extra)
    return d


def _scope_expr(slug: str, doc_filter: str | None = None, kts_path: str = "") -> dict:
    """Build a scope expression dict matching ``_multi_scope_search`` input."""
    return {"slug": slug, "doc_filter": doc_filter, "kts_path": kts_path or slug}


# ── Patch targets ────────────────────────────────────────────
# We patch heavy dependencies in RetrievalService.__init__ so we can
# instantiate the class cheaply.
_INIT_PATCHES = [
    "backend.agents.retrieval_service.VectorStore",
    "backend.agents.retrieval_service.GraphStore",
    "backend.agents.retrieval_service.get_embedding_provider",
    "backend.agents.retrieval_service.ConfidenceScorer",
    "backend.agents.retrieval_service.GapDetector",
]


def _build_svc(config=None):
    """Instantiate a RetrievalService with all heavy deps mocked out."""
    from backend.agents.retrieval_service import RetrievalService

    cfg = config or _make_config()
    with patch.multiple(
        "backend.agents.retrieval_service",
        VectorStore=MagicMock(),
        GraphStore=MagicMock(),
        get_embedding_provider=MagicMock(return_value=MagicMock()),
        ConfidenceScorer=MagicMock(),
        GapDetector=MagicMock(),
    ):
        svc = RetrievalService(cfg)
    return svc


# ── Tests ────────────────────────────────────────────────────

class TestMultiDealParallelExecution:
    """10 tests for _multi_scope_search / _collect_multi_scope_results."""

    # 1 ─ two scopes both return results
    def test_multi_scope_search_two_deals(self) -> None:
        """Mock 2 scopes → results from both returned."""
        svc = _build_svc()

        scope_a = _scope_expr("deal_a")
        scope_b = _scope_expr("deal_b")

        hits_a = [_hit(0.9, "a1"), _hit(0.8, "a2")]
        hits_b = [_hit(0.85, "b1")]

        def _fake_execute(req):
            slug = req.get("scope_override", "")
            if slug == "deal_a":
                return _make_agent_result(hits_a)
            return _make_agent_result(hits_b)

        with patch("backend.agents.retrieval_service.RetrievalService", autospec=True) as MockRS, \
             patch("config.settings.scope_config", return_value=_make_config()):
            MockRS.return_value.execute.side_effect = _fake_execute
            merged = _run(svc._multi_scope_search(
                "test query", [scope_a, scope_b], max_results_per_scope=5,
            ))

        assert len(merged) == 3
        texts = {h["text"] for h in merged}
        assert texts == {"a1", "a2", "b1"}

    # 2 ─ each result has deal_scope attribution
    def test_multi_scope_search_result_attribution(self) -> None:
        """Each result carries the correct ``deal_scope`` field."""
        svc = _build_svc()

        def _fake_execute(req):
            slug = req.get("scope_override", "")
            return _make_agent_result([_hit(0.5, f"from_{slug}")])

        with patch("backend.agents.retrieval_service.RetrievalService", autospec=True) as MockRS, \
             patch("config.settings.scope_config", return_value=_make_config()):
            MockRS.return_value.execute.side_effect = _fake_execute
            merged = _run(svc._multi_scope_search(
                "q", [_scope_expr("alpha"), _scope_expr("beta")],
            ))

        scopes_seen = {h["deal_scope"] for h in merged}
        assert scopes_seen == {"alpha", "beta"}

    # 3 ─ merged results sorted by score descending
    def test_multi_scope_search_sorted_by_score(self) -> None:
        """Merged results are ordered by score descending."""
        svc = _build_svc()

        def _fake_execute(req):
            slug = req.get("scope_override", "")
            if slug == "deal_x":
                return _make_agent_result([_hit(0.3), _hit(0.95)])
            return _make_agent_result([_hit(0.7)])

        with patch("backend.agents.retrieval_service.RetrievalService", autospec=True) as MockRS, \
             patch("config.settings.scope_config", return_value=_make_config()):
            MockRS.return_value.execute.side_effect = _fake_execute
            merged = _run(svc._multi_scope_search(
                "q", [_scope_expr("deal_x"), _scope_expr("deal_y")],
            ))

        scores = [h["score"] for h in merged]
        assert scores == sorted(scores, reverse=True)

    # 4 ─ doc_filter applied per-scope
    def test_multi_scope_search_with_doc_filter(self) -> None:
        """Per-scope doc_filter is forwarded to each child execute call."""
        svc = _build_svc()
        captured_reqs: list[dict] = []

        def _fake_execute(req):
            captured_reqs.append(dict(req))
            return _make_agent_result([_hit(0.5)])

        with patch("backend.agents.retrieval_service.RetrievalService", autospec=True) as MockRS, \
             patch("config.settings.scope_config", return_value=_make_config()):
            MockRS.return_value.execute.side_effect = _fake_execute
            _run(svc._multi_scope_search(
                "q",
                [
                    _scope_expr("deal_1", doc_filter="PSA"),
                    _scope_expr("deal_2", doc_filter="INDENTURE"),
                ],
            ))

        filters = {r["doc_name_prefix"] for r in captured_reqs}
        assert "PSA" in filters
        assert "INDENTURE" in filters

    # 5 ─ one of three scopes throws → other two still return
    def test_multi_scope_one_failure(self) -> None:
        """If 1 of 3 scopes throws, results from the other 2 are returned."""
        svc = _build_svc()

        call_count = 0

        def _fake_execute(req):
            nonlocal call_count
            call_count += 1
            slug = req.get("scope_override", "")
            if slug == "bad_deal":
                raise RuntimeError("scope failed")
            return _make_agent_result([_hit(0.6, f"ok_{slug}")])

        with patch("backend.agents.retrieval_service.RetrievalService", autospec=True) as MockRS, \
             patch("config.settings.scope_config", return_value=_make_config()):
            MockRS.return_value.execute.side_effect = _fake_execute
            merged = _run(svc._multi_scope_search(
                "q",
                [_scope_expr("good_1"), _scope_expr("bad_deal"), _scope_expr("good_2")],
            ))

        # Only results from good_1 and good_2 should survive
        assert len(merged) == 2
        texts = {h["text"] for h in merged}
        assert "ok_good_1" in texts
        assert "ok_good_2" in texts

    # 6 ─ parallel performance: 3 scopes with delay → total < 0.5s
    def test_multi_scope_search_parallel_performance(self) -> None:
        """3 scopes each with 0.1s delay should finish in < 0.5s (parallelism)."""
        svc = _build_svc()

        def _slow_execute(req):
            import time as _t
            _t.sleep(0.1)
            return _make_agent_result([_hit(0.5)])

        with patch("backend.agents.retrieval_service.RetrievalService", autospec=True) as MockRS, \
             patch("config.settings.scope_config", return_value=_make_config()):
            MockRS.return_value.execute.side_effect = _slow_execute

            start = time.monotonic()
            merged = _run(svc._multi_scope_search(
                "q",
                [_scope_expr("d1"), _scope_expr("d2"), _scope_expr("d3")],
            ))
            elapsed = time.monotonic() - start

        assert len(merged) == 3
        # Sequential would be ≥0.3s; parallel should be ~0.1s + overhead
        assert elapsed < 0.5, f"Took {elapsed:.2f}s – expected parallel execution"

    # 7 ─ wildcard resolution produces multiple scopes
    def test_wildcard_resolution_to_multi_scope(self) -> None:
        """ScopeExpr wildcards get resolved to concrete scopes via catalog."""
        from backend.common.scope_resolver import (
            ParsedCommand,
            ScopeExpr,
            resolve_scopes,
        )

        parsed = ParsedCommand(
            mode="search",
            scopes=[ScopeExpr(slug="bear_stearns", doc_filter="PSA", is_wildcard=True)],
            query="What is Distribution Date?",
        )
        catalog = MagicMock()
        catalog.search_deals.return_value = [
            {"slug": "bear_stearns_2006"},
            {"slug": "bear_stearns_2007"},
            {"slug": "bear_stearns_2008"},
        ]

        resolved = resolve_scopes(parsed, catalog)

        assert len(resolved) == 3
        assert all(not s.is_wildcard for s in resolved)
        assert {s.slug for s in resolved} == {
            "bear_stearns_2006",
            "bear_stearns_2007",
            "bear_stearns_2008",
        }
        assert all(s.doc_filter == "PSA" for s in resolved)

    # 8 ─ all scopes return empty → empty merged result
    def test_multi_scope_empty_results(self) -> None:
        """All scopes returning empty → merged list is empty."""
        svc = _build_svc()

        def _fake_execute(req):
            return _make_agent_result([])

        with patch("backend.agents.retrieval_service.RetrievalService", autospec=True) as MockRS, \
             patch("config.settings.scope_config", return_value=_make_config()):
            MockRS.return_value.execute.side_effect = _fake_execute
            merged = _run(svc._multi_scope_search(
                "q", [_scope_expr("empty_1"), _scope_expr("empty_2")],
            ))

        assert merged == []

    # 9 ─ result tagging includes doc_filter_applied field
    def test_multi_scope_result_tagging(self) -> None:
        """Every result carries ``doc_filter_applied`` from its scope expr."""
        svc = _build_svc()

        def _fake_execute(req):
            return _make_agent_result([_hit(0.5)])

        with patch("backend.agents.retrieval_service.RetrievalService", autospec=True) as MockRS, \
             patch("config.settings.scope_config", return_value=_make_config()):
            MockRS.return_value.execute.side_effect = _fake_execute
            merged = _run(svc._multi_scope_search(
                "q",
                [
                    _scope_expr("deal_a", doc_filter="PSA"),
                    _scope_expr("deal_b", doc_filter=None),
                ],
            ))

        filters = {h["doc_filter_applied"] for h in merged}
        assert "PSA" in filters
        # None doc_filter stays None (dict.get returns None when value is None)
        assert None in filters or "" in filters

    # 10 ─ max_results_per_scope is respected (cap = per_scope × num_scopes)
    def test_max_results_per_scope_respected(self) -> None:
        """Total merged results capped at max_results_per_scope × len(scopes)."""
        svc = _build_svc()

        def _fake_execute(req):
            # Return 10 hits per scope — more than the cap
            return _make_agent_result([_hit(0.5 + i * 0.01) for i in range(10)])

        with patch("backend.agents.retrieval_service.RetrievalService", autospec=True) as MockRS, \
             patch("config.settings.scope_config", return_value=_make_config()):
            MockRS.return_value.execute.side_effect = _fake_execute
            merged = _run(svc._multi_scope_search(
                "q",
                [_scope_expr("d1"), _scope_expr("d2")],
                max_results_per_scope=3,
            ))

        # Cap = 3 × 2 = 6
        assert len(merged) <= 6
