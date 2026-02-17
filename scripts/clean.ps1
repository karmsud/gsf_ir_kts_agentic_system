<#
.SYNOPSIS
    Clean KTS build artifacts

.DESCRIPTION
    Removes build artifacts and optionally cached models.
    Use this to start fresh or reclaim disk space.

.PARAMETER All
    Remove everything including cached models

.PARAMETER KeepModels
    Keep cached models (default behavior)

.EXAMPLE
    .\scripts\clean.ps1
    .\scripts\clean.ps1 -All
#>

param(
    [switch]$All
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "KTS Clean Script" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

$RepoRoot = Split-Path -Parent $PSScriptRoot

# Paths to clean
$PathsToClean = @()

# Always clean these
$PathsToClean += @{
    Path = Join-Path $RepoRoot "dist"
    Description = "PyInstaller output"
}

$PathsToClean += @{
    Path = Join-Path $RepoRoot "build"
    Description = "PyInstaller temp files"
}

$PathsToClean += @{
    Path = Join-Path $RepoRoot "extension\bin"
    Description = "Bundled backend"
}

$PathsToClean += @{
    Path = Join-Path $RepoRoot "extension\*.vsix"
    Description = "Old VSIX files (moved to dist/)"
}

$PathsToClean += @{
    Path = Join-Path $RepoRoot ".venv_build"
    Description = "Build virtual environment"
}

# Clean VSIX files in extension directory
$ExtensionDir = Join-Path $RepoRoot "extension"
$VsixFiles = Get-ChildItem -Path $ExtensionDir -Filter "*.vsix" -ErrorAction SilentlyContinue

if ($VsixFiles) {
    foreach ($Vsix in $VsixFiles) {
        $PathsToClean += @{
            Path = $Vsix.FullName
            Description = "VSIX file: $($Vsix.Name)"
        }
    }
}

# Optionally clean models
if ($All) {
    $PathsToClean += @{
        Path = Join-Path $RepoRoot "packaging\models"
        Description = "Cached ML models"
    }
}

# Clean PyInstaller spec files build artifacts
$SpecBuildPaths = @(
    "packaging\build",
    "packaging\dist"
)

foreach ($Path in $SpecBuildPaths) {
    $FullPath = Join-Path $RepoRoot $Path
    $PathsToClean += @{
        Path = $FullPath
        Description = "PyInstaller spec artifacts: $Path"
    }
}

# Perform cleaning
Write-Host "Cleaning build artifacts..." -ForegroundColor Yellow
Write-Host ""

$CleanedCount = 0

foreach ($Item in $PathsToClean) {
    $Path = $Item.Path
    $Description = $Item.Description
    
    if (Test-Path $Path) {
        try {
            Write-Host "  Removing: $Description" -ForegroundColor Gray
            Write-Host "    $Path" -ForegroundColor DarkGray
            
            Remove-Item -Recurse -Force $Path -ErrorAction Stop
            $CleanedCount++
            
            Write-Host "    ✓ Removed" -ForegroundColor Green
        } catch {
            Write-Host "    ⚠ Failed: $_" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  Skipping: $Description (not found)" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "Clean Summary" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""
Write-Host "Removed $CleanedCount item(s)" -ForegroundColor Green
Write-Host ""

if (-not $All) {
    Write-Host "Models preserved: packaging\models\" -ForegroundColor Yellow
    Write-Host "  Use -All flag to remove cached models" -ForegroundColor Gray
    Write-Host ""
}

Write-Host "✓ Clean complete!" -ForegroundColor Green
Write-Host ""
