# KTS Test Suite Runner
# 
# Purpose: Automated test harness for the GSF IR KTS agentic system
# Runs full pipeline: crawl → ingest → status → vision → sample queries
# Generates timestamped logs for validation
#
# Usage: .\run_kts_test_suite.ps1
#
# Prerequisites:
# - Python venv activated (.venv\Scripts\Activate.ps1)
# - Test corpus unzipped at .\kts_test_corpus\
# - All dependencies installed (pip install -r requirements.txt)

param(
    [string]$CorpusPath = ".\kts_test_corpus",
    [string]$LogDir = ".\scripts\logs",
    [int]$QueryLimit = 10,  # Number of test queries to run from Top 50
    [switch]$SkipIngestion,  # Skip crawl/ingest if already done
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

# === HELPER FUNCTIONS ===

function Write-Section {
    param([string]$Title)
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host $Title -ForegroundColor Cyan
    Write-Host "========================================`n" -ForegroundColor Cyan
}

function Invoke-CliCommand {
    param(
        [string]$Command,
        [string]$LogFile,
        [string]$Description
    )
    
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Description..." -ForegroundColor Yellow
    
    $pythonExe = ".\.venv\Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        throw "Python venv not found at $pythonExe. Run: python -m venv .venv"
    }
    
    $fullCommand = "$pythonExe -m cli.main $Command"
    if ($Verbose) {
        Write-Host "  Command: $fullCommand" -ForegroundColor Gray
    }
    
    # Execute and capture output
    $output = Invoke-Expression $fullCommand 2>&1
    $exitCode = $LASTEXITCODE
    
    # Save to log file
    $logEntry = @{
        timestamp = (Get-Date -Format "o")
        command = $fullCommand
        exit_code = $exitCode
        output = $output
    }
    $logEntry | ConvertTo-Json -Depth 10 | Out-File -FilePath $LogFile -Encoding utf8
    
    # Display result
    if ($exitCode -eq 0) {
        Write-Host "  ✓ Success" -ForegroundColor Green
    } else {
        Write-Host "  ✗ FAILED (Exit Code: $exitCode)" -ForegroundColor Red
        Write-Host "  Output: $output" -ForegroundColor Red
    }
    
    return @{
        success = ($exitCode -eq 0)
        output = $output
        exit_code = $exitCode
    }
}

function Test-JsonOutput {
    param([string]$Output)
    
    try {
        $json = $Output | ConvertFrom-Json
        return $true
    } catch {
        return $false
    }
}

function Validate-Citations {
    param([PSCustomObject]$SearchResult)
    
    $issues = @()
    
    if (-not $SearchResult.citations) {
        $issues += "Missing 'citations' field"
        return $issues
    }
    
    foreach ($citation in $SearchResult.citations) {
        if (-not $citation.doc_id) { $issues += "Citation missing 'doc_id'" }
        if (-not $citation.doc_name) { $issues += "Citation missing 'doc_name'" }
        if (-not $citation.source_path) { $issues += "Citation missing 'source_path'" }
        if (-not $citation.uri) { $issues += "Citation missing 'uri'" }
        elseif (-not $citation.uri.StartsWith("file://")) {
            $issues += "Citation URI doesn't start with 'file://': $($citation.uri)"
        }
        if ($null -eq $citation.version) { $issues += "Citation missing 'version'" }
    }
    
    return $issues
}

# === SETUP ===

Write-Section "KTS Test Suite - $timestamp"

# Create log directory
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
    Write-Host "Created log directory: $LogDir" -ForegroundColor Green
}

# Validate corpus exists
if (-not (Test-Path $CorpusPath)) {
    Write-Host "ERROR: Test corpus not found at $CorpusPath" -ForegroundColor Red
    Write-Host "Expected corpus structure:" -ForegroundColor Yellow
    Write-Host "  $CorpusPath\Reference\" -ForegroundColor Yellow
    Write-Host "  $CorpusPath\Release_Notes\" -ForegroundColor Yellow
    Write-Host "  $CorpusPath\Training\" -ForegroundColor Yellow
    Write-Host "  $CorpusPath\Troubleshooting\" -ForegroundColor Yellow
    Write-Host "  $CorpusPath\User_Guides\" -ForegroundColor Yellow
    exit 1
}

Write-Host "Corpus path: $CorpusPath" -ForegroundColor Green
Write-Host "Log directory: $LogDir" -ForegroundColor Green
Write-Host "Timestamp: $timestamp" -ForegroundColor Green

$testResults = @{
    timestamp = $timestamp
    corpus_path = $CorpusPath
    stages = @{}
    summary = @{
        total_tests = 0
        passed = 0
        failed = 0
        warnings = 0
    }
}

# === STAGE 1: CRAWL ===

if (-not $SkipIngestion) {
    Write-Section "Stage 1: Crawl File System"
    
    $result = Invoke-CliCommand `
        -Command "crawl --paths `"$CorpusPath`"" `
        -LogFile "$LogDir\crawl_$timestamp.json" `
        -Description "Scanning corpus for new/modified/deleted files"
    
    $testResults.stages.crawl = @{
        success = $result.success
        exit_code = $result.exit_code
        log_file = "$LogDir\crawl_$timestamp.json"
    }
    
    if ($result.success) {
        $crawlOutput = $result.output | ConvertFrom-Json
        Write-Host "  Files found: new=$($crawlOutput.new_files.Count), modified=$($crawlOutput.modified_files.Count), deleted=$($crawlOutput.deleted_files.Count), unchanged=$($crawlOutput.unchanged_files)" -ForegroundColor Cyan
        $testResults.stages.crawl.stats = @{
            new_files = $crawlOutput.new_files.Count
            modified_files = $crawlOutput.modified_files.Count
            deleted_files = $crawlOutput.deleted_files.Count
            unchanged_files = $crawlOutput.unchanged_files
        }
        $testResults.summary.passed++
    } else {
        $testResults.summary.failed++
    }
    $testResults.summary.total_tests++
} else {
    Write-Host "Skipping crawl/ingest (--SkipIngestion flag)" -ForegroundColor Yellow
}

# === STAGE 2: INGEST ===

if (-not $SkipIngestion) {
    Write-Section "Stage 2: Ingest Documents"
    
    $result = Invoke-CliCommand `
        -Command "ingest --paths `"$CorpusPath`"" `
        -LogFile "$LogDir\ingest_$timestamp.json" `
        -Description "Converting documents to markdown and extracting metadata"
    
    $testResults.stages.ingest = @{
        success = $result.success
        exit_code = $result.exit_code
        log_file = "$LogDir\ingest_$timestamp.json"
    }
    
    if ($result.success) {
        $ingestOutput = $result.output | ConvertFrom-Json
        Write-Host "  Documents ingested: $($ingestOutput.Count)" -ForegroundColor Cyan
        $testResults.stages.ingest.stats = @{
            documents_ingested = $ingestOutput.Count
        }
        $testResults.summary.passed++
    } else {
        $testResults.summary.failed++
    }
    $testResults.summary.total_tests++
}

# === STAGE 3: STATUS CHECK ===

Write-Section "Stage 3: System Status"

$result = Invoke-CliCommand `
    -Command "status" `
    -LogFile "$LogDir\status_$timestamp.json" `
    -Description "Checking system status (documents, graph, vectors)"

$testResults.stages.status = @{
    success = $result.success
    exit_code = $result.exit_code
    log_file = "$LogDir\status_$timestamp.json"
}

if ($result.success) {
    $statusOutput = $result.output | ConvertFrom-Json
    Write-Host "  Documents: $($statusOutput.documents)" -ForegroundColor Cyan
    Write-Host "  Manifest files: $($statusOutput.manifest_files)" -ForegroundColor Cyan
    Write-Host "  Graph nodes: $($statusOutput.graph_nodes)" -ForegroundColor Cyan
    Write-Host "  Graph edges: $($statusOutput.graph_edges)" -ForegroundColor Cyan
    Write-Host "  Vector chunks: $($statusOutput.vector_chunks)" -ForegroundColor Cyan
    
    # Validate expected minimums
    $warnings = @()
    if ($statusOutput.documents -lt 9) { $warnings += "Expected at least 9 documents (corpus has 9 doc files)" }
    if ($statusOutput.graph_nodes -lt 10) { $warnings += "Expected at least 10 graph nodes" }
    if ($statusOutput.vector_chunks -eq 0) { $warnings += "No vector chunks indexed (retrieval will fail)" }
    
    $testResults.stages.status.stats = $statusOutput
    $testResults.stages.status.warnings = $warnings
    
    if ($warnings.Count -gt 0) {
        Write-Host "`n  Warnings:" -ForegroundColor Yellow
        foreach ($warning in $warnings) {
            Write-Host "    - $warning" -ForegroundColor Yellow
        }
        $testResults.summary.warnings += $warnings.Count
    }
    
    $testResults.summary.passed++
} else {
    $testResults.summary.failed++
}
$testResults.summary.total_tests++

# === STAGE 4: VISION WORKFLOW ===

Write-Section "Stage 4: Vision Workflow (Multi-Modal)"

$result = Invoke-CliCommand `
    -Command "describe pending" `
    -LogFile "$LogDir\vision_pending_$timestamp.json" `
    -Description "Checking for images awaiting description"

$testResults.stages.vision_pending = @{
    success = $result.success
    exit_code = $result.exit_code
    log_file = "$LogDir\vision_pending_$timestamp.json"
}

if ($result.success) {
    $visionOutput = $result.output | ConvertFrom-Json
    Write-Host "  Pending images: $($visionOutput.count)" -ForegroundColor Cyan
    
    if ($visionOutput.count -eq 0) {
        Write-Host "  ⚠ WARNING: No pending images found!" -ForegroundColor Yellow
        Write-Host "  Expected: Images from Reference/images/ (4 PNGs)" -ForegroundColor Yellow
        Write-Host "  Possible causes:" -ForegroundColor Yellow
        Write-Host "    - Image extraction not implemented for embedded images" -ForegroundColor Yellow
        Write-Host "    - Markdown image references not parsed" -ForegroundColor Yellow
        Write-Host "    - Standalone image files not discovered" -ForegroundColor Yellow
        Write-Host "  See DIAGNOSTICS section in TEST_MASTER_PLAN.md" -ForegroundColor Yellow
        $testResults.summary.warnings++
    } else {
        Write-Host "  Images awaiting description:" -ForegroundColor Cyan
        foreach ($img in $visionOutput.documents) {
            Write-Host "    - $($img.image_id) from $($img.doc_name)" -ForegroundColor Gray
        }
    }
    
    $testResults.stages.vision_pending.stats = @{
        pending_count = $visionOutput.count
    }
    $testResults.summary.passed++
} else {
    $testResults.summary.failed++
}
$testResults.summary.total_tests++

# === STAGE 5: SAMPLE RETRIEVAL QUERIES ===

Write-Section "Stage 5: Sample Retrieval Queries"

# Load Top 50 queries
$queriesFile = ".\docs\TEST_QUERIES_TOP_50.json"
if (-not (Test-Path $queriesFile)) {
    Write-Host "WARNING: Test queries file not found at $queriesFile" -ForegroundColor Yellow
    Write-Host "Skipping query validation tests" -ForegroundColor Yellow
    $testResults.stages.queries = @{
        skipped = $true
        reason = "Query file not found"
    }
} else {
    $queryPack = Get-Content $queriesFile -Raw | ConvertFrom-Json
    $allQueries = @()
    foreach ($category in $queryPack.categories) {
        $allQueries += $category.queries
    }
    
    # Run first N queries
    $queriesToTest = $allQueries | Select-Object -First $QueryLimit
    Write-Host "Running $($queriesToTest.Count) sample queries (out of $($allQueries.Count) total)`n" -ForegroundColor Cyan
    
    $queryResults = @()
    
    foreach ($query in $queriesToTest) {
        Write-Host "[Q$($query.id)] $($query.query)" -ForegroundColor Yellow
        
        $result = Invoke-CliCommand `
            -Command "search --query `"$($query.query)`" --max-results 3" `
            -LogFile "$LogDir\query_$($query.id)_$timestamp.json" `
            -Description "  Searching"
        
        $queryResult = @{
            query_id = $query.id
            query_text = $query.query
            expected_confidence = $query.expected_confidence
            expected_failure_mode = $query.expected_failure_mode
            success = $result.success
            exit_code = $result.exit_code
            validation_issues = @()
        }
        
        if ($result.success) {
            $searchOutput = $result.output | ConvertFrom-Json
            
            # Validate JSON structure
            if (-not (Test-JsonOutput $result.output)) {
                $queryResult.validation_issues += "Output is not valid JSON"
            }
            
            # Validate citations
            $citationIssues = Validate-Citations $searchOutput
            if ($citationIssues.Count -gt 0) {
                $queryResult.validation_issues += $citationIssues
                Write-Host "  ✗ Citation issues: $($citationIssues -join '; ')" -ForegroundColor Red
            } else {
                Write-Host "  ✓ Citations valid" -ForegroundColor Green
            }
            
            # Check confidence vs. expected
            if ($query.expected_confidence -eq "LOW" -and $searchOutput.confidence -ge 0.5) {
                $queryResult.validation_issues += "Expected LOW confidence but got $($searchOutput.confidence)"
            }
            
            # Check escalation for low-confidence results
            if ($searchOutput.confidence -lt 0.5 -and -not $searchOutput.escalation) {
                $queryResult.validation_issues += "Low confidence (<0.5) but no escalation provided"
            }
            
            Write-Host "  Confidence: $($searchOutput.confidence)" -ForegroundColor Cyan
            Write-Host "  Citations: $($searchOutput.citations.Count)" -ForegroundColor Cyan
            if ($searchOutput.escalation) {
                Write-Host "  Escalation: $($searchOutput.escalation.type)" -ForegroundColor Yellow
            }
            
            if ($queryResult.validation_issues.Count -eq 0) {
                Write-Host "  ✓ PASS" -ForegroundColor Green
                $testResults.summary.passed++
            } else {
                Write-Host "  ✗ FAIL" -ForegroundColor Red
                $testResults.summary.failed++
            }
        } else {
            $queryResult.validation_issues += "Command failed with exit code $($result.exit_code)"
            $testResults.summary.failed++
        }
        
        $queryResults += $queryResult
        $testResults.summary.total_tests++
        Write-Host ""
    }
    
    $testResults.stages.queries = @{
        total_queries = $queriesToTest.Count
        results = $queryResults
        log_pattern = "$LogDir\query_*_$timestamp.json"
    }
}

# === STAGE 6: IDEMPOTENCY CHECK ===

Write-Section "Stage 6: Idempotency Validation"

Write-Host "Re-running crawl to verify no new files detected..." -ForegroundColor Yellow
$result = Invoke-CliCommand `
    -Command "crawl --paths `"$CorpusPath`"" `
    -LogFile "$LogDir\crawl_idempotency_$timestamp.json" `
    -Description "Re-crawling same directory"

$testResults.stages.idempotency_crawl = @{
    success = $result.success
    exit_code = $result.exit_code
}

if ($result.success) {
    $crawlOutput = $result.output | ConvertFrom-Json
    
    if ($crawlOutput.new_files.Count -eq 0 -and $crawlOutput.modified_files.Count -eq 0) {
        Write-Host "  ✓ Idempotency PASS: No new or modified files detected" -ForegroundColor Green
        $testResults.summary.passed++
    } else {
        Write-Host "  ✗ Idempotency FAIL: Found $($crawlOutput.new_files.Count) new, $($crawlOutput.modified_files.Count) modified" -ForegroundColor Red
        $testResults.summary.failed++
    }
} else {
    Write-Host "  ✗ Idempotency check failed to execute" -ForegroundColor Red
    $testResults.summary.failed++
}
$testResults.summary.total_tests++

# === FINAL SUMMARY ===

Write-Section "Test Suite Summary"

$testResults.summary.pass_rate = if ($testResults.summary.total_tests -gt 0) {
    [math]::Round(($testResults.summary.passed / $testResults.summary.total_tests) * 100, 1)
} else { 0 }

Write-Host "Total Tests: $($testResults.summary.total_tests)" -ForegroundColor White
Write-Host "Passed: $($testResults.summary.passed)" -ForegroundColor Green
Write-Host "Failed: $($testResults.summary.failed)" -ForegroundColor Red
Write-Host "Warnings: $($testResults.summary.warnings)" -ForegroundColor Yellow
Write-Host "Pass Rate: $($testResults.summary.pass_rate)%" -ForegroundColor $(if ($testResults.summary.pass_rate -ge 80) { "Green" } else { "Red" })

# Save full test results
$summaryFile = "$LogDir\test_suite_summary_$timestamp.json"
$testResults | ConvertTo-Json -Depth 10 | Out-File -FilePath $summaryFile -Encoding utf8
Write-Host "`nFull results saved to: $summaryFile" -ForegroundColor Cyan

# === EXIT CRITERIA EVALUATION ===

Write-Section "Exit Criteria Evaluation"

$exitCriteria = @(
    @{ name = "Pass rate ≥80%"; met = $testResults.summary.pass_rate -ge 80 },
    @{ name = "Zero failed tests"; met = $testResults.summary.failed -eq 0 },
    @{ name = "Status check passed"; met = $testResults.stages.status.success },
    @{ name = "Idempotency validated"; met = $testResults.stages.idempotency_crawl.success }
)

$allCriteriaMet = $true
foreach ($criterion in $exitCriteria) {
    $status = if ($criterion.met) { "✓ PASS" } else { "✗ FAIL"; $allCriteriaMet = $false }
    $color = if ($criterion.met) { "Green" } else { "Red" }
    Write-Host "  $status - $($criterion.name)" -ForegroundColor $color
}

if ($allCriteriaMet) {
    Write-Host "`n🎉 ALL EXIT CRITERIA MET - System ready for production" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n⚠ SOME EXIT CRITERIA NOT MET - Review failures before go-live" -ForegroundColor Yellow
    exit 1
}
