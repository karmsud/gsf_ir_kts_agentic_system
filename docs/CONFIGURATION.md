# KTS Configuration Guide

**Source of Truth**: `config/settings.py`

## 1. Environment Variables

The backend uses a single primary environment variable to control data location:

| Variable | Description | Default |
|----------|-------------|---------|
| `KTS_KB_PATH` | Path where the knowledge base (`.kts` folder) is stored. | User's home directory (`~/.kts`) |

If `KTS_KB_PATH` is not set, the system defaults to creating `.kts` in the root of the source directory being crawled (workspace-scoped).

## 2. Supported File Formats

The backend uses specific Python libraries to parse these formats.

| Extension | Library | Tier A2 (Full) | Tier A3 (Light) |
|-----------|---------|----------------|-----------------|
| `.docx` | `python-docx` | ✅ | ✅ |
| `.pdf` | `PyMuPDF` | ✅ | ❌ |
| `.pptx` | `python-pptx` | ✅ | ❌ |
| `.html` | `beautifulsoup4` | ✅ | ✅ |
| `.md` | Built-in | ✅ | ✅ |
| `.txt` | Built-in | ✅ | ✅ |
| `.json` | Built-in | ✅ | ✅ |
| `.yaml` | `PyYAML` | ✅ | ✅ |
| `.ini` | Built-in | ✅ | ✅ |
| `.csv` | Built-in | ✅ | ✅ |
| `.png` | Built-in (as raw file) | ✅ | ✅ |

**Note**: Tier A3 builds exclude `PyMuPDF` and `python-pptx` to reduce executable size by ~60%. Attempting to ingest PDF/PPTX in A3 will result in a graceful skip or error log.

## 3. Extension Settings (VS Code)

Once installed, the KTS extension contributes the following settings (`.vscode/settings.json`):

- `kts.kbPath`: Overrides `KTS_KB_PATH`.
- `kts.logLevel`: Controls verbosity (`info`, `debug`, `error`).
- `kts.search.maxResults`: Limit number of search results (default: 5).
- `kts.crawl.auto`: Boolean to enable auto-crawl on folder open.
