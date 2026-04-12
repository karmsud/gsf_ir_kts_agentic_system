"""
ABS retrieval profile — tuned for legal PSA/Indenture documents.

These values override KTS defaults when the scope is ABS.
Legal documents have different characteristics than KTS's standard corpus:
- Longer, more verbose sections
- Precise legal terminology (higher BM25 value)
- Dense cross-references (deeper graph expansion)
- High accuracy requirements (stricter CRAG threshold)
"""

ABS_RETRIEVAL_PROFILE = {
    # ── Chunking ──
    "chunk_max_chars": 4000,          # KTS: 3000 (legal sections run long)
    "chunk_overlap": 800,             # KTS: 500  (cross-clause refs)

    # ── Hybrid Search ──
    "bm25_weight": 0.5,              # KTS: 0.4  (legal terms are precise)
    "vector_weight": 0.5,            # KTS: 0.6  (balance with BM25)
    "rrf_k": 60,                     # Same as KTS default

    # ── Graph Expansion ──
    "graph_bfs_depth": 5,            # KTS: 4    (legal cross-refs run deep)
    "graph_pagerank_weight": 0.25,   # KTS: 0.2  (importance matters more)

    # ── Reranking ──
    "rerank_content_weight": 0.50,   # KTS: 0.6
    "rerank_pagerank_weight": 0.25,  # KTS: 0.2
    "rerank_graph_weight": 0.25,     # KTS: 0.2

    # ── CRAG ──
    "crag_confidence_threshold": 0.85,  # KTS: 0.80 (financial precision)

    # ── Critique ──
    "critique_max_rounds": 3,        # KTS: 5    (faster iteration)
    "critique_target_confidence": 0.92,  # KTS: 0.90

    # ── Multi-Query ──
    "multi_query_count": 6,          # KTS: 8    (legal queries are focused)

    # ── HyDE ──
    "hyde_doc_count": 2,             # KTS: 3    (fewer hypothetical docs)
}


def apply_profile_to_config(config, profile: dict = None) -> None:
    """Apply ABS retrieval profile to a KTSConfig instance.

    Only overrides properties that are at their default values,
    preserving any explicit user overrides.
    """
    if profile is None:
        profile = ABS_RETRIEVAL_PROFILE

    defaults = {
        "abs_retrieval_bm25_weight": ("bm25_weight", 0.5),
        "abs_retrieval_vector_weight": ("vector_weight", 0.5),
        "abs_chunk_max_chars": ("chunk_max_chars", 4000),
        "abs_chunk_overlap": ("chunk_overlap", 800),
        "abs_graph_bfs_depth": ("graph_bfs_depth", 5),
        "abs_graph_pagerank_weight": ("graph_pagerank_weight", 0.25),
        "abs_crag_threshold": ("crag_confidence_threshold", 0.85),
        "abs_critique_max_rounds": ("critique_max_rounds", 3),
        "abs_critique_target": ("critique_target_confidence", 0.92),
        "abs_multi_query_count": ("multi_query_count", 6),
    }

    for config_attr, (profile_key, default_val) in defaults.items():
        if hasattr(config, config_attr):
            current = getattr(config, config_attr)
            if current == default_val:
                setattr(config, config_attr, profile.get(profile_key, default_val))
