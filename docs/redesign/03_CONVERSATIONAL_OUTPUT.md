# Phase C: Conversational Output Format

**Created:** 2026-02-20  
**Status:** APPROVED — Ready for Implementation  
**Effort:** 1-2 hours  
**Priority:** P0 — Do alongside Dev Environment

---

## 1. Problem Statement

### Current Output

The system forces a rigid 5-section academic format via the system prompt:

```
**1. Deal / Scope**
   - Deal name (if identified from context)
   - Documents referenced

**2. Answer (Document-Grounded)**
   - Provide the best direct answer...

**3. Supporting Excerpts**
   - Quote the key excerpts...

**4. Definition Chain** (if applicable)
   - Term → definition source

**5. Gaps / Not Found**
   - If the documents do not contain...
```

### What Users Actually Want

**The GitHub Copilot experience.** When you ask me a question, I:
- Answer directly and conversationally
- Cite sources inline (e.g., "per Section 5.06, the Trustee must...")
- Mention gaps naturally ("the PSA doesn't specify the exact deadline for this")
- Don't impose numbered sections unless the content warrants it
- Adapt the format to the question (lists for enumerations, prose for explanations)

### Real Example of the Problem

**User asks:** "What information must be included in the statement to Certificateholders?"

**Current output (rigid format):**
```
**1. Deal / Scope**
- Bear Stearns Asset Backed Securities 2006-HE2
- PSA (Pooling and Servicing Agreement)

**2. Answer (Document-Grounded)**
The statement to Certificateholders is described in Section 5.06...

**3. Supporting Excerpts**
"The Securities Administrator shall prepare..." (Section 5.06, Page 102)

**4. Definition Chain**
- Certificateholder → Person → individual, corporation...
- Distribution Date → 25th of each month

**5. Gaps / Not Found**
The exact format of the statement is not fully specified in the retrieved context.
```

**Desired output (conversational):**
```
Under Section 5.06 of the PSA, the Securities Administrator must prepare and
deliver a statement to Certificateholders on each Distribution Date (the 25th
of each month, or the next Business Day). The statement must include:

1. The amount of principal and interest distributed to each certificate class
2. The aggregate Stated Principal Balance of the Mortgage Loans
3. The Certificate Principal Balance for each class after the distribution
4. The amount of any Realized Losses allocated
5. The number and principal balance of delinquent Mortgage Loans
6. REO properties and foreclosure status
7. Prepayment speeds and CPR calculations

The statement also includes the certificate factor for each class (per Section
5.06(b)), which allows holders to calculate their current principal balance.

Note: The retrieved context covers the enumerated items but does not include the
full template format. For the exact form, see Exhibit H referenced in Section 5.06.
```

The second answer is what a finance professional would actually use.

---

## 2. New System Prompts

### 2.1 Conversational Legal Prompt

**Replaces:** `LEGAL_SYSTEM_PROMPT` (lines 190-280 of `participant.js`)

```javascript
const LEGAL_SYSTEM_PROMPT = [
  'You are a structured-finance documentation assistant. You answer questions using',
  'ONLY the retrieved context excerpts provided below — never from general knowledge.',
  '',
  'Answer the user\'s question naturally and conversationally. Write the way a senior',
  'analyst would explain something to a colleague: direct, precise, grounded in the',
  'documents.',
  '',
  'Guidelines:',
  '- Cite specific sections and clauses inline (e.g., "per Section 5.06(a), the',
  '  Trustee must..."). Do not create a separate citations section.',
  '- When Capitalized Terms appear, explain their defined meaning inline or in a',
  '  brief parenthetical (e.g., "Distribution Date (the 25th of each month)").',
  '- For enumerations (waterfall steps, reporting items), use a numbered list.',
  '- For definitions, trace the chain naturally: "Current Interest means... where',
  '  Certificate Principal Balance is defined as..."',
  '- If the retrieved context does not contain the answer, say so directly within',
  '  your response — do not create a separate "Gaps" section.',
  '- If the context is ambiguous or silent on a point, quote the relevant text and',
  '  explain what is and isn\'t clear.',
  '- Do NOT use numbered output sections (no "1. Deal/Scope", "2. Answer", etc.).',
  '- Do NOT invent information not present in the retrieved context.',
  '- Do NOT cite external sources, other deals, or general knowledge.',
  '',
  'Write precisely, cite inline, let the answer flow naturally.',
].join('\n');
```

**Key differences from current prompt:**
- 24 lines → 23 lines (similar length, completely different tone)
- Removed rigid numbered output format
- Added "cite inline" instruction
- Added "explain capitalized terms parenthetically" instruction
- Changed from "report template" to "conversation" model
- Removed separate Gaps section — gaps are mentioned naturally
- Added handling for ambiguity ("quote the text and explain")

### 2.2 Conversational KTS (Non-Legal) Prompt

**Replaces:** `KTS_SYSTEM_PROMPT` (lines 126-188 of `participant.js`)

```javascript
const KTS_SYSTEM_PROMPT = [
  'You are a knowledge-base assistant. You answer questions using ONLY the',
  'retrieved context excerpts provided below — never from general knowledge or',
  'external sources.',
  '',
  'Answer the user\'s question naturally and conversationally. Be direct and',
  'helpful, like a knowledgeable colleague.',
  '',
  'Guidelines:',
  '- Cite specific document names and sections inline when relevant.',
  '- For step-by-step procedures, present them as numbered steps.',
  '- For error codes, lead with the resolution, then explain the cause.',
  '- If the question is about a concept, explain it clearly with relevant',
  '  excerpts woven into your answer.',
  '- If the retrieved context does not contain the answer, say so directly.',
  '- Match intent, not just exact wording — "computer will not restate" means',
  '  "will not restart".',
  '- Do NOT use numbered output sections (no "1. Matched Issue", etc.).',
  '- Do NOT invent steps not present in the documents.',
  '',
  'Write concisely, cite inline, focus on solving the user\'s problem.',
].join('\n');
```

**Key differences:**
- Removed rigid "Matched Issue / Solution / Supporting Excerpts" structure
- Added inline citation instruction
- Added step-by-step format guidance (for how-to questions)
- Led with "resolution first, then cause" for error codes
- Much more conversational tone

---

## 3. Native VS Code Chat API: Citations

### 3.1 Current Approach (Manual Markdown)

The current system builds citations as markdown text inside the LLM's answer:

```javascript
// buildLegalContextBlock() — creates markdown labels
return `[Document: ${docName}, Section: ${section}, Page: ${page}]\n${body}`;
```

The LLM then includes these labels in its response text. The user sees:

```
...per [Document: PSA_2006_HE2.pdf, Section: 5.06, Page: 102]...
```

This is plain text. Not clickable. Not styled.

### 3.2 Target Approach (ChatResponseReferencePart)

VS Code's Chat API provides native citation rendering:

```javascript
// After generating the answer, emit file references as native chat references
const vscodeUri = vscode.Uri.file(chunk.source_path);
stream.reference(vscodeUri);
```

This renders as a **clickable pill** below the answer (same style as GitHub Copilot's
file references). Clicking it opens the source document.

### 3.3 Implementation

**In `participant.js`, after the LLM answer is streamed:**

```javascript
// ── Emit native citations ─────────────────────────────
// Collect unique source documents from the retrieved chunks
const citedDocs = new Map();
let search = result.search_result;
if (search?.search_result) search = search.search_result;
const chunks = (search && Array.isArray(search.context_chunks)) ? search.context_chunks : [];

for (const chunk of chunks) {
  const docName = resolveDocName(chunk, 'unknown');
  if (!citedDocs.has(docName)) {
    // Try to create a file URI if source_path exists
    if (chunk.source_path && fs.existsSync(chunk.source_path)) {
      citedDocs.set(docName, vscode.Uri.file(chunk.source_path));
    } else {
      // Use the document name as a text reference
      citedDocs.set(docName, docName);
    }
  }
}

// Emit each cited document as a ChatResponseReferencePart
for (const [name, uri] of citedDocs) {
  if (typeof uri === 'string') {
    // Text-only reference (no file to link to)
    stream.reference(name);
  } else {
    // Clickable file reference
    stream.reference(uri);
  }
}
```

**Visual result:**
```
Under Section 5.06 of the PSA, the Securities Administrator must prepare
and deliver a statement to Certificateholders on each Distribution Date...

📎 PSA_2006_HE2.pdf    📎 Section_5.06_excerpt
```

The pills appear below the answer, exactly like Copilot's file references.

### 3.4 Anchor Links (ChatResponseAnchorPart)

For more precise references (linking to specific line ranges in a document):

```javascript
// If we know the chunk's position within the document
if (chunk.start_line && chunk.source_path) {
  const loc = new vscode.Location(
    vscode.Uri.file(chunk.source_path),
    new vscode.Range(chunk.start_line - 1, 0, chunk.end_line - 1, 0)
  );
  stream.anchor(loc, `Section ${chunk.section}`);
}
```

This creates an inline link that opens the document at the exact line range.
Useful for: "See Section 5.06(a)(iii)" → click → opens PSA at that section.

**Note:** This requires chunks to carry `source_path`, `start_line`, `end_line` metadata.
If not available, fall back to document-level references.

---

## 4. Native Follow-Up Chips

### 4.1 Current Approach (Duplicate)

We currently have TWO follow-up mechanisms:

1. **`followupProvider`** (native, correct) — renders clickable chips below the answer
2. **Markdown bullets in the answer** — `generateLLMFollowUps()` appends suggestions as markdown text

The user sees both: the LLM answer includes follow-up bullets, AND the native chips
appear below. This is confusing and redundant.

### 4.2 Target Approach

**Keep ONLY the `followupProvider`.** Remove all markdown follow-up rendering.

The `followupProvider` is already implemented in `participant.js` (line ~1366):

```javascript
// Phase 11.2: Follow-up state for the followup provider
let _lastFollowUps = [];
```

And registered with:

```javascript
participant.followupProvider = {
  provideFollowups(result, context, token) {
    return _lastFollowUps.map(f => ({
      prompt: f,
      label: f,
      command: '',
    }));
  },
};
```

This already works. We just need to:
1. Remove the markdown follow-up rendering from the answer stream
2. Ensure `_lastFollowUps` is populated with LLM-generated follow-ups
3. The native chips render automatically

### 4.3 What to Remove

In the answer streaming section (~line 1768), there's code that renders follow-ups
as markdown bullets:

```javascript
// REMOVE: These create markdown follow-ups in the answer body
stream.markdown('\n\n---\n**Suggested Follow-up Questions:**\n');
for (const followUp of followUpSuggestions) {
  stream.markdown(`- ${followUp}\n`);
}
```

After removal, follow-ups appear ONLY as native clickable chips below the answer.

---

## 5. Streaming Pipeline Cleanup

### 5.1 Current Flow (Complex)

```
generateAnswer() [bufferMode: true]
  → Collects full answer as string (doesn't stream)
  → Returns answer text

Self-RAG loop [optional]
  → May replace answer text with refined version
  → Each round: full backend call + LLM synthesis

Critique loop [optional]
  → May further modify answer text
  → Each round: critique model + rewrite

Final streaming:
  → stream.markdown(finalAnswer)
  → stream.markdown(followUpBullets)   ← REMOVE
  → _lastFollowUps = generated         ← KEEP
```

### 5.2 Target Flow (Simplified)

```
generateAnswer() [bufferMode: depends on config]
  → If Self-RAG disabled: stream directly, no buffering
  → If Self-RAG enabled: buffer, then stream final version

Self-RAG loop [if enabled]
  → May replace answer with refined version

stream.markdown(finalAnswer)
stream.reference(citedDocs)            ← NEW: native citations
_lastFollowUps = generatedFollowUps    ← KEEP: native chips only
```

### 5.3 Progress Messages

The current `stream.progress()` calls are correct and should be kept:

```javascript
stream.progress('Searching knowledge base...');
stream.progress('Reranking candidates...');
stream.progress('Generating answer...');
stream.progress('Self-RAG round 2...');  // if Self-RAG enabled
```

These display as ephemeral status messages in the chat UI. Good UX, keep them.

---

## 6. LLM Prompt Construction (After Changes)

### 6.1 Final Prompt Structure

```
[System Prompt — 23 lines, conversational]
[Temporal Context — if available, 1-2 lines]
[Cached Terms — if available, resolved definitions from session]
[Conversation History — last 10 turns, if multi-turn]
---
## Retrieved Context
[Chunk 1: Document name, Section, Content]
[Chunk 2: ...]
[...]
[Chunk N: ...]

## User Question
[The actual question]
```

### 6.2 Context Block Format (Simplified)

Instead of heavy markup per chunk, use a clean readable format:

```javascript
function buildContextBlock(chunks, maxChunks) {
  return chunks.slice(0, maxChunks).map((chunk, i) => {
    const doc = resolveDocName(chunk, `source-${i + 1}`);
    const sec = chunk.section ? ` | ${chunk.section}` : '';
    const body = (chunk.content || '').replace(/^\[EVIDENCE\][^\n]*\n?/, '').trim();
    return `--- Source ${i + 1}: ${doc}${sec} ---\n${body}`;
  }).join('\n\n');
}
```

This produces:
```
--- Source 1: PSA_2006_HE2.pdf | Section 5.06 ---
The Securities Administrator shall prepare and forward to each
Certificateholder a statement setting forth...

--- Source 2: PSA_2006_HE2.pdf | Section 1.01 ---
"Distribution Date" means the 25th day of each month...
```

Clean, readable, no JSON-like bracket syntax. The LLM can reference "Source 1" or
"Section 5.06" naturally in its answer.

### 6.3 Unified Context Builder

Replace both `buildContextBlock()` and `buildLegalContextBlock()` with a single
function that works for both modes:

```javascript
/**
 * Build a context block from retrieved chunks for the LLM prompt.
 * Unified for both legal and non-legal modes.
 */
function buildContextBlock(result, maxChunks = 100) {
  let search = result.search_result;
  if (search?.search_result && typeof search.search_result === 'object') {
    search = search.search_result;
  }
  const chunks = Array.isArray(search.context_chunks) ? search.context_chunks : [];
  if (!chunks.length) return '';

  return chunks.slice(0, maxChunks).map((chunk, i) => {
    const body = (chunk.content || '').replace(/^\[EVIDENCE\][^\n]*\n?/, '').trim();
    const doc = resolveDocName(chunk, `source-${i + 1}`);
    const sec = chunk.section ? ` | ${chunk.section}` : '';
    const pg = (chunk.page != null) ? ` | Page ${chunk.page}` : '';
    return `--- Source ${i + 1}: ${doc}${sec}${pg} ---\n${body}`;
  }).join('\n\n');
}
```

This eliminates `buildLegalContextBlock()` entirely. Both modes use the same function.
The system prompt determines the tone and format of the answer, not the context block.

---

## 7. Exact File Changes

### 7.1 `extension/chat/participant.js`

| Line Range | Change | Description |
|------------|--------|-------------|
| 126-188 | REPLACE | `KTS_SYSTEM_PROMPT` → new conversational prompt (Section 2.2) |
| 190-280 | REPLACE | `LEGAL_SYSTEM_PROMPT` → new conversational prompt (Section 2.1) |
| 403-460 | REPLACE | Merge `buildContextBlock()` + `buildLegalContextBlock()` into unified function (Section 6.3) |
| ~541-542 | SIMPLIFY | Remove `mode === 'legal'` branch — use one `buildContextBlock()` |
| ~1768-1785 | REMOVE | Markdown follow-up rendering (keep only `_lastFollowUps` assignment) |
| After answer stream | ADD | Native citation emission using `stream.reference()` (Section 3.3) |

### 7.2 What NOT to Change

- `selectPrompt()` function — still needed to set `mode` for logging and follow-up generation
- `generateAnswer()` — structure stays the same, just uses new prompt content
- `trimContextToTokenBudget()` — still needed for token budget enforcement
- Diagnostic logging — still needed for the Output panel trace
- Self-RAG and Critique orchestration — unchanged (their prompts reference the system prompt)

---

## 8. Testing Plan

### 8.1 Before/After Comparison

Use the golden test harness (Phase D) to compare:

| Question | Old Format | New Format | Better? |
|----------|-----------|-----------|---------|
| "What does Distribution Date mean?" | 5-section report | Conversational with inline definition | Judge |
| "Walk me through the interest waterfall" | Report with excerpts section | Numbered list with inline citations | Judge |
| "What info is in the statement to certificateholders?" | Report with gaps section | Enumerated list with natural gap mention | Judge |

### 8.2 Regression Checks

Ensure the new prompt doesn't introduce:
- **Hallucination** — the "only use retrieved context" constraint is STRONGER in the new prompt
- **Missing citations** — inline citations should be MORE frequent, not less
- **Under-answering** — the conversational style shouldn't truncate; it should synthesize fully
- **Over-answering** — don't add information beyond what the context provides

### 8.3 Format Flexibility

The new prompt should produce different formats depending on the question type:

| Question Type | Expected Format |
|---------------|-----------------|
| "Define X" | Prose with inline definition chain |
| "What are the key dates?" | Table or bullet list |
| "Walk me through the waterfall" | Numbered sequential steps |
| "Who are the parties?" | Bullet list with roles |
| "What happens if X?" | Conditional explanation with section references |
| Follow-up: "Tell me more about that" | Continuation of previous answer style |

The LLM should choose the format. We do NOT prescribe it.

---

## 9. Acceptance Criteria

- [ ] `LEGAL_SYSTEM_PROMPT` and `KTS_SYSTEM_PROMPT` replaced with conversational versions
- [ ] No rigid "1. Deal/Scope 2. Answer 3. Excerpts 4. Chain 5. Gaps" in any output
- [ ] Source citations appear as VS Code native reference pills below the answer
- [ ] Follow-up suggestions appear ONLY as native clickable chips (no markdown bullets in answer)
- [ ] Inline citations present in the answer text ("per Section 5.06...")
- [ ] Answer format adapts to question type (lists for waterfall, prose for definitions)
- [ ] `buildLegalContextBlock()` merged into unified `buildContextBlock()`
- [ ] Golden test pass rate is equal or better than baseline (no regression)
- [ ] No hallucination detected in golden test suite (LLM-as-judge)

---

## 10. Visual Mockup

### Before (v0.0.21)

```
┌─────────────────────────────────────────────────┐
│ @kts What does Distribution Date mean?          │
├─────────────────────────────────────────────────┤
│ **1. Deal / Scope**                             │
│ - Bear Stearns 2006-HE2                         │
│ - PSA                                            │
│                                                  │
│ **2. Answer (Document-Grounded)**               │
│ Distribution Date means the 25th day of each     │
│ month, commencing in February 2006...            │
│                                                  │
│ **3. Supporting Excerpts**                       │
│ "Distribution Date: shall mean the 25th day..."  │
│ (Section 1.01, Page 15)                          │
│                                                  │
│ **4. Definition Chain**                          │
│ - Distribution Date → Section 1.01               │
│ - Business Day → Section 1.01                    │
│                                                  │
│ **5. Gaps / Not Found**                          │
│ No gaps identified.                              │
│                                                  │
│ ---                                              │
│ **Suggested Follow-up Questions:**               │
│ - What is a Business Day?                        │
│ - When is the first Distribution Date?           │
│ - How are distributions calculated?              │
│                                                  │
│ [What is a Business Day?]  [When is the first...│ ← native chips (DUPLICATE!)
└─────────────────────────────────────────────────┘
```

### After (Redesign)

```
┌─────────────────────────────────────────────────┐
│ @kts What does Distribution Date mean?          │
├─────────────────────────────────────────────────┤
│ Distribution Date is defined in Section 1.01     │
│ as the 25th day of each month (or the next       │
│ Business Day if the 25th falls on a weekend or   │
│ holiday), beginning February 2006. A Business    │
│ Day is any day other than a Saturday, Sunday, or │
│ day on which banking institutions in New York     │
│ are authorized or obligated by law to close.     │
│                                                  │
│ The first Distribution Date for this deal was    │
│ February 27, 2006 (the 25th was a Saturday).     │
│                                                  │
│ 📎 PSA_2006_HE2.pdf                             │
│                                                  │
│ [What happens on each Distribution Date?]        │
│ [How are distributions calculated?]              │
│ [What is the Record Date?]                       │
└─────────────────────────────────────────────────┘
```

Cleaner. More useful. No academic scaffolding. Citations as pills. Follow-ups as chips only.
