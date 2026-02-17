# GSF IR Knowledge Training System (KTS)

**Enterprise-grade document intelligence system with agentic capabilities**

Version: 0.0.1 | Status: Development | Architecture: Single Self-Contained VSIX

---

## 🎯 Overview

KTS is a fully self-contained VS Code extension for building enterprise knowledge bases from diverse document types. Designed for air-gapped environments with complete offline operation.

### Key Features
- ✅ **Full Offline Operation** - All models bundled, zero runtime downloads
- ✅ **Single VSIX Package** - One-click installation (~350MB)
- ✅ **No Dependencies** - No Python, Node.js, or internet required
- ✅ **Complete System** - All processors and models included
- ✅ **Enterprise Ready** - Built for secure, isolated environments

### Supported File Types
- **Documents**: .pdf, .docx, .pptx, .rtf
- **Text**: .txt, .md, .json, .yaml, .csv
- **Web**: .html, .xml
- **Named Entity Recognition** - Automatic entity extraction from all files

### Bundled Components
- **Vector Database**: ChromaDB with ONNX embedding model (all-MiniLM-L6-v2)
- **Document Processors**: PyMuPDF (PDF), python-docx (DOCX), python-pptx (PPTX)
- **NLP Engine**: spaCy with en_core_web_sm model
- **Agent Framework**: LangGraph + LangChain for advanced workflows
- **Python Backend**: PyInstaller executable (~250MB) with all dependencies

**Total Size**: ~350 MB

---

## 🚀 Quick Start

### Installation

1. **Download the VSIX** (~350MB)
   - Visit [Releases](https://github.com/karmsud/gsf_ir_kts_agentic_system/releases)
   - Download `kts-agentic-system-0.0.1.vsix`

2. **Install the extension**
   ```bash
   code --install-extension kts-agentic-system-0.0.1.vsix
   ```

3. **Restart VS Code**

That's it! All models, processors, and dependencies are already bundled. No additional setup needed.

### First Use

1. Open VS Code
2. Press `Ctrl+Shift+P`
3. Type "KTS: Configure Workspace"
4. Select your document folder
5. System auto-crawls and ingests supported files
6. Start asking questions via the KTS chat interface

### Verifying Installation

Check the extension output:
1. Go to **View** → **Output**
2. Select **"KTS Agentic System"** from dropdown
3. Look for: `[Runner] Using ExeRunner (auto: exe available and healthy)`

---

## 🏗️ Building from Source

### Prerequisites

- **Python 3.13.5** (with pip)
- **Node.js 18+** (with npm)
- **VS Code Extension Manager**: `npm install -g @vscode/vsce`
- **Visual Studio C++ Build Tools** (for native packages)
- **GitHub CLI** (optional): `winget install GitHub.cli` (for automated releases)

### Quick Build (One Command)

```powershell
.\scripts\build_vsix.ps1
```

**Output**: `dist/kts-agentic-system-0.0.1.vsix` (~350MB)

### Build + Test + Release

```powershell
# Build and test
.\scripts\build_vsix.ps1 -Version "0.0.1" -Test

# Create GitHub release (automated)
.\scripts\release.ps1 -Version "0.0.1"
```

**Requirements for release.ps1:**
- GitHub CLI authenticated: `gh auth login`
- Git working directory clean
- All changes committed

### Build Steps (Detailed)

```powershell
# 1. Download ML models (~35MB)
.\scripts\download_models.ps1

# 2. Build Python backend with PyInstaller (~250MB)
.\scripts\build_backend.ps1

# 3. Package complete VSIX (~350MB)
.\scripts\build_vsix.ps1 -SkipBackendBuild

# 4. Test the VSIX
.\scripts\test_vsix.ps1

# 5. Create GitHub release
.\scripts\release.ps1 -Version "0.0.1"
```

**Duration**: ~10 minutes on typical hardware

### Clean Build

```powershell
# Remove all build artifacts
.\scripts\clean.ps1

# Full rebuild from scratch
.\scripts\build_vsix.ps1 -Clean
```

For detailed build instructions, troubleshooting, and customization, see [BUILD_GUIDE.md](docs/BUILD_GUIDE.md).

---

## 📚 Documentation

- **[Build Guide](docs/BUILD_GUIDE.md)** - Complete build instructions and troubleshooting
- **[User Guide](docs/USER_GUIDE.md)** - Feature walkthroughs and usage examples
- **[Configuration](docs/CONFIGURATION.md)** - Settings and customization options
- **[CLI Reference](docs/CLI_REFERENCE.md)** - Command-line interface documentation
- **[Architecture](docs/ARCHITECTURE.md)** - System design and technical details

---

## 🎯 Use Cases

### Knowledge Base Construction
- Ingest diverse document types (PDF, DOCX, PPTX, TXT, MD, HTML)
- Automatic vectorization with ChromaDB
- Semantic search across all content
- Entity extraction with spaCy NER

### Document Q&A
- Ask natural language questions about your documents
- Context-aware retrieval using vector similarity
- Agentic workflows for complex queries
- Visual output with charts and summaries

### Enterprise Compliance
- Fully offline operation (air-gapped environments)
- No data leaves your machine
- All models bundled (no external API calls)
- Audit trail for all operations

---

## 🔧 Technical Stack

### Core Technologies
- **Vector Database**: ChromaDB with bundled ONNX embedding model (all-MiniLM-L6-v2)
- **Document Processors**: PyMuPDF (PDF), python-docx (DOCX), python-pptx (PPTX), Pillow (images)
- **NLP Engine**: spaCy with en_core_web_sm model (Named Entity Recognition)
- **Agent Framework**: LangGraph + LangChain (agentic workflows)
- **Backend**: Python 3.13.5 bundled as single executable (PyInstaller)
- **Frontend**: VS Code Extension API (JavaScript)

### Build Tools
- **PyInstaller 6.0+** - Backend bundling with all dependencies
- **@vscode/vsce** - VSIX packaging
- **PowerShell** - Build automation (UTF-8 BOM encoded)

### Package Size Breakdown
| Component | Size | Description |
|-----------|------|-------------|
| Python Backend Executable | ~15 MB | PyInstaller entry point |
| Python Runtime + Stdlib | ~50 MB | Interpreter and standard library |
| ChromaDB + ONNX Model | ~140 MB | Vector DB and embedding model |
| Document Processors | ~55 MB | PyMuPDF, python-docx, python-pptx, Pillow |
| spaCy + NER Model | ~27 MB | en_core_web_sm model |
| LangGraph + LangChain | ~30 MB | Agent framework |
| Other Dependencies | ~28 MB | Pydantic, SQLAlchemy, etc. |
| **Total VSIX** | **~350 MB** | Complete self-contained package |

---

## ⚙️ System Requirements

### Runtime Requirements (User Installation)
- **OS**: Windows 10/11 (x64) - **Windows only for v0.0.1**
- **VS Code**: 1.95.0 or later
- **Disk Space**: 500 MB free (for installation + workspace data)
- **Memory**: 4 GB RAM minimum, 8 GB recommended
- **Network**: **Not required** - fully offline operation after installation

### Build Requirements (Developers Only)
- **Python 3.13.5** (with pip and venv)
- **Node.js 18+** (with npm)
- **Visual Studio C++ Build Tools** (for native package compilation)
- **Internet**: Required during build only (downloads models and packages)

---

## 🧪 Testing Status

**Current Status**: Development - Manual Testing Required

### Completed
- ✅ Build system (PowerShell scripts with UTF-8 BOM)
- ✅ PyInstaller spec (all dependencies bundled)
- ✅ Model bundling (ChromaDB ONNX + spaCy en_core_web_sm)
- ✅ Backend path detection (ExeRunner in extension/lib/)
- ✅ VSIX packaging configuration (.vscodeignore)

### Pending Manual Tests
- ⏳ VSIX installation and activation
- ⏳ Backend executable startup
- ⏳ Document ingestion (PDF, DOCX, PPTX, TXT)
- ⏳ Vector search functionality
- ⏳ spaCy NER extraction
- ⏳ Offline operation (disconnected from internet)
- ⏳ Size validation (<500MB)

**Next Step**: Run `.\scripts\build_vsix.ps1` and manual testing

---

## 📝 Project Structure

```
gsf_ir_kts_agentic_system/
├── extension/                       # VS Code extension
│   ├── extension.js                 # Extension entry point
│   ├── package.json                 # Extension manifest
│   ├── .vscodeignore               # VSIX packaging rules
│   ├── bin/win-x64/kts-backend/    # Bundled Python backend (after build)
│   │   ├── kts-backend.exe          # PyInstaller executable
│   │   └── _internal/               # All dependencies, models, processors
│   ├── chat/                        # Chat interface
│   ├── commands/                    # VS Code commands
│   ├── copilot/                     # Copilot integration
│   ├── lib/                         # Extension libraries
│   │   ├── backend_runner.js        # Backend execution (VenvRunner, ExeRunner)
│   │   └── kts_backend.js           # Backend lifecycle manager
│   └── panels/                      # UI panels
├── backend/                         # Python backend source
│   ├── agents/                      # Ingestion, retrieval agents
│   ├── common/                      # Shared utilities
│   ├── graph/                       # Knowledge graph
│   ├── ingestion/                   # File converters and processors
│   │   ├── ner_extractor.py        # spaCy NER (with bundled model detection)
│   │   ├── pdf_converter.py        # PyMuPDF processor
│   │   ├── docx_converter.py       # python-docx processor
│   │   └── pptx_converter.py       # python-pptx processor
│   ├── retrieval/                   # Query and search
│   └── vector/                      # ChromaDB wrapper
├── cli/                             # CLI entry point
│   └── main.py                      # Command-line interface
├── config/                          # Configuration
│   ├── settings.py                  # Application settings
│   └── *.json                       # Taxonomy, acronyms, etc.
├── packaging/                       # Build specifications
│   ├── kts_backend.spec            # PyInstaller spec (single VSIX approach)
│   └── models/                      # ML models (after download)
│       ├── chroma/                  # ChromaDB ONNX model (~23MB)
│       └── spacy/                   # spaCy en_core_web_sm (~12MB)
├── scripts/                         # Build automation (PowerShell)
│   ├── build_vsix.ps1              # Master build script
│   ├── build_backend.ps1           # Backend-only build
│   ├── download_models.ps1         # Model download and caching
│   ├── test_vsix.ps1               # Validation testing
│   └── clean.ps1                    # Cleanup script
├── docs/                            # Documentation
│   ├── BUILD_GUIDE.md              # ⭐ Complete build instructions
│   ├── ARCHITECTURE.md             # System design
│   ├── USER_GUIDE.md               # Feature documentation
│   └── CLI_REFERENCE.md            # Command reference
├── tests/                           # Test suite
│   ├── test_*.py                   # Unit and integration tests
│   └── golden_*.json               # Test fixtures
├── requirements.txt                 # Python dependencies
└── README.md                        # This file
```

---

## 🤝 Contributing

This is a personal project. For issues or feature requests, please open a GitHub issue.

### Development Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Test the build: `.\scripts\build_vsix.ps1 -Clean`
5. Run tests: `.\scripts\test_vsix.ps1`
6. Commit: `git commit -m 'Add amazing feature'`
7. Push: `git push origin feature/amazing-feature`
8. Open a Pull Request

---

## 📄 License

MIT License - See [LICENSE](LICENSE) file for details.

---

## 🚀 Roadmap

### v0.1.0 (Planned)
- Cross-platform support (macOS, Linux)
- Model update mechanism (without full reinstall)
- Performance optimizations (reduce VSIX size)
- Enhanced UI/UX for chat interface

### Future
- Cloud sync for knowledge base (optional)
- Multi-language support (beyond English)
- Advanced visualization (knowledge graphs, entity networks)
- Plugin system for custom processors

---

**Maintained by**: karmsud  
**Last Updated**: 2024  
**Build Status**: 🔨 Development - Manual Testing Phase

For detailed build instructions and troubleshooting, see **[BUILD_GUIDE.md](docs/BUILD_GUIDE.md)**.

