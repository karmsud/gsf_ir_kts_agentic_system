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

  const args = ['search', query, '--max-results', String(maxResults)];
  if (options.docType) {
    args.push('--doc-type', String(options.docType));
  }
  if (options.toolFilter) {
    args.push('--tool-filter', String(options.toolFilter));
  }

  try {
    const searchResult = await runCliJson({ workspaceRoot, args });
    return {
      tool: '@kts',
      status: 'ok',
      query,
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
