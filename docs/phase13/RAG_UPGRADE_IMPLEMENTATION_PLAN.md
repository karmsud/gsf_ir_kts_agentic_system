# Phase 13: Retrieval Quality Upgrades — Implementation Plan

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Motivation — The Retrieval Quality Ceiling

### 1.1 Current Retrieval Limitations

Phase 8 delivered significant retrieval improvements: dual-store, cross-encoder reranking, RRF fusion, graph-first lookup. Phase 9 added directed critique loops. But the core embedding-and-retrieve mechanism has fundamental limitations that no amount of reranking or critique can fix:

| Limitation | Root Cause | Impact |
|-----------|-----------|--------|
| **Vocabulary mismatch** | User queries use different words than document text | Relevant chunks not retrieved at all |
| **Short query, long chunk** | 8-word query embedding vs 300-word chunk embedding — poor cosine match | Miss rate on specific clause lookups |
| **Fixed chunk boundaries** | Chunk splits mid-clause, splitting context | Generated answer lacks surrounding context |
| **Silent retrieval failure** | No confidence signal — 0.31 cosine treated same as 0.98 | User cannot distinguish confident from guessed answers |

Each of these has a well-validated solution in the RAG literature.

### 1.2 HyDE — Solving Vocabulary Mismatch

**Hypothetical Document Embeddings (Gao et al. 2022).**

Instead of embedding the raw user query, generate a hypothetical answer paragraph first, then embed *that*:

```
Query: "What is the Determination Date?"
↓ LLM generates hypothetical:
"The Determination Date means the 25th day of each calendar month, or if such 
 day is not a Business Day, the immediately preceding Business Day, as defined 
 in Section 1.01 of the Pooling and Servicing Agreement."
↓ Embed the hypothetical
↓ Search against chunk embeddings
```

The hypothetical is domain-specific, dense with legal terminology, and semantically close to what a real answer chunk looks like. Retrieval precision on legal definitions improves dramatically because the embedding now matches the *style and vocabulary of the document*, not the style of a user's question.

**Cost**: One fast LLM call per query (GPT-4o-mini, ~$0.001). The returned hypothetical is discarded — it is used only as an embedding seed.

### 1.3 Parent-Child Chunking — Solving Context Fragmentation

Split documents at two levels:
- **Child chunks** (~150 tokens): indexed for retrieval precision. Small and specific.
- **Parent chunks** (~600 tokens): fetched for generation context. Contains the clause in full structural context.

When a child chunk is retrieved, its parent is fetched and sent to the LLM. The LLM sees the full section, not a mid-clause fragment.

### 1.4 Confidence Scoring — Solving Silent Failure

Every answer currently arrives with no signal about retrieval confidence. Users cannot tell if the system found 4 direct matches at 0.97 cosine or cobbled together 2 tangential matches at 0.41. Surfacing this changes the trust dynamic entirely.

---

## 2. Implementation Order

| Order | Increment | Impact | Risk | Rationale |
|-------|-----------|--------|------|-----------|
| **13.1** | Confidence scoring + uncertainty flags | HIGH | LOW | Surface existing metadata. No retrieval change. Immediate trust improvement. |
| **13.2** | Proactive gap alerts | HIGH | LOW | Post-generation check. If N requested terms not found → explicit "not found" notice. |
| **13.3** | Parent-child chunking | VERY HIGH | MEDIUM | Ingestion change. Requires re-ingestion of existing documents. |
| **13.4** | HyDE (Hypothetical Document Embeddings) | HIGH | LOW | One LLM call pre-retrieval. No index change. Feature-flagged. |

---

## 3. Increment 13.1 — Confidence Scoring & Uncertainty Flags

### 3.1 Confidence Tiers

```python
def classify_confidence(top_chunks: list[Chunk]) -> ConfidenceTier:
    if not top_chunks:
        return ConfidenceTier.NO_MATCH
    
    top_score = top_chunks[0].rerank_score
    score_spread = top_chunks[0].rerank_score - top_chunks[-1].rerank_score
    n_direct_matches = sum(1 for c in top_chunks if c.rerank_score > 0.75)
    
    if n_direct_matches >= 2 and top_score > 0.85:
        return ConfidenceTier.HIGH
    elif top_score > 0.65:
        return ConfidenceTier.MEDIUM
    elif top_score > 0.45:
        return ConfidenceTier.LOW
    else:
        return ConfidenceTier.SPECULATIVE
```

### 3.2 User-Facing Display

Appended to every answer in the extension:

| Tier | Display |
|------|---------|
| HIGH | `Answer confidence: **High** — 3 direct matches in Section 1.01` |
| MEDIUM | `Answer confidence: **Medium** — found in context, no direct definition` |
| LOW | `Answer confidence: **Low** — inferred from related clauses` |
| SPECULATIVE | `Answer confidence: **Speculative** — not found directly; answer may be incomplete` |

---

## 4. Increment 13.2 — Proactive Gap Alerts

After generation, compare requested entities against retrieved and cited entities:

```python
def detect_gaps(query: str, answer: str, retrieved_chunks: list[Chunk]) -> list[str]:
    """Return list of terms mentioned in query but not found in retrieved chunks."""
    
    requested_terms = extract_entities(query)  # NER on query
    found_terms = extract_entities(' '.join(c.text for c in retrieved_chunks))
    
    gaps = [term for term in requested_terms if term not in found_terms]
    return gaps
```

If gaps detected, append to answer:

```
> ⚠️ Note: The following terms were requested but could not be located in the 
> indexed documents: **Record Date**, **Certificate Balance**. These may be 
> defined using alternate terminology or located in a section not yet indexed.
```

This is more honest than a hallucinated answer and builds far more durable trust.

---

## 5. Increment 13.3 — Parent-Child Chunking

### 5.1 Index Schema Change

```python
# Child chunk (retrieved)
{
    "chunk_id": "sec_1.01_child_003",
    "text": "...the 25th day of each calendar month...",  # ~150 tokens
    "parent_id": "sec_1.01_parent_001",
    "section": "1.01",
    "doc_type": "PSA"
}

# Parent chunk (fetched for generation, NOT in similarity index)
{
    "chunk_id": "sec_1.01_parent_001",
    "text": "Section 1.01 Definitions. The following terms shall have the 
              meanings set forth below: ... [full section text] ...",  # ~600 tokens
    "child_ids": ["sec_1.01_child_001", "sec_1.01_child_002", "sec_1.01_child_003"]
}
```

Parents are stored in a separate ChromaDB collection (`kts_[scope]_parents`) or as a metadata blob. They are fetched by ID, never by similarity search.

### 5.2 Retrieval Change

```python
# Current: retrieve chunk → send chunk to LLM
child_chunks = similarity_search(query_embedding, top_k=15)
send_to_llm(child_chunks)

# Phase 13.3: retrieve child → fetch parent → send parent to LLM
child_chunks = similarity_search(query_embedding, top_k=15)
parent_ids = [c.parent_id for c in child_chunks]
parent_chunks = fetch_by_ids(parent_ids)  # no re-embedding, direct ID lookup
send_to_llm(parent_chunks)  # full section context
```

---

## 6. Increment 13.4 — HyDE

```python
HYDE_PROMPT = """
Generate a single paragraph that would perfectly answer the following question 
about a legal/financial document. Write in formal document language matching 
the style of a {doc_type}. Be specific and use domain terminology.

Question: {query}

Hypothetical answer paragraph:
"""

async def hyde_embed(query: str, doc_type: str = "Pooling and Servicing Agreement") -> np.ndarray:
    hypothetical = await call_llm(HYDE_PROMPT.format(query=query, doc_type=doc_type),
                                   max_tokens=150, temperature=0.3)
    return embed(hypothetical)  # embed the hypothetical, not the query
```

Feature-flagged: `enable_hyde: true`. Falls back to direct query embedding on LLM failure.

---

## 7. Files Changed

| File | Change Type | Increment |
|------|------------|-----------|
| `backend/agents/retrieval_service.py` | Modified | 13.1, 13.2 |
| `backend/retrieval/confidence_scorer.py` | New | 13.1 |
| `backend/retrieval/gap_detector.py` | New | 13.2 |
| `backend/vector/legal_chunker.py` | Modified | 13.3 (parent-child strategy) |
| `backend/vector/store.py` | Modified | 13.3 (parent store) |
| `backend/retrieval/hyde.py` | New | 13.4 |
| `extension/chat/participant.js` | Modified | 13.1 (display confidence tier) |

---

## 8. Success Metrics

| Metric | Baseline | Target (Phase 13) |
|--------|----------|------------------|
| Retrieval recall on definition queries | ~72% | >90% |
| HyDE precision improvement (definitions) | Baseline | +20-30% |
| "Not found" hallucination rate | ~18% | <5% (gap alerts surface these) |
| User trust (self-reported) | Moderate | High |
| Answer completeness with parent chunks | Baseline | +35% context coverage |
