# Package VSIX with Backend Executable
# This script packages the VS Code extension including the backend executable
# Prerequisites: Backend executable must be built first (run build_backend_exe.ps1)
#
# Tiers:
#   A2  (default) - Full: DOCX + PDF + PPTX + HTML + images
#   A3            - Word + Images: DOCX + HTML (no PDF/PPTX)

param(
    [string]$Version = "1.1.0",
    [ValidateSet("A2", "A3")]
    [string]$Tier = "A2",
    [switch]$IncludeExe = $true,
    [switch]$NoBackendBundle = $false
)

$ErrorActionPreference = "Stop"

$TierLabels = @{ "A2" = "Full"; "A3" = "Word+Images" }
$TierSuffix = if ($Tier -eq "A2") { "" } else { "-$($Tier.ToLower())" }

Write-Host "=== KTS Extension VSIX Packager ===" -ForegroundColor Cyan
Write-Host "Tier: $Tier - $($TierLabels[$Tier])" -ForegroundColor Yellow
Write-Host "Version: $Version" -ForegroundColor Yellow
Write-Host "Include Exe: $IncludeExe" -ForegroundColor Yellow

# Paths
$RepoRoot = (Get-Item $PSScriptRoot).Parent.FullName
$ExtensionRoot = Join-Path $RepoRoot "extension"
$DistDir = Join-Path $ExtensionRoot "dist"
$ExeDir = Join-Path $ExtensionRoot "bin\win-x64\kts-backend"

Write-Host "Extension Root: $ExtensionRoot" -ForegroundColor Gray

# Ensure dist directory exists
if (-not (Test-Path $DistDir)) {
    New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
}

# Check if executable exists (if required)
if ($IncludeExe) {
    $ExePath = Join-Path $ExeDir "kts-backend.exe"
    if (-not (Test-Path $ExePath)) {
        Write-Host "WARNING: Backend executable not found at $ExePath" -ForegroundColor Yellow
        Write-Host "Run build_backend_exe.ps1 first, or use -IncludeExe:`$false" -ForegroundColor Yellow
        Write-Host "Proceeding without executable..." -ForegroundColor Yellow
        $IncludeExe = $false
    } else {
        $ExeSize = (Get-Item $ExePath).Length / 1MB
        Write-Host "Backend executable found: $([math]::Round($ExeSize, 2)) MB" -ForegroundColor Gray
    }
}

# Bundle backend source (Option A1 support)
if (-not $NoBackendBundle) {
    Write-Host "`nBundling backend source..." -ForegroundColor Green
    Push-Location $ExtensionRoot
    & npm run bundle:backend
    Pop-Location
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Backend bundle script failed" -ForegroundColor Red
        exit 1
    }
}

# Update version in package.json if specified
$PackageJsonPath = Join-Path $ExtensionRoot "package.json"
$PackageJson = Get-Content $PackageJsonPath | ConvertFrom-Json
$CurrentVersion = $PackageJson.version

if ($Version -ne $CurrentVersion) {
    Write-Host "Updating version: $CurrentVersion -> $Version" -ForegroundColor Yellow
    $PackageJson.version = $Version
    $PackageJson | ConvertTo-Json -Depth 100 | Set-Content $PackageJsonPath
}

# Package with vsce
Write-Host "`nPackaging VSIX..." -ForegroundColor Green
Push-Location $ExtensionRoot

$OutputFile = Join-Path $DistDir "gsf-ir-kts-$Version$TierSuffix.vsix"

# Run vsce package with proper argument passing
& npx vsce package `
    --no-dependencies `
    --allow-missing-repository `
    --allow-star-activation `
    --out $OutputFile

if ($LASTEXITCODE -ne 0) {
    Pop-Location
    Write-Host "ERROR: vsce package failed" -ForegroundColor Red
    exit 1
}

Pop-Location

# Verify VSIX
if (-not (Test-Path $OutputFile)) {
    Write-Host "ERROR: VSIX not found at $OutputFile" -ForegroundColor Red
    exit 1
}

$VsixSize = (Get-Item $OutputFile).Length / 1KB

Write-Host "`n=== Package Complete ($Tier) ===" -ForegroundColor Cyan
Write-Host "Tier: $Tier - $($TierLabels[$Tier])" -ForegroundColor Yellow
Write-Host "VSIX: $OutputFile" -ForegroundColor Yellow
Write-Host "Size: $([math]::Round($VsixSize, 2)) KB" -ForegroundColor Yellow

if ($IncludeExe) {
    Write-Host "Includes: Backend executable (Option $Tier) + Source (Option A1)" -ForegroundColor Gray
} else {
    Write-Host "Includes: Source only (Option A1)" -ForegroundColor Gray
}

Write-Host "`nReady for installation or distribution." -ForegroundColor Green
