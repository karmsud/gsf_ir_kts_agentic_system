/**
 * Golden Answer Test Runner
 *
 * Runs each question from golden_answer_tests.json through the full KTS
 * RAG pipeline (ktsTool → backend search → LLM generation → post-processing)
 * and captures the resulting answer text, chunks, and metadata.
 *
 * Usage: Register as `kts.runGoldenTests` command in extension.js then:
 *   Cmd+Shift+P → "KTS: Run Golden Tests"
 *
 * Or require directly:
 *   const { runGoldenTests } = require('./tests/golden_answer_runner');
 */
const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function loadTests() {
  const testsPath = path.join(__dirname, 'golden_answer_tests.json');
  return JSON.parse(fs.readFileSync(testsPath, 'utf-8'));
}

function ensureDir(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

// ---------------------------------------------------------------------------
// Single-test execution
// ---------------------------------------------------------------------------

/**
 * Run one golden test through the KTS chat participant pipeline.
 *
 * @param {object} vscode  - The vscode API object
 * @param {object} test    - One element from golden_answer_tests.json
 * @param {object} opts    - { outputChannel, shared }
 * @returns {object}       - { test_id, actual_answer, chunks_used, ... }
 */
async function runSingleTest(vscode, test, { outputChannel, shared, sourcePath }) {
  const start = Date.now();

  // Dynamically require ktsTool & participant helpers
  const ktsTool = require('../extension/copilot/kts_tool');
  const {
    selectModel,
    computeTokenBudget,
    computeMaxChunks,
    trimContextToTokenBudget,
    buildKnowledgePreamble,
    RAG_CONFIG,
  } = require('../extension/chat/participant');

  // Build query — for follow-ups prepend prior_context
  let query = test.question;
  if (test.prior_context) {
    query = `Context from prior conversation: ${test.prior_context}\n\nUser follow-up: ${test.question}`;
  }

  // Determine maxResults from command
  const isDeep = test.command === 'deep';
  const maxResults = isDeep ? RAG_CONFIG.maxContextChunks : Math.floor(RAG_CONFIG.maxContextChunks / 2);

  // Source path is passed explicitly from the command handler (folder picker).
  // It is never read from global config inside the runner.
  if (!sourcePath) {
    throw new Error('No source path provided to runSingleTest. The command handler must pass shared.testSourcePath.');
  }
  const workspaceRoot = shared?.workspaceRoot || path.resolve(__dirname, '..');

  // Call backend search / retrieval
  let result;
  try {
    result = await ktsTool(query, {
      workspaceRoot,
      sourcePath,
      maxResults,
      deepMode: isDeep,
    });
  } catch (err) {
    return {
      test_id: test.test_id,
      category: test.category,
      question: test.question,
      actual_answer: `[ERROR] Backend search failed: ${err.message}`,
      chunks_used: 0,
      chunk_sources: [],
      answer_length: 0,
      elapsed_ms: Date.now() - start,
      metadata: { error: err.message },
    };
  }

  // Extract context chunks for insight
  let search = result?.search_result;
  if (search && search.search_result && typeof search.search_result === 'object') {
    search = search.search_result;
  }
  const chunks = (search && Array.isArray(search.context_chunks))
    ? search.context_chunks
    : (search && Array.isArray(search.results) ? search.results : []);

  // Build citation lookup: doc_id → { section, page, doc_name }
  const citations = (search && Array.isArray(search.citations)) ? search.citations : [];
  const citationMap = {};
  for (const cit of citations) {
    const key = cit.doc_id || cit.doc_name;
    if (key && !citationMap[key]) citationMap[key] = cit;
  }

  // Generate answer via LLM
  let answerText = '';
  let modelId = 'none';
  try {
    const model = await selectModel(vscode, null);
    if (model) {
      modelId = model.id || model.family || 'unknown';
      const tokenBudget = computeTokenBudget(model);
      const maxChunks = computeMaxChunks(tokenBudget);

      // Build context block (mirrors buildLegalContextBlock from participant.js)
      const contextBlocks = chunks.slice(0, maxChunks).map((c, i) => {
        const body = (c.content || '').replace(/^\[EVIDENCE\][^\n]*\n?/, '').trim();

        // Resolve document name: doc_name → source_path filename → doc_id
        let docName = c.doc_name || '';
        if (!docName && c.source_path) {
          const parts = c.source_path.replace(/\\/g, '/').split('/');
          docName = parts[parts.length - 1] || '';
        }
        if (!docName) docName = c.doc_id || `source-${i + 1}`;

        // Cross-reference citation for section/page
        const cit = citationMap[c.doc_id] || citationMap[c.doc_name] || {};
        const section = c.section || cit.section || null;
        const page = c.page ?? cit.page ?? null;

        let label = `[Document: ${docName}`;
        if (section) label += `, Section: ${section}`;
        if (page !== null && page !== undefined) label += `, Page: ${page}`;
        label += ']';

        return `${label}\n${body}`;
      });
      // Phase 8.3-style token-aware trimming (matches generateAnswer)
      const rawBlocks = contextBlocks.map(text => ({ text }));
      const trimmedBlocks = trimContextToTokenBudget(rawBlocks, tokenBudget);
      const contextText = trimmedBlocks.map(b => b.text).join('\n\n');

      // Build shared knowledge preamble (glossary + entity roles — sent once)
      const preamble = buildKnowledgePreamble(result);

      // Use the same LEGAL_SYSTEM_PROMPT as the real extension
      const systemPrompt = [
        'You are Analyst — a precise, cautious structured-finance documentation assistant.',
        'Answer the user\'s question using ONLY the retrieved document excerpts below.',
        '',
        'Rules:',
        '- Provide a direct, document-grounded answer in a professional conversational tone.',
        '- When quoting, cite the document name and section/page naturally in your prose.',
        '- Capitalized Terms are defined terms. When the answer depends on one, trace the',
        '  definition chain: Term → definition → nested terms → their definitions.',
        '- If language is ambiguous or silent, say so and quote the relevant text.',
        '- If documents conflict, present both citations without resolving the conflict',
        '  unless the documents include a priority rule.',
        '- Do not invent rules, assumptions, or interpretations beyond what is stated.',
        '- Do not use general knowledge, external sources, or other deals\' documents.',
        '- If the retrieved context does not contain an answer, say so explicitly.',
      ].join('\n');
      const userMessageParts = [
        preamble,
        preamble ? '' : null,
        `## Retrieved Context`,
        contextText,
        '',
        `## Question`,
        query,
      ].filter(p => p !== null);
      const userMessage = userMessageParts.join('\n');

      const messages = [
        vscode.LanguageModelChatMessage.User(`${systemPrompt}\n\n${userMessage}`),
      ];

      const resp = await model.sendRequest(messages, {}, new vscode.CancellationTokenSource().token);
      for await (const part of resp.text) {
        answerText += part;
      }
    } else {
      answerText = '[NO MODEL] No LLM model available during golden test run.';
    }
  } catch (genErr) {
    answerText = `[GENERATION ERROR] ${genErr.message}`;
  }

  const elapsed = Date.now() - start;

  return {
    test_id: test.test_id,
    category: test.category,
    question: test.question,
    actual_answer: answerText,
    chunks_used: chunks.length,
    chunk_sources: chunks.slice(0, 20).map(c => {
      const cit = citationMap[c.doc_id] || citationMap[c.doc_name] || {};
      let docName = c.doc_name || '';
      if (!docName && c.source_path) {
        const parts = c.source_path.replace(/\\/g, '/').split('/');
        docName = parts[parts.length - 1] || '';
      }
      return {
        doc: docName || c.doc_id || '',
        section: c.section || cit.section || '',
        score: c.score ?? c.relevance_score ?? cit.score ?? null,
        doc_type: c.doc_type || '',
      };
    }),
    answer_length: answerText.length,
    elapsed_ms: elapsed,
    metadata: {
      model: modelId,
      deep_mode: isDeep,
      prior_context: test.prior_context || null,
    },
  };
}

// ---------------------------------------------------------------------------
// Full suite runner
// ---------------------------------------------------------------------------

/**
 * Run all golden answer tests and save results to disk.
 *
 * @param {object} vscode         - The vscode API
 * @param {object} outputChannel  - VS Code OutputChannel for progress
 * @param {object} shared         - Extension shared context { workspaceRoot, ... }
 * @returns {object[]}            - Array of per-test result objects
 */
async function runGoldenTests(vscode, outputChannel, shared) {
  const testSourcePath = shared.testSourcePath;
  if (!testSourcePath) {
    throw new Error('runGoldenTests: shared.testSourcePath is required. The command handler must provide it via folder picker.');
  }

  const tests = loadTests();
  const results = [];
  const startTime = Date.now();

  outputChannel.appendLine(`\n=== Golden Answer Tests: ${tests.length} questions ===\n`);

  for (let i = 0; i < tests.length; i++) {
    const test = tests[i];
    outputChannel.appendLine(`[${i + 1}/${tests.length}] ${test.test_id}: ${test.question}`);

    const result = await runSingleTest(vscode, test, { outputChannel, shared, sourcePath: testSourcePath });
    results.push(result);

    const preview = result.actual_answer.substring(0, 80).replace(/\n/g, ' ');
    outputChannel.appendLine(
      `  → ${result.answer_length} chars, ${result.chunks_used} chunks, ${result.elapsed_ms}ms`
    );
    outputChannel.appendLine(`  → ${preview}...`);
  }

  const totalElapsed = Date.now() - startTime;

  // Save results
  const resultsDir = path.join(__dirname, 'golden_answer_results');
  ensureDir(resultsDir);

  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const outputPath = path.join(resultsDir, `${timestamp}_results.json`);

  const output = {
    timestamp: new Date().toISOString(),
    total_tests: tests.length,
    total_elapsed_ms: totalElapsed,
    avg_elapsed_ms: Math.round(totalElapsed / tests.length),
    results,
  };

  fs.writeFileSync(outputPath, JSON.stringify(output, null, 2));

  outputChannel.appendLine(`\n=== Complete: ${tests.length} tests in ${(totalElapsed / 1000).toFixed(1)}s ===`);
  outputChannel.appendLine(`Results saved to ${outputPath}`);

  return results;
}

module.exports = { runGoldenTests, runSingleTest, loadTests };
