#!/usr/bin/env bash
# =============================================================================
# setup_env.sh — macOS Development Environment Setup
#
# Creates a Python virtual environment and installs all project dependencies.
# Run once after cloning the repository.
#
# Usage:
#   bash scripts/setup_env.sh
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
PYTHON_MIN="3.9"

echo "============================================="
echo "  KTS/ABS Agentic System — Environment Setup"
echo "============================================="
echo "Repo: $REPO_ROOT"

# ── 1. Check Python version ────────────────────────────────────────────
PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" &>/dev/null; then
  echo "ERROR: python3 not found. Install Python $PYTHON_MIN+ first."
  exit 1
fi

PYTHON_VERSION=$("$PYTHON_BIN" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python: $PYTHON_VERSION (via $PYTHON_BIN)"

# ── 2. Create venv ─────────────────────────────────────────────────────
if [ -d "$VENV_DIR" ]; then
  echo "Virtual environment already exists at $VENV_DIR"
  echo "To recreate: rm -rf $VENV_DIR && bash scripts/setup_env.sh"
else
  echo "Creating virtual environment..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  echo "Created: $VENV_DIR"
fi

PIP="$VENV_DIR/bin/pip"
PYTHON="$VENV_DIR/bin/python"

# ── 3. Upgrade pip ─────────────────────────────────────────────────────
echo ""
echo "Upgrading pip..."
"$PIP" install --quiet --upgrade pip setuptools wheel

# ── 4. Install core dependencies (numpy constrained for spaCy compat) ──
echo ""
echo "Installing dependencies (this may take a few minutes)..."

"$PIP" install --quiet \
  click tqdm PyYAML networkx scipy pandas \
  chromadb \
  "onnxruntime>=1.14.0" \
  PyMuPDF python-docx python-pptx \
  beautifulsoup4 Pillow "lxml>=4.9.0" olefile \
  tokenizers openai \
  pytest

# ── 5. Install spaCy with Python-version-aware constraints ────────────
PYTHON_MINOR=$("$PYTHON" -c "import sys; print(sys.version_info.minor)")
if [ "$PYTHON_MINOR" -lt 10 ]; then
  echo ""
  echo "Python < 3.10 detected — installing spaCy 3.6 (thinc 8.1 series)..."
  "$PIP" install --quiet "numpy<2.0" "spacy>=3.5,<3.7"
else
  echo ""
  echo "Python 3.10+ detected — installing spaCy 3.7+..."
  "$PIP" install --quiet "spacy>=3.7.0"
fi

# ── 6. Download spaCy model ────────────────────────────────────────────
echo ""
echo "Downloading spaCy en_core_web_sm model..."
"$PYTHON" -m spacy download en_core_web_sm 2>&1 | grep -E "(Download|Installed|Error|✔)" || true

# ── 7. Verify key imports ──────────────────────────────────────────────
echo ""
echo "Verifying installation..."
"$PYTHON" - <<'VERIFY'
import sys
failures = []
for pkg in ["click","tqdm","yaml","networkx","scipy","pandas",
            "chromadb","onnxruntime","fitz","docx","pptx",
            "bs4","PIL","lxml","olefile","tokenizers","openai","pytest"]:
    try:
        __import__(pkg)
    except ImportError:
        failures.append(pkg)

try:
    import spacy
    spacy.load("en_core_web_sm")
except Exception as e:
    failures.append(f"spacy/model ({e})")

if failures:
    print(f"MISSING: {failures}")
    sys.exit(1)
print("All dependencies verified OK")
VERIFY

echo ""
echo "============================================="
echo "  Setup complete!"
echo "  Activate with: source .venv/bin/activate"
echo "  Then run models download: bash scripts/download_models.sh"
echo "============================================="
