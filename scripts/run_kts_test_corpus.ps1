$ErrorActionPreference = 'Stop'

Set-Location "$PSScriptRoot\.."

$zipPath = Join-Path (Get-Location) 'kts_test_corpus.zip'
$destPath = Join-Path (Get-Location) 'kts_test_corpus'
$pythonExe = Join-Path (Get-Location) '.venv\Scripts\python.exe'

if (-not (Test-Path $zipPath)) {
    throw "Missing corpus zip: $zipPath"
}

if (-not (Test-Path $pythonExe)) {
    throw "Missing Python executable: $pythonExe"
}

Write-Host "[KTS] Expanding archive to $destPath"
Expand-Archive -Path $zipPath -DestinationPath $destPath -Force

Write-Host "[KTS] Running crawl"
& $pythonExe -m cli.main crawl --paths ".\kts_test_corpus"

Write-Host "[KTS] Running ingest"
& $pythonExe -m cli.main ingest --paths ".\kts_test_corpus"

Write-Host "[KTS] Running status"
& $pythonExe -m cli.main status

Write-Host "[KTS] Checking pending image descriptions"
& $pythonExe -m cli.main describe pending
