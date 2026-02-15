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
  outputChannel.appendLine(`[KTS] Source path updated: ${selectedPath}`);
  outputChannel.show(true);

  // KB index lives at <sourcePath>/.kts/
  const ktsDir = path.join(selectedPath, '.kts');
  const ktsExists = fs.existsSync(ktsDir);

  try {
    // Step 1: Crawl (detects new/modified/deleted files)
    outputChannel.appendLine('[KTS] Running auto-crawl...');
    const crawlResult = await runCli({
      backendChannel,
      sourcePath: selectedPath,
      args: ['crawl', '--paths', selectedPath],
      timeoutMs: 180000,
    });
    outputChannel.appendLine(JSON.stringify(crawlResult, null, 2));

    const changes = crawlResult.changes || {};
    const newCount = changes.new_files?.length || 0;
    const modifiedCount = changes.modified_files?.length || 0;
    const deletedCount = changes.deleted_files?.length || 0;
    const unchangedCount = changes.unchanged_files || 0;
    const totalScanned = newCount + modifiedCount + unchangedCount;

    // Step 2: Decide if ingestion is needed
    const needsIngest = newCount > 0 || modifiedCount > 0 || deletedCount > 0 || !ktsExists;

    if (!needsIngest) {
      // Index is current — no ingestion needed
      vscode.window.showInformationMessage(
        `KTS: Index is up to date (${unchangedCount} doc(s), last indexed at ${ktsDir})`
      );
      outputChannel.appendLine(`[KTS] Index up to date. No ingestion needed.`);
      return { sourcePath: selectedPath, crawl: crawlResult, upToDate: true };
    }

    // Step 3: Auto-ingest
    outputChannel.appendLine(`[KTS] Changes detected: ${newCount} new, ${modifiedCount} modified, ${deletedCount} deleted. Running auto-ingest...`);
    const ingestResult = await runCli({
      backendChannel,
      sourcePath: selectedPath,
      args: ['ingest', '--paths', selectedPath],
      timeoutMs: 300000,
    });
    outputChannel.appendLine(JSON.stringify(ingestResult, null, 2));

    const ingestedCount = ingestResult.count
      || (Array.isArray(ingestResult.ingested) ? ingestResult.ingested.length : 0)
      || 0;

    const totalImagesPending = ingestResult.total_images_pending || 0;

    vscode.window.showInformationMessage(
      `KTS: Indexed ${ingestedCount} document(s) (${newCount} new, ${modifiedCount} updated, ${deletedCount} removed)`
    );

    // Step 4: Auto-describe extracted images (Approach C)
    if (totalImagesPending > 0) {
      outputChannel.appendLine(`[KTS] ${totalImagesPending} image(s) pending description. Starting auto-describe...`);
      try {
        const descResult = await autoDescribeImages({
          vscode,
          runCli,
          outputChannel,
          sourcePath: selectedPath,
          backendChannel,
        });

        if (descResult.modelAvailable && descResult.described > 0) {
          vscode.window.showInformationMessage(
            `KTS: Auto-described ${descResult.described} image(s). ${descResult.failed ? descResult.failed + ' failed.' : ''}`
          );
        } else if (!descResult.modelAvailable) {
          vscode.window.showInformationMessage(
            `KTS: ${totalImagesPending} image(s) extracted. Use @kts /describe_images in chat to describe them.`
          );
        }
      } catch (descErr) {
        outputChannel.appendLine(`[KTS] Auto-describe failed (non-blocking): ${descErr.message}`);
        // Non-blocking — images are saved as pending for manual fallback
      }
    }

    return { sourcePath: selectedPath, crawl: crawlResult, ingest: ingestResult };
  } catch (error) {
    outputChannel.appendLine(`[KTS] Auto crawl+ingest failed: ${error.message}`);
    vscode.window.showErrorMessage(`KTS: Auto-indexing failed: ${error.message}`);
    return { sourcePath: selectedPath, error: error.message };
  }
};
