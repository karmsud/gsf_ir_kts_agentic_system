# KTS Extension User Guide

## Overview
The **KTS (Knowledge Transfer System) Extension** brings enterprise knowledge search and retrieval directly into VS Code. It combines a Python-based backend with VS Code UI to provide intelligent search, citations, and context-aware assistance.

**Version**: 1.0.0 (Phase 1 - Self-Contained)

## Prerequisites

### Required
- **Python 3.10+** installed on your machine
  - Windows: Use [python.org](https://www.python.org/downloads/) installer or Microsoft Store
  - Verify: `python --version` or `py -3 --version`

### Optional
- Network access to knowledge source folder (for enterprise deployments)

### NOT Required (Phase 1 removes these)
- ❌ Clone gsf_ir_kts_agentic_system repository
- ❌ Manually create `.venv`
- ❌ Run `pip install -r requirements.txt`

## Installation

### Step 1: Install Extension
1. Download `gsf-ir-kts-1.0.0.vsix`
2. Open VS Code
3. Go to **Extensions** view (Ctrl+Shift+X)
4. Click **...** (More Actions) → **Install from VSIX...**
5. Select `gsf-ir-kts-1.0.0.vsix`

### Step 2: First Activation (Automatic Bootstrap)
1. After installation, VS Code will show:
   ```
   KTS: Setting up backend (first-time setup, this may take a few minutes)...
   ```
2. The extension will:
   - Detect Python
   - Create virtual environment
   - Install dependencies
   - This takes **~30-90 seconds**
3. When complete:
   ```
   KTS: Backend setup complete ✓
   ```

### Troubleshooting Bootstrap
If setup fails:
1. Check **Output** panel → Select **KTS** channel
2. Run **KTS: Doctor** command for diagnostics
3. Common issues:
   - Python not found → Install Python or set `kts.pythonPath`
   - Network proxy → Configure pip proxy
   - Disk space → Free up space in `%APPDATA%`

## Configuration

### Step 1: Set Source Path
The source path is where your raw knowledge documents live (Word docs, PDFs, Markdown, etc.).

**Option A: Use Command**
1. Open Command Palette (Ctrl+Shift+P)
2. Run: **KTS: Select Source Folder**
3. Browse to folder (e.g., `\\network-share\kb-docs\` or `C:\kb-source\`)

**Option B: Use Settings**
1. Open Settings (Ctrl+,)
2. Search: `kts.sourcePath`
3. Enter path: `\\network-share\kb-docs\`

### Step 2: (Optional) Configure KB Workspace
By default, KTS stores its knowledge base (index, vectors, graph) in VS Code global storage.

To use a custom location:
1. Open Settings
2. Search: `kts.kbWorkspacePath`
3. Enter local path: `C:\kts-data\kb-workspace\`

**Default Location**:
```
%APPDATA%\Code\User\globalStorage\gsf-ir.gsf-ir-kts-extension\kts-kb\default\
```

## Basic Workflow

### 1. Initialize Knowledge Base

#### Crawl → Discover Files
```
Command Palette → KTS: Crawl
```
- Scans source path for supported files
- Creates file inventory
- Output: `N files discovered`

#### Ingest → Process Files
```
Command Palette → KTS: Ingest
```
- Extracts content from discovered files
- Creates embeddings and graph
- Output: `N documents ingested`

**Shortcut: Crawl + Ingest**
```
Command Palette → KTS: Crawl & Ingest
```
Runs both operations sequentially.

### 2. Query Knowledge Base

#### Option A: Interactive Search
```
Command Palette → KTS: Search
```
1. Enter query: *"How do I configure BatchBridge connector?"*
2. View results in Output panel
3. Results include:
   - Top 5 matching chunks
   - Document paths
   - Relevance scores

#### Option B: Copilot Chat Integration
```
In Copilot Chat:
@kts /search How do I configure BatchBridge connector?
```
Results inline in chat with context.

#### Option C: Deep Search (More Context)
```
@kts /deep What are all the steps for deploying ToolX?
```
Returns more chunks for complex queries.

### 3. Check Status
```
Command Palette → KTS: Status
```
Shows:
- Document count
- Total chunks
- Last crawl/ingest timestamp
- KB workspace path

### 4. Diagnostics
```
Command Palette → KTS: Doctor
```
Comprehensive health check:
- Python detected
- Venv status
- Backend version
- KB workspace status
- Recent logs
- Configuration

## Advanced Usage

### Multi-Step Ingestion
For large knowledge bases:
1. **Crawl** first (fast) to verify file discovery
2. Check logs for any skipped/errored files
3. **Ingest** (slower) to process
4. Monitor progress in Output panel

### Incremental Updates
After adding new documents to source:
1. **KTS: Crawl** → Discovers new files
2. **KTS: Ingest** → Processes only new/changed files

### View Logs
```
Command Palette → KTS: Open Logs
```
Opens logs directory in File Explorer:
```
<kbWorkspace>\logs\
  20260214_172345_crawl.log
  20260214_172400_ingest.log
  20260214_172500_search.log
```

## Configuration Reference

### Settings (`kts.*`)

| Setting | Description | Default |
|---------|-------------|---------|
| `kts.sourcePath` | Network/local folder with KB documents | `""` (not set) |
| `kts.kbWorkspacePath` | Local KB workspace (manifest/index/graph) | `""` (use global storage) |
| `kts.pythonPath` | Optional Python executable path | `""` (auto-detect) |
| `kts.backendChannel` | Backend source: `bundled` or `workspace` | `bundled` |
| `kts.logLevel` | Log verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |

### Environment Variables (Advanced)
These are set automatically by the extension:

- `KTS_KB_PATH` - Points to KB workspace
- `KTS_SOURCE_PATH` - Points to source folder (during crawl/ingest)

## Commands Reference

| Command | Description | Use Case |
|---------|-------------|----------|
| **KTS: Select Source Folder** | Choose source path | First-time setup |
| **KTS: Crawl** | Discover files | After adding new documents |
| **KTS: Ingest** | Process documents | After crawl |
| **KTS: Crawl & Ingest** | Combined operation | Full refresh |
| **KTS: Status** | Show KB status | Check document count |
| **KTS: Search** | Interactive search | Quick queries |
| **KTS: Doctor** | Diagnostics | Troubleshooting |
| **KTS: Open Logs** | View log files | Debug issues |

## Troubleshooting

### Extension Not Activating
1. Check **Output** → **KTS** channel
2. Look for bootstrap errors
3. Run **KTS: Doctor**

### Python Not Found
**Symptoms**: `Python 3.10+ not found`

**Solutions**:
1. Install Python from [python.org](https://www.python.org/)
2. Or, set `kts.pythonPath` to explicit path:
   ```
   "kts.pythonPath": "C:\\Python310\\python.exe"
   ```

### Bootstrap Timeout
**Symptoms**: Setup hangs during `Installing dependencies...`

**Solutions**:
1. Check internet connection (needs to download packages)
2. Configure pip proxy if behind firewall:
   ```powershell
   # Set before installing extension
   $env:HTTP_PROXY = "http://proxy:8080"
   $env:HTTPS_PROXY = "http://proxy:8080"
   ```
3. Retry: Reload VS Code window (Ctrl+R)

### Crawl/Ingest Fails
**Symptoms**: `Source path does not exist`

**Solutions**:
1. Verify source path is accessible
2. For network paths, check permissions
3. Run **KTS: Select Source Folder** to reconfigure

### No Search Results
**Symptoms**: Search returns 0 results

**Checks**:
1. Run **KTS: Status** → Document count > 0?
2. If 0, run **KTS: Crawl & Ingest**
3. Check logs: **KTS: Open Logs**

### Backend Health Check Failed
**Symptoms**: Doctor shows `healthCheck: false`

**Solutions**:
1. Check **Output** → **KTS** for errors
2. Delete venv and re-bootstrap:
   - Close VS Code
   - Delete: `%APPDATA%\Code\User\globalStorage\gsf-ir.gsf-ir-kts-extension\kts-venv\`
   - Reopen VS Code → Extension re-bootstraps

## FAQ

### Q: Where is my knowledge base stored?
**A**: By default, in VS Code global storage:
```
%APPDATA%\Code\User\globalStorage\gsf-ir.gsf-ir-kts-extension\kts-kb\default\
```
You can change this with `kts.kbWorkspacePath` setting.

### Q: Can I have multiple knowledge bases?
**A**: Phase 1 supports one KB workspace. Multi-profile support planned for Phase 2.

### Q: Does this work offline?
**A**: After initial setup (which requires internet for pip packages), yes. The KB and search are local.

### Q: How do I update to a new version?
**A**: Install new VSIX. Extension auto-creates new venv for new backend version.

### Q: Can I share the KB workspace across machines?
**A**: Not recommended (embeddings are machine-specific). Each machine should crawl+ingest separately.

### Q: What file types are supported?
**A**: Markdown, Word (`.docx`), PDF, plain text, structured data (JSON/CSV). See backend documentation for full list.

### Q: How do I uninstall?
**A**:
1. Uninstall extension from VS Code
2. Manually delete global storage folder:
   ```
   %APPDATA%\Code\User\globalStorage\gsf-ir.gsf-ir-kts-extension\
   ```

## Development Mode (Workspace Channel)

For developers working on the KTS backend:

1. Clone `gsf_ir_kts_agentic_system` repo
2. Create `.venv` and install dependencies
3. Open repo in VS Code
4. Set `kts.backendChannel` to `"workspace"`
5. Extension uses local repo backend instead of bundled

This allows testing backend changes without re-packaging extension.

## Support

- **Logs**: **KTS: Open Logs** command
- **Diagnostics**: **KTS: Doctor** command
- **Output Channel**: View → Output → Select "KTS"

## Appendix: File Locations

### Extension Installation
```
%USERPROFILE%\.vscode\extensions\gsf-ir.gsf-ir-kts-extension-1.0.0\
```

### Global Storage (Managed Venv & Backend)
```
%APPDATA%\Code\User\globalStorage\gsf-ir.gsf-ir-kts-extension\
├── kts-venv\1.0.0\          # Python virtual environment
├── kts-backend\1.0.0\       # Unpacked backend code
└── kts-kb\default\          # Knowledge base workspace
    ├── manifest.json
    ├── documents\
    ├── vectors\
    ├── graph\
    └── logs\
```

### KB Workspace Structure
```
kts-kb\default\
├── manifest.json            # KB metadata
├── documents\               # Ingested document records
├── vectors\                 # Embedding vectors
├── graph\                   # Knowledge graph
└── logs\                    # Operation logs
    ├── 20260214_172345_crawl.log
    ├── 20260214_172400_ingest.log
    └── 20260214_172500_search.log
```
