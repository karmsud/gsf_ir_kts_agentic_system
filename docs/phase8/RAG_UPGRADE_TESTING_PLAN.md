# Phase 8: RAG Upgrade — Testing Plan

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Testing Philosophy

Every Phase 8 increment follows a **layered testing approach**:

```
Layer 1: Unit Tests        — Isolated algorithm correctness
Layer 2: Integration Tests — Component interactions
Layer 3: Regression Tests  — Existing functionality preserved
Layer 4: Golden Tests      — End-to-end retrieval quality
Layer 5: Smoke Tests       — Manual VSIX verification
```

**Zero-regression policy:** All 344 existing Python tests and 74 JS tests must pass at every gate. New tests only add to the count — never replace.

---

## 2. Test Matrix by Increment

### 2.0 Increment 0: Contextual Chunk Headers (CCH)

| Test File | Count | Type | Description |
|-----------|-------|------|-------------|
| `tests/test_phase8_cch.py` | 7 | Unit | Header builder and embedding text separation |
| `tests/test_phase8_cch.py` | 3 | Integration | Chunker end-to-end with CCH enabled |
| `tests/` (existing) | 344 | Regression | Full existing suite |

#### Unit Tests — CCH Header Builder

```python
class TestCCHHeaderBuilder:
    """Unit tests for build_cch_header() and embedding text generation."""

    def test_header_all_fields_present(self):
        """All three fields produce correct [DOC: | TYPE: | SECTION:] format."""
        header = build_cch_header(
            doc_name="PSA-2006HE1",
            doc_type="legal",
            section_title="Article 2 - Definitions"
        )
        assert header == "[DOC: PSA-2006HE1 | TYPE: legal | SECTION: Article 2 - Definitions]\n"

    def test_header_missing_doc_type(self):
        """Missing doc_type omits TYPE field but keeps DOC and SECTION."""
        header = build_cch_header(doc_name="PSA", doc_type="", section_title="Art 2")
        assert "TYPE:" not in header
        assert "DOC: PSA" in header

    def test_header_all_empty_returns_empty(self):
        """All None/empty inputs return empty string (no-op fallback)."""
        assert build_cch_header("", "", "") == ""
        assert build_cch_header(None, None, None) == ""

    def test_header_section_title_truncated_at_80_chars(self):
        """Section titles over 80 chars are truncated."""
        long_title = "A" * 100
        header = build_cch_header("DOC", "legal", long_title)
        assert len([p for p in header.split("|") if "SECTION:" in p][0].strip()) <= 90

    def test_embedding_text_includes_header(self):
        """_create_chunk_for_embedding() returns header + content concatenated."""
        text = "Closing Date means the date of closing."
        result = _create_chunk_for_embedding(text, {
            "doc_name": "PSA", "doc_type": "legal", "section_title": "Art 2"
        })
        assert result.startswith("[DOC: PSA")
        assert "Closing Date means" in result

    def test_stored_metadata_text_is_clean(self):
        """ChromaDB metadatas['text'] contains clean text without CCH header."""
        chunk = create_chunk_with_cch("Closing Date means...", metadata)
        assert not chunk["metadata"]["text"].startswith("[DOC:")

    def test_cch_disabled_by_flag(self):
        """ENABLE_CCH=False → no header prepended, identical to pre-Phase 8 behavior."""
        with override_settings(ENABLE_CCH=False):
            result = _create_chunk_for_embedding("text", metadata)
            assert not result.startswith("[DOC:")

    def test_cch_does_not_affect_display_text(self):
        """User-facing response from retriever contains clean text, no header artifact."""
        # Integration test: ingest chunk with CCH, retrieve, verify display text is clean
        ...

    def test_cch_improves_cross_doc_disambiguation(self):
        """Two identical chunks from different docs should have different embeddings after CCH."""
        # Compare cosine similarity: with CCH should be < without CCH for same-text different-doc chunks
        ...

    def test_cch_integration_with_legal_chunker(self):
        """legal_chunker.py correctly attaches CCH headers during chunking."""
        ...
```

---

### 2.1 Increment 1: BM25 Hybrid Search

| Test File | Count | Type | Description |
|-----------|-------|------|-------------|
| `tests/test_phase8_bm25.py` | 12 | Unit | BM25Retriever class in isolation |
| `tests/test_phase8_bm25.py` | 5 | Integration | BM25 + retriever pipeline |
| `tests/` (existing) | 344 | Regression | Full existing suite |
| `extension/` (existing) | 74 | Regression | Full JS suite |

#### Unit Tests — BM25Retriever

```python
class TestBM25Retriever:
    """Unit tests for BM25Retriever algorithm correctness."""

    def test_build_index_creates_inverted_index(self):
        """Given 3 documents, build_index() creates index with correct terms."""
        docs = [
            {"id": "1", "content": "The Closing Date is defined as January 15"},
            {"id": "2", "content": "Distribution Date means the 25th of each month"},
            {"id": "3", "content": "The Trust shall terminate on the Closing Date"},
        ]
        retriever = BM25Retriever(persist_dir="/tmp/test")
        retriever.build_index(docs)
        assert "closing" in retriever._inverted_index
        assert "date" in retriever._inverted_index
        assert len(retriever._inverted_index["closing"]) == 2  # docs 1, 3

    def test_search_exact_term_ranked_first(self):
        """Query 'Closing Date' should rank docs containing that exact phrase highest."""
        # ... build index with 10 docs, 3 mentioning "Closing Date"
        results = retriever.search("Closing Date", top_k=5)
        assert results[0]["id"] in ["1", "3"]  # docs with "Closing Date"
    
    def test_search_rare_term_scores_higher(self):
        """Rare terms (high IDF) should score higher than common terms."""
        # Doc with rare legal term "subordination" should outrank doc with "the"
        results = retriever.search("subordination", top_k=3)
        assert results[0]["content"].find("subordination") >= 0

    def test_search_empty_query_returns_empty(self):
        """Empty query string returns empty results."""
        results = retriever.search("", top_k=5)
        assert len(results) == 0

    def test_search_no_matching_term_returns_empty(self):
        """Query with no matching terms returns empty results."""
        results = retriever.search("xyznonexistent", top_k=5)
        assert len(results) == 0

    def test_search_top_k_limits_results(self):
        """top_k parameter correctly limits result count."""
        # Index 100 docs, request top_k=3
        results = retriever.search("date", top_k=3)
        assert len(results) <= 3

    def test_tokenizer_case_insensitive(self):
        """'CLOSING' and 'closing' should match the same index entry."""
        retriever.build_index([{"id": "1", "content": "CLOSING Date"}])
        results = retriever.search("closing date", top_k=5)
        assert len(results) == 1

    def test_tokenizer_strips_punctuation(self):
        """Punctuation should be stripped: 'date,' → 'date'."""
        retriever.build_index([{"id": "1", "content": "The date, as defined."}])
        results = retriever.search("date", top_k=5)
        assert len(results) == 1

    def test_idf_calculation(self):
        """IDF for term appearing in 1 of 10 docs should be higher than term in 9 of 10."""
        # Build index, verify _idf_cache values
        assert retriever._idf_cache["rare_term"] > retriever._idf_cache["common_term"]

    def test_persistence_save_and_load(self):
        """save_index() then load_index() should produce identical search results."""
        retriever.build_index(docs)
        r1 = retriever.search("Closing Date", top_k=5)
        retriever.save_index()
        
        retriever2 = BM25Retriever(persist_dir=same_dir)
        assert retriever2.load_index() == True
        r2 = retriever2.search("Closing Date", top_k=5)
        assert r1 == r2

    def test_persistence_missing_file_returns_false(self):
        """load_index() returns False when no index file exists."""
        retriever = BM25Retriever(persist_dir="/tmp/empty")
        assert retriever.load_index() == False

    def test_build_index_empty_corpus(self):
        """Building index from empty corpus should not error."""
        retriever.build_index([])
        results = retriever.search("anything", top_k=5)
        assert len(results) == 0
```

#### Integration Tests — BM25 + Pipeline

```python
class TestBM25Integration:
    """Integration tests: BM25 within the full retrieval pipeline."""

    def test_hybrid_search_combines_bm25_and_vector(self):
        """With enable_bm25_hybrid=True, results contain items from both sources."""
        # Ingest docs, one with exact term match (BM25 advantage),
        # one with semantic match (vector advantage)
        # Verify both appear in final results

    def test_rrf_fusion_weights(self):
        """RRF fusion with bm25_weight=0.4, vector_weight=0.6 produces expected ranking."""
        # Verify doc ranked #1 by BM25 and #5 by vector gets appropriate fused rank

    def test_bm25_disabled_falls_back(self):
        """With enable_bm25_hybrid=False, pipeline works exactly as before."""
        # Run pipeline with flag off, verify BM25 step is skipped

    def test_bm25_index_auto_build_on_missing(self):
        """If BM25 index file is missing, it auto-builds from ChromaDB."""

    def test_bm25_index_survives_backend_restart(self):
        """After build + save, restarting backend loads persisted index."""
```

---

### 2.2 Increment 2: MMR Diversity

| Test File | Count | Type | Description |
|-----------|-------|------|-------------|
| `tests/test_phase8_mmr.py` | 10 | Unit | mmr_select() algorithm |
| `tests/test_phase8_mmr.py` | 4 | Integration | MMR within vector store |
| `tests/` (existing) | 344+ | Regression | Full existing suite |

#### Unit Tests — MMR Selection

```python
class TestMMRSelect:
    """Unit tests for MMR diversity selection algorithm."""

    def test_mmr_basic_diversity(self):
        """Given 10 similar candidates, MMR selects 3 that are maximally diverse."""
        # Create embeddings: 3 clusters of ~similar vectors
        # MMR should pick one from each cluster
        selected = mmr_select(query_emb, candidate_embs, candidates, top_k=3)
        assert len(selected) == 3
        # Verify pairwise cosine sim of selected < avg pairwise sim of top-3

    def test_mmr_lambda_1_equals_topk(self):
        """lambda=1.0 means pure relevance → identical to vanilla top-k."""
        mmr_results = mmr_select(q, embs, cands, top_k=3, lambda_mult=1.0)
        topk_results = sorted(cands, key=lambda x: x["score"], reverse=True)[:3]
        assert [r["id"] for r in mmr_results] == [r["id"] for r in topk_results]

    def test_mmr_lambda_0_max_diversity(self):
        """lambda=0.0 means pure diversity → minimize redundancy."""
        selected = mmr_select(q, embs, cands, top_k=3, lambda_mult=0.0)
        # Pairwise similarity of selected should be very low

    def test_mmr_fewer_candidates_than_k(self):
        """If only 2 candidates and top_k=5, return all 2."""
        selected = mmr_select(q, embs, cands[:2], top_k=5)
        assert len(selected) == 2

    def test_mmr_single_candidate(self):
        """Single candidate → returned as-is."""
        selected = mmr_select(q, embs[:1], cands[:1], top_k=3)
        assert len(selected) == 1

    def test_mmr_empty_candidates(self):
        """Empty candidate list → empty result."""
        selected = mmr_select(q, [], [], top_k=3)
        assert len(selected) == 0

    def test_mmr_preserves_metadata(self):
        """Selected results retain all original metadata fields."""
        selected = mmr_select(q, embs, cands, top_k=2)
        assert "metadata" in selected[0]
        assert "source_path" in selected[0]["metadata"]

    def test_mmr_deterministic(self):
        """Same inputs produce same outputs (no random tie-breaking)."""
        r1 = mmr_select(q, embs, cands, top_k=3)
        r2 = mmr_select(q, embs, cands, top_k=3)
        assert [r["id"] for r in r1] == [r["id"] for r in r2]

    def test_mmr_correct_score_calculation(self):
        """Verify score = lambda*sim(q,d) - (1-lambda)*max(sim(d,selected))."""
        # Hand-computed expected scores for small 3-doc example
        # Verify mmr_select picks the correct order

    def test_mmr_handles_zero_embeddings(self):
        """Documents with zero vectors (all 0s) handled without division errors."""
        zero_embs = np.zeros((3, 384))
        selected = mmr_select(q, zero_embs, cands[:3], top_k=2)
        assert len(selected) == 2  # Returns something, doesn't crash
```

#### Integration Tests — MMR with Vector Store

```python
class TestMMRIntegration:
    """Integration tests: MMR within DualVectorStore."""

    def test_search_items_mmr_returns_diverse_set(self):
        """search_items_mmr() returns more diverse results than search_items()."""

    def test_search_sections_mmr_works(self):
        """search_sections_mmr() returns results with MMR diversity."""

    def test_mmr_disabled_uses_vanilla_search(self):
        """enable_mmr=False → falls back to standard ChromaDB search."""

    def test_mmr_fetch_multiplier(self):
        """mmr_fetch_multiplier=3 fetches 3x candidates before MMR selection."""
```

---

### 2.3 Increment 3: Token-Aware Trimming

| Test File | Count | Type | Description |
|-----------|-------|------|-------------|
| `tests/test_phase8_token_trim.js` | 8 | Unit | JS trimming function |
| `extension/` (existing) | 74 | Regression | Full JS suite |

#### Unit Tests — Token Trimming (JavaScript)

```javascript
describe('trimContextToTokenBudget', () => {
    it('returns all blocks when within budget', () => {
        const blocks = ['Short block 1', 'Short block 2'];
        const result = trimContextToTokenBudget(blocks, 1000);
        assert(result.includes('Short block 1'));
        assert(result.includes('Short block 2'));
        assert(!result.includes('[...truncated]'));
    });

    it('truncates when exceeding budget', () => {
        const blocks = ['A'.repeat(5000), 'B'.repeat(5000)]; // ~2500 tokens
        const result = trimContextToTokenBudget(blocks, 500); // 500 token budget
        assert(result.includes('[...truncated]') || !result.includes('B'.repeat(5000)));
    });

    it('handles empty blocks array', () => {
        const result = trimContextToTokenBudget([], 1000);
        assert.strictEqual(result, '');
    });

    it('handles single block exceeding budget', () => {
        const block = 'X'.repeat(10000); // ~2500 tokens
        const result = trimContextToTokenBudget([block], 100); // 100 token budget
        assert(result.length < 10000);
        assert(result.includes('[...truncated]'));
    });

    it('preserves block order (highest relevance first)', () => {
        const blocks = ['FIRST_BLOCK', 'SECOND_BLOCK', 'THIRD_BLOCK'];
        const result = trimContextToTokenBudget(blocks, 1000);
        assert(result.indexOf('FIRST_BLOCK') < result.indexOf('SECOND_BLOCK'));
    });

    it('uses ~4 chars per token estimation', () => {
        // 100 tokens → ~400 chars budget
        const result = trimContextToTokenBudget(['A'.repeat(800)], 100);
        assert(result.length <= 420); // 400 + some padding
    });

    it('respects minimum useful block size (200 chars)', () => {
        // First block fills most of budget, second has < 200 chars room
        const blocks = ['A'.repeat(380), 'B'.repeat(500)]; // ~95 + 125 tokens
        const result = trimContextToTokenBudget(blocks, 100); // 100 token budget
        // Second block should be dropped entirely, not partially included
    });

    it('joins blocks with double newline', () => {
        const blocks = ['Block A', 'Block B'];
        const result = trimContextToTokenBudget(blocks, 1000);
        assert(result.includes('Block A\n\nBlock B'));
    });
});
```

---

### 2.4 Increment 4: Parent-Child Linking

| Test File | Count | Type | Description |
|-----------|-------|------|-------------|
| `tests/test_phase8_parent_child.py` | 10 | Unit | Parent expansion algorithm |
| `tests/test_phase8_parent_child.py` | 5 | Integration | Full pipeline with parent linking |
| `tests/` (existing) | 344+ | Regression | Full existing suite |

#### Unit Tests — Parent-Child

```python
class TestParentChildExpansion:
    """Unit tests for parent-child document linking."""

    def test_ingestion_adds_parent_section_id(self):
        """After ingestion, item metadata contains parent_section_id."""
        # Ingest a legal document with sections containing items
        # Verify item.metadata["parent_section_id"] is set

    def test_parent_expansion_basic(self):
        """Item with parent_section_id → parent section text retrieved."""
        item = {"id": "item_1", "metadata": {"parent_section_id": "sec_1"}, "score": 0.9}
        expanded = retriever._expand_items_to_parent_sections([item])
        assert len(expanded) == 1
        assert expanded[0]["id"] == "sec_1"

    def test_parent_expansion_deduplication(self):
        """Multiple items with same parent_section_id → one parent section."""
        items = [
            {"id": "item_1", "metadata": {"parent_section_id": "sec_1"}, "score": 0.9},
            {"id": "item_2", "metadata": {"parent_section_id": "sec_1"}, "score": 0.8},
            {"id": "item_3", "metadata": {"parent_section_id": "sec_2"}, "score": 0.7},
        ]
        expanded = retriever._expand_items_to_parent_sections(items)
        parent_ids = [e["id"] for e in expanded]
        assert parent_ids.count("sec_1") == 1  # Deduplicated
        assert "sec_2" in parent_ids

    def test_parent_expansion_max_limit(self):
        """max_parent_sections limits the number of expanded parents."""
        items = [{"id": f"item_{i}", "metadata": {"parent_section_id": f"sec_{i}"}, "score": 0.5}
                 for i in range(20)]
        expanded = retriever._expand_items_to_parent_sections(items, max_parents=5)
        assert len(expanded) <= 5

    def test_parent_expansion_no_parent_id_graceful(self):
        """Items without parent_section_id are skipped gracefully."""
        items = [
            {"id": "item_1", "metadata": {}, "score": 0.9},  # No parent_section_id
            {"id": "item_2", "metadata": {"parent_section_id": "sec_1"}, "score": 0.8},
        ]
        expanded = retriever._expand_items_to_parent_sections(items)
        assert len(expanded) == 1  # Only item_2 expanded

    def test_parent_expansion_missing_parent_in_store(self):
        """If parent section ID exists in metadata but not in store, skip gracefully."""
        item = {"id": "item_1", "metadata": {"parent_section_id": "nonexistent_sec"}, "score": 0.9}
        expanded = retriever._expand_items_to_parent_sections([item])
        assert len(expanded) == 0  # Gracefully skipped

    def test_parent_carries_child_score(self):
        """Expanded parent section carries the matched child's score."""
        item = {"id": "item_1", "metadata": {"parent_section_id": "sec_1"}, "score": 0.92}
        expanded = retriever._expand_items_to_parent_sections([item])
        assert expanded[0]["_child_match_score"] == 0.92

    def test_parent_marked_as_expansion(self):
        """Expanded parent has _matched_via='parent_expansion' metadata."""
        item = {"id": "item_1", "metadata": {"parent_section_id": "sec_1"}, "score": 0.9}
        expanded = retriever._expand_items_to_parent_sections([item])
        assert expanded[0]["_matched_via"] == "parent_expansion"

    def test_empty_items_returns_empty(self):
        """Empty input returns empty output."""
        expanded = retriever._expand_items_to_parent_sections([])
        assert len(expanded) == 0

    def test_backward_compat_old_metadata(self):
        """Items ingested before Phase 8 (no parent_section_id) work in full pipeline."""
        # Ingest doc without parent-child linking
        # Run retrieval → should work exactly as before (no errors, same quality)
```

#### Integration Tests — Parent-Child Pipeline

```python
class TestParentChildIntegration:
    """Integration tests: parent-child linking in full retrieval pipeline."""

    def test_full_pipeline_with_parent_expansion(self):
        """End-to-end: ingest doc, query, verify parent sections appear in results."""

    def test_parent_expansion_disabled_skips_step(self):
        """enable_parent_expansion=False → Step 6a skipped entirely."""

    def test_cross_encoder_rescores_parent_sections(self):
        """Parent sections go through cross-encoder reranking (Step 8)."""

    def test_parent_expansion_with_bm25_results(self):
        """BM25 results also get parent expansion (combined Phase 8 features)."""

    def test_reingestion_preserves_existing_data(self):
        """Re-ingesting a doc with parent-child doesn't corrupt existing index."""
```

---

### 2.5 Increment 5: Targeted HyPE

| Test File | Count | Type | Description |
|-----------|-------|------|-------------|
| `tests/test_phase8_hype.py` | 8 | Python unit | Question generation, storage, retrieval from item_questions |
| `tests/test_phase8_hype.py` | 5 | Python integration | End-to-end enrichment + query resolution |
| `tests/test_phase8_hype.js` | 8 | JS unit | hype_enricher.js batching, rate-limit handling, /enrich_questions command |
| `tests/` (existing) | 344 | Regression | Full existing suite |

#### Python Unit Tests — item_questions Collection

```python
class TestHyPEEnrichment:

    def test_store_item_questions_creates_entries(self):
        """store_item_questions(chunk_id, ['Q1', 'Q2', 'Q3']) creates 3 entries in item_questions."""
        dual_store.store_item_questions("chunk_001", ["What is X?", "Define X.", "When does X apply?"])
        results = dual_store.get_item_questions("chunk_001")
        assert len(results) == 3

    def test_search_item_questions_returns_source_chunk(self):
        """Searching item_questions with a matching question returns source_chunk_id."""
        dual_store.store_item_questions("chunk_001", ["What is the Closing Date?"])
        results = dual_store.search_item_questions("Closing Date definition", top_k=5)
        assert results[0]["metadata"]["source_chunk_id"] == "chunk_001"

    def test_mark_questions_pending_sets_flag(self):
        """mark_questions_pending() sets questions_pending=true in item metadata."""
        dual_store.mark_questions_pending("chunk_001")
        meta = dual_store.get_item_metadata("chunk_001")
        assert meta["questions_pending"] is True

    def test_search_no_questions_stored_returns_empty(self):
        """search_item_questions on empty collection → empty results, no error."""
        results = dual_store.search_item_questions("anything", top_k=5)
        assert results == []

    def test_rrf_with_question_lane(self):
        """RRF merge includes question lane at weight 0.3, BM25 at 0.4, vector at 0.3."""
        # Verify the weights in the merged score formula
        ...

    def test_hype_disabled_skips_question_search(self):
        """ENABLE_HYPE=False → search_item_questions() never called."""
        with override_settings(ENABLE_HYPE=False):
            retrieve("What is Closing Date?")
            assert mock_search_item_questions.call_count == 0

    def test_end_to_end_definition_query_resolved(self):
        """After enrichment, 'What is Closing Date?' finds definition chunk in top-3."""
        ...

    def test_end_to_end_trigger_query_resolved(self):
        """After enrichment, 'When does Section 4.02 trigger?' finds trigger chunk in top-3."""
        ...

    def test_questions_pending_chunks_excluded_from_hype_search(self):
        """Chunks with questions_pending=True are still retrievable via vector/BM25
        even though they have no entries in item_questions."""
        ...

    def test_reenrichment_clears_pending_flag(self):
        """After re-running enrichment, questions_pending=False for successfully enriched chunks."""
        ...

    def test_duplicate_enrichment_is_idempotent(self):
        """Running enrichment twice on the same chunk replaces questions (no duplicates)."""
        ...

    def test_rate_limit_error_marks_pending_not_crash(self):
        """Rate limit during enrichment → chunk marked pending, loop continues with next chunk."""
        ...
```

#### JS Unit Tests — hype_enricher.js

```javascript
describe('HyPE Enricher', () => {

    it('processes chunks in batches of 5', async () => {
        // Feed 12 chunks, verify backend called 3 times (batches of 5, 5, 2)
    });

    it('waits 300ms between batches', async () => {
        const spy = sinon.spy(global, 'setTimeout');
        await enrichChunksWithQuestions(vscode, chunkIds);
        assert(spy.calledWith(sinon.match.any, 300));
    });

    it('marks chunk as pending on rate limit error', async () => {
        mockModel.sendRequest = () => { throw new RateLimitError(); };
        await enrichChunksWithQuestions(vscode, ['c1']);
        assert(mockBackend.markQuestionsPending.calledWith('c1'));
    });

    it('continues processing after rate limit error', async () => {
        // 5 chunks, chunk 3 rate-limited → chunks 4 and 5 still processed
    });

    it('skips non-definition non-trigger chunks', async () => {
        // Only chunks with item_type=definition or item_type=trigger are enriched
    });

    it('/enrich_questions command triggers re-enrichment for pending chunks', async () => {
        // Simulate /enrich_questions → verify backend.getChunksByFilter({questions_pending: true}) called
    });

    it('stores generated questions via backendClient.storeItemQuestions', async () => {
        mockModel.sendRequest = () => Promise.resolve('["Q1", "Q2", "Q3"]');
        await enrichChunksWithQuestions(vscode, ['c1']);
        assert(mockBackend.storeItemQuestions.calledWith('c1', ['Q1', 'Q2', 'Q3']));
    });

    it('gracefully handles JSON parse failure in model response', async () => {
        mockModel.sendRequest = () => Promise.resolve('not valid json');
        // Should not throw; should mark as pending or skip
    });
});
```

---

### 2.6 Increment 6: Multi-Query RAG Fusion

| Test File | Count | Type | Description |
|-----------|-------|------|-------------|
| `tests/test_phase8_multi_query.py` | 8 | Python unit | _multi_query_retrieve, _rrf_merge, extra_queries param |
| `tests/test_phase8_multi_query.py` | 4 | Python integration | End-to-end multi-query retrieval quality |
| `tests/test_phase8_expansion.js` | 7 | JS unit | expandQueryWithLLM, JSON parsing, graceful fallback |
| `tests/` (existing) | 344 | Regression | Full existing suite |

#### Python Unit Tests — Multi-Query Retriever

```python
class TestMultiQueryRetrieval:

    def test_rrf_merge_single_list_is_identity(self):
        """_rrf_merge([[a, b, c]]) returns [(a, 1/(60+1)), (b, 1/(60+2)), (c, 1/(60+3))]"""
        ...

    def test_rrf_merge_boosts_item_ranked_high_in_multiple_lists(self):
        """Chunk appearing at rank 1 in both lists outscores chunk at rank 1 in only one list."""
        list1 = [(chunk_A, 0.9), (chunk_B, 0.8)]
        list2 = [(chunk_A, 0.7), (chunk_C, 0.9)]
        merged = retriever._rrf_merge([list1, list2])
        assert merged[0][0] == chunk_A  # highest combined RRF score

    def test_rrf_merge_deduplicates_by_chunk_id(self):
        """Same chunk appearing in multiple lists appears only once in merged output."""
        list1 = [(chunk_A, 0.8), (chunk_B, 0.7)]
        list2 = [(chunk_A, 0.9), (chunk_C, 0.6)]
        merged = retriever._rrf_merge([list1, list2])
        ids = [c['id'] for c, _ in merged]
        assert ids.count(chunk_A['id']) == 1

    def test_retrieve_with_extra_queries_calls_pipeline_n_plus_1_times(self):
        """retrieve(q, extra_queries=[q1,q2,q3]) runs pipeline 4 times (1 + 3)."""
        with patch.object(retriever, '_run_steps_1_to_7', wraps=...) as mock:
            retriever.retrieve("main", extra_queries=["v1", "v2", "v3"])
            assert mock.call_count == 4

    def test_retrieve_no_extra_queries_runs_single_pipeline(self):
        """retrieve(q) with extra_queries=[] runs pipeline exactly once."""
        ...

    def test_multi_query_disabled_by_flag(self):
        """MULTI_QUERY_ENABLED=False → retrieve() takes single-query path even if extra_queries provided."""
        with override_settings(MULTI_QUERY_ENABLED=False):
            with patch.object(retriever, '_run_steps_1_to_7', wraps=...) as mock:
                retriever.retrieve("main", extra_queries=["v1", "v2"])
                assert mock.call_count == 1

    def test_extra_queries_capped_at_4(self):
        """extra_queries list of 10 is capped to 4 (total 5 runner calls)."""
        with patch.object(retriever, '_run_steps_1_to_7') as mock:
            retriever.retrieve("main", extra_queries=[f"q{i}" for i in range(10)])
            assert mock.call_count == 5

    def test_cross_encoder_receives_merged_pool(self):
        """Steps 8-11 (cross-encoder) receive the RRF-merged pool, not per-query results."""
        ...

    def test_integration_alternate_phrasing_finds_same_chunk(self):
        """'What is Closing Date?' and 'Define the closing date of the trust'
        both resolve to the same definition chunk with MultiQuery enabled."""
        ...

    def test_integration_quality_improvement_over_single_query(self):
        """Multi-query retrieval finds ≥1 additional relevant chunk vs single-query for a test set."""
        ...

    def test_integration_api_accepts_extra_queries_param(self):
        """POST /retrieve with {query: '...', extra_queries: ['v1', 'v2']} returns 200 OK."""
        ...

    def test_integration_api_extra_queries_empty_works(self):
        """POST /retrieve with missing extra_queries param behaves identically to single-query."""
        ...
```

#### JS Unit Tests — query_expander.js

```javascript
describe('Query Expander', () => {

    it('returns array of 4 strings from valid JSON response', async () => {
        mockModel.sendRequest = () => Promise.resolve('["q1","q2","q3","q4"]');
        const variants = await expandQueryWithLLM(vscode, mockModel, 'test query');
        assert.deepEqual(variants, ['q1', 'q2', 'q3', 'q4']);
    });

    it('returns [] on JSON parse failure (graceful degradation)', async () => {
        mockModel.sendRequest = () => Promise.resolve('not json');
        const variants = await expandQueryWithLLM(vscode, mockModel, 'test');
        assert.deepEqual(variants, []);
    });

    it('returns [] on LLM API error (graceful degradation)', async () => {
        mockModel.sendRequest = () => Promise.reject(new Error('API error'));
        const variants = await expandQueryWithLLM(vscode, mockModel, 'test');
        assert.deepEqual(variants, []);
    });

    it('returns [] when response is not an array', async () => {
        mockModel.sendRequest = () => Promise.resolve('{"result": "not array"}');
        const variants = await expandQueryWithLLM(vscode, mockModel, 'test');
        assert.deepEqual(variants, []);
    });

    it('returns [] when array has fewer than 2 items', async () => {
        mockModel.sendRequest = () => Promise.resolve('["only one"]');
        const variants = await expandQueryWithLLM(vscode, mockModel, 'test');
        assert.deepEqual(variants, []);
    });

    it('skips expansion when MULTI_QUERY_ENABLED=false', async () => {
        const spy = sinon.spy(mockModel, 'sendRequest');
        settings.MULTI_QUERY_ENABLED = false;
        await expandQueryWithLLM(vscode, mockModel, 'test');
        assert(spy.notCalled);
    });

    it('passes extra_queries to backend retrieve call when variants available', async () => {
        // In participant.js: variants from expandQueryWithLLM are forwarded to ktsTool's requestBody
        ...
    });
});
```

---

### 2.7 Increment 7: N-Level Definition Chain Traversal

**File:** `tests/test_phase8_def_traversal.py`  
**Scope:** `TermResolver` wiring, ChromaDB fallback Path B, plain-colon PSA fix, cycle detection, depth limit

```python
# tests/test_phase8_def_traversal.py

import pytest
from unittest.mock import MagicMock, patch
from backend.retrieval.term_resolver import TermResolver, TermResolution
from backend.retrieval.human_like_retriever import HumanLikeRetriever


class TestPlainColonPatternFix:

    def test_psa_plain_colon_term_extracted(self):
        """'Current Interest: As of any...' → extracts 'Current Interest'."""
        retriever = make_retriever_stub()
        result = retriever._extract_defined_term("Current Interest: As of any Distribution Date...")
        assert result == "Current Interest"

    def test_plain_colon_all_caps_rejected(self):
        """'CURRENT INTEREST: ...' is an acronym-style heading, not Title Case term."""
        retriever = make_retriever_stub()
        result = retriever._extract_defined_term("CURRENT INTEREST: As of any Distribution Date...")
        assert result is None

    def test_plain_colon_lowercase_rejected(self):
        """'current interest: ...' → not a Capitalized Term, should return None."""
        retriever = make_retriever_stub()
        result = retriever._extract_defined_term("current interest: see section 3")
        assert result is None

    def test_plain_colon_sentence_fragment_rejected(self):
        """Colon in mid-sentence not treated as definition term."""
        retriever = make_retriever_stub()
        result = retriever._extract_defined_term("For example: the following rules apply")
        assert result is None


class TestTermResolverWiring:

    def test_enrich_calls_term_resolver_for_capitalized_terms(self):
        """enrich_with_definitions() must call TermResolver when term in _definition_index."""
        retriever = make_retriever_stub()
        retriever._definition_index = {"current interest": "node_123"}
        with patch.object(TermResolver, 'resolve_term') as mock_resolve:
            mock_resolve.return_value = TermResolution(
                term="Current Interest",
                found=True,
                depth_reached=2,
                closure=["Pass-Through Rate", "Accrual Period"],
                cycles_detected=[],
                truncated=False
            )
            result = retriever.enrich_with_definitions(["Current Interest: As of..."])
        mock_resolve.assert_called_once()
        assert "Pass-Through Rate" in str(result) or len(result) > 1

    def test_enrich_includes_closure_terms_in_output(self):
        """All terms in TermResolution.closure[] appear in enriched output."""
        # Integration test: TermResolver returns [A, B, C], all 3 must be in injected defs
        pass  # Implement with real graph fixture

    def test_enrich_depth_limit_respected(self):
        """TermResolver must not exceed max_depth=5."""
        resolver = TermResolver(graph=make_graph_stub(), max_depth=5)
        # Build a chain of depth 10
        result = resolver.resolve_term("RootTerm")
        assert result.depth_reached <= 5
        assert result.truncated == (result.depth_reached == 5)


class TestChromaDBFallbackPathB:

    def test_graph_miss_triggers_vector_fallback(self):
        """Term not in _definition_index → dual_store fallback query fires."""
        retriever = make_retriever_stub()
        retriever._definition_index = {}  # Empty graph
        with patch.object(retriever.dual_store, 'search_items') as mock_search:
            mock_search.return_value = [("definition text of X", 0.85, {})]
            result = retriever._resolve_term_from_vector("SomeCapitalizedTerm")
        mock_search.assert_called_once()
        call_args = mock_search.call_args
        assert "SomeCapitalizedTerm" in call_args[0][0]  # Query contains the term
        assert result is not None

    def test_vector_fallback_low_score_returns_none(self):
        """Score < 0.7 threshold → fallback returns None, no injection."""
        retriever = make_retriever_stub()
        retriever._definition_index = {}
        with patch.object(retriever.dual_store, 'search_items') as mock_search:
            mock_search.return_value = [("definition text", 0.50, {})]
            result = retriever._resolve_term_from_vector("WeakMatch")
        assert result is None

    def test_term_limit_per_chunk(self):
        """Max 10 terms extracted per chunk --- prevents explosion on definition-dense chunks."""
        long_chunk = " ".join([f"Term{i} Definition" for i in range(50)])
        retriever = make_retriever_stub()
        terms = retriever._extract_capitalized_terms(long_chunk)
        assert len(terms) <= 10


class TestCycleDetection:

    def test_cycle_detected_and_logged(self):
        """Circular definition chain (A → B → A) is detected, not looped infinitely."""
        # Build graph with A → B → A cycle
        graph = make_cyclic_graph_stub()
        resolver = TermResolver(graph=graph, max_depth=5)
        result = resolver.resolve_term("A")
        assert len(result.cycles_detected) > 0
        assert "B" in result.cycles_detected[0] or "A" in result.cycles_detected[0]

    def test_no_infinite_recursion_on_cycle(self):
        """Cyclic graph does not hang or stack overflow."""
        graph = make_cyclic_graph_stub()
        resolver = TermResolver(graph=graph, max_depth=5)
        result = resolver.resolve_term("A")  # Must return, not hang
        assert result is not None


# ── Helpers ──────────────────────────────────────────────────────────────────
def make_retriever_stub():
    return HumanLikeRetriever.__new__(HumanLikeRetriever)

def make_graph_stub():
    return MagicMock()

def make_cyclic_graph_stub():
    """Minimal NetworkX graph: A → B → A."""
    import networkx as nx
    g = nx.DiGraph()
    g.add_node("A", label="DEFINED_TERM", definition="A means B")
    g.add_node("B", label="DEFINED_TERM", definition="B means A")
    g.add_edge("A", "B", type="REFERS_TO")
    g.add_edge("B", "A", type="REFERS_TO")
    return g
```

**~12 test functions** across 4 test classes.

---

### 2.8 Increment 8: Self-RAG Iterative Generation Loop

**Files:** `tests/test_phase8_self_rag.js` (JavaScript), `tests/test_phase8_self_rag.py` (Python integration)  
**Scope:** Gap analysis prompt parsing, termination guards, synthesis integration, `exclude_chunk_ids`

```javascript
// tests/test_phase8_self_rag.js

const assert = require('assert');
const sinon = require('sinon');

const { analyzeGaps } = require('../extension/lib/gap_analyzer');
const { generateIteratively } = require('../extension/lib/iterative_generator');

const mockVscode = require('./helpers/mock_vscode');
const mockModel = require('./helpers/mock_model');

describe('GapAnalyzer', () => {

    it('returns array of gap queries from valid LLM JSON response', async () => {
        mockModel.setNextResponse('["What is Pass-Through Rate?", "Define Accrual Period"]');
        const gaps = await analyzeGaps(mockVscode, mockModel,
            'What is Current Interest?',
            'Current Interest is calculated using the Pass-Through Rate...');
        assert.deepStrictEqual(gaps, ['What is Pass-Through Rate?', 'Define Accrual Period']);
    });

    it('returns [] when LLM says answer is complete', async () => {
        mockModel.setNextResponse('[]');
        const gaps = await analyzeGaps(mockVscode, mockModel,
            'What is Current Interest?',
            '<complete and self-contained answer>');
        assert.deepStrictEqual(gaps, []);
    });

    it('returns [] on LLM response parse failure (graceful fallback)', async () => {
        mockModel.setNextResponse('I cannot determine the gaps.');
        const gaps = await analyzeGaps(mockVscode, mockModel, 'query', 'answer');
        assert.deepStrictEqual(gaps, []);
    });

    it('strips markdown code fences before JSON.parse', async () => {
        mockModel.setNextResponse('```json\n["Define Trustee"]\n```');
        const gaps = await analyzeGaps(mockVscode, mockModel, 'query', 'answer');
        assert.deepStrictEqual(gaps, ['Define Trustee']);
    });

    it('rejects non-array JSON (object, string) and returns []', async () => {
        mockModel.setNextResponse('{"gaps": ["x"]}');
        const gaps = await analyzeGaps(mockVscode, mockModel, 'query', 'answer');
        assert.deepStrictEqual(gaps, []);
    });

    it('truncates gap list to max 5 queries', async () => {
        const longList = JSON.stringify(['q1','q2','q3','q4','q5','q6','q7','q8']);
        mockModel.setNextResponse(longList);
        const gaps = await analyzeGaps(mockVscode, mockModel, 'query', 'answer');
        assert.ok(gaps.length <= 5);
    });
});

describe('IterativeGenerator', () => {

    it('stops after Round 0 when gap analysis returns []', async () => {
        const gapStub = sinon.stub().resolves([]);
        const mockRetrieve = sinon.stub().resolves({ chunks: [] });
        const result = await generateIteratively(mockVscode, mockModel,
            'What is Current Interest?',
            { gapAnalyzer: gapStub, retrieve: mockRetrieve });
        assert.strictEqual(gapStub.callCount, 1);  // Called once, then stopped
        assert.ok(result.rounds_used <= 1);
    });

    it('respects max_rounds=3 hard cap', async () => {
        const alwaysGaps = sinon.stub().resolves(['gap1', 'gap2']);
        const mockRetrieve = sinon.stub().resolves({ chunks: [{ id: 'x', text: 'def' }] });
        const result = await generateIteratively(mockVscode, mockModel,
            'query', { gapAnalyzer: alwaysGaps, retrieve: mockRetrieve });
        assert.ok(result.rounds_used <= 3);
    });

    it('stops early when same gaps appear twice (no-progress guard)', async () => {
        const repeatingGaps = sinon.stub().resolves(['gap1', 'gap2']);
        const mockRetrieve = sinon.stub().resolves({ chunks: [] });  // No new chunks
        const result = await generateIteratively(mockVscode, mockModel,
            'query', { gapAnalyzer: repeatingGaps, retrieve: mockRetrieve });
        // Should stop at round 2 (same gaps as round 1)
        assert.ok(result.rounds_used <= 2);
    });

    it('passes exclude_chunk_ids to retrieve on Round 1+', async () => {
        const gaps = sinon.stub()
            .onFirstCall().resolves(['gap1'])
            .onSecondCall().resolves([]);
        const mockRetrieve = sinon.stub().resolves({ chunks: [{ id: 'chunk_abc', text: 'def' }] });
        await generateIteratively(mockVscode, mockModel, 'query',
            { gapAnalyzer: gaps, retrieve: mockRetrieve });
        const round1Call = mockRetrieve.getCall(1);
        assert.ok(round1Call.args[0].exclude_chunk_ids.includes('chunk_abc'));
    });

    it('carries Round 0 answer into Round 1 synthesis prompt', async () => {
        const gaps = sinon.stub()
            .onFirstCall().resolves(['gap1'])
            .onSecondCall().resolves([]);
        const mockRetrieve = sinon.stub().resolves({ chunks: [{ id: 'new', text: 'extra def' }] });
        let capturedPrompt = '';
        mockModel.onSendRequest = (msgs) => { capturedPrompt = msgs.map(m => m.content).join(' '); };
        await generateIteratively(mockVscode, mockModel, 'query',
            { gapAnalyzer: gaps, retrieve: mockRetrieve });
        assert.ok(capturedPrompt.includes('Previous answer draft'));
    });
});
```

```python
# tests/test_phase8_self_rag.py (Python integration tests)

def test_exclude_chunk_ids_prevents_reuse():
    """Backend /retrieve with exclude_chunk_ids never returns excluded IDs."""
    # Integration test: ingest 3 chunks, retrieve, confirm excluded ones absent
    pass

def test_self_rag_reduces_gap_count_on_current_interest_query():
    """E2E: 'What is Current Interest?' starts at 8 gaps, ends at 0 after Self-RAG."""
    pass  # Requires ingested Bear Stearns PSA fixture

def test_self_rag_latency_within_budget():
    """Full 2-round Self-RAG completes in < 12s on golden query."""
    pass  # Performance assertion

def test_confidence_score_penalized_when_gaps_remain():
    """Adjusted confidence < raw confidence when final gaps list is non-empty."""
    raw_confidence = 1.00
    final_gaps = ["Accrual Period", "Pass-Through Rate"]
    gap_fraction = min(len(final_gaps) / 10.0, 0.5)
    adjusted = raw_confidence * (1.0 - 0.3 * gap_fraction)
    assert adjusted < raw_confidence

def test_confidence_not_penalized_when_zero_gaps():
    """No penalty when gap analysis returns []."""
    raw_confidence = 0.92
    final_gaps = []
    gap_fraction = 0.0
    adjusted = raw_confidence * (1.0 - 0.3 * gap_fraction)
    assert adjusted == raw_confidence

def test_self_rag_disabled_by_feature_flag():
    """SELF_RAG_ENABLED=False → single-round generation, no gap analysis calls."""
    pass

def test_synthesis_prompt_includes_previous_answer():
    """Synthesis prompt passed to LLM in Round 1 explicitly contains prior draft."""
    pass
```

**~9 JS test functions, ~7 Python test functions** = ~16 test functions total.

---

## 3. Regression Test Strategy

### 3.1 Existing Test Suite (Must-Pass at Every Gate)

```
Python Tests:  344 collected
JS Tests:       74 tests

Total Baseline: 418 tests
```

### 3.2 Regression Execution Commands

```bash
# Python regression (run from project root)
python -m pytest tests/ -v --tb=short -x

# JS regression (run from extension/)
cd extension && npm test

# Combined regression script (recommended)
python -m pytest tests/ -v --tb=short && cd extension && npm test
```

### 3.3 Regression Gates

| Gate | When | Criteria |
|------|------|----------|
| **Gate 1** | After BM25 unit tests written | 344 Python + 12 BM25 unit = 356+ pass |
| **Gate 2** | After BM25 integration | 344 Python + 17 BM25 total = 361+ pass, 74 JS pass |
| **Gate 3** | After MMR unit tests | 361+ Python + 10 MMR = 371+ pass |
| **Gate 4** | After MMR integration | 371+ Python + 14 MMR total = 375+ pass |
| **Gate 5** | After token trim | 375+ Python pass, 74 + 8 JS = 82 pass |
| **Gate 6** | After parent-child unit | 375+ Python + 10 parent = 385+ pass |
| **Gate 7** | After parent-child integration | 385+ Python + 15 parent total = 390+ pass |
| **Gate 8 (Final)** | All increments combined | ~395+ Python + 82 JS = ~477+ total, all green |

---

## 4. Golden Query Testing

### 4.1 Golden Query Set

Reuse existing golden queries plus add Phase 8 targeted queries:

```json
// tests/golden_queries_phase8.json
[
    {
        "id": "bm25_exact_term",
        "query": "What is the Closing Date for Bear Stearns 2006-HE2?",
        "expected_in_top5": ["ARTICLE I", "Definitions"],
        "rationale": "Exact term 'Closing Date' should be captured by BM25"
    },
    {
        "id": "bm25_legal_term",
        "query": "What is the subordination structure?",
        "expected_in_top5": ["subordination", "credit enhancement"],
        "rationale": "Legal term 'subordination' is low-frequency, high IDF"
    },
    {
        "id": "mmr_diversity",
        "query": "Describe the waterfall distribution",
        "expected_property": "no_duplicate_sections",
        "rationale": "MMR should prevent 3+ chunks from same section"
    },
    {
        "id": "parent_context",
        "query": "What triggers an Event of Default?",
        "expected_in_top5": ["ARTICLE V", "Event of Default"],
        "rationale": "Item-level match should expand to full ARTICLE V section"
    },
    {
        "id": "token_overflow_prevention",
        "query": "Explain all aspects of the pooling and servicing agreement",
        "expected_property": "no_truncation_error",
        "rationale": "Broad query should not overflow LLM context window"
    }
]
```

### 4.2 Golden Query Execution

```bash
# Run golden query scoring
python tests/score_queries.py --golden tests/golden_queries_v2.json
python tests/score_queries.py --golden tests/golden_queries_phase8.json
```

### 4.3 Quality Metrics

| Metric | Baseline (v0.0.10) | Target (Phase 8) | Measurement |
|--------|-------------------|-------------------|-------------|
| MRR@5 (existing queries) | Current value | ≥ same | score_queries.py |
| MRR@5 (Phase 8 queries) | N/A | ≥ 0.6 | score_queries.py |
| Exact-term recall | ~60% | ≥ 80% | BM25 targeted queries |
| Context diversity | Unknown | No 3+ same-section | Manual check |
| Context overflow rate | Unknown | 0% | Log monitoring |

---

## 5. Performance Testing

### 5.1 Benchmarks

| Metric | Threshold | How to Measure |
|--------|-----------|---------------|
| Backend cold start (with BM25 load) | < 15 seconds | `time python -c "from backend.agents.retrieval_service import ..."` |
| BM25 index build time (1000 docs) | < 5 seconds | In-test timer |
| BM25 search latency (single query) | < 50 ms | In-test timer |
| MMR selection (100 candidates → 10) | < 100 ms | In-test timer |
| Parent expansion (10 items → sections) | < 200 ms | In-test timer |
| Token trimming (JS, 20 blocks) | < 5 ms | In-test timer |
| End-to-end query latency (p50) | < 3 seconds | Timed VSIX queries |
| BM25 index file size (1000 docs) | < 10 MB | File system check |

### 5.2 Performance Test Code

```python
class TestPhase8Performance:
    """Performance benchmarks — not strict pass/fail but logged for monitoring."""

    def test_bm25_build_performance(self):
        """BM25 index build for 1000 documents completes within 5 seconds."""
        docs = generate_synthetic_legal_docs(n=1000)
        start = time.time()
        retriever.build_index(docs)
        elapsed = time.time() - start
        print(f"BM25 build: {elapsed:.2f}s for {len(docs)} docs")
        assert elapsed < 5.0

    def test_bm25_search_performance(self):
        """BM25 search completes within 50ms."""
        start = time.time()
        retriever.search("Closing Date distribution priority", top_k=20)
        elapsed = time.time() - start
        print(f"BM25 search: {elapsed*1000:.1f}ms")
        assert elapsed < 0.05

    def test_mmr_selection_performance(self):
        """MMR selection over 100 candidates completes within 100ms."""
        embs = np.random.randn(100, 384).astype(np.float32)
        q_emb = np.random.randn(384).astype(np.float32)
        start = time.time()
        mmr_select(q_emb, embs, dummy_results(100), top_k=10)
        elapsed = time.time() - start
        print(f"MMR select: {elapsed*1000:.1f}ms")
        assert elapsed < 0.1
```

---

## 6. Manual Smoke Tests

### 6.1 VSIX Smoke Test Checklist

After building the final Phase 8 VSIX:

| # | Test | Expected Result | Pass? |
|---|------|----------------|-------|
| 1 | Install VSIX in VS Code | Extension activates, backend starts | |
| 2 | Ingest Bear Stearns 2006-HE2 PSA | Success, BM25 index built | |
| 3 | `@kts What is the Closing Date?` | Answer references definitions section, exact term match | |
| 4 | `@kts Describe the priority of distribution` | Answer covers waterfall, diverse chunks (not all from same section) | |
| 5 | `@kts Explain all aspects of the trust agreement` | No truncation error, answer is coherent | |
| 6 | `@kts What triggers an Event of Default?` | Answer references full Event of Default section (parent expansion) | |
| 7 | Check Output Channel diagnostics | BM25 hybrid results logged, MMR logged, parent expansion logged | |
| 8 | Ingest a second document | BM25 index rebuilt to include new doc | |
| 9 | Query across both documents | Results from both documents appear | |
| 10 | Test with Phase 8 features disabled via env vars | Behavior identical to v0.0.10 | |

### 6.2 Diagnostic Log Verification

The VS Code Output Channel should show Phase 8 specific entries:

```
[BM25] Index loaded: 1,234 documents, 45,678 unique terms
[BM25] Search "Closing Date" → 20 results (top score: 12.34)
[RRF] Fusing 20 vector + 20 BM25 results → 25 unique (weights: 0.6/0.4)
[MMR] Selected 10 from 30 candidates (λ=0.7)
[Parent] Expanded 3 items → 2 parent sections
[TokenTrim] Context: 856 tokens (budget: 1196) — no trimming needed
```

---

## 7. Error Scenario Testing

### 7.1 Graceful Degradation Tests

```python
class TestPhase8GracefulDegradation:
    """Verify system works when Phase 8 components are missing or fail."""

    def test_missing_bm25_index_file(self):
        """Missing BM25 index → auto-build from ChromaDB, no error."""

    def test_corrupt_bm25_index_file(self):
        """Corrupt JSON in BM25 index → rebuild, log warning, no crash."""

    def test_mmr_numpy_unavailable(self):
        """If numpy somehow missing → fall back to vanilla top-k, log warning."""

    def test_parent_id_points_to_deleted_section(self):
        """parent_section_id references deleted section → skip, no crash."""

    def test_chromadb_returns_no_embeddings(self):
        """ChromaDB include=['embeddings'] fails → fall back to non-MMR search."""

    def test_all_phase8_disabled(self):
        """All Phase 8 flags False → behavior identical to v0.0.10."""

    def test_empty_collection_bm25(self):
        """BM25 on empty ChromaDB collection → empty results, no error."""
```

---

## 8. Test File Summary

| File | New Tests | Type |
|------|-----------|------|
| `tests/test_phase8_cch.py` | ~10 | Python (unit + integration) |
| `tests/test_phase8_bm25.py` | ~17 | Python (unit + integration) |
| `tests/test_phase8_mmr.py` | ~14 | Python (unit + integration) |
| `tests/test_phase8_parent_child.py` | ~15 | Python (unit + integration) |
| `tests/test_phase8_hype.py` | ~13 | Python (unit + integration) |
| `tests/test_phase8_multi_query.py` | ~12 | Python (unit + integration) |
| `tests/test_phase8_integration.py` | ~10 | Python (combined feature integration) |
| `tests/test_phase8_performance.py` | ~5 | Python (benchmarks) |
| `tests/test_phase8_degradation.py` | ~7 | Python (error handling) |
| `tests/test_phase8_token_trim.js` | ~8 | JavaScript (unit) |
| `tests/test_phase8_hype.js` | ~8 | JavaScript (unit) |
| `tests/test_phase8_expansion.js` | ~7 | JavaScript (unit) |
| `tests/golden_queries_phase8.json` | 8 queries | Golden query data |
| `tests/test_phase8_def_traversal.py` | ~12 | Python (TermResolver wiring, plain-colon fix, fallback) |
| `tests/test_phase8_self_rag.js` | ~9 | JavaScript (gap_analyzer, iterative_generator) |
| `tests/test_phase8_self_rag.py` | ~7 | Python (integration, confidence penalty, latency) |
| **Total New** | **~144** | |
| **Total Suite (Phase 8 complete)** | **~562** | 344 + 74 + 144 |

---

## 9. Test Execution Quick Reference

```bash
# ── Run everything ──
python -m pytest tests/ -v --tb=short && cd extension && npm test

# ── Phase 8 tests only ──
python -m pytest tests/test_phase8_*.py -v

# ── Single increment ──
python -m pytest tests/test_phase8_cch.py -v
python -m pytest tests/test_phase8_bm25.py -v
python -m pytest tests/test_phase8_mmr.py -v
python -m pytest tests/test_phase8_parent_child.py -v
python -m pytest tests/test_phase8_hype.py -v
python -m pytest tests/test_phase8_multi_query.py -v
python -m pytest tests/test_phase8_def_traversal.py -v
python -m pytest tests/test_phase8_self_rag.py -v
python -m pytest tests/test_phase8_performance.py -v

# ── JS unit tests ──
cd extension && npm test -- --grep "GapAnalyzer|IterativeGenerator"

# ── Golden query benchmark ──
python tests/score_queries.py --golden tests/golden_queries_phase8.json

# ── Regression only (no Phase 8 tests) ──
python -m pytest tests/ -v --tb=short --ignore=tests/test_phase8_*.py
```
