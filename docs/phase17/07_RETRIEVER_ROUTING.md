# Phase 17 — Retriever Routing & Document Filter Pipeline

> **Document**: 07_RETRIEVER_ROUTING.md
> **Phase**: 17 — Document-Level Isolation & Cross-Deal Intelligence
> **Status**: Design Specification
> **Last Updated**: 2025-07-14

---

## Table of Contents

1. [Overview](#1-overview)
2. [The Gap: doc_name_prefix Not Used at Search Time](#2-the-gap-doc_name_prefix-not-used-at-search-time)
3. [End-to-End Data Flow](#3-end-to-end-data-flow)
4. [CLI Layer Changes](#4-cli-layer-changes)
5. [RetrievalService Changes](#5-retrievalservice-changes)
6. [HumanLikeRetriever Changes](#6-humanlikeretriever-changes)
7. [DualVectorStore Filter Mechanics](#7-dualvectorstore-filter-mechanics)
8. [Graph Selection Logic](#8-graph-selection-logic)
9. [Multi-Scope Parallel Execution](#9-multi-scope-parallel-execution)
10. [Extension Layer Changes](#10-extension-layer-changes)
11. [Backward Compatibility](#11-backward-compatibility)
12. [Tracing & Observability](#12-tracing--observability)

---

## 1. Overview

This document specifies how the `doc_name_prefix` filter flows from the
user's command through every layer of the retrieval pipeline, ending at
the ChromaDB `where` clause. This is the **critical missing link** that
enables document-level search isolation within a deal.

### The Core Insight

During ingestion (Phase 12.1), every ChromaDB item already has a
`doc_name_prefix` metadata field:

```python
# In IngestionAgent._extract_doc_name_prefix() — ALREADY IMPLEMENTED
metadata["doc_name_prefix"] = "PSA_2006-HE1"
```

But during retrieval, this field is **never used as a filter**. The
retrieval pipeline searches ALL items in the deal's ChromaDB collection
regardless of which document they came from.

### Fix Summary

Wire `doc_filter` (a `doc_name_prefix` value) through 4 layers:

```
Extension (participant.js)
    → Backend CLI (cli/main.py)
        → RetrievalService.execute()
            → _human_like_retrieve() / _phase6_retrieve()
                → HumanLikeRetriever.retrieve()
                    → DualVectorStore.search_items(filters={"doc_name_prefix": X})
```

---

## 2. The Gap: doc_name_prefix Not Used at Search Time

### 2.1 Evidence

A search across the retrieval codebase confirms the gap:

**Write side (ingestion)** — `doc_name_prefix` IS set:

```python
# backend/agents/ingestion_agent.py (multiple locations)
metadata["doc_name_prefix"] = doc_name_prefix
```

**Read side (retrieval)** — `doc_name_prefix` is NEVER used:

```
$ grep -r "doc_name_prefix" backend/retrieval/
# → ZERO MATCHES

$ grep -r "doc_name_prefix" backend/agents/retrieval_service.py
# → ZERO MATCHES (only ingestion_agent.py has it)
```

### 2.2 Existing Filter Infrastructure

The infrastructure to support document filtering already exists:

```python
# backend/vector/dual_vector_store.py
def search_items(self, query, top_k=10, filters=None):
    """
    filters: dict of metadata key-value pairs for ChromaDB where clause.
    Example: {"doc_name_prefix": "PSA_2006-HE1"}
    """
    where_clause = filters if filters else None
    results = self.item_collection.query(
        query_embeddings=[embedding],
        n_results=top_k,
        where=where_clause,     # ← Already supported!
    )
```

```python
# backend/retrieval/human_like_retriever.py
def extract_query_filters(self, query):
    filters = {}
    # Extracts section_number, item_type, doc_type_hint
    # BUT NEVER doc_name_prefix  ← THE GAP
    return filters
```

### 2.3 Impact

Without this fix, the following commands are IMPOSSIBLE:
- `@kts /bear_stearns_2006_he1 /PSA what is Realized Loss?`
  → Would search ALL docs in the deal, not just the PSA
- `@kts /compare /deal1 /deal2 /PSA Realized Loss`
  → Cannot constrain comparison to PSAs only

---

## 3. End-to-End Data Flow

### 3.1 Complete Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  EXTENSION (participant.js)                                       │
│                                                                   │
│  User: @kts /bear_stearns_2006_he1 /PSA what is Realized Loss?   │
│                                                                   │
│  parseTwoLevelScope("bear_stearns_2006_he1", "/PSA what is...")   │
│  → { scope: "bear_stearns_2006_he1",                              │
│      doc_type_filter: "PSA",                                      │
│      query: "what is Realized Loss?" }                            │
│                                                                   │
│  kts_tool.call({                                                  │
│      query: "what is Realized Loss?",                             │
│      scope: "bear_stearns_2006_he1",                              │
│      doc_type_filter: "PSA",          ← EXISTING                  │
│      doc_filter: "PSA_2006-HE1",      ← NEW (Phase 17)           │
│  })                                                               │
└────────────────────────┬─────────────────────────────────────────┘
                         │ HTTP/CLI
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│  CLI (cli/main.py)                                                │
│                                                                   │
│  kts query --scope bear_stearns_2006_he1                          │
│            --doc-type PSA                                         │
│            --doc-filter PSA_2006-HE1    ← NEW (Phase 17)          │
│            "what is Realized Loss?"                               │
│                                                                   │
│  request = {                                                      │
│      "query": "what is Realized Loss?",                           │
│      "scope_override": "bear_stearns_2006_he1",                   │
│      "doc_type_filter": "PSA",                                    │
│      "doc_filter": "PSA_2006-HE1",     ← NEW                     │
│  }                                                                │
└────────────────────────┬─────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│  RETRIEVAL SERVICE (retrieval_service.py)                          │
│                                                                   │
│  def execute(self, request):                                      │
│      doc_filter = request.get("doc_filter")  ← NEW               │
│                                                                   │
│      # Resolve doc_filter from doc_type_filter if not explicit    │
│      if not doc_filter and doc_type_filter:                       │
│          doc_filter = catalog.resolve_doc_prefix(                  │
│              scope, doc_type_filter)                               │
│                                                                   │
│      result = self._human_like_retrieve(                          │
│          query, ..., doc_filter=doc_filter)  ← NEW                │
└────────────────────────┬─────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│  HUMAN-LIKE RETRIEVER (human_like_retriever.py)                   │
│                                                                   │
│  def retrieve(self, query, ..., doc_filter=None):                 │
│      filters = self.extract_query_filters(query)                  │
│                                                                   │
│      # Phase 17: Inject doc_name_prefix filter                    │
│      if doc_filter:                                               │
│          filters["doc_name_prefix"] = doc_filter                  │
│                                                                   │
│      # All downstream search calls use filters                    │
│      items = self.dual_store.search_items(                        │
│          query, filters=filters)    ← NOW INCLUDES doc_filter     │
│                                                                   │
│      sections = self.dual_store.search_sections(                  │
│          query, filters=filters)    ← NOW INCLUDES doc_filter     │
└────────────────────────┬─────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│  DUAL VECTOR STORE (dual_vector_store.py)                         │
│                                                                   │
│  def search_items(self, query, top_k=10, filters=None):           │
│      where_clause = filters                                       │
│      results = self.item_collection.query(                        │
│          query_embeddings=[embedding],                            │
│          n_results=top_k,                                         │
│          where=where_clause,       ← {"doc_name_prefix": "PSA"}   │
│      )                                                            │
│                                                                   │
│  ChromaDB WHERE clause:                                           │
│  {"doc_name_prefix": {"$eq": "PSA_2006-HE1"}}                    │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 State Table

| Layer | Parameter Name | Type | Example Value |
|-------|---------------|------|---------------|
| Extension | `doc_type_filter` | string | `"PSA"` |
| Extension | `doc_filter` | string | `"PSA_2006-HE1"` |
| CLI | `--doc-filter` | option | `"PSA_2006-HE1"` |
| RetrievalService | `doc_filter` | string | `"PSA_2006-HE1"` |
| HumanLikeRetriever | `doc_filter` | string | `"PSA_2006-HE1"` |
| DualVectorStore | `filters["doc_name_prefix"]` | string | `"PSA_2006-HE1"` |
| ChromaDB | `where.doc_name_prefix` | string | `"PSA_2006-HE1"` |

---

## 4. CLI Layer Changes

### 4.1 New `--doc-filter` Option

```python
# cli/main.py — add to query command

@click.option(
    "--doc-filter",
    default=None,
    help="Filter results to a specific document (doc_name_prefix value).",
)
def query_cmd(query, scope, doc_type, doc_filter, ...):
    request = {
        "query": query,
        "scope_override": scope,
        "doc_type_filter": doc_type,
        "doc_filter": doc_filter,       # ← NEW
        ...
    }
    result = retrieval_service.execute(request)
```

### 4.2 Auto-Resolution from `--doc-type`

If `--doc-filter` is not explicitly provided but `--doc-type` is, the CLI
resolves the `doc_name_prefix` from the catalog:

```python
if not doc_filter and doc_type and scope:
    catalog = DealCatalog()
    doc_entry = catalog.search_by_doc_type_in_scope(scope, doc_type)
    if doc_entry:
        doc_filter = doc_entry.doc_name_prefix
```

---

## 5. RetrievalService Changes

### 5.1 `execute()` Method Changes

```python
def execute(self, request: dict) -> AgentResult:
    query = request["query"]
    doc_type_filter = request.get("doc_type_filter")
    doc_filter = request.get("doc_filter")          # ← NEW Phase 17
    
    # ... existing scope routing logic ...
    
    # Phase 17: Resolve doc_filter from doc_type_filter + scope
    if not doc_filter and doc_type_filter and resolved_scope:
        doc_filter = self._resolve_doc_filter(
            resolved_scope, doc_type_filter
        )
    
    # Pass doc_filter through to retrieval
    if use_human_like:
        result = self._human_like_retrieve(
            effective_query,
            kb_path=kb_path,
            max_results=max_results,
            extra_queries=extra_queries,
            prior_context_terms=prior_terms,
            doc_filter=doc_filter,                    # ← NEW
        )
```

### 5.2 New `_resolve_doc_filter()` Helper

```python
def _resolve_doc_filter(
    self,
    scope_slug: str,
    doc_type: str,
) -> Optional[str]:
    """Resolve a doc_type (e.g. 'PSA') to a doc_name_prefix
    (e.g. 'PSA_2006-HE1') using the catalog.
    
    This bridges the gap between the user-facing DOC_TYPE token
    and the ChromaDB metadata field.
    """
    if not self._deal_catalog:
        return None
    
    # Look up in deal_documents table
    entry = self._deal_catalog.get_document_by_type(scope_slug, doc_type)
    if entry:
        return entry.doc_name_prefix
    
    # Fallback: try prefix match (doc_type is often a prefix)
    docs = self._deal_catalog.get_documents(scope_slug)
    for doc in docs:
        if doc.doc_name_prefix.upper().startswith(doc_type.upper()):
            return doc.doc_name_prefix
    
    logger.warning(
        "[Phase17] Could not resolve doc_type '%s' to doc_name_prefix "
        "in scope '%s'",
        doc_type, scope_slug,
    )
    return None
```

### 5.3 `_human_like_retrieve()` Changes

```python
def _human_like_retrieve(
    self,
    query: str,
    *,
    kb_path: str,
    max_results: int = 10,
    extra_queries: list[str] | None = None,
    prior_context_terms: list[str] | None = None,
    doc_filter: str | None = None,                    # ← NEW
) -> dict | None:
    """Run human-like Graph-First retrieval."""
    # ... existing setup ...
    
    retriever = HumanLikeRetriever(dual_store, graph, config)
    
    result = retriever.retrieve(
        query,
        max_results=max_results,
        bm25_retriever=bm25,
        config=self.config,
        extra_queries=extra_queries,
        prior_context_terms=prior_context_terms,
        doc_filter=doc_filter,                         # ← NEW
    )
    
    return {
        "results": result.results,
        "confidence": result.confidence,
        "iterations": 1,
        "trace": result.trace,
        "strategy": "graph_first_legal",
        "definitions_glossary": result.definitions_glossary,
        "entity_roles": result.entity_roles,
        "doc_filter_applied": doc_filter,              # ← NEW trace field
    }
```

### 5.4 `_phase6_retrieve()` Changes

The iterative orchestrator path also receives `doc_filter`:

```python
def _phase6_retrieve(
    self,
    query: str,
    *,
    max_results: int = 10,
    extra_queries: list | None = None,
    doc_type_filter: str | None = None,
    scope: str | None = None,
    conversation_history: list | None = None,
    doc_filter: str | None = None,                     # ← NEW
) -> dict | None:
    # ... existing logic ...
    
    if use_human_like:
        result = self._human_like_retrieve(
            effective_query,
            kb_path=kb_path,
            max_results=max_results,
            extra_queries=extra_queries,
            prior_context_terms=prior_terms,
            doc_filter=doc_filter,                      # ← NEW
        )
```

---

## 6. HumanLikeRetriever Changes

### 6.1 `retrieve()` Method Signature Change

```python
def retrieve(
    self,
    query: str,
    *,
    max_results: int = 10,
    bm25_retriever=None,
    config=None,
    extra_queries: list[str] | None = None,
    prior_context_terms: list[str] | None = None,
    doc_filter: str | None = None,                     # ← NEW
) -> RetrievalResult:
```

### 6.2 Filter Injection

The `doc_filter` is injected into the self-query filters before any search
calls:

```python
# At the top of retrieve(), after extract_query_filters():

filters = self.extract_query_filters(query)

# Phase 17: Inject document filter
if doc_filter:
    filters["doc_name_prefix"] = doc_filter
    logger.info(
        "[Phase17] Doc filter applied: doc_name_prefix=%s",
        doc_filter,
    )
```

### 6.3 Affected Search Calls

All internal search calls in `HumanLikeRetriever` that accept `filters`
parameter will automatically receive the `doc_name_prefix` filter:

| Method | Line | Search Type | Now Filtered |
|--------|------|-------------|-------------|
| `_search_items_with_filters` | ~L1068 | Primary item search | ✅ |
| `_search_items_fallback` | ~L1082 | Fallback item search | ✅ |
| `_search_sections` | ~L2277 | Section-level search | ✅ |
| `_graph_expand_search` | ~L2307 | Graph-guided expansion | ✅ |
| `_definition_search` | ~L2361 | Definition lookup | ✅ |

### 6.4 Graph Section Lookup Interaction

When `doc_filter` is active, the graph section lookup should also be
scoped to the specific document's graph:

```python
def _graph_section_lookup(self, query, doc_filter=None):
    """Look up relevant sections via graph traversal.
    
    Phase 17: When doc_filter is set, only traverse nodes
    belonging to that document.
    """
    # Get candidate section nodes
    section_nodes = self._find_sections_for_query(query)
    
    if doc_filter:
        # Filter to sections belonging to the target document
        section_nodes = [
            n for n in section_nodes
            if self.graph.nodes[n].get("doc_name_prefix") == doc_filter
        ]
    
    return section_nodes
```

### 6.5 Definition Enrichment Interaction

When `doc_filter` is active, definition lookups should prefer definitions
from the target document but fall back to other documents if not found:

```python
def _inject_definitions(self, results, doc_filter=None):
    """Enrich results with defined term definitions.
    
    Phase 17: When doc_filter is set:
    1. First look for definitions in the target document
    2. If not found, fall back to any document (with attribution)
    """
    for term in self._referenced_terms(results):
        # Try target doc first
        if doc_filter:
            definition = self._lookup_definition(
                term, doc_filter=doc_filter
            )
            if definition:
                definition["from_target_doc"] = True
                continue
        
        # Fall back to any definition
        definition = self._lookup_definition(term)
        if definition and doc_filter:
            definition["from_target_doc"] = False
            definition["cross_doc_note"] = (
                f"Definition from {definition.get('source_doc', 'unknown')} "
                f"(not found in {doc_filter})"
            )
```

---

## 7. DualVectorStore Filter Mechanics

### 7.1 ChromaDB `where` Clause

ChromaDB supports metadata filtering via the `where` parameter. The
`doc_name_prefix` filter translates to:

```python
# Single value match
where = {"doc_name_prefix": "PSA_2006-HE1"}

# Equivalent to:
where = {"doc_name_prefix": {"$eq": "PSA_2006-HE1"}}
```

### 7.2 Combined Filters

When multiple metadata filters are active (e.g., doc_name_prefix + item_type),
they are combined with `$and`:

```python
# Doc filter + item type filter
filters = {
    "doc_name_prefix": "PSA_2006-HE1",
    "item_type": "Rule",
}

# DualVectorStore converts to ChromaDB where clause:
where = {
    "$and": [
        {"doc_name_prefix": {"$eq": "PSA_2006-HE1"}},
        {"item_type": {"$eq": "Rule"}},
    ]
}
```

### 7.3 Implementation in `DualVectorStore`

```python
# backend/vector/dual_vector_store.py

def _build_where_clause(self, filters: Optional[Dict[str, Any]]) -> Optional[Dict]:
    """Convert a flat filters dict to a ChromaDB where clause.
    
    Phase 17: Handles multi-filter AND combination.
    """
    if not filters:
        return None
    
    if len(filters) == 1:
        # Single filter — direct match
        key, value = next(iter(filters.items()))
        return {key: value}
    
    # Multiple filters — combine with $and
    conditions = [{k: v} for k, v in filters.items()]
    return {"$and": conditions}
```

### 7.4 Metadata Verification

During development, verify that `doc_name_prefix` is present in ChromaDB
metadata for all items:

```python
# Diagnostic query
all_items = collection.get(include=["metadatas"])
has_prefix = sum(
    1 for m in all_items["metadatas"]
    if m.get("doc_name_prefix")
)
total = len(all_items["metadatas"])
print(f"doc_name_prefix present: {has_prefix}/{total} items")
```

---

## 8. Graph Selection Logic

### 8.1 Graph Source Selection

When `doc_filter` is active, the retriever should use the **document-
specific graph** instead of the deal-level graph:

```python
def _select_graph(self, kb_path: str, doc_filter: Optional[str] = None):
    """Select the appropriate graph for retrieval.
    
    Phase 17 dual graph strategy:
    - doc_filter is set → use doc-specific graph (smaller, faster)
    - doc_filter is None → use deal-level graph (includes cross-doc edges)
    """
    if doc_filter:
        # Try doc-specific graph first
        doc_graph_path = os.path.join(
            kb_path, "graph", "doc_graphs", f"{doc_filter}.json"
        )
        if os.path.exists(doc_graph_path):
            logger.info("[Phase17] Using doc-specific graph: %s", doc_filter)
            graph = GraphStore(doc_graph_path).load()
            return graph
    
    # Fall back to deal-level graph (default)
    deal_graph_path = os.path.join(kb_path, "graph", "knowledge_graph.json")
    return GraphStore(deal_graph_path).load()
```

### 8.2 Selection Matrix

| User Command | doc_filter | Graph Used | Rationale |
|-------------|-----------|-----------|-----------|
| `/scope query` | None | Deal-level | Cross-doc relationships needed |
| `/scope /PSA query` | "PSA_2006-HE1" | Doc-specific | Single-doc traversal |
| `/compare /s1 /s2 concept` | None | Deal-level × 2 | Cross-doc edges for comparison |
| `/compare /s1 /s2 /PSA concept` | "PSA_..." | Doc-specific × 2 | PSA-only graph per deal |
| `//PSA query` | "PSA" per deal | Doc-specific × N | Same doc type across deals |
| `/scope /define term` | None | Deal-level | Cross-doc definition discovery |
| `/scope /PSA /define term` | "PSA_2006-HE1" | Doc-specific | PSA-only definitions |

### 8.3 Graph Caching

Document-specific graphs are typically small (100–500 nodes) and can be
cached in memory:

```python
class GraphCache:
    """LRU cache for loaded graphs."""
    
    def __init__(self, max_size: int = 20):
        self._cache: Dict[str, nx.DiGraph] = {}
        self._access_order: List[str] = []
        self._max_size = max_size
    
    def get(self, graph_path: str) -> Optional[nx.DiGraph]:
        if graph_path in self._cache:
            self._access_order.remove(graph_path)
            self._access_order.append(graph_path)
            return self._cache[graph_path]
        return None
    
    def put(self, graph_path: str, graph: nx.DiGraph) -> None:
        if len(self._cache) >= self._max_size:
            evict = self._access_order.pop(0)
            del self._cache[evict]
        self._cache[graph_path] = graph
        self._access_order.append(graph_path)
```

---

## 9. Multi-Scope Parallel Execution

### 9.1 When Multi-Scope is Triggered

Multi-scope parallel execution is triggered by:
- Wildcard scopes: `/bear*`
- Global doc-type: `//PSA`
- Comparison modes: `/compare /deal1 /deal2`
- Aggregate mode: `/aggregate //PSA`

### 9.2 Fan-Out Architecture

```
User: @kts //PSA what is Realized Loss?

ScopeResolver resolves //PSA → [deal1, deal2, deal3, ...]

For each deal:
    ┌─────────────────────┐
    │   Parallel Task      │
    │                      │
    │  1. Resolve kts_path │
    │  2. Load doc graph   │
    │  3. Load dual store  │
    │  4. Run retrieval    │
    │  5. Return results   │
    └─────────────────────┘

Results aggregated → ranked → returned to user
```

### 9.3 Implementation

```python
async def _multi_scope_retrieve(
    self,
    query: str,
    scope_slugs: List[str],
    doc_filter: Optional[str] = None,
    max_results_per_scope: int = 5,
) -> Dict[str, List[Dict]]:
    """Execute retrieval across multiple scopes in parallel.
    
    Phase 17: Supports doc_filter for cross-deal doc-type searches.
    """
    async def _search_one(slug: str) -> Tuple[str, List[Dict]]:
        try:
            # Resolve kts_path from catalog
            entry = self._deal_catalog.get_by_slug(slug)
            if not entry:
                return slug, []
            
            kb_path = entry.kts_path
            
            # Build per-scope retrieval request
            request = {
                "query": query,
                "scope_override": slug,
                "max_results": max_results_per_scope,
                "doc_filter": doc_filter,
            }
            
            result = self._phase6_retrieve(
                query,
                kb_path=kb_path,
                max_results=max_results_per_scope,
                doc_filter=doc_filter,
            )
            
            # Tag results with scope
            if result and result.get("results"):
                for r in result["results"]:
                    r["_scope_slug"] = slug
                    r["_scope_name"] = entry.folder_name
                return slug, result["results"]
            
            return slug, []
        
        except Exception as exc:
            logger.warning(
                "[Phase17] Multi-scope search failed for %s: %s",
                slug, exc,
            )
            return slug, []
    
    # Fan out with concurrency limit
    semaphore = asyncio.Semaphore(5)  # Max 5 concurrent searches
    
    async def _bounded_search(slug):
        async with semaphore:
            return await _search_one(slug)
    
    tasks = [_bounded_search(slug) for slug in scope_slugs]
    results = await asyncio.gather(*tasks)
    
    return {slug: chunks for slug, chunks in results}
```

### 9.4 Result Aggregation

```python
def _aggregate_multi_scope_results(
    self,
    scope_results: Dict[str, List[Dict]],
    max_total: int = 20,
) -> List[Dict]:
    """Merge and rank results from multiple scopes.
    
    Strategy: Interleave top results from each scope, then
    re-rank by confidence score.
    """
    all_results = []
    for slug, results in scope_results.items():
        for r in results:
            r["_source_scope"] = slug
            all_results.append(r)
    
    # Sort by confidence/score
    all_results.sort(
        key=lambda r: r.get("score", r.get("confidence", 0)),
        reverse=True,
    )
    
    return all_results[:max_total]
```

---

## 10. Extension Layer Changes

### 10.1 `participant.js` — Token Parsing Enhancement

```javascript
// Enhanced parseTwoLevelScope to extract doc_filter
function parseTwoLevelScope(command, prompt) {
    const match = (prompt || '').match(/^\/(\w+)\s+([\s\S]*)/);
    if (match) {
        const docType = match[1].toUpperCase();
        return {
            scope: command,
            doc_type_filter: docType,
            query: match[2].trim()
        };
    }
    return {
        scope: command,
        doc_type_filter: null,
        query: (prompt || '').trim()
    };
}
```

### 10.2 `kts_tool.js` — Forward doc_filter

```javascript
// In kts_tool.js call() method:

const toolInput = {
    query: parsed.query,
    scope: parsed.scope,
    doc_type_filter: parsed.doc_type_filter,
    // Phase 17: Let backend resolve doc_name_prefix from doc_type_filter
    // doc_filter is resolved server-side via catalog lookup
};
```

### 10.3 `participant.js` — Result Attribution

```javascript
// When displaying results, show document provenance:

function formatResult(result) {
    const docSource = result.doc_name_prefix || result.source_doc || '';
    const section = result.section_number || result.section || '';
    const confidence = (result.score || result.confidence || 0).toFixed(2);
    
    let attribution = '';
    if (docSource) {
        attribution = `📄 Source: ${docSource}`;
        if (section) attribution += ` > Section ${section}`;
    }
    
    return `${result.content}\n\n${attribution}\n📊 Confidence: ${confidence}`;
}
```

---

## 11. Backward Compatibility

### 11.1 No Breaking Changes

All changes are additive. The `doc_filter` parameter defaults to `None`
at every layer, preserving existing behavior:

| Scenario | doc_filter | Behavior |
|----------|-----------|----------|
| Existing commands (no /DOC_TYPE) | `None` | Searches all docs (unchanged) |
| New commands with /DOC_TYPE | Set | Searches only specified doc |
| CLI without `--doc-filter` | `None` | Searches all docs (unchanged) |
| Direct API without doc_filter | `None` | Searches all docs (unchanged) |

### 11.2 Graceful Degradation

If the catalog is unavailable (no deal_documents table), doc_filter
resolution silently fails and falls back to searching all documents:

```python
def _resolve_doc_filter(self, scope_slug, doc_type):
    try:
        entry = self._deal_catalog.get_document_by_type(scope_slug, doc_type)
        return entry.doc_name_prefix if entry else None
    except Exception:
        logger.debug("[Phase17] Doc filter resolution failed, searching all docs")
        return None
```

---

## 12. Tracing & Observability

### 12.1 Trace Fields

The retrieval trace includes new fields for doc-filter observability:

```python
trace = {
    # Existing fields
    "query": query,
    "scope": resolved_scope,
    "strategy": "graph_first_legal",
    
    # Phase 17 additions
    "doc_filter_requested": doc_type_filter,          # What user asked for
    "doc_filter_resolved": doc_filter,                 # What we resolved to
    "doc_filter_applied": bool(doc_filter),            # Was it applied?
    "graph_source": "doc_specific" if doc_filter else "deal_level",
    
    # For multi-scope
    "multi_scope": len(scope_slugs) > 1,
    "scopes_searched": scope_slugs,
    "results_per_scope": {slug: len(results) for slug, results in scope_results.items()},
}
```

### 12.2 Logging

```python
# Key log messages for debugging:

logger.info("[Phase17] Doc filter: %s → %s", doc_type_filter, doc_filter)
logger.info("[Phase17] Graph source: %s", "doc_specific" if doc_filter else "deal_level")
logger.info("[Phase17] Multi-scope: %d scopes, %d total results",
            len(scope_slugs), sum(len(r) for r in scope_results.values()))
```

---

*End of Document — 07_RETRIEVER_ROUTING.md*
