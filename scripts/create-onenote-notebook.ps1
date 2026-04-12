<#
.SYNOPSIS
    Creates a test OneNote notebook from the GSF IR Support Library
    markdown source for Phase 19 E2E testing.

.DESCRIPTION
    This script generates synthetic .one (OneNote section) and .onetoc2
    (Table of Contents) binary files from the GSF IR Support Library
    markdown content.  The generated notebook can be used to validate
    the Phase 19 OneNote ingestion pipeline end-to-end.

    The script uses Python to generate the binary files via the
    onenote_test_helpers module.

.PARAMETER RootPath
    Path to the project root (where .venv_build exists).

.PARAMETER NotebookName
    Display name for the generated notebook.

.PARAMETER OutputDir
    Directory where the notebook folder will be created.
    Defaults to kb_test\onenote_test_corpus under the project root.

.PARAMETER SourceFile
    Path to the GSF IR Support Library.md source file.

.EXAMPLE
    pwsh -ExecutionPolicy Bypass -File scripts\create-onenote-notebook.ps1 `
      -RootPath "C:\Users\Karmsud\Projects\gsf_ir_kts_agentic_system" `
      -NotebookName "GSF_IR_Test_Notebook"
#>

param(
    [Parameter(Mandatory = $false)]
    [string]$RootPath = (Split-Path -Parent $PSScriptRoot),

    [Parameter(Mandatory = $false)]
    [string]$NotebookName = "GSF_IR_Test_Notebook",

    [Parameter(Mandatory = $false)]
    [string]$OutputDir = "",

    [Parameter(Mandatory = $false)]
    [string]$SourceFile = ""
)

# Resolve paths
$ProjectRoot = (Resolve-Path $RootPath).Path
$PythonExe = Join-Path $ProjectRoot ".venv_build\Scripts\python.exe"

if (-not $OutputDir) {
    $OutputDir = Join-Path $ProjectRoot "kb_test\onenote_test_corpus"
}

if (-not $SourceFile) {
    $SourceFile = Join-Path $ProjectRoot "kb_test\troubleshoot\GSF IR Support Library.md"
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Phase 19: OneNote Test Notebook Generator" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Project Root : $ProjectRoot"
Write-Host "  Python       : $PythonExe"
Write-Host "  Output Dir   : $OutputDir"
Write-Host "  Notebook Name: $NotebookName"
Write-Host "  Source File  : $SourceFile"
Write-Host ""

# Verify Python exists
if (-not (Test-Path $PythonExe)) {
    Write-Host "ERROR: Python not found at $PythonExe" -ForegroundColor Red
    Write-Host "Run: python -m venv .venv_build" -ForegroundColor Yellow
    exit 1
}

# Verify source file exists
if (-not (Test-Path $SourceFile)) {
    Write-Host "ERROR: Source file not found at $SourceFile" -ForegroundColor Red
    exit 1
}

# Create output directory
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    Write-Host "Created output directory: $OutputDir" -ForegroundColor Green
}

# Generate the notebook using the Python test helper
$PythonScript = @"
import sys
sys.path.insert(0, r'$ProjectRoot')

from tests.onenote_test_helpers import create_test_notebook, verify_notebook_structure

nb_dir = create_test_notebook(
    output_dir=r'$OutputDir',
    notebook_name=r'$NotebookName',
    include_images=True,
)

info = verify_notebook_structure(nb_dir)
print(f"Notebook created at: {nb_dir}")
print(f"  .one files:  {info['one_files']}")
print(f"  .onetoc2:    {info['toc_files']}")
print(f"  Total size:  {info['total_size']:,} bytes")
"@

Write-Host "Generating synthetic OneNote files..." -ForegroundColor Yellow
$PythonScript | & $PythonExe -

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "SUCCESS: Test notebook generated!" -ForegroundColor Green
    Write-Host ""

    # List the generated files
    $NbFolder = Join-Path $OutputDir $NotebookName
    if (Test-Path $NbFolder) {
        Write-Host "Generated files:" -ForegroundColor Cyan
        Get-ChildItem $NbFolder | ForEach-Object {
            Write-Host "  $($_.Name)  ($($_.Length) bytes)"
        }
    }

    Write-Host ""
    Write-Host "To test ingestion:" -ForegroundColor Cyan
    Write-Host "  # Dry run (parse only, no vector store writes):"
    Write-Host "  & '$PythonExe' -m cli.main ingest-onenote '$NbFolder' --dry-run --skip-images"
    Write-Host ""
    Write-Host "  # Full ingestion:"
    Write-Host "  & '$PythonExe' -m cli.main ingest-onenote '$NbFolder' --full --skip-images"
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "FAILED: Notebook generation encountered errors." -ForegroundColor Red
    exit 1
}
