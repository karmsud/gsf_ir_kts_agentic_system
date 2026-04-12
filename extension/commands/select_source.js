const fs = require('fs');
const path = require('path');
const { autoDescribeImages } = require('../lib/image_describer');

const INGEST_TIMEOUT_MS = 60 * 60 * 1000; // 1 hour

/**
 * Select Source Folder Command
 *
 * Lets the user select the folder containing raw KB documents and saves it as
 * the active knowledge source (kts.sourceFolder).  After selection the user
 * chooses how to index:
 *
 *   • Crawl + Ingest  — detect new/modified/deleted files, then index changes
 *   • Ingest Only     — index every document in the folder (full re-index)
 *   • Save Only       — save the path and index later via KTS: Crawl & Ingest
 *                       or KTS: Ingest
 *
 * No fallback paths are used.  Every other KTS command that requires a source
 * folder will fail with a clear message if this command has not been run first.
 */
module.exports = async function selectSource({ vscode, outputChannel, runCli } = {}) {
  const config = vscode.workspace.getConfiguration('kts');
  const currentPath = config.get('sourceFolder') || '';
  const backendChannel = config.get('backendChannel') || 'bundled';

  // ── Step 1: Folder picker ───────────────────────────────────────
  const dialogResult = await vscode.window.showOpenDialog({
    canSelectFiles: false,
    canSelectFolders: true,
    canSelectMany: false,
    openLabel: 'Select Source Folder',
    defaultUri: currentPath ? vscode.Uri.file(currentPath) : undefined,
  });

  if (!dialogResult || dialogResult.length === 0) {
    return { cancelled: true };
  }

  const selectedPath = dialogResult[0].fsPath;

  if (!fs.existsSync(selectedPath)) {
    vscode.window.showErrorMessage(`Cannot reach source folder: ${selectedPath}. Check the path or network connection.`);
    return { error: 'Source path unreachable' };
  }

  // ── Step 2: Persist path ────────────────────────────────────────
  await config.update('sourceFolder', selectedPath, vscode.ConfigurationTarget.Global);
  // Phase 12.2: Set knowledgeSourceRoot for scope discovery (subfolders with .kts/)
  await config.update('knowledgeSourceRoot', selectedPath, vscode.ConfigurationTarget.Global);
  outputChannel.appendLine(`\n${'='.repeat(60)}`);
  outputChannel.appendLine(`[KTS] Source folder selected: ${selectedPath}`);
  outputChannel.appendLine(`[KTS] Knowledge base will be stored at: ${path.join(selectedPath, '.kts')}`);
  outputChannel.appendLine(`[KTS] Scope discovery root: ${selectedPath}`);
  outputChannel.appendLine(`${'='.repeat(60)}\n`);
  outputChannel.show(true);

  // ── Step 3: Let user choose how to index ───────────────────────
  const choice = await vscode.window.showQuickPick(
    [
      {
        label: '$(sync) Crawl + Ingest',
        description: 'Scan for new/modified/deleted files, then index changes',
        value: 'crawl_ingest',
      },
      {
        label: '$(database) Ingest Only',
        description: 'Index all documents in the folder directly (full re-index)',
        value: 'ingest_only',
      },
      {
        label: '$(check) Save Selection Only',
        description: 'Save folder path and index later',
        value: 'save_only',
      },
    ],
    {
      placeHolder: 'How would you like to index this folder?',
      ignoreFocusOut: true,
    }
  );

  if (!choice || choice.value === 'save_only') {
    outputChannel.appendLine('[KTS] Source folder saved. Run "KTS: Crawl & Ingest" or "KTS: Ingest" when ready.');
    vscode.window.showInformationMessage('KTS: Source folder saved. Use "KTS: Crawl & Ingest" or "KTS: Ingest" to index.');
    return { sourcePath: selectedPath, indexed: false };
  }

  // ── Step 4: Execute chosen indexing operation ─────────────────
  return vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: 'KTS Knowledge Base', cancellable: false },
    async (progress) => {
      try {
        if (choice.value === 'crawl_ingest') {
          return await _crawlThenIngest(vscode, outputChannel, progress, runCli, config, backendChannel, selectedPath);
        }
        if (choice.value === 'ingest_only') {
          return await _ingestOnly(vscode, outputChannel, progress, runCli, backendChannel, selectedPath);
        }
      } catch (error) {
        outputChannel.appendLine(`\n[KTS] ERROR: ${error.message}`);
        vscode.window.showErrorMessage(`KTS: Indexing failed: ${error.message}`);
        return { sourcePath: selectedPath, error: error.message };
      }
    }
  );
};

// ---------------------------------------------------------------------------
// Crawl → HITL doc-type → Ingest → Image descriptions
// ---------------------------------------------------------------------------
async function _crawlThenIngest(vscode, outputChannel, progress, runCli, config, backendChannel, sourcePath) {
  progress.report({ message: 'Scanning for documents...' });
  outputChannel.appendLine('[KTS] Step 1/3: Crawling source folder...');
  outputChannel.appendLine('[KTS] Looking for supported file types (.doc, .docx, .pdf, .md, .txt, etc.)');

  const crawlResult = await runCli({
    backendChannel,
    sourcePath,
    args: ['crawl', '--paths', sourcePath],
    timeoutMs: INGEST_TIMEOUT_MS,
  });

  const changes = crawlResult.changes || {};
  const newCount = changes.new_files?.length || 0;
  const modifiedCount = changes.modified_files?.length || 0;
  const deletedCount = changes.deleted_files?.length || 0;
  const unchangedCount = changes.unchanged_files || 0;

  outputChannel.appendLine(`[KTS] Crawl complete: ${newCount} new, ${modifiedCount} modified, ${deletedCount} deleted, ${unchangedCount} unchanged`);

  // ── Phase 18: Skip ingest if nothing changed ───────────────────
  if (newCount + modifiedCount === 0) {
    outputChannel.appendLine('[KTS] No new or modified files detected — skipping ingest.');
    const msg = deletedCount > 0
      ? `KTS: No documents to ingest (${deletedCount} deleted, ${unchangedCount} unchanged).`
      : `KTS: All ${unchangedCount} document(s) are up-to-date — nothing to ingest.`;
    vscode.window.showInformationMessage(msg);

    // Still refresh scopes in case .kts/ folders were created by prior runs
    try { await vscode.commands.executeCommand('kts.refreshScopes'); } catch (_) {}

    return { sourcePath, crawl: crawlResult, ingest: { skipped: true, reason: 'no_changes' } };
  }

  // HITL classification for ambiguous document types
  const hitlEnabled = config.get('hitlClassificationEnabled', true);
  const ingestArgs = ['ingest', '--paths', sourcePath];
  if (hitlEnabled && crawlResult?.regime_scores) {
    for (const docScore of crawlResult.regime_scores) {
      if (docScore.score >= 35 && docScore.score <= 64) {
        const docType = await vscode.window.showQuickPick(
          ['Legal / Governing Doc', 'Troubleshooting Guide', 'Operational Procedure', 'User Manual / Reference', 'Skip \u2014 let system decide'],
          { placeHolder: `Ambiguous doc type for "${docScore.filename}" (score: ${docScore.score}). What kind of document is this?` }
        );
        if (docType && docType !== 'Skip \u2014 let system decide') {
          const typeMap = {
            'Legal / Governing Doc': 'GOVERNING_DOC_LEGAL',
            'Troubleshooting Guide': 'GENERIC_GUIDE',
            'Operational Procedure': 'GENERIC_GUIDE',
            'User Manual / Reference': 'GENERIC_GUIDE',
          };
          ingestArgs.push('--doc-type', typeMap[docType] || 'GENERIC_GUIDE');
        }
        break;
      }
    }
  }

  progress.report({ message: 'Indexing documents...' });
  outputChannel.appendLine('[KTS] Step 2/3: Ingesting documents...');

  const ingestResult = await runCli({
    backendChannel,
    sourcePath,
    args: ingestArgs,
    timeoutMs: INGEST_TIMEOUT_MS,
  });

  return _finishIngest(vscode, outputChannel, progress, runCli, backendChannel, sourcePath, ingestResult, crawlResult);
}

// ---------------------------------------------------------------------------
// Ingest all documents directly (no crawl / change detection)
// ---------------------------------------------------------------------------
async function _ingestOnly(vscode, outputChannel, progress, runCli, backendChannel, sourcePath) {
  progress.report({ message: 'Indexing all documents...' });
  outputChannel.appendLine('[KTS] Step 1/2: Ingesting all documents in folder...');

  const ingestResult = await runCli({
    backendChannel,
    sourcePath,
    args: ['ingest', '--paths', sourcePath],
    timeoutMs: INGEST_TIMEOUT_MS,
  });

  return _finishIngest(vscode, outputChannel, progress, runCli, backendChannel, sourcePath, ingestResult, null);
}

// ---------------------------------------------------------------------------
// Shared completion — log counts, auto-describe images, show summary
// ---------------------------------------------------------------------------
async function _finishIngest(vscode, outputChannel, progress, runCli, backendChannel, sourcePath, ingestResult, crawlResult) {
  const ingestedCount = ingestResult.count
    || (Array.isArray(ingestResult.ingested) ? ingestResult.ingested.length : 0)
    || 0;
  const totalChunks = (ingestResult.ingested || []).reduce((sum, doc) => sum + (doc.chunk_count || 0), 0);
  const corpusRegime = ingestResult.corpus_regime || 'unknown';

  outputChannel.appendLine(`[KTS] Ingestion complete:`);
  outputChannel.appendLine(`      - Documents indexed: ${ingestedCount}`);
  outputChannel.appendLine(`      - Total chunks: ${totalChunks}`);
  outputChannel.appendLine(`      - Detected corpus type: ${corpusRegime}`);

  // Auto-describe extracted images
  const totalImagesPending = ingestResult.total_images_pending || 0;
  if (totalImagesPending > 0) {
    progress.report({ message: `Describing ${totalImagesPending} image(s)...` });
    outputChannel.appendLine(`[KTS] Step 3/3: Processing ${totalImagesPending} extracted image(s)...`);
    try {
      const descResult = await autoDescribeImages({ vscode, runCli, outputChannel, sourcePath, backendChannel });
      if (descResult.modelAvailable && descResult.described > 0) {
        outputChannel.appendLine(`[KTS] Image descriptions complete: ${descResult.described} processed.`);
        vscode.window.showInformationMessage(`KTS: Auto-described ${descResult.described} image(s).${descResult.failed ? ` ${descResult.failed} failed.` : ''}`);
      } else if (!descResult.modelAvailable) {
        outputChannel.appendLine('[KTS] Vision model not available. Use @kts /describe_images in chat.');
        vscode.window.showInformationMessage(`KTS: ${totalImagesPending} image(s) extracted. Use @kts /describe_images to describe them.`);
      }
    } catch (descErr) {
      outputChannel.appendLine(`[KTS] Auto-describe skipped (non-blocking): ${descErr.message}`);
    }
  }

  outputChannel.appendLine(`\n${'='.repeat(60)}`);
  outputChannel.appendLine(`[KTS] Knowledge base ready at: ${path.join(sourcePath, '.kts')}`);
  outputChannel.appendLine('[KTS] Try: @kts <your question> in GitHub Copilot Chat');
  outputChannel.appendLine(`${'='.repeat(60)}\n`);

  // Phase 12.2: Trigger scope refresh so dynamic slash commands register
  try {
    await vscode.commands.executeCommand('kts.refreshScopes');
    outputChannel.appendLine('[KTS] Scope discovery refreshed after ingestion.');
  } catch (_) {
    // Non-fatal — scope refresh command may not be registered yet
  }

  vscode.window.showInformationMessage(`KTS: Indexed ${ingestedCount} document(s) with ${totalChunks} searchable chunks`);

  return { sourcePath, crawl: crawlResult, ingest: ingestResult };
}

