# Phase 7: PSA Definition Resolution Engine — Design Discussion

**Date:** February 17, 2026  
**Status:** Design Discussion (pre-implementation)  
**Participants:** Karmsud + Copilot  
**Purpose:** Capture the full design conversation before any implementation begins  

> This document records a design discussion in its entirety — including the problem reframing, mathematical formalization, module breakdown, honest difficulty assessments, key corrections from the user, and future vision. Nothing here is committed to implementation yet. When implementation starts, this will inform the creation of user stories, FRD, PRD, and TRD following a proper Agile SDLC.

---

## Table of Contents

1. [The Problem Statement](#1-the-problem-statement)
2. [The Core Reframing: Compiler, Not Search Engine](#2-the-core-reframing-compiler-not-search-engine)
3. [The PSA as a Programming Language](#3-the-psa-as-a-programming-language)
4. [Mathematical Formalization](#4-mathematical-formalization)
5. [Concrete Example: Current Interest for Class I-A-1](#5-concrete-example-current-interest-for-class-i-a-1)
6. [Module Breakdown](#6-module-breakdown)
   - [Module 1: Term Dictionary Extraction](#module-1-term-dictionary-extraction)
   - [Module 2: Preliminary Statement Table Extraction](#module-2-preliminary-statement-table-extraction)
   - [Module 3: Reference Scanning (DEPENDS_ON Edges)](#module-3-reference-scanning-depends_on-edges)
   - [Module 4: Dependency Graph Construction](#module-4-dependency-graph-construction)
   - [Module 5: Full Resolution Tree (Pre-computed at Ingestion)](#module-5-full-resolution-tree-pre-computed-at-ingestion)
   - [Module 6: Term Classification](#module-6-term-classification)
   - [Module 7: Formula Extraction (English → Math)](#module-7-formula-extraction-english--math)
   - [Module 8: Code Generation (Math → Python)](#module-8-code-generation-math--python)
7. [Honest Assessment: What's Hard and What's Not](#7-honest-assessment-whats-hard-and-whats-not)
8. [Key Insight: This Is Still RAG](#8-key-insight-this-is-still-rag)
9. [Future Vision](#9-future-vision)
10. [Design Decisions Made in This Discussion](#10-design-decisions-made-in-this-discussion)
11. [Open Questions](#11-open-questions)
12. [Implementation Approach: Agile SDLC](#12-implementation-approach-agile-sdlc)

---

## 1. The Problem Statement

### What a human actually does with a PSA

A finance professional working with a Pooling and Servicing Agreement needs to answer questions like: "What is the Current Interest for Class I-A-1 for the January 2025 Distribution Date?"

The human process is:

1. **Locate the definition** of "Current Interest" in Article I (Definitions)
2. **Read the definition** — identify every capitalized defined term within it
3. **Resolve each referenced term** by finding ITS definition
4. **Within each resolved definition**, identify MORE capitalized terms
5. **Recursively resolve** all the way down to leaf terms (constants or external inputs)
6. **Apply context**: Class I-A-1 uses Certificate Principal Balance (not notional), so prune the irrelevant branches
7. **Build the formula**: translate the English definition into a mathematical expression
8. **Plug in values**: initial balances from the Preliminary Statement, current-month variables from external data
9. **Compute**: run the formula to get a dollar amount

Steps 1-6 are done ONCE at deal setup. Steps 7-8 produce an Excel model that lives for 30 years. Step 9 runs monthly.

### What our current RAG system does

Our current system (Phases 1-6) treats the PSA as a **document to search**. When you query "Current Interest", it returns the top-k most similar text chunks. It finds the definition. Maybe it enriches one level of cross-referenced terms (Phase 6 definition injection). But:

- It does NOT recursively resolve all dependencies
- It does NOT extract the mathematical formula
- It does NOT know which terms are constants vs variables vs functions
- It does NOT produce executable logic
- It stops at depth 1 (single definition injection) when the actual dependency tree may be 4-6 levels deep

### The gap

The current system answers: "Here is the text of the Current Interest definition."  
The professional needs: "Here is the complete dependency tree, the formula, and here is how $42,197.50 was computed from these inputs."

---

## 2. The Core Reframing: Compiler, Not Search Engine

The PSA is **source code** written in legal English. What the professional does is **compilation** — transforming that source code into an executable model. 

The correct analogy is NOT "information retrieval from a knowledge base."  
The correct analogy IS "compiling a domain-specific programming language."

```
PSA (English source code)
    ↓  Lexer / Parser
Term Dictionary + Table Data (symbol table)
    ↓  Dependency Resolution
Directed Acyclic Graph of Functions (intermediate representation)
    ↓  Type Checking / Classification
Constants, Variables, Functions identified
    ↓  Code Generation
Python Payment Model (executable)
    ↓  Runtime
Monthly Data Feed (variables) → Distribution Report (output)
```

Every existing RAG system treats the PSA as a document to search. This reframing treats it as a program to compile. These are fundamentally different operations.

---

## 3. The PSA as a Programming Language

### Type System

The PSA contains four types of entities:

#### Constants (C) — set once at Closing Date, immutable for 30 years

Examples:
- Closing Date = "March 30, 2006"
- Cut-off Date = "March 1, 2006"
- Initial Certificate Principal Balance per class — from Preliminary Statement table
- Pass-Through Rate margin — from Preliminary Statement table
- Class category (notional / principal / uncertificated) — from Preliminary Statement table
- Day count convention (e.g., 30/360, Actual/360)

**Source:** Definitions section (for date-type constants) + Preliminary Statement table (for per-class financials).

#### Variables (V) — change each Distribution Date t

Examples:
- Certificate Principal Balance_t = f(CPB_{t-1}, distributions, losses, recoveries)
- Current LIBOR/SOFR rate_t — external market data feed
- Accrual Period_t — calendar computation from Distribution Date dates
- Aggregate Pool Balance_t — sum of remaining loans

**Key property:** Variables are defined recursively — this month's Certificate Principal Balance depends on last month's Certificate Principal Balance, minus distributions, minus losses, plus recoveries.

#### Functions (F) — deterministic logic, never changes

Examples:
- Current Interest(class, t) = formula involving CPB, rate, accrual period, shortfalls
- Certificate Principal Balance(class, t) = formula involving prior CPB, distributions, losses
- Distribution Waterfall(t) = sequential priority of payments

**Key property:** A function's body IS its definition text. The definition text is the "source code" of the function. Each function references other functions, variables, and constants.

#### Cross-References (X) — pointers to obligation/waterfall/reporting sections

Examples:
- "pursuant to Section 5.04(b)" → pointer to Distribution Waterfall section
- "as described in Section 3.01" → pointer to Representations section
- "set forth in the Preliminary Statement" → pointer to Constants table

**Key property:** These are the "call graph" — which functions invoke which obligation sections.

### The document's sections map to programming concepts

| PSA Section | Programming Concept |
|---|---|
| Article I — Definitions | Symbol table / function declarations |
| Preliminary Statement | Constants table / initialization |
| Article V — Distributions | Main function / waterfall algorithm |
| Article IV — Accounts | State variables / data structures |
| Article III — Representations | Preconditions / assertions |
| Article VI — Realized Losses | Error handling / loss allocation |
| Exhibits | Configuration / external data schemas |

---

## 4. Mathematical Formalization

### Definitions as a directed graph

Let D = {d_1, d_2, ..., d_n} be the set of all defined terms in the PSA.

For each defined term d_i, let R(d_i) ⊆ D be the set of defined terms **referenced within** the definition text of d_i.

This gives us a directed graph G = (D, E) where:

E = {(d_i, d_j) | d_j ∈ R(d_i)}

meaning: "the definition of d_i depends on knowing d_j."

### Recursive resolution is the transitive closure

The operation the human performs — recursive resolution — is computing the transitive closure:

R*(d_i) = R(d_i) ∪ R(R(d_i)) ∪ R(R(R(d_i))) ∪ ...

In graph terms: **all nodes reachable from d_i via DFS/BFS.**

### The graph should be a DAG

Legal definitions should not be circular (A defines B, B defines A). If cycles exist, they are drafting anomalies. The system must detect and flag them but handle them gracefully (cycle-breaking with annotation).

### Topological sort gives reading order

If G is a DAG, topological sort gives the order in which terms must be read/evaluated. Leaf nodes (constants) first, then variables that depend only on constants, then functions that depend on those variables, etc.

### Depth metric

For each node d_i:
- depth(d_i) = 0 if R(d_i) = ∅ (leaf / no dependencies)
- depth(d_i) = 1 + max(depth(d_j) for d_j in R(d_i))

This tells us how many levels of recursion are needed to fully resolve d_i.

---

## 5. Concrete Example: Current Interest for Class I-A-1

### The definition text (from the PSA)

> Current Interest: As of any Distribution Date, with respect to the Certificates and interests of each class (other than the Class P Certificates, Class P Interest, the Residual Interests and the Residual Certificates), (i) the interest accrued on the Certificate Principal Balance or Certificate Notional Amount or Uncertificated Notional Amount, as applicable, during the related Accrual Period at the applicable Pass-Through Rate plus any amount previously distributed with respect to interest for such Certificate or interest that has been recovered as a voidable preference by a trustee in bankruptcy minus (ii) the sum of (a) any Prepayment Interest Shortfall for such Distribution Date, to the extent not covered by Compensating Interest and (b) any Relief Act Interest Shortfalls during the related Due Period, provided, however, that for purposes of calculating Current Interest for any such Class, amounts specified in clause (ii) hereof for any such Distribution Date shall be allocated first to the Class CE Certificates, the Class CE Interest and the Residual Certificates in reduction of amounts otherwise distributable to such Certificates and interest on such Distribution Date and then any excess shall be allocated to each Class of Class A Certificates and Class M Certificates pro rata based on the respective amounts of interest accrued pursuant to clause (i) hereof for each such Class on such Distribution Date.

### Dependency tree (what the human builds mentally)

```
Current Interest (depth=4, type=FUNCTION)
├── Distribution Date                    (depth=0, CONSTANT — monthly date from deal schedule)
├── Certificate Principal Balance        (depth=2, VARIABLE — changes monthly)
│   ├── Initial Certificate Principal Balance  (depth=0, CONSTANT — from Prelim Statement)
│   │   └── Closing Date                      (depth=0, CONSTANT)
│   ├── Subsequent Recoveries                 (depth=1, VARIABLE)
│   │   └── Section 5.04(b)                   (CROSS-REFERENCE to waterfall)
│   └── Applied Realized Loss Amounts         (depth=1, VARIABLE)
│       └── ... (further resolution)
├── Certificate Notional Amount          ← PRUNED: Class I-A-1 is not a notional class
├── Uncertificated Notional Amount       ← PRUNED: Class I-A-1 is not uncertificated
├── Accrual Period                       (depth=1, VARIABLE — calendar computation)
│   ├── Distribution Date                (depth=0, already resolved above)
│   └── ... (day count convention terms)
├── Pass-Through Rate                    (depth=1, VARIABLE or CONSTANT per class)
│   └── ... (margin, index rate, etc.)
├── Prepayment Interest Shortfall        (depth=2, VARIABLE)
│   ├── Compensating Interest            (depth=1, VARIABLE)
│   │   └── ...
│   └── ...
├── Relief Act Interest Shortfalls       (depth=1, VARIABLE)
│   └── Due Period                       (depth=0, CONSTANT)
└── [exclusions: Class P, Residual — not applicable to I-A-1]
```

### Key observations from this trace

1. **Depth is variable.** Current Interest needs 4 levels. Closing Date is a leaf (depth 0).

2. **Pruning requires external data.** Knowing Class I-A-1 uses Certificate Principal Balance (not notional) comes from the Preliminary Statement TABLE, not from semantic understanding. The table explicitly lists each class, its initial balance, and whether it's a notional class.

3. **Some edges are cross-references to non-definition sections.** "pursuant to Section 5.04(b)" points to the Distribution Waterfall, not to a defined term. These are a different edge type in the graph.

4. **The formula is parseable.** "(i) interest accrued ... plus recoveries ... minus (ii) the sum of (a) shortfalls and (b) relief act shortfalls" → this is structured arithmetic with enumerated clauses.

5. **Shared dependencies.** "Distribution Date" appears multiple times in the tree but is resolved once. This is why DFS with memoization (visited set) is the right algorithm.

### Why the class/balance information is NOT from semantic search

The user emphasized this point: knowing that Class I-A-1 uses principal balance is NOT derived from semantic similarity search. It comes from a structured table in the Preliminary Statement that lists:
- Class name
- Initial balance (dollar amount)
- Whether it is notional or principal
- Initial pass-through rate
- Margin (if floating)
- Rate type (fixed / floating)

This table must be parsed during ingestion (Module 2) and stored as structured metadata on each class node.

---

## 6. Module Breakdown

### Module 1: Term Dictionary Extraction

**Summary:** Extract a comprehensive dictionary of {term_name → full definition text} from the document's Definitions section.

**Input:** Raw document text  
**Output:** Dictionary {term_name: str → definition_text: str}

**Algorithm:** Scan ARTICLE I (Definitions section) and extract every defined term with its complete, verbatim definition text. PSAs use a regular grammar:
- Pattern A: `"Certificate Principal Balance": As to any Certificate...`
- Pattern B: `"Current Interest" means, as of any Distribution Date...`
- Pattern C: Block of defined terms, each starting with a capitalized term followed by colon

**Difficulty:** LOW — Deterministic regex. The grammar is regular and well-established.

**Key requirement:** Extract the COMPLETE, VERBATIM definition text — every character matters. The current `LegalItemExtractor` truncates and classifies items. This module needs the raw, full text because downstream modules will parse it for formula structure.

**Decision made:** Use a separate, more comprehensive term dictionary from the document's actual definitions section, rather than matching against the set extracted by `DefinedTermExtractor` during current ingestion. Current extraction is lossy; this module requires lossless extraction.

**Open question:** Some terms are defined inline in other articles ("as such term is defined in Section 1.01"). Should these be captured, or only Article I terms?

---

### Module 2: Preliminary Statement Table Extraction

**Summary:** Extract the structured table from the Preliminary Statement that maps class names to initial balances, rates, notional flags, etc.

**Input:** Raw document text (Preliminary Statement section)  
**Output:** Structured table:

```
| Class   | Initial CPB    | Notional? | Init Rate | Margin | Rate Type |
|---------|---------------|-----------|-----------|--------|-----------|
| I-A-1   | $417,353,000  | No        | 5.25%     | —      | Fixed     |
| I-A-2   | $100,000,000  | No        | 5.15%     | —      | Fixed     |
| ...     | ...           | ...       | ...       | ...    | ...       |
| CE      | $0            | No        | 0%        | —      | —         |
```

**Difficulty:** MEDIUM — The Preliminary Statement is a formatted table in the Word doc. With `olefile` extracting raw text, we lose table formatting. The text becomes linearized like:

```
Class I-A-1    $417,353,000    5.250%    Fixed
Class I-A-2    $100,000,000    5.150%    Fixed
```

Parsing this requires recognizing column patterns: dollar amounts (`$[0-9,]+`), percentages (`[0-9.]+%`), class names (`Class [A-Z0-9-]+`), and inferring column alignment from whitespace.

**Why this matters:** This table provides the CONSTANTS for the entire system. Without it, we can build the dependency tree and parse formulas, but we cannot evaluate them. The class category (notional vs principal) determines which branch of a conditional definition applies.

---

### Module 3: Reference Scanning (DEPENDS_ON Edges)

**Summary:** For each definition, scan its text to find all other defined terms referenced within it.

**Input:** One definition's text + the complete term dictionary from Module 1  
**Output:** Set of referenced term names

**Algorithm:** Longest-match dictionary scan.

Sort the term dictionary D by term length (descending). For each position in the definition text, try to match the longest term first.

```
D_sorted = ["Initial Certificate Principal Balance",    # 40 chars
            "Certificate Principal Balance",             # 29 chars
            "Certificate Notional Amount",               # 27 chars
            "Applied Realized Loss Amounts",             # 29 chars
            "Subsequent Recoveries",                     # 21 chars
            "Distribution Date",                         # 17 chars
            "Accrual Period",                             # 14 chars
            ...]

For each position in text:
    for term in D_sorted:
        if text[pos:].startswith(term):
            emit reference to term
            advance pos by len(term)
            break
```

**Why longest-match:** "Certificate Principal Balance" is a term. "Certificate" alone may also be a term. "Initial Certificate Principal Balance" is a third, longer term. We must match the longest one at each occurrence.

**Performance:** Well-known problem (Aho-Corasick automaton for multi-pattern matching). For ~300 terms and ~200-char definitions, even naive O(|text| × |D|) takes microseconds.

**Also detect:** Section cross-references separately (e.g., "pursuant to Section 5.04(b)"). These should emit a different edge type (CROSS_REF vs DEPENDS_ON).

**Difficulty:** LOW — Deterministic string matching.

---

### Module 4: Dependency Graph Construction

**Summary:** Build the directed graph G = (D, E) with DEPENDS_ON edges, at ingestion time.

**Input:** Term dictionary + references from Module 3  
**Output:** NetworkX DiGraph with DEPENDS_ON edges

**Algorithm:**
1. For each term d_i in dictionary, add a node with full definition text as attribute
2. For each d_j in R(d_i) (from Module 3), add edge (d_i, d_j, type="DEPENDS_ON")
3. For each Section cross-reference, add edge (d_i, section_node, type="CROSS_REF")

**Stored as:** New edge type `DEPENDS_ON` in the existing NetworkX graph, alongside existing `HAS_DEFINITION`, `REFERENCES`, `CONTAINS`, `NEXT` edges.

**Validation:**
1. Check DAG property: `nx.is_directed_acyclic_graph(G_definitions)` — should be True
2. If cycles exist: `nx.simple_cycles(G_definitions)` — flag as drafting anomalies
3. Compute topological order: `nx.topological_sort(G_definitions)`

**Pre-computed node attributes:**
- `depth`: longest path from this node to any leaf
- `transitive_dep_count`: |R*(d_i)| — total number of transitive dependencies
- `is_leaf`: True if R(d_i) = ∅

**Difficulty:** LOW — Standard graph algorithms, all native in NetworkX.

---

### Module 5: Full Resolution Tree (Pre-computed at Ingestion)

**Summary:** For every definition, pre-compute and store the complete resolution tree as a JSON attribute on the graph node.

**Decision:** This is done at ingestion, not retrieval. The user's rationale: "the tree, the graph, the fully resolved definition once completed will stay forever. It is set in stone for the life of a 30-year deal."

**Algorithm:** DFS from each definition node on the DEPENDS_ON subgraph. Memoize to avoid redundant computation (many definitions share sub-dependencies).

```python
def build_resolution_tree(G, term_node, visited=None, memo=None):
    if visited is None:
        visited = set()
    if memo is None:
        memo = {}
    if term_node in memo:
        return memo[term_node]
    if term_node in visited:
        return {"cycle_detected": True}  # guard against cycles
    visited.add(term_node)
    
    tree = {
        "term": G.nodes[term_node].get("term_name"),
        "text": G.nodes[term_node].get("text"),
        "depth": 0,
        "dependencies": {}
    }
    
    for dep in G.successors(term_node):
        if G[term_node][dep].get("type") == "DEPENDS_ON":
            sub_tree = build_resolution_tree(G, dep, visited.copy(), memo)
            tree["dependencies"][dep] = sub_tree
            tree["depth"] = max(tree["depth"], 1 + sub_tree.get("depth", 0))
    
    memo[term_node] = tree
    return tree
```

**Storage:** JSON attribute on each graph node. ~300 trees × ~1-5 KB each = < 1 MB total. Stored in the graph JSON file alongside existing node attributes.

**Complexity:** O(V + E) with memoization — one DFS per node, each node visited once total.

**Difficulty:** LOW — DFS on a DAG with memoization.

---

### Module 6: Term Classification

**Summary:** Classify each term as CONSTANT, VARIABLE, FUNCTION, or CROSS_REFERENCE.

**Input:** Definition text + dependency tree + table data from Module 2  
**Output:** Classification label per term

**Heuristic signals:**

| Signal | Classification | Example |
|---|---|---|
| "means [a date]" or "shall mean [fixed value]" with no formula | CONSTANT | "Closing Date", "Cut-off Date" |
| Appears in Preliminary Statement as a fixed value | CONSTANT | Initial CPB, Initial Rate |
| "as of any Distribution Date" — varies per period | VARIABLE | Certificate Principal Balance |
| Contains arithmetic operators (sum, less, plus, product, excess) | FUNCTION | Current Interest |
| "Section X.XX" or "Article N" | CROSS_REFERENCE | "pursuant to Section 5.04(b)" |
| Leaf node with no dependencies | likely CONSTANT | |
| References other VARIABLE terms | likely VARIABLE or FUNCTION | |

**Estimated accuracy:** 70-80% with heuristics alone. The remaining 20-30% requires deeper semantic understanding.

**Risk assessment:**
- Misclassifying a CONSTANT as a VARIABLE → harmless (just parameterize it unnecessarily in the model)
- Misclassifying a FUNCTION as a VARIABLE → dangerous (you'd miss the formula logic)

**Critical path:** FUNCTION detection. If a definition contains "the sum of (i)... and (ii)...", "X less Y", "the product of", "the excess, if any, of X over Y" — it's a FUNCTION. These arithmetic patterns are finite and enumerable in legal/financial language.

**Difficulty:** MEDIUM — Heuristics will get most right, but edge cases exist.

---

### Module 7: Formula Extraction (English → Math)

**Summary:** Parse the natural-language formula in a definition and produce a mathematical expression tree (AST).

**The deterministic grammar of legal math:**

Legal financial documents use a restricted subset of English for arithmetic. The patterns ARE finite:

| Legal Pattern | Math Equivalent | Regex-feasible? |
|---|---|---|
| "the sum of (i) X and (ii) Y" | X + Y | Yes |
| "X plus Y" | X + Y | Yes |
| "X less Y" | X - Y | Yes |
| "X minus Y" | X - Y | Yes |
| "the product of X and Y" | X × Y | Yes |
| "X multiplied by Y" | X × Y | Yes |
| "X divided by Y" | X / Y | Yes |
| "the excess, if any, of X over Y" | max(0, X - Y) | Yes |
| "the lesser of X and Y" | min(X, Y) | Yes |
| "the greater of X and Y" | max(X, Y) | Yes |
| "the ratio of X to Y" | X / Y | Yes |
| "a fraction, the numerator of which is X and the denominator..." | X / Y | Yes |

**What makes this hard EVEN with known patterns:**

The operands X and Y are not simple variable names — they're NESTED defined terms which themselves may contain formulas. The parser needs to handle:

1. **Nested arithmetic:** "the sum of (i) the product of A and B and (ii) C" = (A × B) + C
2. **Enumerated clauses:** Roman numeral lists `(i), (ii), (iii)` that denote operands
3. **Conditional branches:** "in the case of a Class A Certificate, ... ; in the case of a Class M Certificate, ..."
4. **Temporal references:** "on previous Distribution Dates" = sum over t' < t (historical aggregation)
5. **Quantifiers:** "with respect to each class" = for-each loop over classes
6. **Priority/waterfall:** "first to..., then to..., then any excess to..." = sequential if-then logic

**Estimated timeline for full coverage:**

| Sub-task | Scope | Effort |
|---|---|---|
| 10-15 most common arithmetic patterns | "sum of", "less", "product of", "excess" | 1-2 weeks |
| Nested/enumerated clauses | (i), (ii), (iii) with nesting | 1-2 weeks |
| Conditionals | "in the case of", "provided, however" | 1 week |
| Temporal aggregations | "on previous Distribution Dates" | 1 week |
| Waterfall priority logic | Sequential pay, pro-rata, pari passu | 2+ weeks |
| Edge cases and testing | Document-specific variations | Ongoing |

**Difficulty:** HIGH — This is essentially writing a parser for a domain-specific language. It is buildable because the grammar is restricted, but it is a significant engineering effort — not a weekend project.

---

### Module 8: Code Generation (Math → Python)

**Summary:** Transform the parsed AST from Module 7 into executable Python functions.

**Input:** Formula AST + term classifications + resolution tree  
**Output:** Python module with one function per FUNCTION-type term

**Example output:**

```python
def current_interest(cert_class: str, dist_date: date,
                     cpb: Decimal, pass_through_rate: Decimal,
                     accrual_period: int, day_count: int,
                     prepay_shortfall: Decimal, compensating_interest: Decimal,
                     relief_act_shortfall: Decimal) -> Decimal:
    """
    Current Interest per PSA Section 1.01
    
    Source: "As of any Distribution Date, with respect to the
    Certificates and interests of each class..."
    """
    # clause (i): interest accrued on CPB during Accrual Period at Rate
    gross_interest = cpb * pass_through_rate * accrual_period / day_count
    
    # plus: voidable preference recoveries (external input)
    # gross_interest += recovered_preferences  # if applicable
    
    # clause (ii)(a): Prepayment Interest Shortfall net of Compensating Interest
    net_prepay_shortfall = max(Decimal(0), prepay_shortfall - compensating_interest)
    
    # clause (ii)(b): Relief Act Interest Shortfalls
    total_shortfall = net_prepay_shortfall + relief_act_shortfall
    
    # Shortfall allocation: first to CE, then pro-rata to A and M
    if cert_class in CE_CLASSES:
        shortfall_alloc = total_shortfall  # CE absorbs first
    else:
        shortfall_alloc = ...  # pro-rata share of excess after CE absorption
    
    return gross_interest - shortfall_alloc
```

**Difficulty:** MEDIUM — If Module 7 produces a clean AST, generating Python is a standard compiler backend task. The quality of Module 7's output directly determines the quality of Module 8's output.

---

## 7. Honest Assessment: What's Hard and What's Not

### Buildable with confidence (Modules 1-5): The Definition Resolution Engine

These are deterministic graph algorithms on structured text:
- Complete term dictionary extraction from the Definitions section
- Systematic DEPENDS_ON edges via dictionary-based longest-match scanning
- Full pre-computed resolution trees stored as node attributes in the graph
- DAG validation, topological ordering, depth computation

**This alone is a breakthrough.** No existing system gives you: "Here are ALL 23 terms you need to understand to evaluate Current Interest for Class I-A-1, presented in dependency order with full verbatim text." A human doing this manually takes 30-60 minutes per term. The system does it in milliseconds once built.

### Buildable with moderate effort (Module 6): Term Classification

Heuristic-based classification of CONSTANT / VARIABLE / FUNCTION. Gets 70-80% right with pattern matching. Valuable as annotation on the resolution tree even when imperfect.

### Buildable with significant effort (Module 2): Table Extraction

Parsing the Preliminary Statement table from linearized text. The patterns are regular (dollar amounts, percentages, class names) but column alignment and format variations across different PSAs will require iteration.

### Research-grade effort (Modules 7-8): Formula Extraction + Code Generation

Turning "the sum of (i) ... less the sum of (i) ... and (ii) ..." into Python with correct operator precedence, nesting, conditionals, and temporal semantics.

This is a domain-specific compiler. The grammar is restricted enough that it IS tractable, but:
- The surface area is large (many phrasing variations)
- Conditionals ("in the case of", "provided, however") are semi-structured
- Temporal references ("on previous Distribution Dates") encode looping/aggregation
- Testing requires manual verification against real deal models

This should be designed on paper first, with 10-15 test definitions manually parsed end-to-end before any code is written.

---

## 8. Key Insight: This Is Still RAG

The user made a critical correction to the framing. To quote:

> "This compiler problem — it is still RAG. But document ingestion includes all modules 1 to 8 as part of setup. And then RAG should have the ability to answer questions like: 'For month of Jan 2025, class A principal distributed was $200,000.00 — can you explain the math, with document definitions and reference?'"

This reframes the architecture:

```
INGESTION (enhanced by Modules 1-8):
  PSA document
    → Extract term dictionary (Module 1)
    → Extract Preliminary Statement table (Module 2)
    → Build DEPENDS_ON edges (Module 3)
    → Construct dependency graph (Module 4)
    → Pre-compute resolution trees (Module 5)
    → Classify terms as C/V/F (Module 6)
    → Parse formulas to ASTs (Module 7)
    → Generate Python functions (Module 8)
    → Store everything in the graph + vector store

RETRIEVAL (RAG-enhanced by the compiled model):
  User query: "For Jan 2025, Class A got $200K principal — explain?"
    → RAG retrieves the Current Interest definition AND its resolution tree
    → RAG retrieves the compiled formula for Current Interest
    → RAG traces the formula with the user's inputs:
        CPB = $X (from ending balance Dec 2024)
        Rate = 5.25% (fixed)
        Accrual Period = 31 days
        → Interest = CPB × Rate × 31/360 = $Y
    → RAG returns: the math, the PSA definition text source, the section reference
```

The modules are the **ingestion pipeline enhancement**. RAG remains the query interface. But now RAG has access to:
- Not just text chunks, but a compiled dependency graph
- Not just definitions, but executable formulas with traceability
- Not just similarity scores, but mathematical provenance for every number

This IS an enhanced RAG system. The ingestion just got a lot smarter.

---

## 9. Future Vision

As described by the user, the long-term vision is:

### Phase 1: Definition Resolution Engine (Modules 1-5)
The system can return the complete dependency tree for any defined term. A finance professional queries "Current Interest" and gets back all 23 dependent terms in topological order with full verbatim text. This replaces 30-60 minutes of manual cross-referencing.

### Phase 2: Term Classification + Table Extraction (Modules 2, 6)  
The system knows which terms are constants, variables, and functions. It knows each class's initial balance, rate, and category from the Preliminary Statement. The resolution tree is annotated with types.

### Phase 3: Formula Extraction + Code Generation (Modules 7-8)
The system compiles the definitions into executable Python functions. The output is a Python payment model that can be imported and evaluated.

### Phase 4: Deal Model MVP
The compiled Python functions, combined with the Preliminary Statement constants and monthly variable inputs, produce monthly distribution reports. An analyst can input this month's loan pool performance data and get the distribution waterfall output.

### Phase 5: Explainable Computation
"For January 2025, Class I-A-1 received $42,197.50 in interest. Can you explain?"

The system responds:
```
Current Interest(Class I-A-1, Jan 2025):
  Certificate Principal Balance (Dec ending) = $10,000,000.00
  Pass-Through Rate = 5.25% (fixed, from Preliminary Statement)
  Accrual Period = 31 days (Jan 1-31, 30/360 convention → 31/360)
  Gross Interest = $10,000,000 × 5.25% × 31/360 = $45,208.33

  Less shortfalls:
    Prepayment Interest Shortfall = $3,200.00
    Compensating Interest = $189.17
    Net shortfall to Class A (pro-rata share after CE absorption) = $3,010.83

  Current Interest = $45,208.33 - $3,010.83 = $42,197.50

  Source: PSA Section 1.01, "Current Interest" definition
  Dependencies resolved: 23 terms (see resolution tree)
```

### The entire document becomes a word problem

In the user's words: "This entire document is a word problem. All variables (their definitions), all constants (their definitions), definitions themselves become functions. Outputs of functions are inputs of other functions."

The PSA is:
- A word problem with ~300 defined terms
- Where each definition is either a constant, a variable, or a function
- Where functions compose: the output of one function is an input to another
- Where the complete call graph is expressible as a DAG
- Where the "runtime" is monthly inputs producing monthly outputs
- Where the "program" runs for 30 years

Traversing not only the definitions/terms section but also reporting requirements, payment distributions (waterfall), realized loss sections, and account sections would allow building a complete Python payment model from an English-language PSA.

---

## 10. Design Decisions Made in This Discussion

| # | Decision | Rationale |
|---|---|---|
| 1 | Term dictionary should be extracted from the document's actual Definitions section, separate from current `DefinedTermExtractor` | Current extraction is lossy (truncates, classifies, chunks). Full resolution needs complete verbatim text. |
| 2 | Start with full tree, no pruning (Module 4a) | Solves 80% of the user's pain. Pruning (knowing Class I-A-1 uses principal not notional) requires Module 2 (table extraction) which is independent work. |
| 3 | Resolution trees should be pre-computed at ingestion, not at retrieval | The tree is immutable for the 30-year life of a deal. Compute once, store forever. DFS is milliseconds either way, but ingestion-time means the graph is always query-ready. |
| 4 | Implementation should follow proper Agile SDLC | User stories, FRD, PRD, TRD. Small stories (UI/API/logic). Implement one story at a time, test it, lock it, then next. Not "implement modules 1-5 at once." |
| 5 | Class category (notional vs principal) comes from the Preliminary Statement TABLE, not semantic search | This is structured data extraction, not NLP. The table explicitly lists each class with its attributes. |

---

## 11. Open Questions

1. **Scope of definitions extraction:** Only Article I (Definitions section), or also inline definitions from other articles ("as such term is defined in Section 1.01")?

2. **Cross-PSA consistency:** Different PSAs use slightly different definition grammars. How much variation should the parser handle in v1?

3. **Formula verification:** How do we validate that the parsed formula matches the intended interpretation? Gold-standard comparison against manually-built deal models?

4. **Waterfall scope:** The Distribution Waterfall (Article V typically) is not a "definition" but a sequential algorithm. Should Module 7 handle waterfall parsing, or is that a separate module entirely?

5. **Multi-document resolution:** Some PSA terms reference other documents ("as defined in the Indenture"). Is cross-document resolution in scope?

6. **Table extraction robustness:** How much variation in Preliminary Statement table formatting should we handle? Need sample documents to assess.

7. **Test data:** Do we have access to the actual Preliminary Statement table from the Bear Stearns 2006-HE2 PSA to validate Module 2 output against known values?

---

## 12. Implementation Approach: Agile SDLC

The user explicitly stated: "We are not going to say implement module 1 to 5. Instead we are going to create user stories, detailed FRD, PRD and TRD documents, small stories — UI/API/logic stories. We are going to implement one story at a time, test it, lock it, then next."

### Why this matters

In previous RAG development (Phases 1-6), the approach was to implement large features end-to-end, which led to missed edge cases and bugs that were only discovered during integration testing (e.g., the 4 ChromaDB 1.0 compatibility bugs).

### Proposed SDLC structure (to be detailed when implementation begins)

When the design is finalized and implementation starts:

1. **PRD** (Product Requirements Document) — What the system should do, from the user's perspective
2. **FRD** (Functional Requirements Document) — Detailed functional specifications per module
3. **TRD** (Technical Requirements Document) — Technical design, data structures, APIs
4. **User Stories** — Small, testable stories with acceptance criteria

Example user story decomposition for Module 1:

```
Story 1.1: Extract Definitions section from PSA text
  As a system, I need to identify the start and end boundaries of the
  Definitions section (Article I) so that I can extract term definitions.
  Acceptance: Unit test with Bear Stearns 2006-HE2 PSA returns correct boundaries.

Story 1.2: Parse individual term definitions from Definitions section text
  As a system, I need to parse each "Term": definition_text pattern
  so that I can build the term dictionary.
  Acceptance: Unit test extracts "Current Interest", "Certificate Principal Balance",
  and at least 95% of all defined terms with complete verbatim text.

Story 1.3: Handle edge cases in definition parsing
  As a system, I need to handle multi-paragraph definitions, definitions
  with sub-clauses, and definitions that span page breaks.
  Acceptance: Manual review of 10 randomly selected definitions confirms
  verbatim completeness.
```

Each story: implement, test, review, lock. Then next story.

### How to help the coding process

The user asked: "Unless you have suggestion on how I can help you code better, test better."

Suggestions for future implementation sessions:
- **Provide gold-standard data:** For each module, provide 5-10 manually verified examples. E.g., for Module 1: "Here are 5 term definitions I manually extracted — the system's output should match these exactly."
- **One story per session:** Instead of saying "build the resolution engine", say "implement Story 1.1 — extract Definitions section boundaries."
- **Test-first:** Write the test cases BEFORE the implementation code. This forces precise specification.
- **Lock before next:** Don't start Story 1.2 until Story 1.1 passes all tests and is committed.
- **Review output, not code:** After each story, review the system's OUTPUT (e.g., the extracted terms) rather than the code. Correct outputs are the real acceptance criteria.

---

*End of Design Discussion Document*
