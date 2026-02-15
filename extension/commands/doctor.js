const path = require('path');
const fs = require('fs');

/**
 * KTS Doctor Command
 * Provides comprehensive diagnostics for the KTS extension environment
 */
module.exports = async function doctor({ vscode, outputChannel, context, runner } = {}) {
  outputChannel.appendLine('=== KTS Doctor: Running Diagnostics ===');
  outputChannel.show(true);

  const config = vscode.workspace.getConfiguration('kts');
  const { getVenvManager, getBackendRunner } = require('../lib/kts_backend');
  
  let venvManager;
  try {
    venvManager = getVenvManager();
  } catch (e) {
    outputChannel.appendLine(`[ERROR] VenvManager not initialized: ${e.message}`);
    vscode.window.showErrorMessage('KTS Doctor: Extension not properly initialized.');
    return { error: 'VenvManager not initialized' };
  }

  const report = {
    timestamp: new Date().toISOString(),
    configuration: {},
    environment: {},
    backend: {},
    knowledgeBase: {},
    logs: {},
  };

  // 1. Configuration
  outputChannel.appendLine('\n--- Configuration ---');
  report.configuration = {
    sourcePath: config.get('sourcePath') || '(not set)',
    kbWorkspacePath: config.get('kbWorkspacePath') || '(using default global storage)',
    pythonPath: config.get('pythonPath') || '(auto-detect)',
    backendChannel: config.get('backendChannel') || 'bundled',
    backendMode: config.get('backendMode') || 'auto',
    logLevel: config.get('logLevel') || 'INFO',
  };
  outputChannel.appendLine(JSON.stringify(report.configuration, null, 2));

  // 2. Environment Diagnostics
  outputChannel.appendLine('\n--- Environment ---');
  try {
    const diagnostics = await venvManager.getDiagnostics(config.get('pythonPath'));
    report.environment = diagnostics;
    outputChannel.appendLine(JSON.stringify(diagnostics, null, 2));
  } catch (e) {
    report.environment.error = e.message;
    outputChannel.appendLine(`[ERROR] ${e.message}`);
  }

  // 3. Backend Status (both exe and venv)
  outputChannel.appendLine('\n--- Backend Status ---');
  const paths = venvManager.getPaths();
  
  // Check for exe
  const exePath = path.join(context.extensionPath, 'bin', 'win-x64', 'kts-backend', 'kts-backend.exe');
  const exeExists = fs.existsSync(exePath);
  
  report.backend = {
    mode: report.configuration.backendMode,
    currentRunner: runner ? runner.constructor.name : 'Not initialized',
    
    // Option A2 (exe)
    exe: {
      path: exePath,
      exists: exeExists,
      size: exeExists ? fs.statSync(exePath).size : 0,
    },
    
    // Option A1 (venv)
    venv: {
      venvPath: paths.venvPython,
      venvExists: fs.existsSync(paths.venvPython),
      backendPath: paths.backendRoot,
      backendExists: fs.existsSync(path.join(paths.backendRoot, 'cli', 'main.py')),
      backendVersion: venvManager.backendVersion,
    },
  };
  
  outputChannel.appendLine(JSON.stringify(report.backend, null, 2));
  
  // Run health check on current runner
  if (runner) {
    outputChannel.appendLine('\n--- Backend Runner Health Check ---');
    try {
      const runnerHealth = await runner.healthCheck();
      report.backend.health = runnerHealth;
      outputChannel.appendLine(JSON.stringify(runnerHealth, null, 2));
      
      // Get runner diagnostics
      const runnerDiagnostics = await runner.getDiagnostics();
      report.backend.diagnostics = runnerDiagnostics;
      outputChannel.appendLine('\n--- Backend Runner Diagnostics ---');
      outputChannel.appendLine(JSON.stringify(runnerDiagnostics, null, 2));
    } catch (e) {
      report.backend.health = { error: e.message };
      outputChannel.appendLine(`[ERROR] ${e.message}`);
    }
  }

  // 4. Knowledge Base Status
  outputChannel.appendLine('\n--- Knowledge Base ---');
  const kbPath = config.get('kbWorkspacePath') || paths.kbWorkspace;
  const manifestPath = path.join(kbPath, 'manifest.json');
  
  report.knowledgeBase = {
    kbWorkspace: kbPath,
    kbWorkspaceExists: fs.existsSync(kbPath),
    manifestExists: fs.existsSync(manifestPath),
    manifest: null,
  };

  if (fs.existsSync(manifestPath)) {
    try {
      const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
      report.knowledgeBase.manifest = {
        lastCrawl: manifest.last_crawl || 'never',
        lastIngest: manifest.last_ingest || 'never',
        documentCount: manifest.document_count || 0,
        totalChunks: manifest.total_chunks || 0,
      };
    } catch (e) {
      report.knowledgeBase.manifest = `Error reading manifest: ${e.message}`;
    }
  }
  outputChannel.appendLine(JSON.stringify(report.knowledgeBase, null, 2));

  // 5. Recent Logs
  outputChannel.appendLine('\n--- Recent Logs ---');
  const logsDir = path.join(kbPath, 'logs');
  if (fs.existsSync(logsDir)) {
    const logFiles = fs.readdirSync(logsDir)
      .filter(f => f.endsWith('.log'))
      .sort()
      .reverse()
      .slice(0, 3);
    
    report.logs.recentLogFiles = logFiles;
    report.logs.logsDirectory = logsDir;
    
    if (logFiles.length > 0) {
      const latestLog = path.join(logsDir, logFiles[0]);
      const logContent = fs.readFileSync(latestLog, 'utf8');
      const lastLines = logContent.split('\n').slice(-50).join('\n');
      
      outputChannel.appendLine(`\nLast 50 lines from ${logFiles[0]}:`);
      outputChannel.appendLine(lastLines);
      report.logs.latestLogTail = lastLines;
    }
  } else {
    outputChannel.appendLine('No logs directory found.');
    report.logs.status = 'No logs directory';
  }

  // Summary
  outputChannel.appendLine('\n=== Summary ===');
  const issues = [];
  
  // Check if at least one backend mode is available
  const hasExe = report.backend.exe?.exists;
  const hasVenv = report.environment.venvExists && report.environment.healthCheck;
  
  if (!hasExe && !hasVenv) {
    issues.push('No backend available (neither exe nor venv)');
  }
  
  if (report.configuration.backendMode === 'exe' && !hasExe) {
    issues.push('Backend mode set to "exe" but kts-backend.exe not found');
  }
  
  if (report.configuration.backendMode === 'venv' && !hasVenv) {
    issues.push('Backend mode set to "venv" but venv not ready');
  }
  
  if (!report.environment.pythonDetected && !hasExe) {
    issues.push('Python not detected and no exe available');
  }
  
  if (!report.configuration.sourcePath || report.configuration.sourcePath === '(not set)') {
    issues.push('Source path not configured (use "KTS: Select Source Folder")');
  }

  if (issues.length === 0) {
    outputChannel.appendLine('[OK] All checks passed!');
    vscode.window.showInformationMessage('KTS Doctor: All checks passed ✓');
  } else {
    outputChannel.appendLine(`[ISSUES FOUND] ${issues.length} issue(s):`);
    issues.forEach(issue => outputChannel.appendLine(`  - ${issue}`));
    vscode.window.showWarningMessage(`KTS Doctor: ${issues.length} issue(s) found. Check output for details.`);
  }

  return report;
};
