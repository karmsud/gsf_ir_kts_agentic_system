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
  // Prefer VS Code workspace folder; fall back to extension parent (dev layout only)
  const vscode = require('vscode');
  const folders = vscode.workspace.workspaceFolders;
  if (folders && folders.length > 0) {
    return folders[0].uri.fsPath;
  }
  return path.resolve(__dirname, '..', '..');
}

/**
 * Resolve KB workspace path (where manifest/index/graph/vectors live).
 * Shared mode: always uses <sourcePath>/.kts/ so the index lives alongside the source.
 * @param {string|null} userConfigPath - Explicit KB path override (if set in settings)
 * @param {string|null} sourcePath - Source folder; KB path derived as <sourcePath>/.kts/
 */
function resolveKbWorkspacePath(userConfigPath, sourcePath) {
  // 1. Explicit override from settings takes priority
  if (userConfigPath && fs.existsSync(userConfigPath)) {
    return userConfigPath;
  }

  // 2. Derive from source path: <sourceFolder>/.kts/
  if (sourcePath) {
    return path.join(sourcePath, '.kts');
  }

  // 3. Try reading configured source path from VS Code settings
  try {
    const vscode = require('vscode');
    const config = vscode.workspace.getConfiguration('kts');
    const configuredSource = config.get('sourceFolder') || config.get('sourcePath');
    if (configuredSource) {
      return path.join(configuredSource, '.kts');
    }
  } catch (_) {
    // vscode API may not be available in tests
  }

  // 4. Fallback to global storage (should not normally reach here)
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
    // stdout may contain progress lines before the final JSON object.
    // Find the last top-level JSON object or array in the output.
    const lastBrace = trimmed.lastIndexOf('{');
    const lastBracket = trimmed.lastIndexOf('[');
    const jsonStart = Math.max(lastBrace, lastBracket);
    if (jsonStart > 0) {
      const candidate = trimmed.slice(jsonStart).trim();
      try {
        // Walk backwards to find the outermost opening brace that forms valid JSON
        for (let i = jsonStart; i >= 0; i--) {
          if (trimmed[i] === '{' || trimmed[i] === '[') {
            try {
              const parsed = JSON.parse(trimmed.slice(i));
              return parsed;
            } catch (_) {
              // keep searching
            }
          }
        }
        return JSON.parse(candidate);
      } catch (_) {
        // fall through
      }
    }
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
  timeoutMs = 3600000  // 1 hour default
}) {
  const runner = getBackendRunner();
  const kbPath = resolveKbWorkspacePath(kbWorkspacePath, sourcePath);

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

  // Inject pipeline settings from RAG_CONFIG (hardcoded, performance-tuned defaults)
  // Phase 16: Settings simplified — all RAG tuning lives in participant.js RAG_CONFIG.
  // The backend reads these via KTS_ env vars; we set them from the canonical constants.
  try {
    const vscode = require('vscode');
    const ktsConfig = vscode.workspace.getConfiguration('kts');

    // Phase 6 GraphRAG — always enabled (core architecture)
    env.KTS_PHASE6_ENABLED = 'true';
    env.KTS_PHASE6_MAX_ITERATIONS = '10';
    env.KTS_PHASE6_VERBOSE = 'true';

    // Log level — only user-facing setting that maps to backend env var
    const logLevel = ktsConfig.get('logLevel');
    if (logLevel) {
      env.KTS_LOG_LEVEL = logLevel;
    }

    // RAG pipeline constants (sourced from RAG_CONFIG in participant.js)
    env.KTS_MULTI_QUERY_RAG_ENABLED = 'true';
    env.KTS_MULTI_QUERY_VARIANTS = '4';
    env.KTS_SELF_RAG_ENABLED = 'true';
    env.KTS_SELF_RAG_MAX_ROUNDS = '3';
    env.KTS_CRITIQUE_LOOP_ENABLED = 'true';
  } catch (_) {
    // vscode API may not be available in tests
  }

  // Inject model paths from addon registry (set by model extensions)
  try {
    const core = require('../extension');
    const addons = core.getAddonRegistry();
    if (addons.spacy && addons.spacy.modelPath) {
      env.KTS_SPACY_MODEL_PATH = addons.spacy.modelPath;
    }
    if (addons.crossencoder && addons.crossencoder.modelPath) {
      env.KTS_CROSSENCODER_MODEL_PATH = addons.crossencoder.modelPath;
    }
  } catch (_) {
    // Core module not available (e.g. unit tests) — skip addon injection
  }

  // Delegate to BackendRunner (positional args: args, env, cwd, timeoutMs)
  const result = await runner.runCli(args, env, null, timeoutMs);
  
  // Parse JSON output
  return parseJsonOutput(result.stdout);
}

/**
 * Resolve the Python executable and working directory from any BackendRunner type.
 *
 * Handles VenvRunner, WorkspaceRunner, and ExeRunner transparently.
 * Returns { cmd, cmdArgs, cwd } where cmd + cmdArgs are the process-launch tuple.
 *
 * @param {object} runner - A BackendRunner instance (any subclass)
 * @returns {{ cmd: string, cmdArgs: string[], cwd: string|null }}
 */
function getPythonCommandInfo(runner) {
  // WorkspaceRunner: has pythonExe + workspaceRoot
  if (runner.pythonExe && runner.workspaceRoot) {
    return {
      cmd: runner.pythonExe,
      cmdArgs: ['-m', 'cli.main'],
      cwd: runner.workspaceRoot,
    };
  }
  // VenvRunner: has venvManager
  if (runner.venvManager) {
    const paths = runner.venvManager.getPaths();
    return {
      cmd: paths.venvPython,
      cmdArgs: ['-m', 'cli.main'],
      cwd: paths.backendRoot,
    };
  }
  // ExeRunner: has exePath (the exe includes the CLI entry point)
  if (runner.exePath) {
    return {
      cmd: runner.exePath,
      cmdArgs: [],
      cwd: null,
    };
  }
  // Last resort: workspace-relative
  const wsRoot = getWorkspaceRoot();
  const winPy = path.join(wsRoot, '.venv_build', 'Scripts', 'python.exe');
  return {
    cmd: fs.existsSync(winPy) ? winPy : (process.platform === 'win32' ? 'python' : 'python3'),
    cmdArgs: ['-m', 'cli.main'],
    cwd: wsRoot,
  };
}

/**
 * Run an ABS CLI command with bidirectional stdin/stdout streaming.
 *
 * Supports the LLM IPC round-trip:
 *   - Backend emits {"type":"llm_request",...} on stdout
 *   - Caller writes {"type":"llm_response","text":"..."}\n to stdin via writeToStdin()
 *
 * @param {Object} options
 * @param {string[]} options.args            - CLI arguments (e.g. ['abs', 'qa', ...])
 * @param {Object}  [options.env]            - Extra env vars to inject
 * @param {Function} options.onLine          - Called for each JSON line: (msg, writeToStdin) => void
 * @param {AbortSignal} [options.abortSignal] - Optional cancellation signal
 * @returns {Promise<{code: number|null}>}
 */
async function runAbsStreaming({ args, env = {}, onLine, abortSignal }) {
  const runner = getBackendRunner();
  const { cmd, cmdArgs, cwd } = getPythonCommandInfo(runner);
  const allArgs = [...cmdArgs, ...args];

  const mergedEnv = { ...process.env, ...env };
  const finalCwd = cwd || getWorkspaceRoot();

  return new Promise((resolve, reject) => {
    const child = spawn(cmd, allArgs, {
      cwd: finalCwd,
      env: mergedEnv,
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    function writeToStdin(obj) {
      try {
        child.stdin.write(JSON.stringify(obj) + '\n');
      } catch (_) { /* process may have exited */ }
    }

    let stdoutBuf = '';
    child.stdout.on('data', (chunk) => {
      stdoutBuf += chunk.toString('utf8');
      const lines = stdoutBuf.split('\n');
      stdoutBuf = lines.pop(); // retain incomplete final line
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
          const msg = JSON.parse(trimmed);
          onLine(msg, writeToStdin);
        } catch (_) {
          onLine({ type: 'text', text: trimmed }, writeToStdin);
        }
      }
    });

    child.on('error', reject);

    child.on('close', (code) => {
      // Flush any remaining buffer
      if (stdoutBuf.trim()) {
        try { onLine(JSON.parse(stdoutBuf.trim()), writeToStdin); } catch (_) {}
      }
      resolve({ code });
    });

    if (abortSignal) {
      abortSignal.addEventListener('abort', () => {
        try { child.kill(); } catch (_) {}
      });
    }
  });
}

module.exports = {
  initVenvManager,
  getVenvManager,
  initBackendRunner,
  getBackendRunner,
  getWorkspaceRoot,
  resolveKbWorkspacePath,
  runCliJson,
  runAbsStreaming,
  getPythonCommandInfo,
};

