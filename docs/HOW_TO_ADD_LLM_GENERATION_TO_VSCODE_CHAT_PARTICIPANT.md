# How-To: Add LLM Generation to a VS Code Chat Participant (RAG Pattern)

> **Origin**: GSF IR KTS Agentic System, February 2026  
> **Audience**: Developers building VS Code extensions with `@chat` participants that need RAG (Retrieval-Augmented Generation)  
> **Prerequisite**: A working VS Code extension with a chat participant that already retrieves context (chunks/documents) from a backend

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Architecture Overview](#2-architecture-overview)
3. [Step-by-Step Implementation](#3-step-by-step-implementation)
   - 3.1 [Diagnose the Gap](#31-diagnose-the-gap)
   - 3.2 [Design the System Prompt](#32-design-the-system-prompt)
   - 3.3 [Implement Model Selection](#33-implement-model-selection)
   - 3.4 [Build the Context Block](#34-build-the-context-block)
   - 3.5 [Implement Streaming Generation](#35-implement-streaming-generation)
   - 3.6 [Wire into the Chat Handler](#36-wire-into-the-chat-handler)
   - 3.7 [Add Citation & Metadata Appendix](#37-add-citation--metadata-appendix)
4. [Critical Gotchas & Bugs We Hit](#4-critical-gotchas--bugs-we-hit)
5. [Testing Strategy](#5-testing-strategy)
6. [VSIX Packaging & Verification](#6-vsix-packaging--verification)
7. [Complete Code Reference](#7-complete-code-reference)
8. [Checklist](#8-checklist)

---

## 1. Problem Statement

A VS Code chat participant (`@your-agent`) that only returns **raw retrieved chunks** is not a RAG system — it's just an "R" (Retrieval). Users expect synthesized, grounded answers like ChatGPT or Copilot Chat provides.

**Before (retrieval-only)**:
```
User: "How do I fix the dashboard timeout?"

@kts:
### Context 1
Fixed dashboard timeout in ACME v3.2.1 patch...
### Context 2
Known issue: Dashboard hangs after 30 seconds on slow networks...
### Citations
1. ACME Release Notes v3.2.1
```

**After (full RAG with generation)**:
```
User: "How do I fix the dashboard timeout?"

@kts:
The dashboard timeout issue was resolved in ACME v3.2.1. To fix it:
1. Update to ACME v3.2.1 or later
2. If on a slow network, increase the timeout setting in Settings > Dashboard > Timeout
Per the ACME v3.2.1 Release Notes, the root cause was a missing keep-alive on the WebSocket connection.

---
### Sources
1. ACME Release Notes v3.2.1
2. ACME Known Issues Q4 2025

### Agent Reasoning
Retrieval pipeline completed in 1 iteration(s), confidence: 0.87.
- vector_search: Searched 1200 chunks (120ms)
- cross_encoder: Reranked top 20 (45ms)
```

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  VS Code Chat Participant Handler                       │
│                                                         │
│  1. User types question in @your-agent chat              │
│  2. Handler calls backend (CLI/API) for retrieval        │
│  3. Backend returns ranked chunks + citations            │
│  4. Handler selects LLM model via vscode.lm API          │
│  5. Handler sends: [System Prompt + Chunks + Question]   │
│  6. LLM streams synthesized answer into chat             │
│  7. Handler appends citations & metadata below answer    │
│  8. If LLM unavailable → falls back to raw chunks        │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Key insight**: The backend does NOT need modification. All generation logic lives in the **extension JavaScript** (the chat participant handler). The VS Code Language Model API (`vscode.lm`) provides access to whatever model the user has selected in their Copilot chat model picker (GPT-4o, Claude, etc.).

---

## 3. Step-by-Step Implementation

### 3.1 Diagnose the Gap

Before implementing, confirm your chat participant lacks generation. Search your participant handler for these patterns:

```bash
# If NONE of these exist in your chat handler, you're retrieval-only:
grep -n "vscode.lm"              extension/chat/participant.js
grep -n "selectChatModels"       extension/chat/participant.js
grep -n "sendRequest"            extension/chat/participant.js
grep -n "LanguageModelChatMessage" extension/chat/participant.js
```

A retrieval-only handler typically looks like:
```javascript
const result = await backendSearch(query);
stream.markdown(formatAsMarkdown(result));  // ← raw chunks, no LLM
```

### 3.2 Design the System Prompt

The system prompt defines your agent's persona, scope, and guardrails. **This is domain-specific** — do not use a generic prompt.

**Template**:
```javascript
const SYSTEM_PROMPT = [
  'You are **[AGENT NAME]** — [one-line description of role and team].',
  '',
  '## Your role',
  '- [What the agent helps with, line 1]',
  '- [What the agent helps with, line 2]',
  '- Your source material consists of: [list corpus types].',
  '',
  '## Rules',
  '1. **Ground every answer in the retrieved context** provided below.',
  '   Do NOT fabricate steps, version numbers, config values, or tool names.',
  '2. If the retrieved context does not contain enough information to answer,',
  '   say so clearly: "[Your agent] does not have information on this topic yet."',
  '3. When troubleshooting, give **numbered step-by-step** instructions.',
  '4. When referencing a source document, mention its name naturally.',
  '5. Be concise and actionable.',
  '6. Do NOT answer questions outside your domain.',
  '7. If multiple sources conflict, surface the conflict and note which is newer.',
  '8. Use plain language; expand acronyms on first use.',
].join('\\n');
```

**KTS example** (IT support / knowledge base assistant):
```javascript
const KTS_SYSTEM_PROMPT = [
  'You are **KTS** — the Knowledge base, Training, and Support assistant for the',
  'Global Structured Finance Investor Reporting (GSF IR) team.',
  '',
  '## Your role',
  '- Answer questions about internal tools, platforms, and workflows used by GSF IR.',
  '- Help users troubleshoot errors, set up tools, and follow documented procedures.',
  '- Your source material consists of: release notes, tool setup guides,',
  '  troubleshooting guides, known-issues lists, and FAQs.',
  // ... rules ...
].join('\\n');
```

### 3.3 Implement Model Selection

The VS Code Chat API passes the user's selected model via `request.model`. Always prefer this over auto-detection.

```javascript
/**
 * Select a Copilot chat model for answer synthesis.
 * Prefers the user's selected model from request.model (VS Code chat picker).
 * Falls back to auto-detection if not available.
 */
async function selectChatModel(vscode, requestModel) {
  // 1. Use the model the user selected in the chat model picker
  if (requestModel && typeof requestModel.sendRequest === 'function') {
    return requestModel;
  }

  // 2. Fallback: auto-select from available models
  if (!vscode.lm || typeof vscode.lm.selectChatModels !== 'function') {
    return null;
  }

  const families = ['gpt-4o', 'claude-3.5-sonnet', 'gpt-4o-mini'];
  for (const family of families) {
    try {
      const models = await vscode.lm.selectChatModels({ vendor: 'copilot', family });
      if (models && models.length > 0) return models[0];
    } catch (_) { /* try next */ }
  }

  // Last resort: any copilot model
  try {
    const models = await vscode.lm.selectChatModels({ vendor: 'copilot' });
    if (models && models.length > 0) return models[0];
  } catch (_) { /* no model */ }

  return null;
}
```

### 3.4 Build the Context Block

Format retrieved chunks with source labels so the LLM can cite them:

```javascript
function buildContextBlock(result) {
  const chunks = result.context_chunks || [];
  if (!chunks.length) return '';

  return chunks
    .slice(0, 8)  // limit to 8 chunks to stay within token budget
    .map((chunk, i) => {
      const body = (chunk.content || '').trim();
      const source = chunk.doc_name || chunk.doc_id || `source-${i + 1}`;
      return `[Source ${i + 1}: ${source}]\n${body}`;
    })
    .join('\n\n');
}
```

### 3.5 Implement Streaming Generation

⚠️ **CRITICAL GOTCHA**: The VS Code `LanguageModelChatMessage` API does **NOT** have a `System()` method. Only `User()` and `Assistant()` exist. Embed your system prompt in the User message.

```javascript
async function generateAnswer(vscode, model, stream, token, query, result) {
  const contextBlock = buildContextBlock(result);
  if (!contextBlock) return false;

  // Combine system prompt + context + question into a single User message
  // ⚠️ vscode.LanguageModelChatMessage has NO .System() method!
  const userMessage = [
    SYSTEM_PROMPT,       // ← persona + rules
    '',
    '---',
    '',
    '## Retrieved Context',
    contextBlock,        // ← labeled chunks
    '',
    '## User Question',
    query,               // ← original user question
  ].join('\n');

  const messages = [
    vscode.LanguageModelChatMessage.User(userMessage),
  ];

  try {
    const response = await model.sendRequest(messages, {}, token);
    // Stream tokens into the chat as they arrive
    for await (const chunk of response.text) {
      stream.markdown(chunk);
    }
    return true;
  } catch (err) {
    // Quota exceeded, network error, cancellation — fall back to raw chunks
    return false;
  }
}
```

### 3.6 Wire into the Chat Handler

Replace the raw `stream.markdown(toMarkdown(result))` call with the generation flow:

```javascript
// BEFORE (retrieval-only):
const result = await backendSearch(query);
stream.markdown(toMarkdown(result));

// AFTER (full RAG):
const result = await backendSearch(query);

let generated = false;
if (result && result.status === 'ok') {
  const model = await selectChatModel(vscode, request.model);
  if (model) {
    outputChannel.appendLine(`[RAG] Using model: ${model.id || model.family}`);
    generated = await generateAnswer(vscode, model, stream, token, query, result);
  } else {
    outputChannel.appendLine('[RAG] No LLM model available — falling back to raw chunks.');
  }
}

if (generated) {
  // Append citations below the generated answer
  const citations = buildCitationBlock(result);
  if (citations) {
    stream.markdown('\n\n---\n');
    stream.markdown(citations);
  }
} else {
  // Fallback: return raw chunks (pre-RAG behavior, ensures no regression)
  stream.markdown(toMarkdown(result));
}
```

### 3.7 Add Citation & Metadata Appendix

After the generated answer, append sources and any pipeline trace:

```javascript
function buildCitationBlock(result) {
  const citations = result.citations || [];
  if (!citations.length) return '';

  const citationMd = citations
    .slice(0, 10)
    .map((c, i) => {
      const label = c.doc_name || c.doc_id || `source-${i + 1}`;
      const uri = c.uri || c.source_path;
      return uri ? `${i + 1}. [${label}](${uri})` : `${i + 1}. ${label}`;
    })
    .join('\n');

  return `\n### Sources\n${citationMd}\n`;
}
```

---

## 4. Critical Gotchas & Bugs We Hit

These are real bugs encountered during implementation. Save yourself hours by reading these first.

### Gotcha 1: `LanguageModelChatMessage.System is not a function`

**Error**: `KTS failed to process the request: vscode.LanguageModelChatMessage.System is not a function`

**Root cause**: The VS Code Language Model API only exposes:
- `vscode.LanguageModelChatMessage.User(content)`
- `vscode.LanguageModelChatMessage.Assistant(content)`

There is **NO** `System()` method, unlike the OpenAI Chat API.

**Fix**: Embed the system prompt at the top of the User message, separated by `---`:
```javascript
// ❌ WRONG — crashes at runtime
const messages = [
  vscode.LanguageModelChatMessage.System(SYSTEM_PROMPT),
  vscode.LanguageModelChatMessage.User(userQuestion),
];

// ✅ CORRECT — system prompt embedded in User message
const messages = [
  vscode.LanguageModelChatMessage.User(
    SYSTEM_PROMPT + '\n\n---\n\n' + contextBlock + '\n\n' + userQuestion
  ),
];
```

### Gotcha 2: `selectChatModels` always returns gpt-4o (ignores user's model picker)

**Symptom**: Output log always shows `[KTS] RAG generation using model: gpt-4o` even when the user selects Claude or GPT-4o-mini in the chat model picker dropdown.

**Root cause**: Hardcoded model family preference list that always tries gpt-4o first:
```javascript
// ❌ Always picks gpt-4o regardless of user's selection
async function selectChatModel(vscode) {
  const families = ['gpt-4o', 'claude-3.5-sonnet', ...];
  // gpt-4o always found first, returned immediately
}
```

**Fix**: The VS Code Chat API provides the user's selected model via `request.model`. Check it first:
```javascript
// ✅ Honors the user's model picker selection
async function selectChatModel(vscode, requestModel) {
  if (requestModel && typeof requestModel.sendRequest === 'function') {
    return requestModel;  // user's choice
  }
  // ... fallback auto-detection only if request.model is absent
}

// In the handler:
const model = await selectChatModel(vscode, request.model);
```

### Gotcha 3: Backend rebuild is NOT needed for extension-only changes

The generation logic lives entirely in the extension JavaScript. If your backend (Python, exe, etc.) is unchanged, you do **NOT** need to rebuild it. Only the VSIX needs repackaging.

### Gotcha 4: `User()` accepts a string, not an array (for text-only)

For text-only messages (no images), pass a simple string. Arrays with `LanguageModelTextPart` are only needed when mixing text + images:

```javascript
// Text-only: pass a string
vscode.LanguageModelChatMessage.User("Your prompt text here")

// Multimodal (text + image): pass an array of parts
vscode.LanguageModelChatMessage.User([
  new vscode.LanguageModelTextPart("Describe this image"),
  vscode.LanguageModelDataPart.image(imageData, 'image/png'),
])
```

---

## 5. Testing Strategy

The `vscode.lm` API only works inside a running VS Code extension host, so you **cannot** call Copilot from a plain Node.js test. Instead, mock the `vscode` object:

### Mock Structure

```javascript
function createMockVscode({ modelAvailable = true, modelError = false } = {}) {
  const capturedMessages = [];
  const streamedOutput = [];

  const mockModel = {
    id: 'gpt-4o-test',
    family: 'gpt-4o',
    sendRequest: async (messages, opts, token) => {
      capturedMessages.push(...messages);
      if (modelError) throw new Error('Model quota exceeded');
      return {
        text: (async function* () {
          yield 'Answer chunk 1. ';
          yield 'Answer chunk 2.';
        })(),
      };
    },
  };

  return {
    vscode: {
      lm: {
        selectChatModels: async ({ vendor, family } = {}) => {
          if (!modelAvailable) return [];
          if (family === 'gpt-4o') return [mockModel];
          return [];
        },
      },
      chat: {
        createChatParticipant: (id, handler) => {
          return { id, handler, dispose: () => {} };
        },
      },
      LanguageModelChatMessage: {
        User: (text) => ({ role: 'user', content: text }),
      },
    },
    mockModel,
    capturedMessages,
    streamedOutput,
    stream: { markdown: (text) => streamedOutput.push(text) },
    token: { isCancellationRequested: false },
  };
}
```

### What to Test (7 categories, 48 assertions in KTS)

| Test | What it validates |
|---|---|
| **System prompt persona** | Prompt contains your agent name, team, corpus types, grounding rules |
| **Context + query formatting** | Chunks are labeled `[Source N: name]`, metadata stripped, query included |
| **Streaming generation** | LLM response streams token-by-token, citations appended after |
| **Trace/metadata appendix** | Pipeline reasoning steps shown, start/complete steps filtered |
| **Fallback: no model** | Gracefully returns raw chunks, logs the reason |
| **Fallback: LLM error** | If `sendRequest()` throws, returns raw chunks without crashing |
| **request.model honored** | User-selected model used; `selectChatModels` NOT called when `request.model` exists |

### Running the Test

```bash
node tests/test_rag_generation.js
# Expected: 48 passed, 0 failed
```

### Intercepting `require()` for Mocking

Since `participant.js` uses `require('../copilot/kts_tool')`, intercept it in the test:

```javascript
const Module = require('module');
const originalResolve = Module._resolveFilename;
Module._resolveFilename = function (request, parent, ...rest) {
  if (request.includes('kts_tool')) return '__mock_kts_tool__';
  if (request.includes('image_describer')) return '__mock_image_describer__';
  return originalResolve.call(this, request, parent, ...rest);
};

require.cache['__mock_kts_tool__'] = {
  id: '__mock_kts_tool__', filename: '__mock_kts_tool__', loaded: true,
  exports: async function ktsTool(query, opts) {
    return { status: 'ok', search_result: { context_chunks: [...], citations: [...] } };
  },
};
```

---

## 6. VSIX Packaging & Verification

### Build the VSIX

```bash
cd extension
npx @vscode/vsce package --no-dependencies --allow-missing-repository
```

### Move to dist/

```powershell
Move-Item -Path "extension/gsf-ir-kts-extension-0.0.6.vsix" `
          -Destination "dist/gsf-ir-kts-extension-0.0.6.vsix" -Force
```

### Verify the VSIX Contains Your Changes

Always verify — never trust the build blindly:

```powershell
# 1. Check file size grew (RAG code adds ~8-10 KB to participant.js)
npx @vscode/vsce ls --tree 2>&1 | Select-String "participant|chat/"
# Expected: chat/participant.js [~16 KB] (was ~7 KB before)

# 2. Extract and grep for key symbols inside the VSIX
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead("dist/your-extension-0.0.6.vsix")
$entry = $zip.Entries | Where-Object { $_.FullName -like "*participant.js" }
$sr = New-Object System.IO.StreamReader($entry.Open())
$content = $sr.ReadToEnd()
$sr.Close(); $zip.Dispose()

# Check for all RAG generation symbols:
($content | Select-String -Pattern "SYSTEM_PROMPT|selectChatModel|generateAnswer|buildCitationBlock" -AllMatches).Matches.Value | Select-Object -Unique
# Expected: SYSTEM_PROMPT, selectChatModel, generateAnswer, buildCitationBlock
```

### Version Bumping

Always bump version in `package.json` before building:
```json
{
  "version": "0.0.6"  // was 0.0.5
}
```

---

## 7. Complete Code Reference

### File: `extension/chat/participant.js` — Key additions

```javascript
// 1. System prompt (top of file)
const SYSTEM_PROMPT = [...].join('\n');

// 2. Model selection (honors request.model)
async function selectChatModel(vscode, requestModel) { ... }

// 3. Context block builder
function buildContextBlock(result) { ... }

// 4. RAG generation with streaming
async function generateAnswer(vscode, model, stream, token, query, result) { ... }

// 5. Citation & trace helpers
function buildCitationBlock(result) { ... }
function buildTraceBlock(result) { ... }

// 6. Modified handler (in registerChatParticipant)
const model = await selectChatModel(vscode, request.model);
generated = await generateAnswer(vscode, model, stream, token, query, result);
```

### Files changed (summary)

| File | Change | Backend rebuild needed? |
|---|---|---|
| `extension/chat/participant.js` | Added system prompt, model selection, generateAnswer, citation/trace helpers, modified handler | No |
| `extension/package.json` | Version bump 0.0.5 → 0.0.6 | No |
| `tests/test_rag_generation.js` | New — 48-assertion smoke test with mocked vscode | No |

---

## 8. Checklist

Use this checklist for any future project where you need to add LLM generation to a VS Code chat participant:

- [ ] **Diagnose**: Confirm your handler does `stream.markdown(rawChunks)` with no `vscode.lm` calls
- [ ] **System prompt**: Write domain-specific persona with grounding rules (not generic)
- [ ] **Model selection**: Use `request.model` first, `selectChatModels` as fallback only
- [ ] **Message format**: Use `LanguageModelChatMessage.User()` only — **NO `.System()` method exists**
- [ ] **Context block**: Label each chunk `[Source N: doc_name]` so the LLM can cite naturally
- [ ] **Streaming**: Use `for await (const chunk of response.text)` to stream tokens
- [ ] **Fallback**: If `sendRequest()` fails or no model available, return raw chunks (no regression)
- [ ] **Citations**: Append `### Sources` section below a `---` after the generated answer
- [ ] **Tests**: Mock `vscode.lm`, test persona content, streaming, fallback, and `request.model` honored
- [ ] **Verify VSIX**: Extract and grep the built VSIX for key function names before deploying
- [ ] **No backend rebuild**: If only JS extension code changed, skip backend/exe rebuild

---

## Appendix: VS Code Language Model API Quick Reference

```javascript
// Select a model
const models = await vscode.lm.selectChatModels({ vendor: 'copilot', family: 'gpt-4o' });
const model = models[0];

// Or use the user's selection (preferred)
const model = request.model;  // from chat participant handler args

// Build messages (User and Assistant only — NO System)
const messages = [
  vscode.LanguageModelChatMessage.User('Your prompt here'),
];

// For multimodal (text + images):
const messages = [
  vscode.LanguageModelChatMessage.User([
    new vscode.LanguageModelTextPart('Describe this'),
    vscode.LanguageModelDataPart.image(imageBytes, 'image/png'),
  ]),
];

// Send request and stream response
const response = await model.sendRequest(messages, {}, cancellationToken);
for await (const chunk of response.text) {
  stream.markdown(chunk);  // streams to chat UI
}
```

**Minimum VS Code version**: `^1.95.0` (for `vscode.lm.selectChatModels` and chat participant API)

---

*Document created: February 18, 2026*  
*Project: GSF IR KTS Agentic System*  
*Version: 0.0.6*
