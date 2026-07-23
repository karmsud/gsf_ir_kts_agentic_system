from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


def get_bundle_root() -> Path:
    """Return the root directory for bundled data files.

    When running inside a PyInstaller frozen exe this is ``sys._MEIPASS``
    (the distribution directory for --onedir builds).  Otherwise it is the
    repository root inferred from this file's location (config/ is one
    level below the repo root).
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def _env_bool(key: str, default: bool) -> bool:
    """Read a boolean from an environment variable (``true/1/yes`` → True)."""
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in {"true", "1", "yes"}


def _env_float(key: str, default: float) -> float:
    val = os.environ.get(key)
    if val is None:
        return default
    return float(val)


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    if val is None:
        return default
    return int(val)


@dataclass
class KTSConfig:
    source_paths: list[str] = field(default_factory=list)
    supported_extensions: list[str] = field(
        default_factory=lambda: [
            ".doc",
            ".docx",
            ".pdf",
            ".pptx",
            ".htm",
            ".html",
            ".md",
            ".txt",
            ".json",
            ".png",
            ".yaml",
            ".yml",
            ".ini",
            ".csv",
            # Phase 19 — OneNote
            ".one",       # OneNote Section file
            ".onetoc2",   # OneNote Table of Contents
        ]
    )
    knowledge_base_path: str = ".kts"
    chroma_persist_dir: str = ".kts/vectors/chroma"
    graph_path: str = ".kts/graph/knowledge_graph.json"
    manifest_path: str = ".kts/manifest.json"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    confidence_high: float = 0.90
    confidence_medium: float = 0.66
    stale_threshold_days: int = 180

    # ── Phase 4 master toggle (TD §18.1 rollback) ──────────────────
    phase4_enabled: bool = True

    # ── Evidence & Provenance (Epic 5 — TD §7, §11) ───────────────
    strict_provenance_mode: bool = False
    min_provenance_coverage: float = 0.95
    evidence_casefolding: bool = True
    evidence_numeric_tolerance: float = 0.01
    evidence_code_normalization: bool = True

    # ── Regime Classifier (Epic 1 — TD §2) ────────────────────────
    regime_classifier_enabled: bool = True
    corpus_regime_override: str = ""            # force GOVERNING_DOC_LEGAL / GENERIC_GUIDE

    # ── Defined-Term Extraction (Epic 1 — TD §5) ──────────────────
    defined_term_extraction_enabled: bool = True

    # ── NER / Keyphrase (Epic 2 — TD §3.2, §3.3) ─────────────────
    ner_enabled: bool = False                   # auto-enabled when KTS_SPACY_MODEL_PATH set
    spacy_model_path: str = ""                  # set by core extension from addon registry

    # ── Chunk sizing for legal/governing documents ───────────────
    legal_chunk_size: int = 3000                # Fallback char-based chunk size for legal docs
    legal_chunk_overlap: int = 500              # Fallback overlap for legal docs
    legal_min_chunk_size: int = 500             # Min section size for semantic chunking
    legal_max_chunk_size: int = 8000            # Max section size for semantic chunking

    # ── Retrieval Pipeline (Epic 3 — TD §6) ───────────────────────
    max_chunks_per_doc: int = 25                # stratified budget per retrieval pass
    deep_max_chunks_per_doc: int = 40           # /deep mode keeps more chunks per document
    query_expansion_enabled: bool = True        # Multi-query retrieval with LLM expansion
    query_expansion_count: int = 5              # Number of query variations to generate
    acronym_resolver_enabled: bool = True
    learned_synonyms_enabled: bool = True       # use auto-learned synonyms at retrieval
    term_resolution_enabled: bool = True
    
    # ── Context Expansion (Smart Retrieval) ───────────────────────
    context_expansion_enabled: bool = True      # Expand context window around hit chunks
    context_window_size: int = 3                # Chunks to retrieve before/after hit (±N)
    adaptive_expansion_enabled: bool = True     # Adjust window based on confidence
    continuation_detection_enabled: bool = True # Detect mid-sentence/list continuations
    metadata_guided_expansion: bool = True      # Use section headers to guide expansion
    cross_encoder_enabled: bool = True          # enabled by default — bundled ONNX model
    cross_encoder_model_path: str = ""          # auto-resolved from bundle or env var
    pagerank_enabled: bool = True               # PageRank runs as 20% of hybrid reranker
    # NOTE: duplicate context_expansion_enabled removed (was here as False, conflicting with True above)
    multi_hop_enabled: bool = True
    section_aware_chunking_enabled: bool = True # LegalChunker — semantic section-aware chunking

    # ── Phase 6: Hierarchical GraphRAG (Unified) ──────────────────
    # Phase 6 is now ALWAYS enabled — the system is designed around it
    phase6_enabled: bool = True
    phase6_chroma_dir: str = ".kts/vectors/phase6"
    phase6_max_iterations: int = 10
    phase6_min_confidence: float = 0.85
    phase6_min_improvement: float = 0.05
    phase6_content_weight: float = 0.6
    phase6_pagerank_weight: float = 0.2
    phase6_graph_proximity_weight: float = 0.2
    phase6_pagerank_alpha: float = 0.85
    phase6_bfs_depth: int = 4
    phase6_verbose_logging: bool = True
    phase6_result_threshold: float = 0.70  # Only return results >= this confidence

    # ── Phase 7: Definition Resolution Engine ────────────────────
    resolution_engine_enabled: bool = True      # Master toggle for definition resolution
    resolution_max_depth: int = 10              # Max DFS depth for resolution trees
    resolution_tree_format_depth: int = 4       # Default depth for LLM-formatted trees
    resolution_precompute_on_ingest: bool = False # Deprecated: trees computed at query time
    definition_tree_token_budget: int = 50_000    # Token budget for layered definition trees
    resolution_cycle_strategy: str = "break"    # "break" (stop + annotate) or "error" (raise)

    # ── Graph Scoring (TD §6.5) ───────────────────────────────────
    graph_boost_cap: float = 0.7
    graph_boost_timeout_ms: int = 20

    # ── Debug (TD §9.3) ──────────────────────────────────────────
    debug_level: int = 0                        # 0=off, 1=summary, 2=verbose

    # ── Phase 5: Embedding Provider (WS-1) ────────────────────────
    # Embedding model selection: 'bge_onnx_int8' (default), 'legacy_chroma_default' (deprecated)
    # - bge_onnx_int8: BAAI/bge-base-en-v1.5 ONNX INT8 (768-dim) [REQUIRED]
    # - legacy_chroma_default: MiniLM-L6-V2 via ChromaDB (384-dim) [deprecated, dev only]
    embed_provider: str = "bge_onnx_int8"
    embed_model_path: str = ""                  # path to BGE model dir (overrides default)
    # ── Phase 10: Conversation Memory & Context ───────────────────
    session_memory_enabled: bool = True         # In-process session memory
    query_rewriting_enabled: bool = True        # Coreference resolution in follow-ups
    history_summarization_enabled: bool = True  # Compress long histories
    history_max_turns: int = 20                 # Max conversation turns in context
    session_memory_ttl_hours: float = 4.0       # Session TTL before eviction (hours)

    # ── Phase 11: VS Code Deep Integration ────────────────────────
    follow_up_suggestions_enabled: bool = True  # Auto-suggest follow-up questions
    sse_progress_enabled: bool = True           # SSE streaming progress events
    hitl_classification_enabled: bool = True    # Human-in-the-loop doc classification
    definition_mode_enabled: bool = True        # /define slash command support
    audit_mode_enabled: bool = True             # /audit slash command support

    # ── Phase 12: Named Scoped Knowledge Spaces ───────────────────
    knowledge_source_root: str = ""             # Root directory for scope discovery
    per_folder_kts_enabled: bool = True         # Per-folder .kts directories
    deal_catalog_enabled: bool = True           # SQLite deal catalog for routing
    deal_catalog_path: str = ""                 # Path to deal_catalog.db (default: .kts/deal_catalog.db)
    scope_discovery_on_startup: bool = True     # Auto-discover scopes on activation

    # ── Phase 13: Retrieval Quality (13.1-13.5) ──────────────────
    confidence_scoring_enabled: bool = True     # 13.1 — Confidence tier display
    gap_detection_enabled: bool = True          # 13.2 — Post-retrieval gap alerts
    parent_child_chunking_enabled: bool = False # 13.3 — Retrieve child, expand to parent
    hyde_enabled: bool = True                   # 13.4 — Hypothetical Document Embeddings (enabled Phase 19)
    regime_aware_retrieval: bool = True         # 13.5 — Route by corpus regime
    guide_items_top_k: int = 60                 # 13.5 — GuideRetriever items top-k
    guide_sections_top_k: int = 20              # 13.5 — GuideRetriever sections top-k
    guide_graph_expansion: bool = True          # 13.5 — BFS expansion from seed hits
    guide_bfs_depth: int = 4                    # 13.5 — BFS depth for guide expansion
    guide_error_code_boost: float = 0.35        # 13.5 — Additive boost for error-code matches
    guide_step_ordering: bool = True            # 13.5 — Step-sequence ordering

    # ── Phase 14: Deal Intelligence ───────────────────────────────
    deal_summary_cache_enabled: bool = True     # 14.1 — Session deal summary cache
    temporal_reasoning_enabled: bool = True     # 14.2 — current_date injection
    extraction_mode_enabled: bool = True        # 14.3 — /extract structured output
    summary_mode_enabled: bool = True           # 14.4 — /summary 5-section output

    # ── Phase 15: Cross-Deal Intelligence ─────────────────────────
    comparison_mode_enabled: bool = True        # 15.1 — /compare cross-deal
    contradiction_detection_enabled: bool = True # 15.2 — Two-deal contradiction
    baseline_corpus_enabled: bool = False       # 15.3 — Market baseline (requires setup)
    anomaly_detection_enabled: bool = True      # 15.4 — Anomaly scoring (active for /audit)

    # ── Phase 17: Document-Level Isolation & Multi-Deal Analytics ─
    phase17_doc_filter_enabled: bool = True       # Step 1: doc_name_prefix filtering
    phase17_dual_graph_enabled: bool = True       # Steps 2–3: doc-specific graphs
    phase17_rich_catalog_enabled: bool = True     # Step 4: enhanced catalog schema
    phase17_scope_resolver_enabled: bool = True   # Step 5: unified scope parsing
    phase17_graph_routing_enabled: bool = True    # Step 6: doc vs deal graph selection
    phase17_multi_deal_enabled: bool = True       # Step 7: parallel multi-scope
    phase17_diff_mode_enabled: bool = True        # Step 8: /diff mode
    phase17_aggregate_mode_enabled: bool = True   # Step 8: /aggregate mode
    phase17_max_parallel_scopes: int = 5          # Step 7: concurrency limit
    phase17_wildcard_max_matches: int = 20        # Step 5: max wildcard expand
    phase17_multi_scope_timeout_ms: int = 30000   # Step 7: per-scope timeout
    phase17_diff_similarity_threshold: float = 0.85  # Step 8: diff threshold
    phase17_aggregate_outlier_threshold: float = 0.70  # Step 8: outlier threshold

    # ── Phase 8: RAG Upgrade (9 Increments) ──────────────────────
    # Inc 0 — Contextual Chunk Headers
    enable_cch: bool = True                      # 8.0 — Prepend [DOC:|TYPE:|SECTION:] to embeddings
    cch_max_section_len: int = 80                # 8.0 — Truncate long section titles in header

    # Inc 1 — BM25 Hybrid Search
    enable_bm25_hybrid: bool = True              # 8.1 — BM25 keyword + vector hybrid
    bm25_weight: float = 0.4                     # 8.1 — BM25 lane weight in RRF
    vector_weight: float = 0.6                   # 8.1 — Vector lane weight in RRF
    rrf_constant: int = 60                       # 8.1 — RRF constant k
    bm25_k1: float = 1.5                         # 8.1 — BM25 term saturation
    bm25_b: float = 0.75                         # 8.1 — BM25 length normalization

    # Inc 2 — MMR Diversity Sampling
    enable_mmr: bool = True                      # 8.2 — Maximal Marginal Relevance
    mmr_lambda: float = 0.7                      # 8.2 — Relevance vs. diversity trade-off
    mmr_fetch_multiplier: int = 5                # 8.2 — Fetch N× before MMR selection

    # Inc 3 — Token-Aware Context Trimming (JS-only, always on)

    # Inc 4 — Parent-Child Document Linking
    enable_parent_expansion: bool = True         # 8.4 — Expand matched items to parent sections
    max_parent_sections: int = 20                # 8.4 — Cap on expanded parent sections

    # Inc 5 — Targeted HyPE (Hypothetical Prompt Embeddings)
    enable_hype: bool = False                    # 8.5 — HyPE question enrichment (requires LLM)

    # Inc 6 — Multi-Query RAG Fusion
    multi_query_rag_enabled: bool = True         # 8.6 — Multi-query fusion pipeline
    multi_query_variants: int = 8                # 8.6 — Number of LLM query variants
    multi_query_pool_size: int = 60              # 8.6 — Candidate pool per query variant

    # Inc 7 — N-Level Definition Chain Traversal
    definition_traversal_enabled: bool = True    # 8.7 — TermResolver deep traversal
    definition_traversal_depth: int = 8          # 8.7 — Max BFS depth

    # Inc 8 — Self-RAG Iterative Generation Loop (JS-side)
    self_rag_enabled: bool = False               # 8.8 — Self-RAG loop (requires LLM)
    self_rag_max_rounds: int = 5                 # 8.8 — Max retrieval rounds
    self_rag_model: str = "gpt-4.1"             # 8.8 — Model for gap analysis

    # ── Phase 9: Directed Critique RAG ────────────────────────────
    critique_generation_enabled: bool = True     # 9.1 — Generate critique Qs at ingest
    critique_generator_model: str = "gpt-4.1"   # 9.1 — Model for ingest-time generation
    critique_loop_enabled: bool = True           # 9.2 — Directed critique at query time
    critique_model: str = "gpt-4.1"             # 9.2 — Fixed model for critique evaluation
    critique_max_rounds: int = 5                 # 9.2 — Max critique-fix-restart cycles
    critique_restart_on_gap: bool = True         # 9.2 — Restart from Q1 after each fix
    critique_multi_doc_enabled: bool = True      # 9.3 — Use Qs from all retrieved docs
    critique_confidence_exit: float = 0.90       # 9.3 — Early exit threshold for tail Qs
    critique_max_questions_per_doc: int = 25     # 9.1 — Cap on questions per document

    # ── Phase 19: Corrective RAG (CRAG) ──────────────────────────
    crag_enabled: bool = True                    # 19.1 — Corrective RAG pipeline
    crag_max_claims: int = 20                    # 19.1 — Max claims per answer
    crag_evidence_top_k: int = 5                 # 19.1 — Evidence chunks per claim
    crag_drop_contradicted: bool = True          # 19.1 — Remove contradicted claims
    crag_flag_no_evidence: bool = True           # 19.1 — Mark unverified claims

    # ── Phase 19.2: Non-Legal Triple Vector Store ─────────────────
    nonlegal_triple_store_enabled: bool = True   # 19.2 — 3 stores for non-legal docs
    nonlegal_error_boundary_chunking: bool = True  # 19.2 — Store 1: error-boundary chunks
    nonlegal_sentence_level_chunking: bool = True  # 19.2 — Store 2: sentence-level chunks
    nonlegal_structure_aware_chunking: bool = True  # 19.2 — Store 3: structure-aware chunks
    nonlegal_sentence_chunk_size: int = 200      # 19.2 — Target sentence chunk chars
    nonlegal_sentence_overlap: int = 50          # 19.2 — Sentence chunk overlap
    nonlegal_structure_chunk_size: int = 1500    # 19.2 — Structure-aware chunk target

    # ── Phase 19.3: Troubleshooting Graph ─────────────────────────
    troubleshooting_graph_enabled: bool = True   # 19.3 — Dedicated troubleshooting graph
    troubleshooting_graph_path: str = ""         # 19.3 — Path (default: .kts/graph/troubleshooting_graph.json)

    # ── Phase 21: ABS Domain Integration ──────────────────────────
    abs_enabled: bool = False                         # 21 — Master toggle for ABS subsystem
    abs_deals_root: str = "deals"                     # 21 — Root directory for ABS deals
    abs_extraction_mode: str = "hybrid"               # 21 — "template" | "llm" | "hybrid"
    abs_min_quality_score: float = 8.0                # 21 — Min quality gate score
    abs_max_retries: int = 3                          # 21 — Max quality gate retries
    abs_confidence_high: float = 0.90                 # 21 — High confidence threshold
    abs_confidence_low: float = 0.66                  # 21 — Low confidence threshold
    abs_vectorstore_enabled: bool = True              # 21 — Vector store toggle
    abs_graph_enabled: bool = True                    # 21 — Knowledge graph toggle
    abs_embedding_dim: int = 768                      # 21 — Embedding dimension
    abs_chunk_max_chars: int = 3000                   # 21 — Max chunk chars
    abs_chunk_overlap: int = 500                      # 21 — Chunk overlap chars
    abs_normalize_embeddings: bool = True             # 21 — Normalize embedding vectors
    abs_definition_resolution_enabled: bool = True    # 21 — Definition resolution toggle
    abs_definition_resolution_depth: int = 5          # 21 — Max resolution depth
    abs_definition_resolution_confidence: float = 0.80  # 21 — Min definition confidence
    abs_output_tolerance: float = 0.01                # 21 — Output comparison tolerance
    abs_min_definitions: int = 10                     # 21 — Min definitions required
    abs_min_waterfall_rules: int = 5                  # 21 — Min waterfall rules required
    abs_min_vectors: int = 50                         # 21 — Min vectors required

    # ── Phase 22: Infrastructure Integration ──────────────────────────

    # LLM Configuration
    abs_llm_mode: str = "vscode"                     # 22 — "vscode" | "mock" | "none"
    abs_llm_model: str = "gpt-4.1"                   # 22 — Model for background tasks
    abs_llm_temperature: float = 0.0                  # 22 — Default temperature
    abs_llm_max_tokens: int = 4096                   # 22 — Default max tokens
    abs_llm_timeout_seconds: int = 60                 # 22 — Timeout per LLM call
    abs_llm_max_retries: int = 2                      # 22 — Retry count on failure

    # Infrastructure Feature Flags
    abs_use_dual_store: bool = True                   # 22 — Use dual vector store
    abs_use_enhanced_graph: bool = True               # 22 — Use enhanced graph builder
    abs_use_full_retrieval: bool = True               # 22 — Use full retrieval pipeline

    # Retrieval Tuning
    abs_retrieval_max_results: int = 10               # 22 — Max search results
    abs_retrieval_bm25_weight: float = 0.5            # 22 — BM25 weight (legal precision)
    abs_retrieval_vector_weight: float = 0.5          # 22 — Vector weight

    # Graph Tuning
    abs_graph_bfs_depth: int = 5                      # 22 — BFS expansion depth
    abs_graph_pagerank_enabled: bool = True           # 22 — PageRank scoring
    abs_graph_pagerank_weight: float = 0.25           # 22 — PageRank boost weight

    # Advanced Retrieval Features (require LLM)
    abs_crag_enabled: bool = True                     # 22 — CRAG verification
    abs_crag_threshold: float = 0.85                  # 22 — Confidence threshold
    abs_critique_enabled: bool = True                 # 22 — Critique loop
    abs_critique_max_rounds: int = 3                  # 22 — Max refinement rounds
    abs_critique_target: float = 0.92                 # 22 — Target confidence
    abs_multi_query_enabled: bool = True              # 22 — Multi-query expansion
    abs_multi_query_count: int = 6                    # 22 — Query variant count
    abs_hyde_enabled: bool = True                     # 22 — HyDE generation

    # ── Hybrid Retrieval Engine (Graph + Vector + BM25) ───────────────
    # Three-signal RRF fusion exclusively for financial & legal documents.
    hybrid_engine_enabled: bool = True            # Master toggle for new unified engine
    hybrid_vector_weight: float = 1.0             # RRF weight for dense vector signal
    hybrid_bm25_weight: float = 1.0               # RRF weight for BM25 sparse signal
    hybrid_graph_weight: float = 0.6              # RRF weight for graph-expansion signal
    hybrid_rrf_k: int = 60                        # RRF constant k (default 60)
    hybrid_graph_bfs_depth: int = 2               # BFS depth for graph entity expansion

    # ── Financial & Legal Domain Restriction ──────────────────────────
    # When True, off-domain documents are penalised at retrieval time.
    # The system is designed exclusively for financial and legal documents.
    financial_legal_domain_only: bool = True      # Enable domain-specific scoring
    domain_off_penalty: float = 0.4               # Score multiplier for off-domain docs
    domain_section_boost_enabled: bool = True     # Boost waterfall/definition sections

def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_config(root_dir: str | Path | None = None) -> KTSConfig:
    root = Path(root_dir or Path.cwd())
    # Config data files ship inside the bundle; resolve them from there
    bundle = get_bundle_root()
    paths_data = _read_json(bundle / "config" / "file_share_paths.json")
    
    # Allow override for testing isolation
    kb_path = os.environ.get("KTS_KB_PATH", ".kts")
    
    cfg = KTSConfig(
        source_paths=paths_data.get("paths", []),
        knowledge_base_path=kb_path,
        chroma_persist_dir=f"{kb_path}/vectors/chroma",
        graph_path=f"{kb_path}/graph/knowledge_graph.json",
        manifest_path=f"{kb_path}/manifest.json",
        phase6_chroma_dir=f"{kb_path}/vectors/phase6",
        deal_catalog_path=f"{kb_path}/deal_catalog.db",
        troubleshooting_graph_path=f"{kb_path}/graph/troubleshooting_graph.json",
    )

    # ── KTS_ env-var overrides (TD §10.2) ─────────────────────────
    cfg.phase4_enabled = _env_bool("KTS_PHASE4_ENABLED", cfg.phase4_enabled)
    cfg.strict_provenance_mode = _env_bool("KTS_STRICT_PROVENANCE_MODE", cfg.strict_provenance_mode)
    cfg.min_provenance_coverage = _env_float("KTS_MIN_PROVENANCE_COVERAGE", cfg.min_provenance_coverage)
    cfg.regime_classifier_enabled = _env_bool("KTS_REGIME_CLASSIFIER_ENABLED", cfg.regime_classifier_enabled)
    cfg.defined_term_extraction_enabled = _env_bool("KTS_DEFINED_TERM_EXTRACTION_ENABLED", cfg.defined_term_extraction_enabled)
    # NER: auto-enable if model path is provided OR if running as bundled exe
    cfg.spacy_model_path = os.environ.get("KTS_SPACY_MODEL_PATH", cfg.spacy_model_path)
    ner_bundled = getattr(sys, 'frozen', False)  # spaCy model is bundled in PyInstaller build
    # Also auto-detect if the spaCy package + model is installed in the venv
    # (covers workspace / dev mode where model is pip-installed).
    ner_package_available = False
    if not cfg.spacy_model_path and not ner_bundled:
        try:
            import spacy as _spacy_check  # noqa: E402
            _spacy_check.load("en_core_web_sm")
            ner_package_available = True
        except Exception:
            pass
    cfg.ner_enabled = _env_bool(
        "KTS_NER_ENABLED",
        bool(cfg.spacy_model_path) or ner_bundled or ner_package_available,
    )
    cfg.acronym_resolver_enabled = _env_bool("KTS_ACRONYM_RESOLVER_ENABLED", cfg.acronym_resolver_enabled)
    cfg.max_chunks_per_doc = _env_int("KTS_MAX_CHUNKS_PER_DOC", cfg.max_chunks_per_doc)
    cfg.deep_max_chunks_per_doc = _env_int("KTS_DEEP_MAX_CHUNKS_PER_DOC", cfg.deep_max_chunks_per_doc)
    cfg.legal_chunk_size = _env_int("KTS_LEGAL_CHUNK_SIZE", cfg.legal_chunk_size)
    cfg.legal_chunk_overlap = _env_int("KTS_LEGAL_CHUNK_OVERLAP", cfg.legal_chunk_overlap)
    cfg.legal_min_chunk_size = _env_int("KTS_LEGAL_MIN_CHUNK_SIZE", cfg.legal_min_chunk_size)
    cfg.legal_max_chunk_size = _env_int("KTS_LEGAL_MAX_CHUNK_SIZE", cfg.legal_max_chunk_size)
    cfg.query_expansion_enabled = _env_bool("KTS_QUERY_EXPANSION_ENABLED", cfg.query_expansion_enabled)
    cfg.query_expansion_count = _env_int("KTS_QUERY_EXPANSION_COUNT", cfg.query_expansion_count)
    cfg.learned_synonyms_enabled = _env_bool("KTS_LEARNED_SYNONYMS_ENABLED", cfg.learned_synonyms_enabled)
    cfg.term_resolution_enabled = _env_bool("KTS_TERM_RESOLUTION_ENABLED", cfg.term_resolution_enabled)
    # Cross-encoder: enabled by default, auto-detect bundled model.
    # User can disable via KTS_CROSS_ENCODER_ENABLED=0 if needed.
    cfg.cross_encoder_model_path = os.environ.get("KTS_CROSSENCODER_MODEL_PATH", cfg.cross_encoder_model_path)
    cfg.cross_encoder_enabled = _env_bool("KTS_CROSS_ENCODER_ENABLED", True)
    cfg.pagerank_enabled = _env_bool("KTS_PAGERANK_ENABLED", cfg.pagerank_enabled)
    cfg.context_expansion_enabled = _env_bool("KTS_CONTEXT_EXPANSION_ENABLED", cfg.context_expansion_enabled)
    cfg.context_window_size = _env_int("KTS_CONTEXT_WINDOW_SIZE", cfg.context_window_size)
    cfg.adaptive_expansion_enabled = _env_bool("KTS_ADAPTIVE_EXPANSION_ENABLED", cfg.adaptive_expansion_enabled)
    cfg.continuation_detection_enabled = _env_bool("KTS_CONTINUATION_DETECTION_ENABLED", cfg.continuation_detection_enabled)
    cfg.metadata_guided_expansion = _env_bool("KTS_METADATA_GUIDED_EXPANSION", cfg.metadata_guided_expansion)
    cfg.multi_hop_enabled = _env_bool("KTS_MULTI_HOP_ENABLED", cfg.multi_hop_enabled)
    cfg.section_aware_chunking_enabled = _env_bool("KTS_SECTION_AWARE_CHUNKING_ENABLED", cfg.section_aware_chunking_enabled)
    cfg.graph_boost_cap = _env_float("KTS_GRAPH_BOOST_CAP", cfg.graph_boost_cap)
    cfg.graph_boost_timeout_ms = _env_int("KTS_GRAPH_BOOST_TIMEOUT_MS", cfg.graph_boost_timeout_ms)
    cfg.debug_level = _env_int("KTS_DEBUG_LEVEL", cfg.debug_level)

    # ── Phase 6 env-var overrides ─────────────────────────────────
    cfg.phase6_enabled = _env_bool("KTS_PHASE6_ENABLED", cfg.phase6_enabled)
    cfg.phase6_chroma_dir = os.environ.get("KTS_PHASE6_CHROMA_DIR", cfg.phase6_chroma_dir)
    cfg.phase6_max_iterations = _env_int("KTS_PHASE6_MAX_ITERATIONS", cfg.phase6_max_iterations)
    cfg.phase6_min_confidence = _env_float("KTS_PHASE6_MIN_CONFIDENCE", cfg.phase6_min_confidence)
    cfg.phase6_min_improvement = _env_float("KTS_PHASE6_MIN_IMPROVEMENT", cfg.phase6_min_improvement)
    cfg.phase6_content_weight = _env_float("KTS_PHASE6_CONTENT_WEIGHT", cfg.phase6_content_weight)
    cfg.phase6_pagerank_weight = _env_float("KTS_PHASE6_PAGERANK_WEIGHT", cfg.phase6_pagerank_weight)
    cfg.phase6_graph_proximity_weight = _env_float("KTS_PHASE6_GRAPH_PROXIMITY_WEIGHT", cfg.phase6_graph_proximity_weight)
    cfg.phase6_pagerank_alpha = _env_float("KTS_PHASE6_PAGERANK_ALPHA", cfg.phase6_pagerank_alpha)
    cfg.phase6_bfs_depth = _env_int("KTS_PHASE6_BFS_DEPTH", cfg.phase6_bfs_depth)
    cfg.phase6_verbose_logging = _env_bool("KTS_PHASE6_VERBOSE", cfg.phase6_verbose_logging)

    override = os.environ.get("KTS_CORPUS_REGIME_OVERRIDE", "").strip()
    if override:
        cfg.corpus_regime_override = override

    # ── Phase 10-15 env-var overrides ─────────────────────────────
    cfg.session_memory_enabled = _env_bool("KTS_SESSION_MEMORY_ENABLED", cfg.session_memory_enabled)
    cfg.query_rewriting_enabled = _env_bool("KTS_QUERY_REWRITING_ENABLED", cfg.query_rewriting_enabled)
    cfg.history_summarization_enabled = _env_bool("KTS_HISTORY_SUMMARIZATION_ENABLED", cfg.history_summarization_enabled)
    cfg.history_max_turns = int(os.environ.get("KTS_HISTORY_MAX_TURNS", cfg.history_max_turns))
    cfg.session_memory_ttl_hours = float(os.environ.get("KTS_SESSION_MEMORY_TTL_HOURS", cfg.session_memory_ttl_hours))
    cfg.follow_up_suggestions_enabled = _env_bool("KTS_FOLLOW_UP_SUGGESTIONS_ENABLED", cfg.follow_up_suggestions_enabled)
    cfg.sse_progress_enabled = _env_bool("KTS_SSE_PROGRESS_ENABLED", cfg.sse_progress_enabled)
    cfg.hitl_classification_enabled = _env_bool("KTS_HITL_CLASSIFICATION_ENABLED", cfg.hitl_classification_enabled)
    cfg.definition_mode_enabled = _env_bool("KTS_DEFINITION_MODE_ENABLED", cfg.definition_mode_enabled)
    cfg.audit_mode_enabled = _env_bool("KTS_AUDIT_MODE_ENABLED", cfg.audit_mode_enabled)
    cfg.knowledge_source_root = os.environ.get("KTS_KNOWLEDGE_SOURCE_ROOT", cfg.knowledge_source_root)
    cfg.per_folder_kts_enabled = _env_bool("KTS_PER_FOLDER_KTS_ENABLED", cfg.per_folder_kts_enabled)
    cfg.deal_catalog_enabled = _env_bool("KTS_DEAL_CATALOG_ENABLED", cfg.deal_catalog_enabled)
    cfg.scope_discovery_on_startup = _env_bool("KTS_SCOPE_DISCOVERY_ON_STARTUP", cfg.scope_discovery_on_startup)
    cfg.confidence_scoring_enabled = _env_bool("KTS_CONFIDENCE_SCORING_ENABLED", cfg.confidence_scoring_enabled)
    cfg.gap_detection_enabled = _env_bool("KTS_GAP_DETECTION_ENABLED", cfg.gap_detection_enabled)
    cfg.parent_child_chunking_enabled = _env_bool("KTS_PARENT_CHILD_CHUNKING_ENABLED", cfg.parent_child_chunking_enabled)
    cfg.hyde_enabled = _env_bool("KTS_HYDE_ENABLED", cfg.hyde_enabled)
    cfg.regime_aware_retrieval = _env_bool("KTS_REGIME_AWARE_RETRIEVAL", cfg.regime_aware_retrieval)
    cfg.guide_items_top_k = _env_int("KTS_GUIDE_ITEMS_TOP_K", cfg.guide_items_top_k)
    cfg.guide_sections_top_k = _env_int("KTS_GUIDE_SECTIONS_TOP_K", cfg.guide_sections_top_k)
    cfg.guide_graph_expansion = _env_bool("KTS_GUIDE_GRAPH_EXPANSION", cfg.guide_graph_expansion)
    cfg.guide_bfs_depth = _env_int("KTS_GUIDE_BFS_DEPTH", cfg.guide_bfs_depth)
    cfg.guide_error_code_boost = _env_float("KTS_GUIDE_ERROR_CODE_BOOST", cfg.guide_error_code_boost)
    cfg.guide_step_ordering = _env_bool("KTS_GUIDE_STEP_ORDERING", cfg.guide_step_ordering)
    cfg.deal_summary_cache_enabled = _env_bool("KTS_DEAL_SUMMARY_CACHE_ENABLED", cfg.deal_summary_cache_enabled)
    cfg.temporal_reasoning_enabled = _env_bool("KTS_TEMPORAL_REASONING_ENABLED", cfg.temporal_reasoning_enabled)
    cfg.extraction_mode_enabled = _env_bool("KTS_EXTRACTION_MODE_ENABLED", cfg.extraction_mode_enabled)
    cfg.summary_mode_enabled = _env_bool("KTS_SUMMARY_MODE_ENABLED", cfg.summary_mode_enabled)
    cfg.comparison_mode_enabled = _env_bool("KTS_COMPARISON_MODE_ENABLED", cfg.comparison_mode_enabled)
    cfg.contradiction_detection_enabled = _env_bool("KTS_CONTRADICTION_DETECTION_ENABLED", cfg.contradiction_detection_enabled)
    cfg.baseline_corpus_enabled = _env_bool("KTS_BASELINE_CORPUS_ENABLED", cfg.baseline_corpus_enabled)
    cfg.anomaly_detection_enabled = _env_bool("KTS_ANOMALY_DETECTION_ENABLED", cfg.anomaly_detection_enabled)

    # ── Phase 17 env-var overrides ────────────────────────────────
    cfg.phase17_doc_filter_enabled = _env_bool("KTS_PHASE17_DOC_FILTER_ENABLED", cfg.phase17_doc_filter_enabled)
    cfg.phase17_dual_graph_enabled = _env_bool("KTS_PHASE17_DUAL_GRAPH_ENABLED", cfg.phase17_dual_graph_enabled)
    cfg.phase17_rich_catalog_enabled = _env_bool("KTS_PHASE17_RICH_CATALOG_ENABLED", cfg.phase17_rich_catalog_enabled)
    cfg.phase17_scope_resolver_enabled = _env_bool("KTS_PHASE17_SCOPE_RESOLVER_ENABLED", cfg.phase17_scope_resolver_enabled)
    cfg.phase17_graph_routing_enabled = _env_bool("KTS_PHASE17_GRAPH_ROUTING_ENABLED", cfg.phase17_graph_routing_enabled)
    cfg.phase17_multi_deal_enabled = _env_bool("KTS_PHASE17_MULTI_DEAL_ENABLED", cfg.phase17_multi_deal_enabled)
    cfg.phase17_diff_mode_enabled = _env_bool("KTS_PHASE17_DIFF_MODE_ENABLED", cfg.phase17_diff_mode_enabled)
    cfg.phase17_aggregate_mode_enabled = _env_bool("KTS_PHASE17_AGGREGATE_MODE_ENABLED", cfg.phase17_aggregate_mode_enabled)
    cfg.phase17_max_parallel_scopes = _env_int("KTS_PHASE17_MAX_PARALLEL_SCOPES", cfg.phase17_max_parallel_scopes)
    cfg.phase17_wildcard_max_matches = _env_int("KTS_PHASE17_WILDCARD_MAX_MATCHES", cfg.phase17_wildcard_max_matches)
    cfg.phase17_multi_scope_timeout_ms = _env_int("KTS_PHASE17_MULTI_SCOPE_TIMEOUT_MS", cfg.phase17_multi_scope_timeout_ms)

    # ── Phase 9 env-var overrides ─────────────────────────────────
    cfg.critique_generation_enabled = _env_bool("KTS_CRITIQUE_GEN_ENABLED", cfg.critique_generation_enabled)

    # ── Phase 8 env-var overrides ─────────────────────────────────
    cfg.enable_cch = _env_bool("KTS_ENABLE_CCH", cfg.enable_cch)
    cfg.cch_max_section_len = _env_int("KTS_CCH_MAX_SECTION_LEN", cfg.cch_max_section_len)
    cfg.enable_bm25_hybrid = _env_bool("KTS_ENABLE_BM25_HYBRID", cfg.enable_bm25_hybrid)
    cfg.bm25_weight = _env_float("KTS_BM25_WEIGHT", cfg.bm25_weight)
    cfg.vector_weight = _env_float("KTS_VECTOR_WEIGHT", cfg.vector_weight)
    cfg.rrf_constant = _env_int("KTS_RRF_CONSTANT", cfg.rrf_constant)
    cfg.bm25_k1 = _env_float("KTS_BM25_K1", cfg.bm25_k1)
    cfg.bm25_b = _env_float("KTS_BM25_B", cfg.bm25_b)
    cfg.enable_mmr = _env_bool("KTS_ENABLE_MMR", cfg.enable_mmr)
    cfg.mmr_lambda = _env_float("KTS_MMR_LAMBDA", cfg.mmr_lambda)
    cfg.mmr_fetch_multiplier = _env_int("KTS_MMR_FETCH_MULTIPLIER", cfg.mmr_fetch_multiplier)
    cfg.enable_parent_expansion = _env_bool("KTS_ENABLE_PARENT_EXPANSION", cfg.enable_parent_expansion)
    cfg.max_parent_sections = _env_int("KTS_MAX_PARENT_SECTIONS", cfg.max_parent_sections)
    cfg.enable_hype = _env_bool("KTS_ENABLE_HYPE", cfg.enable_hype)
    cfg.multi_query_rag_enabled = _env_bool("KTS_MULTI_QUERY_RAG_ENABLED", cfg.multi_query_rag_enabled)
    cfg.multi_query_variants = _env_int("KTS_MULTI_QUERY_VARIANTS", cfg.multi_query_variants)
    cfg.multi_query_pool_size = _env_int("KTS_MULTI_QUERY_POOL_SIZE", cfg.multi_query_pool_size)
    cfg.definition_traversal_enabled = _env_bool("KTS_DEF_TRAVERSAL_ENABLED", cfg.definition_traversal_enabled)
    cfg.definition_traversal_depth = _env_int("KTS_DEF_TRAVERSAL_DEPTH", cfg.definition_traversal_depth)
    cfg.self_rag_enabled = _env_bool("KTS_SELF_RAG_ENABLED", cfg.self_rag_enabled)
    cfg.self_rag_max_rounds = _env_int("KTS_SELF_RAG_MAX_ROUNDS", cfg.self_rag_max_rounds)
    cfg.self_rag_model = os.environ.get("KTS_SELF_RAG_MODEL", cfg.self_rag_model)
    cfg.critique_generator_model = os.environ.get("KTS_CRITIQUE_GEN_MODEL", cfg.critique_generator_model)
    cfg.critique_loop_enabled = _env_bool("KTS_CRITIQUE_LOOP_ENABLED", cfg.critique_loop_enabled)
    cfg.critique_model = os.environ.get("KTS_CRITIQUE_MODEL", cfg.critique_model)
    cfg.critique_max_rounds = _env_int("KTS_CRITIQUE_MAX_ROUNDS", cfg.critique_max_rounds)
    cfg.critique_restart_on_gap = _env_bool("KTS_CRITIQUE_RESTART", cfg.critique_restart_on_gap)
    cfg.critique_multi_doc_enabled = _env_bool("KTS_CRITIQUE_MULTI_DOC", cfg.critique_multi_doc_enabled)
    cfg.critique_confidence_exit = _env_float("KTS_CRITIQUE_CONFIDENCE_EXIT", cfg.critique_confidence_exit)
    cfg.critique_max_questions_per_doc = _env_int("KTS_CRITIQUE_MAX_Q_PER_DOC", cfg.critique_max_questions_per_doc)

    # ── Phase 19 env-var overrides ────────────────────────────────
    cfg.crag_enabled = _env_bool("KTS_CRAG_ENABLED", cfg.crag_enabled)
    cfg.crag_max_claims = _env_int("KTS_CRAG_MAX_CLAIMS", cfg.crag_max_claims)
    cfg.crag_evidence_top_k = _env_int("KTS_CRAG_EVIDENCE_TOP_K", cfg.crag_evidence_top_k)
    cfg.nonlegal_triple_store_enabled = _env_bool("KTS_NONLEGAL_TRIPLE_STORE", cfg.nonlegal_triple_store_enabled)
    cfg.troubleshooting_graph_enabled = _env_bool("KTS_TROUBLESHOOT_GRAPH", cfg.troubleshooting_graph_enabled)

    # ── Phase 21: ABS env-var overrides ───────────────────────────
    cfg.abs_enabled = _env_bool("KTS_ABS_ENABLED", cfg.abs_enabled)
    cfg.abs_deals_root = os.environ.get("KTS_ABS_DEALS_ROOT", cfg.abs_deals_root)
    cfg.abs_extraction_mode = os.environ.get("KTS_ABS_EXTRACTION_MODE", cfg.abs_extraction_mode)
    cfg.abs_min_quality_score = _env_float("KTS_ABS_MIN_QUALITY_SCORE", cfg.abs_min_quality_score)
    cfg.abs_max_retries = _env_int("KTS_ABS_MAX_RETRIES", cfg.abs_max_retries)
    cfg.abs_confidence_high = _env_float("KTS_ABS_CONFIDENCE_HIGH", cfg.abs_confidence_high)
    cfg.abs_confidence_low = _env_float("KTS_ABS_CONFIDENCE_LOW", cfg.abs_confidence_low)
    cfg.abs_vectorstore_enabled = _env_bool("KTS_ABS_VECTORSTORE_ENABLED", cfg.abs_vectorstore_enabled)
    cfg.abs_graph_enabled = _env_bool("KTS_ABS_GRAPH_ENABLED", cfg.abs_graph_enabled)
    cfg.abs_embedding_dim = _env_int("KTS_ABS_EMBEDDING_DIM", cfg.abs_embedding_dim)
    cfg.abs_chunk_max_chars = _env_int("KTS_ABS_CHUNK_MAX_CHARS", cfg.abs_chunk_max_chars)
    cfg.abs_chunk_overlap = _env_int("KTS_ABS_CHUNK_OVERLAP", cfg.abs_chunk_overlap)
    cfg.abs_normalize_embeddings = _env_bool("KTS_ABS_NORMALIZE_EMBEDDINGS", cfg.abs_normalize_embeddings)
    cfg.abs_definition_resolution_enabled = _env_bool("KTS_ABS_DEF_RESOLUTION_ENABLED", cfg.abs_definition_resolution_enabled)
    cfg.abs_definition_resolution_depth = _env_int("KTS_ABS_DEF_RESOLUTION_DEPTH", cfg.abs_definition_resolution_depth)
    cfg.abs_definition_resolution_confidence = _env_float("KTS_ABS_DEF_RESOLUTION_CONFIDENCE", cfg.abs_definition_resolution_confidence)
    cfg.abs_output_tolerance = _env_float("KTS_ABS_OUTPUT_TOLERANCE", cfg.abs_output_tolerance)
    cfg.abs_min_definitions = _env_int("KTS_ABS_MIN_DEFINITIONS", cfg.abs_min_definitions)
    cfg.abs_min_waterfall_rules = _env_int("KTS_ABS_MIN_WATERFALL_RULES", cfg.abs_min_waterfall_rules)
    cfg.abs_min_vectors = _env_int("KTS_ABS_MIN_VECTORS", cfg.abs_min_vectors)

    # ── Phase 22: ABS infrastructure env-var overrides ────────────────
    cfg.abs_llm_mode = os.environ.get("KTS_ABS_LLM_MODE", cfg.abs_llm_mode)
    cfg.abs_llm_model = os.environ.get("KTS_ABS_LLM_MODEL", cfg.abs_llm_model)
    cfg.abs_llm_temperature = _env_float("KTS_ABS_LLM_TEMPERATURE", cfg.abs_llm_temperature)
    cfg.abs_llm_max_tokens = _env_int("KTS_ABS_LLM_MAX_TOKENS", cfg.abs_llm_max_tokens)
    cfg.abs_llm_timeout_seconds = _env_int("KTS_ABS_LLM_TIMEOUT", cfg.abs_llm_timeout_seconds)
    cfg.abs_llm_max_retries = _env_int("KTS_ABS_LLM_MAX_RETRIES", cfg.abs_llm_max_retries)
    cfg.abs_use_dual_store = _env_bool("KTS_ABS_USE_DUAL_STORE", cfg.abs_use_dual_store)
    cfg.abs_use_enhanced_graph = _env_bool("KTS_ABS_USE_ENHANCED_GRAPH", cfg.abs_use_enhanced_graph)
    cfg.abs_use_full_retrieval = _env_bool("KTS_ABS_USE_FULL_RETRIEVAL", cfg.abs_use_full_retrieval)
    cfg.abs_retrieval_max_results = _env_int("KTS_ABS_RETRIEVAL_MAX_RESULTS", cfg.abs_retrieval_max_results)
    cfg.abs_retrieval_bm25_weight = _env_float("KTS_ABS_BM25_WEIGHT", cfg.abs_retrieval_bm25_weight)
    cfg.abs_retrieval_vector_weight = _env_float("KTS_ABS_VECTOR_WEIGHT", cfg.abs_retrieval_vector_weight)
    cfg.abs_graph_bfs_depth = _env_int("KTS_ABS_GRAPH_BFS_DEPTH", cfg.abs_graph_bfs_depth)
    cfg.abs_graph_pagerank_enabled = _env_bool("KTS_ABS_PAGERANK_ENABLED", cfg.abs_graph_pagerank_enabled)
    cfg.abs_graph_pagerank_weight = _env_float("KTS_ABS_PAGERANK_WEIGHT", cfg.abs_graph_pagerank_weight)
    cfg.abs_crag_enabled = _env_bool("KTS_ABS_CRAG_ENABLED", cfg.abs_crag_enabled)
    cfg.abs_crag_threshold = _env_float("KTS_ABS_CRAG_THRESHOLD", cfg.abs_crag_threshold)
    cfg.abs_critique_enabled = _env_bool("KTS_ABS_CRITIQUE_ENABLED", cfg.abs_critique_enabled)
    cfg.abs_critique_max_rounds = _env_int("KTS_ABS_CRITIQUE_MAX_ROUNDS", cfg.abs_critique_max_rounds)
    cfg.abs_critique_target = _env_float("KTS_ABS_CRITIQUE_TARGET", cfg.abs_critique_target)
    cfg.abs_multi_query_enabled = _env_bool("KTS_ABS_MULTI_QUERY_ENABLED", cfg.abs_multi_query_enabled)
    cfg.abs_multi_query_count = _env_int("KTS_ABS_MULTI_QUERY_COUNT", cfg.abs_multi_query_count)
    cfg.abs_hyde_enabled = _env_bool("KTS_ABS_HYDE_ENABLED", cfg.abs_hyde_enabled)

    return cfg

def scope_config(base_config: KTSConfig, scope_kb_path: str) -> KTSConfig:
    """Create a config copy with all paths scoped to a specific .kts directory.

    Used by Phase 12.1 per-subfolder isolation: each deal folder gets its own
    .kts directory (vectors, graph, manifest, etc.).

    Parameters
    ----------
    base_config : KTSConfig
        The base configuration to clone.
    scope_kb_path : str
        Absolute or relative path to the scoped ``.kts`` directory,
        e.g. ``kb_test/Fin_deal1/.kts``.

    Returns
    -------
    KTSConfig
        A shallow copy with path attributes overridden.
    """
    import copy
    cfg = copy.copy(base_config)
    cfg.knowledge_base_path = scope_kb_path
    cfg.chroma_persist_dir = f"{scope_kb_path}/vectors/chroma"
    cfg.phase6_chroma_dir = f"{scope_kb_path}/vectors/phase6"
    cfg.graph_path = f"{scope_kb_path}/graph/knowledge_graph.json"
    cfg.manifest_path = f"{scope_kb_path}/manifest.json"
    cfg.troubleshooting_graph_path = f"{scope_kb_path}/graph/troubleshooting_graph.json"
    # ABS paths are independent of KTS scope — they live under abs_deals_root
    return cfg