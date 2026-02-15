const path = require('path');
const fs = require('fs');
const { exec } = require('child_process');

/**
 * Open Logs Command
 * Opens the logs directory in file explorer
 */
module.exports = async function openLogs({ vscode, context } = {}) {
  const config = vscode.workspace.getConfiguration('kts');
  const { getVenvManager } = require('../lib/kts_backend');
  
  let venvManager;
  try {
    venvManager = getVenvManager();
  } catch (e) {
    vscode.window.showErrorMessage('KTS not initialized. Please wait for bootstrap.');
    return { error: 'Not initialized' };
  }

  const paths = venvManager.getPaths();
  const kbPath = config.get('kbWorkspacePath') || paths.kbWorkspace;
  const logsDir = path.join(kbPath, 'logs');

  if (!fs.existsSync(logsDir)) {
    fs.mkdirSync(logsDir, { recursive: true });
  }

  // Open in file explorer (Windows)
  if (process.platform === 'win32') {
    exec(`explorer "${logsDir}"`);
  } else {
    vscode.window.showInformationMessage(`Logs directory: ${logsDir}`);
  }

  return { logsDir };
};
