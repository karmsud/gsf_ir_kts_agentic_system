/**
 * Status Command
 * Shows KB status and manifest information
 */
module.exports = async function status({ vscode, outputChannel, runCli } = {}) {
  const config = vscode.workspace.getConfiguration('kts');
  const kbWorkspacePath = config.get('kbWorkspacePath');
  const backendChannel = config.get('backendChannel') || 'bundled';

  outputChannel.appendLine('[KTS Status] Retrieving KB status...');
  outputChannel.show(true);

  try {
    const result = await runCli({
      backendChannel,
      kbWorkspacePath,
      args: ['status'],
      timeoutMs: 30000,
    });

    outputChannel.appendLine(JSON.stringify(result, null, 2));
    
    const summary = `KB Status: ${result.document_count || 0} docs, ${result.total_chunks || 0} chunks`;
    vscode.window.showInformationMessage(summary);
    
    return result;
  } catch (error) {
    outputChannel.appendLine(`[ERROR] ${error.message}`);
    vscode.window.showErrorMessage(`KTS Status failed: ${error.message}`);
    throw error;
  }
};
