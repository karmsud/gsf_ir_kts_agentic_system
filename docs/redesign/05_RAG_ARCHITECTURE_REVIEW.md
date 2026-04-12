# Phase E: RAG Architecture Review & Ablation Study

**Created:** 2026-02-20  
**Status:** APPROVED — Ready for Implementation  
**Effort:** 3-5 hours (ablation experiments take time)  
**Priority:** P1 — After baseline captured (depends on Phase D)

---

## 1. Problem Statement

The KTS RAG pipeline has grown to **48 distinct techniques** across 6 pipeline stages, accumulated over 15 phases of development. Many were added incrementally without measuring their marginal value. The result:

- **5 query expansion mechanisms** (only 2 can be active simultaneously without conflict)
- **3 independent confidence scoring systems** (producing different scores)
- **Keyword-boost rerank AFTER cross-encoder** (potentially overriding trained relevance)
- **70+ boolean feature flags** with undocumented interactions
- **Dead code paths** (context_expansion silently disabled, PageRank standalone unused)
- **Duplicate implementations** (critique loop in both Python and JS)

### Goal

Systematically classify every technique as **KEEP / EVALUATE / REMOVE**, then use the Golden Test Harness (Phase D) to validate decisions with evidence, not intuition.

---

## 2. Complete Pipeline Inventory

### 2.1 Query Processing (7 techniques)

| # | Technique | File | Flag | Default | Classification |
|---|-----------|------|------|---------|---------------|
| 1 | Acronym Resolution | `backend/retrieval/acronym_resolver.py` | `acronym_resolver_enabled` | True | **KEEP** |
| 2 | 3-Tier Synonym Expansion | `backend/retrieval/query_expander.py` | `query_expansion_enabled` | True | **EVALUATE** |
| 3 | Query Rewriting (Coreference) | `backend/retrieval/query_rewriter.py` | `query_rewriting_enabled` | True | **KEEP** |
| 4 | HyDE | `backend/retrieval/hyde.py` | `hyde_enabled` | **False** | **EVALUATE** |
| 5 | JS Multi-Query Expansion | `extension/lib/query_expander.js` | `multi_query_rag_enabled` | True | **EVALUATE** |
| 6 | Scope Routing | `backend/retrieval/scope_router.py` | `deal_catalog_enabled` | True | **KEEP** |
| 7 | Temporal Reasoning | `backend/retrieval/temporal_reasoner.py` | `temporal_reasoning_enabled` | True | **KEEP** |

**Analysis:**

Techniques 2, 4, and 5 are three different ways to reformulate the query before retrieval:
- **#2** (Synonym Expansion): Static + learned synonyms. Zero LLM cost. Deterministic. Low risk.
- **#4** (HyDE): LLM generates a hypothetical answer to use as the search query. High cost (1 LLM call). Currently disabled. Designed for cases where the query's vocabulary differs from the document's vocabulary.
- **#5** (JS Multi-Query): LLM generates 3 alternative phrasings. Medium cost (1 LLM call). Currently enabled. Designed for recall improvement by diversifying query angles.

**Redundancy concern:** If #2 and #5 are both active, the query is expanded twice. The backend synonym expander creates domain-specific reformulations, and the JS expander creates LLM-generated reformulations. These may overlap or conflict.

**Decision needed:** Run ablation to determine which combination produces the best answer quality. Likely outcome: Keep #2 (zero cost) + #5 (LLM diversity), disable #4 (redundant with #5, higher cost).

### 2.2 Retrieval (9 techniques)

| # | Technique | File | Flag | Default | Classification |
|---|-----------|------|------|---------|---------------|
| 8 | Dual-Collection Vector Search | `backend/retrieval/human_like_retriever.py` | `phase6_enabled` | True | **KEEP** |
| 9 | BM25 Keyword Retrieval | `backend/retrieval/bm25_retriever.py` | `enable_bm25_hybrid` | True | **KEEP** |
| 10 | Graph-First Section Discovery | `backend/retrieval/human_like_retriever.py` | Always on (legal) | — | **KEEP** |
| 11 | Section-Scoped Vector Search | `backend/retrieval/human_like_retriever.py` | Always on (legal) | — | **KEEP** |
| 12 | Graph BFS Expansion | `backend/retrieval/iterative_orchestrator.py` | `multi_hop_enabled` | True | **EVALUATE** |
| 13 | HyPE (Hypothetical Question Search) | `extension/lib/hype_enricher.js` | `enable_hype` | **False** | **EVALUATE** |
| 14 | Parent-Child Chunk Expansion | `backend/agents/retrieval_service.py` | `parent_child_chunking_enabled` | **False** | **EVALUATE** |
| 15 | Context Window Expansion | `backend/agents/retrieval_service.py` | `context_expansion_enabled` | **False** (BUG) | **FIX + EVALUATE** |
| 16 | Iterative Convergent Loop | `backend/retrieval/iterative_orchestrator.py` | `phase6_enabled` | True | **EVALUATE** |

**Critical bug — #15 context_expansion_enabled:**

```python
# config/settings.py — TWO declarations:
context_expansion_enabled: bool = True      # Line ~113
context_expansion_enabled: bool = False     # Line ~121 — OVERRIDES!
```

The second declaration silently disables the Smart Retrieval context expansion feature (adaptive context window, continuation detection, metadata-guided boundaries). **Fix: remove the duplicate declaration.**

**Dead code concern — #16 Iterative Convergent Loop:**

The `IterativeOrchestrator` runs a convergent loop (up to 10 iterations) for retrieval improvement. However, in the current pipeline, `HumanLikeRetriever` (for legal docs) already handles all retrieval steps internally. The `IterativeOrchestrator` appears to be a legacy path from Phase 6 development that's effectively bypassed for the primary retrieval flow.

**Decision needed:** Determine if IterativeOrchestrator adds value beyond what HumanLikeRetriever provides. If not, remove it and simplify the pipeline.

### 2.3 Ranking / Reranking (9 techniques)

| # | Technique | File | Flag | Default | Classification |
|---|-----------|------|------|---------|---------------|
| 17 | Cross-Encoder Rerank | `backend/retrieval/cross_encoder.py` | `cross_encoder_enabled` | True | **KEEP** |
| 18 | Hybrid Phase 6 Rerank | `backend/retrieval/hybrid_reranker.py` | Weights configurable | 0.6/0.2/0.2 | **EVALUATE** |
| 19 | Keyword-Boost Rerank | `human_like_retriever.py` | Always on | — | **REMOVE** |
| 20 | RRF (Reciprocal Rank Fusion) | `human_like_retriever.py` | `enable_bm25_hybrid` | True | **KEEP** |
| 21 | MMR (Maximal Marginal Relevance) | `human_like_retriever.py` | `enable_mmr_diversity` | True | **KEEP** |
| 22 | Error-Code Boost | `backend/retrieval/guide_retriever.py` | Always on (guide) | — | **KEEP** |
| 23 | Step-Sequence Ordering | `backend/retrieval/guide_retriever.py` | Always on (guide) | — | **KEEP** |
| 24 | Document Bias Boost | `backend/retrieval/session_memory.py` | `session_memory_enabled` | True | **EVALUATE** |
| 25 | PageRank | `backend/graph/pagerank.py` | `pagerank_enabled` | False | **EVALUATE** |

**Keyword-Boost (#19) — Remove with evidence:**

The cross-encoder is a fine-tuned neural model (ms-marco-MiniLM-L-6-v2) trained on millions of query-passage pairs. It produces precision-optimized relevance scores. The keyword-boost then applies a **flat additive bonus** (+0.1-0.3) for exact keyword matches, which can:

1. Promote a keyword-matching chunk ABOVE a semantically superior one chosen by the cross-encoder
2. Break the cross-encoder's learned balance between semantic meaning and surface form
3. Systematically favor chunks with exact terminology over chunks that use synonyms or paraphrases

Example harm: Query "What happens when loans default?" — the cross-encoder correctly ranks a chunk about "Events of Default provisions" highest. But keyword-boost promotes a chunk containing the literal word "default" in a different context (e.g., "default interest rate") because it matches the query keyword.

**Recommendation:** Remove keyword-boost from both `HumanLikeRetriever` (Step 9) and `GuideRetriever` (Step 7). Validate via golden test ablation.

**PageRank (#25) — Clarify status:**

`pagerank_enabled = False` (standalone), but PageRank is always computed as part of the Phase 6 hybrid score (20% weight in `hybrid_reranker.py`). The standalone flag controls a dead legacy code path. Either:
- Remove the standalone flag and document that PageRank is integral to hybrid reranking
- OR make the hybrid reranker respect the flag (weight=0 if disabled)

### 2.4 Post-Retrieval Enrichment (10 techniques)

| # | Technique | File | Flag | Default | Classification |
|---|-----------|------|------|---------|---------------|
| 26 | Confidence Scoring (5-Tier) | `backend/retrieval/confidence_scorer.py` | `confidence_scoring_enabled` | True | **KEEP** |
| 27 | Gap Detection | `backend/retrieval/gap_detector.py` | `gap_detection_enabled` | True | **KEEP** |
| 28 | Definition Enrichment (BFS) | `backend/retrieval/term_resolver.py` | `definition_traversal_enabled` | True | **KEEP** (core to Phase 7) |
| 29 | Learned Synonym Registry | `backend/retrieval/term_registry.py` | `learned_synonyms_enabled` | True | **EVALUATE** |
| 30 | Evidence Matching / Provenance | `backend/retrieval/evidence_matcher.py` | Always on | — | **KEEP** |
| 31 | Critique Loop (Backend Python) | `backend/retrieval/critique_loop.py` | `critique_loop_enabled` | True | **CONSOLIDATE** |
| 32 | Critique Loop (Frontend JS) | `extension/lib/critique_client.js` | `critique_loop_enabled` | True | **CONSOLIDATE** |
| 33 | Critique Merger | `backend/retrieval/critique_merger.py` | Always on | — | **KEEP** |
| 34 | Contradiction Detection | `backend/retrieval/contradiction_detector.py` | `contradiction_detection_enabled` | True | **KEEP** |
| 35 | Anomaly Scoring | `backend/retrieval/anomaly_scorer.py` | `anomaly_detection_enabled` | **False** | **KEEP** (opt-in, correct) |

**Duplicate Critique Loop (#31 + #32) — Consolidate:**

Both Python and JS implementations exist with nearly identical logic:
- Keyword safety check (deterministic pre-filter)
- Trigger pattern matching
- LLM binary evaluation
- Gap→query translation

Currently, only one executes per request (JS when running in Extension Host, Python when running via CLI). But maintaining both is technical debt.

**Recommendation:** Keep JS implementation only (runs where the LLM API is — VS Code), remove Python backend critique loop. The backend should return raw retrieval results; the frontend handles critique.

**Exception:** If CLI mode needs critique, keep a lightweight Python version. But CLI mode is secondary to the VS Code experience.

### 2.5 Generation (7 techniques)

| # | Technique | File | Flag | Default | Classification |
|---|-----------|------|------|---------|---------------|
| 36 | Regime-Aware Prompt Selection | `participant.js` | Always on | — | **KEEP** |
| 37 | Token-Aware Context Trimming | `participant.js` | Always on | — | **KEEP** |
| 38 | Self-RAG Iterative Loop | `extension/lib/iterative_generator.js` | `self_rag_enabled` | **False** | **EVALUATE** |
| 39 | Gap Analyzer (for Self-RAG) | `extension/lib/gap_analyzer.js` | (tied to #38) | **False** | **EVALUATE** |
| 40 | Definition Mode | `backend/retrieval/definition_mode.py` | `definition_mode_enabled` | True | **KEEP** |
| 41 | Conversation History Injection | `participant.js` | Always on | — | **KEEP** |
| 42 | Cached Term Injection | `participant.js` | `session_memory_enabled` | True | **KEEP** |

**Self-RAG (#38 + #39) — Evaluate carefully:**

Self-RAG is currently disabled by default. When enabled, it:
1. Generates an initial answer
2. LLM identifies gaps in the answer (up to 3 new queries)
3. Runs additional retrieval with gap queries
4. Regenerates with expanded context
5. Repeats until convergent (or max rounds)

**Potential value:** For complex multi-section questions (waterfall, reporting requirements), the initial retrieval may miss important sections. Self-RAG can discover these.

**Potential cost:** Each round costs 1 retrieval + 1 generation + 1 gap analysis LLM call. A 3-round Self-RAG costs 3x the latency and 3x the LLM budget.

**Decision needed:** Run golden tests with Self-RAG enabled (just for complex questions — categories 2 and 3). If it improves completeness by ≥ 0.5 points on average for those categories, keep it enabled by default for those categories.

### 2.6 Post-Generation (6 techniques)

| # | Technique | File | Flag | Default | Classification |
|---|-----------|------|------|---------|---------------|
| 43 | Evidence Provenance Verification | `backend/retrieval/evidence_matcher.py` | Always on | — | **KEEP** |
| 44 | Keyword Safety Check | `extension/lib/critique_client.js` | `critique_loop_enabled` | True | **KEEP** |
| 45 | Session Memory Caching | `backend/retrieval/session_memory.py` | `session_memory_enabled` | True | **KEEP** |
| 46 | Follow-Up Suggestion Generation | `participant.js` | Always on | — | **KEEP** |
| 47 | Comparison Table Rendering | `participant.js` | Always on (compare) | — | **KEEP** |
| 48 | Anomaly Badge Rendering | `participant.js` | `anomaly_detection_enabled` | False | **KEEP** |

No changes needed in post-generation.

---

## 3. Summary of Decisions

### 3.1 Classification Tally

| Decision | Count | Techniques |
|----------|-------|------------|
| **KEEP** | 30 | Core pipeline techniques that are proven or structurally necessary |
| **EVALUATE** | 12 | Need ablation data before deciding |
| **REMOVE** | 1 | Keyword-boost rerank (#19) |
| **CONSOLIDATE** | 2 | Duplicate critique loops (#31 + #32) → single JS implementation |
| **FIX** | 1 | `context_expansion_enabled` duplicate declaration bug (#15) |

### 3.2 Immediate Bug Fixes (No Ablation Needed)

| Bug | File | Fix |
|-----|------|-----|
| `context_expansion_enabled` duplicate | `config/settings.py` lines 113 + 121 | Remove line 121. First declaration (`True`) is the intended default. |
| `pagerank_enabled` dead flag | `config/settings.py` | Remove standalone flag. Document that PageRank is always used as part of hybrid reranker (20% weight). |
| Keyword-boost after cross-encoder | `human_like_retriever.py` + `guide_retriever.py` | Remove keyword-boost rerank step. Cross-encoder alone is sufficient. |

### 3.3 Code to Delete

| File/Code | Reason |
|-----------|--------|
| Keyword-boost block in `human_like_retriever.py` Step 9 (~20 lines) | Overrides cross-encoder decisions |
| Keyword-boost block in `guide_retriever.py` Step 7 (~20 lines) | Same reason |
| Duplicate `context_expansion_enabled: bool = False` line | Bug fix |
| `pagerank_enabled` standalone flag + dead code | Unused legacy path |

---

## 4. Ablation Study Design

### 4.1 Experiment Matrix

Run golden tests (30 questions) for each configuration. Compare to baseline.

| Experiment ID | What Changes | Config |
|---------------|-------------|--------|
| **EXP-A** | Baseline (current v0.0.21 as-is) | All defaults |
| **EXP-B** | Remove keyword-boost | Code change: delete keyword-boost blocks |
| **EXP-C** | Disable JS multi-query expansion | `multi_query_rag_enabled = false` |
| **EXP-D** | Enable Self-RAG | `self_rag_enabled = true` |
| **EXP-E** | Disable synonym expansion | `query_expansion_enabled = false` |
| **EXP-F** | Disable BM25 hybrid | `enable_bm25_hybrid = false` |
| **EXP-G** | Disable MMR diversity | `enable_mmr_diversity = false` |
| **EXP-H** | Enable context expansion (after bug fix) | `context_expansion_enabled = true` |
| **EXP-I** | Combined best: B + D + H | Best combination from individual experiments |

### 4.2 Execution Protocol

For each experiment:

1. Set configuration
2. F5 → launch Extension Host
3. Run `kts.runGoldenTests` command
4. Collect results (30 × 5 scores = 150 data points)
5. Score against baseline
6. Record in `tests/golden_answer_results/ablation/EXP-X_results.json`

**Total: 9 experiments × ~15 minutes each = ~2.5 hours**

### 4.3 Decision Framework

After all experiments:

| If... | Then... |
|-------|---------|
| EXP-B overall ≥ EXP-A | ✅ Remove keyword-boost permanently |
| EXP-B overall < EXP-A by ≥ 0.3 | ❌ Keep keyword-boost (surprising result, investigate) |
| EXP-C overall < EXP-A by ≥ 0.5 | ✅ Keep JS multi-query (it matters) |
| EXP-C overall ≈ EXP-A (±0.2) | 🤔 Keep for now (free recall boost, no harm) |
| EXP-D overall > EXP-A by ≥ 0.5 on complex questions | ✅ Enable Self-RAG for `/deep` command |
| EXP-D overall ≈ EXP-A | ❌ Keep Self-RAG disabled (not worth latency) |
| EXP-H overall > EXP-A | ✅ Fix bug AND enable context expansion |

### 4.4 Expected Outcomes (Predictions)

| Experiment | Predicted Result | Confidence |
|------------|-----------------|------------|
| EXP-B (no keyword-boost) | +0.1 to +0.3 improvement | HIGH — keyword-boost likely hurts precision |
| EXP-C (no multi-query) | -0.1 to -0.3 worse | MEDIUM — multi-query helps recall |
| EXP-D (Self-RAG on) | +0.3 to +0.8 on complex, ±0 on simple | MEDIUM — helps waterfall/reporting |
| EXP-E (no synonyms) | -0.1 to -0.2 worse | LOW — hard to predict |
| EXP-F (no BM25) | -0.2 to -0.4 worse | MEDIUM — BM25 helps exact match (error codes, dates) |
| EXP-G (no MMR) | ±0 to -0.1 | LOW — diversity matters less with GPT-4.1's context window |
| EXP-H (context expansion on) | +0.1 to +0.3 improvement | MEDIUM — more context = better answers |

---

## 5. Pipeline Optimization Plan

### 5.1 Current Pipeline (Too Complex)

```
Query arrives
  ├── [JS] Acronym resolution                    # redundant with #2?
  ├── [JS] Multi-query expansion (LLM call)       # 1 LLM call
  │
  ├── [CLI] Backend search
  │   ├── Scope routing
  │   ├── Query rewriting (LLM call if pronouns)  # 0-1 LLM calls
  │   ├── Session memory bias
  │   ├── 3-tier synonym expansion                # 0 LLM calls
  │   ├── Temporal reasoning
  │   │
  │   ├── [Legal Mode: HumanLikeRetriever]
  │   │   ├── Graph-first section discovery
  │   │   ├── Section-scoped vector search
  │   │   ├── Global vector fallback
  │   │   ├── RRF fusion (vector + BM25)
  │   │   ├── MMR diversity rerank
  │   │   ├── Parent-child expansion
  │   │   ├── Definition enrichment (BFS depth 8)
  │   │   ├── Cross-encoder rerank                # neural model
  │   │   └── Keyword-boost rerank ← REMOVE
  │   │
  │   ├── [Convergent Loop? — unclear if active]
  │   │   ├── Hybrid rerank (sim 0.6 + PR 0.2 + proximity 0.2)
  │   │   ├── Graph BFS expansion (2-hop)
  │   │   └── Confidence check → repeat?
  │   │
  │   ├── Confidence scoring (5-tier)
  │   ├── Gap detection
  │   └── Evidence matching
  │
  ├── [JS] Context building + prompt selection
  ├── [JS] Token budget trimming
  ├── [JS] Conversation history injection
  ├── [JS] LLM generation (GPT-4.1)              # 1 LLM call
  │
  ├── [JS] Self-RAG loop? (0-3 rounds)           # 0-3 LLM calls each
  ├── [JS] Critique loop? (0-3 rounds)            # 0-3 LLM calls each
  │
  ├── [JS] Follow-up generation (regex or LLM)
  └── [JS] Session memory caching
```

Worst case LLM calls per query: **1 (multi-query) + 1 (rewrite) + 1 (generation) + 3×2 (Self-RAG) + 3 (critique) = 12 LLM calls**

### 5.2 Target Pipeline (Streamlined)

```
Query arrives
  ├── [JS] Multi-query expansion (LLM)            # 1 LLM call
  │
  ├── [CLI] Backend search
  │   ├── Scope routing
  │   ├── Query rewriting (if coreference)         # 0-1 LLM calls
  │   ├── Synonym expansion (static + learned)     # 0 LLM calls
  │   ├── Acronym resolution                       # 0 LLM calls
  │   ├── Temporal reasoning
  │   │
  │   ├── [Legal: HumanLikeRetriever]
  │   │   ├── Graph-first → section-scoped search
  │   │   ├── Global vector + BM25 fallback
  │   │   ├── RRF fusion
  │   │   ├── MMR diversity
  │   │   ├── Definition enrichment (BFS)
  │   │   └── Cross-encoder rerank (FINAL ranking)
  │   │
  │   ├── Context expansion (FIXED: enabled)       # restored
  │   ├── Confidence scoring
  │   ├── Gap detection
  │   └── Evidence matching
  │
  ├── [JS] Unified context building
  ├── [JS] Token budget trimming (auto-computed)
  ├── [JS] History + cached terms injection
  ├── [JS] LLM generation (GPT-4.1)               # 1 LLM call
  │
  ├── [JS] Critique loop (if enabled)              # 0-3 LLM calls
  ├── [JS] Native citations (stream.reference)
  ├── [JS] Follow-up chips (followupProvider only)
  └── [JS] Session memory caching
```

Changes:
- Removed keyword-boost rerank
- Cross-encoder is the FINAL ranking step (authority)
- Removed IterativeOrchestrator convergent loop (redundant with HumanLikeRetriever)
- Context expansion FIXED and enabled
- Self-RAG available but disabled by default (enable via `/deep` command)
- Single critique implementation (JS only)
- Acronym resolution moved to backend (alongside synonyms)
- No markdown follow-ups (native chips only)

**Target LLM calls: 1 (multi-query) + 0-1 (rewrite) + 1 (generation) = 2-3 LLM calls**  
With critique: +1-3 = 3-6 LLM calls  
With Self-RAG `/deep`: +3-6 = 5-9 LLM calls

### 5.3 Latency Budget

| Step | Current (est.) | Target (est.) |
|------|---------------|---------------|
| Multi-query expansion | 500ms | 500ms (unchanged) |
| Backend search | 2-4s | 1-3s (no convergent loop) |
| LLM generation | 3-8s | 3-8s (unchanged, model-dependent) |
| Critique (if enabled) | 2-6s | 2-6s (unchanged) |
| **Total (no critique)** | **6-12s** | **5-11s** |
| **Total (with critique)** | **8-18s** | **7-17s** |

Not significantly faster, but cleaner. The big win is **predictability** — no random convergent loop iterations.

---

## 6. Confidence Scoring Unification

### 6.1 Current: Three Independent Systems

| Scorer | Location | Input | Output |
|--------|----------|-------|--------|
| ConfidenceScorer | `confidence_scorer.py` | Cross-encoder scores | HIGH / MEDIUM / LOW / SPECULATIVE / NO_MATCH |
| Hybrid Confidence | `iterative_orchestrator.py` | hybrid_score mean | Float 0-1, threshold 0.85 |
| Critique Confidence | `critique_client.js` | LLM binary + keyword check | Per-fact confidence tracking |

These three systems produce DIFFERENT confidence metrics that are never reconciled.

### 6.2 Target: Single Confidence Pipeline

```
Cross-encoder scores (per chunk)
  └── Aggregate to query-level confidence
       ├── Mean cross-encoder score
       ├── Top-1 score (single best match)
       ├── Score spread (std dev — lower = more confident)
       └── Coverage: % of query terms found in top chunks

Confidence Tier:
  HIGH         = top-1 ≥ 0.8  AND mean ≥ 0.6  AND coverage ≥ 80%
  MEDIUM       = top-1 ≥ 0.5  AND mean ≥ 0.4  AND coverage ≥ 50%
  LOW          = top-1 ≥ 0.3  OR  mean ≥ 0.3
  SPECULATIVE  = top-1 < 0.3  AND mean < 0.3
  NO_MATCH     = no results OR all scores < 0.1
```

One confidence tier. One source of truth. Used by:
- UI display (confidence badge in the answer)
- Critique triggering (only runs if confidence < HIGH)
- Self-RAG triggering (only runs if confidence < MEDIUM)
- Follow-up generation (confidence-aware suggestions)

---

## 7. Feature Flag Cleanup

### 7.1 Current: 70+ Flags

The backend `KTSConfig` dataclass has 70+ boolean/numeric flags. Many have undocumented interactions:

```python
# What happens if BOTH are true?
hyde_enabled: bool = False
multi_query_rag_enabled: bool = True  # from settings, read by JS

# What if phase6_enabled is False but enable_bm25_hybrid is True?
phase6_enabled: bool = True
enable_bm25_hybrid: bool = True

# These three interact — in what order?
cross_encoder_enabled: bool = True
enable_mmr_diversity: bool = True
# keyword_boost — no flag, always on
```

### 7.2 Target: Documented Interactions

Create a feature interaction matrix:

| Flag A | Flag B | Interaction |
|--------|--------|-------------|
| `hyde_enabled` | `multi_query_rag_enabled` | CONFLICT: Both expand the query via LLM. Enable at most one. |
| `self_rag_enabled` | `critique_loop_enabled` | COMPATIBLE: Self-RAG improves context, critique improves answer. Both can run. |
| `enable_bm25_hybrid` | `cross_encoder_enabled` | DEPENDS: BM25 results are only useful if cross-encoder reranks them together with vector results. |
| `enable_mmr_diversity` | `cross_encoder_enabled` | ORDER: MMR should run BEFORE cross-encoder (diversity first, then precision). Currently runs after. |

### 7.3 Backend Config Simplification

The `RAG_CONFIG` constant from Phase B (02_SETTINGS_SIMPLIFICATION.md) hardcodes all performance-tuned values. Only 3 user-facing settings remain. The 70+ backend flags become internal-only constants with documented defaults:

```python
# config/settings.py — After cleanup
# These are INTERNAL constants. Users never see these.
# They are set based on extensive testing (Phase E ablation).

@dataclass
class KTSConfig:
    # ── Core Pipeline (always on) ──
    phase6_enabled: bool = True
    acronym_resolver_enabled: bool = True
    scope_routing_enabled: bool = True
    temporal_reasoning_enabled: bool = True
    cross_encoder_enabled: bool = True
    confidence_scoring_enabled: bool = True
    gap_detection_enabled: bool = True
    definition_traversal_enabled: bool = True
    evidence_matching_enabled: bool = True
    session_memory_enabled: bool = True
    
    # ── Query Expansion ──
    query_expansion_enabled: bool = True          # Static + learned synonyms
    query_rewriting_enabled: bool = True          # Coreference resolution
    hyde_enabled: bool = False                     # Disabled: redundant with JS multi-query
    
    # ── Retrieval ──
    enable_bm25_hybrid: bool = True
    enable_mmr_diversity: bool = True
    multi_hop_enabled: bool = True
    context_expansion_enabled: bool = True         # FIXED: was False due to duplicate
    parent_child_chunking_enabled: bool = False    # Available but off by default
    
    # ── Enrichment ──
    learned_synonyms_enabled: bool = True
    definition_traversal_depth: int = 8
    contradiction_detection_enabled: bool = True
    anomaly_detection_enabled: bool = False        # Opt-in (requires baseline corpus)
    
    # ── REMOVED ──
    # keyword_boost — REMOVED (overrides cross-encoder)
    # pagerank_enabled — REMOVED (always part of hybrid reranker)
    # iterative_convergent_loop — REMOVED (redundant with HumanLikeRetriever)
```

---

## 8. Exact Code Changes

### 8.1 Remove Keyword-Boost

**`backend/retrieval/human_like_retriever.py` — Step 9:**

Find the keyword-boost block (approximately 15-20 lines) that:
1. Extracts keywords from the query
2. Checks each chunk for keyword presence
3. Adds a bonus to the chunk's score

Delete the entire block. The chunks are already ranked by cross-encoder at Step 6.

**`backend/retrieval/guide_retriever.py` — Step 7:**

Same removal. Delete the keyword-boost block.

### 8.2 Fix context_expansion_enabled Bug

**`config/settings.py`:**

Remove the duplicate declaration:
```python
# DELETE this line:
context_expansion_enabled: bool = False     # ChunkExpander — deferred
```

Keep only:
```python
context_expansion_enabled: bool = True      # Expand context window around hit chunks
```

### 8.3 Remove Dead PageRank Flag

**`config/settings.py`:**

Remove:
```python
pagerank_enabled: bool = False
```

Add comment to hybrid reranker:
```python
# PageRank is integral to hybrid scoring (20% weight).
# Not independently toggleable — it runs as part of hybrid_reranker.py.
```

### 8.4 Consolidate Critique Loop

**Decision:** Keep `extension/lib/critique_client.js`. Remove `backend/retrieval/critique_loop.py` from the retrieval pipeline.

The backend's critique_loop.py remains as importable library code for CLI-only scenarios, but the main pipeline (extension → backend → extension) uses only the JS critique.

---

## 9. Testing Protocol

### 9.1 Pre-Ablation

1. Run 575 Python tests — must all pass (no backend regressions)
2. Run `node --check` on all JS files — must pass
3. Run golden answer tests — capture EXP-A baseline

### 9.2 Per-Experiment

1. Apply configuration change
2. Run golden answer tests (30 questions)
3. Compare to EXP-A
4. Record results

### 9.3 Post-Ablation

1. Apply all REMOVE/FIX changes
2. Apply best combination from ablation (EXP-I)
3. Run full Python test suite — all 575 must pass
4. Run golden answer tests — must match or beat baseline
5. Run existing retrieval tests (`score_queries.py`) — no regression

---

## 10. Acceptance Criteria

- [ ] All 48 techniques classified as KEEP/EVALUATE/REMOVE/CONSOLIDATE/FIX
- [ ] `context_expansion_enabled` bug fixed (single declaration, defaults True)
- [ ] Keyword-boost removed from both HumanLikeRetriever and GuideRetriever
- [ ] Dead `pagerank_enabled` standalone flag removed
- [ ] 9 ablation experiments completed with golden test scores
- [ ] Decision for each EVALUATE technique documented with evidence
- [ ] Combined best configuration identified (EXP-I)
- [ ] Confidence scoring unified to single pipeline
- [ ] Feature interaction matrix documented
- [ ] 575 Python tests still pass after all changes
- [ ] Golden answer test overall score ≥ baseline (no regression)
