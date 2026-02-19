# Phase 14: Structured Deal Intelligence Layer — Implementation Plan

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Motivation — From Question-Answering to Deal Intelligence

### 1.1 The Step Change

Phases 1-13 build a progressively better **retrieval and answer system**. Every query-answer pair is independent. The system has no persistent model of the deal it is analyzing. It answers questions; it does not understand deals.

Phase 14 introduces a fundamentally different operating mode: **deal intelligence**. Three capabilities distinguish it:

1. **Structured Extraction**: The system can produce machine-readable JSON of all key deal data points — not prose, not markdown, structured data that feeds downstream systems (Excel, databases, report generators, comparison engines)
2. **Session Deal Summary**: On first query about a document, silently construct and cache a deal data model for the VS Code session. Subsequent queries check this cache before touching the vector store. Guaranteed recall on resolved terms.
3. **Temporal Reasoning**: The system knows what date it is. It can tell you whether a deal date has passed, how many days until a distribution date, whether an optional termination window is open.

### 1.2 Why Temporal Reasoning Matters Dramatically

Consider this gap in every answer KTS currently provides:

> User: "Has the Optional Termination date passed for this deal?"  
> KTS today: "The Optional Termination Date is [date]."  
> KTS Phase 14: "The Optional Termination Date is March 15, 2023. **As of today (February 18, 2026), this date has passed — the Optional Termination window has expired.**"

The first answer requires the user to do mental arithmetic and know the current date. The second answer is a complete intelligent response. The difference is injecting `current_date` into the prompt — literally one variable. The reasoning is done by the LLM. No calculation engine needed.

### 1.3 The Session Deal Summary — The "Always Available" Context

Every defined term lookup via vector search has some probability of failure (wrong chunk, score below threshold, vocabulary mismatch). The session deal summary eliminates this failure mode for terms already resolved:

```
Turn 1: User asks about Determination Date
  → Vector search finds it (score 0.94)
  → Answer returned
  → Session summary updated: {"Determination Date": "25th of month, or prior Business Day"}

Turn 7: User asks a compound question referencing Determination Date
  → Session summary check: Determination Date already resolved ✓
  → No vector search needed for this term
  → Answer constructed from summary + any new retrieval
  → Guaranteed correct recall on previously resolved terms
```

This is perfect recall on session-resolved terms, regardless of retrieval noise. Zero probability of forgetting what was already found.

---

## 2. Implementation Order

| Order | Increment | Impact | Risk | Rationale |
|-------|-----------|--------|------|-----------|
| **14.1** | Session deal summary cache | VERY HIGH | LOW | In-memory dict, session-scoped. No persistence needed. Immediate trust improvement. |
| **14.2** | Temporal reasoning injection | HIGH | LOW | Inject current_date into prompts. Pattern-match for date comparison in generation. |
| **14.3** | Structured extraction mode (/extract) | HIGH | MEDIUM | JSON schema enforcement on output. Requires Phase 11 /extract slash command. |
| **14.4** | Deal summary mode (/summary) | MEDIUM | LOW | Fixed 5-section output template. High user value for onboarding to new deals. |

---

## 3. Increment 14.1 — Session Deal Summary Cache

### 3.1 Summary Schema

```python
@dataclass
class DealSummary:
    scope: str                          # "bear_stearns_2006_HE1"
    deal_name: str | None               # extracted from doc header
    doc_types_present: list[str]        # ["PSA", "PROSUPP", "TRUST"]
    
    # Populated progressively as user asks questions
    parties: dict[str, str]             # {"Depositor": "...", "Trustee": "..."}
    key_dates: dict[str, str]           # {"Closing Date": "...", "Distribution Date": "..."}
    key_amounts: dict[str, str]         # {"Certificate Balance": "..."}
    defined_terms: dict[str, str]       # {"Determination Date": "25th of month..."}
    cited_sections: set[str]            # {"1.01", "2.03", "3.05"}
    
    # Metadata
    turn_count: int
    last_updated: datetime
```

### 3.2 Progressive Population

The summary is NOT computed all at once (too expensive). It is built up incrementally:

- Every answer that resolves a defined term → added to `defined_terms`
- Every answer citing a party → added to `parties`
- Every answer citing a date → added to `key_dates`
- Every answer citing a dollar amount → added to `key_amounts`

After N turns, the summary is rich. After 10 turns on a typical deal session, it contains the 8-12 most commonly queried data points — available at zero retrieval cost for the rest of the session.

### 3.3 Cache-First Retrieval

Before any vector search, check the session deal summary:

```python
def retrieve_with_cache(query, session_memory, scope):
    # Extract entities from query
    requested_terms = extract_entities(query)
    
    # Check summary cache first
    cached_answers = {}
    uncached_terms = []
    for term in requested_terms:
        if term in session_memory.deal_summary.defined_terms:
            cached_answers[term] = session_memory.deal_summary.defined_terms[term]
        else:
            uncached_terms.append(term)
    
    # Only retrieve from vector store for uncached terms
    if uncached_terms:
        retrieved_chunks = vector_search(query, scope)
    else:
        retrieved_chunks = []  # everything from cache
    
    return cached_answers, retrieved_chunks
```

---

## 4. Increment 14.2 — Temporal Reasoning

### 4.1 Current Date Injection

Every prompt receives `current_date` as a system variable:

```python
TEMPORAL_SYSTEM_CONTEXT = """
Today's date is {current_date}.
When answering questions about dates, deadlines, or time periods:
- If a date is in the past, state that explicitly ("this date has passed")
- If a date is in the future, state the time remaining ("X days / X months from today")
- If asked whether a condition based on a date is currently active, evaluate it
- Do not ask the user what today's date is
"""
```

### 4.2 Temporal Query Detection

```python
TEMPORAL_SIGNALS = [
    'has', 'passed', 'yet', 'still', 'current', 'active', 'expired',
    'how long', 'when does', 'is it', 'open', 'closed', 'period'
]

def is_temporal_query(query: str) -> bool:
    query_lower = query.lower()
    return any(signal in query_lower for signal in TEMPORAL_SIGNALS)
```

When temporal signals detected, the prompt template explicitly requests temporal evaluation in the answer.

---

## 5. Increment 14.3 — Structured Extraction Mode (/extract)

### 5.1 Output Schema

```json
{
  "deal_name": "Bear Stearns Asset Backed Securities 2006-HE1 Trust",
  "deal_type": "Pooling and Servicing Agreement",
  "closing_date": "2006-03-15",
  "parties": {
    "Depositor": "Bear Stearns Asset Backed Securities I LLC",
    "Trustee": "Deutsche Bank National Trust Company",
    "Master Servicer": "EMC Mortgage Corporation"
  },
  "key_dates": {
    "Closing Date": "2006-03-15",
    "First Distribution Date": "2006-04-25",
    "Distribution Date": "25th of each month",
    "Determination Date": "20th of each month"
  },
  "key_amounts": {},
  "defined_terms": {
    "Determination Date": "the 20th day of each calendar month...",
    "Business Day": "any day other than a Saturday..."
  },
  "source_sections": ["Section 1.01", "Section 2.01", "Section 11.01"],
  "confidence": "High",
  "extraction_gaps": ["Record Date", "Certificate Balance"]
}
```

`extraction_gaps` lists fields the system attempted to extract but could not locate — explicit, honest reporting of what is missing.

---

## 6. Increment 14.4 — Deal Summary Mode (/summary)

Fixed 5-section structured output, generated against 30 chunks from the deal scope:

```
## Deal Summary: Bear Stearns 2006-HE1

### 1. Parties
| Role | Entity |
|------|--------|
| Depositor | Bear Stearns Asset Backed Securities I LLC |
| Trustee | Deutsche Bank National Trust Company |

### 2. Key Dates
| Date | Value | Status (as of Feb 18, 2026) |
|------|-------|---------------------------|
| Closing Date | March 15, 2006 | ✅ Passed (20 years ago) |
| Optional Termination Date | [if found] | [computed] |

### 3. Key Amounts
...

### 4. Key Obligations
...

### 5. Risk Factors
...

*Confidence: High | Sources: Section 1.01, 2.01, 11.01 | Extraction gaps: [if any]*
```

---

## 7. Files Changed

| File | Change Type | Increment |
|------|------------|-----------|
| `backend/retrieval/session_memory.py` | Modified | 14.1 (DealSummary dataclass) |
| `backend/agents/retrieval_service.py` | Modified | 14.1 (cache-first retrieval), 14.2 (temporal injection) |
| `backend/retrieval/temporal_reasoner.py` | New | 14.2 |
| `backend/retrieval/extraction_mode.py` | New | 14.3 |
| `backend/retrieval/summary_mode.py` | New | 14.4 |
| `extension/chat/participant.js` | Modified | 14.3, 14.4 (JSON rendering, table rendering) |

---

## 8. Success Metrics

| Metric | Baseline | Target (Phase 14) |
|--------|----------|------------------|
| Cache hit rate on turn 5+ of session | 0% | >50% |
| Temporal question accuracy | ~40% (no date awareness) | >95% |
| /extract completeness (fields found) | N/A | >80% of schema |
| Rework rate (user re-asks same Q) | ~25% | <8% |
| "Determined from session cache" queries | 0% | >30% by turn 10 |
