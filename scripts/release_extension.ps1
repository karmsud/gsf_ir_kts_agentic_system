# Release Extension - Full Build Pipeline
# This script runs the complete build and package workflow for the KTS extension
# 1. Build backend executable (PyInstaller)
# 2. Bundle backend source
# 3. Package VSIX

param(
    [string]$Version = "1.1.0",
    [switch]$Clean = $false,
    [switch]$SkipTests = $false,
    [switch]$SkipExe = $false
)

$ErrorActionPreference = "Stop"

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "   KTS Extension Release Pipeline" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "Version: $Version" -ForegroundColor Yellow
Write-Host "Clean Build: $Clean" -ForegroundColor Yellow
Write-Host "Skip Tests: $SkipTests" -ForegroundColor Yellow
Write-Host "Skip Exe: $SkipExe" -ForegroundColor Yellow
Write-Host ""

$StartTime = Get-Date

# Get script directory
$ScriptRoot = $PSScriptRoot

# Step 1: Build backend executable
if (-not $SkipExe) {
    Write-Host "[1/3] Building backend executable..." -ForegroundColor Green
    $BuildExeScript = Join-Path $ScriptRoot "build_backend_exe.ps1"
    
    $BuildArgs = @()
    if ($Clean) { $BuildArgs += "-Clean" }
    if ($SkipTests) { $BuildArgs += "-SkipTests" }
    
    & $BuildExeScript @BuildArgs
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Backend executable build failed" -ForegroundColor Red
        exit 1
    }
    Write-Host ""
} else {
    Write-Host "[1/3] Skipping backend executable build..." -ForegroundColor Yellow
    Write-Host ""
}

# Step 2: Package VSIX
Write-Host "[2/3] Packaging VSIX..." -ForegroundColor Green
$PackageScript = Join-Path $ScriptRoot "package_vsix.ps1"

$PackageArgs = @(
    "-Version", $Version
)
if ($SkipExe) { $PackageArgs += "-IncludeExe:`$false" }

& $PackageScript @PackageArgs

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: VSIX packaging failed" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 3: Summary
Write-Host "[3/3] Generating release summary..." -ForegroundColor Green

$RepoRoot = (Get-Item $ScriptRoot).Parent.FullName
$ExtensionRoot = Join-Path $RepoRoot "extension"
$VsixPath = Join-Path $ExtensionRoot "dist\gsf-ir-kts-$Version.vsix"
$ExeDir = Join-Path $ExtensionRoot "bin\win-x64\kts-backend"

Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "   Release Complete" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan

# VSIX info
if (Test-Path $VsixPath) {
    $VsixSize = (Get-Item $VsixPath).Length / 1KB
    Write-Host "VSIX Package:" -ForegroundColor Yellow
    Write-Host "  Path: $VsixPath" -ForegroundColor Gray
    Write-Host "  Size: $([math]::Round($VsixSize, 2)) KB" -ForegroundColor Gray
}

# Exe info
if (-not $SkipExe -and (Test-Path $ExeDir)) {
    $ExePath = Join-Path $ExeDir "kts-backend.exe"
    if (Test-Path $ExePath) {
        $ExeSize = (Get-Item $ExePath).Length / 1MB
        $DistSize = (Get-ChildItem $ExeDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
        Write-Host ""
        Write-Host "Backend Executable:" -ForegroundColor Yellow
        Write-Host "  Path: $ExePath" -ForegroundColor Gray
        Write-Host "  Exe Size: $([math]::Round($ExeSize, 2)) MB" -ForegroundColor Gray
        Write-Host "  Full Distribution: $([math]::Round($DistSize, 2)) MB" -ForegroundColor Gray
    }
}

# Backend modes
Write-Host ""
Write-Host "Supported Backend Modes:" -ForegroundColor Yellow
if ($SkipExe) {
    Write-Host "  - Option A1 (venv): Yes" -ForegroundColor Gray
    Write-Host "  - Option A2 (exe): No" -ForegroundColor Gray
} else {
    Write-Host "  - Option A1 (venv): Yes" -ForegroundColor Gray
    Write-Host "  - Option A2 (exe): Yes" -ForegroundColor Gray
}

# Timing
$Duration = (Get-Date) - $StartTime
Write-Host ""
Write-Host "Build Duration: $([math]::Round($Duration.TotalSeconds, 1)) seconds" -ForegroundColor Yellow

Write-Host ""
Write-Host "Installation Command:" -ForegroundColor Yellow
Write-Host "  code --install-extension `"$VsixPath`"" -ForegroundColor Gray

Write-Host ""
Write-Host "Release artifacts ready for distribution." -ForegroundColor Green
