# Phase 6: Implementation Plan
## Step-by-Step Execution Guide

**Document Version:** 2.0  
**Date:** February 16, 2026  
**Status:** Proposal - Pending Approval  
**Scope:** Detailed implementation roadmap with file paths and timeline

---

## Table of Contents
1. [Overview](#overview)
2. [Phase 0: Multi-Level Pattern Fix](#phase-0-multi-level-pattern-fix)
3. [Phase 1: ItemExtractor Framework](#phase-1-itemextractor-framework)
4. [Phase 2: Dual Vector Stores + Section Nodes](#phase-2-dual-vector-stores--section-nodes)
5. [Phase 3: REFERENCES Edges](#phase-3-references-edges)
6. [Phase 4: PageRank Boost](#phase-4-pagerank-boost)
7. [Phase 5: Iterative Multi-Hop Retrieval](#phase-5-iterative-multi-hop-retrieval)
8. [Phase 6: Section-Specific Queries](#phase-6-section-specific-queries)
9. [Phase 7: Testing & Deployment](#phase-7-testing--deployment)
10. [Timeline & Dependencies](#timeline--dependencies)
11. [Rollback Strategy](#rollback-strategy)

---

## Overview

### Implementation Philosophy

**Incremental Deployment:**
- Each phase is independently testable
- Feature flags protect production
- Rollback points at every phase
- Continuous validation with golden queries

**Quality Gates:**
- Unit tests pass before merge
- Integration tests validate cross-component interactions
- Golden query benchmark maintained or improved
- No regression in existing functionality

**Risk Mitigation:**
- Phase 0 (pattern fix) has zero risk - standalone change
- Phases 1-3 enable new capabilities without changing existing code paths
- Phase 4-5 introduce new orchestration but fallback available
- Phase 6 exposes new query types (additive only)
- Phase 7 validates entire system before production

---

### Estimated Effort

| Phase | Description | Estimated Time | Risk Level |
|-------|-------------|----------------|------------|
| Phase 0 | Multi-level pattern fix | 30 minutes | ⚪ Very Low |
| Phase 1 | ItemExtractor framework | 4-5 hours | 🟡 Low (new code) |
| Phase 2 | Dual vector stores + section nodes | 4-5 hours | 🟡 Low-Medium |
| Phase 3 | REFERENCES edges | 1-2 hours | ⚪ Very Low |
| Phase 4 | PageRank boost | 2-3 hours | 🟡 Low |
| Phase 5 | Iterative retrieval | 3-4 hours | 🟠 Medium (orchestration) |
| Phase 6 | Section queries | 1 hour | ⚪ Very Low |
| Phase 7 | Testing & deployment | 10-12 hours | 🟢 Low (validation) |
| **TOTAL** | **All phases** | **26-32 hours** | **🟢 Overall Low** |

**Timeline:** 6-8 work days (4 hours/day) with testing

---

## Phase 0: Multi-Level Pattern Fix

### Objective
Fix section pattern to support unlimited nesting (5.02.03.04, etc.) - CRITICAL for PSA parsing

### Risk Assessment
- **Risk Level:** ⚪ Very Low
- **Impact:** Standalone regex change, no dependencies
- **Rollback:** Single file revert (<1 min)
- **Testing:** Pattern validation tests

### Files to Modify

**File 1:** `backend/vector/legal_chunker.py`

**Location:** Lines 71-75

**Current Code:**
```python
SECTION_PATTERN = re.compile(
    r"(?m)^\s*(?:SECTION|Section|§)\s+(\d+(?:\.\d+)?(?:\([a-z0-9]+\))?)[.\s:]?",
    re.IGNORECASE
)
```

**Change:**
```python
SECTION_PATTERN = re.compile(
    r"(?m)^\s*(?:SECTION|Section|§)\s+(\d+(?:\.\d+)*(?:\([a-zA-Z0-9]+\))?)[.\s:]?",
    re.IGNORECASE
)
```

**Changes Explained:**
1. `(?:\.\d+)?` → `(?:\.\d+)*` - Star (*) allows UNLIMITED decimal levels
2. `[a-z0-9]` → `[a-zA-Z0-9]` - Support uppercase in parenthetical (e.g., "(III)")

**Verification:**
```python
# Add to tests/test_legal_chunker.py
def test_multi_level_section_pattern():
    """Test multi-level section number parsing."""
    pattern = SECTION_PATTERN
    
    test_cases = [
        ("Section 5", "5"),
        ("Section 5.02", "5.02"),
        ("Section 5.02.03", "5.02.03"),
        ("Section 5.02.03.04", "5.02.03.04"),
        ("Section 5.02(a)", "5.02(a)"),
        ("Section 5.02(a)(iii)", "5.02(a)(iii)"),
        ("Section 171", "171"),
    ]
    
    for text, expected in test_cases:
        match = pattern.search(text)
        assert match, f"Failed to match: {text}"
        assert match.group(1) == expected, f"Expected {expected}, got {match.group(1)}"
```

**Execution Steps:**
1. Open `backend/vector/legal_chunker.py`
2. Navigate to line 71
3. Replace pattern string as shown above
4. Save file
5. Run test: `pytest tests/test_legal_chunker.py::test_multi_level_section_pattern -v`
6. Verify: All test cases pass

**Estimated Time:** 30 minutes (includes testing)

**Success Criteria:**
- ✅ Pattern matches all test cases
- ✅ No existing tests broken
- ✅ PSA 2006-HE1 re-ingestion captures all sections

---

## Phase 1: ItemExtractor Framework

### Objective
Implement pluggable item extraction framework with legal, technical, and research domain support

### Risk Assessment
- **Risk Level:** 🟡 Low (new code, no existing code modified)
- **Impact:** Enables domain-agnostic extraction
- **Rollback:** None needed (new files only)
- **Testing:** Unit tests for each extractor (60+ tests)

### Files to Create

**1. Abstract Base Class**

**File:** `backend/extraction/__init__.py`
```python
"""Item extraction framework."""
```

**File:** `backend/extraction/item_extractor_base.py`
- **Content:** Copy from Technical Design document, Section "Abstract Base Class"
- **Lines:** ~300 lines
- **Key Components:**
  * `@dataclass Item` - Domain-agnostic item representation
  * `class ItemExtractor(ABC)` - Abstract base with `extract_items()`, `classify_item_type()`, `get_supported_types()`
  * `get_item_extractor(doc_type)` - Factory function
  * Helper methods: `_generate_item_id()`, `_split_into_sentences()`, `_extract_section_references()`

**2. Legal Item Extractor**

**File:** `backend/extraction/legal_item_extractor.py`
- **Content:** Copy from Technical Design document, Section "Legal Item Extractor"
- **Lines:** ~200 lines
- **Key Components:**
  * Legal modal verb patterns (shall, must, may, etc.)
  * Legal actor patterns (Trustee, Servicer, etc.)
  * `classify_item_type()` - Classifies as Obligation, Prohibition, Right, Definition, Condition, Statement
  * `_extract_legal_metadata()` - Extracts actors, verbs, defined terms, section refs

**3. Technical Item Extractor**

**File:** `backend/extraction/technical_item_extractor.py`
- **Content:** Copy from Technical Design document, Section "Technical Item Extractor"
- **Lines:** ~180 lines
- **Key Components:**
  * RFC 2119 requirement patterns (MUST, SHALL, etc.)
  * Procedural step patterns (Step 1, To configure, etc.)
  * `classify_item_type()` - Classifies as Requirement, Procedure, Configuration, Warning, Note, Example
  * `_extract_technical_metadata()` - Extracts parameters, commands, files, URLs

**4. Research Item Extractor**

**File:** `backend/extraction/research_item_extractor.py`
- **Content:** Copy from Technical Design document, Section "Research Item Extractor"
- **Lines:** ~170 lines
- **Key Components:**
  * Mathematical statement patterns (Theorem, Proof, Lemma, etc.)
  * Algorithmic patterns (Algorithm:, Input:, Output:, etc.)
  * `classify_item_type()` - Classifies as Theorem, Proof, Lemma, Algorithm, Observation, Hypothesis
  * `_extract_research_metadata()` - Extracts equations, citations, variables, numbers

**5. Generic Fallback Extractor**

**File:** `backend/extraction/generic_item_extractor.py`
```python
"""Generic item extractor (paragraph-level fallback)."""

from typing import List
from backend.extraction.item_extractor_base import ItemExtractor, Item


class GenericItemExtractor(ItemExtractor):
    """
    Generic fallback extractor for unsupported document types.
    
    Extracts paragraph-level items without semantic classification.
    """
    
    def __init__(self):
        super().__init__()
    
    def get_supported_types(self) -> List[str]:
        return ["Paragraph"]
    
    def extract_items(self, section_text: str, section_number: str,
                     section_heading: str, section_index: int,
                     document_id: str) -> List[Item]:
        """Extract paragraph-level items."""
        if not section_text or len(section_text.strip()) < 10:
            return []
        
        # Split by double newline
        paragraphs = section_text.split("\n\n")
        items = []
        
        for item_index, para in enumerate(paragraphs):
            para = para.strip()
            if len(para) < 10:
                continue
            
            item_id = self._generate_item_id(
                document_id, section_index, "paragraph", item_index, para
            )
            
            item = Item(
                id=item_id,
                item_type="Paragraph",
                text=para,
                document_id=document_id,
                section_number=section_number,
                section_heading=section_heading,
                section_index=section_index,
                item_index=item_index,
                metadata={}
            )
            
            items.append(item)
        
        return items
    
    def classify_item_type(self, text: str) -> str:
        return "Paragraph"
```

### Unit Tests

**File:** `tests/test_item_extractors.py`

Key test cases (60+ tests):
- **Base class tests (10)**
  * `test_generate_item_id()`
  * `test_split_into_sentences()`
  * `test_extract_section_references()`
  * `test_factory_routing_legal()`
  * `test_factory_routing_technical()`
  * `test_factory_routing_research()`
  * `test_factory_fallback()`
  
- **Legal extractor tests (20)**
  * `test_legal_classify_obligation()` - "Trustee shall establish..."
  * `test_legal_classify_prohibition()` - "Servicer shall not transfer..."
  * `test_legal_classify_right()` - "Issuer may redeem..."
  * `test_legal_classify_definition()` - "Distribution Account means..."
  * `test_legal_classify_condition()` - "If Closing Date occurs..."
  * `test_legal_extract_actors()` - Extracts Trustee, Servicer, etc.
  * `test_legal_extract_modal_verbs()` - Extracts shall, must, may
  * `test_legal_extract_defined_terms()` - Extracts quoted terms
  * `test_legal_extract_section_refs()` - Extracts Section 5.02
  * `test_legal_extract_items_from_section()` - Full section extraction
  
- **Technical extractor tests (15)**
  * `test_technical_classify_requirement()` - "System MUST validate..."
  * `test_technical_classify_procedure()` - "Step 1. Configure..."
  * `test_technical_classify_configuration()` - "Set timeout: 30s"
  * `test_technical_classify_warning()` - "WARNING: Do not..."
  * `test_technical_classify_note()` - "Note: This feature..."
  * `test_technical_classify_example()` - "Example: ```code```"
  * `test_technical_extract_parameters()` - Extracts key:value pairs
  * `test_technical_extract_commands()` - Extracts $command or `command`
  * `test_technical_extract_files()` - Extracts /path/to/file
  * `test_technical_extract_urls()` - Extracts https://...
  
- **Research extractor tests (15)**
  * `test_research_classify_theorem()` - "Theorem 1. Let..."
  * `test_research_classify_proof()` - "Proof. We show..."
  * `test_research_classify_lemma()` - "Lemma 2. Supporting..."
  * `test_research_classify_algorithm()` - "Algorithm: Input..."
  * `test_research_classify_observation()` - "We observe that..."
  * `test_research_classify_hypothesis()` - "We hypothesize..."
  * `test_research_extract_numbers()` - Extracts "Theorem 5"
  * `test_research_extract_citations()` - Extracts [Smith et al., 2020]
  * `test_research_extract_variables()` - Extracts single letters
  * `test_research_extract_equations()` - Extracts $$...$$

**Execution Steps:**
1. Create directory: `backend/extraction/`
2. Create `__init__.py`
3. Create `item_extractor_base.py` (copy from Technical Design)
4. Create `legal_item_extractor.py` (copy from Technical Design)
5. Create `technical_item_extractor.py` (copy from Technical Design)
6. Create `research_item_extractor.py` (copy from Technical Design)
7. Create `generic_item_extractor.py` (code above)
8. Create `tests/test_item_extractors.py` with 60+ test cases
9. Run tests: `pytest tests/test_item_extractors.py -v`
10. Verify: All 60+ tests pass

**Estimated Time:** 4-5 hours (includes testing)

**Success Criteria:**
- ✅ All 60+ unit tests pass
- ✅ Factory routing works for legal, technical, research domains
- ✅ Extractors produce valid Item objects with correct metadata
- ✅ Generic fallback handles unknown document types

---

## Phase 2: Dual Vector Stores + Section Nodes

### Objective
Implement dual vector stores (item-level + section-level) and build hierarchical graph with section nodes

### Risk Assessment
- **Risk Level:** 🟡 Low-Medium (new storage + graph modifications)
- **Impact:** Enables multi-granularity retrieval
- **Rollback:** Drop new collections/nodes (<2 min)
- **Testing:** Integration tests for ingestion pipeline

### Files to Create

**1. Dual Vector Store**

**File:** `backend/vector/dual_vector_store.py`
- **Content:** Copy from Technical Design document, Section "Dual Vector Store Implementation"
- **Lines:** ~300 lines
- **Key Components:**
  * `DualVectorStore` class with item_collection and section_collection
  * `add_items()` - Store items in item-level collection
  * `add_sections()` - Store sections in section-level collection
  * `search_items()` - Query item collection
  * `search_sections()` - Query section collection
  * `search()` - Unified interface with store parameter
  * `get_by_id()` - Retrieve by ID from either collection

**2. Enhanced Graph Builder**

**File:** `backend/graph/enhanced_graph_builder.py`
- **Content:** Copy from Technical Design document, Section "Section Node Builder"
- **Lines:** ~400 lines
- **Key Components:**
  * `EnhancedGraphBuilder` class
  * `build_hierarchical_graph()` - Main entry point
  * `_create_document_node()` - Create/update document node
  * `_create_section_node()` - Create Section node (NEW)
  * `_create_item_node()` - Create Item node (replaces Concept)
  * `_create_edge()` - Create typed edges (CONTAINS, NEXT, HAS_RULE, etc.)
  * `_get_edge_type_for_item()` - Map item_type to edge_type
  * `_get_edge_weight_for_item()` - Assign edge weights
  * `_create_reference_edges()` - Build REFERENCES edges (placeholder for Phase 3)

**3. Phase 6 Configuration**

**File:** `backend/common/config_phase6.py`
- **Content:** Copy from Technical Design document, Section "Configuration"
- **Lines:** ~50 lines
- **Key Components:**
  * `@dataclass Phase6Config` with feature flags and parameters
  * `phase6_config` - Global config instance

### Files to Modify

**File:** `backend/ingestion/ingestion_agent.py`

**Modifications:**
1. Import dual vector store and enhanced graph builder
2. Detect Phase 6 flag
3. Route to new pipeline if enabled

**Location:** `ingest_document()` method

**Pseudocode:**
```python
def ingest_document(doc_path: str, doc_id: str) -> dict:
    """Ingest document with Phase 6 support."""
    
    from backend.common.config_phase6 import phase6_config
    
    if phase6_config.enabled:
        # Phase 6 pipeline
        return _ingest_phase6(doc_path, doc_id)
    else:
        # Existing Phase 5 pipeline
        return _ingest_phase5(doc_path, doc_id)


def _ingest_phase6(doc_path: str, doc_id: str) -> dict:
    """Phase 6 ingestion pipeline."""
    from backend.vector.dual_vector_store import DualVectorStore
    from backend.graph.enhanced_graph_builder import EnhancedGraphBuilder
    from backend.extraction.item_extractor_base import get_item_extractor
    
    # 1. Extract text from PDF
    text = extract_pdf_text(doc_path)
    
    # 2. Classify regime (determines doc_type)
    doc_type = classify_regime(text)
    
    # 3. Parse sections
    sections = parse_sections(text)  # Returns list of {section_number, section_heading, section_text}
    
    # 4. Get appropriate item extractor
    extractor = get_item_extractor(doc_type)
    
    # 5. Extract items from each section
    all_items = []
    section_summaries = []
    
    for section_index, section_dict in enumerate(sections):
        items = extractor.extract_items(
            section_text=section_dict["section_text"],
            section_number=section_dict["section_number"],
            section_heading=section_dict["section_heading"],
            section_index=section_index,
            document_id=doc_id
        )
        
        all_items.extend(items)
        
        section_summaries.append({
            "id": f"sec:{doc_id}:{section_index:04d}",
            "section_number": section_dict["section_number"],
            "section_heading": section_dict["section_heading"],
            "section_text": section_dict["section_text"],
            "document_id": doc_id,
            "section_index": section_index,
            "item_count": len(items),
            "item_types": list(set([item.item_type for item in items]))
        })
    
    # 6. Build hierarchical graph
    graph_builder = EnhancedGraphBuilder(neo4j_uri, neo4j_user, neo4j_password)
    graph_stats = graph_builder.build_hierarchical_graph(doc_id, doc_type, sections)
    graph_builder.close()
    
    # 7. Populate dual vector stores
    vector_store = DualVectorStore(persist_directory=phase6_config.chroma_persist_dir)
    vector_store.add_items(all_items)
    vector_store.add_sections(section_summaries)
    vector_store.persist()
    
    return {
        "status": "success",
        "document_id": doc_id,
        "doc_type": doc_type,
        "sections_count": len(sections),
        "items_count": len(all_items),
        "graph_stats": graph_stats
    }
```

### Integration Tests

**File:** `tests/test_phase6_ingestion.py`

Key test cases (15 tests):
- `test_phase6_ingest_psa_2006_he1()` - Full PSA ingestion
- `test_dual_vector_store_items_added()` - Verify items in ChromaDB
- `test_dual_vector_store_sections_added()` - Verify sections in ChromaDB
- `test_hierarchical_graph_document_node()` - Verify Document node created
- `test_hierarchical_graph_section_nodes()` - Verify Section nodes created
- `test_hierarchical_graph_item_nodes()` - Verify Item nodes created
- `test_hierarchical_graph_contains_edges()` - Verify CONTAINS edges (Doc->Section, Section->Item)
- `test_hierarchical_graph_next_edges()` - Verify NEXT edges (Section->Section)
- `test_hierarchical_graph_typed_edges()` - Verify HAS_RULE, HAS_DEFINITION edges
- `test_section_summaries_metadata()` - Verify section metadata (item_count, item_types)
- `test_item_metadata_legal()` - Verify legal metadata (actors, verbs, defined_terms)
- `test_technical_document_ingestion()` - Ingest API spec (technical domain)
- `test_research_document_ingestion()` - Ingest academic paper (research domain)

**Execution Steps:**
1. Create `backend/vector/dual_vector_store.py` (copy from Technical Design)
2. Create `backend/graph/enhanced_graph_builder.py` (copy from Technical Design)
3. Create `backend/common/config_phase6.py` (copy from Technical Design)
4. Modify `backend/ingestion/ingestion_agent.py` (add Phase 6 routing)
5. Create `tests/test_phase6_ingestion.py` with 15 test cases
6. Run single PSA test: `pytest tests/test_phase6_ingestion.py::test_phase6_ingest_psa_2006_he1 -v`
7. Verify: Graph nodes/edges created, vector stores populated
8. Run all integration tests: `pytest tests/test_phase6_ingestion.py -v`
9. Verify: All 15 tests pass

**Estimated Time:** 4-5 hours (includes testing)

**Success Criteria:**
- ✅ PSA 2006-HE1 ingests successfully with Phase 6 pipeline
- ✅ Dual vector stores contain items (500-2K) and sections (50-150)
- ✅ Hierarchical graph has Document → Section → Item structure
- ✅ CONTAINS edges link Document->Section and Section->Item
- ✅ NEXT edges link sequential sections
- ✅ Typed edges (HAS_RULE, HAS_DEFINITION) created
- ✅ Cross-domain ingestion works (legal, technical, research)

---

## Phase 3: REFERENCES Edges

### Objective
Create REFERENCES edges between items (dependencies: rules → definitions)

### Risk Assessment
- **Risk Level:** ⚪ Very Low (additive change to existing graph)
- **Impact:** Enables dependency tracing
- **Rollback:** Delete REFERENCES edges (<30 sec)
- **Testing:** Graph traversal tests

### Files to Modify

**File:** `backend/graph/enhanced_graph_builder.py`

**Method:** `_create_reference_edges()` (currently placeholder)

**Current Code (Placeholder):**
```python
def _create_reference_edges(self, items: List[Item]) -> int:
    """Create REFERENCES edges between items."""
    return 0  # Placeholder
```

**Updated Code:**
```python
def _create_reference_edges(self, items: List[Item]) -> int:
    """
    Create REFERENCES edges between items based on defined term mentions.
    
    Algorithm:
    1. Find all definition items
    2. For each non-definition item, check if it mentions defined terms
    3. Create REFERENCES edge if match found
    
    Returns:
        Number of REFERENCES edges created
    """
    # Build definition lookup: term -> definition_item_id
    definitions = {}
    for item in items:
        if item.item_type == "Definition":
            # Extract defined term (first quoted phrase or first capitalized phrase)
            defined_term = self._extract_defined_term(item.text)
            if defined_term:
                definitions[defined_term.lower()] = item.id
    
    if not definitions:
        return 0  # No definitions in this section
    
    # Find references in non-definition items
    edges_created = 0
    for item in items:
        if item.item_type == "Definition":
            continue  # Skip definitions
        
        # Check if item text mentions any defined terms
        item_text_lower = item.text.lower()
        for defined_term, definition_id in definitions.items():
            if defined_term in item_text_lower:
                # Create REFERENCES edge: item -> definition
                self._create_edge(
                    from_node_id=item.id,
                    to_node_id=definition_id,
                    edge_type="REFERENCES",
                    weight=0.4
                )
                edges_created += 1
    
    return edges_created


def _extract_defined_term(self, definition_text: str) -> Optional[str]:
    """
    Extract the term being defined from definition text.
    
    Examples:
        "Distribution Account" means... → "Distribution Account"
        For purposes of this section, "Sub-Account" refers to... → "Sub-Account"
    """
    import re
    
    # Try quoted term first
    quoted = re.search(r'"([^"]+)"', definition_text)
    if quoted:
        return quoted.group(1)
    
    # Try capitalized phrase before "means"
    capitalized = re.search(r'([A-Z][A-Za-z\s]+)\s+means', definition_text)
    if capitalized:
        return capitalized.group(1).strip()
    
    return None
```

### Tests

**File:** `tests/test_reference_edges.py`

Key test cases (10 tests):
- `test_extract_defined_term_quoted()` - "Distribution Account" means...
- `test_extract_defined_term_capitalized()` - Distribution Account means...
- `test_extract_defined_term_no_match()` - No definition pattern
- `test_references_edge_created()` - Item references definition → edge created
- `test_references_edge_not_created()` - No term match → no edge
- `test_references_multiple_definitions()` - Item references 2+ definitions → 2+ edges
- `test_references_cross_section()` - Item in Section A references definition in Section B (future enhancement)
- `test_graph_traversal_references()` - Query: "What definitions does this item reference?"
- `test_dependency_chain()` - Rule → Definition1 → Definition2 (transitive dependency)

**Execution Steps:**
1. Open `backend/graph/enhanced_graph_builder.py`
2. Locate `_create_reference_edges()` method
3. Replace placeholder with full implementation
4. Add `_extract_defined_term()` helper method
5. Create `tests/test_reference_edges.py` with 10 test cases
6. Run tests: `pytest tests/test_reference_edges.py -v`
7. Verify: All 10 tests pass

**Estimated Time:** 1-2 hours (includes testing)

**Success Criteria:**
- ✅ REFERENCES edges created when item mentions defined term
- ✅ Defined terms extracted correctly (quoted and capitalized patterns)
- ✅ Graph traversal supports "What definitions does this reference?" queries
- ✅ No false positives (only create edges for actual term mentions)

---

## Phase 4: PageRank Boost

### Objective
Implement personalized PageRank computation for graph centrality boosting

### Risk Assessment
- **Risk Level:** 🟡 Low (new computation module, no existing code changed)
- **Impact:** Enhances graph signal from 5-10% to 15-30%
- **Rollback:** Disable PageRank in config (instant)
- **Testing:** PageRank computation tests

### Files to Create

**1. PageRank Computer**

**File:** `backend/graph/pagerank.py`
- **Content:** Copy from Technical Design document, Section "PageRank Boost Computation"
- **Lines:** ~150 lines
- **Key Components:**
  * `PageRankComputer` class
  * `compute()` - Main entry point
  * `_build_subgraph()` - Build 2-hop subgraph around seeds
  * `_compute_personalization()` - Query-based personalization vector
  * `_scale_scores()` - Scale to [0, 0.3] range

**2. Hybrid Reranker**

**File:** `backend/retrieval/hybrid_reranker.py`
- **Content:** Copy from Technical Design document, Section "Hybrid Reranker"
- **Lines:** ~70 lines
- **Key Components:**
  * `HybridReranker` class
  * `rerank()` - Hybrid scoring: 0.7 × content + 0.3 × pagerank

**3. Graph Interface (Helper)**

**File:** `backend/graph/graph_interface.py`

```python
"""
Graph interface for PageRank and retrieval orchestrator.

Provides convenient methods for graph operations without coupling
to Neo4j driver directly.
"""

from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase
import logging


class GraphInterface:
    """
    Interface for graph operations used by PageRank and retrieval.
    """
    
    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str):
        """Initialize graph interface."""
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        self.logger = logging.getLogger(__name__)
    
    def bfs_expand(self, start_node_id: str, max_depth: int = 2,
                  edge_types: Optional[List[str]] = None,
                  avoid_nodes: Optional[set] = None,
                  max_neighbors: int = 20) -> List[Dict[str, Any]]:
        """
        BFS expansion from start node.
        
        Args:
            start_node_id: Starting node ID
            max_depth: Maximum BFS depth (default: 2)
            edge_types: Edge types to follow (e.g., ['CONTAINS', 'NEXT'])
            avoid_nodes: Set of node IDs to skip
            max_neighbors: Maximum neighbors to return
            
        Returns:
            List of neighbor dicts with keys: id, type, distance
        """
        avoid_nodes = avoid_nodes or set()
        
        # Build edge type filter
        if edge_types:
            edge_filter = " OR ".join([f"type(r) = '{et}'" for et in edge_types])
            edge_clause = f"WHERE {edge_filter}"
        else:
            edge_clause = ""
        
        query = f"""
        MATCH path = (start {{id: $start_id}})-[r*1..{max_depth}]-(neighbor)
        {edge_clause}
        WHERE NOT neighbor.id IN $avoid_ids
        RETURN DISTINCT neighbor.id AS id, labels(neighbor)[0] AS type, length(path) AS distance
        ORDER BY distance ASC
        LIMIT $max_neighbors
        """
        
        with self.driver.session() as session:
            result = session.run(query,
                               start_id=start_node_id,
                               avoid_ids=list(avoid_nodes),
                               max_neighbors=max_neighbors)
            
            neighbors = [
                {"id": record["id"], "type": record["type"], "distance": record["distance"]}
                for record in result
            ]
        
        return neighbors
    
    def get_neighbors(self, node_id: str) -> List[Dict[str, Any]]:
        """
        Get immediate neighbors of node.
        
        Returns:
            List of dicts with keys: id, type, weight
        """
        query = """
        MATCH (n {id: $node_id})-[r]-(neighbor)
        RETURN neighbor.id AS id, labels(neighbor)[0] AS type, r.weight AS weight
        """
        
        with self.driver.session() as session:
            result = session.run(query, node_id=node_id)
            neighbors = [
                {"id": record["id"], "type": record["type"], "weight": record["weight"]}
                for record in result
            ]
        
        return neighbors
    
    def get_node_text(self, node_id: str) -> Optional[str]:
        """
        Get text content of node.
        
        Returns:
            Node text or None if not found
        """
        query = """
        MATCH (n {id: $node_id})
        RETURN n.text AS text
        """
        
        with self.driver.session() as session:
            result = session.run(query, node_id=node_id)
            record = result.single()
            return record["text"] if record else None
    
    def get_subgraph(self, seed_nodes: List[str], max_depth: int = 2, max_nodes: int = 1000):
        """
        Get subgraph as NetworkX DiGraph.
        
        Used by PageRank computation.
        """
        import networkx as nx
        
        subgraph = nx.DiGraph()
        visited = set()
        
        for seed_id in seed_nodes:
            if len(visited) >= max_nodes:
                break
            
            # Get neighbors up to max_depth
            neighbors = self.bfs_expand(
                start_node_id=seed_id,
                max_depth=max_depth,
                avoid_nodes=visited,
                max_neighbors=max_nodes - len(visited)
            )
            
            for neighbor in neighbors:
                # Add edge (approximate weight)
                subgraph.add_edge(seed_id, neighbor['id'], weight=0.5)
                visited.add(seed_id)
                visited.add(neighbor['id'])
        
        return subgraph
    
    def close(self):
        """Close Neo4j driver."""
        self.driver.close()
```

### Tests

**File:** `tests/test_pagerank.py`

Key test cases (12 tests):
- `test_pagerank_compute_single_node()` - Single seed node
- `test_pagerank_compute_multiple_nodes()` - Multiple seed nodes
- `test_pagerank_personalization()` - Verify query-based personalization
- `test_pagerank_scaled_to_max()` - Scores scaled to [0, 0.3]
- `test_pagerank_subgraph_size_limit()` - Respects max_nodes=1000
- `test_pagerank_with_empty_graph()` - Handles empty graph gracefully
- `test_hybrid_reranker()` - Content + PageRank scoring
- `test_hybrid_reranker_weights()` - Verify 0.7 + 0.3 weights
- `test_hybrid_reranker_sorting()` - Results sorted by confidence desc
- `test_graph_interface_bfs_expand()` - BFS expansion
- `test_graph_interface_get_neighbors()` - Immediate neighbors
- `test_graph_interface_get_node_text()` - Node text retrieval

**Execution Steps:**
1. Create `backend/graph/graph_interface.py` (code above)
2. Create `backend/graph/pagerank.py` (copy from Technical Design)
3. Create `backend/retrieval/hybrid_reranker.py` (copy from Technical Design)
4. Create `tests/test_pagerank.py` with 12 test cases
5. Run tests: `pytest tests/test_pagerank.py -v`
6. Verify: All 12 tests pass

**Estimated Time:** 2-3 hours (includes testing)

**Success Criteria:**
- ✅ PageRank computes scores for seed nodes
- ✅ Personalization vector based on query similarity
- ✅ Scores scaled to [0, 0.3] range
- ✅ Subgraph size limited to 1000 nodes (performance)
- ✅ Hybrid reranker combines content + PageRank with 0.7/0.3 weights
- ✅ Graph interface provides BFS expansion and neighbor queries

---

## Phase 5: Iterative Multi-Hop Retrieval

### Objective
Implement iterative retrieval orchestrator with alternating vector store queries and graph expansion

### Risk Assessment
- **Risk Level:** 🟠 Medium (complex orchestration logic)
- **Impact:** Enables multi-hop reasoning and adaptive refinement
- **Rollback:** Set `PHASE6_ENABLED=false` (instant)
- **Testing:** End-to-end retrieval tests with PSA queries

### Files to Create

**1. Iterative Retrieval Orchestrator**

**File:** `backend/retrieval/iterative_orchestrator.py`
- **Content:** Copy from Technical Design document, Section "Iterative Retrieval Orchestrator"
- **Lines:** ~200 lines
- **Key Components:**
  * `IterativeRetrievalOrchestrator` class
  * `retrieve()` - Main iterative loop
  * Alternating strategy: iteration % 2 == 0 → items, else → sections
  * Exit criteria: confidence > 0.90, improvement < 0.05, max iterations

### Files to Modify

**File:** `backend/retrieval/retrieval_service.py`

**Method:** `query()` - Main query entry point

**Current Code:**
```python
def query(query_text: str, top_k: int = 5, regime: Optional[str] = None) -> List[dict]:
    """Legacy one-shot query."""
    # Existing implementation
    ...
```

**Updated Code:**
```python
def query(query_text: str, top_k: int = 5, regime: Optional[str] = None) -> List[dict]:
    """
    Main query interface with Phase 6 support.
    
    Routes to iterative retrieval if Phase 6 enabled, else legacy one-shot.
    """
    from backend.common.config_phase6 import phase6_config
    
    if phase6_config.enabled:
        # Phase 6: Iterative multi-hop retrieval
        return _query_phase6(query_text, top_k, regime)
    else:
        # Phase 5: Legacy one-shot retrieval
        return _query_phase5(query_text, top_k, regime)


def _query_phase6(query_text: str, top_k: int, regime: Optional[str]) -> List[dict]:
    """Phase 6 iterative retrieval."""
    from backend.vector.dual_vector_store import DualVectorStore
    from backend.graph.graph_interface import GraphInterface
    from backend.graph.pagerank import PageRankComputer
    from backend.retrieval.hybrid_reranker import HybridReranker
    from backend.retrieval.iterative_orchestrator import IterativeRetrievalOrchestrator
    from sentence_transformers import SentenceTransformer
    
    # Initialize components
    vector_store = DualVectorStore(persist_directory=phase6_config.chroma_persist_dir)
    graph = GraphInterface(neo4j_uri, neo4j_user, neo4j_password)
    embedding_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
    pagerank_computer = PageRankComputer(graph, embedding_model)
    reranker = HybridReranker(pagerank_computer)
    
    orchestrator = IterativeRetrievalOrchestrator(vector_store, graph, reranker)
    
    # Retrieve
    results = orchestrator.retrieve(
        query=query_text,
        max_iterations=phase6_config.max_iterations,
        min_confidence=phase6_config.min_confidence,
        min_improvement=phase6_config.min_improvement,
        top_k=top_k
    )
    
    # Cleanup
    graph.close()
    
    return results


def _query_phase5(query_text: str, top_k: int, regime: Optional[str]) -> List[dict]:
    """Legacy one-shot retrieval (existing implementation)."""
    # Existing code unchanged
    ...
```

### Tests

**File:** `tests/test_iterative_retrieval.py`

Key test cases (20 tests):
- **Basic functionality (5)**
  * `test_orchestrator_initialization()` - Components initialized
  * `test_single_iteration()` - 1 iteration execution
  * `test_multiple_iterations()` - 2-3 iterations
  * `test_alternating_stores()` - Iteration 0→items, 1→sections, 2→items
  * `test_exit_on_max_iterations()` - Hits 3 iterations limit
  
- **Exit criteria (5)**
  * `test_exit_on_high_confidence()` - Confidence > 0.90 → exit
  * `test_exit_on_diminishing_returns()` - Improvement < 0.05 → exit
  * `test_no_early_exit_if_improving()` - Keeps iterating if improving
  * `test_confidence_tracking()` - confidence increases per iteration
  * `test_visited_nodes_dedupe()` - No duplicate node visits
  
- **Graph expansion (5)**
  * `test_bfs_expansion_depth2()` - 2-hop neighbors found
  * `test_expansion_respects_avoid_nodes()` - Skips visited nodes
  * `test_expansion_edge_types()` - Follows CONTAINS, NEXT, REFERENCES
  * `test_expansion_max_neighbors()` - Limits to 20 neighbors/node
  * `test_empty_expansion()` - Handles nodes with no neighbors
  
- **Hybrid reranking (5)**
  * `test_reranking_combines_results()` - Merges vector + expanded results
  * `test_reranking_deduplicates()` - Removes duplicate IDs
  * `test_reranking_sorts_by_confidence()` - Descending confidence order
  * `test_reranking_top_k_kept()` - Keeps top 50 for next iteration
  * `test_pagerank_boost_applied()` - PageRank boosts scores

- **Golden query validation (PSA 2006-HE1)**
  * `test_psa_query_distribution_account()` - "What is Distribution Account?" → confidence > 0.90
  * `test_psa_query_trustee_obligations()` - "What must Trustee establish?" → confidence > 0.90
  * `test_psa_query_section_specific()` - "What's in Section 5.02?" → retrieves all items
  * `test_psa_query_comparative()` - "Compare Trustee vs Servicer duties" → retrieves both
  * `test_psa_query_multi_hop()` - "What accounts and what are sub-account rules?" → 2-3 iterations

**Execution Steps:**
1. Create `backend/retrieval/iterative_orchestrator.py` (copy from Technical Design)
2. Modify `backend/retrieval/retrieval_service.py` (add Phase 6 routing)
3. Create `tests/test_iterative_retrieval.py` with 20 test cases
4. Run single test: `pytest tests/test_iterative_retrieval.py::test_psa_query_distribution_account -v`
5. Verify: Query returns confidence > 0.90
6. Run all tests: `pytest tests/test_iterative_retrieval.py -v`
7. Verify: All 20 tests pass

**Estimated Time:** 3-4 hours (includes testing)

**Success Criteria:**
- ✅ Orchestrator executes 1-3 iterations
- ✅ Alternates between item store (odd) and section store (even)
- ✅ BFS expansion finds 2-hop neighbors
- ✅ Hybrid reranking combines content + PageRank
- ✅ Exit criteria work correctly (confidence, diminishing returns, max iterations)
- ✅ PSA golden queries achieve confidence > 0.90
- ✅ No regressions in existing one-shot retrieval (Phase 5 path still works)

---

## Phase 6: Section-Specific Queries

### Objective
Expose section-specific query methods (additive API, no breaking changes)

### Risk Assessment
- **Risk Level:** ⚪ Very Low (additive API only)
- **Impact:** Enables new query types (section-specific, sequential navigation)
- **Rollback:** None needed (new methods only)
- **Testing:** API tests for new methods

### Files to Modify

**File:** `backend/retrieval/retrieval_service.py`

**Add new methods:**

```python
def query_section(section_number: str, document_id: str) -> Dict[str, Any]:
    """
    Retrieve all items in a specific section.
    
    Args:
        section_number: Section number (e.g., "5.02")
        document_id: Document ID
        
    Returns:
        Dict with keys: section_info, items
    """
    from backend.common.config_phase6 import phase6_config
    from backend.vector.dual_vector_store import DualVectorStore
    from backend.graph.graph_interface import GraphInterface
    
    if not phase6_config.enabled:
        raise NotImplementedError("Section queries require Phase 6")
    
    # Get section node
    graph = GraphInterface(neo4j_uri, neo4j_user, neo4j_password)
    section_id = f"sec:{document_id}:*"  # Use pattern matching
    
    # Query graph for section
    query = """
    MATCH (s:Section {section_number: $section_number, document_id: $document_id})
    RETURN s.id AS id, s.section_heading AS heading, s.item_count AS item_count
    """
    with graph.driver.session() as session:
        result = session.run(query, section_number=section_number, document_id=document_id)
        section = result.single()
    
    if not section:
        return {"error": f"Section {section_number} not found in {document_id}"}
    
    # Get all items in section
    query = """
    MATCH (s:Section {id: $section_id})-[r]->(item:Item)
    RETURN item.id AS id, item.text AS text, item.item_type AS item_type,
           item.item_index AS item_index
    ORDER BY item.item_index ASC
    """
    with graph.driver.session() as session:
        result = session.run(query, section_id=section["id"])
        items = [dict(record) for record in result]
    
    graph.close()
    
    return {
        "section_number": section_number,
        "section_heading": section["heading"],
        "item_count": section["item_count"],
        "items": items
    }


def get_next_section(section_number: str, document_id: str) -> Optional[Dict[str, Any]]:
    """
    Get next sequential section.
    
    Args:
        section_number: Current section number
        document_id: Document ID
        
    Returns:
        Next section dict or None if last section
    """
    from backend.common.config_phase6 import phase6_config
    from backend.graph.graph_interface import GraphInterface
    
    if not phase6_config.enabled:
        raise NotImplementedError("Section navigation requires Phase 6")
    
    graph = GraphInterface(neo4j_uri, neo4j_user, neo4j_password)
    
    # Query NEXT edge
    query = """
    MATCH (s:Section {section_number: $section_number, document_id: $document_id})-[:NEXT]->(next:Section)
    RETURN next.section_number AS section_number, next.section_heading AS heading
    """
    with graph.driver.session() as session:
        result = session.run(query, section_number=section_number, document_id=document_id)
        next_section = result.single()
    
    graph.close()
    
    if next_section:
        return {
            "section_number": next_section["section_number"],
            "section_heading": next_section["heading"]
        }
    else:
        return None


def get_item_dependencies(item_id: str) -> List[Dict[str, Any]]:
    """
    Get definitions referenced by an item.
    
    Args:
        item_id: Item node ID
        
    Returns:
        List of definition items this item references
    """
    from backend.common.config_phase6 import phase6_config
    from backend.graph.graph_interface import GraphInterface
    
    if not phase6_config.enabled:
        raise NotImplementedError("Dependency tracing requires Phase 6")
    
    graph = GraphInterface(neo4j_uri, neo4j_user, neo4j_password)
    
    # Query REFERENCES edges
    query = """
    MATCH (item:Item {id: $item_id})-[:REFERENCES]->(def:Item {item_type: 'Definition'})
    RETURN def.id AS id, def.text AS text, def.section_number AS section_number
    """
    with graph.driver.session() as session:
        result = session.run(query, item_id=item_id)
        dependencies = [dict(record) for record in result]
    
    graph.close()
    
    return dependencies
```

### CLI Integration

**File:** `cli/main.py`

**Add new commands:**

```python
@click.command()
@click.argument('section_number')
@click.option('--doc-id', required=True, help='Document ID')
def section(section_number: str, doc_id: str):
    """Query specific section (Phase 6 only)."""
    from backend.retrieval.retrieval_service import query_section
    
    result = query_section(section_number, doc_id)
    
    if "error" in result:
        click.echo(f"Error: {result['error']}", err=True)
        return
    
    click.echo(f"\nSection {result['section_number']}: {result['section_heading']}")
    click.echo(f"Items: {result['item_count']}\n")
    
    for item in result['items']:
        click.echo(f"{item['item_index']}. [{item['item_type']}] {item['text']}\n")


@click.command()
@click.argument('section_number')
@click.option('--doc-id', required=True, help='Document ID')
def next_section(section_number: str, doc_id: str):
    """Get next section (Phase 6 only)."""
    from backend.retrieval.retrieval_service import get_next_section
    
    next_sec = get_next_section(section_number, doc_id)
    
    if next_sec:
        click.echo(f"Next section: {next_sec['section_number']} - {next_sec['section_heading']}")
    else:
        click.echo("No next section (end of document)")


# Register commands
cli.add_command(section)
cli.add_command(next_section)
```

### Tests

**File:** `tests/test_section_queries.py`

Key test cases (10 tests):
- `test_query_section()` - Retrieve all items in Section 5.02
- `test_query_section_not_found()` - Non-existent section → error
- `test_query_section_item_order()` - Items returned in item_index order
- `test_get_next_section()` - Section 5.02 → Section 5.03
- `test_get_next_section_last()` - Last section → None
- `test_get_item_dependencies()` - Item references 2 definitions → 2 results
- `test_get_item_dependencies_none()` - Item references no definitions → empty list
- `test_cli_section_command()` - CLI: `kts section 5.02 --doc-id psa_2006_he1`
- `test_cli_next_section_command()` - CLI: `kts next-section 5.02 --doc-id psa_2006_he1`

**Execution Steps:**
1. Add new methods to `backend/retrieval/retrieval_service.py`
2. Add CLI commands to `cli/main.py`
3. Create `tests/test_section_queries.py` with 10 test cases
4. Run tests: `pytest tests/test_section_queries.py -v`
5. Test CLI: `python cli/main.py section 5.02 --doc-id psa_2006_he1`
6. Verify: Section items displayed correctly

**Estimated Time:** 1 hour

**Success Criteria:**
- ✅ `query_section()` returns all items in section
- ✅ `get_next_section()` returns next sequential section via NEXT edge
- ✅ `get_item_dependencies()` returns definitions referenced by item
- ✅ CLI commands work and display results
- ✅ All 10 tests pass

---

## Phase 7: Testing & Deployment

### Objective
Comprehensive testing, migration of existing documents, and production deployment

### Risk Assessment
- **Risk Level:** 🟢 Low (validation phase)
- **Impact:** Ensures quality and stability before production
- **Rollback:** Feature flag disables Phase 6 instantly
- **Testing:** Full test suite (100+ tests)

### Testing Checklist

**Unit Tests (60+ tests)**
- ✅ ItemExtractor framework (60 tests) - Phase 1
- ✅ PageRank computation (12 tests) - Phase 4
- ✅ Hybrid reranker (5 tests) - Phase 4
- ✅ Reference edges (10 tests) - Phase 3
- **Total:** 87 unit tests

**Integration Tests (30+ tests)**
- ✅ Phase 6 ingestion (15 tests) - Phase 2
- ✅ Iterative retrieval (20 tests) - Phase 5
- ✅ Section queries (10 tests) - Phase 6
- **Total:** 45 integration tests

**Cross-Domain Validation (9 tests)**

**File:** `tests/test_cross_domain.py`

Key test cases:
- **Legal domain (3)**
  * `test_legal_psa_2006_he1()` - PSA ingestion + query (confidence > 0.90)
  * `test_legal_indenture()` - Indenture ingestion + query
  * `test_legal_regulatory_guidance()` - SEC guidance ingestion + query
  
- **Technical domain (3)**
  * `test_technical_api_spec()` - API documentation ingestion + query
  * `test_technical_user_manual()` - User manual ingestion + query
  * `test_technical_system_design()` - System design doc ingestion + query
  
- **Research domain (3)**
  * `test_research_academic_paper()` - Academic paper ingestion + query (CS theory)
  * `test_research_thesis()` - PhD thesis ingestion + query (math)
  * `test_research_journal_article()` - Journal article ingestion + query (physics)

**Performance Benchmarks (5 tests)**

**File:** `tests/test_performance_benchmarks.py`

Key test cases:
- `test_query_latency_p50()` - Median latency < 250ms
- `test_query_latency_p95()` - P95 latency < 500ms
- `test_query_latency_p99()` - P99 latency < 750ms
- `test_ingestion_time()` - PSA ingestion < 2 minutes
- `test_pagerank_latency()` - PageRank computation < 100ms

**Golden Query Validation (10 tests)**

**File:** `tests/test_golden_queries_phase6.py`

PSA 2006-HE1 queries:
- `test_golden_query_01()` - "What is Distribution Account?" → confidence > 0.90
- `test_golden_query_02()` - "What must Trustee establish?" → confidence > 0.90
- `test_golden_query_03()` - "What are Servicer obligations?" → confidence > 0.85
- `test_golden_query_04()` - "What are sub-account requirements?" → confidence > 0.85
- `test_golden_query_05()` - "What is Closing Date?" → confidence > 0.95 (definition)
- `test_golden_query_06()` - "What's in Section 5.02?" → retrieves 8 items
- `test_golden_query_07()` - "Compare Trustee vs Servicer duties" → retrieves both
- `test_golden_query_08()` - "What definitions does obligation reference?" → REFERENCES edges
- `test_golden_query_09()` - "What happens after Closing Date?" → multi-hop
- `test_golden_query_10()` - "Show next section after 5.02" → Section 5.03

**Regression Tests (20 tests)**

**File:** `tests/test_regression_phase6.py`

Ensure Phase 5 functionality unchanged:
- `test_phase5_query_still_works()` - Legacy query with `PHASE6_ENABLED=false`
- `test_phase5_confidence_maintained()` - Phase 5 confidence scores unchanged
- `test_phase5_ingestion_backward_compatible()` - Old ingest format still works
- `test_phase5_cli_commands()` - All existing CLI commands work
- `test_phase5_vsix_integration()` - VSIX extension still functional
- ... (15 more regression tests)

### Migration Plan

**Objective:** Migrate existing 500+ documents to Phase 6 schema

**Tool:** `backend/migration/phase6_migrator.py` (created in Phase 2)

**Migration Script:**

**File:** `scripts/migrate_to_phase6.py`

```python
"""
Migrate existing documents to Phase 6 schema.

Usage:
    python scripts/migrate_to_phase6.py --all
    python scripts/migrate_to_phase6.py --doc-id psa_2006_he1
"""

import click
import logging
from backend.migration.phase6_migrator import Phase6Migrator
from backend.graph.enhanced_graph_builder import EnhancedGraphBuilder
from backend.vector.dual_vector_store import DualVectorStore
from backend.common.config_phase6 import phase6_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option('--all', is_flag=True, help='Migrate all documents')
@click.option('--doc-id', help='Migrate single document')
@click.option('--batch-size', default=10, help='Batch size for bulk migration')
def migrate(all: bool, doc_id: str, batch_size: int):
    """Migrate documents to Phase 6."""
    
    if not phase6_config.enabled:
        logger.error("Phase 6 not enabled! Set PHASE6_ENABLED=true")
        return
    
    # Initialize components
    graph_builder = EnhancedGraphBuilder(neo4j_uri, neo4j_user, neo4j_password)
    vector_store = DualVectorStore(persist_directory=phase6_config.chroma_persist_dir)
    migrator = Phase6Migrator(graph_builder, vector_store)
    
    if doc_id:
        # Migrate single document
        logger.info(f"Migrating document: {doc_id}")
        # Load document from Phase 5 ingest output
        doc_data = load_document_data(doc_id)
        migrator.migrate_document(doc_id, doc_data['doc_type'], doc_data['sections'])
        logger.info(f"Migration complete: {doc_id}")
    
    elif all:
        # Migrate all documents
        logger.info("Migrating all documents...")
        doc_ids = get_all_document_ids()
        
        total = len(doc_ids)
        for i, doc_id in enumerate(doc_ids):
            logger.info(f"Migrating {i+1}/{total}: {doc_id}")
            
            try:
                doc_data = load_document_data(doc_id)
                migrator.migrate_document(doc_id, doc_data['doc_type'], doc_data['sections'])
            except Exception as e:
                logger.error(f"Failed to migrate {doc_id}: {e}")
                continue
            
            # Batch persist
            if (i + 1) % batch_size == 0:
                vector_store.persist()
                logger.info(f"Batch {(i+1)//batch_size} persisted")
        
        # Final persist
        vector_store.persist()
        logger.info(f"Migration complete: {total} documents")
    
    else:
        logger.error("Must specify --all or --doc-id")


if __name__ == '__main__':
    migrate()
```

**Migration Steps:**
1. **Backup Phase 5 data** (Neo4j dump, ChromaDB copy)
2. **Dry run:** Migrate 10 sample documents
3. **Validation:** Run golden queries on migrated documents
4. **Bulk migration:** Migrate all 500+ documents in batches of 10
5. **Final validation:** Run full test suite
6. **Cutover:** Enable `PHASE6_ENABLED=true`

**Estimated Time:** 10-12 hours (2-3 hours/500 docs = 36-54 hours @ 20 docs/min)

### Deployment Steps

**1. Pre-Deployment Validation**
- ✅ All 159 tests pass (87 unit + 45 integration + 9 cross-domain + 5 performance + 10 golden + 20 regression)
- ✅ Migration dry run successful (10 sample docs)
- ✅ Performance benchmarks met (P95 < 500ms)
- ✅ Golden query confidence > 0.90

**2. Infrastructure Setup**
- Neo4j database ready (Phase 6 schema)
- ChromaDB Phase 6 collection created
- Environment variables set:
  ```bash
  PHASE6_ENABLED=true
  PHASE6_CHROMA_DIR=./chroma_phase6
  PHASE6_MAX_ITERATIONS=3
  PHASE6_MIN_CONFIDENCE=0.90
  PHASE6_MIN_IMPROVEMENT=0.05
  ```

**3. Phased Rollout**

**Week 1: Alpha (Internal)**
- Enable Phase 6 for internal team only
- Monitor query confidence, latency, errors
- Gather feedback on new features

**Week 2: Beta (10% Users)**
- Enable Phase 6 for 10% of users via feature flag
- A/B test: Phase 5 vs Phase 6 query confidence
- Monitor performance metrics

**Week 3: Gradual Rollout (50% → 100%)**
- Increase to 50% users
- Monitor for 3 days
- If stable, increase to 100%

**4. Monitoring**
- Query confidence (target: > 0.90 avg)
- Query latency (target: P95 < 500ms)
- Iteration count distribution (target: avg 2.3)
- PageRank boost contribution (target: 15-30%)
- Error rate (target: < 0.1%)

**5. Rollback Plan**
- **Immediate:** Set `PHASE6_ENABLED=false` (reverts to Phase 5, < 1 min)
- **Code Rollback:** Revert Git commit (< 5 min)
- **Data Rollback:** Restore Neo4j from backup (< 30 min)
- **Full Restore:** Restore Neo4j + ChromaDB from backup (< 2 hours)

**Estimated Time:** 10-12 hours (setup + migration + validation)

**Success Criteria:**
- ✅ All 159 tests pass
- ✅ Migration successful (500+ documents)
- ✅ Query confidence > 0.90 (PSA 2006-HE1)
- ✅ Query latency P95 < 500ms
- ✅ No regressions in Phase 5 functionality
- ✅ Cross-domain queries work (legal, technical, research)

---

## Timeline & Dependencies

### Critical Path

```
Phase 0 (30 min) → Phase 1 (4-5 hrs) → Phase 2 (4-5 hrs) → Phase 4 (2-3 hrs) → Phase 5 (3-4 hrs) → Phase 7 (10-12 hrs)
                                                   ↓
                                            Phase 3 (1-2 hrs) → Phase 6 (1 hr) → Phase 7
```

**Critical Path Phases:** 0 → 1 → 2 → 4 → 5 → 7 (Total: 24-30 hours)

**Parallel Phases:**
- Phase 3 (REFERENCES) can run in parallel with Phase 4 after Phase 2 complete
- Phase 6 (Section queries) can run after Phase 5

### Daily Schedule (4 hours/day)

**Day 1: Foundation**
- Phase 0: Multi-level pattern fix (30 min)
- Phase 1: ItemExtractor framework (3.5 hrs)
- **Deliverable:** Item extraction working for legal, technical, research domains

**Day 2: Storage & Graph**
- Phase 2: Dual vector stores + section nodes (4 hrs)
- **Deliverable:** Hierarchical graph built, dual vector stores populated

**Day 3: Graph Enhancement**
- Phase 3: REFERENCES edges (1 hr)
- Phase 4: PageRank boost (3 hrs)
- **Deliverable:** Graph with dependency edges, PageRank computation working

**Day 4: Iterative Retrieval**
- Phase 5: Iterative multi-hop retrieval (4 hrs)
- **Deliverable:** End-to-end iterative retrieval with alternating stores

**Day 5: API & Basic Testing**
- Phase 6: Section-specific queries (1 hr)
- Unit tests (Phase 0-6) (3 hrs)
- **Deliverable:** All new APIs exposed, unit tests pass

**Day 6: Integration Testing**
- Integration tests (4 hrs)
- **Deliverable:** End-to-end flows validated

**Day 7: Cross-Domain & Performance**
- Cross-domain validation (2 hrs)
- Performance benchmarks (2 hrs)
- **Deliverable:** Legal, technical, research domains working; performance targets met

**Day 8: Migration & Deployment**
- Migration (2 hrs for samples, 6 hrs for all 500+ docs)
- Golden query validation (1 hr)
- Regression tests (1 hr)
- **Deliverable:** Full system migrated, validated, ready for production

---

## Rollback Strategy

### Rollback Levels

**Level 1: Instant (< 1 minute) - Feature Flag**
```bash
# Disable Phase 6, revert to Phase 5
export PHASE6_ENABLED=false
# Or update config file
echo "PHASE6_ENABLED=false" > config/.env
# Restart services
```
**Scope:** Reverts query path to Phase 5, no data loss

---

**Level 2: Fast (< 5 minutes) - Code Rollback**
```bash
# Revert Git commit
git revert <phase6_commit_hash>
git push

# Restart services
systemctl restart kts_backend
systemctl restart kts_vsix_server
```
**Scope:** Removes Phase 6 code, Phase 5 resumes

---

**Level 3: Medium (< 30 minutes) - Graph Rollback**
```bash
# Restore Neo4j from pre-Phase-6 backup
neo4j-admin restore --from=/backups/neo4j_phase5.backup --database=neo4j --force

# Restart Neo4j
systemctl restart neo4j
```
**Scope:** Restores graph to Phase 5 schema, loses Phase 6 nodes/edges

---

**Level 4: Full (< 2 hours) - Complete Data Restore**
```bash
# Restore Neo4j
neo4j-admin restore --from=/backups/neo4j_phase5.backup --database=neo4j --force

# Restore ChromaDB
rm -rf ./chroma_phase6
cp -r /backups/chroma_phase5 ./chroma

# Restart all services
systemctl restart neo4j
systemctl restart kts_backend
systemctl restart kts_vsix_server
```
**Scope:** Full restoration to Phase 5 state

---

### Rollback Decision Matrix

| Issue | Rollback Level | Justification |
|-------|---------------|---------------|
| Query latency > 1s (P95) | Level 1 (Feature Flag) | Performance unacceptable |
| Confidence dropping < 0.80 | Level 1 (Feature Flag) | Quality regression |
| Critical bug (crash, data loss) | Level 2 (Code Rollback) | Stability issue |
| Graph corruption | Level 3 (Graph Rollback) | Data integrity |
| Unrecoverable state | Level 4 (Full Restore) | Nuclear option |

---

## Related Documents

- [Executive Summary](01_EXECUTIVE_SUMMARY.md) - Business case and ROI
- [System Design](02_SYSTEM_DESIGN.md) - High-level architecture
- [Architecture Upgrade](03_ARCHITECTURE_UPGRADE.md) - Detailed architecture
- [Technical Design](04_TECHNICAL_DESIGN.md) - Implementation-ready code
- [Testing Plan](06_TESTING_PLAN.md) - Comprehensive validation strategy

---

*This implementation plan provides a detailed, step-by-step roadmap for Phase 6 execution. Each phase is independently testable with clear success criteria and rollback procedures.*
