# Extension Architecture Audit: KTS Agentic System

## 1. Executive Summary
**Verdict: Option B - UI Wrapper (Thin Client)**

The **KTS Agentic System VS Code Extension** functions as a thin UI wrapper that delegates all business logic to the Python backend residing in the user's active workspace. It is **not** a self-contained application.

The extension is designed to operate specifically on the `gsf_ir_kts_agentic_system` repository (or a structure compatible with it) when opened in VS Code. It assumes the presence of a local Python environment and the specific directory structure of this repository.

## 2. Evidence of Architecture

### A. Execution Delegation
The extension does not contain the business logic for crawling, ingestion, or analysis. Instead, it spawns a child process to execute the Python CLI found in the workspace.

*   **File:** `extension/lib/kts_backend.js`
*   **Mechanism:** `runCliJson` function.
*   **Command:** Spawns `python -m cli.main ...`
*   **Conclusion:** The extension relies 100% on the Python code being present and runnable in the workspace.

### B. Environment Dependency
The extension explicitly checks for and uses a specific Python virtual environment structure expected in the workspace root.

*   **File:** `extension/lib/kts_backend.js`
*   **Mechanism:** `resolvePythonExecutable` function checks:
    *   `{workspaceRoot}/.venv/Scripts/python.exe` (Windows)
    *   `{workspaceRoot}/.venv/bin/python` (POSIX)
*   **Conclusion:** The extension is tightly coupled to the local development environment setup. It does not bundle a Python runtime.

### C. Workspace Orientation
The activation logic prioritizes the currently open VS Code workspace folder as the context for execution.

*   **File:** `extension/extension.js`
*   **Logic:** `const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri?.fsPath || getWorkspaceRoot();`
*   **Conclusion:** The operations are context-dependent on what the user has opened, consistent with a tool meant to manipulate the open codebase.

## 3. Deployment & Usage Implications

### Prerequisites for Users
For the extension to function correctly, the following conditions must be met on the user's machine:
1.  **Repository:** The `gsf_ir_kts_agentic_system` repo must be cloned.
2.  **Workspace:** The repo folder must be opened as the root workspace in VS Code.
3.  **Environment:** A Python virtual environment must be created at `.venv` in the repo root.
4.  **Dependencies:** Dependencies must be installed (e.g., via `pip install -r requirements.txt`) so that `cli.main` is executable.

### Packaging
*   There is no need to bundle the `backend/`, `cli/`, or `config/` folders into the `.vsix` extension package.
*   The extension package only needs to contain:
    *   `extension/extension.js`
    *   `extension/lib/`
    *   `extension/commands/`
    *   `extension/package.json`
    *   `extension/chat/` (and related UI assets)

### Potential Risks
*   **Environment Mismatch:** If the user has not set up `.venv` or has missing dependencies, the extension commands will fail silently or with generic exit codes.
*   **Pathing Issues:** If the user opens a subdirectory (e.g., `backend/`) as the workspace root instead of the repo root, the relative path resolution for `.venv` and `cli` module import will likely fail.

## 4. Recommendations

1.  **Add Pre-flight Checks:** The extension should verify the existence of `.venv` and `cli/main.py` on activation and provide a helpful error message ("Please run setup.py or create .venv") instead of failing during command execution.
2.  **Documentation:** Explicitly state in the `README.md` that this is a "Workspace Companion" extension, not a standalone tool.
3.  **Configurability:** Consider adding a VS Code setting (e.g., `kts.pythonPath`) to allow users to specify a Python interpreter if they are not using the standard `.venv` location.
