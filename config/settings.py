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
    legal_max_chunk_size: int = 5000            # Max section size for semantic chunking

    # ── Retrieval Pipeline (Epic 3 — TD §6) ───────────────────────
    max_chunks_per_doc: int = 3                 # dedup keeps top N chunks per document
    deep_max_chunks_per_doc: int = 5            # /deep mode keeps more chunks per document
    query_expansion_enabled: bool = True        # Multi-query retrieval with LLM expansion
    query_expansion_count: int = 3              # Number of query variations to generate
    acronym_resolver_enabled: bool = True
    learned_synonyms_enabled: bool = True       # use auto-learned synonyms at retrieval
    term_resolution_enabled: bool = True
    
    # ── Context Expansion (Smart Retrieval) ───────────────────────
    context_expansion_enabled: bool = True      # Expand context window around hit chunks
    context_window_size: int = 1                # Chunks to retrieve before/after hit (±N)
    adaptive_expansion_enabled: bool = True     # Adjust window based on confidence
    continuation_detection_enabled: bool = True # Detect mid-sentence/list continuations
    metadata_guided_expansion: bool = True      # Use section headers to guide expansion
    cross_encoder_enabled: bool = False         # auto-enabled when KTS_CROSSENCODER_MODEL_PATH set
    cross_encoder_model_path: str = ""          # set by core extension from addon registry
    pagerank_enabled: bool = False              # deferred to Phase 4.1
    context_expansion_enabled: bool = False     # ChunkExpander — deferred
    multi_hop_enabled: bool = True
    section_aware_chunking_enabled: bool = True # LegalChunker — semantic section-aware chunking

    # ── Graph Scoring (TD §6.5) ───────────────────────────────────
    graph_boost_cap: float = 0.7
    graph_boost_timeout_ms: int = 20

    # ── Debug (TD §9.3) ──────────────────────────────────────────
    debug_level: int = 0                        # 0=off, 1=summary, 2=verbose


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
    cfg.ner_enabled = _env_bool("KTS_NER_ENABLED", bool(cfg.spacy_model_path) or ner_bundled)
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
    # Cross-encoder: auto-enable if model path is provided
    cfg.cross_encoder_model_path = os.environ.get("KTS_CROSSENCODER_MODEL_PATH", cfg.cross_encoder_model_path)
    cfg.cross_encoder_enabled = _env_bool("KTS_CROSS_ENCODER_ENABLED", bool(cfg.cross_encoder_model_path))
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
    override = os.environ.get("KTS_CORPUS_REGIME_OVERRIDE", "").strip()
    if override:
        cfg.corpus_regime_override = override

    return cfg
