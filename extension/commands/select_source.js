const fs = require('fs');
const path = require('path');
const { autoDescribeImages } = require('../lib/image_describer');

/**
 * Select Source Folder Command
 * Lets user select the network/local folder containing raw KB documents.
 * Automatically runs crawl + freshness check + ingest after selection.
 */
module.exports = async function selectSource({ vscode, outputChannel, runCli } = {}) {
  const config = vscode.workspace.getConfiguration('kts');
  const currentPath = config.get('sourcePath') || '';
  const backendChannel = config.get('backendChannel') || 'bundled';

  const options = {
    canSelectFiles: false,
    canSelectFolders: true,
    canSelectMany: false,
    openLabel: 'Select Source Folder',
    defaultUri: currentPath ? vscode.Uri.file(currentPath) : undefined,
  };

  const dialogResult = await vscode.window.showOpenDialog(options);

  if (!dialogResult || dialogResult.length === 0) {
    return { cancelled: true };
  }

  const selectedPath = dialogResult[0].fsPath;

  // Graceful network/path check
  if (!fs.existsSync(selectedPath)) {
    vscode.window.showErrorMessage(`Cannot reach source folder: ${selectedPath}. Check the path or network connection.`);
    return { error: 'Source path unreachable' };
  }

  // Save source path
  await config.update('sourcePath', selectedPath, vscode.ConfigurationTarget.Global);
  outputChannel.appendLine(`\n${'='.repeat(60)}`);
  outputChannel.appendLine(`[KTS] Source folder selected: ${selectedPath}`);
  outputChannel.appendLine(`[KTS] Knowledge base will be stored at: ${path.join(selectedPath, '.kts')}`);
  outputChannel.appendLine(`${'='.repeat(60)}\n`);
  outputChannel.show(true);

  // KB index lives at <sourcePath>/.kts/
  const ktsDir = path.join(selectedPath, '.kts');
  const ktsExists = fs.existsSync(ktsDir);

  // Run the indexing pipeline with progress indicator
  return vscode.window.withProgress({
    location: vscode.ProgressLocation.Notification,
    title: 'KTS Knowledge Base',
    cancellable: false
  }, async (progress) => {
    try {
      // Step 1: Crawl (detects new/modified/deleted files)
      progress.report({ message: 'Scanning for documents...' });
      outputChannel.appendLine('[KTS] Step 1/3: Crawling source folder...');
      outputChannel.appendLine('[KTS] Looking for supported file types (.doc, .docx, .pdf, .md, .txt, etc.)');
      
      const crawlResult = await runCli({
        backendChannel,
        sourcePath: selectedPath,
        args: ['crawl', '--paths', selectedPath],
        timeoutMs: 3600000, // 1 hour
      });

      const changes = crawlResult.changes || {};
      const newCount = changes.new_files?.length || 0;
      const modifiedCount = changes.modified_files?.length || 0;
      const deletedCount = changes.deleted_files?.length || 0;
      const unchangedCount = changes.unchanged_files || 0;
      const totalScanned = newCount + modifiedCount + unchangedCount;

      outputChannel.appendLine(`[KTS] Crawl complete:`);
      outputChannel.appendLine(`      - New files: ${newCount}`);
      outputChannel.appendLine(`      - Modified: ${modifiedCount}`);
      outputChannel.appendLine(`      - Deleted: ${deletedCount}`);
      outputChannel.appendLine(`      - Unchanged: ${unchangedCount}`);

      // Step 2: Decide if ingestion is needed
      const needsIngest = newCount > 0 || modifiedCount > 0 || deletedCount > 0 || !ktsExists;

      if (!needsIngest) {
        outputChannel.appendLine(`\n[KTS] Index is up to date. No ingestion needed.`);
        outputChannel.appendLine(`[KTS] Ready for queries! Use @kts in chat or run KTS: Search.\n`);
        vscode.window.showInformationMessage(
          `KTS: Index is up to date (${unchangedCount} doc(s))`
        );
        return { sourcePath: selectedPath, crawl: crawlResult, upToDate: true };
      }

      // Step 3: Auto-ingest
      progress.report({ message: `Indexing ${newCount + modifiedCount} document(s)...` });
      outputChannel.appendLine(`\n[KTS] Step 2/3: Ingesting documents...`);
      outputChannel.appendLine(`[KTS] This includes: text extraction, chunking, embedding, and graph building.`);
      outputChannel.appendLine(`[KTS] Please wait - this may take a few minutes for large documents.\n`);

      const ingestResult = await runCli({
        backendChannel,
        sourcePath: selectedPath,
        args: ['ingest', '--paths', selectedPath],
        timeoutMs: 3600000, // 1 hour
      });

      const ingestedCount = ingestResult.count
        || (Array.isArray(ingestResult.ingested) ? ingestResult.ingested.length : 0)
        || 0;

      const totalChunks = (ingestResult.ingested || []).reduce((sum, doc) => sum + (doc.chunk_count || 0), 0);
      const corpusRegime = ingestResult.corpus_regime || 'unknown';

      outputChannel.appendLine(`[KTS] Ingestion complete:`);
      outputChannel.appendLine(`      - Documents indexed: ${ingestedCount}`);
      outputChannel.appendLine(`      - Total chunks created: ${totalChunks}`);
      outputChannel.appendLine(`      - Detected corpus type: ${corpusRegime}`);

      const totalImagesPending = ingestResult.total_images_pending || 0;

      // Step 4: Auto-describe extracted images (Approach C)
      if (totalImagesPending > 0) {
        progress.report({ message: `Describing ${totalImagesPending} image(s)...` });
        outputChannel.appendLine(`\n[KTS] Step 3/3: Processing extracted images...`);
        outputChannel.appendLine(`[KTS] Found ${totalImagesPending} image(s) that need descriptions for searchability.\n`);
        
        try {
          const descResult = await autoDescribeImages({
            vscode,
            runCli,
            outputChannel,
            sourcePath: selectedPath,
            backendChannel,
          });

          if (descResult.modelAvailable && descResult.described > 0) {
            outputChannel.appendLine(`[KTS] Image descriptions complete: ${descResult.described} processed.`);
            vscode.window.showInformationMessage(
              `KTS: Auto-described ${descResult.described} image(s). ${descResult.failed ? descResult.failed + ' failed.' : ''}`
            );
          } else if (!descResult.modelAvailable) {
            outputChannel.appendLine(`[KTS] Vision model not available. Use @kts /describe_images in chat to describe images manually.`);
            vscode.window.showInformationMessage(
              `KTS: ${totalImagesPending} image(s) extracted. Use @kts /describe_images in chat to describe them.`
            );
          }
        } catch (descErr) {
          outputChannel.appendLine(`[KTS] Auto-describe skipped (non-blocking): ${descErr.message}`);
        }
      } else {
        outputChannel.appendLine(`\n[KTS] Step 3/3: No images to process.`);
      }

      // Summary
      outputChannel.appendLine(`\n${'='.repeat(60)}`);
      outputChannel.appendLine(`[KTS] Indexing complete!`);
      outputChannel.appendLine(`[KTS] Your knowledge base is ready at: ${ktsDir}`);
      outputChannel.appendLine(`[KTS] Try: @kts <your question> in GitHub Copilot Chat`);
      outputChannel.appendLine(`${'='.repeat(60)}\n`);

      vscode.window.showInformationMessage(
        `KTS: Indexed ${ingestedCount} document(s) with ${totalChunks} searchable chunks`
      );

      return { sourcePath: selectedPath, crawl: crawlResult, ingest: ingestResult };
    } catch (error) {
      outputChannel.appendLine(`\n[KTS] ERROR: ${error.message}`);
      outputChannel.appendLine(`[KTS] Check the output above for details.\n`);
      vscode.window.showErrorMessage(`KTS: Auto-indexing failed: ${error.message}`);
      return { sourcePath: selectedPath, error: error.message };
    }
  });
};
