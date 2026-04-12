const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const crawlIngest = require('./commands/crawl_ingest');
const crawl = require('./commands/crawl');
const ingest = require('./commands/ingest');
const status = require('./commands/status');
const search = require('./commands/search');
const selectSource = require('./commands/select_source');
const doctor = require('./commands/doctor');
const openLogs = require('./commands/open_logs');
const viewStatus = require('./commands/view_status');
const trainingPath = require('./commands/training_path');
const changeImpact = require('./commands/change_impact');
const freshnessAudit = require('./commands/freshness_audit');
const imageDescription = require('./commands/image_description');
const imageDescriptionComplete = require('./commands/image_description_complete');
const { registerChatParticipant } = require('./chat/participant');
const { registerABSParticipant } = require('./chat/absParticipant');
const { initVenvManager, initBackendRunner, runCliJson, runAbsStreaming } = require('./lib/kts_backend');
const { refreshScopes } = require('./lib/scope_discovery');

// ---------------------------------------------------------------------------
// Addon Registry — model extensions register here via registerAddon()
// ---------------------------------------------------------------------------
const _addonRegistry = {};

function register(context, command, handler, shared) {
  const disposable = vscode.commands.registerCommand(command, async () => {
    try {
      await handler(shared);
    } catch (error) {
      shared.outputChannel.appendLine(`[KTS] ${command} failed: ${error.message}`);
      shared.outputChannel.show(true);
      vscode.window.showErrorMessage(`KTS command failed: ${error.message}`);
    }
  });
  context.subscriptions.push(disposable);
}

async function bootstrapBackend(context, backendMode, backendChannel, venvManager, config, outputChannel) {
  outputChannel.appendLine(`[KTS] Checking backend status (mode: ${backendMode}, channel: ${backendChannel})...`);
  
  // If exe mode or auto mode, check if exe exists
  if (backendMode === 'exe' || backendMode === 'auto') {
    const exePath = path.join(context.extensionPath, 'bin', 'win-x64', 'kts-backend', 'kts-backend.exe');
    if (fs.existsSync(exePath)) {
      outputChannel.appendLine('[KTS] Executable backend found. Skipping venv bootstrap.');
      return;
    }
    
    if (backendMode === 'exe') {
      outputChannel.appendLine('[KTS] WARNING: exe mode requested but kts-backend.exe not found. Falling back to venv.');
    }
  }
  
  // Bootstrap venv if in bundled mode
  if (backendChannel === 'bundled') {
    const isValid = await venvManager.isVenvValid();
    
    if (!isValid) {
      outputChannel.appendLine('[KTS] Backend not initialized. Starting bootstrap...');
      outputChannel.show(true);
      
      vscode.window.showInformationMessage('KTS: Setting up backend (first-time setup, this may take a few minutes)...');
      
      try {
        const pythonPath = config.get('pythonPath');
        const detectedPython = await venvManager.detectPython(pythonPath);
        outputChannel.appendLine(`[KTS] Python detected: ${detectedPython}`);
        
        await venvManager.bootstrap(detectedPython);
        
        vscode.window.showInformationMessage('KTS: Backend setup complete ✓');
        outputChannel.appendLine('[KTS] Bootstrap complete!');
      } catch (error) {
        outputChannel.appendLine(`[KTS] Bootstrap failed: ${error.message}`);
        outputChannel.show(true);
        vscode.window.showErrorMessage(`KTS Bootstrap failed: ${error.message}. Run "KTS: Doctor" for diagnostics.`);
        throw error;
      }
    } else {
      outputChannel.appendLine('[KTS] Backend already initialized.');
    }
  }
}

async function activate(context) {
  const outputChannel = vscode.window.createOutputChannel('KTS');
  context.subscriptions.push(outputChannel);

  outputChannel.appendLine('[KTS] Activating extension...');

  // Initialize venv manager
  const venvManager = initVenvManager(context, outputChannel);
  const config = vscode.workspace.getConfiguration('kts');

  // ── Backward-compat migration: sourcePath → sourceFolder ──
  try {
    const legacyPath = config.get('sourcePath');
    const newPath = config.get('sourceFolder');
    if (legacyPath && !newPath) {
      await config.update('sourceFolder', legacyPath, vscode.ConfigurationTarget.Global);
      outputChannel.appendLine(`[KTS] Migrated kts.sourcePath → kts.sourceFolder: ${legacyPath}`);
    }
  } catch (_) { /* non-fatal */ }

  // Bootstrap backend asynchronously (don't block activation)
  const backendChannel = config.get('backendChannel') || 'bundled';
  const backendMode = config.get('backendMode') || 'auto';
  
  bootstrapBackend(context, backendMode, backendChannel, venvManager, config, outputChannel).catch((error) => {
    outputChannel.appendLine(`[KTS] Deferred bootstrap failed: ${error.message}`);
  });

  // Initialize backend runner
  let runner = null;
  try {
    runner = await initBackendRunner(vscode, context, outputChannel);
  } catch (error) {
    outputChannel.appendLine(`[KTS] Backend runner initialization failed: ${error.message}`);
    outputChannel.appendLine('[KTS] Commands will be available but may fail until backend is ready.');
  }

  const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri?.fsPath;
  const shared = { 
    vscode, 
    outputChannel, 
    context,
    workspaceRoot,
    runner,
    runCli: runCliJson,
    runCliJson,           // alias so both names work
    runAbsStreaming,      // bidirectional streaming IPC for @abs LLM round-trips
  };

  // Register new commands
  register(context, 'kts.selectSource', selectSource, shared);
  register(context, 'kts.crawl', crawl, shared);
  register(context, 'kts.ingest', ingest, shared);
  register(context, 'kts.status', status, shared);
  register(context, 'kts.search', search, shared);
  register(context, 'kts.doctor', doctor, shared);
  register(context, 'kts.openLogs', openLogs, shared);
  
  // Register legacy commands
  register(context, 'kts.crawlIngest', crawlIngest, shared);
  register(context, 'kts.viewStatus', viewStatus, shared);
  register(context, 'kts.trainingPath', trainingPath, shared);
  register(context, 'kts.changeImpact', changeImpact, shared);
  register(context, 'kts.freshnessAudit', freshnessAudit, shared);
  register(context, 'kts.imageDescription', imageDescription, shared);
  register(context, 'kts.imageDescriptionComplete', imageDescriptionComplete, shared);

  registerChatParticipant(vscode, context, shared);

  // ── @abs chat participant (Phase 23) ─────────────────────────────────────
  registerABSParticipant(vscode, context, shared);

  // ── Golden Test Harness commands (dev-mode only) ───────────────
  // The test runners live in ../tests/ which is excluded from the VSIX.
  // Only register these commands when running from the workspace source.
  const isDevMode = fs.existsSync(path.join(context.extensionPath, '..', 'tests', 'golden_answer_runner.js'));
  if (isDevMode) {
    const goldenTestCmd = vscode.commands.registerCommand('kts.runGoldenTests', async () => {
      const goldenChannel = vscode.window.createOutputChannel('KTS Golden Tests');
      goldenChannel.show();

      try {
        const { runGoldenTests } = require('../tests/golden_answer_runner');
        const { scoreResults, saveScores, saveAsBaseline } = require('../tests/golden_answer_scorer');
        const { selectModel } = require('./chat/participant');

        const dialogResult = await vscode.window.showOpenDialog({
          canSelectFiles: false,
          canSelectFolders: true,
          canSelectMany: false,
          openLabel: 'Select KB folder for Golden Tests',
          defaultUri: (() => {
            const cur = vscode.workspace.getConfiguration('kts').get('sourceFolder');
            return cur ? vscode.Uri.file(cur) : undefined;
          })(),
        });
        if (!dialogResult || dialogResult.length === 0) {
          goldenChannel.appendLine('Golden tests cancelled \u2014 no source folder selected.');
          return;
        }
        const testSourcePath = dialogResult[0].fsPath;
        goldenChannel.appendLine(`[KTS] Running tests against: ${testSourcePath}\n`);

        goldenChannel.appendLine('Starting golden answer test suite...\n');
        const results = await runGoldenTests(vscode, goldenChannel, { ...shared, testSourcePath });

        goldenChannel.appendLine('\n=== SCORING ===\n');
        const model = await selectModel(vscode, null);
        if (!model) {
          goldenChannel.appendLine('ERROR: No LLM model available for scoring.');
          return;
        }

        const scores = await scoreResults(vscode, model, results, goldenChannel);
        const scorePath = saveScores(scores, path.join(context.extensionPath, '..', 'tests'));
        goldenChannel.appendLine(`\nScores saved to ${scorePath}`);

        goldenChannel.appendLine(`\n=== SUMMARY ===`);
        goldenChannel.appendLine(`Average: ${scores.average.toFixed(2)} / 5.00`);
        for (const cat of scores.by_category) {
          goldenChannel.appendLine(`  ${cat.name}: ${cat.average.toFixed(2)} (${cat.count} tests)`);
        }
        if (scores.regressions.length > 0) {
          goldenChannel.appendLine(`\n\u26a0 REGRESSIONS: ${scores.regressions.length}`);
          for (const r of scores.regressions) {
            goldenChannel.appendLine(`  ${r.test_id}: ${r.dimension} ${r.baseline} \u2192 ${r.current} (\u0394${r.delta})`);
          }
        } else {
          goldenChannel.appendLine('\n\u2713 No regressions detected.');
        }

        const choice = await vscode.window.showInformationMessage(
          `Golden tests complete: ${scores.average.toFixed(2)}/5.00 avg. Save as baseline?`,
          'Save Baseline', 'Skip'
        );
        if (choice === 'Save Baseline') {
          const bp = saveAsBaseline(scores);
          goldenChannel.appendLine(`Baseline saved to ${bp}`);
        }
      } catch (err) {
        goldenChannel.appendLine(`\nFATAL: ${err.message}\n${err.stack}`);
      }
    });
    context.subscriptions.push(goldenTestCmd);

    const tsGoldenTestCmd = vscode.commands.registerCommand('kts.runTSGoldenTests', async () => {
      const tsChannel = vscode.window.createOutputChannel('KTS TS Guide Golden Tests');
      tsChannel.show();

      try {
        const { runTSGoldenTests } = require('../tests/golden_ts_guide_runner');
        const { scoreResults, saveScores, saveAsBaseline } = require('../tests/golden_ts_guide_scorer');
        const { selectModel } = require('./chat/participant');

        const tsDialogResult = await vscode.window.showOpenDialog({
          canSelectFiles: false,
          canSelectFolders: true,
          canSelectMany: false,
          openLabel: 'Select KB folder for TS Guide Golden Tests',
          defaultUri: (() => {
            const cur = vscode.workspace.getConfiguration('kts').get('sourceFolder');
            return cur ? vscode.Uri.file(cur) : undefined;
          })(),
        });
        if (!tsDialogResult || tsDialogResult.length === 0) {
          tsChannel.appendLine('TS Guide golden tests cancelled \u2014 no source folder selected.');
          return;
        }
        const testSourcePath = tsDialogResult[0].fsPath;
        tsChannel.appendLine(`[KTS] Running tests against: ${testSourcePath}\n`);

        tsChannel.appendLine('Starting TS Guide golden answer test suite...\n');
        const results = await runTSGoldenTests(vscode, tsChannel, { ...shared, testSourcePath });

        tsChannel.appendLine('\n=== SCORING ===\n');
        const model = await selectModel(vscode, null);
        if (!model) {
          tsChannel.appendLine('ERROR: No LLM model available for scoring.');
          return;
        }

        const scores = await scoreResults(vscode, model, results, tsChannel);
        const scorePath = saveScores(scores, path.join(context.extensionPath, '..', 'tests'));
        tsChannel.appendLine(`\nScores saved to ${scorePath}`);

        tsChannel.appendLine(`\n=== SUMMARY ===`);
        tsChannel.appendLine(`Average: ${scores.average.toFixed(2)} / 5.00`);
        for (const cat of scores.by_category) {
          tsChannel.appendLine(`  ${cat.name}: ${cat.average.toFixed(2)} (${cat.count} tests)`);
        }
        if (scores.regressions.length > 0) {
          tsChannel.appendLine(`\n\u26a0 REGRESSIONS: ${scores.regressions.length}`);
          for (const r of scores.regressions) {
            tsChannel.appendLine(`  ${r.test_id}: ${r.dimension} ${r.baseline} \u2192 ${r.current} (\u0394${r.delta})`);
          }
        } else {
          tsChannel.appendLine('\n\u2713 No regressions detected.');
        }

        const choice = await vscode.window.showInformationMessage(
          `TS Guide golden tests complete: ${scores.average.toFixed(2)}/5.00 avg. Save as baseline?`,
          'Save Baseline', 'Skip'
        );
        if (choice === 'Save Baseline') {
          const bp = saveAsBaseline(scores);
          tsChannel.appendLine(`Baseline saved to ${bp}`);
        }
      } catch (err) {
        tsChannel.appendLine(`\nFATAL: ${err.message}\n${err.stack}`);
      }
    });
    context.subscriptions.push(tsGoldenTestCmd);
    outputChannel.appendLine('[KTS] Dev mode detected \u2014 golden test commands registered.');
  }

  // Phase 12.2: Scope discovery on activation
  // Note: participant stored on shared by registerChatParticipant() for dynamic command updates
  // Phase 18: Pass base commands so dynamic scope commands merge with statics
  const baseCommands = shared._baseCommands || [];
  refreshScopes(shared._chatParticipant || null, baseCommands).then(scopes => {
    // Phase 18: Cache discovered scopes so the participant can build knownSlugs
    shared._discoveredScopes = scopes || [];
    const indexed = (scopes || []).filter(s => s.indexed);
    if (indexed.length > 0) {
      const slugList = indexed.map(s => `/` + s.slug).join(', ');
      outputChannel.appendLine(`[KTS] Discovered ${indexed.length} indexed scope(s): ${slugList}`);
      outputChannel.appendLine(`[KTS] Tip: Use \`@kts /scope_slug your question\` to target a specific knowledge base.`);
    }
  }).catch(err => {
    outputChannel.appendLine(`[KTS] Scope discovery skipped: ${err.message}`);
  });

  // Phase 18: Register kts.refreshScopes command (uses base commands for merge)
  register(context, 'kts.refreshScopes', async () => {
    try {
      const scopes = await refreshScopes(shared._chatParticipant || null, shared._baseCommands || []);
      shared._discoveredScopes = scopes || [];
      const indexed = (scopes || []).filter(s => s.indexed).length;
      vscode.window.showInformationMessage(`KTS: Discovered ${scopes.length} folder(s), ${indexed} indexed.`);
    } catch (err) {
      vscode.window.showErrorMessage(`KTS: Scope refresh failed — ${err.message}`);
    }
  }, shared);

  outputChannel.appendLine('[KTS] Extension activated.');
  
  // Return API for model extensions
  return {
    registerAddon,
    getAddonRegistry,
  };
}

function deactivate() {}

// ---------------------------------------------------------------------------
// registerAddon() — called by model extensions during their activate()
// ---------------------------------------------------------------------------
/**
 * Register a model addon with the core extension.
 * @param {{ type: string, name: string, modelPath: string, capabilities: string[] }} config
 */
function registerAddon(config) {
  if (!config || !config.name) {
    console.warn('[KTS] registerAddon called with invalid config', config);
    return;
  }
  _addonRegistry[config.name] = config;
  // Logged via outputChannel by the caller; avoid console.log in production
}

/**
 * Return a snapshot of all registered addons.
 */
function getAddonRegistry() {
  return { ..._addonRegistry };
}

module.exports = {
  activate,
  deactivate,
  registerAddon,
  getAddonRegistry,
};
