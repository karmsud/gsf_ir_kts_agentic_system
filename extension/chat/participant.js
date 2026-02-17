const ktsTool = require('../copilot/kts_tool');
const { autoDescribeImages } = require('../lib/image_describer');

function toMarkdown(result) {
  if (!result || result.status !== 'ok' || !result.search_result) {
    return `KTS retrieval failed.\n\n${result?.error ? `Error: ${result.error}` : 'No result returned.'}`;
  }

  const search = result.search_result;
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
  ].filter(Boolean).join('\n');
}

function extractMaxResults(request) {
  const command = request?.command;
  if (!command || typeof command !== 'string') {
    return { maxResults: 5, deepMode: false };
  }

  if (command === 'deep') {
    return { maxResults: 10, deepMode: true };
  }
  return { maxResults: 5, deepMode: false };
}

/**
 * Approach B: /describe_images chat command handler.
 * Lists pending images and triggers auto-description using Copilot LM API.
 * Semi-manual fallback when auto-describe during ingestion fails.
 */
async function handleDescribeImages(vscode, shared, stream, token, query) {
  const config = vscode.workspace.getConfiguration('kts');
  const sourcePath = config.get('sourcePath') || '';
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

  const participant = vscode.chat.createChatParticipant('kts.assistant', async (request, _chatContext, stream, token) => {
    try {
      const query = (request?.prompt || '').trim();

      // --- Approach B: /describe_images command ---
      if (request?.command === 'describe_images') {
        return await handleDescribeImages(vscode, shared, stream, token, query);
      }

      if (!query) {
        stream.markdown('Please provide a question for KTS.');
        return;
      }

      const { maxResults, deepMode } = extractMaxResults(request);
      const result = await ktsTool(query, {
        workspaceRoot: shared.workspaceRoot,
        maxResults,
        deepMode,
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
