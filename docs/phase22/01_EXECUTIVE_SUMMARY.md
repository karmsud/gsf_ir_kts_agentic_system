# Phase 22: Executive Summary
## Infrastructure Replacement & LLM Wiring via VS Code LM API

**Document Version:** 1.0  
**Date:** February 26, 2026  
**Status:** Proposal — Pending Approval  
**Business Impact:** TRANSFORMATIONAL — ABS agents gain enterprise retrieval + LLM generation  
**Estimated Effort:** 10–14 hours  
**Prerequisite:** Phase 21 complete (all ABS code in `backend/abs/`, AgentBase merged)

---

## Table of Contents
1. [Executive Overview](#executive-overview)
2. [Two Transformations](#two-transformations)
3. [LLM Strategy](#llm-strategy)
4. [Infrastructure Replacement Summary](#infrastructure-replacement-summary)
5. [LLM Call Site Map](#llm-call-site-map)
6. [Value Proposition](#value-proposition)
7. [Risk Assessment](#risk-assessment)
8. [Success Metrics](#success-metrics)

---

## Executive Overview

### What Phase 22 Delivers

Phase 21 placed ABS domain logic inside KTS but left three temporary stubs (`embedder`, `graph_builder`, `vector_search`) and zero LLM calls. Phase 22 completes the integration:

1. **Infrastructure Replacement** — Remove stubs; wire ABS modules to KTS's production-grade retrieval, graph, and embedding infrastructure
2. **LLM Wiring** — Connect all 32 identified LLM call sites to GPT-4.1 via VS Code LM API

**After Phase 22, ABS agents can:**
- Ingest PSA documents with 31-module retrieval pipeline (BM25, HyDE, CRAG, critique loop)
- Generate payment models with GPT-4.1 via VS Code LM API
- Answer ABS domain questions with multi-hop graph-guided retrieval
- Generate governing documents with LLM-powered natural language generation
- Audit payment models with LLM-powered analysis

---

## Two Transformations

### Transformation 1: Infrastructure Replacement

Replace temporary stubs with KTS's production infrastructure:

| Stub | Replacement | Capability Gain |
|------|------------|-----------------|
| `abs/skills/embedder.py` | `backend/vector/embedding_provider.py` | BGE ONNX INT8, query prefix, model hash |
| `abs/skills/graph_builder.py` | `backend/graph/enhanced_graph_builder.py` | 14 node types, PageRank, resolution trees |
| `abs/skills/vector_search.py` | `backend/retrieval/retrieval_service.py` | 31 retrieval modules, BM25 hybrid, CRAG |

**Net effect:** ABS ingestion/search jumps from basic single-vector-store retrieval to enterprise-grade hierarchical GraphRAG.

### Transformation 2: LLM Wiring

Connect GPT-4.1 to all code paths that need language model generation:

```
┌─────────────────────────────────────────────────────────┐
│                  VS Code LM API                          │
│                                                          │
│  vscode.lm.selectChatModels({vendor:'copilot',           │
│                               family:'gpt-4.1'})         │
│                                                          │
│  Free in org — no API key, no rate limits                │
└──────────────────────────┬──────────────────────────────┘
                           │
              ┌────────────┼──────────────┐
              │            │              │
     ┌────────▼────┐  ┌────▼─────┐  ┌────▼──────────┐
     │ Background  │  │ User-    │  │ Quality       │
     │ Tasks       │  │ Visible  │  │ Enhancement   │
     │             │  │ Outputs  │  │               │
     │ GPT-4.1     │  │ User-    │  │ GPT-4.1       │
     │ hardcoded   │  │ selected │  │ hardcoded     │
     │             │  │ model    │  │               │
     │ • CRAG      │  │          │  │ • Critique    │
     │ • Concept   │  │ • Q&A    │  │   loop        │
     │   vocab     │  │ • Model  │  │ • Self-RAG    │
     │ • Multi-    │  │   gen    │  │ • Multi-query │
     │   query     │  │ • Audit  │  │   expansion   │
     │ • Gov doc   │  │ • Gov    │  │               │
     │   gen       │  │   doc    │  │               │
     └─────────────┘  └──────────┘  └───────────────┘
```

---

## LLM Strategy

### Two-Tier Model Selection

**Tier 1: Background Tasks (GPT-4.1 hardcoded)**
- CRAG claim verification
- Concept vocabulary enrichment  
- Multi-query expansion
- Governing document generation (internal structure)
- Definition extraction augmentation
- Critique generation

**Tier 2: User-Visible Outputs (User-selected model)**
- Q&A answers displayed in chat
- Payment model Python code generation
- Model auditing reports
- Governing document final output (if user-facing)

### KTS `llm_callable` Pattern

KTS already has a dependency-injection pattern for LLM calls (`llm_callable`). ABS modules adopt this pattern:

```python
# Pattern used by all ABS LLM calls:
from typing import Callable, Optional

LLMCallable = Callable[[str, Optional[str]], str]
# signature: (prompt: str, system_prompt: Optional[str]) -> str

class ModelCreationAgent(AgentBase):
    def __init__(self, deal_scope, config, llm_callable: Optional[LLMCallable] = None):
        super().__init__("model-creation", config, deal_scope=deal_scope)
        self._llm = llm_callable  # injected by extension or CLI

    def _run(self, task):
        if self._llm:
            code = self._llm(self.system_prompt, None)
        else:
            code = self._template_based_generation(task)
        return code
```

### VS Code LM API Bridge

The extension passes an `llm_callable` that wraps `vscode.lm.selectChatModels()`:

```javascript
// extension/chat/abs_participant.js
async function createLLMCallable(vscode, model) {
    return async (prompt, systemPrompt) => {
        const [selectedModel] = await vscode.lm.selectChatModels({
            vendor: 'copilot',
            family: model || 'gpt-4.1'
        });
        const messages = [];
        if (systemPrompt) {
            messages.push(vscode.LanguageModelChatMessage.User(systemPrompt));
        }
        messages.push(vscode.LanguageModelChatMessage.User(prompt));
        const response = await selectedModel.sendRequest(messages);
        let result = '';
        for await (const chunk of response.text) {
            result += chunk;
        }
        return result;
    };
}
```

---

## Infrastructure Replacement Summary

### Embedder Replacement

| Aspect | PayGen (`embedder.py`, 136 lines) | KTS (`embedding_provider.py`) |
|--------|----------------------------------|------------------------------|
| Model | BGE ONNX INT8 768-dim | BGE ONNX INT8 768-dim (identical) |
| Query prefix | None | `"Represent this sentence: "` |
| ChromaDB adapter | Basic `upsert()` | Full adapter with metadata, batch |
| Model hash | None | SHA-256 for cache invalidation |
| Functions | `embed()`, `chunk_text()` | `embed_query()`, `embed_documents()` |

**Migration:** Replace calls to `embed_and_store()` with KTS's `EmbeddingProvider.embed_documents()`.

### Graph Builder Replacement

| Aspect | PayGen (`graph_builder.py`, 294 lines) | KTS (`enhanced_graph_builder.py`, 3,000+ lines) |
|--------|---------------------------------------|------------------------------------------------|
| Node types | 7 (document, section, concept, etc.) | 14 (+ items, definitions, errors, procedures) |
| PageRank | None | Personalized PageRank (0.85 alpha) |
| Resolution trees | None | Full definition resolution trees |
| NER enrichment | None | SpaCy NER node creation |
| Edge types | 3 (HAS_CONCEPT, HAS_SECTION, REFERENCES) | 12 (+ CONTAINS, NEXT, HAS_RULE, DEFINES, etc.) |

**Migration:** Replace `build_graph()` + `query_graph()` with KTS's `EnhancedGraphBuilder`.

### Vector Search Replacement

| Aspect | PayGen (`vector_search.py`, 179 lines) | KTS (`retrieval_service.py`, 2,714 lines) |
|--------|----------------------------------------|------------------------------------------|
| Search modes | 1 (basic vector) | 31 modules (BM25, HyDE, CRAG, etc.) |
| Reranking | None | Cross-encoder + PageRank hybrid |
| Context expansion | None | Adaptive context window |
| Section awareness | Basic metadata filter | Full section-level + item-level dual search |

**Migration:** Replace `vector_search()` + `search_by_section()` with KTS's `RetrievalService.search()`.

---

## LLM Call Site Map

### ABS Domain — 17 Call Sites

| # | Module | Function | LLM Purpose | Tier |
|---|--------|----------|-------------|------|
| 1 | `governing_doc_generator.py` | `_generate_section()` | Generate governing doc section text | Background |
| 2 | `governing_doc_generator.py` | `_summarize_section()` | Summarize extracted section | Background |
| 3 | `governing_doc_generator.py` | `_classify_obligations()` | Classify obligation types | Background |
| 4 | `model_creation_agent.py` | `_generate_payment_model()` | Generate Python payment model code | User-visible |
| 5 | `model_creation_agent.py` | `_refine_model()` | Refine model based on test failures | User-visible |
| 6 | `model_auditor_agent.py` | `_audit_model()` | Audit payment model logic | User-visible |
| 7 | `model_auditor_agent.py` | `_compare_to_spec()` | Compare model to PSA spec | User-visible |
| 8 | `qa_agent.py` | `_answer_question()` | Answer ABS domain question | User-visible |
| 9 | `qa_agent.py` | `_generate_citations()` | Generate source citations | Background |
| 10 | `document_quality_agent.py` | `_assess_extraction_quality()` | Assess extraction completeness | Background |
| 11 | `document_comparison_agent.py` | `_compare_documents()` | Compare two deal documents | User-visible |
| 12 | `cashflow_projection_agent.py` | `_explain_projection()` | Explain projection results | User-visible |
| 13 | `investor_reporting_agent.py` | `_generate_report()` | Generate investor report | User-visible |
| 14 | `stress_testing_agent.py` | `_analyze_scenarios()` | Analyze stress test results | User-visible |
| 15 | `structured_extractor.py` | `_extract_with_llm()` | LLM-assisted field extraction | Background |
| 16 | `definition_resolution.py` | `_resolve_ambiguous()` | Resolve ambiguous definitions | Background |
| 17 | `ingestion_validator.py` | `_validate_completeness()` | Validate ingestion completeness | Background |

### KTS Infrastructure — 15 Call Sites (Already Mapped)

| # | Module | Function | LLM Purpose | Tier |
|---|--------|----------|-------------|------|
| 18 | `multi_query_rag.py` | `expand_query()` | Generate query variants | Background |
| 19 | `hyde_generator.py` | `generate_hypothetical()` | HyDE hypothetical document | Background |
| 20 | `critique_generator.py` | `generate_critique()` | Generate retrieval critique | Background |
| 21 | `critique_loop.py` | `critique_and_refine()` | Iterative critique refinement | Background |
| 22 | `self_rag.py` | `self_assess()` | Self-RAG relevance check | Background |
| 23 | `concept_vocabulary.py` | `enrich_vocabulary()` | Concept vocabulary enrichment | Background |
| 24 | `crag_verifier.py` | `verify_claims()` | CRAG claim verification | Background |
| 25 | `crag_verifier.py` | `generate_claims()` | Extract claims from answer | Background |
| 26 | `summary_generator.py` | `summarize()` | Document summary generation | User-visible |
| 27 | `extraction_agent.py` | `extract_fields()` | Field extraction | Background |
| 28–32 | Various | Various | Additional LLM calls | Mixed |

**Total: 32 LLM call sites across unified codebase.**

---

## Value Proposition

### Before Phase 22
- ABS code in KTS but uses stubs — cannot ingest or search
- Zero LLM calls — all agents are template-based or no-ops
- No retrieval beyond basic vector search

### After Phase 22
- Full enterprise retrieval pipeline available to ABS agents
- GPT-4.1 powers model generation, auditing, Q&A, governing docs
- 31 retrieval modules enhance ABS document understanding
- Hierarchical graph with PageRank improves relevance scoring
- CRAG verification ensures factual accuracy of ABS answers

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| LLM API unavailability | ⚪ Low | 🟡 Medium | Template fallback for all LLM calls; `llm_callable` is optional |
| Infrastructure API mismatch | 🟡 Medium | 🟡 Medium | Write adapter functions; test with real PSA data |
| Embedding dimension mismatch | ⚪ Very Low | 🟠 High | Both use 768-dim BGE ONNX INT8 — verified identical |
| Graph schema incompatibility | 🟡 Medium | 🟡 Medium | ABS nodes use `abs_` prefix to avoid collision |
| Rate limiting on GPT-4.1 | ⚪ Very Low | ⚪ Low | Free in org; no observed limits |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| All 3 stubs replaced with real KTS infrastructure | ✅ |
| ABS ingestion pipeline processes Bear Stearns 2006-HE1 | ✅ |
| ABS vector search returns relevant results (recall ≥ 0.80) | ✅ |
| ABS graph contains at least 14 node types for ingested deal | ✅ |
| LLM generates syntactically valid Python payment model | ✅ |
| LLM answers ABS domain question with citations | ✅ |
| Governing doc generator produces complete document | ✅ |
| All 32 LLM call sites wired and testable | ✅ |
| Template fallback works when LLM unavailable | ✅ |
| All KTS + Phase 21 tests still pass (zero regression) | ✅ |
