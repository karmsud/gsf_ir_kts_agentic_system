# Phase 11: VS Code Native Intelligence Layer — Implementation Plan

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Motivation — We Are Using 20% of the Platform

### 1.1 What the VS Code Chat API Provides That We Ignore

The VS Code Chat Participant API was designed by the same team that built GitHub Copilot. It is production-tested by tens of millions of users. As of v0.0.12, KTS uses it only as a text input/output pipe. The following capabilities are available in the current API, require no new dependencies, and are being ignored entirely:

| VS Code API Feature | What It Does | KTS Status |
|--------------------|-------------|-----------|
| `context.references` | Typed #file, #selection, #editor variables user drags into chat | ❌ Ignored |
| `response.followUp()` | Render clickable suggested follow-up questions after each answer | ❌ Not used |
| `vscode.lm.selectChatModels()` | Runtime model selection (GPT-4o, Claude, o1, etc.) | ❌ Hardcoded |
| `response.progress()` during retrieval | Stream live status while backend processes | ❌ Partially used (ingestion only) |
| Additional slash commands | `/define`, `/extract`, `/compare`, `/audit` as structured modes | ❌ Only /ingest, /search |
| `vscode.window.showWarningMessage()` | Confirmation dialogs for destructive operations | ❌ Not used |

### 1.2 The #file / #selection Gap Is a Trust Problem

A legal analyst highlights a clause in an open document. They want to ask: *"What does this mean under the deal terms?"* Today they must:
1. Copy the text
2. Paste it into the chat box
3. Re-type the question

With `context.references`, they drag the selection into chat and ask. The selected text arrives as a typed, structured object — the exact text, the file it came from, the line numbers. Your RAG uses it directly as the retrieval seed. This is zero new UI. It is one API call in `participant.js`.

---

## 2. Implementation Philosophy

> *"VS Code already solved UI, UX, and trust. Our job is to wire our intelligence to the hooks it provides — not re-implement them."*

**Design constraints:**
- Every feature in this phase is an extension-side (JavaScript) change only
- Backend receives richer context (reference text, mode flag) but adds no new endpoints
- Model selection exposed as a VS Code setting, not a chat command
- Follow-up suggestions are deterministically generated from the answer, not another LLM call

---

## 3. Implementation Order

| Order | Increment | Impact | Risk | Rationale |
|-------|-----------|--------|------|-----------|
| **11.1** | #file / #selection / #editor support | VERY HIGH | LOW | Highest analyst UX impact. Single handler change. |
| **11.2** | Follow-up question suggestions | HIGH | LOW | Drives discovery. Add after answer is streamed. |
| **11.3** | Rich retrieval progress streaming | MEDIUM | LOW | "Searching 3 docs... reranking..." — trust multiplier |
| **11.4** | Extended slash commands as structured modes | HIGH | MEDIUM | /define /extract /compare /audit |
| **11.5** | Runtime model selection via `vscode.lm` | MEDIUM | MEDIUM | User chooses model per task |
| **11.6** | Confirmation dialogs for destructive ops | LOW | LOW | /delete, /clear-index |
| **11.7** | Interactive ingestion classification (HITL) | HIGH | MEDIUM | Copilot Chat asks user to confirm/correct doc_type during ingestion |

---

## 4. Increment 11.1 — #file / #selection / #editor Variables

### 4.1 How VS Code Reference Variables Work

When a user types `@kts #selection what does this mean?` or drags a file into the chat input, VS Code populates `request.references`:

```javascript
// request.references is an array of vscode.ChatPromptReference
for (const ref of request.references) {
    if (ref.id === 'vscode.selection') {
        // ref.value is { uri, range, selectedText }
        selectedText = ref.value.selectedText;
        sourceFile = ref.value.uri.fsPath;
    }
    if (ref.id === 'vscode.file') {
        // ref.value is a vscode.Uri
        fileContent = await readFileContent(ref.value);
    }
    if (ref.id === 'vscode.editor') {
        // ref.value is { uri, selection, visibleRanges }
        editorContext = ref.value;
    }
}
```

### 4.2 Behavior Change

When `#selection` or `#file` references are present:

1. **Reference text as query seed**: The selected/file text is prepended to the query as additional context
2. **Source-biased retrieval**: The source file URI is passed to backend as a preferred document hint
3. **Grounded generation**: The LLM prompt explicitly says "Answer with respect to the following selected clause:" followed by the reference text

This changes the UX from *"ask about a document"* to *"ask about a specific passage"* — dramatically more precise for legal review.

### 4.3 UI Behavior

```
User: [drags clause from open PSA] @kts what limitations apply to this clause?

KTS: [reads clause text from selection]
     [searches for related clauses across deal docs]
     [generates: "This clause, found in Section 3.04, is subject to the 
      following limitations as defined in Sections 1.01 and 5.02: ..."]
     [suggests follow-ups: "Are there exceptions to Section 3.04?"]
```

---

## 5. Increment 11.2 — Follow-Up Question Suggestions

### 5.1 The Pattern

`response.followUp()` renders clickable suggestion chips below each answer. When clicked, they populate the chat input and trigger a new request.

```javascript
// After streaming the answer:
return [
    { prompt: `Are there exceptions to this definition?` },
    { prompt: `Which sections reference the ${primaryTerm}?` },
    { prompt: `Compare this with how it is defined in other deals` }
];
```

### 5.2 Follow-Up Generation Strategy

Follow-ups are generated **deterministically from the answer** — no additional LLM call:

| Answer Content Detected | Generated Follow-Ups |
|------------------------|---------------------|
| Defined term found | "What sections reference [term]?", "Are there exceptions to [term]?" |
| Date found | "Has [date] passed?", "What events are triggered on [date]?" |
| Dollar amount found | "How is this amount calculated?", "Are there caps or floors?" |
| Party name found | "What are all obligations of [party]?", "Who succeeds [party] if removed?" |
| Cross-reference detected | "Show me the full text of [referenced section]" |

Post-Phase-10, follow-ups also use session memory to avoid re-suggesting already-answered questions.

---

## 6. Increment 11.3 — Rich Retrieval Progress Streaming

### 6.1 Current State

`response.progress()` is called during ingestion. During retrieval (8-second wait for complex queries), the user sees nothing.

### 6.2 Target

Stream progressive status messages during retrieval:

```
Searching 3 documents (481 chunks)...
Reranking 47 candidates...
Running critique check (round 1)...
Generating answer...
```

Implementation: the backend sends Server-Sent Events during the retrieval pipeline, and `participant.js` calls `response.progress(statusMessage)` for each event.

---

## 7. Increment 11.4 — Extended Slash Commands as Structured Modes

Each slash command sets a **retrieval mode flag** passed to the backend. The same retrieval pipeline runs, but the prompt template, chunk budget, and output format change.

| Command | Mode | Behavior |
|---------|------|---------|
| `/define [term]` | DEFINITION | Retrieve only definitional chunks. Output: term + definition + source section. No inference. |
| `/extract` | EXTRACTION | Structured JSON output: all key dates, parties, amounts, defined terms from retrieved context |
| `/compare` | COMPARISON | Multi-doc retrieval of same concept. Side-by-side table output. (Requires Phase 12 scopes) |
| `/audit [topic]` | AUDIT | Retrieve all clauses related to a topic (risk, liability, indemnification). Bullet list output. |
| `/summary` | SUMMARY | Executive summary mode. Fixed 5-section output: Parties, Key Dates, Key Amounts, Key Obligations, Risks |

---

## 8. Increment 11.5 — Runtime Model Selection via `vscode.lm`

```javascript
// User selects model in VS Code settings: kts.generationModel
const models = await vscode.lm.selectChatModels({
    vendor: settings.modelVendor,  // 'copilot', 'anthropic', etc.
    family: settings.modelFamily   // 'gpt-4o', 'claude-3-5-sonnet', 'o1'
});
const model = models[0];
```

The model used for generation is now a runtime setting. The user can choose:
- **Fast/cheap mode** (GPT-4o-mini): quick definition lookups
- **Standard mode** (GPT-4o, Claude 3.5 Sonnet): normal queries
- **Deep reasoning mode** (o1, Claude Opus): complex synthesis, contract review

The retrieval pipeline is identical in all modes — only the final generation call changes.

---

## 9. Increment 11.7 — Interactive Ingestion Classification (Human-in-the-Loop)

### 9.1 The Problem

The regime classifier uses heuristic signals (definitions sections, named parties, section numbering, etc.) to auto-classify documents. These signals are brittle — a troubleshooting guide with structured sections and party names like "the Servicer" can easily trigger enough signals to be misclassified as `GOVERNING_DOC_LEGAL`. Misclassification affects chunking strategy, retrieval ranking, and regime-specific prompt routing.

### 9.2 The Solution: Ask the User via Copilot Chat

When the regime classifier produces a **low-confidence or ambiguous result** (score in the MIXED range, or below a confidence threshold), the extension **pauses ingestion and asks the user** to confirm or correct the classification via Copilot Chat follow-up chips.

### 9.3 User Experience Flow

```
[ User selects source folder → ingestion starts ]
       ↓
[ Backend classifies doc: regime_score = 52 (MIXED) ]
       ↓
[ Extension opens Copilot Chat panel with message: ]

  "I'm ingesting 'HE1_Troubleshooting_Guide.docx' and I'm not confident
   about its document type (auto-classified as MIXED, score 52/100).
   
   What kind of document is this?"

   [Legal / Governing Doc]  [Troubleshooting Guide]
   [Operational Procedure]  [Skip — let system decide]
       ↓
[ User clicks "Troubleshooting Guide" ]
       ↓
[ doc_type overridden → metadata updated → ingestion resumes ]
```

### 9.4 Technical Design

**Extension side (participant.js / select_source.js):**
- After each document's crawl+classify step, check if `regime_result.score` falls in the ambiguous range (35-65)
- If ambiguous, use `response.followUp()` to present classification chips
- Wait for user response before continuing to the next document
- Pass confirmed `doc_type_override` to the ingest CLI call via `--doc-type` flag

**Backend side (ingestion_agent.py):**
- Accept optional `--doc-type` CLI flag that overrides auto-classification
- If provided, skip regime classifier entirely and use user's choice
- Store user override in manifest as `doc_type_source: "user"` vs `doc_type_source: "auto"`

**Confidence thresholds:**

| Score Range | Action |
|-------------|--------|
| ≥ 65 | Auto-classify silently (high confidence) |
| 35–64 | Ask user via Copilot Chat (ambiguous) |
| < 35 | Auto-classify as `GENERIC_GUIDE` silently |

### 9.5 Bulk Ingestion Optimization

For folders with many documents, asking per-document would be tedious. Options:
- **Batch mode**: Show all ambiguous docs in one chat message with a table, let user classify them all at once
- **Template mode**: "Apply same classification to all docs in this folder?" with a sticky choice
- **First-doc learning**: Classify first ambiguous doc interactively, apply same type to remaining docs from same folder unless signals diverge significantly

### 9.6 Files Changed

| File | Change Type |
|------|------------|
| `extension/chat/participant.js` | Modified — add classification confirmation handler |
| `extension/commands/select_source.js` | Modified — pause/resume ingestion on ambiguous classification |
| `cli/main.py` | Modified — accept `--doc-type` override flag |
| `backend/agents/ingestion_agent.py` | Modified — honour doc_type override |
| `backend/ingestion/regime_classifier.py` | Modified — expose confidence level in result |

---

## 10. Files Changed (Full Phase)

| File | Change Type | Phase |
|------|------------|-------|
| `extension/chat/participant.js` | Modified | 11.1, 11.2, 11.3, 11.4, 11.5, 11.7 |
| `extension/commands/select_source.js` | Modified | 11.7 |
| `extension/package.json` | Modified | 11.4, 11.5 (new commands, new setting) |
| `backend/agents/retrieval_service.py` | Modified | 11.3 (SSE progress), 11.4 (mode routing) |
| `backend/agents/ingestion_agent.py` | Modified | 11.7 (doc_type override) |
| `backend/ingestion/regime_classifier.py` | Modified | 11.7 (confidence exposure) |
| `cli/main.py` | Modified | 11.7 (--doc-type flag) |
| `backend/retrieval/extraction_mode.py` | New | 11.4 |
| `backend/retrieval/audit_mode.py` | New | 11.4 |

---

## 11. Success Metrics

| Metric | Baseline (Phase 10) | Target (Phase 11) |
|--------|--------------------|--------------------|
| #selection usage rate (user sessions) | N/A | >40% of power users |
| Follow-up click-through rate | N/A | >25% of answers |
| /define command usage | N/A (does not exist) | Significant |
| User-reported query retry rate | ~35% | <15% |
| Model selection flexibility | None (hardcoded) | Full (3+ models) |
| Doc-type classification accuracy | ~70% (heuristic) | >95% (with HITL corrections) |
| User override rate (ambiguous docs) | N/A | Measured per corpus |
