# Phase 10: Conversation Memory & Session Intelligence — Implementation Plan

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Motivation — The History Is Already There

### 1.1 The Gap We Are Closing

Every call to the KTS chat participant handler receives `context.history` — a fully typed array of every prior user message and assistant response in the current VS Code session. VS Code manages session lifetime, persists history across requests, and handles all rendering. As of v0.0.12, `participant.js` discards this object entirely before calling the backend. The system treats every question as a cold start.

This is a correctness problem, not just a UX convenience. Consider:

| Turn | User Message | What KTS Returns Today | What KTS Should Return |
|------|-------------|----------------------|----------------------|
| 1 | "What is the Determination Date?" | Correct answer | Correct answer |
| 2 | "And what happens if it falls on a weekend?" | Retrieves nothing (no noun) | Rewrites to "What happens if the Determination Date falls on a weekend?" then retrieves |
| 3 | "What about the Closing Date — same rule?" | Retrieves random Closing Date chunks | Understands "same rule" = non-business-day treatment, queries that angle specifically |
| 4 | "So which comes first?" | Has no idea what "which" refers to | Knows it means Determination Date vs Closing Date order |

Turn 2, 3, and 4 are **not answerable without history**. They produce either silent retrieval failures or hallucinated answers today. They happen constantly in real legal review sessions where users drill down progressively.

### 1.2 What "Session Intelligence" Means

Four distinct capabilities, implemented in order of dependency:

1. **Query Rewriting** — resolve coreferences ("it", "same rule", "which") before the query touches the retriever
2. **Entity Session Memory** — track which defined terms, documents, and sections have been resolved this session
3. **Document Bias** — bias retrieval toward documents already in context rather than cold global search
4. **History Summarization** — compress old turns into a rolling summary so LLM context window stays manageable

### 1.3 Academic Grounding

| Technique | Source | Relevance |
|-----------|--------|-----------|
| **Conversational QA** | QuAC (Choi et al. 2018), CoQA (Reddy et al. 2019) | Show 40%+ accuracy degradation on follow-up Qs without history |
| **Query Rewriting for Conversational RAG** | Vakulenko et al. 2021 | Standalone query generation from conversational context |
| **ConvDR** | Yu et al. 2021 | Dense conversational retrieval — history as decontextualization signal |
| **Summary Buffer Memory** | LangChain design | Keep last N verbatim + rolling LLM summary of older turns |
| **RAG with Memory** | LlamaIndex production pattern | Session-scoped entity extraction + retrieval bias |

---

## 2. Implementation Philosophy

> *"VS Code is the session store. We consume what it already gives us — we do not build a new session layer."*

**Design constraints:**
- History extraction happens entirely in `participant.js` (extension side) — zero new backend infrastructure
- History is compressed before transit (token budget enforced in extension, not backend)
- Backend receives a `conversation_context` field alongside `query` — existing backends ignore it gracefully (backward compatible)
- Query rewriting uses the **same LLM** the user already has selected — no second model required for this phase
- History summarization is triggered lazily (only when turn count exceeds threshold) — no latency cost on early turns

---

## 3. Implementation Order

Four increments, strict dependencies:

| Order | Increment | Impact | Risk | Rationale |
|-------|-----------|--------|------|-----------|
| **10.1** | History extraction + transit (participant.js → backend) | HIGH | LOW | Plumbing only. No behavior change yet. Validates the pipe before building on it. |
| **10.2** | Query rewriting via coreference resolution | VERY HIGH | LOW | Single LLM call before retrieval. Immediately fixes follow-up question failures. |
| **10.3** | Entity session memory + document bias | HIGH | MEDIUM | Track resolved entities. Bias retriever toward in-context documents. |
| **10.4** | History summarization (rolling summary buffer) | MEDIUM | LOW | Lazy compression of old turns. Prevents context window overflow on long sessions. |

---

## 4. Increment 10.1 — History Extraction & Transit

### 4.1 What Changes

**`extension/chat/participant.js`** — extract and serialize `context.history` before calling backend:

```javascript
// Extract last N turns from VS Code history
function buildConversationContext(context, maxTurns = 10) {
    const turns = [];
    const history = context.history || [];
    const recent = history.slice(-maxTurns);
    
    for (const turn of recent) {
        if (turn instanceof vscode.ChatRequestTurn) {
            turns.push({ role: 'user', content: turn.prompt });
        } else if (turn instanceof vscode.ChatResponseTurn) {
            // Collect text fragments from response parts
            const text = turn.response
                .filter(p => p instanceof vscode.ChatResponseMarkdownPart)
                .map(p => p.value.value)
                .join('');
            turns.push({ role: 'assistant', content: text.slice(0, 500) }); // truncated
        }
    }
    return turns;
}
```

**`backend/agents/retrieval_service.py`** — accept and log `conversation_context` in request schema (no behavior change yet):

```python
class QueryRequest(BaseModel):
    query: str
    source_path: str
    conversation_context: list[dict] = []  # new, optional, backward compatible
    scope: str | None = None               # for Phase 12
```

### 4.2 Validation

- History object is received and logged by backend on every multi-turn session
- Backend still returns identical results (no behavior change)
- Token count of serialized history stays under 2000 tokens

---

## 5. Increment 10.2 — Query Rewriting via Coreference Resolution

### 5.1 What Changes

**`backend/retrieval/query_rewriter.py`** (new file):

```python
REWRITE_PROMPT = """
You are helping a legal document retrieval system.
Given a conversation history and a new question, rewrite the question as a
fully self-contained, specific query that can be answered without any context
from the conversation history. Resolve all pronouns and references.

If the question is already standalone, return it unchanged.
Return ONLY the rewritten query, no explanation.

Conversation history:
{history}

New question: {query}

Standalone query:
"""

async def rewrite_query(query: str, history: list[dict]) -> str:
    if not history:
        return query  # fast path on first turn
    
    # Only rewrite if coreference signals are present
    coreference_signals = ['it', 'this', 'that', 'they', 'same', 'which',
                           'those', 'both', 'either', 'the above', 'the same']
    query_lower = query.lower()
    needs_rewrite = any(sig in query_lower for sig in coreference_signals)
    
    if not needs_rewrite and len(query.split()) > 8:
        return query  # long specific query — skip rewrite cost
    
    prompt = REWRITE_PROMPT.format(
        history=format_history(history[-6:]),  # last 3 turns
        query=query
    )
    rewritten = await call_llm(prompt, max_tokens=150)
    return rewritten.strip()
```

### 5.2 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Signal-gated rewrite | Only call LLM if coreference signals present — skips ~60% of queries, saves latency |
| Last 6 turns only | Coreferences resolve within 2-3 turns in practice — full history is noise |
| Max 150 output tokens | Query rewriting never needs a long output |
| Fallback to original | If rewrite LLM fails, original query passes through unchanged |

### 5.3 Validation

Before/after test pairs (from real session failures):

| Input Query | History | Expected Rewrite |
|-------------|---------|-----------------|
| "And what happens if it falls on a weekend?" | User asked about Determination Date | "What happens if the Determination Date falls on a non-business day?" |
| "What about the Closing Date — same rule?" | Discussed non-business-day treatment | "Does the non-business-day treatment apply to the Closing Date as well?" |
| "So which comes first?" | Discussed Determination Date and Closing Date | "Does the Determination Date or the Closing Date occur first in the deal timeline?" |
| "Who is responsible for that?" | Discussed Servicer Advance obligation | "Who is responsible for making Servicer Advances?" |

---

## 6. Increment 10.3 — Entity Session Memory & Document Bias

### 6.1 Session Memory Model

**`backend/retrieval/session_memory.py`** (new file):

Session memory is a lightweight in-process dict keyed by `session_id`. Each session stores:

```python
@dataclass
class SessionMemory:
    session_id: str
    resolved_terms: dict[str, str]     # term → answer snippet
    active_documents: list[str]         # doc paths seen this session
    active_sections: list[str]          # section IDs retrieved this session
    turn_count: int
    created_at: datetime
    last_accessed: datetime
```

`session_id` is generated by the extension on first turn and passed with every request (a UUID stored in extension memory for the VS Code window lifetime).

### 6.2 Document Bias

When retrieving, if `session_memory.active_documents` is non-empty, apply a **score boost** to chunks from those documents:

```python
def apply_document_bias(results: list[Chunk], session_memory: SessionMemory) -> list[Chunk]:
    for chunk in results:
        if chunk.source_doc in session_memory.active_documents:
            chunk.biased_score = chunk.score * 1.15  # 15% boost
        else:
            chunk.biased_score = chunk.score
    return sorted(results, key=lambda c: c.biased_score, reverse=True)
```

This is conservative — a 15% boost, never filtering. New documents can still appear if they score well.

---

## 7. Increment 10.4 — History Summarization

### 7.1 Summary Buffer Pattern

Maintain two components in session memory:

```
[verbatim_recent_turns]    ← last 4 turns, full text
[rolling_summary]          ← LLM-compressed summary of all older turns
```

When turn count exceeds 4, compress oldest 2 turns into rolling summary. The summary prompt:

```python
SUMMARY_PROMPT = """
You are maintaining a compact memory of a legal document Q&A session.

Existing summary: {existing_summary}
New turns to incorporate:
{new_turns}

Update the summary to include key facts established, defined terms resolved,
and documents discussed. Be concise — max 200 words. Preserve all specific
values (dates, amounts, party names). Return only the updated summary.
"""
```

### 7.2 Token Budget Enforcement

Total context sent to backend per query:

| Component | Max Tokens |
|-----------|-----------|
| Rolling summary | 200 |
| Verbatim recent turns (4) | 800 |
| Current query | 100 |
| **Total conversation context** | **~1100** |

This is fixed overhead regardless of session length. No context window risk.

---

## 8. Files Changed

| File | Change Type | Phase |
|------|------------|-------|
| `extension/chat/participant.js` | Modified | 10.1, 10.2, 10.3 |
| `backend/agents/retrieval_service.py` | Modified | 10.1 |
| `backend/retrieval/query_rewriter.py` | New | 10.2 |
| `backend/retrieval/session_memory.py` | New | 10.3 |
| `config/settings.py` | Modified | 10.4 |

---

## 9. Success Metrics

| Metric | Baseline (v0.0.12) | Target (Phase 10) |
|--------|-------------------|------------------|
| Follow-up question recall | ~30% | >85% |
| Coreference resolution accuracy | 0% | >90% |
| Session memory hit rate (turn 3+) | 0% | >60% |
| Context window overflow incidents | N/A | 0 |
| Latency increase (median) | 0ms | <300ms |
