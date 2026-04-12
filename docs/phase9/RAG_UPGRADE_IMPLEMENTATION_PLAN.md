# Phase 9: Directed Critique RAG — Implementation Plan

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Motivation — Empirical Evidence

### 1.1 The HP Guide Experiment (2026-02-18)

During VSIX 0.0.11 validation, the HP Troubleshooting Guide (`TS_GUIDE.pdf`) was ingested and queried with:

> *"computer failed to restate even if we pressed the power button"*

The same 3 retrieved chunks (confidence 0.96) were sent to two different LLM models via the identical KTS Support prompt:

| Dimension | GPT-4.1 | Claude Opus 4.6 |
|-----------|---------|-----------------|
| **Matched Issue** | Single merged title | 3 distinct section matches with exact page refs |
| **Step ordering** | Unstructured mix | Prioritized — force-off first → diagnostics last |
| **CAUTION preservation** | ❌ Missing | ✅ Verbatim caution included (data loss warning) |
| **Excerpts cited** | 5 quotes, some redundant | 3 quotes, zero redundancy |
| **Cross-chunk synthesis** | Flat merge | Synthesized across 3 sections |

### 1.2 The Core Finding

**Critique quality is the bottleneck, not retrieval quality.** Both models received identical retrieval. The difference is entirely in the model's ability to:

1. Recognize safety-critical annotations (CAUTION, WARNING)
2. Order steps by severity
3. De-duplicate excerpt selection
4. Synthesize across multiple source sections

In a Self-RAG loop, a weaker model will **hallucinate satisfaction** and exit the loop early — it declares "no gaps" because it doesn't recognize what's missing. A stronger model finds real gaps but costs more per call.

### 1.3 The Design Principle

> **Decompose holistic self-critique into targeted binary sub-checks.** A weaker model can reliably answer "Is there a CAUTION tag in the source that's missing from your answer?" even when it can't answer "Is your answer complete?"

This principle, combined with **ingestion-time question generation** (the LLM sees the full document once, amortized across all future queries), forms the basis of Phase 9.

### 1.4 Academic Grounding

| Technique | Paper / Implementation | Relevance to Phase 9 |
|-----------|----------------------|----------------------|
| **Self-RAG** | Asai et al. 2023 | Reflection tokens [ISREL], [ISSUP], [ISUSE] — we replicate via structured critique schema |
| **FLARE** | Jiang et al. 2023 | Confidence-triggered re-retrieval — we replicate via gap detection + re-query |
| **CRAG** | Yan et al. 2024 | Separate evaluator model from generator — our dual-model architecture |
| **LangChain Self-RAG** | Production template | Structured JSON critique `{"relevant": bool, "supported": bool}` per chunk |
| **LlamaIndex Corrective RAG** | Production template | Relevance → support → hallucination check sequence |
| **Cohere RAG pipeline** | Production impl | Forced binary output per assertion |
| **Anthropic prompting guide** | Best practice | Decompose complex judgment into narrow yes/no sub-questions |

**Our unique contribution:** Ingestion-time critique question generation. No published system generates document-specific critique questions at ingest time and stores them for query-time consumption. This is novel.

---

## 2. Implementation Philosophy

> *"We want to mimic superior LLM behavior without paying superior LLM prices — by engineering the critique loop to compensate for what weaker models miss."*

**Design constraints:**
- Critique loop uses a **fixed low-cost model** (GPT-4.1 or GPT-4o) — independent of user's selected chat model
- User's selected model generates the **final answer only** — premium tokens spent on output, not on evaluation
- **Full regression** after every gap-fix: restart critique from Q₁ (SDLC regression test analogy)
- **Latency is secondary** to answer quality — user trust is more valuable than 2-second savings

---

## 3. Implementation Order

Three increments, strict dependencies:

| Order | Increment | Impact | Risk | Rationale |
|-------|-----------|--------|------|-----------|
| **9.1** | Ingestion-Time Critique Question Generation | HIGH | LOW | Foundation — everything in 9.2 and 9.3 depends on having a question store. One LLM call per doc at ingest, amortized across all queries forever. |
| **9.2** | Directed Sequential Critique Loop + Dual-Model Architecture | VERY HIGH | MEDIUM | The core loop. Requires 9.1 question store + Phase 8 Inc 8 iterative loop as starting point. |
| **9.3** | Multi-Doc Provenance-Filtered Merging + Gap→Query Translation + Best-Answer Selection | HIGH | MEDIUM | Multi-doc completeness. Requires 9.1 (questions from multiple docs) + 9.2 (loop to evaluate against). |

---

## 4. Increment 9.1: Ingestion-Time Critique Question Generation

### 4.1 What Is It?

During document ingestion, after chunking and embedding, the system makes one additional LLM call per document. This call receives the full document text (or a representative summary if it exceeds context limits) and generates a set of **section-level critique questions** with **trigger keywords**. These questions are stored as `.kts/documents/{doc_id}/critique_questions.json` and are consumed at query time by the critique loop.

**The economic insight:** 1 LLM call at ingest time is amortized across potentially thousands of queries against that document. The cost per query is effectively zero.

### 4.2 What Gets Generated

For each section identified during ingestion, the LLM generates:

1. **Critique questions** — binary yes/no questions about answer completeness
2. **Trigger keywords** — terms that must be present in retrieved chunks for the question to activate
3. **Rubric entries** — expected answer structure for common query patterns against this section

Additionally, **doc-level questions** are generated that apply regardless of which section is retrieved.

**Example — HP Troubleshooting Guide (`doc_3842400`):**

```json
{
  "doc_id": "doc_3842400",
  "doc_type": "TROUBLESHOOT",
  "generated_at": "2026-02-18T17:45:00Z",
  "generator_model": "gpt-4.1",
  "doc_level_questions": [
    {
      "id": "dq_001",
      "question": "Does the answer preserve all CAUTION and NOTE callouts from the matched section?",
      "trigger_keywords": ["CAUTION", "NOTE", "WARNING", "⚠"],
      "trigger_logic": "any_in_source",
      "priority": 1
    },
    {
      "id": "dq_002",
      "question": "Are specific page numbers or section references cited for each solution step?",
      "trigger_keywords": [],
      "trigger_logic": "always",
      "priority": 2
    }
  ],
  "section_questions": [
    {
      "section_id": "sec000",
      "section_title": "Solving General Problems",
      "questions": [
        {
          "id": "sq_001",
          "question": "Is the Problem→Cause→Solution table structure preserved in the answer?",
          "trigger_keywords": ["Problem", "Cause", "Solution"],
          "trigger_logic": "all_in_source",
          "priority": 1
        },
        {
          "id": "sq_002",
          "question": "Does the answer reference Appendix A POST error codes when the Power LED or beep codes are mentioned?",
          "trigger_keywords": ["POST", "LED", "blinking", "beep", "error code"],
          "trigger_logic": "any_in_source",
          "priority": 2
        },
        {
          "id": "sq_003",
          "question": "Is the step sequence consistent with the document — most direct fix first (hold power button) before escalation (unplug cord)?",
          "trigger_keywords": ["power button", "restart", "shut down", "unplug"],
          "trigger_logic": "any_in_source",
          "priority": 3
        }
      ],
      "rubric": {
        "pattern": "computer will not start|locked up|power button",
        "expected_structure": [
          "Force-off procedure (hold power button 4 seconds)",
          "Power LED diagnostic check",
          "Appendix A reference if blinking red",
          "Escalation path (authorized dealer)"
        ]
      }
    }
  ]
}
```

**Example — PSA Governing Document:**

```json
{
  "doc_id": "doc_5054059",
  "doc_type": "GOVERNING_DOC",
  "doc_level_questions": [
    {
      "id": "dq_001",
      "question": "Are all Capitalized Terms used in the answer traced to their defined meanings?",
      "trigger_keywords": [],
      "trigger_logic": "always",
      "priority": 1
    },
    {
      "id": "dq_002",
      "question": "Are conflicting or ambiguous provisions both cited rather than only one interpretation presented?",
      "trigger_keywords": ["notwithstanding", "except", "provided however"],
      "trigger_logic": "any_in_source",
      "priority": 2
    }
  ],
  "section_questions": [
    {
      "section_id": "sec001",
      "section_title": "Definitions",
      "questions": [
        {
          "id": "sq_001",
          "question": "Is the full definition chain traced for every Capitalized Term — including nested terms referenced within the definition?",
          "trigger_keywords": ["means", "shall mean", "defined"],
          "trigger_logic": "any_in_source",
          "priority": 1
        },
        {
          "id": "sq_002",
          "question": "Are cross-references to other Sections or Articles in the definition resolved or flagged?",
          "trigger_keywords": ["Section", "Article", "pursuant to", "as defined in"],
          "trigger_logic": "any_in_source",
          "priority": 2
        }
      ]
    }
  ]
}
```

### 4.3 Deliverables

| File | Action | Description |
|------|--------|-------------|
| `backend/agents/critique_question_generator.py` | **CREATE** | ~200 lines. LLM call to generate critique questions at ingest time. |
| `backend/agents/ingestion_agent.py` | MODIFY | After Phase 6 pipeline, call critique question generator. |
| `backend/common/models.py` | MODIFY | Add `CritiqueQuestion`, `SectionCritique`, `DocCritique` dataclasses. |
| `config/settings.py` | MODIFY | Add `critique_generation_enabled`, `critique_generator_model` settings. |
| `tests/test_phase9_critique_gen.py` | **CREATE** | ~250 lines. Unit + integration tests. |

### 4.4 Implementation Steps

**Step 9.1.1: Define data models in `models.py`**

```python
@dataclass
class CritiqueQuestion:
    id: str
    question: str
    trigger_keywords: list[str]
    trigger_logic: str  # "always" | "any_in_source" | "all_in_source"
    priority: int

@dataclass
class SectionCritique:
    section_id: str
    section_title: str
    questions: list[CritiqueQuestion]
    rubric: dict | None = None  # optional expected answer structure

@dataclass
class DocCritique:
    doc_id: str
    doc_type: str
    generated_at: str
    generator_model: str
    doc_level_questions: list[CritiqueQuestion]
    section_questions: list[SectionCritique]
```

**Step 9.1.2: Create `critique_question_generator.py`**

```python
class CritiqueQuestionGenerator:
    """Generate document-specific critique questions at ingest time.
    
    Uses a fixed low-cost LLM (gpt-4.1) to analyze the full document
    and produce section-level binary yes/no critique questions with
    trigger keywords.
    """
    
    GENERATION_PROMPT = """..."""  # See Technical Design §3.3
    
    def generate(self, doc_text: str, doc_type: str, sections: list[dict]) -> DocCritique:
        """Generate critique questions for a document."""
        ...
    
    def save(self, doc_critique: DocCritique, kts_path: Path) -> Path:
        """Save to .kts/documents/{doc_id}/critique_questions.json"""
        ...
    
    def load(self, doc_id: str, kts_path: Path) -> DocCritique | None:
        """Load critique questions for a document."""
        ...
```

**Step 9.1.3: Wire into ingestion pipeline**

In `ingestion_agent.py`, after `_run_phase6_pipeline()` completes:

```python
if self.config.critique_generation_enabled:
    generator = CritiqueQuestionGenerator(self.config)
    critique = generator.generate(
        doc_text=full_text,
        doc_type=normalize_doc_type(doc_regime),
        sections=section_dicts
    )
    generator.save(critique, Path(self.config.knowledge_base_path))
```

**Step 9.1.4: Handle context-length limits**

For documents exceeding the LLM context window (e.g., 200-page PSA):
- Send the first 3000 tokens (typically definitions + TOC) + last 1000 tokens
- Per-section: send the section title + first 500 tokens of each section
- The LLM generates questions from structure, not full content — this degrades gracefully

**Step 9.1.5: Write unit and integration tests**

See Testing Plan §2.1 for full test matrix.

**Step 9.1.6: Run regression**
```bash
pytest tests/ -v --tb=short
```
Gate: **ALL existing tests PASS + new tests PASS**

### 4.5 Rollback Plan

`critique_generation_enabled = False` → ingestion skips question generation entirely. Existing ingestion flow unchanged. `critique_questions.json` files are standalone — deleting them has zero impact on retrieval or ChromaDB.

---

## 5. Increment 9.2: Directed Sequential Critique Loop + Dual-Model Architecture

### 5.1 What Is It?

After the initial LLM answer is generated (using the user's selected model), the system loads critique questions for all retrieved documents and runs them **sequentially, one at a time** through a fixed low-cost LLM. If a gap is found, the gap is translated into a retrieval query, new chunks are fetched, the answer is re-synthesized, and **the full critique sequence restarts from Q₁** (regression testing model).

**Dual-model architecture:**
- **Critique model** (fixed): GPT-4.1 or GPT-4o — runs all critique checks and gap translation
- **Generation model** (user-selected): Claude Opus, GPT-4.1, etc. — produces the initial and final answer

### 5.2 The Loop — Formal Specification

```
INPUTS:
  A₀         = initial answer from user's selected model
  Q           = ordered list of active critique questions (from 9.1 + defaults)
  chunks₀     = initially retrieved chunks
  max_rounds  = 3 (configurable)

ALGORITHM:
  best_answer  = A₀
  best_score   = confidence(A₀)
  all_chunks   = chunks₀

  for round in 1..max_rounds:
    for i, question in enumerate(Q):
      
      # -- Trigger pre-filter (deterministic, no LLM) --
      if question.trigger_logic != "always":
        if not trigger_matches(question.trigger_keywords, all_chunks):
          SKIP question
          continue
      
      # -- Ask critique question to fixed-cost LLM --
      verdict = critique_llm(question, current_answer, all_chunks)
      # verdict = { "pass": bool, "gap_description": str | null }
      
      if verdict.pass:
        continue to next question
      
      # -- Gap found: translate to retrieval query --
      re_query = critique_llm.translate_gap_to_query(verdict.gap_description)
      
      # -- Re-retrieve --
      new_chunks = retrieve(re_query, exclude_ids=seen_chunk_ids)
      all_chunks = all_chunks + new_chunks
      seen_chunk_ids.update(new_chunks)
      
      # -- Re-synthesize with user's model --
      current_answer = generation_llm(query, all_chunks, prior_answer=current_answer)
      
      # -- Track best answer --
      current_score = confidence(current_answer)
      if current_score > best_score:
        best_answer = current_answer
        best_score = current_score
      
      # -- RESTART from Q₁ (full regression) --
      break  # break inner for-loop, outer for-loop increments round
    
    else:
      # Inner loop completed without break → all questions passed
      EXIT with current_answer  # CONVERGED
  
  return best_answer  # max_rounds reached — return highest-confidence version
```

### 5.3 Deliverables

| File | Action | Description |
|------|--------|-------------|
| `backend/retrieval/critique_loop.py` | **CREATE** | ~350 lines. Core directed critique loop orchestrator. |
| `backend/retrieval/critique_prompts.py` | **CREATE** | ~100 lines. Prompt templates for critique, gap translation, re-synthesis. |
| `extension/chat/participant.js` | MODIFY | Wire critique loop into `generateAnswer()` after initial LLM response. |
| `extension/lib/critique_client.js` | **CREATE** | ~120 lines. JS client for critique loop — model selection, streaming. |
| `config/settings.py` | MODIFY | Add `critique_loop_enabled`, `critique_model`, `critique_max_rounds`, `critique_restart_on_gap`. |
| `tests/test_phase9_critique_loop.py` | **CREATE** | ~400 lines. Unit + integration tests. |

### 5.4 Implementation Steps

**Step 9.2.1: Create `critique_prompts.py`**

Three prompt templates:
1. **Critique prompt** — binary evaluation of a single question against the answer
2. **Gap→Query translation prompt** — convert a gap description into a 5-10 word retrieval query
3. **Re-synthesis prompt** — integrate new chunks into existing answer

See Technical Design §4.4 for exact prompt text.

**Step 9.2.2: Create `critique_loop.py`**

```python
class DirectedCritiqueLoop:
    """Sequential critique loop with full restart on gap detection.
    
    Uses a fixed low-cost LLM for critique checks.
    Uses the caller-specified model for answer re-synthesis.
    Tracks best answer across all iterations.
    """
    
    def __init__(self, config, critique_llm, generation_llm, retriever):
        self.config = config
        self.critique_llm = critique_llm
        self.generation_llm = generation_llm
        self.retriever = retriever
        self.max_rounds = config.critique_max_rounds  # default 3
    
    def run(self, query, initial_answer, initial_chunks, 
            critique_questions) -> CritiqueResult:
        """Execute the directed critique loop."""
        ...
```

**Step 9.2.3: Implement trigger pre-filter**

```python
def trigger_matches(question: CritiqueQuestion, chunks: list[dict]) -> bool:
    """Deterministic keyword check — no LLM needed."""
    all_text = " ".join(c.get("content", "") for c in chunks).lower()
    keywords = [kw.lower() for kw in question.trigger_keywords]
    
    if question.trigger_logic == "always":
        return True
    elif question.trigger_logic == "any_in_source":
        return any(kw in all_text for kw in keywords)
    elif question.trigger_logic == "all_in_source":
        return all(kw in all_text for kw in keywords)
    return False
```

**Step 9.2.4: Implement keyword safety net (deterministic)**

Before starting the LLM critique loop, run a fast deterministic check:

```python
SAFETY_KEYWORDS = ["CAUTION", "WARNING", "⚠", "NOTE:", "IMPORTANT:"]

def keyword_safety_check(answer: str, source_chunks: list[dict]) -> list[str]:
    """If source has CAUTION/WARNING and answer doesn't, flag it."""
    source_text = " ".join(c.get("content", "") for c in source_chunks)
    missing = []
    for kw in SAFETY_KEYWORDS:
        if kw in source_text and kw not in answer:
            missing.append(f"Source contains '{kw}' but the answer does not include it.")
    return missing
```

**Step 9.2.5: Wire into `participant.js`**

After initial LLM generation completes:

```javascript
if (settings.critique_loop_enabled) {
    // Load critique questions for retrieved docs
    const questions = await loadCritiqueQuestions(result);
    
    // Select fixed critique model (gpt-4.1)
    const critiqueModel = await selectFixedModel(vscode, 'gpt-4.1');
    
    // Run critique loop (streams progressive updates)
    const improved = await runCritiqueLoop(
        vscode, critiqueModel, userModel, stream, token,
        query, initialAnswer, result, questions
    );
    
    stream.markdown(improved.answer);
}
```

**Step 9.2.6: Write tests and run regression**

See Testing Plan §2.2 for full test matrix.

### 5.5 Rollback Plan

`critique_loop_enabled = False` → `generateAnswer()` returns the single-round answer exactly as Phase 8 designed. All critique code is dead. Zero blast radius.

---

## 6. Increment 9.3: Multi-Doc Provenance-Filtered Merging + Gap→Query Translation + Best-Answer Selection

### 6.1 What Is It?

When a query retrieves chunks from multiple documents, each document's `critique_questions.json` must be consulted. **Pure union** of all questions would generate 71%+ false gaps (questions about unretrieved sections). This increment implements **provenance-filtered union with trigger-keyword pre-filtering** and chunk-count-weighted ordering.

Additionally, this increment formalizes:
- **Gap→Query translation** — converting LLM gap descriptions into effective retrieval queries
- **Best-answer selection** — tracking confidence across rounds and returning the highest-scoring version

### 6.2 Question Merging Algorithm

```python
def merge_critique_questions(
    retrieved_chunks: list[dict],
    critique_stores: dict[str, DocCritique]  # doc_id → DocCritique
) -> list[CritiqueQuestion]:
    """
    Provenance-filtered union: only include questions from sections
    whose chunks were actually retrieved.
    
    Ordering: doc-level universal → high-chunk-count doc's sections 
              → low-chunk-count doc's sections
    """
    # Step 1: Identify which doc_ids and section_ids are in retrieved chunks
    doc_section_map = defaultdict(set)  # doc_id → set of section_ids
    doc_chunk_counts = Counter()        # doc_id → chunk count
    
    for chunk in retrieved_chunks:
        doc_id = chunk.get("doc_id")
        section_id = chunk.get("metadata", {}).get("section_id", "sec000")
        doc_section_map[doc_id].add(section_id)
        doc_chunk_counts[doc_id] += 1
    
    # Step 2: Collect doc-level questions (always included)
    active_questions = []
    for doc_id in doc_section_map:
        if doc_id in critique_stores:
            active_questions.extend(critique_stores[doc_id].doc_level_questions)
    
    # Step 3: Collect section-level questions (provenance-filtered)
    # Order by chunk count descending
    for doc_id, _ in doc_chunk_counts.most_common():
        if doc_id not in critique_stores:
            continue
        for section_crit in critique_stores[doc_id].section_questions:
            if section_crit.section_id in doc_section_map[doc_id]:
                active_questions.extend(section_crit.questions)
    
    # Step 4: Sort by priority within each group
    active_questions.sort(key=lambda q: q.priority)
    
    return active_questions
```

**Expected active question counts:**

| Scenario | Total questions in store | After provenance filter | After trigger filter |
|----------|------------------------|------------------------|---------------------|
| Single doc (HP guide) | 10-15 | 4-6 | 2-4 |
| Single doc (PSA) | 24-30 | 8-12 | 4-8 |
| Multi-doc (PSA + Pro Supp) | 42-48 | 12-18 | 5-10 |

### 6.3 Gap→Query Translation

When a critique question identifies a gap, the gap description must be **converted into a retrieval query**. These are structurally different:

- Gap: *"The CAUTION about not holding the power button for more than 4 seconds during standby resume is missing from the answer."*
- Query: *"power button standby resume caution data loss four seconds"*

The translation prompt forces a concise, keyword-rich output:

```
Given this gap in an answer: {gap_description}
Convert it into a 5-10 word search query targeting the missing information.
Return ONLY the query string, nothing else.
```

### 6.4 Best-Answer Selection

Track `(answer, confidence_score)` at every iteration. On loop exit, return `argmax(confidence_score)`:

```python
class AnswerTracker:
    """Track answers across critique rounds, return the best one."""
    
    def __init__(self):
        self.history: list[tuple[str, float, int]] = []  # (answer, score, round)
    
    def record(self, answer: str, score: float, round_num: int):
        self.history.append((answer, score, round_num))
    
    @property
    def best(self) -> tuple[str, float, int]:
        return max(self.history, key=lambda x: x[1])
    
    @property
    def improved(self) -> bool:
        """Did any iteration improve over the initial answer?"""
        return len(self.history) > 1 and self.best[1] > self.history[0][1]
```

### 6.5 Deliverables

| File | Action | Description |
|------|--------|-------------|
| `backend/retrieval/critique_merger.py` | **CREATE** | ~150 lines. Provenance-filtered question merging. |
| `backend/retrieval/critique_loop.py` | MODIFY | Add gap→query translation, best-answer tracking, multi-doc support. |
| `backend/retrieval/critique_prompts.py` | MODIFY | Add gap→query translation prompt. |
| `tests/test_phase9_multi_doc_critique.py` | **CREATE** | ~300 lines. Unit + integration tests. |

### 6.6 Implementation Steps

**Step 9.3.1: Create `critique_merger.py`**

Implement `merge_critique_questions()` as specified in §6.2.

**Step 9.3.2: Add gap→query translation to `critique_prompts.py`**

```python
GAP_TO_QUERY_PROMPT = """
Given this gap in an answer: {gap_description}
The original user question was: {user_query}
Convert the gap into a 5-10 word search query targeting the missing information.
Return ONLY the query string, nothing else.
"""
```

**Step 9.3.3: Add `AnswerTracker` to `critique_loop.py`**

Wire into the main loop — `tracker.record()` after each re-synthesis. On exit, `tracker.best` returns the highest-confidence answer.

**Step 9.3.4: Wire merger into critique loop entry point**

```python
# In critique_loop.py:
def _load_and_merge_questions(self, retrieved_chunks):
    """Load critique_questions.json for each retrieved doc, merge."""
    critique_stores = {}
    for doc_id in {c["doc_id"] for c in retrieved_chunks}:
        critique = self.question_generator.load(doc_id, self.kts_path)
        if critique:
            critique_stores[doc_id] = critique
    
    return merge_critique_questions(retrieved_chunks, critique_stores)
```

**Step 9.3.5: Confidence-based early exit for tail questions**

After processing all doc-level and high-chunk-count section questions: if `confidence > 0.90` and only low-chunk-count doc's questions remain → exit early.

```python
# Inside the critique inner loop:
if (current_score > 0.90 and 
    all(q.source_doc_chunk_count <= 1 for q in remaining_questions)):
    break  # tail questions from minor docs — not worth another round
```

**Step 9.3.6: Write tests and run regression**

See Testing Plan §2.3 for full test matrix.

### 6.7 Rollback Plan

If multi-doc merging causes issues, fall back to **single-doc mode**: only use critique questions from the doc with the most retrieved chunks. Set `critique_multi_doc_enabled = False` in settings.

---

## 7. End-to-End Data Flow

```
INGESTION TIME (Inc 9.1)
═══════════════════════════════════════════════════════════
  User clicks "Ingest Source Folder"
    → crawl → ingest → chunk → embed → graph build
    → [NEW] critique_question_generator.generate(full_doc_text, sections)
    → saves .kts/documents/{doc_id}/critique_questions.json
    → ingestion complete

QUERY TIME (Inc 9.2 + 9.3)
═══════════════════════════════════════════════════════════
  User: @kts /search "computer won't restart after pressing power button"
    
  Step 1: Retrieval (existing Phase 6/8 pipeline)
    → chunks retrieved (3-5 chunks, confidence 0.96)
    → doc_type vote → KTS Support mode
  
  Step 2: Initial Answer (user's selected model)
    → Claude Opus generates A₀ from chunks + KTS Support prompt
  
  Step 3: Load Critique Questions (Inc 9.3 merger)
    → For each doc_id in retrieved chunks:
         load critique_questions.json
    → Provenance-filter: keep questions for retrieved sections only
    → Trigger pre-filter: skip questions whose keywords don't match chunks
    → Order: doc-level → high-chunk-count → low-chunk-count
    → Active set: ~5 questions
  
  Step 4: Keyword Safety Net (deterministic, no LLM)
    → Check: source has CAUTION → answer has CAUTION? 
    → If missing → inject synthetic gap before critique loop starts
  
  Step 5: Directed Critique Loop (Inc 9.2, fixed model)
    → for round in 1..3:
         for Q in active_questions:
           trigger_matches(Q, chunks)? → if no, skip
           critiqueModel.evaluate(Q, answer) → {"pass": true/false, "gap": ...}
           if gap found:
             re_query = critiqueModel.translate_gap(gap)
             new_chunks = retrieve(re_query)
             answer = generationModel.synthesize(query, answer, new_chunks)
             tracker.record(answer, confidence)
             RESTART from Q₁  ← full regression
         all passed → CONVERGED → EXIT
  
  Step 6: Best Answer Selection
    → return tracker.best (highest confidence across all rounds)
  
  Step 7: Stream to User
    → markdown stream with mode indicator, citations, reasoning trace
    → trace now includes: "critique_rounds: 2, questions_evaluated: 8, 
       gaps_found: 1, re-queries: 1"
```

---

## 8. Configuration Parameters

| Parameter | Default | Env Override | Description |
|-----------|---------|-------------|-------------|
| `critique_generation_enabled` | `True` | `KTS_CRITIQUE_GEN_ENABLED` | Generate questions at ingest time |
| `critique_generator_model` | `"gpt-4.1"` | `KTS_CRITIQUE_GEN_MODEL` | Model for ingest-time question generation |
| `critique_loop_enabled` | `True` | `KTS_CRITIQUE_LOOP_ENABLED` | Enable directed critique at query time |
| `critique_model` | `"gpt-4.1"` | `KTS_CRITIQUE_MODEL` | Fixed model for critique evaluation |
| `critique_max_rounds` | `3` | `KTS_CRITIQUE_MAX_ROUNDS` | Maximum critique-fix-restart cycles |
| `critique_restart_on_gap` | `True` | `KTS_CRITIQUE_RESTART` | Restart from Q₁ after each fix |
| `critique_multi_doc_enabled` | `True` | `KTS_CRITIQUE_MULTI_DOC` | Use questions from all retrieved docs |
| `critique_confidence_exit` | `0.90` | `KTS_CRITIQUE_CONFIDENCE_EXIT` | Early exit threshold for tail questions |
| `critique_max_questions_per_doc` | `15` | `KTS_CRITIQUE_MAX_Q_PER_DOC` | Cap on questions per document |

---

## 9. Dependencies and Prerequisites

| Prerequisite | Status | Notes |
|-------------|--------|-------|
| Phase 8 Inc 8 (iterative loop) | ✅ Designed | Not yet implemented — Phase 9 supersedes |
| Phase 6 DualVectorStore ingestion | ✅ Built | Section/item metadata includes doc_type |
| `critique_questions.json` storage | To implement | Inc 9.1 |
| VS Code LM API `selectChatModels` | ✅ Confirmed | Same pattern as `image_describer.js` |
| GPT-4.1 access (fixed critique model) | ✅ Available | No rate limits at firm |
| `.kts/documents/{doc_id}/` directory | ✅ Exists | Already used for image storage |
| Re-ingestion of all sources | Required | After 9.1 to generate critique questions |

---

## 10. Success Criteria

| Criterion | Measurement | Target |
|-----------|------------|--------|
| HP guide CAUTION preservation | Manual test: GPT-4.1 with critique loop | ✅ CAUTION included |
| PSA definition chain completeness | Golden query: "Current Interest" | ≥90% nested terms resolved |
| False gap rate (multi-doc) | Automated: count gaps from unretrieved sections | < 5% |
| Loop convergence within max_rounds | Automated: track round count distribution | ≥80% converge round ≤ 2 |
| Best-answer vs. initial-answer | A/B on golden set | best_answer ≥ initial_answer in ≥90% |
| Critique question quality | Manual review of 10 docs' generated questions | ≥80% judged relevant |
| Ingestion latency overhead | Timer: ingest with vs. without critique gen | < 5s per document |
| Query latency | Timer: end-to-end with critique loop | < 15s median (3-round max) |
| Existing test suite passes | pytest + mocha | Zero regressions |
