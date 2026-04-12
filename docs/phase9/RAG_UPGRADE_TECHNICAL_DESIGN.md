# Phase 9: Directed Critique RAG — Technical Design Document

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Executive Summary

Phase 9 replaces Phase 8's holistic Self-RAG gap analysis (Technique 9) with a **directed, document-specific critique system** that decomposes self-evaluation into targeted binary sub-checks. Where Phase 8's Self-RAG asks the LLM "Is your answer complete?" (a holistic judgment that weaker models fail at), Phase 9 asks "Is there a CAUTION tag in the source that's missing from your answer?" (a binary check that even cheap models can answer reliably).

Three techniques, each building on the previous:

| Order | Technique | When It Runs | LLM Cost |
|-------|-----------|-------------|----------|
| 9.1 | Ingestion-Time Critique Question Generation | Ingest time | 1 call/document (amortized) |
| 9.2 | Directed Sequential Critique Loop + Dual-Model | Query time | Fixed-cost model × N questions × max_rounds |
| 9.3 | Multi-Doc Provenance-Filtered Merging | Query time | 0 additional (extends 9.2 ordering logic) |

**Relationship to Phase 8:** Phase 9 supersedes Phase 8 Technique 9 (§10 of the Phase 8 Technical Design). Techniques 1-8 from Phase 8 remain unchanged and are prerequisites. The Phase 8 Self-RAG loop (§10.3) is replaced by the Phase 9 Directed Critique Loop (§4 of this document). The Phase 8 gap analysis prompt (§10.4) is replaced by per-question binary critique (§4.4).

---

## 2. Key Design Principles

### 2.1 Decomposed Critique Over Holistic Judgment

The central insight driving Phase 9:

> A weaker model answering 5 narrow binary questions performs better than a stronger model answering 1 open-ended question.

**Why this works:** Binary classification (yes/no + evidence) is a fundamentally easier task than open-ended gap identification. GPT-4.1 at $0.002/1K tokens can reliably detect "CAUTION tag present in source but absent from answer" — it cannot reliably detect "the answer fails to preserve safety-critical annotations from the source."

### 2.2 Ingestion-Time Investment, Query-Time Payoff

Generating critique questions at ingestion time means:
- The LLM sees the **full document** (not just retrieved chunks)
- The cost is **one call per document** (not one call per query)
- Questions can reference specific section structure, defined terms, cross-references
- Questions can include **trigger keywords** for deterministic pre-filtering

### 2.3 Full Regression on State Change

After every answer modification, restart critique from Q₁:
- An answer that passed Q₃ before the fix may now fail Q₃ due to the re-synthesis
- This mirrors SDLC regression testing: every code change triggers the full test suite
- The outer loop is capped at `max_rounds` (default 3) to prevent runaway loops

### 2.4 Dual-Model Architecture

| Role | Model | Cost | Justification |
|------|-------|------|---------------|
| **Final answer generation** | User's selected model | Variable (may be Opus, GPT-4.1, etc.) | Premium tokens for user-facing output |
| **Critique evaluation** | Fixed: GPT-4.1 | Low, predictable | Binary yes/no doesn't need frontier performance |
| **Re-synthesis** | User's selected model | Variable | New chunks need same-quality integration |
| **Gap→Query translation** | Fixed: GPT-4.1 | Low | 5-10 word output, trivial task |
| **Ingest-time question gen** | Fixed: GPT-4.1 | Low, one-time | Amortized across all queries |

---

## 3. Technique 9.1: Ingestion-Time Critique Question Generation

### 3.1 Problem Statement

Phase 8's Self-RAG uses a single holistic gap analysis prompt at query time:

```
List the specific sub-questions or Capitalized Terms referenced 
in the draft answer that are NOT yet fully defined or explained in it.
```

This prompt has two flaws:
1. **It's generic** — the same prompt for legal PSAs, troubleshooting guides, and policy manuals
2. **It relies on the LLM recognizing what's missing from a narrow window** — at query time, the LLM only sees retrieved chunks, not the full document

### 3.2 Technical Approach

At ingestion time, after the Phase 6 pipeline completes, make one LLM call per document. The LLM receives the full document (or a structured summary for long docs) and generates:

1. **Doc-level critique questions** — apply to any query against this document
2. **Section-level critique questions** — apply only when chunks from that section are retrieved
3. **Trigger keywords** per question — for deterministic pre-filtering at query time
4. **Rubrics** per section — expected answer structure for common query patterns

### 3.3 Generation Prompt

```
System: You are a document quality analyst. Your task is to generate 
critique questions that can verify whether an AI-generated answer about 
this document is complete and accurate.

User:
Document type: {doc_type}
Document title: {doc_title}

Full document text (or structured summary):
{doc_content}

Sections identified:
{section_list_with_titles}

Instructions:
1. Generate 2-4 doc-level critique questions that apply to ANY query 
   against this document. These should check for universal answer quality 
   requirements (citations, safety annotations, terminology accuracy).

2. For each section, generate 1-4 section-level critique questions that 
   verify answer completeness when that section's content is retrieved.
   Focus on:
   - Structural elements that should be preserved (tables, ordered steps, 
     cross-references)
   - Safety-critical annotations (CAUTION, WARNING, NOTE)
   - Defined terms that require full resolution
   - Ordering constraints (e.g., do X before Y)

3. For each question, provide trigger keywords — terms that must appear 
   in the source chunks for the question to be relevant. Use "always" 
   for questions that should always be asked.

4. For each section, optionally provide a rubric: a regex-like pattern 
   for the query, and the expected answer structure.

Output format: JSON matching this schema:
{schema}
```

Where `{schema}` is the `DocCritique` JSON schema (see §3.4).

### 3.4 Data Schema: `DocCritique`

Stored at `.kts/documents/{doc_id}/critique_questions.json`:

```json
{
  "$schema": "critique_questions_v1",
  "doc_id": "string",
  "doc_type": "string",
  "doc_title": "string",
  "generated_at": "ISO 8601 datetime",
  "generator_model": "string",
  "generator_version": "1.0",
  "doc_level_questions": [
    {
      "id": "dq_NNN",
      "question": "string — binary yes/no question about answer quality",
      "trigger_keywords": ["string"],
      "trigger_logic": "always | any_in_source | all_in_source",
      "priority": 1
    }
  ],
  "section_questions": [
    {
      "section_id": "secNNN",
      "section_title": "string",
      "questions": [
        {
          "id": "sq_NNN",
          "question": "string — binary yes/no question",
          "trigger_keywords": ["string"],
          "trigger_logic": "always | any_in_source | all_in_source",
          "priority": 1
        }
      ],
      "rubric": {
        "pattern": "regex pattern matching likely queries for this section",
        "expected_structure": ["ordered list of expected answer elements"]
      }
    }
  ]
}
```

**Field semantics:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique within the doc: `dq_NNN` for doc-level, `sq_NNN` for section-level |
| `question` | string | Binary yes/no question. Must be answerable by comparing answer text to source text. |
| `trigger_keywords` | string[] | Keywords to look for in source chunks. Empty = always apply. |
| `trigger_logic` | enum | `"always"`: always active. `"any_in_source"`: any keyword in chunks → active. `"all_in_source"`: all keywords must be present. |
| `priority` | int | 1 = highest (always check first). Higher numbers = lower priority. |
| `rubric.pattern` | string | Regex matching likely user queries for this section |
| `rubric.expected_structure` | string[] | Ordered list of answer elements expected for matching queries |

### 3.5 Context-Length Handling for Long Documents

Documents exceeding the LLM context window (128K tokens for GPT-4.1) are handled via structured summarization:

```python
def prepare_doc_for_critique_gen(doc_text: str, sections: list[dict], 
                                  max_tokens: int = 100_000) -> str:
    """Prepare document content for critique question generation.
    
    For short docs: send full text.
    For long docs: send structured summary (section titles + first 500 tokens each).
    """
    estimated_tokens = len(doc_text) // 4  # conservative estimate
    
    if estimated_tokens <= max_tokens:
        return doc_text
    
    # Structured summary mode
    parts = []
    parts.append(f"[DOCUMENT BEGINNING — first 3000 tokens]\n{doc_text[:12000]}")
    
    for section in sections:
        title = section.get("title", "Untitled")
        content = section.get("content", "")[:2000]  # ~500 tokens
        parts.append(f"\n[SECTION: {title}]\n{content}")
    
    parts.append(f"\n[DOCUMENT END — last 1000 tokens]\n{doc_text[-4000:]}")
    
    return "\n".join(parts)
```

This degrades gracefully: the LLM generates questions from the document's **structure** (section titles, key terms, patterns) rather than exhaustive content — which is exactly what we want. Structural questions ("Is the Problem→Cause→Solution table preserved?") are more useful than content questions ("Did you include the sentence on page 47?").

### 3.6 Validation Pass

After generation, validate the output:

```python
def validate_critique_questions(critique: DocCritique) -> list[str]:
    """Validate generated critique questions for quality."""
    errors = []
    
    # Check: all questions end with "?"
    for q in _all_questions(critique):
        if not q.question.strip().endswith("?"):
            errors.append(f"{q.id}: Question doesn't end with '?'")
    
    # Check: trigger_logic is valid enum
    valid_logics = {"always", "any_in_source", "all_in_source"}
    for q in _all_questions(critique):
        if q.trigger_logic not in valid_logics:
            errors.append(f"{q.id}: Invalid trigger_logic '{q.trigger_logic}'")
    
    # Check: non-"always" questions have at least one trigger keyword
    for q in _all_questions(critique):
        if q.trigger_logic != "always" and not q.trigger_keywords:
            errors.append(f"{q.id}: Non-always trigger has no keywords")
    
    # Check: section_ids reference known sections
    known_ids = {s.section_id for s in critique.section_questions}
    # (This is validated against ingestion metadata)
    
    # Check: reasonable question count (2-15 per section)
    for sc in critique.section_questions:
        if len(sc.questions) > 15:
            errors.append(
                f"Section {sc.section_id}: {len(sc.questions)} questions "
                f"exceeds max (15)")
    
    return errors
```

### 3.7 Default Question Library

If LLM generation fails or is disabled, fall back to a static library of doc_type-specific questions:

```python
DEFAULT_QUESTIONS = {
    "GOVERNING_DOC": [
        CritiqueQuestion(
            id="default_gd_001",
            question="Are all Capitalized Terms used in the answer traced to their defined meanings?",
            trigger_keywords=[],
            trigger_logic="always",
            priority=1
        ),
        CritiqueQuestion(
            id="default_gd_002",
            question="Are cross-references to other Sections or Articles resolved or flagged?",
            trigger_keywords=["Section", "Article", "pursuant to"],
            trigger_logic="any_in_source",
            priority=2
        ),
        # ... more defaults per doc_type
    ],
    "TROUBLESHOOT": [
        CritiqueQuestion(
            id="default_ts_001",
            question="Does the answer preserve all CAUTION and WARNING annotations from the source?",
            trigger_keywords=["CAUTION", "WARNING", "⚠"],
            trigger_logic="any_in_source",
            priority=1
        ),
        CritiqueQuestion(
            id="default_ts_002",
            question="Are troubleshooting steps presented in the same order as the source document?",
            trigger_keywords=[],
            trigger_logic="always",
            priority=2
        ),
    ],
    "SUPPLEMENT": [
        CritiqueQuestion(
            id="default_su_001",
            question="Does the answer reference the specific supplement date and amendment number?",
            trigger_keywords=["dated", "supplement", "amendment"],
            trigger_logic="any_in_source",
            priority=1
        ),
    ],
}
```

### 3.8 Implementation Location

| File | Lines (est.) | Description |
|------|-------------|-------------|
| `backend/agents/critique_question_generator.py` | ~200 | Generator class: `generate()`, `save()`, `load()`, `validate()` |
| `backend/common/models.py` | ~40 | Dataclasses: `CritiqueQuestion`, `SectionCritique`, `DocCritique` |
| `backend/agents/critique_defaults.py` | ~80 | `DEFAULT_QUESTIONS` dictionary by doc_type |
| `backend/agents/ingestion_agent.py` | ~15 (diff) | Wire generator after Phase 6 pipeline |
| `config/settings.py` | ~8 (diff) | Add critique generation settings |

---

## 4. Technique 9.2: Directed Sequential Critique Loop + Dual-Model Architecture

### 4.1 Problem Statement

Phase 8's Self-RAG loop (Technical Design §10.3) uses a **holistic gap analysis** prompt that asks the LLM to identify all missing information at once:

```
List the specific sub-questions or Capitalized Terms referenced 
in the draft answer that are NOT yet fully defined or explained in it.
Return ONLY a JSON array of retrieval query strings.
Return [] if the answer is complete and fully self-contained.
```

**Failure mode observed empirically (GPT-4.1 vs Claude Opus, 2026-02-18):**
- GPT-4.1 missed the missing CAUTION tag entirely — it returned `[]` (no gaps)
- Claude Opus detected 3 distinct gaps including the CAUTION tag
- Same retrieved chunks, same prompt → **critique quality is the bottleneck**

Phase 8's design cannot fix this because:
1. The gap prompt is model-dependent — cheaper models produce worse gap analysis
2. The gap prompt is generic — no document-specific knowledge of what "complete" means
3. The loop has no regression mechanism — fixing gap A doesn't re-check gaps B and C

### 4.2 Technical Approach

Replace the holistic gap prompt with **sequential binary sub-checks** from the document-specific critique question store (generated by Technique 9.1). Each question is evaluated independently, and any failure triggers targeted re-retrieval + re-synthesis + full restart.

**The dual-model architecture** decouples critique cost from answer quality:

```
┌─────────────────────────────────────┐
│         User's Selected Model       │
│  (Claude Opus, GPT-4.1, etc.)       │
│  - Initial answer generation        │
│  - Re-synthesis after gap fixes     │
│  - Final answer to user             │
└─────────────┬───────────────────────┘
              │ answer text
              ▼
┌─────────────────────────────────────┐
│      Fixed Critique Model (GPT-4.1) │
│  - Binary critique evaluation       │
│  - Gap→query translation            │
│  - Confidence scoring               │
│  - Trigger keyword pre-filter       │
└─────────────────────────────────────┘
```

### 4.3 Loop State Machine

```
                 ┌──────────────┐
                 │  INITIALIZE  │
                 │  A₀ = initial│
                 │  round = 0   │
                 └──────┬───────┘
                        │
                        ▼
            ┌───────────────────────┐
       ┌───▶│  EVALUATE NEXT Qᵢ    │
       │    │  (trigger pre-filter) │
       │    └──────────┬────────────┘
       │               │
       │     ┌─── pass ──┬── fail ──┐
       │     │           │          │
       │     ▼           │          ▼
       │  i < |Q|?       │    ┌──────────┐
       │  ├─ yes ─┐      │    │ TRANSLATE │
       │  │       │      │    │ gap→query │
       │  │  next Qᵢ₊₁   │    └────┬─────┘
       │  │       │      │         │
       │  └───────┘      │         ▼
       │                 │    ┌──────────┐
       │                 │    │ RETRIEVE  │
       │                 │    │ new chunks│
       │                 │    └────┬─────┘
       │                 │         │
       │                 │         ▼
       │                 │    ┌──────────┐
       │                 │    │RE-SYNTH   │
       │                 │    │ (user LLM)│
       │                 │    └────┬─────┘
       │                 │         │
       │                 │         ▼
       │                 │    round < max?
       │                 │    ├─ yes → RESTART from Q₁ ──┐
       │                 │    │                           │
       │                 │    └─ no → RETURN best_answer  │
       │                 │                                │
       │   All Qᵢ passed │                                │
       │                 ▼                                │
       │           ┌──────────┐                           │
       │           │CONVERGED │                           │
       │           │return A  │                           │
       │           └──────────┘                           │
       │                                                  │
       └──────────────────────────────────────────────────┘
              (restart from Q₁)
```

### 4.4 Prompt Templates

#### 4.4.1 Single-Question Critique Prompt

```
System: You are a document quality reviewer. Evaluate ONLY the specific 
question below. Do not evaluate anything else.

User:
Question: {question.question}

Answer under review:
{current_answer}

Source content (retrieved chunks):
{formatted_chunks}

Instructions:
- Answer the question with "pass" or "fail"
- If "fail", describe the specific gap in 1-2 sentences
- Be strict: if the answer is vague where the source is specific, fail

Output format (JSON only):
{"pass": true}
or
{"pass": false, "gap_description": "The answer omits the CAUTION about..."}
```

**Why single-question, not batch:** Batching 5 questions into one prompt causes weaker models to conflate results or miss individual failures. One question per prompt = one binary judgment = reliable even for cheap models.

#### 4.4.2 Gap→Query Translation Prompt

```
System: Convert a gap description into a retrieval search query.

User:
Gap found in answer: {gap_description}
Original user question: {user_query}

Generate a 5-10 word search query that targets the missing information.
Return ONLY the query string — no explanation, no formatting.
```

**Examples:**

| Gap Description | Translated Query |
|----------------|-----------------|
| "CAUTION about data loss during standby resume is missing" | `power button standby resume caution data loss` |
| "Nested term 'Available Funds' referenced but not defined" | `Available Funds definition means shall mean` |
| "Cross-reference to Section 5.04(b) not resolved" | `Section 5.04 b obligations requirements` |

#### 4.4.3 Re-Synthesis Prompt

```
System: You are a document analyst. Integrate new context into an existing 
answer to fill a specific gap.

User:
Original question: {user_query}

Current answer (has a gap):
{current_answer}

Gap identified: {gap_description}

New context retrieved to fill the gap:
{new_chunks_formatted}

Instructions:
1. Integrate the new context into the current answer
2. Specifically address the identified gap
3. Do not remove correct existing content — only add and refine
4. Maintain the same answer format and citation style
5. Update confidence and source references
```

### 4.5 Trigger Pre-Filter Algorithm

The trigger pre-filter is a **deterministic, zero-cost check** that prevents the LLM from being asked irrelevant questions:

```python
def trigger_matches(question: CritiqueQuestion, 
                    chunks: list[dict]) -> bool:
    """Deterministic keyword check — no LLM cost.
    
    Returns True if the question should be evaluated.
    Returns False if the question's trigger keywords are 
    not found in the source chunks (question is irrelevant).
    """
    if question.trigger_logic == "always":
        return True
    
    # Concatenate all chunk text, lowercase for case-insensitive matching
    all_text = " ".join(
        c.get("content", "") for c in chunks
    ).lower()
    
    keywords = [kw.lower() for kw in question.trigger_keywords]
    
    if question.trigger_logic == "any_in_source":
        return any(kw in all_text for kw in keywords)
    elif question.trigger_logic == "all_in_source":
        return all(kw in all_text for kw in keywords)
    
    return False  # unknown logic → skip
```

**Expected filtering ratio:** For a document with 10-15 section-level questions, a typical query retrieves chunks from 1-2 sections. After provenance filtering (§5) removes questions from unretrieved sections, and trigger filtering removes questions whose keywords don't match, the active set is typically **3-5 questions** — a 60-75% reduction.

### 4.6 Keyword Safety Net (Deterministic Pre-Check)

Before the LLM critique loop, run a fast deterministic check for safety-critical keywords. This catches the most important class of gaps (CAUTION/WARNING omission) without any LLM cost:

```python
SAFETY_KEYWORDS = {
    "CAUTION": "CAUTION annotation",
    "WARNING": "WARNING annotation",
    "⚠": "warning symbol",
    "NOTE:": "NOTE callout",
    "IMPORTANT:": "IMPORTANT callout",
    "DO NOT": "prohibition statement",
    "MUST NOT": "prohibition statement",
}

def keyword_safety_check(answer: str, 
                         source_chunks: list[dict]) -> list[dict]:
    """Deterministic check: if source has safety keyword and answer 
    doesn't, return synthetic gap.
    
    Returns list of synthetic gap objects to inject into critique loop.
    """
    source_text = " ".join(c.get("content", "") for c in source_chunks)
    missing = []
    
    for keyword, label in SAFETY_KEYWORDS.items():
        if keyword in source_text and keyword not in answer:
            missing.append({
                "pass": False,
                "gap_description": (
                    f"Source contains {label} ('{keyword}') "
                    f"but the answer does not include it."
                ),
                "source": "keyword_safety_net"
            })
    
    return missing
```

These synthetic gaps are injected as the **first items** in the critique queue — they get priority because safety-critical omissions are the highest-impact gaps.

### 4.7 Confidence Scoring

The critique loop tracks confidence at each iteration:

```python
@dataclass
class CritiqueResult:
    """Result of the directed critique loop."""
    answer: str
    confidence: float          # 0.0 – 1.0
    rounds_executed: int
    questions_evaluated: int
    gaps_found: int
    gaps_fixed: int
    re_queries: list[str]      # queries generated from gaps
    converged: bool            # True if all questions passed
    answer_history: list[tuple[str, float]]  # (answer, confidence) per round
```

Confidence is calculated as:

$$\text{confidence} = \frac{\text{questions\_passed}}{\text{questions\_evaluated}} \times (1 - 0.1 \times \text{unfixed\_gaps})$$

Where `unfixed_gaps` = gaps found in the final round that couldn't be fixed (new chunks didn't help).

### 4.8 Progressive Streaming

During the critique loop, stream intermediate status to the user:

```javascript
// In participant.js during critique loop:
stream.progress(`Evaluating answer quality (${round}/${maxRounds})...`);

// After each gap fix:
stream.progress(
    `Found gap: ${gapDescription.substring(0, 60)}... ` +
    `Retrieving additional context.`
);

// On convergence:
stream.progress(
    `Answer verified: ${questionsEvaluated} checks passed, ` +
    `confidence ${(confidence * 100).toFixed(0)}%.`
);
```

### 4.9 Implementation Location

| File | Lines (est.) | Description |
|------|-------------|-------------|
| `backend/retrieval/critique_loop.py` | ~350 | Core loop: `DirectedCritiqueLoop.run()` |
| `backend/retrieval/critique_prompts.py` | ~100 | 3 prompt templates + formatting helpers |
| `extension/chat/participant.js` | ~40 (diff) | Wire loop into `generateAnswer()` |
| `extension/lib/critique_client.js` | ~120 | JS client: model selection, streaming, error handling |
| `config/settings.py` | ~6 (diff) | Add loop settings |

---

## 5. Technique 9.3: Multi-Doc Provenance-Filtered Merging

### 5.1 Problem Statement

When a query retrieves chunks from multiple documents, the critique question store contains questions from all ingested documents. **Pure union** of all questions generates a catastrophic false gap rate.

**Mathematical demonstration:**

Given:
- Doc A has 12 section-level questions across 4 sections
- Doc B has 8 section-level questions across 3 sections
- Query retrieves chunks from 1 section of Doc A and 1 section of Doc B

Pure union: 12 + 8 = 20 questions active.  
Relevant: 3 (Doc A sec X) + 3 (Doc B sec Y) = 6 questions.  
False gap rate: 14/20 = **70%** — the critique loop would chase 14 phantom gaps.

### 5.2 Provenance Filtering Algorithm

Only include questions from sections whose chunks were **actually retrieved**:

```python
from collections import Counter, defaultdict

def merge_critique_questions(
    retrieved_chunks: list[dict],
    critique_stores: dict[str, DocCritique]
) -> list[CritiqueQuestion]:
    """Provenance-filtered union with chunk-count-weighted ordering.
    
    Algorithm:
    1. Map each retrieved chunk to its (doc_id, section_id)
    2. Include doc-level questions for all docs with ≥1 retrieved chunk
    3. Include section-level questions ONLY for sections with ≥1 chunk
    4. Order by: doc-level first, then section-level by chunk count desc
    5. Within each group, order by priority
    
    Expected false gap rate: <5% (vs. 70% for pure union)
    """
    # Step 1: Build provenance map
    doc_section_map: dict[str, set[str]] = defaultdict(set)
    doc_chunk_counts: Counter = Counter()
    
    for chunk in retrieved_chunks:
        doc_id = chunk.get("doc_id") or chunk.get("metadata", {}).get("doc_id")
        section_id = (
            chunk.get("section_id") or 
            chunk.get("metadata", {}).get("section_id", "sec000")
        )
        if doc_id:
            doc_section_map[doc_id].add(section_id)
            doc_chunk_counts[doc_id] += 1
    
    # Step 2: Collect doc-level questions (always included for retrieved docs)
    doc_level = []
    for doc_id in doc_section_map:
        if doc_id in critique_stores:
            for q in critique_stores[doc_id].doc_level_questions:
                # Tag question with source doc info for debugging
                q._source_doc_id = doc_id
                q._source_doc_chunk_count = doc_chunk_counts[doc_id]
                doc_level.append(q)
    
    # Sort doc-level by priority
    doc_level.sort(key=lambda q: q.priority)
    
    # Step 3: Collect section-level questions (provenance-filtered)
    section_level = []
    for doc_id, count in doc_chunk_counts.most_common():
        if doc_id not in critique_stores:
            continue
        retrieved_sections = doc_section_map[doc_id]
        for section_crit in critique_stores[doc_id].section_questions:
            if section_crit.section_id in retrieved_sections:
                for q in section_crit.questions:
                    q._source_doc_id = doc_id
                    q._source_doc_chunk_count = count
                    q._source_section_id = section_crit.section_id
                    section_level.append(q)
    
    # Sort section-level by (chunk count desc, priority asc)
    section_level.sort(
        key=lambda q: (-q._source_doc_chunk_count, q.priority)
    )
    
    # Step 4: Combine: doc-level first, then section-level
    return doc_level + section_level
```

### 5.3 Expected Question Counts After Filtering

| Scenario | Store total | After provenance | After trigger | Active % |
|----------|------------|-----------------|---------------|----------|
| Single doc, 1 section retrieved | 15 | 5-6 | 2-4 | 15-27% |
| Single doc, 3 sections retrieved | 15 | 10-12 | 5-8 | 33-53% |
| 2 docs, 1 section each | 30 | 8-10 | 3-6 | 10-20% |
| 3 docs, mixed sections | 45 | 12-18 | 5-10 | 11-22% |

The dual filtering (provenance + trigger) reduces the active question set to roughly **N/5 to N/3** of the total store, making the critique loop tractable even for multi-doc queries.

### 5.4 Gap→Query Translation

When the critique loop identifies a gap, the gap description is a natural language sentence (e.g., "The CAUTION about data loss during standby resume is missing"). This must be converted into an effective retrieval query.

**The translation is a distinct prompting sub-step** — not rolled into the critique evaluation. This separation ensures:
1. The critique prompt stays focused on yes/no evaluation
2. The translation prompt can be optimized independently
3. Translation quality can be measured and improved separately

```python
class GapToQueryTranslator:
    """Convert critique gap descriptions into retrieval queries."""
    
    TRANSLATION_PROMPT = """
Given this gap in an answer: {gap_description}
The original user question was: {user_query}
Convert the gap into a 5-10 word search query targeting the missing information.
Return ONLY the query string — no explanation, no formatting.
"""
    
    def translate(self, gap_description: str, user_query: str,
                  critique_llm) -> str:
        """Translate a gap into a retrieval query."""
        prompt = self.TRANSLATION_PROMPT.format(
            gap_description=gap_description,
            user_query=user_query
        )
        return critique_llm.generate(prompt).strip()
    
    def translate_with_fallback(self, gap_description: str, 
                                 user_query: str,
                                 critique_llm) -> str:
        """Translate with keyword-extraction fallback."""
        try:
            query = self.translate(gap_description, user_query, critique_llm)
            if query and 3 <= len(query.split()) <= 15:
                return query
        except Exception:
            pass
        
        # Fallback: extract capitalized terms and nouns from gap
        return self._keyword_extract(gap_description)
    
    @staticmethod
    def _keyword_extract(text: str) -> str:
        """Simple keyword extraction fallback."""
        words = text.split()
        keywords = [w for w in words if w[0].isupper() or len(w) > 5]
        return " ".join(keywords[:8])
```

### 5.5 Best-Answer Selection

The critique loop may run multiple rounds, each producing a different answer. **The best answer is not necessarily the last one** — a re-synthesis might introduce errors while fixing a gap.

```python
class AnswerTracker:
    """Track answer quality across critique rounds.
    
    Returns the highest-confidence answer, not the latest one.
    This prevents regression: if Round 2's fix for gap A 
    accidentally breaks the answer for gap B, we keep Round 1's 
    answer if it had higher overall confidence.
    """
    
    def __init__(self):
        self.history: list[dict] = []
    
    def record(self, answer: str, confidence: float, 
               round_num: int, gaps_remaining: int):
        self.history.append({
            "answer": answer,
            "confidence": confidence,
            "round": round_num,
            "gaps_remaining": gaps_remaining,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    @property
    def best(self) -> dict:
        """Return the answer with highest confidence."""
        if not self.history:
            raise ValueError("No answers recorded")
        return max(self.history, key=lambda h: h["confidence"])
    
    @property
    def improved(self) -> bool:
        """Did any iteration improve over the initial answer?"""
        if len(self.history) < 2:
            return False
        return self.best["confidence"] > self.history[0]["confidence"]
    
    @property
    def regression_detected(self) -> bool:
        """Did the latest answer score lower than a previous one?"""
        if len(self.history) < 2:
            return False
        return self.history[-1]["confidence"] < self.best["confidence"]
```

### 5.6 Confidence-Based Early Exit

After processing doc-level and high-chunk-count section questions, if confidence exceeds the threshold and only tail questions remain:

```python
def should_early_exit(current_confidence: float,
                      remaining_questions: list[CritiqueQuestion],
                      threshold: float = 0.90) -> bool:
    """Exit early if confidence is high and remaining questions 
    are from low-contribution documents.
    
    "Tail questions" = from docs contributing ≤1 chunk to retrieval.
    These are unlikely to reveal critical gaps.
    """
    if current_confidence < threshold:
        return False
    
    # All remaining questions from minor-contribution docs?
    return all(
        getattr(q, '_source_doc_chunk_count', 0) <= 1
        for q in remaining_questions
    )
```

### 5.7 Implementation Location

| File | Lines (est.) | Description |
|------|-------------|-------------|
| `backend/retrieval/critique_merger.py` | ~150 | `merge_critique_questions()`, provenance map builder |
| `backend/retrieval/critique_loop.py` | ~60 (diff) | Add `GapToQueryTranslator`, `AnswerTracker`, early exit |
| `backend/retrieval/critique_prompts.py` | ~20 (diff) | Add `GAP_TO_QUERY_PROMPT` |
| `tests/test_phase9_multi_doc_critique.py` | ~300 | See Testing Plan §2.3 |

---

## 6. Integration Points with Phase 8

Phase 9 techniques integrate with Phase 8 at specific points in the retrieval pipeline. This section clarifies which Phase 8 components are **used, extended, or replaced.**

### 6.1 Technique Dependency Map

| Phase 8 Technique | Phase 9 Relationship | Notes |
|-------------------|---------------------|-------|
| 0 — CCH (Contextual Chunk Headers) | **USED** | Critique questions reference section_id from CCH metadata |
| 1 — BM25 Hybrid Search | **USED** | Gap→query re-retrieval uses BM25+vector hybrid |
| 2 — MMR Diversity Sampling | **USED** | Re-retrieved chunks go through MMR dedup |
| 3 — Parent-Child Document Linking | **USED** | Critique question section_ids match parent_section_id |
| 4 — Token-Aware Context Trimming | **USED** | Re-synthesis respects token limits |
| 5 — Targeted HyPE | **USED** | HyPE-enriched chunks improve trigger keyword matching |
| 6 — Multi-Query RAG Fusion | **USED** | Initial retrieval still uses multi-query |
| 7 — N-Level Definition Chain | **USED** | Critique questions for GOVERNING_DOC check definition resolution |
| 8 — Self-RAG Iterative Loop | **REPLACED** | Phase 9.2 replaces the holistic loop entirely |

### 6.2 File-Level Changes

| Phase 8 File | Phase 9 Change | Reason |
|-------------|---------------|--------|
| `backend/retrieval/self_rag.py` (planned) | **Not created** — replaced by `critique_loop.py` | Phase 9 loop replaces Phase 8 Self-RAG |
| `backend/retrieval/iterative_orchestrator.py` | No change | Still handles retrieval-level iteration; Phase 9 adds generation-level |
| `extension/chat/participant.js` | Modified | Wire critique loop after initial answer |
| `backend/agents/ingestion_agent.py` | Modified | Add critique question generation call |

---

## 7. Storage Layout

```
.kts/
├── config/
│   └── settings.json
├── chroma_db/
│   ├── items/
│   └── sections/
├── graph/
│   └── knowledge_graph.json
├── documents/
│   ├── doc_3842400/                    # HP Troubleshooting Guide
│   │   ├── images/
│   │   │   └── img_001.png
│   │   ├── metadata.json
│   │   └── critique_questions.json     ← NEW (Inc 9.1)
│   ├── doc_5054059/                    # PSA Governing Document
│   │   ├── images/
│   │   ├── metadata.json
│   │   └── critique_questions.json     ← NEW (Inc 9.1)
│   └── doc_7890123/                    # Prospectus Supplement
│       ├── images/
│       ├── metadata.json
│       └── critique_questions.json     ← NEW (Inc 9.1)
└── critique_cache/                     ← NEW (Inc 9.2, optional)
    └── {query_hash}.json              # Cache critique results per query
```

### 7.1 critique_questions.json Size Estimates

| Doc Type | Sections | Questions | File Size |
|----------|----------|-----------|-----------|
| TROUBLESHOOT (HP guide) | 5-8 | 10-20 | ~3 KB |
| GOVERNING_DOC (PSA) | 15-25 | 30-50 | ~8 KB |
| SUPPLEMENT (Pro Supp) | 10-15 | 20-35 | ~5 KB |

Total overhead per corpus: negligible (<100 KB for 20 documents).

---

## 8. Error Handling and Edge Cases

### 8.1 Critique Generation Failures

| Failure | Handling |
|---------|---------|
| LLM returns invalid JSON | Parse with `json_repair` → validate → fallback to defaults |
| LLM returns no questions | Use `DEFAULT_QUESTIONS[doc_type]` |
| LLM returns 50+ questions for one section | Truncate to `critique_max_questions_per_doc` (default 15) |
| LLM refuses content (safety filter) | Log warning, use defaults |
| Context length exceeded | Use structured summary mode (§3.5) |

### 8.2 Critique Loop Failures

| Failure | Handling |
|---------|---------|
| Critique LLM returns invalid JSON | Treat as "pass" (optimistic) — log warning |
| Gap→query translation returns empty | Use keyword extraction fallback |
| Re-retrieval returns 0 new chunks | Skip — don't re-synthesize with no new context |
| Re-synthesis produces shorter answer | Regression — keep previous best via `AnswerTracker` |
| All 3 rounds exhausted with gaps remaining | Return `AnswerTracker.best` with `converged=False` |
| Critique model unavailable | Graceful fallback: skip critique, return initial answer |
| Timeout (critique loop > 30s) | Exit with best answer so far |

### 8.3 Multi-Doc Edge Cases

| Scenario | Handling |
|----------|---------|
| Retrieved doc has no critique_questions.json | Use `DEFAULT_QUESTIONS[doc_type]` |
| chunk has no section_id metadata | Assign to `"sec000"` (default section) |
| Same question appears from two docs | Deduplicate by question text (keep highest priority) |
| All questions filtered out by triggers | Short-circuit: return initial answer as-is |

---

## 9. Performance Characteristics

### 9.1 Latency Model

| Component | Latency | Calls per query |
|-----------|---------|----------------|
| Load critique_questions.json | <1ms | 1-3 per query |
| Trigger pre-filter | <1ms | 5-15 questions |
| Keyword safety check | <1ms | 1 per query |
| Critique LLM call (per question) | ~300-500ms | 3-5 active questions |
| Gap→query translation | ~200ms | 0-2 per round |
| Re-retrieval (BM25+vector) | ~100-200ms | 0-2 per round |
| Re-synthesis (user's model) | ~2-4s | 0-2 per round |

**Best case** (all questions pass, round 1): 5 × 400ms = **2.0s overhead**  
**Typical case** (1 gap found, 2 rounds): 2.0s + 200ms + 150ms + 3s + 2.0s = **7.4s total**  
**Worst case** (3 rounds, 2 gaps each): ~**15s total**

### 9.2 Token Cost Model

Per query (typical):

| Component | Input tokens | Output tokens | Cost (GPT-4.1) |
|-----------|-------------|--------------|----------------|
| 5 critique checks | 5 × 2000 | 5 × 50 | ~$0.02 |
| 1 gap translation | 200 | 10 | ~$0.0004 |
| 1 re-retrieval | — | — | $0 (local) |
| **Critique subtotal** | | | **~$0.02** |
| 1 re-synthesis (user model) | 4000 | 1000 | varies |
| **Total query overhead** | | | **~$0.02 + re-synthesis** |

Per document (ingestion):

| Component | Input tokens | Output tokens | Cost (GPT-4.1) |
|-----------|-------------|--------------|----------------|
| Critique question generation | ~10,000 | ~2,000 | ~$0.024 |
| **Ingestion overhead** | | | **~$0.024/document** |

### 9.3 Comparison to Phase 8 Self-RAG

| Dimension | Phase 8 Self-RAG | Phase 9 Directed Critique |
|-----------|-----------------|--------------------------|
| Gap detection | 1 holistic prompt | 3-5 targeted binary checks |
| False gap rate | ~30-50% (model-dependent) | <5% (provenance-filtered) |
| Missing-gap rate | ~20-40% (model-dependent) | <10% (keyword safety net catches critical) |
| Questions per round | 1 (open-ended) | 3-5 (binary) |
| LLM calls per round | 1 (expensive) | 5 (cheap) + 0-1 (translation) |
| Restart behavior | Resume from last gap | Full restart (regression test) |
| Model dependency | Same model for everything | Dual: cheap for critique, premium for answer |
| Doc-specific knowledge | None (generic prompt) | Document-specific questions from ingest |

---

## 10. Technical Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Critique questions generated at ingest are too generic | Medium | Medium | Validation pass rejects vague questions; supplement with doc_type defaults |
| Trigger keywords miss valid matches (false negative) | Low | Low | "always" questions as backstop; fuzzy matching for common variants |
| LLM generates leading/biased questions | Low | Medium | Prompt engineering: "binary yes/no only"; validation rejects non-question output |
| Dual-model adds too much latency | Medium | Medium | Feature flag; early exit on high confidence; parallel critique checks (future) |
| Provenance filter over-filters (removes valid questions) | Low | Low | Doc-level "always" questions bypass provenance filter entirely |
| Re-synthesis degrades answer quality | Medium | High | `AnswerTracker` returns best version; regression detection logging |
| Critique loop creates retrieval storm | Low | High | Hard cap: max 2 re-queries per round, max 3 rounds |
| GPT-4.1 unavailable or rate-limited | Low | Medium | Configurable `critique_model`; fallback to user's model |
| critique_questions.json corruption | Very Low | Low | Validate on load; regenerate on validation failure |
| Circular gap→fix→gap regression | Low | Medium | `prev_gaps` comparison: if same gap appears twice, skip it |

---

## 11. Success Criteria

| Criterion | Measurement | Target |
|-----------|------------|--------|
| CAUTION preservation (HP guide) | GPT-4.1 with critique loop vs. without | ✅ CAUTION present with loop |
| Critique question relevance | Manual review of 10 docs | ≥80% questions judged relevant |
| False gap rate (multi-doc) | Automated: count gaps from unretrieved sections | <5% |
| Missing-gap rate (safety keywords) | Automated: inject known gaps, measure detection | ≥95% for CAUTION/WARNING |
| Loop convergence | Distribution of rounds needed | ≥80% converge in ≤2 rounds |
| Best-answer vs. initial-answer | A/B on 20 golden queries | best ≥ initial in ≥90% of cases |
| Ingestion latency | Timer: per-document critique generation | <5s per document |
| Query latency | End-to-end with critique loop | <15s median |
| Regression test passes | Full pytest + mocha suite | Zero regressions |
| Token cost per query | Automated tracking | <$0.05 critique overhead |
