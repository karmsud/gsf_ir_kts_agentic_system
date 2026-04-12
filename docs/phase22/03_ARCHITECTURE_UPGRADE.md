# Phase 22: Architecture Upgrade
## Infrastructure Replacement & LLM Integration Details

**Document Version:** 1.0  
**Date:** February 26, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** Stub replacement, adapter implementation, LLM wiring

---

## Table of Contents
1. [Transformation Summary](#transformation-summary)
2. [Transformation 1: Embedder Stub → EmbeddingProvider](#transformation-1-embedder)
3. [Transformation 2: Graph Stub → EnhancedGraphBuilder](#transformation-2-graph)
4. [Transformation 3: Vector Search Stub → RetrievalService](#transformation-3-vector-search)
5. [Transformation 4: LLM Bridge Module](#transformation-4-llm-bridge)
6. [Transformation 5: ABS Agent LLM Wiring](#transformation-5-agent-wiring)
7. [Transformation 6: ABS-Specific Retrieval Pipeline Configuration](#transformation-6-retrieval-config)
8. [Transformation 7: ABS Graph Schema in KTS Graph](#transformation-7-graph-schema)
9. [API Mismatch Resolution](#api-mismatch-resolution)
10. [Backward Compatibility](#backward-compatibility)

---

## Transformation Summary

| # | Transformation | Files Changed | Lines Changed | Risk |
|---|---------------|---------------|---------------|------|
| 1 | Embedder stub → adapter | 1 replaced, 1 new adapter | ~80 → ~120 | 🟢 Low |
| 2 | Graph stub → adapter | 1 replaced, 1 new adapter | ~60 → ~100 | 🟡 Medium |
| 3 | Vector search stub → adapter | 1 replaced, 1 new adapter | ~50 → ~130 | 🟡 Medium |
| 4 | LLM bridge module | 1 new file | ~180 new | 🟡 Medium |
| 5 | ABS agent LLM wiring | 13 agent files modified | ~50 lines each | 🟡 Medium |
| 6 | Retrieval pipeline config | 2 modified | ~40 new | 🟢 Low |
| 7 | ABS graph schema | 2 modified, 1 new | ~200 new | 🟢 Low |
| **Total** | | **~22 files** | **~1,200 lines** | **🟡 Medium** |

---

## Transformation 1: Embedder Stub → EmbeddingProvider

### Before (Phase 21 Stub)

```python
# backend/abs/skills/embedder.py — STUB
def embed(texts: list[str], config) -> list[list[float]]:
    raise NotImplementedError("Stub: will be replaced in Phase 22")
```

### After (Phase 22 Adapter)

```python
# backend/abs/skills/embedder.py — ADAPTER
from backend.vector.embedding_provider import EmbeddingProvider
from config.settings import KTSConfig

_provider_cache: dict[str, EmbeddingProvider] = {}

def _get_provider(config: KTSConfig) -> EmbeddingProvider:
    """Singleton provider per config hash."""
    key = config.abs_embedding_model_path or "default"
    if key not in _provider_cache:
        _provider_cache[key] = EmbeddingProvider(config)
    return _provider_cache[key]

def embed(texts: list[str], config: KTSConfig) -> list[list[float]]:
    """Embed texts using KTS's BGE ONNX INT8 provider.
    
    API bridge: PayGen called embed(texts) with config.
    KTS EmbeddingProvider.embed_documents(texts) returns list[list[float]].
    Same signature — direct delegation.
    """
    provider = _get_provider(config)
    return provider.embed_documents(texts)

def chunk_text(text: str, max_chars: int = 3000, overlap: int = 500) -> list[str]:
    """Chunk text for embedding. Delegates to KTS's legal chunker."""
    from backend.vector.legal_chunker import LegalChunker
    chunker = LegalChunker(max_chars=max_chars, overlap=overlap)
    return chunker.chunk(text)

def embed_and_store(
    texts: list[str],
    metadatas: list[dict],
    collection_name: str,
    config: KTSConfig,
) -> int:
    """Embed texts and store in ChromaDB. Returns count stored."""
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
    return len(texts)
```

### API Mismatch Analysis

| Aspect | PayGen (caller) | KTS (provider) | Resolution |
|--------|----------------|----------------|------------|
| Function | `embed(texts, config)` | `provider.embed_documents(texts)` | Adapter wraps |
| Return | `list[list[float]]` | `list[list[float]]` | **Same** |
| Model | BGE ONNX INT8 768-dim | BGE ONNX INT8 768-dim | **Same** |
| Chunker | Simple char-split | LegalChunker (heading-aware) | **Upgrade** — KTS's is better |

---

## Transformation 2: Graph Stub → EnhancedGraphBuilder

### Before (Phase 21 Stub)

```python
# backend/abs/skills/graph_builder.py — STUB
def build_graph(sections, config) -> None:
    raise NotImplementedError("Stub: will be replaced in Phase 22")
```

### After (Phase 22 Adapter)

```python
# backend/abs/skills/graph_builder.py — ADAPTER
import networkx as nx
from pathlib import Path
from typing import Optional

from backend.graph.enhanced_graph_builder import EnhancedGraphBuilder
from backend.graph.knowledge_graph import KnowledgeGraph
from config.settings import KTSConfig

# ABS node types (extends KTS's 14 standard types)
ABS_NODE_TYPES = {
    "abs_deal", "abs_document", "abs_article", "abs_section",
    "abs_definition", "abs_obligation", "abs_waterfall_rule",
    "abs_class", "abs_account", "abs_trigger",
}

ABS_EDGE_TYPES = {
    "HAS_DOCUMENT", "HAS_ARTICLE", "HAS_SECTION",
    "DEFINES", "HAS_OBLIGATION", "HAS_RULE",
    "REFERENCES", "USES_TERM", "APPLIES_TO", "TRIGGERS",
}


def build_graph(sections: list[dict], config: KTSConfig) -> nx.DiGraph:
    """Build ABS-specific knowledge graph using KTS infrastructure.
    
    API bridge:
    - PayGen passed flat section list with string labels
    - KTS EnhancedGraphBuilder expects typed sections with metadata
    - Adapter normalizes PayGen format to KTS schema
    """
    builder = EnhancedGraphBuilder(config)
    
    # Transform PayGen section format to KTS expected format
    kts_sections = _transform_sections(sections)
    graph = builder.build_from_sections(kts_sections)
    
    # Add ABS-specific node attributes
    for node_id, data in graph.nodes(data=True):
        if data.get("node_type", "").startswith("abs_"):
            data["abs_domain"] = True
    
    # Compute PageRank if enabled
    if config.abs_graph_pagerank_enabled:
        _compute_pagerank(graph)
    
    return graph


def _transform_sections(sections: list[dict]) -> list[dict]:
    """Transform PayGen section format to KTS format.
    
    PayGen format:
    {
        "section_id": "5.02",
        "title": "Establishment of Accounts",
        "text": "...",
        "article": "V",
        "items": [...]
    }
    
    KTS format:
    {
        "id": "...",
        "node_type": "section",
        "content": "...",
        "metadata": {...},
        "children": [...]
    }
    """
    kts_sections = []
    for s in sections:
        kts_sections.append({
            "id": f"abs_section_{s.get('section_id', '')}",
            "node_type": "abs_section",
            "content": s.get("text", ""),
            "metadata": {
                "section_id": s.get("section_id"),
                "title": s.get("title"),
                "article": s.get("article"),
            },
            "children": [
                {
                    "id": f"abs_item_{i}_{s.get('section_id', '')}",
                    "node_type": _classify_item(item),
                    "content": item.get("text", ""),
                    "metadata": item,
                }
                for i, item in enumerate(s.get("items", []))
            ],
        })
    return kts_sections


def _classify_item(item: dict) -> str:
    """Classify extracted item into ABS node type."""
    item_type = item.get("type", "").lower()
    type_map = {
        "definition": "abs_definition",
        "obligation": "abs_obligation",
        "rule": "abs_waterfall_rule",
        "account": "abs_account",
        "trigger": "abs_trigger",
    }
    return type_map.get(item_type, "abs_obligation")


def _compute_pagerank(graph: nx.DiGraph) -> None:
    """Add PageRank scores to all nodes."""
    try:
        ranks = nx.pagerank(graph, alpha=0.85, max_iter=100)
        for node_id, score in ranks.items():
            graph.nodes[node_id]["pagerank"] = score
    except nx.NetworkXError:
        pass  # Empty or disconnected graph


def save_graph(graph: nx.DiGraph, path: Path) -> None:
    """Save graph to GraphML."""
    path.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(graph, str(path))


def load_graph(path: Path) -> Optional[nx.DiGraph]:
    """Load graph from GraphML."""
    if path.exists():
        return nx.read_graphml(str(path))
    return None
```

### API Mismatch Analysis

| Aspect | PayGen (caller) | KTS (provider) | Resolution |
|--------|----------------|----------------|------------|
| Input | `list[dict]` flat sections | `list[dict]` typed sections | `_transform_sections()` adapter |
| Graph type | `nx.DiGraph` (7 node types) | `nx.DiGraph` (14+ node types) | **Superset** — add 10 ABS types |
| PageRank | Not used | Integral (weight 0.2) | **Upgrade** — now available |
| Persistence | `write_graphml` | `write_graphml` | **Same** |

---

## Transformation 3: Vector Search Stub → RetrievalService

### Before (Phase 21 Stub)

```python
# backend/abs/skills/vector_search.py — STUB
def vector_search(query, config, **kwargs) -> list:
    raise NotImplementedError("Stub: will be replaced in Phase 22")
```

### After (Phase 22 Adapter)

```python
# backend/abs/skills/vector_search.py — ADAPTER
from dataclasses import dataclass
from typing import Optional, Protocol

from backend.retrieval.retrieval_service import RetrievalService
from backend.retrieval.retrieval_result import RetrievalResult
from config.settings import KTSConfig


@dataclass
class SearchResult:
    """ABS search result — maps from KTS RetrievalResult."""
    text: str
    score: float
    metadata: dict
    source: str = ""
    section: str = ""
    confidence: float = 0.0
    evidence_chain: list[str] = None
    
    def __post_init__(self):
        if self.evidence_chain is None:
            self.evidence_chain = []


_service_cache: dict[str, RetrievalService] = {}


def _get_service(config: KTSConfig) -> RetrievalService:
    """Singleton retrieval service."""
    key = id(config)
    if key not in _service_cache:
        _service_cache[key] = RetrievalService(config)
    return _service_cache[key]


def vector_search(
    query: str,
    config: KTSConfig,
    collection_name: Optional[str] = None,
    max_results: int = 10,
    llm_callable: Optional[callable] = None,
    **kwargs,
) -> list[SearchResult]:
    """Search using KTS's full retrieval pipeline.
    
    API bridge:
    - PayGen called simple vector_search(query) → list[dict]
    - KTS RetrievalService.search() returns RetrievalResult objects
    - Adapter maps RetrievalResult → SearchResult for PayGen consumers
    
    LLM Integration:
    - If llm_callable provided, enables advanced retrieval features:
      - Multi-query expansion (generates 8 query variants)
      - HyDE (hypothetical document embedding)
      - CRAG (corrective retrieval augmented generation)
      - Critique loop (iterative refinement)
    - If None, uses basic vector+BM25 hybrid search (still very good)
    """
    service = _get_service(config)
    
    # Configure retrieval features based on LLM availability
    search_kwargs = {
        "query": query,
        "max_results": max_results,
        "collection_filter": collection_name,
    }
    
    if llm_callable is not None:
        search_kwargs["llm_callable"] = llm_callable
        search_kwargs["enable_multi_query"] = config.abs_multi_query_enabled
        search_kwargs["enable_hyde"] = config.abs_hyde_enabled
        search_kwargs["enable_crag"] = config.abs_crag_enabled
        search_kwargs["enable_critique"] = config.abs_critique_enabled
    else:
        search_kwargs["enable_multi_query"] = False
        search_kwargs["enable_hyde"] = False
        search_kwargs["enable_crag"] = False
        search_kwargs["enable_critique"] = False
    
    results = service.search(**search_kwargs, **kwargs)
    
    return [_map_result(r) for r in results]


def _map_result(r: RetrievalResult) -> SearchResult:
    """Map KTS RetrievalResult to ABS SearchResult."""
    return SearchResult(
        text=r.content,
        score=r.confidence,
        metadata=r.metadata,
        source=getattr(r, 'source', ''),
        section=r.metadata.get('section', ''),
        confidence=r.confidence,
        evidence_chain=getattr(r, 'evidence_chain', []),
    )


def search_by_section(
    section_id: str,
    config: KTSConfig,
    collection_name: Optional[str] = None,
) -> list[SearchResult]:
    """Search for content in a specific section."""
    return vector_search(
        query=f"section:{section_id}",
        config=config,
        collection_name=collection_name,
    )


def semantic_similarity(
    query: str,
    texts: list[str],
    config: KTSConfig,
) -> list[float]:
    """Compute semantic similarity between query and texts.
    
    Uses KTS's EmbeddingProvider for encoding, then cosine similarity.
    """
    from backend.vector.embedding_provider import EmbeddingProvider
    import numpy as np
    
    provider = EmbeddingProvider(config)
    query_vec = provider.embed_documents([query])[0]
    text_vecs = provider.embed_documents(texts)
    
    # Cosine similarity
    query_norm = np.linalg.norm(query_vec)
    scores = []
    for tv in text_vecs:
        tv_norm = np.linalg.norm(tv)
        if query_norm == 0 or tv_norm == 0:
            scores.append(0.0)
        else:
            scores.append(float(np.dot(query_vec, tv) / (query_norm * tv_norm)))
    return scores
```

---

## Transformation 4: LLM Bridge Module

### New File: `backend/abs/llm_bridge.py`

```python
"""
LLM Bridge — Injectable LLM callable factory.

Responsibilities:
1. Create LLM callables for different runtime environments
2. Handle IPC with VS Code extension (primary mode)
3. Provide mock callables for testing
4. Track token usage and latency

Architecture:
    VS Code Extension
         ↓ (subprocess + stdin/stdout IPC)
    Python CLI
         ↓ (creates callable)
    LLM Bridge
         ↓ (callable)
    ABS Agents
"""

import json
import sys
import time
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMUsageStats:
    """Track LLM usage across a session."""
    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_latency_ms: float = 0.0
    errors: int = 0
    call_log: list[dict] = field(default_factory=list)
    
    def record(self, input_tokens: int, output_tokens: int, latency_ms: float):
        self.total_calls += 1
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_latency_ms += latency_ms
    
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / max(self.total_calls, 1)


# Global usage tracker
_usage = LLMUsageStats()


LLMCallable = Callable[[str, Optional[str]], str]


def create_llm_callable(
    mode: str = "none",
    model: str = "gpt-4.1",
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> Optional[LLMCallable]:
    """Factory for LLM callables.
    
    Args:
        mode: "vscode" | "mock" | "none"
        model: Model identifier (used in vscode mode)
        temperature: Default temperature
        max_tokens: Default max tokens
        
    Returns:
        LLMCallable or None if mode="none"
    """
    if mode == "vscode":
        return _create_vscode_callable(model, temperature, max_tokens)
    elif mode == "mock":
        return _create_mock_callable()
    elif mode == "none":
        return None
    else:
        logger.warning(f"Unknown LLM mode: {mode}, returning None")
        return None


def get_usage_stats() -> LLMUsageStats:
    """Get global LLM usage statistics."""
    return _usage


def _create_vscode_callable(
    model: str,
    temperature: float,
    max_tokens: int,
) -> LLMCallable:
    """Create callable that communicates with VS Code extension via IPC.
    
    Protocol:
    1. Write JSON request to stdout (one line)
    2. Read JSON response from stdin (one line)
    3. Response contains "text" field with LLM output
    """
    def call_llm(prompt: str, system_prompt: Optional[str] = None) -> str:
        global _usage
        start = time.time()
        
        request = {
            "type": "llm_request",
            "model": model,
            "prompt": prompt,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        try:
            # Send request
            sys.stdout.write(json.dumps(request) + "\n")
            sys.stdout.flush()
            
            # Read response
            response_line = sys.stdin.readline()
            if not response_line:
                _usage.errors += 1
                return ""
            
            response = json.loads(response_line)
            text = response.get("text", "")
            
            # Track usage
            latency = (time.time() - start) * 1000
            _usage.record(
                input_tokens=response.get("input_tokens", len(prompt) // 4),
                output_tokens=response.get("output_tokens", len(text) // 4),
                latency_ms=latency,
            )
            
            return text
            
        except Exception as e:
            _usage.errors += 1
            logger.error(f"LLM call failed: {e}")
            return ""
    
    return call_llm


def _create_mock_callable() -> LLMCallable:
    """Mock callable for testing.
    
    Returns deterministic responses based on prompt content.
    Useful for unit tests and CI/CD pipelines.
    """
    def mock_llm(prompt: str, system_prompt: Optional[str] = None) -> str:
        global _usage
        _usage.record(input_tokens=len(prompt) // 4, output_tokens=50, latency_ms=1.0)
        
        prompt_lower = prompt.lower()
        
        # Payment model generation
        if "payment model" in prompt_lower or "waterfall" in prompt_lower:
            return (
                "def calculate_distribution(deal_data, period):\n"
                "    '''Mock distribution waterfall.'''\n"
                "    available = deal_data['available_funds']\n"
                "    distributions = {}\n"
                "    # Step 1: Trustee fees\n"
                "    trustee_fee = min(available, deal_data['trustee_fee'])\n"
                "    distributions['trustee'] = trustee_fee\n"
                "    available -= trustee_fee\n"
                "    return distributions\n"
            )
        
        # Q&A
        elif "question" in prompt_lower or "query" in prompt_lower:
            return (
                "Based on Section 5.02 of the PSA, the Trustee shall establish "
                "and maintain the Distribution Account for the benefit of "
                "Certificateholders. Distributions shall be made on each "
                "Distribution Date in accordance with the priority of payments "
                "set forth in Section 5.04."
            )
        
        # Multi-query expansion
        elif "generate" in prompt_lower and "queries" in prompt_lower:
            return json.dumps([
                "distribution waterfall payment priority",
                "trustee responsibilities distribution account",
                "certificateholder payment schedule",
                "overcollateralization trigger events",
            ])
        
        # Governing doc generation
        elif "governing" in prompt_lower:
            return (
                "# Distribution Waterfall\n\n"
                "## Priority of Payments\n\n"
                "1. Trustee Fee\n"
                "2. Servicer Fee\n"
                "3. Class A Interest\n"
                "4. Class A Principal\n"
                "5. Class B Interest\n"
            )
        
        # CRAG verification
        elif "verify" in prompt_lower or "claim" in prompt_lower:
            return json.dumps({
                "verified": True,
                "confidence": 0.92,
                "evidence": "Section 5.02 confirms...",
            })
        
        # Default
        else:
            return f"Mock LLM response for: {prompt[:80]}..."
    
    return mock_llm
```

---

## Transformation 5: ABS Agent LLM Wiring

### Pattern: Add `llm_callable` to All 13 ABS Agents

Each of the 13 ABS agents receives `llm_callable` via constructor injection.

**Before (PayGen — no LLM):**

```python
class GoverningDocGenerator(AgentBase):
    def __init__(self, config, deal_scope):
        super().__init__(name="governing_doc_generator", config=config)
        self.deal_scope = deal_scope
    
    def _run(self, task):
        # Template-based only
        return self._generate_from_template(task)
```

**After (Phase 22 — LLM-enhanced):**

```python
class GoverningDocGenerator(AgentBase):
    def __init__(
        self,
        config: KTSConfig,
        deal_scope: DealScope,
        llm_callable: Optional[LLMCallable] = None,
    ):
        super().__init__(
            name="governing_doc_generator",
            config=config,
            llm_callable=llm_callable,
        )
        self.deal_scope = deal_scope
    
    def _run(self, task):
        if self._llm:
            return self._generate_with_llm(task)
        else:
            return self._generate_from_template(task)
    
    def _generate_with_llm(self, task):
        """LLM-powered generation with quality gate."""
        prompt = self._build_prompt(task)
        system = (
            "You are an ABS payment model engineer specializing in "
            "Pooling and Servicing Agreements. Generate a governing "
            "document section based on the extracted PSA data."
        )
        response = self._llm(prompt, system)
        return self._parse_and_validate(response)
```

### All 17 ABS LLM Call Sites

| # | Agent/Module | Purpose | System Prompt Theme | Tier |
|---|-------------|---------|-------------------|------|
| 1 | `governing_doc_generator` | Generate waterfall rules | ABS payment engineer | Background |
| 2 | `governing_doc_generator` | Section consolidation | Legal doc merger | Background |
| 3 | `knowledge_store` | Concept vocabulary build | ABS terminology | Background |
| 4 | `knowledge_store` | Term disambiguation | Financial lexicon | Background |
| 5 | `model_creation_agent` | Python model generation | Python ABS engineer | User-visible |
| 6 | `model_creation_agent` | Error refinement loop | Debug assistant | Background |
| 7 | `model_creation_agent` | Model validation | QA engineer | Background |
| 8 | `qa_agent` | Answer user questions | ABS analyst | User-visible |
| 9 | `qa_agent` | Follow-up generation | Socratic questioner | Background |
| 10 | `structured_extractor` | Entity extraction | Legal data extractor | Background |
| 11 | `structured_extractor` | Relationship mapping | Knowledge graph | Background |
| 12 | `audit_agent` | Model audit report | ABS auditor | User-visible |
| 13 | `audit_agent` | Discrepancy analysis | Financial analyst | Background |
| 14 | `data_prep` | Data normalization | Data engineer | Background |
| 15 | `deal_analyzer` | Deal structure analysis | Structured finance | User-visible |
| 16 | `ingestion_orchestrator` | Section classification | Document classifier | Background |
| 17 | `pipeline_coordinator` | Status summarization | Project manager | User-visible |

### 15 KTS-Side LLM Call Sites (Inherited)

These already exist in KTS and gain ABS content through the retrieval pipeline:

| # | KTS Module | Purpose | Already Wired? |
|---|-----------|---------|----------------|
| 1 | CRAG verifier | Claim verification | ✅ Yes |
| 2 | Critique loop | Answer refinement | ✅ Yes |
| 3 | Multi-query generator | Query expansion | ✅ Yes |
| 4 | HyDE generator | Hypothetical docs | ✅ Yes |
| 5 | Concept vocab builder | Term extraction | ✅ Yes |
| 6 | Query router | Scope resolution | ✅ Yes |
| 7 | Answer synthesizer | Final answer | ✅ Yes |
| 8 | Context summarizer | Context compression | ✅ Yes |
| 9 | Follow-up generator | Question chaining | ✅ Yes |
| 10 | Reranker (neural) | Cross-encoder rerank | ✅ Yes (model) |
| 11 | Classification agent | Document classifier | ✅ Yes |
| 12 | Generation agent | Content generation | ✅ Yes |
| 13 | Analysis agent | Pattern analysis | ✅ Yes |
| 14 | Extraction agent | Data extraction | ✅ Yes |
| 15 | Orchestrator agent | Pipeline coordination | ✅ Yes |

---

## Transformation 6: ABS-Specific Retrieval Pipeline Configuration

### ABS Retrieval Profile

ABS documents have unique characteristics that require tuned retrieval parameters:

```python
# backend/abs/config/retrieval_profile.py

"""
ABS-specific retrieval profile — optimized for legal PSA/Indenture documents.

Key differences from KTS defaults:
1. Longer context windows (legal clauses are verbose)
2. Higher BM25 weight (legal terms are precise, not fuzzy)
3. More aggressive graph expansion (legal cross-references matter)
4. Tighter CRAG verification (financial accuracy is critical)
"""

ABS_RETRIEVAL_PROFILE = {
    # Chunking
    "chunk_max_chars": 4000,          # KTS default: 3000 (legal sections are longer)
    "chunk_overlap": 800,             # KTS default: 500
    
    # Hybrid search weights
    "bm25_weight": 0.5,              # KTS default: 0.4 (legal terms are precise)
    "vector_weight": 0.5,            # KTS default: 0.6
    "rrf_k": 60,                     # Same as KTS
    
    # Graph expansion
    "graph_bfs_depth": 5,            # KTS default: 4 (cross-references run deep)
    "graph_pagerank_weight": 0.25,   # KTS default: 0.2 (important sections matter more)
    
    # Reranking weights
    "rerank_content_weight": 0.5,    # KTS default: 0.6
    "rerank_pagerank_weight": 0.25,  # KTS default: 0.2
    "rerank_graph_weight": 0.25,     # KTS default: 0.2
    
    # CRAG
    "crag_confidence_threshold": 0.85,  # KTS default: 0.80 (financial accuracy)
    
    # Critique
    "critique_max_rounds": 3,        # KTS default: 5 (faster for deal analysis)
    "critique_target_confidence": 0.92,  # KTS default: 0.90
    
    # Multi-query
    "multi_query_count": 6,          # KTS default: 8 (legal queries are more focused)
}
```

---

## Transformation 7: ABS Graph Schema in KTS Graph

### Registration of ABS Node/Edge Types

```python
# backend/abs/config/graph_schema.py

"""
ABS graph schema — registers ABS-specific node and edge types
with KTS's graph infrastructure.
"""

from backend.graph.enhanced_graph_builder import NodeType, EdgeType

# Register ABS node types
ABS_NODE_TYPES = [
    NodeType(
        name="abs_deal",
        description="ABS deal entity (e.g., Bear Stearns 2006-HE1)",
        properties=["deal_id", "issuer", "series", "closing_date"],
        is_root=True,
    ),
    NodeType(
        name="abs_document",
        description="Legal document (PSA, Indenture, Supplement)",
        properties=["doc_type", "content_hash", "filename", "page_count"],
    ),
    NodeType(
        name="abs_article",
        description="Article within a legal document",
        properties=["article_num", "title", "text_preview"],
    ),
    NodeType(
        name="abs_section",
        description="Section within an article",
        properties=["section_num", "parent_article", "title", "text"],
    ),
    NodeType(
        name="abs_definition",
        description="Defined term within the agreement",
        properties=["term", "full_text", "section_ref"],
    ),
    NodeType(
        name="abs_obligation",
        description="Obligation or duty described in the agreement",
        properties=["actor", "verb", "full_text", "section_ref"],
    ),
    NodeType(
        name="abs_waterfall_rule",
        description="Payment waterfall priority rule",
        properties=["priority", "payee", "formula", "conditions"],
    ),
    NodeType(
        name="abs_class",
        description="Certificate/note class in the deal",
        properties=["class_name", "initial_balance", "rate_type"],
    ),
    NodeType(
        name="abs_account",
        description="Deal account (e.g., Distribution Account)",
        properties=["account_name", "purpose", "section_ref"],
    ),
    NodeType(
        name="abs_trigger",
        description="Performance trigger or event of default",
        properties=["trigger_type", "threshold", "consequence"],
    ),
]

# Register ABS edge types
ABS_EDGE_TYPES = [
    EdgeType("HAS_DOCUMENT", "abs_deal", "abs_document", weight=1.0),
    EdgeType("HAS_ARTICLE", "abs_document", "abs_article", weight=1.0),
    EdgeType("HAS_SECTION", "abs_article", "abs_section", weight=1.0),
    EdgeType("DEFINES", "abs_section", "abs_definition", weight=0.9),
    EdgeType("HAS_OBLIGATION", "abs_section", "abs_obligation", weight=0.9),
    EdgeType("HAS_RULE", "abs_section", "abs_waterfall_rule", weight=0.95),
    EdgeType("REFERENCES", "abs_section", "abs_section", weight=0.7),
    EdgeType("USES_TERM", "abs_obligation", "abs_definition", weight=0.8),
    EdgeType("APPLIES_TO", "abs_waterfall_rule", "abs_class", weight=0.9),
    EdgeType("TRIGGERS", "abs_trigger", "abs_waterfall_rule", weight=0.85),
]
```

---

## API Mismatch Resolution — Complete Map

| Call Site | PayGen API | KTS API | Resolution | Effort |
|-----------|-----------|---------|------------|--------|
| `embed(texts)` | `embed(list, config)` → `list[list[float]]` | `provider.embed_documents(list)` → `list[list[float]]` | Direct delegation | 🟢 5 min |
| `chunk_text(text)` | `chunk_text(str, max_chars, overlap)` → `list[str]` | `LegalChunker.chunk(str)` → `list[str]` | Adapter + KTS upgrade | 🟢 10 min |
| `build_graph(sections)` | `build_graph(list[dict], config)` → `nx.DiGraph` | `builder.build_from_sections(list[dict])` → `nx.DiGraph` | `_transform_sections()` adapter | 🟡 30 min |
| `vector_search(query)` | `vector_search(str, config, **kw)` → `list[dict]` | `service.search(str, **kw)` → `list[RetrievalResult]` | `_map_result()` adapter | 🟡 30 min |
| `save_graph(graph)` | `save_graph(nx.DiGraph, Path)` | `nx.write_graphml()` | Same | 🟢 0 min |
| `load_graph(path)` | `load_graph(Path)` → `Optional[nx.DiGraph]` | `nx.read_graphml()` | Same | 🟢 0 min |

---

## Backward Compatibility

### KTS Guarantees

1. **No existing KTS test breaks** — ABS adapters are additive, not modifying
2. **KTS agents unchanged** — Only ABS agents get LLM wiring
3. **KTS config defaults preserved** — All `abs_*` properties have defaults
4. **KTS vector collections untouched** — ABS uses `abs_` prefixed collections
5. **KTS graph nodes untouched** — ABS uses `abs_` prefixed node types

### ABS Guarantees

1. **All 13 agents work without LLM** — `llm_callable=None` falls back to templates
2. **All adapters are thin** — Max 130 lines each, easily debuggable
3. **All transformations are reversible** — Stubs can be swapped back in for isolation testing
