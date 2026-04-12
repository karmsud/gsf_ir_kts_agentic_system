# RAG Model Usage Setup — Post-Phase 15 State

**Document Version**: 1.0  
**Date**: February 19, 2026  
**System Version**: v0.0.16  
**Purpose**: Baseline documentation of LLM model allocation across the RAG pipeline after Phase 15 completion

---

## Executive Summary

After Phase 15, the KTS RAG system uses LLMs in **5 distinct components**, with different cost profiles and configurability:

| Component | Default Model | Cost Tier | User Control | Default State |
|---|---|---|---|---|
| Critique Questions | `gpt-4.1` → `gpt-4o` → `gpt-4o-mini` | **FREE** (cheap chain) | ❌ No | ✅ Enabled |
| Multi-Query Expansion | User's selected model | **PREMIUM** | ✅ Yes | ✅ Enabled |
| Final Answer Generation | User's selected model | **PREMIUM** | ✅ Yes | ✅ Always on |
| Self-RAG Synthesis | User's selected model | **PREMIUM** | ✅ Yes | ❌ Disabled |
| Self-RAG Gap Detection | User's selected model | **PREMIUM** | ✅ Yes | ❌ Disabled |

**Key Insight**: Only critique generation uses a hardcoded cheap model. All user-facing generation (multi-query, answer synthesis, Self-RAG) respects the user's model selection, meaning **premium model choice → premium token costs**.

**Design Goal**: Build RAG pipeline so robust that even free/cheap models produce satisfactory results through superior retrieval and context engineering.

---

## Component Breakdown

### 1. Critique Questions Generation (Phase 9.2)

**Function**: Generate document-specific binary critique questions during ingestion  
**When Executed**: Ingestion time only (not per query)  
**Token Cost**: ~500-1000 tokens per document

**Model Selection Logic**:
```javascript
// extension/lib/critique_client.js:23
const preferred = ['gpt-4.1', 'gpt-4o', 'gpt-4o-mini'];
```

**Fallback Chain**:
1. Try `gpt-4.1` (latest cheap model)
2. Try `gpt-4o` (mid-tier model)
3. Try `gpt-4o-mini` (cheapest model)
4. Try any available Copilot model
5. Fail gracefully if none available

**Configuration**:
- Backend config: `critique_generation_enabled` (default: `True`)
- Code: [backend/agents/ingestion_agent.py:610](../../backend/agents/ingestion_agent.py#L610)

**Status**: ✅ **Enabled by default**

---

### 2. Multi-Query Expansion (Phase 8.6)

**Function**: Generate 4 semantic variants of user query for RAG fusion  
**When Executed**: Every query (before retrieval)  
**Token Cost**: ~400 tokens per query (prompt + 4 variants)

**Model Selection**:
```javascript
// extension/chat/participant.js:1297
const expansionModel = await selectChatModel(vscode, request.model);
```
Uses **whatever model the user selected** in the VS Code chat model picker (GPT-4o, Claude Sonnet, etc.)

**Prompt Template**:
```
Given this legal/financial query, generate 4 semantically different rephrasings 
that would help retrieve complementary relevant sections. 
Return ONLY a JSON array of strings, no explanation.

Query: "{user_query}"
```

**Configuration**:
- Setting: `kts.multiQueryEnabled` (default: `true`)
- Code: [extension/chat/participant.js:1289-1295](../../extension/chat/participant.js#L1289-L1295)

**Status**: ✅ **Enabled by default**

**Impact**: If user selects Claude Opus or GPT-4, generation happens with that premium model.

---

### 3. Final Answer Generation (Phase 11.5)

**Function**: Synthesize final answer from retrieved context  
**When Executed**: Every query (after retrieval)  
**Token Cost**: 1K-8K tokens depending on context size (typically 2-4K)

**Model Selection**:
```javascript
// extension/chat/participant.js:1362
const model = await selectChatModel(vscode, preferredModel);
```

**Override Hierarchy**:
1. `kts.generationModel` setting (e.g., `"gpt-4o"`)
2. User's selected model in chat picker
3. Fallback to any available Copilot model

**Prompt Engineering**:
- Mode detection: `legal` vs `kts` based on `doc_type` majority vote
- Legal mode: Formal legal analyst with strict citation requirements
- KTS mode: Support engineer with conversational tone
- Token-aware context trimming (Phase 8.3)
- Temporal context injection (Phase 14.2)
- Cached term definitions (Phase 14.1)

**Configuration**:
- Setting: `kts.generationModel` (default: `"auto"`)
- Package.json: [extension/package.json:99-103](../../extension/package.json#L99-L103)

**Status**: ✅ **Always enabled** (core RAG functionality)

**Code References**:
- Model selection: [extension/chat/participant.js:275-301](../../extension/chat/participant.js#L275-L301)
- Generation function: [extension/chat/participant.js:455-550](../../extension/chat/participant.js#L455-L550)
- Prompt selection: [extension/chat/participant.js:1362-1367](../../extension/chat/participant.js#L1362-L1367)

---

### 4. Self-RAG Synthesis (Phase 8.8)

**Function**: Iterative answer refinement with gap-driven re-retrieval  
**When Executed**: Optionally after initial generation (if enabled)  
**Token Cost**: 2K-10K tokens per round × 1-3 rounds

**Model Selection**: Uses the **same model as final generation** (component #3)

**Process Flow**:
1. Generate initial answer
2. Evaluate answer for gaps/uncertainties
3. Generate focused sub-queries for missing information
4. Retrieve additional context
5. Re-synthesize answer with expanded context
6. Repeat up to 3 rounds or until no gaps detected

**Configuration**:
- Setting: `kts.selfRagEnabled` (default: `false`)
- Code: [extension/chat/participant.js:1372-1379](../../extension/chat/participant.js#L1372-L1379)

**Status**: ❌ **Disabled by default** (opt-in feature)

**Why Disabled**: High token cost, experimental feature. Requires explicit user opt-in.

---

### 5. Self-RAG Gap Detection (Phase 8.8)

**Function**: Identify knowledge gaps and generate sub-queries  
**When Executed**: Part of Self-RAG iterative loop (when enabled)  
**Token Cost**: Included in component #4 (integrated with synthesis)

**Model Selection**: Uses the **same model as Self-RAG synthesis** (component #4)

**Gap Detection Prompt**:
```
Review this answer and identify 2-3 specific gaps or uncertainties 
that need additional information. For each gap, formulate a precise 
sub-query to retrieve the missing information.
```

**Configuration**: Controlled by `kts.selfRagEnabled` (same as component #4)

**Status**: ❌ **Disabled by default** (part of Self-RAG feature)

**Code**: [extension/lib/self_rag.js](../../extension/lib/self_rag.js) — `generateIteratively()`

---

## Configuration Matrix

### Configuration Options (User-Facing)

| Setting | Type | Default | Location | Impact |
|---|---|---|---|---|
| `kts.generationModel` | string | `"auto"` | package.json | Overrides model for components 3-5 |
| `kts.multiQueryEnabled` | boolean | `true` | In-code only | Enables/disables component 2 |
| `kts.selfRagEnabled` | boolean | `false` | In-code only | Enables/disables components 4-5 |
| `critique_generation_enabled` | boolean | `True` | Backend config | Enables/disables component 1 |

### Hidden Settings (Not Exposed in UI)

**Multi-Query Expansion**:
- Controlled programmatically via `cfg.get('multiQueryEnabled', true)`
- No UI setting in package.json
- Default: **Enabled**

**Self-RAG**:
- Controlled programmatically via `cfg.get('selfRagEnabled', false)`
- No UI setting in package.json
- Default: **Disabled**

---

## Token Cost Analysis

### Per-Query Cost Breakdown (Default Configuration)

| Scenario | Components Active | Model | Est. Tokens | Cost (GPT-4o) | Cost (Claude Opus) |
|---|---|---|---|---|---|
| **Basic Query** | 2 + 3 | User's choice | 2.4K-8.4K | $0.01-$0.04 | $0.02-$0.08 |
| **Self-RAG (3 rounds)** | 2 + 3 + 4 + 5 | User's choice | 10K-30K | $0.05-$0.15 | $0.10-$0.30 |

**Basic Query Cost**:
- Multi-query expansion: 400 tokens
- Final generation: 2K-8K tokens (depends on context size)

**Self-RAG Cost**:
- Initial generation: 2K-8K tokens
- Round 1: Gap detection (500) + retrieval (0) + synthesis (2K-5K)
- Round 2: Gap detection (500) + retrieval (0) + synthesis (2K-5K)
- Round 3: Gap detection (500) + retrieval (0) + synthesis (2K-5K)

**Ingestion Cost** (Per Document):
- Critique questions: 500-1K tokens (cheap model)
- Cost: $0.0005-$0.001 per document (gpt-4o-mini)

---

## Model Family Preferences

### User-Selectable Models (Components 2-5)

The system attempts to respect user's model choice through this resolution chain:

```javascript
// extension/chat/participant.js:275-296
async function selectChatModel(vscode, requestModel) {
  // 1. Try user's requested model from chat picker
  if (requestModel && requestModel.family) {
    const models = await vscode.lm.selectChatModels({ 
      vendor: 'copilot', 
      family: requestModel.family 
    });
    if (models.length > 0) return models[0];
  }
  
  // 2. Fallback: any available copilot model
  const models = await vscode.lm.selectChatModels({ vendor: 'copilot' });
  return models.length > 0 ? models[0] : null;
}
```

**Supported Families**:
- `gpt-4o` (OpenAI GPT-4o)
- `gpt-4.1` (OpenAI GPT-4.1)
- `gpt-4o-mini` (OpenAI GPT-4o-mini)
- `claude-3.5-sonnet` (Anthropic Claude 3.5 Sonnet)
- `claude-3-5-sonnet` (Anthropic Claude 3.5 Sonnet alternate)
- `claude-opus-4.5` (Anthropic Claude Opus 4.5, if available)
- Any other Copilot-available model

---

## Retrieval Pipeline (No LLM Usage)

The following components **do NOT use LLMs** (pure vector/graph operations):

| Component | Method | Cost |
|---|---|---|
| Embedding Generation | BGE ONNX INT8 (local) | Free |
| Vector Search | ChromaDB similarity | Free |
| Graph Traversal | NetworkX (Phase 6) | Free |
| Cross-Encoder Reranking | ONNX cross-encoder | Free |
| Evidence Matching | Regex + spaCy NER | Free |
| Scope Routing | FTS5 SQLite | Free |
| Confidence Scoring | Rule-based heuristics | Free |
| Gap Detection (Phase 13) | Keyword matching | Free |
| Freshness Tagging | Date parsing | Free |

**Phase 6 GraphRAG** (when enabled):
- Iterative multi-hop retrieval
- Item extraction from graph
- Dual vector store fusion
- **NO LLM calls** — pure graph traversal + vector operations

---

## Design Philosophy: Model-Agnostic RAG

### Current State (Phase 15)

**Token Dependency**: 4 of 5 LLM components use user's selected model
- Multi-query expansion: User's model
- Final generation: User's model
- Self-RAG: User's model (if enabled)
- Only critique uses hardcoded cheap model

**Cost Sensitivity**: Premium model selection → 3-20× higher token costs

### Target State (Post-Phase 15 Optimization)

**Goal**: Build RAG so robust that **free models produce 90%+ quality of premium models**

**Strategy**:
1. **Superior Retrieval** → Reduce generation burden
   - Phase 6 multi-hop graph traversal
   - RRF fusion of multi-query variants
   - Cross-encoder precision reranking
   - Evidence header markup (Phase 8.5)

2. **Context Engineering** → Maximize signal density
   - Token-aware trimming (Phase 8.3)
   - Parent-child chunk expansion (Phase 13.3)
   - Temporal context injection (Phase 14.2)
   - Cached term definitions (Phase 14.1)

3. **Prompt Optimization** → Reduce hallucination
   - Doc-type aware prompt selection
   - Strict citation templates
   - Confidence tier guidance
   - Gap-aware instructions

4. **Critique Loop** → Quality assurance without premium models
   - Document-specific critique questions (cheap model)
   - Binary verification prompts
   - Automated fact-checking

**Success Metric**: `gpt-4o-mini` produces answers indistinguishable from `gpt-4o` or `claude-opus` due to superior context quality and prompt engineering.

---

## Testing Strategy: Model Comparison

### Controlled Experiments

To validate model-agnostic design, run identical queries across model tiers:

**Test Matrix**:
| Model Tier | Model | Cost/1M Tokens | Expected Quality |
|---|---|---|---|
| **Premium** | Claude Opus 4.5 | $60 | Baseline (100%) |
| **Mid-Tier** | GPT-4o | $5 | Target: 95%+ of baseline |
| **Budget** | GPT-4o-mini | $0.60 | Target: 90%+ of baseline |
| **Free** | GPT-4.1 (if available) | Free | Target: 85%+ of baseline |

**Evaluation Dimensions**:
1. **Accuracy**: Correctness of answer
2. **Citation Quality**: Relevance and precision of sources
3. **Completeness**: Coverage of query intent
4. **Hallucination Rate**: Fabricated information
5. **Tone**: Appropriate formality for doc_type

**Example Query Set**:
- Simple fact lookup: "What is the trustee's address?"
- Complex reasoning: "Compare servicer duties in Sections 3 and 7"
- Multi-document: "How does this PSA differ from industry standard?"
- Temporal: "What changed in the 2006 amendment?"
- Definition: "Define 'Eligible Receivables' as used in this deal"

---

## Current Feature State Summary

| Feature | Component ID | Default State | User Override | LLM Used |
|---|---|---|---|---|
| Critique Generation | 1 | ✅ Enabled | ❌ No | gpt-4.1/4o/4o-mini (cheap) |
| Multi-Query Expansion | 2 | ✅ Enabled | ✅ Yes | User's model |
| Answer Generation | 3 | ✅ Enabled | ✅ Yes | User's model |
| Self-RAG Synthesis | 4 | ❌ Disabled | ✅ Yes | User's model |
| Self-RAG Gap Detection | 5 | ❌ Disabled | ✅ Yes | User's model |
| Phase 6 GraphRAG | N/A | ❌ Disabled | ✅ Yes | None (no LLM) |

**Critical Observation**: Phase 6 (hierarchical GraphRAG) is **disabled by default** (`kts.phase6Enabled: false`). This is the most sophisticated retrieval component and should be evaluated for default enablement in Phase 16+.

---

## Phase 16+ Recommendations

### 1. Model Cost Optimization
- [ ] Add `kts.expansionModel` setting to use cheap model for multi-query
- [ ] Implement parallel generation with model comparison (premium vs free)
- [ ] Add token budget controls per component

### 2. Configuration Exposure
- [ ] Expose `multiQueryEnabled` in package.json settings UI
- [ ] Expose `selfRagEnabled` in package.json settings UI
- [ ] Add cost estimation UI before enabling Self-RAG

### 3. Retrieval Enhancement (Reduce LLM Dependency)
- [ ] Enable Phase 6 by default after validation
- [ ] Add query classification to skip LLM for simple lookups
- [ ] Implement caching of multi-query variants for common patterns

### 4. Model-Agnostic Design Validation
- [ ] Run controlled experiments (premium vs free models)
- [ ] Establish quality baselines for each model tier
- [ ] Measure hallucination rates across models
- [ ] Optimize prompts to minimize model-dependent quality variance

### 5. Monitoring & Analytics
- [ ] Add token usage tracking per component
- [ ] Log model family used for each query
- [ ] Track cost per query by model tier
- [ ] Alert when token costs exceed thresholds

---

## Code References

### LLM Integration Points

| Component | File | Lines | Function |
|---|---|---|---|
| Critique Model Selection | `extension/lib/critique_client.js` | 16-45 | `selectCritiqueModel()` |
| Multi-Query Expansion | `extension/lib/query_expander.js` | 18-44 | `expandQueryWithLLM()` |
| Multi-Query Invocation | `extension/chat/participant.js` | 1286-1310 | Inline in handler |
| Generation Model Selection | `extension/chat/participant.js` | 275-301 | `selectChatModel()` |
| Answer Generation | `extension/chat/participant.js` | 455-550 | `generateAnswer()` |
| Self-RAG Loop | `extension/lib/self_rag.js` | Full file | `generateIteratively()` |
| Critique Backend | `backend/agents/critique_question_generator.py` | Full file | `CritiqueQuestionGenerator` |
| Ingestion Critique Call | `backend/agents/ingestion_agent.py` | 605-625 | Phase 9.2 block |

### Configuration Files

| Setting | File | Line |
|---|---|---|
| `kts.generationModel` | `extension/package.json` | 99-103 |
| `kts.phase6Enabled` | `extension/package.json` | 73-77 |
| `multiQueryEnabled` | `extension/chat/participant.js` | 1292 (in-code) |
| `selfRagEnabled` | `extension/chat/participant.js` | 1375 (in-code) |
| `critique_generation_enabled` | `backend/agents/ingestion_agent.py` | 610 (in-code) |

---

## Revision History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | 2026-02-19 | System | Initial documentation post-Phase 15 |

---

## Appendix: Token Budget Calculations

### Context Window Allocation

**Input Token Budget** (per model):
```
GPT-4o:          128K context → reserve 120K for input
Claude Opus:     200K context → reserve 190K for input
GPT-4o-mini:     128K context → reserve 120K for input
```

**Typical RAG Payload**:
```
System Prompt:          500 tokens
Temporal Context:       100 tokens
Cached Terms:          200 tokens
Retrieved Context:    2000-6000 tokens (trimmed)
User Query:            50-200 tokens
---
Total Input:          2850-6900 tokens
```

**Output Budget**:
```
Answer:               500-2000 tokens
Citations:            200-500 tokens
---
Total Output:         700-2500 tokens
```

**Per-Query Total**: 3.5K-9.5K tokens (well within all model limits)

---

*End of Document*
