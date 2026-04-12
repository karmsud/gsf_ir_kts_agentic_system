"""
Golden GSF IR Support Library End-to-End Test Harness
======================================================

Tests the ``kb_test/troubleshoot/`` corpus (GSF IR Support Library.md) —
the canonical **non-legal document** gold standard — using the full RAG
pipeline: HyDE, CRAG critique-loop, dual-vector (dense + BM25 fusion),
knowledge-graph retrieval, and cross-encoder reranking.

Scoring: 1-5 numeric per query.  Target: avg >= 4.5 / 5.0.

  Score 5 (Excellent)  term_recall >= 0.75 AND results returned
  Score 4 (Good)       term_recall >= 0.50 AND results returned
  Score 3 (Acceptable) term_recall >= 0.30 AND results returned
  Score 2 (Poor)       term_recall >= 0.10 AND results returned
  Score 1 (Fail)       no results OR term_recall < 0.10

Run all 20 tests::

    python -m pytest tests/test_golden_gsf_ir_support.py -v --tb=short

Skip re-ingestion (use existing .kts)::

    KTS_GOLDEN_SKIP_INGEST=1 python -m pytest tests/test_golden_gsf_ir_support.py -v

Environment variables:
    KTS_GOLDEN_SKIP_INGEST=1   — skip ingestion (use pre-existing .kts dirs)
    KTS_GOLDEN_VERBOSE=1       — print full scoring detail per query
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
# Project root on sys.path
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
KB_TROUBLESHOOT = ROOT / "kb_test" / "troubleshoot"
KB_ROOT = ROOT / "kb_test"
GOLDEN_FILE = ROOT / "tests" / "golden_gsf_ir_support.json"
RESULTS_DIR = ROOT / "tests" / "golden_results"
PYTHON = str(ROOT / ".venv_build" / "Scripts" / "python.exe")
if not Path(PYTHON).exists():
    PYTHON = sys.executable


# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------
SCORE_EXCELLENT = 5.0   # term_recall >= 0.75
SCORE_GOOD = 4.0        # term_recall >= 0.50
SCORE_ACCEPTABLE = 3.0  # term_recall >= 0.30
SCORE_POOR = 2.0        # term_recall >= 0.10
SCORE_FAIL = 1.0        # no results or recall < 0.10

TARGET_AVG_SCORE = 4.5
TARGET_MIN_PER_QUERY = SCORE_ACCEPTABLE  # every test must score at least 3


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class QueryResult:
    query_id: str
    query: str
    group: str
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
    score: float = SCORE_FAIL
    term_recall: float = 0.0
    has_results: bool = False
    chunk_count: int = 0
    notes: str = ""

    @property
    def passed(self) -> bool:
        return self.score >= TARGET_MIN_PER_QUERY


# ---------------------------------------------------------------------------
# JSON serialisation helper
# ---------------------------------------------------------------------------
def _serialize(value):
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _serialize(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# Chunk extraction helpers (shared with golden_kb_test)
# ---------------------------------------------------------------------------
def _extract_chunks(result_data: dict) -> list:
    sr = result_data.get("search_result")
    if sr is None:
        return []
    if is_dataclass(sr) and not isinstance(sr, type):
        sr = asdict(sr)
    if isinstance(sr, dict):
        return sr.get("context_chunks", [])
    return []


def _all_chunk_text(chunks: list) -> str:
    parts = []
    for c in chunks:
        if is_dataclass(c) and not isinstance(c, type):
            c = asdict(c)
        if isinstance(c, dict):
            parts.append(c.get("content", ""))
            parts.append(c.get("text", ""))
            parts.append(c.get("section_text", ""))
    return " ".join(parts).lower()


def _term_recall(expected_terms: list, text: str) -> float:
    """Fraction of expected_terms found case-insensitively in text."""
    if not expected_terms:
        return 1.0
    hits = sum(1 for t in expected_terms if t.lower() in text)
    return hits / len(expected_terms)


# ---------------------------------------------------------------------------
# 5-point scoring
# ---------------------------------------------------------------------------
def _compute_score(term_recall: float, has_results: bool) -> float:
    """Map (term_recall, has_results) → 1-5 numeric score."""
    if not has_results:
        return SCORE_FAIL
    if term_recall >= 0.75:
        return SCORE_EXCELLENT
    if term_recall >= 0.50:
        return SCORE_GOOD
    if term_recall >= 0.30:
        return SCORE_ACCEPTABLE
    if term_recall >= 0.10:
        return SCORE_POOR
    return SCORE_FAIL


def _score_query(q: dict, result: QueryResult) -> QueryScore:
    """Score a single query result against golden expectations."""
    score = QueryScore(
        query_id=q["query_id"],
        group=q.get("group_id", result.group),
    )

    if result.error and not result.chunks:
        score.notes = f"ERROR: {result.error[:200]}"
        return score

    score.has_results = bool(result.chunks)
    score.chunk_count = len(result.chunks)

    if not score.has_results:
        score.notes = f"No results ({result.elapsed_s:.1f}s)"
        score.score = SCORE_FAIL
        return score

    text = _all_chunk_text(result.chunks)
    expected_terms = q.get("expected_must_include_terms", [])
    score.term_recall = _term_recall(expected_terms, text)
    score.score = _compute_score(score.term_recall, score.has_results)
    score.notes = (
        f"score={score.score:.0f}/5  recall={score.term_recall:.0%}  "
        f"chunks={score.chunk_count}  {result.elapsed_s:.1f}s"
    )
    return score


# ---------------------------------------------------------------------------
# In-process query execution
# ---------------------------------------------------------------------------
def _run_query(q: dict, corpus_root: Path, services: dict) -> QueryResult:
    """Execute one golden query via the in-process RetrievalService."""
    scope_slug = q.get("scope")
    qr = QueryResult(
        query_id=q["query_id"],
        query=q["query"],
        group=q.get("group_id", ""),
        scope=scope_slug,
        doc_filter=q.get("doc_filter"),
    )

    request = {
        "query": q["query"],
        "max_results": 5,
        "session_id": f"gsf_ir_{q['query_id']}",
        "conversation_history": [],
        "extra_queries": [],
        "compare_scopes": [],
        "phase17_mode": q.get("mode", "search"),
        "phase17_scopes": [],
    }

    doc_filter = q.get("doc_filter")
    if doc_filter:
        request["doc_name_prefix"] = doc_filter.upper()

    # Resolve RetrievalService
    rs = None
    if scope_slug:
        # Normalise slug: lower + underscores
        slug_key = scope_slug.lower().replace("-", "_").replace(" ", "_")
        rs = services.get(slug_key)
        if rs is None:
            qr.error = f"No RetrievalService for scope: {slug_key} (available: {list(services.keys())})"
            return qr
    else:
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
        logger.exception("[GSF-IR-Golden] Query %s failed", q["query_id"])

    return qr


# ---------------------------------------------------------------------------
# Session-scoped ingestion fixture
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def ingested_troubleshoot():
    """Ingest the troubleshoot corpus once per session.

    If KTS_GOLDEN_SKIP_INGEST=1 is set, assumes kb_test/troubleshoot/.kts
    already exists from a prior run.
    """
    skip = os.environ.get("KTS_GOLDEN_SKIP_INGEST", "").strip() in ("1", "true", "yes")

    if not KB_TROUBLESHOOT.exists():
        pytest.skip(f"troubleshoot corpus not found at {KB_TROUBLESHOOT}")

    kts_dir = KB_TROUBLESHOOT / ".kts"

    if skip:
        logger.info("[GSF-IR] Skipping ingestion (KTS_GOLDEN_SKIP_INGEST=1)")
    elif not kts_dir.exists():
        logger.info("[GSF-IR] Ingesting troubleshoot corpus…")
        t0 = time.time()
        cmd = [PYTHON, "-m", "cli.main", "ingest", "--paths", str(KB_TROUBLESHOOT)]
        env = {**os.environ, "PYTHONPATH": str(ROOT)}
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=900, cwd=str(ROOT), env=env
        )
        elapsed = time.time() - t0
        logger.info("[GSF-IR] Ingestion finished in %.1fs (exit=%d)", elapsed, proc.returncode)
        if proc.returncode != 0:
            logger.error("[GSF-IR] Ingestion stderr:\n%s", proc.stderr[-3000:])
    else:
        logger.info("[GSF-IR] .kts already exists — skipping ingestion")

    if not kts_dir.exists():
        pytest.fail(f"No .kts directory found after ingestion at {kts_dir}")

    return {"corpus_root": str(KB_TROUBLESHOOT), "scope": "troubleshoot"}


@pytest.fixture(scope="session")
def gsf_ir_golden_pack():
    """Load the GSF IR Support Library golden query pack."""
    if not GOLDEN_FILE.exists():
        pytest.skip(f"Golden file not found: {GOLDEN_FILE}")
    with GOLDEN_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def gsf_ir_services(ingested_troubleshoot):
    """Create the RetrievalService for the troubleshoot scope — loaded once."""
    services: Dict[str, Any] = {}

    kts_path = str(KB_TROUBLESHOOT / ".kts")
    os.environ["KTS_KB_PATH"] = kts_path
    base_config = load_config()
    services["__base_config__"] = base_config

    scoped_cfg = scope_config(base_config, kts_path)
    try:
        rs = RetrievalService(scoped_cfg)
        services["troubleshoot"] = rs
        logger.info("[GSF-IR] RetrievalService loaded for troubleshoot scope")
    except Exception as exc:
        logger.error("[GSF-IR] Failed to load troubleshoot scope: %s", exc)
        services["troubleshoot"] = None

    return services


# ---------------------------------------------------------------------------
# Helpers to load query groups
# ---------------------------------------------------------------------------
def _load_group(group_id: str) -> list[dict]:
    """Return all queries for group_id from the golden pack (at import time)."""
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


# ---------------------------------------------------------------------------
# Result persistence
# ---------------------------------------------------------------------------
_SESSION_RESULTS: List[dict] = []
_SESSION_SCORES: List[float] = []


def _save_result(q: dict, result: QueryResult, score: QueryScore) -> None:
    _SESSION_RESULTS.append({
        "query_id": score.query_id,
        "group": score.group,
        "query": q["query"],
        "scope": q.get("scope"),
        "score": score.score,
        "term_recall": round(score.term_recall, 3),
        "has_results": score.has_results,
        "chunk_count": score.chunk_count,
        "elapsed_s": round(result.elapsed_s, 2),
        "notes": score.notes,
        "error": result.error,
    })
    _SESSION_SCORES.append(score.score)


# ---------------------------------------------------------------------------
#  Assert helper — DRY
# ---------------------------------------------------------------------------
def _assert_score(q: dict, result: QueryResult, score: QueryScore) -> None:
    verbose = os.environ.get("KTS_GOLDEN_VERBOSE", "").strip() in ("1", "true")
    if verbose:
        print(f"\n[{score.query_id}] {q['query'][:70]}")
        print(f"  -> {score.notes}")

    _save_result(q, result, score)

    assert score.has_results, (
        f"[{score.query_id}] No chunks returned for: {q['query'][:60]}\n"
        f"  Error: {result.error}"
    )
    assert score.score >= TARGET_MIN_PER_QUERY, (
        f"[{score.query_id}] Score too low: {score.score:.0f}/5 "
        f"(need >= {TARGET_MIN_PER_QUERY:.0f}). "
        f"term_recall={score.term_recall:.0%}  notes={score.notes}"
    )


# ---------------------------------------------------------------------------
# ════════════════════════  Test classes  ════════════════════════════════════
# ---------------------------------------------------------------------------

class TestGSFIRIngestion:
    """Sanity checks: corpus exists and is ingested."""

    @pytest.mark.gsf_ir
    def test_corpus_folder_exists(self):
        assert KB_TROUBLESHOOT.exists(), f"Troubleshoot corpus not found: {KB_TROUBLESHOOT}"

    @pytest.mark.gsf_ir
    def test_source_file_present(self):
        md = KB_TROUBLESHOOT / "GSF IR Support Library.md"
        assert md.exists(), f"Source markdown missing: {md}"

    @pytest.mark.gsf_ir
    def test_ingestion_ran(self, ingested_troubleshoot):
        assert ingested_troubleshoot is not None

    @pytest.mark.gsf_ir
    def test_kts_dir_exists(self, ingested_troubleshoot):
        kts = KB_TROUBLESHOOT / ".kts"
        assert kts.exists(), f".kts not found at {kts}"

    @pytest.mark.gsf_ir
    def test_retrieval_service_loaded(self, gsf_ir_services):
        rs = gsf_ir_services.get("troubleshoot")
        assert rs is not None, (
            "RetrievalService failed to load for troubleshoot scope. "
            f"Available: {list(gsf_ir_services.keys())}"
        )


# ---------------------------------------------------------------------------
# Import & Data-Loading queries
# ---------------------------------------------------------------------------
_IMPORT_QUERIES = _load_group("TS_IMPORT")


class TestTSImport:
    """Five import-related golden queries against GSF IR Support Library."""

    @pytest.mark.gsf_ir
    @pytest.mark.parametrize(
        "query_spec", _IMPORT_QUERIES, ids=[q["query_id"] for q in _IMPORT_QUERIES]
    )
    def test_import_query(self, ingested_troubleshoot, gsf_ir_services, query_spec):
        result = _run_query(query_spec, KB_TROUBLESHOOT, gsf_ir_services)
        score = _score_query(query_spec, result)
        _assert_score(query_spec, result, score)


# ---------------------------------------------------------------------------
# VDI / Citrix queries
# ---------------------------------------------------------------------------
_VDI_QUERIES = _load_group("TS_VDI_CITRIX")


class TestTSVDICitrix:
    """Four VDI/Citrix environment golden queries."""

    @pytest.mark.gsf_ir
    @pytest.mark.parametrize(
        "query_spec", _VDI_QUERIES, ids=[q["query_id"] for q in _VDI_QUERIES]
    )
    def test_vdi_query(self, ingested_troubleshoot, gsf_ir_services, query_spec):
        result = _run_query(query_spec, KB_TROUBLESHOOT, gsf_ir_services)
        score = _score_query(query_spec, result)
        _assert_score(query_spec, result, score)


# ---------------------------------------------------------------------------
# Workflow / Package-PDF queries
# ---------------------------------------------------------------------------
_WORKFLOW_QUERIES = _load_group("TS_WORKFLOW_PACKAGE")


class TestTSWorkflowPackage:
    """Five workflow / package-PDF / lock-error golden queries."""

    @pytest.mark.gsf_ir
    @pytest.mark.parametrize(
        "query_spec", _WORKFLOW_QUERIES, ids=[q["query_id"] for q in _WORKFLOW_QUERIES]
    )
    def test_workflow_query(self, ingested_troubleshoot, gsf_ir_services, query_spec):
        result = _run_query(query_spec, KB_TROUBLESHOOT, gsf_ir_services)
        score = _score_query(query_spec, result)
        _assert_score(query_spec, result, score)


# ---------------------------------------------------------------------------
# Macro / Excel / Trust-Center queries
# ---------------------------------------------------------------------------
_MACRO_QUERIES = _load_group("TS_MACRO_EXCEL")


class TestTSMacroExcel:
    """Four macro/Excel/Trust-Center golden queries."""

    @pytest.mark.gsf_ir
    @pytest.mark.parametrize(
        "query_spec", _MACRO_QUERIES, ids=[q["query_id"] for q in _MACRO_QUERIES]
    )
    def test_macro_query(self, ingested_troubleshoot, gsf_ir_services, query_spec):
        result = _run_query(query_spec, KB_TROUBLESHOOT, gsf_ir_services)
        score = _score_query(query_spec, result)
        _assert_score(query_spec, result, score)


# ---------------------------------------------------------------------------
# Terminology / Concepts queries
# ---------------------------------------------------------------------------
_CONCEPT_QUERIES = _load_group("TS_CONCEPTS")


class TestTSConcepts:
    """Two terminology/process-concept golden queries."""

    @pytest.mark.gsf_ir
    @pytest.mark.parametrize(
        "query_spec", _CONCEPT_QUERIES, ids=[q["query_id"] for q in _CONCEPT_QUERIES]
    )
    def test_concept_query(self, ingested_troubleshoot, gsf_ir_services, query_spec):
        result = _run_query(query_spec, KB_TROUBLESHOOT, gsf_ir_services)
        score = _score_query(query_spec, result)
        _assert_score(query_spec, result, score)


# ---------------------------------------------------------------------------
# Aggregate score test — MUST run after all parameterised tests
# ---------------------------------------------------------------------------
class TestGSFIRAggregateScore:
    """Verify the session-level avg score >= 4.5 across all 20 queries."""

    @pytest.mark.gsf_ir
    def test_avg_score_gte_target(self):
        """Fails if the rolling session average drops below TARGET_AVG_SCORE.

        This test is intentionally greedy — it will only be meaningful once
        the 20 parametrised tests above have run.  Use::

            pytest tests/test_golden_gsf_ir_support.py -v --tb=short

        to run the full suite in a single invocation.
        """
        if not _SESSION_SCORES:
            pytest.skip("No scores collected yet — run the full test suite")

        avg = sum(_SESSION_SCORES) / len(_SESSION_SCORES)
        below = [r for r in _SESSION_RESULTS if r["score"] < TARGET_MIN_PER_QUERY]

        fail_lines = []
        if below:
            fail_lines.append(f"Queries below min score ({TARGET_MIN_PER_QUERY:.0f}):")
            for r in below:
                fail_lines.append(
                    f"  [{r['query_id']}] score={r['score']:.0f}  "
                    f"recall={r['term_recall']:.0%}  {r['notes']}"
                )

        assert avg >= TARGET_AVG_SCORE, (
            f"Avg score {avg:.2f}/5.0 < target {TARGET_AVG_SCORE}/5.0 "
            f"({len(_SESSION_SCORES)} queries scored)\n" + "\n".join(fail_lines)
        )


# ---------------------------------------------------------------------------
# Session-level report fixture
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def write_gsf_ir_report():
    """Write a JSON report after all tests complete."""
    yield

    if not _SESSION_RESULTS:
        return

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    report_path = RESULTS_DIR / f"gsf_ir_run_{ts}.json"

    total = len(_SESSION_RESULTS)
    passed = sum(1 for r in _SESSION_RESULTS if r["score"] >= TARGET_MIN_PER_QUERY)
    avg_score = sum(r["score"] for r in _SESSION_RESULTS) / total if total else 0

    by_group: dict[str, dict] = {}
    for r in _SESSION_RESULTS:
        g = r["group"]
        by_group.setdefault(g, {"total": 0, "passed": 0, "scores": [], "recalls": []})
        by_group[g]["total"] += 1
        if r["score"] >= TARGET_MIN_PER_QUERY:
            by_group[g]["passed"] += 1
        by_group[g]["scores"].append(r["score"])
        by_group[g]["recalls"].append(r["term_recall"])

    summary = {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total, 3) if total else 0,
        "avg_score": round(avg_score, 2),
        "target_avg": TARGET_AVG_SCORE,
        "met_target": avg_score >= TARGET_AVG_SCORE,
        "by_group": {
            g: {
                "total": d["total"],
                "passed": d["passed"],
                "avg_score": round(sum(d["scores"]) / len(d["scores"]), 2)
                if d["scores"] else 0,
                "avg_recall": round(sum(d["recalls"]) / len(d["recalls"]), 3)
                if d["recalls"] else 0,
            }
            for g, d in by_group.items()
        },
    }

    report = {
        "timestamp": ts,
        "corpus": str(KB_TROUBLESHOOT),
        "document": "GSF IR Support Library.md",
        "summary": summary,
        "results": _SESSION_RESULTS,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # ── Console summary ──────────────────────────────────────────────────
    width = 72
    bar = "=" * width
    print(f"\n{bar}")
    print(f"  GSF IR SUPPORT LIBRARY — GOLDEN TEST REPORT: {report_path.name}")
    print(bar)
    print(f"  Total: {total}  |  Passed (>={TARGET_MIN_PER_QUERY:.0f}/5): {passed}"
          f"  |  Avg Score: {avg_score:.2f}/5.0"
          f"  ({'TARGET MET' if avg_score >= TARGET_AVG_SCORE else 'BELOW TARGET'})")
    print(f"  Target: avg >= {TARGET_AVG_SCORE}/5.0")
    print()
    for g, d in summary["by_group"].items():
        print(
            f"  {g:<22} {d['passed']}/{d['total']}"
            f"  avg={d['avg_score']:.2f}/5"
            f"  recall={d['avg_recall']:.0%}"
        )
    print(bar)

    # Show any failures
    failed = [r for r in _SESSION_RESULTS if r["score"] < TARGET_MIN_PER_QUERY]
    if failed:
        print(f"\n  FAILED QUERIES ({len(failed)}):")
        for r in failed:
            print(f"    [{r['query_id']}] score={r['score']:.0f}  "
                  f"recall={r['term_recall']:.0%}  {r['notes']}")
        print()
