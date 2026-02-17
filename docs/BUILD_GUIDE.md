# KTS Agentic System - Build Guide

## Overview

This guide covers building a **single, self-contained VSIX** (~350MB) for the KTS Agentic System VS Code extension. The VSIX includes:

- Complete VS Code extension (JavaScript)
- Bundled Python backend (PyInstaller executable)
- All ML models (ChromaDB ONNX, spaCy NER)
- All document processors (PDF, DOCX, PPTX, HTML)
- **Zero runtime dependencies** - fully offline operation

**Version**: 0.0.1  
**Target Platform**: Windows x64 only  
**Distribution**: GitHub Releases

---

## Prerequisites

### Required Software

1. **Python 3.13.5**
   - Download: https://www.python.org/downloads/
   - **CRITICAL**: Add Python to PATH during installation
   - Verify: `python --version` should show `Python 3.13.5`

2. **Node.js 18+ with npm**
   - Download: https://nodejs.org/
   - Verify: `node --version` && `npm --version`

3. **Git** (for version control)
   - Download: https://git-scm.com/

4. **VS Code Extension Manager (vsce)**
   ```powershell
   npm install -g @vscode/vsce
   ```

5. **Visual Studio C++ Build Tools** (for native Python packages)
   - Download: https://visualstudio.microsoft.com/downloads/ → Build Tools for Visual Studio
   - Install "Desktop development with C++" workload

### System Requirements

- **Disk Space**: ~2 GB free (build artifacts, venv, models)
- **RAM**: 8 GB minimum (16 GB recommended for large document ingestion)
- **Internet**: Required during build only (downloads models, packages)

---

## Build Process

### Quick Start (One Command)

```powershell
# Build complete VSIX (~350MB)
.\scripts\build_vsix.ps1

# Output: extension\kts-agentic-system-0.0.1.vsix
```

### Step-by-Step Build

If you need more control or want to troubleshoot:

#### 1. Download ML Models (~35MB)

```powershell
.\scripts\download_models.ps1
```

**What it does:**
- Downloads ChromaDB ONNX model (sentence-transformers/all-MiniLM-L6-v2)
- Downloads spaCy NER model (en_core_web_sm-3.7.1)
- Caches models in `packaging/models/` for bundling

**Expected output:**
```
packaging/models/
├── chroma/
│   └── all-MiniLM-L6-v2/        (~23MB)
└── spacy/
    └── en_core_web_sm/          (~12MB)
```

#### 2. Build Backend Executable (~250MB)

```powershell
.\scripts\build_backend.ps1
```

**What it does:**
- Creates isolated build venv: `.venv_build/`
- Installs all requirements from `requirements.txt`
- Runs PyInstaller with `packaging/kts_backend.spec`
- Bundles models, processors, and all dependencies
- Outputs to `dist/kts-backend/` directory

**Expected output:**
```
dist/kts-backend/
├── kts-backend.exe              (~15MB)
├── _internal/                   (~235MB)
│   ├── chroma_models/
│   ├── spacy_models/
│   ├── Python DLLs/
│   └── all dependencies
```

**Duration**: 5-10 minutes on typical hardware

#### 3. Package VSIX (~350MB)

```powershell
# If you already built the backend separately:
.\scripts\build_vsix.ps1 -SkipBackendBuild
```

**What it does:**
- Copies `dist/kts-backend/` → `extension/bin/win-x64/kts-backend/`
- Installs npm dependencies in `extension/`
- Packages VSIX with `vsce package`
- Applies `.vscodeignore` rules
- Outputs `kts-agentic-system-0.0.1.vsix`

**Expected output:**
```
extension/kts-agentic-system-0.0.1.vsix  (~350MB)
```

---

## Build Scripts Reference

### `build_vsix.ps1` (Master Orchestrator)

**Usage:**
```powershell
.\scripts\build_vsix.ps1 [-SkipBackendBuild] [-SkipTests] [-Clean]
```

**Parameters:**
- `-SkipBackendBuild`: Skip backend build if already up-to-date
- `-SkipTests`: Skip validation tests (faster, for quick iterations)
- `-Clean`: Clean all build artifacts before building

**Example workflows:**

```powershell
# Full clean build
.\scripts\build_vsix.ps1 -Clean

# Quick rebuild (backend unchanged)
.\scripts\build_vsix.ps1 -SkipBackendBuild

# Fast iteration (skip tests)
.\scripts\build_vsix.ps1 -SkipBackendBuild -SkipTests
```

### `build_backend.ps1` (Backend Only)

**Usage:**
```powershell
.\scripts\build_backend.ps1 [-Clean]
```

Use when:
- Modifying Python backend code
- Testing PyInstaller spec changes
- Debugging bundling issues

### `download_models.ps1` (Models Only)

**Usage:**
```powershell
.\scripts\download_models.ps1
```

Use when:
- Models missing or corrupted
- Upgrading model versions
- Fresh clone of repository

### `test_vsix.ps1` (Validation)

**Usage:**
```powershell
.\scripts\test_vsix.ps1
```

**What it does:**
- Installs VSIX to isolated test profile
- Verifies backend executable
- Checks VSIX size (warns if >500MB)
- Runs smoke tests

**Required before:**
- GitHub releases
- Distribution to users
- Major version bumps

### `clean.ps1` (Cleanup)

**Usage:**
```powershell
.\scripts\clean.ps1 [-All]
```

**Parameters:**
- `-All`: Also removes downloaded models (requires re-download)

**Cleans:**
- `dist/` - PyInstaller output
- `build/` - Intermediate files
- `.venv_build/` - Isolated build venv
- `extension/bin/` - Copied backend
- `extension/*.vsix` - Built packages

---

## Troubleshooting

### Build Fails: "Python not found"

**Symptom:**
```
python : The term 'python' is not recognized...
```

**Solution:**
1. Reinstall Python 3.13.5 with "Add to PATH" checked
2. Or manually add Python to PATH:
   ```powershell
   # Add to System Environment Variables → Path
   C:\Python313\
   C:\Python313\Scripts\
   ```
3. Restart PowerShell and verify:
   ```powershell
   python --version  # Should show: Python 3.13.5
   ```

### Build Fails: "PyInstaller error: Failed to execute script"

**Symptom:**
```
ERROR: Failed to execute script due to unhandled exception!
```

**Common causes:**
1. **Missing C++ Build Tools**
   - Install Visual Studio Build Tools with C++ workload
   - Some packages (e.g., `blis`, `murmurhash`) need native compilation

2. **Antivirus blocking PyInstaller**
   - Temporarily disable antivirus during build
   - Add `dist/` and `.venv_build/` to exclusions

3. **Corrupted venv**
   ```powershell
   .\scripts\clean.ps1 -All
   .\scripts\build_vsix.ps1 -Clean
   ```

### Build Succeeds but VSIX is Huge (>500MB)

**Symptom:**
```
WARNING: VSIX size is 612 MB (exceeds 500 MB limit)
```

**Investigation:**
```powershell
# Check what's included
cd extension
vsce ls

# Check backend size
Get-ChildItem bin\win-x64\kts-backend -Recurse | Measure-Object -Property Length -Sum
```

**Common causes:**
1. **Leftover test data in extension/**
   - Remove any accidentally included sample files
   - Check `.vscodeignore` excludes test data

2. **Duplicate dependencies in PyInstaller**
   - Review `packaging/kts_backend.spec` → `excludes`
   - Add unnecessary packages (e.g., `scipy`, `matplotlib`, `torch`)

3. **Debug symbols included**
   - Ensure PyInstaller runs with `--strip` (already in spec)

### VSIX Installs but Backend Won't Start

**Symptom:**
```
Backend executable not found at: C:\Users\...\kts-backend.exe
```

**Debugging:**
1. Check extension output channel in VS Code:
   ```
   View → Output → "KTS Agentic System"
   ```

2. Verify backend path:
   ```powershell
   # Should exist:
   code --install-extension .\extension\kts-agentic-system-0.0.1.vsix
   # Then check:
   dir $env:USERPROFILE\.vscode\extensions\kts-agentic-system-*\bin\win-x64\kts-backend
   ```

3. Test backend directly:
   ```powershell
   cd extension\bin\win-x64\kts-backend
   .\kts-backend.exe --version
   ```

**Solution if missing:**
- Verify `extension\.vscodeignore` includes `!bin/win-x64/kts-backend/**`
- Rebuild: `.\scripts\build_vsix.ps1 -Clean`

### Backend Starts but Models Not Found

**Symptom:**
```
Model loading failed: [Errno 2] No such file or directory: 'chroma_models/...'
```

**Debugging:**
1. Check if models bundled:
   ```powershell
   dir dist\kts-backend\_internal\chroma_models
   dir dist\kts-backend\_internal\spacy_models
   ```

2. Check PyInstaller spec includes models:
   ```python
   # In packaging/kts_backend.spec → datas
   ('packaging/models/chroma/', 'chroma_models'),
   ('packaging/models/spacy/en_core_web_sm', 'spacy_models/en_core_web_sm'),
   ```

**Solution:**
1. Ensure models downloaded:
   ```powershell
   .\scripts\download_models.ps1
   ```
2. Rebuild backend:
   ```powershell
   .\scripts\build_backend.ps1 -Clean
   ```

### Document Processor Import Errors

**Symptom:**
```
ImportError: No module named 'docx' / 'pptx' / 'fitz'
```

**Solution:**
Ensure `packaging/kts_backend.spec` includes processors in `hidden_imports`:
```python
hiddenimports=[
    # Document processors
    'docx', 'docx.oxml', 'docx.parts', 'docx.text',
    'pptx', 'pptx.oxml', 'pptx.util',
    'fitz',  # PyMuPDF
    'PIL', 'PIL.Image',
    # ... rest
],
```

Rebuild:
```powershell
.\scripts\build_backend.ps1 -Clean
```

---

## Modifying the Build

### Adding New Python Dependencies

1. Add to `requirements.txt`:
   ```txt
   new-package==1.2.3
   ```

2. If the package has hidden imports, add to `packaging/kts_backend.spec`:
   ```python
   hiddenimports=[
       'new_package',
       'new_package.submodule',
       # ...
   ]
   ```

3. Rebuild:
   ```powershell
   .\scripts\build_backend.ps1 -Clean
   ```

### Upgrading ML Models

#### ChromaDB ONNX Model

1. Modify `scripts/download_models.ps1`:
   ```powershell
   # Change model name:
   $ChromaModelName = "sentence-transformers/all-MiniLM-L12-v2"  # New version
   ```

2. Update model reference in backend code:
   ```python
   # In backend/vector/chroma_manager.py or similar
   embedding_function = embedding_functions.ONNXMiniLM_L12_v2()
   ```

3. Clean and rebuild:
   ```powershell
   .\scripts\clean.ps1 -All
   .\scripts\build_vsix.ps1 -Clean
   ```

#### spaCy NER Model

1. Modify `scripts/download_models.ps1`:
   ```powershell
   # Change model version:
   spacy download en_core_web_md  # Larger model
   ```

2. Update spec datas path:
   ```python
   # In packaging/kts_backend.spec
   ('packaging/models/spacy/en_core_web_md', 'spacy_models/en_core_web_md'),
   ```

3. Update backend model loader:
   ```python
   # In backend/ingestion/ner_extractor.py
   bundled_model = Path(sys._MEIPASS) / 'spacy_models' / 'en_core_web_md'
   ```

4. Clean and rebuild:
   ```powershell
   .\scripts\clean.ps1 -All
   .\scripts\build_vsix.ps1 -Clean
   ```

### Reducing VSIX Size

If approaching 500MB limit:

1. **Exclude unnecessary PyInstaller files:**
   ```python
   # In packaging/kts_backend.spec → excludes
   excludes=[
       'matplotlib', 'scipy', 'numpy.distutils',
       'pytest', 'unittest', 'email', 'xml',
       # Add more as needed
   ]
   ```

2. **Use smaller models:**
   - ChromaDB: Switch to smaller embedding model
   - spaCy: Use `en_core_web_sm` instead of `md` or `lg`

3. **Compress executable:**
   ```python
   # In packaging/kts_backend.spec → EXE()
   upx=True,  # Requires UPX install
   upx_exclude=[],
   ```

4. **Remove debug info:**
   ```python
   # In packaging/kts_backend.spec → Analysis()
   optimize=2,  # Python optimization level
   ```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
# .github/workflows/build-release.yml
name: Build and Release VSIX

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: windows-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python 3.13
        uses: actions/setup-python@v5
        with:
          python-version: '3.13.5'
      
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '18'
      
      - name: Install vsce
        run: npm install -g @vscode/vsce
      
      - name: Extract version from tag
        id: get_version
        run: echo "VERSION=${GITHUB_REF#refs/tags/v}" >> $GITHUB_OUTPUT
        shell: bash
      
      - name: Build VSIX
        run: .\scripts\build_vsix.ps1 -Version "${{ steps.get_version.outputs.VERSION }}"
        shell: powershell
      
      - name: Test VSIX
        run: .\scripts\test_vsix.ps1
        shell: powershell
      
      - name: Create Release
        uses: softprops/action-gh-release@v1
        with:
          files: |
            dist/kts-agentic-system-*.vsix
            dist/kts-agentic-system-*.sha256
          generate_release_notes: true
          draft: false
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### Automated Release (Recommended)

Uses the `release.ps1` script to automate the entire process:

```powershell
# Build VSIX
.\scripts\build_vsix.ps1 -Version "0.0.1" -Test

# Create GitHub release (requires gh CLI)
.\scripts\release.ps1 -Version "0.0.1"
```

**What `release.ps1` does:**
1. Validates VSIX exists in `dist/`
2. Generates SHA256 checksum
3. Verifies git status
4. Creates and pushes git tag (`v0.0.1`)
5. Creates GitHub release with auto-generated notes
6. Uploads VSIX and checksum as release assets

**Requirements:**
- **GitHub CLI**: `winget install GitHub.cli` or <https://cli.github.com/>
- **Authentication**: `gh auth login`

### Manual Release Process

If GitHub CLI is not available:

1. **Build and test:**
   ```powershell
   .\scripts\build_vsix.ps1 -Version "0.0.1"
   .\scripts\test_vsix.ps1
   ```

2. **Create and push tag:**
   ```powershell
   git tag -a v0.0.1 -m "Release v0.0.1"
   git push origin v0.0.1
   ```

3. **Create GitHub Release:**
   - Go to: https://github.com/YOUR_ORG/gsf_ir_kts_agentic_system/releases/new
   - Choose tag: `v0.0.1`
   - Title: "KTS Agentic System v0.0.1"
   - Upload assets from `dist/`:
     - `kts-agentic-system-0.0.1.vsix`
     - `kts-agentic-system-0.0.1.sha256`
   - Add release notes (see `dist/release-notes-0.0.1.md`)
   - Click "Publish release"

4. **Verify download:**
   - Download VSIX from release page
   - Verify checksum: `Get-FileHash kts-agentic-system-0.0.1.vsix -Algorithm SHA256`
   - Install: `code --install-extension kts-agentic-system-0.0.1.vsix`
   - Test basic functionality

---

## Architecture Notes

### Why Single VSIX?

**Advantages:**
- ✅ Simplest user experience (one-click install)
- ✅ Fully offline operation (no internet required)
- ✅ All dependencies bundled (no venv setup)
- ✅ Consistent behavior across machines
- ✅ GitHub releases support large files (<500MB)

**Trade-offs:**
- ⚠️ Large download size (~350MB)
- ⚠️ Updates require full re-download
- ⚠️ Build time ~10 minutes

**Alternative approaches considered:**
- Modular build: Separate backend package (rejected: complexity)
- Online model download: Fetch at runtime (rejected: requires internet)

### Bundled Components

| Component | Size | Purpose |
|-----------|------|---------|
| VS Code Extension (JS) | ~5 MB | UI, commands, panels, chat |
| PyInstaller Executable | ~15 MB | CLI entry point |
| Python Runtime + Stdlib | ~50 MB | Interpreter, standard library |
| ChromaDB + Dependencies | ~140 MB | Vector database, ONNX model |
| Document Processors | ~55 MB | PyMuPDF, python-docx, python-pptx, Pillow |
| spaCy + Model | ~27 MB | NER engine, en_core_web_sm |
| LangGraph + LangChain | ~30 MB | Agent framework |
| Other Dependencies | ~28 MB | Pydantic, SQLAlchemy, BeautifulSoup, etc. |
| **Total** | **~350 MB** | |

### Directory Structure After Build

```
extension/
├── kts-agentic-system-0.0.1.vsix     # Packaged extension (~350MB)
├── bin/
│   └── win-x64/
│       └── kts-backend/               # Bundled backend (~250MB)
│           ├── kts-backend.exe        # PyInstaller entry point
│           └── _internal/
│               ├── chroma_models/     # ChromaDB ONNX model
│               ├── spacy_models/      # spaCy NER model
│               └── [Python DLLs]      # All dependencies
├── extension.js                       # Extension entry point
├── lib/
│   ├── backend_runner.js              # Detects and runs kts-backend.exe
│   └── kts_backend.js                 # Backend lifecycle manager
└── [JS modules]                       # Chat, commands, copilot, panels
```

---

## Testing Checklist

Before releasing v0.0.1:

### Build Tests
- [ ] `.\scripts\download_models.ps1` completes without errors
- [ ] `.\scripts\build_backend.ps1` produces `dist/kts-backend/kts-backend.exe`
- [ ] `.\scripts\build_vsix.ps1` produces VSIX ~350MB
- [ ] `.\scripts\test_vsix.ps1` passes all checks

### Installation Tests
- [ ] VSIX installs without errors: `code --install-extension *.vsix`
- [ ] Extension appears in VS Code Extensions panel
- [ ] Backend executable found at correct path
- [ ] Extension activates without errors

### Functional Tests
- [ ] **Crawl command**: Can crawl local directories (docs folder)
- [ ] **Ingest command**: Can ingest documents (PDF, DOCX, PPTX)
- [ ] **Query command**: Returns relevant results
- [ ] **ChromaDB**: Vector embeddings work offline
- [ ] **spaCy NER**: Entity extraction works offline
- [ ] **Document processors**: PDF, DOCX, PPTX, HTML processing works

### Offline Tests
- [ ] Disconnect from internet
- [ ] Restart VS Code
- [ ] Extension still works (crawl, ingest, query)
- [ ] No error messages about missing models

### Performance Tests
- [ ] Extension loads in <5 seconds
- [ ] Backend starts in <10 seconds
- [ ] Ingesting 10 documents takes <30 seconds
- [ ] Query response time <2 seconds

---

## Support & Contribution

### Getting Help

- **GitHub Issues**: https://github.com/YOUR_ORG/gsf_ir_kts_agentic_system/issues
- **Documentation**: See `docs/` folder in repository
- **Build problems**: Check "Troubleshooting" section above

### Contributing

If modifying the build system:

1. Test changes thoroughly:
   ```powershell
   .\scripts\clean.ps1 -All
   .\scripts\build_vsix.ps1 -Clean
   .\scripts\test_vsix.ps1
   ```

2. Update this guide if:
   - Adding new build parameters
   - Changing directory structure
   - Modifying bundled components

3. Keep VSIX size under 500MB:
   - Monitor with `test_vsix.ps1`
   - Optimize if approaching limit

---

## Version History

### v0.0.1 (Current)
- Initial single VSIX build
- Python 3.13.5, Windows x64 only
- ChromaDB ONNX + spaCy en_core_web_sm bundled
- ~350MB total size
- Full offline operation

### Planned (v0.1.0)
- Cross-platform support (macOS, Linux)
- Model update mechanism
- Incremental model downloads
- Reduced VSIX size optimizations

---

## License

See [LICENSE](../LICENSE) file in repository root.

---

**Last Updated**: 2024  
**Maintainer**: KTS Development Team
