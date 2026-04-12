/**
 * Phase 10 — Concept Vocabulary LLM Client (JavaScript side)
 *
 * Handles the LLM enrichment phase for concept vocabulary during
 * ingestion.  Selects a Copilot model, extracts defined terms from the
 * graph (via CLI), batches them to the LLM for synonym generation,
 * and writes results back to the graph (via CLI).
 *
 * This is a separate module from critique_client.js so the two can be
 * customised independently.
 *
 * Two-phase flow (JS orchestrates, Python does the graph I/O):
 *   1. CLI: `enrich-vocabulary extract-terms`  → JSON {terms: {name: excerpt}}
 *   2. JS:  batch terms → Copilot LLM → collect synonyms
 *   3. CLI: `enrich-vocabulary apply-synonyms --synonyms-file <path>`
 */

const vscode = require('vscode');
const fs = require('fs');
const path = require('path');

// ── Model selection (separate from critique) ─────────────────────

/**
 * Select a Copilot model for concept vocabulary enrichment.
 * Preference chain: gpt-4.1 → gpt-4o → gpt-4o-mini → any.
 *
 * @returns {Promise<import('vscode').LanguageModelChat | null>}
 */
async function selectConceptModel() {
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

// ── Prompt templates ─────────────────────────────────────────────

const TERM_SYNONYM_PROMPT = `For each defined term below, list 5-8 alternate search keywords or phrases (synonyms, abbreviations, related concepts, plural forms) a reader might use when searching for information about this concept.

Terms:
{TERMS}

Return ONLY valid JSON — no markdown fences, no explanation:
{"Term Name": ["keyword1", "keyword2", ...], ...}`;

/**
 * Per-definition focused keyword prompt.  One call per term so keywords
 * are tightly scoped to the *specific meaning* of that definition rather
 * than being diluted across a batch of 17 unrelated terms.
 */
const PER_TERM_KEYWORD_PROMPT = `You are indexing a financial/legal document for full-text search.

Defined term: "{TERM_NAME}"
Definition excerpt: "{DEFINITION}"

List 5-8 specific search keywords or short phrases that a reader would type when looking up THIS particular concept only (not other terms).
Think: synonyms, abbreviations, plain-English paraphrases, related financial/legal jargon.

Return ONLY a valid JSON array — no markdown fences, no explanation:
["keyword1", "keyword2", ...]`;

// ── Core: generate synonyms via Copilot LLM ─────────────────────

/**
 * Generate synonym keywords for defined terms using the Copilot LLM.
 *
 * @param {Object<string, string>} terms - {termName: definitionExcerpt}
 * @param {import('vscode').LanguageModelChat} model - Selected Copilot model
 * @param {import('vscode').OutputChannel} outputChannel
 * @param {number} batchSize - Terms per LLM call (default 17)
 * @returns {Promise<Object<string, string[]>>} {termName: [synonym1, ...]}
 */
async function generateTermSynonyms(terms, model, outputChannel, batchSize = 17) {
  const termEntries = Object.entries(terms);
  const allSynonyms = {};

  if (termEntries.length === 0) {
    return allSynonyms;
  }

  outputChannel.appendLine(
    `[KTS-CONCEPT] Generating synonyms for ${termEntries.length} defined terms ` +
    `in batches of ${batchSize} using ${model.id || 'copilot'}`
  );

  for (let i = 0; i < termEntries.length; i += batchSize) {
    const batch = termEntries.slice(i, i + batchSize);
    const numbered = batch
      .map(([name], idx) => `${idx + 1}. ${name}`)
      .join('\n');

    const prompt = TERM_SYNONYM_PROMPT.replace('{TERMS}', numbered);

    try {
      const messages = [vscode.LanguageModelChatMessage.User(prompt)];
      const response = await model.sendRequest(messages, {}, new vscode.CancellationTokenSource().token);

      // Collect streamed response
      let fullText = '';
      for await (const chunk of response.text) {
        fullText += chunk;
      }

      const parsed = parseJsonResponse(fullText);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        for (const [termName, synonyms] of Object.entries(parsed)) {
          if (Array.isArray(synonyms)) {
            allSynonyms[termName] = synonyms.map(s => String(s));
          }
        }
      }

      outputChannel.appendLine(
        `[KTS-CONCEPT] Batch ${Math.floor(i / batchSize) + 1}: ` +
        `${batch.length} terms → ${Object.keys(parsed || {}).length} synonym sets`
      );
    } catch (err) {
      outputChannel.appendLine(
        `[KTS-CONCEPT] Batch ${Math.floor(i / batchSize) + 1} failed: ${err.message}`
      );
      // Continue with remaining batches
    }
  }

  outputChannel.appendLine(
    `[KTS-CONCEPT] Generated synonyms for ${Object.keys(allSynonyms).length}/${termEntries.length} terms`
  );

  return allSynonyms;
}

// ── Per-term keyword generation (Q1) ────────────────────────────

/**
 * Generate focused keywords for each defined term using ONE LLM call
 * per term (not batched).  Keywords capture the specific meaning of
 * each definition, not just synonyms.
 *
 * @param {Object<string, string>} terms - {termName: definitionExcerpt}
 * @param {import('vscode').LanguageModelChat} model
 * @param {import('vscode').OutputChannel} outputChannel
 * @returns {Promise<Object<string, string[]>>} {termName: [keyword1, ...]}
 */
async function generatePerTermKeywords(terms, model, outputChannel) {
  const termEntries = Object.entries(terms);
  const allKeywords = {};

  if (termEntries.length === 0) {
    return allKeywords;
  }

  outputChannel.appendLine(
    `[KTS-CONCEPT] Generating per-definition keywords for ${termEntries.length} terms ` +
    `(1 call per term — ${model.id || 'copilot'})`
  );

  let succeeded = 0;
  let failed = 0;

  for (const [termName, definitionExcerpt] of termEntries) {
    // Trim definition to ~400 chars for prompt efficiency
    const defTrimmed = (definitionExcerpt || '').trim().slice(0, 400);
    if (!defTrimmed) {
      continue;
    }

    const prompt = PER_TERM_KEYWORD_PROMPT
      .replace('{TERM_NAME}', termName)
      .replace('{DEFINITION}', defTrimmed);

    try {
      const messages = [vscode.LanguageModelChatMessage.User(prompt)];
      const response = await model.sendRequest(
        messages,
        {},
        new vscode.CancellationTokenSource().token
      );

      let fullText = '';
      for await (const chunk of response.text) {
        fullText += chunk;
      }

      const parsed = parseJsonResponse(fullText);
      if (Array.isArray(parsed) && parsed.length > 0) {
        allKeywords[termName] = parsed.map(k => String(k).trim()).filter(Boolean);
        succeeded++;
      } else {
        failed++;
      }
    } catch (err) {
      outputChannel.appendLine(
        `[KTS-CONCEPT] Per-term keywords failed for "${termName}": ${err.message}`
      );
      failed++;
    }
  }

  outputChannel.appendLine(
    `[KTS-CONCEPT] Per-term keywords: ${succeeded} succeeded, ${failed} failed ` +
    `out of ${termEntries.length} terms`
  );

  return allKeywords;
}

// ── Orchestrator: full enrichment flow ───────────────────────────

/**
 * Run the full concept vocabulary LLM enrichment pipeline.
 *
 * 1. Extract terms from graph via CLI
 * 2. Generate synonyms via Copilot LLM
 * 3. Write synonyms back to graph via CLI
 *
 * @param {Function} runCli - The runCliJson function from kts_backend.js
 * @param {Object} cliOptions - Base options for runCli (backendChannel, kbWorkspacePath, sourcePath)
 * @param {import('vscode').OutputChannel} outputChannel
 * @returns {Promise<{success: boolean, termsProcessed: number, synonymsGenerated: number}>}
 */
async function enrichVocabulary(runCli, cliOptions, outputChannel) {
  const result = { success: false, termsProcessed: 0, synonymsGenerated: 0 };

  try {
    // Step 1: Select model
    const model = await selectConceptModel();
    if (!model) {
      outputChannel.appendLine(
        '[KTS-CONCEPT] WARNING: No Copilot model available — ' +
        'concept vocabulary will use deterministic-only extraction'
      );
      result.success = true; // Not a failure — graph already has deterministic keywords
      return result;
    }

    outputChannel.appendLine(`[KTS-CONCEPT] Using model: ${model.id || 'copilot'}`);

    // Step 2: Extract terms from graph
    outputChannel.appendLine('[KTS-CONCEPT] Extracting defined terms from graph...');
    const extractResult = await runCli({
      ...cliOptions,
      args: ['enrich-vocabulary', 'extract-terms'],
      timeoutMs: 60000,
    });

    const terms = extractResult?.terms;
    const termCount = extractResult?.count || 0;

    if (!terms || termCount === 0) {
      outputChannel.appendLine('[KTS-CONCEPT] No defined terms found in graph — skipping LLM enrichment');
      result.success = true;
      return result;
    }

    outputChannel.appendLine(`[KTS-CONCEPT] Found ${termCount} defined terms`);
    result.termsProcessed = termCount;

    // Step 3: Generate synonyms via LLM
    const synonyms = await generateTermSynonyms(terms, model, outputChannel);
    result.synonymsGenerated = Object.keys(synonyms).length;

    if (Object.keys(synonyms).length === 0) {
      outputChannel.appendLine('[KTS-CONCEPT] No synonyms generated — skipping apply step');
      result.success = true;
      return result;
    }

    // Step 4: Write synonyms to temp file and apply via CLI
    const kbPath = cliOptions.kbWorkspacePath
      || (cliOptions.sourcePath ? require('path').join(cliOptions.sourcePath, '.kts') : null);

    if (!kbPath) {
      outputChannel.appendLine('[KTS-CONCEPT] ERROR: Cannot determine KB path for synonym file');
      return result;
    }

    const synonymsFile = path.join(kbPath, '_concept_synonyms.json');
    fs.writeFileSync(synonymsFile, JSON.stringify(synonyms, null, 2), 'utf-8');
    outputChannel.appendLine(`[KTS-CONCEPT] Wrote ${Object.keys(synonyms).length} synonym sets to ${synonymsFile}`);

    const applyResult = await runCli({
      ...cliOptions,
      args: ['enrich-vocabulary', 'apply-synonyms', '--synonyms-file', synonymsFile],
      timeoutMs: 60000,
    });

    outputChannel.appendLine(
      `[KTS-CONCEPT] Applied: ${applyResult?.terms_matched || 0} terms matched, ` +
      `${applyResult?.keywords_added || 0} keywords added`
    );

    // Clean up temp file
    try { fs.unlinkSync(synonymsFile); } catch (_) { /* ignore */ }

    // Step 5: Generate per-definition keywords (Q1 — 1 LLM call per term)
    outputChannel.appendLine('[KTS-CONCEPT] Step 5: Generating per-definition keywords...');
    const termKeywords = await generatePerTermKeywords(terms, model, outputChannel);

    if (Object.keys(termKeywords).length > 0) {
      const termKwFile = path.join(kbPath, '_term_keywords.json');
      fs.writeFileSync(termKwFile, JSON.stringify(termKeywords, null, 2), 'utf-8');

      const applyKwResult = await runCli({
        ...cliOptions,
        args: ['enrich-vocabulary', 'apply-term-keywords', '--keywords-file', termKwFile],
        timeoutMs: 60000,
      });

      outputChannel.appendLine(
        `[KTS-CONCEPT] Term keywords applied: ` +
        `${applyKwResult?.terms_matched || 0} terms, ` +
        `${applyKwResult?.keywords_stored || 0} keywords stored`
      );

      try { fs.unlinkSync(termKwFile); } catch (_) { /* ignore */ }
    } else {
      outputChannel.appendLine('[KTS-CONCEPT] No per-term keywords generated — skipping apply step');
    }

    result.success = true;
    return result;

  } catch (err) {
    outputChannel.appendLine(`[KTS-CONCEPT] Enrichment failed: ${err.message}`);
    return result;
  }
}

// ── JSON parsing helper ──────────────────────────────────────────

/**
 * Parse a JSON response from the LLM, tolerating markdown fences.
 * @param {string} text
 * @returns {any}
 */
function parseJsonResponse(text) {
  let cleaned = (text || '').trim();

  // Strip markdown code fences
  if (cleaned.startsWith('```')) {
    const lines = cleaned.split('\n');
    const filtered = lines.filter(l => !l.trim().startsWith('```'));
    cleaned = filtered.join('\n').trim();
  }

  try {
    return JSON.parse(cleaned);
  } catch {
    // Try to find the first { or [ and parse from there
    const braceIdx = cleaned.indexOf('{');
    const bracketIdx = cleaned.indexOf('[');
    const start = Math.max(0,
      braceIdx >= 0 && bracketIdx >= 0 ? Math.min(braceIdx, bracketIdx) :
      braceIdx >= 0 ? braceIdx : bracketIdx
    );
    if (start > 0 || braceIdx === 0 || bracketIdx === 0) {
      try {
        return JSON.parse(cleaned.slice(start));
      } catch {
        // fall through
      }
    }
    return null;
  }
}

module.exports = {
  selectConceptModel,
  generateTermSynonyms,
  generatePerTermKeywords,
  enrichVocabulary,
  parseJsonResponse,
};
