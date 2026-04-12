# Phase 8: RAG Upgrade — Implementation Plan

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Implementation Philosophy

> *"Rigorously test after each change so regression does not backfire."*

Every Phase 8 technique is implemented as an **isolated, testable increment**. Each increment follows this cycle:

```
Code Change → Unit Tests → Integration Tests → Full Regression → Backend Rebuild → VSIX Build → Manual Smoke Test
```

If any gate fails, the increment is reverted before proceeding.

---

## 2. Implementation Order

Techniques are ordered by: **impact × (1 / risk)**.

| Order | Technique | Impact | Risk | Rationale |
|-------|-----------|--------|------|-----------|
| 0 | Contextual Chunk Headers (CCH) | MEDIUM | NONE | Single-line chunker change. No schema change. No re-ingestion. Improves embedding quality for all future ingestions. |
| 1 | BM25 Hybrid Search | HIGH | LOW | Additive — new file, no existing code modified until integration. Captures exact legal terms missed by embeddings. |
| 2 | MMR Diversity | MEDIUM | LOW | Utility function added to existing module. Swap one call site. |
| 3 | Token-Aware Trimming | MEDIUM | NONE | JS-only change. Cannot break Python backend. Safety net. |
| 4 | Parent-Child Linking | HIGH | MEDIUM | Requires metadata schema change + re-ingestion. Done last because schema migration is highest risk. |
| 5 | Targeted HyPE | HIGH | LOW | Post-ingestion LLM pass over definitions/triggers only (~100-180 chunks). Requires new ChromaDB collection. Uses same Copilot LM API pattern as image_describer.js. |
| 6 | Multi-Query RAG Fusion | HIGH | LOW | LLM generates 4-5 query variants at query time. Each variant retrieved via existing pipeline. Pool merged with RRF. Cross-encoder reranks unified pool. Richer evidence for final LLM generation. |
| 7 | N-Level Definition Chain Traversal | HIGH | LOW | Post-retrieval: extract all Capitalized Terms from results, BFS through graph to depth N, fetch definitions via ChromaDB fallback. Pure retrieval — no LLM. TermResolver already built, needs wiring. |
| 8 | Self-RAG Iterative Generation Loop | VERY HIGH | MEDIUM | LLM generates initial answer, then self-critiques for gaps, issues gap queries back to retrieval, combines answers, loops until gaps=[]. Requires GPT-4o/4.1 (no rate limits at your firm). |

---

## 3. Increment 0: Contextual Chunk Headers (CCH)

### 3.1 What Is It?

Before embedding a chunk, prepend a structured header containing the document name, type, section, and subsection. This means the embedding vector directly encodes *where* the text lives in the document — matching queries like "ARTICLE IV distribution waterfall" directly against section-aware text rather than relying on metadata filters.

**Before CCH:**
```
"The Servicer shall, on each Distribution Date, distribute amounts..."
```

**After CCH:**
```
"[DOC: Bear Stearns 2006-HE2 PSA | TYPE: legal | ARTICLE IV | Section 4.01 Distributions]
The Servicer shall, on each Distribution Date, distribute amounts..."
```

### 3.2 Deliverables

| File | Action | Description |
|------|--------|-------------|
| `backend/vector/legal_chunker.py` | MODIFY | Prepend CCH header to chunk content before embedding. |
| `backend/vector/dual_vector_store.py` | MODIFY | Store original content separately from embedded content if needed for display. |
| `tests/test_phase8_cch.py` | CREATE | ~80 lines. Unit tests for header generation and embedding impact. |

### 3.3 Implementation Steps

**Step 0.1: Add `build_cch_header()` to `legal_chunker.py`**

```python
def build_cch_header(doc_name: str, doc_type: str, section_title: str, subsection: str = None) -> str:
    """Build a Contextual Chunk Header for prepending before embedding."""
    parts = [f"DOC: {doc_name}", f"TYPE: {doc_type}"]
    if section_title:
        parts.append(section_title)
    if subsection:
        parts.append(subsection)
    return f"[{' | '.join(parts)}]\n"
```

**Step 0.2: Prepend header before embedding, store clean content for display**

In `legal_chunker.py`, when creating each chunk:

```python
cch_header = build_cch_header(
    doc_name=doc_name,
    doc_type=doc_type,
    section_title=section.title,
    subsection=item.subsection_title if hasattr(item, 'subsection_title') else None
)
# Embed: header + content (embedding captures location context)
chunk.embedded_content = cch_header + chunk.content
# Display: original content only (answer generation uses clean text)
chunk.content = chunk.content  # unchanged
```

**Step 0.3: Write `test_phase8_cch.py`**

- `test_cch_header_format()` — verify header format matches expected pattern
- `test_cch_header_components()` — doc_name, doc_type, section all present
- `test_cch_header_missing_subsection()` — graceful handling when no subsection
- `test_cch_embedded_differs_from_display()` — embedded_content ≠ content
- `test_cch_existing_chunks_unaffected()` — chunks without CCH still work
- `test_cch_section_header_retrieval()` — query "ARTICLE IV" retrieves CCH-tagged chunk higher

**Step 0.4: Run CCH tests**
```bash
pytest tests/test_phase8_cch.py -v
```
Gate: **ALL PASS**

**Step 0.5: Run full regression**
```bash
pytest tests/ -v --tb=short && cd extension && npm test
```
Gate: **ALL tests PASS**

### 3.4 Important Caveat

CCH improves embedding quality for **newly ingested** documents. Existing indexed documents will not benefit until re-ingested. This is fine — it's a forward-looking improvement with zero backward-incompatibility risk. The re-ingestion that Parent-Child (Increment 4) will force anyway will pick up CCH.

### 3.5 Rollback Plan

Remove the `build_cch_header()` call from `legal_chunker.py`. Since existing embeddings are not modified, rollback is trivially safe.

---

## 4. Increment 1: BM25 Hybrid Search

### 4.1 Deliverables

| File | Action | Description |
|------|--------|-------------|
| `backend/retrieval/bm25_retriever.py` | CREATE | ~150 lines. BM25Retriever class with inverted index, BM25 scoring, JSON persistence. |
| `backend/retrieval/human_like_retriever.py` | MODIFY | Accept BM25Retriever in `__init__`. Add Step 5a (BM25 search). Modify Step 6 (RRF fusion). |
| `backend/agents/retrieval_service.py` | MODIFY | Instantiate BM25Retriever, pass to HumanLikeRetriever. |
| `config/settings.py` | MODIFY | Add `enable_bm25_hybrid`, `bm25_weight`, `vector_weight`, `rrf_constant` fields if global config used. |
| `tests/test_phase8_bm25.py` | CREATE | ~200 lines. Unit tests for BM25Retriever + integration tests for hybrid pipeline. |

### 4.2 Implementation Steps

**Step 1.1: Create `bm25_retriever.py`**

```python
class BM25Retriever:
    """BM25 keyword retriever with inverted index persistence."""
    
    def __init__(self, persist_dir: str, k1=1.5, b=0.75):
        ...
    
    def build_index(self, documents: List[Dict]) -> None:
        """Build inverted index from documents. Each doc = {id, content, metadata}."""
        # 1. Tokenize each doc (lowercase, strip punctuation, split whitespace)
        # 2. Build inverted index: token → {doc_id: term_frequency}
        # 3. Compute doc lengths and average doc length
        # 4. Compute IDF for each token
        
    def search(self, query: str, top_k: int = 20) -> List[Dict]:
        """Score all docs against query via BM25, return top_k."""
        # 1. Tokenize query
        # 2. For each query token, accumulate BM25 score per doc
        # 3. Sort by score descending, return top_k
        
    def save_index(self) -> None:
        """Persist index to {persist_dir}/_kts_bm25_index.json."""
        
    def load_index(self) -> bool:
        """Load index from disk. Returns True if found."""
```

**Step 1.2: Write `test_phase8_bm25.py`**

- `test_bm25_build_index()` — build from synthetic corpus, verify index size
- `test_bm25_search_exact_match()` — query with exact term, verify top result
- `test_bm25_search_no_match()` — query with absent term, verify empty result
- `test_bm25_persistence()` — save then load, verify identical results
- `test_bm25_tokenizer_normalization()` — verify case-insensitive, punctuation handling
- `test_bm25_idf_calculation()` — verify rare terms score higher
- `test_bm25_empty_corpus()` — graceful handling of empty corpus

**Step 1.3: Run BM25 unit tests**  
```bash
pytest tests/test_phase8_bm25.py -v
```
Gate: **ALL PASS**

**Step 1.4: Integrate into `human_like_retriever.py`**

- Add `bm25_retriever: Optional[BM25Retriever] = None` parameter to `__init__`
- After Step 5 (global fallback), add Step 5a:
  ```python
  if self.config.enable_bm25_hybrid and self.bm25_retriever:
      bm25_results = self.bm25_retriever.search(query_text, top_k=top_k * 2)
  ```
- Modify Step 6 (fusion) to include BM25 results via weighted RRF:
  ```python
  def _rrf_fuse(self, result_lists, weights=None, c=60):
      # Weighted reciprocal rank fusion
  ```

**Step 1.5: Wire BM25Retriever in `retrieval_service.py`**

- After DualVectorStore init, create BM25Retriever
- On ingestion completion, trigger `bm25_retriever.build_index()`
- On retrieval, pass to HumanLikeRetriever

**Step 1.6: Run full regression**
```bash
# Python tests
pytest tests/ -v --tb=short

# JS tests
cd extension && npm test
```
Gate: **ALL 418+ tests PASS** (344 Python + 74 JS + new BM25 tests)

**Step 1.7: Build backend binary**
```powershell
.\scripts\build_backend.ps1
```
Gate: **Binary starts, responds to health check**

### 4.3 Rollback Plan

If regression fails after integration (Step 1.4-1.5):
1. Set `enable_bm25_hybrid = False` in config → immediate restore of original behavior
2. If needed, `git revert` the integration commits (Step 1.4-1.5)
3. `bm25_retriever.py` and tests remain for later fix

---

## 5. Increment 2: MMR Diversity

### 4.1 Deliverables

| File | Action | Description |
|------|--------|-------------|
| `backend/vector/dual_vector_store.py` | MODIFY | Add `mmr_select()` utility, `search_items_mmr()`, `search_sections_mmr()`. |
| `backend/retrieval/human_like_retriever.py` | MODIFY | Use MMR search when `enable_mmr=True` in global fallback path. |
| `tests/test_phase8_mmr.py` | CREATE | ~150 lines. Unit tests for MMR selection + integration. |

### 4.2 Implementation Steps

**Step 2.1: Implement `mmr_select()` in `dual_vector_store.py`**

```python
def mmr_select(query_embedding, candidate_embeddings, candidate_results, 
               top_k, lambda_mult=0.7):
    """Maximal Marginal Relevance selection.
    
    Greedy O(k×n) algorithm:
    For each slot in top_k:
        score = lambda * sim(query, doc) - (1-lambda) * max(sim(doc, selected))
        Pick doc with highest score
    """
```

**Step 2.2: Add `search_items_mmr()` and `search_sections_mmr()`**

- Call existing ChromaDB `query()` with `n_results = top_k * mmr_fetch_multiplier`
- Also request `include=["embeddings", "documents", "metadatas", "distances"]`
- Pass embeddings to `mmr_select()` to get diverse subset

**Step 2.3: Write `test_phase8_mmr.py`**

- `test_mmr_select_basic()` — 10 candidates, 3 selected, verify diversity > simple top-3
- `test_mmr_lambda_1_equals_standard()` — lambda=1.0 → same as vanilla top-k
- `test_mmr_lambda_0_max_diversity()` — lambda=0.0 → each selected doc very different
- `test_mmr_fewer_candidates_than_k()` — graceful handling
- `test_mmr_single_candidate()` — edge case
- `test_search_items_mmr_integration()` — mock ChromaDB, verify MMR called

**Step 2.4: Run MMR unit tests**  
```bash
pytest tests/test_phase8_mmr.py -v
```
Gate: **ALL PASS**

**Step 2.5: Integrate into retriever**

- In `human_like_retriever.py`, Step 5 (global fallback):
  - Change `self.dual_store.search_items(query, top_k)` → `self.dual_store.search_items_mmr(query, top_k)` when `enable_mmr=True`

**Step 2.6: Run full regression**
```bash
pytest tests/ -v --tb=short
cd extension && npm test
```
Gate: **ALL tests PASS**

### 4.3 Rollback Plan

Set `enable_mmr = False` → reverts to vanilla top-k ChromaDB search. MMR code remains but is unused.

---

## 6. Increment 3: Token-Aware Trimming

### 5.1 Deliverables

| File | Action | Description |
|------|--------|-------------|
| `extension/chat/participant.js` | MODIFY | Add `trimContextToTokenBudget()` function, call it in `generateAnswer()`. |
| `tests/test_phase8_token_trim.js` | CREATE | ~100 lines. Unit tests for trimming logic. |

### 5.2 Implementation Steps

**Step 3.1: Implement `trimContextToTokenBudget()` in `participant.js`**

```javascript
const TOKEN_RATIO = 4;       // ~4 chars per token
const RESERVED_TOKENS = 2900; // system prompt + query + answer buffer
const MAX_CONTEXT_TOKENS = 4096 - RESERVED_TOKENS; // ~1196 tokens for context

function trimContextToTokenBudget(blocks, maxTokens = MAX_CONTEXT_TOKENS) {
    let totalChars = 0;
    const maxChars = maxTokens * TOKEN_RATIO;
    const kept = [];
    
    for (const block of blocks) {
        if (totalChars + block.length > maxChars) {
            // Add partial block if room
            const remaining = maxChars - totalChars;
            if (remaining > 200) { // at least 200 chars to be useful
                kept.push(block.substring(0, remaining) + '\n[...truncated]');
            }
            break;
        }
        kept.push(block);
        totalChars += block.length;
    }
    
    return kept.join('\n\n');
}
```

**Step 3.2: Integrate into `generateAnswer()`**

- After `buildLegalContextBlock()` / `buildContextBlock()` returns array of blocks
- Before constructing the LM API messages:
  ```javascript
  const trimmedContext = trimContextToTokenBudget(contextBlocks);
  ```

**Step 3.3: Write `test_phase8_token_trim.js`**

- `test_trim_short_context_unchanged()` — context within budget → no trimming
- `test_trim_long_context_truncated()` — context exceeds budget → trimmed with indicator
- `test_trim_empty_blocks()` — no blocks → empty string
- `test_trim_single_huge_block()` — one block exceeds budget → partial + truncation message
- `test_trim_respects_token_ratio()` — verify ~4 chars per token estimation

**Step 3.4: Run JS tests**
```bash
cd extension && npm test
```
Gate: **ALL JS tests PASS**

### 5.3 Rollback Plan

Risk is effectively zero — trimming only removes excess context that would overflow anyway. In worst case, remove the `trimContextToTokenBudget()` call to restore previous behavior.

---

## 7. Increment 4: Parent-Child Linking

### 6.1 Deliverables

| File | Action | Description |
|------|--------|-------------|
| `backend/agents/ingestion_agent.py` | MODIFY | Add `parent_section_id` to item metadata during hierarchical ingestion. |
| `backend/vector/dual_vector_store.py` | MODIFY | Add `get_items_by_parent()` query method. |
| `backend/retrieval/human_like_retriever.py` | MODIFY | Add Step 6a: parent section expansion after RRF fusion. |
| `tests/test_phase8_parent_child.py` | CREATE | ~200 lines. Unit + integration tests. |

### 6.2 Implementation Steps

**Step 4.1: Modify ingestion to add `parent_section_id`**

In `ingestion_agent.py`, during hierarchical ingestion where items are extracted from sections:

```python
# Current: item metadata = {doc_id, source_path, chunk_index, doc_type}
# Phase 8: item metadata += {parent_section_id: section.chunk_id}
```

This is the only **schema-breaking change** in Phase 8. Existing items without `parent_section_id` are handled gracefully:

```python
parent_id = item_metadata.get("parent_section_id", None)
if parent_id:
    # expand to parent section
```

**Step 4.2: Add `get_items_by_parent()` to `dual_vector_store.py`**

```python
def get_items_by_parent(self, parent_section_id: str) -> List[Dict]:
    """Retrieve all items that belong to a parent section."""
    results = self.item_collection.get(
        where={"parent_section_id": parent_section_id}
    )
    return self._format_results(results)
```

**Step 4.3: Add parent expansion in retriever**

After Step 6 (RRF fusion), insert Step 6a:

```python
def _expand_items_to_parent_sections(self, item_results, max_parents=10):
    """For each item result, fetch the parent section for richer context."""
    seen_parents = set()
    expanded = []
    
    for item in item_results:
        parent_id = item.get("metadata", {}).get("parent_section_id")
        if parent_id and parent_id not in seen_parents:
            seen_parents.add(parent_id)
            parent = self.dual_store.get_section_by_id(parent_id)
            if parent:
                expanded.append({
                    **parent,
                    "_child_match_score": item.get("score", 0),
                    "_matched_via": "parent_expansion"
                })
            if len(seen_parents) >= max_parents:
                break
    
    return expanded
```

**Step 4.4: Write `test_phase8_parent_child.py`**

- `test_ingestion_adds_parent_section_id()` — ingest doc, verify items have parent metadata
- `test_parent_expansion_basic()` — item with parent_id → section text returned
- `test_parent_expansion_dedup()` — 3 items same parent → 1 section returned
- `test_parent_expansion_missing_metadata()` — items without parent_id → graceful skip
- `test_parent_expansion_max_parents()` — verify limit is respected
- `test_get_items_by_parent()` — ChromaDB where-filter works
- `test_backward_compat_old_items()` — old items (no parent_id) still work in pipeline

**Step 4.5: Run tests**
```bash
pytest tests/test_phase8_parent_child.py -v
pytest tests/ -v --tb=short
```
Gate: **ALL tests PASS** including backward compatibility

**Step 4.6: Build and verify**
```powershell
.\scripts\build_backend.ps1
# Build VSIX
.\scripts\build_vsix.ps1
```

### 6.3 Rollback Plan

1. Set `enable_parent_expansion = False` → skips Step 6a entirely
2. Old items without `parent_section_id` continue to work (backward compatible)
3. If ingestion broke, re-ingest without the parent-child modification

---

## 8. Increment 5: Targeted HyPE (Hypothetical Prompt Embeddings)

### 8.1 What Is It?

At ingestion time, for each high-value chunk (definitions and trigger/event provisions), use the Copilot LM API to generate 3-5 questions that the chunk answers. Embed those questions and store them in a dedicated `item_questions` ChromaDB collection. At query time, search both `items` (text match) and `item_questions` (question match), merge via RRF. Result: definition queries match the question *"What is the Closing Date?"* against chunk embeddings rather than definition text — dramatically better for natural-language queries.

**Pattern reused from:** `extension/lib/image_describer.js` — the same batch LLM + graceful skip pattern.

### 8.2 Scope: Targeted, Not Full Corpus

| Chunk Type | Apply HyPE? | Estimated Count per PSA |
|-----------|------------|------------------------|
| DEFINITIONS section items | Yes | 50-100 |
| EVENT/TRIGGER provisions | Yes | 30-50 |
| ARTICLE headings | Yes | 20-30 |
| Regular section text | No | 800+ |
| **Total LLM calls per document** | | **~100-180** |

### 8.3 Deliverables

| File | Action | Description |
|------|--------|-------------|
| `extension/lib/hype_enricher.js` | CREATE | ~150 lines. Batch question generation using VS Code LM API. |
| `backend/vector/dual_vector_store.py` | MODIFY | Add `item_questions` ChromaDB collection. `add_item_questions()`, `search_item_questions()`. |
| `backend/retrieval/human_like_retriever.py` | MODIFY | Search `item_questions` in parallel with `items`, merge via RRF. |
| `extension/commands/ingest.js` | MODIFY | After ingestion completes, trigger `hype_enricher.js` for definition/trigger chunks. |
| `tests/test_phase8_hype.py` | CREATE | ~120 lines. Unit + integration tests. |
| `tests/test_phase8_hype.js` | CREATE | ~80 lines. JS tests for question generation. |

### 8.4 Architecture

```
Ingestion flow (JS layer):
  kts.ingest → backend finishes → ingest.js receives chunk list
  → filter definition + trigger chunks
  → for each targeted chunk (batched, 5 at a time):
      LLM prompt: "Generate 4 questions this text answers:\n{chunk}"
      LLM response: ["What is X?", "How is X defined?", ...]
  → POST to new backend endpoint: /questions/add
  → backend embeds questions, stores in item_questions collection
  → marks chunk as questions_ready=true in metadata
  → graceful skip on rate limit: marks chunk as questions_pending=true

Retrieval flow (Python layer):
  query → search item_questions (vector similarity)
  → merge with item + section results via RRF (weight: 0.3 questions / 0.4 BM25 / 0.3 vector)
  → cross-encoder reranks combined pool
```

### 8.5 Implementation Steps

**Step 5.1: Add `item_questions` collection to `dual_vector_store.py`**

```python
self.question_collection = self.client.get_or_create_collection(
    name="item_questions",
    embedding_function=self.embedding_fn,
    metadata={"hnsw:space": "cosine"}
)

def add_item_questions(self, chunk_id: str, questions: List[str]) -> None:
    """Store question embeddings linked to a chunk."""
    for i, question in enumerate(questions):
        self.question_collection.add(
            ids=[f"{chunk_id}_q{i}"],
            documents=[question],
            metadatas=[{"source_chunk_id": chunk_id}]
        )

def search_item_questions(self, query: str, top_k: int = 10) -> List[Dict]:
    """Search questions, return source chunk IDs."""
    results = self.question_collection.query(
        query_texts=[query], n_results=top_k
    )
    # Return source chunks by resolving chunk IDs
    return self._resolve_source_chunks(results)
```

**Step 5.2: Create `extension/lib/hype_enricher.js`**

```javascript
async function enrichChunksWithQuestions(vscode, runCli, chunks, outputChannel) {
    const model = await selectChatModel(vscode, null);
    if (!model) {
        outputChannel.appendLine('[HyPE] No LLM available — skipping question enrichment');
        return { enriched: 0, pending: chunks.length, failed: 0 };
    }
    
    const BATCH_SIZE = 5;
    const QUESTION_PROMPT = [
        'Generate exactly 4 questions that this legal text directly answers.',
        'Return only the questions, one per line, no numbering.',
        'Focus on: what is defined, who is responsible, when does it trigger, how is it calculated.',
        '\nText:',
    ].join('\n');
    
    // ... batch processing with rate-limit handling (same pattern as image_describer.js)
}
```

**Step 5.3: Wire into `ingest.js`**

After `runCli(['ingest', ...])` completes successfully:
```javascript
const definitionChunks = ingestResult.chunks
    .filter(c => c.chunk_type === 'definition' || c.chunk_type === 'trigger');
if (definitionChunks.length > 0) {
    await enrichChunksWithQuestions(vscode, runCli, definitionChunks, outputChannel);
}
```

**Step 5.4: Expose a `/enrich_questions` chat command**

For re-running enrichment on demand (e.g., after rate-limit failures):
```
@kts /enrich_questions
→ Re-runs HyPE for all chunks marked questions_pending=true
```

**Step 5.5: Write tests, run regression, build**

Same gate pattern as all other increments.

### 8.6 Rollback Plan

1. Remove `search_item_questions()` from retrieval pipeline (question collection stays but is unused)
2. `item_questions` collection can be dropped without affecting any other collection
3. No changes to existing `items` or `sections` metadata

---

## 9. Increment 6: Multi-Query RAG Fusion

### 9.1 What Is It?

Instead of sending the user's raw query directly to retrieval, the system first asks an LLM to generate **4-5 semantically diverse query variants** covering different angles of the same question. Each variant is executed against the full retrieval pipeline (BM25 + vector + HyPE where applicable). All result sets are pooled and merged using **Reciprocal Rank Fusion (RRF)**, then the unified pool is reranked by the cross-encoder before passing the top-K to the final LLM.

**Why 4-5 variants and not 10?** Diminishing returns kick in after 5 — the embedding space saturates and duplicates dominate. 4-5 variants reliably cover:
- Literal phrasing (user's original query)
- Synonym/paraphrase angle
- Broader definitional angle ("what is X")
- Application/consequence angle ("when does X apply")
- Exception/edge-case angle ("what are the limits of X")

**Relationship to existing code:** `decompose_query()` in `human_like_retriever.py` (Step 2 of the 11-step pipeline) already does rule-based sub-query decomposition for compound questions. Increment 6 replaces this with LLM-based expansion that is broader and applied to all queries, not just compound ones.

### 9.2 Architecture

```
JS Layer (participant.js)
  └─ expandQueryWithLLM(vscode, model, userQuery)
       └─ LLM prompt: "Generate 4 alternative phrasings..."
       └─ returns: string[]  (4-5 variants, first = original)

  └─ POST /retrieve  { query: originalQuery, extra_queries: [v1, v2, v3, v4] }

Backend (human_like_retriever.py)
  └─ for each query in [query] + extra_queries:
       └─ run steps 1-7 of existing pipeline (hybrid BM25+vector+HyPE)
       └─ collect (chunk, score) pairs
  └─ RRF merge all per-query ranked lists (k=60)
  └─ cross-encoder reranks merged pool
  └─ return top-K to JS
```

**Data flow:**
- 5 queries × top-5 per query = 25 candidate chunks in pool (before dedup)
- After dedup by chunk ID: typically 15-22 unique chunks
- Cross-encoder reranks to top-6 for final LLM context

### 9.3 Deliverables

**Python backend:**
- `human_like_retriever.py`: extend `retrieve()` to accept `extra_queries: list[str] = []` parameter
- `human_like_retriever.py`: new `_run_single_query_pipeline(query, steps_1_7)` helper that returns `list[tuple[chunk, score]]`
- `human_like_retriever.py`: new `_rrf_merge(ranked_lists, k=60)` for fusing multiple result lists
- `human_like_retriever.py`: update Step 2 to skip rule-based `decompose_query()` when `extra_queries` is provided
- `backend/api` or router: pass `extra_queries` from request body through to retriever

**JS extension:**
- `extension/lib/query_expander.js` (new file): `expandQueryWithLLM(vscode, model, query)` → returns `string[]`
- `extension/chat/participant.js`: call `expandQueryWithLLM()` before `ktsTool()`, pass variants into the tool call
- `extension/chat/ktsTool.js` (or equivalent): forward `extra_queries` to the `/retrieve` backend call

**Config:**
- `config/settings.py`: `MULTI_QUERY_ENABLED = True`, `MULTI_QUERY_VARIANTS = 4`
- `config/settings.py`: `MULTI_QUERY_POOL_SIZE = 5` (top-K per variant query)

### 9.4 LLM Prompt for Query Expansion

```
System: You are a legal document retrieval assistant. Given a user question about insurance or legal compliance, generate 4 alternative phrasings that cover different angles. Return only the 4 variants as a JSON array of strings. Do not repeat the original question.

User: {query}

Example output:
["What is the definition of insured under this policy?",
 "How does the policy define who qualifies as an insured party?",
 "Insured definition coverage scope",
 "Who is covered as an insured person in this agreement?"]
```

### 9.5 Implementation Steps

**Step 6.1: Backend — extend retriever for multi-query**

1. Add `extra_queries: list[str] = []` to `retrieve()` signature in `human_like_retriever.py`
2. Extract steps 1-7 (semantic parse → hybrid fetch) into `_run_single_query_pipeline(q)`
3. Run pipeline for `[query] + extra_queries`, collect per-query `(chunk, rank)` lists
4. Implement `_rrf_merge()`: `score = Σ 1/(k + rank_i)` for each chunk across all lists
5. Pass merged pool to existing cross-encoder reranking (steps 8-11 unchanged)

**Step 6.2: JS — query expansion module**

1. Create `extension/lib/query_expander.js`
2. Implement `expandQueryWithLLM(vscode, model, query)` using the same `model.sendRequest()` pattern as `image_describer.js`
3. Parse JSON array response with fallback (`if not array → return []`)
4. Guard: if expansion fails or returns < 2 items, proceed with original query only (no extra_queries)

**Step 6.3: Wire together in participant.js**

1. Import `expandQueryWithLLM` from `query_expander.js`
2. Before calling the retrieval tool, call `expandQueryWithLLM(vscode, copilotModel, userQuery)`
3. Pass resulting array as `extra_queries` in the payload to `ktsTool` / backend
4. Add config check: `if (!settings.MULTI_QUERY_ENABLED) skip expansion`

**Step 6.4: Pass through backend API layer**

1. Update `/retrieve` request schema to accept optional `extra_queries: string[]`
2. Forward to `human_like_retriever.retrieve(query, extra_queries=extra_queries)`

### 9.6 Latency Analysis

| Operation | Added Latency | Mitigation |
|-----------|--------------|------------|
| LM API call for expansion | ~500-800ms | Non-blocking (runs before spinner starts) |
| 4× extra pipeline runs (BM25+vector) | ~200-400ms | Each is fast; no LLM calls in Python pipeline |
| RRF merge + cross-encoder on larger pool | ~50-100ms | Cross-encoder already runs on 15-25 chunks |
| **Total overhead** | **~750ms-1300ms** | Acceptable for richer answer quality |

### 9.7 Rollback Plan

1. Set `MULTI_QUERY_ENABLED = False` in settings — JS skips expansion, sends single query as before
2. `extra_queries = []` → backend takes existing single-query path untouched
3. `query_expander.js` is standalone — removal has zero impact on any other extension component
4. Python `_rrf_merge()` is only called when `len(extra_queries) > 0`, so it is dead code when disabled

---

## 10. Increment 7: N-Level Definition Chain Traversal

### 10.1 What Is It?

After primary retrieval returns chunks, extract every Capitalized Term (potential defined term) from the result text. For each term, do a BFS traversal through the graph via `REFERENCES`/`REFERS_TO`/`DEPENDS_ON` edges to depth N (default N=5). For any term not found in the graph, issue a targeted ChromaDB vector search filtered by `item_type=definition`. Inject all resolved definitions into the answer context.

**Key insight from the Bear Stearns trace:** The response correctly identified 8 unresolved nested terms (Pass-Through Rate, Accrual Period, etc.) but did nothing about them. This increment closes that gap — automatically, without any LLM, in ~100ms.

**Infrastructure already built:**
- `backend/retrieval/term_resolver.py` — `TermResolver` with BFS to `max_depth=5`, cycle detection, `TermResolution` dataclass
- `_definition_index` in `HumanLikeRetriever` — term (lowercase) → graph node ID
- `enrich_with_definitions()` in `HumanLikeRetriever` — already extracts terms, just stops at depth 1
- `should_activate_resolver()` — activation gate already exists

**What's missing:** Wiring `TermResolver` into the main pipeline, and a ChromaDB fallback when the graph doesn't have definition items populated.

### 10.2 Two-Path Algorithm

```
For each Capitalized Term T in retrieval results:

  Path A — Graph (fast, zero network calls):
    1. Look up T in _definition_index
    2. If found → call TermResolver.resolve_term(T, graph, max_depth=N)
    3. Collect all closure terms + their definition text

  Path B — ChromaDB fallback (when graph misses):
    4. If T not in _definition_index:
       → dual_store.search_items(f"definition of {T}", top_k=3,
                                  filters={"item_type": "definition"})
    5. Return top result as definition

  Stop conditions:
    - max_depth reached (default 5)
    - Cycle detected (already in TermResolution.cycles_detected)
    - Token budget exhausted (default 2000 tokens)
    - Term already resolved in this query
```

### 10.3 PSA Plain-Colon Pattern Fix

The existing `_extract_defined_term()` doesn't match PSA-style plain colon definitions:
```
"Current Interest: As of any Distribution Date..."
```
(No smart quotes around the term.) Fix to `legal_chunker.py` and `human_like_retriever.py`:

```python
# Add to _extract_defined_term():
# Pattern: TERM: description (plain colon, no quotes, term is first N words before colon)
m3 = re.match(r'^([A-Z][A-Za-z\s]{2,60}?):\s+', definition_text.strip())
if m3:
    candidate = m3.group(1).strip()
    # Sanity check: should look like a defined term (Title Case, not a sentence)
    if re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*$', candidate):
        return candidate
```

### 10.4 Deliverables

- `backend/retrieval/human_like_retriever.py`: extend `enrich_with_definitions()` to call `TermResolver` for graph-found terms
- `backend/retrieval/human_like_retriever.py`: add `_resolve_term_from_vector()` ChromaDB fallback
- `backend/retrieval/human_like_retriever.py`: fix `_extract_defined_term()` for plain-colon PSA pattern
- `backend/retrieval/human_like_retriever.py`: expose resolved chain in `injected_definitions` metadata so it surfaces in the Definition Chain section of the response
- `config/settings.py`: `DEFINITION_TRAVERSAL_DEPTH = 5`, `DEFINITION_TRAVERSAL_ENABLED = True`

### 10.5 Rollback Plan

1. `DEFINITION_TRAVERSAL_ENABLED = False` → `enrich_with_definitions()` takes existing depth-1 path
2. `TermResolver` is called only inside the enrichment step — zero blast radius

---

## 11. Increment 8: Self-RAG Iterative Generation Loop

### 11.1 What Is It?

The LLM generates an initial answer from the retrieved chunks, then **self-critiques** that answer against the original user query to identify remaining gaps. The gaps become new retrieval queries. New chunks are merged with the original context and the LLM produces an improved answer. This loop continues until the LLM reports no remaining gaps, or a safety cap of 3 rounds is reached.

**Academic basis:**
- **FLARE** (Jiang et al. 2023) — Forward-Looking Active REtrieval: model generates and retrieves when uncertain
- **Self-RAG** (Asai et al. 2023) — LLM decides when to retrieve and critiques its own outputs
- **Iterative RAG** — various 2024 implementations for agentic question answering

**Critical difference from existing `IterativeOrchestrator`:** `IterativeOrchestrator` loops at the *retrieval* level (stops when `confidence >= threshold`). This loops at the *generation* level — the LLM is the convergence judge, not a similarity score.

**For the Bear Stearns query:**
- Round 0 → produces the answer shown in the trace (definition found, 8 nested terms unresolved)
- Round 1 gap analysis → `["What is Pass-Through Rate?", "What is Accrual Period?", ...]`
- Round 1 retrieval → fetches those 8 definitions (aided by Inc 7)
- Round 1 synthesis → complete answer with full definition chain
- Round 2 gap analysis → `[]` (fully answered)
- **Done in 2 rounds, ~6-9 seconds total**

### 11.2 Architecture

```
[JS Layer — participant.js]

Round 0:
  1. expandQueryWithLLM()          → 4-5 variants (Inc 6)
  2. POST /retrieve {variants}     → initial_chunks (top-K)
  3. LLM(initial_chunks, query)    → initial_answer

Round N (max_iterations=3):
  4. LLM(gap_analysis_prompt):
       Input:  {original_query, current_answer}
       Output: JSON array of gap questions, or []
  5. If gaps == [] → STOP, stream current_answer to user
  6. POST /retrieve {gap_queries}  → new_chunks (dedup vs. previous)
  7. LLM(synthesis_prompt):
       Input:  {original_query, current_answer, new_chunks}
       Output: improved_answer
  8. current_answer = improved_answer, loop to step 4

Safety:
  - max_iterations = 3 (configurable)
  - If round N returns same gap questions as round N-1 → STOP (no progress)
  - chunk_ids_seen set: never send same chunk twice
```

### 11.3 LLM Prompts

**Gap Analysis Prompt:**
```
You are a legal document analyst checking whether a draft answer is complete.

Original question: {original_query}

Draft answer:
{current_answer}

Identify specific sub-questions or Capitalized Terms that are referenced in the
draft answer but not yet fully defined or explained. Return ONLY a JSON array
of string queries to send to the document retrieval system.
Return [] if the answer is complete.

Example output:
["What is the Pass-Through Rate?",
 "Define Accrual Period in this PSA",
 "What are Relief Act Interest Shortfalls?"]
```

**Synthesis Prompt:**
```
You are a legal document analyst producing a comprehensive answer.

Original question: {original_query}

Previous answer draft:
{current_answer}

Additional retrieved context:
{new_chunks}

Produce an improved, combined answer that incorporates the new context.
Do not repeat the previous answer verbatim — integrate and expand.
Maintain the document-grounded format (definitions, excerpts, gaps).
```

### 11.4 Deliverables

**JS extension:**
- `extension/lib/gap_analyzer.js` (new): `analyzeGaps(vscode, model, originalQuery, currentAnswer)` → `string[]`
- `extension/lib/iterative_generator.js` (new): orchestrator that runs the round loop
- `extension/chat/participant.js`: replace single LLM call with `await iterativeGenerate(...)` call

**Python backend:**
- `backend/api` (or router): extend `/retrieve` to accept `exclude_chunk_ids: string[]` to prevent re-serving seen chunks
- `backend/retrieval/human_like_retriever.py`: filter out `exclude_chunk_ids` from results

**Config:**
- `config/settings.py`: `SELF_RAG_ENABLED = True`, `SELF_RAG_MAX_ROUNDS = 3`, `SELF_RAG_MODEL = "gpt-4o"` (or "gpt-4.1")
- `extension/lib/settings.js`: `selfRagEnabled`, `selfRagMaxRounds`

### 11.5 Latency Budget

| Operation | Latency | Notes |
|-----------|---------|-------|
| Round 0 retrieval | ~500-800ms | Existing pipeline |
| Round 0 generation (GPT-4o) | ~2-4s | Initial answer |
| Gap analysis (GPT-4o) | ~500-800ms | Small prompt, fast |
| Round N retrieval | ~300-500ms | Fewer queries, targeted |
| Round N synthesis (GPT-4o) | ~2-4s | Incremental update |
| **2-round total** | **~6-10s** | Acceptable for legal analysis |
| **3-round total** | **~10-16s** | Max case |

### 11.6 Rollback Plan

1. `SELF_RAG_ENABLED = False` → `participant.js` falls back to single LLM call (exact current behavior)
2. `gap_analyzer.js` and `iterative_generator.js` are standalone — zero impact on existing code
3. Backend `exclude_chunk_ids` parameter is optional — ignored when not sent

---

## 12. Final Integration

After all 9 increments pass individually:

### 12.1 Combined Integration Test

```bash
# Enable all features
KTS_BM25_ENABLED=true KTS_MMR_ENABLED=true KTS_PARENT_EXPAND=true \
KTS_DEFINITION_TRAVERSAL_ENABLED=true KTS_SELF_RAG_ENABLED=true \
pytest tests/ -v --tb=short

# Run golden query benchmark
python tests/score_queries.py --golden tests/golden_queries_v2.json
```

### 12.2 Version Bump

```json
// extension/package.json
"version": "0.0.11"
```

### 10.3 Final Build

```powershell
.\scripts\build_backend.ps1
.\scripts\build_vsix.ps1
```

### 10.4 Acceptance Criteria

| Criterion | Threshold | Measurement |
|-----------|-----------|-------------|
| All existing tests pass | 100% | pytest + npm test |
| All new Phase 8 tests pass | 100% | pytest test_phase8_* |
| Golden query MRR@5 improvement | ≥ +5% | score_queries.py |
| Exact-term recall (BM25) | ≥ 80% for legal terms | Manual 5-query spot check |
| Context diversity | No 3+ chunks from same paragraph | Manual inspection |
| No context overflow | Zero truncation errors in logs | VSIX diagnostic output |
| Backend startup time | < 15 seconds (including BM25 index load) | Timed startup |
| Retrieval latency (p50) | < 3 seconds | Timed queries |

---

## 13. Timeline Estimate

| Increment | Estimated Effort | Cumulative |
|-----------|-----------------|------------|
| 0. Contextual Chunk Headers | 1-2 hours | 1-2 hours |
| 1. BM25 Hybrid Search | 3-4 hours | 4-6 hours |
| 2. MMR Diversity | 2-3 hours | 6-9 hours |
| 3. Token Trimming | 1-2 hours | 7-11 hours |
| 4. Parent-Child Linking | 3-4 hours | 10-15 hours |
| 5. Targeted HyPE | 3-5 hours | 13-20 hours |
| 6. Multi-Query RAG Fusion | 2-3 hours | 15-23 hours |
| 7. N-Level Definition Traversal | 2-3 hours | 17-26 hours |
| 8. Self-RAG Iterative Generation | 4-6 hours | 21-32 hours |
| Final integration + golden tests | 2-3 hours | 23-35 hours |

**Total: ~3–4.5 working days**

---

## 14. Risk Matrix

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| BM25 index too large for VSIX | Low | Medium | Index is ~2-5 MB JSON, within limits. Monitor. |
| MMR numpy dependency missing in bundle | Low | High | numpy already in PyInstaller bundle (verified). |
| Parent-child re-ingestion breaks existing docs | Medium | High | Backward-compatible metadata check. Old docs work without parent_id. |
| Token trimming cuts critical context | Low | Medium | Blocks ordered by relevance score. Most important content kept. |
| BM25 slow on large corpora (>10K docs) | Low | Medium | Pre-computed IDF, inverted index. O(n) per query for n matching docs. |
| Cross-encoder scores differ with parent sections | Medium | Low | Parent sections are longer but more contextual. Cross-encoder adapts. |
| Definition graph not populated (ingestion gap) | High | Medium | ChromaDB fallback (Path B) — works even when graph is empty. Fix ingestion separately. |
| Self-RAG loop never terminates | Low | High | Hard cap: max_iterations=3. Progress guard: stop if same gaps returned twice. |
| Self-RAG increases latency above user tolerance | Medium | Medium | Feature flag. Show progressive streaming per round so user sees partial answer immediately. |
| GPT-4o unavailable / model switch | Low | Low | Model configured per-tenant in settings. Fallback to existing single-round path. |

---

## 15. Dependencies Between Increments

```
Increment 0 (CCH)              ─── Independent. Benefits all future ingestions.
Increment 1 (BM25)             ─── Independent.
Increment 2 (MMR)              ─── Independent.
Increment 3 (Token Trim)       ─── Independent (JS only).
Increment 4 (Parent-Child)     ─── Benefits from BM25+MMR. Schema change triggers re-ingestion which picks up CCH.
Increment 5 (HyPE)             ─── Benefits from BM25 (RRF fusion). Requires item_questions collection.
Increment 6 (Multi-Query)      ─── Benefits from all retrieval increments (richer pool).
Increment 7 (Def Traversal)    ─── Uses graph+ChromaDB directly. Benefits from CCH (better embeddings on defs).
Increment 8 (Self-RAG)         ─── Superset: calls retrieval (Inc 1+6+7) then generates. Highest value last.

     0 ──────────────────────────────────────→ 4 (re-ingestion picks up CCH improvements)
     1 ───┐                                         │
     2 ───┼──→ 4 (parent expansion + MMR) ──────────┘
     3 ───┘                                    ↑
     1 ──→ 5 (RRF fusion includes HyPE lane)   │
     0 ──→ 7 (better def embeddings)            │
     1,2,5,6,7 ──→ 8 (Self-RAG calls everything above)

                          ↓
                  Final Integration
```

All increments can be developed in parallel but serial development is strongly recommended — each increment provides a regression baseline for the next.
