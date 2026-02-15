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
const { initVenvManager, initBackendRunner, runCliJson } = require('./lib/kts_backend');

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

  outputChannel.appendLine('[KTS] Extension activated.');
}

function deactivate() {}

module.exports = {
  activate,
  deactivate,
};
