# Phase 9: Directed Critique RAG — Architecture Document

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Architectural Principles

### 1.1 Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Decompose, don't escalate** | Instead of upgrading the critique model, decompose holistic judgment into binary sub-checks. Cheaper and more reliable. |
| **Invest at ingest, payoff at query** | One LLM call per document at ingest generates targeted critique questions — amortized across thousands of queries. |
| **Dual-model architecture** | Fixed cheap model (GPT-4.1) for all critique evaluation; user's selected model for answer generation only. Predictable cost. |
| **Full regression, not incremental** | After every gap-fix, restart critique from Q₁. Mirrors SDLC regression testing — changing code means re-running all tests. |
| **Provenance-filtered, not pure union** | Multi-doc question merging only activates questions from actually retrieved sections. Prevents 70%+ false gap rate. |
| **Deterministic before probabilistic** | Keyword safety net catches CAUTION/WARNING gaps with zero LLM cost before the critique loop even starts. |
| **Feature-flagged independently** | Ingest-time generation, query-time loop, and multi-doc merging each have their own config flag. |
| **Supersede Phase 8 Technique 9** | Phase 9 replaces Phase 8's holistic Self-RAG with directed critique. Phase 8 Techniques 1-8 remain as-is. |

### 1.2 Architectural Goals

1. **Critique precision:** Targeted binary questions detect gaps that holistic prompts miss (empirically validated: CAUTION preservation)
2. **Model independence:** Critique quality doesn't degrade when user selects a cheaper chat model
3. **Cost predictability:** Fixed critique model = predictable per-query cost (~$0.02)
4. **Doc-specific intelligence:** Critique questions reflect actual document structure (sections, tables, annotations)
5. **Multi-doc correctness:** Only relevant questions activate for each query's retrieved document set
6. **Convergence guarantee:** Hard cap on rounds + progress guard + best-answer selection
7. **Zero regression:** All Phase 6-8 tests pass after every increment
8. **Graceful degradation:** If generation fails → default questions. If loop fails → return initial answer.

---

## 2. Layer Architecture

### 2.1 Phase 9 Layer Changes

Phase 9 adds a new **CRITIQUE LAYER** between the existing Retrieval and Presentation layers, and extends the Ingestion layer with critique question generation.

```
┌─────────────────────────────────────────────────────┐
│                  PRESENTATION LAYER                  │
│  extension/chat/participant.js                       │
│  • Prompt selection (Legal vs KTS)         EXISTING  │
│  • Context block construction              EXISTING  │
│  • LLM streaming via VS Code LM API       EXISTING  │
│  + critique_client.js                      NEW 9.2   │
│  │ Wire critique loop after initial answer           │
│  │ Stream progress during critique rounds            │
│  │ Display critique trace (questions, gaps, rounds)  │
├─────────────────────────────────────────────────────┤
│                  ★ CRITIQUE LAYER (NEW)             │
│  backend/retrieval/critique_loop.py         NEW 9.2  │
│  • Directed sequential evaluation                    │
│  • Trigger pre-filter (deterministic)                │
│  • Keyword safety net (deterministic)                │
│  • Gap→query translation (fixed LLM)                │
│  • Re-retrieval orchestration                        │
│  • Best-answer tracking (argmax confidence)          │
│  • Full restart on gap (regression model)            │
│                                                      │
│  backend/retrieval/critique_merger.py       NEW 9.3  │
│  • Provenance-filtered question merging              │
│  • Chunk-count-weighted ordering                     │
│  • Confidence-based early exit                       │
│                                                      │
│  backend/retrieval/critique_prompts.py      NEW 9.2  │
│  • Single-question critique prompt                   │
│  • Gap→query translation prompt                      │
│  • Re-synthesis prompt                               │
├─────────────────────────────────────────────────────┤
│                  ORCHESTRATION LAYER                  │
│  backend/agents/retrieval_service.py       EXISTING  │
│  (no Phase 9 changes)                                │
├─────────────────────────────────────────────────────┤
│                  RETRIEVAL LAYER                      │
│  backend/retrieval/human_like_retriever.py  EXISTING │
│  + exclude_chunk_ids param support          MOD 9.2  │
│  backend/retrieval/bm25_retriever.py        Phase 8  │
│  backend/retrieval/cross_encoder.py         EXISTING │
├─────────────────────────────────────────────────────┤
│                  STORAGE LAYER                        │
│  backend/vector/dual_vector_store.py        EXISTING │
│  backend/graph/persistence.py               EXISTING │
│  + critique_questions.json per doc          NEW 9.1  │
├─────────────────────────────────────────────────────┤
│                  INGESTION LAYER                      │
│  backend/agents/ingestion_agent.py          MODIFIED │
│  │ + call CritiqueQuestionGenerator         MOD 9.1  │
│  backend/agents/critique_question_generator.py       │
│  │ NEW 9.1 — generates doc-specific questions        │
│  backend/agents/critique_defaults.py                 │
│  │ NEW 9.1 — fallback questions by doc_type          │
│  backend/common/models.py                   MODIFIED │
│  │ + CritiqueQuestion, SectionCritique, DocCritique  │
│  backend/vector/legal_chunker.py            EXISTING │
│  backend/extraction/legal_item_extractor.py EXISTING │
└─────────────────────────────────────────────────────┘
```

### 2.2 Key Architecture Change: Critique as a Separate Layer

In Phase 8, Self-RAG was embedded in the **Presentation layer** (`gap_analyzer.js`, `iterative_generator.js`). This created problems:
- Tight coupling with VS Code LM API
- JavaScript-only implementation (Python retrieval couldn't participate)
- Model selection tied to user's chat model

Phase 9 moves critique into a dedicated **Python-side layer** between Orchestration and Presentation:
- Critique logic is testable without VS Code
- Dual-model selection is controlled server-side
- Re-retrieval is a direct function call (not HTTP→backend→ChromaDB round-trip)
- The JS side (`critique_client.js`) is a thin wrapper that wires the API

---

## 3. Component Architecture

### 3.1 CritiqueQuestionGenerator (Inc 9.1)

```
┌──────────────────────────────────────────┐
│      CritiqueQuestionGenerator           │
│                                          │
│  Responsibilities:                       │
│  • Generate doc-specific critique Qs     │
│  • Handle context-length via summaries   │
│  • Validate generated questions          │
│  • Save/load critique_questions.json     │
│  • Fall back to defaults on failure      │
│                                          │
│  Dependencies:                           │
│  • LLM (GPT-4.1 via VS Code LM API)     │
│  • File system (.kts/documents/)         │
│  • Models: DocCritique, CritiqueQuestion │
│  • DEFAULT_QUESTIONS from critique_defaults│
│                                          │
│  Interface:                              │
│  generate(doc_text, doc_type, sections)  │
│    → DocCritique                         │
│  save(critique, kts_path)               │
│    → Path                                │
│  load(doc_id, kts_path)                 │
│    → DocCritique | None                  │
│  validate(critique)                      │
│    → list[str] (errors)                  │
│                                          │
│  File: backend/agents/                   │
│        critique_question_generator.py    │
│  Est. Lines: ~200                        │
└──────────────────────────────────────────┘
```

### 3.2 DirectedCritiqueLoop (Inc 9.2)

```
┌──────────────────────────────────────────┐
│        DirectedCritiqueLoop              │
│                                          │
│  Responsibilities:                       │
│  • Execute sequential binary critique    │
│  • Apply trigger pre-filter              │
│  • Run keyword safety net                │
│  • Manage dual-model (critique + gen)    │
│  • Gap→query translation                 │
│  • Orchestrate re-retrieval              │
│  • Track best answer across rounds       │
│  • Enforce max_rounds cap                │
│  • Stream progress updates               │
│                                          │
│  Dependencies:                           │
│  • Critique LLM (fixed: GPT-4.1)        │
│  • Generation LLM (user's selection)     │
│  • HumanLikeRetriever (re-retrieval)     │
│  • CritiqueQuestionGenerator (load Qs)   │
│  • CritiqueMerger (multi-doc merging)    │
│  • AnswerTracker (best answer)           │
│                                          │
│  Interface:                              │
│  run(query, initial_answer,             │
│      initial_chunks, critique_questions) │
│    → CritiqueResult                      │
│                                          │
│  Internal Methods:                       │
│  _evaluate_question(Q, answer, chunks)   │
│    → {"pass": bool, "gap_description": ?}│
│  _translate_gap(gap, query) → str        │
│  _re_retrieve(query, exclude_ids)        │
│    → list[dict]                          │
│  _re_synthesize(query, answer,           │
│                  new_chunks, gap) → str   │
│  _keyword_safety_check(answer, chunks)   │
│    → list[dict]                          │
│                                          │
│  File: backend/retrieval/critique_loop.py│
│  Est. Lines: ~350                        │
└──────────────────────────────────────────┘
```

### 3.3 CritiqueMerger (Inc 9.3)

```
┌──────────────────────────────────────────┐
│          CritiqueMerger                  │
│                                          │
│  Responsibilities:                       │
│  • Map chunks to (doc_id, section_id)    │
│  • Filter questions by provenance        │
│  • Order by chunk-count descending       │
│  • Deduplicate identical questions       │
│  • Implement early exit logic            │
│                                          │
│  Dependencies:                           │
│  • Retrieved chunks (with metadata)      │
│  • DocCritique stores (loaded)           │
│                                          │
│  Interface:                              │
│  merge_critique_questions(               │
│    retrieved_chunks,                     │
│    critique_stores                       │
│  ) → list[CritiqueQuestion]             │
│                                          │
│  should_early_exit(                      │
│    confidence,                           │
│    remaining_questions,                  │
│    threshold                             │
│  ) → bool                                │
│                                          │
│  File: backend/retrieval/               │
│        critique_merger.py                │
│  Est. Lines: ~150                        │
└──────────────────────────────────────────┘
```

### 3.4 AnswerTracker (Inc 9.2/9.3)

```
┌──────────────────────────────────────────┐
│          AnswerTracker                   │
│                                          │
│  Responsibilities:                       │
│  • Record (answer, score) per round      │
│  • Return argmax(confidence) answer      │
│  • Detect regression (latest < best)     │
│  • Report improvement status             │
│                                          │
│  Dependencies: None                      │
│                                          │
│  Interface:                              │
│  record(answer, confidence, round)       │
│  best → dict                             │
│  improved → bool                         │
│  regression_detected → bool              │
│                                          │
│  File: backend/retrieval/critique_loop.py│
│  (embedded class, ~30 lines)             │
└──────────────────────────────────────────┘
```

### 3.5 CritiqueClient (JS Side — Inc 9.2)

```
┌──────────────────────────────────────────┐
│      CritiqueClient (JavaScript)         │
│                                          │
│  Responsibilities:                       │
│  • Select fixed critique model via       │
│    vscode.lm.selectChatModels()          │
│  • Call backend critique_loop endpoint   │
│  • Stream progress to chat UI            │
│  • Handle critique model unavailability  │
│  • Render critique trace in response     │
│                                          │
│  Dependencies:                           │
│  • VS Code LM API                        │
│  • Backend HTTP API                      │
│  • participant.js (integration)          │
│                                          │
│  Interface:                              │
│  selectCritiqueModel() → ChatModel       │
│  runCritiqueLoop(query, initialAnswer,   │
│    result, questions, stream, token)     │
│    → CritiqueResult                      │
│                                          │
│  File: extension/lib/critique_client.js  │
│  Est. Lines: ~120                        │
└──────────────────────────────────────────┘
```

---

## 4. Data Flow Architecture

### 4.1 Ingestion-Time Flow (Inc 9.1)

```
User: @kts Ingest source_4/
         │
         ▼
┌────────────────────────┐
│  Ingestion Agent        │
│  (existing pipeline)    │
│  crawl → extract →     │
│  chunk → embed → graph │
└──────────┬─────────────┘
           │ doc_text, sections, doc_type
           ▼
┌────────────────────────┐
│  CritiqueQuestionGen   │  ← NEW (Inc 9.1)
│  1. Prepare doc content│
│     (full or summary)  │
│  2. Call fixed LLM     │
│     (GPT-4.1)          │
│  3. Parse questions    │
│  4. Validate           │
│  5. Save to .kts/      │
│     documents/{id}/    │
│     critique_questions │
│     .json              │
└──────────┬─────────────┘
           │ (on failure)
           ▼
┌────────────────────────┐
│  Default Library        │
│  critique_defaults.py  │
│  Static questions by   │
│  doc_type              │
└────────────────────────┘
```

### 4.2 Query-Time Flow (Inc 9.2 + 9.3)

```
User: @kts "computer won't restart after pressing power button"
         │
         ▼
┌────────────────────────────────────────────────────┐
│  EXISTING PIPELINE (Phase 6/7/8)                    │
│  1. Filter extraction                               │
│  2. Query decomposition                             │
│  3. Graph section discovery                         │
│  4-5. Section + global search (+ BM25 hybrid)       │
│  6. RRF fusion (+ parent expansion)                 │
│  7. Definition enrichment                           │
│  8. Cross-encoder rerank                            │
│  9. Keyword boost                                   │
│  10-11. Drill-down + confidence                     │
└──────────────┬─────────────────────────────────────┘
               │ chunks (3-5), confidence, doc_type_vote
               ▼
┌────────────────────────────────────────────────────┐
│  PRESENTATION: Initial Answer (user's model)        │
│  participant.js → LLM API → answer A₀               │
└──────────────┬─────────────────────────────────────┘
               │ A₀, chunks, doc_ids
               ▼
┌────────────────────────────────────────────────────┐
│  ★ CRITIQUE LAYER (NEW)                            │
│                                                     │
│  Step A: Load questions (Inc 9.1)                   │
│    For each doc_id → load critique_questions.json   │
│    If missing → load DEFAULT_QUESTIONS[doc_type]    │
│                                                     │
│  Step B: Merge questions (Inc 9.3)                  │
│    Provenance filter: keep only retrieved sections  │
│    Order: doc-level → high-chunk-count → low        │
│                                                     │
│  Step C: Trigger pre-filter (deterministic)         │
│    Skip questions whose keywords don't match chunks │
│    Result: ~5 active questions from ~15 total       │
│                                                     │
│  Step D: Keyword safety net (deterministic)         │
│    CAUTION in source && !CAUTION in answer → gap    │
│    Inject synthetic gaps at front of queue           │
│                                                     │
│  Step E: Sequential critique loop (Inc 9.2)         │
│    for round in 1..max_rounds:                      │
│      for Q in active_questions:                     │
│        Pre-filter: trigger_matches(Q, chunks)?      │
│        Critique: fixed_llm(Q, A, chunks) → verdict  │
│        If fail:                                     │
│          query = fixed_llm.translate_gap(gap)       │
│          new_chunks = retriever.search(query)       │
│          A = user_llm.synthesize(A, new_chunks)     │
│          tracker.record(A, confidence)              │
│          RESTART from Q₁                            │
│      All passed → CONVERGED                         │
│                                                     │
│  Step F: Best-answer selection                      │
│    return tracker.best (argmax confidence)           │
│                                                     │
│  Step G: Early exit check (Inc 9.3)                 │
│    If confidence > 0.90 and only tail questions     │
│    remain → skip remaining, return current          │
│                                                     │
└──────────────┬─────────────────────────────────────┘
               │ best_answer, critique_trace
               ▼
┌────────────────────────────────────────────────────┐
│  PRESENTATION: Stream to User                       │
│  participant.js renders:                            │
│  • Answer (markdown)                                │
│  • Citations                                        │
│  • Critique trace:                                  │
│    "✓ 5 checks passed, 1 gap fixed, 2 rounds,     │
│     confidence 0.94"                                │
└────────────────────────────────────────────────────┘
```

---

## 5. Dual-Model Selection Architecture

### 5.1 Model Selection Flow

```
┌──────────────────────────────────────┐
│        VS Code LM API                 │
│  vscode.lm.selectChatModels()        │
│                                       │
│  • User's model (chat panel):         │
│    Whatever model is selected in      │
│    VS Code Copilot (Opus, GPT-4.1)   │
│                                       │
│  • Critique model (fixed):            │
│    selectChatModels({                 │
│      vendor: 'copilot',               │
│      family: 'gpt-4.1'               │
│    })[0]                              │
│                                       │
│  Fallback chain for critique:         │
│  1. gpt-4.1 (preferred)              │
│  2. gpt-4o (if 4.1 unavailable)      │
│  3. user's selected model (last resort)│
└──────────────────────────────────────┘
```

### 5.2 Model Selection in JavaScript

```javascript
async function selectCritiqueModel(vscode) {
    // Try preferred critique model first
    const preferred = ['gpt-4.1', 'gpt-4o', 'gpt-4o-mini'];
    
    for (const family of preferred) {
        const models = await vscode.lm.selectChatModels({
            vendor: 'copilot',
            family: family
        });
        if (models.length > 0) {
            return models[0];
        }
    }
    
    // Fallback: use whatever model is available
    const any = await vscode.lm.selectChatModels({ vendor: 'copilot' });
    return any[0] || null;
}
```

### 5.3 Cost Comparison

| Architecture | Critique cost per query | Quality consistency |
|-------------|------------------------|---------------------|
| Phase 8 (single model) | $0 (same model) | ❌ Varies with user's model choice |
| Phase 9 (dual model) | ~$0.02 (fixed GPT-4.1) | ✅ Always GPT-4.1 quality |

The $0.02 overhead per query for critique is negligible compared to the $0.03-0.15 cost of the user-facing answer generation — and it **guarantees** consistent critique quality regardless of which model the user selects in their chat panel.

---

## 6. File Structure — Phase 9 Changes

```
backend/
├── retrieval/
│   ├── human_like_retriever.py    ← MOD (exclude_chunk_ids param)
│   ├── critique_loop.py           ← NEW (Inc 9.2: directed critique loop)
│   ├── critique_merger.py         ← NEW (Inc 9.3: provenance-filtered merging)
│   ├── critique_prompts.py        ← NEW (Inc 9.2: prompt templates)
│   ├── bm25_retriever.py          ← UNCHANGED (Phase 8)
│   ├── cross_encoder.py           ← UNCHANGED
│   └── iterative_orchestrator.py  ← UNCHANGED
├── vector/
│   ├── dual_vector_store.py       ← UNCHANGED
│   ├── legal_chunker.py           ← UNCHANGED
│   └── embedding_provider.py      ← UNCHANGED
├── agents/
│   ├── ingestion_agent.py         ← MOD (wire critique question gen)
│   ├── critique_question_generator.py ← NEW (Inc 9.1)
│   ├── critique_defaults.py       ← NEW (Inc 9.1: default question library)
│   └── retrieval_service.py       ← UNCHANGED
├── extraction/
│   └── legal_item_extractor.py    ← UNCHANGED
├── graph/
│   ├── enhanced_graph_builder.py  ← UNCHANGED
│   └── persistence.py             ← UNCHANGED
└── common/
    ├── models.py                  ← MOD (CritiqueQuestion, DocCritique dataclasses)
    └── explainability.py          ← UNCHANGED

extension/
├── chat/
│   └── participant.js             ← MOD (wire critique loop after initial answer)
├── lib/
│   ├── critique_client.js         ← NEW (Inc 9.2: JS critique loop client)
│   ├── hype_enricher.js           ← UNCHANGED (Phase 8)
│   ├── query_expander.js          ← UNCHANGED (Phase 8)
│   ├── gap_analyzer.js            ← DEPRECATED (replaced by critique_loop.py)
│   └── iterative_generator.js     ← DEPRECATED (replaced by critique_loop.py)
└── ...                            ← UNCHANGED

config/
└── settings.py                    ← MOD (9 new critique settings)

tests/
├── test_phase9_critique_gen.py         ← NEW (Inc 9.1: ~30 tests)
├── test_phase9_critique_loop.py        ← NEW (Inc 9.2: ~38 tests)
├── test_phase9_multi_doc_critique.py   ← NEW (Inc 9.3: ~19 tests)
├── test_phase9_integration.py          ← NEW (cross-increment)
├── test_phase9_comparative.py          ← NEW (A/B scoring)
├── golden_queries_phase9.json          ← NEW (20 golden queries)
└── ...                                 ← UNCHANGED (regression suite)

.kts/
└── documents/
    └── {doc_id}/
        └── critique_questions.json     ← NEW (Inc 9.1, per document)
```

### 6.1 New Files Summary

| File | Inc | Lines (est.) | Purpose |
|------|-----|-------------|---------|
| `backend/agents/critique_question_generator.py` | 9.1 | ~200 | Ingest-time question generation |
| `backend/agents/critique_defaults.py` | 9.1 | ~80 | Default fallback questions |
| `backend/retrieval/critique_loop.py` | 9.2 | ~350 | Core critique loop + AnswerTracker |
| `backend/retrieval/critique_prompts.py` | 9.2 | ~100 | Prompt templates (critique, translate, synthesize) |
| `backend/retrieval/critique_merger.py` | 9.3 | ~150 | Provenance-filtered question merging |
| `extension/lib/critique_client.js` | 9.2 | ~120 | JS client for dual-model + streaming |
| **Total new code** | | **~1000** | |

| Modified File | Inc | Lines changed (est.) |
|-----|-----|-----|
| `backend/common/models.py` | 9.1 | ~40 (new dataclasses) |
| `backend/agents/ingestion_agent.py` | 9.1 | ~15 (wire generator) |
| `backend/retrieval/human_like_retriever.py` | 9.2 | ~10 (exclude_chunk_ids) |
| `extension/chat/participant.js` | 9.2 | ~40 (wire critique loop) |
| `config/settings.py` | 9.1+9.2 | ~15 (new settings) |
| **Total modified** | | **~120** |

### 6.2 Deprecated Files (Phase 8 → Phase 9)

| Phase 8 File (planned) | Phase 9 Replacement | Reason |
|------------------------|--------------------|---------| 
| `extension/lib/gap_analyzer.js` | `backend/retrieval/critique_loop.py` | Holistic gap analysis → directed binary critique |
| `extension/lib/iterative_generator.js` | `backend/retrieval/critique_loop.py` | JS-side loop → Python-side loop with dual-model |

These Phase 8 files are **never created** — Phase 9 supersedes them. The implementation will go directly to the Phase 9 architecture.

---

## 7. Storage Architecture

### 7.1 critique_questions.json Lifecycle

```
CREATION (Inc 9.1, ingest time):
  ingestion_agent.py 
    → CritiqueQuestionGenerator.generate()
    → CritiqueQuestionGenerator.validate()
    → CritiqueQuestionGenerator.save()
    → .kts/documents/{doc_id}/critique_questions.json

READING (Inc 9.2/9.3, query time):
  critique_loop.py
    → CritiqueQuestionGenerator.load(doc_id)
    → CritiqueMerger.merge_critique_questions()
    → DirectedCritiqueLoop.run()

REGENERATION:
  Re-ingest document → generate() overwrites existing file
  Manual: delete file → next ingest regenerates
  Config change: critique_generator_model → regenerate all

DELETION:
  Safe to delete at any time
  Missing file → DEFAULT_QUESTIONS[doc_type] used
  No ChromaDB dependency — standalone JSON
```

### 7.2 Storage Size Impact

| Component | Size per doc | Size per corpus (20 docs) |
|-----------|-------------|---------------------------|
| critique_questions.json | 3-8 KB | 60-160 KB |
| ChromaDB (existing) | 5-50 MB | 5-50 MB |
| Graph JSON (existing) | 0.5-5 MB | 0.5-5 MB |
| **Phase 9 overhead** | | **< 0.2 MB** |

Negligible storage impact. The critique_questions.json files are smaller than a single image thumbnail.

---

## 8. Technique Source Mapping

| KTS Implementation | Source | Algorithm Adopted |
|-------------------|--------|-------------------|
| `CritiqueQuestionGenerator.generate()` | **Novel** (no published precedent) | LLM generates section-level binary critique Qs from full doc at ingest time |
| `DirectedCritiqueLoop.run()` | Self-RAG (Asai 2023) + CRAG (Yan 2024) | Decomposed reflection tokens → binary per-question critique with separate evaluator model |
| Dual-model (critique ≠ generation) | CRAG (Yan 2024) | External evaluator model distinct from generator |
| `trigger_matches()` | Cohere RAG pipeline | Deterministic pre-filter on keyword presence before LLM evaluation |
| `keyword_safety_check()` | Anthropic prompting guide | Decompose complex judgment ("is answer complete?") into narrow checks ("is CAUTION present?") |
| `merge_critique_questions()` | LlamaIndex Corrective RAG (adapted) | Relevance filtering of evaluation criteria based on retrieval provenance |
| Full restart on gap (Q₁ regression) | **SDLC regression testing** (novel application to RAG) | Every state change re-runs the full test suite |
| `AnswerTracker.best` (argmax confidence) | Multi-agent debate (Du et al. 2023) | Best answer = highest consensus score across rounds, not necessarily latest |
| Gap→query translation | FLARE (Jiang 2023) | Convert low-confidence signals into targeted retrieval queries |

**Novel contributions unique to KTS Phase 9:**
1. Ingestion-time critique question generation (no published precedent)
2. Section-level trigger keywords for deterministic pre-filtering
3. Full Q₁ regression restart on gap-fix (SDLC analogy applied to RAG)
4. Provenance-filtered multi-doc question merging with chunk-count ordering
5. Rubric-based expected answer structure per section

---

## 9. Configuration Architecture

### 9.1 Phase 9 Feature Flags

```python
# In config/settings.py — Phase 9 additions

# ── Inc 9.1: Ingestion-Time Critique ──
critique_generation_enabled: bool = True
critique_generator_model: str = "gpt-4.1"
critique_max_questions_per_doc: int = 15

# ── Inc 9.2: Directed Critique Loop ──
critique_loop_enabled: bool = True
critique_model: str = "gpt-4.1"
critique_max_rounds: int = 3
critique_restart_on_gap: bool = True

# ── Inc 9.3: Multi-Doc Merging ──
critique_multi_doc_enabled: bool = True
critique_confidence_exit: float = 0.90
```

### 9.2 Environment Variable Overrides

```
KTS_CRITIQUE_GEN_ENABLED=false    → skip ingest-time generation
KTS_CRITIQUE_GEN_MODEL=gpt-4o    → use different generation model
KTS_CRITIQUE_LOOP_ENABLED=false   → skip query-time critique
KTS_CRITIQUE_MODEL=gpt-4o        → use different critique model
KTS_CRITIQUE_MAX_ROUNDS=5         → allow more loop iterations
KTS_CRITIQUE_RESTART=false        → resume-from-gap (not regression)
KTS_CRITIQUE_MULTI_DOC=false      → single-doc mode only
KTS_CRITIQUE_CONFIDENCE_EXIT=0.95 → higher threshold for early exit
KTS_CRITIQUE_MAX_Q_PER_DOC=20     → more questions per doc
```

---

## 10. Deployment Considerations

### 10.1 Build Pipeline Impact

Phase 9 adds **~1000 lines of pure Python** and **~120 lines of JavaScript**. No new binary dependencies, no new pip packages, no new ONNX models. Build pipeline unchanged:

```
Python source → PyInstaller → kts-backend binary → extension/bin/
Extension source + bin/ → vsce package → .vsix
```

Expected VSIX size impact: < 10 KB increase (pure source code only).

### 10.2 Re-Ingestion Requirement

After implementing Inc 9.1, all previously ingested documents must be **re-ingested** to generate their critique_questions.json files. This is the same re-ingestion already required by Phase 8 (CCH headers, parent-child linking).

**Detection and notification:**
```python
def _needs_critique_generation(self, doc_id: str) -> bool:
    """Check if document has critique questions generated."""
    critique_path = self.kts_path / "documents" / doc_id / "critique_questions.json"
    return not critique_path.exists()
```

When detected, the extension shows: *"New critique question generation available. Re-ingest documents for improved answer quality."*

### 10.3 Backward Compatibility

All Phase 9 features degrade gracefully:

| Scenario | Behavior |
|----------|----------|
| No critique_questions.json for doc | Use DEFAULT_QUESTIONS[doc_type] |
| critique_loop_enabled = False | Return initial answer (Phase 8 behavior) |
| Critique model unavailable | Skip critique, return initial answer |
| All questions filtered by triggers | Return initial answer (no critique needed) |
| No sections in chunk metadata | Assign to sec000, doc-level questions only |
| critique_generation_enabled = False | No questions generated; loop uses defaults |
