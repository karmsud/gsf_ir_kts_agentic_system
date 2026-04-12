# Phase 23: System Design
## CLI, VS Code Extension & Packaging Architecture

**Document Version:** 1.0  
**Date:** February 26, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** Architecture for user-facing surfaces

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [VS Code `@abs` Chat Participant](#abs-chat-participant)
3. [ABS CLI Architecture](#abs-cli-architecture)
4. [Data Flow — Chat Participant Request](#data-flow-chat)
5. [Data Flow — CLI Command](#data-flow-cli)
6. [Data Flow — VSIX Build](#data-flow-vsix)
7. [Slash Command Design](#slash-command-design)
8. [State Management](#state-management)
9. [Error Handling & User Feedback](#error-handling)
10. [Package Architecture](#package-architecture)

---

## Architecture Overview

Phase 23 adds three parallel surfaces that all converge on the same backend:

```
┌──────────────────────────────────────────────────────────┐
│                    USER SURFACES                          │
│                                                           │
│  ┌───────────┐  ┌───────────┐  ┌────────────────────┐  │
│  │ @abs Chat  │  │ CLI       │  │ (Future: Web API)  │  │
│  │ Participant│  │ Commands  │  │                    │  │
│  └─────┬─────┘  └─────┬─────┘  └────────┬───────────┘  │
│        │              │                  │               │
└────────┼──────────────┼──────────────────┼───────────────┘
         │              │                  │
         ▼              ▼                  ▼
┌──────────────────────────────────────────────────────────┐
│                 ORCHESTRATION LAYER                        │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              ABSOrchestrator                         │ │
│  │                                                      │ │
│  │  ingest(deal_id, source_dir) → IngestResult          │ │
│  │  generate(deal_id) → GenerateResult                  │ │
│  │  audit(deal_id) → AuditResult                        │ │
│  │  qa(deal_id, query) → QAResult                       │ │
│  │  status(deal_id) → StatusResult                      │ │
│  └─────────────────────────────────────────────────────┘ │
│                          │                                │
└──────────────────────────┼────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│                   BACKEND (Phase 21 + 22)                 │
│                                                           │
│  Agents → Adapters → KTS Infrastructure → Results        │
└──────────────────────────────────────────────────────────┘
```

### ABSOrchestrator

Both the chat participant and CLI converge on a shared `ABSOrchestrator` class. This ensures identical behavior regardless of entry point:

```python
# backend/abs/orchestrator.py (~200 lines)

class ABSOrchestrator:
    """Unified entry point for all ABS operations.
    
    Both chat participant and CLI delegate to this class.
    """
    def __init__(
        self,
        config: KTSConfig,
        llm_callable: Optional[LLMCallable] = None,
    ):
        self.config = config
        self.llm = llm_callable
    
    async def ingest(self, deal_id: str, source_dir: Path) -> IngestResult: ...
    async def generate(self, deal_id: str) -> GenerateResult: ...
    async def audit(self, deal_id: str) -> AuditResult: ...
    async def qa(self, deal_id: str, query: str) -> QAResult: ...
    def status(self, deal_id: str) -> StatusResult: ...
```

---

## VS Code `@abs` Chat Participant

### Registration Pattern

Following KTS's existing `@kts` participant pattern:

```typescript
// extension/src/abs/absParticipant.ts

import * as vscode from 'vscode';

export function registerABSParticipant(
    context: vscode.ExtensionContext,
): void {
    const participant = vscode.chat.createChatParticipant(
        'abs',
        handleABSRequest,
    );
    
    participant.iconPath = vscode.Uri.joinPath(
        context.extensionUri,
        'media',
        'abs-icon.svg',
    );
    
    // Register slash commands
    participant.followupProvider = {
        provideFollowups: provideABSFollowups,
    };
    
    context.subscriptions.push(participant);
}
```

### Request Handler

```typescript
async function handleABSRequest(
    request: vscode.ChatRequest,
    context: vscode.ChatContext,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
): Promise<vscode.ChatResult> {
    const command = request.command;  // slash command or undefined
    const prompt = request.prompt;
    
    switch (command) {
        case 'ingest':
            return handleIngest(prompt, stream, token);
        case 'generate':
            return handleGenerate(prompt, stream, token);
        case 'audit':
            return handleAudit(prompt, stream, token);
        case 'status':
            return handleStatus(prompt, stream, token);
        default:
            // Free-text Q&A
            return handleQA(prompt, stream, token);
    }
}
```

### LLM Model Selection

```typescript
// Two-tier model selection:
async function getLLMModel(
    tier: 'background' | 'user-visible',
    token: vscode.CancellationToken,
): Promise<vscode.LanguageModelChat> {
    if (tier === 'background') {
        // Always GPT-4.1 for background tasks
        const models = await vscode.lm.selectChatModels({
            vendor: 'copilot',
            family: 'gpt-4.1',
        });
        return models[0];
    } else {
        // User-selected model for visible outputs
        const models = await vscode.lm.selectChatModels({
            vendor: 'copilot',
        });
        return models[0];
    }
}
```

---

## ABS CLI Architecture

### Command Registration

Following KTS's existing Click CLI pattern:

```python
# cli/abs/__init__.py

import click
from cli.abs.ingest_cmd import abs_ingest
from cli.abs.generate_cmd import abs_generate
from cli.abs.audit_cmd import abs_audit
from cli.abs.qa_cmd import abs_qa
from cli.abs.status_cmd import abs_status


@click.group()
def abs_group():
    """ABS payment model generation commands."""
    pass

abs_group.add_command(abs_ingest, "ingest")
abs_group.add_command(abs_generate, "generate")
abs_group.add_command(abs_audit, "audit")
abs_group.add_command(abs_qa, "qa")
abs_group.add_command(abs_status, "status")
```

### Registration in Main CLI

```python
# cli/main.py — add abs subgroup

from cli.abs import abs_group

@click.group()
def main():
    """KTS Agentic System CLI."""
    pass

# Existing commands
main.add_command(search)
main.add_command(analyze)
# ...

# New ABS commands (prefixed)
main.add_command(abs_group, "abs")
```

### CLI Command Signatures

```python
# All commands share these common options:
@click.option('--deal-id', required=True, help='Deal identifier')
@click.option('--config', default=None, help='Config file path')
@click.option('--llm-mode', default='none', type=click.Choice(['vscode', 'mock', 'none']))
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')

# kts abs ingest
@click.option('--source-dir', required=True, type=click.Path(exists=True))
@click.option('--force', is_flag=True, help='Re-ingest even if already complete')

# kts abs generate
@click.option('--output-dir', default=None, type=click.Path())
@click.option('--max-retries', default=3, type=int)

# kts abs audit
@click.option('--model-path', default=None, type=click.Path())
@click.option('--expected-csv', default=None, type=click.Path())

# kts abs qa
@click.option('--query', '-q', required=True, help='Question to ask')
@click.option('--max-results', default=10, type=int)
```

---

## Data Flow — Chat Participant Request

```
User: "@abs What are the triggers in Bear Stearns 2006-HE1?"
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  1. absParticipant.handleABSRequest()                    │
│     - command = undefined (free text)                    │
│     - Detect deal_id from context or prompt parsing      │
│     - Select LLM model (user-visible tier)               │
└──────────────────────┬──────────────────────────────────┘
                       │
        ▼              │
┌──────────────────────┼──────────────────────────────────┐
│  2. Spawn Python subprocess                              │
│     kts abs qa --deal-id bear_stearns_2006_he1          │
│                --query "triggers"                        │
│                --llm-mode vscode                         │
│                                                          │
│  3. IPC loop:                                            │
│     Python stdout → JSON requests for LLM calls          │
│     Extension stdin → JSON responses with LLM text       │
│                                                          │
│  4. Streaming:                                           │
│     stream.markdown("## Triggers in Bear Stearns...")    │
│     stream.markdown("1. **OC Trigger**: Section 5.06...") │
│     stream.markdown("2. **Delinquency Trigger**: ...")   │
│     stream.reference(document_uri)                       │
└──────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│  5. Python backend flow:                                  │
│     ABSOrchestrator.qa(deal_id, query)                   │
│     → QAAgent.execute(task=query)                        │
│     → vector_search adapter → KTS RetrievalService       │
│     → llm_callable (via IPC) for answer generation       │
│     → Quality gate evaluation                            │
│     → Return formatted answer with citations             │
└──────────────────────────────────────────────────────────┘
```

---

## Data Flow — CLI Command

```
Terminal: kts abs ingest --deal-id bear_2006_he1 --source-dir ./deals/bear/

        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  1. Click command handler: abs_ingest()                  │
│     - Parse options                                      │
│     - Load KTSConfig                                     │
│     - Create llm_callable (based on --llm-mode)          │
│     - Create ABSOrchestrator                             │
└──────────────────────┬──────────────────────────────────┘
                       │
        ▼              │
┌──────────────────────┼──────────────────────────────────┐
│  2. ABSOrchestrator.ingest(deal_id, source_dir)          │
│                                                          │
│     a. DealScope(deal_id, config) — set up directories   │
│     b. DocumentConverter — PDF → text                    │
│     c. SectionSplitter — split by headings               │
│     d. StructuredExtractor — extract entities             │
│     e. embedder_adapter.embed_and_store() — vectorize    │
│     f. graph_adapter.build_graph() — create graph        │
│     g. GoverningDocGenerator — create gov docs           │
│     h. DealManifest.save() — mark complete               │
│                                                          │
│  3. Progress output:                                     │
│     [1/8] Converting PDF...                ✅ (12s)      │
│     [2/8] Splitting sections...            ✅ (3s)       │
│     [3/8] Extracting entities...           ✅ (8s)       │
│     [4/8] Embedding 1,247 items...         ✅ (45s)      │
│     [5/8] Building knowledge graph...      ✅ (5s)       │
│     [6/8] Generating governing docs...     ✅ (30s)      │
│     [7/8] Validating deal manifest...      ✅ (2s)       │
│     [8/8] Complete!                                      │
│                                                          │
│     Ingested: 1,247 items, 87 sections, 423 graph nodes  │
│     Time: 1m 45s                                         │
└──────────────────────────────────────────────────────────┘
```

---

## Data Flow — VSIX Build

```
Source Code
    │
    ├── extension/src/           TypeScript source
    │   ├── abs/                 @abs participant
    │   └── kts/                 @kts participant (existing)
    │
    ├── backend/                 Python backend
    │   ├── abs/                 ABS domain
    │   ├── agents/              KTS agents
    │   └── ...                  
    │
    └── packaging/               Build scripts
        ├── build_vsix.ps1      
        └── pyinstaller.spec    
            │
            ▼
    ┌───────────────────────────────────────────────────┐
    │  1. PyInstaller: Build Python → single binary     │
    │     Input: cli/main.py + backend/**               │
    │     Output: build/kts_backend/kts_backend.exe     │
    │     Size: ~35MB                                    │
    │                                                    │
    │  2. TypeScript: Compile extension                  │
    │     Input: extension/src/**/*.ts                   │
    │     Output: extension/dist/extension.js            │
    │     Size: ~200KB                                   │
    │                                                    │
    │  3. VSCE: Package VSIX                            │
    │     Input: package.json + dist/ + build/           │
    │     Output: gsf-ir-kts-agentic-system-X.Y.Z.vsix  │
    │     Size: ~50MB                                    │
    └───────────────────────────────────────────────────┘
```

---

## Slash Command Design

### `@abs /ingest <deal_id>`

```
User Input:  @abs /ingest bear_stearns_2006_he1

Response:
┌─────────────────────────────────────────────────────────┐
│ 📁 Ingesting Bear Stearns 2006-HE1                      │
│                                                          │
│ ▸ Converting PDF documents...          ✅ Done (12s)     │
│ ▸ Splitting into sections...           ✅ Done (3s)      │
│ ▸ Extracting structured entities...    ✅ Done (8s)      │
│ ▸ Embedding 1,247 items...             ✅ Done (45s)     │
│ ▸ Building knowledge graph...          ✅ Done (5s)      │
│ ▸ Generating governing documents...    ✅ Done (30s)     │
│                                                          │
│ **Summary:**                                             │
│ - Documents: 3 (PSA, Supplement, Indenture)             │
│ - Sections: 87                                           │
│ - Items: 1,247 (definitions, obligations, rules)        │
│ - Graph nodes: 423                                       │
│ - Graph edges: 1,156                                    │
│ - Time: 1m 43s                                           │
└─────────────────────────────────────────────────────────┘
```

### `@abs /generate <deal_id>`

```
User Input:  @abs /generate bear_stearns_2006_he1

Response:
┌─────────────────────────────────────────────────────────┐
│ ⚙️ Generating Payment Model                              │
│                                                          │
│ ▸ Loading deal data...                 ✅ Done           │
│ ▸ Retrieving waterfall rules...        ✅ Done (8s)      │
│ ▸ Generating Python model (GPT-4.1)... ✅ Done (15s)    │
│ ▸ Running validation...                ✅ Done (5s)      │
│                                                          │
│ **Generated Model:**                                     │
│ ```python                                                │
│ def calculate_distribution(deal_data, period):           │
│     available = deal_data['available_funds']             │
│     distributions = {}                                   │
│     # Step 1: Trustee Fee                                │
│     ...                                                  │
│ ```                                                      │
│                                                          │
│ **Validation:** 48/48 periods match (tolerance: 0.01)   │
│ **Quality Score:** 0.94 (5-dimension gate passed)        │
└─────────────────────────────────────────────────────────┘
```

### `@abs /audit <deal_id>`

```
User Input:  @abs /audit bear_stearns_2006_he1

Response:
┌─────────────────────────────────────────────────────────┐
│ 🔍 Audit Report: Bear Stearns 2006-HE1                  │
│                                                          │
│ **Model Coverage:**                                      │
│ ✅ Trustee Fee          — Section 5.04(a) — Matched     │
│ ✅ Servicer Fee         — Section 5.04(b) — Matched     │
│ ✅ Class A Interest     — Section 5.04(c) — Matched     │
│ ⚠️ Class B Interest     — Section 5.04(d) — 0.02 diff   │
│ ✅ OC Trigger           — Section 5.06    — Matched     │
│                                                          │
│ **Summary:** 14/15 rules match, 1 within tolerance      │
│ **Confidence:** 0.93                                    │
└─────────────────────────────────────────────────────────┘
```

### `@abs <free-text question>`

```
User Input:  @abs What triggers the stepdown in overcollateralization?

Response:
┌─────────────────────────────────────────────────────────┐
│ Based on **Section 5.06** of the PSA:                    │
│                                                          │
│ The overcollateralization target steps down from         │
│ **$4,500,000** to **$2,250,000** (the "Stepdown OC      │
│ Amount") on any Distribution Date on or after which:     │
│                                                          │
│ 1. The Cumulative Net Loss Percentage does not exceed    │
│    the applicable percentage in the table below:         │
│                                                          │
│ | Month | Max Loss % |                                   │
│ |-------|-----------|                                     │
│ | 1-12  | 2.75%     |                                     │
│ | 13-24 | 5.50%     |                                     │
│ | 25-36 | 7.00%     |                                     │
│ | 37+   | 8.50%     |                                     │
│                                                          │
│ 2. No **Trigger Event** (Section 5.07) is in effect.    │
│                                                          │
│ *Sources: Section 5.06(b), Table 5-1*                    │
│                                                          │
│ **Follow-up questions:**                                 │
│ - What happens when the stepdown is reversed?            │
│ - How is the Cumulative Net Loss calculated?             │
│ - What are the Trigger Events in Section 5.07?           │
└─────────────────────────────────────────────────────────┘
```

---

## State Management

### Deal Context Persistence

The `@abs` participant maintains deal context across turns:

```typescript
interface ABSSessionState {
    activeDealId: string | null;
    lastQuery: string | null;
    ingestStatus: 'not-started' | 'in-progress' | 'complete';
    modelGenerated: boolean;
    turnHistory: Array<{role: string, content: string}>;
}

// Stored in vscode.ChatContext for cross-turn persistence
```

### Deal ID Detection

```typescript
function detectDealId(prompt: string, context: vscode.ChatContext): string | null {
    // 1. Explicit in prompt: "@abs /ingest bear_stearns_2006_he1"
    const explicit = prompt.match(/\b([a-z_]+_\d{4}_\w+)\b/i);
    if (explicit) return explicit[1];
    
    // 2. From previous turns
    for (const turn of context.history.reverse()) {
        // Check for deal_id in previous turns
    }
    
    // 3. From workspace (look for deals/ directory)
    return null;
}
```

---

## Error Handling & User Feedback

### Chat Participant Errors

```typescript
// Structured error responses
stream.markdown('⚠️ **Error:** Deal not found: `bear_stearns_2006_he1`\n\n');
stream.markdown('Available deals:\n');
stream.markdown('- `bear_stearns_2006_he1` (ingested)\n');
stream.markdown('- `lehman_2007_abs2` (not ingested)\n');
stream.markdown('\nUse `@abs /ingest <deal_id>` to ingest a new deal.');
```

### CLI Errors

```python
# Click error handling with helpful messages
@click.command()
def abs_ingest(deal_id, source_dir, ...):
    try:
        result = orchestrator.ingest(deal_id, source_dir)
        click.echo(f"✅ Ingested {result.item_count} items")
    except DealNotFoundError as e:
        click.echo(f"❌ Deal not found: {e.deal_id}", err=True)
        click.echo(f"   Source directory: {source_dir}", err=True)
        raise SystemExit(1)
    except IngestionError as e:
        click.echo(f"❌ Ingestion failed at step {e.step}: {e}", err=True)
        click.echo(f"   Partial progress saved. Re-run with --force to restart.", err=True)
        raise SystemExit(1)
```

---

## Package Architecture

### `package.json` Changes

```json
{
    "contributes": {
        "chatParticipants": [
            {
                "id": "kts",
                "name": "KTS",
                "description": "Knowledge & Taxonomy System",
                "isSticky": true,
                "commands": [
                    {"name": "search", "description": "Search knowledge base"},
                    {"name": "analyze", "description": "Analyze documents"}
                ]
            },
            {
                "id": "abs",
                "name": "ABS",
                "description": "ABS Payment Model Generator",
                "isSticky": true,
                "commands": [
                    {"name": "ingest", "description": "Ingest deal documents"},
                    {"name": "generate", "description": "Generate payment model"},
                    {"name": "audit", "description": "Audit payment model"},
                    {"name": "status", "description": "Show deal status"}
                ]
            }
        ]
    }
}
```

### PyInstaller Spec Changes

```python
# packaging/kts.spec — add ABS modules

a = Analysis(
    ['../cli/main.py'],
    pathex=[],
    datas=[
        ('../config', 'config'),
        ('../backend', 'backend'),        # Includes backend/abs/
        ('../knowledge_base', 'knowledge_base'),
    ],
    hiddenimports=[
        'backend.abs',
        'backend.abs.agents',
        'backend.abs.skills',
        'backend.abs.config',
        'backend.abs.llm_bridge',
        'cli.abs',
        # ... existing KTS imports
    ],
)
```
