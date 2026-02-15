const path = require('path');
const fs = require('fs');

/**
 * Crawl Command
 * Crawls the configured source path for documents
 */
module.exports = async function crawl({ vscode, outputChannel, runCli } = {}) {
  const config = vscode.workspace.getConfiguration('kts');
  const sourcePath = config.get('sourcePath');
  const kbWorkspacePath = config.get('kbWorkspacePath');
  const backendChannel = config.get('backendChannel') || 'bundled';

  if (!sourcePath) {
    vscode.window.showWarningMessage('Please set source path first (KTS: Select Source Folder)');
    return { error: 'No source path configured' };
  }

  if (!fs.existsSync(sourcePath)) {
    vscode.window.showErrorMessage(`Source path does not exist: ${sourcePath}`);
    return { error: 'Source path not found' };
  }

  outputChannel.appendLine(`[KTS Crawl] Source: ${sourcePath}`);
  outputChannel.show(true);

  try {
    const result = await runCli({
      backendChannel,
      kbWorkspacePath,
      sourcePath,
      args: ['crawl', '--paths', sourcePath],
      timeoutMs: 180000,
    });

    outputChannel.appendLine(JSON.stringify(result, null, 2));
    
    const filesFound = result.files_found || result.count || 0;
    vscode.window.showInformationMessage(`KTS Crawl complete: ${filesFound} file(s) discovered.`);
    
    return result;
  } catch (error) {
    outputChannel.appendLine(`[ERROR] ${error.message}`);
    vscode.window.showErrorMessage(`KTS Crawl failed: ${error.message}`);
    throw error;
  }
};
