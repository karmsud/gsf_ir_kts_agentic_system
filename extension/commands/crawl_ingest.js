const path = require('path');
const fs = require('fs');

/**
 * Crawl + Ingest Command (Combined)
 * Legacy command that runs both crawl and ingest sequentially
 */
module.exports = async function crawlIngest({ vscode, outputChannel, runCli } = {}) {
  const config = vscode.workspace.getConfiguration('kts');
  const sourcePath = config.get('sourcePath');
  const kbWorkspacePath = config.get('kbWorkspacePath');
  const backendChannel = config.get('backendChannel') || 'bundled';

  // If no source path configured, prompt for one
  let targetPath = sourcePath;
  
  if (!targetPath) {
    const input = await vscode.window.showInputBox({
      prompt: 'Enter file or folder path to crawl and ingest',
      value: 'tests/fixtures/simple',
      ignoreFocusOut: true,
    });

    if (!input) {
      return { cancelled: true };
    }
    
    targetPath = input;
  }

  if (!fs.existsSync(targetPath)) {
    vscode.window.showErrorMessage(`Path does not exist: ${targetPath}`);
    return { error: 'Path not found' };
  }

  outputChannel.appendLine(`[KTS Crawl+Ingest] Target: ${targetPath}`);
  outputChannel.show(true);

  try {
    // Crawl
    outputChannel.appendLine('[KTS] Running crawl...');
    const crawlResult = await runCli({ 
      backendChannel,
      kbWorkspacePath,
      sourcePath: targetPath,
      args: ['crawl', '--paths', targetPath],
      timeoutMs: 180000,
    });
    outputChannel.appendLine(JSON.stringify(crawlResult, null, 2));

    // Ingest
    outputChannel.appendLine('[KTS] Running ingest...');
    const ingestResult = await runCli({ 
      backendChannel,
      kbWorkspacePath,
      sourcePath: targetPath,
      args: ['ingest', '--paths', targetPath],
      timeoutMs: 300000,
    });
    outputChannel.appendLine(JSON.stringify(ingestResult, null, 2));

    const ingestedCount = ingestResult.count
      || (Array.isArray(ingestResult.ingested) ? ingestResult.ingested.length : 0)
      || ingestResult.ingested_count
      || 0;
    vscode.window.showInformationMessage(`KTS crawl+ingest complete. Ingested ${ingestedCount} document(s).`);

    return { crawl: crawlResult, ingest: ingestResult };
  } catch (error) {
    outputChannel.appendLine(`[ERROR] ${error.message}`);
    vscode.window.showErrorMessage(`KTS Crawl+Ingest failed: ${error.message}`);
    throw error;
  }
};
