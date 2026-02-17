<#
.SYNOPSIS
    Download and cache ML models for offline VSIX bundling

.DESCRIPTION
    This script downloads:
    1. ChromaDB embedding model (all-MiniLM-L6-v2 ONNX)
    2. spaCy NER model (en_core_web_sm)
    
    Models are cached to packaging/models/ for PyInstaller bundling.

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
Write-Host "KTS Model Download Script" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

# Paths
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ModelsDir = Join-Path $RepoRoot "packaging\models"
$ChromaDir = Join-Path $ModelsDir "chroma"
$SpacyDir = Join-Path $ModelsDir "spacy"
$VenvPath = Join-Path $RepoRoot ".venv_build"

# Create directories
New-Item -ItemType Directory -Force -Path $ChromaDir | Out-Null
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

Write-Host "[2/3] Downloading ChromaDB embedding model..." -ForegroundColor Yellow

# Install chromadb and its embedding dependencies
python -m pip install --quiet chromadb onnxruntime tokenizers tqdm httpx

# Trigger ChromaDB to download the ONNX model, then copy to our packaging dir
$TempScript = Join-Path $env:TEMP "download_chroma_model.py"
@"
import shutil
from pathlib import Path
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

# Trigger model download (goes to ~/.cache/chroma/onnx_models/all-MiniLM-L6-v2/)
print('Downloading ChromaDB ONNX model (all-MiniLM-L6-v2)...')
ef = ONNXMiniLM_L6_V2()

# Verify it works
test_embedding = ef(['test sentence'])
print(f'  Embedding dimension: {len(test_embedding[0])}')

# Copy from user cache to packaging directory
src = ONNXMiniLM_L6_V2.DOWNLOAD_PATH  # ~/.cache/chroma/onnx_models/all-MiniLM-L6-v2
dst = Path(r'$ChromaDir') / 'all-MiniLM-L6-v2'

print(f'  Source: {src}')
print(f'  Destination: {dst}')

if dst.exists():
    shutil.rmtree(dst)

# Copy just the onnx/ subfolder (skip the .tar.gz archive)
onnx_src = src / 'onnx'
onnx_dst = dst / 'onnx'
if onnx_src.exists():
    shutil.copytree(onnx_src, onnx_dst)
    total_size = sum(f.stat().st_size for f in onnx_dst.rglob('*') if f.is_file())
    file_count = sum(1 for f in onnx_dst.rglob('*') if f.is_file())
    print(f'  Copied: {file_count} files, {total_size / 1024 / 1024:.1f} MB')
else:
    raise FileNotFoundError(f'ONNX model folder not found at {onnx_src}')

print('Done - ChromaDB model cached for bundling.')
"@ | Out-File -FilePath $TempScript -Encoding UTF8

python $TempScript
if ($LASTEXITCODE -ne 0) {
    throw "Failed to download ChromaDB model"
}
Remove-Item $TempScript

Write-Host "✓ ChromaDB model cached" -ForegroundColor Green
Write-Host ""

Write-Host "[3/3] Downloading spaCy model (en_core_web_sm)..." -ForegroundColor Yellow

# Install spacy if not present
python -m pip install --quiet "spacy>=3.7.0"

# Download spaCy model
python -m spacy download en_core_web_sm
if ($LASTEXITCODE -ne 0) {
    throw "Failed to download spaCy model"
}

# Find where spaCy installed the model
$SpacyModelPath = python -c "import en_core_web_sm; print(en_core_web_sm.__path__[0])"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to locate spaCy model"
}

# Copy to our packaging directory
Write-Host "Copying spaCy model to packaging cache..." -ForegroundColor Green
$DestPath = Join-Path $SpacyDir "en_core_web_sm"
if (Test-Path $DestPath) {
    Remove-Item -Recurse -Force $DestPath
}
Copy-Item -Recurse -Force $SpacyModelPath $DestPath

Write-Host "✓ spaCy model cached" -ForegroundColor Green
Write-Host ""

# Verify models exist
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "Model Download Summary" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan

$ChromaModelFiles = Get-ChildItem -Recurse $ChromaDir | Measure-Object -Property Length -Sum
$SpacyModelFiles = Get-ChildItem -Recurse $SpacyDir | Measure-Object -Property Length -Sum

Write-Host "ChromaDB models: $ChromaDir" -ForegroundColor Green
Write-Host "  Size: $([math]::Round($ChromaModelFiles.Sum / 1MB, 2)) MB" -ForegroundColor Gray
Write-Host "  Files: $($ChromaModelFiles.Count)" -ForegroundColor Gray

Write-Host ""
Write-Host "spaCy models: $SpacyDir" -ForegroundColor Green
Write-Host "  Size: $([math]::Round($SpacyModelFiles.Sum / 1MB, 2)) MB" -ForegroundColor Gray
Write-Host "  Files: $($SpacyModelFiles.Count)" -ForegroundColor Gray

Write-Host ""
Write-Host "✓ All models downloaded and cached successfully!" -ForegroundColor Green
Write-Host "  Ready for PyInstaller bundling." -ForegroundColor Gray
Write-Host ""
