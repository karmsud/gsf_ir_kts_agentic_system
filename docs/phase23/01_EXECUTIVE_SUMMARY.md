# Phase 23: Executive Summary
## CLI, VS Code Extension & Packaging

**Document Version:** 1.0  
**Date:** February 26, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** User-facing surfaces, chat participant, CLI commands, VSIX packaging

---

## Table of Contents
1. [Phase Objective](#phase-objective)
2. [What Phase 23 Delivers](#what-phase-23-delivers)
3. [Relationship to Phase 21 and 22](#relationship)
4. [Three Deliverables](#three-deliverables)
5. [Component Inventory](#component-inventory)
6. [Risk Assessment](#risk-assessment)
7. [Success Metrics](#success-metrics)
8. [Phase Relationship Diagram](#phase-diagram)

---

## Phase Objective

Phase 23 is the **user-facing layer** — it takes everything built in Phase 21 (domain code) and Phase 22 (infrastructure + LLM) and exposes it through:

1. **`@abs` Chat Participant** — VS Code chat panel integration for interactive deal analysis
2. **ABS CLI Commands** — Terminal commands for batch operations (ingest, generate, audit, Q&A)
3. **Combined VSIX Package** — Single extension containing both KTS and ABS functionality

After Phase 23, users can:
- Type `@abs /ingest bear_stearns_2006_he1` in VS Code chat to ingest a deal
- Type `@abs What is the Distribution Waterfall?` to ask questions
- Run `kts abs-generate bear_stearns_2006_he1` from terminal for batch model generation
- Install a single `.vsix` file that provides both `@kts` and `@abs` chat participants

---

## What Phase 23 Delivers

### Before Phase 23

```
User can:
├── Use @kts chat participant ✅
├── Use kts CLI commands ✅
├── BUT:
│   ├── No @abs chat participant ❌
│   ├── No ABS CLI commands ❌
│   ├── No way to trigger ABS agents ❌
│   └── ABS code exists but is unreachable ❌
```

### After Phase 23

```
User can:
├── Use @kts chat participant ✅ (unchanged)
├── Use kts CLI commands ✅ (unchanged)
├── Use @abs chat participant ✅ (NEW)
│   ├── @abs /ingest <deal_id>
│   ├── @abs /generate <deal_id>
│   ├── @abs /audit <deal_id>
│   ├── @abs <question about deal>
│   └── @abs /status
├── Use ABS CLI commands ✅ (NEW)
│   ├── kts abs-ingest <deal_id> --source-dir <path>
│   ├── kts abs-generate <deal_id>
│   ├── kts abs-audit <deal_id>
│   ├── kts abs-qa <deal_id> --query "..."
│   └── kts abs-status <deal_id>
└── Install single VSIX ✅ (COMBINED)
```

---

## Relationship to Phase 21 and 22

```
Phase 21: Domain Code      Phase 22: Infrastructure     Phase 23: User Surface
─────────────────────      ─────────────────────────    ─────────────────────
                                                        
13 ABS agents        ────► LLM wiring (32 sites) ────► @abs chat participant
DealScope/Manifest   ────► Adapter replacement    ────► ABS CLI commands
Quality gates        ────► KTS infra delegation   ────► Combined VSIX
Error hierarchy      ────► Retrieval integration  ────► End-to-end tests
~5,500 lines domain  ────► ~1,200 lines infra     ────► ~800 lines surface

Total after Phase 23: ~7,500 new lines in KTS
```

---

## Three Deliverables

### Deliverable 1: `@abs` Chat Participant

| Aspect | Detail |
|--------|--------|
| Registration | `vscode.chat.createChatParticipant('abs', handler)` |
| Slash Commands | `/ingest`, `/generate`, `/audit`, `/status` |
| Free-text | Routes to QA agent with deal context |
| LLM Model | User-selected for visible, GPT-4.1 for background |
| Output | Markdown with code blocks, citations, progress |

### Deliverable 2: ABS CLI Commands

| Command | Purpose | Python Entry Point |
|---------|---------|-------------------|
| `kts abs-ingest` | Ingest PSA/Indenture for a deal | `cli.abs.ingest_cmd` |
| `kts abs-generate` | Generate payment model | `cli.abs.generate_cmd` |
| `kts abs-audit` | Audit generated model | `cli.abs.audit_cmd` |
| `kts abs-qa` | Ask questions about a deal | `cli.abs.qa_cmd` |
| `kts abs-status` | Show deal processing status | `cli.abs.status_cmd` |

### Deliverable 3: Combined VSIX Package

| Aspect | Detail |
|--------|--------|
| Extension ID | `gsf-ir-kts-agentic-system` (unchanged) |
| Participants | `@kts` + `@abs` (both registered) |
| Backend | Single PyInstaller binary with ABS modules |
| Size | ~50MB (up from ~40MB with ABS additions) |

---

## Component Inventory — Phase 23

| Category | New Files | Modified Files | New Lines |
|----------|----------|----------------|-----------|
| Chat participant (TS) | 3 | 2 | ~400 |
| CLI commands (Python) | 6 | 1 | ~300 |
| VSIX packaging | 1 | 2 | ~50 |
| End-to-end tests | 4 | 0 | ~350 |
| **Total** | **14** | **5** | **~1,100** |

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| `@abs` conflicts with `@kts` model selection | 🟡 Medium | Separate model contexts per participant |
| CLI subprocess spawning adds latency | 🟡 Medium | Lazy-load ABS modules, pre-warm on startup |
| VSIX size increase breaks install | 🟢 Low | ABS modules are ~2MB; well within limits |
| Extension activation time increases | 🟡 Medium | Lazy register `@abs` only when ABS deals exist |
| PyInstaller binary size grows | 🟢 Low | ABS is pure Python, no new native deps |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| `@abs` chat response time (first token) | < 3 seconds |
| CLI `abs-ingest` for 200-page PSA | < 5 minutes |
| CLI `abs-generate` with mock LLM | < 30 seconds |
| CLI `abs-qa` with mock LLM | < 10 seconds |
| VSIX size | < 55MB |
| Extension activation time | < 2 seconds |
| End-to-end tests pass | 90%+ |

---

## Phase Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    VS Code Extension (VSIX)                      │
│                                                                   │
│  ┌──────────────────┐        ┌──────────────────────┐           │
│  │  @kts Participant │       │  @abs Participant     │  ← NEW   │
│  │  (existing)       │       │                       │           │
│  │  /search          │       │  /ingest              │           │
│  │  /analyze         │       │  /generate            │           │
│  │  /generate        │       │  /audit               │           │
│  └────────┬──────────┘       │  /status              │           │
│           │                  │  [free-text Q&A]      │           │
│           │                  └──────────┬────────────┘           │
│           │                             │                        │
│           │         ┌───────────────────┘                        │
│           │         │                                            │
│           ▼         ▼                                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   LLM Bridge (IPC)                       │    │
│  │   vscode.lm.selectChatModels() → subprocess stdin/out    │    │
│  └────────────────────────┬────────────────────────────────┘    │
│                           │                                      │
└───────────────────────────┼──────────────────────────────────────┘
                            │ subprocess call
                            ▼
┌───────────────────────────────────────────────────────────────────┐
│                    Python Backend (PyInstaller)                    │
│                                                                   │
│  ┌────────────────┐  ┌──────────────────────────────────────┐   │
│  │ CLI (Click)     │  │ Backend                               │   │
│  │                 │  │                                       │   │
│  │ kts search     │  │  ┌─────────┐  ┌───────────────────┐  │   │
│  │ kts analyze    │  │  │ KTS     │  │ ABS (backend/abs/)│  │   │
│  │ kts abs-ingest │  │  │ agents  │  │ 13 agents         │  │   │
│  │ kts abs-generate│ │  │ 15      │  │ adapters          │  │   │
│  │ kts abs-audit  │  │  │ modules │  │ llm_bridge        │  │   │
│  │ kts abs-qa     │  │  └─────────┘  └───────────────────┘  │   │
│  │ kts abs-status │  │                                       │   │
│  └────────────────┘  └──────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```
