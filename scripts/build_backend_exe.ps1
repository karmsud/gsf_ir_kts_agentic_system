# Build Backend Executable using PyInstaller
# This script builds a PyInstaller onedir distribution for the KTS backend
# Output: extension/bin/win-x64/kts-backend/

param(
    [switch]$Clean = $false,
    [switch]$SkipTests = $false
)

$ErrorActionPreference = "Stop"

Write-Host "=== KTS Backend Executable Builder ===" -ForegroundColor Cyan
Write-Host "Target: Windows x64 (onedir)" -ForegroundColor Yellow

# Paths
$RepoRoot = (Get-Item $PSScriptRoot).Parent.FullName
$ExtensionRoot = Join-Path $RepoRoot "extension"
$OutputDir = Join-Path $ExtensionRoot "bin\win-x64\kts-backend"
$SpecFile = Join-Path $RepoRoot "packaging\kts_backend.spec"
$DistDir = Join-Path $RepoRoot "dist"
$BuildDir = Join-Path $RepoRoot "build"

Write-Host "Repo Root: $RepoRoot" -ForegroundColor Gray
Write-Host "Output Dir: $OutputDir" -ForegroundColor Gray

# Clean if requested
if ($Clean) {
    Write-Host "`nCleaning previous build artifacts..." -ForegroundColor Yellow
    if (Test-Path $DistDir) { Remove-Item $DistDir -Recurse -Force }
    if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force }
    if (Test-Path $OutputDir) { Remove-Item $OutputDir -Recurse -Force }
}

# Check Python and venv
Write-Host "`nChecking Python environment..." -ForegroundColor Green
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "ERROR: Virtual environment not found at $RepoRoot\.venv" -ForegroundColor Red
    Write-Host "Please run: python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

Write-Host "Using Python: $VenvPython" -ForegroundColor Gray

# Check PyInstaller
Write-Host "Checking PyInstaller..." -ForegroundColor Green
& $VenvPython -m pip show pyinstaller | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyInstaller..." -ForegroundColor Yellow
    & $VenvPython -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to install PyInstaller" -ForegroundColor Red
        exit 1
    }
}

# Optional: Run quick health check
if (-not $SkipTests) {
    Write-Host "`nRunning health check..." -ForegroundColor Green
    & $VenvPython -c "import cli, backend, config; print('Imports OK')"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Health check failed. Fix imports before building." -ForegroundColor Red
        exit 1
    }
    Write-Host "Health check passed." -ForegroundColor Gray
}

# Build with PyInstaller
Write-Host "`nBuilding executable with PyInstaller..." -ForegroundColor Green
Write-Host "Spec file: $SpecFile" -ForegroundColor Gray

& $VenvPython -m PyInstaller --clean --noconfirm "$SpecFile"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: PyInstaller build failed" -ForegroundColor Red
    exit 1
}

# Move output to extension/bin
Write-Host "`nMoving output to extension directory..." -ForegroundColor Green
$PyInstallerOutput = Join-Path $DistDir "kts-backend"

if (-not (Test-Path $PyInstallerOutput)) {
    Write-Host "ERROR: PyInstaller output not found at $PyInstallerOutput" -ForegroundColor Red
    exit 1
}

# Ensure output directory exists
$OutputParent = Split-Path $OutputDir -Parent
if (-not (Test-Path $OutputParent)) {
    New-Item -ItemType Directory -Path $OutputParent -Force | Out-Null
}

# Move the distribution
if (Test-Path $OutputDir) {
    Remove-Item $OutputDir -Recurse -Force
}
Move-Item $PyInstallerOutput $OutputDir -Force

Write-Host "Executable built successfully." -ForegroundColor Green

# Verify executable
$ExePath = Join-Path $OutputDir "kts-backend.exe"
if (-not (Test-Path $ExePath)) {
    Write-Host "ERROR: Executable not found at $ExePath" -ForegroundColor Red
    exit 1
}

# Test executable
Write-Host "`nTesting executable..." -ForegroundColor Green
$TestResult = & $ExePath --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: Executable test failed (exit code $LASTEXITCODE)" -ForegroundColor Yellow
    Write-Host "Output: $TestResult" -ForegroundColor Gray
} else {
    Write-Host "Executable test passed: $TestResult" -ForegroundColor Gray
}

# Size report
$ExeSize = (Get-Item $ExePath).Length / 1MB
$DistSize = (Get-ChildItem $OutputDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB

Write-Host "`n=== Build Complete ===" -ForegroundColor Cyan
Write-Host "Executable: $ExePath" -ForegroundColor Yellow
Write-Host "Exe Size: $([math]::Round($ExeSize, 2)) MB" -ForegroundColor Yellow
Write-Host "Total Distribution Size: $([math]::Round($DistSize, 2)) MB" -ForegroundColor Yellow

# Cleanup build artifacts
if ($Clean) {
    Write-Host "`nCleaning up PyInstaller artifacts..." -ForegroundColor Yellow
    if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force }
    # Keep dist dir as it might have other content
}

Write-Host "`nReady for packaging into VSIX." -ForegroundColor Green
