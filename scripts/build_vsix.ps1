<#
.SYNOPSIS
    Master build script for KTS VSIX extension

.DESCRIPTION
    Complete build pipeline:
    1. Download ML models (if needed)
    2. Build backend with PyInstaller
    3. Copy backend to extension/bin/
    4. Package VSIX with vsce
    5. Optional: Run validation tests
    
    Output: dist/gsf-ir-kts-extension-X.X.X.vsix

.PARAMETER Version
    Version number for the build (default: 0.0.1)

.PARAMETER SkipModels
    Skip model download if already cached

.PARAMETER SkipBackend
    Skip backend build if already built

.PARAMETER Test
    Run validation tests after building

.PARAMETER Clean
    Clean all build artifacts before starting

.EXAMPLE
    .\scripts\build_vsix.ps1
    .\scripts\build_vsix.ps1 -Version "0.0.2" -Clean -Test
    .\scripts\build_vsix.ps1 -SkipModels -SkipBackend  # Quick rebuild
#>

param(
    [string]$Version = "0.0.1",
    [switch]$SkipModels,
    [switch]$SkipBackend,
    [switch]$Test,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "  KTS VSIX BUILD PIPELINE" -ForegroundColor Cyan
Write-Host "  Version: $Version" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

# Paths
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ScriptsDir = $PSScriptRoot
$ExtensionDir = Join-Path $RepoRoot "extension"
$DistDir = Join-Path $RepoRoot "dist"
$BackendSource = Join-Path $DistDir "kts-backend"
$BackendDest = Join-Path $ExtensionDir "bin\win-x64\kts-backend"

# Clean if requested
if ($Clean) {
    Write-Host "CLEANING BUILD ARTIFACTS" -ForegroundColor Yellow
    Write-Host "-" * 80 -ForegroundColor Gray
    
    if (Test-Path $DistDir) {
        Write-Host "Removing dist/..." -ForegroundColor Gray
        Remove-Item -Recurse -Force $DistDir
    }
    
    if (Test-Path $BackendDest) {
        Write-Host "Removing extension/bin/..." -ForegroundColor Gray
        Remove-Item -Recurse -Force $BackendDest
    }
    
    $VsixFiles = Get-ChildItem -Path $ExtensionDir -Filter "*.vsix"
    if ($VsixFiles) {
        Write-Host "Removing old VSIX files..." -ForegroundColor Gray
        $VsixFiles | Remove-Item -Force
    }
    
    Write-Host "✓ Cleaned" -ForegroundColor Green
    Write-Host ""
}

# Step 1: Download Models
if (-not $SkipModels) {
    Write-Host ""
    Write-Host "STEP 1: DOWNLOAD ML MODELS" -ForegroundColor Cyan
    Write-Host "-" * 80 -ForegroundColor Gray
    
    $DownloadScript = Join-Path $ScriptsDir "download_models.ps1"
    & $DownloadScript
    
    if ($LASTEXITCODE -ne 0) {
        throw "Model download failed"
    }
} else {
    Write-Host "STEP 1: DOWNLOAD ML MODELS - SKIPPED" -ForegroundColor Yellow
    Write-Host ""
}

# Step 2: Build Backend
if (-not $SkipBackend) {
    Write-Host ""
    Write-Host "STEP 2: BUILD BACKEND (PYINSTALLER)" -ForegroundColor Cyan
    Write-Host "-" * 80 -ForegroundColor Gray
    
    $BuildBackendScript = Join-Path $ScriptsDir "build_backend.ps1"
    & $BuildBackendScript -Version $Version
    
    if ($LASTEXITCODE -ne 0) {
        throw "Backend build failed"
    }
} else {
    Write-Host "STEP 2: BUILD BACKEND - SKIPPED" -ForegroundColor Yellow
    Write-Host ""
}

# Step 3: Copy Backend to Extension
Write-Host ""
Write-Host "STEP 3: COPY BACKEND TO EXTENSION" -ForegroundColor Cyan
Write-Host "-" * 80 -ForegroundColor Gray

if (-not (Test-Path $BackendSource)) {
    throw "Backend not found: $BackendSource (run without -SkipBackend)"
}

# Remove old backend if exists
if (Test-Path $BackendDest) {
    Write-Host "Removing old backend..." -ForegroundColor Gray
    Remove-Item -Recurse -Force $BackendDest
}

# Copy new backend
Write-Host "Copying backend to extension..." -ForegroundColor Green
Write-Host "  From: $BackendSource" -ForegroundColor Gray
Write-Host "  To: $BackendDest" -ForegroundColor Gray

$ParentDir = Split-Path -Parent $BackendDest
New-Item -ItemType Directory -Force -Path $ParentDir | Out-Null

Copy-Item -Recurse -Force $BackendSource $BackendDest

# Verify copy
$BackendExe = Join-Path $BackendDest "kts-backend.exe"
if (-not (Test-Path $BackendExe)) {
    throw "Backend copy failed - executable not found"
}

$SizeInfo = Get-ChildItem -Recurse $BackendDest | Measure-Object -Property Length -Sum
$SizeMB = [math]::Round($SizeInfo.Sum / 1MB, 2)

Write-Host "✓ Backend copied: $SizeMB MB" -ForegroundColor Green
Write-Host ""

# Step 4: Update package.json version
Write-Host ""
Write-Host "STEP 4: UPDATE PACKAGE.JSON" -ForegroundColor Cyan
Write-Host "-" * 80 -ForegroundColor Gray

$PackageJsonPath = Join-Path $ExtensionDir "package.json"

# Use Node.js to update version – avoids PowerShell BOM / JSON formatting issues
node -e "const fs=require('fs'); const p='$($PackageJsonPath -replace '\\','/')'; const j=JSON.parse(fs.readFileSync(p,'utf8')); j.version='$Version'; fs.writeFileSync(p,JSON.stringify(j,null,2)+'\n')"

if ($LASTEXITCODE -ne 0) {
    throw "Failed to update package.json version"
}

Write-Host "✓ Updated version to $Version" -ForegroundColor Green
Write-Host ""

# Step 5: Package VSIX
Write-Host ""
Write-Host "STEP 5: PACKAGE VSIX" -ForegroundColor Cyan
Write-Host "-" * 80 -ForegroundColor Gray

Push-Location $ExtensionDir

try {
    # Check if vsce is installed
    $VsceVersion = npx @vscode/vsce --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing @vscode/vsce..." -ForegroundColor Yellow
        npm install -g @vscode/vsce
    }
    
    Write-Host "Packaging VSIX..." -ForegroundColor Green
    Write-Host "  Using: vsce package --no-dependencies" -ForegroundColor Gray
    
    # Package VSIX (allow large files, no dependencies check)
    npx @vscode/vsce package --no-dependencies 2>&1 | ForEach-Object {
        if ($_ -match "ERROR|WARNING") {
            Write-Host $_ -ForegroundColor Yellow
        } elseif ($_ -match "DONE|Packaged") {
            Write-Host $_ -ForegroundColor Green
        } else {
            Write-Host $_ -ForegroundColor Gray
        }
    }
    
    if ($LASTEXITCODE -ne 0) {
        throw "VSIX packaging failed"
    }
    
} finally {
    Pop-Location
}

# Find the generated VSIX
$VsixFile = Get-ChildItem -Path $ExtensionDir -Filter "*.vsix" | Select-Object -First 1

if (-not $VsixFile) {
    throw "VSIX file not found after packaging"
}

# Move to dist/
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
$FinalVsix = Join-Path $DistDir $VsixFile.Name

if (Test-Path $FinalVsix) {
    Remove-Item $FinalVsix
}

Move-Item $VsixFile.FullName $FinalVsix

Write-Host "✓ VSIX created: $($VsixFile.Name)" -ForegroundColor Green
Write-Host ""

# Step 6: Build Summary
Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "BUILD SUMMARY" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan

$VsixSize = [math]::Round((Get-Item $FinalVsix).Length / 1MB, 2)

Write-Host "VSIX File: $FinalVsix" -ForegroundColor Green
Write-Host "  Version: $Version" -ForegroundColor Gray
Write-Host "  Size: $VsixSize MB" -ForegroundColor Gray
Write-Host ""

if ($VsixSize -gt 500) {
    Write-Host "⚠ WARNING: VSIX size exceeds 500MB!" -ForegroundColor Yellow
    Write-Host "  Consider optimization if this is too large." -ForegroundColor Gray
    Write-Host ""
}

Write-Host "Installation command:" -ForegroundColor Cyan
Write-Host "  code --install-extension $FinalVsix" -ForegroundColor White
Write-Host ""

# Step 7: Optional Testing
if ($Test) {
    Write-Host ""
    Write-Host "STEP 7: VALIDATION TESTS" -ForegroundColor Cyan
    Write-Host "-" * 80 -ForegroundColor Gray
    
    $TestScript = Join-Path $ScriptsDir "test_vsix.ps1"
    if (Test-Path $TestScript) {
        & $TestScript -VsixPath $FinalVsix
    } else {
        Write-Host "⚠ Test script not found: $TestScript" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "=" * 80 -ForegroundColor Green
Write-Host "✓ BUILD COMPLETE!" -ForegroundColor Green
Write-Host "=" * 80 -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Manual testing: code --install-extension $FinalVsix" -ForegroundColor White
Write-Host "  2. If tests pass, create GitHub Release" -ForegroundColor White
Write-Host "  3. Upload VSIX to release assets" -ForegroundColor White
Write-Host ""
