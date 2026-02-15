# GSF IR KTS Agentic System

Localized Agentic RAG system for knowledge retrieval, impact analysis, and freshness auditing.Designed for secure, self-contained environments with zero external API dependencies for core retrieval.

**Status**: Active Development  
**Version**: 1.0.0 (SemVer)

---

## 📚 Documentation Index

| Topic | Description | Link |
| :--- | :--- | :--- |
| **Architecture** | System Design, Components, Data Flow | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| **CLI Reference** | Command Line Tool Usage (Ingest, Retrieve, Audit) | [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md) |
| **Configuration** | Settings, Environment Variables, Paths | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| **Extension** | VS Code Extension Dev, Build, Debugging | [docs/EXTENSION.md](docs/EXTENSION.md) |
| **Testing** | Evaluation Suite, Unit Tests, Metrics | [docs/TESTING.md](docs/TESTING.md) |
| **Release** | Versioning, Packaging, Publishing | [docs/RELEASE.md](docs/RELEASE.md) |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- VS Code (for Extension)
- PowerShell 7+ (Recommended for scripts)

### Setup (Developer)

```powershell
# Clone repository
git clone <repo-url>
cd gsf_ir_kts_agentic_system

# Create Virtual Environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install Dependencies
pip install -r requirements.txt

# Verify Installation
python -m cli.main --version
```

### Setup (VS Code Extension User)

1. **Install from VSIX**:
   - Download the latest `.vsix` release.
   - In VS Code: `Ctrl+Shift+P` -> `Extensions: Install from VSIX...`
2. **Reload VS Code**.
3. **Open Copilot Chat**:
   - Type `@kts help` to verify connection.

---

## 🛠️ Core Workflows

### 1. Ingestion (Maintenance Engineer)
Aggregate documentation from network shares or local folders into the Knowledge Base.

```powershell
# Crawl and Ingest a directory
python -m cli.main ingest --path "C:\Docs\Policies" --recursive

# Update Search Index
python -m cli.main index --rebuild
```

### 2. Retrieval (User)
Query the system for answers grounded in your documentation.

```powershell
python -m cli.main query "What is the policy on remote work?"
```

### 3. Evaluation (QA)
Run the standard accuracy and performance suite.

```powershell
python scripts/run_full_eval_suite.py --tier A2
```

---

## 🏗️ Build Editions

| Tier | Features | Target Audience | Size |
| :--- | :--- | :--- | :--- |
| **A2 (Full)** | Text + Image Analysis + OCR | Research/Engineering | large |
| **A3 (Light)** | Text Only | Standard Users | small |

See [docs/EXTENSION.md](docs/EXTENSION.md) for build instructions.

---
**Maintained by**: GSF IR Team  
**License**: Proprietary
