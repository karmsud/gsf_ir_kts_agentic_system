<#
.SYNOPSIS
    Autonomous end-to-end test suite for GSF IR KTS agentic system
.DESCRIPTION
    Runs full ingestion pipeline, Top 50 queries, advanced agent scenarios,
    idempotency checks, and pytest suite. Logs all outputs with timestamps.
.EXAMPLE
    .\scripts\autopilot_run_all.ps1
#>

param(
    [switch]$SkipIngestion,
    [switch]$QuickMode,
    [string]$LogDir = ""
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

# ============================================================================
# SETUP
# ============================================================================

$RepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepoRoot

if ([string]::IsNullOrEmpty($LogDir)) {
    $Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $LogDir = Join-Path $RepoRoot "scripts\logs\autopilot_$Timestamp"
}

if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

$LogFile = Join-Path $LogDir "autopilot_console.log"
$ResultsFile = Join-Path $LogDir "results.json"
$MetricsFile = Join-Path $LogDir "metrics.json"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] [$Level] $Message"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line
}

function Write-Section {
    param([string]$Title)
    $separator = "=" * 80
    Write-Log ""
    Write-Log $separator
    Write-Log "  $Title"
    Write-Log $separator
}

function Invoke-CLICommand {
    param(
        [string]$Command,
        [string]$Description,
        [string]$OutputFile = ""
    )
    
    Write-Log "Running: $Command" "CMD"
    $start = Get-Date
    
    if ([string]::IsNullOrEmpty($OutputFile)) {
        $OutputFile = Join-Path $LogDir "$Description.log"
    }
    
    $output = & .\.venv\Scripts\python.exe -m cli.main $Command.Split(" ") 2>&1
    $exitCode = $LASTEXITCODE
    $duration = (Get-Date) - $start
    
    $output | Out-File -FilePath $OutputFile -Encoding utf8
    $output | ForEach-Object { Write-Log $_ "OUT" }
    
    Write-Log "Exit code: $exitCode | Duration: $($duration.TotalSeconds)s" "RESULT"
    
    return @{
        Command = $Command
        Description = $Description
        ExitCode = $exitCode
        Duration = $duration.TotalSeconds
        OutputFile = $OutputFile
        Output = $output -join "`n"
    }
}

# ============================================================================
# PHASE 0: ENVIRONMENT CHECK
# ============================================================================

Write-Section "PHASE 0: ENVIRONMENT CHECK"

$EnvCheck = @{}

# Check Python
if (Test-Path ".\.venv\Scripts\python.exe") {
    $pythonVersion = & .\.venv\Scripts\python.exe --version 2>&1
    Write-Log "Python: $pythonVersion" "OK"
    $EnvCheck.Python = $pythonVersion.ToString()
} else {
    Write-Log "Python venv not found at .\.venv\Scripts\python.exe" "ERROR"
    $EnvCheck.Python = "MISSING"
}

# Check test corpus
if (Test-Path ".\kts_test_corpus") {
    $corpusFiles = Get-ChildItem -Path ".\kts_test_corpus" -Recurse -File
    $corpusCount = $corpusFiles.Count
    Write-Log "Test corpus: $corpusCount files found" "OK"
    $EnvCheck.CorpusFiles = $corpusCount
} else {
    Write-Log "Test corpus not found at .\kts_test_corpus" "ERROR"
    $EnvCheck.CorpusFiles = 0
}

# Check CLI
if (Test-Path ".\cli\main.py") {
    Write-Log "CLI entrypoint: cli\main.py found" "OK"
    $EnvCheck.CLI = "OK"
} else {
    Write-Log "CLI entrypoint not found" "ERROR"
    $EnvCheck.CLI = "MISSING"
}

# Check query pack
$QueryPackPath = ".\docs\TEST_QUERIES_TOP_50.json"
$QueryPack = $null
$AllQueries = @()
if (Test-Path $QueryPackPath) {
    try {
        $QueryPackData = Get-Content $QueryPackPath -Raw | ConvertFrom-Json
        # Flatten queries from all categories
        foreach ($category in $QueryPackData.categories) {
            $AllQueries += $category.queries
        }
        $QueryPack = @{ queries = $AllQueries }
        Write-Log "Query pack: $($AllQueries.Count) queries loaded" "OK"
        $EnvCheck.QueryPack = $AllQueries.Count
    } catch {
        Write-Log "Failed to parse query pack: $_" "WARN"
        $EnvCheck.QueryPack = "ERROR"
    }
} else {
    Write-Log "Query pack not found at $QueryPackPath" "WARN"
    $EnvCheck.QueryPack = 0
}

$Results = @{
    Timestamp = Get-Date -Format "o"
    Environment = $EnvCheck
    Phases = @{}
}

# ============================================================================
# PHASE 1: INGESTION PIPELINE
# ============================================================================

if (!$SkipIngestion) {
    Write-Section "PHASE 1: INGESTION PIPELINE"
    
    $IngestionResults = @()
    
    # Clean knowledge base for fresh run
    Write-Log "Cleaning knowledge_base for fresh ingestion..."
    if (Test-Path ".\knowledge_base\documents") {
        Remove-Item ".\knowledge_base\documents\*" -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path ".\knowledge_base\vectors") {
        Remove-Item ".\knowledge_base\vectors\*" -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path ".\knowledge_base\graph") {
        Remove-Item ".\knowledge_base\graph\*" -Recurse -Force -ErrorAction SilentlyContinue
    }
    # CRITICAL: Also reset manifest.json so crawl sees files as new (not modified)
    if (Test-Path ".\knowledge_base\manifest.json") {
        @{files = @{}; updated_at = $null} | ConvertTo-Json | Out-File ".\knowledge_base\manifest.json" -Encoding utf8
    }
    Write-Log "Knowledge base cleaned"
    
    # 1.1: Crawl
    $crawlResult = Invoke-CLICommand -Command "crawl --paths `".\kts_test_corpus`"" -Description "crawl"
    $IngestionResults += $crawlResult
    
    # 1.2: Ingest
    $ingestResult = Invoke-CLICommand -Command "ingest" -Description "ingest"
    $IngestionResults += $ingestResult
    
    # 1.3: Status
    $statusResult = Invoke-CLICommand -Command "status" -Description "status"
    $IngestionResults += $statusResult
    
    # 1.4: Vision - describe pending
    $describePendingResult = Invoke-CLICommand -Command "describe pending" -Description "describe_pending"
    $IngestionResults += $describePendingResult
    
    # Parse status output for metrics
    $statusMetrics = @{
        DocumentsIngested = 0
        ImagesPending = 0
        VectorsCreated = 0
    }
    
    # Try to extract from ingest output first
    if ($ingestResult.Output -match '"count":\s*(\d+)') {
        $statusMetrics.DocumentsIngested = [int]$matches[1]
    }
    # Fallback to status output
    if ($statusMetrics.DocumentsIngested -eq 0 -and $statusResult.Output -match '"documents":\s*(\d+)') {
        $statusMetrics.DocumentsIngested = [int]$matches[1]
    }
    if ($describePendingResult.Output -match '"count":\s*(\d+)') {
        $statusMetrics.ImagesPending = [int]$matches[1]
    }
    
    Write-Log "Ingestion metrics: $($statusMetrics.DocumentsIngested) docs, $($statusMetrics.ImagesPending) images pending"
    
    $Results.Phases.Ingestion = @{
        Commands = $IngestionResults
        Metrics = $statusMetrics
        Pass = ($crawlResult.ExitCode -eq 0) -and ($ingestResult.ExitCode -eq 0)
    }
} else {
    Write-Log "Skipping ingestion phase (--SkipIngestion flag)" "WARN"
}

# ============================================================================
# PHASE 2: TOP 50 QUERIES
# ============================================================================

Write-Section "PHASE 2: TOP 50 QUERIES"

$QueryResults = @()
$QueryMetrics = @{
    Total = 0
    WithCitations = 0
    WithoutCitations = 0
    ExpectedDocMatches = 0
    UnexpectedResults = 0
    Errors = 0
}

if ($QueryPack -and $QueryPack.queries) {
    $queriesToRun = $QueryPack.queries
    if ($QuickMode) {
        $queriesToRun = $queriesToRun | Select-Object -First 10
        Write-Log "Quick mode: running first 10 queries only" "INFO"
    }
    
    $QueryMetrics.Total = $queriesToRun.Count
    
    foreach ($q in $queriesToRun) {
        $queryId = $q.id
        $queryText = $q.query
        $expectedDocs = $q.expected_doc_ids
        
        Write-Log "Query $queryId : $queryText" "QUERY"
        
        $queryOutputFile = Join-Path $LogDir "query_${queryId}.json"
        $searchResult = Invoke-CLICommand -Command "search `"$queryText`"" -Description "query_$queryId" -OutputFile $queryOutputFile
        
        # Parse results for citations
        $hasCitations = $false
        $matchedExpected = $false
        
        if ($searchResult.Output -match 'file://|doc_id|source_path') {
            $hasCitations = $true
            $QueryMetrics.WithCitations++
        } else {
            $QueryMetrics.WithoutCitations++
        }
        
        # Check if expected doc IDs appear (match against doc_name, not full path)
        if ($expectedDocs) {
            foreach ($expectedDoc in $expectedDocs) {
                # Match docname anywhere in output (could be in doc_name field or filename)
                if ($searchResult.Output -match [regex]::Escape($expectedDoc)) {
                    $matchedExpected = $true
                    break
                }
            }
            if ($matchedExpected) {
                $QueryMetrics.ExpectedDocMatches++
            } else {
                $QueryMetrics.UnexpectedResults++
            }
        }
        
        if ($searchResult.ExitCode -ne 0) {
            $QueryMetrics.Errors++
        }
        
        $QueryResults += @{
            QueryId = $queryId
            QueryText = $queryText
            ExitCode = $searchResult.ExitCode
            HasCitations = $hasCitations
            MatchedExpected = $matchedExpected
            OutputFile = $queryOutputFile
        }
    }
    
    Write-Log "Query metrics: $($QueryMetrics.WithCitations)/$($QueryMetrics.Total) with citations"
    Write-Log "Expected doc matches: $($QueryMetrics.ExpectedDocMatches), Unexpected: $($QueryMetrics.UnexpectedResults)"
    
} else {
    Write-Log "No query pack available, skipping query tests" "WARN"
}

$Results.Phases.Queries = @{
    Results = $QueryResults
    Metrics = $QueryMetrics
    Pass = ($QueryMetrics.WithCitations -eq $QueryMetrics.Total) -and ($QueryMetrics.Errors -eq 0)
}

# ============================================================================
# PHASE 3: ADVANCED AGENTS
# ============================================================================

Write-Section "PHASE 3: ADVANCED AGENTS"

$AdvancedResults = @()

# 3.1: Training Path
Write-Log "Testing Training Path agent..."
$trainingTopic = "ToolX authentication"
$trainingResult = Invoke-CLICommand -Command "training --topic `"$trainingTopic`"" -Description "training_path"
$AdvancedResults += @{ Agent = "Training"; Result = $trainingResult }

# 3.2: Impact Analysis
Write-Log "Testing Impact agent..."
$impactEntity = "ToolX"
$impactResult = Invoke-CLICommand -Command "impact --entity `"$impactEntity`"" -Description "impact"
$AdvancedResults += @{ Agent = "Impact"; Result = $impactResult }

# 3.3: Freshness
Write-Log "Testing Freshness agent..."
$freshnessResult = Invoke-CLICommand -Command "freshness" -Description "freshness"
$AdvancedResults += @{ Agent = "Freshness"; Result = $freshnessResult }

$advancedPass = ($AdvancedResults | Where-Object { $_.Result.ExitCode -ne 0 }).Count -eq 0

$Results.Phases.AdvancedAgents = @{
    Results = $AdvancedResults
    Pass = $advancedPass
}

# ============================================================================
# PHASE 4: IDEMPOTENCY CHECK
# ============================================================================

Write-Section "PHASE 4: IDEMPOTENCY CHECK"

Write-Log "Re-running crawl and ingest to check for duplicates..."

# Get doc count before
$beforeStatus = Invoke-CLICommand -Command "status" -Description "status_before_rerun"
$beforeCount = 0
if ($beforeStatus.Output -match 'Documents ingested: (\d+)') {
    $beforeCount = [int]$matches[1]
}
Write-Log "Documents before rerun: $beforeCount"

# Re-crawl and re-ingest
$recrawlResult = Invoke-CLICommand -Command "crawl --paths `".\kts_test_corpus`"" -Description "recrawl"
$reingestResult = Invoke-CLICommand -Command "ingest" -Description "reingest"

# Get doc count after
$afterStatus = Invoke-CLICommand -Command "status" -Description "status_after_rerun"
$afterCount = 0
if ($afterStatus.Output -match 'Documents ingested: (\d+)') {
    $afterCount = [int]$matches[1]
}
Write-Log "Documents after rerun: $afterCount"

$duplicatesCreated = $afterCount -gt $beforeCount
if ($duplicatesCreated) {
    Write-Log "FAILURE: Duplicates created! Before: $beforeCount, After: $afterCount" "ERROR"
} else {
    Write-Log "SUCCESS: No duplicates. Count stable at $afterCount" "OK"
}

$Results.Phases.Idempotency = @{
    BeforeCount = $beforeCount
    AfterCount = $afterCount
    DuplicatesCreated = $duplicatesCreated
    Pass = !$duplicatesCreated
}

# ============================================================================
# PHASE 5: PYTEST SUITE
# ============================================================================

Write-Section "PHASE 5: PYTEST SUITE"

$pytestOutputFile = Join-Path $LogDir "pytest.log"
Write-Log "Running pytest..."

$pytestOutput = & .\.venv\Scripts\python.exe -m pytest tests\ -v --tb=short 2>&1
$pytestExitCode = $LASTEXITCODE
$pytestOutput | Out-File -FilePath $pytestOutputFile -Encoding utf8
$pytestOutput | ForEach-Object { Write-Log $_ "PYTEST" }

$pytestPass = $pytestExitCode -eq 0
Write-Log "Pytest exit code: $pytestExitCode" $(if ($pytestPass) { "OK" } else { "ERROR" })

$Results.Phases.Pytest = @{
    ExitCode = $pytestExitCode
    OutputFile = $pytestOutputFile
    Pass = $pytestPass
}

# ============================================================================
# SUMMARY & EXIT CRITERIA
# ============================================================================

Write-Section "SUMMARY & EXIT CRITERIA"

$ExitCriteria = @{
    IngestionComplete = $Results.Phases.Ingestion.Pass
    QueriesWithCitations = ($QueryMetrics.WithCitations -eq $QueryMetrics.Total)
    QueryAccuracy = ($QueryMetrics.Total -gt 0) -and (($QueryMetrics.ExpectedDocMatches / $QueryMetrics.Total) -ge 0.9)
    NoIdempotencyDuplicates = $Results.Phases.Idempotency.Pass
    AdvancedAgentsPass = $Results.Phases.AdvancedAgents.Pass
    PytestPass = $Results.Phases.Pytest.Pass
}

$ExitCriteria.AllPass = ($ExitCriteria.Values | Where-Object { $_ -eq $false }).Count -eq 0

Write-Log ""
Write-Log "EXIT CRITERIA EVALUATION:"
Write-Log "  [$(if($ExitCriteria.IngestionComplete){'PASS'}else{'FAIL'})] Ingestion pipeline completed without errors"
Write-Log "  [$(if($ExitCriteria.QueriesWithCitations){'PASS'}else{'FAIL'})] All queries returned citations"
Write-Log "  [$(if($ExitCriteria.QueryAccuracy){'PASS'}else{'FAIL'})] Query accuracy >= 90% (expected doc matches)"
Write-Log "  [$(if($ExitCriteria.NoIdempotencyDuplicates){'PASS'}else{'FAIL'})] No duplicates on re-ingestion"
Write-Log "  [$(if($ExitCriteria.AdvancedAgentsPass){'PASS'}else{'FAIL'})] Advanced agents executed without errors"
Write-Log "  [$(if($ExitCriteria.PytestPass){'PASS'}else{'FAIL'})] Pytest suite passed"
Write-Log ""
Write-Log "OVERALL RESULT: $(if($ExitCriteria.AllPass){'PASS'}else{'FAIL'})" $(if($ExitCriteria.AllPass){'OK'}else{'ERROR'})

$Results.ExitCriteria = $ExitCriteria
$Results.OverallPass = $ExitCriteria.AllPass

# ============================================================================
# SAVE RESULTS
# ============================================================================

Write-Log ""
Write-Log "Saving results to:"
Write-Log "  Console log: $LogFile"
Write-Log "  Results JSON: $ResultsFile"
Write-Log "  Metrics JSON: $MetricsFile"

$Results | ConvertTo-Json -Depth 10 | Out-File -FilePath $ResultsFile -Encoding utf8

$Metrics = @{
    Timestamp = Get-Date -Format "o"
    Environment = $EnvCheck
    Ingestion = $Results.Phases.Ingestion.Metrics
    Queries = $QueryMetrics
    ExitCriteria = $ExitCriteria
}
$Metrics | ConvertTo-Json -Depth 5 | Out-File -FilePath $MetricsFile -Encoding utf8

Write-Log ""
Write-Log "Autopilot run complete."
Write-Log "Log directory: $LogDir"

Pop-Location

if ($ExitCriteria.AllPass) {
    exit 0
} else {
    exit 1
}
