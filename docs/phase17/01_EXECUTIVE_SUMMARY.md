# Phase 17: Executive Summary
## Deal-Scoped Isolation, Dual Graph Strategy & Multi-Deal Intelligence

**Document Version:** 1.0  
**Date:** February 22, 2026  
**Status:** Proposal — Pending Approval  
**Business Impact:** CRITICAL — Enables per-deal/per-document isolation, cross-deal analytics, and portfolio-level intelligence  
**Depends On:** Phase 6 (Dual Vector Stores), Phase 12 (Scope Infrastructure), Phase 15 (Comparison Mode)

---

## Table of Contents
1. [Executive Overview](#executive-overview)
2. [Problem Statement](#problem-statement)
3. [Five Breakthrough Capabilities](#five-breakthrough-capabilities)
4. [Use Case Matrix](#use-case-matrix)
5. [Architectural Decision: Single ChromaDB + Metadata Filtering](#architectural-decision)
6. [Command Syntax Design](#command-syntax-design)
7. [Value Proposition](#value-proposition)
8. [Risk Assessment](#risk-assessment)
9. [Success Metrics](#success-metrics)

---

## Executive Overview

### The Portfolio Intelligence Opportunity

Phase 17 transforms KTS from a **single-deal Q&A tool** into a **portfolio-level legal intelligence platform**. Users gain the ability to:

- Query a **single document** within a deal (e.g., only the PSA)
- Query **all documents** within a deal (PSA + ProSupp together)
- Query the **same document type** across 10+ deals
- **Compare**, **diff**, and **aggregate** answers across deals
- Auto-discover deals via **wildcard matching** and **structured catalog queries**

**The Five Innovations:**

| # | Innovation | What It Enables |
|---|-----------|-----------------|
| 1 | **Dual Graph Strategy** | Doc-specific graph for precision, deal-level graph for cross-doc reasoning |
| 2 | **Read-Side Doc Filtering** | `doc_name_prefix` metadata filter on ChromaDB `where` clause at search time |
| 3 | **Unified Scope Resolution Pipeline** | Single code path handles all 14 use cases — single-doc to portfolio-wide |
| 4 | **Enhanced Deal Catalog** | Structured metadata (vintage, issuer, series) enables wildcard + catalog queries |
| 5 | **Three Comparison Modes** | `/compare` (side-by-side), `/diff` (red-flag), `/aggregate` (portfolio pattern) |

---

## Problem Statement

### Current State (Post-Phase 12/15)

**What works:**
- Per-deal `.kts/` folder isolation (write side — Phase 12.1, implemented)
- `doc_name_prefix` metadata stored in ChromaDB chunks during ingestion
- Deal catalog infrastructure (SQLite + FTS5)
- Comparison mode, contradiction detection, anomaly scoring (Phase 15)
- Scope discovery + dynamic slash commands

**What's missing (the gaps Phase 17 fills):**

| Gap | Impact | Phase 17 Fix |
|-----|--------|-------------|
| No read-side doc filtering | Cannot isolate search to PSA-only within a deal | Wire `doc_name_prefix` as ChromaDB `where` filter |
| Single graph per deal | No way to choose doc-specific vs cross-doc traversal | Dual graph: doc-level + deal-level |
| No doc graph nodes have `doc_name_prefix` | Graph traversal cannot be doc-scoped | Add `doc_name_prefix` attribute to all graph nodes |
| Extension doesn't parse `/scope/DOC` syntax | Cannot express doc-level scoping in chat | New path-based token parser |
| Wildcards not wired to catalog | Cannot query "all Bear Stearns 2006 deals" | Catalog wildcard resolution |
| No `/diff` or `/aggregate` modes | Only `/compare` exists | New comparison engines |
| Catalog lacks structured metadata | Cannot filter by vintage, issuer, series | Enhanced `DealCatalog` schema |
| No scope autocomplete in extension | Poor UX for multi-deal queries | Dynamic completions from catalog |

---

## Five Breakthrough Capabilities

### Capability 1: Document-Level Isolation Within a Deal

```
@kts /fin_deal1/PSA What is the Distribution Date?
```

**How it works:**
1. Scope resolution → `fin_deal1` → loads `Fin_deal1/.kts/`
2. Doc filter → `PSA` → applies `where: {"doc_name_prefix": "PSA"}` to ChromaDB
3. Graph → loads `doc_graphs/PSA.json` (not deal graph)
4. Retriever runs in a tight scope: only PSA vectors, only PSA graph nodes

**Value:** Legal analysts frequently need to find the exact definition/clause in a specific document without noise from supplementary materials.

### Capability 2: Cross-Document Reasoning Within a Deal

```
@kts /fin_deal1 What is the Distribution Date?
```

**How it works:**
1. Scope resolution → `fin_deal1` → loads `Fin_deal1/.kts/`
2. No doc filter → all documents participate
3. Graph → loads `knowledge_graph.json` (deal graph with cross-doc edges)
4. Retriever can follow `DEFINED_IN(PSA) → REFERENCED_IN(ProSupp)` edges

**Value:** Structured finance analysis requires understanding how terms in the PSA are applied in the ProSupp. Cross-doc graph edges enable this natively.

### Capability 3: Same Doc Type Across All Deals

```
@kts //PSA What is the Distribution Date?
```

**How it works:**
1. `//` prefix → all scopes from catalog
2. Doc filter → `PSA`
3. Parallel search across all deal ChromaDBs, each filtered to PSA
4. Results aggregated with deal attribution

**Value:** Portfolio analysts need to compare how the same concept is defined across all PSAs in a portfolio.

### Capability 4: Wildcard Multi-Deal Queries

```
@kts /bear_stearns_2006* What is the Distribution Date?
```

**How it works:**
1. Wildcard → catalog query: `slug LIKE 'bear_stearns_2006%'`
2. Returns: `[bear_stearns_2006he1, bear_stearns_2006he2, ...]`
3. Parallel scoped search across all matched deals
4. Results include deal attribution

**Value:** Analysts working on a portfolio of 50+ deals from the same vintage need efficient batch querying.

### Capability 5: Three Comparison Modes

```
@kts /compare /fin_deal1 /fin_deal2 What is the Distribution Date?
@kts /diff /fin_deal1/PSA /fin_deal2/PSA Distribution Date
@kts /aggregate /bear_stearns_2006* How is Realized Loss defined?
```

| Mode | Output | Use Case |
|------|--------|----------|
| `/compare` | Side-by-side table across deals | "How does each deal define this?" |
| `/diff` | Highlighted differences + semantic delta | "Where do these deals diverge?" |
| `/aggregate` | Pattern summary + outlier detection | "What's the common language? Who is different?" |

---

## Use Case Matrix

| # | Use Case | Command | Scope Resolution | Doc Filter | Graph |
|---|----------|---------|-----------------|-----------|-------|
| 1 | One doc in one deal | `@kts /fin_deal1/PSA ...` | Single scope | `PSA` | `doc_graphs/PSA.json` |
| 2 | All docs in one deal | `@kts /fin_deal1 ...` | Single scope | None | `knowledge_graph.json` |
| 3 | One doc type, all deals | `@kts //PSA ...` | All scopes | `PSA` | Per-deal `doc_graphs/PSA.json` |
| 4 | Wildcard deals | `@kts /bear_stearns_2006* ...` | Catalog wildcard | None | Per-deal deal graph |
| 5 | Wildcard + doc filter | `@kts /bear_stearns_2006*/PSA ...` | Catalog wildcard | `PSA` | Per-deal doc graph |
| 6 | Compare wildcards | `@kts /compare /bear_stearns_2006* ...` | Catalog wildcard | None | Per-deal deal graph |
| 7 | Compare with doc filter | `@kts /compare /fin_deal1/PSA /fin_deal2/PSA ...` | Multi-scope | `PSA` | Per-deal doc graph |
| 8 | Define across docs in deal | `@kts /fin_deal1 /define Distribution Date` | Single scope | None | Deal graph (cross-doc) |
| 9 | Audit one doc | `@kts /audit /fin_deal1/PSA` | Single scope | `PSA` | Doc graph |
| 10 | Diff two docs in same deal | `@kts /diff /fin_deal1/PSA /fin_deal1/PROSUPP Distribution Date` | Single scope × 2 | Per-target | Per-doc graph |
| 11 | Diff same doc across deals | `@kts /diff /fin_deal1/PSA /fin_deal2/PSA Distribution Date` | Multi-scope | `PSA` | Per-deal doc graph |
| 12 | Structured catalog query | `@kts /vintage:2006 /issuer:bear_stearns ...` | Catalog structured | None | Per-deal deal graph |
| 13 | List docs in deal | `@kts /list /fin_deal1` | Single scope | None | N/A |
| 14 | Aggregate across wildcard | `@kts /aggregate /bear_stearns_2006* How is Realized Loss defined?` | Catalog wildcard | None | Per-deal deal graph |

---

## Architectural Decision

### Single ChromaDB per Deal + Metadata Filtering (Option A)

**Decision:** One ChromaDB collection per deal. Document-level isolation via `doc_name_prefix` metadata `where` clause.

**Rationale:**

| Factor | Option A (Chosen) | Option B (Per-Doc Collections) |
|--------|-------------------|-------------------------------|
| Single-doc query | `where: {doc_name_prefix: "PSA"}` — fast | Direct collection — fast |
| All-docs-in-deal query | Single query — fast | N queries + merge + renormalize — slower |
| Cross-doc graph | Unified graph captures PSA↔ProSupp refs | Must split or duplicate graph |
| Disk overhead | One HNSW index per deal | N HNSW indices per deal |
| Retriever complexity | Minimal — add `where` filter | Major — multiplex + merge |
| Industry standard | ✅ Weaviate, Pinecone, Luminance | Uncommon |

**Industry Alignment:** Legal AI platforms (Relativity, DISCO, Luminance, Kira Systems) and vector DB best practices (Pinecone namespaces, Weaviate multi-tenancy) converge on workspace-level isolation + metadata filtering.

**Key insight:** Within a structured finance deal, documents are interdependent. The PSA defines terms that the ProSupp references. Splitting them into separate vector spaces destroys cross-document semantic relationships that the deal-level graph captures.

---

## Command Syntax Design

### Path-Based Token Syntax

```
@kts /scope[/DOC_TYPE] [query]
@kts //DOC_TYPE [query]                 ← all deals
@kts /scope_wild* [query]               ← wildcard
@kts /scope_wild*/DOC_TYPE [query]      ← wildcard + doc filter
@kts /mode /scope[/DOC_TYPE] [query]    ← with mode prefix
@kts /key:value [query]                 ← structured catalog filter
```

**Parsing rules:**
1. If token matches a known **mode** (`compare`, `diff`, `aggregate`, `audit`, `define`, `list`) → set mode
2. If token starts with `//` → all-deals + doc filter
3. If token contains `*` → wildcard catalog query
4. If token contains `:` → structured catalog filter
5. If token matches known scope slug → set scope
6. If token follows a scope and is uppercase → doc filter
7. Remainder → query text

---

## Value Proposition

| Stakeholder | Current Pain | Phase 17 Solution |
|------------|-------------|-------------------|
| Legal Analyst | Must manually open each PSA to find definitions | `@kts /fin_deal1/PSA` isolates to PSA only |
| Portfolio Manager | Cannot compare terms across deals | `@kts /compare /bear_stearns_2006*` |
| Risk Officer | No visibility into language outliers | `@kts /aggregate` detects patterns + outliers |
| Diligence Team | Must read both PSA and ProSupp | `@kts /fin_deal1` queries across all docs with graph |
| Senior Management | No portfolio-level analytics | `@kts /vintage:2006` batch analysis |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Dual graph increases build time | Medium | Low | Doc graphs are partitions of deal graph — one pass + split |
| Wildcard queries hit many ChromaDBs | Low | Medium | Parallel execution via asyncio/threading |
| Complex command syntax confuses users | Medium | Medium | Autocomplete + error messages with suggestions |
| FTS5 unavailable on some SQLite builds | Low | Low | Already has LIKE fallback in DealCatalog |
| Memory pressure with many open ChromaDBs | Low | Medium | Lazy loading + LRU cache for DualVectorStore instances |

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Single-doc query precision | ≥ 0.95 | Only PSA chunks returned when PSA filter active |
| Cross-doc query recall | ≥ 0.90 | Definition from PSA found when querying deal-level |
| Multi-deal latency (10 deals) | ≤ 5 seconds | Wall clock for wildcard query across 10 deals |
| Comparison output quality | 100% attribution | Every result tagged with deal + doc source |
| User adoption (post-deploy) | 80% using scope syntax | Telemetry on slash command usage |
| Zero regression | All golden queries pass | Automated test suite |

---

*End of Document — 01_EXECUTIVE_SUMMARY.md*
