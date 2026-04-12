# Phase B: Settings Simplification

**Created:** 2026-02-20  
**Status:** APPROVED — Ready for Implementation  
**Effort:** 30 minutes  
**Priority:** P1 (after Dev Environment and Conversational Output)

---

## 1. Problem Statement

The extension currently exposes **25+ user-facing settings** in `extension/package.json`.
A structured-finance analyst should not need to know what "MMR lambda", "token budget",
"Self-RAG max rounds", or "cross-encoder rerank" means to ask a question about their PSA.

### Current Settings Inventory

**File:** `extension/package.json` → `contributes.configuration.properties`

| Setting | Type | Default | Should Exist? |
|---------|------|---------|---------------|
| `kts.sourcePath` | string | "" | **YES** — user must specify source docs |
| `kts.kbWorkspacePath` | string | "" | No — use extension global storage |
| `kts.pythonPath` | string | "" | No — auto-detect |
| `kts.backendChannel` | enum | "bundled" | No — internal dev toggle |
| `kts.backendMode` | enum | "auto" | No — internal dev toggle |
| `kts.logLevel` | enum | "INFO" | **YES** — useful for troubleshooting |
| `kts.graphRagEnabled` | boolean | true | No — always on |
| `kts.graphRagMaxIterations` | integer | 10 | No — hardcode |
| `kts.graphRagVerboseLogging` | boolean | false | No — subsume into logLevel |
| `kts.ingestionTimeoutMinutes` | integer | 60 | No — compute from file size |
| `kts.generationModel` | enum | "auto" | **YES** — but simplify |
| `kts.reasoningModel` | enum | "gpt-4.1" | No — same model for everything |
| `kts.multiQueryEnabled` | boolean | true | No — always on |
| `kts.selfRagEnabled` | boolean | true | No — always on (if ablation proves value) |
| `kts.multiQueryModel` | enum | "auto" | No — same model for everything |
| `kts.selfRagModel` | enum | "auto" | No — same model for everything |
| `kts.critiqueModel` | enum | "auto" | No — same model for everything |
| `kts.critiqueLoopEnabled` | boolean | true | No — always on (if ablation proves value) |
| `kts.multiQueryVariants` | integer | 8 | No — hardcode |
| `kts.selfRagMaxRounds` | integer | 5 | No — hardcode |
| `kts.maxContextChunks` | integer | 100 | No — hardcode |
| `kts.tokenBudget` | integer | 800000 | No — compute from model context window |
| `kts.knowledgeSourceRoot` | string | "" | No — merge with sourcePath |

**Total: 23 settings. User needs: 3.**

---

## 2. Target: 3 User-Facing Settings

### 2.1 `kts.sourceFolder`

**Purpose:** Where are the documents?

```json
"kts.sourceFolder": {
  "type": "string",
  "default": "",
  "description": "Folder containing your documents (PSA, guides, manuals). Use KTS: Select Source Folder to browse."
}
```

This replaces `kts.sourcePath` and `kts.knowledgeSourceRoot`. One setting, one purpose.

### 2.2 `kts.logLevel`

**Purpose:** How much debug output do you want?

```json
"kts.logLevel": {
  "type": "string",
  "default": "normal",
  "enum": ["normal", "verbose"],
  "enumDescriptions": [
    "Show document counts, retrieval hits, and confidence scores.",
    "Show full pipeline trace: graph hops, chunk scores, embedding calls, token counts. Use when diagnosing retrieval quality."
  ],
  "description": "Output panel logging detail. 'verbose' shows every pipeline step."
}
```

This simplifies the 4-level enum (DEBUG/INFO/WARNING/ERROR) to 2 levels that a user
actually understands. Internally, "normal" maps to INFO, "verbose" maps to DEBUG.

### 2.3 `kts.model`

**Purpose:** Which LLM should we use?

```json
"kts.model": {
  "type": "string",
  "default": "auto",
  "enum": ["auto", "gpt-4.1", "gpt-4o", "gpt-4o-mini", "claude-sonnet-4"],
  "enumDescriptions": [
    "Use your active GitHub Copilot model (recommended)",
    "OpenAI GPT-4.1 — strongest reasoning, 1M context window",
    "OpenAI GPT-4o — balanced quality and speed",
    "OpenAI GPT-4o Mini — fast and lightweight",
    "Anthropic Claude Sonnet 4 — strong analysis"
  ],
  "description": "Language model for answer generation and reasoning. 'auto' uses whatever model you have active in GitHub Copilot."
}
```

This replaces all 5 model dropdowns (generationModel, reasoningModel, multiQueryModel,
selfRagModel, critiqueModel). One model for everything. The user picks it once (or uses
the chat model picker), and all components use the same model.

---

## 3. Internal-Only Settings (Hidden from Users)

These settings remain in the codebase as **hardcoded constants** inside the JavaScript
files. They are not exposed in `package.json` and cannot be changed by users.

### 3.1 Hardcoded in `extension/chat/participant.js`

```javascript
// ── Internal RAG Configuration ─────────────────────────────────────
// These are tuned for GPT-4.1's 1M context window.
// Do not expose to users as settings.
const RAG_CONFIG = {
  // Retrieval
  maxContextChunks: 100,          // Was: kts.maxContextChunks
  tokenBudget: 800000,            // Was: kts.tokenBudget (80% of GPT-4.1's 1M)
  multiQueryVariants: 4,          // Was: kts.multiQueryVariants (reduced from 8 pending ablation)
  
  // Self-RAG (enabled by default, disabled if ablation shows no value)
  selfRagEnabled: true,           // Was: kts.selfRagEnabled
  selfRagMaxRounds: 3,            // Was: kts.selfRagMaxRounds (reduced from 5)
  
  // Critique (enabled by default, disabled if ablation shows no value)
  critiqueEnabled: true,          // Was: kts.critiqueLoopEnabled
  critiqueMaxRounds: 3,           // Was: settings.py critique_max_rounds
  
  // Graph RAG
  graphRagMaxIterations: 10,      // Was: kts.graphRagMaxIterations
  
  // Token estimation
  TOKEN_RATIO: 4,                 // ~4 chars per token
  RESERVED_TOKENS: 5000,          // System prompt + overhead
};
```

### 3.2 Hardcoded in `config/settings.py` (Backend)

The backend `KTSConfig` dataclass keeps all its current fields but they are
**internal implementation details**, never surfaced to users. The only field
that comes from user settings is the log level.

### 3.3 Dev-Only Settings (Not in package.json, but available)

For development, these settings remain accessible via VS Code's settings.json
but are not shown in the Settings UI:

```json
// .vscode/settings.json (dev workspace only)
{
  "kts.backendMode": "venv",        // Dev: use live Python source
  "kts.backendChannel": "workspace", // Dev: use workspace code
  "kts.pythonPath": "",              // Dev: override Python path
  "kts.kbWorkspacePath": ""          // Dev: override workspace path
}
```

These are accessible to developers who know about them but invisible to end users.
They stay in package.json with `"markdownDescription"` prefixed by `[Developer]`
and all grouped under an `"Advanced (Developer)"` section using `"order"` properties.

---

## 4. Implementation: Exact Changes to `extension/package.json`

### 4.1 New Configuration Block (Replace Entire `properties` Object)

The `contributes.configuration.properties` object in `extension/package.json`
(currently lines 30-280) will be replaced with:

```json
"properties": {
  "kts.sourceFolder": {
    "type": "string",
    "default": "",
    "order": 1,
    "description": "Folder containing your documents (PSA, guides, manuals). Use 'KTS: Select Source Folder' to browse."
  },
  "kts.logLevel": {
    "type": "string",
    "default": "normal",
    "enum": ["normal", "verbose"],
    "enumDescriptions": [
      "Show document counts, retrieval hits, and confidence scores.",
      "Full pipeline trace: graph hops, chunk scores, embedding calls, token counts."
    ],
    "order": 2,
    "description": "Output panel logging detail."
  },
  "kts.model": {
    "type": "string",
    "default": "auto",
    "enum": ["auto", "gpt-4.1", "gpt-4o", "gpt-4o-mini", "claude-sonnet-4"],
    "enumDescriptions": [
      "Use your active GitHub Copilot model (recommended)",
      "OpenAI GPT-4.1 — strongest reasoning, 1M context",
      "OpenAI GPT-4o — balanced quality and speed",
      "OpenAI GPT-4o Mini — fast and lightweight",
      "Anthropic Claude Sonnet 4 — strong analysis"
    ],
    "order": 3,
    "description": "Language model for answer generation. 'auto' uses your active Copilot model."
  },

  "kts.backendMode": {
    "type": "string",
    "default": "auto",
    "enum": ["auto", "venv", "exe"],
    "order": 100,
    "markdownDescription": "**[Developer]** Backend execution: 'auto' (prefer exe), 'venv' (live Python), 'exe' (compiled)."
  },
  "kts.backendChannel": {
    "type": "string",
    "default": "bundled",
    "enum": ["bundled", "workspace"],
    "order": 101,
    "markdownDescription": "**[Developer]** Backend source: 'bundled' (VSIX) or 'workspace' (git repo)."
  },
  "kts.pythonPath": {
    "type": "string",
    "default": "",
    "order": 102,
    "markdownDescription": "**[Developer]** Override Python executable path."
  },
  "kts.kbWorkspacePath": {
    "type": "string",
    "default": "",
    "order": 103,
    "markdownDescription": "**[Developer]** Override knowledge base workspace path."
  },
  "kts.ingestionTimeoutMinutes": {
    "type": "integer",
    "default": 60,
    "minimum": 5,
    "maximum": 180,
    "order": 104,
    "markdownDescription": "**[Developer]** Max time (minutes) for document ingestion."
  }
}
```

**Result:** Users see 3 settings. Developers see 5 more under `[Developer]` prefix.

### 4.2 Backward Compatibility

The old `kts.sourcePath` setting may be in existing users' `settings.json`.
Add a migration check in `extension/extension.js`:

```javascript
// Migrate kts.sourcePath → kts.sourceFolder
const cfg = vscode.workspace.getConfiguration('kts');
const oldPath = cfg.get('sourcePath', '');
const newPath = cfg.get('sourceFolder', '');
if (oldPath && !newPath) {
  await cfg.update('sourceFolder', oldPath, vscode.ConfigurationTarget.Global);
  outputChannel.appendLine(`[KTS] Migrated kts.sourcePath → kts.sourceFolder: ${oldPath}`);
}
```

---

## 5. Implementation: Changes to `extension/chat/participant.js`

### 5.1 Replace All Settings Reads with RAG_CONFIG

**Before (scattered throughout the file):**

```javascript
// Line ~1452: Multi-query variants
let numVariants = 4;
try {
  const cfg = vscode.workspace.getConfiguration('kts');
  numVariants = cfg.get('multiQueryVariants', 4);
} catch (_) { /* use default */ }

// Line ~535: Max chunks
let maxChunks = 100;
try {
  const cfg = vscode.workspace.getConfiguration('kts');
  maxChunks = cfg.get('maxContextChunks', 100);
} catch (_) { /* use default */ }

// Line ~553: Token budget
let modelMaxTokens = model.maxInputTokens || 4096;
try {
  const cfg = vscode.workspace.getConfiguration('kts');
  modelMaxTokens = cfg.get('tokenBudget', modelMaxTokens);
} catch (_) { /* use model's native max */ }
```

**After (one constant, used everywhere):**

```javascript
// Top of participant.js, after imports
const RAG_CONFIG = {
  maxContextChunks: 100,
  tokenBudget: 800000,
  multiQueryVariants: 4,
  selfRagEnabled: true,
  selfRagMaxRounds: 3,
  critiqueEnabled: true,
  critiqueMaxRounds: 3,
  graphRagMaxIterations: 10,
  TOKEN_RATIO: 4,
  RESERVED_TOKENS: 5000,
};

// Then replace every try/catch settings read:
// BEFORE: let numVariants = 4; try { ... } catch (_) {}
// AFTER:  const numVariants = RAG_CONFIG.multiQueryVariants;
```

### 5.2 Specific Lines to Change

| Location | Current Code | Replacement |
|----------|-------------|-------------|
| ~Line 535 | `maxChunks = cfg.get('maxContextChunks', 100)` | `const maxChunks = RAG_CONFIG.maxContextChunks` |
| ~Line 553 | `modelMaxTokens = cfg.get('tokenBudget', ...)` | `const modelMaxTokens = RAG_CONFIG.tokenBudget` |
| ~Line 1452 | `numVariants = cfg.get('multiQueryVariants', 4)` | `const numVariants = RAG_CONFIG.multiQueryVariants` |
| ~Line 1532 | `selfRagEnabled = cfg.get('selfRagEnabled', false)` | `const selfRagEnabled = RAG_CONFIG.selfRagEnabled` |
| ~Line 1567 | `maxRounds = cfg.get('selfRagMaxRounds', 3)` | `const maxRounds = RAG_CONFIG.selfRagMaxRounds` |
| ~Line 1643 | `critiqueEnabled = cfg.get('critiqueLoopEnabled', true)` | `const critiqueEnabled = RAG_CONFIG.critiqueEnabled` |

### 5.3 Model Selection Unification

**Before (5 model selections):**

```javascript
// Generation model
const cfg = vscode.workspace.getConfiguration('kts');
const modelSetting = cfg.get('generationModel');
// ... resolve model

// Reasoning model per component
async function selectReasoningModel(vscode, component = null) {
  const componentKey = `${component}Model`;
  const componentModel = cfg.get(componentKey, 'auto');
  // ... complex per-component resolution
}
```

**After (1 model for everything):**

```javascript
/**
 * Select the single LLM model for all RAG operations.
 * Uses kts.model setting or the user's active Copilot model.
 */
async function selectModel(vscode, requestModel) {
  // 1. User's chat picker model (highest priority)
  if (requestModel && typeof requestModel.sendRequest === 'function') {
    return requestModel;
  }

  // 2. kts.model setting
  const cfg = vscode.workspace.getConfiguration('kts');
  const modelSetting = cfg.get('model', 'auto');
  
  if (modelSetting && modelSetting !== 'auto') {
    try {
      const models = await vscode.lm.selectChatModels({ family: modelSetting });
      if (models && models.length > 0) return models[0];
    } catch (_) { /* fallback */ }
  }

  // 3. Fallback: auto-select best available
  const families = ['gpt-4.1', 'gpt-4o', 'claude-sonnet-4', 'gpt-4o-mini'];
  for (const family of families) {
    try {
      const models = await vscode.lm.selectChatModels({ vendor: 'copilot', family });
      if (models && models.length > 0) return models[0];
    } catch (_) { /* try next */ }
  }

  return null;
}

// Usage: same model everywhere
const model = await selectModel(vscode, request.model);
// model is used for: generation, multi-query, self-RAG, critique, follow-ups, gap analysis
```

This eliminates `selectChatModel()` AND `selectReasoningModel()` — replaced by one
function `selectModel()`.

---

## 6. Token Budget Auto-Computation

Instead of a hardcoded 800K token budget, detect the model's context window:

```javascript
function computeTokenBudget(model) {
  const maxTokens = model.maxInputTokens || 128000;  // VS Code LM API provides this
  // Use 80% of context window, leaving 20% for system prompt + generation
  return Math.floor(maxTokens * 0.8);
}

// In generateAnswer():
const tokenBudget = computeTokenBudget(model);
// If user picks gpt-4.1 (1M): tokenBudget = 800,000
// If user picks gpt-4o (128K): tokenBudget = 102,400
// If user picks gpt-4o-mini (128K): tokenBudget = 102,400
```

This means we never need a `tokenBudget` setting — it adapts to the model automatically.
Similarly, `maxContextChunks` can be scaled:

```javascript
function computeMaxChunks(tokenBudget) {
  // Average chunk is ~500 tokens. Leave room for 60% retrieval, 40% other.
  return Math.min(200, Math.floor(tokenBudget * 0.6 / 500));
}
```

---

## 7. Acceptance Criteria

- [ ] `extension/package.json` shows exactly 3 user-facing settings + 5 developer settings
- [ ] All RAG tuning parameters are in `RAG_CONFIG` constant in `participant.js`
- [ ] No `try { cfg.get(...) } catch` blocks remain in `participant.js` (except for the 3 user settings)
- [ ] `selectModel()` replaces both `selectChatModel()` and `selectReasoningModel()`
- [ ] Token budget is auto-computed from `model.maxInputTokens`
- [ ] Existing behavior is unchanged (all removed settings default to their current values)
- [ ] Backward compatibility: `kts.sourcePath` migrates to `kts.sourceFolder`
- [ ] Golden test harness score is unchanged (settings simplification is behavior-preserving)

---

## 8. Before/After Summary

| Metric | Before | After |
|--------|--------|-------|
| User-facing settings | 23 | 3 |
| Model dropdowns | 5 | 1 |
| Boolean toggles | 4 | 0 |
| Numeric knobs | 6 | 0 |
| Settings read try/catch blocks | ~15 | 3 |
| Model selection functions | 2 | 1 |
| Code complexity | High (scattered reads) | Low (one config object) |
