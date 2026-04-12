"""
Golden PSA End-to-End Test Harness  (in-process API)
=====================================================

Ingests the ``kb_test/`` corpus *once* (per pytest session), then runs the
golden query pack (``tests/golden_kb_test.json``) through the Python API
**in-process** — no subprocess overhead, models loaded once.

Run via F5 → "Test: Golden PSA (kb_test)" or from the terminal::

    python -m pytest tests/test_golden_kb_test.py -v --tb=short

Environment variables honoured:
    KTS_GOLDEN_SKIP_INGEST=1   — skip ingestion (use pre-existing .kts dirs)
    KTS_GOLDEN_VERBOSE=1       — print full search output per query
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import load_config, scope_config  # noqa: E402
from backend.agents import RetrievalService  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
KB_TEST = ROOT / "kb_test"
GOLDEN_FILE = ROOT / "tests" / "golden_kb_test.json"
RESULTS_DIR = ROOT / "tests" / "golden_results"
PYTHON = str(ROOT / ".venv_build" / "Scripts" / "python.exe")
if not Path(PYTHON).exists():
    PYTHON = sys.executable


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class QueryResult:
    query_id: str
    query: str
    group: str
    mode: str
    scope: Optional[str]
    doc_filter: Optional[str]
    success: bool = False
    raw_data: Optional[dict] = None
    error: Optional[str] = None
    chunks: list = field(default_factory=list)
    elapsed_s: float = 0.0


@dataclass
class QueryScore:
    query_id: str
    group: str
    passed: bool
    term_recall: float = 0.0
    doc_type_match: bool = False
    has_results: bool = False
    notes: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _serialize(value):
    """Recursively serialize dataclasses / dicts / lists to plain dicts."""
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _serialize(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    return value


def _scope_to_folder(scope_slug: str, corpus_root: Path) -> str:
    """Map a scope slug (e.g., 'bear_stearns_2006_he1') to actual folder name."""
    for d in corpus_root.iterdir():
        if d.is_dir():
            if d.name.lower().replace("-", "_").replace(" ", "_") == scope_slug.lower():
                return d.name
    try:
        from backend.vector.deal_catalog import slugify
        for d in corpus_root.iterdir():
            if d.is_dir():
                if slugify(d.name) == scope_slug:
                    return d.name
    except ImportError:
        pass
    return scope_slug


def _is_glob(scope_slug: str) -> bool:
    """Check if scope slug contains glob characters."""
    return any(c in scope_slug for c in ("*", "?", "["))


def _expand_glob_scope(scope_slug: str, corpus_root: Path) -> list[str]:
    """Expand a glob-style scope (e.g. 'bear_stearns*') to matching folder names."""
    import fnmatch
    pattern = scope_slug.lower().replace("-", "_").replace(" ", "_")
    matches = []
    for d in corpus_root.iterdir():
        if d.is_dir():
            normalized = d.name.lower().replace("-", "_").replace(" ", "_")
            if fnmatch.fnmatch(normalized, pattern):
                matches.append(d.name)
    return matches


def _extract_chunks(result_data: dict) -> list:
    """Extract context_chunks from the AgentResult.data dict."""
    sr = result_data.get("search_result")
    if sr is None:
        return []
    # SearchResult dataclass → convert to dict if needed
    if is_dataclass(sr) and not isinstance(sr, type):
        sr = asdict(sr)
    if isinstance(sr, dict):
        return sr.get("context_chunks", [])
    return []


def _all_chunk_text(chunks: list) -> str:
    """Concatenate all text content from chunks (case-folded)."""
    parts = []
    for c in chunks:
        if is_dataclass(c) and not isinstance(c, type):
            c = asdict(c)
        if isinstance(c, dict):
            parts.append(c.get("content", ""))
            parts.append(c.get("text", ""))
            parts.append(c.get("section_text", ""))
    return " ".join(parts).lower()


def _term_recall(expected_terms: list[str], text: str) -> float:
    """Fraction of expected terms found in text (case-insensitive)."""
    if not expected_terms:
        return 1.0
    hits = sum(1 for t in expected_terms if t.lower() in text)
    return hits / len(expected_terms)


# ---------------------------------------------------------------------------
# Session-scoped ingestion fixture
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def ingested_corpus():
    """Ingest kb_test corpus once for the entire test session.

    Each sub-folder in kb_test/ is ingested as a separate scope.
    If KTS_GOLDEN_SKIP_INGEST=1 is set, skips ingestion and assumes
    .kts directories already exist from a prior run.
    """
    skip_ingest = os.environ.get("KTS_GOLDEN_SKIP_INGEST", "").strip() in ("1", "true", "yes")

    if not KB_TEST.exists():
        pytest.skip(f"kb_test corpus not found at {KB_TEST}")

    scopes_found = [d for d in KB_TEST.iterdir() if d.is_dir() and d.name != ".kts"]
    if not scopes_found:
        pytest.skip("No sub-folders found in kb_test/")

    if skip_ingest:
        logger.info("[Golden] Skipping ingestion (KTS_GOLDEN_SKIP_INGEST=1)")
    else:
        logger.info("[Golden] Ingesting kb_test corpus (%d scopes)...", len(scopes_found))
        t0 = time.time()
        # Use CLI subprocess just for ingestion (one-shot, heavy but once)
        cmd = [PYTHON, "-m", "cli.main", "ingest", "--paths", str(KB_TEST)]
        env = {**os.environ, "PYTHONPATH": str(ROOT)}
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900,
                              cwd=str(ROOT), env=env)
        elapsed = time.time() - t0
        logger.info("[Golden] Ingestion finished in %.1fs (exit=%d)", elapsed, proc.returncode)
        if proc.returncode != 0:
            logger.error("[Golden] Ingestion stderr:\n%s", proc.stderr[-3000:])

    # Verify at least one scope has .kts
    has_kts = any((KB_TEST / d.name / ".kts").exists() for d in scopes_found)
    if not has_kts:
        pytest.fail(
            f"No .kts directories found after ingestion. "
            f"Scopes checked: {[d.name for d in scopes_found]}"
        )

    return {
        "corpus_root": str(KB_TEST),
        "scopes": [d.name for d in scopes_found],
    }


@pytest.fixture(scope="session")
def golden_pack():
    """Load the golden query pack."""
    if not GOLDEN_FILE.exists():
        pytest.skip(f"Golden file not found: {GOLDEN_FILE}")
    with GOLDEN_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def retrieval_services(ingested_corpus):
    """Create RetrievalService instances for each scope — loaded ONCE.

    Returns a dict mapping scope_slug → RetrievalService.
    Also stores a '__base_config__' key for multi-scope operations.
    """
    services: Dict[str, Any] = {}
    scopes = ingested_corpus["scopes"]
    corpus_root = Path(ingested_corpus["corpus_root"])

    # Base config (uses first scope as default KB path)
    first_kts = str(corpus_root / scopes[0] / ".kts")
    os.environ["KTS_KB_PATH"] = first_kts
    base_config = load_config()
    services["__base_config__"] = base_config

    for scope_name in scopes:
        kts_path = str(corpus_root / scope_name / ".kts")
        if not Path(kts_path).exists():
            logger.warning("[Golden] .kts not found for scope %s, skipping", scope_name)
            continue
        scoped_cfg = scope_config(base_config, kts_path)
        slug = scope_name.lower().replace("-", "_").replace(" ", "_")
        try:
            rs = RetrievalService(scoped_cfg)
            services[slug] = rs
            logger.info("[Golden] RetrievalService loaded for scope: %s", slug)
        except Exception as exc:
            logger.error("[Golden] Failed to load scope %s: %s", slug, exc)
            services[slug] = None

    return services


# ---------------------------------------------------------------------------
# In-process query execution
# ---------------------------------------------------------------------------
def _run_golden_query(q: dict, corpus_root: Path, services: dict) -> QueryResult:
    """Run a single golden query in-process via RetrievalService."""
    qr = QueryResult(
        query_id=q["query_id"],
        query=q["query"],
        group=q.get("group_id", ""),
        mode=q.get("mode", "search"),
        scope=q.get("scope"),
        doc_filter=q.get("doc_filter"),
    )

    mode = q.get("mode", "search")
    scope_slug = q.get("scope")
    scopes_list = q.get("scopes", [])
    doc_filter = q.get("doc_filter")

    # Build the request dict matching cli/main.py search command
    request = {
        "query": q["query"],
        "max_results": 5,
        "session_id": f"golden_{q['query_id']}",
        "conversation_history": [],
        "extra_queries": [],
        "compare_scopes": [],
        "phase17_mode": mode,
        "phase17_scopes": [],
    }

    if doc_filter:
        request["doc_name_prefix"] = doc_filter.upper()

    if mode not in ("search", None):
        request["retrieval_mode"] = mode

    # Resolve which RetrievalService(s) to use
    rs = None

    if scope_slug and _is_glob(scope_slug):
        # Wildcard scope — expand to matching folders and treat as multi-scope
        matched_folders = _expand_glob_scope(scope_slug, corpus_root)
        if not matched_folders:
            qr.error = f"No folders match wildcard scope: {scope_slug}"
            return qr
        resolved_kts = [str(corpus_root / f / ".kts") for f in matched_folders]
        request["phase17_scopes"] = resolved_kts
        request.pop("scope_override", None)
        # Use first matched scope's service as the driver
        first_slug = matched_folders[0].lower().replace("-", "_").replace(" ", "_")
        rs = services.get(first_slug)
        if rs is None:
            qr.error = f"No RetrievalService for wildcard first match: {first_slug}"
            return qr

    elif scope_slug:
        # Single scope — RetrievalService is already scoped via scope_config(),
        # so do NOT set scope_override (it triggers the scope router which
        # rejects the path and returns needs_scope_clarification=True).
        folder = _scope_to_folder(scope_slug, corpus_root)
        slug_key = folder.lower().replace("-", "_").replace(" ", "_")
        rs = services.get(slug_key)
        if rs is None:
            qr.error = f"No RetrievalService for scope: {slug_key}"
            return qr

    elif scopes_list:
        # Multi-scope: build scoped paths list
        resolved_kts = []
        for s in scopes_list:
            folder = _scope_to_folder(s, corpus_root)
            resolved_kts.append(str(corpus_root / folder / ".kts"))
        request["phase17_scopes"] = resolved_kts
        # Use first scope's service as the driver
        first_folder = _scope_to_folder(scopes_list[0], corpus_root)
        first_slug = first_folder.lower().replace("-", "_").replace(" ", "_")
        rs = services.get(first_slug)
        if rs is None:
            qr.error = f"No RetrievalService for first scope: {first_slug}"
            return qr

    else:
        # No scope specified — use first available service
        for key, svc in services.items():
            if not key.startswith("__") and svc is not None:
                rs = svc
                break
        if rs is None:
            qr.error = "No RetrievalService available"
            return qr

    try:
        t0 = time.time()
        result = rs.execute(request)
        qr.elapsed_s = time.time() - t0
        qr.success = result.success
        qr.raw_data = _serialize(result.data) if result.data else {}
        qr.chunks = _extract_chunks(result.data)
    except Exception as exc:
        qr.error = str(exc)
        logger.exception("[Golden] Query %s failed", q["query_id"])

    return qr


# ---------------------------------------------------------------------------
# Score a single query result
# ---------------------------------------------------------------------------
def _score_query(q: dict, result: QueryResult) -> QueryScore:
    """Score a query result against golden expectations."""
    score = QueryScore(
        query_id=q["query_id"],
        group=q.get("group_id", result.group),
        passed=False,
    )

    # Special: /list mode
    if q.get("mode") == "list":
        deals = []
        if result.raw_data:
            deals = result.raw_data.get("deals", [])
            sr = result.raw_data.get("search_result", {})
            if isinstance(sr, dict):
                deals = deals or sr.get("deals", [])
        min_expected = q.get("expect_deals_count_gte", 1)
        score.has_results = len(deals) >= min_expected
        score.passed = score.has_results
        score.notes = f"{len(deals)} deals returned (need >= {min_expected})"
        return score

    # Special: negative controls
    if q.get("expect_empty_or_low_relevance"):
        if not result.chunks or len(result.chunks) == 0:
            score.passed = True
            score.has_results = False
            score.notes = "Correctly returned empty (negative control)"
        else:
            text = _all_chunk_text(result.chunks)
            expected = q.get("expected_must_include_terms", [])
            if expected:
                recall = _term_recall(expected, text)
                score.term_recall = recall
                score.passed = recall < 0.3  # Low recall = good for negative
                score.notes = f"Negative: recall={recall:.0%} (want <30%)"
            else:
                score.passed = True
                score.notes = f"Negative: {len(result.chunks)} chunks (no term check)"
            score.has_results = True
        return score

    # Special: /diff and /aggregate modes
    if q.get("mode") in ("diff", "aggregate"):
        if result.raw_data:
            output_text = json.dumps(result.raw_data, default=str).lower()
            expected_terms = q.get("expected_must_include_terms", [])
            score.term_recall = _term_recall(expected_terms, output_text)
            score.has_results = bool(result.raw_data.get("search_result"))
            score.passed = (score.term_recall >= 0.3 or not expected_terms) and score.has_results
            score.notes = f"{q['mode']}: recall={score.term_recall:.0%}, {result.elapsed_s:.1f}s"
        else:
            score.notes = f"{q['mode']}: no output"
        return score

    # Standard search scoring
    if result.error and not result.chunks:
        score.notes = f"ERROR: {result.error[:200]}"
        return score

    score.has_results = len(result.chunks) > 0
    if not score.has_results:
        score.notes = f"No results returned ({result.elapsed_s:.1f}s)"
        return score

    text = _all_chunk_text(result.chunks)
    expected_terms = q.get("expected_must_include_terms", [])
    score.term_recall = _term_recall(expected_terms, text)

    # Doc type check
    expected_dt = q.get("expected_doc_type")
    if expected_dt:
        chunk_doc_types = set()
        for c in result.chunks:
            if is_dataclass(c) and not isinstance(c, type):
                c = asdict(c)
            if isinstance(c, dict):
                dt = c.get("doc_type", "") or ""
                meta = c.get("metadata", {})
                if isinstance(meta, dict):
                    dt = dt or meta.get("doc_type", "")
                chunk_doc_types.add(dt.upper())
        score.doc_type_match = expected_dt.upper() in chunk_doc_types or not chunk_doc_types
    else:
        score.doc_type_match = True

    score.passed = score.term_recall >= 0.5 and score.has_results
    score.notes = (
        f"recall={score.term_recall:.0%}, "
        f"chunks={len(result.chunks)}, "
        f"dt_match={score.doc_type_match}, "
        f"{result.elapsed_s:.1f}s"
    )
    return score


# ---------------------------------------------------------------------------
# Pytest tests — parametrized by group
# ---------------------------------------------------------------------------
class TestGoldenIngestion:
    """Verify ingestion completed for all scopes."""

    @pytest.mark.golden
    def test_corpus_exists(self):
        assert KB_TEST.exists(), f"kb_test not found at {KB_TEST}"

    @pytest.mark.golden
    def test_scopes_present(self):
        scopes = [d.name for d in KB_TEST.iterdir() if d.is_dir() and d.name != ".kts"]
        assert len(scopes) >= 2, f"Expected >= 2 scopes, found {scopes}"

    @pytest.mark.golden
    def test_ingestion_ran(self, ingested_corpus):
        assert ingested_corpus is not None
        assert len(ingested_corpus["scopes"]) >= 2

    @pytest.mark.golden
    def test_kts_dirs_exist(self, ingested_corpus):
        for scope in ingested_corpus["scopes"]:
            kts = KB_TEST / scope / ".kts"
            assert kts.exists(), f".kts missing for scope: {scope}"

    @pytest.mark.golden
    def test_retrieval_services_loaded(self, retrieval_services):
        real_services = {k: v for k, v in retrieval_services.items()
                        if not k.startswith("__") and v is not None}
        assert len(real_services) >= 2, (
            f"Expected >= 2 retrieval services, got {list(real_services.keys())}"
        )


def _load_queries_by_group(group_id: str) -> list[dict]:
    """Load golden queries for a specific group."""
    if not GOLDEN_FILE.exists():
        return []
    with GOLDEN_FILE.open("r", encoding="utf-8") as f:
        pack = json.load(f)
    for group in pack.get("test_groups", []):
        if group["group_id"] == group_id:
            for q in group["queries"]:
                q["group_id"] = group_id
            return group["queries"]
    return []


# --- Deal-scope queries ---
_DEAL_SCOPE_QUERIES = _load_queries_by_group("DEAL_SCOPE")

class TestDealScope:
    """Deal-scope golden queries: single deal, no doc filter."""

    @pytest.mark.golden
    @pytest.mark.parametrize(
        "query_spec",
        _DEAL_SCOPE_QUERIES,
        ids=[q["query_id"] for q in _DEAL_SCOPE_QUERIES],
    )
    def test_deal_scope(self, ingested_corpus, retrieval_services, query_spec):
        result = _run_golden_query(query_spec, KB_TEST, retrieval_services)
        score = _score_query(query_spec, result)

        verbose = os.environ.get("KTS_GOLDEN_VERBOSE", "").strip() in ("1", "true")
        if verbose:
            print(f"\n[{score.query_id}] {query_spec['query'][:60]}")
            print(f"  → {score.notes}")

        _save_result(query_spec, result, score)

        assert score.has_results, (
            f"[{score.query_id}] No results for: {query_spec['query'][:60]}"
        )
        assert score.term_recall >= 0.5, (
            f"[{score.query_id}] Term recall too low: {score.term_recall:.0%}. "
            f"Notes: {score.notes}"
        )


# --- Document-scope queries ---
_DOC_SCOPE_QUERIES = _load_queries_by_group("DOC_SCOPE")

class TestDocScope:
    """Document-scope golden queries: deal + doc_filter."""

    @pytest.mark.golden
    @pytest.mark.parametrize(
        "query_spec",
        _DOC_SCOPE_QUERIES,
        ids=[q["query_id"] for q in _DOC_SCOPE_QUERIES],
    )
    def test_doc_scope(self, ingested_corpus, retrieval_services, query_spec):
        result = _run_golden_query(query_spec, KB_TEST, retrieval_services)
        score = _score_query(query_spec, result)

        verbose = os.environ.get("KTS_GOLDEN_VERBOSE", "").strip() in ("1", "true")
        if verbose:
            print(f"\n[{score.query_id}] {query_spec['query'][:60]}")
            print(f"  → {score.notes}")

        _save_result(query_spec, result, score)

        assert score.has_results, (
            f"[{score.query_id}] No results for doc-scoped query"
        )
        assert score.term_recall >= 0.5, (
            f"[{score.query_id}] Term recall too low: {score.term_recall:.0%}. "
            f"Notes: {score.notes}"
        )


# --- Cross-deal queries ---
_CROSS_DEAL_QUERIES = _load_queries_by_group("CROSS_DEAL")

class TestCrossDeal:
    """Cross-deal queries: /diff and /aggregate across multiple scopes."""

    @pytest.mark.golden
    @pytest.mark.parametrize(
        "query_spec",
        _CROSS_DEAL_QUERIES,
        ids=[q["query_id"] for q in _CROSS_DEAL_QUERIES],
    )
    def test_cross_deal(self, ingested_corpus, retrieval_services, query_spec):
        result = _run_golden_query(query_spec, KB_TEST, retrieval_services)
        score = _score_query(query_spec, result)

        verbose = os.environ.get("KTS_GOLDEN_VERBOSE", "").strip() in ("1", "true")
        if verbose:
            print(f"\n[{score.query_id}] {query_spec['query'][:60]}")
            print(f"  → {score.notes}")

        _save_result(query_spec, result, score)

        assert result.success or result.raw_data, (
            f"[{score.query_id}] Cross-deal query produced no output. Error: {result.error}"
        )


# --- Negative controls ---
_NEGATIVE_QUERIES = _load_queries_by_group("NEGATIVE")

class TestNegativeControls:
    """Negative controls: scoping should isolate results."""

    @pytest.mark.golden
    @pytest.mark.parametrize(
        "query_spec",
        _NEGATIVE_QUERIES,
        ids=[q["query_id"] for q in _NEGATIVE_QUERIES],
    )
    def test_negative(self, ingested_corpus, retrieval_services, query_spec):
        result = _run_golden_query(query_spec, KB_TEST, retrieval_services)
        score = _score_query(query_spec, result)

        verbose = os.environ.get("KTS_GOLDEN_VERBOSE", "").strip() in ("1", "true")
        if verbose:
            print(f"\n[{score.query_id}] {query_spec['query'][:60]}")
            print(f"  → {score.notes}")

        _save_result(query_spec, result, score)

        assert score.passed, (
            f"[{score.query_id}] Negative control failed: {score.notes}"
        )


# --- Wildcard / List queries ---
_WILDCARD_QUERIES = _load_queries_by_group("WILDCARD")

class TestWildcard:
    """Wildcard scope patterns and /list mode."""

    @pytest.mark.golden
    @pytest.mark.parametrize(
        "query_spec",
        _WILDCARD_QUERIES,
        ids=[q["query_id"] for q in _WILDCARD_QUERIES],
    )
    def test_wildcard(self, ingested_corpus, retrieval_services, query_spec):
        result = _run_golden_query(query_spec, KB_TEST, retrieval_services)
        score = _score_query(query_spec, result)

        verbose = os.environ.get("KTS_GOLDEN_VERBOSE", "").strip() in ("1", "true")
        if verbose:
            print(f"\n[{score.query_id}] {query_spec['query'][:60]}")
            print(f"  → {score.notes}")

        _save_result(query_spec, result, score)

        if query_spec.get("mode") == "list":
            # List mode may pass or fail — just don't crash
            assert result.success or result.error is None, (
                f"[{score.query_id}] List mode error: {result.error}"
            )
        else:
            assert result.success or result.raw_data, (
                f"[{score.query_id}] Wildcard query returned no output"
            )


# ---------------------------------------------------------------------------
# Result persistence — one JSON per test run for analysis
# ---------------------------------------------------------------------------
_SESSION_RESULTS: list[dict] = []


def _save_result(query_spec: dict, result: QueryResult, score: QueryScore):
    """Append a query result to the session-level collection for reporting."""
    _SESSION_RESULTS.append({
        "query_id": score.query_id,
        "group": score.group,
        "query": query_spec["query"],
        "mode": query_spec.get("mode", "search"),
        "scope": query_spec.get("scope"),
        "doc_filter": query_spec.get("doc_filter"),
        "passed": score.passed,
        "term_recall": round(score.term_recall, 3),
        "doc_type_match": score.doc_type_match,
        "has_results": score.has_results,
        "chunk_count": len(result.chunks),
        "elapsed_s": round(result.elapsed_s, 2),
        "notes": score.notes,
        "error": result.error,
    })


@pytest.fixture(scope="session", autouse=True)
def write_golden_report():
    """Write collected results to disk after all tests run."""
    yield
    if _SESSION_RESULTS:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        report_path = RESULTS_DIR / f"golden_run_{ts}.json"

        total = len(_SESSION_RESULTS)
        passed = sum(1 for r in _SESSION_RESULTS if r["passed"])
        by_group: dict[str, dict] = {}
        for r in _SESSION_RESULTS:
            g = r["group"]
            by_group.setdefault(g, {"total": 0, "passed": 0, "avg_recall": []})
            by_group[g]["total"] += 1
            if r["passed"]:
                by_group[g]["passed"] += 1
            by_group[g]["avg_recall"].append(r["term_recall"])

        summary = {
            "total": total,
            "passed": passed,
            "pass_rate": round(passed / total, 3) if total else 0,
            "by_group": {
                g: {
                    "total": d["total"],
                    "passed": d["passed"],
                    "pass_rate": round(d["passed"] / d["total"], 3) if d["total"] else 0,
                    "avg_recall": round(sum(d["avg_recall"]) / len(d["avg_recall"]), 3)
                    if d["avg_recall"] else 0,
                }
                for g, d in by_group.items()
            },
        }

        report = {
            "timestamp": ts,
            "corpus": str(KB_TEST),
            "summary": summary,
            "results": _SESSION_RESULTS,
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\n{'=' * 70}")
        print(f"GOLDEN TEST REPORT: {report_path}")
        print(f"{'=' * 70}")
        print(f"  Total: {total}  |  Passed: {passed}  |  Rate: {summary['pass_rate']:.0%}")
        for g, d in summary["by_group"].items():
            print(
                f"  {g:<15} {d['passed']}/{d['total']}"
                f" ({d['pass_rate']:.0%})"
                f" avg_recall={d['avg_recall']:.0%}"
            )
        print(f"{'=' * 70}")
