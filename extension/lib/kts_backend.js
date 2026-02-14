const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

function getWorkspaceRoot(explicitRoot) {
  if (explicitRoot) {
    return explicitRoot;
  }
  return path.resolve(__dirname, '..', '..');
}

function resolvePythonExecutable(workspaceRoot) {
  const windowsVenvPython = path.join(workspaceRoot, '.venv', 'Scripts', 'python.exe');
  const posixVenvPython = path.join(workspaceRoot, '.venv', 'bin', 'python');

  if (fs.existsSync(windowsVenvPython)) {
    return windowsVenvPython;
  }
  if (fs.existsSync(posixVenvPython)) {
    return posixVenvPython;
  }

  return process.platform === 'win32' ? 'python' : 'python3';
}

function parseJsonOutput(stdout) {
  const trimmed = (stdout || '').trim();
  if (!trimmed) {
    return {};
  }
  return JSON.parse(trimmed);
}

function runCliJson({ workspaceRoot, args, timeoutMs = 120000 }) {
  const root = getWorkspaceRoot(workspaceRoot);
  const pythonExecutable = resolvePythonExecutable(root);
  const pythonArgs = ['-m', 'cli.main', ...args];

  return new Promise((resolve, reject) => {
    const child = spawn(pythonExecutable, pythonArgs, {
      cwd: root,
      stdio: ['ignore', 'pipe', 'pipe'],
      shell: false,
    });

    let stdout = '';
    let stderr = '';
    let timedOut = false;

    const timer = setTimeout(() => {
      timedOut = true;
      child.kill();
    }, timeoutMs);

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
        reject(new Error(`KTS backend command timed out after ${timeoutMs}ms`));
        return;
      }

      if (code !== 0) {
        const message = stderr.trim() || `KTS backend command failed with exit code ${code}`;
        reject(new Error(message));
        return;
      }

      try {
        resolve(parseJsonOutput(stdout));
      } catch (error) {
        reject(new Error(`Failed to parse backend JSON output: ${error.message}`));
      }
    });
  });
}

module.exports = {
  getWorkspaceRoot,
  resolvePythonExecutable,
  runCliJson,
};
