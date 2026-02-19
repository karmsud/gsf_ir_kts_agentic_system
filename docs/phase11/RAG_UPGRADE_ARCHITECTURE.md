# Phase 11: VS Code Native Intelligence Layer — Architecture Document

**Version:** 1.0  
**Date:** 2026-02-18  
**Author:** KTS Engineering  
**Status:** Draft  

---

## 1. Architectural Principles

| Decision | Rationale |
|----------|-----------|
| **Extension-side only for VS Code features** | #file, #selection, follow-ups, model selection — all in participant.js. Backend is mode-aware, not VS Code-aware. |
| **Mode flag, not new endpoints** | Slash commands (/define, /extract) pass a `retrieval_mode` flag to the existing endpoint. One contract, many behaviors. |
| **Follow-ups are deterministic, not generative** | Regex/pattern-matching on the answer to generate follow-up suggestions. No LLM call. Zero latency. Zero cost. |
| **Model selection is a setting, not a command** | Users set preferred model in VS Code settings (kts.generationModel). No /switch-model chat command. |
| **SSE for streaming progress** | Server-Sent Events from backend to extension during retrieval pipeline execution. Native HTTP, no WebSocket complexity. |

---

## 2. Layer Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                   VS CODE CHAT API                            │
│   request.references   ← #file, #selection, #editor         │
│   response.progress()  ← streaming status messages           │
│   response.followUp()  ← clickable follow-up chips           │
│   vscode.lm.selectChatModels() ← runtime model selection     │
├──────────────────────────────────────────────────────────────┤
│              PRESENTATION LAYER (participant.js)              │
│   + extractReferences()         NEW 11.1                     │
│   │ Parse #file, #selection, #editor from request.references  │
│   │ Add reference text as query context                        │
│   │ Pass source_doc_hint to backend                           │
│                                                               │
│   + generateFollowUps()         NEW 11.2                     │
│   │ Pattern-match defined terms, dates, amounts in answer     │
│   │ Return vscode.ChatFollowup array                          │
│                                                               │
│   + streamRetrievalProgress()   NEW 11.3                     │
│   │ SSE listener → response.progress(msg)                     │
│                                                               │
│   + parseSlashMode()            NEW 11.4                     │
│   │ /define → DEFINITION mode                                 │
│   │ /extract → EXTRACTION mode                                │
│   │ /compare → COMPARISON mode                                │
│   │ /audit → AUDIT mode                                       │
│   │ /summary → SUMMARY mode                                   │
│                                                               │
│   + selectModel()               NEW 11.5                     │
│   │ vscode.lm.selectChatModels() on each request              │
│   │ Model choice from kts.generationModel setting             │
│                                                               │
│   + confirmClassification()     NEW 11.7                     │
│   │ During ingestion, if regime confidence is ambiguous        │
│   │ Pause and present follow-up chips via Copilot Chat:       │
│   │   [Legal/Governing Doc] [Troubleshooting Guide]           │
│   │   [Operational Procedure] [Other]                         │
│   │ User selection overrides auto-classification               │
├──────────────────────────────────────────────────────────────┤
│              ORCHESTRATION LAYER (backend)                    │
│   backend/agents/retrieval_service.py  MODIFIED              │
│   • Accept retrieval_mode in request                          │
│   • Route to mode-specific prompt/output handler              │
│   • Emit SSE progress events during pipeline                  │
│                                                               │
│   backend/retrieval/extraction_mode.py   NEW 11.4            │
│   • JSON schema enforcement for /extract output               │
│                                                               │
│   backend/retrieval/audit_mode.py        NEW 11.4            │
│   • Topic-clustering for /audit output                        │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Retrieval Mode Routing Table

| Mode | Prompt Template | Chunk Budget | Output Format | LLM Temperature |
|------|----------------|-------------|--------------|----------------|
| `DEFAULT` | Legal/KTS system prompt | 15 chunks | Prose answer | 0.3 |
| `DEFINITION` | "Extract the precise definition of [term] from the provided text. Output: term, definition, source section only." | 5 chunks | `**[Term]**: [definition]\n*Source: [section]*` | 0.0 |
| `EXTRACTION` | "Extract all key data points as structured JSON. Schema: {dates, parties, amounts, defined_terms}" | 20 chunks | JSON code block | 0.0 |
| `COMPARISON` | "Compare how concept [X] is defined across the provided documents. Highlight equivalences and divergences." | 10 chunks per scope | Markdown table | 0.2 |
| `AUDIT` | "List all clauses related to [topic]. For each: section, clause summary, risk assessment (Low/Medium/High)." | 25 chunks | Bullet list with risk tags | 0.1 |
| `SUMMARY` | "Generate an executive summary with exactly 5 sections: Parties, Key Dates, Key Amounts, Key Obligations, Risk Factors." | 30 chunks | 5-section structured output | 0.2 |

---

## 4. Follow-Up Generation Pattern Map

```javascript
const FOLLOW_UP_PATTERNS = [
    {
        // Defined term found in answer
        regex: /\*\*([A-Z][a-zA-Z\s]+)\*\*\s+means/,
        generate: (match) => [
            `Which sections reference the ${match[1]}?`,
            `Are there exceptions or exclusions to the ${match[1]}?`,
        ]
    },
    {
        // Date found in answer
        regex: /\b(\w+ \d{1,2},? \d{4})\b/,
        generate: (match) => [
            `Has ${match[1]} passed?`,
            `What events are triggered on or after ${match[1]}?`,
        ]
    },
    {
        // Dollar amount found
        regex: /\$[\d,]+(?:\.\d{2})?/,
        generate: (match) => [
            `How is this amount calculated?`,
            `Are there caps, floors, or adjustments to this amount?`,
        ]
    },
    {
        // Section cross-reference found
        regex: /Section (\d+(?:\.\d+)*)/g,
        generate: (match) => [
            `Show me the full text of Section ${match[1]}`,
        ]
    }
];
```
