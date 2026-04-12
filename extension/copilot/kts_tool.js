const { runCliJson, getWorkspaceRoot } = require('../lib/kts_backend');

module.exports = async function ktsTool(query, options = {}) {
  if (!query || typeof query !== 'string') {
    return {
      tool: '@kts',
      status: 'error',
      error: 'Query text is required.',
    };
  }

  const workspaceRoot = getWorkspaceRoot(options.workspaceRoot);
  const maxResults = Number.isInteger(options.maxResults) ? options.maxResults : 5;

  // Resolve source path for .kts/ derivation
  let sourcePath = options.sourcePath;
  if (!sourcePath) {
    try {
      const vscode = require('vscode');
      const config = vscode.workspace.getConfiguration('kts');
      sourcePath = config.get('sourceFolder') || config.get('sourcePath');
    } catch (_) {
      // vscode API may not be available in tests
    }
  }

  const args = ['search', query, '--max-results', String(maxResults)];
  if (options.deepMode) {
    args.push('--deep');
  }
  if (options.docType) {
    args.push('--doc-type', String(options.docType));
  }
  if (options.toolFilter) {
    args.push('--tool-filter', String(options.toolFilter));
  }
  // Phase 10.1: Forward session context to backend
  if (options.sessionId) {
    args.push('--session-id', String(options.sessionId));
  }
  if (options.conversationHistory) {
    args.push('--conversation-history', String(options.conversationHistory));
  }
  if (options.retrievalMode) {
    args.push('--retrieval-mode', String(options.retrievalMode));
  }
  if (options.scopeOverride) {
    args.push('--scope-override', String(options.scopeOverride));
  }
  if (options.sourceDocHint) {
    args.push('--source-doc-hint', String(options.sourceDocHint));
  }
  // Phase 8.6: Forward multi-query variants to backend
  if (options.extraQueries && Array.isArray(options.extraQueries) && options.extraQueries.length > 0) {
    args.push('--extra-queries', JSON.stringify(options.extraQueries));
  }
  // Phase 15.1: Forward compare scopes for /compare mode
  if (options.compareScopes && Array.isArray(options.compareScopes) && options.compareScopes.length > 0) {
    args.push('--compare-scopes', options.compareScopes.join(','));
  }
  // Phase 17: Forward mode, doc-filter, and multi-scope CLI args
  if (options.phase17Mode) {
    args.push('--mode', String(options.phase17Mode));
  }
  if (options.phase17DocFilter) {
    args.push('--doc-filter', String(options.phase17DocFilter));
  }
  if (options.phase17Scopes && Array.isArray(options.phase17Scopes) && options.phase17Scopes.length > 0) {
    args.push('--scopes', options.phase17Scopes.join(','));
  }
  // Also forward any extra CLI args built by the Phase 17 token parser
  if (options.phase17ExtraCliArgs && Array.isArray(options.phase17ExtraCliArgs)) {
    args.push(...options.phase17ExtraCliArgs);
  }
  // VS Code Settings pass-through: retrieval pool, HyDE, BM25, Phase 19, etc.
  // These override backend defaults to match user's VS Code setting values.
  if (options.backendSettingsArgs && Array.isArray(options.backendSettingsArgs) && options.backendSettingsArgs.length > 0) {
    args.push(...options.backendSettingsArgs);
  }

  try {
    const searchResult = await runCliJson({ workspaceRoot, sourcePath, args });
    return {
      tool: '@kts',
      status: 'ok',
      query,
      deep_mode: !!options.deepMode,
      search_result: searchResult,
    };
  } catch (error) {
    return {
      tool: '@kts',
      status: 'error',
      query,
      error: error.message,
    };
  }
};
