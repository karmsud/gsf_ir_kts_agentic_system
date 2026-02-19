# Phase 10: Conversation Memory & Session Intelligence — Architecture Document

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Architectural Principles

| Decision | Rationale |
|----------|-----------|
| **VS Code is the session store** | `context.history` is managed by VS Code. We read it, we do not replicate it. No Redis, no SQLite, no session DB. |
| **History extracted in extension, not backend** | The extension is closest to VS Code's session lifecycle. Backend is stateless by design. |
| **Query rewriting before retrieval, always** | Retrieval quality depends on query quality. Rewriting is the highest-leverage single intervention. |
| **Signal-gated rewriting** | Don't pay LLM cost on unambiguous standalone queries. Heuristic detection before LLM call. |
| **Document bias, never document filter** | Boost in-context documents, but never exclude new ones. Prevents the session from becoming a closed loop. |
| **Lazy summarization** | Summarize only when verbatim history budget is exhausted. No background threads. |
| **session_id from extension** | Extension generates a UUID on first turn per VS Code window. Trivially unique, no server-side session management. |

---

## 2. Layer Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   VS CODE CHAT API                        │
│   context.history  ← MANAGED BY VS CODE, FREE            │
│   context.references ← #file, #selection (Phase 11)      │
├──────────────────────────────────────────────────────────┤
│              PRESENTATION LAYER (participant.js)          │
│   + buildConversationContext()      NEW 10.1              │
│   + compress history to token budget NEW 10.4             │
│   + generate session_id             NEW 10.1              │
│   POST /query { query, conversation_context, session_id } │
├──────────────────────────────────────────────────────────┤
│              ★ CONVERSATION LAYER (NEW Phase 10)         │
│   backend/retrieval/query_rewriter.py     NEW 10.2        │
│   • Coreference signal detection                          │
│   • LLM-based standalone query generation                 │
│   • Fallback to original on failure                       │
│                                                           │
│   backend/retrieval/session_memory.py     NEW 10.3        │
│   • In-process session dict (session_id keyed)            │
│   • resolved_terms, active_documents, active_sections     │
│   • TTL: 4 hours since last access                        │
│   • Document bias application                             │
├──────────────────────────────────────────────────────────┤
│              ORCHESTRATION LAYER                          │
│   backend/agents/retrieval_service.py   MODIFIED 10.1     │
│   • Accept conversation_context, session_id in request    │
│   • Pass rewritten query downstream                       │
│   • Update session memory after retrieval                 │
├──────────────────────────────────────────────────────────┤
│              RETRIEVAL / CRITIQUE LAYERS                  │
│   (Phase 8, 9 — unchanged)                               │
└──────────────────────────────────────────────────────────┘
```

---

## 3. Data Flow

### Turn 1 (Cold Start)
```
User: "What is the Determination Date?"
  → history = []
  → session_id = newly generated UUID
  → query_rewriter: no-op (empty history)
  → retrieval: cold global search
  → session_memory: store { "Determination Date": answer_snippet, active_docs: [PSA.doc] }
  → response returned
```

### Turn 2 (Coreference)
```
User: "And what happens if it falls on a weekend?"
  → history = [Turn 1 user+assistant]
  → query_rewriter detects "it" → calls LLM
  → rewritten: "What happens if the Determination Date falls on a non-business day?"
  → retrieval: biased toward PSA.doc (15% boost, already in session)
  → session_memory: update active_sections
  → response returned
```

### Turn 8 (Summarization activates)
```
  → turns 1-4: move to rolling_summary (200 word LLM compression)
  → turns 5-8: verbatim in context
  → total context: ~1100 tokens regardless of session length
```

---

## 4. Session Memory Lifecycle

```
VS Code window opens
    → session_id generated (UUID v4)
    → SessionMemory created (empty)
    
Each query turn:
    → Retrieve from session_memory by session_id
    → Apply document bias to retrieval results
    → Update resolved_terms, active_documents from returned chunks
    
TTL expiry (4h inactivity):
    → SessionMemory evicted from in-process dict
    → Next query starts fresh (graceful, no error)
    
VS Code window closes:
    → session_id abandoned
    → Memory evicted on next TTL pass
```

---

## 5. Rollout & Rollback

| Flag | Default | Effect |
|------|---------|--------|
| `enable_query_rewriting` | `true` | Enables coreference resolution |
| `enable_session_memory` | `true` | Enables document bias and entity tracking |
| `enable_history_summarization` | `true` | Enables rolling summary buffer |
| `history_max_turns` | `10` | Max turns sent to backend |
| `session_memory_ttl_hours` | `4` | TTL for in-process session cache |

All flags default `true`. Setting any to `false` degrades gracefully — behavior reverts to v0.0.12.
