const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const VenvManager = require('./venv_manager');
const { BackendRunnerFactory } = require('./backend_runner');

/**
 * KTS Backend Bridge - Unified interface for Option A1 (venv) and Option A2 (exe)
 * 
 * Supports multiple backend modes:
 * - Option A1: Managed Python venv (bundled source)
 * - Option A2: PyInstaller executable (onedir distribution)
 * - Workspace: Development mode (uses workspace .venv)
 * 
 * The BackendRunner abstraction handles mode selection and execution.
 */

let venvManager = null;
let backendRunner = null;

function initVenvManager(context, outputChannel) {
  if (!venvManager) {
    venvManager = new VenvManager(context, outputChannel);
  }
  return venvManager;
}

function getVenvManager() {
  if (!venvManager) {
    throw new Error('VenvManager not initialized. Call initVenvManager first.');
  }
  return venvManager;
}

/**
 * Initialize backend runner based on configuration
 */
async function initBackendRunner(vscode, context, outputChannel) {
  const config = vscode.workspace.getConfiguration('kts');
  const backendMode = config.get('backendMode') || 'auto';
  const backendChannel = config.get('backendChannel') || 'bundled';

  outputChannel.appendLine(`[Backend] Initializing runner (mode: ${backendMode}, channel: ${backendChannel})`);

  backendRunner = await BackendRunnerFactory.create(
    backendMode,
    backendChannel,
    context,
    venvManager,
    outputChannel
  );

  outputChannel.appendLine(`[Backend] Runner initialized: ${backendRunner.constructor.name}`);
  return backendRunner;
}

function getBackendRunner() {
  if (!backendRunner) {
    throw new Error('BackendRunner not initialized. Call initBackendRunner first.');
  }
  return backendRunner;
}

/**
 * Get workspace root for legacy "workspace" backend channel (dev mode)
 */
function getWorkspaceRoot(explicitRoot) {
  if (explicitRoot) {
    return explicitRoot;
  }
  return path.resolve(__dirname, '..', '..');
}

/**
 * Resolve KB workspace path (where manifest/index/graph/vectors live)
 */
function resolveKbWorkspacePath(userConfigPath) {
  if (userConfigPath && fs.existsSync(userConfigPath)) {
    return userConfigPath;
  }

  // Default to global storage
  const paths = getVenvManager().getPaths();
  return paths.kbWorkspace;
}

function parseJsonOutput(stdout) {
  const trimmed = (stdout || '').trim();
  if (!trimmed) {
    return {};
  }
  try {
    return JSON.parse(trimmed);
  } catch (e) {
    // If not JSON, return as text
    return { output: trimmed };
  }
}

/**
 * Run CLI command with JSON output - Delegates to BackendRunner
 * @param {Object} options
 * @param {string} options.backendChannel - 'bundled' or 'workspace' (legacy, used for workspace mode)
 * @param {string} options.vscodeWorkspaceRoot - VS Code workspace root (used in workspace mode)
 * @param {string} options.kbWorkspacePath - KB workspace path (where manifest lives)
 * @param {string} options.sourcePath - Source path for crawl/ingest operations
 * @param {string[]} options.args - CLI arguments
 * @param {number} options.timeoutMs - Timeout in milliseconds
 */
async function runCliJson({ 
  backendChannel = 'bundled',
  vscodeWorkspaceRoot = null,
  kbWorkspacePath = null,
  sourcePath = null,
  args, 
  timeoutMs = 120000 
}) {
  const runner = getBackendRunner();
  const kbPath = resolveKbWorkspacePath(kbWorkspacePath);

  // Ensure KB workspace exists
  if (!fs.existsSync(kbPath)) {
    fs.mkdirSync(kbPath, { recursive: true });
  }

  // Build environment variables
  const env = {
    KTS_KB_PATH: kbPath,
  };

  if (sourcePath) {
    env.KTS_SOURCE_PATH = sourcePath;
  }

  // Delegate to BackendRunner
  const result = await runner.runCli(args, { env, timeoutMs });
  
  // Parse JSON output
  return parseJsonOutput(result.stdout);
}

module.exports = {
  initVenvManager,
  getVenvManager,
  initBackendRunner,
  getBackendRunner,
  getWorkspaceRoot,
  resolveKbWorkspacePath,
  runCliJson,
};

