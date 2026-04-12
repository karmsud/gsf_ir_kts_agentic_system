/**
 * kts_settings.js — VS Code Settings Reader for KTS
 *
 * Reads all `kts.*` workspace settings and returns a structured config
 * object.  Replaces the hardcoded RAG_CONFIG constant in participant.js.
 *
 * Usage:
 *   const { loadKtsSettings, getBackendCliArgs } = require('../lib/kts_settings');
 *   const settings = loadKtsSettings(vscode);
 *   const mode = 'legal';  // or 'kts' (non-legal)
 *   const cliArgs = getBackendCliArgs(settings, mode);
 */

'use strict';

/**
 * Read all KTS tuning settings from VS Code workspace configuration.
 * Returns a flat config object with legal/non-legal variants where applicable.
 *
 * @param {object} vscode  The VS Code API object (passed in from extension host)
 * @returns {KtsSettings}  Structured settings object
 */
function loadKtsSettings(vscode) {
  let cfg;
  try {
    cfg = vscode.workspace.getConfiguration('kts');
  } catch (_) {
    // Fallback when called outside VS Code (e.g., test environment)
    cfg = { get: (key, def) => def };
  }

  const g = (key, def) => {
    try { return cfg.get(key, def); }
    catch (_) { return def; }
  };

  // ── Models ────────────────────────────────────────────────────────────────
  const critiqueModel    = g('models.critiqueModel', 'auto');
  const queryExpModel    = g('models.queryExpansionModel', 'auto');

  // ── Multi-Query Expansion & HyDE ─────────────────────────────────────────
  const multiQueryEnabledLegal    = g('rag.multiQuery.enabledForLegal', false);
  const multiQueryEnabledNonLegal = g('rag.multiQuery.enabledForNonLegal', false);
  const multiQueryVariants        = g('rag.multiQuery.variants', 1);
  const hydeEnabledLegal          = g('rag.hyde.enabledForLegal', false);
  const hydeEnabledNonLegal       = g('rag.hyde.enabledForNonLegal', false);

  // ── Retrieval Pool ────────────────────────────────────────────────────────
  const legalItemsTopK      = g('retrieval.legal.itemsTopK', 20);
  const legalSectionsTopK   = g('retrieval.legal.sectionsTopK', 8);
  const nonLegalItemsTopK   = g('retrieval.nonLegal.itemsTopK', 12);
  const nonLegalSectionsTopK = g('retrieval.nonLegal.sectionsTopK', 5);
  const maxContextChunks    = g('retrieval.maxContextChunks', 20);

  // ── Cross-Encoder ─────────────────────────────────────────────────────────
  const crossEncoderEnabled        = g('retrieval.crossEncoder.enabled', true);
  const crossEncoderPoolLegal      = g('retrieval.crossEncoder.poolSizeLegal', 20);
  const crossEncoderPoolNonLegal   = g('retrieval.crossEncoder.poolSizeNonLegal', 12);

  // ── BM25 Hybrid ───────────────────────────────────────────────────────────
  const bm25Enabled = g('retrieval.bm25.enabled', true);
  const bm25Weight  = g('retrieval.bm25.weight', 0.4);
  const bm25K1      = g('retrieval.bm25.k1', 1.5);
  const bm25B       = g('retrieval.bm25.b', 0.75);

  // ── Critique Loop ─────────────────────────────────────────────────────────
  const critiqueEnabledLegal     = g('critique.enabledForLegal', true);
  const critiqueEnabledNonLegal  = g('critique.enabledForNonLegal', false);
  const critiqueMaxRoundsLegal   = g('critique.maxRoundsLegal', 1);
  const critiqueMaxRoundsNonLegal = g('critique.maxRoundsNonLegal', 1);
  const critiqueRestartOnGap     = g('critique.restartOnGap', false);
  const critiqueConfidenceExit   = g('critique.confidenceExit', 0.9);
  const critiqueMaxQuestionsPerRound = g('critique.maxQuestionsPerRound', 3);

  // ── CRAG ──────────────────────────────────────────────────────────────────
  const cragEnabledLegal         = g('crag.enabledForLegal', false);
  const cragEnabledNonLegal      = g('crag.enabledForNonLegal', false);
  const cragMaxClaims            = g('crag.maxClaims', 5);
  const cragEvidenceTopK         = g('crag.evidenceTopK', 5);
  const cragAllowReRetrieval     = g('crag.allowBackendReRetrieval', false);
  const cragDropContradicted     = g('crag.dropContradicted', true);
  const cragFlagNoEvidence       = g('crag.flagNoEvidence', true);

  // ── Phase 19 / Non-Legal Triple Store ────────────────────────────────────
  const phase19TripleStore          = g('phase19.tripleStoreEnabled', true);
  const phase19ErrorBoundary        = g('phase19.errorBoundaryChunking', true);
  const phase19Sentence             = g('phase19.sentenceLevelChunking', true);
  const phase19Structure            = g('phase19.structureAwareChunking', true);
  const phase19TroubleshootingGraph = g('phase19.troubleshootingGraphEnabled', true);

  // ── Chunking ──────────────────────────────────────────────────────────────
  const legalChunkSize     = g('chunking.legalChunkSize', 3000);
  const legalChunkOverlap  = g('chunking.legalChunkOverlap', 500);
  const nonLegalChunkSize  = g('chunking.nonLegalChunkSize', 1000);
  const nonLegalChunkOverlap = g('chunking.nonLegalChunkOverlap', 200);
  const cchEnabled         = g('chunking.cchEnabled', true);

  // ── Context Window ────────────────────────────────────────────────────────
  const ctxMaxChunks        = g('context.maxChunksInPrompt', 25);
  const ctxTokenUtilization = g('context.tokenBudgetUtilization', 0.8);
  const ctxReservedTokens   = g('context.reservedTokens', 5000);

  return {
    // — Models
    critiqueModel,
    queryExpansionModel: queryExpModel,

    // — Multi-Query (JS side)
    multiQueryEnabledLegal,
    multiQueryEnabledNonLegal,
    multiQueryVariants,

    // — HyDE (backend)
    hydeEnabledLegal,
    hydeEnabledNonLegal,

    // — Retrieval pool (backend)
    legalItemsTopK,
    legalSectionsTopK,
    nonLegalItemsTopK,
    nonLegalSectionsTopK,
    maxContextChunks: Math.min(maxContextChunks, ctxMaxChunks),

    // — Cross-encoder (backend)
    crossEncoderEnabled,
    crossEncoderPoolLegal,
    crossEncoderPoolNonLegal,

    // — BM25 (backend)
    bm25Enabled,
    bm25Weight,
    bm25K1,
    bm25B,

    // — Critique loop (JS side)
    critiqueEnabledLegal,
    critiqueEnabledNonLegal,
    critiqueMaxRoundsLegal,
    critiqueMaxRoundsNonLegal,
    critiqueRestartOnGap,
    critiqueConfidenceExit,
    critiqueMaxQuestionsPerRound,

    // — CRAG (JS side)
    cragEnabledLegal,
    cragEnabledNonLegal,
    cragMaxClaims,
    cragEvidenceTopK,
    cragAllowReRetrieval,
    cragDropContradicted,
    cragFlagNoEvidence,

    // — Phase 19 (backend)
    phase19TripleStore,
    phase19ErrorBoundary,
    phase19Sentence,
    phase19Structure,
    phase19TroubleshootingGraph,

    // — Chunking (backend, affects ingest only — stored for CLI pass-through)
    legalChunkSize,
    legalChunkOverlap,
    nonLegalChunkSize,
    nonLegalChunkOverlap,
    cchEnabled,

    // — Context window (JS side)
    tokenBudgetUtilization: ctxTokenUtilization,
    reservedTokens: ctxReservedTokens,
  };
}

/**
 * Return mode-specific convenience accessors for a loaded settings object.
 * mode: 'legal' | 'kts'  (as returned by selectPrompt())
 *
 * @param {object} settings  Result of loadKtsSettings()
 * @param {string} mode      'legal' or 'kts'
 * @returns {KtsModeSettings}
 */
function settingsForMode(settings, mode) {
  const isLegal = mode === 'legal';
  return {
    // Multi-query
    multiQueryEnabled: isLegal ? settings.multiQueryEnabledLegal : settings.multiQueryEnabledNonLegal,
    multiQueryVariants: settings.multiQueryVariants,

    // Retrieval pool
    itemsTopK: isLegal ? settings.legalItemsTopK : settings.nonLegalItemsTopK,
    sectionsTopK: isLegal ? settings.legalSectionsTopK : settings.nonLegalSectionsTopK,
    crossEncoderPool: isLegal ? settings.crossEncoderPoolLegal : settings.crossEncoderPoolNonLegal,

    // HyDE
    hydeEnabled: isLegal ? settings.hydeEnabledLegal : settings.hydeEnabledNonLegal,

    // Critique
    critiqueEnabled:  isLegal ? settings.critiqueEnabledLegal  : settings.critiqueEnabledNonLegal,
    critiqueMaxRounds: isLegal ? settings.critiqueMaxRoundsLegal : settings.critiqueMaxRoundsNonLegal,
    ...pickCritique(settings),

    // CRAG
    cragEnabled: isLegal ? settings.cragEnabledLegal : settings.cragEnabledNonLegal,
    ...pickCrag(settings),

    // Context
    maxContextChunks: settings.maxContextChunks,
  };
}

function pickCritique(s) {
  return {
    critiqueRestartOnGap: s.critiqueRestartOnGap,
    critiqueConfidenceExit: s.critiqueConfidenceExit,
    critiqueMaxQuestionsPerRound: s.critiqueMaxQuestionsPerRound,
  };
}

function pickCrag(s) {
  return {
    cragMaxClaims: s.cragMaxClaims,
    cragEvidenceTopK: s.cragEvidenceTopK,
    cragAllowReRetrieval: s.cragAllowReRetrieval,
    cragDropContradicted: s.cragDropContradicted,
    cragFlagNoEvidence: s.cragFlagNoEvidence,
  };
}

/**
 * Build CLI arg array for the kts-backend `search` command based on the
 * current settings and retrieval mode.
 *
 * @param {object} settings  Result of loadKtsSettings()
 * @param {string} mode      'legal' or 'kts'
 * @returns {string[]}       CLI args to append to the search command
 */
function getBackendCliArgs(settings, mode) {
  const ms = settingsForMode(settings, mode);
  const args = [];

  // Retrieval pool
  args.push('--guide-items-top-k', String(ms.itemsTopK));
  args.push('--guide-sections-top-k', String(ms.sectionsTopK));

  // HyDE
  if (!ms.hydeEnabled) {
    args.push('--no-hyde');
  }

  // Cross-encoder
  if (!settings.crossEncoderEnabled) {
    args.push('--no-cross-encoder');
  } else {
    args.push('--cross-encoder-pool', String(ms.crossEncoderPool));
  }

  // BM25
  if (!settings.bm25Enabled) {
    args.push('--no-bm25');
  } else {
    args.push('--bm25-weight', String(settings.bm25Weight));
    args.push('--bm25-k1', String(settings.bm25K1));
    args.push('--bm25-b', String(settings.bm25B));
  }

  // Phase 19 (non-legal triple store)
  if (!settings.phase19TripleStore || mode === 'legal') {
    args.push('--no-triple-store');
  }
  if (!settings.phase19TroubleshootingGraph || mode === 'legal') {
    args.push('--no-troubleshooting-graph');
  }

  // CCH
  if (!settings.cchEnabled) {
    args.push('--no-cch');
  }

  return args;
}

/**
 * Effective multi-query variant count for a given set of settings and mode.
 * Returns 0 if multi-query is disabled for this mode.
 *
 * @param {object} settings
 * @param {string|null} mode  'legal' | 'kts' | null (unknown — pre-retrieval)
 * @returns {number}
 */
function effectiveMultiQueryVariants(settings, mode) {
  if (mode === 'legal' && !settings.multiQueryEnabledLegal) return 0;
  if (mode === 'kts'   && !settings.multiQueryEnabledNonLegal) return 0;
  if (mode === null) {
    // Pre-retrieval: enable if EITHER legal or non-legal has it on
    if (!settings.multiQueryEnabledLegal && !settings.multiQueryEnabledNonLegal) return 0;
  }
  return settings.multiQueryVariants;
}

module.exports = {
  loadKtsSettings,
  settingsForMode,
  getBackendCliArgs,
  effectiveMultiQueryVariants,
};
