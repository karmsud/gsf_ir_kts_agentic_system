const path = require('path');
const fs = require('fs');

/**
 * Ingest Command
 * Ingests discovered documents into the KB
 */
module.exports = async function ingest({ vscode, outputChannel, runCli } = {}) {
  const config = vscode.workspace.getConfiguration('kts');
  const sourcePath = config.get('sourcePath');
  const kbWorkspacePath = config.get('kbWorkspacePath');
  const backendChannel = config.get('backendChannel') || 'bundled';

  if (!sourcePath) {
    vscode.window.showWarningMessage('Please set source path first (KTS: Select Source Folder)');
    return { error: 'No source path configured' };
  }

  outputChannel.appendLine(`[KTS Ingest] Source: ${sourcePath}`);
  outputChannel.show(true);

  try {
    const result = await runCli({
      backendChannel,
      kbWorkspacePath,
      sourcePath,
      args: ['ingest', '--paths', sourcePath],
      timeoutMs: 300000,
    });

    outputChannel.appendLine(JSON.stringify(result, null, 2));
    
    const ingestedCount = result.ingested_count || result.count || 0;
    vscode.window.showInformationMessage(`KTS Ingest complete: ${ingestedCount} document(s) ingested.`);
    
    return result;
  } catch (error) {
    outputChannel.appendLine(`[ERROR] ${error.message}`);
    vscode.window.showErrorMessage(`KTS Ingest failed: ${error.message}`);
    throw error;
  }
};
