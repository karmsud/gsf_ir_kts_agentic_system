/**
 * Phase 9.2 — Critique Client (JavaScript side)
 *
 * Thin wrapper that selects the fixed critique model via VS Code LM API,
 * calls the backend critique loop, streams progress to the chat UI,
 * and handles critique-model unavailability gracefully.
 *
 * The heavy logic lives in Python (critique_loop.py).  This JS module
 * is responsible only for model selection, streaming, and error handling.
 */

const vscode = require('vscode');

// ── Model selection ──────────────────────────────────────────────

/**
 * Attempt to select a fixed low-cost model for critique evaluation.
 * Tries a preference chain: gpt-4.1 → gpt-4o → gpt-4o-mini → any.
 *
 * @returns {Promise<import('vscode').LanguageModelChat | null>}
 */
async function selectCritiqueModel() {
  const preferred = ['gpt-4.1', 'gpt-4o', 'gpt-4o-mini'];

  for (const family of preferred) {
    try {
      const models = await vscode.lm.selectChatModels({
        vendor: 'copilot',
        family,
      });
      if (models.length > 0) {
        return models[0];
      }
    } catch {
      // Model unavailable — try next
    }
  }

  // Fallback: any available copilot model
  try {
    const any = await vscode.lm.selectChatModels({ vendor: 'copilot' });
    return any.length > 0 ? any[0] : null;
  } catch {
    return null;
  }
}

// ── Safety keyword constants (mirrors Python SAFETY_KEYWORDS) ────

const SAFETY_KEYWORDS = {
  'CAUTION': 'CAUTION annotation',
  'WARNING': 'WARNING annotation',
  '\u26a0': 'warning symbol',
  'NOTE:': 'NOTE callout',
  'IMPORTANT:': 'IMPORTANT callout',
  'DO NOT': 'prohibition statement',
  'MUST NOT': 'prohibition statement',
};

// ── Deterministic helpers ────────────────────────────────────────

/**
 * Deterministic keyword safety check — zero LLM cost.
 * If source has a safety keyword but the answer doesn't, it's a gap.
 * @param {string} answer
 * @param {Array} chunks
 * @returns {Array<{pass: boolean, gap_description: string, source: string}>}
 */
function keywordSafetyCheck(answer, chunks) {
  const sourceText = (chunks || [])
    .map(c => c.content || c.text || '')
    .join(' ');
  const missing = [];
  for (const [keyword, label] of Object.entries(SAFETY_KEYWORDS)) {
    if (sourceText.includes(keyword) && !answer.includes(keyword)) {
      missing.push({
        pass: false,
        gap_description: `Source contains ${label} ('${keyword}') but the answer does not include it.`,
        source: 'keyword_safety_net',
      });
    }
  }
  return missing;
}

/**
 * Deterministic trigger pre-filter — zero LLM cost.
 * @param {object} question   Question with trigger_keywords + trigger_logic
 * @param {Array}  chunks     Retrieved chunks
 * @returns {boolean}
 */
function triggerMatches(question, chunks) {
  if (question.trigger_logic === 'always') return true;
  const allText = (chunks || [])
    .map(c => (c.content || c.text || '').toLowerCase())
    .join(' ');
  const keywords = (question.trigger_keywords || []).map(k => k.toLowerCase());
  if (keywords.length === 0) return false;
  if (question.trigger_logic === 'any_in_source') {
    return keywords.some(kw => allText.includes(kw));
  }
  if (question.trigger_logic === 'all_in_source') {
    return keywords.every(kw => allText.includes(kw));
  }
  return false;
}

// ── LLM call helper ──────────────────────────────────────────────

/**
 * Send a prompt to a VS Code LM model and return the text response.
 * @param {import('vscode').LanguageModelChat} model
 * @param {string} prompt
 * @param {import('vscode').CancellationToken} token
 * @returns {Promise<string>}
 */
async function _callModel(model, prompt, token) {
  const messages = [vscode.LanguageModelChatMessage.User(prompt)];
  const response = await model.sendRequest(messages, {}, token);
  let text = '';
  for await (const chunk of response.text) {
    text += chunk;
  }
  return text.trim();
}

// ── Critique-loop driver ─────────────────────────────────────────

/**
 * Run the unified critique-driven Self-RAG loop.
 *
 * Algorithm:
 * 1. Keyword safety check (deterministic — zero LLM cost)
 * 2. For each critique question: binary evaluation via critiqueModel
 * 3. On gap: translate gap→query, re-RETRIEVE via retrieveFn, re-synthesize
 *    with (orig query + all accumulated chunks + previous answer)
 * 4. Restart critique from Q1 after each fix
 * 5. Repeat until all questions pass OR maxRounds exhausted
 * 6. Track best answer across all rounds via confidence scoring
 *
 * This replaces the old two-stage pipeline (Self-RAG then Critique)
 * with a single critique-driven loop that retrieves when needed.
 *
 * @param {object}  opts
 * @param {import('vscode').LanguageModelChat} opts.critiqueModel  Fixed critique model
 * @param {import('vscode').LanguageModelChat} opts.userModel      User's selected model
 * @param {import('vscode').ChatResponseStream} opts.stream        Chat response stream
 * @param {import('vscode').CancellationToken}  opts.token         Cancellation token
 * @param {string}  opts.query            Original user query
 * @param {string}  opts.initialAnswer    Initial LLM-generated answer
 * @param {object}  opts.result           Retrieval result from backend
 * @param {Array}   opts.questions        Loaded critique questions
 * @param {number}  [opts.maxRounds=3]    Maximum critique rounds
 * @param {boolean} [opts.restartOnGap=true] Restart from Q1 after each fix
 * @param {number}  [opts.confidenceExit=0.90] Confidence threshold for early exit
 * @param {Function} [opts.retrieveFn]    async (gapQuery, excludeIds) => {chunks, chunkIds}
 * @param {string}  [opts.systemPrompt]   System prompt for re-synthesis
 * @returns {Promise<{answer: string, trace: object} | null>}
 */
async function runCritiqueLoop(opts) {
  const {
    critiqueModel,
    userModel,
    stream,
    token,
    query,
    initialAnswer,
    result,
    questions,
    maxRounds = 3,
    restartOnGap = true,
    confidenceExit = 0.90,
    retrieveFn = null,
    systemPrompt = '',
  } = opts;

  if (!critiqueModel || !questions || questions.length === 0) {
    return null; // Nothing to critique
  }

  // Extract chunks from result
  let search = result?.search_result;
  if (search?.search_result && typeof search.search_result === 'object') {
    search = search.search_result;
  }
  const chunks = (search && Array.isArray(search.context_chunks))
    ? search.context_chunks
    : [];

  stream.progress('Evaluating answer quality...');

  // ── Answer tracker ───────────────────────────────────────────
  const history = [];
  const recordAnswer = (answer, confidence, round) => {
    history.push({ answer, confidence, round });
  };
  const getBest = () => {
    if (history.length === 0) return { answer: initialAnswer, confidence: 0.5, round: 0 };
    return history.reduce((a, b) => a.confidence >= b.confidence ? a : b);
  };

  // ── Confidence computation ───────────────────────────────────
  const computeConfidence = (evaluated, unfixed) => {
    if (evaluated === 0) return 0.5;
    const base = (evaluated - Math.max(unfixed, 0)) / evaluated;
    const penalty = 0.1 * Math.max(unfixed, 0);
    return Math.max(0, Math.min(1, base - penalty));
  };

  let currentAnswer = initialAnswer;
  let currentConfidence = 0.5;
  let totalEvaluated = 0;
  let totalGaps = 0;
  let totalFixed = 0;
  const reQueries = [];
  const seenChunkIds = new Set(chunks.map(c => c.id || '').filter(Boolean));
  const allChunks = [...chunks];

  recordAnswer(currentAnswer, currentConfidence, 0);

  // ── Step 1: Keyword safety check (round 1 only) ─────────────
  const safetyGaps = keywordSafetyCheck(currentAnswer, allChunks);

  const trace = {
    critiqueModel: critiqueModel.id || 'unknown',
    questionsLoaded: questions.length,
    maxRounds,
    safetyGapsFound: safetyGaps.length,
    questionsEvaluated: 0,
    gapsFound: 0,
    gapsFixed: 0,
    roundsExecuted: 0,
    converged: false,
    status: 'running',
  };

  try {
    for (let round = 1; round <= maxRounds; round++) {
      if (token.isCancellationRequested) break;
      trace.roundsExecuted = round;
      let gapFoundThisRound = false;

      stream.progress(`Evaluating answer quality (round ${round}/${maxRounds})...`);

      // Safety gaps (round 1 only)
      if (round === 1 && safetyGaps.length > 0) {
        for (const sgap of safetyGaps) {
          totalEvaluated++;
          totalGaps++;
          // Simple keyword-based re-query for safety gaps
          const reQ = sgap.gap_description.split("'").filter(s => s.length > 2 && s.length < 30)[0] || query;
          reQueries.push(reQ);
          // Re-synthesize to include the missing safety keyword
          if (userModel) {
            try {
              const resynthPrompt = `The following answer about "${query}" has a gap: ${sgap.gap_description}\n\nCurrent answer:\n${currentAnswer}\n\nPlease fix the answer to address this gap. Keep all existing correct content.`;
              currentAnswer = await _callModel(userModel, resynthPrompt, token);
              totalFixed++;
            } catch { /* keep current answer */ }
          }
          currentConfidence = computeConfidence(totalEvaluated, totalGaps - totalFixed);
          recordAnswer(currentAnswer, currentConfidence, round);
          if (restartOnGap) { gapFoundThisRound = true; break; }
        }
        if (gapFoundThisRound) continue;
      }

      // ── Step 2-3: Evaluate each critique question ────────────
      for (let i = 0; i < questions.length; i++) {
        if (token.isCancellationRequested) break;
        const question = questions[i];

        // Trigger pre-filter (deterministic)
        if (question.trigger_logic !== 'always') {
          if (!triggerMatches(question, allChunks)) continue;
        }

        // Early exit: high confidence + only tail questions remain
        if (currentConfidence >= confidenceExit) {
          const remaining = questions.slice(i);
          const allTail = remaining.every(
            q => (q._source_doc_chunk_count || 0) <= 1,
          );
          if (allTail) {
            trace.converged = true;
            trace.status = 'converged_early_exit';
            break;
          }
        }

        // Binary critique evaluation via critiqueModel
        totalEvaluated++;
        const critiquePrompt =
          `System: You are a document quality reviewer. Evaluate ONLY the specific question below. Do not evaluate anything else.\n\n` +
          `Question: ${question.question}\n\n` +
          `Answer under review:\n${currentAnswer}\n\n` +
          `Source content (retrieved chunks):\n${allChunks.map((c, idx) => `[Chunk ${idx + 1}] ${c.content || c.text || ''}`).join('\n\n')}\n\n` +
          `Instructions:\n- Answer the question with "pass" or "fail"\n- If "fail", describe the specific gap in 1-2 sentences\n- Be strict: if the answer is vague where the source is specific, fail\n\n` +
          `Output format (JSON only):\n{"pass": true}\nor\n{"pass": false, "gap_description": "The answer omits the CAUTION about..."}`;

        let verdict = { pass: true };
        try {
          let raw = await _callModel(critiqueModel, critiquePrompt, token);
          // Strip markdown code fences
          if (raw.startsWith('```')) raw = raw.split('\n').slice(1).join('\n');
          if (raw.endsWith('```')) raw = raw.slice(0, raw.lastIndexOf('```'));
          verdict = JSON.parse(raw.trim());
        } catch {
          // Optimistic: treat invalid response as pass
          verdict = { pass: true };
        }

        if (verdict.pass) continue;

        // ── Gap found — retrieve + re-synthesize ─────────────
        totalGaps++;
        const gapDesc = verdict.gap_description || 'Unknown gap';

        // Step 4a: Gap → query translation via critiqueModel
        let reQ = '';
        try {
          const gapToQueryPrompt =
            `System: Convert a gap description into a retrieval search query.\n\n` +
            `Gap found in answer: ${gapDesc}\nOriginal user question: ${query}\n\n` +
            `Generate a 5-10 word search query that targets the missing information.\nReturn ONLY the query string — no explanation, no formatting.`;
          reQ = await _callModel(critiqueModel, gapToQueryPrompt, token);
          // Validate: should be 3-15 words
          const wordCount = reQ.split(/\s+/).length;
          if (wordCount < 3 || wordCount > 15) {
            reQ = gapDesc.split(' ').filter(w => w.length > 5).slice(0, 8).join(' ') || query;
          }
        } catch {
          reQ = gapDesc.split(' ').filter(w => w.length > 5).slice(0, 8).join(' ') || query;
        }
        reQueries.push(reQ);

        // Step 4b: Re-RETRIEVE new chunks for the gap query
        let newChunkTexts = [];
        if (retrieveFn) {
          try {
            const retrieved = await retrieveFn(reQ, Array.from(seenChunkIds));
            if (retrieved && retrieved.chunks && retrieved.chunks.length > 0) {
              for (const c of retrieved.chunks) {
                const cid = c.id || c.chunk_id || '';
                if (cid && seenChunkIds.has(cid)) continue;
                allChunks.push(c);
                newChunkTexts.push(c.content || c.text || '');
                if (cid) seenChunkIds.add(cid);
              }
              trace.chunksRetrieved = (trace.chunksRetrieved || 0) + newChunkTexts.length;
            }
          } catch { /* retrieval failed — re-synth with existing context */ }
        }

        // Step 4c: Re-synthesize with ALL accumulated evidence
        if (userModel) {
          try {
            // Build context from all accumulated chunks
            const allCtxText = allChunks
              .map((c, idx) => `[Chunk ${idx + 1}] ${c.content || c.text || ''}`)
              .join('\n\n');

            const resynthPrompt = systemPrompt
              ? [
                  systemPrompt,
                  '',
                  '---',
                  '',
                  '## Retrieved Context',
                  allCtxText,
                  '',
                  newChunkTexts.length > 0
                    ? `## Newly Retrieved Evidence (for gap: ${gapDesc})\n${newChunkTexts.join('\n\n')}\n`
                    : '',
                  '## Previous Answer (has a gap)',
                  currentAnswer,
                  '',
                  `## Gap to Fix: ${gapDesc}`,
                  '',
                  '## User Question',
                  query,
                  '',
                  'Instructions: Produce a complete, improved answer that fixes the identified gap.',
                  'Do not remove correct existing content — only add, refine, and improve.',
                  'Maintain the same answer format and citation style.',
                ].join('\n')
              : `System: You are a document analyst. Integrate new context into an existing answer to fill a specific gap.\n\n` +
                `Original question: ${query}\n\n` +
                `Current answer (has a gap):\n${currentAnswer}\n\n` +
                `Gap identified: ${gapDesc}\n\n` +
                (newChunkTexts.length > 0
                  ? `New evidence retrieved:\n${newChunkTexts.join('\n\n')}\n\n`
                  : '') +
                `All available context:\n${allCtxText}\n\n` +
                `Instructions:\n1. Fix the identified gap using the new evidence and all available context\n2. Do not remove correct existing content — only add and refine\n3. Maintain the same answer format and citation style`;

            currentAnswer = await _callModel(userModel, resynthPrompt, token);
            totalFixed++;
          } catch { /* keep current answer */ }
        }

        currentConfidence = computeConfidence(totalEvaluated, totalGaps - totalFixed);
        recordAnswer(currentAnswer, currentConfidence, round);

        if (restartOnGap) {
          gapFoundThisRound = true;
          break; // restart from Q1
        }
      }

      if (!gapFoundThisRound) {
        trace.converged = true;
        trace.status = 'converged';
        break;
      }
    }
  } catch (err) {
    trace.status = `error: ${err.message || String(err)}`;
  }

  // Finalize trace
  trace.questionsEvaluated = totalEvaluated;
  trace.gapsFound = totalGaps;
  trace.gapsFixed = totalFixed;
  if (!trace.converged && trace.status === 'running') {
    trace.status = 'max_rounds_exhausted';
  }

  const best = getBest();
  stream.progress(
    `Critique complete: ${totalEvaluated} checks, ${totalGaps} gaps found, ${totalFixed} fixed (${trace.roundsExecuted} rounds)`,
  );

  return {
    answer: best.answer,
    trace,
  };
}

// ── Exports ──────────────────────────────────────────────────────

module.exports = {
  selectCritiqueModel,
  runCritiqueLoop,
  keywordSafetyCheck,
  triggerMatches,
  _callModel,
};
