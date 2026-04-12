const path = require('path');
const fs = require('fs');
const { enrichVocabulary } = require('../lib/concept_client');

const INGEST_TIMEOUT_MS = 60 * 60 * 1000; // 1 hour

/**
 * Crawl + Ingest Command
 *
 * Uses the source folder configured by "KTS: Select Source Folder".
 * If no folder is configured, shows an error and exits — no fallback prompts.
 *
 * Phase 18: If crawl detects no new/modified files and ingestion already
 * exists (.kts/ present), ingest is skipped. Users must run Ingest
 * explicitly to force re-ingestion of unchanged documents.
 */
module.exports = async function crawlIngest({ vscode, outputChannel, runCli } = {}) {
  const config = vscode.workspace.getConfiguration('kts');
  const sourcePath = config.get('sourceFolder');
  const kbWorkspacePath = config.get('kbWorkspacePath');
  const backendChannel = config.get('backendChannel') || 'bundled';

  if (!sourcePath) {
    vscode.window.showErrorMessage('No source folder configured. Run "KTS: Select Source Folder" first.');
    return { error: 'No source path configured' };
  }

  if (!fs.existsSync(sourcePath)) {
    vscode.window.showErrorMessage(`Source folder not found: ${sourcePath}. Run "KTS: Select Source Folder" to update.`);
    return { error: 'Source path not found' };
  }

  outputChannel.appendLine(`\n[KTS Crawl+Ingest] Source: ${sourcePath}`);
  outputChannel.show(true);

  return vscode.window.withProgress({
    location: vscode.ProgressLocation.Notification,
    title: 'KTS Crawl+Ingest',
    cancellable: false
  }, async (progress) => {
    try {
      // ── Step 1: Crawl ──────────────────────────────────────────
      outputChannel.appendLine('[KTS] Timeout: 60 min fixed');
      progress.report({ message: 'Scanning for documents...' });
      outputChannel.appendLine('[KTS] Step 1/2: Running crawl...');
      const crawlResult = await runCli({
        backendChannel,
        kbWorkspacePath,
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

      // ── Phase 18: Skip ingest if nothing changed ───────────────
      if (newCount + modifiedCount === 0) {
        outputChannel.appendLine('[KTS] No new or modified files detected — skipping ingest.');
        const msg = deletedCount > 0
          ? `KTS: No documents to ingest (${deletedCount} deleted, ${unchangedCount} unchanged).`
          : `KTS: All ${unchangedCount} document(s) are up-to-date — nothing to ingest.`;
        vscode.window.showInformationMessage(msg);

        // Still refresh scopes in case .kts/ folders were created by prior runs
        try { await vscode.commands.executeCommand('kts.refreshScopes'); } catch (_) {}

        return { crawl: crawlResult, ingest: { skipped: true, reason: 'no_changes' } };
      }

      // ── Step 2: Ingest (only new + modified) ───────────────────
      progress.report({ message: `Indexing ${newCount + modifiedCount} document(s)...` });
      outputChannel.appendLine(`[KTS] Step 2/2: Running ingest for ${newCount + modifiedCount} changed document(s)...`);
      const ingestResult = await runCli({
        backendChannel,
        kbWorkspacePath,
        sourcePath,
        args: ['ingest', '--paths', sourcePath],
        timeoutMs: INGEST_TIMEOUT_MS,
      });

      const ingestedCount = ingestResult.count
        || (Array.isArray(ingestResult.ingested) ? ingestResult.ingested.length : 0)
        || ingestResult.ingested_count
        || 0;

      const totalChunks = (ingestResult.ingested || []).reduce((sum, doc) => sum + (doc.chunk_count || 0), 0);

      outputChannel.appendLine(`[KTS] Ingest complete: ${ingestedCount} document(s), ${totalChunks} chunks`);

      // Concept vocabulary enrichment
      progress.report({ message: 'Enriching concept vocabulary...' });
      try {
        const cliOptions = { backendChannel, kbWorkspacePath, sourcePath };
        const enrichResult = await enrichVocabulary(runCli, cliOptions, outputChannel);
        if (enrichResult.success) {
          outputChannel.appendLine(
            `[KTS] Concept vocabulary enriched: ` +
            `${enrichResult.termsProcessed} terms, ${enrichResult.synonymsGenerated} synonym sets`
          );
        }
      } catch (enrichErr) {
        // Non-fatal — deterministic keywords are already in the graph
        outputChannel.appendLine(
          `[KTS] Concept vocabulary LLM enrichment skipped: ${enrichErr.message}`
        );
      }

      // Phase 18: Refresh dynamic scope commands after ingestion creates .kts/ folders
      try { await vscode.commands.executeCommand('kts.refreshScopes'); } catch (_) {}

      vscode.window.showInformationMessage(`KTS: Indexed ${ingestedCount} document(s) with ${totalChunks} chunks.`);
      return { crawl: crawlResult, ingest: ingestResult };
    } catch (error) {
      outputChannel.appendLine(`[KTS] ERROR: ${error.message}`);
      vscode.window.showErrorMessage(`KTS Crawl+Ingest failed: ${error.message}`);
      throw error;
    }
  });
};
