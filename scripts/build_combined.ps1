# build_combined.ps1 — Phase 23 Combined KTS + ABS VSIX Build Script
# Usage: .\scripts\build_combined.ps1 [-Version "1.0.0"] [-SkipTests] [-SkipBackend]
#
# Steps:
#   1. Run Python tests  (unless -SkipTests)
#   2. Build Python backend  (unless -SkipBackend)
#   3. Validate package.json (both participants registered)
#   4. Package VSIX

[CmdletBinding()]
param(
    [string] $Version    = "0.0.9",
    [switch] $SkipTests,
    [switch] $SkipBackend,
    [switch] $DryRun
)

$ErrorActionPreference = "Stop"

$ProjectRoot  = Resolve-Path (Join-Path $PSScriptRoot "..")
$ExtensionDir = Join-Path $ProjectRoot "extension"

Write-Host ""
Write-Host "╔═══════════════════════════════════════════╗"
Write-Host "║   KTS + ABS Combined Build  (Phase 23)    ║"
Write-Host "╚═══════════════════════════════════════════╝"
Write-Host "  Version      : $Version"
Write-Host "  Project root : $ProjectRoot"
Write-Host "  Dry run      : $DryRun"
Write-Host ""

# ─── Step 1: Python Tests ───────────────────────────────────────────────────
if (-not $SkipTests) {
    Write-Host "=== Step 1: Python Tests ==="
    Push-Location $ProjectRoot
    try {
        python -m pytest tests/ -x -q --tb=short 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Python tests failed (exit $LASTEXITCODE)"
        }
        Write-Host "Python tests: PASS ✅`n"
    } finally {
        Pop-Location
    }
} else {
    Write-Host "=== Step 1: Python Tests (SKIPPED) ===`n"
}

# ─── Step 2: Python Backend Build ──────────────────────────────────────────
if (-not $SkipBackend) {
    Write-Host "=== Step 2: Python Backend Build ==="
    $BuildScript = Join-Path $ExtensionDir "scripts\bundle_backend.ps1"
    if (Test-Path $BuildScript) {
        Push-Location $ExtensionDir
        try {
            if (-not $DryRun) {
                powershell -ExecutionPolicy Bypass -File $BuildScript
                if ($LASTEXITCODE -ne 0) {
                    Write-Error "Backend build failed (exit $LASTEXITCODE)"
                }
            } else {
                Write-Host "  [DryRun] Would run: $BuildScript"
            }
            Write-Host "Backend build: PASS ✅`n"
        } finally {
            Pop-Location
        }
    } else {
        Write-Warning "Backend build script not found at $BuildScript — skipping"
    }
} else {
    Write-Host "=== Step 2: Backend Build (SKIPPED) ===`n"
}

# ─── Step 3: Validate package.json ─────────────────────────────────────────
Write-Host "=== Step 3: package.json Validation ==="
$PkgJson = Join-Path $ExtensionDir "package.json"

$validation = python -c @"
import json, sys
pkg = json.load(open(r'$($PkgJson.Replace('\','\\'))'))
participants = pkg.get('contributes', {}).get('chatParticipants', [])
names = [p.get('name', p.get('id','')) for p in participants]
print(f'Chat participants found: {names}')
has_kts = any('kts' in n for n in names)
has_abs = any('abs' in n for n in names)
if not has_kts:
    print('ERROR: @kts participant missing from package.json')
    sys.exit(1)
if not has_abs:
    print('ERROR: @abs participant missing from package.json')
    sys.exit(1)
print('Both @kts and @abs registered: OK')
abs_p = next(p for p in participants if 'abs' in p.get('name','') + p.get('id',''))
cmds = [c.get('name') for c in abs_p.get('commands', [])]
print(f'@abs commands: {cmds}')
expected = {'ingest', 'generate', 'audit', 'status'}
missing = expected - set(cmds)
if missing:
    print(f'ERROR: @abs missing commands: {missing}')
    sys.exit(1)
print('@abs commands: OK')
"@ 2>&1

Write-Host $validation
if ($LASTEXITCODE -ne 0) {
    Write-Error "package.json validation failed"
}
Write-Host "package.json validation: PASS ✅`n"

# ─── Step 4: Validate CLI imports ──────────────────────────────────────────
Write-Host "=== Step 4: CLI Import Validation ==="
Push-Location $ProjectRoot
try {
    python -c @"
from backend.abs.orchestrator import ABSOrchestrator, IngestResult, GenerateResult, AuditResult, QAResult, StatusResult
from backend.abs.ipc_protocol import ProgressMessage, LLMRequest, LLMResponse
from backend.abs.streaming import ABSStream
from cli.abs import abs_group
print('ABSOrchestrator import: OK')
print('IPC types import: OK')
print('ABSStream import: OK')
print('CLI abs_group import: OK')
s = ABSStream(mode='terminal')
s.progress('Test step', 'done')
print('ABSStream instantiation: OK')
"@ 2>&1
    if ($LASTEXITCODE -ne 0) { Write-Error "CLI import validation failed" }
    Write-Host "CLI imports: PASS ✅`n"
} finally {
    Pop-Location
}

# ─── Step 5: Package VSIX ──────────────────────────────────────────────────
Write-Host "=== Step 5: Package VSIX ==="
Push-Location $ExtensionDir
try {
    # Update version in package.json
    $pkg = Get-Content $PkgJson -Raw | ConvertFrom-Json
    $pkg.version = $Version
    $pkg | ConvertTo-Json -Depth 20 | Set-Content $PkgJson

    if (-not $DryRun) {
        npx @vscode/vsce package --no-dependencies 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Error "VSIX packaging failed (exit $LASTEXITCODE)"
        }
        $vsix = Get-ChildItem -Filter "*.vsix" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($vsix) {
            Write-Host "VSIX created: $($vsix.Name) ($([math]::Round($vsix.Length/1MB, 2)) MB)"
        }
    } else {
        Write-Host "  [DryRun] Would run: npx @vscode/vsce package --no-dependencies"
        Write-Host "  [DryRun] Output: gsf-ir-kts-extension-$Version.vsix"
    }
    Write-Host "VSIX packaging: PASS ✅`n"
} finally {
    Pop-Location
}

Write-Host "╔═══════════════════════════════════════════╗"
Write-Host "║   BUILD COMPLETE ✅  Phase 23             ║"
Write-Host "╚═══════════════════════════════════════════╝"
