#Requires -Version 5.1
<#
.SYNOPSIS
    Query Accuracy Tuning Orchestrator - Runs golden query evaluation with parameter sweep.

.DESCRIPTION
    Executes ingestion, runs all golden queries, scores results, and optionally sweeps ranking parameters.
    Targets: Tune Top-1 ≥99%, Holdout Top-1 ≥90%, Overall Top-3 ≥98%

.PARAMETER Mode
    baseline  = Run once with current settings
    sweep     = Run parameter sweep over ranking weights
    full      = Baseline + sweep + best config selection

.PARAMETER SkipIngest
    Skip document ingestion (assumes KB already populated)

.PARAMETER ShowDetails
    Show detailed failure analysis in scoring

.EXAMPLE
    .\run_accuracy_tuning.ps1 -Mode baseline
    .\run_accuracy_tuning.ps1 -Mode full
    .\run_accuracy_tuning.ps1 -Mode sweep -SkipIngest -ShowDetails
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("baseline", "sweep", "full")]
    [string]$Mode = "baseline",
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipIngest = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$ShowDetails = $false
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Configure paths
$RepoRoot = Split-Path $PSScriptRoot -Parent
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$GoldenQueriesPath = Join-Path $RepoRoot "tests\golden_queries.json"
$ScorerScript = Join-Path $RepoRoot "tests\score_queries.py"
$KnowledgeBase = Join-Path $RepoRoot "knowledge_base"
$Corpus = Join-Path $RepoRoot "kts_test_corpus"
$OutputDir = Join-Path $RepoRoot "tests\accuracy_tuning_output"
$RetrievalServicePath = Join-Path $RepoRoot "backend\agents\retrieval_service.py"

# Create output directory
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

Write-Host "`n=====================================================================" -ForegroundColor Cyan
Write-Host "   QUERY ACCURACY TUNING ORCHESTRATOR" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "Mode:          $Mode" -ForegroundColor White
Write-Host "Skip Ingest:   $SkipIngest" -ForegroundColor White
Write-Host "Show Details:  $ShowDetails" -ForegroundColor White
Write-Host "Output Dir:    $OutputDir" -ForegroundColor White
Write-Host "Golden Pack:   $GoldenQueriesPath" -ForegroundColor White
Write-Host "=====================================================================`n" -ForegroundColor Cyan

# Validate prerequisites
if (-not (Test-Path $GoldenQueriesPath)) {
    Write-Host "ERROR: Golden queries file not found: $GoldenQueriesPath" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $ScorerScript)) {
    Write-Host "ERROR: Scorer script not found: $ScorerScript" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $PythonExe)) {
    Write-Host "ERROR: Python venv not found: $PythonExe" -ForegroundColor Red
    Write-Host "Run: python -m venv .venv" -ForegroundColor Yellow
    exit 1
}

# Load golden queries
Write-Host "[1/5] Loading golden queries..." -ForegroundColor Yellow
$GoldenData = Get-Content $GoldenQueriesPath -Raw | ConvertFrom-Json
$TotalQueries = $GoldenData.queries.Count
$TuneQueries = ($GoldenData.queries | Where-Object { $_.split -eq "tune" }).Count
$HoldoutQueries = ($GoldenData.queries | Where-Object { $_.split -eq "holdout" }).Count
Write-Host "  Loaded $TotalQueries queries (Tune: $TuneQueries, Holdout: $HoldoutQueries)" -ForegroundColor Green

# Step 2: Ingest documents
if (-not $SkipIngest) {
    Write-Host "`n[2/5] Ingesting documents..." -ForegroundColor Yellow
    Write-Host "  Cleaning knowledge base..." -ForegroundColor Gray
    
    # Reset KB
    if (Test-Path $KnowledgeBase) {
        Remove-Item -Path $KnowledgeBase -Recurse -Force
    }
    New-Item -ItemType Directory -Path $KnowledgeBase -Force | Out-Null
    
    $ManifestPath = Join-Path $KnowledgeBase "manifest.json"
    # Use UTF8NoBOM to avoid JSON decode error, and use proper manifest structure
    $Utf8NoBomEncoding = New-Object System.Text.UTF8Encoding $False
    $ManifestContent = '{"files": {}, "updated_at": null}'
    [System.IO.File]::WriteAllText($ManifestPath, $ManifestContent, $Utf8NoBomEncoding)
    
    Write-Host "  Running ingestion..." -ForegroundColor Gray
    $IngestOutput = & $PythonExe -m cli.main ingest --paths $Corpus 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Ingestion failed" -ForegroundColor Red
        Write-Host $IngestOutput -ForegroundColor Red
        exit 1
    }
    
    # Parse ingestion stats
    if ($IngestOutput -match "Processed (\d+) documents") {
        $DocsIngested = $Matches[1]
        Write-Host "  ✅ Ingested $DocsIngested documents" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ Could not parse ingestion count" -ForegroundColor Yellow
    }
} else {
    Write-Host "`n[2/5] Skipping ingestion (using existing KB)" -ForegroundColor Yellow
}

# Step 3: Execute all golden queries
Write-Host "`n[3/5] Executing golden queries..." -ForegroundColor Yellow
$ResultsFile = Join-Path $OutputDir "search_results.json"
$SearchResults = @{}
$SuccessCount = 0
$FailCount = 0

foreach ($Query in $GoldenData.queries) {
    $QueryId = $Query.query_id
    $QueryText = $Query.query_text
    
    Write-Host "  [$QueryId] $QueryText" -ForegroundColor Gray -NoNewline
    
    try {
        $SearchOutput = & $PythonExe -m cli.main search $QueryText 2>&1 | Out-String
        
        if ($LASTEXITCODE -eq 0) {
            # Parse JSON output from CLI
            try {
                $SearchJson = $SearchOutput | ConvertFrom-Json
                $SearchResults[$QueryId] = @{
                    "query_id" = $QueryId
                    "query_text" = $QueryText
                    "retrieved_chunks" = @($SearchJson.context_chunks)
                }
            } catch {
                # JSON parsing failed, store raw output
                $SearchResults[$QueryId] = @{
                    "query_id" = $QueryId
                    "query_text" = $QueryText
                    "output" = $SearchOutput
                    "retrieved_chunks" = @()
                }
            }
            
            Write-Host " ✅" -ForegroundColor Green
            $SuccessCount++
        } else {
            $SearchResults[$QueryId] = @{
                "query_id" = $QueryId
                "query_text" = $QueryText
                "error" = "Search command failed with exit code $LASTEXITCODE"
                "output" = $SearchOutput
                "retrieved_chunks" = @()
            }
            Write-Host " ❌" -ForegroundColor Red
            $FailCount++
        }
    } catch {
        $SearchResults[$QueryId] = @{
            "query_id" = $QueryId
            "query_text" = $QueryText
            "error" = $_.Exception.Message
            "retrieved_chunks" = @()
        }
        Write-Host " ❌ (exception)" -ForegroundColor Red
        $FailCount++
    }
}

Write-Host "`n  Executed: $SuccessCount/$TotalQueries queries" -ForegroundColor $(if ($SuccessCount -eq $TotalQueries) { "Green" } else { "Yellow" })
if ($FailCount -gt 0) {
    Write-Host "  Failed: $FailCount queries" -ForegroundColor Red
}

# Save search results
$ResultsJson = $SearchResults | ConvertTo-Json -Depth 10
$Utf8NoBomEncoding = New-Object System.Text.UTF8Encoding $False
[System.IO.File]::WriteAllText($ResultsFile, $ResultsJson, $Utf8NoBomEncoding)
Write-Host "  Results saved to: $ResultsFile" -ForegroundColor Gray

# Step 4: Score results
Write-Host "`n[4/5] Scoring query accuracy..." -ForegroundColor Yellow
$ScoreArgs = @($GoldenQueriesPath, $ResultsFile)
if ($ShowDetails) {
    $ScoreArgs += "--verbose"
}

$ScoreOutput = & $PythonExe $ScorerScript $ScoreArgs 2>&1 | Out-String
Write-Host $ScoreOutput

# Parse score results
$ScoresFile = Join-Path $OutputDir "accuracy_scores.json"
if (Test-Path $ScoresFile) {
    $ScoreData = Get-Content $ScoresFile -Raw | ConvertFrom-Json
    $TuneTop1 = $ScoreData.metrics.tune.top1_accuracy
    $HoldoutTop1 = $ScoreData.metrics.holdout.top1_accuracy
    $OverallTop3 = $ScoreData.metrics.overall.top3_accuracy
    $AllTargetsMet = $ScoreData.safe_targets.all_targets_met
    
    Write-Host "`n  SAFE TARGETS:" -ForegroundColor Cyan
    Write-Host "    Tune Top-1:     $TuneTop1% (target ≥99%)" -ForegroundColor $(if ($TuneTop1 -ge 99) { "Green" } else { "Red" })
    Write-Host "    Holdout Top-1:  $HoldoutTop1% (target ≥90%)" -ForegroundColor $(if ($HoldoutTop1 -ge 90) { "Green" } else { "Red" })
    Write-Host "    Overall Top-3:  $OverallTop3% (target ≥98%)" -ForegroundColor $(if ($OverallTop3 -ge 98) { "Green" } else { "Red" })
    
    if ($AllTargetsMet) {
        Write-Host "`n  ✅ ALL TARGETS MET - TUNING COMPLETE!" -ForegroundColor Green
    } else {
        Write-Host "`n  ❌ Targets not met - tuning required" -ForegroundColor Red
    }
} else {
    Write-Host "  ⚠ Could not load score data" -ForegroundColor Yellow
}

# Step 5: Parameter sweep (if requested)
if ($Mode -eq "sweep" -or $Mode -eq "full") {
    Write-Host "`n[5/5] Running parameter sweep..." -ForegroundColor Yellow
    Write-Host "  ⚠ Parameter sweep not yet implemented" -ForegroundColor Yellow
    Write-Host "  Manual tuning required: Edit $RetrievalServicePath rerank() function" -ForegroundColor Gray
    Write-Host "  Suggested tuning strategies:" -ForegroundColor Gray
    Write-Host "    1. Add exact match boosting (query term in doc_name)" -ForegroundColor Gray
    Write-Host "    2. Boost doc_type matches (query intent → expected doc_type)" -ForegroundColor Gray
    Write-Host "    3. Add error code detection (ERR-XXX-000 pattern recognition)" -ForegroundColor Gray
    Write-Host "    4. Increase how/what/when/where intent boosting" -ForegroundColor Gray
    Write-Host "    5. Add title/heading boosting" -ForegroundColor Gray
    Write-Host "`n  After manual tuning, rerun: .\run_accuracy_tuning.ps1 -Mode baseline -SkipIngest" -ForegroundColor Cyan
} else {
    Write-Host "`n[5/5] Skipping parameter sweep (Mode: baseline)" -ForegroundColor Yellow
}

Write-Host "`n=====================================================================" -ForegroundColor Cyan
Write-Host "   ACCURACY TUNING COMPLETE" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "Output directory: $OutputDir" -ForegroundColor White
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Review accuracy_scores.json for detailed failures" -ForegroundColor Gray
Write-Host "  2. Tune retrieval_service.py rerank() function" -ForegroundColor Gray
Write-Host "  3. Rerun with: .\run_accuracy_tuning.ps1 -Mode baseline -SkipIngest -Verbose" -ForegroundColor Gray
Write-Host "=====================================================================`n" -ForegroundColor Cyan

exit 0
