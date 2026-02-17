<#
.SYNOPSIS
    Build KTS backend with PyInstaller

.DESCRIPTION
    Creates a self-contained executable bundle with:
    - Python backend code
    - All dependencies (ChromaDB, spaCy, PyMuPDF, etc.)
    - Pre-bundled ML models
    
    Output: dist/kts-backend/ (~300MB)

.PARAMETER Version
    Version number for the build (default: 0.0.1)

.PARAMETER Clean
    Clean dist/ before building

.EXAMPLE
    .\scripts\build_backend.ps1
    .\scripts\build_backend.ps1 -Version "0.0.2" -Clean
#>

param(
    [string]$Version = "0.0.1",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "KTS Backend Build Script (PyInstaller)" -ForegroundColor Cyan
Write-Host "Version: $Version" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

# Paths
$RepoRoot = Split-Path -Parent $PSScriptRoot
$PackagingDir = Join-Path $RepoRoot "packaging"
$DistDir = Join-Path $RepoRoot "dist"
$VenvPath = Join-Path $RepoRoot ".venv_build"
$SpecFile = Join-Path $PackagingDir "kts_backend.spec"

# Clean if requested
if ($Clean -and (Test-Path $DistDir)) {
    Write-Host "Cleaning dist directory..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $DistDir
    Write-Host "✓ Cleaned" -ForegroundColor Green
    Write-Host ""
}

Write-Host "[1/4] Setting up Python environment..." -ForegroundColor Yellow

# Create or update venv
if (-not (Test-Path $VenvPath)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Green
    python -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create virtual environment"
    }
}

# Activate venv
$ActivateScript = Join-Path $VenvPath "Scripts\Activate.ps1"
& $ActivateScript

Write-Host "Python: $(python --version)" -ForegroundColor Green

# Upgrade pip
Write-Host "Upgrading pip..." -ForegroundColor Gray
python -m pip install --quiet --upgrade pip

Write-Host "✓ Environment ready" -ForegroundColor Green
Write-Host ""

Write-Host "[2/4] Installing dependencies from requirements.txt..." -ForegroundColor Yellow

$RequirementsFile = Join-Path $RepoRoot "requirements.txt"
python -m pip install --quiet -r $RequirementsFile

Write-Host "✓ Dependencies installed" -ForegroundColor Green
Write-Host ""

Write-Host "[3/4] Verifying models are cached..." -ForegroundColor Yellow

$ModelsDir = Join-Path $PackagingDir "models"
$ChromaDir = Join-Path $ModelsDir "chroma"
$SpacyDir = Join-Path $ModelsDir "spacy\en_core_web_sm"

if (-not (Test-Path $ChromaDir)) {
    Write-Host "⚠ ChromaDB models not found!" -ForegroundColor Red
    Write-Host "  Run: .\scripts\download_models.ps1" -ForegroundColor Yellow
    throw "Models not downloaded"
}

if (-not (Test-Path $SpacyDir)) {
    Write-Host "⚠ spaCy model not found!" -ForegroundColor Red
    Write-Host "  Run: .\scripts\download_models.ps1" -ForegroundColor Yellow
    throw "Models not downloaded"
}

Write-Host "✓ ChromaDB model: $ChromaDir" -ForegroundColor Green
Write-Host "✓ spaCy model: $SpacyDir" -ForegroundColor Green
Write-Host ""

Write-Host "[4/4] Running PyInstaller..." -ForegroundColor Yellow
Write-Host "Spec file: $SpecFile" -ForegroundColor Gray

# Change to packaging directory (PyInstaller spec requires this)
Push-Location $PackagingDir

try {
    # Run PyInstaller – direct output to repo-root dist/ so build_vsix.ps1 can find it
    Write-Host "  distpath → $DistDir" -ForegroundColor Gray
    Write-Host "  workpath → $(Join-Path $PackagingDir 'build')" -ForegroundColor Gray

    # Use cmd /c to prevent PowerShell from treating PyInstaller's stderr INFO 
    # lines as terminating NativeCommandError exceptions.
    $pyExe = (Get-Command python).Source
    cmd /c "`"$pyExe`" -m PyInstaller --clean --noconfirm --distpath `"$DistDir`" kts_backend.spec 2>&1"
    
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed (exit code $LASTEXITCODE)"
    }
} finally {
    Pop-Location
}

Write-Host "✓ PyInstaller build complete" -ForegroundColor Green
Write-Host ""

# Verify output
$BackendDist = Join-Path $DistDir "kts-backend"
$BackendExe = Join-Path $BackendDist "kts-backend.exe"

if (-not (Test-Path $BackendExe)) {
    throw "Build failed - executable not found: $BackendExe"
}

Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "Build Summary" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan

# Calculate size
$SizeInfo = Get-ChildItem -Recurse $BackendDist | Measure-Object -Property Length -Sum
$SizeMB = [math]::Round($SizeInfo.Sum / 1MB, 2)

Write-Host "Output: $BackendDist" -ForegroundColor Green
Write-Host "  Size: $SizeMB MB" -ForegroundColor Gray
Write-Host "  Files: $($SizeInfo.Count)" -ForegroundColor Gray
Write-Host ""

# Test executable
Write-Host "Testing backend executable..." -ForegroundColor Yellow
$TestOutput = & $BackendExe --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Backend executable works: $TestOutput" -ForegroundColor Green
} else {
    Write-Host "⚠ Backend test returned exit code: $LASTEXITCODE" -ForegroundColor Yellow
    Write-Host "  Output: $TestOutput" -ForegroundColor Gray
}

Write-Host ""
Write-Host "✓ Backend build complete!" -ForegroundColor Green
Write-Host "  Ready for VSIX packaging." -ForegroundColor Gray
Write-Host ""
