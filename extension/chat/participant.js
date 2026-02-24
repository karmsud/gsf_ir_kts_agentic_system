const ktsTool = require('../copilot/kts_tool');
const { autoDescribeImages } = require('../lib/image_describer');
const { parseTwoLevelScope, parseCommandTokens, buildCliArgsFromTokens } = require('../lib/scope_discovery');
const { runCritiqueLoop } = require('../lib/critique_client');
// Phase 8.6: Multi-Query RAG Fusion
const { expandQueryWithLLM } = require('../lib/query_expander');

// ── Internal RAG Configuration ─────────────────────────────────────
// Tuned for GPT-4.1's 1M context window. Not exposed as user settings.
const RAG_CONFIG = {
  maxContextChunks: 100,
  multiQueryVariants: 2,
  critiqueEnabled: true,
  critiqueMaxRounds: 3,
  graphRagMaxIterations: 10,
  TOKEN_RATIO: 4,
  RESERVED_TOKENS: 5000,
};

/**
 * Compute token budget from model's context window (80% utilization).
 */
function computeTokenBudget(model) {
  const maxTokens = model.maxInputTokens || 128000;
  return Math.floor(maxTokens * 0.8);
}

/**
 * Compute max context chunks from token budget.
 */
function computeMaxChunks(tokenBudget) {
  return Math.min(200, Math.floor(tokenBudget * 0.6 / 500));
}

// ---------------------------------------------------------------------------
// Phase 11.1: #file / #selection / #editor Reference Extraction
// ---------------------------------------------------------------------------
/**
 * Parse VS Code Chat references (#file, #selection, #editor) from request.
 * Returns { referenceText, sourceDocHint } to enrich the query and retrieval.
 */
async function extractReferences(request) {
  const parts = [];
  let sourceDocHint = null;

  if (!request || !request.references || !Array.isArray(request.references)) {
    return { referenceText: '', sourceDocHint: null };
  }

  for (const ref of request.references) {
    try {
      if (ref.id === 'vscode.selection' || ref.id === 'copilot.selection') {
        // #selection — user highlighted text in editor
        const selectedText = ref.value?.selectedText
          || ref.value?.text
          || (typeof ref.value === 'string' ? ref.value : '');
        if (selectedText) {
          parts.push(`[Selected text]: ${selectedText}`);
        }
        if (ref.value?.uri?.fsPath) {
          sourceDocHint = ref.value.uri.fsPath;
        }
      } else if (ref.id === 'vscode.file' || ref.id === 'copilot.file') {
        // #file — user dragged a file into chat
        const uri = ref.value?.uri || ref.value;
        if (uri && uri.fsPath) {
          sourceDocHint = uri.fsPath;
          parts.push(`[Referenced file]: ${uri.fsPath}`);
        }
      } else if (ref.id === 'vscode.editor' || ref.id === 'copilot.editor') {
        // #editor — active editor context
        if (ref.value?.uri?.fsPath) {
          sourceDocHint = ref.value.uri.fsPath;
        }
        const visibleText = ref.value?.selectedText || ref.value?.text || '';
        if (visibleText) {
          parts.push(`[Editor context]: ${visibleText}`);
        }
      }
    } catch (_) {
      // Gracefully skip malformed references
    }
  }

  return {
    referenceText: parts.join('\n'),
    sourceDocHint,
  };
}

// ── Phase 10: Session tracking ──────────────────────────────────────
let _sessionTurnCount = 0;
const _conversationHistory = [];

/**
 * Generate a unique session ID per VS Code window.
 * Resets when the extension reloads.
 */
const _sessionId = `kts_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

/**
 * Phase 10.1: Build conversation context from VS Code's ChatContext history.
 *
 * Parses vscode.ChatRequestTurn and vscode.ChatResponseTurn from the native
 * context.history to supplement the manual _conversationHistory array.
 *
 * @param {import('vscode').ChatContext} chatContext  Native VS Code chat context
 * @param {number} maxTurns  Maximum turns to include
 * @returns {Array<{role: string, content: string}>}
 */
function buildConversationContext(chatContext, maxTurns = 10) {
  const turns = [];
  if (!chatContext || !chatContext.history) return turns;

  const history = chatContext.history;
  const startIdx = Math.max(0, history.length - maxTurns);
  for (let i = startIdx; i < history.length; i++) {
    const turn = history[i];
    if (turn.participant === 'kts.assistant' || !turn.participant) {
      // ChatRequestTurn (user turn)
      if (turn.prompt !== undefined) {
        turns.push({ role: 'user', content: turn.prompt || '' });
      }
      // ChatResponseTurn (assistant turn)
      if (turn.response !== undefined) {
        // Extract text from response parts
        const parts = [];
        try {
          for (const part of turn.response) {
            if (typeof part === 'string') {
              parts.push(part);
            } else if (part.value && typeof part.value === 'string') {
              parts.push(part.value);
            }
          }
        } catch (_) {
          // response may not be iterable in all VS Code versions
        }
        if (parts.length > 0) {
          turns.push({ role: 'assistant', content: parts.join('').slice(0, 2000) });
        }
      }
    }
  }
  return turns;
}

// ---------------------------------------------------------------------------
// KTS RAG System Prompt — Non-Legal (Knowledge, Training, Support)
// ---------------------------------------------------------------------------
const KTS_SYSTEM_PROMPT = [
  'You are KTS Assistant — a precise, helpful knowledge-base assistant.',
  'Answer the user\'s question using ONLY the retrieved context below.',
  '',
  'Rules:',
  '- Synthesize a clear, direct answer. Do not recite chunks verbatim.',
  '- Interpret semantically: "computer will not restate" means "will not restart".',
  '- When multiple chunks are relevant, combine them into one coherent answer.',
  '- If the context does not contain an answer, say so explicitly.',
  '- Do not invent information or cite external sources.',
  '- Write in a professional, conversational tone — no rigid numbered sections.',
  '- Naturally mention the source document or section when quoting key facts.',
].join('\n');

// ---------------------------------------------------------------------------
// Legal / Governing Document System Prompt
// ---------------------------------------------------------------------------
const LEGAL_SYSTEM_PROMPT = [
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

// ---------------------------------------------------------------------------
// LLM Model Selection (for RAG generation)
// ---------------------------------------------------------------------------
/**
 * Select the single LLM model for all RAG operations.
 * Uses kts.model setting or the user's active Copilot model.
 * Replaces both selectChatModel() and selectReasoningModel().
 */
async function selectModel(vscode, requestModel) {
  // 1. User's chat picker model (highest priority)
  if (requestModel && typeof requestModel.sendRequest === 'function') {
    return requestModel;
  }

  // 2. kts.model setting
  if (!vscode.lm || typeof vscode.lm.selectChatModels !== 'function') {
    return null;
  }

  try {
    const cfg = vscode.workspace.getConfiguration('kts');
    const modelSetting = cfg.get('model', 'auto');
    if (modelSetting && modelSetting !== 'auto') {
      const models = await vscode.lm.selectChatModels({ family: modelSetting });
      if (models && models.length > 0) return models[0];
    }
  } catch (_) { /* fallback */ }

  // 3. Fallback: auto-select best available
  const families = ['gpt-4.1', 'gpt-4o', 'claude-sonnet-4', 'gpt-4o-mini'];
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

// Backward-compat aliases for existing test imports
const selectChatModel = selectModel;
const selectReasoningModel = (vscode, _component) => selectModel(vscode, null);

// ---------------------------------------------------------------------------
// RAG Answer Generation
// ---------------------------------------------------------------------------

/**
 * Majority-vote prompt selection based on doc_type metadata.
 * If more than 50% of retrieved chunks have doc_type === 'GOVERNING_DOC',
 * use the Legal prompt; otherwise use the KTS (non-legal) prompt.
 * Returns { prompt, mode } where mode is 'legal' or 'kts'.
 */
function selectPrompt(result) {
  let search = result.search_result;
  if (search && search.search_result && typeof search.search_result === 'object') {
    search = search.search_result;
  }
  const chunks = (search && Array.isArray(search.context_chunks)) ? search.context_chunks : [];
  if (!chunks.length) return { prompt: KTS_SYSTEM_PROMPT, mode: 'kts' };

  const govCount = chunks.filter(
    c => (c.doc_type || '').toUpperCase() === 'GOVERNING_DOC'
  ).length;
  const isLegal = govCount / chunks.length > 0.5;

  return isLegal
    ? { prompt: LEGAL_SYSTEM_PROMPT, mode: 'legal' }
    : { prompt: KTS_SYSTEM_PROMPT, mode: 'kts' };
}

/**
 * Extract a human-readable document name from a chunk.
 * Prefers doc_name, then extracts filename from source_path, then doc_id.
 */
function resolveDocName(chunk, fallback) {
  if (chunk.doc_name) return chunk.doc_name;
  if (chunk.source_path) {
    const parts = chunk.source_path.replace(/\\/g, '/').split('/');
    return parts[parts.length - 1] || fallback;
  }
  return chunk.doc_id || fallback;
}

/**
 * Build a context block from retrieved chunks for the LLM prompt.
 * Used for non-legal (KTS) mode — labels chunks as [Source N: name].
 */
function buildContextBlock(result, maxChunks = 100) {
  let search = result.search_result;
  if (search.search_result && typeof search.search_result === 'object') {
    search = search.search_result;
  }
  const chunks = Array.isArray(search.context_chunks) ? search.context_chunks : [];
  if (!chunks.length) return '';

  return chunks
    .slice(0, maxChunks)
    .map((chunk, i) => {
      const body = (chunk.content || '').replace(/^\[EVIDENCE\][^\n]*\n?/, '').trim();
      const source = resolveDocName(chunk, `source-${i + 1}`);
      return `[Source ${i + 1}: ${source}]\n${body}`;
    })
    .join('\n\n');
}

/**
 * Build a context block for Legal / Governing Document mode.
 * Labels each chunk with Document name, Section, and Page when available.
 */
function buildLegalContextBlock(result, maxChunks = 100) {
  let search = result.search_result;
  if (search.search_result && typeof search.search_result === 'object') {
    search = search.search_result;
  }
  const chunks = Array.isArray(search.context_chunks) ? search.context_chunks : [];
  const citations = Array.isArray(search.citations) ? search.citations : [];

  if (!chunks.length) return '';

  // Build a quick lookup: doc_id -> citation metadata (section, page)
  const citationMap = {};
  for (const cit of citations) {
    const key = cit.doc_id || cit.doc_name;
    if (key && !citationMap[key]) citationMap[key] = cit;
  }

  return chunks
    .slice(0, maxChunks)
    .map((chunk, i) => {
      const body = (chunk.content || '').replace(/^\[EVIDENCE\][^\n]*\n?/, '').trim();
      const docName = resolveDocName(chunk, `document-${i + 1}`);

      // Try chunk-level section/page first, then citation-level
      const cit = citationMap[chunk.doc_id] || citationMap[chunk.doc_name] || {};
      const section = chunk.section || cit.section || null;
      const page = chunk.page ?? cit.page ?? null;

      let label = `[Document: ${docName}`;
      if (section) label += `, Section: ${section}`;
      if (page !== null && page !== undefined) label += `, Page: ${page}`;
      label += ']';

      return `${label}\n${body}`;
    })
    .join('\n\n');
}

// ── Phase 9.2: Extract critique questions from retrieval metadata ────

/**
 * Build a "knowledge preamble" from shared definitions glossary and entity
 * roles.  These are sent ONCE before the per-chunk context blocks so the
 * LLM has the glossary / role context without it being duplicated per chunk.
 */
function buildKnowledgePreamble(result) {
  let search = result.search_result;
  if (search && search.search_result && typeof search.search_result === 'object') {
    search = search.search_result;
  }
  if (!search) return '';

  const parts = [];

  // Entity role mappings (NER)
  const roles = search.entity_roles;
  if (Array.isArray(roles) && roles.length > 0) {
    const roleLines = roles.map(r => `- ${r.entity} → ${r.term}`);
    parts.push(`## Entity Roles\n${roleLines.join('\n')}`);
  }

  // Definitions glossary (resolution trees + dependency maps)
  const glossary = search.definitions_glossary;
  if (typeof glossary === 'string' && glossary.trim()) {
    parts.push(`## Definitions Glossary\n${glossary.trim()}`);
  }

  return parts.join('\n\n');
}

/**
 * Extract critique questions from the backend search response.
 * The backend now injects a top-level `critique_questions` array via
 * merge_critique_questions() (provenance-filtered, priority-sorted).
 * Falls back to per-chunk metadata for backward compatibility.
 */
function _extractCritiqueQuestions(result) {
  const questions = [];
  const seen = new Set();

  // ── Primary: top-level critique_questions from backend payload ──
  const topLevel = result?.critique_questions
    || result?.search_result?.critique_questions
    || [];
  for (const q of topLevel) {
    const text = typeof q === 'string' ? q : q.question;
    if (text && !seen.has(text)) {
      seen.add(text);
      questions.push({
        question: text,
        trigger_keywords: q.trigger_keywords || [],
        trigger_logic: q.trigger_logic || 'always',
        priority: q.priority ?? 1,
      });
    }
  }

  // ── Fallback: per-chunk metadata (legacy/backward compat) ──────
  if (questions.length === 0) {
    let search = result?.search_result;
    if (search?.search_result && typeof search.search_result === 'object') {
      search = search.search_result;
    }
    const chunks = (search && Array.isArray(search.context_chunks))
      ? search.context_chunks : [];
    for (const chunk of chunks) {
      const cqs = chunk.critique_questions
        || chunk.metadata?.critique_questions
        || [];
      for (const q of cqs) {
        const text = typeof q === 'string' ? q : q.question;
        if (text && !seen.has(text)) {
          seen.add(text);
          questions.push({
            question: text,
            trigger_keywords: q.trigger_keywords || [],
            trigger_logic: q.trigger_logic || 'always',
            priority: q.priority ?? 1,
          });
        }
      }
    }
  }

  // Sort by priority ascending (1 = highest)
  questions.sort((a, b) => a.priority - b.priority);
  return questions;
}

/**
 * Generate a synthesized answer using the VS Code LM API (Copilot).
 * Streams the response token-by-token into the chat stream.
 * Returns true if generation succeeded, false to fall back to raw chunks.
 */
async function generateAnswer(vscode, model, stream, token, query, result, outputChannel, options = {}) {
  const bufferMode = options.bufferMode || false;  // When true, collect tokens without streaming to UI
  const conversationHistory = options.conversationHistory || [];  // Recent turns for multi-turn context
  // Select prompt + context formatter based on chunk doc_type metadata
  const { prompt, mode } = selectPrompt(result);
  const tokenBudget = computeTokenBudget(model);
  const maxChunks = computeMaxChunks(tokenBudget);
  const contextBlock = mode === 'legal'
    ? buildLegalContextBlock(result, maxChunks)
    : buildContextBlock(result, maxChunks);
  if (!contextBlock) return false;

  // Phase 8.3: Token-aware context trimming
  const contextParts = contextBlock.split('\n\n').filter(Boolean);
  const contextBlocks = contextParts.map(part => ({ text: part }));
  const trimmedBlocks = trimContextToTokenBudget(contextBlocks, tokenBudget);
  const trimmedContext = trimmedBlocks.map(b => b.text).join('\n\n');

  // Phase 14.2: Inject temporal context into prompt if available
  const temporalPreamble = getTemporalContextForPrompt(result);

  // Phase 14.1: Inject cached term definitions from session deal summary
  let cachedTermsPreamble = '';
  const searchData = result.search_result?.search_result || result.search_result;
  const cachedTerms = searchData?.cached_terms;
  if (cachedTerms && typeof cachedTerms === 'object' && Object.keys(cachedTerms).length > 0) {
    const termLines = Object.entries(cachedTerms)
      .map(([term, def]) => `- **${term}**: ${def}`)
      .join('\n');
    cachedTermsPreamble = `\n## Previously Resolved Terms (from session cache)\n${termLines}\nUse these definitions when answering. Do not re-retrieve them.\n`;
  }

  // Phase 10.1: Build conversation history preamble (last N turns)
  let historyPreamble = '';
  if (conversationHistory.length > 0) {
    // Include last 5 turns (user+assistant pairs) for multi-turn context
    const recentTurns = conversationHistory.slice(-20);  // 20 entries = ~10 pairs
    const formattedTurns = recentTurns.map(t => {
      const role = t.role === 'user' ? 'User' : 'Assistant';
      // Cap each turn to 1500 chars to control token usage
      const content = (t.content || '').slice(0, 1500);
      return `**${role}:** ${content}`;
    }).join('\n\n');
    historyPreamble = `\n## Conversation History (for context only)\nThe user is continuing a conversation. Here are the recent exchanges:\n\n${formattedTurns}\n\nUse this history to understand follow-up references (e.g., \"that section\", \"list more details\"). The current question and retrieved context below take precedence.\n`;
  }

  // Build shared knowledge preamble (definitions glossary + entity roles)
  // Sent once BEFORE the per-chunk context blocks to avoid duplication.
  const knowledgePreamble = buildKnowledgePreamble(result);

  const userMessage = [
    prompt,
    temporalPreamble,  // empty string when there is no temporal context
    cachedTermsPreamble,  // empty string when no cached terms
    historyPreamble,  // empty string when no conversation history
    '',
    '---',
    '',
    knowledgePreamble,  // shared glossary + entity roles (empty if none)
    knowledgePreamble ? '' : null,  // spacer after preamble
    '## Retrieved Context',
    trimmedContext,
    '',
    '## User Question',
    query,
  ].filter(line => line !== null).join('\n');

  // ── Diagnostic logging to Output Channel ──────────────────────────────
  if (outputChannel) {
    const log = (msg) => outputChannel.appendLine(msg);
    const sep = '═'.repeat(72);

    log('');
    log(sep);
    log(`[KTS-DIAG] LLM Prompt Payload  —  ${new Date().toISOString()}`);
    log(sep);

    // 1. Prompt mode + model
    log(`  Mode       : ${mode.toUpperCase()} (${mode === 'legal' ? 'Legal Analyst' : 'KTS Support'})`);
    log(`  Model      : ${model.id || model.family || 'unknown'}`);
    log(`  Query      : ${query}`);
    log('');

    // 2. Per-chunk doc_type breakdown
    let search = result.search_result;
    if (search && search.search_result && typeof search.search_result === 'object') {
      search = search.search_result;
    }
    const allChunks = (search && Array.isArray(search.context_chunks)) ? search.context_chunks : [];
    log(`  Chunks     : ${allChunks.length} retrieved`);
    allChunks.forEach((c, i) => {
      const dt = (c.doc_type || 'UNKNOWN').toUpperCase();
      const dn = resolveDocName(c, 'unnamed');
      const sec = c.section ? `, sec=${c.section}` : '';
      const pg  = (c.page !== null && c.page !== undefined) ? `, pg=${c.page}` : '';
      log(`    [${i + 1}] doc_type=${dt}  doc=${dn}${sec}${pg}`);
    });

    // 3. doc_type vote summary
    const typeCounts = {};
    allChunks.forEach(c => {
      const t = (c.doc_type || 'UNKNOWN').toUpperCase();
      typeCounts[t] = (typeCounts[t] || 0) + 1;
    });
    const voteStr = Object.entries(typeCounts).map(([t, n]) => `${t}=${n}`).join(', ');
    log(`  Vote       : ${voteStr}  →  ${mode}`);
    log('');

    // 4. Full LLM payload (indented for readability)
    log('  ─── FULL LLM MESSAGE (start) ───');
    userMessage.split('\n').forEach(line => log(`  │ ${line}`));
    log('  ─── FULL LLM MESSAGE (end) ─────');
    log(sep);
    log('');
  }

  const messages = [
    vscode.LanguageModelChatMessage.User(userMessage),
  ];

  try {
    const response = await model.sendRequest(messages, {}, token);
    // Phase 10.1: Collect answer text for conversation history
    const collectedChunks = [];
    // Mode indicator removed (Phase 16: conversational output — no rigid badges)
    for await (const chunk of response.text) {
      if (!bufferMode) stream.markdown(chunk);
      collectedChunks.push(chunk);
    }
    // Return collected text + mode metadata for downstream use
    const answerText = collectedChunks.join('');
    return { text: answerText, mode, prompt, contextBlock };
  } catch (err) {
    if (outputChannel) {
      outputChannel.appendLine(`[KTS-DIAG] LLM call failed: ${err.message}`);
    }
    // If the LM call fails (quota, cancellation, etc.), fall back to raw chunks
    return false;
  }
}

function toMarkdown(result) {
  if (!result || result.status !== 'ok' || !result.search_result) {
    return `KTS retrieval failed.\n\n${result?.error ? `Error: ${result.error}` : 'No result returned.'}`;
  }

  // Handle both wrapped and unwrapped search_result from CLI
  // CLI may return: {context_chunks: [...]} OR {search_result: {...}, term_resolution: {...}}
  let search = result.search_result;
  if (search.search_result && typeof search.search_result === 'object') {
    // Wrapped case: unwrap the nested search_result
    search = search.search_result;
  }
  
  const chunks = Array.isArray(search.context_chunks) ? search.context_chunks : [];
  const citations = Array.isArray(search.citations) ? search.citations : [];
  const isDeep = result.deep_mode || false;
  const displayLimit = isDeep ? 10 : 5;

  if (!chunks.length) {
    return 'No matching KTS context was found for this query. Try adding product/tool names or error codes.';
  }

  const summary = chunks
    .slice(0, displayLimit)
    .map((chunk, index) => {
      // Strip internal [EVIDENCE] metadata header before display
      const body = (chunk.content || '').replace(/^\[EVIDENCE\][^\n]*\n?/, '').trim();
      return `### Context ${index + 1}\n${body}`;
    })
    .join('\n\n');

  const citationMd = citations
    .slice(0, 10)
    .map((citation, index) => {
      const label = citation.doc_name || citation.doc_id || `source-${index + 1}`;
      const uri = citation.uri || citation.source_path;
      return uri ? `${index + 1}. [${label}](${uri})` : `${index + 1}. ${label}`;
    })
    .join('\n');

  const confidence = typeof search.confidence === 'number' ? search.confidence.toFixed(2) : 'n/a';

  // Term resolution (Gap 5)
  let termResMd = '';
  const termRes = result.search_result?.term_resolution;
  if (termRes && termRes.activated && Array.isArray(termRes.resolutions) && termRes.resolutions.length > 0) {
    const items = termRes.resolutions.map(r => {
      const closure = (r.closure || []).join(' → ');
      return `- **${r.root_term}**: ${closure}`;
    }).join('\n');
    termResMd = `\n\n### Defined-Term Resolution\n${items}`;
  }

  // Freshness (Gap 5)
  let freshnessMd = '';
  const freshness = search.freshness;
  if (freshness && (freshness.aging > 0 || freshness.stale > 0)) {
    freshnessMd = `\n\n> **Freshness**: ${freshness.current} current, ${freshness.aging} aging, ${freshness.stale} stale`;
  }

  // Related topics (Gap 5)
  let topicsMd = '';
  const topics = Array.isArray(search.related_topics) ? search.related_topics : [];
  if (topics.length > 0) {
    topicsMd = `\n\n**Related topics**: ${topics.join(', ')}`;
  }

  // Agent Reasoning trace (Phase 6 explainability)
  let traceMd = '';
  const phase6 = result.search_result?.phase6;
  if (phase6) {
    const traceSteps = Array.isArray(phase6.trace) ? phase6.trace : (phase6.trace?.steps || []);
    if (traceSteps.length > 0) {
      const stepsText = traceSteps
        .filter(s => s.step && s.step !== 'start' && s.step !== 'complete')
        .map(s => {
          const why = s.why ? ` — *${s.why}*` : '';
          const elapsed = typeof s.elapsed_ms === 'number' ? ` (${Math.round(s.elapsed_ms)}ms)` : '';
          return `- **${s.step}**: ${s.description || ''}${why}${elapsed}`;
        })
        .join('\n');
      if (stepsText) {
        const iters = phase6.iterations || 1;
        const p6conf = typeof phase6.confidence === 'number' ? phase6.confidence.toFixed(2) : 'n/a';
        traceMd = `\n\n### Agent Reasoning\n` +
          `Retrieval pipeline completed in ${iters} iteration(s), confidence: ${p6conf}.\n\n` +
          stepsText;
      }
    }
  }

  // Phase 13.1: Confidence tier display (fallback path)
  let confidenceTierMd = '';
  const tier = search.confidence_tier;
  if (tier && tier.display) {
    confidenceTierMd = `\n\n${tier.display}`;
  }

  // Phase 13.2: Gap alert display (fallback path)
  let gapAlertMd = '';
  const gap = search.gap_alert;
  if (gap && gap.display) {
    gapAlertMd = `\n\n${gap.display}`;
  }

  return [
    `KTS retrieved context (confidence: ${confidence}).`,
    '',
    summary,
    '',
    '### Citations',
    citationMd || 'No citations returned.',
    termResMd,
    freshnessMd,
    topicsMd,
    traceMd,
    confidenceTierMd,
    gapAlertMd,
  ].filter(Boolean).join('\n');
}

// ---------------------------------------------------------------------------
// Citation & Trace helpers (used after RAG-generated answers)
// ---------------------------------------------------------------------------
function buildCitationBlock(result) {
  let search = result.search_result;
  if (search.search_result && typeof search.search_result === 'object') {
    search = search.search_result;
  }
  const citations = Array.isArray(search.citations) ? search.citations : [];
  if (!citations.length) return '';

  const citationMd = citations
    .slice(0, 10)
    .map((citation, index) => {
      const label = citation.doc_name || citation.doc_id || `source-${index + 1}`;
      const uri = citation.uri || citation.source_path;
      return uri ? `${index + 1}. [${label}](${uri})` : `${index + 1}. ${label}`;
    })
    .join('\n');

  return `\n### Sources\n${citationMd}\n`;
}

function buildTraceBlock(result) {
  const phase6 = result.search_result?.phase6;
  if (!phase6) return '';

  const traceSteps = Array.isArray(phase6.trace) ? phase6.trace : (phase6.trace?.steps || []);
  if (!traceSteps.length) return '';

  const stepsText = traceSteps
    .filter(s => s.step && s.step !== 'start' && s.step !== 'complete')
    .map(s => {
      const why = s.why ? ` — *${s.why}*` : '';
      const elapsed = typeof s.elapsed_ms === 'number' ? ` (${Math.round(s.elapsed_ms)}ms)` : '';
      return `- **${s.step}**: ${s.description || ''}${why}${elapsed}`;
    })
    .join('\n');

  if (!stepsText) return '';

  const iters = phase6.iterations || 1;
  const p6conf = typeof phase6.confidence === 'number' ? phase6.confidence.toFixed(2) : 'n/a';
  return `\n### Agent Reasoning\nRetrieval pipeline completed in ${iters} iteration(s), confidence: ${p6conf}.\n\n${stepsText}\n`;
}

function extractMaxResults(request, vscode) {
  const command = request?.command;
  
  // Use RAG_CONFIG defaults; scale by half for normal, full for deep
  const configured = RAG_CONFIG.maxContextChunks;
  const defaultMax = Math.floor(configured / 2);
  const deepMax = configured;
  
  if (!command || typeof command !== 'string') {
    return { maxResults: defaultMax, deepMode: false };
  }

  if (command === 'deep') {
    return { maxResults: deepMax, deepMode: true };
  }
  return { maxResults: defaultMax, deepMode: false };
}

// ---------------------------------------------------------------------------
// Phase 13.1: Confidence Tier Display
// ---------------------------------------------------------------------------
function buildConfidenceBlock(result) {
  const tier = result.search_result?.confidence_tier;
  if (!tier || !tier.display) return '';
  return `\n${tier.display}\n`;
}

// ---------------------------------------------------------------------------
// Phase 13.2: Gap Alert Display
// ---------------------------------------------------------------------------
function buildGapAlertBlock(result) {
  const gap = result.search_result?.gap_alert;
  if (!gap || !gap.display) return '';
  return `\n${gap.display}\n`;
}

// ---------------------------------------------------------------------------
// Phase 15.1: Comparison Table Rendering
// ---------------------------------------------------------------------------
function buildComparisonBlock(result) {
  const comparison = result.search_result?.comparison_result;
  if (!comparison) return '';

  let block = `\n## Comparison: "${comparison.concept}" across ${(comparison.scopes_compared || []).length} deals\n\n`;

  // Render raw markdown from LLM comparison
  if (comparison.raw_markdown) {
    block += comparison.raw_markdown + '\n';
  }

  // Render contradiction alerts
  const contradictions = result.search_result?.contradictions;
  if (contradictions && contradictions.length > 0) {
    const actual = contradictions.filter(c => c.contradicts);
    if (actual.length > 0) {
      block += '\n### 🔴 Contradictions Detected\n\n';
      for (const c of actual) {
        const sev = c.severity === 'material' ? '**Material**' : 'Minor';
        block += `- ${sev}: ${c.scope_a} vs ${c.scope_b} — ${c.summary || 'Conflict detected'}\n`;
        if (c.contradiction_type) {
          block += `  Type: ${c.contradiction_type}\n`;
        }
      }
    }
  }

  return block;
}

// ---------------------------------------------------------------------------
// Phase 15.4: Anomaly Badge Rendering
// ---------------------------------------------------------------------------
function buildAnomalyBlock(result) {
  const anomalies = result.search_result?.anomaly_scores;
  if (!anomalies || !anomalies.length) return '';

  const flagged = anomalies.filter(a => a.is_anomalous);
  if (!flagged.length) return '';

  let block = '\n### Anomaly Flags\n\n';
  for (const a of anomalies) {
    let icon, label;
    if (a.severity === 'high') {
      icon = '🔴'; label = 'Significant deviation';
    } else if (a.severity === 'medium') {
      icon = '⚠️'; label = 'Non-standard';
    } else if (a.severity === 'low') {
      icon = '🔵'; label = 'Minor deviation';
    } else {
      icon = '✅'; label = 'Standard language';
    }

    block += `- ${icon} **${label}** — ${a.clause_type || 'clause'}`;
    if (typeof a.similarity_to_standard === 'number') {
      block += ` (similarity: ${a.similarity_to_standard.toFixed(2)})`;
    }
    block += '\n';

    if (a.deviation_signals && a.deviation_signals.length > 0) {
      block += `  Deviation signals: ${a.deviation_signals.join(', ')}\n`;
    }
  }
  return block;
}

// ---------------------------------------------------------------------------
// Phase 14.3: Extraction Result Rendering
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Phase 17: Multi-Scope Result Attribution & Diff/Aggregate Rendering
// ---------------------------------------------------------------------------

/**
 * Build a diff result block for /diff mode output.
 * Shows field-level diffs between two scopes with significance badges.
 */
function buildDiffBlock(result) {
  const diff = result.search_result?.diff_result;
  if (!diff) return '';

  let block = '\n## Diff Results\n\n';
  const pairs = diff.pairwise_diffs || [];
  if (!pairs.length) {
    block += '_No meaningful differences detected._\n';
    return block;
  }

  for (const pair of pairs) {
    block += `### ${pair.scope_a || 'Scope A'} vs ${pair.scope_b || 'Scope B'}\n\n`;
    const fieldDiffs = pair.field_diffs || [];
    if (fieldDiffs.length === 0) {
      block += '_Identical or highly similar._\n\n';
      continue;
    }
    block += '| Field | ' + (pair.scope_a || 'A') + ' | ' + (pair.scope_b || 'B') + ' | Significance |\n';
    block += '|-------|---|---|---|\n';
    for (const fd of fieldDiffs) {
      const sig = fd.significance === 'high' ? '🔴 High' : fd.significance === 'medium' ? '⚠️ Medium' : '🔵 Low';
      const valA = (fd.value_a || '—').replace(/\|/g, '\\|');
      const valB = (fd.value_b || '—').replace(/\|/g, '\\|');
      block += `| ${fd.field || 'n/a'} | ${valA} | ${valB} | ${sig} |\n`;
    }
    block += '\n';
  }

  if (diff.summary) {
    block += `**Summary:** ${diff.summary}\n`;
  }
  return block;
}

/**
 * Build an aggregate result block for /aggregate mode output.
 * Shows consensus patterns, outliers, and deviations.
 */
function buildAggregateBlock(result) {
  const agg = result.search_result?.aggregate_result;
  if (!agg) return '';

  let block = `\n## Aggregate Analysis (${agg.scope_count || '?'} deals)\n\n`;

  // Consensus pattern
  if (agg.consensus) {
    block += '### Consensus Pattern\n\n';
    block += agg.consensus + '\n\n';
  }

  // Outliers table
  const outliers = agg.outliers || [];
  if (outliers.length > 0) {
    block += '### Outliers\n\n';
    block += '| Deal | Deviation Type | Detail |\n';
    block += '|------|---------------|--------|\n';
    for (const o of outliers) {
      const detail = (o.detail || o.text || '—').replace(/\|/g, '\\|');
      block += `| ${o.scope || 'unknown'} | ${o.deviation_type || 'n/a'} | ${detail} |\n`;
    }
    block += '\n';
  } else {
    block += '_No outliers detected — all deals align with the consensus._\n\n';
  }

  if (agg.summary) {
    block += `**Summary:** ${agg.summary}\n`;
  }
  return block;
}

/**
 * Build multi-scope attribution block.
 * When results come from multiple deals, label each chunk with its deal scope.
 */
function buildMultiScopeAttribution(result) {
  const scopes = result.search_result?.scopes_searched;
  if (!scopes || !Array.isArray(scopes) || scopes.length < 2) return '';

  let block = '\n### Scopes Searched\n\n';
  for (const s of scopes) {
    const icon = s.status === 'ok' ? '✅' : s.status === 'timeout' ? '⏱️' : '❌';
    const count = typeof s.result_count === 'number' ? ` (${s.result_count} results)` : '';
    block += `- ${icon} **${s.slug || s.scope}**${count}\n`;
  }
  return block;
}

// ---------------------------------------------------------------------------
/**
 * Render structured extraction results as a formatted block.
 * Shows extracted fields as a table/code block and lists extraction gaps.
 */
function buildExtractionBlock(result) {
  let search = result.search_result;
  if (search && search.search_result && typeof search.search_result === 'object') {
    search = search.search_result;
  }
  const extraction = search?.extraction_result;
  if (!extraction) return '';

  let block = '\n\n---\n**📋 Structured Extraction**\n\n';

  if (extraction.parsed_ok) {
    const data = extraction.data || {};
    // Deal header
    if (data.deal_name) block += `**Deal:** ${data.deal_name}\n`;
    if (data.deal_type) block += `**Type:** ${data.deal_type}\n`;
    if (data.closing_date) block += `**Closing Date:** ${data.closing_date}\n\n`;

    // Parties table
    if (data.parties && Object.keys(data.parties).length > 0) {
      block += '### Parties\n| Role | Entity |\n|------|--------|\n';
      for (const [role, entity] of Object.entries(data.parties)) {
        if (entity) block += `| ${role} | ${entity} |\n`;
      }
      block += '\n';
    }

    // Key Dates table
    if (data.key_dates && Object.keys(data.key_dates).length > 0) {
      block += '### Key Dates\n| Date | Value |\n|------|-------|\n';
      for (const [name, value] of Object.entries(data.key_dates)) {
        if (value) block += `| ${name} | ${value} |\n`;
      }
      block += '\n';
    }

    // Defined Terms
    if (data.defined_terms && Object.keys(data.defined_terms).length > 0) {
      block += '### Defined Terms\n';
      for (const [term, def] of Object.entries(data.defined_terms)) {
        block += `- **${term}**: ${def}\n`;
      }
      block += '\n';
    }

    // Confidence & sources
    if (data.confidence) block += `*Confidence: ${data.confidence}*`;
    if (data.source_sections && data.source_sections.length > 0) {
      block += ` | *Sources: ${data.source_sections.join(', ')}*`;
    }
    block += '\n';
  } else {
    block += '⚠️ JSON parsing failed — raw extraction returned.\n';
    if (extraction.data?.raw_text) {
      block += '```\n' + extraction.data.raw_text.slice(0, 2000) + '\n```\n';
    }
  }

  // Extraction gaps
  const gaps = extraction.extraction_gaps || [];
  if (gaps.length > 0) {
    block += `\n**Extraction Gaps:** ${gaps.join(', ')}\n`;
  }

  return block;
}

// ---------------------------------------------------------------------------
// Phase 14.4: Summary Result Rendering
// ---------------------------------------------------------------------------
/**
 * Render deal summary results. The raw markdown from the LLM is the summary
 * itself (5 sections). We add metadata and confidence footer.
 */
function buildSummaryBlock(result) {
  let search = result.search_result;
  if (search && search.search_result && typeof search.search_result === 'object') {
    search = search.search_result;
  }
  const summary = search?.summary_result;
  if (!summary) return '';

  let block = '\n\n---\n';
  if (summary.scope) block += `**📄 Deal Summary: ${summary.scope}**\n\n`;

  // Raw markdown from LLM is the 5-section summary
  if (summary.raw_markdown) {
    block += summary.raw_markdown + '\n';
  }

  // Sections coverage check
  const expectedSections = ['Parties', 'Key Dates', 'Key Amounts', 'Key Obligations', 'Risk Factors'];
  const found = summary.sections_found || [];
  const missing = expectedSections.filter(s => !found.includes(s));
  if (missing.length > 0) {
    block += `\n⚠️ *Missing sections: ${missing.join(', ')}*\n`;
  }

  return block;
}

// ---------------------------------------------------------------------------
// Phase 14.2: Temporal Context Injection
// ---------------------------------------------------------------------------
function getTemporalContextForPrompt(result) {
  const ctx = result.search_result?.temporal_context;
  const eval_ = result.search_result?.temporal_evaluation;
  if (!ctx) return '';
  let block = `\n${ctx}`;
  if (eval_) block += `\n${eval_}`;
  return block;
}

// ---------------------------------------------------------------------------
// Phase 11.2: Follow-Up Suggestion Generation
// ---------------------------------------------------------------------------

/**
 * FOLLOW_UP_PATTERNS — deterministic regex patterns applied to the ANSWER text.
 * Each entry: { regex, generate(match) → string[] }
 * Per spec: pattern-match defined terms, dates, dollar amounts, cross-refs,
 * and party names in the generated answer — no LLM call, zero latency.
 */
const FOLLOW_UP_PATTERNS = [
  {
    // Defined term found in answer: **Term** means ...
    regex: /\*\*([A-Z][a-zA-Z\s]+)\*\*\s+means/,
    generate: (match) => [
      `Which sections reference the ${match[1]}?`,
      `Are there exceptions or exclusions to the ${match[1]}?`,
    ],
  },
  {
    // Date found in answer: January 15, 2024 or Jan 15 2024
    regex: /\b(\w+ \d{1,2},? \d{4})\b/,
    generate: (match) => [
      `Has ${match[1]} passed?`,
      `What events are triggered on or after ${match[1]}?`,
    ],
  },
  {
    // Dollar amount found in answer
    regex: /\$[\d,]+(?:\.\d{2})?/,
    generate: (_match) => [
      'How is this amount calculated?',
      'Are there caps, floors, or adjustments to this amount?',
    ],
  },
  {
    // Section cross-reference found
    regex: /Section (\d+(?:\.\d+)*)/,
    generate: (match) => [
      `Show me the full text of Section ${match[1]}`,
    ],
  },
  {
    // Party name found (common structured-finance roles)
    regex: /\b(Trustee|Servicer|Depositor|Master Servicer|Issuer|Seller|Noteholder)\b/i,
    generate: (match) => [
      `What are all obligations of the ${match[1]}?`,
      `Who succeeds the ${match[1]} if removed?`,
    ],
  },
];

function buildFollowUpSuggestions(query, result, mode, answerText) {
  // Phase 11.2: Generate follow-ups deterministically from ANSWER text
  const suggestions = [];

  // Use the provided answerText (generated answer) or fall back to result extraction
  const text = answerText || _extractAnswerText(result);

  if (text) {
    // Apply FOLLOW_UP_PATTERNS to the answer text
    for (const pattern of FOLLOW_UP_PATTERNS) {
      const match = pattern.regex.exec(text);
      if (match) {
        suggestions.push(...pattern.generate(match));
      }
      if (suggestions.length >= 3) break;
    }
  }

  // Fallback: if no answer patterns matched, generate query-based follow-ups
  if (suggestions.length === 0) {
    if (mode === 'legal') {
      if (/definition|defined\s+term/i.test(query)) {
        suggestions.push('What other terms reference this definition?');
      } else if (/date|deadline|period/i.test(query)) {
        suggestions.push('Has this date already passed?');
      } else {
        suggestions.push('What are the key defined terms in this section?');
        suggestions.push('Are there any related provisions?');
      }
    } else {
      if (/error|fail|issue|problem/i.test(query)) {
        suggestions.push('What is the escalation path if this persists?');
      } else if (/how\s+to|steps|process/i.test(query)) {
        suggestions.push('Are there any known issues with this process?');
      } else {
        suggestions.push('Can you provide more detail on this topic?');
      }
    }
  }

  return suggestions.slice(0, 3);
}

/**
 * Extract the answer text string from a result object for follow-up pattern matching.
 * Handles various result shapes: { answer }, { search_result.answer }, raw string.
 */
function _extractAnswerText(result) {
  if (!result) return '';
  if (typeof result === 'string') return result;
  if (result.answer) return result.answer;
  if (result.search_result && result.search_result.answer) return result.search_result.answer;
  if (result.search_result && typeof result.search_result === 'string') return result.search_result;
  return '';
}

/**
 * Generate context-aware follow-up questions using the LLM.
 * Called when regex-based patterns don't produce good suggestions.
 * Returns 3 specific follow-up questions grounded in the query + answer.
 */
async function generateLLMFollowUps(vscode, model, token, query, answerText, mode) {
  if (!model || !answerText) return [];
  try {
    const systemPrompt = mode === 'legal'
      ? 'You are a structured-finance legal analyst. Given a user question and the answer provided, suggest exactly 3 specific follow-up questions the user would naturally ask next. Questions must be grounded in the answer content — reference specific sections, terms, parties, or dates mentioned. Do NOT suggest generic questions. Return ONLY a JSON array of 3 strings.'
      : 'You are a knowledge-base assistant. Given a user question and the answer provided, suggest exactly 3 specific follow-up questions the user would naturally ask next. Questions must be grounded in the answer content. Do NOT suggest generic questions. Return ONLY a JSON array of 3 strings.';
    const messages = [
      vscode.LanguageModelChatMessage.User(
        `${systemPrompt}\n\n## User Question\n${query}\n\n## Answer\n${answerText.slice(0, 2000)}`
      ),
    ];
    const resp = await model.sendRequest(messages, {}, token);
    let raw = '';
    for await (const part of resp.text) { raw += part; }
    // Parse JSON array from response
    const jsonMatch = raw.match(/\[[\s\S]*\]/);
    if (jsonMatch) {
      const arr = JSON.parse(jsonMatch[0]);
      if (Array.isArray(arr)) {
        return arr.filter(s => typeof s === 'string' && s.trim()).slice(0, 3);
      }
    }
  } catch (_) { /* fall through to regex-based */ }
  return [];
}

// ---------------------------------------------------------------------------
// Phase 11.7: HITL Classification Confirmation
// ---------------------------------------------------------------------------
/**
 * Check if a regime classification result falls in the ambiguous range (35-64)
 * and should be confirmed by the user via Copilot Chat.
 *
 * @param {number} regimeScore  Numerical confidence score from regime classifier
 * @param {string} autoDocType  The auto-classified doc_type
 * @returns {{ isAmbiguous: boolean, suggestedChoices: string[] }}
 */
function confirmClassification(regimeScore, autoDocType) {
  const AMBIGUOUS_LOW = 35;
  const AMBIGUOUS_HIGH = 64;

  if (typeof regimeScore !== 'number') {
    return { isAmbiguous: false, suggestedChoices: [] };
  }

  const isAmbiguous = regimeScore >= AMBIGUOUS_LOW && regimeScore <= AMBIGUOUS_HIGH;

  if (!isAmbiguous) {
    return { isAmbiguous: false, suggestedChoices: [] };
  }

  // Standard doc_type choices for HITL confirmation
  const choices = [
    'Legal / Governing Doc',
    'Troubleshooting Guide',
    'Operational Procedure',
    'User Manual / Reference',
    'Skip — let system decide',
  ];

  return {
    isAmbiguous: true,
    autoDocType: autoDocType || 'UNKNOWN',
    regimeScore,
    suggestedChoices: choices,
  };
}

// ---------------------------------------------------------------------------
// Phase 11.4: Retrieval Mode Detection from Slash Commands
// ---------------------------------------------------------------------------
function detectRetrievalMode(command) {
  const modeMap = {
    'search': 'search',
    'extract': 'extract',
    'audit': 'audit',
    'summary': 'summary',
    'compare': 'compare',
    'define': 'define',
  };
  return modeMap[command] || null;
}

/**
 * Approach B: /describe_images chat command handler.
 * Lists pending images and triggers auto-description using Copilot LM API.
 * Semi-manual fallback when auto-describe during ingestion fails.
 */
async function handleDescribeImages(vscode, shared, stream, token, query) {
  const config = vscode.workspace.getConfiguration('kts');
  const sourcePath = config.get('sourceFolder') || config.get('sourcePath') || '';
  const backendChannel = config.get('backendChannel') || 'bundled';

  if (!sourcePath) {
    stream.markdown('No source folder configured. Run **KTS: Select Source Folder** first.');
    return;
  }

  stream.markdown('Checking for pending image descriptions...\n\n');

  // 1. Get pending images from backend
  let pendingData;
  try {
    pendingData = await shared.runCli({
      backendChannel,
      sourcePath,
      args: ['describe', 'pending'],
      timeoutMs: 30000,
    });
  } catch (err) {
    stream.markdown(`Failed to fetch pending images: ${err.message}`);
    return;
  }

  const documents = Array.isArray(pendingData.documents) ? pendingData.documents : [];
  if (!documents.length) {
    stream.markdown('All images have been described. No pending images found.');
    return;
  }

  // Summarize what's pending
  let totalPending = 0;
  const docSummary = documents.map(doc => {
    const count = doc.pending_count || (doc.pending_images || []).length || 0;
    totalPending += count;
    return `- **${doc.doc_id}**: ${count} image(s)`;
  }).join('\n');

  stream.markdown(`### Pending Images\n\n${totalPending} image(s) across ${documents.length} document(s):\n\n${docSummary}\n\n`);

  // 2. Auto-describe using Copilot LM API
  stream.markdown('Starting auto-description using Copilot vision model...\n\n');

  try {
    const result = await autoDescribeImages({
      vscode,
      runCli: shared.runCli,
      outputChannel: shared.outputChannel,
      sourcePath,
      backendChannel,
    });

    if (!result.modelAvailable) {
      stream.markdown(
        '**Vision model not available.** Copilot cannot describe images in this session.\n\n' +
        'Fallback options:\n' +
        '1. Run **KTS: Image Description** command to view pending images\n' +
        '2. Run **KTS: Complete Image Descriptions** to submit manual descriptions\n' +
        '3. Try again later when Copilot vision models are accessible'
      );
      return;
    }

    stream.markdown(
      `### Results\n\n` +
      `- Described: **${result.described}**\n` +
      `- Failed: **${result.failed}**\n` +
      `- Skipped: **${result.skipped}**\n\n` +
      (result.described > 0
        ? 'Descriptions have been indexed and are now searchable in KTS queries.'
        : 'No images were successfully described. Check the KTS output channel for details.')
    );
  } catch (err) {
    stream.markdown(`Auto-description failed: ${err.message}\n\nCheck the KTS output channel for details.`);
  }
}

function registerChatParticipant(vscode, context, shared) {
  if (!vscode.chat || typeof vscode.chat.createChatParticipant !== 'function') {
    shared.outputChannel.appendLine('[KTS] chat participant API not available in this VS Code build.');
    return;
  }

  // Phase 11.2: Follow-up state for the followup provider
  let _lastFollowUps = [];

  const participant = vscode.chat.createChatParticipant('kts.assistant', async (request, chatContext, stream, token) => {

    try {
      const query = (request?.prompt || '').trim();

      // --- Approach B: /describe_images command ---
      if (request?.command === 'describe_images') {
        return await handleDescribeImages(vscode, shared, stream, token, query);
      }

      // --- Phase 18: /scope command — list or target scopes ---
      if (request?.command === 'scope') {
        const scopes = shared._discoveredScopes || [];
        const indexed = scopes.filter(s => s.indexed);

        if (indexed.length === 0) {
          stream.markdown(
            'No indexed scopes discovered yet.\n\n' +
            'Run **KTS: Select Source Folder** and ingest documents first. ' +
            'Each subfolder with a `.kts/` directory becomes a scope.'
          );
          return;
        }

        // If user typed @kts /scope deal_name query, route to that scope
        if (query) {
          // Parse the first word as a potential scope slug
          const words = query.split(/\s+/);
          const candidateSlug = (words[0] || '').toLowerCase().replace(/[^a-z0-9_*]/g, '');
          const matchedScope = indexed.find(s => s.slug === candidateSlug);

          if (matchedScope) {
            // Re-route as if they used /deal_slug — fall through to normal handler
            // by setting up the same state parseCommandTokens would create
            stream.markdown(`Querying scope **${matchedScope.name}** ...\n\n`);
            // We'll let it fall through to the normal retrieval path below
            // by adjusting request-like state. For now, list and guide.
          }
        }

        // List available scopes
        let md = `### Available Knowledge Scopes\n\n`;
        md += `Use \`@kts /scope_name your question\` to target a specific scope.\n\n`;
        for (const s of indexed) {
          const dtInfo = s.docTypes && s.docTypes.length > 0
            ? ` — doc types: ${s.docTypes.join(', ')}`
            : '';
          md += `- **/${s.slug}** — ${s.name}${dtInfo}\n`;
        }
        md += `\n> **Tip:** Type \`@kts /${indexed[0].slug} your question\` to search within that scope.`;
        stream.markdown(md);
        return;
      }

      // Phase 11.6: Confirmation dialog for destructive operations
      const destructiveCommands = ['delete', 'clear-index', 'reset'];
      if (request?.command && destructiveCommands.includes(request.command)) {
        const confirmed = await vscode.window.showWarningMessage(
          `Are you sure you want to run /${request.command}? This operation cannot be undone.`,
          { modal: true },
          'Yes'
        );
        if (confirmed !== 'Yes') {
          stream.markdown('Operation cancelled.');
          return;
        }
      }

      if (!query) {
        stream.markdown('Please provide a question for KTS.');
        return;
      }

      // Phase 10.1: Track session turns and build conversation history
      _sessionTurnCount++;
      // Merge VS Code native history with our manual tracking
      const nativeHistory = buildConversationContext(chatContext, 10);
      const manualHistory = _conversationHistory.slice(-20);
      // Prefer manual history (has actual answer text); fall back to native
      const conversationHistory = manualHistory.length > 0 ? manualHistory : nativeHistory;

      // Phase 11.1: Extract #file / #selection / #editor references
      const { referenceText, sourceDocHint } = await extractReferences(request);
      let enrichedQuery = query;
      if (referenceText) {
        enrichedQuery = `${referenceText}\n\n${query}`;
      }

      // Phase 11.4: Detect retrieval mode from slash command
      const retrievalMode = detectRetrievalMode(request?.command);

      // Phase 12.2 + Phase 17 + Phase 18: Parse command tokens (modes, scopes, doc filters)
      // Always parse command tokens so scope slugs and /search work correctly.
      let scopeOverride = null;
      let docTypeFilter = null;
      let effectiveQuery = enrichedQuery;
      let compareScopes = [];
      let phase17Mode = null;
      let phase17Scopes = [];
      let phase17ExtraCliArgs = [];

      {
        // Phase 18: Build known scope slugs for compound command splitting
        const knownSlugs = (shared && shared._discoveredScopes)
          ? new Set(shared._discoveredScopes.filter(s => s.indexed).map(s => s.slug))
          : new Set();

        // Phase 18: Check if the command itself is a scope slug (e.g. /bear_stearns_2006_he1)
        // Normalize to lowercase since scope discovery lowercases slugs
        const cmdName = (request?.command || '').toLowerCase();
        const isScopeCommand = knownSlugs.has(cmdName);

        // Phase 18.1: Also parse tokens when prompt starts with / (unrecognized slash commands)
        const hasSlashInPrompt = !cmdName && enrichedQuery.trim().startsWith('/');

        if (retrievalMode || isScopeCommand || cmdName === 'search' || hasSlashInPrompt) {
          const parsed = parseCommandTokens(cmdName, enrichedQuery, knownSlugs);
          phase17Mode = parsed.mode;
          phase17Scopes = parsed.scopes;
          effectiveQuery = parsed.query || enrichedQuery;
          phase17ExtraCliArgs = buildCliArgsFromTokens(parsed);

          // If command is a scope slug, ensure it's used as scope override
          if (isScopeCommand && parsed.scopes.length === 0) {
            scopeOverride = cmdName;
          }

          // Maintain backward-compat: primary scope + docType
          if (parsed.scopes.length > 0) {
            scopeOverride = parsed.scopes[0].slug;
            docTypeFilter = parsed.scopes[0].docFilter || parsed.globalDocFilter || null;
          } else if (!scopeOverride) {
            docTypeFilter = parsed.globalDocFilter || null;
          }

          // Phase 15.1 compat: /compare populates compareScopes
          if (parsed.mode === 'compare' && parsed.scopes.length >= 2) {
            compareScopes = parsed.scopes.map(s => s.slug);
          }
        }
      }

      // Phase 11.3: Stream retrieval progress
      if (stream.progress) {
        stream.progress('Searching knowledge base...');
      }

      const { maxResults, deepMode } = extractMaxResults(request, vscode);

      // Phase 8.6: Multi-Query Expansion via LLM
      let extraQueries = [];
      try {
        // Use unified model for multi-query expansion
        const expansionModel = await selectModel(vscode, null);
        if (expansionModel) {
          const numVariants = RAG_CONFIG.multiQueryVariants;
            
          extraQueries = await expandQueryWithLLM(vscode, expansionModel, effectiveQuery, numVariants);
          if (extraQueries.length > 0 && shared.outputChannel) {
            shared.outputChannel.appendLine(`[KTS] Phase 8.6 Multi-Query: ${extraQueries.length} variant(s) generated (model: ${expansionModel.id || expansionModel.family || 'unknown'})`);
          }
        }
      } catch (_multiQueryErr) {
        // Non-fatal — proceed with single query
        if (shared.outputChannel) {
          shared.outputChannel.appendLine(`[KTS] Multi-query expansion failed: ${_multiQueryErr.message}`);
        }
      }

      const result = await ktsTool(effectiveQuery, {
        workspaceRoot: shared.workspaceRoot,
        maxResults,
        deepMode,
        docType: docTypeFilter,
        // Phase 10.1: Pass session context to backend
        sessionId: _sessionId,
        conversationHistory: conversationHistory.length > 0 ? JSON.stringify(conversationHistory) : undefined,
        retrievalMode: retrievalMode || undefined,
        scopeOverride: scopeOverride || undefined,
        // Phase 11.1: Pass source document hint to backend
        sourceDocHint: sourceDocHint || undefined,
        // Phase 8.6: Forward multi-query variants to backend
        extraQueries: extraQueries.length > 0 ? extraQueries : undefined,
        // Phase 15.1: Forward compare scopes for cross-deal comparison
        compareScopes: compareScopes.length > 0 ? compareScopes : undefined,
        // Phase 17: Forward mode, doc filter, and multi-scope args
        phase17Mode: phase17Mode || undefined,
        phase17DocFilter: docTypeFilter || undefined,
        phase17Scopes: phase17Scopes.length > 0 ? phase17Scopes.map(s => s.slug) : undefined,
        phase17ExtraCliArgs: phase17ExtraCliArgs.length > 0 ? phase17ExtraCliArgs : undefined,
      });

      // Phase 11.3: Stream post-retrieval progress
      if (stream.progress && result && result.status === 'ok') {
        const chunkCount = result.search_result?.chunks?.length
          || result.search_result?.results?.length || 0;
        if (chunkCount > 0) {
          stream.progress(`Reranking ${chunkCount} candidates...`);
        }
        stream.progress('Generating answer...');
      }

      // --- RAG Generation: synthesize answer via Copilot LLM ---
      let generated = false;
      let currentMode = 'kts';
      let model = null;  // Declared at outer scope so follow-ups can access it
      if (result && result.status === 'ok' && result.search_result) {
        model = await selectModel(vscode, request.model);
        if (model) {
          shared.outputChannel.appendLine(`[KTS] RAG generation using model: ${model.id || model.family || 'copilot'}`);
          const { mode } = selectPrompt(result);
          currentMode = mode;
          // Determine if Critique will post-process (buffer mode)
          const willPostProcess = RAG_CONFIG.critiqueEnabled;

          const genResult = await generateAnswer(vscode, model, stream, token, effectiveQuery, result, shared.outputChannel, { bufferMode: willPostProcess, conversationHistory });
          if (genResult && typeof genResult === 'object' && genResult.text) {
            generated = genResult.text;
            currentMode = genResult.mode;
          } else if (genResult && typeof genResult === 'string') {
            generated = genResult;  // Legacy path
          } else {
            generated = genResult;
          }

          // ── Unified Critique-RAG Loop ─────────────────────────────
          // Replaces old two-stage pipeline (Self-RAG → Critique).
          // Flow: Generate → Critique → if gaps → re-retrieve → re-synthesize → repeat (max 3 rounds)
          if (generated && typeof generated === 'string') {
            try {
              if (RAG_CONFIG.critiqueEnabled) {
                const critiqueModel = await selectModel(vscode, null);
                if (critiqueModel) {
                  const critiqueQuestions = _extractCritiqueQuestions(result);
                  const maxRounds = RAG_CONFIG.critiqueMaxRounds;

                  if (critiqueQuestions.length > 0) {
                    shared.outputChannel.appendLine(
                      `[KTS-CRITIQUE] Running unified critique-RAG loop: ${critiqueQuestions.length} questions, max ${maxRounds} rounds, model=${critiqueModel.id || 'unknown'}`
                    );

                    // Build retrieveFn: sub-retrieval via ktsTool for gap-filling
                    const retrieveFn = async (gapQuery, excludeIds) => {
                      try {
                        const subResult = await ktsTool(gapQuery, {
                          workspaceRoot: shared.workspaceRoot,
                          maxResults: 15,
                        });
                        let subSearch = subResult?.search_result;
                        if (subSearch && subSearch.search_result) subSearch = subSearch.search_result;
                        const chunks = (subSearch && Array.isArray(subSearch.context_chunks))
                          ? subSearch.context_chunks
                            .map(c => ({ text: c.text || c.content || '', id: c.chunk_id || c.id || '' }))
                            .filter(c => !excludeIds.includes(c.id))
                          : [];
                        return { chunks, chunkIds: chunks.map(c => c.id) };
                      } catch { return { chunks: [], chunkIds: [] }; }
                    };

                    // Use the generation prompt (full persona) for re-synthesis
                    const critiqueSystemPrompt = genResult?.prompt || (currentMode === 'legal' ? LEGAL_SYSTEM_PROMPT : KTS_SYSTEM_PROMPT);

                    const critiqueResult = await runCritiqueLoop({
                      critiqueModel,
                      userModel: model,
                      stream,
                      token,
                      query: effectiveQuery,
                      initialAnswer: generated,
                      result,
                      questions: critiqueQuestions,
                      maxRounds,
                      retrieveFn,
                      systemPrompt: critiqueSystemPrompt,
                    });

                    if (critiqueResult && critiqueResult.answer) {
                      generated = critiqueResult.answer;
                      result._critiqueTrace = critiqueResult.trace;
                      shared.outputChannel.appendLine(
                        `[KTS-CRITIQUE] Critique complete: status=${critiqueResult.trace?.status || 'done'}, ` +
                        `rounds=${critiqueResult.trace?.roundsExecuted || 0}, ` +
                        `gaps=${critiqueResult.trace?.gapsFound || 0}, ` +
                        `fixed=${critiqueResult.trace?.gapsFixed || 0}, ` +
                        `chunksRetrieved=${critiqueResult.trace?.chunksRetrieved || 0}`
                      );
                    }
                  }
                } else {
                  shared.outputChannel.appendLine('[KTS-CRITIQUE] No critique model available — skipping.');
                }
              }
            } catch (critiqueErr) {
              shared.outputChannel.appendLine(`[KTS-CRITIQUE] Critique loop failed: ${critiqueErr.message}`);
              // Non-fatal — continue with original generated answer
            }
          }
          // ── End Unified Critique-RAG Loop ─────────────────────────

          // ── Stream final answer (after all post-processing) ──────
          if (generated && typeof generated === 'string' && willPostProcess) {
            stream.markdown(generated);
          }
        } else {
          shared.outputChannel.appendLine('[KTS] No LLM model available — falling back to raw chunks.');
        }
      }

      if (generated) {
        // Append citations and trace below the generated answer
        const citations = buildCitationBlock(result);
        const trace = buildTraceBlock(result);
        if (citations || trace) {
          stream.markdown('\n\n---\n');
        }
        if (citations) stream.markdown(citations);
        if (trace) stream.markdown(trace);

        // Phase 13.1: Confidence tier display
        const confidenceBlock = buildConfidenceBlock(result);
        if (confidenceBlock) stream.markdown(confidenceBlock);

        // Phase 13.2: Gap alert display
        const gapBlock = buildGapAlertBlock(result);
        if (gapBlock) stream.markdown(gapBlock);

        // Phase 15.1: Comparison table display
        const comparisonBlock = buildComparisonBlock(result);
        if (comparisonBlock) stream.markdown(comparisonBlock);

        // Phase 15.4: Anomaly badge display
        const anomalyBlock = buildAnomalyBlock(result);
        if (anomalyBlock) stream.markdown(anomalyBlock);

        // Phase 17: Diff mode results
        const diffBlock = buildDiffBlock(result);
        if (diffBlock) stream.markdown(diffBlock);

        // Phase 17: Aggregate mode results
        const aggregateBlock = buildAggregateBlock(result);
        if (aggregateBlock) stream.markdown(aggregateBlock);

        // Phase 17: Multi-scope attribution
        const multiScopeBlock = buildMultiScopeAttribution(result);
        if (multiScopeBlock) stream.markdown(multiScopeBlock);

        // Phase 14.3: Extraction result display
        const extractionBlock = buildExtractionBlock(result);
        if (extractionBlock) stream.markdown(extractionBlock);

        // Phase 14.4: Summary result display
        const summaryBlock = buildSummaryBlock(result);
        if (summaryBlock) stream.markdown(summaryBlock);

        // Phase 11.2: Follow-up suggestions (context-aware)
        // Try LLM-generated follow-ups first, fall back to regex patterns
        let followUps = [];
        if (generated && model) {
          try {
            followUps = await generateLLMFollowUps(vscode, model, token, effectiveQuery, generated, currentMode);
          } catch (_) { /* fall back to regex */ }
        }
        if (followUps.length === 0) {
          followUps = buildFollowUpSuggestions(effectiveQuery, result, currentMode, generated);
        }
        if (followUps.length > 0) {
          // Store follow-ups for native followup provider (no markdown rendering)
          _lastFollowUps = followUps.map(prompt => ({ prompt }));
        }
      } else {
        // Fallback: return raw retrieved chunks (pre-RAG behavior)
        stream.markdown(toMarkdown(result));
      }

      // Phase 10.1: Update conversation history after turn
      _conversationHistory.push({
        role: 'user',
        content: effectiveQuery,
        turn: _sessionTurnCount,
        timestamp: Date.now(),
      });
      if (generated) {
        // Phase 10.1: Store actual answer text for coreference resolution
        const answerContent = typeof generated === 'string'
          ? generated.slice(0, 2000)  // Cap at 2000 chars to keep history compact
          : `[Generated answer for: ${effectiveQuery}]`;
        _conversationHistory.push({
          role: 'assistant',
          content: answerContent,
          turn: _sessionTurnCount,
          timestamp: Date.now(),
        });
      }
    } catch (error) {
      if (token?.isCancellationRequested) {
        return;
      }
      stream.markdown(`KTS failed to process the request: ${error.message}`);
    }
  });

  // Phase 11.2: Follow-Up Provider — renders clickable suggestion chips
  participant.followupProvider = {
    provideFollowups(_result, _context, _token) {
      return _lastFollowUps;
    },
  };

  // Phase 11.6: Confirmation dialogs for destructive operations
  participant.onDidReceiveFeedback(() => {
    // Placeholder: feedback handling can be extended for analytics
  });

  context.subscriptions.push(participant);

  // Phase 12.2: Expose participant reference for dynamic scope command registration
  if (shared) {
    shared._chatParticipant = participant;

    // Phase 18: Store base commands from package.json for merging with dynamic scopes.
    // These are the static commands declared in contributes.chatParticipants[].commands.
    shared._baseCommands = [
      { name: 'search',          description: 'Retrieve concise context and citations' },
      { name: 'deep',            description: 'Retrieve more context chunks for complex issues' },
      { name: 'describe_images', description: 'Describe pending images using Copilot vision (fallback for auto-describe)' },
      { name: 'define',          description: 'Look up a defined term and its closure chain' },
      { name: 'extract',         description: 'Extract structured fields (parties, dates, amounts) from the current scope' },
      { name: 'compare',         description: 'Compare a concept across multiple deals side-by-side' },
      { name: 'audit',           description: 'Generate a topic-clustering audit with risk tags' },
      { name: 'summary',         description: 'Generate a fixed 5-section deal summary' },
      { name: 'scope',           description: 'List available knowledge scopes or target a specific scope' },
    ];
  }
}

// ---------------------------------------------------------------------------
// Phase 8.3 — Token-Aware Context Trimming
// ---------------------------------------------------------------------------
const TOKEN_RATIO = 4;             // ~4 chars per token (English text heuristic)
const RESERVED_TOKENS = 5000;      // reserved for system prompt + history + answer

/**
 * Trim context blocks to fit within a token budget.
 * Blocks are kept in priority order; once the budget is exhausted the
 * remaining blocks are dropped and a truncation indicator is appended.
 *
 * @param {Array<{text: string}>} blocks - context blocks (each must have .text)
 * @param {number} maxTokens - total token budget for the model
 * @returns {Array<{text: string}>} trimmed blocks (may include truncation indicator)
 */
function trimContextToTokenBudget(blocks, maxTokens) {
  if (!blocks || blocks.length === 0) return [];

  const budget = maxTokens - RESERVED_TOKENS;
  if (budget <= 0) return [];

  let usedTokens = 0;
  const kept = [];

  for (const block of blocks) {
    const txt = block.text || '';
    const tokens = Math.ceil(txt.length / TOKEN_RATIO);

    if (usedTokens + tokens <= budget) {
      kept.push(block);
      usedTokens += tokens;
    } else {
      // Partial fit: include as much as possible
      const remainingChars = (budget - usedTokens) * TOKEN_RATIO;
      if (remainingChars > 40) {
        kept.push({ ...block, text: txt.slice(0, remainingChars) + '\n[...truncated]' });
      }
      kept.push({ text: `[Context trimmed: ${blocks.length - kept.length} block(s) omitted to fit token budget]` });
      break;
    }
  }

  return kept;
}

module.exports = {
  registerChatParticipant,
  toMarkdown,
  // Exported for testing
  selectPrompt,
  buildContextBlock,
  buildLegalContextBlock,
  selectChatModel,
  selectReasoningModel,
  generateAnswer,
  KTS_SYSTEM_PROMPT,
  LEGAL_SYSTEM_PROMPT,
  // Phase 10-15 helpers
  buildConfidenceBlock,
  buildGapAlertBlock,
  buildComparisonBlock,
  buildAnomalyBlock,
  buildExtractionBlock,
  buildSummaryBlock,
  buildFollowUpSuggestions,
  getTemporalContextForPrompt,
  detectRetrievalMode,
  // Phase 17 additions
  buildDiffBlock,
  buildAggregateBlock,
  buildMultiScopeAttribution,
  // Phase 10.1 additions
  buildConversationContext,
  // Phase 11 additions
  extractReferences,
  confirmClassification,
  FOLLOW_UP_PATTERNS,
  _extractAnswerText,
  // Phase 9 additions
  _extractCritiqueQuestions,
  // Phase 8 additions
  trimContextToTokenBudget,
  TOKEN_RATIO,
  RESERVED_TOKENS,
  // Unified model & config exports
  RAG_CONFIG,
  selectModel,
  computeTokenBudget,
  computeMaxChunks,
  // Knowledge preamble (glossary + entity roles)
  buildKnowledgePreamble,
};
