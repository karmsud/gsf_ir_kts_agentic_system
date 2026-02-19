# Phase 14: Structured Deal Intelligence Layer — Architecture Document

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Architectural Principles

| Decision | Rationale |
|----------|-----------|
| **Session summary is progressive, not upfront** | Computing a full deal summary upfront costs N LLM calls and delays the first answer. Build it incrementally per query at zero marginal cost. |
| **Cache-first, vector-second** | Before any similarity search, check session cache. Resolved terms are retrieved instantly and with 100% recall. |
| **current_date is a system variable, not a tool** | The LLM does temporal reasoning natively. Inject the date; don't build a calendar engine. |
| **Extraction output is JSON, not prose** | /extract mode enforces a JSON schema at the prompt level. No post-processing parser needed — LLM directly fills the schema. |
| **Session summary lives in SessionMemory** | No new data structure. Extend Phase 10's SessionMemory with DealSummary fields. Same lifecycle, same TTL. |

---

## 2. Layer Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                   SESSION INTELLIGENCE LAYER                  │
│   (Extension of Phase 10 SessionMemory)                       │
│                                                               │
│   backend/retrieval/session_memory.py   MODIFIED 14.1        │
│   + DealSummary embedded in SessionMemory                     │
│   + cache_first_retrieval()                                   │
│   + update_summary_from_answer()                              │
├──────────────────────────────────────────────────────────────┤
│                   TEMPORAL REASONING LAYER                    │
│   backend/retrieval/temporal_reasoner.py   NEW 14.2          │
│   • Inject current_date into all prompt templates             │
│   • Detect temporal query signals                             │
│   • Add temporal evaluation instruction to prompts            │
├──────────────────────────────────────────────────────────────┤
│                   STRUCTURED OUTPUT LAYER                     │
│   backend/retrieval/extraction_mode.py    NEW 14.3           │
│   • JSON schema definition                                    │
│   • Prompt with explicit schema enforcement                   │
│   • extraction_gaps computation                               │
│                                                               │
│   backend/retrieval/summary_mode.py       NEW 14.4           │
│   • 5-section fixed template                                  │
│   • Temporal status column in dates table                     │
│   • Confidence and source citation footer                     │
├──────────────────────────────────────────────────────────────┤
│                   PRESENTATION LAYER                          │
│   extension/chat/participant.js          MODIFIED            │
│   • Render JSON extraction as formatted table or code block   │
│   • Render temporal status badges (✅ Passed, ⏳ Pending)     │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Session Deal Summary — Data Flow

```
Turn 1                          Turn 5                          Turn 10
  │                               │                               │
Query: "What is                Query: "Who is                 Query: "List all
  Determination Date?"           the Trustee?"                  key deal dates"
  │                               │                               │
Cache: empty → vector search    Cache: D.Date found ✓          Cache: D.Date ✓
  │                               │      → vector for Trustee     │      Trustee ✓
Retrieved: D.Date definition    │                               │      → vector only for
  │                               Retrieved: Trustee = Deutsche   │        remaining dates
Update cache:                   │                               │
  defined_terms["Determination  Update cache:                  Cache hit:  ~50%
   Date"] = "25th of month..."    parties["Trustee"] = "Deutsche" No retrieval cost for
                                                                  cached terms
```

---

## 4. Temporal Prompt Injection

```python
# Every prompt receives:
system_context = f"""
Today's date is {datetime.now().strftime('%B %d, %Y')}.

When the user's question involves dates, periods, or time-dependent conditions:
- Evaluate whether referenced dates are past or future relative to today
- State explicitly if a date has passed or how much time remains
- If a condition is date-gated, evaluate whether it is currently active
- Do not hedge — if you can compute it, compute it
"""
```

This one injection transforms every date-related answer from a passive lookup to an active evaluation.

---

## 5. Extraction JSON Schema Enforcement

```python
EXTRACTION_SCHEMA_PROMPT = """
Extract all available information from the provided document context and fill 
the following JSON schema. Use null for fields not found. Do not invent data.

Schema:
{schema_json}

For extraction_gaps: list field names where you searched but found no answer.

Return ONLY the JSON object. No preamble, no explanation.
"""
```

The JSON schema is defined once in `extraction_mode.py` and included verbatim in the prompt. LLM output is parsed with `json.loads()`. If parsing fails, the raw response is returned with a parse error flag — never a crash.
