# Phase D: Golden Answer Test Harness

**Created:** 2026-02-20  
**Status:** APPROVED — Ready for Implementation  
**Effort:** 2-3 hours  
**Priority:** P0 — Needed before ANY RAG changes (establishes baseline)

---

## 1. Problem Statement

### What We Have Now

Three test files that test **retrieval quality** (do the right chunks come back?):

| File | Tests | What It Measures |
|------|-------|------------------|
| `tests/golden_psa_2006he1.json` | 100 | Chunk retrieval: correct sections, must-include terms, top-1 constraints |
| `tests/golden_queries_v2.json` | 50 | IT corpus retrieval: keyphrase recall, entity recall, doc-type priority |
| `tests/psa_test_queries.json` | 20 | PSA entity/keyphrase recall from CLI backend |

These tests answer: **"Did we retrieve the right chunks?"**

They do NOT answer: **"Did we generate a useful answer?"**

### What We Need

An **end-to-end answer quality test suite** that:

1. Sends a question through the FULL pipeline (query expansion → retrieval → reranking → generation → critique)
2. Captures the final answer text the user sees
3. Scores the answer on 5 dimensions using LLM-as-judge
4. Compares before/after when we change ANY RAG technique
5. Runs in the dev host (F5 workflow) — no VSIX build required

### Why This Must Come First

Every other document in this redesign (settings simplification, prompt changes, RAG architecture ablation) changes the pipeline. Without answer-quality tests, we're flying blind:

- "Does the new conversational prompt produce better answers?" → Need golden tests
- "Does removing keyword-boost rerank hurt anything?" → Need golden tests
- "Does Self-RAG actually improve answers?" → Need golden tests

---

## 2. Test Architecture

### 2.1 Overview

```
tests/golden_answer_tests.json         ← 30 golden Q&A pairs with expected answers
tests/golden_answer_runner.js          ← Node.js runner using VS Code LM API
tests/golden_answer_scorer.js          ← LLM-as-judge scorer (5 dimensions)
tests/golden_answer_baseline.json      ← Captured baseline answers (before changes)
tests/golden_answer_results/           ← Timestamped result files
```

### 2.2 Flow

```
                    ┌─────────────────────────────────────┐
                    │  golden_answer_tests.json           │
                    │  30 questions + expected answers     │
                    └────────────────┬────────────────────┘
                                     │
                    ┌────────────────▼────────────────────┐
                    │  golden_answer_runner.js             │
                    │  For each question:                  │
                    │    1. Call @kts participant           │
                    │    2. Capture full answer text        │
                    │    3. Capture retrieved chunks        │
                    │    4. Capture timing/metadata         │
                    └────────────────┬────────────────────┘
                                     │
                    ┌────────────────▼────────────────────┐
                    │  golden_answer_scorer.js             │
                    │  For each (question, answer) pair:    │
                    │    1. LLM-as-judge scores 5 dims     │
                    │    2. Compare to baseline scores      │
                    │    3. Flag regressions                │
                    └────────────────┬────────────────────┘
                                     │
                    ┌────────────────▼────────────────────┐
                    │  golden_answer_results/              │
                    │  2026-02-20T14:30:00_results.json    │
                    │  - Per-question scores               │
                    │  - Aggregate by category             │
                    │  - Regressions vs baseline           │
                    └─────────────────────────────────────┘
```

---

## 3. Golden Questions (30 Total, 6 Categories)

### Category 1: Defined Terms (5 questions)

These test the system's ability to find and explain capitalized defined terms, including tracing definition chains.

| ID | Question | Key Expected Content |
|----|----------|---------------------|
| G01 | What does Distribution Date mean? | 25th of each month (or next Business Day), commencing February 2006. Should reference Business Day definition. |
| G02 | Define Certificateholder under this agreement. | Person in whose name a Certificate is registered in the Certificate Register. Should resolve Person → individual, corporation, partnership... |
| G03 | What is the Certificate Principal Balance? | Initial CPB reduced by distributions of principal, Realized Losses, Applied Realized Loss Amounts. Should mention it is per-class. |
| G04 | What does Current Interest mean for a Class A certificate? | Interest accrued on CPB during Accrual Period at Pass-Through Rate, plus recovered preferences, minus Prepayment Interest Shortfalls (net of Compensating Interest) and Relief Act Shortfalls. Should mention CE first-loss allocation. |
| G05 | Trace the full definition chain for Prepayment Interest Shortfall. | Must mention: Scheduled Payment, Stated Principal Balance, Mortgage Rate, and how the shortfall arises from prepayments reducing interest accrual. Should go at least 2 levels deep. |

### Category 2: Waterfall / Payment Priority (5 questions)

These test understanding of sequential payment logic and priority of distributions.

| ID | Question | Key Expected Content |
|----|----------|---------------------|
| G06 | Walk me through the principal distribution waterfall. | Sequential: Class A-1 → A-2 → ... → M classes (credit enhancement). Should reference Section 5.04 or 5.05. Must distinguish between principal and interest waterfalls. |
| G07 | How are interest payments distributed among certificate classes? | Interest current on Class A first, then Class M in order, then residual. Should mention Pass-Through Rate per class. |
| G08 | What happens when Realized Losses exceed subordination? | CE certificates absorb first. When depleted, losses allocate up to M classes in reverse order. Should reference Section 6.xx (or wherever loss allocation is). |
| G09 | In what order are funds applied from the Collection Account? | Trust fees, servicer fees, then waterfall. Should distinguish Available Funds, Distribution Account, Collection Account. |
| G10 | What is the priority between Class A-1 and Class A-2 for principal? | Sequential pay within A classes. A-1 fully paid before A-2 receives principal (unless simultaneous pay-down conditions). Should cite specific section. |

### Category 3: Statement to Certificateholders / Reporting (5 questions)

These test the system's ability to enumerate reporting requirements.

| ID | Question | Key Expected Content |
|----|----------|---------------------|
| G11 | What information must be included in the monthly statement to Certificateholders? | List of items: distributions, balances, delinquency data, loss data, prepayment speeds, certificate factors. Should reference Section 5.06. |
| G12 | When must the Securities Administrator deliver the statement? | On or before each Distribution Date (or within X business days). Should specify the entity responsible. |
| G13 | What is the certificate factor and where is it reported? | Ratio of current CPB to initial CPB for each class. Reported in the monthly statement per Section 5.06(b). |
| G14 | What reports must the Master Servicer provide to the Trustee? | Servicing reports, delinquency reports, REO reports. Should distinguish from Certificateholder statements. |
| G15 | Where are the forms for these reports specified? | Exhibits section (e.g., Exhibit H or similar). Should reference specific exhibit numbers. |

### Category 4: Key Dates and Deadlines (5 questions)

These test extraction of temporal information.

| ID | Question | Key Expected Content |
|----|----------|---------------------|
| G16 | What is the Closing Date for this deal? | March 30, 2006. Should come from definitions or preamble. |
| G17 | When is the Cut-off Date and why does it matter? | March 1, 2006. Determines which mortgage loans are included in the trust. Loans originated after this date are excluded. |
| G18 | What is the Record Date for determining Certificateholders? | Business Day before each Distribution Date. Determines who receives that month's distribution. |
| G19 | When can the optional termination (cleanup call) be exercised? | When aggregate pool balance falls below a threshold (typically 10% of initial). Should cite specific section and percentage. |
| G20 | What is the Accrual Period and how is it calculated? | Period from prior Distribution Date to current Distribution Date. Day count convention (30/360 or Actual/360). Should identify which convention this deal uses. |

### Category 5: Parties and Roles (5 questions)

These test identification of named parties and their responsibilities.

| ID | Question | Key Expected Content |
|----|----------|---------------------|
| G21 | Who are the main parties to this agreement? | Depositor, Master Servicer (EMC Mortgage Corporation), Trustee (LaSalle Bank), Securities Administrator. Should list at least 4 parties with their legal names. |
| G22 | What are the Master Servicer's key obligations? | Collect payments, advance delinquent payments (if required), maintain insurance, report to Trustee. Should reference Article III or IV. |
| G23 | Under what conditions can the Master Servicer be terminated? | Events of Default: failure to make required advances, bankruptcy, breach of representations uncured after notice period. Should cite specific section. |
| G24 | What is the Trustee's role in this transaction? | Holds the trust assets for benefit of Certificateholders. Fiduciary duty. Executes distribution waterfall. Prudent person standard. |
| G25 | Who is the Depositor and what did they contribute? | Bear Stearns Asset Backed Securities, Inc. Deposited the mortgage loans into the trust. Should reference the conveyance/transfer provisions. |

### Category 6: Conversational Follow-Ups (5 questions)

These test multi-turn conversation quality. Each question depends on a "prior answer" context.

| ID | Question | Prior Context | Key Expected Content |
|----|----------|--------------|---------------------|
| G26 | "Tell me more about that" | After G01 (Distribution Date) | Should elaborate on Distribution Date — perhaps Business Day definition, first Distribution Date, adjustment rules. Should NOT restart from scratch. |
| G27 | "What about for the M classes?" | After G07 (interest waterfall) | Should explain M class interest specifics — subordination, different Pass-Through Rates, sequential within M classes. |
| G28 | "Is that different from the interest waterfall?" | After G06 (principal waterfall) | Should compare/contrast principal vs interest distribution logic. Highlight that principal is sequential while interest may be pari passu within a class group. |
| G29 | "What happens if they don't?" | After G22 (Master Servicer obligations) | Should explain consequences of Master Servicer non-performance — Events of Default, successor servicer appointment, indemnification. |
| G30 | "When was it signed?" | After G21 (parties) | Should provide the execution date / effective date from the agreement. Likely March 30, 2006 (Closing Date). |

---

## 4. Expected Answer Format

Each golden test includes the question, the expected answer content, and scoring rubrics:

```json
{
  "test_id": "G01",
  "category": "defined_terms",
  "category_name": "Defined Terms",
  "question": "What does Distribution Date mean?",
  "prior_context": null,
  "expected_answer_contains": [
    "25th",
    "Business Day",
    "February 2006",
    "Section 1.01"
  ],
  "expected_answer_not_contains": [
    "I don't know",
    "not found in the documents"
  ],
  "expected_sections": ["Section 1.01", "Article I"],
  "ideal_answer_summary": "Distribution Date means the 25th day of each month (or the next Business Day if the 25th is not a Business Day), commencing in February 2006. Business Day means any day other than a Saturday, Sunday, or day on which banking institutions in New York are authorized to be closed.",
  "scoring_rubric": {
    "completeness": "Must include the date (25th), the Business Day fallback, the commencement month, and the section reference.",
    "accuracy": "All facts must match the PSA text. No invented dates or conditions.",
    "grounding": "Must cite Section 1.01 or Article I. Inline citations preferred.",
    "usability": "Answer should be immediately useful to a finance professional without needing to read more.",
    "no_hallucination": "No information beyond what is in the PSA. No general knowledge about distribution dates."
  }
}
```

---

## 5. LLM-as-Judge Scoring

### 5.1 Scoring Dimensions

Each answer is scored on 5 dimensions, each 1-5:

| Dimension | 1 (Fail) | 3 (Adequate) | 5 (Excellent) |
|-----------|----------|--------------|---------------|
| **Completeness** | Missing key facts | Has main answer, missing details | All expected facts present with supporting detail |
| **Accuracy** | Contains factual errors | Technically correct but imprecise | Precisely matches PSA text with correct citations |
| **Grounding** | No citations or references | Mentions document but no section | Inline citations to specific sections/clauses |
| **Usability** | Unusable without further research | Requires some additional lookup | Immediately actionable for a finance professional |
| **No-Hallucination** | Invents substantive facts | Minor embellishments beyond source | Strictly sourced from retrieved context |

### 5.2 Judge Prompt

```javascript
const JUDGE_PROMPT = `You are an expert judge evaluating the quality of a RAG system's answer about a structured-finance document (PSA — Pooling and Servicing Agreement).

## Question
{question}

## Expected Answer Content
{ideal_answer_summary}

## Must Contain
{expected_answer_contains}

## Must NOT Contain
{expected_answer_not_contains}

## System's Answer
{actual_answer}

## Scoring Rubric
{scoring_rubric}

Score the answer on each dimension from 1 to 5. Return ONLY a JSON object:

{
  "completeness": { "score": <1-5>, "reason": "<one sentence>" },
  "accuracy": { "score": <1-5>, "reason": "<one sentence>" },
  "grounding": { "score": <1-5>, "reason": "<one sentence>" },
  "usability": { "score": <1-5>, "reason": "<one sentence>" },
  "no_hallucination": { "score": <1-5>, "reason": "<one sentence>" },
  "overall": <1-5>,
  "critical_failures": ["<any critical issues>"]
}`;
```

### 5.3 Composite Score

```
overall_score = (completeness × 0.25) + (accuracy × 0.30) + (grounding × 0.20) 
              + (usability × 0.15) + (no_hallucination × 0.10)
```

Accuracy is weighted highest because a wrong answer is worse than an incomplete one.

### 5.4 Regression Detection

A change **regresses** a question if:
- Any dimension drops by ≥ 2 points
- The overall score drops by ≥ 1 point
- A `critical_failures` entry appears that wasn't in the baseline

A change **improves** a question if:
- Overall score increases by ≥ 0.5 points AND no dimension drops by ≥ 1 point

---

## 6. Runner Implementation

### 6.1 `tests/golden_answer_runner.js`

This runs inside the VS Code Extension Host (same environment as the chat participant):

```javascript
const vscode = require('vscode');
const fs = require('fs');
const path = require('path');

/**
 * Run all golden answer tests and capture results.
 * Invoke via VS Code command: kts.runGoldenTests
 */
async function runGoldenTests(outputChannel) {
  const testsPath = path.join(__dirname, 'golden_answer_tests.json');
  const tests = JSON.parse(fs.readFileSync(testsPath, 'utf-8'));
  
  const results = [];
  const startTime = Date.now();
  
  for (const test of tests) {
    outputChannel.appendLine(`Running ${test.test_id}: ${test.question}`);
    
    const result = await runSingleTest(test, outputChannel);
    results.push(result);
    
    outputChannel.appendLine(
      `  → ${result.answer_length} chars, ${result.chunks_used} chunks, ${result.elapsed_ms}ms`
    );
  }
  
  const elapsed = Date.now() - startTime;
  const outputPath = path.join(
    __dirname, 'golden_answer_results',
    `${new Date().toISOString().replace(/[:.]/g, '-')}_results.json`
  );
  
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, JSON.stringify({
    timestamp: new Date().toISOString(),
    total_tests: tests.length,
    total_elapsed_ms: elapsed,
    results: results,
  }, null, 2));
  
  outputChannel.appendLine(`\nResults saved to ${outputPath}`);
  return results;
}

async function runSingleTest(test, outputChannel) {
  const start = Date.now();
  
  // Build the chat request
  // This calls the ktsTool → backend search → LLM generation → full pipeline
  const answer = await invokeChatParticipant(test.question, test.prior_context);
  
  const elapsed = Date.now() - start;
  
  return {
    test_id: test.test_id,
    category: test.category,
    question: test.question,
    actual_answer: answer.text,
    chunks_used: answer.chunks?.length || 0,
    chunk_sources: (answer.chunks || []).map(c => ({
      doc: c.source,
      section: c.section,
      score: c.score,
    })),
    answer_length: answer.text.length,
    elapsed_ms: elapsed,
    metadata: {
      model: answer.model,
      self_rag_rounds: answer.self_rag_rounds || 0,
      critique_applied: answer.critique_applied || false,
    },
  };
}
```

### 6.2 Integration with Extension

Register as a VS Code command so it can be triggered from the command palette:

```javascript
// In extension.js activate()
const goldenTestCmd = vscode.commands.registerCommand('kts.runGoldenTests', async () => {
  const outputChannel = vscode.window.createOutputChannel('KTS Golden Tests');
  outputChannel.show();
  
  const { runGoldenTests } = require('./tests/golden_answer_runner');
  const results = await runGoldenTests(outputChannel);
  
  // Run scorer
  const { scoreResults } = require('./tests/golden_answer_scorer');
  const scores = await scoreResults(results);
  
  outputChannel.appendLine('\n=== SCORING COMPLETE ===');
  outputChannel.appendLine(
    `Average: ${scores.average.toFixed(2)} / 5.00`
  );
  for (const cat of scores.by_category) {
    outputChannel.appendLine(
      `  ${cat.name}: ${cat.average.toFixed(2)}`
    );
  }
  if (scores.regressions.length > 0) {
    outputChannel.appendLine(`\n⚠ REGRESSIONS: ${scores.regressions.length}`);
    for (const r of scores.regressions) {
      outputChannel.appendLine(`  ${r.test_id}: ${r.dimension} dropped ${r.delta}`);
    }
  }
});
context.subscriptions.push(goldenTestCmd);
```

---

## 7. Baseline Capture

### 7.1 Process

1. Run golden tests against current v0.0.21 system (before ANY changes)
2. Save results as `tests/golden_answer_baseline.json`
3. Score the baseline
4. This becomes the reference point for all future comparisons

### 7.2 Expected Baseline Performance

Based on the current system's behavior, estimated baseline scores:

| Category | Completeness | Accuracy | Grounding | Usability | Overall |
|----------|-------------|----------|-----------|-----------|---------|
| Defined Terms | 3-4 | 4-5 | 2-3 | 2-3 | 3.2 |
| Waterfall | 3 | 3-4 | 2-3 | 2 | 2.8 |
| Reporting | 3 | 3-4 | 2-3 | 2-3 | 2.9 |
| Key Dates | 4 | 4-5 | 2-3 | 3 | 3.4 |
| Parties/Roles | 4 | 4-5 | 2-3 | 3 | 3.4 |
| Follow-Ups | 2-3 | 3 | 1-2 | 2 | 2.3 |

**Expected overall baseline: ~3.0 / 5.0**

The main weaknesses of v0.0.21:
- **Grounding** (2-3): The rigid 5-section format puts citations in a separate section rather than inline
- **Usability** (2-3): The academic format requires the user to mentally reassemble information
- **Follow-Ups** (2.3): Multi-turn conversation is the weakest area

After implementing the redesign (conversational prompt + settings simplification + RAG cleanup):
- **Target overall: 4.0+ / 5.0**
- **Target grounding: 4.0+** (inline citations from new prompt)
- **Target usability: 4.0+** (conversational format)

---

## 8. Ablation Testing Protocol

### 8.1 Purpose

When we want to evaluate whether a specific RAG technique helps or hurts, we:

1. Run golden tests with the technique enabled → Score A
2. Run golden tests with the technique disabled → Score B
3. Compare: if Score A > Score B, the technique helps

### 8.2 Techniques to Ablate (from Phase E)

| Config | Technique | Hypothesis |
|--------|-----------|------------|
| `kts.selfRagEnabled = false` | Self-RAG iterative loop | Improves completeness for complex questions |
| `kts.critiqueLoopEnabled = false` | Critique loop | Improves accuracy by catching errors |
| `kts.multiQueryRagEnabled = false` | JS multi-query expansion | Improves recall by diversifying queries |
| Keyword-boost removed (code change) | Keyword-boost rerank | May HURT accuracy by overriding cross-encoder |
| `enable_bm25_hybrid = false` | BM25 hybrid search | Improves recall for exact-match queries |
| `enable_mmr_diversity = false` | MMR diversity rerank | Improves diversity but may reduce precision |

### 8.3 Results Format

```json
{
  "experiment": "ablation_keyword_boost",
  "baseline_config": { "keyword_boost": true },
  "variant_config": { "keyword_boost": false },
  "baseline_overall": 3.14,
  "variant_overall": 3.28,
  "delta": +0.14,
  "verdict": "REMOVE — keyword boost HURTS answer quality",
  "per_question_deltas": [
    { "test_id": "G01", "baseline": 3.8, "variant": 4.0, "delta": +0.2 },
    ...
  ],
  "regressions": [],
  "improvements": ["G04", "G06", "G08"]
}
```

---

## 9. Integration with CI / Dev Workflow

### 9.1 Dev Host (F5) Workflow

```
Developer changes a prompt or RAG technique
  → F5 launches Extension Host
  → Cmd+Shift+P → "KTS: Run Golden Tests"
  → Output panel shows progress
  → Results file saved to tests/golden_answer_results/
  → Scores compared to baseline automatically
  → Regressions flagged in output
```

### 9.2 Pre-Build Gate

Before building a new VSIX:
1. Run golden tests
2. If any question regresses by ≥ 1 overall point → block build
3. If average overall drops by ≥ 0.3 → warning
4. Generate summary report in `tests/golden_answer_results/latest_summary.md`

### 9.3 A/B Testing

For larger changes (e.g., new prompt):
1. Save current results as "before"
2. Apply changes
3. F5 → run golden tests → save as "after"
4. Compare side by side

---

## 10. File Schema: `golden_answer_tests.json`

```json
[
  {
    "test_id": "G01",
    "category": "defined_terms",
    "category_name": "Defined Terms",
    "question": "What does Distribution Date mean?",
    "command": "search",
    "prior_context": null,
    "expected_answer_contains": [
      "25th",
      "Business Day",
      "February 2006"
    ],
    "expected_answer_not_contains": [
      "I don't know",
      "not found"
    ],
    "expected_sections": ["Section 1.01"],
    "ideal_answer_summary": "Distribution Date means the 25th day of each month (or the next Business Day), commencing February 2006.",
    "scoring_rubric": {
      "completeness": "Must include date, Business Day fallback, commencement month.",
      "accuracy": "All facts match PSA. No invented dates.",
      "grounding": "Cites Section 1.01 or Article I inline.",
      "usability": "Immediately useful to finance professional.",
      "no_hallucination": "No external knowledge about distribution dates."
    },
    "difficulty": "easy",
    "depends_on": null
  },
  {
    "test_id": "G26",
    "category": "follow_ups",
    "category_name": "Conversational Follow-Ups",
    "question": "Tell me more about that",
    "command": "search",
    "prior_context": "The user previously asked 'What does Distribution Date mean?' and received an answer explaining it as the 25th of each month.",
    "expected_answer_contains": [
      "Business Day",
      "Distribution Date"
    ],
    "expected_answer_not_contains": [
      "I'm not sure what you're referring to"
    ],
    "expected_sections": ["Section 1.01"],
    "ideal_answer_summary": "Elaborates on Distribution Date: Business Day definition, first Distribution Date specifics, adjustment mechanics.",
    "scoring_rubric": {
      "completeness": "Must add NEW information beyond the prior answer.",
      "accuracy": "Facts match PSA.",
      "grounding": "Cites relevant section.",
      "usability": "Builds on prior answer without restating everything.",
      "no_hallucination": "No external knowledge."
    },
    "difficulty": "hard",
    "depends_on": "G01"
  }
]
```

---

## 11. Relationship to Existing Tests

### Not Replacing — Complementing

| Existing Test | What It Tests | Keep? |
|---------------|---------------|-------|
| `golden_psa_2006he1.json` (100 tests) | Retrieval precision (right chunks returned) | ✅ Keep as-is |
| `golden_queries_v2.json` (50 tests) | IT corpus retrieval quality | ✅ Keep as-is |
| `psa_test_queries.json` (20 tests) | CLI backend integration | ✅ Keep as-is |
| `score_queries.py` (705 lines) | Scoring engine for retrieval tests | ✅ Keep as-is |
| **NEW: `golden_answer_tests.json`** | **End-to-end answer quality** | **ADD** |

The new tests sit on TOP of the existing retrieval tests. If retrieval regresses, answer quality will also regress. But answer quality can regress even with perfect retrieval (bad prompt, bad context building, hallucination).

### Migration Path

1. Phase D (this doc): Create the 30 golden answer tests + runner + scorer
2. Capture baseline on v0.0.21
3. Implement Phases B + C (settings + prompt changes)
4. Re-run golden tests → measure improvement
5. Phase E (RAG ablation) → run golden tests per configuration
6. Final: golden answer tests become the primary quality gate

---

## 12. Acceptance Criteria

- [ ] `tests/golden_answer_tests.json` created with 30 questions across 6 categories
- [ ] `tests/golden_answer_runner.js` executes all tests through the full pipeline
- [ ] `tests/golden_answer_scorer.js` scores each answer on 5 dimensions via LLM-as-judge
- [ ] `kts.runGoldenTests` command registered and works from command palette
- [ ] Baseline captured for current v0.0.21 system
- [ ] Results output includes per-question scores, per-category averages, and regression flags
- [ ] Follow-up tests (G26-G30) correctly use prior_context for multi-turn evaluation
- [ ] Scoring is reproducible (±0.3 variance across 3 runs with same config)
