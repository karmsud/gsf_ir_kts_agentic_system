const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

/**
 * BackendRunner - Unified abstraction for executing KTS backend commands
 * 
 * Supports multiple execution modes:
 * - VenvRunner: Option A1 - Uses managed Python venv
 * - ExeRunner: Option A2 - Uses PyInstaller executable
 * 
 * All commands go through this interface to ensure consistency.
 */

class BackendRunner {
  constructor(outputChannel) {
    this.outputChannel = outputChannel;
  }

  /**
   * Execute a CLI command
   * @param {string[]} args - CLI arguments (e.g., ['crawl', '--paths', 'source'])
   * @param {object} env - Environment variables
   * @param {string} cwd - Working directory
   * @param {number} timeoutMs - Timeout in milliseconds
   * @returns {Promise<{stdout: string, stderr: string, code: number}>}
   */
  async runCli(args, env = {}, cwd = null, timeoutMs = 3600000) {
    throw new Error('BackendRunner.runCli must be implemented by subclass');
  }

  /**
   * Get backend version
   * @returns {Promise<string>}
   */
  async getVersion() {
    throw new Error('BackendRunner.getVersion must be implemented by subclass');
  }

  /**
   * Check if backend is healthy
   * @returns {Promise<boolean>}
   */
  async healthCheck() {
    throw new Error('BackendRunner.healthCheck must be implemented by subclass');
  }

  /**
   * Get diagnostic information
   * @returns {Promise<object>}
   */
  async getDiagnostics() {
    throw new Error('BackendRunner.getDiagnostics must be implemented by subclass');
  }

  /**
   * Helper: Spawn a process and capture output
   * Logs stderr in real-time (for progress messages) and stdout after completion
   */
  _spawn(command, args, options = {}) {
    const { cwd, env, timeout = 3600000 } = options; // 1 hour default

    return new Promise((resolve, reject) => {
      this.outputChannel?.appendLine(`[Runner] Executing: ${command} ${args.join(' ')}`);

      const child = spawn(command, args, {
        cwd: cwd || process.cwd(),
        env: { ...process.env, ...env },
        stdio: ['ignore', 'pipe', 'pipe'],
        shell: false,
      });

      let stdout = '';
      let stderr = '';
      let timedOut = false;

      const timer = setTimeout(() => {
        timedOut = true;
        child.kill();
      }, timeout);

      child.stdout.on('data', (chunk) => {
        stdout += chunk.toString();
      });

      child.stderr.on('data', (chunk) => {
        const text = chunk.toString();
        stderr += text;
        // Stream stderr to output channel for real-time progress visibility
        const lines = text.split('\n').filter(l => l.trim());
        lines.forEach(line => {
          this.outputChannel?.appendLine(`[Backend] ${line}`);
        });
      });

      child.on('error', (error) => {
        clearTimeout(timer);
        this.outputChannel?.appendLine(`[Runner] Error: ${error.message}`);
        reject(error);
      });

      child.on('close', (code) => {
        clearTimeout(timer);

        if (timedOut) {
          const error = new Error(`Command timed out after ${timeout}ms`);
          this.outputChannel?.appendLine(`[Runner] Timeout`);
          reject(error);
          return;
        }

        this.outputChannel?.appendLine(`[Runner] Exit code: ${code}`);
        
        // Log stdout (JSON result) - truncate if very large for readability
        if (stdout.trim()) {
          const maxLogLength = 5000;
          if (stdout.length > maxLogLength) {
            this.outputChannel?.appendLine(`[Runner] Output (truncated): ${stdout.slice(0, maxLogLength)}...`);
          } else {
            this.outputChannel?.appendLine(`[Runner] Output: ${stdout.trim()}`);
          }
        }
        
        resolve({ stdout, stderr, code });
      });
    });
  }
}

/**
 * VenvRunner - Option A1: Managed Python venv
 * Uses the managed venv created by VenvManager
 */
class VenvRunner extends BackendRunner {
  constructor(venvManager, outputChannel) {
    super(outputChannel);
    this.venvManager = venvManager;
  }

  async runCli(args, env = {}, cwd = null, timeoutMs = 3600000) {
    const paths = this.venvManager.getPaths();
    const pythonExe = paths.venvPython;
    const backendRoot = paths.backendRoot;

    if (!fs.existsSync(pythonExe)) {
      throw new Error('Venv Python not found. Run bootstrap first.');
    }

    const finalCwd = cwd || backendRoot;
    const pythonArgs = ['-m', 'cli.main', ...args];

    const result = await this._spawn(pythonExe, pythonArgs, {
      cwd: finalCwd,
      env,
      timeout: timeoutMs,
    });

    if (result.code !== 0) {
      const message = result.stderr.trim() || `Command failed with exit code ${result.code}`;
      throw new Error(message);
    }

    return result;
  }

  async getVersion() {
    try {
      const result = await this.runCli(['--version'], {}, null, 10000);
      return result.stdout.trim() || this.venvManager.backendVersion;
    } catch (e) {
      return this.venvManager.backendVersion;
    }
  }

  async healthCheck() {
    try {
      const paths = this.venvManager.getPaths();
      
      // Check venv exists
      if (!fs.existsSync(paths.venvPython)) {
        return false;
      }

      // Check backend exists
      if (!fs.existsSync(path.join(paths.backendRoot, 'cli', 'main.py'))) {
        return false;
      }

      // Quick import check
      const result = await this._spawn(paths.venvPython, ['-c', 'import cli, backend'], {
        cwd: paths.backendRoot,
        timeout: 10000,
      });

      return result.code === 0;
    } catch (e) {
      return false;
    }
  }

  async getDiagnostics() {
    const paths = this.venvManager.getPaths();
    const diagnostics = {
      mode: 'venv',
      pythonPath: paths.venvPython,
      backendPath: paths.backendRoot,
      pythonExists: fs.existsSync(paths.venvPython),
      backendExists: fs.existsSync(path.join(paths.backendRoot, 'cli', 'main.py')),
      version: await this.getVersion(),
      healthy: await this.healthCheck(),
    };

    return diagnostics;
  }
}

/**
 * ExeRunner - Option A2: PyInstaller executable
 * Uses the bundled kts-backend.exe
 */
class ExeRunner extends BackendRunner {
  constructor(context, outputChannel) {
    super(outputChannel);
    this.context = context;
    this.exePath = this._resolveExePath();
  }

  _resolveExePath() {
    // Look for exe in extension directory
    const extensionPath = this.context.extensionPath;
    const exePath = path.join(extensionPath, 'bin', 'win-x64', 'kts-backend', 'kts-backend.exe');
    return exePath;
  }

  async runCli(args, env = {}, cwd = null, timeoutMs = 3600000) {
    if (!fs.existsSync(this.exePath)) {
      throw new Error(`Backend executable not found at: ${this.exePath}`);
    }

    const finalCwd = cwd || path.dirname(this.exePath);

    const result = await this._spawn(this.exePath, args, {
      cwd: finalCwd,
      env,
      timeout: timeoutMs,
    });

    if (result.code !== 0) {
      const message = result.stderr.trim() || `Command failed with exit code ${result.code}`;
      throw new Error(message);
    }

    return result;
  }

  async getVersion() {
    try {
      const result = await this.runCli(['--version'], {}, null, 10000);
      return result.stdout.trim();
    } catch (e) {
      return 'unknown';
    }
  }

  async healthCheck() {
    try {
      // Check exe exists
      if (!fs.existsSync(this.exePath)) {
        return false;
      }

      // Try running --version
      const result = await this._spawn(this.exePath, ['--version'], {
        timeout: 10000,
      });

      return result.code === 0;
    } catch (e) {
      return false;
    }
  }

  async getDiagnostics() {
    const diagnostics = {
      mode: 'exe',
      exePath: this.exePath,
      exeExists: fs.existsSync(this.exePath),
      version: await this.getVersion(),
      healthy: await this.healthCheck(),
    };

    if (diagnostics.exeExists) {
      try {
        const stats = fs.statSync(this.exePath);
        diagnostics.exeSize = `${(stats.size / 1024 / 1024).toFixed(2)} MB`;
        diagnostics.exeModified = stats.mtime.toISOString();
      } catch (e) {
        // Ignore
      }
    }

    return diagnostics;
  }
}

/**
 * BackendRunnerFactory - Creates the appropriate runner based on configuration
 */
class BackendRunnerFactory {
  /**
   * Create a runner based on backend mode setting
   * @param {string} backendMode - 'auto', 'venv', or 'exe'
   * @param {string} backendChannel - 'bundled' or 'workspace'
   * @param {object} context - VS Code extension context
   * @param {object} venvManager - VenvManager instance
   * @param {object} outputChannel - VS Code output channel
   * @returns {Promise<BackendRunner>}
   */
  static async create(backendMode, backendChannel, context, venvManager, outputChannel) {
    // Workspace channel always uses venv
    if (backendChannel === 'workspace') {
      outputChannel.appendLine('[RunnerFactory] Using VenvRunner (workspace mode)');
      return new VenvRunner(venvManager, outputChannel);
    }

    // Handle bundled channel modes
    if (backendMode === 'venv') {
      outputChannel.appendLine('[RunnerFactory] Using VenvRunner (forced by setting)');
      return new VenvRunner(venvManager, outputChannel);
    }

    if (backendMode === 'exe') {
      outputChannel.appendLine('[RunnerFactory] Using ExeRunner (forced by setting)');
      const runner = new ExeRunner(context, outputChannel);
      
      // Validate exe exists
      if (!await runner.healthCheck()) {
        throw new Error('Backend executable not found or unhealthy. Please rebuild the extension or switch to venv mode.');
      }
      
      return runner;
    }

    // Auto mode: prefer exe if available and healthy
    if (backendMode === 'auto') {
      const exeRunner = new ExeRunner(context, outputChannel);
      const exeHealthy = await exeRunner.healthCheck();

      if (exeHealthy) {
        outputChannel.appendLine('[RunnerFactory] Using ExeRunner (auto: exe available and healthy)');
        return exeRunner;
      }

      outputChannel.appendLine('[RunnerFactory] Using VenvRunner (auto: exe not available, falling back to venv)');
      return new VenvRunner(venvManager, outputChannel);
    }

    // Default to venv
    outputChannel.appendLine('[RunnerFactory] Using VenvRunner (default)');
    return new VenvRunner(venvManager, outputChannel);
  }
}

module.exports = {
  BackendRunner,
  VenvRunner,
  ExeRunner,
  BackendRunnerFactory,
};
