# GSF IR Knowledge Training System (KTS)

**Enterprise-grade document intelligence system with modular architecture**

Version: 0.0.1 | Status: Production Ready | Architecture: Modular (6 Extensions)

---

## 🎯 Overview

KTS is a self-contained VS Code extension system for building enterprise knowledge bases from diverse document types. Designed for air-gapped environments with full offline operation.

### Key Features
- ✅ **Full Offline Operation** - ChromaDB embedding model bundled, no internet required
- ✅ **Modular Architecture** - Install only the processors you need
- ✅ **Size Optimized** - All extensions < 100MB (GitHub compatible)
- ✅ **Zero Dependencies** - No Python or Node.js installation required
- ✅ **Enterprise Ready** - Tested for US Bank deployment

### Supported File Types
- **Base** (Core): .txt, .md, .json, .yaml, .csv, .html, .xml
- **Office** (Processor): .docx, .pptx
- **PDF** (Processor): .pdf
- **Advanced** (NLP): Named Entity Recognition, keyphrase extraction

---

## 📦 Extension Modules

| Extension | Size | Purpose | Required |
|-----------|------|---------|----------|
| **gsf-ir-kts-extension** | ~50-70 MB | Core: Vector DB, embeddings, base converters | Yes |
| **kts-processors-office** | ~22-30 MB | DOCX/PPTX converter | Optional |
| **kts-processors-pdf** | ~40-55 MB | PDF converter | Optional |
| **kts-processors-nlp** | ~80-95 MB | spaCy runtime for NER | Optional |
| **kts-models-spacy** | ~12-15 MB | en_core_web_sm model | For NLP |
| **kts-models-crossencoder** | ~20-25 MB | High-precision ranking | Recommended |

**Total**: ~230 MB for full system

---

## 🚀 Quick Start (Work Laptop)

### Installation

```bash
# Clone extensions repository
git clone https://github.com/karmsud/kts_extensions
cd kts_extensions/0.0.1

# Install extensions (in order)
code --install-extension gsf-ir-kts-extension-0.0.1.vsix
code --install-extension kts-processors-office-0.0.1.vsix
code --install-extension kts-processors-pdf-0.0.1.vsix
code --install-extension kts-models-crossencoder-0.0.1.vsix

# Optional: For Named Entity Recognition
code --install-extension kts-processors-nlp-0.0.1.vsix
code --install-extension kts-models-spacy-0.0.1.vsix
```

### First Use

1. Restart VS Code
2. Press `Ctrl+Shift+P`
3. Type "KTS: Select Source"
4. Choose your document folder
5. System auto-crawls and ingests
6. Ask questions via `Ctrl+Shift+P` → "KTS: Search"

---

## 🏗️ Development Build Process

### Build All Extensions

```powershell
# One command to build all 6 extensions
.\scripts\build_all_modular.ps1 -Version "0.0.1" -Clean
```

**What it does:**
1. Creates Python virtual environment
2. Pre-downloads ChromaDB embedding model (for offline)
3. Builds Core backend + 3 processor backends
4. Downloads ML models (spaCy, CrossEncoder)
5. Packages 6 VSIX files
6. Validates all < 100MB
7. Output: `dist/0.0.1/`

**Duration**: ~15-20 minutes (first build)

### Deploy to GitHub

```powershell
# Sync to kts_extensions repo
.\scripts\sync_to_kts_extensions.ps1 -Version "0.0.1" -Commit

# Push to GitHub
cd ..\kts_extensions
git push origin main
git push origin v0.0.1
```

---

## 📚 Documentation

### User Guides
- **[Quick Reference](docs/MODULAR_QUICK_REFERENCE.md)** - Architecture and deployment
- **[User Guide](docs/USER_GUIDE.md)** - Feature walkthroughs
- **[Configuration](docs/CONFIGURATION.md)** - Settings and customization

### Technical Documentation
- **[Architecture](docs/ARCHITECTURE.md)** - System design
- **[Build Guide](docs/BUILD_GUIDE.md)** - Detailed build process
- **[Modular Implementation](docs/MODULAR_IMPLEMENTATION_STATUS.md)** - Architecture status

---

## 🎯 Use Cases

### Scenario 1: Configuration Analysis
**Install**: Core + CrossEncoder (~68 MB)  
**File Types**: YAML, JSON, INI, CSV  
**Example**: Analyze BatchBridge configs, OpsFlow networks

### Scenario 2: Document Knowledge Base
**Install**: Core + Office + PDF + CrossEncoder (~145 MB)  
**File Types**: + DOCX, PPTX, PDF  
**Example**: Pooling & Servicing Agreements, procedure docs

### Scenario 3: Advanced NLP
**Install**: All 6 extensions (~230 MB)  
**File Types**: All supported  
**Features**: + Named Entity Recognition, automatic tagging  
**Example**: Extract entities from legal documents

---

## 🔧 Technical Stack

### Core Technologies
- **Vector Database**: ChromaDB (with bundled all-MiniLM-L6-v2)
- **Embedding Model**: ONNX-optimized Sentence Transformers
- **Backend**: Python 3.11+ (bundled via PyInstaller)
- **Frontend**: VS Code Extension API (JavaScript)

### Optional Enhancements
- **NER**: spaCy en_core_web_sm
- **Re-ranking**: Cross-encoder ONNX model
- **Document Processors**: PyMuPDF, python-docx, python-pptx

### Build Tools
- PyInstaller 6.0+ (backend bundling)
- @vscode/vsce (extension packaging)
- PowerShell (build automation)

---

## ⚙️ System Requirements

- **OS**: Windows 10/11 (x64)
- **VS Code**: 1.95.0 or later
- **Disk Space**: 500 MB for full installation
- **Memory**: 4 GB RAM minimum, 8 GB recommended
- **Network**: Not required after installation

---

## 🧪 Testing Status

- ✅ Core extension: Base file types (txt, md, json, yaml, csv)
- ✅ Office processor: DOCX/PPTX with image extraction
- ✅ PDF processor: Multi-page PDFs with images
- ✅ NLP processor: Entity extraction and keyphrase
- ✅ CrossEncoder: Re-ranking accuracy improvement
- ✅ Offline operation: No internet after install
- ✅ Size validation: All extensions < 100MB

---

## 📝 Project Structure

```
gsf_ir_kts_agentic_system/
├── extension/                      # Core extension
│   ├── bin/win-x64/kts-backend/   # Bundled Python backend
│   ├── extension.js                # Main VS Code extension
│   └── package.json
├── extension-processors-office/    # DOCX/PPTX processor
├── extension-processors-pdf/       # PDF processor
├── extension-processors-nlp/       # spaCy NER processor
├── extension-models-spacy/         # spaCy model files
├── extension-models-crossencoder/  # CrossEncoder ONNX model
├── backend/                        # Python backend source
│   ├── agents/                     # Ingestion, retrieval agents
│   ├── vector/                     # ChromaDB wrapper
│   ├── graph/                      # Knowledge graph  
│   └── ingestion/                  # File converters
├── packaging/                      # PyInstaller specs
│   ├── kts_backend.spec           # Core backend
│   ├── office_processor.spec       # Office processor
│   ├── pdf_processor.spec          # PDF processor
│   └── nlp_processor.spec          # NLP processor
├── scripts/                        # Build automation
│   ├── build_all_modular.ps1      # Complete build
│   ├── sync_to_kts_extensions.ps1 # Deploy to Git
│   └── download_chromadb_model.py # Pre-cache model
└── docs/                           # Documentation
```

---

## 🤝 Contributing

This is a private enterprise system. For issues or feature requests, contact the maintainer.

---

## 📄 License

MIT License - See [LICENSE.txt](LICENSE.txt)

---

## 🔗 Related Repositories

- **[kts_extensions](https://github.com/karmsud/kts_extensions)** - Pre-built VSIX downloads

---

**Maintained by**: karmsud  
**Last Updated**: 2026-02-16  
**Build Status**: ✅ Production Ready
