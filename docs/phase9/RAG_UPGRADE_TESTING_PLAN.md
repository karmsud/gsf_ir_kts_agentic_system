# Phase 9: Directed Critique RAG — Testing Plan

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Testing Philosophy

Phase 9 testing follows a **5-layer approach** consistent with Phase 8:

| Layer | What | How | Volume |
|-------|------|-----|--------|
| 1. Unit | Individual functions in isolation | pytest, mocked LLM calls | ~60 tests |
| 2. Integration | Component interactions (generator → store → loop) | pytest with real file I/O, mocked LLM | ~30 tests |
| 3. End-to-End | Full ingest → critique gen → query → critique loop | pytest with real LLM (optional), real ChromaDB | ~15 tests |
| 4. Golden Query | Known queries with known expected answers | Automated scoring against golden answers | ~20 queries |
| 5. Regression | Existing test suite passes after all changes | pytest + mocha | All existing |

**Phase 9 adds a unique 6th layer:**

| Layer | What | How | Volume |
|-------|------|-----|--------|
| 6. Comparative | Same query, with vs. without critique loop | A/B scoring on golden set | ~20 queries |

### 1.1 Test File Organization

```
tests/
├── test_phase9_critique_gen.py         # Inc 9.1: question generation
├── test_phase9_critique_loop.py        # Inc 9.2: directed critique loop
├── test_phase9_multi_doc_critique.py   # Inc 9.3: multi-doc merging
├── test_phase9_integration.py          # Cross-increment integration
├── test_phase9_comparative.py          # A/B: with loop vs. without
└── golden_queries_phase9.json          # Golden query definitions
```

---

## 2. Test Matrices by Increment

### 2.1 Increment 9.1: Ingestion-Time Critique Question Generation

**File:** `tests/test_phase9_critique_gen.py`

#### 2.1.1 Unit Tests — CritiqueQuestionGenerator

| # | Test | Input | Expected | Priority |
|---|------|-------|----------|----------|
| 1 | `test_generate_returns_valid_schema` | Mock LLM returns well-formed JSON | `DocCritique` with all required fields | P0 |
| 2 | `test_generate_handles_invalid_json` | Mock LLM returns malformed JSON | Falls back to `DEFAULT_QUESTIONS` | P0 |
| 3 | `test_generate_handles_empty_response` | Mock LLM returns empty string | Falls back to `DEFAULT_QUESTIONS` | P0 |
| 4 | `test_generate_truncates_excess_questions` | Mock LLM returns 25 questions for one section | Truncated to `max_questions_per_doc` (15) | P1 |
| 5 | `test_generate_for_troubleshoot_doc` | HP guide full text + sections | Questions include CAUTION/WARNING check | P0 |
| 6 | `test_generate_for_governing_doc` | PSA full text + sections | Questions include defined term check | P0 |
| 7 | `test_generate_for_supplement_doc` | Pro Supp full text + sections | Questions include amendment reference check | P1 |
| 8 | `test_generate_respects_doc_type` | Different doc_types | Questions differ meaningfully per doc_type | P1 |
| 9 | `test_generate_includes_trigger_keywords` | Any doc | Every non-"always" question has ≥1 trigger keyword | P0 |
| 10 | `test_generate_includes_section_ids` | Doc with 3 sections | Section questions tagged to correct section_ids | P0 |

#### 2.1.2 Unit Tests — Validation

| # | Test | Input | Expected | Priority |
|---|------|-------|----------|----------|
| 11 | `test_validate_rejects_non_question` | Question without "?" at end | Validation error returned | P1 |
| 12 | `test_validate_rejects_invalid_trigger_logic` | `trigger_logic: "sometimes"` | Validation error returned | P0 |
| 13 | `test_validate_rejects_missing_keywords` | `trigger_logic: "any_in_source"` + empty keywords | Validation error returned | P0 |
| 14 | `test_validate_accepts_always_no_keywords` | `trigger_logic: "always"` + empty keywords | No validation errors | P0 |
| 15 | `test_validate_accepts_well_formed_critique` | Complete valid DocCritique | Empty error list | P0 |

#### 2.1.3 Unit Tests — Storage

| # | Test | Input | Expected | Priority |
|---|------|-------|----------|----------|
| 16 | `test_save_creates_json_file` | Valid DocCritique + temp path | File exists at expected path | P0 |
| 17 | `test_save_overwrites_existing` | Save twice to same path | Second version persisted | P1 |
| 18 | `test_load_returns_critique` | Previously saved DocCritique | Loaded object matches saved | P0 |
| 19 | `test_load_returns_none_if_missing` | Non-existent doc_id | Returns `None` | P0 |
| 20 | `test_load_handles_corrupted_json` | Invalid JSON at expected path | Returns `None` + logs warning | P1 |

#### 2.1.4 Unit Tests — Context Length Handling

| # | Test | Input | Expected | Priority |
|---|------|-------|----------|----------|
| 21 | `test_prepare_short_doc_returns_full` | 5-page doc (< max_tokens) | Full text returned | P1 |
| 22 | `test_prepare_long_doc_returns_summary` | 200-page PSA (> max_tokens) | Structured summary with sections | P1 |
| 23 | `test_prepare_summary_includes_all_sections` | 15-section doc | All 15 section titles in summary | P1 |

#### 2.1.5 Unit Tests — Default Library

| # | Test | Input | Expected | Priority |
|---|------|-------|----------|----------|
| 24 | `test_defaults_exist_for_governing_doc` | `DEFAULT_QUESTIONS["GOVERNING_DOC"]` | ≥2 questions returned | P0 |
| 25 | `test_defaults_exist_for_troubleshoot` | `DEFAULT_QUESTIONS["TROUBLESHOOT"]` | ≥2 questions returned | P0 |
| 26 | `test_defaults_exist_for_supplement` | `DEFAULT_QUESTIONS["SUPPLEMENT"]` | ≥1 question returned | P1 |
| 27 | `test_defaults_have_valid_schema` | All default questions | Pass validation | P0 |

#### 2.1.6 Integration Tests — Ingestion Pipeline

| # | Test | Input | Expected | Priority |
|---|------|-------|----------|----------|
| 28 | `test_ingestion_generates_critique_file` | Ingest HP guide with critique enabled | `critique_questions.json` exists | P0 |
| 29 | `test_ingestion_skips_when_disabled` | Ingest with `critique_generation_enabled=False` | No `critique_questions.json` | P0 |
| 30 | `test_ingestion_uses_configured_model` | Config: `critique_generator_model = "gpt-4o"` | LLM call uses gpt-4o | P1 |

---

### 2.2 Increment 9.2: Directed Sequential Critique Loop

**File:** `tests/test_phase9_critique_loop.py`

#### 2.2.1 Unit Tests — Trigger Pre-Filter

| # | Test | Input | Expected | Priority |
|---|------|-------|----------|----------|
| 1 | `test_trigger_always_returns_true` | `trigger_logic="always"`, any chunks | `True` | P0 |
| 2 | `test_trigger_any_matches_single` | `["CAUTION"]`, chunk contains "CAUTION" | `True` | P0 |
| 3 | `test_trigger_any_no_match` | `["CAUTION"]`, chunk has no "CAUTION" | `False` | P0 |
| 4 | `test_trigger_any_case_insensitive` | `["caution"]`, chunk has "CAUTION" | `True` | P0 |
| 5 | `test_trigger_all_requires_all` | `["CAUTION", "WARNING"]`, chunk has only "CAUTION" | `False` | P0 |
| 6 | `test_trigger_all_both_present` | `["CAUTION", "WARNING"]`, both in chunk | `True` | P0 |
| 7 | `test_trigger_empty_chunks` | Any question, empty chunk list | `False` (except "always") | P1 |

#### 2.2.2 Unit Tests — Keyword Safety Net

| # | Test | Input | Expected | Priority |
|---|------|-------|----------|----------|
| 8 | `test_safety_detects_missing_caution` | Source has "CAUTION", answer doesn't | 1 synthetic gap returned | P0 |
| 9 | `test_safety_passes_when_present` | Both source and answer have "CAUTION" | Empty list | P0 |
| 10 | `test_safety_detects_multiple_missing` | Source has "CAUTION" + "WARNING", answer has neither | 2 synthetic gaps | P0 |
| 11 | `test_safety_ignores_absent_keywords` | Source has no safety keywords | Empty list | P1 |
| 12 | `test_safety_detects_warning_symbol` | Source has "⚠", answer doesn't | 1 synthetic gap | P1 |

#### 2.2.3 Unit Tests — Single Critique Evaluation

| # | Test | Input | Expected | Priority |
|---|------|-------|----------|----------|
| 13 | `test_critique_pass_returns_true` | Mock LLM returns `{"pass": true}` | Pass verdict | P0 |
| 14 | `test_critique_fail_returns_gap` | Mock LLM returns `{"pass": false, "gap_description": "..."}` | Fail verdict with description | P0 |
| 15 | `test_critique_invalid_json_treated_as_pass` | Mock LLM returns garbage | Treated as pass (optimistic) | P0 |
| 16 | `test_critique_timeout_treated_as_pass` | Mock LLM raises timeout | Treated as pass | P1 |

#### 2.2.4 Unit Tests — Gap→Query Translation

| # | Test | Input | Expected | Priority |
|---|------|-------|----------|----------|
| 17 | `test_translate_returns_query_string` | Gap about missing CAUTION | 5-10 word query string | P0 |
| 18 | `test_translate_fallback_on_invalid` | Mock LLM returns 100-word essay | Keyword extraction fallback used | P1 |
| 19 | `test_translate_fallback_on_empty` | Mock LLM returns "" | Keyword extraction fallback used | P1 |
| 20 | `test_keyword_extract_basic` | "The CAUTION about data loss..." | Contains "CAUTION", "data", "loss" | P1 |

#### 2.2.5 Unit Tests — Answer Tracker

| # | Test | Input | Expected | Priority |
|---|------|-------|----------|----------|
| 21 | `test_tracker_returns_highest_confidence` | Round 0: 0.7, Round 1: 0.9, Round 2: 0.85 | Returns Round 1 answer | P0 |
| 22 | `test_tracker_improved_true` | Round 0: 0.7, Round 1: 0.9 | `improved == True` | P0 |
| 23 | `test_tracker_improved_false` | Round 0: 0.9, Round 1: 0.8 | `improved == False` | P0 |
| 24 | `test_tracker_regression_detected` | Round 0: 0.8, Round 1: 0.9, Round 2: 0.7 | `regression_detected == True` | P1 |
| 25 | `test_tracker_single_entry` | One answer recorded | Returns that answer; `improved == False` | P0 |

#### 2.2.6 Integration Tests — Full Critique Loop

| # | Test | Input | Expected | Priority |
|---|------|-------|----------|----------|
| 26 | `test_loop_converges_all_pass` | 3 questions, all pass | `converged=True`, `rounds_executed=1` | P0 |
| 27 | `test_loop_one_gap_fix_converge` | Q1 pass, Q2 fail (then pass), Q3 pass | `rounds_executed=2`, `gaps_found=1` | P0 |
| 28 | `test_loop_restarts_from_q1` | Q3 fails → verify Q1 re-evaluated in round 2 | Q1 evaluated in both rounds | P0 |
| 29 | `test_loop_caps_at_max_rounds` | Every round has a gap | `rounds_executed=max_rounds`, `converged=False` | P0 |
| 30 | `test_loop_returns_best_not_last` | Round 1: 0.9, Round 2: 0.7 | Returns Round 1 answer (0.9) | P0 |
| 31 | `test_loop_safety_gaps_evaluated_first` | 2 safety gaps + 3 regular questions | Safety gaps checked before questions | P1 |
| 32 | `test_loop_skip_filtered_questions` | 5 questions, 2 trigger-filtered out | Only 3 questions evaluated | P1 |
| 33 | `test_loop_early_exit_high_confidence` | Confidence 0.95, only tail questions remain | Loop exits early | P1 |
| 34 | `test_loop_disabled_returns_initial` | `critique_loop_enabled=False` | Returns initial answer unchanged | P0 |
| 35 | `test_loop_critique_model_failure_graceful` | Critique model raises exception | Returns initial answer, logs warning | P0 |

#### 2.2.7 Integration Tests — Dual-Model Architecture

| # | Test | Input | Expected | Priority |
|---|------|-------|----------|----------|
| 36 | `test_critique_uses_fixed_model` | Config: `critique_model="gpt-4.1"` | Critique calls use gpt-4.1 | P0 |
| 37 | `test_synthesis_uses_user_model` | User selected Claude Opus | Re-synthesis uses Opus | P0 |
| 38 | `test_models_are_independent` | Different models configured | Critique model ≠ generation model | P0 |

---

### 2.3 Increment 9.3: Multi-Doc Provenance-Filtered Merging

**File:** `tests/test_phase9_multi_doc_critique.py`

#### 2.3.1 Unit Tests — Provenance Filtering

| # | Test | Input | Expected | Priority |
|---|------|-------|----------|----------|
| 1 | `test_single_doc_single_section` | 3 chunks from doc_A/sec001 | Only sec001 questions active | P0 |
| 2 | `test_single_doc_multi_section` | Chunks from sec001 + sec003 | sec001 + sec003 questions; sec002 excluded | P0 |
| 3 | `test_multi_doc_provenance_filter` | Doc A/sec001 + Doc B/sec002 | Only sec001 (A) + sec002 (B) questions | P0 |
| 4 | `test_doc_level_always_included` | 2 docs retrieved | Doc-level questions from both docs | P0 |
| 5 | `test_unretrieved_sections_excluded` | Doc A has 4 sections, only sec001 retrieved | sec002, sec003, sec004 questions excluded | P0 |
| 6 | `test_no_critique_store_for_doc` | doc_C has no critique_questions.json | Uses DEFAULT_QUESTIONS for doc_C's type | P1 |

#### 2.3.2 Unit Tests — Ordering

| # | Test | Input | Expected | Priority |
|---|------|-------|----------|----------|
| 7 | `test_doc_level_before_section` | Mix of doc and section questions | Doc-level questions appear first | P0 |
| 8 | `test_high_chunk_doc_first` | Doc A: 5 chunks, Doc B: 1 chunk | Doc A section questions before Doc B | P0 |
| 9 | `test_within_group_priority_order` | Section questions with priority 1, 3, 2 | Sorted: 1, 2, 3 | P1 |
| 10 | `test_equal_chunk_count_stable_order` | Two docs each with 2 chunks | Order is stable (no random shuffling) | P1 |

#### 2.3.3 Unit Tests — Deduplication

| # | Test | Input | Expected | Priority |
|---|------|-------|----------|----------|
| 11 | `test_duplicate_questions_deduped` | Same question text from two docs | Kept once (higher priority wins) | P1 |
| 12 | `test_similar_not_deduped` | Slightly different question wording | Both kept | P2 |

#### 2.3.4 Unit Tests — Confidence-Based Early Exit

| # | Test | Input | Expected | Priority |
|---|------|-------|----------|----------|
| 13 | `test_early_exit_high_confidence_tail` | Confidence 0.95, remaining from 1-chunk doc | `should_early_exit() == True` | P0 |
| 14 | `test_no_exit_low_confidence` | Confidence 0.70, remaining from 1-chunk doc | `should_early_exit() == False` | P0 |
| 15 | `test_no_exit_high_confidence_important` | Confidence 0.95, remaining from 5-chunk doc | `should_early_exit() == False` | P0 |

#### 2.3.5 Integration Tests — Multi-Doc Full Loop

| # | Test | Input | Expected | Priority |
|---|------|-------|----------|----------|
| 16 | `test_multi_doc_loop_evaluates_both` | Chunks from HP guide + PSA | Questions from both docs evaluated | P0 |
| 17 | `test_multi_doc_gap_in_secondary_doc` | Primary doc passes, secondary has gap | Gap fixed with re-retrieval from secondary | P1 |
| 18 | `test_multi_doc_early_exit_on_tail` | Primary doc done, secondary is 1-chunk | Early exit after primary questions pass | P1 |
| 19 | `test_false_gap_rate_below_threshold` | Simulate multi-doc with known provenance | False gap rate < 5% | P0 |

---

## 3. Golden Query Test Suite

### 3.1 Golden Query Format

```json
{
    "id": "gq_phase9_001",
    "query": "computer failed to restart even after pressing the power button",
    "source_docs": ["source_4/TS_GUIDE.pdf"],
    "expected_mode": "KTS Support",
    "expected_doc_type": "TROUBLESHOOT",
    "critique_checks": {
        "caution_preserved": true,
        "steps_ordered_by_severity": true,
        "page_refs_cited": true,
        "post_error_codes_mentioned": false
    },
    "expected_critique_behavior": {
        "min_questions_evaluated": 3,
        "expected_gaps_found": 0,
        "expected_converge_round": 1
    },
    "min_confidence": 0.85,
    "notes": "Primary test case from GPT-4.1 vs Opus experiment"
}
```

### 3.2 Golden Queries

| ID | Query | Doc Type | Key Critique Check |
|----|-------|----------|-------------------|
| gq_001 | computer failed to restart after pressing power button | TROUBLESHOOT | CAUTION preserved, steps ordered |
| gq_002 | What is the Closing Date | GOVERNING_DOC | Full definition with nested terms |
| gq_003 | Define Current Interest under the PSA | GOVERNING_DOC | Definition chain ≥3 levels deep |
| gq_004 | computer locked up and is not responding | TROUBLESHOOT | LED diagnostic check mentioned |
| gq_005 | What are the Servicer's obligations under Section 3.01 | GOVERNING_DOC | Cross-references resolved |
| gq_006 | HP computer won't turn on | TROUBLESHOOT | Force-off → LED → Appendix A sequence |
| gq_007 | What happens on an Event of Default | GOVERNING_DOC | All capitalized EoD sub-terms defined |
| gq_008 | blank screen after power on | TROUBLESHOOT | POST error reference, not just power cycle |
| gq_009 | What is Realized Loss | GOVERNING_DOC | Formula components enumerated |
| gq_010 | computer beeps but doesn't start | TROUBLESHOOT | Appendix A beep code reference |
| gq_011 | (multi-doc) obligations under supplement vs PSA | GOVERNING_DOC | Both docs' critique questions used |
| gq_012 | (multi-doc) compare troubleshoot steps for locked screen vs no power | TROUBLESHOOT | Two sections' questions merged |
| gq_013 | what is the Available Funds waterfall | GOVERNING_DOC | Nested terms: Available Funds → sub-terms |
| gq_014 | computer makes noise but screen is blank | TROUBLESHOOT | Fan vs. POST vs. power supply distinction |
| gq_015 | Define Certificateholder and their rights | GOVERNING_DOC | Cross-section references (Voting, Distributions) |
| gq_016 | (typo) compter wont start after presing button | TROUBLESHOOT | Semantic tolerance + critique still catches gaps |
| gq_017 | What is the Distribution Date calculation | GOVERNING_DOC | Date formula + nested terms |
| gq_018 | USB device not recognized | TROUBLESHOOT | Different section from power issues |
| gq_019 | (vague) tell me about the PSA | GOVERNING_DOC | Broad query → critique catches missing specifics |
| gq_020 | (multi-doc) What provisions apply to both PSA and supplement | GOVERNING_DOC | Multi-doc provenance filtering tested |

### 3.3 Comparative Scoring

Each golden query is evaluated **twice**: once with critique loop disabled, once with critique loop enabled. The scoring function:

```python
def score_golden_query(result: dict, golden: dict) -> dict:
    """Score a query result against golden expectations."""
    scores = {}
    
    # Critique preservation checks
    for check_name, expected in golden["critique_checks"].items():
        actual = evaluate_check(check_name, result["answer"])
        scores[check_name] = actual == expected
    
    # Confidence threshold
    scores["confidence_met"] = result["confidence"] >= golden["min_confidence"]
    
    # Critique behavior (only when loop enabled)
    if "critique_trace" in result:
        trace = result["critique_trace"]
        behavior = golden["expected_critique_behavior"]
        scores["questions_evaluated"] = (
            trace["questions_evaluated"] >= behavior["min_questions_evaluated"]
        )
        scores["converge_round"] = (
            trace["rounds_executed"] <= behavior["expected_converge_round"] + 1
        )
    
    return scores
```

---

## 4. Test Infrastructure

### 4.1 Mock LLM for Unit Tests

```python
class MockCritiqueLLM:
    """Configurable mock LLM for critique loop testing."""
    
    def __init__(self, responses: dict[str, str]):
        """
        responses: mapping of question_id → JSON response string.
        If a question_id is not in the map, returns '{"pass": true}'.
        """
        self.responses = responses
        self.call_log = []
    
    def generate(self, prompt: str) -> str:
        self.call_log.append(prompt)
        
        # Match question ID from prompt
        for q_id, response in self.responses.items():
            if q_id in prompt:
                return response
        
        return '{"pass": true}'
    
    @property
    def call_count(self):
        return len(self.call_log)
```

### 4.2 Fixture: HP Guide Critique Questions

```python
@pytest.fixture
def hp_guide_critique():
    """Pre-built critique questions for HP Troubleshooting Guide."""
    return DocCritique(
        doc_id="doc_3842400",
        doc_type="TROUBLESHOOT",
        generated_at="2026-02-18T17:45:00Z",
        generator_model="gpt-4.1",
        doc_level_questions=[
            CritiqueQuestion(
                id="dq_001",
                question="Does the answer preserve all CAUTION annotations?",
                trigger_keywords=["CAUTION", "WARNING"],
                trigger_logic="any_in_source",
                priority=1
            ),
        ],
        section_questions=[
            SectionCritique(
                section_id="sec000",
                section_title="Solving General Problems",
                questions=[
                    CritiqueQuestion(
                        id="sq_001",
                        question="Is the Problem→Cause→Solution structure preserved?",
                        trigger_keywords=["Problem", "Cause", "Solution"],
                        trigger_logic="all_in_source",
                        priority=1
                    ),
                    CritiqueQuestion(
                        id="sq_002",
                        question="Are steps ordered by severity (force-off first)?",
                        trigger_keywords=["power button", "restart"],
                        trigger_logic="any_in_source",
                        priority=2
                    ),
                ],
                rubric={
                    "pattern": "computer will not start|locked up|power button",
                    "expected_structure": [
                        "Force-off procedure",
                        "Power LED diagnostic",
                        "Appendix A reference",
                        "Escalation path"
                    ]
                }
            ),
        ]
    )
```

### 4.3 Fixture: PSA Critique Questions

```python
@pytest.fixture
def psa_critique():
    """Pre-built critique questions for PSA Governing Document."""
    return DocCritique(
        doc_id="doc_5054059",
        doc_type="GOVERNING_DOC",
        generated_at="2026-02-18T17:45:00Z",
        generator_model="gpt-4.1",
        doc_level_questions=[
            CritiqueQuestion(
                id="dq_001",
                question="Are all Capitalized Terms traced to their definitions?",
                trigger_keywords=[],
                trigger_logic="always",
                priority=1
            ),
        ],
        section_questions=[
            SectionCritique(
                section_id="sec001",
                section_title="Definitions",
                questions=[
                    CritiqueQuestion(
                        id="sq_001",
                        question="Is the full definition chain traced for nested terms?",
                        trigger_keywords=["means", "shall mean"],
                        trigger_logic="any_in_source",
                        priority=1
                    ),
                ],
                rubric=None
            ),
        ]
    )
```

### 4.4 Pytest Markers

```python
# conftest.py additions
import pytest

def pytest_configure(config):
    config.addinivalue_line("markers", "phase9: Phase 9 Directed Critique tests")
    config.addinivalue_line("markers", "critique_gen: Increment 9.1 tests")
    config.addinivalue_line("markers", "critique_loop: Increment 9.2 tests")
    config.addinivalue_line("markers", "multi_doc: Increment 9.3 tests")
    config.addinivalue_line("markers", "comparative: A/B comparison tests")
    config.addinivalue_line("markers", "requires_llm: Requires live LLM API")
```

Run increment-specific tests:
```bash
pytest -m critique_gen -v       # Inc 9.1 only
pytest -m critique_loop -v      # Inc 9.2 only  
pytest -m multi_doc -v          # Inc 9.3 only
pytest -m phase9 -v             # All Phase 9
pytest -m "phase9 and not requires_llm" -v  # Phase 9 without live LLM
```

---

## 5. Performance Testing

### 5.1 Ingestion-Time Latency

| Test | Method | Target |
|------|--------|--------|
| Critique generation per doc (HP guide) | Timer around `generate()` | < 3s |
| Critique generation per doc (PSA) | Timer around `generate()` | < 5s |
| Critique save/load round-trip | Timer around `save()` + `load()` | < 10ms |
| Full ingestion with critique gen | Timer around full ingest pipeline | < 10% overhead vs. without |

### 5.2 Query-Time Latency

| Test | Method | Target | 
|------|--------|--------|
| Trigger pre-filter (15 questions) | Timer around `trigger_matches()` loop | < 1ms |
| Keyword safety check | Timer around `keyword_safety_check()` | < 1ms |
| Single critique LLM call | Timer around one `critique_llm.generate()` | < 500ms |
| Full critique loop (converge round 1) | Timer around `DirectedCritiqueLoop.run()` | < 5s |
| Full critique loop (3 rounds) | Timer around `DirectedCritiqueLoop.run()` | < 15s |
| Question merging (3 docs) | Timer around `merge_critique_questions()` | < 5ms |

### 5.3 Token Cost Tracking

```python
class TokenCostTracker:
    """Track LLM token usage during critique operations."""
    
    def __init__(self):
        self.calls = []
    
    def record(self, model: str, input_tokens: int, output_tokens: int):
        self.calls.append({
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
        })
    
    @property
    def total_input_tokens(self):
        return sum(c["input_tokens"] for c in self.calls)
    
    @property
    def total_output_tokens(self):
        return sum(c["output_tokens"] for c in self.calls)
    
    @property
    def estimated_cost(self):
        """Estimate cost at GPT-4.1 rates."""
        return (self.total_input_tokens * 0.002 + 
                self.total_output_tokens * 0.008) / 1000
```

Target: critique overhead < $0.05 per query.

---

## 6. Regression Gates

Each increment must pass all gates before proceeding:

### 6.1 Inc 9.1 Gate

| Gate | Command | Threshold |
|------|---------|-----------|
| All existing tests pass | `pytest tests/ -v --tb=short` | 0 new failures |
| Inc 9.1 tests pass | `pytest -m critique_gen -v` | 100% pass |
| Ingestion latency acceptable | Performance test | < 5s per doc |
| Generated questions pass validation | `validate_critique_questions()` on 3 test docs | 0 validation errors |

### 6.2 Inc 9.2 Gate

| Gate | Command | Threshold |
|------|---------|-----------|
| All existing tests pass | `pytest tests/ -v --tb=short` | 0 new failures |
| Inc 9.2 tests pass | `pytest -m critique_loop -v` | 100% pass |
| HP guide CAUTION test | Golden query gq_001 with GPT-4.1 | CAUTION preserved |
| Query latency acceptable | Performance test | < 15s median |
| Feature flag works | Test with `critique_loop_enabled=False` | Identical to pre-9.2 behavior |

### 6.3 Inc 9.3 Gate

| Gate | Command | Threshold |
|------|---------|-----------|
| All existing tests pass | `pytest tests/ -v --tb=short` | 0 new failures |
| Inc 9.3 tests pass | `pytest -m multi_doc -v` | 100% pass |
| False gap rate | Automated test | < 5% |
| Multi-doc golden queries | gq_011, gq_012, gq_020 | All pass |
| Comparative improvement | A/B on full golden set | ≥ 90% improved or equal |

### 6.4 Final Gate (All Phase 9)

| Gate | Command | Threshold |
|------|---------|-----------|
| Full test suite | `pytest tests/ -v --tb=short` | 0 failures |
| Phase 9 tests | `pytest -m phase9 -v` | 100% pass |
| Mocha extension tests | `cd extension && npm test` | 100% pass |
| Comparative golden set | 20 golden queries, A/B | ≥ 18/20 improved |
| Build succeeds | `.\scripts\build_backend.ps1 -Clean` | Exit 0, exe runs |
| VSIX builds | `.\scripts\build_vsix.ps1 -Version "0.1.0"` | < 230 MB |

---

## 7. Test Data Requirements

### 7.1 Minimum Corpus for Testing

| Source | Doc Type | Purpose |
|--------|----------|---------|
| HP Troubleshooting Guide (source_4) | TROUBLESHOOT | Primary test doc — CAUTION preservation, step ordering |
| 2006HE1 PSA (source_1) | GOVERNING_DOC | Legal definition chains, cross-references |
| Prospectus Supplement (source_2) | SUPPLEMENT | Multi-doc merge testing with PSA |

### 7.2 Pre-Generated critique_questions.json for Testing

Testing can proceed **before** the LLM generator is implemented by using hand-crafted critique question files as fixtures. The fixtures in §4.2 and §4.3 serve this purpose. This enables Inc 9.2 and 9.3 testing to run in parallel with Inc 9.1 development.

---

## 8. Test Execution Summary

| Category | Est. Tests | Est. Runtime (no LLM) | Est. Runtime (with LLM) |
|----------|-----------|----------------------|------------------------|
| Inc 9.1 Unit | 27 | 2s | 30s (3 LLM calls) |
| Inc 9.1 Integration | 3 | 5s | 20s |
| Inc 9.2 Unit | 25 | 2s | N/A (all mocked) |
| Inc 9.2 Integration | 13 | 3s | 60s (loop iterations) |
| Inc 9.3 Unit | 15 | 1s | N/A (all mocked) |
| Inc 9.3 Integration | 4 | 2s | 45s |
| Golden Queries | 20 | N/A | 300s (20 queries × 15s) |
| Comparative | 20 | N/A | 600s (20 × 2 modes × 15s) |
| **Total** | **~127** | **~15s** | **~18 min** |
