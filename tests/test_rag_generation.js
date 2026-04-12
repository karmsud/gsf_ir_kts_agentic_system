/**
 * Smoke test for RAG generation in participant.js
 *
 * Mocks the vscode LM API and kts_tool to verify:
 *  1. System prompt is correct (KTS persona, not financial analyst)
 *  2. Model selection works and falls back gracefully
 *  3. generateAnswer streams tokens into the chat stream
 *  4. Citations and trace are appended after generation
 *  5. Fallback to raw toMarkdown() when no model is available
 *  6. Edge cases: empty chunks, LLM error, cancellation
 *
 * Run: node tests/test_rag_generation.js
 */

const path = require('path');

// ── Fake modules that participant.js requires ──────────────────────────────
// We need to intercept require() for kts_tool and image_describer
const Module = require('module');
const originalResolve = Module._resolveFilename;
Module._resolveFilename = function (request, parent, ...rest) {
  if (request.includes('kts_tool')) {
    return '__mock_kts_tool__';
  }
  if (request.includes('image_describer')) {
    return '__mock_image_describer__';
  }
  return originalResolve.call(this, request, parent, ...rest);
};

// Register mock modules in the require cache
// Use a mutable delegate so tests can swap the kts_tool behavior at runtime
const _ktsToolDelegate = {
  fn: async function ktsTool(query, opts) {
    // Simulate a successful retrieval with 3 chunks
    return {
      status: 'ok',
      search_result: {
        context_chunks: [
          { content: '[EVIDENCE] doc1\nTo install ACME Tool v3.2, run `setup.exe /silent`.', doc_name: 'ACME Setup Guide v3.2' },
          { content: 'Known issue: ACME crashes on Windows 11 if .NET 6 is missing.', doc_name: 'ACME Known Issues Q4 2025' },
          { content: 'Release note: Fixed dashboard timeout in ACME v3.2.1 patch.', doc_name: 'ACME v3.2.1 Release Notes' },
        ],
        citations: [
          { doc_name: 'ACME Setup Guide v3.2', uri: 'file:///docs/acme_setup.pdf' },
          { doc_name: 'ACME Known Issues Q4 2025', uri: 'file:///docs/acme_ki.pdf' },
        ],
        confidence: 0.87,
        phase6: {
          trace: [
            { step: 'start', description: 'Begin' },
            { step: 'vector_search', description: 'Searched 1200 chunks', why: 'semantic match', elapsed_ms: 120 },
            { step: 'cross_encoder', description: 'Reranked top 20', elapsed_ms: 45 },
            { step: 'complete', description: 'Done' },
          ],
          iterations: 1,
          confidence: 0.87,
        },
      },
    };
  },
};

require.cache['__mock_kts_tool__'] = {
  id: '__mock_kts_tool__',
  filename: '__mock_kts_tool__',
  loaded: true,
  exports: async function (query, opts) { return _ktsToolDelegate.fn(query, opts); },
};

require.cache['__mock_image_describer__'] = {
  id: '__mock_image_describer__',
  filename: '__mock_image_describer__',
  loaded: true,
  exports: { autoDescribeImages: async () => ({}) },
};

// ── Now require the actual participant module ──────────────────────────────
const participantPath = path.resolve(__dirname, '..', 'extension', 'chat', 'participant.js');
const { registerChatParticipant, toMarkdown, selectPrompt, buildContextBlock, buildLegalContextBlock, KTS_SYSTEM_PROMPT, LEGAL_SYSTEM_PROMPT } = require(participantPath);

// ── Test infrastructure ────────────────────────────────────────────────────
let testsPassed = 0;
let testsFailed = 0;

function assert(condition, message) {
  if (!condition) {
    testsFailed++;
    console.error(`  FAIL: ${message}`);
  } else {
    testsPassed++;
    console.log(`  PASS: ${message}`);
  }
}

// ── Mock vscode object ─────────────────────────────────────────────────────
function createMockVscode({ modelAvailable = true, modelError = false } = {}) {
  const capturedMessages = [];
  const streamedOutput = [];

  const mockModel = {
    id: 'gpt-4o-test',
    family: 'gpt-4o',
    sendRequest: async (messages, opts, token) => {
      capturedMessages.push(...messages);
      if (modelError) {
        throw new Error('Model quota exceeded');
      }
      return {
        text: (async function* () {
          yield 'To install ACME Tool v3.2, ';
          yield 'run the setup wizard ';
          yield 'with the `/silent` flag.';
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
      workspace: {
        getConfiguration: () => ({ get: () => '' }),
      },
    },
    _mockModel: mockModel,
    capturedMessages,
    streamedOutput,
    mockModel,
    stream: {
      markdown: (text) => streamedOutput.push(text),
    },
    token: { isCancellationRequested: false },
  };
}

// ── Tests ───────────────────────────────────────────────────────────────────

async function testSystemPromptContent() {
  console.log('\n── Test: System prompt contains correct KTS persona ──');

  const { vscode, capturedMessages, stream, token } = createMockVscode();

  // We need to call registerChatParticipant and invoke the handler
  let handler;
  vscode.chat.createChatParticipant = (id, h) => {
    handler = h;
    return { id, dispose: () => {} };
  };

  const shared = {
    workspaceRoot: 'C:\\test',
    outputChannel: { appendLine: () => {} },
  };
  const context = { subscriptions: [] };

  registerChatParticipant(vscode, context, shared);
  assert(typeof handler === 'function', 'Chat handler was registered');

  // Invoke the handler with the user's selected model on request.model
  const request = { prompt: 'How do I install ACME Tool?', command: undefined, model: vscode._mockModel };
  await handler(request, {}, stream, token);

  // System prompt is embedded in the single User message (vscode LM API has no System method)
  const userMsg = capturedMessages.find(m => m.role === 'user');
  assert(!!userMsg, 'User message was sent to LLM');
  assert(userMsg.content.includes('technical support assistant'), 'Prompt mentions technical support assistant');
  assert(userMsg.content.includes('troubleshooting'), 'Prompt mentions troubleshooting');
  assert(userMsg.content.includes('GSF IR'), 'Prompt mentions GSF IR');
  assert(userMsg.content.includes('Global Structured Finance Investor Reporting'), 'Prompt expands GSF IR');
  assert(userMsg.content.includes('knowledge source'), 'Prompt mentions knowledge source');
  assert(userMsg.content.includes('No documented solution'), 'Prompt has no-match fallback text');
  assert(userMsg.content.includes('Do not invent'), 'Prompt has no-fabrication rule');
  assert(userMsg.content.includes('Do not reference external'), 'Prompt forbids external sources');
  assert(userMsg.content.includes('Matched Error Title'), 'Prompt has structured output format');
  assert(userMsg.content.includes('Suggested Solution'), 'Prompt asks for solution');
  assert(!userMsg.content.includes('structured-finance documentation'), 'Non-legal prompt does NOT say structured-finance documentation');
  assert(!userMsg.content.includes('Capitalized Terms'), 'Non-legal prompt does NOT mention Capitalized Terms');
}

async function testUserMessageContainsContextAndQuery() {
  console.log('\n── Test: User message contains retrieved context + query ──');

  const { vscode, capturedMessages, stream, token, mockModel } = createMockVscode();

  let handler;
  vscode.chat.createChatParticipant = (id, h) => { handler = h; return { id, dispose: () => {} }; };

  registerChatParticipant(vscode, { subscriptions: [] }, {
    workspaceRoot: 'C:\\test',
    outputChannel: { appendLine: () => {} },
  });

  await handler({ prompt: 'How do I install ACME Tool?', model: mockModel }, {}, stream, token);

  const userMsg = capturedMessages.find(m => m.role === 'user');
  assert(!!userMsg, 'User message was sent to LLM');
  assert(userMsg.content.includes('## Retrieved Context'), 'User message has Retrieved Context header');
  assert(userMsg.content.includes('## User Question'), 'User message has User Question header');
  assert(userMsg.content.includes('How do I install ACME Tool?'), 'User message contains original query');
  assert(userMsg.content.includes('[Source 1: ACME Setup Guide v3.2]'), 'Context has labeled source 1');
  assert(userMsg.content.includes('[Source 2: ACME Known Issues Q4 2025]'), 'Context has labeled source 2');
  assert(userMsg.content.includes('setup.exe /silent'), 'Context includes chunk content');
  assert(!userMsg.content.includes('[EVIDENCE]'), '[EVIDENCE] metadata was stripped');
}

async function testStreamingGeneration() {
  console.log('\n── Test: LLM response is streamed into chat ──');

  const { vscode, streamedOutput, stream, token, mockModel } = createMockVscode();

  let handler;
  vscode.chat.createChatParticipant = (id, h) => { handler = h; return { id, dispose: () => {} }; };

  registerChatParticipant(vscode, { subscriptions: [] }, {
    workspaceRoot: 'C:\\test',
    outputChannel: { appendLine: () => {} },
  });

  await handler({ prompt: 'How do I install ACME Tool?', model: mockModel }, {}, stream, token);

  const fullOutput = streamedOutput.join('');
  assert(fullOutput.includes('To install ACME Tool v3.2,'), 'Streamed output contains LLM answer');
  assert(fullOutput.includes('/silent'), 'Streamed output contains full answer');
  assert(fullOutput.includes('### Sources'), 'Citations appended after answer');
  assert(fullOutput.includes('ACME Setup Guide v3.2'), 'Citation includes source name');
  assert(fullOutput.includes('---'), 'Separator between answer and metadata');
}

async function testTraceAppended() {
  console.log('\n── Test: Agent reasoning trace is appended ──');

  const { vscode, streamedOutput, stream, token, mockModel } = createMockVscode();

  let handler;
  vscode.chat.createChatParticipant = (id, h) => { handler = h; return { id, dispose: () => {} }; };

  registerChatParticipant(vscode, { subscriptions: [] }, {
    workspaceRoot: 'C:\\test',
    outputChannel: { appendLine: () => {} },
  });

  await handler({ prompt: 'ACME crash on startup', model: mockModel }, {}, stream, token);

  const fullOutput = streamedOutput.join('');
  assert(fullOutput.includes('### Agent Reasoning'), 'Trace section present');
  assert(fullOutput.includes('vector_search'), 'Trace includes vector_search step');
  assert(fullOutput.includes('cross_encoder'), 'Trace includes cross_encoder step');
  assert(!fullOutput.includes('**start**'), 'Trace excludes start step');
  assert(!fullOutput.includes('**complete**'), 'Trace excludes complete step');
}

async function testFallbackWhenNoModel() {
  console.log('\n── Test: Falls back to raw chunks when no LLM model ──');

  const { vscode, streamedOutput, stream, token } = createMockVscode({ modelAvailable: false });
  const logs = [];

  let handler;
  vscode.chat.createChatParticipant = (id, h) => { handler = h; return { id, dispose: () => {} }; };

  registerChatParticipant(vscode, { subscriptions: [] }, {
    workspaceRoot: 'C:\\test',
    outputChannel: { appendLine: (msg) => logs.push(msg) },
  });

  await handler({ prompt: 'How do I install ACME Tool?' }, {}, stream, token);

  const fullOutput = streamedOutput.join('');
  assert(fullOutput.includes('Context 1'), 'Fallback shows raw Context 1');
  assert(fullOutput.includes('Context 2'), 'Fallback shows raw Context 2');
  assert(fullOutput.includes('### Citations'), 'Fallback shows Citations header');
  assert(!fullOutput.includes('### Sources'), 'Fallback does NOT show Sources (RAG) header');
  assert(logs.some(l => l.includes('No LLM model available')), 'Logged fallback reason');
}

async function testFallbackOnLLMError() {
  console.log('\n── Test: Falls back to raw chunks when LLM throws error ──');

  const { vscode, streamedOutput, stream, token } = createMockVscode({ modelAvailable: true, modelError: true });

  let handler;
  vscode.chat.createChatParticipant = (id, h) => { handler = h; return { id, dispose: () => {} }; };

  registerChatParticipant(vscode, { subscriptions: [] }, {
    workspaceRoot: 'C:\\test',
    outputChannel: { appendLine: () => {} },
  });

  await handler({ prompt: 'Dashboard timeout error' }, {}, stream, token);

  const fullOutput = streamedOutput.join('');
  assert(fullOutput.includes('Context 1'), 'Falls back to raw chunks on LLM error');
  assert(fullOutput.includes('### Citations'), 'Shows Citations header in fallback');
}

async function testToMarkdownStillWorks() {
  console.log('\n── Test: toMarkdown() pure function still works ──');

  const result = {
    status: 'ok',
    search_result: {
      context_chunks: [
        { content: 'Step 1: Download installer', doc_name: 'Guide' },
      ],
      citations: [{ doc_name: 'Guide', uri: 'file:///guide.pdf' }],
      confidence: 0.92,
    },
  };

  const md = toMarkdown(result);
  assert(md.includes('confidence: 0.92'), 'toMarkdown shows confidence');
  assert(md.includes('Step 1: Download installer'), 'toMarkdown shows chunk content');
  assert(md.includes('Guide'), 'toMarkdown shows citation');

  // Error case
  const errMd = toMarkdown({ status: 'error', error: 'Backend crashed' });
  assert(errMd.includes('Backend crashed'), 'toMarkdown shows error message');

  // Empty chunks
  const emptyMd = toMarkdown({ status: 'ok', search_result: { context_chunks: [] } });
  assert(emptyMd.includes('No matching KTS context'), 'toMarkdown handles empty chunks');
}

async function testRequestModelHonored() {
  console.log('\n── Test: request.model (user-selected) is used over auto-select ──');

  const capturedMessages = [];
  const streamedOutput = [];
  const userSelectedModel = {
    id: 'claude-3.5-sonnet-user-picked',
    family: 'claude-3.5-sonnet',
    sendRequest: async (messages, opts, token) => {
      capturedMessages.push(...messages);
      return {
        text: (async function* () { yield 'Answer from Claude.'; })(),
      };
    },
  };

  // selectChatModels should NOT be called if request.model is present
  let selectCalled = false;
  const vscode = {
    lm: {
      selectChatModels: async () => { selectCalled = true; return []; },
    },
    chat: { createChatParticipant: (id, h) => { handler = h; return { id, dispose: () => {} }; } },
    LanguageModelChatMessage: { User: (text) => ({ role: 'user', content: text }) },
    workspace: { getConfiguration: () => ({ get: () => '' }) },
  };

  let handler;
  const logs = [];
  registerChatParticipant(vscode, { subscriptions: [] }, {
    workspaceRoot: 'C:\\test',
    outputChannel: { appendLine: (msg) => logs.push(msg) },
  });

  const stream = { markdown: (t) => streamedOutput.push(t) };
  const token = { isCancellationRequested: false };

  await handler({ prompt: 'ACME crash', model: userSelectedModel }, {}, stream, token);

  const fullOutput = streamedOutput.join('');
  assert(fullOutput.includes('Answer from Claude'), 'User-selected model was used for generation');
  assert(!selectCalled, 'selectChatModels was NOT called when request.model exists');
  assert(logs.some(l => l.includes('claude-3.5-sonnet-user-picked')), 'Log shows user-selected model id');
}

// ── Dual-Prompt Tests ───────────────────────────────────────────────────────

async function testSelectPromptKtsDefault() {
  console.log('\n── Test: selectPrompt returns KTS for non-legal chunks ──');

  const result = {
    search_result: {
      context_chunks: [
        { content: 'ACME install guide', doc_name: 'Guide', doc_type: 'USER_GUIDE' },
        { content: 'Troubleshooting FAQ', doc_name: 'FAQ', doc_type: 'TROUBLESHOOT' },
        { content: 'Release note v3', doc_name: 'RN', doc_type: 'RELEASE_NOTE' },
      ],
    },
  };

  const { prompt, mode } = selectPrompt(result);
  assert(mode === 'kts', 'Mode is kts for non-legal chunks');
  assert(prompt === KTS_SYSTEM_PROMPT, 'KTS prompt selected');
  assert(prompt.includes('technical support assistant'), 'KTS prompt content correct');
}

async function testSelectPromptLegalMajority() {
  console.log('\n── Test: selectPrompt returns Legal when majority is GOVERNING_DOC ──');

  const result = {
    search_result: {
      context_chunks: [
        { content: 'PSA Section 2.03', doc_name: 'PSA_2006HE1.pdf', doc_type: 'GOVERNING_DOC' },
        { content: 'Indenture Article IV', doc_name: 'Indenture.pdf', doc_type: 'GOVERNING_DOC' },
        { content: 'Servicing agreement', doc_name: 'ServicingAgreement.pdf', doc_type: 'GOVERNING_DOC' },
        { content: 'Release note v1', doc_name: 'RN.pdf', doc_type: 'RELEASE_NOTE' },
      ],
    },
  };

  const { prompt, mode } = selectPrompt(result);
  assert(mode === 'legal', 'Mode is legal when 3/4 chunks are GOVERNING_DOC');
  assert(prompt === LEGAL_SYSTEM_PROMPT, 'Legal prompt selected');
  assert(prompt.includes('structured-finance documentation'), 'Legal prompt content correct');
  assert(prompt.includes('Capitalized Terms'), 'Legal prompt mentions definition chains');
}

async function testSelectPromptMixedTieBreaks() {
  console.log('\n── Test: selectPrompt tie-breaks to KTS at exactly 50% ──');

  const result = {
    search_result: {
      context_chunks: [
        { content: 'PSA excerpt', doc_name: 'PSA.pdf', doc_type: 'GOVERNING_DOC' },
        { content: 'User guide', doc_name: 'Guide.pdf', doc_type: 'USER_GUIDE' },
      ],
    },
  };

  const { mode } = selectPrompt(result);
  assert(mode === 'kts', '50/50 tie-breaks to KTS (requires >50% for legal)');
}

async function testSelectPromptNoDocType() {
  console.log('\n── Test: selectPrompt defaults to KTS when doc_type is missing ──');

  const result = {
    search_result: {
      context_chunks: [
        { content: 'Some chunk', doc_name: 'Doc1.pdf' },
        { content: 'Another chunk', doc_name: 'Doc2.pdf' },
      ],
    },
  };

  const { mode } = selectPrompt(result);
  assert(mode === 'kts', 'Defaults to KTS when doc_type is absent');
}

async function testBuildLegalContextBlockFormat() {
  console.log('\n── Test: buildLegalContextBlock formats with Document/Section/Page ──');

  const result = {
    search_result: {
      context_chunks: [
        { content: 'Distribution Date means...', doc_name: 'PSA_2006HE1.pdf', doc_id: 'psa001', section: '2.03', page: 15 },
        { content: 'Servicer shall...', doc_name: 'ServicingAgreement.pdf', doc_id: 'sa001' },
      ],
      citations: [
        { doc_id: 'sa001', doc_name: 'ServicingAgreement.pdf', section: 'Article IV', page: 42 },
      ],
    },
  };

  const block = buildLegalContextBlock(result);
  assert(block.includes('[Document: PSA_2006HE1.pdf, Section: 2.03, Page: 15]'), 'Chunk-level section and page in label');
  assert(block.includes('Distribution Date means'), 'Chunk content preserved');
  assert(block.includes('[Document: ServicingAgreement.pdf, Section: Article IV, Page: 42]'), 'Citation-level section and page used as fallback');
  assert(block.includes('Servicer shall'), 'Second chunk content preserved');
  assert(!block.includes('[Source'), 'Legal block does NOT use [Source N:] format');
}

async function testBuildContextBlockFormat() {
  console.log('\n── Test: buildContextBlock uses [Source N:] format ──');

  const result = {
    search_result: {
      context_chunks: [
        { content: '[EVIDENCE] doc1\nInstall ACME', doc_name: 'Guide.pdf' },
        { content: 'Known issue XYZ', doc_name: 'KnownIssues.pdf' },
      ],
    },
  };

  const block = buildContextBlock(result);
  assert(block.includes('[Source 1: Guide.pdf]'), 'Source 1 label present');
  assert(block.includes('[Source 2: KnownIssues.pdf]'), 'Source 2 label present');
  assert(block.includes('Install ACME'), 'Content preserved');
  assert(!block.includes('[EVIDENCE]'), 'EVIDENCE prefix stripped');
  assert(!block.includes('[Document:'), 'KTS block does NOT use [Document:] format');
}

async function testLegalPromptUsedInGeneration() {
  console.log('\n── Test: Legal prompt is used when chunks are GOVERNING_DOC ──');

  // Swap kts_tool to return legal chunks via the mutable delegate
  const origFn = _ktsToolDelegate.fn;
  _ktsToolDelegate.fn = async function () {
    return {
      status: 'ok',
      search_result: {
        context_chunks: [
          { content: 'Distribution Date means the 25th day of each month.', doc_name: 'PSA_2006HE1.pdf', doc_type: 'GOVERNING_DOC', section: '2.03', page: 15 },
          { content: 'Certificate Balance shall be reduced by...', doc_name: 'PSA_2006HE1.pdf', doc_type: 'GOVERNING_DOC', section: '5.01', page: 45 },
          { content: 'Servicer shall remit collections...', doc_name: 'ServicingAgreement.pdf', doc_type: 'GOVERNING_DOC', section: 'Art IV', page: 30 },
        ],
        citations: [
          { doc_name: 'PSA_2006HE1.pdf', uri: 'file:///docs/psa.pdf', section: '2.03', page: 15 },
        ],
        confidence: 0.91,
        phase6: { trace: [], iterations: 1, confidence: 0.91 },
      },
    };
  };

  const capturedMessages = [];
  const streamedOutput = [];
  const mockModel = {
    id: 'gpt-4o-test',
    sendRequest: async (messages) => {
      capturedMessages.push(...messages);
      return { text: (async function* () { yield 'The Distribution Date is defined as...'; })() };
    },
  };

  const vscode = {
    lm: { selectChatModels: async () => [mockModel] },
    chat: { createChatParticipant: (id, h) => { handler = h; return { id, dispose: () => {} }; } },
    LanguageModelChatMessage: { User: (text) => ({ role: 'user', content: text }) },
    workspace: { getConfiguration: () => ({ get: () => '' }) },
  };

  let handler;
  registerChatParticipant(vscode, { subscriptions: [] }, {
    workspaceRoot: 'C:\\test',
    outputChannel: { appendLine: () => {} },
  });

  const stream = { markdown: (t) => streamedOutput.push(t) };
  await handler({ prompt: 'What is the Distribution Date?', model: mockModel }, {}, stream, { isCancellationRequested: false });

  const userMsg = capturedMessages.find(m => m.role === 'user');
  assert(!!userMsg, 'User message sent to LLM');
  assert(userMsg.content.includes('structured-finance documentation'), 'Legal prompt was used');
  assert(userMsg.content.includes('Capitalized Terms'), 'Legal prompt includes definition chain guidance');
  assert(userMsg.content.includes('[Document: PSA_2006HE1.pdf, Section: 2.03, Page: 15]'), 'Legal context block format used');
  assert(!userMsg.content.includes('[Source 1:'), 'Legal mode does NOT use [Source N:] format');

  const fullOutput = streamedOutput.join('');
  assert(fullOutput.includes('Legal Analyst'), 'Mode indicator shows Legal Analyst');
  assert(fullOutput.includes('The Distribution Date is defined as'), 'LLM answer streamed');

  // Restore original delegate
  _ktsToolDelegate.fn = origFn;
}

async function testModeIndicatorInOutput() {
  console.log('\n── Test: Mode indicator is prepended to LLM answer ──');

  const { vscode, streamedOutput, stream, token, mockModel } = createMockVscode();

  let handler;
  vscode.chat.createChatParticipant = (id, h) => { handler = h; return { id, dispose: () => {} }; };

  registerChatParticipant(vscode, { subscriptions: [] }, {
    workspaceRoot: 'C:\\test',
    outputChannel: { appendLine: () => {} },
  });

  await handler({ prompt: 'How do I install ACME Tool?', model: mockModel }, {}, stream, token);

  const fullOutput = streamedOutput.join('');
  assert(fullOutput.includes('*[KTS Support mode]*'), 'KTS mode indicator shown for non-legal chunks');
}

// ── Runner ──────────────────────────────────────────────────────────────────
async function main() {
  console.log('=== KTS RAG Generation Smoke Tests ===\n');

  await testSystemPromptContent();
  await testUserMessageContainsContextAndQuery();
  await testStreamingGeneration();
  await testTraceAppended();
  await testFallbackWhenNoModel();
  await testFallbackOnLLMError();
  await testToMarkdownStillWorks();
  await testRequestModelHonored();

  // Dual-prompt tests
  await testSelectPromptKtsDefault();
  await testSelectPromptLegalMajority();
  await testSelectPromptMixedTieBreaks();
  await testSelectPromptNoDocType();
  await testBuildLegalContextBlockFormat();
  await testBuildContextBlockFormat();
  await testLegalPromptUsedInGeneration();
  await testModeIndicatorInOutput();

  console.log(`\n${'='.repeat(50)}`);
  console.log(`Results: ${testsPassed} passed, ${testsFailed} failed`);
  console.log('='.repeat(50));

  if (testsFailed > 0) {
    process.exit(1);
  }
}

main().catch(err => {
  console.error('Test runner crashed:', err);
  process.exit(1);
});
