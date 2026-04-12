# Phase F: Definition Resolution Engine (Phase 7 Modules 1-5)

**Created:** 2026-02-20  
**Status:** APPROVED — Ready for Implementation  
**Effort:** 2-3 weeks (Module per week, iterative)  
**Priority:** P2 — After Phases A-E complete  
**Source:** `docs/phase7/DESIGN_DISCUSSION.md` (764 lines of design rationale)

---

## 1. Problem Statement

When a finance professional asks "What does Current Interest mean for Class I-A-1?", the correct answer requires resolving **23 dependent defined terms** across **4 levels of nesting**. Our current system (Phase 6) resolves **1 level** of definition injection. The remaining 22 terms are invisible.

### What Current System Does

```
User: "What does Current Interest mean?"
System: "Current Interest means [definition text]. 
         Certificate Principal Balance means [definition text]."
         ← stops at depth 1
```

### What We Need

```
User: "What does Current Interest mean?"
System: "Current Interest is defined in Section 1.01 as the interest 
         accrued on the Certificate Principal Balance during the 
         Accrual Period (the period between Distribution Dates) at 
         the applicable Pass-Through Rate, plus any recovered 
         voidable preferences, minus:
         (i) Prepayment Interest Shortfalls not covered by 
             Compensating Interest, and
         (ii) Relief Act Interest Shortfalls during the Due Period.
         
         Where:
         - Certificate Principal Balance = Initial CPB (from the 
           Preliminary Statement) reduced by principal distributions, 
           Realized Losses, and Applied Realized Loss Amounts
         - Pass-Through Rate = 5.25% fixed (for Class I-A-1)
         - Accrual Period = Distribution Date to Distribution Date
         - Distribution Date = 25th of each month (or next Business Day)
         
         The full dependency chain involves 23 defined terms resolved 
         from 4 levels of cross-references.
         
         [Full resolution tree available via /define Current Interest --deep]"
```

---

## 2. Scope: Modules 1-5 Only

Per the design discussion decision, we implement only Modules 1-5:

| Module | Name | Difficulty | Status |
|--------|------|-----------|--------|
| **1** | Term Dictionary Extraction | LOW | In scope |
| **2** | Preliminary Statement Table Extraction | MEDIUM | In scope |
| **3** | Reference Scanning (DEPENDS_ON Edges) | LOW | In scope |
| **4** | Dependency Graph Construction | LOW | In scope |
| **5** | Full Resolution Tree (Pre-computed) | LOW | In scope |
| 6 | Term Classification (C/V/F) | MEDIUM | Future |
| 7 | Formula Extraction (English → Math) | HIGH | Future |
| 8 | Code Generation (Math → Python) | MEDIUM | Future |

Modules 6-8 are deferred — they represent the "PSA compiler" vision. Modules 1-5 alone deliver massive value: the complete dependency tree for any defined term, pre-computed at ingestion, available instantly at query time.

---

## 3. Architecture Overview

### 3.1 Ingestion-Time Pipeline

```
PSA Document
  ↓
[Module 1] Term Dictionary Extraction
  → {term_name: str → definition_text: str}  (300+ entries)
  ↓
[Module 2] Preliminary Statement Table Extraction
  → Structured table: class → initial_cpb, rate, notional_flag, etc.
  ↓
[Module 3] Reference Scanning
  → For each definition: set of referenced term names
  → DEPENDS_ON edges + CROSS_REF edges
  ↓
[Module 4] Dependency Graph Construction
  → NetworkX DiGraph with DEPENDS_ON edges
  → DAG validation, topological sort, depth metric
  ↓
[Module 5] Resolution Tree Pre-computation
  → JSON tree attribute on each graph node
  → DFS with memoization, O(V + E)
  ↓
Stored in: knowledge graph (.json) + metadata on vector store items
```

### 3.2 Query-Time Enhancement

```
User asks: "What does Current Interest mean?"
  ↓
[Existing] Vector search + cross-encoder → retrieves definition chunk
  ↓
[NEW] Check if queried term has a pre-computed resolution tree
  → If yes: attach full resolution tree to context
  → Inject all transitive dependencies into LLM context
  → LLM sees the complete picture (23 terms, not just 1)
  ↓
[Existing] LLM generates comprehensive answer with inline citations
```

### 3.3 Integration Points

| Component | Integration |
|-----------|-------------|
| `backend/ingestion/` | Add Modules 1-5 as post-ingestion enrichment steps |
| `backend/graph/graph_builder.py` | Add DEPENDS_ON edge type alongside existing REFERENCES, CONTAINS, NEXT |
| `backend/retrieval/term_resolver.py` | Replace current BFS depth-8 with pre-computed resolution tree lookup |
| `backend/retrieval/human_like_retriever.py` | Definition enrichment step uses resolution tree instead of BFS |
| `config/settings.py` | Add `resolution_engine_enabled: bool = True` |

---

## 4. Module 1: Term Dictionary Extraction

### 4.1 Purpose

Extract a comprehensive dictionary of `{term_name → full definition text}` from the document's Definitions section (Article I in PSAs).

### 4.2 Input/Output

**Input:** Raw document text (full PSA, typically 80,000-100,000 words)  
**Output:** Dictionary:
```python
{
    "Current Interest": "As of any Distribution Date, with respect to the Certificates...",
    "Certificate Principal Balance": "With respect to any Certificate...",
    "Distribution Date": "The 25th day of each month...",
    # ... 300+ entries
}
```

### 4.3 Algorithm: State Machine Parser

PSA definitions follow a regular grammar. The parser uses a simple state machine:

```python
"""
Module 1: Term Dictionary Extraction

Extracts {term_name: definition_text} from Article I (Definitions section).
Uses a state machine parser that handles:
- Pattern A: "Term Name": definition text...
- Pattern B: "Term Name" means definition text...
- Pattern C: "Term Name" shall mean definition text...
- Multi-paragraph definitions
- Definitions with sub-clauses (i), (ii), (iii)
- Definitions that span page breaks
"""

import re
from typing import Dict, Tuple, Optional


# Regex patterns for definition boundaries
DEFINITION_START = re.compile(
    r'"([A-Z][A-Za-z\s\-/]+?)"'           # Quoted capitalized term name
    r'\s*'                                   # Optional whitespace
    r'(?::|shall\s+mean|means|is\s+defined\s+as)',  # Separator patterns
    re.MULTILINE
)

# Section boundary markers (Article II, III, etc. signals end of definitions)
ARTICLE_BOUNDARY = re.compile(
    r'^\s*ARTICLE\s+[IVX]+[.\s]',
    re.MULTILINE
)


def extract_definitions_section(text: str) -> Tuple[str, int, int]:
    """
    Locate the Definitions section (Article I) boundaries.
    
    Returns:
        (section_text, start_offset, end_offset)
    """
    # Find Article I start
    art1_match = re.search(
        r'ARTICLE\s+I[.\s]*\n\s*(?:DEFINITIONS|Definitions)',
        text, re.MULTILINE
    )
    if not art1_match:
        # Fallback: look for "Section 1.01" as the definitions start
        art1_match = re.search(r'Section\s+1\.01', text)
    
    if not art1_match:
        return '', 0, 0
    
    start = art1_match.start()
    
    # Find end: next ARTICLE boundary
    remaining = text[art1_match.end():]
    end_match = ARTICLE_BOUNDARY.search(remaining)
    
    if end_match:
        end = art1_match.end() + end_match.start()
    else:
        # If no next article, take next 100K chars (safety bound)
        end = min(start + 100_000, len(text))
    
    return text[start:end], start, end


def extract_term_dictionary(text: str) -> Dict[str, str]:
    """
    Extract all defined terms from the Definitions section.
    
    Returns:
        Dictionary mapping term names to their complete, verbatim definition text.
    """
    section_text, section_start, _ = extract_definitions_section(text)
    if not section_text:
        return {}
    
    # Find all definition start positions
    matches = list(DEFINITION_START.finditer(section_text))
    if not matches:
        return {}
    
    dictionary = {}
    
    for i, match in enumerate(matches):
        term_name = match.group(1).strip()
        
        # Definition text starts after the separator
        def_start = match.end()
        
        # Definition ends at the next definition start, or end of section
        if i + 1 < len(matches):
            def_end = matches[i + 1].start()
        else:
            def_end = len(section_text)
        
        definition_text = section_text[def_start:def_end].strip()
        
        # Clean up: remove trailing whitespace and orphan punctuation
        definition_text = re.sub(r'\s+', ' ', definition_text).strip()
        if definition_text.endswith('.'):
            pass  # Keep trailing period
        
        if term_name and definition_text:
            dictionary[term_name] = definition_text
    
    return dictionary
```

### 4.4 Edge Cases

| Edge Case | Handling |
|-----------|---------|
| Multi-paragraph definitions | Definition extends until next quoted term pattern |
| Definitions with sub-clauses `(i), (ii)` | Included as part of definition text (no special parsing) |
| Page breaks within definitions | Linearized text from `olefile` extraction doesn't have page breaks |
| Inline definitions in other articles | Module 1 only extracts from Article I. Inline definitions are a Module 1.5 enhancement. |
| Duplicate terms (rare) | Last definition wins (with warning logged) |
| Terms containing hyphens ("Pass-Through Rate") | Regex handles hyphens in term names |

### 4.5 Acceptance Criteria

- [ ] Extracts >= 95% of defined terms from Bear Stearns 2006-HE2 PSA
- [ ] Complete verbatim text for each definition (no truncation)
- [ ] Handles "means", "shall mean", "is defined as", and colon separators
- [ ] Multi-paragraph definitions preserved completely
- [ ] Unit test: manually verify 10 randomly selected definitions against source PDF

### 4.6 User Stories

**Story 1.1:** Extract Definitions section boundaries  
**Story 1.2:** Parse individual term definitions  
**Story 1.3:** Handle edge cases (multi-paragraph, sub-clauses, hyphens)  
**Story 1.4:** Unit tests with Bear Stearns PSA

---

## 5. Module 2: Preliminary Statement Table Extraction

### 5.1 Purpose

Extract the structured table from the Preliminary Statement that maps certificate classes to their initial attributes (balances, rates, notional flags).

### 5.2 Input/Output

**Input:** Raw document text (Preliminary Statement section)  
**Output:** Structured data:

```python
@dataclass
class ClassMetadata:
    class_name: str           # "I-A-1", "M-1", "CE"
    initial_cpb: Decimal      # $417,353,000
    is_notional: bool         # True if notional class
    initial_rate: Decimal     # 5.25%
    rate_type: str            # "fixed" | "floating"
    margin: Optional[Decimal] # None for fixed, basis points for floating
    cusip: Optional[str]      # CUSIP identifier if present

# Output:
classes: Dict[str, ClassMetadata]
```

### 5.3 Algorithm: Pattern-Based Table Parser

The Preliminary Statement table, when linearized from the Word document, follows recognizable patterns:

```python
"""
Module 2: Preliminary Statement Table Extraction

Parses the linearized Preliminary Statement table to extract per-class metadata.
"""

import re
from decimal import Decimal
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ClassMetadata:
    class_name: str
    initial_cpb: Decimal
    is_notional: bool
    initial_rate: Decimal
    rate_type: str            # "fixed" | "floating"
    margin: Optional[Decimal]
    cusip: Optional[str] = None


# Patterns for table data extraction
CLASS_NAME_PATTERN = re.compile(r'Class\s+([A-Z0-9][\w-]*)')
DOLLAR_AMOUNT = re.compile(r'\$[\d,]+(?:\.\d{2})?')
PERCENTAGE = re.compile(r'(\d+\.\d+)\s*%')
CUSIP_PATTERN = re.compile(r'\b([A-Z0-9]{9})\b')  # 9 alphanumeric chars


def extract_preliminary_statement(text: str) -> str:
    """Locate the Preliminary Statement section."""
    # Common markers
    start_patterns = [
        r'PRELIMINARY\s+STATEMENT',
        r'Preliminary\s+Statement',
        r'The\s+following\s+table\s+sets\s+forth',
    ]
    
    for pattern in start_patterns:
        match = re.search(pattern, text)
        if match:
            # Extract from match to next ARTICLE or major section
            section_end = re.search(
                r'ARTICLE\s+[IVX]+|(?:SECTION|Section)\s+\d+\.\d+',
                text[match.end():]
            )
            end = match.end() + section_end.start() if section_end else match.end() + 20_000
            return text[match.start():end]
    
    return ''


def parse_class_table(prelim_text: str) -> Dict[str, ClassMetadata]:
    """
    Parse the linearized table into structured class metadata.
    
    The text typically looks like:
        Class I-A-1    $417,353,000    5.250%    Fixed
        Class I-A-2    $100,000,000    5.150%    Fixed
        ...
    """
    classes = {}
    
    # Split into lines and look for class entries
    lines = prelim_text.split('\n')
    
    for line in lines:
        class_match = CLASS_NAME_PATTERN.search(line)
        if not class_match:
            continue
        
        class_name = class_match.group(1)
        
        # Extract dollar amount
        dollar_match = DOLLAR_AMOUNT.search(line)
        initial_cpb = Decimal(
            dollar_match.group().replace('$', '').replace(',', '')
        ) if dollar_match else Decimal(0)
        
        # Extract percentage (rate)
        pct_match = PERCENTAGE.search(line)
        initial_rate = Decimal(pct_match.group(1)) / 100 if pct_match else Decimal(0)
        
        # Determine rate type
        rate_type = 'floating' if re.search(r'(?i)float|LIBOR|SOFR|variable', line) else 'fixed'
        
        # Determine if notional
        is_notional = bool(re.search(r'(?i)notional', line)) or initial_cpb == 0
        
        # Extract CUSIP if present
        cusip_match = CUSIP_PATTERN.search(line)
        cusip = cusip_match.group(1) if cusip_match else None
        
        # Margin for floating rate
        margin = None
        if rate_type == 'floating':
            margin_match = re.search(r'(\d+\.?\d*)\s*(?:bps|basis\s+points)', line)
            if margin_match:
                margin = Decimal(margin_match.group(1))
        
        classes[class_name] = ClassMetadata(
            class_name=class_name,
            initial_cpb=initial_cpb,
            is_notional=is_notional,
            initial_rate=initial_rate,
            rate_type=rate_type,
            margin=margin,
            cusip=cusip,
        )
    
    return classes
```

### 5.4 Why This Module Matters

The Preliminary Statement provides the **CONSTANTS** for the entire deal:
- Which class uses Certificate Principal Balance vs. Certificate Notional Amount
- Initial balance per class (needed to trace subsequent amortization)
- Rate type (affects how the Pass-Through Rate resolves)

Without this data, the resolution tree can show ALL branches of a conditional definition but cannot **prune** to show only the branch relevant to a specific class.

### 5.5 Acceptance Criteria

- [ ] Correctly extracts all certificate classes from Bear Stearns 2006-HE2 PSA
- [ ] Initial CPB amounts match the source document
- [ ] Rate information extracted (fixed vs floating)
- [ ] Notional class identification correct
- [ ] Unit test: compare extracted table against manually verified values

### 5.6 User Stories

**Story 2.1:** Locate Preliminary Statement section boundaries  
**Story 2.2:** Parse class names and dollar amounts from linearized table  
**Story 2.3:** Extract rate information and notional flags  
**Story 2.4:** Validate against known Bear Stearns 2006-HE2 values

---

## 6. Module 3: Reference Scanning (DEPENDS_ON Edges)

### 6.1 Purpose

For each definition, identify all other defined terms referenced within it. This produces the DEPENDS_ON edges for the dependency graph.

### 6.2 Algorithm: Aho-Corasick Multi-Pattern Matching

Standard longest-match dictionary scanning. For ~300 terms and ~200-char definitions, even naive O(|text| × |D|) is fast enough. Aho-Corasick is the optimal solution:

```python
"""
Module 3: Reference Scanning

Scans each definition's text to find all referenced defined terms.
Uses longest-match dictionary scanning to produce DEPENDS_ON edges.
"""

from typing import Dict, Set, List, Tuple
import re


def build_reference_map(
    term_dictionary: Dict[str, str]
) -> Dict[str, Set[str]]:
    """
    For each term, find all other terms referenced in its definition.
    
    Args:
        term_dictionary: {term_name → definition_text} from Module 1
    
    Returns:
        {term_name → set of referenced term names}
    """
    # Sort terms by length (longest first) for longest-match
    sorted_terms = sorted(term_dictionary.keys(), key=len, reverse=True)
    
    reference_map: Dict[str, Set[str]] = {}
    
    for term_name, definition_text in term_dictionary.items():
        references = set()
        
        # Scan definition text for references to other terms
        remaining = definition_text
        pos = 0
        
        while pos < len(remaining):
            matched = False
            for candidate in sorted_terms:
                if candidate == term_name:
                    continue  # Don't self-reference
                
                # Check if candidate appears at this position
                if remaining[pos:pos + len(candidate)] == candidate:
                    references.add(candidate)
                    pos += len(candidate)
                    matched = True
                    break
            
            if not matched:
                pos += 1
        
        reference_map[term_name] = references
    
    return reference_map


# Also detect section cross-references
SECTION_REF_PATTERN = re.compile(
    r'(?:Section|Sections)\s+(\d+\.\d+(?:\([a-z]\))?(?:\([ivx]+\))?)'
)


def extract_section_references(definition_text: str) -> List[str]:
    """Extract section cross-references (e.g., "Section 5.04(b)")."""
    return [m.group(1) for m in SECTION_REF_PATTERN.finditer(definition_text)]
```

### 6.3 Edge Types

| Edge Type | Source | Target | Meaning |
|-----------|--------|--------|---------|
| `DEPENDS_ON` | Term A | Term B | Definition of A uses Term B |
| `CROSS_REF` | Term A | Section X.XX | Definition of A references Section X.XX |
| `HAS_DEFINITION` | (existing) | (existing) | Current graph edge: chunk → term |
| `REFERENCES` | (existing) | (existing) | Current graph edge: generic cross-reference |

### 6.4 Performance

- ~300 terms × ~200-char avg definition = 60,000 comparisons per definition
- ~300 definitions × 60,000 = 18M comparisons total
- At ~1 billion comparisons/sec (string matching): **<0.02 seconds**

With Aho-Corasick automaton: O(|text| + |matches|) per definition = even faster.

### 6.5 Acceptance Criteria

- [ ] Build reference map for all 300+ terms in Bear Stearns PSA
- [ ] Longest-match: "Certificate Principal Balance" ≠ "Certificate" + "Principal Balance"
- [ ] Self-references excluded
- [ ] Section cross-references extracted separately
- [ ] Unit test: verify references for "Current Interest" include at least: Certificate Principal Balance, Certificate Notional Amount, Accrual Period, Pass-Through Rate, Distribution Date, Prepayment Interest Shortfall, Compensating Interest, Relief Act Interest Shortfalls

### 6.6 User Stories

**Story 3.1:** Implement longest-match dictionary scanner  
**Story 3.2:** Extract section cross-references  
**Story 3.3:** Validate reference map for 10 key definitions  

---

## 7. Module 4: Dependency Graph Construction

### 7.1 Purpose

Build the directed graph G = (D, E) with DEPENDS_ON edges as a new layer on the existing NetworkX knowledge graph.

### 7.2 Implementation

```python
"""
Module 4: Dependency Graph Construction

Adds DEPENDS_ON edges to the existing NetworkX knowledge graph.
Validates DAG property. Computes topological sort and depth metrics.
"""

import networkx as nx
from typing import Dict, Set, Optional, List


def build_definition_graph(
    graph: nx.DiGraph,
    term_dictionary: Dict[str, str],
    reference_map: Dict[str, Set[str]],
    section_references: Optional[Dict[str, List[str]]] = None,
) -> nx.DiGraph:
    """
    Add definition nodes and DEPENDS_ON edges to the knowledge graph.
    
    Args:
        graph: Existing NetworkX knowledge graph
        term_dictionary: {term_name → definition_text}
        reference_map: {term_name → set of referenced terms}
        section_references: {term_name → list of section references}
    
    Returns:
        Enhanced graph with DEPENDS_ON edges
    """
    # Add/update nodes for each defined term
    for term_name, definition_text in term_dictionary.items():
        node_id = f"TERM::{term_name}"
        
        if node_id not in graph:
            graph.add_node(node_id)
        
        # Set/update attributes
        graph.nodes[node_id].update({
            'type': 'defined_term',
            'term_name': term_name,
            'definition_text': definition_text,
            'text_length': len(definition_text),
        })
    
    # Add DEPENDS_ON edges
    for term_name, references in reference_map.items():
        source_id = f"TERM::{term_name}"
        for ref_term in references:
            target_id = f"TERM::{ref_term}"
            if target_id in graph:
                graph.add_edge(source_id, target_id, type='DEPENDS_ON')
    
    # Add CROSS_REF edges for section references
    if section_references:
        for term_name, sections in section_references.items():
            source_id = f"TERM::{term_name}"
            for section in sections:
                section_id = f"SECTION::{section}"
                if section_id in graph:
                    graph.add_edge(source_id, section_id, type='CROSS_REF')
    
    # Validate and annotate
    _validate_and_annotate(graph, term_dictionary)
    
    return graph


def _validate_and_annotate(graph: nx.DiGraph, term_dictionary: Dict[str, str]):
    """Validate DAG property and compute depth metrics."""
    
    # Extract the DEPENDS_ON subgraph
    term_nodes = [n for n in graph if graph.nodes[n].get('type') == 'defined_term']
    depends_on_edges = [
        (u, v) for u, v, d in graph.edges(data=True)
        if d.get('type') == 'DEPENDS_ON'
    ]
    subgraph = graph.edge_subgraph(depends_on_edges).copy()
    
    # Check for cycles
    cycles = list(nx.simple_cycles(subgraph))
    if cycles:
        for cycle in cycles:
            term_names = [graph.nodes[n].get('term_name', n) for n in cycle]
            # Log warning but don't fail
            print(f"WARNING: Cycle detected in definition graph: {' → '.join(term_names)}")
            # Mark cycle nodes
            for node in cycle:
                graph.nodes[node]['has_cycle'] = True
    
    # Compute depth for each node
    for node in term_nodes:
        if node not in subgraph:
            graph.nodes[node]['depth'] = 0
            graph.nodes[node]['is_leaf'] = True
            continue
        
        # Depth = longest path from this node to any leaf
        try:
            depth = nx.dag_longest_path_length(
                nx.subgraph_view(subgraph, filter_node=lambda n: True)
            )
            # Node-specific: longest path from this node
            descendants = nx.descendants(subgraph, node)
            if not descendants:
                graph.nodes[node]['depth'] = 0
                graph.nodes[node]['is_leaf'] = True
            else:
                max_depth = 0
                for desc in descendants:
                    try:
                        path = nx.shortest_path_length(subgraph, node, desc)
                        max_depth = max(max_depth, path)
                    except nx.NetworkXNoPath:
                        pass
                graph.nodes[node]['depth'] = max_depth
                graph.nodes[node]['is_leaf'] = False
        except nx.NetworkXUnfeasible:
            # Cycle — set depth to -1 as sentinel
            graph.nodes[node]['depth'] = -1
            graph.nodes[node]['is_leaf'] = False
    
    # Compute transitive dependency count
    for node in term_nodes:
        if node in subgraph:
            trans_deps = nx.descendants(subgraph, node)
            graph.nodes[node]['transitive_dep_count'] = len(trans_deps)
        else:
            graph.nodes[node]['transitive_dep_count'] = 0
    
    # Topological sort (for reading order)
    if not cycles:
        try:
            topo_order = list(nx.topological_sort(subgraph))
            for i, node in enumerate(topo_order):
                graph.nodes[node]['topo_order'] = i
        except nx.NetworkXUnfeasible:
            pass
```

### 7.3 Graph Statistics (Expected for Bear Stearns 2006-HE2)

| Metric | Expected Value |
|--------|---------------|
| Total defined terms | 300-400 |
| Terms with ≥ 1 dependency | 200-250 |
| Leaf terms (no dependencies) | 100-150 |
| Max depth | 4-6 |
| Average depth | 1.5-2.0 |
| Cycles | 0 (if any, these are drafting anomalies) |
| Total DEPENDS_ON edges | 800-1200 |

### 7.4 Acceptance Criteria

- [ ] All defined terms represented as nodes with `type='defined_term'`
- [ ] DEPENDS_ON edges correctly reflect reference map from Module 3
- [ ] DAG validation passes (no cycles in Bear Stearns PSA)
- [ ] Depth metric computed for every term node
- [ ] Topological sort produces a valid reading order
- [ ] `transitive_dep_count` for "Current Interest" = ~23

### 7.5 User Stories

**Story 4.1:** Add term nodes and DEPENDS_ON edges to existing graph  
**Story 4.2:** Implement DAG validation and cycle detection  
**Story 4.3:** Compute depth and topological order  
**Story 4.4:** Integration test with Bear Stearns PSA graph

---

## 8. Module 5: Full Resolution Tree (Pre-computed)

### 8.1 Purpose

For every definition, pre-compute and store the complete resolution tree as a JSON attribute on the graph node. This is the core deliverable — from this, the LLM can answer ANY definition question with full context.

### 8.2 Implementation

```python
"""
Module 5: Full Resolution Tree Pre-computation

DFS with memoization. Computed once at ingestion. Stored on graph nodes.
"""

import json
import networkx as nx
from typing import Dict, Optional, Any


def build_resolution_tree(
    graph: nx.DiGraph,
    term_node: str,
    visited: Optional[set] = None,
    memo: Optional[Dict[str, dict]] = None,
) -> dict:
    """
    Build the complete resolution tree for a defined term.
    
    Uses DFS with memoization: each subtree computed once, shared across
    all terms that reference it.
    
    Args:
        graph: Knowledge graph with DEPENDS_ON edges
        term_node: Node ID (e.g., "TERM::Current Interest")
        visited: Cycle detection set (current path)
        memo: Memoization cache
    
    Returns:
        Resolution tree as nested dictionary.
    """
    if visited is None:
        visited = set()
    if memo is None:
        memo = {}
    
    # Memoization: return cached result
    if term_node in memo:
        return memo[term_node]
    
    # Cycle detection
    if term_node in visited:
        return {
            'term': graph.nodes[term_node].get('term_name', term_node),
            'cycle_detected': True,
            'depth': 0,
            'dependencies': {},
        }
    
    visited = visited | {term_node}  # New set to avoid mutation
    
    node_data = graph.nodes.get(term_node, {})
    
    tree = {
        'term': node_data.get('term_name', term_node),
        'definition_text': node_data.get('definition_text', ''),
        'depth': 0,
        'is_leaf': True,
        'dependency_count': 0,
        'transitive_count': 0,
        'dependencies': {},
    }
    
    # Find DEPENDS_ON successors
    for successor in graph.successors(term_node):
        edge_data = graph[term_node][successor]
        if edge_data.get('type') != 'DEPENDS_ON':
            continue
        
        sub_tree = build_resolution_tree(graph, successor, visited, memo)
        dep_name = sub_tree['term']
        tree['dependencies'][dep_name] = sub_tree
        tree['depth'] = max(tree['depth'], 1 + sub_tree.get('depth', 0))
        tree['is_leaf'] = False
    
    tree['dependency_count'] = len(tree['dependencies'])
    tree['transitive_count'] = sum(
        1 + sub.get('transitive_count', 0)
        for sub in tree['dependencies'].values()
    )
    
    memo[term_node] = tree
    return tree


def precompute_all_resolution_trees(graph: nx.DiGraph) -> Dict[str, dict]:
    """
    Pre-compute resolution trees for ALL defined terms.
    
    Runs DFS from each term node. Memoization ensures O(V + E) total
    even though we call build_resolution_tree() for each term.
    
    Returns:
        {term_name → resolution_tree_dict}
    """
    memo: Dict[str, dict] = {}
    trees: Dict[str, dict] = {}
    
    term_nodes = [
        n for n in graph.nodes
        if graph.nodes[n].get('type') == 'defined_term'
    ]
    
    for node in term_nodes:
        tree = build_resolution_tree(graph, node, visited=None, memo=memo)
        term_name = graph.nodes[node].get('term_name', node)
        trees[term_name] = tree
        
        # Store on graph node as JSON attribute
        graph.nodes[node]['resolution_tree'] = json.dumps(tree)
    
    return trees


def format_resolution_tree_for_llm(tree: dict, max_depth: int = 4, indent: int = 0) -> str:
    """
    Format a resolution tree as human-readable text for LLM context injection.
    
    Example output:
    
    Current Interest (depth=4, 23 dependencies)
    ├── Definition: "As of any Distribution Date, with respect to..."
    ├── Certificate Principal Balance (depth=2, 5 dependencies)
    │   ├── Definition: "With respect to any Certificate..."
    │   ├── Initial Certificate Principal Balance (leaf)
    │   │   └── Definition: "The initial principal balance..."
    │   └── Realized Losses (depth=1, 2 dependencies)
    │       └── Definition: "With respect to any Distribution Date..."
    ├── Accrual Period (depth=1, 1 dependency)
    │   ├── Definition: "With respect to any Distribution Date..."
    │   └── Distribution Date (leaf)
    │       └── Definition: "The 25th day of each month..."
    └── Pass-Through Rate (leaf)
        └── Definition: "With respect to any class..."
    """
    prefix = '│   ' * indent
    term = tree.get('term', '?')
    depth = tree.get('depth', 0)
    trans = tree.get('transitive_count', 0)
    definition = tree.get('definition_text', '')
    
    # Truncate definition for display (first 200 chars)
    def_preview = definition[:200] + '...' if len(definition) > 200 else definition
    
    lines = []
    
    if depth == 0:
        lines.append(f'{prefix}{term} (leaf)')
    else:
        lines.append(f'{prefix}{term} (depth={depth}, {trans} dependencies)')
    
    lines.append(f'{prefix}├── Definition: "{def_preview}"')
    
    if indent < max_depth:
        deps = tree.get('dependencies', {})
        dep_items = list(deps.items())
        for i, (dep_name, sub_tree) in enumerate(dep_items):
            is_last = (i == len(dep_items) - 1)
            connector = '└── ' if is_last else '├── '
            sub_text = format_resolution_tree_for_llm(sub_tree, max_depth, indent + 1)
            lines.append(sub_text)
    elif tree.get('dependencies'):
        dep_count = len(tree['dependencies'])
        lines.append(f'{prefix}└── [+{dep_count} more dependencies, depth limit reached]')
    
    return '\n'.join(lines)
```

### 8.3 Storage

- **On graph nodes:** `resolution_tree` attribute (JSON string, ~1-5 KB per term)
- **Total size:** ~300 terms × ~3 KB average = ~900 KB
- **Stored in:** Existing graph JSON file (`knowledge_graph.json`)

### 8.4 Query-Time Integration

When the user asks about a defined term:

```python
# In term_resolver.py (replacing current BFS):

def resolve_term(graph, term_name):
    """
    Resolve a defined term using pre-computed resolution tree.
    Replaces the current BFS depth-8 traversal.
    """
    node_id = f"TERM::{term_name}"
    
    if node_id not in graph:
        return None
    
    tree_json = graph.nodes[node_id].get('resolution_tree')
    if not tree_json:
        return None
    
    tree = json.loads(tree_json)
    
    # Format for LLM context injection
    formatted = format_resolution_tree_for_llm(tree, max_depth=4)
    
    return {
        'term': term_name,
        'depth': tree['depth'],
        'dependency_count': tree['transitive_count'],
        'formatted_tree': formatted,
        'raw_tree': tree,
    }
```

The formatted tree is injected into the LLM context alongside the retrieved chunks. The LLM can then produce a complete, depth-aware answer.

### 8.5 Acceptance Criteria

- [ ] Resolution tree computed for ALL defined terms in Bear Stearns PSA
- [ ] "Current Interest" tree has depth ≥ 3 and ≥ 15 transitive dependencies
- [ ] "Distribution Date" tree has depth 0-1 (leaf or near-leaf)
- [ ] Memoization works: total computation < 1 second for 300+ terms
- [ ] `format_resolution_tree_for_llm()` produces readable output
- [ ] Trees stored on graph nodes and persist across sessions
- [ ] `resolve_term()` returns complete tree in < 10ms

### 8.6 User Stories

**Story 5.1:** Implement DFS with memoization for resolution tree  
**Story 5.2:** Format resolution tree as human-readable text  
**Story 5.3:** Store trees on graph nodes during ingestion  
**Story 5.4:** Replace BFS depth-8 in `term_resolver.py` with tree lookup  
**Story 5.5:** Integration test: query "Current Interest" and verify full tree in response

---

## 9. Ingestion Pipeline Integration

### 9.1 Where in the Pipeline

Modules 1-5 run as **post-ingestion enrichment** — after all documents are chunked, embedded, and the base graph is built:

```
Document ingestion (existing):
  1. Extract text (olefile, PDF, etc.)
  2. Chunk text (semantic boundaries)
  3. Embed chunks (BGE ONNX)
  4. Store in ChromaDB (items + sections collections)
  5. Build knowledge graph (CONTAINS, REFERENCES, NEXT edges)

NEW: Definition Resolution enrichment:
  6. [Module 1] Extract term dictionary from definitions section
  7. [Module 2] Extract Preliminary Statement table
  8. [Module 3] Scan each definition for references → reference map
  9. [Module 4] Add DEPENDS_ON edges to graph, validate DAG
  10. [Module 5] Pre-compute resolution trees, store on nodes
  11. Save enriched graph
```

### 9.2 File Organization

```
backend/
  extraction/
    definition_extractor.py      ← Module 1 (NEW)
    prelim_statement_parser.py   ← Module 2 (NEW)
  graph/
    reference_scanner.py         ← Module 3 (NEW)
    definition_graph_builder.py  ← Module 4 (NEW)
    resolution_tree.py           ← Module 5 (NEW)
  retrieval/
    term_resolver.py             ← MODIFIED: use pre-computed trees
```

### 9.3 Configuration

```python
# config/settings.py additions:
resolution_engine_enabled: bool = True    # Enable Modules 1-5
resolution_max_depth: int = 10            # Max depth for resolution trees
resolution_tree_format_depth: int = 4     # Max depth for LLM display
```

---

## 10. Testing Strategy

### 10.1 Unit Tests (Per Module)

```python
# tests/test_resolution_engine.py

class TestModule1:
    def test_extract_definitions_section_boundary(self):
        """Section starts at ARTICLE I and ends before ARTICLE II."""
        
    def test_parse_means_pattern(self):
        """'Term means ...' pattern correctly parsed."""
    
    def test_parse_colon_pattern(self):
        """'"Term": ...' pattern correctly parsed."""
    
    def test_multi_paragraph_definition(self):
        """Definition spanning multiple paragraphs extracted completely."""
    
    def test_bear_stearns_term_count(self):
        """Bear Stearns 2006-HE2 has >= 250 defined terms."""


class TestModule3:
    def test_longest_match(self):
        """'Certificate Principal Balance' matched as one term, not three."""
    
    def test_no_self_reference(self):
        """Term does not appear in its own reference set."""
    
    def test_current_interest_references(self):
        """Current Interest references at least 5 other terms."""
    
    def test_section_cross_references(self):
        """Section 5.04(b) detected as CROSS_REF."""


class TestModule4:
    def test_dag_property(self):
        """Definition graph is a DAG (no cycles)."""
    
    def test_depth_computation(self):
        """Leaf terms have depth 0. Current Interest >= 3."""
    
    def test_topological_sort(self):
        """Leaves come before dependents in topo order."""


class TestModule5:
    def test_resolution_tree_current_interest(self):
        """Current Interest tree has >= 15 transitive dependencies."""
    
    def test_memoization_correctness(self):
        """Shared subtree same object reference in memo."""
    
    def test_format_for_llm_readable(self):
        """Formatted tree is human-readable with proper indentation."""
    
    def test_cycle_handling(self):
        """Artificial cycle produces 'cycle_detected: true' marker."""
```

### 10.2 Integration Tests

```python
class TestResolutionEngineIntegration:
    def test_full_pipeline_bear_stearns(self):
        """
        Ingest Bear Stearns PSA → extract terms → build graph → 
        compute trees → query 'Current Interest' → verify full chain.
        """
    
    def test_term_resolver_uses_precomputed_tree(self):
        """term_resolver.py returns pre-computed tree, not BFS result."""
    
    def test_resolution_tree_in_retrieval_context(self):
        """Retrieved chunks include resolution tree for queried term."""
```

### 10.3 Golden Answer Tests

After implementation, run the Phase D golden test harness:
- Category 1 (Defined Terms, G01-G05) should improve significantly
- Completeness should jump from baseline 3-4 to 4-5
- The resolution tree gives the LLM ALL the information it needs

---

## 11. Execution Plan

### 11.1 Story Sequence

| Week | Stories | Deliverable |
|------|---------|-------------|
| 1 | 1.1-1.4, 3.1-3.3 | Term dictionary extraction + reference scanner |
| 2 | 4.1-4.4, 5.1-5.3 | Graph construction + resolution tree |
| 3 | 2.1-2.4, 5.4-5.5 | Table extraction + integration with retrieval |

### 11.2 Dependencies

```
Module 1 → Module 3 (needs term dictionary to scan references)
Module 3 → Module 4 (needs reference map to build graph)
Module 4 → Module 5 (needs graph to compute resolution trees)
Module 2 ──────────→ Module 5 (table data annotates trees, independent of 3→4)
```

Module 2 can be developed in parallel with Modules 3-4.

### 11.3 Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Term extraction < 95% accuracy | Manual review of first 50 terms. Iterate regex patterns. |
| Cycles in definition graph | Cycle-breaking with `cycle_detected` marker. Log and investigate. |
| Table format varies across PSAs | Start with Bear Stearns format. Generalize in v2. |
| Resolution trees too large for context | `max_depth` parameter limits LLM injection depth |
| Performance at ingestion | Memoized DFS is O(V+E). Expected < 1 second for 300 terms. |

---

## 12. Acceptance Criteria (Overall)

- [ ] Modules 1-5 implemented and passing unit tests
- [ ] Bear Stearns 2006-HE2 PSA produces ≥ 250 defined terms with complete text
- [ ] Dependency graph is a valid DAG
- [ ] Resolution tree for "Current Interest" shows ≥ 15 transitive dependencies at depth ≥ 3
- [ ] Pre-computed trees stored on graph nodes and survive session restart
- [ ] `term_resolver.py` uses pre-computed trees (not BFS)
- [ ] Golden answer tests: Category 1 (Defined Terms) improves by ≥ 1.0 overall point
- [ ] Total ingestion time increase < 5 seconds
- [ ] 575 existing Python tests still pass
- [ ] New test file `tests/test_resolution_engine.py` with ≥ 20 tests, all passing
