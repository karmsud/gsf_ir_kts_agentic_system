const path = require('path');
const fs = require('fs');
const { enrichVocabulary } = require('../lib/concept_client');

const INGEST_TIMEOUT_MS = 60 * 60 * 1000; // 1 hour — ingestion is a one-time operation, never compromise on completeness

/**
 * Ingest Command
 * Ingests discovered documents into the KB
 */
module.exports = async function ingest({ vscode, outputChannel, runCli } = {}) {
  const config = vscode.workspace.getConfiguration('kts');
  const sourcePath = config.get('sourceFolder');
  const kbWorkspacePath = config.get('kbWorkspacePath');
  const backendChannel = config.get('backendChannel') || 'bundled';
  if (!sourcePath) {
    vscode.window.showWarningMessage('Please set source path first (KTS: Select Source Folder)');
    return { error: 'No source path configured' };
  }

  const timeoutMs = INGEST_TIMEOUT_MS;
  const timeoutMin = 60;

  outputChannel.appendLine(`[KTS Ingest] Source: ${sourcePath}`);
  outputChannel.appendLine(`[KTS Ingest] Timeout: ${timeoutMin} min (fixed 1 hour)`);
  outputChannel.show(true);

  return vscode.window.withProgress({
    location: vscode.ProgressLocation.Notification,
    title: 'KTS Ingest',
    cancellable: false
  }, async (progress) => {
    try {
      progress.report({ message: `Indexing documents (timeout: ${timeoutMin} min)...` });

      const result = await runCli({
        backendChannel,
        kbWorkspacePath,
        sourcePath,
        args: ['ingest', '--paths', sourcePath],
        timeoutMs,
      });

      outputChannel.appendLine(JSON.stringify(result, null, 2));

      const ingestedCount = result.count
        || (Array.isArray(result.ingested) ? result.ingested.length : 0)
        || result.ingested_count
        || 0;

      // ── Phase 10: Concept Vocabulary LLM Enrichment ────────────
      // After ingestion, enrich the graph's concept keywords with
      // Copilot LLM-generated synonyms for defined terms.  This runs
      // as a post-processing step: extract terms → LLM → apply.
      // If no model is available, deterministic keywords still apply.
      progress.report({ message: 'Enriching concept vocabulary via LLM...' });
      try {
        const cliOptions = { backendChannel, kbWorkspacePath, sourcePath };
        const enrichResult = await enrichVocabulary(runCli, cliOptions, outputChannel);
        if (enrichResult.success) {
          outputChannel.appendLine(
            `[KTS Ingest] Concept vocabulary enriched: ` +
            `${enrichResult.termsProcessed} terms, ${enrichResult.synonymsGenerated} synonym sets`
          );
        }
      } catch (enrichErr) {
        // Non-fatal — deterministic keywords are already in the graph
        outputChannel.appendLine(
          `[KTS Ingest] Concept vocabulary LLM enrichment skipped: ${enrichErr.message}`
        );
      }

      vscode.window.showInformationMessage(`KTS Ingest complete: ${ingestedCount} document(s) ingested.`);

      return result;
    } catch (error) {
      outputChannel.appendLine(`[ERROR] ${error.message}`);
      if (error.message && error.message.includes('timed out')) {
        vscode.window.showErrorMessage(
          `KTS Ingest timed out after ${timeoutMin} min. The document may be extremely large. Check the KTS Output channel for progress.`
        );
      } else {
        vscode.window.showErrorMessage(`KTS Ingest failed: ${error.message}`);
      }
      throw error;
    }
  });
};
