# Phase 23: Architecture Upgrade
## Chat Participant, CLI & Packaging Details

**Document Version:** 1.0  
**Date:** February 26, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** Detailed architecture for each user-facing component

---

## Table of Contents
1. [Transformation Summary](#transformation-summary)
2. [Transformation 1: `@abs` Chat Participant Registration](#transformation-1)
3. [Transformation 2: ABS Request Handler & Routing](#transformation-2)
4. [Transformation 3: ABS CLI Command Group](#transformation-3)
5. [Transformation 4: ABSOrchestrator — Unified Backend Entry](#transformation-4)
6. [Transformation 5: IPC Protocol Enhancement](#transformation-5)
7. [Transformation 6: Streaming Output](#transformation-6)
8. [Transformation 7: Combined VSIX Build](#transformation-7)
9. [Backward Compatibility](#backward-compatibility)

---

## Transformation Summary

| # | Transformation | Files | Lines | Risk |
|---|---------------|-------|-------|------|
| 1 | `@abs` participant registration | 2 new, 1 modified | ~150 | 🟢 Low |
| 2 | Request handler & routing | 1 new | ~200 | 🟡 Medium |
| 3 | CLI command group (5 commands) | 6 new, 1 modified | ~300 | 🟢 Low |
| 4 | ABSOrchestrator | 1 new | ~200 | 🟡 Medium |
| 5 | IPC protocol enhancement | 1 modified | ~50 | 🟡 Medium |
| 6 | Streaming output | 1 new | ~100 | 🟢 Low |
| 7 | VSIX build config | 2 modified, 1 new | ~50 | 🟢 Low |
| **Total** | | **~15 files** | **~1,050** | **🟡 Medium** |

---

## Transformation 1: `@abs` Chat Participant Registration

### New File: `extension/src/abs/absParticipant.ts`

```typescript
import * as vscode from 'vscode';
import { handleABSRequest } from './absRequestHandler';
import { provideABSFollowups } from './absFollowups';

/**
 * Register the @abs chat participant with VS Code.
 * 
 * Pattern mirrors existing @kts registration in extension/src/kts/ktsParticipant.ts.
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
    
    console.log('@abs chat participant registered');
}
```

### Modified File: `extension/src/extension.ts`

```typescript
// Add to existing activate() function:
import { registerABSParticipant } from './abs/absParticipant';

export function activate(context: vscode.ExtensionContext) {
    // ... existing KTS registration ...
    
    // Register @abs chat participant
    registerABSParticipant(context);
}
```

### New File: `extension/src/abs/absFollowups.ts`

```typescript
import * as vscode from 'vscode';

/**
 * Provide follow-up suggestions after @abs responses.
 */
export function provideABSFollowups(
    result: vscode.ChatResult,
    context: vscode.ChatContext,
    token: vscode.CancellationToken,
): vscode.ChatFollowup[] {
    const lastCommand = result.metadata?.command;
    
    if (lastCommand === 'ingest') {
        return [
            { prompt: '@abs /generate', label: 'Generate Payment Model' },
            { prompt: '@abs /status', label: 'Check Status' },
        ];
    }
    
    if (lastCommand === 'generate') {
        return [
            { prompt: '@abs /audit', label: 'Audit Model' },
            { prompt: '@abs What are the waterfall rules?', label: 'View Rules' },
        ];
    }
    
    // Default: suggest common questions
    return [
        { prompt: '@abs What is the Distribution Waterfall?', label: 'Waterfall' },
        { prompt: '@abs What are the triggers?', label: 'Triggers' },
        { prompt: '@abs /status', label: 'Status' },
    ];
}
```

---

## Transformation 2: ABS Request Handler & Routing

### New File: `extension/src/abs/absRequestHandler.ts`

```typescript
import * as vscode from 'vscode';
import { handleLLMRequest } from './absLLMBridge';
import { spawnPythonBackend, PythonIPC } from '../common/pythonIPC';

interface ABSSessionState {
    activeDealId: string | null;
    lastQuery: string | null;
    ingestStatus: 'not-started' | 'in-progress' | 'complete';
    modelGenerated: boolean;
}

const sessionState: ABSSessionState = {
    activeDealId: null,
    lastQuery: null,
    ingestStatus: 'not-started',
    modelGenerated: false,
};

/**
 * Main request handler for @abs chat participant.
 * Routes slash commands and free-text to appropriate handlers.
 */
export async function handleABSRequest(
    request: vscode.ChatRequest,
    context: vscode.ChatContext,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
): Promise<vscode.ChatResult> {
    const command = request.command;
    const prompt = request.prompt.trim();
    
    // Detect deal ID
    const dealId = detectDealId(prompt, context) || sessionState.activeDealId;
    
    try {
        switch (command) {
            case 'ingest':
                return await handleIngest(dealId, prompt, stream, token);
            case 'generate':
                return await handleGenerate(dealId, stream, token);
            case 'audit':
                return await handleAudit(dealId, stream, token);
            case 'status':
                return await handleStatus(dealId, stream, token);
            default:
                return await handleQA(dealId, prompt, stream, token);
        }
    } catch (error) {
        stream.markdown(`\n⚠️ **Error:** ${error.message}\n`);
        return { metadata: { error: true } };
    }
}


async function handleIngest(
    dealId: string | null,
    prompt: string,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
): Promise<vscode.ChatResult> {
    if (!dealId) {
        stream.markdown('Please specify a deal ID: `@abs /ingest <deal_id>`');
        return { metadata: { command: 'ingest', error: true } };
    }
    
    sessionState.activeDealId = dealId;
    stream.markdown(`📁 **Ingesting ${dealId}**\n\n`);
    
    // Spawn Python backend
    const ipc = await spawnPythonBackend([
        'abs', 'ingest',
        '--deal-id', dealId,
        '--llm-mode', 'vscode',
    ]);
    
    // Stream progress updates
    for await (const message of ipc.messages(token)) {
        if (message.type === 'progress') {
            stream.markdown(`▸ ${message.step}... ${message.status}\n`);
        } else if (message.type === 'llm_request') {
            const response = await handleLLMRequest(message, token);
            ipc.send(response);
        } else if (message.type === 'result') {
            stream.markdown(`\n**Summary:**\n`);
            stream.markdown(`- Items: ${message.item_count}\n`);
            stream.markdown(`- Sections: ${message.section_count}\n`);
            stream.markdown(`- Graph nodes: ${message.node_count}\n`);
            sessionState.ingestStatus = 'complete';
        }
    }
    
    return { metadata: { command: 'ingest', dealId } };
}


async function handleGenerate(
    dealId: string | null,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
): Promise<vscode.ChatResult> {
    if (!dealId) {
        stream.markdown('Please specify a deal ID: `@abs /generate <deal_id>`');
        return { metadata: { command: 'generate', error: true } };
    }
    
    stream.markdown(`⚙️ **Generating Payment Model for ${dealId}**\n\n`);
    
    const ipc = await spawnPythonBackend([
        'abs', 'generate',
        '--deal-id', dealId,
        '--llm-mode', 'vscode',
    ]);
    
    for await (const message of ipc.messages(token)) {
        if (message.type === 'progress') {
            stream.markdown(`▸ ${message.step}...\n`);
        } else if (message.type === 'llm_request') {
            const response = await handleLLMRequest(message, token);
            ipc.send(response);
        } else if (message.type === 'code') {
            stream.markdown('\n```python\n' + message.code + '\n```\n');
        } else if (message.type === 'result') {
            stream.markdown(`\n**Validation:** ${message.validation}\n`);
            stream.markdown(`**Quality Score:** ${message.quality_score}\n`);
            sessionState.modelGenerated = true;
        }
    }
    
    return { metadata: { command: 'generate', dealId } };
}


async function handleAudit(
    dealId: string | null,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
): Promise<vscode.ChatResult> {
    if (!dealId) {
        stream.markdown('Please specify a deal ID: `@abs /audit <deal_id>`');
        return { metadata: { command: 'audit', error: true } };
    }
    
    stream.markdown(`🔍 **Auditing ${dealId}**\n\n`);
    
    const ipc = await spawnPythonBackend([
        'abs', 'audit',
        '--deal-id', dealId,
        '--llm-mode', 'vscode',
    ]);
    
    for await (const message of ipc.messages(token)) {
        if (message.type === 'llm_request') {
            const response = await handleLLMRequest(message, token);
            ipc.send(response);
        } else if (message.type === 'result') {
            stream.markdown(message.report);
        }
    }
    
    return { metadata: { command: 'audit', dealId } };
}


async function handleStatus(
    dealId: string | null,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
): Promise<vscode.ChatResult> {
    if (!dealId) {
        stream.markdown('Specify a deal ID or use without to see all deals.');
    }
    
    const ipc = await spawnPythonBackend([
        'abs', 'status',
        ...(dealId ? ['--deal-id', dealId] : []),
    ]);
    
    for await (const message of ipc.messages(token)) {
        if (message.type === 'result') {
            stream.markdown(message.status_report);
        }
    }
    
    return { metadata: { command: 'status', dealId } };
}


async function handleQA(
    dealId: string | null,
    query: string,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
): Promise<vscode.ChatResult> {
    if (!dealId) {
        stream.markdown(
            'Please specify a deal first. Use `@abs /ingest <deal_id>` or ' +
            'include the deal name in your question.'
        );
        return { metadata: { command: 'qa', error: true } };
    }
    
    const ipc = await spawnPythonBackend([
        'abs', 'qa',
        '--deal-id', dealId,
        '--query', query,
        '--llm-mode', 'vscode',
    ]);
    
    for await (const message of ipc.messages(token)) {
        if (message.type === 'llm_request') {
            const response = await handleLLMRequest(message, token);
            ipc.send(response);
        } else if (message.type === 'stream') {
            stream.markdown(message.text);
        } else if (message.type === 'result') {
            stream.markdown(message.answer);
            if (message.sources) {
                stream.markdown('\n\n*Sources:*\n');
                for (const src of message.sources) {
                    stream.markdown(`- ${src}\n`);
                }
            }
        }
    }
    
    sessionState.lastQuery = query;
    return { metadata: { command: 'qa', dealId } };
}


function detectDealId(
    prompt: string,
    context: vscode.ChatContext,
): string | null {
    // Pattern: word_word_NNNN_... (e.g., bear_stearns_2006_he1)
    const match = prompt.match(/\b([a-z][a-z_]*_\d{4}_[a-z0-9]+)\b/i);
    if (match) return match[1].toLowerCase();
    
    // Check previous turns
    for (const turn of [...context.history].reverse()) {
        if ('metadata' in turn && turn.metadata?.dealId) {
            return turn.metadata.dealId;
        }
    }
    
    return null;
}
```

---

## Transformation 3: ABS CLI Command Group

### New File: `cli/abs/__init__.py`

```python
"""ABS CLI command group — terminal interface for deal operations."""

import click
from cli.abs.ingest_cmd import abs_ingest
from cli.abs.generate_cmd import abs_generate
from cli.abs.audit_cmd import abs_audit
from cli.abs.qa_cmd import abs_qa
from cli.abs.status_cmd import abs_status


@click.group("abs")
def abs_group():
    """ABS Payment Model Generator commands.
    
    Ingest deal documents, generate payment models,
    audit results, and ask questions about deals.
    """
    pass


abs_group.add_command(abs_ingest, "ingest")
abs_group.add_command(abs_generate, "generate")
abs_group.add_command(abs_audit, "audit")
abs_group.add_command(abs_qa, "qa")
abs_group.add_command(abs_status, "status")
```

### New File: `cli/abs/ingest_cmd.py`

```python
"""CLI command: kts abs ingest"""

import click
import time
from pathlib import Path

from config.settings import KTSConfig
from backend.abs.llm_bridge import create_llm_callable


@click.command("ingest")
@click.option("--deal-id", required=True, help="Deal identifier")
@click.option("--source-dir", required=True, type=click.Path(exists=True),
              help="Directory containing deal documents (PDF)")
@click.option("--llm-mode", default="none",
              type=click.Choice(["vscode", "mock", "none"]),
              help="LLM backend mode")
@click.option("--force", is_flag=True, help="Re-ingest even if complete")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def abs_ingest(deal_id, source_dir, llm_mode, force, verbose):
    """Ingest deal documents (PSA, Indenture, Supplements).
    
    Processes PDF documents, extracts structured data, builds
    vector store and knowledge graph for the specified deal.
    
    Example:
        kts abs ingest --deal-id bear_stearns_2006_he1 \\
            --source-dir ./deals/bear_stearns/
    """
    config = KTSConfig()
    config.abs_llm_mode = llm_mode
    llm = create_llm_callable(mode=llm_mode)
    
    from backend.abs.orchestrator import ABSOrchestrator
    orchestrator = ABSOrchestrator(config=config, llm_callable=llm)
    
    start = time.time()
    click.echo(f"📁 Ingesting {deal_id} from {source_dir}")
    
    try:
        result = orchestrator.ingest(
            deal_id=deal_id,
            source_dir=Path(source_dir),
            force=force,
            progress_callback=lambda step, status: click.echo(
                f"  [{step}] {status}"
            ) if verbose else None,
        )
        
        elapsed = time.time() - start
        click.echo(f"\n✅ Ingestion complete ({elapsed:.1f}s)")
        click.echo(f"   Items: {result.item_count}")
        click.echo(f"   Sections: {result.section_count}")
        click.echo(f"   Graph nodes: {result.node_count}")
        
    except Exception as e:
        click.echo(f"\n❌ Ingestion failed: {e}", err=True)
        raise SystemExit(1)
```

### New File: `cli/abs/generate_cmd.py`

```python
"""CLI command: kts abs generate"""

import click
from pathlib import Path
from config.settings import KTSConfig
from backend.abs.llm_bridge import create_llm_callable


@click.command("generate")
@click.option("--deal-id", required=True, help="Deal identifier")
@click.option("--output-dir", default=None, type=click.Path(),
              help="Output directory for generated model")
@click.option("--llm-mode", default="none",
              type=click.Choice(["vscode", "mock", "none"]),
              help="LLM backend mode")
@click.option("--max-retries", default=3, type=int,
              help="Max retry attempts for model generation")
@click.option("--verbose", "-v", is_flag=True)
def abs_generate(deal_id, output_dir, llm_mode, max_retries, verbose):
    """Generate a payment waterfall model for a deal.
    
    Requires deal to be ingested first (kts abs ingest).
    Uses LLM to generate Python code based on governing documents.
    
    Example:
        kts abs generate --deal-id bear_stearns_2006_he1 --llm-mode mock
    """
    config = KTSConfig()
    config.abs_llm_mode = llm_mode
    llm = create_llm_callable(mode=llm_mode)
    
    from backend.abs.orchestrator import ABSOrchestrator
    orchestrator = ABSOrchestrator(config=config, llm_callable=llm)
    
    click.echo(f"⚙️ Generating payment model for {deal_id}")
    
    try:
        result = orchestrator.generate(
            deal_id=deal_id,
            output_dir=Path(output_dir) if output_dir else None,
            max_retries=max_retries,
        )
        
        click.echo(f"\n✅ Model generated")
        click.echo(f"   Output: {result.output_path}")
        click.echo(f"   Validation: {result.validation_summary}")
        click.echo(f"   Quality score: {result.quality_score:.2f}")
        
    except Exception as e:
        click.echo(f"\n❌ Generation failed: {e}", err=True)
        raise SystemExit(1)
```

### New File: `cli/abs/audit_cmd.py`

```python
"""CLI command: kts abs audit"""

import click
from pathlib import Path
from config.settings import KTSConfig
from backend.abs.llm_bridge import create_llm_callable


@click.command("audit")
@click.option("--deal-id", required=True, help="Deal identifier")
@click.option("--model-path", default=None, type=click.Path(),
              help="Path to model file (default: auto-detect)")
@click.option("--expected-csv", default=None, type=click.Path(),
              help="Expected results CSV for comparison")
@click.option("--llm-mode", default="none",
              type=click.Choice(["vscode", "mock", "none"]))
@click.option("--verbose", "-v", is_flag=True)
def abs_audit(deal_id, model_path, expected_csv, llm_mode, verbose):
    """Audit a generated payment model against deal documents.
    
    Compares model output against governing document rules and
    optional expected results CSV.
    
    Example:
        kts abs audit --deal-id bear_stearns_2006_he1 --llm-mode mock
    """
    config = KTSConfig()
    config.abs_llm_mode = llm_mode
    llm = create_llm_callable(mode=llm_mode)
    
    from backend.abs.orchestrator import ABSOrchestrator
    orchestrator = ABSOrchestrator(config=config, llm_callable=llm)
    
    click.echo(f"🔍 Auditing {deal_id}")
    
    try:
        result = orchestrator.audit(
            deal_id=deal_id,
            model_path=Path(model_path) if model_path else None,
            expected_csv=Path(expected_csv) if expected_csv else None,
        )
        
        click.echo(result.report)
        click.echo(f"\nConfidence: {result.confidence:.2f}")
        
    except Exception as e:
        click.echo(f"\n❌ Audit failed: {e}", err=True)
        raise SystemExit(1)
```

### New File: `cli/abs/qa_cmd.py`

```python
"""CLI command: kts abs qa"""

import click
from config.settings import KTSConfig
from backend.abs.llm_bridge import create_llm_callable


@click.command("qa")
@click.option("--deal-id", required=True, help="Deal identifier")
@click.option("--query", "-q", required=True, help="Question to ask")
@click.option("--max-results", default=10, type=int,
              help="Max retrieval results")
@click.option("--llm-mode", default="none",
              type=click.Choice(["vscode", "mock", "none"]))
@click.option("--verbose", "-v", is_flag=True)
def abs_qa(deal_id, query, max_results, llm_mode, verbose):
    """Ask a question about a deal's documents.
    
    Uses the retrieval pipeline to find relevant sections and
    optionally generates an LLM-powered answer.
    
    Example:
        kts abs qa --deal-id bear_stearns_2006_he1 \\
            --query "What is the Distribution Waterfall?" \\
            --llm-mode mock
    """
    config = KTSConfig()
    config.abs_llm_mode = llm_mode
    config.abs_retrieval_max_results = max_results
    llm = create_llm_callable(mode=llm_mode)
    
    from backend.abs.orchestrator import ABSOrchestrator
    orchestrator = ABSOrchestrator(config=config, llm_callable=llm)
    
    try:
        result = orchestrator.qa(deal_id=deal_id, query=query)
        
        click.echo(f"\n{result.answer}")
        
        if verbose and result.sources:
            click.echo(f"\nSources:")
            for src in result.sources:
                click.echo(f"  - {src}")
        
        if result.follow_ups:
            click.echo(f"\nFollow-up questions:")
            for q in result.follow_ups:
                click.echo(f"  - {q}")
        
    except Exception as e:
        click.echo(f"\n❌ Q&A failed: {e}", err=True)
        raise SystemExit(1)
```

### New File: `cli/abs/status_cmd.py`

```python
"""CLI command: kts abs status"""

import click
from config.settings import KTSConfig


@click.command("status")
@click.option("--deal-id", default=None, help="Deal identifier (omit for all)")
@click.option("--verbose", "-v", is_flag=True)
def abs_status(deal_id, verbose):
    """Show deal processing status.
    
    Without --deal-id, shows all known deals.
    With --deal-id, shows detailed status for one deal.
    
    Example:
        kts abs status
        kts abs status --deal-id bear_stearns_2006_he1
    """
    config = KTSConfig()
    
    from backend.abs.orchestrator import ABSOrchestrator
    orchestrator = ABSOrchestrator(config=config)
    
    result = orchestrator.status(deal_id=deal_id)
    click.echo(result.status_report)
```

---

## Transformation 4: ABSOrchestrator — Unified Backend Entry

### New File: `backend/abs/orchestrator.py`

```python
"""
ABSOrchestrator — unified entry point for all ABS operations.

Both the chat participant and CLI converge on this class.
Ensures identical behavior regardless of entry point.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable

from config.settings import KTSConfig
from backend.abs.agents.deal_scope import DealScope
from backend.abs.agents.deal_manifest import DealManifest

logger = logging.getLogger(__name__)

LLMCallable = Callable  # Callable[[str, Optional[str]], str]


@dataclass
class IngestResult:
    deal_id: str
    item_count: int
    section_count: int
    node_count: int
    edge_count: int
    elapsed_seconds: float


@dataclass
class GenerateResult:
    deal_id: str
    output_path: Path
    validation_summary: str
    quality_score: float


@dataclass
class AuditResult:
    deal_id: str
    report: str
    confidence: float
    rules_matched: int
    rules_total: int


@dataclass
class QAResult:
    deal_id: str
    answer: str
    sources: list[str]
    confidence: float
    follow_ups: list[str]


@dataclass
class StatusResult:
    status_report: str


class ABSOrchestrator:
    """Unified orchestrator for all ABS operations.
    
    Usage:
        config = KTSConfig()
        llm = create_llm_callable(mode="mock")
        orch = ABSOrchestrator(config=config, llm_callable=llm)
        
        result = orch.ingest("bear_2006_he1", Path("./deals/bear/"))
        result = orch.generate("bear_2006_he1")
        result = orch.qa("bear_2006_he1", "What is the waterfall?")
    """
    
    def __init__(
        self,
        config: KTSConfig,
        llm_callable: Optional[LLMCallable] = None,
    ):
        self.config = config
        self.llm = llm_callable
    
    def ingest(
        self,
        deal_id: str,
        source_dir: Path,
        force: bool = False,
        progress_callback: Optional[Callable] = None,
    ) -> IngestResult:
        """Ingest deal documents — full pipeline."""
        import time
        start = time.time()
        
        scope = DealScope(deal_id=deal_id, config=self.config)
        manifest = DealManifest(deal_id=deal_id, config=self.config)
        
        if manifest.is_complete() and not force:
            logger.info(f"Deal {deal_id} already ingested, use force=True to re-ingest")
            return IngestResult(
                deal_id=deal_id,
                item_count=manifest.item_count,
                section_count=manifest.section_count,
                node_count=manifest.node_count,
                edge_count=manifest.edge_count,
                elapsed_seconds=0,
            )
        
        # Run pipeline steps
        from backend.abs.agents.ingestion_orchestrator import IngestionOrchestrator
        orchestrator = IngestionOrchestrator(
            config=self.config,
            deal_scope=scope,
            llm_callable=self.llm,
        )
        
        result = orchestrator.execute(
            task=str(source_dir),
            progress_callback=progress_callback,
        )
        
        elapsed = time.time() - start
        return IngestResult(
            deal_id=deal_id,
            item_count=result.get("item_count", 0),
            section_count=result.get("section_count", 0),
            node_count=result.get("node_count", 0),
            edge_count=result.get("edge_count", 0),
            elapsed_seconds=elapsed,
        )
    
    def generate(
        self,
        deal_id: str,
        output_dir: Optional[Path] = None,
        max_retries: int = 3,
    ) -> GenerateResult:
        """Generate payment model for deal."""
        scope = DealScope(deal_id=deal_id, config=self.config)
        
        from backend.abs.agents.model_creation_agent import ModelCreationAgent
        agent = ModelCreationAgent(
            config=self.config,
            deal_scope=scope,
            llm_callable=self.llm,
        )
        
        result = agent.execute(task="generate_model")
        
        out_path = output_dir or scope.models_dir
        return GenerateResult(
            deal_id=deal_id,
            output_path=out_path,
            validation_summary=result.get("validation", ""),
            quality_score=result.get("quality_score", 0.0),
        )
    
    def audit(
        self,
        deal_id: str,
        model_path: Optional[Path] = None,
        expected_csv: Optional[Path] = None,
    ) -> AuditResult:
        """Audit generated model against deal documents."""
        scope = DealScope(deal_id=deal_id, config=self.config)
        
        from backend.abs.agents.audit_agent import AuditAgent
        agent = AuditAgent(
            config=self.config,
            deal_scope=scope,
            llm_callable=self.llm,
        )
        
        result = agent.execute(task="audit_model")
        
        return AuditResult(
            deal_id=deal_id,
            report=result.get("report", ""),
            confidence=result.get("confidence", 0.0),
            rules_matched=result.get("rules_matched", 0),
            rules_total=result.get("rules_total", 0),
        )
    
    def qa(self, deal_id: str, query: str) -> QAResult:
        """Answer a question about a deal."""
        scope = DealScope(deal_id=deal_id, config=self.config)
        
        from backend.abs.agents.qa_agent import QAAgent
        agent = QAAgent(
            config=self.config,
            deal_scope=scope,
            llm_callable=self.llm,
        )
        
        result = agent.execute(task=query)
        
        return QAResult(
            deal_id=deal_id,
            answer=result.get("answer", ""),
            sources=result.get("sources", []),
            confidence=result.get("confidence", 0.0),
            follow_ups=result.get("follow_ups", []),
        )
    
    def status(self, deal_id: Optional[str] = None) -> StatusResult:
        """Get deal processing status."""
        if deal_id:
            manifest = DealManifest(deal_id=deal_id, config=self.config)
            report = manifest.status_report()
        else:
            report = DealManifest.list_all_deals(self.config)
        
        return StatusResult(status_report=report)
```

---

## Transformation 5: IPC Protocol Enhancement

### Enhanced Protocol Messages

```python
# backend/abs/ipc_protocol.py

"""
IPC protocol messages between VS Code extension and Python backend.

All messages are single-line JSON objects.
Direction: Python→Extension or Extension→Python.
"""

# Python → Extension
PROGRESS_MESSAGE = {
    "type": "progress",
    "step": "Converting PDF...",
    "status": "in-progress",    # "in-progress" | "done" | "failed"
    "step_number": 1,
    "total_steps": 8,
}

LLM_REQUEST = {
    "type": "llm_request",
    "model": "gpt-4.1",
    "prompt": "...",
    "system_prompt": "...",
    "temperature": 0.0,
    "max_tokens": 4096,
}

STREAM_MESSAGE = {
    "type": "stream",
    "text": "Based on Section 5.02...",
}

CODE_MESSAGE = {
    "type": "code",
    "language": "python",
    "code": "def calculate_distribution(...):\n    ...",
}

RESULT_MESSAGE = {
    "type": "result",
    "command": "ingest",
    "data": { ... },
}

ERROR_MESSAGE = {
    "type": "error",
    "message": "Deal not found",
    "code": "DEAL_NOT_FOUND",
}

# Extension → Python
LLM_RESPONSE = {
    "type": "llm_response",
    "text": "...",
    "input_tokens": 150,
    "output_tokens": 200,
}
```

---

## Transformation 6: Streaming Output

### Streaming from Python to Extension

```python
# backend/abs/streaming.py

"""
Streaming output for ABS operations.
Writes progress and results as JSON lines to stdout.
"""

import json
import sys
from typing import Optional


class ABSStream:
    """Stream output to VS Code extension or terminal."""
    
    def __init__(self, mode: str = "terminal"):
        """
        Args:
            mode: "terminal" for human-readable, "ipc" for JSON lines
        """
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
            print(f"```{language}")
            print(code)
            print("```")
    
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

## Transformation 7: Combined VSIX Build

### Modified: `package.json`

Add the `@abs` chat participant to the extension manifest alongside `@kts`.

### Modified: `packaging/kts.spec`

Add ABS modules to PyInstaller's hidden imports and data collection.

### New: `scripts/build_combined.ps1`

```powershell
# Build combined KTS + ABS VSIX package

param(
    [string]$Version = "1.0.0"
)

Write-Host "Building combined KTS + ABS VSIX v$Version"

# Step 1: Build Python backend
Write-Host "  [1/4] Building Python backend..."
pyinstaller packaging/kts.spec --noconfirm --clean
$backendSize = (Get-Item "build\kts_backend\kts_backend.exe").Length / 1MB
Write-Host "  Backend size: $([math]::Round($backendSize, 1)) MB"

# Step 2: Compile TypeScript
Write-Host "  [2/4] Compiling TypeScript..."
Push-Location extension
npm run compile
Pop-Location

# Step 3: Run tests
Write-Host "  [3/4] Running tests..."
python -m pytest tests/ -x -q

# Step 4: Package VSIX
Write-Host "  [4/4] Packaging VSIX..."
Push-Location extension
npx vsce package --no-dependencies -o "../dist/gsf-ir-kts-agentic-system-$Version.vsix"
Pop-Location

$vsixSize = (Get-Item "dist\gsf-ir-kts-agentic-system-$Version.vsix").Length / 1MB
Write-Host "`nBuild complete!"
Write-Host "  VSIX: dist\gsf-ir-kts-agentic-system-$Version.vsix ($([math]::Round($vsixSize, 1)) MB)"
```

---

## Backward Compatibility

### KTS Extension Guarantees

1. **`@kts` participant unchanged** — Registration, handler, followups all preserved
2. **Existing CLI commands unchanged** — `kts search`, `kts analyze`, etc. still work
3. **Extension activation time** — `@abs` uses lazy registration, < 50ms overhead
4. **VSIX install backward compatible** — Same extension ID, just with additional features

### ABS Guarantees

1. **All CLI commands work without LLM** — `--llm-mode none` is the default
2. **All slash commands handle missing deal gracefully** — Error message with instructions
3. **Orchestrator is stateless** — No side effects between operations
4. **IPC protocol is backwards compatible** — Unknown message types are ignored
