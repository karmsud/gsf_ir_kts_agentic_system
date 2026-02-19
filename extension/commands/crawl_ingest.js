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

  outputChannel.appendLine(`\n[KTS Crawl+Ingest] Target: ${targetPath}`);
  outputChannel.show(true);

  return vscode.window.withProgress({
    location: vscode.ProgressLocation.Notification,
    title: 'KTS Crawl+Ingest',
    cancellable: false
  }, async (progress) => {
    try {
      // Crawl
      const INGEST_TIMEOUT_MS = 60 * 60 * 1000; // 1 hour fixed
      const crawlTimeout = INGEST_TIMEOUT_MS;
      const ingestTimeout = INGEST_TIMEOUT_MS;
      outputChannel.appendLine(`[KTS] Timeout: 60 min (fixed 1 hour)`);

      progress.report({ message: 'Scanning for documents...' });
      outputChannel.appendLine('[KTS] Step 1/2: Running crawl...');
      const crawlResult = await runCli({ 
        backendChannel,
        kbWorkspacePath,
        sourcePath: targetPath,
        args: ['crawl', '--paths', targetPath],
        timeoutMs: crawlTimeout,
      });

      const changes = crawlResult.changes || {};
      const newCount = changes.new_files?.length || 0;
      const modifiedCount = changes.modified_files?.length || 0;
      outputChannel.appendLine(`[KTS] Crawl complete: ${newCount} new, ${modifiedCount} modified`);

      // Ingest
      progress.report({ message: `Indexing documents (timeout: ${ingestMin} min)...` });
      outputChannel.appendLine('[KTS] Step 2/2: Running ingest...');
      const ingestResult = await runCli({ 
        backendChannel,
        kbWorkspacePath,
        sourcePath: targetPath,
        args: ['ingest', '--paths', targetPath],
        timeoutMs: ingestTimeout,
      });

      const ingestedCount = ingestResult.count
        || (Array.isArray(ingestResult.ingested) ? ingestResult.ingested.length : 0)
        || ingestResult.ingested_count
        || 0;
      
      const totalChunks = (ingestResult.ingested || []).reduce((sum, doc) => sum + (doc.chunk_count || 0), 0);
      
      outputChannel.appendLine(`[KTS] Ingest complete: ${ingestedCount} document(s), ${totalChunks} chunks`);
      vscode.window.showInformationMessage(`KTS: Indexed ${ingestedCount} document(s) with ${totalChunks} chunks.`);

      return { crawl: crawlResult, ingest: ingestResult };
    } catch (error) {
      outputChannel.appendLine(`[KTS] ERROR: ${error.message}`);
      vscode.window.showErrorMessage(`KTS Crawl+Ingest failed: ${error.message}`);
      throw error;
    }
  });
};
