# Phase 16 — Settings & UX Polish

> **Status**: Completed ✅
> **Created**: 2026-02-19
> **Completed**: 2026-02-19

All Phase 16 enhancements have been implemented and shipped.

---

## Enhancement 1: Model Selection Dropdowns ✅

**Status**: Completed

All 5 model settings converted from free-text to enum dropdowns:

| Setting | Options |
|---------|---------|
| `kts.generationModel` | `auto`, `user`, `gpt-4.1`, `gpt-4o`, `gpt-4o-mini`, `claude-sonnet-4` |
| `kts.reasoningModel` | `auto`, `user`, `gpt-4.1`, `gpt-4o`, `gpt-4o-mini`, `claude-sonnet-4` |
| `kts.multiQueryModel` | `auto`, `user`, `gpt-4.1`, `gpt-4o`, `gpt-4o-mini`, `claude-sonnet-4` |
| `kts.selfRagModel` | `auto`, `user`, `gpt-4.1`, `gpt-4o`, `gpt-4o-mini`, `claude-sonnet-4` |
| `kts.critiqueModel` | `auto`, `user`, `gpt-4.1`, `gpt-4o`, `gpt-4o-mini`, `claude-sonnet-4` |

Each setting has `enumDescriptions` for VS Code hover help.

---

## Enhancement 2: Settings Sanitization ✅

**Status**: Completed

Renamed all "Phase X" references in user-facing settings to functional names.

---

## Bug Fixes (implemented alongside Phase 16)

### Fix 1: Self-RAG Buffer Mode ✅
`generateAnswer()` now supports `bufferMode` — when Self-RAG or Critique will post-process, tokens are collected without streaming. Final answer streams only after all refinement. Self-RAG `synthesizeFn` uses full persona prompt instead of generic.

### Fix 2: Critique Question Passthrough ✅
Backend `retrieval_service.py` now loads critique questions from `{kts_path}/documents/{doc_id}/critique_questions.json` and calls `merge_critique_questions()` to inject them into the search payload. JS `_extractCritiqueQuestions()` reads from the new top-level field.

### Fix 3: Context-Aware Follow-Up Questions ✅
- `buildFollowUpSuggestions()` now receives the generated answer text for regex matching
- New `generateLLMFollowUps()` function produces context-aware follow-ups using the LLM
- LLM follow-ups tried first; regex patterns used as fallback

---

## Phase 16+ Backlog (future consideration)

- [ ] Enable GraphRAG by default after validation
- [ ] Add query classification to skip LLM for simple lookups
- [ ] Add token usage tracking per component
- [ ] Run controlled experiments (premium vs free models)
- [ ] Establish quality baselines for each model tier
- [ ] Implement caching of multi-query variants for common patterns
