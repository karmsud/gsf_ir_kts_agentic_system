# Phase 23: Technical Design
## Implementation-Ready Code & File Structure

**Document Version:** 1.0  
**Date:** February 26, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** Complete code for all Phase 23 components

---

## Table of Contents
1. [File Structure](#file-structure)
2. [TypeScript Components](#typescript-components)
3. [Python CLI Components](#python-cli-components)
4. [Backend Orchestrator](#backend-orchestrator)
5. [IPC & Streaming](#ipc--streaming)
6. [Package Configuration](#package-configuration)
7. [PyInstaller Configuration](#pyinstaller-configuration)
8. [Integration Wiring](#integration-wiring)

---

## File Structure

```
Phase 23 creates ~14 new files and modifies ~5 existing files.
Total new code: ~1,100 lines (~600 TypeScript, ~500 Python)

extension/
├── src/
│   └── abs/                          ← NEW DIRECTORY
│       ├── absParticipant.ts         ← NEW  ~45 lines
│       ├── absRequestHandler.ts      ← NEW  ~250 lines
│       ├── absLLMBridge.ts           ← NEW  ~90 lines
│       └── absFollowups.ts           ← NEW  ~45 lines
│
├── package.json                      ← MODIFIED (chatParticipants entry)
│
cli/
├── main.py                           ← MODIFIED (add abs_group)
├── abs/                              ← NEW DIRECTORY
│   ├── __init__.py                   ← NEW  ~25 lines
│   ├── ingest_cmd.py                 ← NEW  ~55 lines
│   ├── generate_cmd.py               ← NEW  ~50 lines
│   ├── audit_cmd.py                  ← NEW  ~50 lines
│   ├── qa_cmd.py                     ← NEW  ~50 lines
│   └── status_cmd.py                 ← NEW  ~25 lines

backend/
├── abs/
│   ├── orchestrator.py               ← NEW  ~200 lines
│   ├── streaming.py                  ← NEW  ~70 lines
│   └── ipc_protocol.py              ← NEW  ~40 lines

packaging/
├── kts.spec                          ← MODIFIED (ABS hidden imports)

scripts/
├── build_combined.ps1                ← NEW  ~40 lines
```

---

## TypeScript Components

### 1. `extension/src/abs/absParticipant.ts`

```typescript
import * as vscode from 'vscode';
import { handleABSRequest } from './absRequestHandler';
import { provideABSFollowups } from './absFollowups';

/**
 * Register the @abs chat participant.
 * Called from extension activate().
 */
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

    participant.followupProvider = {
        provideFollowups: provideABSFollowups,
    };

    context.subscriptions.push(participant);
}
```

### 2. `extension/src/abs/absRequestHandler.ts`

Complete implementation (250 lines):

```typescript
import * as vscode from 'vscode';
import { ABSLLMBridge } from './absLLMBridge';

// ─── Session State ──────────────────────────────────────────
interface ABSSessionState {
    activeDealId: string | null;
    lastQuery: string | null;
    ingestStatus: 'not-started' | 'in-progress' | 'complete';
    modelGenerated: boolean;
}

const state: ABSSessionState = {
    activeDealId: null,
    lastQuery: null,
    ingestStatus: 'not-started',
    modelGenerated: false,
};

// ─── Request Handler ────────────────────────────────────────
export async function handleABSRequest(
    request: vscode.ChatRequest,
    context: vscode.ChatContext,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
): Promise<vscode.ChatResult> {
    const prompt = request.prompt.trim();
    const dealId = detectDealId(prompt, context) ?? state.activeDealId;

    try {
        switch (request.command) {
            case 'ingest':
                return await cmdIngest(dealId, prompt, stream, token);
            case 'generate':
                return await cmdGenerate(dealId, stream, token);
            case 'audit':
                return await cmdAudit(dealId, stream, token);
            case 'status':
                return await cmdStatus(dealId, stream, token);
            default:
                return await cmdQA(dealId, prompt, stream, token);
        }
    } catch (err: any) {
        stream.markdown(`\n⚠️ **Error:** ${err.message}\n`);
        return { metadata: { error: true } };
    }
}

// ─── /ingest ────────────────────────────────────────────────
async function cmdIngest(
    dealId: string | null,
    prompt: string,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
): Promise<vscode.ChatResult> {
    if (!dealId) {
        stream.markdown('Specify a deal ID: `@abs /ingest bear_stearns_2006_he1`');
        return { metadata: { command: 'ingest', error: true } };
    }

    state.activeDealId = dealId;
    stream.markdown(`📁 **Ingesting ${dealId}**\n\n`);

    const bridge = new ABSLLMBridge();
    const { ipc } = await bridge.spawnBackend([
        'abs', 'ingest', '--deal-id', dealId, '--llm-mode', 'vscode',
    ]);

    for await (const msg of ipc.messages(token)) {
        switch (msg.type) {
            case 'progress':
                stream.markdown(`▸ ${msg.step}... ${msg.status}\n`);
                break;
            case 'llm_request':
                const resp = await bridge.handleLLMRequest(msg, token);
                ipc.send(resp);
                break;
            case 'result':
                stream.markdown(`\n**Summary:**\n`);
                stream.markdown(`| Metric | Count |\n|--------|-------|\n`);
                stream.markdown(`| Items | ${msg.item_count} |\n`);
                stream.markdown(`| Sections | ${msg.section_count} |\n`);
                stream.markdown(`| Graph Nodes | ${msg.node_count} |\n`);
                state.ingestStatus = 'complete';
                break;
        }
    }

    return { metadata: { command: 'ingest', dealId } };
}

// ─── /generate ──────────────────────────────────────────────
async function cmdGenerate(
    dealId: string | null,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
): Promise<vscode.ChatResult> {
    if (!dealId) {
        stream.markdown('Specify a deal ID: `@abs /generate bear_stearns_2006_he1`');
        return { metadata: { command: 'generate', error: true } };
    }

    stream.markdown(`⚙️ **Generating Payment Model for ${dealId}**\n\n`);

    const bridge = new ABSLLMBridge();
    const { ipc } = await bridge.spawnBackend([
        'abs', 'generate', '--deal-id', dealId, '--llm-mode', 'vscode',
    ]);

    for await (const msg of ipc.messages(token)) {
        switch (msg.type) {
            case 'progress':
                stream.markdown(`▸ ${msg.step}...\n`);
                break;
            case 'llm_request':
                ipc.send(await bridge.handleLLMRequest(msg, token));
                break;
            case 'code':
                stream.markdown(`\n\`\`\`python\n${msg.code}\n\`\`\`\n`);
                break;
            case 'result':
                stream.markdown(`\n**Quality Score:** ${msg.quality_score}\n`);
                stream.markdown(`**Validation:** ${msg.validation}\n`);
                state.modelGenerated = true;
                break;
        }
    }

    return { metadata: { command: 'generate', dealId } };
}

// ─── /audit ─────────────────────────────────────────────────
async function cmdAudit(
    dealId: string | null,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
): Promise<vscode.ChatResult> {
    if (!dealId) {
        stream.markdown('Specify a deal ID: `@abs /audit bear_stearns_2006_he1`');
        return { metadata: { command: 'audit', error: true } };
    }

    stream.markdown(`🔍 **Auditing ${dealId}**\n\n`);

    const bridge = new ABSLLMBridge();
    const { ipc } = await bridge.spawnBackend([
        'abs', 'audit', '--deal-id', dealId, '--llm-mode', 'vscode',
    ]);

    for await (const msg of ipc.messages(token)) {
        switch (msg.type) {
            case 'llm_request':
                ipc.send(await bridge.handleLLMRequest(msg, token));
                break;
            case 'result':
                stream.markdown(msg.report);
                break;
        }
    }

    return { metadata: { command: 'audit', dealId } };
}

// ─── /status ────────────────────────────────────────────────
async function cmdStatus(
    dealId: string | null,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
): Promise<vscode.ChatResult> {
    const bridge = new ABSLLMBridge();
    const { ipc } = await bridge.spawnBackend([
        'abs', 'status', ...(dealId ? ['--deal-id', dealId] : []),
    ]);

    for await (const msg of ipc.messages(token)) {
        if (msg.type === 'result') {
            stream.markdown(msg.status_report);
        }
    }

    return { metadata: { command: 'status', dealId } };
}

// ─── Free Text Q&A ─────────────────────────────────────────
async function cmdQA(
    dealId: string | null,
    query: string,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
): Promise<vscode.ChatResult> {
    if (!dealId) {
        stream.markdown(
            'Please specify a deal first. Use `@abs /ingest <deal_id>` or ' +
            'include the deal name in your question.',
        );
        return { metadata: { command: 'qa', error: true } };
    }

    const bridge = new ABSLLMBridge();
    const { ipc } = await bridge.spawnBackend([
        'abs', 'qa', '--deal-id', dealId, '--query', query,
        '--llm-mode', 'vscode',
    ]);

    for await (const msg of ipc.messages(token)) {
        switch (msg.type) {
            case 'llm_request':
                ipc.send(await bridge.handleLLMRequest(msg, token));
                break;
            case 'stream':
                stream.markdown(msg.text);
                break;
            case 'result':
                stream.markdown(msg.answer);
                if (msg.sources?.length) {
                    stream.markdown('\n\n*Sources:*\n');
                    for (const s of msg.sources) {
                        stream.markdown(`- ${s}\n`);
                    }
                }
                break;
        }
    }

    state.lastQuery = query;
    return { metadata: { command: 'qa', dealId } };
}

// ─── Deal ID Detection ─────────────────────────────────────
function detectDealId(
    prompt: string,
    context: vscode.ChatContext,
): string | null {
    // Pattern: word_word_NNNN_... (e.g., bear_stearns_2006_he1)
    const match = prompt.match(/\b([a-z][a-z_]*_\d{4}_[a-z0-9]+)\b/i);
    if (match) return match[1].toLowerCase();

    // Fallback: search conversation history
    for (const turn of [...context.history].reverse()) {
        if ('metadata' in turn && (turn as any).metadata?.dealId) {
            return (turn as any).metadata.dealId;
        }
    }

    return null;
}
```

### 3. `extension/src/abs/absLLMBridge.ts`

```typescript
import * as vscode from 'vscode';

/**
 * Bridges VS Code's LLM API with ABS Python backend over IPC.
 *
 * Two-tier model selection:
 *   - Background tasks (ingest, audit): GPT-4.1 hardcoded
 *   - Visible output (generate, qa):    User-selected model
 */
export class ABSLLMBridge {
    /**
     * Get LLM model for a given tier.
     */
    async getModel(tier: 'background' | 'visible'): Promise<vscode.LanguageModelChat> {
        if (tier === 'background') {
            const [model] = await vscode.lm.selectChatModels({
                vendor: 'copilot',
                family: 'gpt-4.1',
            });
            if (!model) throw new Error('GPT-4.1 model not available');
            return model;
        } else {
            const [model] = await vscode.lm.selectChatModels({
                vendor: 'copilot',
            });
            if (!model) throw new Error('No chat model available');
            return model;
        }
    }

    /**
     * Handle an LLM request from the Python backend.
     */
    async handleLLMRequest(
        request: { prompt: string; system_prompt?: string; model?: string },
        token: vscode.CancellationToken,
    ): Promise<{ type: string; text: string; input_tokens: number; output_tokens: number }> {
        const tier = request.model === 'gpt-4.1' ? 'background' : 'visible';
        const model = await this.getModel(tier);

        const messages: vscode.LanguageModelChatMessage[] = [];
        if (request.system_prompt) {
            messages.push(
                vscode.LanguageModelChatMessage.User(
                    `[System] ${request.system_prompt}`,
                ),
            );
        }
        messages.push(vscode.LanguageModelChatMessage.User(request.prompt));

        const response = await model.sendRequest(messages, {}, token);
        let text = '';
        for await (const chunk of response.text) {
            text += chunk;
        }

        return {
            type: 'llm_response',
            text,
            input_tokens: 0,   // VS Code API doesn't expose token counts
            output_tokens: 0,
        };
    }

    /**
     * Spawn the Python backend subprocess.
     * Delegates to common IPC module.
     */
    async spawnBackend(args: string[]): Promise<{ ipc: any }> {
        // Import from existing KTS IPC infrastructure
        const { PythonIPC } = await import('../common/pythonIPC');
        const ipc = new PythonIPC(args);
        await ipc.start();
        return { ipc };
    }
}
```

### 4. `extension/src/abs/absFollowups.ts`

```typescript
import * as vscode from 'vscode';

/**
 * Provide contextual follow-up suggestions based on the last @abs result.
 */
export function provideABSFollowups(
    result: vscode.ChatResult,
    _context: vscode.ChatContext,
    _token: vscode.CancellationToken,
): vscode.ChatFollowup[] {
    const cmd = result.metadata?.command;

    switch (cmd) {
        case 'ingest':
            return [
                { prompt: '@abs /generate', label: 'Generate Payment Model' },
                { prompt: '@abs /status', label: 'Check Status' },
            ];

        case 'generate':
            return [
                { prompt: '@abs /audit', label: 'Audit Generated Model' },
                { prompt: '@abs What are the waterfall rules?', label: 'View Rules' },
            ];

        case 'audit':
            return [
                { prompt: '@abs /generate', label: 'Regenerate Model' },
                { prompt: '@abs What are the triggers?', label: 'Review Triggers' },
            ];

        default:
            return [
                { prompt: '@abs /status', label: 'Deal Status' },
                { prompt: '@abs What is the Distribution Waterfall?', label: 'Waterfall' },
            ];
    }
}
```

---

## Python CLI Components

### 5. `cli/abs/__init__.py`

```python
"""ABS CLI command group — Click subgroup under main KTS CLI."""

import click
from cli.abs.ingest_cmd import abs_ingest
from cli.abs.generate_cmd import abs_generate
from cli.abs.audit_cmd import abs_audit
from cli.abs.qa_cmd import abs_qa
from cli.abs.status_cmd import abs_status


@click.group("abs")
def abs_group():
    """ABS Payment Model Generator commands."""
    pass


abs_group.add_command(abs_ingest, "ingest")
abs_group.add_command(abs_generate, "generate")
abs_group.add_command(abs_audit, "audit")
abs_group.add_command(abs_qa, "qa")
abs_group.add_command(abs_status, "status")
```

### 6. `cli/abs/ingest_cmd.py`

```python
"""CLI command: kts abs ingest"""
import click
import time
from pathlib import Path
from config.settings import KTSConfig
from backend.abs.llm_bridge import create_llm_callable


@click.command("ingest")
@click.option("--deal-id", required=True, help="Deal identifier")
@click.option("--source-dir", required=True, type=click.Path(exists=True))
@click.option("--llm-mode", default="none",
              type=click.Choice(["vscode", "mock", "none"]))
@click.option("--force", is_flag=True, help="Re-ingest even if complete")
@click.option("--verbose", "-v", is_flag=True)
def abs_ingest(deal_id, source_dir, llm_mode, force, verbose):
    """Ingest deal documents into knowledge base."""
    config = KTSConfig()
    config.abs_llm_mode = llm_mode
    llm = create_llm_callable(mode=llm_mode)

    from backend.abs.orchestrator import ABSOrchestrator
    orch = ABSOrchestrator(config=config, llm_callable=llm)

    start = time.time()
    click.echo(f"📁 Ingesting {deal_id} from {source_dir}")

    result = orch.ingest(
        deal_id=deal_id,
        source_dir=Path(source_dir),
        force=force,
        progress_callback=(
            lambda step, status: click.echo(f"  [{step}] {status}")
        ) if verbose else None,
    )

    elapsed = time.time() - start
    click.echo(f"\n✅ Complete ({elapsed:.1f}s)")
    click.echo(f"   Items: {result.item_count}")
    click.echo(f"   Sections: {result.section_count}")
    click.echo(f"   Graph nodes: {result.node_count}")
```

### 7. `cli/abs/generate_cmd.py`

```python
"""CLI command: kts abs generate"""
import click
from pathlib import Path
from config.settings import KTSConfig
from backend.abs.llm_bridge import create_llm_callable


@click.command("generate")
@click.option("--deal-id", required=True, help="Deal identifier")
@click.option("--output-dir", default=None, type=click.Path())
@click.option("--llm-mode", default="none",
              type=click.Choice(["vscode", "mock", "none"]))
@click.option("--max-retries", default=3, type=int)
@click.option("--verbose", "-v", is_flag=True)
def abs_generate(deal_id, output_dir, llm_mode, max_retries, verbose):
    """Generate payment waterfall model for a deal."""
    config = KTSConfig()
    config.abs_llm_mode = llm_mode
    llm = create_llm_callable(mode=llm_mode)

    from backend.abs.orchestrator import ABSOrchestrator
    orch = ABSOrchestrator(config=config, llm_callable=llm)

    click.echo(f"⚙️ Generating payment model for {deal_id}")

    result = orch.generate(
        deal_id=deal_id,
        output_dir=Path(output_dir) if output_dir else None,
        max_retries=max_retries,
    )

    click.echo(f"\n✅ Model generated")
    click.echo(f"   Output: {result.output_path}")
    click.echo(f"   Quality: {result.quality_score:.2f}")
```

### 8. `cli/abs/audit_cmd.py`

```python
"""CLI command: kts abs audit"""
import click
from pathlib import Path
from config.settings import KTSConfig
from backend.abs.llm_bridge import create_llm_callable


@click.command("audit")
@click.option("--deal-id", required=True, help="Deal identifier")
@click.option("--model-path", default=None, type=click.Path())
@click.option("--expected-csv", default=None, type=click.Path())
@click.option("--llm-mode", default="none",
              type=click.Choice(["vscode", "mock", "none"]))
@click.option("--verbose", "-v", is_flag=True)
def abs_audit(deal_id, model_path, expected_csv, llm_mode, verbose):
    """Audit generated model against deal documents."""
    config = KTSConfig()
    config.abs_llm_mode = llm_mode
    llm = create_llm_callable(mode=llm_mode)

    from backend.abs.orchestrator import ABSOrchestrator
    orch = ABSOrchestrator(config=config, llm_callable=llm)

    click.echo(f"🔍 Auditing {deal_id}")

    result = orch.audit(
        deal_id=deal_id,
        model_path=Path(model_path) if model_path else None,
        expected_csv=Path(expected_csv) if expected_csv else None,
    )

    click.echo(result.report)
    click.echo(f"\nConfidence: {result.confidence:.2f}")
```

### 9. `cli/abs/qa_cmd.py`

```python
"""CLI command: kts abs qa"""
import click
from config.settings import KTSConfig
from backend.abs.llm_bridge import create_llm_callable


@click.command("qa")
@click.option("--deal-id", required=True, help="Deal identifier")
@click.option("--query", "-q", required=True, help="Question text")
@click.option("--max-results", default=10, type=int)
@click.option("--llm-mode", default="none",
              type=click.Choice(["vscode", "mock", "none"]))
@click.option("--verbose", "-v", is_flag=True)
def abs_qa(deal_id, query, max_results, llm_mode, verbose):
    """Ask a question about a deal's documents."""
    config = KTSConfig()
    config.abs_llm_mode = llm_mode
    config.abs_retrieval_max_results = max_results
    llm = create_llm_callable(mode=llm_mode)

    from backend.abs.orchestrator import ABSOrchestrator
    orch = ABSOrchestrator(config=config, llm_callable=llm)

    result = orch.qa(deal_id=deal_id, query=query)

    click.echo(f"\n{result.answer}")

    if verbose and result.sources:
        click.echo("\nSources:")
        for src in result.sources:
            click.echo(f"  - {src}")
```

### 10. `cli/abs/status_cmd.py`

```python
"""CLI command: kts abs status"""
import click
from config.settings import KTSConfig


@click.command("status")
@click.option("--deal-id", default=None, help="Deal ID (omit for all)")
@click.option("--verbose", "-v", is_flag=True)
def abs_status(deal_id, verbose):
    """Show deal processing status."""
    config = KTSConfig()

    from backend.abs.orchestrator import ABSOrchestrator
    orch = ABSOrchestrator(config=config)

    result = orch.status(deal_id=deal_id)
    click.echo(result.status_report)
```

### 11. `cli/main.py` — Modification

```python
# Add to existing cli/main.py:

from cli.abs import abs_group

# In the main group setup:
main.add_command(abs_group, "abs")

# This enables:
#   kts abs ingest --deal-id ...
#   kts abs generate --deal-id ...
#   kts abs audit --deal-id ...
#   kts abs qa --deal-id ... --query "..."
#   kts abs status
```

---

## Backend Orchestrator

### 12. `backend/abs/orchestrator.py`

Full implementation provided in [03_ARCHITECTURE_UPGRADE.md](03_ARCHITECTURE_UPGRADE.md#transformation-4).

Key design points:
- **Stateless** — Each method creates its own agents
- **Lazy imports** — Agent classes imported inside methods to avoid circular deps
- **Dataclass results** — `IngestResult`, `GenerateResult`, `AuditResult`, `QAResult`, `StatusResult`
- **Progress callback** — Optional `Callable[[str, str], None]` for step progress

---

## IPC & Streaming

### 13. `backend/abs/ipc_protocol.py`

```python
"""IPC protocol constants for ABS extension↔backend communication."""

from typing import TypedDict, Optional, Literal


class ProgressMessage(TypedDict):
    type: Literal["progress"]
    step: str
    status: str
    step_number: int
    total_steps: int


class LLMRequest(TypedDict):
    type: Literal["llm_request"]
    model: str
    prompt: str
    system_prompt: Optional[str]
    temperature: float
    max_tokens: int


class LLMResponse(TypedDict):
    type: Literal["llm_response"]
    text: str
    input_tokens: int
    output_tokens: int


class StreamMessage(TypedDict):
    type: Literal["stream"]
    text: str


class CodeMessage(TypedDict):
    type: Literal["code"]
    language: str
    code: str


class ResultMessage(TypedDict):
    type: Literal["result"]
    command: str


class ErrorMessage(TypedDict):
    type: Literal["error"]
    message: str
    code: str
```

### 14. `backend/abs/streaming.py`

```python
"""Streaming output for ABS operations."""

import json
import sys
from typing import Optional


class ABSStream:
    """Stream output to VS Code extension (IPC) or terminal (text)."""

    def __init__(self, mode: str = "terminal"):
        self.mode = mode

    def progress(self, step: str, status: str = "in-progress",
                 step_num: int = 0, total: int = 0):
        if self.mode == "ipc":
            self._write({
                "type": "progress",
                "step": step,
                "status": status,
                "step_number": step_num,
                "total_steps": total,
            })
        else:
            emoji = "✅" if status == "done" else "▸"
            print(f"  {emoji} {step}")

    def markdown(self, text: str):
        if self.mode == "ipc":
            self._write({"type": "stream", "text": text})
        else:
            print(text)

    def code(self, code: str, language: str = "python"):
        if self.mode == "ipc":
            self._write({"type": "code", "language": language, "code": code})
        else:
            print(f"```{language}\n{code}\n```")

    def result(self, data: dict):
        if self.mode == "ipc":
            self._write({"type": "result", **data})
        else:
            for k, v in data.items():
                print(f"  {k}: {v}")

    def error(self, message: str, code: str = "UNKNOWN"):
        if self.mode == "ipc":
            self._write({"type": "error", "message": message, "code": code})
        else:
            print(f"❌ Error: {message}")

    def _write(self, obj: dict):
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()
```

---

## Package Configuration

### 15. `extension/package.json` — Changes

```jsonc
{
    "contributes": {
        "chatParticipants": [
            {
                "id": "kts",
                "name": "kts",
                "fullName": "KTS Knowledge Taxonomy System",
                "description": "Search and analyze knowledge taxonomy",
                "isSticky": true,
                "commands": [
                    // ... existing KTS commands ...
                ]
            },
            {
                "id": "abs",
                "name": "abs",
                "fullName": "ABS Payment Model Generator",
                "description": "Ingest deal docs, generate payment models, audit and Q&A",
                "isSticky": true,
                "commands": [
                    {
                        "name": "ingest",
                        "description": "Ingest deal documents (PDF) into knowledge base"
                    },
                    {
                        "name": "generate",
                        "description": "Generate payment waterfall model from ingested data"
                    },
                    {
                        "name": "audit",
                        "description": "Audit model against governing documents"
                    },
                    {
                        "name": "status",
                        "description": "Show deal processing status"
                    }
                ]
            }
        ]
    }
}
```

---

## PyInstaller Configuration

### 16. `packaging/kts.spec` — Changes

```python
# Add to hiddenimports list:
abs_hidden_imports = [
    'backend.abs',
    'backend.abs.orchestrator',
    'backend.abs.streaming',
    'backend.abs.ipc_protocol',
    'backend.abs.llm_bridge',
    'backend.abs.agents',
    'backend.abs.agents.agent_base',
    'backend.abs.agents.deal_scope',
    'backend.abs.agents.deal_manifest',
    'backend.abs.agents.ingestion_orchestrator',
    'backend.abs.agents.structured_extractor',
    'backend.abs.agents.waterfall_rule_extractor',
    'backend.abs.agents.trigger_event_extractor',
    'backend.abs.agents.definition_extractor',
    'backend.abs.agents.priority_payment_mapper',
    'backend.abs.agents.cross_reference_linker',
    'backend.abs.agents.model_creation_agent',
    'backend.abs.agents.qa_agent',
    'backend.abs.agents.audit_agent',
    'backend.abs.agents.validation_agent',
    'backend.abs.agents.pdf_converter',
    'backend.abs.agents.amendment_tracker',
    'backend.abs.agents.governing_doc_generator',
    'backend.abs.quality',
    'backend.abs.quality.quality_gate',
    'backend.abs.quality.metrics',
    'cli.abs',
    'cli.abs.ingest_cmd',
    'cli.abs.generate_cmd',
    'cli.abs.audit_cmd',
    'cli.abs.qa_cmd',
    'cli.abs.status_cmd',
]

# Add to datas for any ABS static resources:
abs_datas = [
    ('backend/abs/config/*.json', 'backend/abs/config'),
]
```

---

## Integration Wiring

### Extension Activation — Full Flow

```typescript
// extension/src/extension.ts

import * as vscode from 'vscode';
import { registerKTSParticipant } from './kts/ktsParticipant';
import { registerABSParticipant } from './abs/absParticipant';

export function activate(context: vscode.ExtensionContext) {
    // Existing KTS activation
    registerKTSParticipant(context);
    
    // New ABS activation (lightweight, no eager loading)
    registerABSParticipant(context);
    
    console.log('KTS + ABS extension activated');
}

export function deactivate() {}
```

### CLI Main — Full Flow

```python
# cli/main.py

import click
from cli.abs import abs_group

@click.group()
def main():
    """KTS — Knowledge Taxonomy System CLI."""
    pass

# ... existing KTS commands ...

# Register ABS subgroup
main.add_command(abs_group, "abs")

if __name__ == "__main__":
    main()
```

### Data Flow Summary

```
User ──► @abs /ingest bear_2006_he1
         │
         ▼
    absRequestHandler.ts
         │  detectDealId() → "bear_2006_he1"
         │  cmdIngest()
         │
         ▼
    ABSLLMBridge.spawnBackend()
         │  subprocess: kts_backend abs ingest --deal-id bear_2006_he1
         │
         ▼
    cli/abs/ingest_cmd.py
         │  ABSOrchestrator(config, llm)
         │  orch.ingest(deal_id, source_dir)
         │
         ▼
    backend/abs/orchestrator.py
         │  DealScope(deal_id)
         │  IngestionOrchestrator(config, scope, llm)
         │  orchestrator.execute(source_dir)
         │
         ▼
    13 ABS agents run in sequence
         │  Each agent: AgentBase.execute()
         │  Quality gate after each step
         │
         ▼
    Results stream back via IPC (JSON lines)
         │
         ▼
    Chat participant renders markdown in VS Code
```
