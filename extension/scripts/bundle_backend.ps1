# Bundle Backend Script
# Packages the Python backend into the extension for self-contained distribution
# Run from repo root: .\extension\scripts\bundle_backend.ps1

param(
    [string]$BackendVersion = "1.0.0"
)

$ErrorActionPreference = "Stop"

Write-Host "=== KTS Backend Bundler ===" -ForegroundColor Cyan
Write-Host "Backend Version: $BackendVersion" -ForegroundColor Yellow

# Paths
$RepoRoot = (Get-Item $PSScriptRoot).Parent.Parent.FullName
$ExtensionRoot = Join-Path $RepoRoot "extension"
$BundleDir = Join-Path $ExtensionRoot "backend_bundle"

# Clean existing bundle
if (Test-Path $BundleDir) {
    Write-Host "Cleaning existing bundle directory..." -ForegroundColor Yellow
    Remove-Item $BundleDir -Recurse -Force
}

# Create bundle structure
Write-Host "Creating bundle structure..." -ForegroundColor Green
New-Item -ItemType Directory -Path $BundleDir -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BundleDir "cli") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BundleDir "backend") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BundleDir "config") -Force | Out-Null

# Copy CLI module
Write-Host "Copying cli/..." -ForegroundColor Green
Copy-Item -Path (Join-Path $RepoRoot "cli\*") -Destination (Join-Path $BundleDir "cli") -Recurse -Force

# Copy backend modules (excluding tests and __pycache__)
Write-Host "Copying backend/..." -ForegroundColor Green
$BackendSource = Join-Path $RepoRoot "backend"
$BackendDest = Join-Path $BundleDir "backend"

Get-ChildItem $BackendSource -Directory | Where-Object { 
    $_.Name -notin @("__pycache__", "tests", ".pytest_cache") 
} | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination $BackendDest -Recurse -Force
}

# Copy __init__.py files
Get-ChildItem $BackendSource -Filter "__init__.py" -File | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination $BackendDest -Force
}

# Copy config files
Write-Host "Copying config files..." -ForegroundColor Green
$ConfigSource = Join-Path $RepoRoot "config"
$ConfigDest = Join-Path $BundleDir "config"

Copy-Item -Path (Join-Path $ConfigSource "__init__.py") -Destination $ConfigDest -Force -ErrorAction SilentlyContinue
Copy-Item -Path (Join-Path $ConfigSource "settings.py") -Destination $ConfigDest -Force -ErrorAction SilentlyContinue
Copy-Item -Path (Join-Path $ConfigSource "taxonomy_rules.json") -Destination $ConfigDest -Force -ErrorAction SilentlyContinue
Copy-Item -Path (Join-Path $ConfigSource "file_share_paths.json") -Destination $ConfigDest -Force -ErrorAction SilentlyContinue

# Copy requirements.txt with pinned versions
Write-Host "Copying requirements.txt..." -ForegroundColor Green
Copy-Item -Path (Join-Path $RepoRoot "requirements.txt") -Destination (Join-Path $BundleDir "requirements.txt") -Force

# Write version metadata
Write-Host "Writing version metadata..." -ForegroundColor Green
@{
    "version" = $BackendVersion
    "bundled_at" = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssK")
    "python_min_version" = "3.10"
} | ConvertTo-Json | Set-Content -Path (Join-Path $BundleDir "backend_version.json")

# Summary
$BundleSize = (Get-ChildItem $BundleDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host "`n=== Bundle Complete ===" -ForegroundColor Cyan
Write-Host "Bundle Directory: $BundleDir" -ForegroundColor Yellow
Write-Host "Bundle Size: $([math]::Round($BundleSize, 2)) MB" -ForegroundColor Yellow
Write-Host "Version: $BackendVersion" -ForegroundColor Yellow

# List top-level contents
Write-Host "`nBundle Contents:" -ForegroundColor Cyan
Get-ChildItem $BundleDir | Format-Table Name, Length, Mode -AutoSize
