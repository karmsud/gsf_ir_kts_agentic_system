# Phase 17: Dual Graph Strategy
## Doc-Specific Graphs + Deal-Level Graph with Cross-Document Edges

**Document Version:** 1.0  
**Date:** February 22, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** Graph architecture, cross-doc edge types, partitioning algorithm, retriever selection

---

## Table of Contents
1. [Overview](#overview)
2. [Current Graph Architecture](#current-graph-architecture)
3. [Proposed Dual Graph Architecture](#proposed-dual-graph-architecture)
4. [Cross-Document Edge Types](#cross-document-edge-types)
5. [Graph Build Pipeline](#graph-build-pipeline)
6. [Graph Partitioning Algorithm](#graph-partitioning-algorithm)
7. [Retriever Graph Selection Logic](#retriever-graph-selection-logic)
8. [Node Metadata Enrichment](#node-metadata-enrichment)
9. [Performance Considerations](#performance-considerations)

---

## Overview

### Why Dual Graphs?

A single deal folder may contain multiple related documents (PSA, ProSupp, Trust Agreement, etc.). These documents are interdependent — the PSA defines terms that the ProSupp references, the Trust Agreement establishes roles mentioned across all documents.

**The user has two distinct needs:**

1. **Precision queries** — "What does the PSA say about Distribution Date?"
   → Only traverse PSA sections and items. No noise from ProSupp.
   → Use **doc-specific graph** (`doc_graphs/PSA.json`)

2. **Cross-document reasoning** — "What is the Distribution Date?"
   → The PSA defines it in Section 1.01, the ProSupp references it in the payment waterfall.
   → Graph should follow cross-doc edges: `DEFINED_IN(PSA) → REFERENCED_IN(PROSUPP)`
   → Use **deal-level graph** (`knowledge_graph.json`)

### Design Decision

Build **one deal-level graph** during ingestion, then **partition** it into doc-specific subgraphs. This is efficient (single build pass + O(N) partition) and ensures consistency (doc graphs are exact subsets of the deal graph, minus cross-doc edges).

---

## Current Graph Architecture

### Existing Schema (Phase 6 + NER Enrichment)

```
┌─────────────────┐
│    DOCUMENT      │ ← One node per document
│   Properties:    │
│   - doc_type     │
│   - title        │
│   - path         │
│   - regime       │
└────────┬────────┘
         │ CONTAINS (weight: 1.0)
         ▼
┌─────────────────┐
│    SECTION       │ ← One node per section
│   Properties:    │
│   - heading      │
│   - section_num  │
│   - section_idx  │
│   - doc_id       │
│   - synopsis     │
│   - concept_kw   │
└────────┬────────┘
         │ HAS_RULE / HAS_DEFINITION / HAS_ITEM (typed)
         ▼
┌─────────────────┐
│      ITEM        │ ← One node per extracted item (definition, rule, etc.)
│   Properties:    │
│   - item_type    │
│   - text         │
│   - document_id  │
│   - section_num  │
└─────────────────┘

Additional edges:
  Section ──NEXT──▶ Section (sequential navigation)
  Item ──REFERENCES──▶ Item (cross-reference within same doc)
  ENTITY ──ASSIGNED_ROLE──▶ defined_term (NER party identification)
```

### Current Limitation

All nodes from all documents in a deal go into **one graph**. The graph has no attribute to distinguish PSA nodes from ProSupp nodes. The retriever always traverses the entire graph — even when the user only asked about the PSA.

---

## Proposed Dual Graph Architecture

### Deal-Level Graph (`knowledge_graph.json`)

Same as current graph, PLUS:

1. **Every node gets `doc_name_prefix` attribute** — identifies which document the node belongs to
2. **Cross-document edges** — new edge types connecting related nodes across documents
3. **Cross-doc reference edges** — explicit "as described in the PSA, Section X.XX" edges

```
┌─────────────────┐                               ┌─────────────────┐
│  doc:PSA_Bear06  │                               │ doc:ProSupp_B06  │
│  doc_name_prefix │                               │  doc_name_prefix │
│  = "PSA"         │                               │  = "PROSUPP"     │
└────────┬────────┘                               └────────┬────────┘
         │ CONTAINS                                         │ CONTAINS
         ▼                                                  ▼
┌─────────────────┐    SECTION_CROSS_REF    ┌─────────────────┐
│ sec:PSA:0001     │◀─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│ sec:ProSupp:0015│
│ "Definitions"    │                        │ "Distributions"  │
│ doc_name_prefix  │                        │ doc_name_prefix  │
│ = "PSA"          │                        │ = "PROSUPP"      │
└────────┬────────┘                        └────────┬────────┘
         │ HAS_DEFINITION                           │ HAS_ITEM
         ▼                                          ▼
┌─────────────────┐  TERM_CROSS_DOC_REF    ┌─────────────────┐
│ item:def-dist-dt │──────────────────────▶│ item:stmt-dist   │
│ "Distribution    │                        │ "The Distribution│
│  Date means..."  │                        │  Date for each   │
│ doc_name_prefix  │                        │  period..."      │
│ = "PSA"          │                        │ doc_name_prefix  │
│                  │                        │ = "PROSUPP"      │
└─────────────────┘                        └─────────────────┘
```

### Doc-Specific Graph (`doc_graphs/PSA.json`)

A **partition** of the deal graph containing ONLY:
- Nodes where `doc_name_prefix == "PSA"`
- Edges where **both** endpoints have `doc_name_prefix == "PSA"`
- NO cross-doc edges (those live exclusively in the deal graph)

```
┌─────────────────┐
│  doc:PSA_Bear06  │
│  doc_name_prefix │
│  = "PSA"         │
└────────┬────────┘
         │ CONTAINS
         ▼
┌─────────────────┐──NEXT──▶ ┌─────────────────┐──NEXT──▶ ...
│ sec:PSA:0001     │         │ sec:PSA:0002     │
│ "Definitions"    │         │ "Distributions"  │
└────────┬────────┘         └────────┬────────┘
         │ HAS_DEFINITION            │ HAS_RULE
         ▼                           ▼
┌─────────────────┐         ┌─────────────────┐
│ item:def-dist-dt │         │ item:rule-dist   │
│ "Distribution    │◀────────│ (REFERENCES)     │
│  Date means..."  │         │ "On each Distri- │
│                  │         │  bution Date..." │
└─────────────────┘         └─────────────────┘
```

---

## Cross-Document Edge Types

### New Edge Types (Added to `graph/schema.py`)

| Edge Type | Source → Target | Description | Weight | Example |
|-----------|-----------------|-------------|--------|---------|
| `TERM_CROSS_DOC_REF` | ITEM (definition in Doc A) → ITEM (reference in Doc B) | Same defined term appears in another document | 0.9 | "Distribution Date" defined in PSA §1.01, referenced in ProSupp §4.01 |
| `ENTITY_SHARED` | ENTITY node → ENTITY node | Same NER entity appears in both documents | 0.8 | "JPMorgan Chase" as Trustee mentioned in both PSA and ProSupp |
| `CONCEPT_COOCCURRENCE` | SECTION → SECTION (different docs) | Sections in different docs share concept keywords | 0.6 | PSA §5.04 "loss allocation" ↔ ProSupp §3.02 "loss allocation" |
| `SECTION_CROSS_REF` | SECTION → SECTION (different docs) | Explicit textual cross-reference ("as described in the PSA, Section X") | 0.95 | ProSupp §3 → PSA §5.05 (explicit mention) |

### Edge Detection Algorithms

#### `TERM_CROSS_DOC_REF` Detection

```python
def detect_term_cross_doc_refs(graph: nx.DiGraph) -> list[tuple[str, str, dict]]:
    """Find defined terms in Doc A that are referenced in Doc B.
    
    Algorithm:
    1. Collect all ITEM nodes with item_type == "Definition"
    2. Extract the defined term surface form from each
    3. For each item in OTHER documents, check if the term appears in the text
    4. Create TERM_CROSS_DOC_REF edge from definition item → referencing item
    """
    edges = []
    
    # Collect definitions keyed by term text
    definitions = {}  # {term_lower: (node_id, doc_prefix)}
    for node_id, attrs in graph.nodes(data=True):
        if attrs.get("type") == "ITEM" and attrs.get("item_type") == "Definition":
            # Extract term from first ~50 chars (before "means" or "shall mean")
            text = attrs.get("text", "")
            term = extract_term_from_definition(text)
            if term:
                definitions[term.lower()] = (node_id, attrs.get("doc_name_prefix", ""))
    
    # Scan non-definition items for term references
    for node_id, attrs in graph.nodes(data=True):
        if attrs.get("type") != "ITEM":
            continue
        doc_prefix = attrs.get("doc_name_prefix", "")
        text = attrs.get("text", "").lower()
        
        for term_lower, (def_node_id, def_prefix) in definitions.items():
            if def_prefix == doc_prefix:
                continue  # Same doc — already handled by REFERENCES edge
            if term_lower in text:
                edges.append((def_node_id, node_id, {
                    "type": "TERM_CROSS_DOC_REF",
                    "weight": 0.9,
                    "term": term_lower,
                    "source_doc": def_prefix,
                    "target_doc": doc_prefix,
                }))
    
    return edges
```

#### `ENTITY_SHARED` Detection

```python
def detect_entity_shared(graph: nx.DiGraph) -> list[tuple[str, str, dict]]:
    """Find NER entities that appear in multiple documents.
    
    Algorithm:
    1. Collect all ENTITY nodes grouped by surface_form
    2. For entities appearing in 2+ doc_name_prefixes, create ENTITY_SHARED edges
    """
    from collections import defaultdict
    
    entity_groups = defaultdict(list)  # {surface_form: [(node_id, doc_prefix)]}
    
    for node_id, attrs in graph.nodes(data=True):
        if attrs.get("type") == "ENTITY":
            surface = attrs.get("surface_form", "")
            doc_prefix = attrs.get("doc_name_prefix", "")
            if surface and doc_prefix:
                entity_groups[surface.lower()].append((node_id, doc_prefix))
    
    edges = []
    for surface, entries in entity_groups.items():
        # Get unique doc prefixes
        by_doc = defaultdict(list)
        for nid, dp in entries:
            by_doc[dp].append(nid)
        
        if len(by_doc) < 2:
            continue  # Same doc only
        
        # Create pairwise edges between docs
        doc_list = list(by_doc.items())
        for i in range(len(doc_list)):
            for j in range(i + 1, len(doc_list)):
                doc_a, nodes_a = doc_list[i]
                doc_b, nodes_b = doc_list[j]
                # Connect first node from each doc (representative)
                edges.append((nodes_a[0], nodes_b[0], {
                    "type": "ENTITY_SHARED",
                    "weight": 0.8,
                    "entity_surface": surface,
                    "doc_a": doc_a,
                    "doc_b": doc_b,
                }))
    
    return edges
```

#### `CONCEPT_COOCCURRENCE` Detection

```python
def detect_concept_cooccurrence(graph: nx.DiGraph, min_overlap: int = 2) -> list[tuple[str, str, dict]]:
    """Find sections in different documents that share concept keywords.
    
    Algorithm:
    1. For each SECTION node, get its concept_keywords set
    2. Compare sections across different doc_name_prefixes
    3. If keyword overlap >= min_overlap, create CONCEPT_COOCCURRENCE edge
    """
    sections_by_doc = defaultdict(list)
    
    for node_id, attrs in graph.nodes(data=True):
        if attrs.get("type") == "SECTION":
            keywords = set(attrs.get("concept_keywords", "").split(","))
            keywords.discard("")
            doc_prefix = attrs.get("doc_name_prefix", "")
            if keywords and doc_prefix:
                sections_by_doc[doc_prefix].append((node_id, keywords))
    
    edges = []
    doc_list = list(sections_by_doc.items())
    for i in range(len(doc_list)):
        for j in range(i + 1, len(doc_list)):
            doc_a, secs_a = doc_list[i]
            doc_b, secs_b = doc_list[j]
            for nid_a, kw_a in secs_a:
                for nid_b, kw_b in secs_b:
                    overlap = kw_a & kw_b
                    if len(overlap) >= min_overlap:
                        edges.append((nid_a, nid_b, {
                            "type": "CONCEPT_COOCCURRENCE",
                            "weight": 0.6,
                            "shared_concepts": ",".join(sorted(overlap)),
                            "overlap_count": len(overlap),
                        }))
    
    return edges
```

#### `SECTION_CROSS_REF` Detection

```python
def detect_section_cross_refs(graph: nx.DiGraph) -> list[tuple[str, str, dict]]:
    """Find explicit textual cross-references between documents.
    
    Patterns detected:
    - "as described in the PSA, Section 5.05"
    - "pursuant to Section 2.01 of the Pooling and Servicing Agreement"
    - "see Section 3.02 of the Prospectus Supplement"
    
    Algorithm:
    1. For each ITEM node, scan text for cross-reference patterns
    2. Extract target document name + section number
    3. Find matching SECTION node in the target document
    4. Create SECTION_CROSS_REF edge from source section → target section
    """
    import re
    
    CROSS_REF_PATTERNS = [
        # "Section X.XX of the PSA/Pooling and Servicing Agreement"
        r'Section\s+(\d+(?:\.\d+)*)\s+of\s+the\s+([\w\s]+?)(?:\s*[,;.\)])',
        # "as described/defined in the PSA, Section X.XX"
        r'(?:as\s+)?(?:described|defined|set\s+forth)\s+in\s+the\s+([\w\s]+?),?\s*Section\s+(\d+(?:\.\d+)*)',
        # "pursuant to Section X.XX of the [Agreement Name]"
        r'pursuant\s+to\s+Section\s+(\d+(?:\.\d+)*)\s+of\s+the\s+([\w\s]+?)(?:\s*[,;.\)])',
    ]
    
    # Map document names to doc_name_prefix
    DOC_NAME_MAP = {
        "pooling and servicing agreement": "PSA",
        "psa": "PSA",
        "prospectus supplement": "PROSUPP",
        "prospectus": "PROSUPP",
        "trust agreement": "TRUST",
        "indenture": "INDENTURE",
        "servicing agreement": "SERVICING",
    }
    
    # Build section lookup: (doc_prefix, section_number) → section_node_id
    section_lookup = {}
    for node_id, attrs in graph.nodes(data=True):
        if attrs.get("type") == "SECTION":
            key = (attrs.get("doc_name_prefix", ""), attrs.get("section_number", ""))
            section_lookup[key] = node_id
    
    edges = []
    for node_id, attrs in graph.nodes(data=True):
        if attrs.get("type") != "ITEM":
            continue
        text = attrs.get("text", "")
        source_doc = attrs.get("doc_name_prefix", "")
        source_section = attrs.get("section_number", "")
        
        for pattern in CROSS_REF_PATTERNS:
            for match in re.finditer(pattern, text, re.I):
                groups = match.groups()
                # Determine target doc + section from pattern groups
                # (pattern-specific extraction logic)
                target_doc_name = None
                target_section_num = None
                # ... extract from groups based on pattern structure ...
                
                if target_doc_name and target_section_num:
                    target_prefix = DOC_NAME_MAP.get(target_doc_name.lower().strip())
                    if target_prefix and target_prefix != source_doc:
                        source_sec_key = (source_doc, source_section)
                        target_sec_key = (target_prefix, target_section_num)
                        if source_sec_key in section_lookup and target_sec_key in section_lookup:
                            edges.append((
                                section_lookup[source_sec_key],
                                section_lookup[target_sec_key],
                                {
                                    "type": "SECTION_CROSS_REF",
                                    "weight": 0.95,
                                    "source_doc": source_doc,
                                    "target_doc": target_prefix,
                                    "target_section": target_section_num,
                                }
                            ))
    
    return edges
```

---

## Graph Build Pipeline

### Sequence Diagram

```
Ingestion Agent (per-deal)
    │
    ├─── For each document in deal folder:
    │       │
    │       ├── Extract sections + items
    │       ├── EnhancedGraphBuilder.build_hierarchical_graph()
    │       │     └── Pass doc_name_prefix to all node attributes    ← NEW
    │       └── Result: doc node + section nodes + item nodes in deal graph
    │
    ├─── After all documents processed:                                ← NEW
    │       │
    │       ├── CrossDocEdgeBuilder.build()
    │       │     ├── detect_term_cross_doc_refs()
    │       │     ├── detect_entity_shared()
    │       │     ├── detect_concept_cooccurrence()
    │       │     └── detect_section_cross_refs()
    │       │
    │       └── Save deal graph → knowledge_graph.json
    │
    └─── Partition deal graph into doc-specific graphs:                ← NEW
            │
            ├── GraphPartitioner.partition(deal_graph)
            │     ├── Group nodes by doc_name_prefix
            │     ├── For each prefix → extract subgraph
            │     └── Include only intra-doc edges
            │
            └── Save each → doc_graphs/{PREFIX}.json
```

---

## Graph Partitioning Algorithm

### Specification

```python
class GraphPartitioner:
    """Partition a deal-level graph into doc-specific subgraphs.
    
    Each doc graph contains:
    - All nodes with matching doc_name_prefix
    - All edges where BOTH source and target have the same doc_name_prefix
    - Excludes cross-doc edges (TERM_CROSS_DOC_REF, ENTITY_SHARED, etc.)
    
    The deal graph is NOT modified — doc graphs are derived copies.
    """
    
    CROSS_DOC_EDGE_TYPES = {
        "TERM_CROSS_DOC_REF",
        "ENTITY_SHARED", 
        "CONCEPT_COOCCURRENCE",
        "SECTION_CROSS_REF",
    }
    
    @staticmethod
    def partition(deal_graph: nx.DiGraph) -> dict[str, nx.DiGraph]:
        """Partition deal graph into doc-specific subgraphs.
        
        Args:
            deal_graph: The full deal-level NetworkX DiGraph
            
        Returns:
            Dict mapping doc_name_prefix → subgraph
            Example: {"PSA": <DiGraph>, "PROSUPP": <DiGraph>}
        """
        # Collect unique doc prefixes
        prefix_nodes: dict[str, set[str]] = defaultdict(set)
        
        for node_id, attrs in deal_graph.nodes(data=True):
            prefix = attrs.get("doc_name_prefix", "")
            if prefix:
                prefix_nodes[prefix].add(node_id)
        
        doc_graphs: dict[str, nx.DiGraph] = {}
        
        for prefix, nodes in prefix_nodes.items():
            # Create subgraph with only this doc's nodes
            subgraph = deal_graph.subgraph(nodes).copy()
            
            # Remove any cross-doc edges that may have slipped in
            edges_to_remove = []
            for u, v, data in subgraph.edges(data=True):
                if data.get("type") in GraphPartitioner.CROSS_DOC_EDGE_TYPES:
                    edges_to_remove.append((u, v))
            for u, v in edges_to_remove:
                subgraph.remove_edge(u, v)
            
            doc_graphs[prefix] = subgraph
        
        return doc_graphs
    
    @staticmethod
    def save_doc_graphs(
        doc_graphs: dict[str, nx.DiGraph],
        graph_dir: str,
    ) -> dict[str, str]:
        """Save doc-specific graphs to disk.
        
        Args:
            doc_graphs: Dict from partition()
            graph_dir: Base graph directory (e.g., "Fin_deal1/.kts/graph")
            
        Returns:
            Dict mapping prefix → file path
        """
        doc_graphs_dir = Path(graph_dir) / "doc_graphs"
        doc_graphs_dir.mkdir(parents=True, exist_ok=True)
        
        paths = {}
        for prefix, graph in doc_graphs.items():
            path = doc_graphs_dir / f"{prefix}.json"
            store = GraphStore(str(path))
            store.save(graph)
            paths[prefix] = str(path)
            logger.info(
                "[Phase17] Saved doc graph: %s (%d nodes, %d edges)",
                path, graph.number_of_nodes(), graph.number_of_edges()
            )
        
        return paths
```

---

## Retriever Graph Selection Logic

### Selection Matrix

| Command | `doc_filter` | Graph Selected | Graph Path |
|---------|-------------|----------------|-----------|
| `@kts /fin_deal1/PSA ...` | `"PSA"` | Doc graph | `.kts/graph/doc_graphs/PSA.json` |
| `@kts /fin_deal1 ...` | `None` | Deal graph | `.kts/graph/knowledge_graph.json` |
| `@kts /compare /d1/PSA /d2/PSA ...` | `"PSA"` per scope | Doc graph per scope | Each `.kts/graph/doc_graphs/PSA.json` |
| `@kts /compare /d1 /d2 ...` | `None` | Deal graph per scope | Each `.kts/graph/knowledge_graph.json` |
| `@kts /diff /d1/PSA /d1/PROSUPP ...` | Per target | Doc graph per target | `PSA.json`, `PROSUPP.json` |

### Implementation in RetrievalService

```python
def _select_graph_path(self, config: KTSConfig, doc_filter: str | None) -> str:
    """Select the appropriate graph path based on doc filter.
    
    Args:
        config: Scoped KTS config (points to deal .kts/ directory)
        doc_filter: Document name prefix (e.g., "PSA") or None
        
    Returns:
        Absolute path to the graph JSON file
    """
    base_graph_dir = Path(config.graph_path).parent
    
    if doc_filter and config.doc_graphs_enabled:
        doc_graph_path = base_graph_dir / "doc_graphs" / f"{doc_filter}.json"
        if doc_graph_path.exists():
            logger.info("[Phase17] Using doc graph: %s", doc_graph_path)
            return str(doc_graph_path)
        else:
            logger.warning(
                "[Phase17] Doc graph not found: %s, falling back to deal graph",
                doc_graph_path
            )
    
    # Fallback: deal-level graph
    return config.graph_path
```

### Fallback Behavior

If a doc graph doesn't exist (e.g., first ingestion before Phase 17 partition):
1. Log a warning
2. Fall back to the deal-level graph
3. Apply `doc_name_prefix` filter to vector searches regardless
4. Graph traversal may include nodes from other docs (wider recall, slightly less precision)

This ensures backward compatibility and graceful degradation.

---

## Node Metadata Enrichment

### New Attribute: `doc_name_prefix`

Every node in the graph receives a `doc_name_prefix` attribute during build:

| Node Type | Current Attributes | New Attribute |
|-----------|-------------------|---------------|
| DOCUMENT | doc_type, title, path, regime | `doc_name_prefix` |
| SECTION | heading, section_number, section_index, doc_id, synopsis, concept_keywords | `doc_name_prefix` |
| ITEM | item_type, text, document_id, section_number, section_heading, section_index, item_index | `doc_name_prefix` |
| ENTITY | entity_type, surface_form | `doc_name_prefix` |
| DEFINED_TERM | surface_form, confidence, extraction_strategy | `doc_name_prefix` |
| CONCEPT | name | `doc_name_prefix` (may span multiple docs in deal graph) |

### Implementation in `EnhancedGraphBuilder`

The `build_hierarchical_graph()` method receives `doc_name_prefix` as a new parameter:

```python
def build_hierarchical_graph(
    self,
    document_id: str,
    doc_type: str,
    sections: List[Dict[str, Any]],
    *,
    doc_metadata: Optional[Dict[str, Any]] = None,
    doc_name_prefix: str = "",    # ← NEW PARAMETER
    llm_callable: Any | None = None,
) -> Dict[str, int]:
    # ... existing code ...
    
    # Document node
    doc_attrs = {
        "type": "DOCUMENT",
        "doc_type": doc_type,
        "doc_name_prefix": doc_name_prefix,  # ← NEW
        **(doc_metadata or {}),
    }
    G.add_node(doc_node_id, **doc_attrs)
    
    for section_index, section_dict in enumerate(sections):
        # Section node
        G.add_node(section_id,
            type="SECTION",
            heading=section_heading,
            section_number=section_number,
            doc_id=document_id,
            doc_name_prefix=doc_name_prefix,  # ← NEW
            # ... existing attrs ...
        )
        
        for item in items:
            G.add_node(item.id,
                type="ITEM",
                item_type=item.item_type,
                doc_name_prefix=doc_name_prefix,  # ← NEW
                # ... existing attrs ...
            )
```

---

## Performance Considerations

### Build Time Impact

| Operation | Current | With Phase 17 | Delta |
|-----------|---------|--------------|-------|
| Graph build (per doc) | ~2s | ~2.1s (+attribute) | +5% |
| Cross-doc edge detection | N/A | ~0.5s per deal | New |
| Graph partitioning | N/A | ~0.2s per deal | New |
| Doc graph serialization | N/A | ~0.1s per doc graph | New |
| **Total per 2-doc deal** | **~4s** | **~5s** | **+25%** |

### Memory Impact

| Graph | Typical Size (2-doc PSA deal) | Resident Memory |
|-------|------------------------------|-----------------|
| Deal graph | ~1,500 nodes, ~3,000 edges | ~2 MB |
| PSA doc graph | ~800 nodes, ~1,500 edges | ~1.2 MB |
| ProSupp doc graph | ~700 nodes, ~1,500 edges | ~1 MB |
| **Total** | | **~4.2 MB** (vs ~2 MB current) |

Impact: approximately 2× memory for graph storage. Acceptable for deals with 2-5 documents.

### Disk Impact

| File | Typical Size |
|------|-------------|
| `knowledge_graph.json` | ~800 KB |
| `doc_graphs/PSA.json` | ~400 KB |
| `doc_graphs/PROSUPP.json` | ~350 KB |
| **Total** | **~1.5 MB** (vs ~800 KB current) |

Impact: approximately 2× disk for graph files. Well within tolerance for local storage.

---

*End of Document — 03_DUAL_GRAPH_STRATEGY.md*
