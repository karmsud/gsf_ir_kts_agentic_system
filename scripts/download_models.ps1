<#
.SYNOPSIS
    Download and cache ML models for offline VSIX bundling

.DESCRIPTION
    This script downloads:
    1. BGE ONNX INT8 embedding model (Phase 5 WS-1 - REQUIRED)
    2. Cross-Encoder ONNX model for reranking (REQUIRED)
    3. spaCy NER model (en_core_web_sm)
    
    Models are cached to packaging/models/ for PyInstaller bundling.
    
    NOTE: As of Phase 5, the legacy ChromaDB MiniLM-L6-v2 model is no longer used.
    All embeddings now use the BGE ONNX INT8 model (768-dim).

.PARAMETER Force
    Force re-download even if models exist

.EXAMPLE
    .\scripts\download_models.ps1
    .\scripts\download_models.ps1 -Force
#>

param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "KTS Model Download Script (Phase 5 + Cross-Encoder)" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

# Paths
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ModelsDir = Join-Path $RepoRoot "packaging\models"
$BgeDir = Join-Path $ModelsDir "bge"
$CeDir = Join-Path $ModelsDir "cross_encoder"
$SpacyDir = Join-Path $ModelsDir "spacy"
$VenvPath = Join-Path $RepoRoot ".venv_build"

# Create directories
New-Item -ItemType Directory -Force -Path $BgeDir | Out-Null
New-Item -ItemType Directory -Force -Path $CeDir | Out-Null
New-Item -ItemType Directory -Force -Path $SpacyDir | Out-Null

Write-Host "[1/3] Checking Python environment..." -ForegroundColor Yellow

# Check if venv exists
if (-not (Test-Path $VenvPath)) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Green
    python -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create virtual environment"
    }
}

# Activate venv
$ActivateScript = Join-Path $VenvPath "Scripts\Activate.ps1"
& $ActivateScript

Write-Host "Python: $(python --version)" -ForegroundColor Green
Write-Host ""

# ═══════════════════════════════════════════════════════════════════════════
# BGE ONNX INT8 Model (REQUIRED)
# ═══════════════════════════════════════════════════════════════════════════

Write-Host "[2/3] Downloading BGE ONNX INT8 embedding model..." -ForegroundColor Yellow

$BgeModelFile = Join-Path $BgeDir "model.onnx"
if ((Test-Path $BgeModelFile) -and -not $Force) {
    Write-Host "BGE model already exists at: $BgeDir" -ForegroundColor Gray
    Write-Host "Use -Force to re-download" -ForegroundColor Gray
} else {
    # Call the dedicated BGE download script
    $BgeScript = Join-Path $PSScriptRoot "download_bge_model.ps1"
    if (Test-Path $BgeScript) {
        & $BgeScript -OutputDir $BgeDir
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to download BGE model"
        }
    } else {
        throw "BGE download script not found at: $BgeScript"
    }
}

Write-Host "✓ BGE ONNX INT8 model ready" -ForegroundColor Green
Write-Host ""

# ═══════════════════════════════════════════════════════════════════════════
# Cross-Encoder ONNX Model (REQUIRED)
# ═══════════════════════════════════════════════════════════════════════════

Write-Host "[3/4] Downloading Cross-Encoder ONNX model..." -ForegroundColor Yellow

$CeModelFile = Join-Path $CeDir "model.onnx"
if ((Test-Path $CeModelFile) -and -not $Force) {
    Write-Host "Cross-encoder model already exists at: $CeDir" -ForegroundColor Gray
    Write-Host "Use -Force to re-download" -ForegroundColor Gray
} else {
    Write-Host "Downloading cross-encoder/ms-marco-MiniLM-L-6-v2 from HuggingFace..." -ForegroundColor Green
    python -m pip install --quiet huggingface_hub
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install huggingface_hub"
    }
    python -c @"
import os, shutil
from pathlib import Path
from huggingface_hub import snapshot_download

model_id = 'cross-encoder/ms-marco-MiniLM-L-6-v2'
out = Path(r'$CeDir')
out.mkdir(parents=True, exist_ok=True)

cache_dir = snapshot_download(repo_id=model_id)
print(f'Downloaded to: {cache_dir}')

# Copy tokenizer files
for f in ['config.json', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json', 'vocab.txt']:
    src = os.path.join(cache_dir, f)
    if os.path.exists(src):
        shutil.copy2(src, out / f)
        print(f'  Copied {f}')

# Copy quantized ONNX model (avx2 for Windows x64)
onnx_src = os.path.join(cache_dir, 'onnx', 'model_quint8_avx2.onnx')
if os.path.exists(onnx_src):
    shutil.copy2(onnx_src, out / 'model.onnx')
    sz = os.path.getsize(str(out / 'model.onnx'))
    print(f'  Copied model.onnx ({sz / 1024 / 1024:.1f} MB)')
else:
    # Fallback to full model
    onnx_src = os.path.join(cache_dir, 'onnx', 'model.onnx')
    if os.path.exists(onnx_src):
        shutil.copy2(onnx_src, out / 'model.onnx')
        print('  Copied model.onnx (full, not quantized)')
    else:
        print('  ERROR: No ONNX model found!')
        exit(1)
"@
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to download cross-encoder model"
    }
}

Write-Host "✓ Cross-encoder model ready" -ForegroundColor Green
Write-Host ""

# ═══════════════════════════════════════════════════════════════════════════
# spaCy NER Model
# ═══════════════════════════════════════════════════════════════════════════

Write-Host "[4/4] Downloading spaCy model (en_core_web_sm)..." -ForegroundColor Yellow

$SpacyModelPath = Join-Path $SpacyDir "en_core_web_sm"
if ((Test-Path $SpacyModelPath) -and -not $Force) {
    Write-Host "spaCy model already exists at: $SpacyModelPath" -ForegroundColor Gray
    Write-Host "Use -Force to re-download" -ForegroundColor Gray
} else {
    # Install spacy if not present (force-reinstall click since spacy's CLI
    # dependency can be left missing/broken by resolver backtracking after
    # other packages like optimum/transformers pin conflicting versions)
    python -m pip install --quiet "spacy>=3.7.0" "click>=8.0.0"
    python -c "import click" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        python -m pip install --quiet --force-reinstall "click>=8.0.0"
    }

    # Download spaCy model
    python -m spacy download en_core_web_sm
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to download spaCy model"
    }

    # Find where spaCy installed the model
    $InstalledPath = python -c "import en_core_web_sm; print(en_core_web_sm.__path__[0])"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to locate spaCy model"
    }

    # Copy to our packaging directory
    Write-Host "Copying spaCy model to packaging cache..." -ForegroundColor Green
    if (Test-Path $SpacyModelPath) {
        Remove-Item -Recurse -Force $SpacyModelPath
    }
    Copy-Item -Recurse -Force $InstalledPath $SpacyModelPath
}

Write-Host "✓ spaCy model ready" -ForegroundColor Green
Write-Host ""

# ═══════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════

Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "Model Download Summary" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

# BGE model stats
$BgeModelFile = Join-Path $BgeDir "model.onnx"
if (Test-Path $BgeModelFile) {
    $BgeSize = (Get-Item $BgeModelFile).Length / 1MB
    Write-Host "BGE ONNX INT8: $BgeDir" -ForegroundColor Green
    Write-Host "  Model size: $([math]::Round($BgeSize, 1)) MB" -ForegroundColor Gray
    Write-Host "  Dimensions: 768" -ForegroundColor Gray
    Write-Host "  Status: READY" -ForegroundColor Green
} else {
    Write-Host "BGE ONNX INT8: NOT FOUND" -ForegroundColor Red
    Write-Host "  Run: .\scripts\download_bge_model.ps1" -ForegroundColor Yellow
}

Write-Host ""

# Cross-encoder model stats
$CeModelFile = Join-Path $CeDir "model.onnx"
if (Test-Path $CeModelFile) {
    $CeSize = (Get-Item $CeModelFile).Length / 1MB
    Write-Host "Cross-Encoder ONNX: $CeDir" -ForegroundColor Green
    Write-Host "  Model: ms-marco-MiniLM-L-6-v2 (quantized INT8)" -ForegroundColor Gray
    Write-Host "  Size: $([math]::Round($CeSize, 1)) MB" -ForegroundColor Gray
    Write-Host "  Status: READY" -ForegroundColor Green
} else {
    Write-Host "Cross-Encoder ONNX: NOT FOUND" -ForegroundColor Red
}

Write-Host ""

# spaCy model stats
$SpacyModelPath = Join-Path $SpacyDir "en_core_web_sm"
if (Test-Path $SpacyModelPath) {
    $SpacyFiles = Get-ChildItem -Recurse $SpacyModelPath | Measure-Object -Property Length -Sum
    Write-Host "spaCy NER: $SpacyModelPath" -ForegroundColor Green
    Write-Host "  Size: $([math]::Round($SpacyFiles.Sum / 1MB, 1)) MB" -ForegroundColor Gray
    Write-Host "  Files: $($SpacyFiles.Count)" -ForegroundColor Gray
    Write-Host "  Status: READY" -ForegroundColor Green
} else {
    Write-Host "spaCy NER: NOT FOUND" -ForegroundColor Red
}

Write-Host ""
Write-Host "✓ Model download complete!" -ForegroundColor Green
Write-Host "  Run: .\scripts\build_backend.ps1 to build the VSIX" -ForegroundColor Gray
Write-Host ""
