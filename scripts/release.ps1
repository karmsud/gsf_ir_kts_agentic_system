<#
.SYNOPSIS
    Automated GitHub release script for KTS VSIX

.DESCRIPTION
    Prepares and publishes a GitHub release with the built VSIX:
    1. Validates VSIX exists in dist/
    2. Creates Git tag with version
    3. Generates checksums (SHA256)
    4. Creates GitHub release (manual or gh CLI)
    5. Uploads VSIX as release asset
    
    Requires GitHub CLI (gh) installed for automated upload.
    Falls back to manual instructions if gh not available.

.PARAMETER Version
    Version number for the release (e.g., "0.0.1")

.PARAMETER Draft
    Create as draft release (review before publishing)

.PARAMETER Prerelease
    Mark as pre-release (beta, alpha, etc.)

.PARAMETER Notes
    Custom release notes (default: auto-generated)

.PARAMETER Force
    Skip confirmation prompts

.EXAMPLE
    .\scripts\release.ps1 -Version "0.0.1"
    .\scripts\release.ps1 -Version "0.1.0" -Draft
    .\scripts\release.ps1 -Version "1.0.0" -Notes "Major release"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$Version,
    
    [switch]$Draft,
    [switch]$Prerelease,
    [string]$Notes,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "  KTS GITHUB RELEASE AUTOMATION" -ForegroundColor Cyan
Write-Host "  Version: v$Version" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

# Paths
$RepoRoot = Split-Path -Parent $PSScriptRoot
$DistDir = Join-Path $RepoRoot "dist"
$VsixPattern = "kts-agentic-system-$Version.vsix"
$VsixPath = Join-Path $DistDir $VsixPattern

# Step 1: Validate VSIX exists
Write-Host "[STEP 1] Validate VSIX" -ForegroundColor Cyan
Write-Host "-" * 80 -ForegroundColor Gray

if (-not (Test-Path $VsixPath)) {
    Write-Host "✗ VSIX not found: $VsixPath" -ForegroundColor Red
    Write-Host ""
    Write-Host "Available VSIX files in dist/:" -ForegroundColor Yellow
    
    if (Test-Path $DistDir) {
        Get-ChildItem -Path $DistDir -Filter "*.vsix" | ForEach-Object {
            Write-Host "  - $($_.Name)" -ForegroundColor Gray
        }
    } else {
        Write-Host "  (dist/ folder not found)" -ForegroundColor Gray
    }
    
    Write-Host ""
    Write-Host "Run this first:" -ForegroundColor Yellow
    Write-Host "  .\scripts\build_vsix.ps1 -Version `"$Version`"" -ForegroundColor White
    Write-Host ""
    exit 1
}

$VsixFile = Get-Item $VsixPath
$VsixSizeMB = [math]::Round($VsixFile.Length / 1MB, 2)

Write-Host "✓ VSIX found: $($VsixFile.Name)" -ForegroundColor Green
Write-Host "  Size: $VsixSizeMB MB" -ForegroundColor Gray
Write-Host "  Path: $VsixPath" -ForegroundColor Gray
Write-Host ""

# Step 2: Generate checksums
Write-Host "[STEP 2] Generate Checksums" -ForegroundColor Cyan
Write-Host "-" * 80 -ForegroundColor Gray

$Sha256Hash = (Get-FileHash -Path $VsixPath -Algorithm SHA256).Hash
$ChecksumFile = Join-Path $DistDir "kts-agentic-system-$Version.sha256"

"$Sha256Hash  $($VsixFile.Name)" | Set-Content $ChecksumFile -Encoding UTF8

Write-Host "✓ SHA256: $Sha256Hash" -ForegroundColor Green
Write-Host "  Saved to: $ChecksumFile" -ForegroundColor Gray
Write-Host ""

# Step 3: Verify git status
Write-Host "[STEP 3] Verify Git Status" -ForegroundColor Cyan
Write-Host "-" * 80 -ForegroundColor Gray

# Check if in git repo
try {
    $GitStatus = git status --porcelain 2>&1
} catch {
    Write-Host "✗ Not a git repository" -ForegroundColor Red
    exit 1
}

# Check for uncommitted changes
if ($GitStatus) {
    Write-Host "⚠ Uncommitted changes detected:" -ForegroundColor Yellow
    Write-Host ""
    git status --short
    Write-Host ""
    
    if (-not $Force) {
        $Response = Read-Host "Continue anyway? (y/N)"
        if ($Response -ne "y" -and $Response -ne "Y") {
            Write-Host "✗ Release cancelled" -ForegroundColor Red
            exit 1
        }
    }
}

# Check if tag already exists
$TagName = "v$Version"
$TagExists = git tag -l $TagName

if ($TagExists) {
    Write-Host "⚠ Tag '$TagName' already exists" -ForegroundColor Yellow
    
    if (-not $Force) {
        $Response = Read-Host "Delete and recreate tag? (y/N)"
        if ($Response -ne "y" -and $Response -ne "Y") {
            Write-Host "✗ Release cancelled" -ForegroundColor Red
            exit 1
        }
        
        # Delete local tag
        git tag -d $TagName
        
        # Delete remote tag if exists
        try {
            git push origin --delete $TagName 2>$null
        } catch {
            # Remote tag might not exist
        }
    }
}

Write-Host "✓ Git status verified" -ForegroundColor Green
Write-Host ""

# Step 4: Create Git tag
Write-Host "[STEP 4] Create Git Tag" -ForegroundColor Cyan
Write-Host "-" * 80 -ForegroundColor Gray

$TagMessage = "Release v$Version - KTS Agentic System"
git tag -a $TagName -m $TagMessage

Write-Host "✓ Created tag: $TagName" -ForegroundColor Green
Write-Host "  Message: $TagMessage" -ForegroundColor Gray
Write-Host ""

# Step 5: Push tag to GitHub
Write-Host "[STEP 5] Push Tag to GitHub" -ForegroundColor Cyan
Write-Host "-" * 80 -ForegroundColor Gray

if (-not $Force) {
    $Response = Read-Host "Push tag '$TagName' to GitHub? (Y/n)"
    if ($Response -eq "n" -or $Response -eq "N") {
        Write-Host "✗ Skipping push (delete tag with: git tag -d $TagName)" -ForegroundColor Yellow
        exit 0
    }
}

Write-Host "Pushing tag to origin..." -ForegroundColor Green
git push origin $TagName

Write-Host "✓ Tag pushed to GitHub" -ForegroundColor Green
Write-Host ""

# Step 6: Generate release notes
Write-Host "[STEP 6] Generate Release Notes" -ForegroundColor Cyan
Write-Host "-" * 80 -ForegroundColor Gray

if (-not $Notes) {
    # Auto-generate release notes
    $Notes = @"
## KTS Agentic System v$Version

**Single Self-Contained VSIX** (~350MB)

### 📦 What's Included
- **Complete VS Code Extension** - Full UI, commands, chat interface
- **Bundled Python Backend** - PyInstaller executable (~250MB)
- **All ML Models** - ChromaDB ONNX (all-MiniLM-L6-v2), spaCy (en_core_web_sm)
- **Document Processors** - PDF (PyMuPDF), DOCX, PPTX, HTML, and more
- **Zero Dependencies** - No Python, Node.js, or internet required

### 🚀 Installation

``````bash
# Download VSIX from release assets below
code --install-extension kts-agentic-system-$Version.vsix
``````

Restart VS Code and you're ready to go!

### ✨ Features
- ✅ Full offline operation (air-gapped environments)
- ✅ Document ingestion (PDF, DOCX, PPTX, TXT, MD, HTML)
- ✅ Semantic vector search with ChromaDB
- ✅ Named Entity Recognition (spaCy)
- ✅ Agentic workflows (LangGraph + LangChain)
- ✅ Chat interface for Q&A

### 📋 Requirements
- **OS**: Windows 10/11 (x64 only for v$Version)
- **VS Code**: 1.95.0 or later
- **Disk Space**: 500 MB free
- **RAM**: 8 GB recommended

### 🔐 Verification
SHA256: ``$Sha256Hash``

### 📖 Documentation
- [Build Guide](https://github.com/karmsud/gsf_ir_kts_agentic_system/blob/main/docs/BUILD_GUIDE.md)
- [User Guide](https://github.com/karmsud/gsf_ir_kts_agentic_system/blob/main/docs/USER_GUIDE.md)
- [Configuration](https://github.com/karmsud/gsf_ir_kts_agentic_system/blob/main/docs/CONFIGURATION.md)

### 🐛 Known Issues
- Windows x64 only (macOS/Linux support planned for v0.1.0)
- ~350MB download size (future releases will explore size optimization)

---

**Platform Support**: Windows x64  
**First Release**: February 2026
"@
}

Write-Host "Release notes prepared:" -ForegroundColor Green
Write-Host ""
Write-Host $Notes -ForegroundColor Gray
Write-Host ""

# Step 7: Create GitHub Release
Write-Host "[STEP 7] Create GitHub Release" -ForegroundColor Cyan
Write-Host "-" * 80 -ForegroundColor Gray

# Check if GitHub CLI is installed
$HasGhCli = $null -ne (Get-Command gh -ErrorAction SilentlyContinue)

if ($HasGhCli) {
    Write-Host "✓ GitHub CLI (gh) detected" -ForegroundColor Green
    Write-Host ""
    
    if (-not $Force) {
        $Response = Read-Host "Create GitHub release with 'gh' CLI? (Y/n)"
        if ($Response -eq "n" -or $Response -eq "N") {
            $HasGhCli = $false
        }
    }
}

if ($HasGhCli) {
    # Create release with gh CLI
    Write-Host "Creating release with GitHub CLI..." -ForegroundColor Green
    
    $GhArgs = @(
        "release", "create", $TagName,
        $VsixPath,
        $ChecksumFile,
        "--title", "KTS Agentic System v$Version",
        "--notes", $Notes
    )
    
    if ($Draft) {
        $GhArgs += "--draft"
        Write-Host "  Mode: Draft" -ForegroundColor Yellow
    }
    
    if ($Prerelease) {
        $GhArgs += "--prerelease"
        Write-Host "  Mode: Pre-release" -ForegroundColor Yellow
    }
    
    Write-Host ""
    
    & gh @GhArgs
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "✓ GitHub release created!" -ForegroundColor Green
        Write-Host ""
        Write-Host "View release:" -ForegroundColor Cyan
        
        # Get repo URL
        $RepoUrl = git config --get remote.origin.url
        $RepoUrl = $RepoUrl -replace '\.git$', ''
        $RepoUrl = $RepoUrl -replace 'git@github\.com:', 'https://github.com/'
        
        Write-Host "  $RepoUrl/releases/tag/$TagName" -ForegroundColor White
        Write-Host ""
    } else {
        Write-Host "✗ GitHub CLI release creation failed" -ForegroundColor Red
        Write-Host ""
        Write-Host "Try manual release creation (see instructions below)" -ForegroundColor Yellow
        $HasGhCli = $false
    }
    
} else {
    # Manual release instructions
    Write-Host "⚠ GitHub CLI (gh) not available" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Manual Release Instructions:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "1. Go to GitHub repository releases:" -ForegroundColor White
    
    $RepoUrl = git config --get remote.origin.url
    $RepoUrl = $RepoUrl -replace '\.git$', ''
    $RepoUrl = $RepoUrl -replace 'git@github\.com:', 'https://github.com/'
    
    Write-Host "   $RepoUrl/releases/new" -ForegroundColor Gray
    Write-Host ""
    Write-Host "2. Fill in release details:" -ForegroundColor White
    Write-Host "   - Tag: $TagName" -ForegroundColor Gray
    Write-Host "   - Title: KTS Agentic System v$Version" -ForegroundColor Gray
    Write-Host "   - Description: (see notes above)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "3. Upload release assets:" -ForegroundColor White
    Write-Host "   - $VsixPath" -ForegroundColor Gray
    Write-Host "   - $ChecksumFile" -ForegroundColor Gray
    Write-Host ""
    Write-Host "4. Publish release" -ForegroundColor White
    Write-Host ""
    
    # Save release notes to file for easy copy-paste
    $NotesFile = Join-Path $DistDir "release-notes-$Version.md"
    $Notes | Set-Content $NotesFile -Encoding UTF8
    
    Write-Host "Release notes saved to: $NotesFile" -ForegroundColor Green
    Write-Host ""
}

# Final Summary
Write-Host ""
Write-Host "=" * 80 -ForegroundColor Green
Write-Host "✓ RELEASE PREPARATION COMPLETE!" -ForegroundColor Green
Write-Host "=" * 80 -ForegroundColor Green
Write-Host ""
Write-Host "Summary:" -ForegroundColor Cyan
Write-Host "  Version: v$Version" -ForegroundColor White
Write-Host "  Tag: $TagName" -ForegroundColor White
Write-Host "  VSIX: $VsixSizeMB MB" -ForegroundColor White
Write-Host "  SHA256: $Sha256Hash" -ForegroundColor White
Write-Host ""

if ($Draft) {
    Write-Host "⚠ Draft release created - review before publishing" -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "Next steps:" -ForegroundColor Cyan
if ($HasGhCli) {
    Write-Host "  1. Review the release on GitHub" -ForegroundColor White
    Write-Host "  2. Test the VSIX download and installation" -ForegroundColor White
    Write-Host "  3. Ask users to test before wider announcement" -ForegroundColor White
} else {
    Write-Host "  1. Complete manual release creation on GitHub" -ForegroundColor White
    Write-Host "  2. Upload VSIX and checksum files" -ForegroundColor White
    Write-Host "  3. Test download and installation" -ForegroundColor White
}
Write-Host ""

