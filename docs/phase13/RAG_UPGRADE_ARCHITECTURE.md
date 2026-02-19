# Phase 13: Retrieval Quality Upgrades — Architecture Document

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Architectural Principles

| Decision | Rationale |
|----------|-----------|
| **HyDE is pre-retrieval, not post-retrieval** | Generate hypothetical before embedding. The embedding is the hypothetical, not the query. |
| **Parent chunks are stored, not indexed** | Parents live in a metadata/blob store, not the similarity index. Fetched by ID, never by similarity. |
| **Confidence is derived from existing signals** | Rerank scores and match counts are already computed. Confidence tier is a free derivation. |
| **Gap detection is post-generation** | Compare requested entities (NER on query) against found entities (NER on retrieved chunks). Simple set difference. |
| **All increments are independently feature-flagged** | HyDE, parent-child, confidence, gap detection each toggle independently. Roll back one without affecting others. |

---

## 2. Layer Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                   QUERY PROCESSING LAYER                      │
│   backend/retrieval/hyde.py          NEW 13.4                │
│   • Hypothetical paragraph generation                         │
│   • Signal-gated: only apply to definition/lookup queries     │
│   • Embed hypothetical → use as query vector                  │
├──────────────────────────────────────────────────────────────┤
│                   VECTOR RETRIEVAL LAYER                      │
│   backend/vector/store.py            MODIFIED 13.3           │
│   • Retrieve child chunks (small, precise)                    │
│   • Fetch parent chunks by parent_id (full context)           │
│                                                               │
│   backend/vector/legal_chunker.py    MODIFIED 13.3           │
│   • Two-pass chunking: small child (~150t) + large parent (~600t) │
│   • Parent ID reference stored in child chunk metadata        │
├──────────────────────────────────────────────────────────────┤
│                   POST-RETRIEVAL ANALYSIS LAYER               │
│   backend/retrieval/confidence_scorer.py  NEW 13.1           │
│   • Classify HIGH/MEDIUM/LOW/SPECULATIVE from rerank scores   │
│   • Count direct matches above threshold                       │
│                                                               │
│   backend/retrieval/gap_detector.py       NEW 13.2           │
│   • NER on query → requested_terms                            │
│   • NER on chunk text → found_terms                           │
│   • gaps = requested_terms − found_terms                      │
│   • Return gaps for explicit "not found" flagging             │
├──────────────────────────────────────────────────────────────┤
│                   PRESENTATION LAYER                          │
│   extension/chat/participant.js      MODIFIED 13.1           │
│   • Render confidence tier badge after every answer           │
│   • Render gap alert blockquote if gaps non-empty             │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Parent-Child Chunk Schema

```
SIMILARITY INDEX (child chunks only)
─────────────────────────────────────────────────────────
chunk_id     TEXT  "kts_sec1.01_child_003"
text         TEXT  "...the 25th day of each calendar month..."  (~150 tokens)
parent_id    TEXT  "kts_sec1.01_parent_001"
section      TEXT  "1.01"
doc_type     TEXT  "PSA"
source_doc   TEXT  "psa.docx"
─────────────────────────────────────────────────────────

PARENT STORE (blob/metadata, NOT similarity index)
─────────────────────────────────────────────────────────
parent_id    TEXT  "kts_sec1.01_parent_001"
text         TEXT  "Section 1.01 Definitions. [full section...]"  (~600 tokens)
child_ids    JSON  ["kts_sec1.01_child_001", "002", "003"]
section      TEXT  "1.01"
doc_type     TEXT  "PSA"
─────────────────────────────────────────────────────────
```

---

## 4. HyDE Query Flow

```
Query: "What is the Determination Date?"
    │
    ├─ HyDE enabled AND definition-type query detected?
    │       YES:
    │       ├─ Call LLM: "Generate hypothetical paragraph answering: [query]"
    │       ├─ Receive: "The Determination Date means the 25th day of each calendar month..."
    │       ├─ Embed hypothetical → query_vector
    │       └─ Similarity search with query_vector
    │
    │       NO (HyDE disabled OR non-definition query):
    │       └─ Embed raw query → query_vector → similarity search
    │
    └─ Retrieved: child_chunks
           ↓
       Fetch parent_chunks by parent_id
           ↓
       Send parent_chunks to LLM for generation
```

---

## 5. Confidence Tier Logic

```
Input: top_chunks after cross-encoder reranking

n_direct_matches = count(c for c in top_chunks if c.rerank_score > 0.75)
top_score = top_chunks[0].rerank_score

HIGH:        n_direct_matches >= 2  AND  top_score > 0.85
MEDIUM:      top_score in (0.65, 0.85]
LOW:         top_score in (0.45, 0.65]
SPECULATIVE: top_score <= 0.45 OR len(top_chunks) == 0

Display appended to every answer:
HIGH:        ✅ Answer confidence: High (N direct matches in [sections])
MEDIUM:      🔵 Answer confidence: Medium (found in context, no direct definition)
LOW:         ⚠️ Answer confidence: Low (inferred from related clauses — verify manually)
SPECULATIVE: 🔴 Answer confidence: Speculative (not found — answer may be incomplete)
```
