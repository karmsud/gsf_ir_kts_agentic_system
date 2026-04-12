# VS Code Chat Agent — Project Bootstrap Template

> **Purpose**: Drop this file into any new repo and ask GitHub Copilot to scaffold a complete VS Code Chat Participant agent with a Python backend, RAG pipeline, golden test harness, and VSIX packaging.
>
> **Usage**: `@workspace set up this project using the blueprint in docs/VSCODE_CHAT_AGENT_BOOTSTRAP.md`
>
> **Origin**: Distilled from the GSF IR KTS Agentic System (16 phases, 2300+ tests, Feb 2026)

Core Architecture (§2-5): Full project structure, 3-layer architecture (extension orchestrator → Python backend → Copilot LLM), CLI bridge pattern with runCliJson(), Backend Runner factory (exe vs venv), Python data models with exact field name mapping.

RAG Pipeline (§6-7): RAG_CONFIG hardcoded constant, token budget computation, 9-stage retrieval pipeline, model selection (request.model → setting → auto-detect), system prompt template, streaming generation with fallback, the LanguageModelChatMessage.User() pattern (no .System()).

VS Code Native Features (§8-10): Slash command mode routing table, #file/#selection/#editor reference extraction, deterministic follow-up generation (zero LLM cost), progress streaming, native citations (stream.reference()), confirmation dialogs, conversation history extraction, signal-gated query rewriting, session memory with TTL.

Testing (§11-12): Complete golden answer test harness — test definition schema, 6 categories, runner, scorer (5 dimensions + weights), regression detection, baseline pinning. Mock vscode pattern for Node.js tests.

DevOps (§13-15): F5 dev workflow (< 5s edit-test cycle), launch.json, VSIX build pipeline (PowerShell), PyInstaller spec, .vscodeignore, VSIX verification, 3 user settings rule.

Advanced (§16-17): Scoped knowledge spaces (folder = namespace = slash command), confidence scoring tiers, gap detection.

Guardrails (§18-19): 7 critical gotchas (all from real bugs), comprehensive checklist, 16 lessons learned.

To use it in a future project, just drop the file and tell Copilot:
@workspace set up this project using the blueprint in docs/VSCODE_CHAT_AGENT_BOOTSTRAP.md

---

## Table of Contents

1. [Quick Start — What to Tell Copilot](#1-quick-start)
2. [Project Structure](#2-project-structure)
3. [Extension Architecture](#3-extension-architecture)
4. [Chat Participant Setup](#4-chat-participant-setup)
5. [Backend Bridge (Python ↔ JS)](#5-backend-bridge)
6. [RAG Pipeline](#6-rag-pipeline)
7. [LLM Generation via VS Code LM API](#7-llm-generation)
8. [Slash Commands & Mode Routing](#8-slash-commands)
9. [VS Code Native Features](#9-vscode-native-features)
10. [Conversation Memory & Session Intelligence](#10-conversation-memory)
11. [Golden Answer Test Harness](#11-golden-test-harness)
12. [Unit & Integration Testing](#12-testing)
13. [Dev Environment & F5 Workflow](#13-dev-environment)
14. [VSIX Build & Packaging](#14-vsix-packaging)
15. [Settings & Configuration](#15-settings)
16. [Scoped Knowledge Spaces](#16-scoped-knowledge)
17. [Confidence Scoring & Gap Detection](#17-confidence-scoring)
18. [Critical Gotchas](#18-gotchas)
19. [Checklist](#19-checklist)
20. [VS Code API Quick Reference](#20-api-reference)

---

## 1. Quick Start — What to Tell Copilot {#1-quick-start}

Copy-paste this prompt to bootstrap a new agent project:

```
@workspace Using the blueprint in docs/VSCODE_CHAT_AGENT_BOOTSTRAP.md, scaffold a
VS Code Chat Participant extension called "@<AGENT_NAME>" that:
1. Uses a Python backend for retrieval/processing (CLI bridge, not HTTP)
2. Uses the VS Code LM API (Copilot models) for answer generation
3. Has a chat participant with slash commands: /search, /deep, /define, /summary
4. Includes a golden answer test harness (LLM-as-judge, 5 dimensions)
5. Packages as a VSIX with PyInstaller-compiled backend
6. Supports F5 dev workflow with Extension Development Host

Domain: <YOUR_DOMAIN>
Corpus: <YOUR_DOCUMENT_TYPES>
```

Replace `<AGENT_NAME>`, `<YOUR_DOMAIN>`, and `<YOUR_DOCUMENT_TYPES>` with your specifics.

---

## 2. Project Structure {#2-project-structure}

```
your-agent/
├── .vscode/
│   └── launch.json              # F5 Extension Dev Host config
├── backend/
│   ├── __init__.py
│   ├── common/
│   │   └── models.py            # Dataclasses: TextChunk, Citation, SearchResult
│   ├── ingestion/               # Document crawl → chunk → embed → store
│   ├── retrieval/               # Vector search, BM25, reranking, confidence
│   ├── extraction/              # Domain-specific entity extraction
│   ├── graph/                   # Knowledge graph (NetworkX)
│   ├── vector/                  # ChromaDB / embedding provider
│   └── agents/                  # LLM-powered backend agents (optional)
├── cli/
│   ├── __init__.py
│   └── main.py                  # CLI entry: python -m cli.main <command> <args>
├── config/
│   └── settings.py              # Backend configuration dataclass
├── extension/
│   ├── extension.js             # VS Code activate/deactivate, command registration
│   ├── package.json             # Extension manifest (commands, settings, participant)
│   ├── .vscodeignore            # Exclude dev files from VSIX
│   ├── chat/
│   │   └── participant.js       # Chat handler: RAG pipeline + LLM generation
│   ├── copilot/
│   │   └── tool.js              # Backend bridge: JS → CLI → Python → JSON
│   ├── commands/                 # VS Code command handlers (one file each)
│   │   ├── crawl_ingest.js
│   │   ├── search.js
│   │   ├── select_source.js
│   │   ├── status.js
│   │   └── doctor.js
│   ├── lib/
│   │   ├── backend_runner.js    # ExeRunner / VenvRunner factory
│   │   ├── venv_manager.js      # Managed Python venv lifecycle
│   │   ├── kts_backend.js       # runCliJson() — the CLI bridge
│   │   └── scope_discovery.js   # Folder-based knowledge space detection
│   ├── panels/                  # Webview panels (optional)
│   └── bin/                     # PyInstaller exe bundled here for VSIX
│       └── win-x64/
│           └── your-backend/
│               └── your-backend.exe
├── tests/
│   ├── golden_answer_tests.json # Golden Q&A pairs (see §11)
│   ├── golden_answer_runner.js  # Run all golden tests through full pipeline
│   ├── golden_answer_scorer.js  # LLM-as-judge scoring (5 dimensions)
│   ├── golden_answer_results/   # Timestamped results + scores JSON
│   ├── golden_answer_baseline.json  # Pinned baseline for regression detection
│   ├── test_rag_generation.js   # Mocked vscode unit tests
│   ├── conftest.py              # Pytest fixtures
│   └── test_*.py                # Python backend tests
├── scripts/
│   ├── build_vsix.ps1           # Master build: models → backend → VSIX
│   ├── build_backend.ps1        # PyInstaller compilation
│   ├── download_models.ps1      # Fetch ML models (embeddings, cross-encoder)
│   └── clean.ps1                # Remove build artifacts
├── packaging/
│   └── your_backend.spec        # PyInstaller spec file
├── docs/
│   ├── ARCHITECTURE.md
│   ├── BUILD_GUIDE.md
│   └── TESTING.md
├── requirements.txt             # Python dependencies
└── README.md
```

---

## 3. Extension Architecture {#3-extension-architecture}

### Core Principle

The VS Code extension is the **orchestrator**. The Python backend is the **retrieval engine**. The Copilot LLM is the **generator**. Keep these three layers cleanly separated.

```
┌─────────────────────────────────────────────────────┐
│  VS Code Extension (JavaScript)                     │
│                                                     │
│  extension.js          — Activation, command registry│
│  chat/participant.js   — Chat handler, RAG pipeline  │
│  copilot/tool.js       — Backend CLI bridge          │
│  lib/kts_backend.js    — runCliJson() subprocess     │
│  lib/backend_runner.js — Exe vs Venv abstraction     │
│  commands/*.js         — One file per command        │
└───────────────────┬────────────────┬────────────────┘
                    │ CLI (stdin/stdout JSON)  │ vscode.lm API
                    ▼                         ▼
┌──────────────────────┐    ┌──────────────────────────┐
│  Python Backend       │    │  Copilot LLM (GPT-4.1,   │
│  cli/main.py          │    │  Claude, etc.)             │
│  → search, ingest,    │    │  → Answer generation       │
│    crawl, status      │    │  → Multi-query expansion   │
│  Returns JSON to      │    │  → Follow-up generation    │
│  stdout               │    │  → Test scoring (judge)    │
└──────────────────────┘    └──────────────────────────┘
```

### Data Flow (Single Query)

```
User types "@agent what is X?"
  → participant.js receives (request, stream, token)
  → Extracts query + references (#file, #selection)
  → Calls tool.js(query, options)
    → tool.js calls runCliJson(['search', query, '--max-results', '10'])
      → Spawns: python -m cli.main search "what is X?" --max-results 10
      → Backend: vector search → BM25 → RRF fusion → rerank → confidence
      → Returns JSON: { context_chunks: [...], citations: [...], confidence }
  → participant.js receives SearchResult
  → Selects LLM model (request.model → setting → auto-detect)
  → Builds context block: [Document: name, Section: X]\nchunk_content
  → Sends: [SystemPrompt + Context + Question] → model.sendRequest()
  → Streams tokens: for await (chunk of response.text) { stream.markdown(chunk) }
  → Appends citations via stream.reference() or markdown
  → Generates follow-up suggestions via response.followUp()
```

---

## 4. Chat Participant Setup {#4-chat-participant-setup}

### package.json — Participant Declaration

```json
{
  "name": "your-agent-extension",
  "displayName": "Your Agent",
  "version": "0.1.0",
  "engines": { "vscode": "^1.95.0" },
  "main": "./extension.js",
  "activationEvents": ["onStartupFinished"],
  "contributes": {
    "chatParticipants": [
      {
        "id": "your-agent.assistant",
        "name": "agent",
        "fullName": "Your Agent Name",
        "description": "Describe what this agent does in one sentence.",
        "isSticky": true,
        "commands": [
          { "name": "search", "description": "Retrieve concise context and citations" },
          { "name": "deep", "description": "Retrieve more chunks for complex queries" },
          { "name": "define", "description": "Look up a defined term and its dependency chain" },
          { "name": "summary", "description": "Generate a structured summary" }
        ]
      }
    ],
    "commands": [
      { "command": "your-agent.selectSource", "title": "Agent: Select Source Folder" },
      { "command": "your-agent.ingest", "title": "Agent: Ingest Documents" },
      { "command": "your-agent.status", "title": "Agent: Status" },
      { "command": "your-agent.doctor", "title": "Agent: Doctor (Diagnostics)" },
      { "command": "your-agent.runGoldenTests", "title": "Agent: Run Golden Answer Tests" }
    ],
    "configuration": {
      "title": "Your Agent",
      "properties": {
        "your-agent.sourceFolder": {
          "type": "string",
          "default": "",
          "order": 1,
          "description": "Folder containing your documents."
        },
        "your-agent.logLevel": {
          "type": "string",
          "default": "normal",
          "enum": ["normal", "verbose"],
          "order": 2,
          "description": "Output panel logging detail."
        },
        "your-agent.model": {
          "type": "string",
          "default": "auto",
          "enum": ["auto", "gpt-4.1", "gpt-4o", "gpt-4o-mini", "claude-sonnet-4"],
          "enumDescriptions": [
            "Use your active Copilot model (recommended)",
            "GPT-4.1 — strongest reasoning, 1M context",
            "GPT-4o — balanced quality and speed",
            "GPT-4o Mini — fast and lightweight",
            "Claude Sonnet 4 — strong analysis"
          ],
          "order": 3,
          "description": "LLM for answer generation. 'auto' uses your active Copilot model."
        },
        "your-agent.backendMode": {
          "type": "string",
          "default": "auto",
          "enum": ["auto", "venv", "exe"],
          "order": 100,
          "markdownDescription": "**[Developer]** Backend execution: 'auto' (prefer exe), 'venv' (live Python), 'exe' (compiled)."
        }
      }
    }
  }
}
```

### extension.js — Activation

```javascript
const vscode = require('vscode');
const { registerChatParticipant } = require('./chat/participant');
const { initBackendRunner, runCliJson } = require('./lib/kts_backend');

async function activate(context) {
  const outputChannel = vscode.window.createOutputChannel('Your Agent', { log: true });
  outputChannel.appendLine('[Agent] Activating...');

  // Shared context — passed to all command handlers and the chat participant
  const shared = {
    context,
    outputChannel,
    workspaceRoot: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '',
  };

  // Initialize backend runner (venv or exe based on settings)
  await initBackendRunner(vscode, context, outputChannel);

  // Register chat participant
  registerChatParticipant(vscode, context, shared);

  // Register commands
  function register(command, handler) {
    context.subscriptions.push(
      vscode.commands.registerCommand(command, async () => {
        try { await handler(shared); }
        catch (err) {
          outputChannel.appendLine(`[Agent] ${command} failed: ${err.message}`);
          vscode.window.showErrorMessage(`Command failed: ${err.message}`);
        }
      })
    );
  }

  register('your-agent.selectSource', require('./commands/select_source'));
  register('your-agent.ingest', require('./commands/ingest'));
  register('your-agent.status', require('./commands/status'));
  register('your-agent.doctor', require('./commands/doctor'));

  // Golden test command — only in dev host
  register('your-agent.runGoldenTests', async (shared) => {
    const { runGoldenTests } = require('../tests/golden_answer_runner');
    const { scoreResults, saveBaseline } = require('../tests/golden_answer_scorer');
    const results = await runGoldenTests(vscode, outputChannel, shared);
    const model = await selectModel(vscode, null);
    if (model) {
      const scores = await scoreResults(vscode, model, results, outputChannel);
      // Prompt to save as baseline
      const avg = scores.average.toFixed(2);
      const choice = await vscode.window.showInformationMessage(
        `Golden tests complete: ${avg}/5.00 Avg. Save as baseline?`,
        'Yes', 'No'
      );
      if (choice === 'Yes') saveBaseline(scores);
    }
  });

  outputChannel.appendLine('[Agent] Activated successfully.');
}

function deactivate() {}
module.exports = { activate, deactivate };
```

---

## 5. Backend Bridge (Python ↔ JS) {#5-backend-bridge}

### Design Principle

The extension talks to the Python backend via **CLI subprocess** (not HTTP). This enables:
- VSIX packaging with PyInstaller exe (no server to manage)
- Clean process lifecycle (spawn → JSON stdout → exit)
- Same CLI works for terminal debugging
- Dev mode: live Python venv. Prod mode: compiled exe.

### CLI Protocol

```
Extension → Backend:   python -m cli.main <command> [args...] --json
Backend  → Extension:  JSON on stdout, logs on stderr
```

### kts_backend.js — The Bridge

```javascript
const { spawn } = require('child_process');

/**
 * Call the Python backend CLI and parse JSON response.
 * @param {object} opts - { workspaceRoot, sourcePath, args }
 * @returns {Promise<object>} Parsed JSON from backend stdout
 */
async function runCliJson({ workspaceRoot, sourcePath, args }) {
  const runner = getBackendRunner(); // ExeRunner or VenvRunner
  const env = {
    ...process.env,
    WORKSPACE_ROOT: workspaceRoot || '',
    SOURCE_PATH: sourcePath || '',
  };

  return new Promise((resolve, reject) => {
    const proc = runner.spawn(args, { env });
    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', d => stdout += d.toString());
    proc.stderr.on('data', d => stderr += d.toString());

    proc.on('close', code => {
      if (code !== 0) {
        return reject(new Error(`Backend exited ${code}: ${stderr.slice(-500)}`));
      }
      try {
        resolve(JSON.parse(stdout));
      } catch (err) {
        reject(new Error(`Invalid JSON from backend: ${err.message}`));
      }
    });
  });
}
```

### Backend Runner Factory

```javascript
class ExeRunner {
  constructor(exePath) { this.exePath = exePath; }
  spawn(args, opts) { return spawn(this.exePath, args, opts); }
}

class VenvRunner {
  constructor(pythonPath, cliModule) {
    this.pythonPath = pythonPath;
    this.cliModule = cliModule;
  }
  spawn(args, opts) {
    return spawn(this.pythonPath, ['-m', this.cliModule, ...args], opts);
  }
}

class BackendRunnerFactory {
  static async create(mode, channel, context, venvManager, outputChannel) {
    // Exe mode: look for bundled executable
    if (mode === 'exe' || mode === 'auto') {
      const exePath = path.join(context.extensionPath, 'bin', 'win-x64', 'your-backend', 'your-backend.exe');
      if (fs.existsSync(exePath)) return new ExeRunner(exePath);
    }
    // Venv mode: use Python directly
    const pythonPath = venvManager?.pythonPath || 'python';
    return new VenvRunner(pythonPath, 'cli.main');
  }
}
```

### tool.js — The Backend Bridge Function

```javascript
const { runCliJson, getWorkspaceRoot } = require('../lib/kts_backend');

module.exports = async function backendTool(query, options = {}) {
  const workspaceRoot = getWorkspaceRoot(options.workspaceRoot);
  const maxResults = Number.isInteger(options.maxResults) ? options.maxResults : 5;

  const args = ['search', query, '--max-results', String(maxResults)];
  if (options.deepMode) args.push('--deep');
  if (options.docType) args.push('--doc-type', String(options.docType));
  if (options.sessionId) args.push('--session-id', String(options.sessionId));
  if (options.retrievalMode) args.push('--retrieval-mode', String(options.retrievalMode));

  try {
    const searchResult = await runCliJson({ workspaceRoot, args });
    return { status: 'ok', query, search_result: searchResult };
  } catch (error) {
    return { status: 'error', query, error: error.message };
  }
};
```

### Python CLI Entry Point

```python
# cli/main.py
import sys, json, argparse

def main():
    parser = argparse.ArgumentParser(prog='your-agent')
    sub = parser.add_subparsers(dest='command')

    # search command
    sp = sub.add_parser('search')
    sp.add_argument('query')
    sp.add_argument('--max-results', type=int, default=5)
    sp.add_argument('--deep', action='store_true')
    sp.add_argument('--doc-type', default=None)
    sp.add_argument('--session-id', default=None)

    # ingest command
    ip = sub.add_parser('ingest')
    ip.add_argument('source_path')

    # status command
    sub.add_parser('status')

    args = parser.parse_args()

    if args.command == 'search':
        from backend.retrieval.search import search
        result = search(args.query, max_results=args.max_results, deep=args.deep)
        json.dump(result.to_dict(), sys.stdout)
    elif args.command == 'ingest':
        from backend.ingestion.pipeline import ingest
        result = ingest(args.source_path)
        json.dump(result.to_dict(), sys.stdout)
    elif args.command == 'status':
        from backend.common.status import get_status
        json.dump(get_status(), sys.stdout)

if __name__ == '__main__':
    main()
```

### Backend Data Models

```python
# backend/common/models.py
from dataclasses import dataclass, field, asdict
from typing import Optional

@dataclass
class TextChunk:
    chunk_id: str
    doc_id: str
    content: str                              # The actual text
    source_path: str = ''                     # File path
    chunk_index: int = 0
    doc_type: str = ''
    doc_name: str = ''                        # Friendly name
    section: str = ''                         # Section heading
    page: int | None = None
    entities: list[str] = field(default_factory=list)
    keyphrases: list[str] = field(default_factory=list)

@dataclass
class Citation:
    doc_id: str
    doc_name: str = ''
    source_path: str = ''
    uri: str = ''
    version: str = ''
    section: str = ''
    page: int | None = None

@dataclass
class SearchResult:
    context_chunks: list[TextChunk] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    confidence: float = 0.0
    confidence_tier: str = 'UNKNOWN'         # HIGH, MEDIUM, LOW, SPECULATIVE
    gaps: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)
```

**CRITICAL**: The extension JS must use the **exact same field names** as the Python dataclass. `content` (not `text`). `source_path` (not `source`). `section` on Citation (not on TextChunk unless explicitly set).

---

## 6. RAG Pipeline {#6-rag-pipeline}

### Internal Configuration (Not User-Facing)

```javascript
// participant.js — top of file
const RAG_CONFIG = {
  maxContextChunks: 100,           // Upper bound before token trimming
  multiQueryVariants: 4,           // Number of query rewrites
  selfRagEnabled: false,           // Toggle iterative refinement
  selfRagMaxRounds: 3,
  critiqueEnabled: false,          // Toggle critique loop
  critiqueMaxRounds: 3,
  TOKEN_RATIO: 4,                  // Chars per token estimate
  RESERVED_TOKENS: 5000,           // System prompt + overhead
};
```

**Design Rule**: Never expose RAG tuning parameters as user settings. Use a hardcoded `RAG_CONFIG` constant. Only expose 3 user settings: `sourceFolder`, `logLevel`, `model`.

### Token Budget Computation

```javascript
function computeTokenBudget(model) {
  const maxTokens = model.maxInputTokens || 128000;
  return Math.floor(maxTokens * 0.8);  // 80% utilization
}

function computeMaxChunks(tokenBudget) {
  return Math.min(200, Math.floor(tokenBudget * 0.6 / 500));
  // 60% of budget for context, 500 tokens per chunk average
}
```

### Retrieval Pipeline Stages (Backend — Python)

```
1. Query Expansion      → BM25 + multi-query variants (optional)
2. Vector Search        → ChromaDB cosine similarity, top-K
3. BM25 Hybrid Search   → Inverted index keyword search
4. RRF Fusion           → Reciprocal Rank Fusion: w_bm25=0.4, w_vector=0.6
5. MMR Diversity         → Greedy maximal marginal relevance (λ=0.7)
6. Cross-Encoder Rerank → ONNX cross-encoder model for precision
7. Graph Expansion       → Follow DEPENDS_ON / REFERS_TO edges
8. Confidence Scoring    → HIGH / MEDIUM / LOW / SPECULATIVE tiers
9. Gap Detection         → NER requested vs found entity comparison
```

Each stage is **feature-flagged** in the config dataclass and can be toggled independently.

---

## 7. LLM Generation via VS Code LM API {#7-llm-generation}

### Model Selection

```javascript
/**
 * Select a Copilot LLM model.
 * Priority: request.model → setting → auto-detect
 */
async function selectModel(vscode, requestModel) {
  // 1. Honor user's chat model picker selection
  if (requestModel && typeof requestModel.sendRequest === 'function') {
    return requestModel;
  }

  // 2. Check extension setting
  const config = vscode.workspace.getConfiguration('your-agent');
  const modelSetting = config.get('model') || 'auto';

  if (modelSetting !== 'auto' && vscode.lm?.selectChatModels) {
    try {
      const models = await vscode.lm.selectChatModels({ vendor: 'copilot', family: modelSetting });
      if (models?.length) return models[0];
    } catch (_) {}
  }

  // 3. Auto-detect: try preferred families in order
  if (vscode.lm?.selectChatModels) {
    for (const family of ['gpt-4.1', 'gpt-4o', 'claude-sonnet-4', 'gpt-4o-mini']) {
      try {
        const models = await vscode.lm.selectChatModels({ vendor: 'copilot', family });
        if (models?.length) return models[0];
      } catch (_) {}
    }
    // Last resort: any copilot model
    try {
      const models = await vscode.lm.selectChatModels({ vendor: 'copilot' });
      if (models?.length) return models[0];
    } catch (_) {}
  }

  return null;
}
```

### System Prompt Template

```javascript
// DOMAIN-SPECIFIC — customize for your agent
const SYSTEM_PROMPT = [
  'You are AgentName — a precise, cautious [domain] assistant.',
  'Answer the user\'s question using ONLY the retrieved document excerpts below.',
  '',
  'Rules:',
  '- Provide a direct, document-grounded answer in a professional conversational tone.',
  '- When quoting, cite the document name and section/page naturally in your prose.',
  '- If language is ambiguous or silent, say so and quote the relevant text.',
  '- If documents conflict, present both citations without resolving the conflict',
  '  unless the documents include a priority rule.',
  '- Do not invent rules, assumptions, or interpretations beyond what is stated.',
  '- Do not use general knowledge or external sources.',
  '- If the retrieved context does not contain an answer, say so explicitly.',
].join('\n');
```

### Context Block Builder

```javascript
/**
 * Build labeled context block from search results.
 * Format: [Document: name, Section: X, Page: Y]\ncontent
 */
function buildContextBlock(searchResult) {
  const chunks = searchResult.context_chunks || [];
  const citations = searchResult.citations || [];
  if (!chunks.length) return '';

  // Citation lookup: doc_id → { section, page, doc_name }
  const citationMap = {};
  for (const cit of citations) {
    const key = cit.doc_id || cit.doc_name;
    if (key && !citationMap[key]) citationMap[key] = cit;
  }

  return chunks.map((c, i) => {
    const body = (c.content || '').trim();

    // Resolve document name
    let docName = c.doc_name || '';
    if (!docName && c.source_path) {
      docName = c.source_path.replace(/\\/g, '/').split('/').pop() || '';
    }
    if (!docName) docName = c.doc_id || `source-${i + 1}`;

    // Cross-reference citation for section/page
    const cit = citationMap[c.doc_id] || citationMap[c.doc_name] || {};
    const section = c.section || cit.section || null;
    const page = c.page ?? cit.page ?? null;

    let label = `[Document: ${docName}`;
    if (section) label += `, Section: ${section}`;
    if (page != null) label += `, Page: ${page}`;
    label += ']';

    return `${label}\n${body}`;
  }).join('\n\n');
}
```

### Streaming Generation

```javascript
/**
 * Generate answer via LLM and stream into chat.
 *
 * CRITICAL: vscode.LanguageModelChatMessage has NO .System() method!
 * Embed system prompt in the User message.
 */
async function generateAnswer(vscode, model, stream, token, query, searchResult) {
  const contextBlock = buildContextBlock(searchResult);
  if (!contextBlock) return false;

  const tokenBudget = computeTokenBudget(model);
  const maxChunks = computeMaxChunks(tokenBudget);

  // Trim context to token budget
  const trimmedContext = trimContextToTokenBudget(contextBlock, tokenBudget);

  const userMessage = [
    SYSTEM_PROMPT,
    '',
    '## Retrieved Context',
    trimmedContext,
    '',
    '## Question',
    query,
  ].join('\n');

  // ⚠️ User() only — NO System() method exists!
  const messages = [
    vscode.LanguageModelChatMessage.User(userMessage),
  ];

  try {
    const response = await model.sendRequest(messages, {}, token);
    for await (const chunk of response.text) {
      stream.markdown(chunk);
    }
    return true;
  } catch (err) {
    // Quota exceeded, network error, cancellation → fall back to raw chunks
    return false;
  }
}
```

### Fallback Pattern

```javascript
// In the chat handler — ALWAYS have a fallback
let generated = false;
if (searchResult && searchResult.context_chunks?.length) {
  const model = await selectModel(vscode, request.model);
  if (model) {
    generated = await generateAnswer(vscode, model, stream, token, query, searchResult);
  }
}

if (generated) {
  // Append citations after the generated answer
  appendCitations(stream, searchResult);
} else {
  // Fallback: raw chunks (never leave user with nothing)
  stream.markdown(formatRawChunks(searchResult));
}
```

---

## 8. Slash Commands & Mode Routing {#8-slash-commands}

### Command Dispatch

```javascript
// In the chat handler
const command = request.command || 'search';

const MODE_TABLE = {
  search:  { maxChunks: 10, temperature: 0.1, prompt: SYSTEM_PROMPT },
  deep:    { maxChunks: 30, temperature: 0.1, prompt: SYSTEM_PROMPT },
  define:  { maxChunks: 15, temperature: 0.0, prompt: DEFINITION_PROMPT },
  summary: { maxChunks: 20, temperature: 0.2, prompt: SUMMARY_PROMPT },
  extract: { maxChunks: 15, temperature: 0.0, prompt: EXTRACTION_PROMPT },
  compare: { maxChunks: 30, temperature: 0.2, prompt: COMPARISON_PROMPT },
  audit:   { maxChunks: 30, temperature: 0.0, prompt: AUDIT_PROMPT },
};

const mode = MODE_TABLE[command] || MODE_TABLE.search;
```

### Example Mode Prompts

```javascript
const DEFINITION_PROMPT = [
  'You are a terminology assistant. Look up the requested defined term.',
  'Trace the complete definition chain: Term → definition → nested terms → their definitions.',
  'Quote exact language from the source documents.',
  'If a term has multiple definitions across documents, present each with its source.',
].join('\n');

const SUMMARY_PROMPT = [
  'Produce a structured summary with these sections:',
  '1. **Parties** — all named parties and their roles',
  '2. **Key Dates** — closing, effective, termination, reporting dates',
  '3. **Key Amounts** — notional, thresholds, fees',
  '4. **Key Obligations** — what each party must do',
  '5. **Risk Factors** — identified risks, carve-outs, conditions',
].join('\n');
```

---

## 9. VS Code Native Features {#9-vscode-native-features}

### 9.1 Reference Variables (#file, #selection, #editor)

```javascript
async function extractReferences(request) {
  const parts = [];
  let sourceDocHint = null;

  if (!request?.references?.length) {
    return { referenceText: '', sourceDocHint: null };
  }

  for (const ref of request.references) {
    if (ref.id === 'vscode.selection' || ref.id === 'copilot.selection') {
      const text = ref.value?.selectedText || ref.value?.text || '';
      if (text) parts.push(`[Selected Text]\n${text}`);
    }
    else if (ref.id === 'vscode.file' || ref.id === 'copilot.file') {
      const uri = ref.value?.uri || ref.value;
      if (uri) {
        sourceDocHint = path.basename(uri.fsPath || uri.path || '');
        parts.push(`[Referenced File: ${sourceDocHint}]`);
      }
    }
    else if (ref.id === 'vscode.editor') {
      const text = ref.value?.text || ref.value?.content || '';
      if (text) parts.push(`[Active Editor]\n${text.slice(0, 2000)}`);
    }
  }

  return {
    referenceText: parts.join('\n\n'),
    sourceDocHint,
  };
}

// In handler:
const { referenceText, sourceDocHint } = await extractReferences(request);
let query = request.prompt;
if (referenceText) query = `${referenceText}\n\n${query}`;
```

### 9.2 Follow-Up Suggestions

```javascript
// Deterministic follow-up generation (zero LLM cost)
function generateFollowUps(query, answer, searchResult) {
  const followUps = [];

  // Detect defined terms in the answer
  const termPattern = /\*\*([A-Z][A-Za-z\s]+)\*\*\s+means/g;
  let match;
  while ((match = termPattern.exec(answer)) !== null) {
    followUps.push({ prompt: `Define "${match[1]}"`, command: 'define' });
  }

  // Detect section cross-references
  const sectionPattern = /Section\s+(\d+\.\d+)/g;
  while ((match = sectionPattern.exec(answer)) !== null) {
    followUps.push({ prompt: `What does Section ${match[1]} say?`, command: 'search' });
  }

  // Detect date references
  const datePattern = /(\w+\s+\d{1,2},?\s+\d{4})/g;
  while ((match = datePattern.exec(answer)) !== null) {
    followUps.push({ prompt: `What obligations are triggered by ${match[1]}?`, command: 'search' });
  }

  return followUps.slice(0, 3); // Max 3 suggestions
}

// Wire into response:
const participant = vscode.chat.createChatParticipant('your-agent.assistant', handler);
participant.followupProvider = {
  provideFollowups(result, context, token) {
    return (result.metadata?.followUps || []).map(f => ({
      prompt: f.prompt,
      command: f.command,
      label: f.prompt,
    }));
  },
};
```

### 9.3 Progress Streaming

```javascript
// Show retrieval progress in chat UI
stream.progress('Searching knowledge base...');
const result = await backendTool(query, options);
stream.progress('Generating answer...');
const generated = await generateAnswer(vscode, model, stream, token, query, result);
```

### 9.4 Native Citations

```javascript
// Use ChatResponseReferencePart for clickable file citations
function appendCitations(stream, searchResult) {
  const citations = searchResult.citations || [];
  for (const cit of citations) {
    if (cit.uri || cit.source_path) {
      const uri = vscode.Uri.file(cit.source_path || cit.uri);
      stream.reference(uri);
    }
  }
}
```

### 9.5 Confirmation Dialogs

```javascript
// For destructive operations (re-ingest, delete index, etc.)
const choice = await vscode.window.showWarningMessage(
  'This will re-ingest all documents. Continue?',
  { modal: true },
  'Yes', 'No'
);
if (choice !== 'Yes') return;
```

---

## 10. Conversation Memory & Session Intelligence {#10-conversation-memory}

### Design Principle

"VS Code IS the session store." Read `context.history` — don't replicate it. Backend stays stateless.

### History Extraction

```javascript
function buildConversationContext(context) {
  const turns = [];
  const maxTurns = 10;

  if (!context?.history?.length) return [];

  const history = context.history.slice(-maxTurns);
  for (const turn of history) {
    if (turn instanceof vscode.ChatRequestTurn) {
      turns.push({ role: 'user', content: turn.prompt });
    } else if (turn instanceof vscode.ChatResponseTurn) {
      // Reconstruct response text from parts
      let text = '';
      for (const part of turn.response) {
        if (part instanceof vscode.ChatResponseMarkdownPart) {
          text += part.value.value;
        }
      }
      if (text) turns.push({ role: 'assistant', content: text });
    }
  }

  return turns;
}

// Pass to backend for coreference resolution:
const history = buildConversationContext(context);
const args = ['search', query];
if (history.length) {
  args.push('--conversation-history', JSON.stringify(history));
}
```

### Backend Query Rewriting (Signal-Gated)

```python
# backend/retrieval/query_rewriter.py
COREFERENCE_SIGNALS = ['it', 'this', 'that', 'these', 'those', 'same', 'above', 'previous']

def needs_rewriting(query: str) -> bool:
    """Only invoke LLM if coreference signals are detected."""
    tokens = query.lower().split()
    return any(signal in tokens for signal in COREFERENCE_SIGNALS)

def rewrite_query(query: str, conversation_history: list[dict]) -> str:
    if not needs_rewriting(query):
        return query  # Skip LLM call — save cost

    # Call LLM to resolve coreferences
    prompt = f"""Given this conversation:
{format_history(conversation_history[-6:])}

Rewrite the following query to be self-contained:
Query: {query}

Rewritten:"""
    return call_llm(prompt, max_tokens=150)
```

### Session Memory (Optional, In-Process)

```python
# backend/retrieval/session_memory.py
from dataclasses import dataclass, field
from datetime import datetime, timedelta

@dataclass
class SessionState:
    session_id: str
    resolved_terms: dict = field(default_factory=dict)
    active_documents: set = field(default_factory=set)
    active_sections: set = field(default_factory=set)
    last_access: datetime = field(default_factory=datetime.now)
    ttl_hours: int = 4

    @property
    def is_expired(self):
        return datetime.now() - self.last_access > timedelta(hours=self.ttl_hours)

# In-process store (dict keyed by session_id)
_sessions: dict[str, SessionState] = {}

def get_session(session_id: str) -> SessionState:
    s = _sessions.get(session_id)
    if s and not s.is_expired:
        s.last_access = datetime.now()
        return s
    s = SessionState(session_id=session_id)
    _sessions[session_id] = s
    return s
```

---

## 11. Golden Answer Test Harness {#11-golden-test-harness}

This is the most important testing innovation. It tests **answer quality**, not just retrieval correctness.

### Architecture

```
golden_answer_tests.json     → Test definitions (questions, rubrics, expected answers)
golden_answer_runner.js      → Runs each test through full pipeline (backend + LLM)
golden_answer_scorer.js      → LLM-as-judge scores each answer on 5 dimensions
golden_answer_baseline.json  → Pinned scores for regression detection
golden_answer_results/       → Timestamped results + scores
```

### Test Definition Schema

```json
[
  {
    "test_id": "G01",
    "category": "defined_terms",
    "category_name": "Defined Terms",
    "question": "What does Distribution Date mean?",
    "command": "search",
    "prior_context": null,
    "expected_answer_contains": ["25th", "Business Day"],
    "expected_answer_not_contains": ["I don't know", "not found"],
    "expected_sections": ["Section 1.01"],
    "ideal_answer_summary": "Distribution Date means the 25th day of each month...",
    "scoring_rubric": {
      "completeness": "Must include date, Business Day fallback, commencement month.",
      "accuracy": "All facts match source. No invented dates.",
      "grounding": "Cites Section 1.01 or equivalent inline.",
      "usability": "Immediately useful to domain professional.",
      "no_hallucination": "No external knowledge."
    },
    "difficulty": "easy",
    "depends_on": null
  }
]
```

### Categories (Customize for Your Domain)

| Category | Tests | What It Measures |
|----------|-------|------------------|
| `defined_terms` | 5-8 | Can the agent look up and trace term definitions? |
| `key_dates` | 4-6 | Can the agent find specific dates and temporal conditions? |
| `parties` | 4-6 | Can the agent identify named parties and their roles? |
| `waterfall` | 4-6 | Can the agent explain complex procedural flows? |
| `reporting` | 3-5 | Can the agent answer reporting and compliance questions? |
| `follow_ups` | 3-5 | Can the agent handle multi-turn conversations? |

**Total**: 25-35 golden tests is a good starting size.

### Scoring Dimensions

| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| `completeness` | 0.25 | Does the answer cover all required elements? |
| `accuracy` | 0.30 | Are all stated facts correct per source documents? |
| `grounding` | 0.20 | Are claims grounded in cited sources? |
| `usability` | 0.15 | Is the answer immediately useful to a professional? |
| `no_hallucination` | 0.10 | Is the answer free from fabricated information? |

### Runner (golden_answer_runner.js)

```javascript
async function runSingleTest(vscode, test, { outputChannel, shared }) {
  const start = Date.now();
  const backendTool = require('../extension/copilot/tool');
  const { selectModel, computeTokenBudget, computeMaxChunks, RAG_CONFIG }
    = require('../extension/chat/participant');

  // Build query (prepend prior_context for follow-ups)
  let query = test.question;
  if (test.prior_context) {
    query = `Context: ${test.prior_context}\n\nFollow-up: ${test.question}`;
  }

  // Call backend
  const isDeep = test.command === 'deep';
  const maxResults = isDeep ? RAG_CONFIG.maxContextChunks : Math.floor(RAG_CONFIG.maxContextChunks / 2);

  let result;
  try {
    result = await backendTool(query, {
      workspaceRoot: shared?.workspaceRoot,
      maxResults,
      deepMode: isDeep,
    });
  } catch (err) {
    return {
      test_id: test.test_id,
      actual_answer: `[ERROR] ${err.message}`,
      chunks_used: 0, chunk_sources: [],
    };
  }

  // Extract chunks + citations
  let search = result?.search_result;
  if (search?.search_result) search = search.search_result;
  const chunks = search?.context_chunks || search?.results || [];
  const citations = search?.citations || [];

  // Build citation lookup
  const citationMap = {};
  for (const cit of citations) {
    const key = cit.doc_id || cit.doc_name;
    if (key && !citationMap[key]) citationMap[key] = cit;
  }

  // Generate answer via LLM (same as production participant)
  let answerText = '';
  try {
    const model = await selectModel(vscode, null);
    if (model) {
      const tokenBudget = computeTokenBudget(model);
      const maxChunks = computeMaxChunks(tokenBudget);

      const contextBlocks = chunks.slice(0, maxChunks).map((c, i) => {
        const body = (c.content || '').trim();
        let docName = c.doc_name || '';
        if (!docName && c.source_path) {
          docName = c.source_path.replace(/\\/g, '/').split('/').pop() || '';
        }
        if (!docName) docName = c.doc_id || `source-${i + 1}`;

        const cit = citationMap[c.doc_id] || {};
        const section = c.section || cit.section || null;
        const page = c.page ?? cit.page ?? null;

        let label = `[Document: ${docName}`;
        if (section) label += `, Section: ${section}`;
        if (page != null) label += `, Page: ${page}`;
        label += ']';
        return `${label}\n${body}`;
      });

      const userMessage = [
        SYSTEM_PROMPT,       // Same prompt as production!
        '',
        '## Retrieved Context',
        contextBlocks.join('\n\n'),
        '',
        '## Question',
        query,
      ].join('\n');

      const messages = [vscode.LanguageModelChatMessage.User(userMessage)];
      const resp = await model.sendRequest(messages, {}, new vscode.CancellationTokenSource().token);
      for await (const part of resp.text) answerText += part;
    }
  } catch (genErr) {
    answerText = `[GENERATION ERROR] ${genErr.message}`;
  }

  return {
    test_id: test.test_id,
    category: test.category,
    question: test.question,
    actual_answer: answerText,
    chunks_used: chunks.length,
    chunk_sources: chunks.slice(0, 20).map(c => {
      const cit = citationMap[c.doc_id] || {};
      return {
        doc: c.doc_name || c.source_path?.split('/').pop() || c.doc_id || '',
        section: c.section || cit.section || '',
        doc_type: c.doc_type || '',
      };
    }),
    elapsed_ms: Date.now() - start,
    metadata: { model: 'copilot', deep_mode: isDeep },
  };
}
```

### Scorer (golden_answer_scorer.js)

```javascript
const WEIGHTS = {
  completeness: 0.25,
  accuracy: 0.30,
  grounding: 0.20,
  usability: 0.15,
  no_hallucination: 0.10,
};

function buildJudgePrompt(test, actualAnswer) {
  return `You are an expert judge evaluating a RAG system's answer.

## Question
${test.question}

## Expected Answer Content
${test.ideal_answer_summary}

## Must Contain
${JSON.stringify(test.expected_answer_contains)}

## Must NOT Contain
${JSON.stringify(test.expected_answer_not_contains)}

## System's Answer
${actualAnswer}

## Scoring Rubric
${Object.entries(test.scoring_rubric).map(([k, v]) => `- ${k}: ${v}`).join('\n')}

Score on each dimension from 1 to 5. Return ONLY a JSON object:
{
  "completeness": { "score": <1-5>, "reason": "<one sentence>" },
  "accuracy": { "score": <1-5>, "reason": "<one sentence>" },
  "grounding": { "score": <1-5>, "reason": "<one sentence>" },
  "usability": { "score": <1-5>, "reason": "<one sentence>" },
  "no_hallucination": { "score": <1-5>, "reason": "<one sentence>" },
  "critical_failures": ["<issues, or empty>"]
}`;
}

function computeOverall(scores) {
  let total = 0;
  for (const [dim, weight] of Object.entries(WEIGHTS)) {
    total += (scores[dim]?.score || 1) * weight;
  }
  return Math.round(total * 100) / 100;
}
```

### Regression Detection

```javascript
function detectRegressions(currentScores, baselineScores, threshold = 0.5) {
  const regressions = [];
  for (const current of currentScores) {
    const baseline = baselineScores.get(current.test_id);
    if (baseline && current.overall < baseline.overall - threshold) {
      regressions.push({
        test_id: current.test_id,
        baseline: baseline.overall,
        current: current.overall,
        delta: current.overall - baseline.overall,
      });
    }
  }
  return regressions;
}
```

### Running Golden Tests

From the Command Palette in the Extension Development Host:
```
Ctrl+Shift+P → "Agent: Run Golden Answer Tests"
```

This runs all tests → scores them → detects regressions → prompts to save baseline.

---

## 12. Unit & Integration Testing {#12-testing}

### Mock VS Code for Node.js Tests

The `vscode.lm` API only works inside a running VS Code extension host. For CI and fast iteration, mock the vscode object:

```javascript
// tests/test_helpers.js
function createMockVscode({ modelAvailable = true, modelError = false } = {}) {
  const capturedMessages = [];
  const streamedOutput = [];

  const mockModel = {
    id: 'gpt-4o-test',
    family: 'gpt-4o',
    maxInputTokens: 128000,
    sendRequest: async (messages, opts, token) => {
      capturedMessages.push(...messages);
      if (modelError) throw new Error('Model quota exceeded');
      return {
        text: (async function* () {
          yield 'Generated answer chunk 1. ';
          yield 'Generated answer chunk 2.';
        })(),
      };
    },
  };

  return {
    vscode: {
      lm: {
        selectChatModels: async ({ vendor, family } = {}) => {
          if (!modelAvailable) return [];
          return [mockModel];
        },
      },
      chat: {
        createChatParticipant: (id, handler) => ({
          id, handler, dispose: () => {},
          followupProvider: null,
        }),
      },
      LanguageModelChatMessage: {
        User: (text) => ({ role: 'user', content: text }),
        Assistant: (text) => ({ role: 'assistant', content: text }),
      },
      CancellationTokenSource: class { constructor() { this.token = { isCancellationRequested: false }; } },
      workspace: {
        getConfiguration: () => ({
          get: (key) => {
            const defaults = { model: 'auto', sourceFolder: '', logLevel: 'normal' };
            return defaults[key];
          },
        }),
      },
    },
    mockModel,
    capturedMessages,
    streamedOutput,
    stream: {
      markdown: (text) => streamedOutput.push(text),
      progress: () => {},
      reference: () => {},
    },
    token: { isCancellationRequested: false },
  };
}
```

### What to Test

| Category | Assertions | Example |
|----------|------------|---------|
| System prompt persona | 5-8 | Contains agent name, grounding rules, citation instructions |
| Context block format | 5-8 | Chunks labeled `[Document: X, Section: Y]`, content trimmed |
| Streaming generation | 5-8 | Tokens arrive sequentially, citations appended after |
| Fallback: no model | 3-5 | Returns raw chunks, logs reason, no crash |
| Fallback: LLM error | 3-5 | `sendRequest()` throws → raw chunks, no crash |
| `request.model` honored | 3-5 | User-selected model used; `selectChatModels` NOT called |
| Follow-up generation | 3-5 | Defined terms, sections, dates detected → follow-up chips |

### Python Backend Tests

```python
# tests/conftest.py
import pytest
from backend.common.models import TextChunk, Citation, SearchResult

@pytest.fixture
def sample_chunks():
    return [
        TextChunk(chunk_id='c1', doc_id='d1', content='Sample text...', section='1.01'),
        TextChunk(chunk_id='c2', doc_id='d1', content='More text...', section='2.03'),
    ]

@pytest.fixture
def sample_search_result(sample_chunks):
    return SearchResult(
        context_chunks=sample_chunks,
        citations=[Citation(doc_id='d1', doc_name='Test Doc', section='1.01')],
        confidence=0.85,
        confidence_tier='HIGH',
    )
```

---

## 13. Dev Environment & F5 Workflow {#13-dev-environment}

### launch.json

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Extension Dev Host",
      "type": "extensionHost",
      "request": "launch",
      "args": [
        "--extensionDevelopmentPath=${workspaceFolder}/extension"
      ],
      "outFiles": [],
      "preLaunchTask": null
    }
  ]
}
```

### Dev Workflow

1. Set `your-agent.backendMode` to `"venv"` in VS Code settings
2. Press `F5` → Extension Development Host opens
3. Type `@agent your question` in Copilot Chat
4. Edit `participant.js` → save → `Ctrl+R` in Dev Host to reload
5. **Edit-test cycle: < 5 seconds** (no VSIX rebuild needed)

### Backend Dev Mode

When `backendMode = "venv"`:
- Extension uses `python -m cli.main` directly (your workspace Python)
- Live code changes take effect immediately
- No PyInstaller recompilation needed
- Set `pythonPath` to your venv's python if needed

When `backendMode = "exe"`:
- Extension uses the compiled PyInstaller exe from `extension/bin/`
- Used for VSIX distribution and production

---

## 14. VSIX Build & Packaging {#14-vsix-packaging}

### Build Pipeline (PowerShell)

```powershell
# scripts/build_vsix.ps1
param(
    [string]$Version = "0.1.0",
    [switch]$SkipModels,
    [switch]$SkipBackend,
    [switch]$Clean
)

# Step 1: Download ML models (embeddings, cross-encoder)
# Step 2: Build backend with PyInstaller
# Step 3: Copy backend exe to extension/bin/win-x64/
# Step 4: Update package.json version
# Step 5: Package VSIX with vsce
# Step 6: Move to dist/

# Example usage:
# .\scripts\build_vsix.ps1 -Version "0.1.0" -Clean
# .\scripts\build_vsix.ps1 -SkipModels -SkipBackend  # Quick extension-only rebuild
```

### PyInstaller Spec

```python
# packaging/your_backend.spec
a = Analysis(
    ['../cli/main.py'],
    pathex=['..'],
    datas=[
        ('../config', 'config'),
        ('../models', 'models'),  # ML model weights
    ],
    hiddenimports=[
        'backend.retrieval.search',
        'backend.ingestion.pipeline',
        'chromadb', 'sentence_transformers',
    ],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], name='your-backend', console=True)
coll = COLLECT(exe, a.binaries, a.datas, name='your-backend')
```

### .vscodeignore

```
# Exclude from VSIX
.vscode/**
tests/**
docs/**
scripts/**
packaging/**
backend/**
cli/**
config/**
*.py
*.spec
.gitignore
.git/**
__pycache__/**
*.pyc
node_modules/**
```

### Verify VSIX Contents

```powershell
# After building — always verify!
npx @vscode/vsce ls 2>&1 | Select-String "participant|tool|backend"

# Check key symbols exist
$zip = [System.IO.Compression.ZipFile]::OpenRead("dist/your-extension-0.1.0.vsix")
$entry = $zip.Entries | Where-Object { $_.FullName -like "*participant.js" }
$sr = New-Object System.IO.StreamReader($entry.Open())
$content = $sr.ReadToEnd()
$sr.Close(); $zip.Dispose()
$content | Select-String "SYSTEM_PROMPT|selectModel|generateAnswer|buildContextBlock"
```

---

## 15. Settings & Configuration {#15-settings}

### Design Rule: 3 User Settings + Hidden RAG Config

| Setting | Type | Purpose |
|---------|------|---------|
| `sourceFolder` | string | Where documents live |
| `logLevel` | enum: normal/verbose | Output panel detail |
| `model` | enum: auto/gpt-4.1/gpt-4o/... | LLM for generation |

Everything else — chunk sizes, reranking weights, temperature, retrieval modes — goes in the hardcoded `RAG_CONFIG` object. Users should never see RAG tuning knobs.

### Developer-Only Settings (hidden via high `order`)

```json
"your-agent.backendMode": { "order": 100, "markdownDescription": "**[Developer]** ..." },
"your-agent.pythonPath": { "order": 101, "markdownDescription": "**[Developer]** ..." }
```

These appear at the bottom of the settings UI and are clearly labeled `[Developer]`.

---

## 16. Scoped Knowledge Spaces {#16-scoped-knowledge}

### Design: Folder = Namespace = Slash Command

```
documents/
├── project_alpha/        → @agent /project_alpha [question]
│   ├── .kts/             → ChromaDB collection: agent_project_alpha
│   │   ├── chroma/
│   │   ├── graph/
│   │   └── term_registry/
│   ├── spec.pdf
│   └── design.docx
├── project_beta/         → @agent /project_beta [question]
│   ├── .kts/
│   ├── manual.pdf
│   └── faq.md
```

### Auto-Discovery

```javascript
// lib/scope_discovery.js
function discoverScopes(rootPath) {
  const scopes = [];
  const entries = fs.readdirSync(rootPath, { withFileTypes: true });

  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const ktsDir = path.join(rootPath, entry.name, '.kts');
    if (fs.existsSync(ktsDir)) {
      const slug = entry.name.toLowerCase().replace(/\s+/g, '_');
      scopes.push({ name: entry.name, slug, path: path.join(rootPath, entry.name) });
    }
  }
  return scopes;
}
```

### Two-Level Scope Narrowing

```
@agent /project_alpha /api What is the rate limit?
       ─────────────  ────
       scope           doc_type filter
```

First token = folder scope (ChromaDB collection filter). Second token = document type filter (ChromaDB `where` clause). Zero duplication — same index, different views.

---

## 17. Confidence Scoring & Gap Detection {#17-confidence-scoring}

### Confidence Tiers

```python
class ConfidenceTier:
    HIGH = 'HIGH'           # ≥2 direct matches AND top_score > 0.85
    MEDIUM = 'MEDIUM'       # top_score > 0.65
    LOW = 'LOW'             # top_score > 0.45
    SPECULATIVE = 'SPECULATIVE'  # ≤ 0.45

def compute_confidence(chunks: list[TextChunk]) -> tuple[float, str]:
    if not chunks:
        return 0.0, ConfidenceTier.SPECULATIVE

    scores = [c.score for c in chunks if hasattr(c, 'score') and c.score]
    top_score = max(scores) if scores else 0.0
    high_matches = sum(1 for s in scores if s > 0.85)

    if high_matches >= 2 and top_score > 0.85:
        return top_score, ConfidenceTier.HIGH
    elif top_score > 0.65:
        return top_score, ConfidenceTier.MEDIUM
    elif top_score > 0.45:
        return top_score, ConfidenceTier.LOW
    else:
        return top_score, ConfidenceTier.SPECULATIVE
```

### Gap Detection

```python
def detect_gaps(query: str, chunks: list[TextChunk]) -> list[str]:
    """Compare entities in query vs entities found in chunks."""
    requested = extract_entities(query)     # NER on query
    found = set()
    for chunk in chunks:
        found.update(extract_entities(chunk.content))

    gaps = requested - found
    return [f'"{entity}" not found in retrieved documents' for entity in gaps]
```

### Display in Chat

```javascript
// After answer generation
if (searchResult.confidence_tier) {
  const badge = {
    HIGH: '🟢 High Confidence',
    MEDIUM: '🟡 Medium Confidence',
    LOW: '🟠 Low Confidence',
    SPECULATIVE: '🔴 Speculative',
  }[searchResult.confidence_tier] || '';

  stream.markdown(`\n\n*${badge}*`);
}

if (searchResult.gaps?.length) {
  stream.markdown('\n\n> ⚠️ **Not found in documents**: ' + searchResult.gaps.join(', '));
}
```

---

## 18. Critical Gotchas {#18-gotchas}

These are real bugs we hit. Avoid them.

### Gotcha 1: `LanguageModelChatMessage.System is not a function`

The VS Code LM API only has `.User()` and `.Assistant()`. There is **NO** `.System()` method.

```javascript
// ❌ CRASHES — System() does not exist
vscode.LanguageModelChatMessage.System(SYSTEM_PROMPT)

// ✅ Embed system prompt in User message
vscode.LanguageModelChatMessage.User(SYSTEM_PROMPT + '\n---\n' + context + '\n' + query)
```

### Gotcha 2: `request.model` Ignored → Always Gets gpt-4o

If you hardcode a model selection priority list, it will always pick the first available model regardless of what the user selected in the chat model picker.

```javascript
// ❌ Always picks gpt-4o
async function selectModel() {
  const models = await vscode.lm.selectChatModels({ family: 'gpt-4o' });
  return models[0]; // ignores user's Claude/GPT-4o-mini selection
}

// ✅ Check request.model first
async function selectModel(vscode, requestModel) {
  if (requestModel?.sendRequest) return requestModel;
  // ... fallback auto-detection
}
```

### Gotcha 3: Wrong Field Names = 100% Empty Metadata

Backend returns `content`, `source_path`, `doc_id`. If your JS uses `text`, `source`, `file` — you get empty strings silently.

```javascript
// ❌ Wrong field names (silent failure)
const text = chunk.text;      // undefined — field is "content"
const src = chunk.source;     // undefined — field is "source_path"

// ✅ Correct field names matching Python dataclass
const text = chunk.content;
const src = chunk.source_path;
```

### Gotcha 4: No Backend Rebuild for Extension-Only Changes

If you only changed JavaScript files, you do NOT need to rebuild the PyInstaller exe. Only the VSIX needs repackaging. Don't waste 10 minutes on a backend rebuild.

### Gotcha 5: `selectChatModels()` Returns Empty Outside Extension Host

The `vscode.lm` API only works inside a running VS Code extension host. In Node.js tests, it returns nothing. Always mock the vscode object for tests.

### Gotcha 6: Duplicate Config Declarations

If you declare a setting twice in your config (e.g., two `enable_feature = True/False` lines), the second silently overrides the first. Grep for duplicates.

### Gotcha 7: Streaming Requires `for await...of`

The LLM response is an async generator. You MUST iterate it with `for await`:

```javascript
// ❌ Gets nothing — response.text is an async generator
const answer = response.text;

// ✅ Iterate the stream
let answer = '';
for await (const chunk of response.text) {
  answer += chunk;
  stream.markdown(chunk);
}
```

---

## 19. Checklist {#19-checklist}

Use this for every new project:

### Setup
- [ ] `package.json` with `chatParticipants`, `commands`, `configuration` sections
- [ ] `engines.vscode: "^1.95.0"` minimum
- [ ] `activationEvents: ["onStartupFinished"]`
- [ ] `.vscode/launch.json` for F5 Extension Dev Host
- [ ] `.vscodeignore` to exclude dev files from VSIX

### Chat Participant
- [ ] `vscode.chat.createChatParticipant()` in extension.js
- [ ] Chat handler receives `(request, context, stream, token)`
- [ ] Slash command dispatch via `request.command`
- [ ] `#file`/`#selection`/`#editor` reference extraction from `request.references`
- [ ] `followupProvider` for follow-up suggestion chips

### Backend Bridge
- [ ] CLI: `python -m cli.main <command> [args] → JSON stdout`
- [ ] `runCliJson()` spawns subprocess, parses JSON response
- [ ] `BackendRunnerFactory`: ExeRunner (prod) vs VenvRunner (dev)
- [ ] Data models match exactly: Python `TextChunk` ↔ JS field names

### LLM Generation
- [ ] `selectModel()`: request.model → setting → auto-detect
- [ ] System prompt: domain-specific, grounding rules, NO generic prompt
- [ ] Message: `LanguageModelChatMessage.User()` only — NO `.System()`
- [ ] Context block: `[Document: name, Section: X]\ncontent` labels
- [ ] Token budget: `model.maxInputTokens * 0.8`
- [ ] Streaming: `for await (chunk of response.text) { stream.markdown(chunk) }`
- [ ] Fallback: if LLM unavailable → raw chunks (no regression)

### Testing
- [ ] Golden answer test definitions: 25-35 questions across 5-6 categories
- [ ] Golden runner: full pipeline (backend + LLM) for each test
- [ ] Golden scorer: LLM-as-judge on 5 dimensions with weighted composite
- [ ] Baseline pinning + regression detection (threshold: 0.5)
- [ ] Mock vscode for Node.js unit tests
- [ ] Python backend pytest suite
- [ ] `your-agent.runGoldenTests` command registered

### Packaging
- [ ] `scripts/build_vsix.ps1` — full pipeline: models → backend → VSIX
- [ ] PyInstaller spec for backend compilation
- [ ] Version bump in package.json before each build
- [ ] VSIX verification: extract and grep for key symbols
- [ ] Backend exe at `extension/bin/win-x64/your-backend/your-backend.exe`

### Configuration
- [ ] 3 user settings: sourceFolder, logLevel, model
- [ ] `RAG_CONFIG` hardcoded constant (not user-facing)
- [ ] Developer settings at `order: 100+` with `[Developer]` prefix

---

## 20. VS Code API Quick Reference {#20-api-reference}

```javascript
// ─── Chat Participant ─────────────────────────────────
const participant = vscode.chat.createChatParticipant('id', handler);
participant.isSticky = true;
participant.followupProvider = { provideFollowups(result, ctx, token) { ... } };

// Handler signature:
async function handler(request, context, stream, token) {
  request.prompt;       // User's message text
  request.command;      // Slash command name (e.g., 'search', 'define')
  request.model;        // User's selected LLM model
  request.references;   // #file, #selection, #editor references
  context.history;      // Array of ChatRequestTurn / ChatResponseTurn

  stream.markdown(text);              // Render markdown
  stream.progress(msg);               // Show progress indicator
  stream.reference(uri);              // Clickable file citation
  stream.anchor(location, label);     // Jump-to-location link

  return { metadata: { followUps: [...] } };
}

// ─── Language Model API ───────────────────────────────
const models = await vscode.lm.selectChatModels({ vendor: 'copilot', family: 'gpt-4.1' });
const model = models[0];  // or request.model

model.id;               // 'gpt-4.1'
model.family;           // 'gpt-4.1'
model.maxInputTokens;   // 1000000

const message = vscode.LanguageModelChatMessage.User('prompt text');
// ⚠️ NO .System() method. Only .User() and .Assistant().

const response = await model.sendRequest([message], {}, cancellationToken);
for await (const chunk of response.text) {
  stream.markdown(chunk);
}

// ─── Configuration ────────────────────────────────────
const config = vscode.workspace.getConfiguration('your-agent');
const value = config.get('sourceFolder');

// ─── Commands ─────────────────────────────────────────
vscode.commands.registerCommand('your-agent.ingest', async () => { ... });

// ─── UI ───────────────────────────────────────────────
const channel = vscode.window.createOutputChannel('Your Agent', { log: true });
channel.appendLine('[Agent] Message');
channel.show(true);

await vscode.window.showInformationMessage('Done!', 'OK');
await vscode.window.showWarningMessage('Destructive action?', { modal: true }, 'Yes', 'No');

const uri = await vscode.window.showOpenDialog({ canSelectFolders: true });
```

### Minimum Requirements

| Requirement | Version |
|-------------|---------|
| VS Code | `^1.95.0` |
| Node.js | `^18.0.0` |
| Python | `^3.10` |
| GitHub Copilot subscription | Required (provides `vscode.lm` API) |

---

## Appendix: Lessons Learned (16 Phases)

1. **Start with the golden test harness** — not at the end. It is the single most valuable investment.
2. **3 settings, not 25** — every setting you expose is a support ticket waiting to happen.
3. **`request.model` first** — always honor the user's chat model picker before auto-detecting.
4. **Embed system prompt in User message** — there is no `.System()` method in the VS Code LM API.
5. **Frontend generates, backend retrieves** — keep generation in JS, retrieval in Python. Clean separation.
6. **Feature-flag everything** — every RAG technique gets a boolean flag. Default to optimal. Never expose flags to users.
7. **Signal-gate LLM calls** — only invoke the LLM for query rewriting if coreference signals are detected. Saves cost.
8. **F5 dev workflow** — the edit-test cycle must be < 5 seconds. VSIX rebuilds are for releases only.
9. **Binary prompts beat open-ended** — "Does this answer cover X? yes/no" is more reliable than "Rate this 1-5."
10. **Folder = namespace** — each document folder gets its own isolated vector store and slash command. Zero config.
11. **Pre-compute at ingestion** — definition chains, entity graphs, critique questions. Query time should be instant lookup.
12. **Session memory is a dict with TTL** — you don't need Redis. An in-process dict with 4-hour TTL works for VS Code extensions.
13. **Cross-reference citation objects** — chunk metadata often doesn't have section/page. Cross-reference via `citationMap[chunk.doc_id]`.
14. **Verify VSIX contents** — extract and grep. Never trust the build blindly.
15. **Backend rebuild ≠ extension rebuild** — if only JS changed, skip the 10-minute PyInstaller build.
16. **Ablation before optimization** — measure each technique's individual contribution before adding more.

---

*Template version: 1.0.0*  
*Distilled from: GSF IR KTS Agentic System, Phases 1–16 + Redesign*  
*Last updated: February 20, 2026*
