"""
Vector search adapter — bridges PayGen search calls to KTS DualVectorStore.

Phase 22 replacement for Phase 21 stub.

KTS APIs used:
    DualVectorStore(persist_dir, provider).search_items(query, top_k, filters)
    get_embedding_provider(config) → EmbeddingProvider for embeddings

Ported from PayGen pipeline.skills.vector_search → backend.abs.skills
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Lazy KTS infrastructure imports ──────────────────────────────

try:
    from backend.vector.dual_vector_store import DualVectorStore
    from backend.vector.embedding_provider import get_embedding_provider
    _HAS_VECTOR = True
except ImportError:
    _HAS_VECTOR = False
    logger.warning("KTS DualVectorStore unavailable — vector_search() will fail")


# ── Data Classes ──────────────────────────────────────────────────


@dataclass
class SearchResult:
    """ABS search result — compatible with PayGen consumers.

    Enhanced from Phase 21 stub with source, section, confidence,
    and evidence_chain fields for richer retrieval information.
    """
    text: str
    score: float  # cosine similarity (higher = more similar)
    metadata: dict = field(default_factory=dict)
    id: str = ""
    source: str = ""
    section: str = ""
    confidence: float = 0.0
    evidence_chain: list[str] = field(default_factory=list)


# ── Singleton cache ──────────────────────────────────────────────

_store: Optional[Any] = None
_provider: Optional[Any] = None


def _get_store(config) -> Any:
    """Lazy-init singleton DualVectorStore."""
    global _store, _provider
    if _store is None:
        if not _HAS_VECTOR:
            raise RuntimeError(
                "KTS DualVectorStore not available. "
                "Ensure backend.vector.dual_vector_store is importable."
            )
        logger.info("Initializing DualVectorStore for ABS domain")
        _provider = get_embedding_provider(config)
        persist_dir = getattr(config, "chroma_persist_dir", str(Path.cwd() / "chroma_db"))
        _store = DualVectorStore(persist_dir, embedding_provider=_provider)
    return _store


def reset_store() -> None:
    """Reset cached store (for testing)."""
    global _store, _provider
    _store = None
    _provider = None


# ── Public API ────────────────────────────────────────────────────


def vector_search(
    query_text: str,
    config=None,
    collection_name: Optional[str] = None,
    n_results: int = 10,
    where_filter: Optional[dict] = None,
    llm_callable: Optional[Any] = None,
    *,
    # Legacy signature compat
    chroma_path: Optional[Path] = None,
    embedding_model: Optional[str] = None,
) -> list[SearchResult]:
    """Search ABS content using KTS's DualVectorStore.

    Uses BM25 + vector hybrid search via ChromaDB. When ``llm_callable``
    is provided, future enhancements can enable multi-query expansion,
    HyDE, CRAG verification, and critique loops.

    Args:
        query_text: Natural language query.
        config: KTSConfig instance.
        collection_name: Optional collection context (informational).
        n_results: Maximum results to return.
        where_filter: Optional metadata filter dict.
        llm_callable: Optional LLM function for advanced features.

    Returns:
        List of SearchResult objects sorted by score descending.
    """
    if config is None:
        from config.settings import load_config
        config = load_config()

    store = _get_store(config)

    # Build filter from collection_name context + explicit filter
    filters = dict(where_filter or {})
    if collection_name:
        # If collection_name encodes deal_id (e.g. "abs_bear_stearns_items"),
        # add it as a metadata filter
        if collection_name.startswith("abs_") and "_items" in collection_name:
            deal_part = collection_name.replace("abs_", "").replace("_items", "")
            filters["deal_id"] = deal_part

    filter_arg = filters if filters else None

    # Search using DualVectorStore
    results = store.search_items(
        query=query_text,
        top_k=n_results,
        filters=filter_arg,
    )

    mapped = [_map_kts_result(r) for r in results]
    logger.debug(f"ABS search '{query_text[:50]}...' returned {len(mapped)} results")
    return mapped


def _map_kts_result(r: dict) -> SearchResult:
    """Map KTS search result dict to ABS SearchResult."""
    metadata = r.get("metadata", {})
    return SearchResult(
        text=r.get("text", r.get("content", "")),
        score=r.get("similarity", r.get("score", 0.0)),
        metadata=metadata,
        id=r.get("id", ""),
        source=metadata.get("source_file", metadata.get("source", "")),
        section=metadata.get("section_number", metadata.get("section", "")),
        confidence=r.get("similarity", r.get("confidence", 0.0)),
        evidence_chain=[],
    )


def search_by_section(
    query_text: str,
    config=None,
    collection_name: Optional[str] = None,
    section_type: str = "",
    n_results: int = 5,
    *,
    chroma_path: Optional[Path] = None,
) -> list[SearchResult]:
    """Search within a specific section type.

    Args:
        query_text: Query text.
        config: KTSConfig instance.
        collection_name: Optional collection context.
        section_type: Section type filter.
        n_results: Max results.

    Returns:
        List of SearchResult objects.
    """
    where_filter = {}
    if section_type:
        where_filter["section_type"] = section_type

    return vector_search(
        query_text=query_text,
        config=config,
        collection_name=collection_name,
        n_results=n_results,
        where_filter=where_filter,
    )


def search_definitions(
    term: str,
    config=None,
    deal_id: str = "",
) -> list[SearchResult]:
    """Search for a defined term across a deal's documents."""
    where_filter = {"item_type": "Definition"}
    if deal_id:
        where_filter["deal_id"] = deal_id

    return vector_search(
        query_text=f'definition of "{term}"',
        config=config,
        collection_name=f"abs_{deal_id}_items" if deal_id else None,
        n_results=5,
        where_filter=where_filter,
    )


def search_waterfall_rules(
    config=None,
    deal_id: str = "",
    llm_callable: Optional[Any] = None,
) -> list[SearchResult]:
    """Search for all waterfall/distribution rules in a deal.

    This is a key ABS-specific search used by the model creation agent.
    """
    where_filter: dict[str, Any] = {}
    if deal_id:
        where_filter["deal_id"] = deal_id

    return vector_search(
        query_text="distribution waterfall payment priority rules order",
        config=config,
        collection_name=f"abs_{deal_id}_items" if deal_id else None,
        n_results=20,
        llm_callable=llm_callable,
        where_filter=where_filter,
    )


def search_cross_deal(
    query_text: str,
    deal_paths: list[Path],
    config=None,
    n_per_deal: int = 3,
) -> dict[str, list[SearchResult]]:
    """Search across multiple deals' vectors for cross-referencing.

    Args:
        query_text: Search query.
        deal_paths: List of deal directory paths.
        config: KTSConfig instance.
        n_per_deal: Results per deal.

    Returns:
        Dict mapping deal_id to list of SearchResult.
    """
    results: dict[str, list[SearchResult]] = {}
    for deal_path in deal_paths:
        deal_id = Path(deal_path).name
        deal_results = vector_search(
            query_text=query_text,
            config=config,
            collection_name=f"abs_{deal_id}_items",
            n_results=n_per_deal,
        )
        results[deal_id] = deal_results
    return results
