from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Skip test files whose dependencies haven't been created yet
collect_ignore = [str(Path(__file__).parent / "test_gold_standards_validation.py")]


# ---------------------------------------------------------------------------
# Async event-loop isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_asyncio_loop():
    """Give every test a fresh, valid asyncio event loop.

    Under Python 3.9, ``asyncio.run()`` leaves the thread's loop unset *and*
    flags ``_set_called=True``, which makes a subsequent
    ``asyncio.get_event_loop()`` raise ``RuntimeError: There is no current event
    loop`` instead of auto-creating one. Some suites use ``asyncio.run()`` and
    others use ``get_event_loop().run_until_complete()``; resetting a fresh loop
    per test keeps both styles working together regardless of execution order.
    """
    import asyncio

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield
    finally:
        # Close every loop tied to this test (the one we created plus any the
        # test swapped in) so we never leak event loops across the suite.
        try:
            current = asyncio.get_event_loop_policy()._local._loop
        except Exception:  # pragma: no cover - defensive
            current = None
        for lp in {loop, current}:
            if lp is not None:
                try:
                    if not lp.is_closed():
                        lp.close()
                except Exception:  # pragma: no cover - defensive cleanup
                    pass


# ---------------------------------------------------------------------------
# pytest CLI option: --fast
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    parser.addoption(
        "--fast",
        action="store_true",
        default=False,
        help="Run a representative ~5%% smoke subset (~120 of 2300+ tests). "
             "Deterministic: same tests every run. At least 1 test per file.",
    )


# Files that are too slow for --fast (real corpus ingestion, subprocess CLI, etc.)
_FAST_SKIP_FILES = {
    "test_e2e_real_corpus.py",
    "test_phase2_cli_10x.py",
}


def pytest_collection_modifyitems(config, items):
    """When --fast is given, keep ~5%% of tests (at least 1 per file).

    Selection is deterministic (MD5 hash of node-id) so the same subset is
    chosen every run, making results reproducible.
    Heavy integration files listed in _FAST_SKIP_FILES are excluded entirely.
    A 30-second per-test timeout is enforced.
    """
    if not config.getoption("--fast"):
        return

    # ---- enforce per-test timeout when --fast is active ----
    for item in items:
        if not item.get_closest_marker("timeout"):
            item.add_marker(pytest.mark.timeout(30))

    # Group collected tests by source file, skip heavy files
    by_file: dict[object, list] = defaultdict(list)
    for item in items:
        fname = Path(str(item.fspath)).name
        if fname in _FAST_SKIP_FILES:
            continue
        by_file[item.fspath].append(item)

    selected: list = []
    for _fspath, file_items in sorted(by_file.items(), key=lambda kv: str(kv[0])):
        n = len(file_items)
        # Keep ceiling(n / 20) — i.e. 5 %, minimum 1
        keep = max(1, -(-n // 20))
        # Deterministic pick: sort by hash, take the first `keep`
        file_items.sort(key=lambda it: hashlib.md5(it.nodeid.encode()).hexdigest())
        selected.extend(file_items[:keep])

    deselected = [item for item in items if item not in set(selected)]
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = selected


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """Register custom markers used across all phase tests."""
    for marker, desc in [
        ("phase8", "Phase 8 RAG Upgrade tests"),
        ("phase9", "Phase 9 Directed Critique tests"),
        ("phase10", "Phase 10 Conversation Memory & Session Intelligence tests"),
        ("phase11", "Phase 11 VS Code Native Intelligence Layer tests"),
        ("critique_gen", "Increment 9.1 — critique question generation tests"),
        ("critique_loop", "Increment 9.2 — directed critique loop tests"),
        ("multi_doc", "Increment 9.3 — multi-doc provenance merging tests"),
        ("comparative", "A/B comparison tests (with vs without critique)"),
        ("query_rewrite", "Phase 10.2 — query rewriting tests"),
        ("session_memory", "Phase 10.3 — session memory & document bias tests"),
        ("history_summarize", "Phase 10.4 — history summarization tests"),
        ("requires_llm", "Requires a live LLM API — slow"),
        # Phase 17 — Multi-Deal Knowledge Isolation
        ("phase17", "Phase 17 Multi-Deal Knowledge Isolation tests"),
        ("phase17_doc_filter", "Phase 17 — Document filter read-side wiring"),
        ("phase17_graph", "Phase 17 — Dual graph metadata & partitioning"),
        ("phase17_catalog", "Phase 17 — Deal catalog schema upgrade"),
        ("phase17_scope", "Phase 17 — Scope resolver pipeline"),
        ("phase17_routing", "Phase 17 — Retriever routing & mode dispatch"),
        ("phase17_multi_deal", "Phase 17 — Multi-deal parallel search"),
        ("phase17_diff", "Phase 17 — Diff & aggregate analytical modes"),
        ("phase17_cli", "Phase 17 — CLI list-deals & mode options"),
        ("phase17_attribution", "Phase 17 — Result attribution rendering"),
        ("phase17_integration", "Phase 17 — Cross-step integration"),
        ("phase17_performance", "Phase 17 — Performance & concurrency"),
        ("phase17_golden", "Phase 17 — Golden query validations"),
        ("golden", "Golden PSA E2E tests against kb_test corpus"),
        ("phase17_regression", "Phase 17 — Backward-compatibility regression"),
        ("prebuild", "Pre-build validation gate tests"),
    ]:
        config.addinivalue_line("markers", f"{marker}: {desc}")


@pytest.fixture(autouse=True)
def _clean_runtime_dirs(monkeypatch):
    runtime_dir = Path(tempfile.mkdtemp(prefix="kts_test_runtime_", dir=str(ROOT)))
    monkeypatch.setenv("KTS_KB_PATH", str(runtime_dir))

    for child in [runtime_dir / "documents", runtime_dir / "vectors", runtime_dir / "graph", runtime_dir / "logs"]:
        child.mkdir(parents=True, exist_ok=True)

    yield

    shutil.rmtree(runtime_dir, ignore_errors=True)
