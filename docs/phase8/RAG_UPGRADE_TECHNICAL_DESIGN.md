# Phase 8: RAG Upgrade — Technical Design Document

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Executive Summary

Phase 8 introduces nine RAG techniques into the existing KTS retrieval pipeline. Techniques 1-4 are **purely algorithmic** enhancements (no additional LLM calls). Techniques 5-9 add targeted LLM usage at ingestion time, query time, or generation time where the quality gain justifies the cost.

**Techniques to adopt (implementation order 0 → 8):**

| Implementation Order | # | Technique | Source | Problem Solved |
|---------------------|---|-----------|--------|----------------|
| 0 | 5 | Contextual Chunk Headers (CCH) | RAG_Techniques-main | Embeddings lose document-level context (which doc, which section) |
| 1 | 1 | BM25 Hybrid Search | `EnsembleRetriever` (RRF) | Exact term matching ("Closing Date", "Section 5.04") |
| 2 | 2 | MMR Diversity Sampling | `VectorStore.max_marginal_relevance_search` | Redundant/duplicate chunks in top-k |
| 3 | 4 | Token-Aware Context Trimming | `StuffDocumentsChain` pattern | LLM context overflow / truncation |
| 4 | 3 | Parent-Child Document Linking | `ParentDocumentRetriever` | "Right section found, returned chunk too narrow" |
| 5 | 6 | Targeted HyPE | RAG_Techniques-main (adapted) | Definition/trigger chunks are poor query-style matches |
| 6 | 7 | Multi-Query RAG Fusion | RAG Fusion (Shi et al.) | Single query misses alternate phrasings of the same legal concept |
| 7 | 8 | N-Level Definition Chain Traversal | Recursive RAG / TermResolver (in-house) | Nested Capitalized Terms left unresolved; definition chain truncated at depth 1 |
| 8 | 9 | Self-RAG Iterative Generation Loop | FLARE (Jiang et al. 2023) / Self-RAG (Asai et al. 2023) | Single-round generation misses gaps it cannot detect without seeing the draft answer |

---

## 2. Technique 1: BM25 Hybrid Search with Reciprocal Rank Fusion

### 2.1 Problem Statement

The current pipeline uses **only** dense vector similarity (cosine distance in ChromaDB) for retrieval. This fails when:
- User queries contain exact legal terms: "Closing Date", "Realized Loss", "Section 5.04(a)"
- The embedding model conflates semantically similar but legally distinct terms
- Short defined terms (2-3 words) get diluted in the embedding space

**Evidence:** Query "What is the Closing Date" returned 20 chunks from `global_fallback` with `confidence: 0.00` — the cosine-similarity model couldn't distinguish the specific term "Closing Date" from generic date-related text.

### 2.2 Technical Approach

Implement a BM25 (Best Matching 25) keyword retriever alongside the existing dense vector retriever. Combine results using **Weighted Reciprocal Rank Fusion (RRF)** — the same algorithm from LangChain's `EnsembleRetriever`.

#### 2.2.1 BM25 Algorithm

BM25 scores documents by term frequency with saturation and document length normalization:

$$\text{BM25}(q, d) = \sum_{t \in q} \text{IDF}(t) \cdot \frac{f(t, d) \cdot (k_1 + 1)}{f(t, d) + k_1 \cdot (1 - b + b \cdot \frac{|d|}{avgdl})}$$

Where:
- $f(t, d)$ = frequency of term $t$ in document $d$
- $|d|$ = document length, $avgdl$ = average document length
- $k_1 = 1.5$ (term frequency saturation), $b = 0.75$ (length normalization)
- $\text{IDF}(t) = \log\frac{N - n(t) + 0.5}{n(t) + 0.5}$ (inverse document frequency)

#### 2.2.2 Reciprocal Rank Fusion (RRF)

For each document appearing in any retriever's results:

$$\text{RRF}(d) = \sum_{r \in \text{retrievers}} \frac{w_r}{\text{rank}_r(d) + c}$$

Where:
- $w_r$ = weight of retriever $r$ (default: 0.5 each for BM25 and vector)
- $c = 60$ (RRF constant from the original Cormack et al. paper)
- $\text{rank}_r(d)$ = 1-based rank of document $d$ in retriever $r$ (∞ if absent)

#### 2.2.3 Implementation Location

**New file:** `backend/retrieval/bm25_retriever.py`

```python
class BM25Retriever:
    """BM25 keyword retriever over item and section text.
    
    Maintains an in-memory inverted index built at initialization
    from the dual vector store's item and section collections.
    """
    
    def __init__(self, dual_store: DualVectorStore, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self._build_index(dual_store)
    
    def _build_index(self, dual_store):
        """Extract all documents from ChromaDB, build inverted index."""
        # Fetch all items and sections
        # Tokenize (lowercased, split on whitespace + punctuation)
        # Build term → {doc_id: tf} mapping
        # Pre-compute IDF for all terms
        # Pre-compute document lengths and avgdl
    
    def search(self, query: str, top_k: int = 20) -> List[Dict]:
        """BM25 search returning ranked results."""
```

**Modified file:** `backend/retrieval/human_like_retriever.py`

- Add `BM25Retriever` as a dependency alongside `DualVectorStore`
- New Step 4.5: Run BM25 search in parallel with section-scoped vector search
- Modify Step 6 (RRF fusion): Fuse BM25 + vector results instead of just sub-query results

#### 2.2.4 Configuration

```python
@dataclass
class RetrievalConfig:
    # ... existing fields ...
    
    # BM25 Hybrid Search (Phase 8)
    enable_bm25_hybrid: bool = True
    bm25_weight: float = 0.4        # Weight in RRF fusion
    vector_weight: float = 0.6      # Weight in RRF fusion  
    rrf_constant: int = 60          # RRF constant c
    bm25_k1: float = 1.5            # BM25 term frequency saturation
    bm25_b: float = 0.75            # BM25 length normalization
```

#### 2.2.5 Dependency

**Library:** `rank_bm25` (pure Python, ~50 KB, no C dependencies)  
**Alternative:** Custom implementation (~80 lines) to avoid new dependency in PyInstaller bundle.  
**Recommendation:** Custom implementation — eliminates dependency risk for VSIX packaging.

### 2.3 Expected Impact

| Metric | Before | After (Expected) |
|--------|--------|-------------------|
| Exact term recall ("Closing Date") | ~30% | ~90% |
| Section number queries ("Section 5.04") | ~20% | ~95% |
| Semantic queries ("how are losses allocated") | ~70% | ~70% (unchanged) |
| Mixed queries ("Section 5 loss allocation") | ~40% | ~85% |

---

## 3. Technique 2: Maximal Marginal Relevance (MMR) Diversity

### 3.1 Problem Statement

The current `search_items()` and `search_sections()` methods use pure cosine similarity (`query_texts=[query], n_results=top_k`). This often returns 5+ chunks from the same paragraph or adjacent paragraphs, wasting context window tokens on redundant information.

**Evidence:** Cross-encoder reranked 20 results, but many were near-duplicates from the same article, leaving no room for relevant chunks from other sections.

### 3.2 Technical Approach

ChromaDB does **not** natively support MMR. We implement it as a post-retrieval step.

#### 3.2.1 MMR Algorithm

Given query $q$, candidate set $C$, and already-selected set $S$:

$$\text{MMR}(d) = \lambda \cdot \text{sim}(q, d) - (1 - \lambda) \cdot \max_{s \in S} \text{sim}(d, s)$$

Where:
- $\lambda = 0.7$ (balance relevance vs. diversity; higher = more relevant, lower = more diverse)
- $\text{sim}$ = cosine similarity using pre-computed embeddings
- Iteratively select the document with highest MMR score, add to $S$, repeat

#### 3.2.2 Implementation Location

**Modified file:** `backend/vector/dual_vector_store.py`

Add `search_items_mmr()` and `search_sections_mmr()` methods:

```python
def search_items_mmr(
    self,
    query: str,
    top_k: int = 10,
    fetch_k: int = 30,      # Fetch more candidates for diversity pool
    lambda_mult: float = 0.7,
    filters: Optional[Dict] = None,
) -> List[Dict[str, Any]]:
    """Search with Maximal Marginal Relevance for diverse results."""
    # 1. Fetch fetch_k candidates (3x top_k)
    # 2. Get embeddings for query and all candidates
    # 3. Iteratively select top_k using MMR scoring
    # 4. Return diverse, relevant subset
```

**Modified file:** `backend/retrieval/human_like_retriever.py`

- Replace `dual_store.search_items()` calls with `dual_store.search_items_mmr()` in global fallback
- Section-scoped search continues with regular similarity (small candidate set, diversity less critical)

#### 3.2.3 Embedding Access

MMR requires document embeddings (not just distances). ChromaDB supports this:

```python
results = self.item_collection.query(
    query_texts=[query],
    n_results=fetch_k,
    include=["documents", "metadatas", "distances", "embeddings"],  # Add embeddings
)
```

The embedding provider also exposes `embed_query()` for the query embedding.

#### 3.2.4 Configuration

```python
@dataclass
class RetrievalConfig:
    # ... existing fields ...
    
    # MMR Diversity (Phase 8)
    enable_mmr: bool = True
    mmr_lambda: float = 0.7          # 0=pure diversity, 1=pure relevance
    mmr_fetch_multiplier: int = 3    # Fetch 3x top_k for diversity pool
```

### 3.3 Expected Impact

| Metric | Before | After (Expected) |
|--------|--------|-------------------|
| Unique sections in top-10 | ~3-4 | ~6-8 |
| Context diversity score | ~0.4 | ~0.7 |
| Information coverage per query | Moderate | High |

---

## 4. Technique 3: Parent-Child Document Linking

### 4.1 Problem Statement

The dual store has **items** (sentence-level, ~50-200 chars) and **sections** (~500-2000 chars), but they are:
1. In separate collections with no explicit linking
2. Searched independently
3. Items are very small — when matched, the returned text lacks surrounding context

The ParentDocumentRetriever pattern solves this: search on small chunks (precision), return large chunks (context).

### 4.2 Technical Approach

#### 4.2.1 Current Architecture

```
Item Collection:     [item_1] [item_2] [item_3] ... [item_N]
Section Collection:  [sec_1]  [sec_2]  [sec_3]  ... [sec_M]
                     ↑ No explicit link between corresponding items and sections
```

Both collections store `document_id` in metadata, but there's no `parent_section_id` linking items to their containing section.

#### 4.2.2 Target Architecture

```
Item Collection:     [item_1 → sec_1] [item_2 → sec_1] [item_3 → sec_2] ...
Section Collection:  [sec_1]          [sec_2]          [sec_3] ...

Search flow:  query → search items → deduplicate by parent_section_id → return sections
```

#### 4.2.3 Changes Required

**1. Ingestion (schema change):**

**Modified file:** `backend/agents/ingestion_agent.py`

When adding items to the dual store, include `parent_section_id` in metadata:

```python
# Current (line ~140):
item_meta = {
    "document_id": doc_id,
    "section_number": section_number,
    "item_type": item.item_type,
    ...
}

# Phase 8:
item_meta = {
    "document_id": doc_id,
    "section_number": section_number,
    "item_type": item.item_type,
    "parent_section_id": section_id,   # NEW: link to section collection
    ...
}
```

**2. Retrieval (parent lookup):**

**Modified file:** `backend/retrieval/human_like_retriever.py`

New method:

```python
def _expand_items_to_parent_sections(
    self, 
    item_results: List[Dict],
    max_parents: int = 10,
) -> List[Dict]:
    """Given matched items, return their parent sections for richer context."""
    seen_section_ids = set()
    parent_sections = []
    
    for item in item_results:
        parent_id = item.get("metadata", {}).get("parent_section_id")
        if parent_id and parent_id not in seen_section_ids:
            seen_section_ids.add(parent_id)
            section = self.dual_store.get_by_id(parent_id)
            if section:
                section["matched_item"] = item  # Preserve precision info
                parent_sections.append(section)
    
    return parent_sections[:max_parents]
```

**3. Re-ingestion required:** Existing documents must be re-ingested to add `parent_section_id` metadata. This is a **breaking change** for existing indexes.

#### 4.2.4 Configuration

```python
@dataclass
class RetrievalConfig:
    # ... existing fields ...
    
    # Parent-Child Linking (Phase 8)
    enable_parent_expansion: bool = True
    max_parent_sections: int = 10
```

#### 4.2.5 Migration Strategy

Since re-ingestion is required:
1. Add `parent_section_id` to ingestion pipeline
2. Add `_expand_items_to_parent_sections()` to retriever (gracefully handles missing `parent_section_id`)
3. Existing un-upgraded indexes continue working (expansion returns empty, no crash)
4. After re-ingestion, parent expansion activates automatically

### 4.3 Expected Impact

| Metric | Before | After (Expected) |
|--------|--------|-------------------|
| Context richness per chunk | ~100 chars (item) / ~1000 chars (section) | ~1000 chars (always section-level) |
| Definition visibility in context | Item text only | Full section with surrounding definitions |
| LLM answer quality | Fragmented excerpts | Complete section context |

---

## 5. Technique 4: Token-Aware Context Trimming

### 5.1 Problem Statement

The JS-side `buildContextBlock()` and `buildLegalContextBlock()` concatenate all retrieved chunks into the LLM prompt without checking total token count. If the cross-encoder returns 10 long sections (~1000 tokens each), the combined prompt may exceed the model's context window, causing silent truncation.

### 5.2 Technical Approach

#### 5.2.1 Token Estimation

VS Code's LM API doesn't expose a tokenizer. Use a conservative character-based estimate:
- **1 token ≈ 4 characters** (standard GPT-family approximation)
- Reserve tokens: system prompt (~800 tokens) + query (~100 tokens) + answer budget (~2000 tokens)
- Available for context: `model.maxInputTokens - 2900`

#### 5.2.2 Implementation Location

**Modified file:** `extension/chat/participant.js`

```javascript
function trimContextToTokenBudget(contextBlocks, maxTokens) {
    const TOKEN_RATIO = 4; // chars per token
    let totalChars = 0;
    const trimmed = [];
    
    for (const block of contextBlocks) {
        const blockChars = block.length;
        if (totalChars + blockChars > maxTokens * TOKEN_RATIO) {
            // Add partial block up to budget
            const remaining = (maxTokens * TOKEN_RATIO) - totalChars;
            if (remaining > 200) { // Min useful context
                trimmed.push(block.substring(0, remaining) + '\n[... truncated]');
            }
            break;
        }
        trimmed.push(block);
        totalChars += blockChars;
    }
    
    return trimmed.join('\n\n');
}
```

#### 5.2.3 Integration Point

In `generateAnswer()`, after building context but before constructing the LLM message:

```javascript
// Current: context is unlimited
const contextText = isLegal 
    ? buildLegalContextBlock(chunks, citations)
    : buildContextBlock(chunks);

// Phase 8: trim to budget
const maxContextTokens = (model.maxInputTokens || 8192) - 2900;
const trimmedContext = trimContextToTokenBudget(
    contextText.split('\n\n---\n\n'),  // Split on chunk boundaries
    maxContextTokens
);
```

### 5.3 Expected Impact

| Metric | Before | After (Expected) |
|--------|--------|-------------------|
| Context overflow risk | Uncontrolled | Zero — always within budget |
| Answer quality with many chunks | Degrades silently | Best chunks prioritized |
| Compatibility with smaller models | May fail | Graceful degradation |

---

## 6. Technique 5: Contextual Chunk Headers (CCH)

### 6.1 Problem Statement

Embedding models have no knowledge of which document a chunk came from, its type (e.g., legal vs policy), or which section it belongs to. Two chunks with identical text from different documents receive identical embeddings and are thus indistinguishable during retrieval. Legal queries like "What does the Policy of Insurance say about X" require document-level context that pure semantic embeddings discard.

### 6.2 Technical Approach

Prepend a structured **context header** to each chunk's text before it is embedded. The header is stripped from the displayed output — users see clean content, but the embedding "knows" the provenance.

**Header format:**
```
[DOC: {doc_name} | TYPE: {doc_type} | SECTION: {section_title}]
{original chunk text}
```

**Example:**
```
[DOC: PSA-2006HE1 | TYPE: legal | SECTION: Article 2 — Definitions]
"Closing Date" means the date on which the Trust is formed...
```

### 6.3 Implementation Location

**Modified file:** `backend/ingestion/legal_chunker.py`

```python
def build_cch_header(doc_name: str, doc_type: str, section_title: str) -> str:
    """Build a Contextual Chunk Header for embedding.
    
    Returns the header string only — caller concatenates with chunk text.
    Returns empty string if all inputs are empty/None (no-op fallback).
    """
    parts = []
    if doc_name:  parts.append(f"DOC: {doc_name}")
    if doc_type:  parts.append(f"TYPE: {doc_type}")
    if section_title: parts.append(f"SECTION: {section_title[:80]}")
    if not parts:
        return ""
    return f"[{' | '.join(parts)}]\n"


# In the chunk creation path:
def _create_chunk_for_embedding(text: str, metadata: dict) -> str:
    """Return the string to embed (includes CCH header).
    Stored metadata retains the clean `text` field for display.
    """
    header = build_cch_header(
        doc_name=metadata.get("doc_name", ""),
        doc_type=metadata.get("doc_type", ""),
        section_title=metadata.get("section_title", "")
    )
    return header + text  # embedded text has context; displayed text does not
```

### 6.4 Storage Separation

| ChromaDB field | Contains |
|---------------|----------|
| `documents` (embedded text) | `[CCH header]\n{chunk text}` |
| `metadatas["text"]` | Clean `{chunk text}` only (for display) |

This ensures the VS Code response panel shows clean text while retrieval benefits from contextually enriched embeddings.

### 6.5 Configuration

```python
# config/settings.py
ENABLE_CCH = True          # global on/off flag
CCH_MAX_SECTION_LEN = 80   # truncate section titles at N chars
```

### 6.6 Expected Impact

| Metric | Before | After (Expected) |
|--------|--------|------------------|
| Cross-document disambiguation | Relies on cosine only | Header anchors doc provenance in embedding space |
| Recall for doc-specific queries | Medium | High |
| Embedding computation cost | Baseline | +5-10% (header is ~15-25 tokens) |
| Re-ingestion required | — | Yes (first-time only) |

---

## 7. Technique 6: Targeted HyPE (Hypothetical Prompt Embeddings)

### 7.1 Problem Statement

Definition clauses and trigger conditions are written in declarative legal prose ("'X' means...", "If Y occurs..."). User queries are conversational and question-like ("What is X?", "When does Y happen?"). The semantic gap between these two writing styles reduces cosine similarity even when the chunk is the correct answer.

**HyPE's insight:** Instead of trying to close the query→document gap, close the document→query gap. For each high-value chunk, generate hypothetical question(s) that the chunk would answer. Store those questions as a secondary embedding. At query time, match against questions rather than raw legal text.

### 7.2 Scope: Targeted Not Full-Corpus

Full-corpus HyPE (~1,500 chunks × 1 LLM call = 17-30 min at ingestion) is impractical. Targeted HyPE applies only to:
- **Defined Terms:** chunks whose `item_type = "definition"` (~80-120 chunks per document)
- **Trigger Conditions:** chunks whose `item_type = "trigger"` (~20-60 chunks per document)

Total per document: ~100-180 chunks → **5-8 minutes** at ingestion time.

### 7.3 Architecture

**New file:** `extension/lib/hype_enricher.js`

```javascript
/**
 * HyPE Enricher — generates hypothetical questions for high-value chunks
 * at ingestion time using the VS Code Language Model API.
 * 
 * Pattern mirrors image_describer.js::autoDescribeImages()
 */
async function enrichChunksWithQuestions(vscode, chunkIds, batchSize = 5) {
    const model = await selectChatModel(vscode);
    const results = [];
    
    for (let i = 0; i < chunkIds.length; i += batchSize) {
        const batch = chunkIds.slice(i, i + batchSize);
        for (const chunkId of batch) {
            try {
                const chunk = await backendClient.getChunkById(chunkId);
                const questions = await generateQuestionsForChunk(model, chunk);
                await backendClient.storeItemQuestions(chunkId, questions);
            } catch (err) {
                if (isRateLimitError(err)) {
                    await backendClient.markQuestionsPending(chunkId);
                } else {
                    console.error(`HyPE: skipping chunk ${chunkId}:`, err.message);
                }
            }
        }
        await new Promise(r => setTimeout(r, 300)); // rate-limit delay
    }
    return results;
}
```

**New ChromaDB collection:** `item_questions`

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | `{chunk_id}::q{n}` |
| `documents` | string | Hypothetical question text |
| `metadatas.source_chunk_id` | string | Back-reference to original chunk |
| `metadatas.questions_pending` | bool | True if rate-limited at ingestion |

### 7.4 Question Generation Prompt

```
System: You are a legal document analyst. Given a legal clause, generate 3 natural-language questions that this clause would directly answer. Return only the questions as a JSON array of strings.

User: {chunk_text}

Example output:
["What is the definition of Closing Date?",
 "When does the trust closing date occur?",
 "How is the Closing Date determined under this agreement?"]
```

### 7.5 Retrieval Integration

**RRF weight adjustment (with HyPE active):**

$$\text{RRF}(d) = \frac{0.3}{\text{rank}_{q}(d) + 60} + \frac{0.4}{\text{rank}_{BM25}(d) + 60} + \frac{0.3}{\text{rank}_{vec}(d) + 60}$$

where $\text{rank}_{q}$ = rank from question-embedding search in `item_questions`.

**Modified files:** `backend/vector/dual_vector_store.py` (+`search_item_questions()`, `add_item_questions()`, `store_item_questions()`)

### 7.6 Expected Impact

| Metric | Before | After (Expected) |
|--------|--------|------------------|
| Definition queries recall | Medium | High (question→question match) |
| Trigger condition recall | Low-Medium | High |
| Ingestion time overhead | 0 | +5-8 min (one-time, definitions+triggers only) |
| Third collection memory | 0 | ~2-5 MB for 500-900 questions |

---

## 8. Technique 7: Multi-Query RAG Fusion

### 8.1 Problem Statement

A single user query typically expresses only one phrasing of a legal question. The retrieval system may rank the best chunk at position 8 instead of position 1 because the user's exact words don't match the chunk's prose style — even though semantically they are identical. The problem is **phrasing sensitivity of cosine similarity**.

### 8.2 Technical Approach

At query time, ask an LLM to generate **4 semantically diverse variants** of the user's query. Run the full retrieval pipeline (BM25 + vector + HyPE) for each variant. Merge all ranked lists using RRF. The cross-encoder reranks the merged pool. This is the **RAG Fusion** technique (Shi et al., 2023).

**Relationship to existing code:** `decompose_query()` in `human_like_retriever.py` Step 2 is rule-based sub-query splitting for compound questions. Multi-Query RAG Fusion replaces this with LLM-generated diverse angles for all query types.

### 8.3 Query Expansion — Angles Generated

1. **Literal paraphrase** — synonym rewrite of the user's query
2. **Definitional angle** — "What is / How is X defined?"
3. **Application angle** — "When / how does X apply under this agreement?"
4. **Exception angle** — "What are the limits or exclusions for X?"

### 8.4 Implementation Location

**New JS file:** `extension/lib/query_expander.js`

```javascript
/**
 * Expand a user query into 4 diverse variants using the VS Code LM API.
 * Returns an array of 4 strings, or [] on failure (safe degradation).
 */
async function expandQueryWithLLM(vscode, model, query) {
    const prompt = `Generate 4 alternative phrasings of this legal document query, each covering a different angle (paraphrase, definition, application, exception). Return ONLY a JSON array of 4 strings.

Query: ${query}`;
    
    try {
        const messages = [vscode.LanguageModelChatMessage.User(prompt)];
        const response = await model.sendRequest(messages, {}, new vscode.CancellationTokenSource().token);
        let text = '';
        for await (const chunk of response.text) text += chunk;
        const variants = JSON.parse(text);
        return Array.isArray(variants) && variants.length >= 2 ? variants : [];
    } catch {
        return [];  // graceful degradation — proceed with original query only
    }
}
```

**Modified Python file:** `backend/retrieval/human_like_retriever.py`

```python
def retrieve(self, query: str, extra_queries: list[str] = [], **kwargs):
    """Retrieve with optional RAG Fusion over extra_queries."""
    if extra_queries and self.settings.MULTI_QUERY_ENABLED:
        return self._multi_query_retrieve(query, extra_queries, **kwargs)
    return self._single_query_retrieve(query, **kwargs)

def _multi_query_retrieve(self, query, extra_queries, **kwargs):
    all_queries = [query] + extra_queries[:4]  # cap at 5 total
    per_query_results = [
        self._run_steps_1_to_7(q, **kwargs) for q in all_queries
    ]
    merged = self._rrf_merge(per_query_results, k=60)
    return self._run_steps_8_to_11(merged, **kwargs)  # cross-encoder + final

def _rrf_merge(self, ranked_lists: list[list[tuple]], k: int = 60):
    scores = {}
    for ranked_list in ranked_lists:
        for rank, (chunk, _score) in enumerate(ranked_list, start=1):
            cid = chunk['id']
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    # Sort by RRF score descending, return (chunk, rrf_score) tuples
    merged = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    # Re-resolve chunk objects by ID
    chunk_map = {c['id']: c for lst in ranked_lists for c, _ in lst}
    return [(chunk_map[cid], score) for cid, score in merged]
```

### 8.5 Latency and Configuration

```python
# config/settings.py
MULTI_QUERY_ENABLED = True
MULTI_QUERY_VARIANTS = 4      # number of LLM-generated variants
MULTI_QUERY_POOL_SIZE = 5     # top-K per variant before RRF
```

**Expected overhead per query:** ~750-1300ms total (LLM expansion ~600ms + 4× fast pipeline runs ~300ms + RRF ~50ms). The user's observed thinking time already includes the expansion window.

### 8.6 Expected Impact

| Metric | Before | After (Expected) |
|--------|--------|------------------|
| Phrasing-sensitive misses | ~15-20% of queries | <5% |
| Candidate pool for cross-encoder | 6-10 chunks | 15-22 unique chunks |
| Latency overhead | 0 | +750-1300ms |
| Final answer quality | Good | Excellent (richer evidence) |

---

## 9. Technique 8: N-Level Definition Chain Traversal

### 9.1 Problem Statement

Every legal definition contains Capitalized Terms that are themselves defined elsewhere. After primary retrieval, the system recovered the definition of "Current Interest" but left 8 nested terms (Pass-Through Rate, Accrual Period, Compensating Interest, etc.) unresolved. The LLM correctly flagged these as gaps but could not fill them because no secondary retrieval occurred.

The fix is a **post-retrieval definition closure pass**: extract every Capitalized Term from the result, follow `REFERENCES`/`REFERS_TO` graph edges to depth N, and issue targeted ChromaDB fallback queries for any term the graph doesn't know. Zero LLM calls. The `TermResolver` class that performs BFS traversal already exists (`backend/retrieval/term_resolver.py`). It only needs wiring.

### 9.2 Algorithm

```
INPUT: result_chunks (list of retrieved text chunks)
OUTPUT: result_chunks enriched with definition_chain (all resolved nested terms)

1. Extract all Capitalized Terms from result text
   (re.findall pattern: [A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)

2. For each term T:

   Path A — Graph BFS (fast, ~0ms):
     a. Look up T in _definition_index  (term → graph node_id)
     b. If found: call TermResolver.resolve_term(T, graph, max_depth=N)
     c. TermResolver returns: TermResolution{closure, depth_reached, cycles_detected}
     d. For each term in closure not yet seen: add to resolved_set

   Path B — ChromaDB fallback (~50ms per term):
     a. If T not in _definition_index (graph miss):
        → dual_store.search_items(f"definition of {T}",
                                   top_k=3,
                                   filters={"item_type": "definition"})
     b. If result found and score >= 0.7: add to resolved_set

3. Inject resolved_set definitions into context for cross-encoder + final answer

SAFETY:
  - max_depth = N (default 5, configurable)
  - max_terms_per_chunk = 10 (avoid explosion on dense definition chunks)
  - Cycle detection: TermResolution.cycles_detected list (already implemented)
  - Token budget: TermResolution.truncated flag (already implemented)
```

**Time complexity:** O(N × D) where N = number of unique Capitalized Terms, D = average graph degree. For a PSA with 200 defined terms, this is ~1-5ms in graph, ~500ms if 10 ChromaDB fallbacks fire.

### 9.3 PSA Plain-Colon Pattern Fix

PSA definitions use plain ASCII colon without quotes:
```
"Current Interest: As of any Distribution Date..."
```

The existing `_extract_defined_term()` regex misses this. Simple fix:

```python
# Add as last pattern in _extract_defined_term():
m_colon = re.match(
    r'^([A-Z][a-zA-Z\s]{2,60}?):\s+[A-Z]',  # TERM: Sentence...
    definition_text.strip()
)
if m_colon:
    candidate = m_colon.group(1).strip()
    # Validate: must be Title Case (not an acronym or sentence fragment)
    words = candidate.split()
    if all(w[0].isupper() for w in words) and 1 <= len(words) <= 6:
        return candidate
```

### 9.4 What's Already Built vs. What's Missing

| Component | Status | File |
|-----------|--------|------|
| `TermResolver.resolve_term()` with BFS, max_depth, cycle detection | ✅ Built | `backend/retrieval/term_resolver.py` |
| `_definition_index` (term → graph node_id) | ✅ Built | `human_like_retriever.py` |
| `enrich_with_definitions()` Step 5 | ✅ Built (depth 1 only) | `human_like_retriever.py` |
| `should_activate_resolver()` activation gate | ✅ Built | `term_resolver.py` |
| Call `TermResolver` in Step 5 for graph-found terms | ❌ Missing | Wire into `enrich_with_definitions()` |
| ChromaDB fallback for graph misses | ❌ Missing | New helper `_resolve_term_from_vector()` |
| Plain-colon pattern in `_extract_defined_term()` | ❌ Missing | Fix in `human_like_retriever.py` |
| Expose resolved chain in response Definition Chain section | ❌ Missing | Surface `injected_definitions` in participant.js |

### 9.5 Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| Nested terms resolved per query | 0 (graph empty) or 1 (depth 1) | Up to N levels |
| "Current Interest" definition chain completeness | 1/9 terms | 9/9 terms |
| Query latency overhead | 0 | +1-5ms (graph) or +50ms×gap_count (fallback) |

---

## 10. Technique 9: Self-RAG Iterative Generation Loop

### 10.1 Problem Statement

Single-round RAG has a fundamental blind spot: the LLM receives context, generates an answer, and stops — even when the answer itself makes clear that more information is needed. The LLM cannot send follow-up queries because it has no channel back to the retrieval system.

In the Bear Stearns trace the system returned confidence 1.00 with 8 unresolved nested terms listed under "Gaps / Not Found". The LLM **knew** what was missing but was architecturally unable to act on that knowledge.

### 10.2 Academic Grounding

| Technique | Paper | Core Idea |
|-----------|-------|-----------|
| **FLARE** | Jiang et al. 2023, "Active Retrieval Augmented Generation" | When LLM confidence in next tokens is low, it pauses generation and retrieves |
| **Self-RAG** | Asai et al. 2023 | LLM generates special reflection tokens ([Retrieve], [IsREL], [IsSUP]) to control retrieval |
| **Iterative RAG** | Various 2024 | Loop retrieve → generate → critique → retrieve until convergence |

This implementation is closest to **Iterative RAG with LLM-as-judge**: the convergence signal comes from the LLM's own gap analysis, not from a retrieval confidence score. **This fundamentally differs from the existing `IterativeOrchestrator`**, which loops at the retrieval level.

### 10.3 Loop Architecture

```
Round 0 — Initial:
  query_variants   = expandQueryWithLLM(query)         # Inc 6
  initial_chunks   = retrieve(query_variants)            # full pipeline
  current_answer   = llm_generate(query, initial_chunks)
  seen_chunk_ids   = {c.id for c in initial_chunks}

Repeat (max_rounds = 3):
  gaps = llm_gap_analysis(query, current_answer)
  # gaps = [] means: LLM is satisfied — STOP
  if not gaps or gaps == prev_gaps:
      break                                             # convergence or no progress

  new_chunks = retrieve(gaps, exclude_ids=seen_chunk_ids)
  seen_chunk_ids.update({c.id for c in new_chunks})

  current_answer = llm_synthesize(query, current_answer, new_chunks)
  prev_gaps = gaps

Return current_answer
```

### 10.4 Gap Analysis Prompt (Structured)

```
System: You are a legal document analyst. Your job is to identify gaps 
        in a draft answer to a legal document query.

User:
Original question: {query}

Draft answer:
{current_answer}

Task: List the specific sub-questions or Capitalized Terms referenced 
in the draft answer that are NOT yet fully defined or explained in it.
Return ONLY a JSON array of retrieval query strings.
Return [] if the answer is complete and fully self-contained.

Output format: ["query1", "query2"] or []
```

### 10.5 Synthesis Prompt

```
System: You are a legal document analyst. Produce a comprehensive, 
        integrated answer to the original question.

User:
Original question: {query}

Previous answer draft:
{current_answer}

Additional retrieved context:
{new_chunks_formatted}

Instructions:
1. Integrate the new context with the previous draft.
2. Do not repeat text verbatim — synthesize and expand.
3. Maintain the document-grounded format (definitions, excerpts, source citations).
4. Update the Definition Chain and Gaps sections accordingly.
```

### 10.6 Confidence Score Update

After Self-RAG, the confidence score should reflect generation-level completeness, not just retrieval precision:

```javascript
// In participant.js after iterative generation:
const gap_fraction = finalGaps.length === 0 ? 0.0 
                   : Math.min(finalGaps.length / 10.0, 0.5);
const adjusted_confidence = rawConfidence * (1.0 - 0.3 * gap_fraction);
```

A score of 1.00 with unresolved gaps is misleading for legal work. After Self-RAG with 0 remaining gaps the score should legitimately be high.

### 10.7 Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| Definition chain completeness | 1-2 levels resolved | Full chain resolved across rounds |
| Confidence score accuracy | Blind to gaps | Penalizes unresolved terms |
| Latency per query | ~2-4s (single round) | ~6-10s (2 rounds), ~10-16s (3 rounds) |
| "Current Interest" answer quality | Core definition only | Full chain: all 9 nested terms resolved |
| User-visible partial answer | None (final only) | Round-by-round streaming (progressive reveal) |

---

## 11. Technical Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| BM25 index memory usage on large corpus | Medium | Low | Lazy-load index; cap at 50K items; test with real corpus |
| MMR computation cost (O(k² × d)) | Low | Low | Only applied to global fallback (20-30 candidates), not section-scoped |
| Parent-child re-ingestion disruption | High | Medium | Backward-compatible: missing `parent_section_id` → skip expansion |
| Token estimation inaccuracy | Low | Low | Conservative estimate; 4 chars/token works for English legal text |
| BM25 tokenization for legal terms | Medium | Medium | Custom tokenizer preserving hyphenated terms, section numbers |
| PyInstaller bundle size increase | Low | Low | No new binary dependencies; all pure Python |
| HyPE rate-limiting at ingestion | Medium | Low | Batch-of-5 with 300ms delay; `questions_pending` flag for retry |
| Multi-Query latency regression | Low | Medium | Feature flag `MULTI_QUERY_ENABLED`; disable if latency unacceptable |
| LLM query expansion hallucinations | Low | Low | Fallback to `extra_queries=[]` on parse failure; original query always included |
| Definition graph not populated (ingestion miss) | High | Medium | Path B ChromaDB fallback works regardless of graph state |
| Self-RAG infinite loop | Low | High | Hard cap `max_rounds=3`; progress guard: stop if `gaps == prev_gaps` |
| Self-RAG latency unacceptable | Medium | Medium | Feature flag; progressive streaming per round (user sees Round 0 answer immediately) |
| GPT-4o model unavailable | Low | Low | `SELF_RAG_MODEL` setting; graceful single-round fallback |

---

## 12. Dependencies and Prerequisites

| Prerequisite | Status | Notes |
|-------------|--------|-------|
| Phase 7 fixes (TOC exclusion, definition patterns, doc_name resolution) | ✅ Complete | v0.0.10 |
| Re-ingestion of test corpus | Required | After CCH and parent-child schema changes |
| Python `rank_bm25` or custom impl | To decide | Custom preferred for VSIX packaging |
| ChromaDB embedding include support | ✅ Available | `include=["embeddings"]` supported since ChromaDB 0.4.x |
| VS Code LM API at ingestion time | ✅ Confirmed | `image_describer.js` pattern — `selectChatModels` + `sendRequest` |
| Third ChromaDB collection (`item_questions`) | To implement | `dual_vector_store.py` extension |
| `TermResolver` class | ✅ Built | `backend/retrieval/term_resolver.py` — just needs wiring |
| GPT-4o or GPT-4.1 model access | ✅ Available | No rate limits at your firm; configure `SELF_RAG_MODEL` |
| `/retrieve` API `exclude_chunk_ids` param | To implement | Prevents re-serving seen chunks in Self-RAG rounds |

---

## 13. Success Criteria

| Criterion | Measurement | Target |
|-----------|------------|--------|
| "Closing Date" query finds correct definition | Manual test | Top-3 results contain definition text |
| Section number queries match exact section | Golden test suite | ≥90% recall |
| No duplicate chunks in top-5 | Diversity metric | ≥4 unique sections |
| Context never exceeds model limit | Automated test | 100% compliance |
| Alternate phrasing queries still resolve | Golden suite (rephrased set) | ≥85% recall |
| Existing test suite passes | `pytest` + `mocha` | ≥500 total tests pass |
| No new external pip dependencies | Dependency audit | 0 new pip packages |
| HyPE enrichment completes within time budget | Ingestion timer | <10 min for 200 targeted chunks |
| Definition chain fully resolved (all nested terms) | Golden query with nested terms | ≥90% of nested terms resolved |
| Self-RAG reduces "Gaps / Not Found" count | Before/after comparison on golden set | ≥70% reduction in gap count |
