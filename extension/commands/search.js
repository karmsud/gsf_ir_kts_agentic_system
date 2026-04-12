/**
 * Search Command
 * Interactive search with query input
 */
module.exports = async function search({ vscode, outputChannel, runCli } = {}) {
  const config = vscode.workspace.getConfiguration('kts');
  const sourcePath = config.get('sourceFolder');
  const kbWorkspacePath = config.get('kbWorkspacePath');
  const backendChannel = config.get('backendChannel') || 'bundled';

  if (!sourcePath) {
    vscode.window.showWarningMessage('Please set source path first (KTS: Select Source Folder)');
    return { error: 'No source path configured' };
  }

  const query = await vscode.window.showInputBox({
    prompt: 'Enter search query',
    placeHolder: 'e.g., How do I configure BatchBridge connector?',
    ignoreFocusOut: true,
  });

  if (!query) {
    return { cancelled: true };
  }

  outputChannel.appendLine(`\n[KTS Search] Query: "${query}"`);
  outputChannel.appendLine(`[KTS Search] Searching indexed documents...`);
  outputChannel.show(true);

  return vscode.window.withProgress({
    location: vscode.ProgressLocation.Notification,
    title: 'KTS Search',
    cancellable: false
  }, async (progress) => {
    progress.report({ message: 'Searching...' });

    try {
      const result = await runCli({
        backendChannel,
        kbWorkspacePath,
        sourcePath,
        args: ['search', query, '--max-results', '5'],
        timeoutMs: 60000,
      });

      // Handle both wrapped and unwrapped result structures
      const searchResult = result.search_result || result;
      const chunks = Array.isArray(searchResult.context_chunks) ? searchResult.context_chunks : [];
      const confidence = searchResult.confidence;
      
      outputChannel.appendLine(`[KTS Search] Found ${chunks.length} result(s) (confidence: ${confidence?.toFixed(2) || 'n/a'})`);
      
      if (chunks.length > 0) {
        outputChannel.appendLine(`[KTS Search] Top result from: ${chunks[0].doc_name || chunks[0].doc_id || 'unknown'}`);
      }
      
      vscode.window.showInformationMessage(`KTS Search: ${chunks.length} result(s) found.`);
      
      return result;
    } catch (error) {
      outputChannel.appendLine(`[KTS Search] ERROR: ${error.message}`);
      vscode.window.showErrorMessage(`KTS Search failed: ${error.message}`);
      throw error;
    }
  });
};
