# Phase 22: Technical Design
## Implementation-Ready Specifications

**Document Version:** 1.0  
**Date:** February 26, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** Exact file paths, code implementations, configuration

---

## Table of Contents
1. [File Structure — Phase 22 Changes](#file-structure)
2. [Modified Files](#modified-files)
3. [New Files](#new-files)
4. [Adapter Implementations — Complete Code](#adapter-implementations)
5. [LLM Bridge — Complete Code](#llm-bridge)
6. [ABS Agent LLM Injection — Pattern and All 13 Agents](#agent-injection)
7. [ABS Retrieval Profile — Complete Code](#retrieval-profile)
8. [ABS Graph Schema Registration — Complete Code](#graph-schema)
9. [KTSConfig Phase 22 Additions](#config-additions)
10. [VS Code Extension Bridge (JavaScript Side)](#vscode-bridge)
11. [Integration Points — Detailed Wiring](#integration-points)

---

## File Structure — Phase 22 Changes

```
gsf_ir_kts_agentic_system/
├── backend/
│   └── abs/
│       ├── skills/
│       │   ├── embedder.py          ← REPLACED (stub → adapter, ~120 lines)
│       │   ├── graph_builder.py     ← REPLACED (stub → adapter, ~150 lines)
│       │   └── vector_search.py     ← REPLACED (stub → adapter, ~160 lines)
│       ├── config/
│       │   ├── __init__.py          ← NEW (5 lines)
│       │   ├── retrieval_profile.py ← NEW (60 lines)
│       │   └── graph_schema.py      ← NEW (100 lines)
│       ├── llm_bridge.py            ← NEW (200 lines)
│       ├── agents/
│       │   ├── governing_doc_generator.py  ← MODIFIED (+40 lines)
│       │   ├── knowledge_store.py          ← MODIFIED (+35 lines)
│       │   ├── model_creation_agent.py     ← MODIFIED (+60 lines)
│       │   ├── qa_agent.py                 ← MODIFIED (+45 lines)
│       │   ├── structured_extractor.py     ← MODIFIED (+35 lines)
│       │   ├── audit_agent.py              ← MODIFIED (+40 lines)
│       │   ├── data_prep.py                ← MODIFIED (+20 lines)
│       │   ├── deal_analyzer.py            ← MODIFIED (+30 lines)
│       │   ├── ingestion_orchestrator.py   ← MODIFIED (+25 lines)
│       │   ├── pipeline_coordinator.py     ← MODIFIED (+20 lines)
│       │   ├── section_splitter.py         ← MODIFIED (+15 lines)
│       │   ├── document_converter.py       ← MODIFIED (+10 lines)
│       │   └── model_validator.py          ← MODIFIED (+15 lines)
│       └── __init__.py              ← MODIFIED (add llm_bridge export)
├── config/
│   └── settings.py                  ← MODIFIED (+30 lines, Phase 22 config)
└── extension/
    └── src/
        └── abs/
            └── absParticipant.ts     ← NEW (placeholder, ~50 lines)
```

### Summary

| Category | Count | Lines |
|---------|-------|-------|
| Replaced (stub → adapter) | 3 | ~430 |
| New files | 5 | ~415 |
| Modified files | 15 | ~420 |
| **Total** | **23** | **~1,265** |

---

## Modified Files

### 1. `backend/abs/__init__.py` — Add LLM Bridge Export

```python
# Add to existing __init__.py:
from backend.abs.llm_bridge import create_llm_callable, get_usage_stats, LLMCallable
```

### 2. `config/settings.py` — Phase 22 Config Additions

Add these properties to the `KTSConfig` class (after existing `abs_*` properties from Phase 21):

```python
    # ── Phase 22: Infrastructure Integration ──────────────────────────
    
    # LLM Configuration
    abs_llm_mode: str = "none"                    # "vscode" | "mock" | "none"
    abs_llm_model: str = "gpt-4.1"               # Model for background tasks
    abs_llm_temperature: float = 0.0             # Default temperature
    abs_llm_max_tokens: int = 4096              # Default max tokens
    abs_llm_timeout_seconds: int = 60            # Timeout per LLM call
    abs_llm_max_retries: int = 2                 # Retry count on failure
    
    # Infrastructure Feature Flags
    abs_use_dual_store: bool = True              # Use dual vector store
    abs_use_enhanced_graph: bool = True          # Use enhanced graph builder
    abs_use_full_retrieval: bool = True          # Use full retrieval pipeline
    
    # Retrieval Tuning
    abs_retrieval_max_results: int = 10          # Max search results
    abs_retrieval_bm25_weight: float = 0.5       # BM25 weight (legal precision)
    abs_retrieval_vector_weight: float = 0.5     # Vector weight
    abs_chunk_max_chars: int = 4000              # Chunk size (legal sections)
    abs_chunk_overlap: int = 800                 # Overlap chars
    
    # Graph Tuning
    abs_graph_bfs_depth: int = 5                 # BFS expansion depth
    abs_graph_pagerank_enabled: bool = True      # PageRank scoring
    abs_graph_pagerank_weight: float = 0.25      # PageRank boost weight
    
    # Advanced Retrieval Features (require LLM)
    abs_crag_enabled: bool = True                # CRAG verification
    abs_crag_threshold: float = 0.85             # Confidence threshold
    abs_critique_enabled: bool = True            # Critique loop
    abs_critique_max_rounds: int = 3             # Max refinement rounds
    abs_critique_target: float = 0.92            # Target confidence
    abs_multi_query_enabled: bool = True         # Multi-query expansion
    abs_multi_query_count: int = 6               # Query variant count
    abs_hyde_enabled: bool = True                # HyDE generation
```

---

## New Files

### `backend/abs/config/__init__.py`

```python
"""ABS-specific configuration — retrieval profiles and graph schema."""

from backend.abs.config.retrieval_profile import ABS_RETRIEVAL_PROFILE
from backend.abs.config.graph_schema import ABS_NODE_TYPES, ABS_EDGE_TYPES
```

### `backend/abs/config/retrieval_profile.py`

```python
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
                # Apply profile value (which is same as default in this case)
                setattr(config, config_attr, profile.get(profile_key, default_val))
```

### `backend/abs/config/graph_schema.py`

```python
"""
ABS graph schema — node and edge type definitions for ABS domain.

Registers 10 ABS-specific node types and 10 edge types into
KTS's EnhancedGraphBuilder type system. All prefixed with 'abs_'
to prevent namespace collisions with KTS's 14 standard types.
"""

from dataclasses import dataclass


@dataclass
class NodeTypeDef:
    """Definition of a graph node type."""
    name: str
    description: str
    properties: list[str]
    is_root: bool = False


@dataclass
class EdgeTypeDef:
    """Definition of a graph edge type."""
    name: str
    from_type: str
    to_type: str
    weight: float = 1.0


ABS_NODE_TYPES = [
    NodeTypeDef(
        name="abs_deal",
        description="ABS deal entity (e.g., Bear Stearns 2006-HE1)",
        properties=["deal_id", "issuer", "series", "closing_date", "deal_type"],
        is_root=True,
    ),
    NodeTypeDef(
        name="abs_document",
        description="Legal document (PSA, Indenture, Supplement)",
        properties=["doc_type", "content_hash", "filename", "page_count"],
    ),
    NodeTypeDef(
        name="abs_article",
        description="Article within a legal document",
        properties=["article_num", "title", "text_preview"],
    ),
    NodeTypeDef(
        name="abs_section",
        description="Section within an article",
        properties=["section_num", "parent_article", "title"],
    ),
    NodeTypeDef(
        name="abs_definition",
        description="Defined term within the agreement",
        properties=["term", "full_text", "section_ref"],
    ),
    NodeTypeDef(
        name="abs_obligation",
        description="Obligation or duty",
        properties=["actor", "verb", "full_text", "section_ref"],
    ),
    NodeTypeDef(
        name="abs_waterfall_rule",
        description="Payment waterfall priority rule",
        properties=["priority", "payee", "formula", "conditions"],
    ),
    NodeTypeDef(
        name="abs_class",
        description="Certificate/note class",
        properties=["class_name", "initial_balance", "rate_type", "coupon"],
    ),
    NodeTypeDef(
        name="abs_account",
        description="Deal account",
        properties=["account_name", "purpose", "section_ref"],
    ),
    NodeTypeDef(
        name="abs_trigger",
        description="Performance trigger or event of default",
        properties=["trigger_type", "threshold", "consequence", "section_ref"],
    ),
]

ABS_EDGE_TYPES = [
    EdgeTypeDef("HAS_DOCUMENT", "abs_deal", "abs_document", weight=1.0),
    EdgeTypeDef("HAS_ARTICLE", "abs_document", "abs_article", weight=1.0),
    EdgeTypeDef("HAS_SECTION", "abs_article", "abs_section", weight=1.0),
    EdgeTypeDef("DEFINES", "abs_section", "abs_definition", weight=0.9),
    EdgeTypeDef("HAS_OBLIGATION", "abs_section", "abs_obligation", weight=0.9),
    EdgeTypeDef("HAS_RULE", "abs_section", "abs_waterfall_rule", weight=0.95),
    EdgeTypeDef("REFERENCES", "abs_section", "abs_section", weight=0.7),
    EdgeTypeDef("USES_TERM", "abs_obligation", "abs_definition", weight=0.8),
    EdgeTypeDef("APPLIES_TO", "abs_waterfall_rule", "abs_class", weight=0.9),
    EdgeTypeDef("TRIGGERS", "abs_trigger", "abs_waterfall_rule", weight=0.85),
]


def get_all_node_type_names() -> list[str]:
    """Return all ABS node type names."""
    return [n.name for n in ABS_NODE_TYPES]


def get_all_edge_type_names() -> list[str]:
    """Return all ABS edge type names."""
    return [e.name for e in ABS_EDGE_TYPES]
```

---

## Adapter Implementations — Complete Code

### `backend/abs/skills/embedder.py` (Replaces Stub)

```python
"""
Embedder adapter — bridges PayGen embedding calls to KTS EmbeddingProvider.

Phase 22 replacement for Phase 21 stub.
Preserves PayGen's function signatures for backward compatibility.

PayGen API:
    embed(texts, config) → list[list[float]]
    chunk_text(text, max_chars, overlap) → list[str]
    embed_and_store(texts, metadatas, collection, config) → int

KTS API:
    EmbeddingProvider(config).embed_documents(texts) → list[list[float]]
    LegalChunker(max_chars, overlap).chunk(text) → list[str]
    DualVectorStore(config).add_items(...) → None
"""

import logging
from typing import Optional

from backend.vector.embedding_provider import EmbeddingProvider
from config.settings import KTSConfig

logger = logging.getLogger(__name__)

_provider: Optional[EmbeddingProvider] = None


def _get_provider(config: KTSConfig) -> EmbeddingProvider:
    """Lazy-init singleton embedding provider."""
    global _provider
    if _provider is None:
        logger.info("Initializing EmbeddingProvider for ABS domain")
        _provider = EmbeddingProvider(config)
    return _provider


def reset_provider() -> None:
    """Reset cached provider (for testing)."""
    global _provider
    _provider = None


def embed(texts: list[str], config: KTSConfig) -> list[list[float]]:
    """Embed texts using KTS's BGE ONNX INT8 provider.
    
    Args:
        texts: List of text strings to embed.
        config: KTSConfig instance.
        
    Returns:
        List of 768-dimensional embedding vectors.
    """
    if not texts:
        return []
    provider = _get_provider(config)
    return provider.embed_documents(texts)


def chunk_text(
    text: str,
    max_chars: int = None,
    overlap: int = None,
) -> list[str]:
    """Split text into overlapping chunks.
    
    Uses KTS's LegalChunker which is heading-aware — an upgrade
    over PayGen's simple character-split approach.
    """
    from backend.vector.legal_chunker import LegalChunker
    
    if max_chars is None:
        max_chars = 4000  # ABS default (longer than KTS's 3000)
    if overlap is None:
        overlap = 800     # ABS default (more than KTS's 500)
    
    chunker = LegalChunker(max_chars=max_chars, overlap=overlap)
    return chunker.chunk(text)


def embed_and_store(
    texts: list[str],
    metadatas: list[dict],
    collection_name: str,
    config: KTSConfig,
) -> int:
    """Embed texts and store in ChromaDB.
    
    Args:
        texts: Text content to embed and store.
        metadatas: Metadata dictionaries for each text.
        collection_name: ChromaDB collection name (use abs_ prefix).
        config: KTSConfig instance.
        
    Returns:
        Number of items stored.
    """
    if not texts:
        return 0
    
    if len(texts) != len(metadatas):
        raise ValueError(
            f"texts ({len(texts)}) and metadatas ({len(metadatas)}) must have same length"
        )
    
    provider = _get_provider(config)
    embeddings = provider.embed_documents(texts)
    
    from backend.vector.dual_vector_store import DualVectorStore
    store = DualVectorStore(config)
    store.add_items(
        texts=texts,
        embeddings=embeddings,
        metadatas=metadatas,
        collection_name=collection_name,
    )
    
    logger.info(f"Stored {len(texts)} items in collection '{collection_name}'")
    return len(texts)


def embed_query(query: str, config: KTSConfig) -> list[float]:
    """Embed a single query string.
    
    Uses the same provider but may apply different preprocessing
    for queries vs documents in the future.
    """
    provider = _get_provider(config)
    vectors = provider.embed_documents([query])
    return vectors[0] if vectors else []
```

### `backend/abs/skills/graph_builder.py` (Replaces Stub)

```python
"""
Graph builder adapter — bridges PayGen graph calls to KTS EnhancedGraphBuilder.

Phase 22 replacement for Phase 21 stub.

PayGen API:
    build_graph(sections, config) → nx.DiGraph
    save_graph(graph, path) → None
    load_graph(path) → Optional[nx.DiGraph]

KTS API:
    EnhancedGraphBuilder(config).build_from_sections(sections) → nx.DiGraph
    PageRank computation via nx.pagerank()
"""

import logging
import networkx as nx
from pathlib import Path
from typing import Optional

from backend.graph.enhanced_graph_builder import EnhancedGraphBuilder
from backend.abs.config.graph_schema import (
    ABS_NODE_TYPES,
    ABS_EDGE_TYPES,
    get_all_node_type_names,
)
from config.settings import KTSConfig

logger = logging.getLogger(__name__)


def build_graph(sections: list[dict], config: KTSConfig) -> nx.DiGraph:
    """Build ABS knowledge graph using KTS's enhanced builder.
    
    Transforms PayGen's flat section format into KTS's typed format,
    then delegates to EnhancedGraphBuilder.
    
    Args:
        sections: PayGen-format section dicts with items.
        config: KTSConfig instance.
        
    Returns:
        NetworkX DiGraph with ABS-typed nodes/edges.
    """
    builder = EnhancedGraphBuilder(config)
    
    # Transform to KTS format
    kts_sections = _transform_sections(sections)
    graph = builder.build_from_sections(kts_sections)
    
    # Tag ABS nodes
    for node_id, data in graph.nodes(data=True):
        if data.get("node_type", "").startswith("abs_"):
            data["abs_domain"] = True
    
    # PageRank
    if config.abs_graph_pagerank_enabled:
        _compute_pagerank(graph)
    
    node_count = graph.number_of_nodes()
    edge_count = graph.number_of_edges()
    logger.info(f"Built ABS graph: {node_count} nodes, {edge_count} edges")
    
    return graph


def _transform_sections(sections: list[dict]) -> list[dict]:
    """Transform PayGen section format to KTS format.
    
    PayGen:  {"section_id": "5.02", "title": "...", "text": "...", "items": [...]}
    KTS:     {"id": "abs_section_5.02", "node_type": "abs_section", "content": "...", ...}
    """
    kts_sections = []
    for s in sections:
        sid = s.get("section_id", "unknown")
        children = []
        for i, item in enumerate(s.get("items", [])):
            children.append({
                "id": f"abs_item_{i}_{sid}",
                "node_type": _classify_item_type(item),
                "content": item.get("text", str(item)),
                "metadata": item,
            })
        
        kts_sections.append({
            "id": f"abs_section_{sid}",
            "node_type": "abs_section",
            "content": s.get("text", ""),
            "metadata": {
                "section_id": sid,
                "title": s.get("title", ""),
                "article": s.get("article", ""),
            },
            "children": children,
        })
    
    return kts_sections


def _classify_item_type(item: dict) -> str:
    """Map PayGen item type to ABS node type."""
    item_type = item.get("type", "").lower()
    mapping = {
        "definition": "abs_definition",
        "obligation": "abs_obligation",
        "rule": "abs_waterfall_rule",
        "waterfall": "abs_waterfall_rule",
        "account": "abs_account",
        "trigger": "abs_trigger",
        "event_of_default": "abs_trigger",
        "class": "abs_class",
    }
    return mapping.get(item_type, "abs_obligation")


def _compute_pagerank(graph: nx.DiGraph) -> None:
    """Compute and attach PageRank scores."""
    if graph.number_of_nodes() == 0:
        return
    try:
        ranks = nx.pagerank(graph, alpha=0.85, max_iter=100)
        for node_id, score in ranks.items():
            graph.nodes[node_id]["pagerank"] = score
        logger.debug(f"Computed PageRank for {len(ranks)} nodes")
    except nx.NetworkXError as e:
        logger.warning(f"PageRank computation failed: {e}")


def save_graph(graph: nx.DiGraph, path: Path) -> None:
    """Save graph to GraphML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(graph, str(path))
    logger.info(f"Saved graph to {path}")


def load_graph(path: Path) -> Optional[nx.DiGraph]:
    """Load graph from GraphML file."""
    if not path.exists():
        logger.warning(f"Graph file not found: {path}")
        return None
    graph = nx.read_graphml(str(path))
    logger.info(f"Loaded graph from {path}: {graph.number_of_nodes()} nodes")
    return graph


def get_neighbors(
    graph: nx.DiGraph,
    node_id: str,
    depth: int = 1,
    edge_types: Optional[set[str]] = None,
) -> list[tuple[str, dict]]:
    """Get neighboring nodes up to specified depth.
    
    Args:
        graph: The knowledge graph.
        node_id: Starting node.
        depth: BFS depth.
        edge_types: Optional filter for edge types.
        
    Returns:
        List of (node_id, node_data) tuples.
    """
    if node_id not in graph:
        return []
    
    visited = set()
    queue = [(node_id, 0)]
    results = []
    
    while queue:
        current, d = queue.pop(0)
        if current in visited or d > depth:
            continue
        visited.add(current)
        
        if current != node_id:
            results.append((current, dict(graph.nodes[current])))
        
        for neighbor in graph.successors(current):
            edge_data = graph.edges[current, neighbor]
            if edge_types is None or edge_data.get("edge_type") in edge_types:
                queue.append((neighbor, d + 1))
    
    return results
```

### `backend/abs/skills/vector_search.py` (Replaces Stub)

```python
"""
Vector search adapter — bridges PayGen search calls to KTS RetrievalService.

Phase 22 replacement for Phase 21 stub.

PayGen API:
    vector_search(query, config, collection, max_results) → list[SearchResult]
    search_by_section(section_id, config) → list[SearchResult]

KTS API:
    RetrievalService(config).search(query, **kwargs) → list[RetrievalResult]
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from backend.retrieval.retrieval_service import RetrievalService
from config.settings import KTSConfig

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """ABS search result — compatible with PayGen consumers."""
    text: str
    score: float
    metadata: dict
    source: str = ""
    section: str = ""
    confidence: float = 0.0
    evidence_chain: list[str] = field(default_factory=list)


_service: Optional[RetrievalService] = None


def _get_service(config: KTSConfig) -> RetrievalService:
    """Lazy-init singleton retrieval service."""
    global _service
    if _service is None:
        logger.info("Initializing RetrievalService for ABS domain")
        _service = RetrievalService(config)
    return _service


def reset_service() -> None:
    """Reset cached service (for testing)."""
    global _service
    _service = None


def vector_search(
    query: str,
    config: KTSConfig,
    collection_name: Optional[str] = None,
    max_results: int = 10,
    llm_callable: Optional[callable] = None,
    **kwargs,
) -> list[SearchResult]:
    """Search ABS content using KTS's full retrieval pipeline.
    
    When llm_callable is provided, enables:
    - Multi-query expansion (6 query variants)
    - HyDE (hypothetical document embedding)
    - CRAG verification (claim-level fact checking)
    - Critique loop (iterative refinement, max 3 rounds)
    
    When llm_callable is None:
    - Uses BM25 + vector hybrid search (still very effective)
    - No LLM-powered features
    
    Args:
        query: Search query text.
        config: KTSConfig instance.
        collection_name: Optional collection filter (abs_{deal_id}_items).
        max_results: Maximum results to return.
        llm_callable: Optional LLM function for advanced features.
        
    Returns:
        List of SearchResult objects sorted by score descending.
    """
    service = _get_service(config)
    
    search_kwargs = {
        "query": query,
        "max_results": max_results,
    }
    
    if collection_name:
        search_kwargs["collection_filter"] = collection_name
    
    # Enable/disable LLM features
    has_llm = llm_callable is not None
    search_kwargs["llm_callable"] = llm_callable
    search_kwargs["enable_multi_query"] = has_llm and config.abs_multi_query_enabled
    search_kwargs["enable_hyde"] = has_llm and config.abs_hyde_enabled
    search_kwargs["enable_crag"] = has_llm and config.abs_crag_enabled
    search_kwargs["enable_critique"] = has_llm and config.abs_critique_enabled
    
    # Apply ABS-specific retrieval weights
    search_kwargs["bm25_weight"] = config.abs_retrieval_bm25_weight
    search_kwargs["vector_weight"] = config.abs_retrieval_vector_weight
    
    results = service.search(**search_kwargs, **kwargs)
    
    mapped = [_map_result(r) for r in results]
    logger.debug(f"ABS search '{query[:50]}...' returned {len(mapped)} results")
    return mapped


def _map_result(r) -> SearchResult:
    """Map KTS RetrievalResult to ABS SearchResult."""
    return SearchResult(
        text=getattr(r, 'content', str(r)),
        score=getattr(r, 'confidence', 0.0),
        metadata=getattr(r, 'metadata', {}),
        source=getattr(r, 'source', ''),
        section=getattr(r, 'metadata', {}).get('section', ''),
        confidence=getattr(r, 'confidence', 0.0),
        evidence_chain=getattr(r, 'evidence_chain', []),
    )


def search_by_section(
    section_id: str,
    config: KTSConfig,
    collection_name: Optional[str] = None,
) -> list[SearchResult]:
    """Search for all content in a specific section."""
    return vector_search(
        query=f"section:{section_id}",
        config=config,
        collection_name=collection_name,
    )


def search_definitions(
    term: str,
    config: KTSConfig,
    deal_id: str,
) -> list[SearchResult]:
    """Search for a defined term across a deal's documents."""
    return vector_search(
        query=f'definition of "{term}"',
        config=config,
        collection_name=f"abs_{deal_id}_items",
        max_results=5,
    )


def search_waterfall_rules(
    config: KTSConfig,
    deal_id: str,
    llm_callable: Optional[callable] = None,
) -> list[SearchResult]:
    """Search for all waterfall/distribution rules in a deal.
    
    This is a key ABS-specific search used by the model creation agent.
    """
    return vector_search(
        query="distribution waterfall payment priority rules order",
        config=config,
        collection_name=f"abs_{deal_id}_items",
        max_results=20,
        llm_callable=llm_callable,
    )
```

---

## LLM Bridge — Complete Code

See Architecture Upgrade doc (03) for complete `backend/abs/llm_bridge.py` implementation (~200 lines).

### Usage Pattern in Agents

```python
from backend.abs.llm_bridge import create_llm_callable

# CLI creates callable based on mode flag
llm = create_llm_callable(mode=config.abs_llm_mode, model=config.abs_llm_model)

# Pass to agent constructor
agent = QAAgent(config=config, deal_scope=scope, llm_callable=llm)

# Agent uses internally
result = agent.execute(task="Answer: What is the Distribution Waterfall?")
```

---

## ABS Agent LLM Injection — All 13 Agents

### Universal Pattern

Every ABS agent follows this pattern for LLM injection:

```python
class SomeABSAgent(AgentBase):
    """Example ABS agent with LLM injection."""
    
    def __init__(
        self,
        config: KTSConfig,
        deal_scope: DealScope,
        llm_callable: Optional[LLMCallable] = None,  # ← Added in Phase 22
    ):
        super().__init__(
            name="some_abs_agent",
            config=config,
            llm_callable=llm_callable,                # ← Passed to base
        )
        self.deal_scope = deal_scope
    
    def _run(self, task: str) -> AgentOutput:
        if self._llm:
            return self._llm_enhanced_run(task)
        else:
            return self._template_fallback(task)
    
    def _llm_enhanced_run(self, task: str) -> AgentOutput:
        """LLM-powered execution path."""
        prompt = self._build_prompt(task)
        system = self._get_system_prompt()
        response = self._llm(prompt, system)
        return self._parse_response(response)
    
    def _template_fallback(self, task: str) -> AgentOutput:
        """Non-LLM fallback — existing PayGen behavior."""
        # Original PayGen logic unchanged
        ...
```

### Per-Agent LLM Details

#### 1. `governing_doc_generator.py`

```python
# System prompts for 2 call sites:
SYSTEM_GENERATE = (
    "You are an ABS payment model engineer specializing in "
    "Pooling and Servicing Agreements. Generate a structured "
    "governing document section based on the extracted PSA data. "
    "Use precise financial terminology. Output markdown."
)

SYSTEM_CONSOLIDATE = (
    "You are a legal document merger. Consolidate the following "
    "governing document sections into a coherent whole, resolving "
    "conflicts by preferring the most specific provision."
)
```

#### 2. `model_creation_agent.py`

```python
# System prompts for 3 call sites:
SYSTEM_GENERATE_MODEL = (
    "You are a Python financial engineer. Generate a payment "
    "waterfall model based on the governing document rules. "
    "The model must be a pure Python function that takes deal_data "
    "and period as inputs and returns a dict of distributions. "
    "Use only standard library. No external dependencies."
)

SYSTEM_REFINE = (
    "You are a debugging assistant for ABS payment models. "
    "The model produced incorrect outputs. Analyze the errors "
    "and generate a corrected version."
)

SYSTEM_VALIDATE = (
    "You are a QA engineer for financial models. Review the "
    "payment model code for correctness, edge cases, and "
    "compliance with the governing document rules."
)
```

#### 3. `qa_agent.py`

```python
# System prompts for 2 call sites:
SYSTEM_ANSWER = (
    "You are an ABS analyst answering questions about structured "
    "finance deals. Use the provided context from the PSA/Indenture "
    "to give precise, citation-backed answers. Always cite the "
    "specific Section number."
)

SYSTEM_FOLLOWUP = (
    "You are a Socratic questioner. Based on the user's question "
    "and the answer provided, generate 3 follow-up questions that "
    "would deepen understanding of the deal structure."
)
```

#### 4. `structured_extractor.py`

```python
SYSTEM_EXTRACT = (
    "You are a legal data extraction engine. Extract structured "
    "entities from the PSA section text. Output JSON with fields: "
    "type, text, actors, defined_terms, section_ref."
)

SYSTEM_RELATE = (
    "You are a knowledge graph builder. Given extracted entities, "
    "identify relationships between them. Output JSON edges with "
    "fields: from_id, to_id, relationship, confidence."
)
```

#### 5–13. Remaining Agents (abbreviated — same pattern)

Each follows the universal pattern above with domain-specific system prompts. The full system prompt text for each agent will be maintained in `backend/abs/config/prompts.py` (new file, ~200 lines of system prompt constants).

---

## VS Code Extension Bridge (JavaScript Side)

### `extension/src/abs/absLLMBridge.ts` (Placeholder)

```typescript
/**
 * ABS LLM Bridge — handles IPC with Python backend for LLM calls.
 * 
 * Protocol:
 * 1. Python writes JSON request to stdout: {"type":"llm_request",...}
 * 2. Extension reads request, calls vscode.lm.selectChatModels()
 * 3. Extension sends prompt to selected model
 * 4. Extension writes JSON response to Python's stdin: {"text":"..."}
 */

import * as vscode from 'vscode';

interface LLMRequest {
    type: 'llm_request';
    model: string;
    prompt: string;
    system_prompt?: string;
    temperature: number;
    max_tokens: number;
}

interface LLMResponse {
    text: string;
    input_tokens: number;
    output_tokens: number;
}

export async function handleLLMRequest(
    request: LLMRequest,
    token: vscode.CancellationToken,
): Promise<LLMResponse> {
    // Select model — use gpt-4.1 for background, user-selected for visible
    const models = await vscode.lm.selectChatModels({
        vendor: 'copilot',
        family: request.model || 'gpt-4.1',
    });
    
    if (models.length === 0) {
        return { text: '', input_tokens: 0, output_tokens: 0 };
    }
    
    const model = models[0];
    const messages = [
        vscode.LanguageModelChatMessage.User(request.prompt),
    ];
    
    if (request.system_prompt) {
        messages.unshift(
            vscode.LanguageModelChatMessage.User(
                `[System] ${request.system_prompt}`
            ),
        );
    }
    
    const response = await model.sendRequest(messages, {}, token);
    
    let text = '';
    for await (const chunk of response.text) {
        text += chunk;
    }
    
    return {
        text,
        input_tokens: request.prompt.length / 4,  // Approximate
        output_tokens: text.length / 4,
    };
}
```

---

## Integration Points — Detailed Wiring

### Where Adapters Get Called

| Caller Module | Adapter Called | Method | Context |
|--------------|---------------|--------|---------|
| `ingestion_orchestrator` | `embedder.embed_and_store()` | Store document chunks | After section splitting |
| `ingestion_orchestrator` | `graph_builder.build_graph()` | Build deal graph | After extraction |
| `governing_doc_generator` | `vector_search.vector_search()` | Find waterfall rules | During generation |
| `model_creation_agent` | `vector_search.search_waterfall_rules()` | Get deal rules | Before model gen |
| `model_creation_agent` | `embedder.embed_query()` | Similarity check | Validation |
| `qa_agent` | `vector_search.vector_search()` | Answer questions | Every query |
| `audit_agent` | `vector_search.vector_search()` | Find discrepancies | Audit run |
| `knowledge_store` | `embedder.embed()` | Build term index | Concept vocab |
| `knowledge_store` | `graph_builder.get_neighbors()` | Related terms | Term expansion |
| `deal_analyzer` | `graph_builder.load_graph()` | Analyze structure | Deal overview |
| `deal_analyzer` | `vector_search.vector_search()` | Find key sections | Analysis |
| `structured_extractor` | `embedder.embed()` | Classify items | Extraction |

### Initialization Flow

```python
# In CLI command handler (e.g., abs-qa):

def handle_abs_qa(deal_id: str, query: str, config: KTSConfig):
    """Full initialization flow for an ABS Q&A session."""
    
    # 1. Create LLM callable
    from backend.abs.llm_bridge import create_llm_callable
    llm = create_llm_callable(
        mode=config.abs_llm_mode,
        model=config.abs_llm_model,
    )
    
    # 2. Create deal scope
    from backend.abs.agents.deal_scope import DealScope
    scope = DealScope(deal_id=deal_id, config=config)
    
    # 3. Create QA agent with all dependencies
    from backend.abs.agents.qa_agent import QAAgent
    agent = QAAgent(
        config=config,
        deal_scope=scope,
        llm_callable=llm,
    )
    
    # 4. Execute — agent internally calls vector_search adapter with llm_callable
    result = agent.execute(task=query)
    
    # 5. Quality gate evaluation happens inside AgentBase.execute()
    return result
```
