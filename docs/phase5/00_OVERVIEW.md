# Phase 5 — Overview & Scope

**Date**: 2026-02-16  
**Status**: Design — pending approval before implementation

---

## Executive Summary

Phase 5 upgrades the KTS retrieval pipeline from a single-path, single-model, single-query system into a multi-stage, multi-signal, evidence-driven RAG architecture. The work is divided into **7 workstreams** executed in dependency order.

---

## Workstreams

| # | Workstream | Description | LLM Required | Offline Safe |
|---|-----------|-------------|:---:|:---:|
| **WS-1** | Embedding Provider Swap | Replace MiniLM-L6-v2 (384-dim) with BGE-base-en-v1.5 ONNX INT8 (768-dim) | No | Yes |
| **WS-2** | Self-Query Metadata Filter Extraction | Auto-derive `doc_type`, `tool`, `error_code` filters from query text before retrieval | No | Yes |
| **WS-3** | Confidence Score Overhaul | Replace rudimentary formula with multi-signal confidence using all computed scores | No | Yes |
| **WS-4** | Query Decomposition + Reciprocal Rank Fusion | Multi-query generation + parallel retrieval + RRF merge | Optional GHCP | Degraded |
| **WS-5** | Self-RAG Retry Loop | Evidence-driven re-retrieval when provenance coverage is low | Optional GHCP | Degraded |
| **WS-6** | HyDE (Hypothetical Document Embedding) | Generate synthetic passage → embed → retrieve for vague queries | Requires GHCP | No |
| **WS-7** | RAPTOR-Lite Summary Index | Section/doc summaries indexed alongside raw chunks | Requires GHCP | No |

---

## Dependency Graph

```
WS-1 (Embedding Swap)
  │
  ├── WS-2 (Self-Query Filters)     ── independent of WS-1 but benefits from it
  │
  ├── WS-3 (Confidence Overhaul)    ── independent, pure math
  │
  └── WS-4 (Decomposition + RRF)    ── requires WS-2 (filters per sub-query)
        │
        └── WS-5 (Self-RAG Retry)   ── requires WS-4 (retry = re-decompose)
              │
              └── WS-6 (HyDE)       ── optional add-on to retry path
                    │
                    └── WS-7 (RAPTOR-Lite)  ── independent indexing upgrade
```

**Critical path**: WS-1 → WS-4 → WS-5

**Can run in parallel**: WS-2, WS-3 (independent of each other and WS-1 code-wise, though WS-1 requires full re-index which exercises WS-2)

---

## Scope Boundaries

### In Scope
- Embedding model swap (BGE INT8, 768-dim, fully offline)
- Provider abstraction + config-driven selection
- Self-query metadata filter extraction (rule-based, no LLM)
- Multi-query decomposition (rule-based first, optional GHCP)
- Reciprocal rank fusion for multi-query results
- Evidence-driven re-retrieval loop (1 retry max)
- Confidence score overhaul (multi-signal)
- Index metadata storage + mismatch detection
- VSIX bundling of new model
- Full retest with 3 source folders

### Out of Scope
- Text-to-SQL / Text-to-Cypher (no relational/graph DB)
- Specialized embeddings / ColBERT / fine-tuning
- Semantic splitter (current recursive splitter is adequate)
- RankGPT / LLM-based reranking (cross-encoder is sufficient)
- Semantic router (single retrieval backend)
- Answer generation changes (retrieval-only scope)

### Deferred to Phase 6+
- RAPTOR-lite summary index (WS-7) — requires LLM at ingest time
- HyDE (WS-6) — requires GHCP availability validation
- Multi-backend routing (when/if additional backends are added)

---

## Priority & Implementation Order

| Order | Workstream | Rationale |
|---|---|---|
| **1st** | WS-1: Embedding Swap | Foundation — must be done first, all indexes rebuilt |
| **2nd** | WS-2: Self-Query Filters | Biggest retrieval accuracy win, no LLM, low risk |
| **3rd** | WS-3: Confidence Overhaul | Low effort, uses existing signals, improves UX |
| **4th** | WS-4: Query Decomposition + RRF | Structural improvement, builds on WS-2 |
| **5th** | WS-5: Self-RAG Retry | Evidence-driven quality loop, builds on WS-4 |
| **Deferred** | WS-6: HyDE | Requires GHCP, optional |
| **Deferred** | WS-7: RAPTOR-Lite | Requires GHCP at ingest, optional |

---

## Success Criteria

| Metric | Phase 4 Baseline | Phase 5 Target |
|---|---|---|
| PSA hit rate (source_1 + source_2) | 10/10 (100%) | 10/10 (100%) — no regression |
| Golden query hit rate (KB test) | 20/20 (100%) | 20/20 (100%) — no regression |
| Confidence score accuracy | Rudimentary (floor 0.3) | Multi-signal, reflects actual relevance |
| Metadata filter precision | 0% auto-extracted | >80% of queries with extractable filters get correct filters |
| Multi-query decomposition | N/A | Compound queries split and fused |
| Evidence retry recovery | N/A | >50% of low-coverage results improved by retry |
| VSIX size | 222.63 MB | ≤ 250 MB |
| Offline operation | 100% | 100% (WS-1 through WS-3) |

---

## Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| BGE 768-dim changes score distributions | HIGH | Full retest with golden queries; retune thresholds |
| Self-query filter extraction too aggressive (false filters) | MEDIUM | Always include unfiltered fallback retrieval |
| Query decomposition latency (LLM round-trip) | MEDIUM | Rule-based first; LLM optional via config flag |
| Self-RAG retry doubles latency | MEDIUM | Hard cap at 1 retry; skip if coverage > threshold |
| VSIX size growth | LOW | INT8 quantization limits model to ~110 MB |

---

## Document Index

| Document | Description |
|----------|-------------|
| [01_ARCHITECTURE.md](01_ARCHITECTURE.md) | System architecture, component diagram, data flow |
| [02_TECHNICAL_DESIGN.md](02_TECHNICAL_DESIGN.md) | Detailed design per workstream |
| [03_IMPLEMENTATION_PLAN.md](03_IMPLEMENTATION_PLAN.md) | Phased implementation with file-level changes |
| [04_TESTING_PLAN.md](04_TESTING_PLAN.md) | Test strategy, test cases, validation criteria |
