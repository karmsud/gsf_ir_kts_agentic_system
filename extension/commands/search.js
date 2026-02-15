/**
 * Search Command
 * Interactive search with query input
 */
module.exports = async function search({ vscode, outputChannel, runCli } = {}) {
  const config = vscode.workspace.getConfiguration('kts');
  const sourcePath = config.get('sourcePath');
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

  outputChannel.appendLine(`[KTS Search] Query: ${query}`);
  outputChannel.show(true);

  try {
    const result = await runCli({
      backendChannel,
      kbWorkspacePath,
      sourcePath,
      args: ['search', '--query', query, '--top-k', '5'],
      timeoutMs: 60000,
    });

    outputChannel.appendLine(JSON.stringify(result, null, 2));
    
    const hitCount = result.results?.length || 0;
    vscode.window.showInformationMessage(`KTS Search: ${hitCount} result(s) found.`);
    
    return result;
  } catch (error) {
    outputChannel.appendLine(`[ERROR] ${error.message}`);
    vscode.window.showErrorMessage(`KTS Search failed: ${error.message}`);
    throw error;
  }
};
