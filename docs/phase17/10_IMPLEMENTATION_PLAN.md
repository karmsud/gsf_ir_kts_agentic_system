# Phase 17: Implementation Plan
## Step-by-Step Execution Guide

**Document Version:** 1.0  
**Date:** February 22, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** Detailed implementation roadmap with file paths, code changes, and timeline  
**Prerequisites:** Phase 12.1 per-folder .kts isolation (completed), Phase 6 dual vector store (completed)

---

## Table of Contents

1. [Overview](#overview)
2. [Step 1: Doc-Name-Prefix Read-Side Wiring](#step-1-doc-name-prefix-read-side-wiring)
3. [Step 2: Dual Graph Build](#step-2-dual-graph-build)
4. [Step 3: Graph Partitioning & Doc-Graph Persistence](#step-3-graph-partitioning--doc-graph-persistence)
5. [Step 4: Deal Catalog Schema Upgrade](#step-4-deal-catalog-schema-upgrade)
6. [Step 5: Scope Resolution Pipeline](#step-5-scope-resolution-pipeline)
7. [Step 6: Retriever Routing — Doc Filter & Graph Selection](#step-6-retriever-routing--doc-filter--graph-selection)
8. [Step 7: Multi-Deal Parallel Execution](#step-7-multi-deal-parallel-execution)
9. [Step 8: Comparison / Diff / Aggregate Modes](#step-8-comparison--diff--aggregate-modes)
10. [Step 9: CLI Upgrades](#step-9-cli-upgrades)
11. [Step 10: Extension UX — Parsing, Autocomplete, Rendering](#step-10-extension-ux--parsing-autocomplete-rendering)
12. [Step 11: Result Attribution & Rendering](#step-11-result-attribution--rendering)
13. [Timeline & Dependencies](#timeline--dependencies)
14. [Rollback Strategy](#rollback-strategy)
15. [Feature Flags](#feature-flags)

---

## Overview

### Implementation Philosophy

**Incremental Deployment:**
- Each step is independently testable
- Feature flags protect production
- Rollback points at every step
- Continuous validation with golden queries

**Quality Gates:**
- Unit tests pass before proceeding to next step
- Integration tests validate cross-component interactions
- Golden query benchmark maintained or improved
- No regression in existing functionality

**Risk Mitigation:**
- Steps 1–3 are write-side changes that don't affect existing read paths
- Steps 4–6 introduce new query routing with fallback to current behavior
- Steps 7–8 add new capabilities (additive only)
- Steps 9–11 are UX layer changes with graceful degradation

---

### Estimated Effort

| Step | Description | Estimated Time | Risk Level |
|------|-------------|----------------|------------|
| Step 1 | Doc-name-prefix read-side wiring | 2–3 hours | ⚪ Very Low |
| Step 2 | Dual graph build | 3–4 hours | 🟡 Low |
| Step 3 | Graph partitioning & persistence | 2–3 hours | 🟡 Low |
| Step 4 | Deal catalog schema upgrade | 2–3 hours | 🟡 Low |
| Step 5 | Scope resolution pipeline | 3–4 hours | 🟠 Medium |
| Step 6 | Retriever routing (doc filter + graph) | 4–5 hours | 🟠 Medium |
| Step 7 | Multi-deal parallel execution | 3–4 hours | 🟠 Medium |
| Step 8 | Comparison / diff / aggregate modes | 4–6 hours | 🟠 Medium |
| Step 9 | CLI upgrades | 2–3 hours | ⚪ Very Low |
| Step 10 | Extension UX (parsing, autocomplete) | 4–5 hours | 🟡 Low |
| Step 11 | Result attribution & rendering | 2–3 hours | ⚪ Very Low |
| **TOTAL** | **All steps** | **31–43 hours** | **🟢 Overall Low–Medium** |

**Timeline:** 8–11 work days (4 hours/day) with testing

---

## Step 1: Doc-Name-Prefix Read-Side Wiring

### Objective
Wire the existing `doc_name_prefix` metadata (already stored during ingestion) as a ChromaDB `where` filter on the read/retrieval side.

### Risk Assessment
- **Risk Level:** ⚪ Very Low
- **Impact:** Additive filter, no existing behavior changes when filter is absent
- **Rollback:** Remove filter argument — one-line revert per call site
- **Testing:** Query with and without filter, verify result sets

### Files to Modify

---

**File 1: `cli/main.py`**

**What:** Add `--doc-filter` option to the `search` command

**Current location:** Line ~400 (search command options block)

**Add option:**
```python
@click.option("--doc-filter", default=None,
              help="Phase 17: Filter results to a specific document type (e.g., PSA, PROSUPP).")
```

**Wire into request dict:**
```python
result = retrieval.execute({
    ...
    "doc_name_prefix": doc_filter.upper() if doc_filter else None,
    ...
})
```

**Add parameter to function signature:**
```python
def search(query, max_results, doc_type, tool_filter, ..., doc_filter, compare_scopes):
```

---

**File 2: `backend/agents/retrieval_service.py`**

**What:** Accept `doc_name_prefix` from request and pass through to `_phase6_retrieve` and `_human_like_retrieve`.

**Location 1:** ~Line 1410 (main execute method)

**Add extraction:**
```python
doc_name_prefix = request.get("doc_name_prefix")
```

**Location 2:** All calls to `_phase6_retrieve()` — add `doc_name_prefix=doc_name_prefix` kwarg.

**Location 3:** `_phase6_retrieve()` signature — add `doc_name_prefix: str | None = None` parameter.

**Location 4:** `_human_like_retrieve()` signature — add `doc_name_prefix: str | None = None` parameter. Forward to `HumanLikeRetriever.retrieve()`.

---

**File 3: `backend/retrieval/human_like_retriever.py`**

**What:** Apply `doc_name_prefix` as a ChromaDB `where` filter on all `search_items()` and `search_sections()` calls.

**Location:** `retrieve()` method (~Line 2143)

**Change in filter extraction block:**
```python
# AFTER existing filter extraction:
if doc_name_prefix:
    filters["doc_name_prefix"] = doc_name_prefix
```

**Change in global fallback block (~Line 2270):**
```python
item_filters = {}
if "item_type" in filters:
    item_filters["item_type"] = filters["item_type"]
if "doc_name_prefix" in filters:
    item_filters["doc_name_prefix"] = filters["doc_name_prefix"]
global_items = self.dual_store.search_items(
    sub_query,
    top_k=max_results * 2,
    filters=item_filters if item_filters else None
)
```

**Change in section-scoped search (~Line 1068):**
```python
filters: Dict[str, Any] = {"section_number": sec_num}
if item_type_filter:
    filters["item_type"] = item_type_filter
if doc_name_prefix:
    filters["doc_name_prefix"] = doc_name_prefix
```

### Verification
```bash
# Without filter — returns chunks from ALL docs in deal
kts search "What is Distribution Date?" --scope-override fin_deal1

# With filter — only PSA chunks
kts search "What is Distribution Date?" --scope-override fin_deal1 --doc-filter PSA

# Verify PSA chunks returned have doc_name_prefix=PSA in metadata
```

### Success Criteria
- ✅ `--doc-filter PSA` returns only PSA-sourced chunks
- ✅ Without `--doc-filter`, behavior is identical to pre-Phase 17
- ✅ Filter works with both human-like and iterative retrievers
- ✅ No performance regression (metadata filter is O(1) in ChromaDB)

---

## Step 2: Dual Graph Build

### Objective
During graph building, tag every node and edge with `doc_name_prefix` so the graph can be partitioned per-document and filtered at query time.

### Risk Assessment
- **Risk Level:** 🟡 Low (extends existing graph build)
- **Impact:** Adds metadata to nodes/edges, does not change graph structure
- **Rollback:** Remove attribute additions — graph still usable without them

### Files to Modify

---

**File 1: `backend/graph/enhanced_graph_builder.py`**

**What:** Accept `doc_name_prefix` parameter and stamp it on every node and edge created.

**Method:** `build_hierarchical_graph()` (~Line 42)

**Add parameter:**
```python
def build_hierarchical_graph(
    self,
    document_id: str,
    doc_type: str,
    sections: List[Dict[str, Any]],
    *,
    doc_metadata: Optional[Dict[str, Any]] = None,
    doc_name_prefix: str = "",              # NEW
    llm_callable: Any | None = None,
) -> Dict[str, int]:
```

**Stamp on document node:**
```python
doc_attrs: dict[str, Any] = {
    "type": "DOCUMENT",
    "doc_type": doc_type,
    "doc_name_prefix": doc_name_prefix,     # NEW
    **(doc_metadata or {}),
}
```

**Stamp on every section node (~Line 90+):**
```python
section_attrs = {
    ...
    "doc_name_prefix": doc_name_prefix,     # NEW
}
```

**Stamp on every item node (item creation loop):**
```python
item_attrs = {
    ...
    "doc_name_prefix": doc_name_prefix,     # NEW
}
```

**Stamp on every edge (all `G.add_edge()` calls):**
```python
G.add_edge(src, tgt, type=edge_type, doc_name_prefix=doc_name_prefix)
```

---

**File 2: `backend/graph/builder.py`**

**What:** Same treatment for the basic GraphBuilder's `upsert_document()` method.

**Method:** `upsert_document()` (~Line 63)

**Add to doc_attrs:**
```python
doc_attrs = {
    "type": "DOCUMENT",
    "title": metadata.get("title", doc.doc_id),
    "path": doc.source_path,
    "doc_type": metadata.get("doc_type", "UNKNOWN"),
    "doc_regime": metadata.get("doc_regime", "UNKNOWN"),
    "doc_name_prefix": metadata.get("doc_name_prefix", ""),  # NEW
}
```

---

**File 3: `backend/agents/ingestion_agent.py`**

**What:** Pass `doc_name_prefix` to `build_hierarchical_graph()` during ingestion.

**Location:** ~Line 123 (graph builder call)

```python
enhanced_builder.build_hierarchical_graph(
    document_id=doc_id,
    doc_type=doc_type,
    sections=sections,
    doc_metadata=metadata,
    doc_name_prefix=_extract_doc_name_prefix(source_path.stem),  # NEW
)
```

### Verification
```bash
# After re-ingestion, inspect graph JSON:
python -c "
import json
g = json.load(open('kb_test/Fin_deal1/.kts/graph/knowledge_graph.json'))
prefixes = set()
for nid, attrs in g['nodes'].items():
    if 'doc_name_prefix' in attrs:
        prefixes.add(attrs['doc_name_prefix'])
print('Doc prefixes in graph:', prefixes)
"
# Expected: {'PSA', 'PROSUPP'}
```

### Success Criteria
- ✅ Every node in the graph has `doc_name_prefix` attribute
- ✅ Every edge in the graph has `doc_name_prefix` attribute
- ✅ Prefixes correctly identify source document
- ✅ Existing graph queries still work (attribute is additive)

---

## Step 3: Graph Partitioning & Doc-Graph Persistence

### Objective
After building the full deal graph, partition it into per-document sub-graphs and write them to `doc_graphs/` directory. Also add cross-document edges to the deal-level graph.

### Risk Assessment
- **Risk Level:** 🟡 Low (new code, post-processing step)
- **Impact:** Creates additional files, does not modify existing graph
- **Rollback:** Delete `doc_graphs/` directory

### Files to Create

---

**New File: `backend/graph/graph_partitioner.py`**

```python
"""
Phase 17.2 — Graph Partitioner

Partitions a deal-level graph into per-document sub-graphs based on
the `doc_name_prefix` attribute. Also builds cross-document edges
in the deal graph.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Set

import networkx as nx

logger = logging.getLogger(__name__)


def partition_graph_by_document(
    deal_graph: nx.DiGraph,
    output_dir: str,
) -> Dict[str, int]:
    """
    Partition a deal-level graph into per-document sub-graphs.

    Args:
        deal_graph: The full deal graph with doc_name_prefix on all nodes.
        output_dir: Directory to write doc_graphs/ into.

    Returns:
        Dict mapping doc_name_prefix → node count in sub-graph.
    """
    doc_graphs_dir = Path(output_dir) / "doc_graphs"
    doc_graphs_dir.mkdir(parents=True, exist_ok=True)

    # Group nodes by doc_name_prefix
    prefix_nodes: Dict[str, Set[str]] = {}
    for node_id, attrs in deal_graph.nodes(data=True):
        prefix = attrs.get("doc_name_prefix", "")
        if prefix:
            prefix_nodes.setdefault(prefix, set()).add(node_id)

    stats: Dict[str, int] = {}

    for prefix, node_ids in prefix_nodes.items():
        sub_graph = deal_graph.subgraph(node_ids).copy()
        out_path = doc_graphs_dir / f"{prefix}.json"
        _save_graph_json(sub_graph, out_path)
        stats[prefix] = len(node_ids)
        logger.info(
            "[Phase17] Doc graph %s: %d nodes, %d edges → %s",
            prefix, len(node_ids), sub_graph.number_of_edges(), out_path,
        )

    return stats


def add_cross_document_edges(deal_graph: nx.DiGraph) -> int:
    """
    Detect and add cross-document relationship edges.

    Cross-doc edges are identified when:
    1. A TERM node is DEFINED in doc A but REFERENCED in doc B
    2. An NER entity appears in multiple documents
    3. A concept keyword appears in multiple documents

    Returns:
        Count of cross-document edges added.
    """
    cross_edges_added = 0

    # Collect TERM nodes with their doc_name_prefix
    term_nodes: Dict[str, Dict[str, list]] = {}  # term_text → {prefix → [node_ids]}
    for node_id, attrs in deal_graph.nodes(data=True):
        node_type = attrs.get("type", "")
        prefix = attrs.get("doc_name_prefix", "")
        if not prefix:
            continue

        if node_type == "TERM":
            label = attrs.get("label", attrs.get("name", node_id))
            term_nodes.setdefault(label, {}).setdefault(prefix, []).append(node_id)

    # Add CROSS_DOC_TERM edges for terms appearing in multiple docs
    for term_label, prefix_map in term_nodes.items():
        if len(prefix_map) < 2:
            continue
        prefixes = list(prefix_map.keys())
        for i in range(len(prefixes)):
            for j in range(i + 1, len(prefixes)):
                src_nodes = prefix_map[prefixes[i]]
                tgt_nodes = prefix_map[prefixes[j]]
                for src in src_nodes:
                    for tgt in tgt_nodes:
                        if not deal_graph.has_edge(src, tgt):
                            deal_graph.add_edge(
                                src, tgt,
                                type="CROSS_DOC_TERM",
                                source_doc=prefixes[i],
                                target_doc=prefixes[j],
                                term=term_label,
                            )
                            cross_edges_added += 1

    # Collect NER entity nodes by entity name
    entity_nodes: Dict[str, Dict[str, list]] = {}
    for node_id, attrs in deal_graph.nodes(data=True):
        node_type = attrs.get("type", "")
        prefix = attrs.get("doc_name_prefix", "")
        if node_type in ("ENTITY", "NER_ENTITY") and prefix:
            name = attrs.get("name", attrs.get("label", ""))
            if name:
                entity_nodes.setdefault(name, {}).setdefault(prefix, []).append(node_id)

    # Add CROSS_DOC_ENTITY edges
    for entity_name, prefix_map in entity_nodes.items():
        if len(prefix_map) < 2:
            continue
        prefixes = list(prefix_map.keys())
        for i in range(len(prefixes)):
            for j in range(i + 1, len(prefixes)):
                src = prefix_map[prefixes[i]][0]
                tgt = prefix_map[prefixes[j]][0]
                if not deal_graph.has_edge(src, tgt):
                    deal_graph.add_edge(
                        src, tgt,
                        type="CROSS_DOC_ENTITY",
                        source_doc=prefixes[i],
                        target_doc=prefixes[j],
                        entity=entity_name,
                    )
                    cross_edges_added += 1

    logger.info("[Phase17] Added %d cross-document edges", cross_edges_added)
    return cross_edges_added


def _save_graph_json(G: nx.DiGraph, path: Path) -> None:
    """Save graph in the project's canonical JSON format."""
    nodes = {}
    for node_id, attrs in G.nodes(data=True):
        nodes[node_id] = {"id": node_id, **attrs}
    edges = []
    for src, tgt, attrs in G.edges(data=True):
        edges.append({"source": src, "target": tgt, **attrs})
    data = {"nodes": nodes, "edges": edges}
    if G.graph:
        data["graph"] = dict(G.graph)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
```

### Files to Modify

---

**File: `backend/agents/ingestion_agent.py`**

**What:** After graph build completes for a deal scope, partition and add cross-doc edges.

**Location:** After `enhanced_builder.build_hierarchical_graph()` completes (post-processing block)

```python
# Phase 17: Dual graph strategy
from backend.graph.graph_partitioner import partition_graph_by_document, add_cross_document_edges

deal_graph = graph_store.load()
cross_edges = add_cross_document_edges(deal_graph)
graph_store.save(deal_graph)

doc_graph_stats = partition_graph_by_document(
    deal_graph,
    output_dir=str(Path(config.graph_path).parent),
)
logger.info("[Phase17] Deal graph: +%d cross-doc edges. Doc graphs: %s", cross_edges, doc_graph_stats)
```

### Storage Layout After Step 3

```
Fin_deal1/.kts/
  graph/
    knowledge_graph.json       ← deal graph (all docs + cross-doc edges)
    doc_graphs/
      PSA.json                 ← only PSA nodes/edges
      PROSUPP.json             ← only PROSUPP nodes/edges
```

### Verification
```bash
python -c "
import json
# Check deal graph has cross-doc edges
g = json.load(open('kb_test/Fin_deal1/.kts/graph/knowledge_graph.json'))
cross = [e for e in g['edges'] if e.get('type', '').startswith('CROSS_DOC')]
print(f'Deal graph: {len(g[\"nodes\"])} nodes, {len(g[\"edges\"])} edges, {len(cross)} cross-doc edges')

# Check doc graphs exist
import os
doc_dir = 'kb_test/Fin_deal1/.kts/graph/doc_graphs'
for f in os.listdir(doc_dir):
    dg = json.load(open(os.path.join(doc_dir, f)))
    print(f'{f}: {len(dg[\"nodes\"])} nodes, {len(dg[\"edges\"])} edges')
"
```

### Success Criteria
- ✅ `doc_graphs/PSA.json` contains only PSA-sourced nodes
- ✅ `doc_graphs/PROSUPP.json` contains only PROSUPP-sourced nodes
- ✅ `knowledge_graph.json` contains all nodes + `CROSS_DOC_TERM` and `CROSS_DOC_ENTITY` edges
- ✅ Partitioning is idempotent (re-run produces same result)

---

## Step 4: Deal Catalog Schema Upgrade

### Objective
Upgrade the deal catalog to store rich deal metadata (deal name, vintage, series, issuer, doc types) enabling structured queries and wildcard matching.

### Risk Assessment
- **Risk Level:** 🟡 Low (schema extension, backward compatible)
- **Impact:** Existing catalog entries preserved; new fields nullable
- **Rollback:** Drop new columns (SQLite ALTER TABLE)

### Files to Modify

---

**File: `backend/vector/deal_catalog.py`**

**What:** Extend schema with new columns and add structured query methods.

**Current Schema (from existing code):**
```sql
CREATE TABLE IF NOT EXISTS deals (
    scope_slug TEXT PRIMARY KEY,
    folder_path TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
)
```

**New Schema:**
```sql
CREATE TABLE IF NOT EXISTS deals (
    scope_slug    TEXT PRIMARY KEY,
    folder_path   TEXT NOT NULL,
    deal_name     TEXT DEFAULT '',
    vintage       INTEGER DEFAULT 0,
    series        TEXT DEFAULT '',
    issuer        TEXT DEFAULT '',
    doc_types     TEXT DEFAULT '',         -- comma-separated: "PSA,PROSUPP"
    chunk_count   INTEGER DEFAULT 0,
    status        TEXT DEFAULT 'active',   -- active | stale | error
    created_at    TEXT DEFAULT (datetime('now')),
    updated_at    TEXT DEFAULT (datetime('now'))
)
```

**New methods to add:**

```python
def upsert_deal(self, scope_slug: str, folder_path: str, *,
                deal_name: str = "", vintage: int = 0, series: str = "",
                issuer: str = "", doc_types: list[str] | None = None,
                chunk_count: int = 0, status: str = "active") -> None:
    """Insert or update a deal entry with full metadata."""
    ...

def search_deals(self, *, deal_name: str = "", vintage: int = 0,
                 pattern: str = "") -> list[dict]:
    """Search deals by structured metadata or wildcard pattern.
    
    Args:
        deal_name: Exact or prefix match on deal_name.
        vintage: Exact match on vintage year.
        pattern: Wildcard pattern (e.g., 'bear_stearns_2006*').
    
    Returns:
        List of matching deal entries as dicts.
    """
    ...

def get_doc_types(self, scope_slug: str) -> list[str]:
    """Return list of document types ingested for a given deal."""
    ...

def list_all_deals(self) -> list[dict]:
    """Return all catalog entries with full metadata."""
    ...
```

**New helper function — deal metadata extraction from folder name:**

```python
def _parse_deal_folder_name(folder_name: str) -> dict:
    """
    Heuristic extraction of deal metadata from folder name.
    
    Examples:
        "Bear_Stearns_2006_HE1" → {deal_name: "Bear Stearns", vintage: 2006, series: "HE1"}
        "Fin_deal1"              → {deal_name: "Fin deal1", vintage: 0, series: ""}
    """
    ...
```

---

**File: `backend/agents/ingestion_agent.py`**

**What:** After successful ingestion of a deal scope, update the catalog with full metadata.

**Location:** Post-processing block (after graph build)

```python
# Phase 17: Update deal catalog with rich metadata
from backend.vector.deal_catalog import DealCatalog, _parse_deal_folder_name

catalog = DealCatalog(config.deal_catalog_path)
folder_meta = _parse_deal_folder_name(scope_folder.name)
doc_types_in_scope = list({
    _extract_doc_name_prefix(Path(r["source"]).stem)
    for r in results if r.get("source")
})

catalog.upsert_deal(
    scope_slug=scope_slug,
    folder_path=str(scope_folder),
    deal_name=folder_meta.get("deal_name", ""),
    vintage=folder_meta.get("vintage", 0),
    series=folder_meta.get("series", ""),
    doc_types=doc_types_in_scope,
    chunk_count=sum(r.get("chunks", 0) for r in results),
    status="active",
)
```

### Verification
```bash
# After re-ingestion:
python -c "
import sqlite3
conn = sqlite3.connect('kb_test/.kts_catalog/deal_catalog.db')
conn.row_factory = sqlite3.Row
for row in conn.execute('SELECT * FROM deals'):
    print(dict(row))
"
```

### Success Criteria
- ✅ Schema migration works cleanly (new columns added, old data preserved)
- ✅ `search_deals(pattern='bear_stearns_2006*')` returns matching deals
- ✅ `get_doc_types('fin_deal1')` returns `['PSA', 'PROSUPP']`
- ✅ Folder name parsing extracts deal_name, vintage, series where possible

---

## Step 5: Scope Resolution Pipeline

### Objective
Build a unified scope resolution pipeline that parses user commands into structured scope expressions + doc filter + mode, then resolves scope slugs via the deal catalog.

### Risk Assessment
- **Risk Level:** 🟠 Medium (central orchestration, all commands flow through this)
- **Impact:** Single code path for all 14 use cases
- **Rollback:** Bypass pipeline — pass raw scope slug directly (existing behavior)

### Files to Create

---

**New File: `backend/common/scope_resolver.py`**

**Purpose:** Parse slash-token commands and resolve to concrete scope expressions.

**Key classes:**

```python
@dataclass
class ScopeExpr:
    """One scope target parsed from user input."""
    slug: str                    # e.g., "fin_deal1"
    doc_filter: str | None       # e.g., "PSA" or None
    is_wildcard: bool = False    # e.g., "bear_stearns_2006*"

@dataclass
class ParsedCommand:
    """Fully parsed user command."""
    mode: str                    # "search" | "compare" | "diff" | "aggregate" | "define" | "audit" | "list"
    scopes: list[ScopeExpr]
    query: str
    raw_input: str

def parse_command(raw_input: str) -> ParsedCommand:
    """
    Parse slash-token commands from user input.
    
    Syntax:
        /scope_slug           → deal scope only
        /scope_slug/DOC_TYPE  → deal scope + doc filter
        //DOC_TYPE            → all deals, doc filter only
        /scope_wild*          → wildcard scope
        /scope_wild*/DOC_TYPE → wildcard + doc filter
        /compare, /diff, /aggregate, /audit, /list, /define → modes
    
    Examples:
        "@kts /fin_deal1/PSA What is Distribution Date?"
        → ParsedCommand(mode="search", scopes=[ScopeExpr("fin_deal1", "PSA")],
                         query="What is Distribution Date?")
        
        "@kts /compare /bear_stearns_2006*/PSA What is Distribution Date?"
        → ParsedCommand(mode="compare",
                         scopes=[ScopeExpr("bear_stearns_2006", "PSA", is_wildcard=True)],
                         query="What is Distribution Date?")
    """
    ...

def resolve_scopes(
    parsed: ParsedCommand,
    catalog: "DealCatalog",
) -> list[ScopeExpr]:
    """
    Resolve wildcard scopes via deal catalog.
    
    Expands "bear_stearns_2006*" into concrete scope slugs by
    querying the catalog. Also handles //DOC_TYPE (all deals).
    
    Returns expanded list of ScopeExpr with is_wildcard=False.
    """
    ...
```

### Key Design Rules

1. **Mode tokens** (`/compare`, `/diff`, `/aggregate`, `/audit`, `/list`, `/define`) are recognized first and removed from token stream
2. **Remaining slash tokens** are scope expressions — parsed into `ScopeExpr`
3. **If a token contains `/`** internal to it (e.g., `/fin_deal1/PSA`), split at second `/` → slug + doc_filter
4. **If token starts with `//`** (e.g., `//PSA`), it's a global doc filter → scope=`*`, doc_filter=PSA
5. **If token ends with `*`**, it's a wildcard → resolve via catalog
6. **Everything after the last slash token** is the query text

### Files to Modify

**File: `extension/chat/participant.js`**

**What:** Replace current ad-hoc slash parsing with a call to the scope resolver (via CLI bridge).

**The extension will parse the slash tokens client-side** and forward structured data:

```javascript
// Parse slash tokens from query
const tokens = query.match(/\/[a-z0-9_*\/]+/gi) || [];
let mode = 'search';
const scopeExprs = [];

for (const token of tokens) {
    const clean = token.substring(1); // strip leading /
    if (['compare', 'diff', 'aggregate', 'audit', 'list', 'define'].includes(clean)) {
        mode = clean;
    } else if (clean.startsWith('/')) {
        // "//PSA" → global doc filter
        scopeExprs.push({ slug: '*', docFilter: clean.substring(1).toUpperCase() });
    } else if (clean.includes('/')) {
        // "fin_deal1/PSA" → scope + doc filter
        const [slug, doc] = clean.split('/');
        scopeExprs.push({ slug, docFilter: doc.toUpperCase(), isWildcard: slug.includes('*') });
    } else {
        scopeExprs.push({ slug: clean, docFilter: null, isWildcard: clean.includes('*') });
    }
}
```

### Verification
```python
# Unit test:
from backend.common.scope_resolver import parse_command

cmd = parse_command("@kts /compare /bear_stearns_2006*/PSA What is Distribution Date?")
assert cmd.mode == "compare"
assert len(cmd.scopes) == 1
assert cmd.scopes[0].slug == "bear_stearns_2006"
assert cmd.scopes[0].doc_filter == "PSA"
assert cmd.scopes[0].is_wildcard == True
assert cmd.query == "What is Distribution Date?"
```

### Success Criteria
- ✅ All 14 use cases parse correctly
- ✅ Wildcard resolution returns correct catalog matches
- ✅ Global doc filter (`//PSA`) resolves to all ingested deals
- ✅ Malformed input returns helpful error messages

---

## Step 6: Retriever Routing — Doc Filter & Graph Selection

### Objective
Modify the retrieval service to select the appropriate graph (deal-level or doc-level) and apply doc-name-prefix filters based on the resolved scope expression.

### Risk Assessment
- **Risk Level:** 🟠 Medium (changes to retrieval routing)
- **Impact:** New graph selection logic, new filter application
- **Rollback:** Always use deal-level graph (ignore doc_filter for graph selection)

### Files to Modify

---

**File: `backend/agents/retrieval_service.py`**

**What:** Add graph selection logic based on `doc_name_prefix`.

**New method:**
```python
def _select_graph_path(self, scope_kts_path: str, doc_name_prefix: str | None) -> str:
    """
    Select deal-level or doc-level graph based on doc_name_prefix.

    If doc_name_prefix is present AND a doc-specific graph exists,
    use the doc graph for tighter traversal. Otherwise fall back
    to the deal-level graph.
    """
    if doc_name_prefix:
        doc_graph_path = os.path.join(
            scope_kts_path, "graph", "doc_graphs", f"{doc_name_prefix}.json"
        )
        if os.path.exists(doc_graph_path):
            logger.info("[Phase17] Using doc-specific graph: %s", doc_graph_path)
            return doc_graph_path

    deal_graph_path = os.path.join(scope_kts_path, "graph", "knowledge_graph.json")
    return deal_graph_path
```

**Modify `_phase6_retrieve()` and `_human_like_retrieve()`:**

Replace hardcoded graph load with:
```python
graph_path = self._select_graph_path(kb_path, doc_name_prefix)
graph_store = GraphStore(graph_path)
graph = graph_store.load()
```

---

**File: `backend/retrieval/human_like_retriever.py`**

**What:** Accept optional `doc_name_prefix` in `retrieve()` method and merge into filters.

**Change `retrieve()` signature:**
```python
def retrieve(
    self,
    query: str,
    *,
    max_results: int = 10,
    extra_queries: list[str] | None = None,
    prior_context_terms: list[str] | None = None,
    doc_name_prefix: str | None = None,      # NEW
) -> dict:
```

**Inject into filter extraction:**
```python
# After existing filter extraction:
if doc_name_prefix:
    filters["doc_name_prefix"] = doc_name_prefix
```

**Propagate to ALL internal search calls** — section-scoped, global fallback, routing-aware supplemental, and MMR calls.

### Verification
```bash
# Single-doc query — should use doc graph + filtered ChromaDB:
kts search "What is Distribution Date?" --scope-override fin_deal1 --doc-filter PSA
# Check logs for: "[Phase17] Using doc-specific graph: .../doc_graphs/PSA.json"

# Deal-level query — should use full deal graph + no filter:
kts search "What is Distribution Date?" --scope-override fin_deal1
# Check logs for deal graph path
```

### Success Criteria
- ✅ Doc graph selected when `doc_filter` active and graph exists
- ✅ Deal graph selected as fallback
- ✅ `doc_name_prefix` filter propagated to ALL ChromaDB queries
- ✅ No regression without doc filter

---

## Step 7: Multi-Deal Parallel Execution

### Objective
Enable queries across multiple deals (wildcard or explicit) to execute in parallel, with proper score normalization and result merging.

### Risk Assessment
- **Risk Level:** 🟠 Medium (parallel execution, score normalization)
- **Impact:** New execution pipeline for multi-scope queries
- **Rollback:** Fall back to sequential execution

### Files to Modify

---

**File: `backend/agents/retrieval_service.py`**

**What:** Add multi-scope dispatch method.

**New method:**
```python
async def _multi_scope_search(
    self,
    query: str,
    scope_exprs: list[dict],
    max_results_per_scope: int = 5,
    doc_name_prefix: str | None = None,
) -> list[dict]:
    """
    Execute search across multiple scopes in parallel.

    Each scope gets its own RetrievalService instance with scoped config.
    Results are tagged with scope_slug and doc_name_prefix for attribution.
    Scores are normalized per-scope (min-max) then merged.

    Args:
        query: User's query text.
        scope_exprs: List of {"slug": str, "doc_filter": str|None, "kts_path": str}.
        max_results_per_scope: Results per deal.
        doc_name_prefix: Override doc filter if needed.

    Returns:
        Merged result list sorted by normalized score descending.
    """
    import asyncio
    from config.settings import scope_config

    async def _search_one(expr):
        scfg = scope_config(self.config, expr["kts_path"])
        svc = RetrievalService(scfg)
        result = svc.execute({
            "query": query,
            "max_results": max_results_per_scope,
            "doc_name_prefix": expr.get("doc_filter") or doc_name_prefix,
            "scope_override": expr["slug"],
        })
        # Tag results with scope attribution
        for hit in result.get("results", []):
            hit["deal_scope"] = expr["slug"]
            hit["doc_filter_applied"] = expr.get("doc_filter", "")
        return result

    tasks = [_search_one(expr) for expr in scope_exprs]
    all_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Merge and normalize
    merged = []
    for r in all_results:
        if isinstance(r, Exception):
            logger.error("[Phase17] Multi-scope search error: %s", r)
            continue
        merged.extend(r.get("results", []))

    # Score normalization: min-max per scope, then global sort
    # (Scores from different ChromaDBs may have different distributions)
    merged.sort(key=lambda h: h.get("score", 0), reverse=True)
    return merged[:max_results_per_scope * len(scope_exprs)]
```

### Verification
```bash
kts search "What is Distribution Date?" --scope-override "fin_deal1,fin_deal2"
# Should return results from both deals, each tagged with deal_scope
```

### Success Criteria
- ✅ 10-deal wildcard query completes in ≤ 5 seconds
- ✅ Results correctly attributed to source deal
- ✅ Score ordering is meaningful across deals
- ✅ Individual scope failures don't crash the entire query

---

## Step 8: Comparison / Diff / Aggregate Modes

### Objective
Implement three distinct analytical modes for cross-deal and cross-document queries.

### Risk Assessment
- **Risk Level:** 🟠 Medium (new analytical engines)
- **Impact:** New capabilities, additive only
- **Rollback:** Disable via feature flag

### Files to Create / Modify

---

**New File: `backend/agents/diff_engine.py`**

```python
"""
Phase 17 — Diff Engine

Compares retrieval results across two or more scopes, highlighting
specific differences in language, amounts, dates, and obligations.
"""

class DiffEngine:
    """
    Creates structured diffs between deal documents.
    
    Output format:
    {
        "query": "...",
        "diffs": [
            {
                "field": "Distribution Date timing",
                "values": {
                    "fin_deal1/PSA": "the 25th day of each month",
                    "fin_deal2/PSA": "the last business day of each month"
                },
                "diff_type": "value_difference",
                "significance": "high"
            }
        ],
        "common": [...],   # aspects that are identical across scopes
        "summary": "..."   # natural language summary of differences
    }
    """
    
    def diff(self, results_by_scope: dict[str, list], query: str) -> dict:
        """Compute structured diff across scope results."""
        ...
```

---

**New File: `backend/agents/aggregation_engine.py`**

```python
"""
Phase 17 — Aggregation Engine

Summarizes patterns across multiple deals, detecting the
common pattern and flagging outliers.
"""

class AggregationEngine:
    """
    Analyzes results across N deals to find patterns.
    
    Output format:
    {
        "query": "...",
        "pattern": "8 of 10 deals define Distribution Date as the 25th",
        "outliers": [
            {"deal": "bear_stearns_2006he3", "text": "last business day", "deviation": "timing"}
        ],
        "confidence": 0.92,
        "deal_count": 10,
        "summary": "..."
    }
    """
    
    def aggregate(self, results_by_scope: dict[str, list], query: str) -> dict:
        """Find patterns and outliers across scope results."""
        ...
```

---

**File: `backend/agents/retrieval_service.py`**

**What:** Wire mode dispatch in the main execute method.

```python
# In execute():
mode = request.get("mode", "search")

if mode == "compare":
    return self._execute_compare(request)
elif mode == "diff":
    return self._execute_diff(request)
elif mode == "aggregate":
    return self._execute_aggregate(request)
elif mode == "list":
    return self._execute_list(request)
else:
    return self._execute_search(request)  # existing search path
```

### Existing Comparison Engine

**Note:** `backend/agents/contradiction_detector.py` and `backend/agents/comparison_engine.py` (Phase 15) already exist. The `/compare` mode should delegate to the existing `ContradictionDetector` + `ComparisonMode`. The `/diff` and `/aggregate` modes are net-new.

### Success Criteria
- ✅ `/compare` produces side-by-side results with contradiction detection
- ✅ `/diff` highlights specific textual differences with significance scoring
- ✅ `/aggregate` identifies majority pattern + outliers across N deals
- ✅ All three modes support doc-level filtering

---

## Step 9: CLI Upgrades

### Objective
Update the CLI to support all new Phase 17 commands and options.

### Risk Assessment
- **Risk Level:** ⚪ Very Low (additive options, no breaking changes)
- **Rollback:** Remove new options

### Files to Modify

---

**File: `cli/main.py`**

**New/updated options for `search` command:**

```python
@click.option("--doc-filter", default=None,
              help="Phase 17: Filter to specific doc type (e.g., PSA, PROSUPP).")
@click.option("--mode", default="search",
              type=click.Choice(["search", "compare", "diff", "aggregate", "define", "audit", "list"]),
              help="Phase 17: Query mode.")
@click.option("--scopes", default=None,
              help="Phase 17: Comma-separated scope slugs or wildcard pattern.")
```

**New `list` command:**

```python
@cli.command()
@click.option("--scope", default=None, help="Show details for a specific deal scope.")
def list_deals(scope):
    """List all ingested deals with metadata."""
    config = _ctx()
    catalog = DealCatalog(config.deal_catalog_path)
    
    if scope:
        deals = catalog.search_deals(pattern=scope)
    else:
        deals = catalog.list_all_deals()
    
    for deal in deals:
        click.echo(json.dumps(deal, indent=2))
```

### Success Criteria
- ✅ `kts search "..." --doc-filter PSA --scope-override fin_deal1` works
- ✅ `kts search "..." --mode compare --scopes "fin_deal1,fin_deal2"` works
- ✅ `kts search "..." --mode aggregate --scopes "bear_stearns_2006*"` works
- ✅ `kts list-deals` shows all ingested deals
- ✅ `kts list-deals --scope "bear_stearns*"` shows filtered results

---

## Step 10: Extension UX — Parsing, Autocomplete, Rendering

### Objective
Implement client-side slash token parsing, scope autocomplete, and result attribution rendering in the VS Code extension.

### Risk Assessment
- **Risk Level:** 🟡 Low (extension UI, graceful degradation)
- **Rollback:** Disable autocomplete, fall back to raw text

### Files to Modify

---

**File: `extension/chat/participant.js`**

**What:** Replace current scope parsing with unified command parser.

See Step 5 for the parsing logic. Additionally:

```javascript
// Build CLI args from parsed command
const cliArgs = ['search', concept];
if (mode !== 'search') cliArgs.push('--mode', mode);
for (const expr of scopeExprs) {
    if (expr.slug !== '*') cliArgs.push('--scope-override', expr.slug);
    if (expr.docFilter) cliArgs.push('--doc-filter', expr.docFilter);
}
if (scopeExprs.some(e => e.isWildcard)) {
    cliArgs.push('--scopes', scopeExprs.map(e => e.slug + (e.isWildcard ? '*' : '')).join(','));
}
```

---

**File: `extension/lib/scope_discovery.js`**

**What:** Extend scope discovery to also report doc types per scope.

```javascript
async function discoverScopes(knowledgeSourceRoot) {
    // ... existing code ...
    
    // Phase 17: Also discover document types per scope
    for (const scope of scopes) {
        if (scope.indexed) {
            const docGraphsDir = path.join(scope.ktsPath, 'graph', 'doc_graphs');
            try {
                const docGraphFiles = await fs.promises.readdir(docGraphsDir);
                scope.docTypes = docGraphFiles
                    .filter(f => f.endsWith('.json'))
                    .map(f => f.replace('.json', ''));
            } catch {
                scope.docTypes = [];
            }
        }
    }
    
    return scopes;
}
```

---

**File: `extension/chat/participant.js`**

**What:** Register doc-type sub-commands in chat participant.

After scope discovery, for each scope with doc types, register:
- `/fin_deal1` — query entire deal
- Autocomplete after `/fin_deal1/` → show `PSA`, `PROSUPP`

---

**File: `extension/copilot/kts_tool.js`**

**What:** Forward new parameters (`--doc-filter`, `--mode`, `--scopes`) to CLI.

### Success Criteria
- ✅ Typing `@kts /` shows scope autocomplete
- ✅ Typing `@kts /fin_deal1/` shows doc type autocomplete
- ✅ Parsed command correctly forwarded to CLI
- ✅ Graceful degradation when autocomplete data unavailable

---

## Step 11: Result Attribution & Rendering

### Objective
Ensure every result in multi-scope and multi-doc queries carries clear deal + document attribution, and render appropriately in the extension.

### Risk Assessment
- **Risk Level:** ⚪ Very Low (display logic)
- **Rollback:** Revert rendering template

### Files to Modify

---

**File: `extension/chat/participant.js`**

**What:** Update result rendering for multi-scope results.

**For compare mode:**
```markdown
## Comparison: "What is Distribution Date?"

### fin_deal1 / PSA
> "Distribution Date" means the 25th day of each month...
> — Section 1.01, Score: 0.96

### fin_deal2 / PSA  
> "Distribution Date" means the last Business Day of each month...
> — Section 1.01, Score: 0.94

### ⚠️ Differences Detected
- **Timing:** Deal 1 uses "25th day", Deal 2 uses "last Business Day"
```

**For aggregate mode:**
```markdown
## Aggregation: "How is Realized Loss defined?" (10 deals)

### Common Pattern (8/10 deals)
> "Realized Loss" means the amount by which the Stated Principal Balance
> of a Mortgage Loan exceeds liquidation proceeds...

### Outliers (2/10 deals)
- **bear_stearns_2006he3:** Includes additional deduction for servicer advances
- **bear_stearns_2006he7:** Uses "Net Loss" instead of "Realized Loss"
```

**For single-scope single-doc:**
```markdown
## fin_deal1 / PSA — "What is Distribution Date?"

> "Distribution Date" means the 25th day of each month...
> — Section 1.01, Score: 0.96
```

### Success Criteria
- ✅ Multi-scope results show deal + doc attribution
- ✅ Compare mode renders side-by-side with diff highlights
- ✅ Aggregate mode shows pattern + outliers
- ✅ Single-scope results show scope context

---

## Timeline & Dependencies

### Dependency Graph

```
Step 1 (doc filter read-side) ──┐
                                 ├── Step 6 (retriever routing)
Step 2 (dual graph metadata) ──┤
                                 │
Step 3 (graph partitioning) ────┘
                                 
Step 4 (catalog upgrade) ───────── Step 5 (scope resolver) ──── Step 7 (parallel execution)
                                                                       │
                                                                       ├── Step 8 (compare/diff/aggregate)
                                                                       │
Step 9 (CLI) ──────────────────────────────────────────────────────────┘
                                                                       │
Step 10 (extension UX) ────────────────────────────────────────────────┤
                                                                       │
Step 11 (result rendering) ────────────────────────────────────────────┘
```

### Suggested Execution Order

| Day | Steps | Focus |
|-----|-------|-------|
| Day 1 | Steps 1 + 2 | Write-side: metadata wiring |
| Day 2 | Step 3 | Write-side: graph partitioning |
| Day 3 | Step 4 | Catalog schema upgrade |
| Day 4 | Step 5 | Scope resolver (core parsing logic) |
| Day 5 | Step 6 | Retriever routing (graph selection + filters) |
| Day 6 | Step 7 | Multi-deal parallel execution |
| Day 7 | Step 8 | Comparison / diff / aggregate engines |
| Day 8 | Step 9 | CLI wiring |
| Day 9 | Steps 10 + 11 | Extension UX + rendering |
| Day 10–11 | Integration testing | End-to-end validation |

---

## Rollback Strategy

### Per-Step Rollback

| Step | Rollback Action | Time |
|------|----------------|------|
| Step 1 | Remove `--doc-filter` option + filter propagation | 5 min |
| Step 2 | Remove `doc_name_prefix` from graph builder calls | 5 min |
| Step 3 | Delete `doc_graphs/` directory + `graph_partitioner.py` | 2 min |
| Step 4 | Revert catalog schema (old columns still work) | 5 min |
| Step 5 | Bypass scope resolver — raw slug pass-through | 5 min |
| Step 6 | Always select deal-level graph | 5 min |
| Step 7 | Disable parallel — sequential fallback | 5 min |
| Step 8 | Disable `/diff` and `/aggregate` modes | 5 min |
| Step 9 | Remove new CLI options | 5 min |
| Step 10 | Remove autocomplete — plain text input | 5 min |
| Step 11 | Revert to standard rendering | 5 min |

### Full Rollback
Revert all Phase 17 changes — total time < 15 minutes. The system falls back to Phase 12.1 behavior (per-deal isolation without doc filtering or multi-deal queries).

---

## Feature Flags

All Phase 17 features are gated by config flags in `config/settings.py`:

```python
# Phase 17 flags (KTSConfig dataclass)
phase17_doc_filter_enabled: bool = True       # Step 1: doc_name_prefix filtering
phase17_dual_graph_enabled: bool = True       # Steps 2–3: doc-specific graphs
phase17_rich_catalog_enabled: bool = True     # Step 4: enhanced catalog schema
phase17_scope_resolver_enabled: bool = True   # Step 5: unified scope parsing
phase17_graph_routing_enabled: bool = True    # Step 6: doc vs deal graph selection
phase17_multi_deal_enabled: bool = True       # Step 7: parallel multi-scope
phase17_diff_mode_enabled: bool = True        # Step 8: /diff mode
phase17_aggregate_mode_enabled: bool = True   # Step 8: /aggregate mode
```

When a flag is `False`, the system falls back to existing behavior:
- No doc filter applied
- Only deal-level graph used
- Old catalog schema (scope_slug + folder_path only)
- Raw scope slug pass-through
- Sequential execution
- Only `/compare` mode (existing Phase 15)

---

*End of Document — 10_IMPLEMENTATION_PLAN.md*
