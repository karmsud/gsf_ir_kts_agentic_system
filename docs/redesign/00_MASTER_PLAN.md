# KTS System Redesign — Master Plan

**Created:** 2026-02-20  
**Author:** Agent + Karmsud  
**Status:** APPROVED — Ready for Implementation  
**Version:** 1.0

---

## Executive Summary

The KTS Knowledge Assistant has accumulated 15 phases of features producing a working but
over-engineered RAG pipeline.  Testing requires a 10+ minute VSIX build→install→ingest cycle.
The output format is rigid and academic.  25+ user-facing settings create decision fatigue.
The RAG pipeline stacks 30+ techniques whose individual value has never been measured.

This redesign strips the system back to a clean, measurable, conversational foundation —
then builds up through empirical testing.

---

## Design Document Index

| # | Document | Phase | Effort | Priority |
|---|----------|-------|--------|----------|
| 01 | [DEV_ENVIRONMENT.md](01_DEV_ENVIRONMENT.md) | A | 1 hour | **P0 — Do First** |
| 02 | [SETTINGS_SIMPLIFICATION.md](02_SETTINGS_SIMPLIFICATION.md) | B | 30 min | P1 |
| 03 | [CONVERSATIONAL_OUTPUT.md](03_CONVERSATIONAL_OUTPUT.md) | C | 1-2 hours | **P0 — Do First** |
| 04 | [GOLDEN_TEST_HARNESS.md](04_GOLDEN_TEST_HARNESS.md) | D | 2-3 hours | **P0 — Do First** |
| 05 | [RAG_ARCHITECTURE_REVIEW.md](05_RAG_ARCHITECTURE_REVIEW.md) | E | Ongoing | P1 |
| 06 | [DEFINITION_RESOLUTION_ENGINE.md](06_DEFINITION_RESOLUTION_ENGINE.md) | F | 1-2 weeks | P2 |

---

## Execution Order

```
Week 1 — Foundation
├── Day 1:  Phase A — Dev Environment (1 hour)
│   ├── launch.json for F5 Extension Development Host
│   ├── kts.backendMode: "venv" config for live Python
│   └── README update with dev workflow
│
├── Day 1:  Phase C — Conversational Output (1-2 hours)
│   ├── Replace rigid 5-section system prompts
│   ├── Use native ChatResponseReferencePart for citations
│   ├── Remove duplicate markdown follow-ups
│   └── Test in dev host immediately
│
├── Day 2:  Phase B — Settings Simplification (30 min)
│   ├── Strip package.json to 3 user-facing settings
│   ├── Hardcode all RAG tuning internally
│   └── Remove all toggle switches
│
└── Day 2-3: Phase D — Golden Test Harness (2-3 hours)
    ├── Create golden_answer_tests.json (30 questions)
    ├── Build test runner (Node.js, runs in dev host)
    ├── Add LLM-as-judge scoring
    └── Run first baseline measurement

Week 2 — Architecture Validation
├── Phase E — RAG Ablation Study (ongoing)
│   ├── Run baseline (graph + vector + BM25 + CE + defs)
│   ├── Add multi-query, measure impact
│   ├── Add Self-RAG, measure impact
│   ├── Add critique, measure impact
│   ├── Remove keyword-boost-after-CE, measure impact
│   └── Produce scorecard: keep / remove decisions
│
└── Phase F — Definition Resolution Engine (Modules 1-5)
    ├── Story 1: PSA definitions section parser
    ├── Story 2: DEPENDS_ON edge builder (Aho-Corasick)
    ├── Story 3: Resolution tree pre-computation (DFS)
    ├── Story 4: Resolution tree storage on graph nodes
    ├── Story 5: Resolution tree injection into retrieval
    └── Re-measure with golden test harness
```

---

## Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| Dev cycle time (edit → test) | 10-15 minutes | < 5 seconds |
| User-facing settings | 25+ | 3 |
| Output format satisfaction | Low (rigid 5-section) | Conversational, citation-inline |
| Golden test pass rate | Not measured | Baselined, tracked per commit |
| RAG techniques with measured value | 0 of 30+ | All justified by ablation data |
| Definition resolution latency | Per-query BFS traversal | Pre-computed at ingestion |

---

## Dependencies Between Phases

```
Phase A (Dev Environment) ─── required by ──→ everything else
                                              (can't iterate without fast dev cycle)

Phase C (Conversational Output) ─── independent
Phase B (Settings Simplification) ─── independent

Phase D (Golden Test Harness) ─── requires A (dev host to run tests)
Phase E (Ablation Study) ─── requires D (test harness to measure)
Phase F (Definition Resolution) ─── requires D (to measure before/after impact)
```

---

## What We Are NOT Doing

1. **Not building Modules 6-8** (term classification, formula extraction, code generation) — these are research-grade and out of scope for this redesign.

2. **Not rewriting the backend from scratch** — the Python backend (retrieval_service.py, human_like_retriever.py, graph builder) is solid. We're tuning which techniques are active, not rebuilding.

3. **Not changing the ingestion pipeline** — except for Phase F (definition resolution), the crawl → chunk → embed → graph pipeline stays as-is.

4. **Not shipping a new VSIX during development** — the whole point is to iterate in F5 dev mode. A VSIX build happens only when a milestone is validated by the golden test harness.

---

## Files That Will Be Modified

### Phase A (Dev Environment)
- **NEW:** `.vscode/launch.json`
- **NEW:** `.vscode/settings.json` (workspace dev defaults)
- **EDIT:** `README.md` (add dev workflow section)

### Phase B (Settings Simplification)
- **EDIT:** `extension/package.json` — remove ~20 settings, keep 3
- **EDIT:** `extension/chat/participant.js` — hardcode defaults, remove settings reads
- **EDIT:** `extension/lib/iterative_generator.js` — hardcode maxRounds
- **EDIT:** `extension/lib/gap_analyzer.js` — hardcode maxGaps

### Phase C (Conversational Output)
- **EDIT:** `extension/chat/participant.js` — replace LEGAL_SYSTEM_PROMPT (lines 190-280) and KTS_SYSTEM_PROMPT (lines 126-188)
- **EDIT:** `extension/chat/participant.js` — use ChatResponseReferencePart for citations
- **EDIT:** `extension/chat/participant.js` — remove duplicate markdown follow-ups

### Phase D (Golden Test Harness)
- **NEW:** `tests/golden_answer_tests.json`
- **NEW:** `tests/run_golden_tests.js`
- **NEW:** `tests/llm_judge.js`
- **EDIT:** `extension/package.json` — add `test:golden` script

### Phase E (Ablation Study)
- **EDIT:** `config/settings.py` — fix duplicate `context_expansion_enabled`, unify confidence
- **EDIT:** `backend/retrieval/human_like_retriever.py` — make keyword-boost-after-CE toggleable
- **EDIT:** Configuration flags for ablation toggles

### Phase F (Definition Resolution)
- **NEW:** `backend/extraction/psa_definitions_parser.py` — Module 1
- **NEW:** `backend/graph/dependency_scanner.py` — Module 3
- **NEW:** `backend/graph/resolution_tree.py` — Module 5
- **EDIT:** `backend/graph/builder.py` — add DEPENDS_ON edges (Module 4)
- **EDIT:** `backend/graph/schema.py` — add DEPENDS_ON edge type
- **EDIT:** `backend/retrieval/term_resolver.py` — read pre-computed trees instead of BFS

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Conversational prompt produces hallucinations (no rigid format guardrails) | Medium | High | Golden test harness catches it immediately; keep "use only retrieved context" constraint |
| Removing settings breaks existing users | Low | Medium | All removed settings get hardcoded to their current "GO BIG" defaults — behavior unchanged |
| Ablation study shows all techniques help | Low | Low | Then we've proven the architecture is sound and can document why each exists |
| PSA definitions parser fails on other PSA formats | Medium | Medium | V1 targets Bear Stearns 2006-HE2 only; generalize in V2 |
| F5 dev host differs from VSIX runtime | Low | Low | The extension.js entry point is identical in both; only the packaging differs |

---

## Review Checklist

Before implementing each phase, confirm:

- [ ] Design document read and approved
- [ ] Acceptance criteria understood
- [ ] Files to be modified identified
- [ ] No conflicting changes with other phases
- [ ] Golden test baseline recorded (for Phases E and F)
