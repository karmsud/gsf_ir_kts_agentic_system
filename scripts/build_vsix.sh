#!/usr/bin/env bash
# =============================================================================
# build_vsix.sh — macOS/Linux VSIX build script
#
# Builds the VS Code extension VSIX package that bundles:
#   - The Python backend (PyInstaller executable via Docker cross-compile OR
#     direct build on Windows; on macOS we build the macOS binary for dev)
#   - ML models (BGE ONNX INT8 + spaCy en_core_web_sm)
#   - VS Code extension JavaScript
#
# NOTE: The production VSIX targets Windows x64 (PyInstaller .exe).
#       On macOS this script builds a development VSIX with the macOS backend
#       binary, suitable for local testing and CI.
#
# Prerequisites:
#   - Node.js + npm (for vsce)
#   - Python venv at .venv (run setup_env.sh first)
#   - Models downloaded (run download_models.sh first)
#
# Usage:
#   bash scripts/build_vsix.sh [--skip-backend] [--skip-models]
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

VENV="$REPO_ROOT/.venv"
PYTHON="$VENV/bin/python"
MODELS_DIR="$REPO_ROOT/packaging/models"
EXT_DIR="$REPO_ROOT/extension"
DIST_DIR="$REPO_ROOT/dist"

SKIP_BACKEND=false
SKIP_MODELS=false

for arg in "$@"; do
  case "$arg" in
    --skip-backend) SKIP_BACKEND=true ;;
    --skip-models)  SKIP_MODELS=true ;;
  esac
done

echo "================================================"
echo "  KTS/ABS VSIX Builder (macOS)"
echo "================================================"
echo "Repo       : $REPO_ROOT"
echo "Models dir : $MODELS_DIR"
echo "Output dir : $DIST_DIR"

mkdir -p "$DIST_DIR"

# ── 1. Pre-flight checks ──────────────────────────────────────────────
echo ""
echo "[1/5] Pre-flight checks..."

if ! command -v node &>/dev/null; then
  echo "ERROR: node not found. Install via: brew install node"
  exit 1
fi
if ! command -v npm &>/dev/null; then
  echo "ERROR: npm not found."
  exit 1
fi
echo "  Node: $(node --version)  npm: $(npm --version)"

if [ ! -f "$PYTHON" ]; then
  echo "ERROR: Python venv not found. Run: bash scripts/setup_env.sh"
  exit 1
fi
echo "  Python: $("$PYTHON" --version)"

# Install vsce if missing
if ! command -v vsce &>/dev/null && ! npx --yes @vscode/vsce --version &>/dev/null 2>&1; then
  echo "  Installing @vscode/vsce..."
  npm install -g @vscode/vsce 2>&1 | tail -3
fi

# ── 2. Download/verify models ─────────────────────────────────────────
if [ "$SKIP_MODELS" = false ]; then
  echo ""
  echo "[2/5] Verifying models..."
  if [ ! -f "$MODELS_DIR/bge/bge-base-en-v1.5/config.json" ]; then
    echo "  Models missing — running download_models.sh..."
    bash "$REPO_ROOT/scripts/download_models.sh"
  else
    echo "  Models OK"
  fi
else
  echo "[2/5] Skipping model verification (--skip-models)"
fi

# ── 3. Build Python backend (PyInstaller) ────────────────────────────
if [ "$SKIP_BACKEND" = false ]; then
  echo ""
  echo "[3/5] Building Python backend (PyInstaller)..."

  # Install pyinstaller if missing
  "$PYTHON" -m pip show pyinstaller &>/dev/null 2>&1 || \
    "$PYTHON" -m pip install pyinstaller --quiet

  # Copy models into packaging/ for bundling
  if [ -d "$MODELS_DIR/bge/bge-base-en-v1.5/onnx-int8" ]; then
    echo "  Copying BGE ONNX INT8 model..."
    mkdir -p "$REPO_ROOT/packaging/models/bge-base-en-v1.5/onnx-int8"
    cp -r "$MODELS_DIR/bge/bge-base-en-v1.5/onnx-int8/." \
          "$REPO_ROOT/packaging/models/bge-base-en-v1.5/onnx-int8/"
  fi

  echo "  Running PyInstaller..."
  "$PYTHON" -m PyInstaller \
    "$REPO_ROOT/packaging/kts_backend.spec" \
    --distpath "$REPO_ROOT/dist/backend" \
    --workpath "$REPO_ROOT/build/pyinstaller" \
    --noconfirm 2>&1 | tail -10

  # Copy built backend into extension/bin/
  PLATFORM="$(uname -m)"
  if [ "$PLATFORM" = "arm64" ]; then
    BIN_PLATFORM="macos-arm64"
  else
    BIN_PLATFORM="macos-x64"
  fi
  mkdir -p "$EXT_DIR/bin/$BIN_PLATFORM"
  cp -r "$REPO_ROOT/dist/backend/kts-backend/." "$EXT_DIR/bin/$BIN_PLATFORM/kts-backend/"
  echo "  Backend binary: $EXT_DIR/bin/$BIN_PLATFORM/kts-backend/"
else
  echo "[3/5] Skipping backend build (--skip-backend)"
fi

# ── 4. Bundle models into extension ──────────────────────────────────
echo ""
echo "[4/5] Copying models to extension bundle..."

EXT_MODELS="$EXT_DIR/models"
mkdir -p "$EXT_MODELS"

if [ -d "$MODELS_DIR/bge/bge-base-en-v1.5/onnx-int8" ]; then
  echo "  Copying BGE ONNX INT8..."
  mkdir -p "$EXT_MODELS/bge-base-en-v1.5/onnx-int8"
  cp -r "$MODELS_DIR/bge/bge-base-en-v1.5/onnx-int8/." \
        "$EXT_MODELS/bge-base-en-v1.5/onnx-int8/"
fi

if [ -d "$MODELS_DIR/spacy/en_core_web_sm" ]; then
  echo "  Copying spaCy model..."
  mkdir -p "$EXT_MODELS/spacy"
  cp -r "$MODELS_DIR/spacy/en_core_web_sm" "$EXT_MODELS/spacy/"
fi

# ── 5. Package VSIX ──────────────────────────────────────────────────
echo ""
echo "[5/5] Packaging VSIX..."

cd "$EXT_DIR"
if [ -f "package-lock.json" ]; then
  npm ci --silent 2>/dev/null || npm install --silent
fi

# Get version from package.json
VERSION=$(node -e "console.log(require('./package.json').version)")
VSIX_NAME="kts-agentic-system-$VERSION.vsix"

# Use npx vsce to avoid global install requirement
npx --yes @vscode/vsce package \
  --out "$DIST_DIR/$VSIX_NAME" \
  --no-dependencies 2>&1 | tail -5

echo ""
echo "================================================"
echo "  VSIX built successfully!"
echo ""
echo "  Output: $DIST_DIR/$VSIX_NAME"
echo ""
echo "  Install with:"
echo "    code --install-extension $DIST_DIR/$VSIX_NAME"
echo "================================================"
