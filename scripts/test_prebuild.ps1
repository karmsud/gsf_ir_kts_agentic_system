<#
.SYNOPSIS
    Pre-build test gate — runs all tests before packaging.

.DESCRIPTION
    Executes the complete testing matrix:
      1. Clean leftover test runtime directories
      2. Python: Phase 17 tests (197 unit tests)
      3. JavaScript: Extension tests (scope, participant, tool)
      4. Python: Pre-build validation suite
      5. Python: Fast smoke across ALL phases (~5%)
    
    Exit code 0 = all passed → safe to build.
    Exit code 1 = failures detected → fix before build.

.PARAMETER Phase17Only
    Run only Phase 17 tests (fastest option).

.PARAMETER SkipJS
    Skip JavaScript extension tests.

.PARAMETER Verbose
    Show full pytest verbose output.

.EXAMPLE
    .\scripts\test_prebuild.ps1
    .\scripts\test_prebuild.ps1 -Phase17Only
    .\scripts\test_prebuild.ps1 -SkipJS -Verbose
#>

param(
    [switch]$Phase17Only,
    [switch]$SkipJS,
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $RepoRoot ".venv_build\Scripts\python.exe"
$FailCount = 0
$StepResults = @()

function Banner($text) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor Cyan
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor Cyan
    Write-Host ""
}

function StepResult($name, $passed) {
    $Script:StepResults += @{ Name = $name; Passed = $passed }
    if (-not $passed) { $Script:FailCount++ }
}

# ─── Check prerequisites ─────────────────────────────────────
if (-not (Test-Path $VenvPython)) {
    Write-Host "ERROR: .venv_build not found. Run: python -m venv .venv_build" -ForegroundColor Red
    exit 1
}

Banner "KTS PRE-BUILD TEST GATE"

$totalStart = Get-Date

# ─── Step 0: Clean test runtimes ─────────────────────────────
Write-Host "[0/5] Cleaning leftover test runtime directories..." -ForegroundColor Yellow
$runtimes = Get-ChildItem -Path $RepoRoot -Directory -Filter "kts_test_runtime_*" -ErrorAction SilentlyContinue
if ($runtimes) {
    $runtimes | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  Removed $($runtimes.Count) runtime dirs" -ForegroundColor Gray
} else {
    Write-Host "  No runtime dirs to clean" -ForegroundColor Gray
}

# ─── Pytest args ──────────────────────────────────────────────
$VerboseArg = if ($Verbose) { "-v" } else { "-q" }

# ─── Step 1: Phase 17 unit tests ─────────────────────────────
Banner "STEP 1/5: PHASE 17 UNIT TESTS (197 tests)"

$step1Start = Get-Date
& $VenvPython -m pytest tests/ -k "phase17" $VerboseArg --tb=short --no-header 2>&1 | ForEach-Object { Write-Host $_ }
$step1Passed = ($LASTEXITCODE -eq 0)
$step1Time = ((Get-Date) - $step1Start).TotalSeconds

if ($step1Passed) {
    Write-Host "`n  PASS (${step1Time:N1}s)" -ForegroundColor Green
} else {
    Write-Host "`n  FAIL (${step1Time:N1}s)" -ForegroundColor Red
}
StepResult "Phase 17 Python Tests" $step1Passed

if ($Phase17Only) {
    # Skip remaining steps
    goto summary
}

# ─── Step 2: Extension JS tests ──────────────────────────────
if (-not $SkipJS) {
    Banner "STEP 2/5: EXTENSION JAVASCRIPT TESTS"
    
    $jsTestFiles = @(
        (Join-Path $RepoRoot "extension\tests\scope_discovery.test.js"),
        (Join-Path $RepoRoot "extension\tests\participant_phase17.test.js"),
        (Join-Path $RepoRoot "extension\tests\kts_tool_forwarding.test.js")
    )
    
    $nodeAvailable = $true
    try {
        $null = & node --version 2>&1
        if ($LASTEXITCODE -ne 0) { $nodeAvailable = $false }
    } catch {
        $nodeAvailable = $false
    }
    
    if ($nodeAvailable) {
        $step2Start = Get-Date
        & node --test @jsTestFiles 2>&1 | ForEach-Object { Write-Host $_ }
        $step2Passed = ($LASTEXITCODE -eq 0)
        $step2Time = ((Get-Date) - $step2Start).TotalSeconds
        
        if ($step2Passed) {
            Write-Host "`n  PASS (${step2Time:N1}s)" -ForegroundColor Green
        } else {
            Write-Host "`n  FAIL (${step2Time:N1}s)" -ForegroundColor Red
        }
        StepResult "Extension JS Tests" $step2Passed
    } else {
        Write-Host "  SKIP — Node.js not found" -ForegroundColor Yellow
        StepResult "Extension JS Tests" $true  # Don't block build for missing node
    }
} else {
    Write-Host "STEP 2/5: EXTENSION JS TESTS — SKIPPED (-SkipJS)" -ForegroundColor Yellow
    StepResult "Extension JS Tests" $true
}

# ─── Step 3: Pre-build validation suite ──────────────────────
Banner "STEP 3/5: PRE-BUILD VALIDATION SUITE"

$step3Start = Get-Date
& $VenvPython -m pytest tests/test_prebuild_suite.py $VerboseArg --tb=short --no-header 2>&1 | ForEach-Object { Write-Host $_ }
$step3Passed = ($LASTEXITCODE -eq 0)
$step3Time = ((Get-Date) - $step3Start).TotalSeconds

if ($step3Passed) {
    Write-Host "`n  PASS (${step3Time:N1}s)" -ForegroundColor Green
} else {
    Write-Host "`n  FAIL (${step3Time:N1}s)" -ForegroundColor Red
}
StepResult "Pre-Build Validation" $step3Passed

# ─── Step 4: Fast smoke (~5%) ────────────────────────────────
Banner "STEP 4/5: FAST SMOKE TEST (all phases ~5%)"

$step4Start = Get-Date
& $VenvPython -m pytest tests/ --fast --ignore=tests/test_e2e_real_corpus.py --ignore=tests/test_bug_fix_integration.py $VerboseArg --tb=short --no-header --timeout=30 2>&1 | ForEach-Object { Write-Host $_ }
$step4Passed = ($LASTEXITCODE -eq 0)
$step4Time = ((Get-Date) - $step4Start).TotalSeconds

if ($step4Passed) {
    Write-Host "`n  PASS (${step4Time:N1}s)" -ForegroundColor Green
} else {
    Write-Host "`n  FAIL (${step4Time:N1}s)" -ForegroundColor Red
}
StepResult "Fast Smoke (all phases)" $step4Passed

# ─── Step 5: Lint/error check on key files ───────────────────
Banner "STEP 5/5: SYNTAX CHECK (py -m py_compile)"

$keyFiles = @(
    "config/settings.py",
    "cli/main.py",
    "backend/agents/retrieval_service.py",
    "backend/retrieval/human_like_retriever.py",
    "backend/graph/graph_partitioner.py",
    "backend/common/scope_resolver.py",
    "backend/agents/diff_engine.py",
    "backend/agents/aggregation_engine.py",
    "backend/vector/deal_catalog.py",
    "backend/graph/enhanced_graph_builder.py",
    "backend/graph/builder.py",
    "backend/agents/ingestion_agent.py"
)

$compileOK = $true
foreach ($f in $keyFiles) {
    $fullPath = Join-Path $RepoRoot $f
    & $VenvPython -m py_compile $fullPath 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  FAIL: $f" -ForegroundColor Red
        $compileOK = $false
    } else {
        if ($Verbose) { Write-Host "  OK: $f" -ForegroundColor Gray }
    }
}

if ($compileOK) {
    Write-Host "  All $($keyFiles.Count) files compile cleanly" -ForegroundColor Green
}
StepResult "Syntax Check" $compileOK

# ─── Summary ─────────────────────────────────────────────────
:summary

$totalTime = ((Get-Date) - $totalStart).TotalSeconds

Banner "TEST GATE SUMMARY"

foreach ($r in $StepResults) {
    $icon = if ($r.Passed) { "[PASS]" } else { "[FAIL]" }
    $color = if ($r.Passed) { "Green" } else { "Red" }
    Write-Host ("  {0,-8} {1}" -f $icon, $r.Name) -ForegroundColor $color
}

Write-Host ""
Write-Host ("  Total time: {0:N1}s" -f $totalTime) -ForegroundColor Gray
Write-Host ""

if ($FailCount -eq 0) {
    Write-Host "  ========================================" -ForegroundColor Green
    Write-Host "   ALL GATES PASSED — READY TO BUILD" -ForegroundColor Green
    Write-Host "  ========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Next: .\scripts\build_vsix.ps1" -ForegroundColor Cyan
    exit 0
} else {
    Write-Host "  ========================================" -ForegroundColor Red
    Write-Host "   $FailCount GATE(S) FAILED — FIX BEFORE BUILD" -ForegroundColor Red
    Write-Host "  ========================================" -ForegroundColor Red
    exit 1
}
