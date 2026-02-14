const ktsTool = require('../copilot/kts_tool');

function toMarkdown(result) {
  if (!result || result.status !== 'ok' || !result.search_result) {
    return `KTS retrieval failed.\n\n${result?.error ? `Error: ${result.error}` : 'No result returned.'}`;
  }

  const search = result.search_result;
  const chunks = Array.isArray(search.context_chunks) ? search.context_chunks : [];
  const citations = Array.isArray(search.citations) ? search.citations : [];

  if (!chunks.length) {
    return 'No matching KTS context was found for this query. Try adding product/tool names or error codes.';
  }

  const summary = chunks
    .slice(0, 5)
    .map((chunk, index) => `### Context ${index + 1}\n${chunk.content}`)
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
  return [
    `KTS retrieved context (confidence: ${confidence}).`,
    '',
    summary,
    '',
    '### Citations',
    citationMd || 'No citations returned.',
  ].join('\n');
}

function extractMaxResults(request) {
  const command = request?.command;
  if (!command || typeof command !== 'string') {
    return 5;
  }

  if (command === 'deep') {
    return 8;
  }
  return 5;
}

function registerChatParticipant(vscode, context, shared) {
  if (!vscode.chat || typeof vscode.chat.createChatParticipant !== 'function') {
    shared.outputChannel.appendLine('[KTS] chat participant API not available in this VS Code build.');
    return;
  }

  const participant = vscode.chat.createChatParticipant('kts.assistant', async (request, _chatContext, stream, token) => {
    try {
      const query = (request?.prompt || '').trim();
      if (!query) {
        stream.markdown('Please provide a question for KTS.');
        return;
      }

      const maxResults = extractMaxResults(request);
      const result = await ktsTool(query, {
        workspaceRoot: shared.workspaceRoot,
        maxResults,
      });

      stream.markdown(toMarkdown(result));
    } catch (error) {
      if (token?.isCancellationRequested) {
        return;
      }
      stream.markdown(`KTS failed to process the request: ${error.message}`);
    }
  });

  context.subscriptions.push(participant);
}

module.exports = {
  registerChatParticipant,
  toMarkdown,
};
