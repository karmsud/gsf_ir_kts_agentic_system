# Phase 22: System Design
## Infrastructure Replacement & LLM Integration Architecture

**Document Version:** 1.0  
**Date:** February 26, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** System-level architecture for infrastructure swap and LLM wiring

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Infrastructure Replacement Architecture](#infrastructure-replacement-architecture)
3. [LLM Integration Architecture](#llm-integration-architecture)
4. [Data Flow — ABS Ingestion with KTS Infrastructure](#data-flow-abs-ingestion)
5. [Data Flow — ABS Retrieval with KTS Pipeline](#data-flow-abs-retrieval)
6. [Data Flow — LLM-Powered Model Generation](#data-flow-model-generation)
7. [Adapter Layer Design](#adapter-layer-design)
8. [ABS-Specific Graph Schema](#abs-specific-graph-schema)
9. [ABS-Specific Vector Collections](#abs-specific-vector-collections)
10. [Configuration Integration](#configuration-integration)

---

## Architecture Overview

### Design Principles

1. **Adapter pattern** — ABS modules call thin adapter functions that delegate to KTS infrastructure. This keeps ABS code clean and decoupled.
2. **LLM dependency injection** — All LLM calls use `llm_callable: Optional[Callable]`. When `None`, agents fall back to template-based behavior.
3. **Namespace isolation** — ABS vector collections use `abs_` prefix. ABS graph nodes use `abs_` namespace. No collision with KTS data.
4. **Feature flags** — Each infrastructure integration is toggleable via `abs_*` config properties.

---

## Infrastructure Replacement Architecture

### Before Phase 22 (Stubs)

```
backend/abs/skills/embedder.py       → NotImplementedError
backend/abs/skills/graph_builder.py  → NotImplementedError
backend/abs/skills/vector_search.py  → NotImplementedError
```

### After Phase 22 (Adapters)

```
backend/abs/skills/embedder.py       → Adapter → backend/vector/embedding_provider.py
backend/abs/skills/graph_builder.py  → Adapter → backend/graph/enhanced_graph_builder.py
backend/abs/skills/vector_search.py  → Adapter → backend/retrieval/retrieval_service.py
```

### Adapter Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                ABS Domain Modules                              │
│                                                                │
│  governing_doc_generator.py                                   │
│  knowledge_store.py              ┌─────────────────────────┐  │
│  model_creation_agent.py    ───► │   ABS Adapter Layer     │  │
│  qa_agent.py                     │                         │  │
│  structured_extractor.py         │  embedder_adapter.py    │  │
│                                  │  graph_adapter.py       │  │
│                                  │  retrieval_adapter.py   │  │
│                                  └──────────┬──────────────┘  │
└─────────────────────────────────────────────┼─────────────────┘
                                              │
┌─────────────────────────────────────────────┼─────────────────┐
│               KTS Infrastructure                               │
│                                              │                  │
│  ┌───────────────────┐  ┌───────────────────▼──────────────┐  │
│  │ EmbeddingProvider │  │ RetrievalService (2,714 lines)   │  │
│  │ BGE ONNX INT8     │  │ 31 retrieval modules             │  │
│  │ 768-dim            │  │ BM25 + HyDE + CRAG + critique   │  │
│  └───────────────────┘  └──────────────────────────────────┘  │
│                                                                │
│  ┌───────────────────┐  ┌──────────────────────────────────┐  │
│  │ DualVectorStore   │  │ EnhancedGraphBuilder             │  │
│  │ Items + Sections  │  │ 14 node types, PageRank          │  │
│  └───────────────────┘  └──────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

---

## LLM Integration Architecture

### Dependency Injection Flow

```
┌──────────────────────────────────────────────────────────┐
│                VS Code Extension                          │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │            @abs Chat Participant                     │ │
│  │                                                      │ │
│  │  1. User sends message                               │ │
│  │  2. Select LLM model (user pref or gpt-4.1)         │ │
│  │  3. Create llm_callable wrapper                      │ │
│  │  4. Pass to Python backend via CLI args/stdin        │ │
│  └───────────────────────┬─────────────────────────────┘ │
└──────────────────────────┼───────────────────────────────┘
                           │ subprocess call with --llm-mode
                           ▼
┌──────────────────────────────────────────────────────────┐
│                  CLI / Python Backend                      │
│                                                           │
│  abs-qa --deal-id bear_2006_he1 --query "..." --llm-mode │
│                                                           │
│  ┌────────────────────────────────────────────────────┐  │
│  │              LLM Bridge Module                      │  │
│  │                                                     │  │
│  │  def create_llm_callable(mode: str) -> LLMCallable  │  │
│  │                                                     │  │
│  │  mode="vscode"  → stdin/stdout IPC to extension     │  │
│  │  mode="openai"  → direct OpenAI API (future)        │  │
│  │  mode="mock"    → deterministic test responses      │  │
│  │  mode="none"    → return None (template fallback)   │  │
│  └────────────────────────┬───────────────────────────┘  │
│                           │                               │
│  ┌────────────────────────▼───────────────────────────┐  │
│  │              ABS Agent                              │  │
│  │                                                     │  │
│  │  def __init__(self, ..., llm_callable=None):        │  │
│  │      self._llm = llm_callable                       │  │
│  │                                                     │  │
│  │  def _run(self, task):                              │  │
│  │      if self._llm:                                  │  │
│  │          return self._llm(prompt, system)           │  │
│  │      else:                                          │  │
│  │          return self._template_fallback(task)        │  │
│  └─────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### LLMCallable Type Signature

```python
from typing import Callable, Optional, Protocol

class LLMCallable(Protocol):
    def __call__(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str:
        """Send prompt to LLM and return response text."""
        ...
```

### LLM Bridge Module

**File:** `backend/abs/llm_bridge.py`

```python
"""
LLM Bridge — creates llm_callable instances for different backends.

Supports:
- "vscode" mode: IPC with VS Code extension (primary)
- "mock" mode: Deterministic responses for testing
- "none" mode: Returns None (template fallback)
"""

import json
import sys
import logging
from typing import Optional

logger = logging.getLogger(__name__)

LLMCallable = callable  # Callable[[str, Optional[str]], str]


def create_llm_callable(mode: str = "none") -> Optional[LLMCallable]:
    """Factory for LLM callables based on runtime mode."""
    if mode == "vscode":
        return _create_vscode_callable()
    elif mode == "mock":
        return _create_mock_callable()
    elif mode == "none":
        return None
    else:
        logger.warning(f"Unknown LLM mode: {mode}, falling back to None")
        return None


def _create_vscode_callable() -> LLMCallable:
    """IPC-based callable that communicates with VS Code extension."""
    def call_llm(prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        request = {
            "type": "llm_request",
            "prompt": prompt,
            "system_prompt": system_prompt,
            "temperature": kwargs.get("temperature", 0.0),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        sys.stdout.write(json.dumps(request) + "\n")
        sys.stdout.flush()
        response_line = sys.stdin.readline()
        response = json.loads(response_line)
        return response.get("text", "")
    return call_llm


def _create_mock_callable() -> LLMCallable:
    """Mock callable for testing — returns deterministic responses."""
    def mock_llm(prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        if "payment model" in prompt.lower():
            return "# Mock payment model\ndef calculate_payment(): return 0.0"
        elif "question" in prompt.lower() or "query" in prompt.lower():
            return "Mock answer: Based on Section 5.02, the Trustee shall establish..."
        elif "governing" in prompt.lower():
            return "# Mock Governing Document\n## Distribution Waterfall\n..."
        else:
            return f"Mock LLM response for: {prompt[:50]}..."
    return mock_llm
```

---

## Data Flow — ABS Ingestion with KTS Infrastructure

```
PSA/Indenture PDF
        │
        ▼
┌───────────────────┐
│ document_converter│ (abs/ingestion/)
│ PDF → text        │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ section_splitter  │ (abs/ingestion/)
│ Split by Article/ │
│ Section headers   │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐      ┌─────────────────────────────┐
│ structured_       │      │ KTS LegalItemExtractor      │
│ extractor         │─────►│ (backend/extraction/)       │
│                   │      │ Extract items: obligations,  │
│                   │      │ definitions, conditions      │
└───────┬───────────┘      └──────────────┬──────────────┘
        │                                  │
        ▼                                  ▼
┌───────────────────┐      ┌─────────────────────────────┐
│ embedder_adapter  │      │ KTS EmbeddingProvider       │
│ (abs/skills/)     │─────►│ (backend/vector/)           │
│                   │      │ BGE ONNX INT8, 768-dim      │
│ embed_and_store() │      │ embed_documents()           │
└───────┬───────────┘      └──────────────┬──────────────┘
        │                                  │
        ├──────────────┬───────────────────┘
        │              │
        ▼              ▼
┌──────────────┐ ┌───────────────┐
│ ABS Vector   │ │ ABS Section   │
│ Collection   │ │ Collection    │
│ (items)      │ │               │
│ abs_{deal}_  │ │ abs_{deal}_   │
│ items        │ │ sections      │
└──────┬───────┘ └───────┬───────┘
       │                 │
       ▼                 ▼
┌─────────────────────────────────────────┐
│ graph_adapter → EnhancedGraphBuilder    │
│                                          │
│ Document → Section → Item hierarchy     │
│ DEFINES, HAS_RULE, REFERENCES edges    │
│ PageRank computation                     │
└─────────────────────────────────────────┘
        │
        ▼
┌───────────────────┐
│ governing_doc_    │
│ generator         │
│                   │────► LLM (GPT-4.1) for section generation
│ Generate govdocs  │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ DealManifest.save │
│ ingestion_status  │
│ = COMPLETE        │
└───────────────────┘
```

---

## Data Flow — ABS Retrieval with KTS Pipeline

```
User Query: "What is the Distribution Waterfall in Bear Stearns 2006-HE1?"
        │
        ▼
┌───────────────────┐
│ retrieval_adapter │ (abs/skills/)
│                   │
│ Delegates to KTS  │
│ RetrievalService  │
└───────┬───────────┘
        │
        ▼
┌────────────────────────────────────────────────────────┐
│            KTS Retrieval Pipeline (31 modules)          │
│                                                         │
│  1. Query Understanding                                │
│     - Acronym resolution                               │
│     - Term resolution                                  │
│     - Query expansion (LLM: GPT-4.1)                  │
│                                                         │
│  2. Multi-Query RAG (LLM: GPT-4.1)                    │
│     - Generate 8 query variants                        │
│     - Pool results (top 60)                            │
│                                                         │
│  3. Hybrid Search                                       │
│     - BM25 (weight 0.4) + Vector (weight 0.6)         │
│     - RRF fusion (k=60)                                │
│                                                         │
│  4. Graph Expansion                                     │
│     - BFS depth=4 from top hits                        │
│     - PageRank boost (weight 0.2)                      │
│                                                         │
│  5. Cross-Encoder Reranking                            │
│     - Content similarity (weight 0.6)                  │
│     - PageRank centrality (weight 0.2)                 │
│     - Graph proximity (weight 0.2)                     │
│                                                         │
│  6. CRAG Verification (LLM: GPT-4.1)                  │
│     - Extract claims from answer                       │
│     - Verify each claim against evidence               │
│     - Drop contradicted, flag unsupported              │
│                                                         │
│  7. Critique Loop (LLM: GPT-4.1, max 5 rounds)        │
│     - Generate critique questions                      │
│     - Search for additional evidence                   │
│     - Refine answer                                    │
│     - Exit when confidence > 0.90                      │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
                    Final ranked results
                    with confidence score
                    and source citations
```

---

## Data Flow — LLM-Powered Model Generation

```
User: "@abs /generate bear_stearns_2006_he1"
        │
        ▼
┌───────────────────┐
│ ModelCreationAgent │
│ (abs/agents/)      │
│                    │
│ 1. Load DealScope │
│ 2. Load Manifest  │
│ 3. Check ready    │
└───────┬────────────┘
        │
        ▼
┌───────────────────┐
│ data_prep          │ (abs/generation/)
│                    │
│ Load deal_setup,   │
│ class_definitions, │
│ monthly data       │
└───────┬────────────┘
        │
        ▼
┌───────────────────────────────────────────────────┐
│ Retrieval: Get governing docs + waterfall rules    │
│                                                    │
│ retrieval_adapter.search(                          │
│     "distribution waterfall payment rules",        │
│     scope=deal_scope                               │
│ )                                                  │
└───────────────────────┬───────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────┐
│ LLM Generation (GPT-4.1)                          │
│                                                    │
│ System: "You are an ABS payment model engineer..." │
│ Prompt:                                            │
│   - Governing doc text                             │
│   - Waterfall rules                                │
│   - Deal setup (classes, dates, rates)             │
│   - Output format: Python function                 │
│   - Validation rules                               │
│                                                    │
│ → Returns Python code                              │
└───────────────────────┬───────────────────────────┘
        │
        ▼
┌───────────────────┐
│ model_runner       │ (abs/generation/)
│                    │
│ Execute model for  │
│ each payment date  │
│ Collect outputs    │
└───────┬────────────┘
        │
        ▼
┌───────────────────┐
│ model_validator    │ (abs/generation/)
│                    │
│ Compare outputs    │
│ to expected CSV    │
│                    │
│ Tolerance: 0.01   │
└───────┬────────────┘
        │
        ▼
┌───────────────────┐
│ Quality Gate       │
│ 5-dim evaluation   │
│                    │
│ If failed → retry  │
│ with refinement    │
│ prompt + errors    │
└────────────────────┘
```

---

## Adapter Layer Design

### `backend/abs/skills/embedder.py` (Adapter)

```python
"""
Embedder adapter — delegates to KTS EmbeddingProvider.

Replaces the Phase 21 stub with real KTS infrastructure.
Preserves the PayGen function signatures for backward compatibility.
"""

from typing import Optional
from pathlib import Path

from backend.vector.embedding_provider import EmbeddingProvider
from config.settings import KTSConfig


_provider: Optional[EmbeddingProvider] = None


def _get_provider(config: KTSConfig) -> EmbeddingProvider:
    global _provider
    if _provider is None:
        _provider = EmbeddingProvider(config)
    return _provider


def chunk_text(text: str, max_chars: int = 3000, overlap: int = 500) -> list[str]:
    """Split text into overlapping chunks."""
    # Use KTS's legal chunker for ABS documents
    from backend.vector.legal_chunker import LegalChunker
    chunker = LegalChunker(max_chars=max_chars, overlap=overlap)
    return chunker.chunk(text)


def embed(texts: list[str], config: KTSConfig) -> list[list[float]]:
    """Embed texts using KTS's BGE ONNX INT8 provider."""
    provider = _get_provider(config)
    return provider.embed_documents(texts)


def embed_and_store(
    texts: list[str],
    metadatas: list[dict],
    collection_name: str,
    config: KTSConfig,
) -> None:
    """Embed texts and store in ChromaDB via KTS provider."""
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
```

### `backend/abs/skills/graph_builder.py` (Adapter)

```python
"""
Graph builder adapter — delegates to KTS EnhancedGraphBuilder.
"""

import networkx as nx
from pathlib import Path
from typing import Optional

from backend.graph.enhanced_graph_builder import EnhancedGraphBuilder
from config.settings import KTSConfig


def build_graph(sections: list[dict], config: KTSConfig) -> nx.DiGraph:
    """Build graph from extracted sections using KTS's enhanced builder."""
    builder = EnhancedGraphBuilder(config)
    return builder.build_from_sections(sections)


def save_graph(graph: nx.DiGraph, path: Path) -> None:
    """Save graph to GraphML file."""
    nx.write_graphml(graph, str(path))


def load_graph(path: Path) -> Optional[nx.DiGraph]:
    """Load graph from GraphML file."""
    if path.exists():
        return nx.read_graphml(str(path))
    return None


def query_graph(graph: nx.DiGraph, query: str, config: KTSConfig) -> list[dict]:
    """Query graph using KTS's graph-guided retrieval."""
    builder = EnhancedGraphBuilder(config)
    return builder.query(graph, query)
```

### `backend/abs/skills/vector_search.py` (Adapter)

```python
"""
Vector search adapter — delegates to KTS RetrievalService.
"""

from dataclasses import dataclass
from typing import Optional

from backend.retrieval.retrieval_service import RetrievalService
from config.settings import KTSConfig


@dataclass
class SearchResult:
    text: str
    score: float
    metadata: dict
    source: str = ""
    section: str = ""


def vector_search(
    query: str,
    config: KTSConfig,
    collection_name: Optional[str] = None,
    max_results: int = 10,
    **kwargs,
) -> list[SearchResult]:
    """Search using KTS's full retrieval pipeline."""
    service = RetrievalService(config)
    results = service.search(
        query=query,
        max_results=max_results,
        collection_filter=collection_name,
        **kwargs,
    )
    return [
        SearchResult(
            text=r.content,
            score=r.confidence,
            metadata=r.metadata,
            source=r.source,
            section=getattr(r, 'section', ''),
        )
        for r in results
    ]


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
```

---

## ABS-Specific Graph Schema

### Node Types for ABS Domain

ABS ingestion creates these node types in the KTS graph (using `abs_` namespace):

| Node Type | Source | Properties |
|-----------|--------|-----------|
| `abs_deal` | DealManifest | `deal_id, issuer, series, closing_date` |
| `abs_document` | Ingested PSA/Indenture | `doc_type, content_hash, filename` |
| `abs_article` | Section splitter | `article_num, title, text_preview` |
| `abs_section` | Section splitter | `section_num, parent_article, title` |
| `abs_definition` | Structured extractor | `term, full_text, section_ref` |
| `abs_obligation` | Structured extractor | `actor, verb, full_text, section_ref` |
| `abs_waterfall_rule` | Structured extractor | `priority, payee, formula, conditions` |
| `abs_class` | Deal setup | `class_name, initial_balance, rate_type` |
| `abs_account` | Structured extractor | `account_name, purpose, section_ref` |
| `abs_trigger` | Structured extractor | `trigger_type, threshold, consequence` |

### Edge Types

| Edge Type | From → To | Weight |
|-----------|-----------|--------|
| `HAS_DOCUMENT` | abs_deal → abs_document | 1.0 |
| `HAS_ARTICLE` | abs_document → abs_article | 1.0 |
| `HAS_SECTION` | abs_article → abs_section | 1.0 |
| `DEFINES` | abs_section → abs_definition | 0.9 |
| `HAS_OBLIGATION` | abs_section → abs_obligation | 0.9 |
| `HAS_RULE` | abs_section → abs_waterfall_rule | 0.95 |
| `REFERENCES` | abs_section → abs_section | 0.7 |
| `USES_TERM` | abs_obligation → abs_definition | 0.8 |
| `APPLIES_TO` | abs_waterfall_rule → abs_class | 0.9 |
| `TRIGGERS` | abs_trigger → abs_waterfall_rule | 0.85 |

---

## ABS-Specific Vector Collections

### Dual-Store Pattern

Each deal gets two ChromaDB collections (following KTS's dual-store pattern):

| Collection Name | Granularity | Items Per Deal | Content |
|----------------|-------------|----------------|---------|
| `abs_{deal_id}_items` | Sentence-level | 500–2,000 | Individual definitions, obligations, rules |
| `abs_{deal_id}_sections` | Section-level | 50–150 | Full article/section text |

### Metadata Schema

```python
# Item-level metadata
{
    "deal_id": "bear_stearns_2006_he1",
    "doc_type": "PSA",
    "section": "5.02",
    "item_type": "definition",      # definition | obligation | rule | condition
    "actors": ["Trustee"],
    "defined_terms": ["Distribution Account"],
    "source_file": "PSA_2006_HE1.pdf",
    "page_number": 42,
}

# Section-level metadata
{
    "deal_id": "bear_stearns_2006_he1",
    "doc_type": "PSA",
    "article": "V",
    "section": "5.02",
    "title": "Establishment of Accounts",
    "item_count": 15,
    "source_file": "PSA_2006_HE1.pdf",
    "page_range": "40-45",
}
```

---

## Configuration Integration

### Phase 22 Config Additions to KTSConfig

```python
# Add to config/settings.py KTSConfig:

# Phase 22: ABS Infrastructure Integration
abs_llm_mode: str = "none"                    # "vscode" | "mock" | "none"
abs_llm_model: str = "gpt-4.1"               # Model for background tasks
abs_llm_temperature: float = 0.0             # Default temperature
abs_llm_max_tokens: int = 4096              # Default max tokens
abs_use_dual_store: bool = True              # Use dual vector store
abs_use_enhanced_graph: bool = True          # Use enhanced graph builder
abs_use_full_retrieval: bool = True          # Use full retrieval pipeline
abs_retrieval_max_results: int = 10          # Max search results
abs_graph_bfs_depth: int = 4                 # Graph expansion depth
abs_graph_pagerank_enabled: bool = True      # PageRank scoring
abs_crag_enabled: bool = True                # CRAG verification
abs_critique_enabled: bool = True            # Critique loop
abs_multi_query_enabled: bool = True         # Multi-query expansion
abs_hyde_enabled: bool = True                # HyDE generation
```
