"""Phase 19 + Follow-up: End-to-end import and functional audit."""
import os
import sys

# Ensure project root is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import traceback

results = {}
pass_count = 0
fail_count = 0


def check(label, fn):
    global pass_count, fail_count
    try:
        fn()
        print(f"[PASS] {label}")
        pass_count += 1
    except Exception as e:
        print(f"[FAIL] {label}: {e}")
        traceback.print_exc()
        fail_count += 1


print("=" * 60)
print("PHASE 19 END-TO-END IMPORT & FUNCTIONAL AUDIT")
print("=" * 60)


# ── 1. Config flags ──────────────────────────────────────────
def t1():
    from config.settings import KTSConfig
    c = KTSConfig()
    results["HyDE"] = c.hyde_enabled
    results["CRAG"] = c.crag_enabled
    results["TripleStore"] = c.nonlegal_triple_store_enabled
    results["TSGraph"] = c.troubleshooting_graph_enabled
    results["XEncoder"] = c.cross_encoder_enabled
    for k, v in results.items():
        assert v, f"{k} is OFF"

check("Config: all Phase 19 flags ON", t1)


# ── 2. CRAG imports + regex extraction ───────────────────────
def t2():
    from backend.retrieval.crag import (
        CRAGProcessor, CRAGConfig, CRAGResult,
        ClaimVerdict, VerifiedClaim, ClaimExtractor,
        ClaimVerifier, AnswerRewriter,
    )
    proc = CRAGProcessor(CRAGConfig())
    claims = proc.extractor.extract_with_regex(
        "ERR-RUN-204 caused by OOM. Fix is increase mem."
    )
    assert len(claims) >= 1, f"Got {len(claims)} claims"

check("CRAG: imports + regex claim extraction", t2)


# ── 3. Error-boundary chunker ────────────────────────────────
def t3():
    from backend.vector.error_boundary_chunker import chunk_by_error_boundaries
    txt = (
        "## ERR-AUTH-407\nProblem: SSO redirect fails behind proxy servers.\n"
        "Root Cause: Proxy strips Authorization headers from requests.\n"
        "Solution: Configure proxy to pass X-Forwarded-For and X-Forwarded-Proto headers.\n\n"
        "---\n\n"
        "## ERR-RUN-204\nProblem: OOM during batch processing of large data sets.\n"
        "Root Cause: Container memory limit is set too low at 512MB.\n"
        "Solution: Increase container memory to 4GB and add monitoring."
    )
    ch = chunk_by_error_boundaries("d1", "/t.md", txt, min_chunk_chars=20)
    assert len(ch) >= 2, f"Got {len(ch)} chunks"

check("Error-boundary chunker: 2+ chunks", t3)


# ── 4. Sentence chunker (no infinite loop) ───────────────────
def t4():
    from backend.vector.sentence_chunker import chunk_by_sentences
    txt = (
        "## ERR-AUTH-407\nProblem: SSO redirect fails behind proxy.\n"
        "Root Cause: Proxy strips auth headers.\n"
        "Solution: Configure proxy to pass X-Forwarded headers.\n---\n"
        "## ERR-RUN-204\nProblem: OOM during batch processing.\n"
        "Root Cause: Memory limit too low.\n"
        "Solution: Increase container memory to 4GB."
    )
    ch, par = chunk_by_sentences("d1", "/t.md", txt)
    assert len(ch) >= 2, f"Got {len(ch)} chunks"
    assert len(par) >= 2, f"Got {len(par)} parents"

check("Sentence chunker: chunks + parents", t4)


# ── 5. Structure chunker ─────────────────────────────────────
def t5():
    from backend.vector.structure_chunker import chunk_by_structure
    txt = (
        "# Troubleshooting Guide\n## Network Issues\n"
        "Firewall rules may block access.\n"
        "## Auth Issues\nSSO may fail behind proxy."
    )
    ch = chunk_by_structure("d1", "/t.md", txt)
    assert len(ch) >= 1, f"Got {len(ch)} chunks"

check("Structure chunker: heading detection", t5)


# ── 6. NonLegalTripleStore import ─────────────────────────────
def t6():
    from backend.vector.nonlegal_triple_store import (
        NonLegalTripleStore, COLL_ERROR_BOUNDARY,
        COLL_SENTENCE, COLL_SENTENCE_PARENT, COLL_STRUCTURE,
    )
    assert COLL_ERROR_BOUNDARY and COLL_SENTENCE and COLL_STRUCTURE

check("NonLegalTripleStore: import + collections", t6)


# ── 7. Troubleshooting schema ────────────────────────────────
def t7():
    from backend.graph.troubleshooting_schema import (
        TS_SCHEMA_VERSION, TS_NODE_TYPES, TS_EDGE_TYPES,
        validate_ts_node, validate_ts_edge,
    )
    assert len(TS_NODE_TYPES) >= 8, f"Got {len(TS_NODE_TYPES)}"
    assert len(TS_EDGE_TYPES) >= 12, f"Got {len(TS_EDGE_TYPES)}"
    # validate_ts_node(node_type, attrs) — raises on invalid
    try:
        validate_ts_node("ERROR_CODE", {"description": "ERR-001", "name": "ERR-001"})
    except Exception as e:
        raise AssertionError(f"validate_ts_node failed: {e}")
    try:
        validate_ts_edge("ADDRESSES")
    except Exception as e:
        raise AssertionError(f"validate_ts_edge failed: {e}")

check("TS schema: 8+ nodes, 12+ edges, validation", t7)


# ── 8. Troubleshooting builder import ────────────────────────
def t8():
    from backend.graph.troubleshooting_builder import (
        TroubleshootingGraphBuilder, ExtractedEntity, ExtractedRelation,
    )
    assert callable(TroubleshootingGraphBuilder)

check("TroubleshootingGraphBuilder: import", t8)


# ── 9. Troubleshooting traversal import ──────────────────────
def t9():
    from backend.graph.troubleshooting_traversal import (
        resolve_troubleshooting_context, find_related_errors,
        TroubleshootingResult, TraversalContext,
    )
    assert callable(resolve_troubleshooting_context)

check("Troubleshooting traversal: import", t9)


# ── 10. backend.graph __init__ exports ───────────────────────
def t10():
    from backend.graph import (
        TroubleshootingGraphBuilder,
        resolve_troubleshooting_context,
        find_related_errors,
        TS_SCHEMA_VERSION,
    )

check("backend.graph: __init__ exports", t10)


# ── 11. backend.vector __init__ exports ──────────────────────
def t11():
    from backend.vector import (
        NonLegalTripleStore,
        chunk_by_error_boundaries,
        chunk_by_sentences,
        chunk_by_structure,
    )

check("backend.vector: __init__ exports", t11)


# ── 12. backend.retrieval __init__ exports ───────────────────
def t12():
    from backend.retrieval import (
        CRAGProcessor, CRAGConfig, CRAGResult, ClaimVerdict,
    )

check("backend.retrieval: __init__ exports", t12)


# ── 13. Cross-encoder ────────────────────────────────────────
def t13():
    from backend.retrieval.cross_encoder import rerank, score_pairs
    assert callable(rerank)

check("Cross-encoder: rerank + score_pairs", t13)


# ── 14. HyDE ─────────────────────────────────────────────────
def t14():
    from backend.retrieval.hyde import HyDEProcessor, HyDEConfig

check("HyDE: import", t14)


# ── 15. Enhanced graph builder LLM enrichment ────────────────
def t15():
    import inspect
    from backend.graph.enhanced_graph_builder import EnhancedGraphBuilder
    src = inspect.getsource(EnhancedGraphBuilder._llm_enrich_sections)
    assert "_LEGAL_LLM_EXTRACTION_PROMPT" in src, "Prompt not referenced"

check("EnhancedGraphBuilder: _llm_enrich_sections", t15)


# ── 16. TroubleshootingGraphBuilder functional ────────────────
def t16():
    import tempfile
    import os
    from backend.graph.troubleshooting_builder import TroubleshootingGraphBuilder
    from backend.graph.persistence import GraphStore

    with tempfile.TemporaryDirectory() as tmpdir:
        gpath = os.path.join(tmpdir, "ts_graph.json")
        store = GraphStore(gpath)
        builder = TroubleshootingGraphBuilder(store)

        sections = [
            {
                "section_number": 1,
                "section_heading": "Authentication Errors",
                "section_text": (
                    "Error ERR-AUTH-407: SSO redirect fails behind proxy.\n"
                    "Symptom: Users see a blank page after login attempt.\n"
                    "Root cause: Proxy strips Authorization headers.\n"
                    "Solution: Configure proxy to pass X-Forwarded-* headers.\n"
                    "Workaround: Use direct VPN connection."
                ),
            },
            {
                "section_number": 2,
                "section_heading": "Memory Errors",
                "section_text": (
                    "Error ERR-RUN-204: Out of memory during batch processing.\n"
                    "Symptom: Process crashes with exit code 137.\n"
                    "Root cause: Container memory limit set to 512MB.\n"
                    "Solution: Increase container memory to 4GB.\n"
                    "Affects component: BatchProcessor."
                ),
            },
        ]

        result = builder.build_troubleshooting_graph("test_doc", "/test/guide.md", sections)
        graph = store.load()

    # Verify structure
    assert graph.number_of_nodes() >= 6, f"Only {graph.number_of_nodes()} nodes"
    assert graph.number_of_edges() >= 4, f"Only {graph.number_of_edges()} edges"

    # Verify node types exist
    node_types = {d.get("type") for _, d in graph.nodes(data=True)}
    assert "ERROR_CODE" in node_types, f"No ERROR_CODE nodes. Types: {node_types}"
    assert "SOLUTION" in node_types or "SECTION" in node_types

    print(f"    Graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    print(f"    Node types: {sorted(node_types)}")

check("TroubleshootingGraphBuilder: functional build", t16)


# ── 17. Troubleshooting traversal functional ──────────────────
def t17():
    import tempfile
    import os
    from backend.graph.troubleshooting_builder import TroubleshootingGraphBuilder
    from backend.graph.troubleshooting_traversal import (
        resolve_troubleshooting_context,
        find_related_errors,
    )
    from backend.graph.persistence import GraphStore

    # Build a graph first
    with tempfile.TemporaryDirectory() as tmpdir:
        gpath = os.path.join(tmpdir, "ts_graph.json")
        store = GraphStore(gpath)
        builder = TroubleshootingGraphBuilder(store)
        sections = [
            {
                "section_number": 1,
                "section_heading": "Auth Errors",
                "section_text": (
                    "Error ERR-AUTH-407: SSO fails.\n"
                    "Symptom: Blank page.\n"
                    "Root cause: Proxy strips headers.\n"
                    "Solution: Configure proxy."
                ),
            },
        ]
        result = builder.build_troubleshooting_graph("doc1", "/doc.md", sections)
        graph = store.load()

    # Resolve context for the error
    ctx = resolve_troubleshooting_context(graph, "ERR-AUTH-407")
    print(f"    Context type: {type(ctx).__name__}, has content: {bool(ctx)}")
    assert ctx is not None, "No context returned"

    # Find related
    related = find_related_errors(graph, "ERR-AUTH-407")
    print(f"    Related errors: {related}")

check("Troubleshooting traversal: resolve + find_related", t17)


# ── 18. CRAG heuristic fallback pipeline end-to-end ──────────
def t18():
    from backend.retrieval.crag import CRAGProcessor, CRAGConfig

    config = CRAGConfig()
    proc = CRAGProcessor(config)

    answer = (
        "The error ERR-AUTH-407 is caused by proxy stripping headers. "
        "The solution is to configure the proxy to pass X-Forwarded headers."
    )
    chunks = [
        {
            "content": "ERR-AUTH-407: SSO redirect fails behind proxy. "
                       "Root cause: Proxy strips Authorization headers.",
            "source_path": "/guide.md",
        },
        {
            "content": "Configure proxy to pass X-Forwarded-For and "
                       "X-Forwarded-Proto headers to resolve auth issues.",
            "source_path": "/guide.md",
        },
    ]

    # retrieve_fn must be callable: (query, top_k) -> List[dict]
    def retrieve_fn(query, top_k=3):
        return chunks[:top_k]

    result = proc.run_sync(answer, retrieve_fn, source_chunks=chunks)
    print(f"    CRAG result type: {type(result).__name__}")
    print(f"    Claims found: {len(result.claims)}")
    print(f"    Contradicted: {result.contradicted_count}")
    assert result is not None
    assert hasattr(result, "claims")
    assert hasattr(result, "corrected_answer")

check("CRAG: full heuristic pipeline (no LLM)", t18)


# ── 19. NonLegalTripleStore functional (temp dir) ─────────────
def t19():
    import tempfile
    import os
    import shutil
    from backend.vector.nonlegal_triple_store import NonLegalTripleStore

    tmpdir = tempfile.mkdtemp()
    try:
        store = NonLegalTripleStore(persist_dir=tmpdir)
        doc_text = (
            "## ERR-AUTH-407\n"
            "Problem: SSO redirect fails behind proxy.\n"
            "Root Cause: Proxy strips auth headers.\n"
            "Solution: Configure proxy to pass X-Forwarded headers.\n"
            "---\n"
            "## ERR-RUN-204\n"
            "Problem: OOM during batch processing.\n"
            "Root Cause: Memory limit too low.\n"
            "Solution: Increase container memory to 4GB."
        )
        store.add_document("test_doc", "/guide.md", doc_text)

        # Search
        results = store.search("proxy authentication error", top_k=3)
        print(f"    Search returned {len(results)} results")
        assert len(results) >= 1, f"Expected >=1 results, got {len(results)}"
    finally:
        # ChromaDB locks files on Windows — ignore cleanup errors
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

check("NonLegalTripleStore: add_document + search", t19)


# ── 20. Golden queries JSON schema ───────────────────────────
def t20():
    import json
    import os
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "golden_queries_nonlegal.json",
    )
    assert os.path.exists(path), f"File not found: {path}"
    with open(path) as f:
        data = json.load(f)
    queries = data.get("queries", data) if isinstance(data, dict) else data
    assert isinstance(queries, list), "Expected queries list"
    assert len(queries) == 25, f"Expected 25 queries, got {len(queries)}"
    ids = [q["query_id"] for q in queries]
    assert len(set(ids)) == 25, "Duplicate IDs"
    tune = [q for q in queries if q["split"] == "tune"]
    hold = [q for q in queries if q["split"] == "holdout"]
    assert len(tune) == 20, f"Expected 20 tune, got {len(tune)}"
    assert len(hold) == 5, f"Expected 5 holdout, got {len(hold)}"

check("Golden queries: 25 queries, 20/5 split", t20)


# ── Summary ──────────────────────────────────────────────────
print()
print("=" * 60)
print("CONFIG FLAGS:")
for k, v in results.items():
    status = "ON" if v else "** OFF **"
    print(f"  {k}: {status}")
print()
print(f"RESULTS: {pass_count} PASS / {fail_count} FAIL out of 20 checks")
print("=" * 60)

if fail_count > 0:
    sys.exit(1)
