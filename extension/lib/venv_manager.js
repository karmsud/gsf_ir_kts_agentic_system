const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

/**
 * VenvManager: Manages the self-contained Python virtual environment for KTS backend
 * Responsibilities:
 * - Detect system Python
 * - Create and manage venv in VS Code global storage
 * - Install dependencies from bundled backend
 * - Perform health checks
 * - Handle version upgrades
 */

class VenvManager {
  constructor(context, outputChannel) {
    this.context = context;
    this.outputChannel = outputChannel;
    this.backendVersion = this._readBackendVersion();
  }

  /**
   * Read backend version from bundled metadata
   */
  _readBackendVersion() {
    try {
      const versionPath = path.join(__dirname, '..', 'backend_bundle', 'backend_version.json');
      if (fs.existsSync(versionPath)) {
        const metadata = JSON.parse(fs.readFileSync(versionPath, 'utf8'));
        return metadata.version || '1.0.0';
      }
    } catch (error) {
      this.outputChannel?.appendLine(`[VenvManager] Could not read backend version: ${error.message}`);
    }
    return '1.0.0';
  }

  /**
   * Get paths for venv and backend storage
   */
  getPaths() {
    const globalStoragePath = this.context.globalStorageUri.fsPath;
    
    return {
      globalStorage: globalStoragePath,
      venvRoot: path.join(globalStoragePath, 'kts-venv', this.backendVersion),
      backendRoot: path.join(globalStoragePath, 'kts-backend', this.backendVersion),
      kbWorkspace: path.join(globalStoragePath, 'kts-kb', 'default'),
      venvPython: process.platform === 'win32'
        ? path.join(globalStoragePath, 'kts-venv', this.backendVersion, 'Scripts', 'python.exe')
        : path.join(globalStoragePath, 'kts-venv', this.backendVersion, 'bin', 'python'),
    };
  }

  /**
   * Detect system Python executable
   */
  async detectPython(userProvidedPath) {
    if (userProvidedPath && fs.existsSync(userProvidedPath)) {
      return userProvidedPath;
    }

    // Try py launcher first (Windows)
    if (process.platform === 'win32') {
      try {
        await this._runCommand('py', ['-3', '--version']);
        return 'py -3';
      } catch (e) {
        // Fall through to try python
      }
    }

    // Try python3/python
    const candidates = process.platform === 'win32' ? ['python'] : ['python3', 'python'];
    
    for (const cmd of candidates) {
      try {
        const result = await this._runCommand(cmd, ['--version']);
        if (result.includes('Python 3.')) {
          return cmd;
        }
      } catch (e) {
        // Try next candidate
      }
    }

    throw new Error('Python 3.10+ not found. Please install Python or configure kts.pythonPath setting.');
  }

  /**
   * Check if venv is already set up and valid
   */
  async isVenvValid() {
    const paths = this.getPaths();
    
    // Check if venv python exists
    if (!fs.existsSync(paths.venvPython)) {
      return false;
    }

    // Check if backend is unpacked
    if (!fs.existsSync(path.join(paths.backendRoot, 'cli', 'main.py'))) {
      return false;
    }

    // Check if requirements are installed (quick health check)
    try {
      await this._runCommand(paths.venvPython, ['-c', 'import backend, cli']);
      return true;
    } catch (e) {
      return false;
    }
  }

  /**
   * Bootstrap the complete environment
   */
  async bootstrap(pythonPath) {
    this.outputChannel.appendLine('[VenvManager] Starting bootstrap...');
    
    const paths = this.getPaths();
    
    // 1. Ensure directories exist
    this._ensureDir(paths.globalStorage);
    this._ensureDir(paths.venvRoot);
    this._ensureDir(paths.backendRoot);
    this._ensureDir(paths.kbWorkspace);

    // 2. Unpack backend bundle
    await this._unpackBackend(paths.backendRoot);

    // 3. Create venv
    await this._createVenv(pythonPath, paths.venvRoot);

    // 4. Install dependencies
    await this._installDependencies(paths.venvPython, paths.backendRoot);

    // 5. Health check
    await this._healthCheck(paths.venvPython, paths.backendRoot);

    this.outputChannel.appendLine('[VenvManager] Bootstrap complete!');
  }

  /**
   * Unpack backend bundle from extension into global storage
   */
  async _unpackBackend(targetDir) {
    this.outputChannel.appendLine(`[VenvManager] Unpacking backend to ${targetDir}...`);
    
    const bundleSource = path.join(__dirname, '..', 'backend_bundle');
    
    if (!fs.existsSync(bundleSource)) {
      throw new Error('Backend bundle not found in extension. Extension may be corrupted.');
    }

    // Clean target if exists
    if (fs.existsSync(targetDir)) {
      fs.rmSync(targetDir, { recursive: true, force: true });
    }

    // Copy bundle
    this._copyRecursive(bundleSource, targetDir);
    
    this.outputChannel.appendLine('[VenvManager] Backend unpacked successfully.');
  }

  /**
   * Create virtual environment
   */
  async _createVenv(pythonCmd, venvPath) {
    this.outputChannel.appendLine(`[VenvManager] Creating venv at ${venvPath}...`);

    // Clean if exists
    if (fs.existsSync(venvPath)) {
      fs.rmSync(venvPath, { recursive: true, force: true });
    }

    const args = pythonCmd === 'py -3' 
      ? ['-3', '-m', 'venv', venvPath]
      : ['-m', 'venv', venvPath];
    const cmd = pythonCmd.split(' ')[0];

    await this._runCommand(cmd, args, { timeout: 60000 });
    
    this.outputChannel.appendLine('[VenvManager] Venv created successfully.');
  }

  /**
   * Install dependencies from requirements.txt
   */
  async _installDependencies(venvPython, backendRoot) {
    this.outputChannel.appendLine('[VenvManager] Installing dependencies...');

    const requirementsPath = path.join(backendRoot, 'requirements.txt');
    
    if (!fs.existsSync(requirementsPath)) {
      throw new Error('requirements.txt not found in backend bundle.');
    }

    await this._runCommand(venvPython, [
      '-m', 'pip', 'install', '--upgrade', 'pip'
    ], { timeout: 120000 });

    await this._runCommand(venvPython, [
      '-m', 'pip', 'install', '-r', requirementsPath
    ], { timeout: 300000 });

    this.outputChannel.appendLine('[VenvManager] Dependencies installed successfully.');
  }

  /**
   * Perform health check
   */
  async _healthCheck(venvPython, backendRoot) {
    this.outputChannel.appendLine('[VenvManager] Running health check...');

    // Test imports
    await this._runCommand(venvPython, [
      '-c', 'import cli, backend, config; print("Imports OK")'
    ], { 
      cwd: backendRoot,
      timeout: 30000 
    });

    // Test CLI module
    await this._runCommand(venvPython, [
      '-m', 'cli.main', '--help'
    ], { 
      cwd: backendRoot,
      timeout: 30000 
    });

    this.outputChannel.appendLine('[VenvManager] Health check passed.');
  }

  /**
   * Get diagnostic information
   */
  async getDiagnostics(pythonPath) {
    const paths = this.getPaths();
    const diagnostics = {
      backendVersion: this.backendVersion,
      pythonDetected: null,
      pythonVersion: null,
      venvExists: fs.existsSync(paths.venvPython),
      venvPath: paths.venvPython,
      backendExists: fs.existsSync(path.join(paths.backendRoot, 'cli', 'main.py')),
      backendPath: paths.backendRoot,
      kbWorkspacePath: paths.kbWorkspace,
      kbWorkspaceExists: fs.existsSync(paths.kbWorkspace),
      installedPackages: null,
      healthCheck: false,
    };

    try {
      diagnostics.pythonDetected = await this.detectPython(pythonPath);
      const versionOutput = await this._runCommand(diagnostics.pythonDetected.split(' ')[0], ['--version']);
      diagnostics.pythonVersion = versionOutput.trim();
    } catch (e) {
      diagnostics.pythonVersion = `Error: ${e.message}`;
    }

    if (diagnostics.venvExists) {
      try {
        const pipList = await this._runCommand(paths.venvPython, ['-m', 'pip', 'list', '--format=freeze']);
        diagnostics.installedPackages = crypto.createHash('md5').update(pipList).digest('hex').substring(0, 8);
      } catch (e) {
        diagnostics.installedPackages = 'Error reading packages';
      }

      try {
        await this._runCommand(paths.venvPython, ['-c', 'import cli, backend']);
        diagnostics.healthCheck = true;
      } catch (e) {
        diagnostics.healthCheck = false;
      }
    }

    return diagnostics;
  }

  /**
   * Helper: Run a command and return stdout
   */
  _runCommand(command, args, options = {}) {
    return new Promise((resolve, reject) => {
      const { cwd, timeout = 30000 } = options;
      
      const child = spawn(command, args, {
        cwd: cwd,
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
        stderr += chunk.toString();
      });

      child.on('error', (error) => {
        clearTimeout(timer);
        reject(error);
      });

      child.on('close', (code) => {
        clearTimeout(timer);

        if (timedOut) {
          reject(new Error(`Command timed out after ${timeout}ms`));
          return;
        }

        if (code !== 0) {
          reject(new Error(stderr.trim() || `Command failed with exit code ${code}`));
          return;
        }

        resolve(stdout);
      });
    });
  }

  /**
   * Helper: Ensure directory exists
   */
  _ensureDir(dirPath) {
    if (!fs.existsSync(dirPath)) {
      fs.mkdirSync(dirPath, { recursive: true });
    }
  }

  /**
   * Helper: Recursive copy
   */
  _copyRecursive(src, dest) {
    if (fs.statSync(src).isDirectory()) {
      if (!fs.existsSync(dest)) {
        fs.mkdirSync(dest, { recursive: true });
      }
      fs.readdirSync(src).forEach((item) => {
        this._copyRecursive(path.join(src, item), path.join(dest, item));
      });
    } else {
      fs.copyFileSync(src, dest);
    }
  }
}

module.exports = VenvManager;
