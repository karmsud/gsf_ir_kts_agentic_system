#!/usr/bin/env bash
# =============================================================================
# download_models.sh — Download ML models for offline bundling
#
# Downloads:
#   1. BGE ONNX INT8 embedding model (~140MB) — BAAI/bge-base-en-v1.5
#   2. spaCy en_core_web_sm (~27MB)
#
# Output:
#   packaging/models/bge/bge-base-en-v1.5/onnx-int8/
#   packaging/models/spacy/en_core_web_sm/
#
# The downloaded models are bundled into the VSIX by build_vsix.sh.
#
# Usage:
#   bash scripts/download_models.sh
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$REPO_ROOT/.venv"
PYTHON="$VENV/bin/python"
MODELS_DIR="$REPO_ROOT/packaging/models"

echo "================================================"
echo "  KTS/ABS Model Downloader"
echo "================================================"
echo "Output dir: $MODELS_DIR"

if [ ! -f "$PYTHON" ]; then
  echo "ERROR: venv not found. Run: bash scripts/setup_env.sh first"
  exit 1
fi

mkdir -p "$MODELS_DIR/bge" "$MODELS_DIR/spacy"

# ── 1. BGE base model (PyTorch weights — we ONNX-quantise below) ──────
BGE_DIR="$MODELS_DIR/bge/bge-base-en-v1.5"
if [ -d "$BGE_DIR" ] && [ -f "$BGE_DIR/config.json" ]; then
  echo "[BGE] Already downloaded: $BGE_DIR"
else
  echo "[BGE] Downloading BAAI/bge-base-en-v1.5 from HuggingFace..."
  "$PYTHON" - <<PYEOF
from huggingface_hub import snapshot_download
path = snapshot_download(
    repo_id="BAAI/bge-base-en-v1.5",
    ignore_patterns=["*.msgpack", "*.h5", "flax_model*", "tf_model*", "rust_model*"],
    local_dir="$BGE_DIR",
)
print(f"  Saved to: {path}")
PYEOF
fi

# ── 2. Quantise BGE to ONNX INT8 ──────────────────────────────────────
ONNX_INT8_DIR="$BGE_DIR/onnx-int8"
if [ -d "$ONNX_INT8_DIR" ] && [ -f "$ONNX_INT8_DIR/model_int8.onnx" ]; then
  echo "[BGE-ONNX] Already quantised: $ONNX_INT8_DIR"
else
  echo "[BGE-ONNX] Exporting & quantising to ONNX INT8..."
  "$PYTHON" - <<PYEOF
import os, sys

# Install optimum if not available
try:
    from optimum.onnxruntime import ORTModelForFeatureExtraction
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install",
        "optimum[onnxruntime]", "-q"])
    from optimum.onnxruntime import ORTModelForFeatureExtraction

from optimum.onnxruntime import ORTModelForFeatureExtraction
from optimum.onnxruntime.configuration import AutoQuantizationConfig
from optimum.onnxruntime import ORTQuantizer

model_dir = "$BGE_DIR"
out_dir   = "$ONNX_INT8_DIR"
os.makedirs(out_dir, exist_ok=True)

print("  Exporting to ONNX FP32...")
model = ORTModelForFeatureExtraction.from_pretrained(model_dir, export=True)
model.save_pretrained(out_dir)

print("  Quantising to INT8...")
quantizer = ORTQuantizer.from_pretrained(out_dir)
qconfig   = AutoQuantizationConfig.avx2(is_static=False, per_channel=False)
quantizer.quantize(save_dir=out_dir, quantization_config=qconfig)

print(f"  Saved INT8 model to: {out_dir}")
PYEOF
fi

# ── 3. spaCy en_core_web_sm ───────────────────────────────────────────
SPACY_DIR="$MODELS_DIR/spacy"
if [ -d "$SPACY_DIR/en_core_web_sm" ]; then
  echo "[spaCy] Already downloaded: $SPACY_DIR/en_core_web_sm"
else
  echo "[spaCy] Downloading en_core_web_sm..."
  "$PYTHON" -m spacy download en_core_web_sm 2>&1 | grep -E "(Download|Install|✔|Error)" || true

  # Copy from site-packages to packaging/models/spacy/
  "$PYTHON" - <<PYEOF
import shutil, site, os
from pathlib import Path

for sp in site.getsitepackages():
    candidate = Path(sp) / "en_core_web_sm"
    if candidate.exists():
        dst = Path("$SPACY_DIR/en_core_web_sm")
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(candidate, dst, symlinks=False)
        print(f"  Copied: {candidate} → {dst}")
        break
else:
    print("  WARNING: en_core_web_sm not found in site-packages (installed as link?)")
    print("  Check: python -c \"import en_core_web_sm; print(en_core_web_sm.__file__)\"")
PYEOF
fi

# ── 4. Summary ─────────────────────────────────────────────────────────
echo ""
echo "================================================"
echo "  Model download complete!"
echo ""
echo "  BGE model : $BGE_DIR"
echo "  ONNX INT8 : $ONNX_INT8_DIR"
echo "  spaCy     : $SPACY_DIR"
echo ""
echo "  Next: bash scripts/build_vsix.sh"
echo "================================================"
