<#
Creates a OneNote notebook + sections + pages from the markdown files in this folder.

Prereqs:
- Windows desktop OneNote installed (OneNote 2016 / OneNote for Microsoft 365 desktop)
- Run PowerShell in 64-bit
- OneNote must have been opened at least once, signed in, and allowed COM automation

Usage:
  pwsh -ExecutionPolicy Bypass -File .\create-onenote-notebook.ps1 -RootPath "C:\path\to\onenote_test_corpus" -NotebookName "TS_GUIDE_RAG_Test"

Notes:
- This script inserts markdown as plain text (headings preserved as text).
- If you want richer formatting, you can extend UpdatePageContent to emit OneNote XML with styled outlines.
#>

param(
  [Parameter(Mandatory=$true)][string]$RootPath,
  [Parameter(Mandatory=$true)][string]$NotebookName
)

function New-OneNoteApplication {
  try {
    return New-Object -ComObject "OneNote.Application"
  } catch {
    throw "Unable to create OneNote COM object. Ensure desktop OneNote is installed and launched at least once."
  }
}

function Get-OneNoteHierarchyXml([__ComObject]$OneNote, [int]$scope=0) {
  # scope: 0 = notebooks, 1 = sections, 2 = pages
  $xml = ""
  $OneNote.GetHierarchy("", $scope, [ref]$xml)
  return [xml]$xml
}

function Ensure-Notebook([__ComObject]$OneNote, [string]$NotebookName) {
  # OneNote COM doesn't offer a simple "create notebook named X" for all versions.
  # Easiest: create a section group under the default notebook with the desired name.
  # For a true separate notebook, prefer Graph API; for this RAG test, section group is enough.

  $hier = Get-OneNoteHierarchyXml -OneNote $OneNote -scope 0
  $defaultNotebook = $hier.Notebooks.Notebook | Select-Object -First 1
  if(-not $defaultNotebook) { throw "No notebook found. Open OneNote and create a notebook first." }

  # Create a section group named NotebookName
  $existing = $defaultNotebook.SectionGroup | Where-Object { $_.name -eq $NotebookName } | Select-Object -First 1
  if($existing) { return $existing.ID }

  $newId = ""
  $OneNote.CreateNewSection($defaultNotebook.ID, $NotebookName, [ref]$newId) | Out-Null
  # CreateNewSection makes a section, not a section group. We'll use a top-level section as container.
  return $newId
}

function Ensure-Section([__ComObject]$OneNote, [string]$ParentId, [string]$SectionName) {
  $newSectionId = ""
  $OneNote.CreateNewSection($ParentId, $SectionName, [ref]$newSectionId) | Out-Null
  return $newSectionId
}

function New-PageWithText([__ComObject]$OneNote, [string]$SectionId, [string]$Title, [string]$BodyText) {
  $pageId = ""
  $OneNote.CreateNewPage($SectionId, [ref]$pageId, 0) | Out-Null

  # Minimal OneNote Page XML
  $ns = "http://schemas.microsoft.com/office/onenote/2013/onenote"
  $pageXml = @"
<?xml version="1.0"?>
<one:Page xmlns:one="$ns" ID="$pageId">
  <one:Title>
    <one:OE>
      <one:T><![CDATA[$Title]]></one:T>
    </one:OE>
  </one:Title>
  <one:Outline>
    <one:OEChildren>
      <one:OE>
        <one:T><![CDATA[$BodyText]]></one:T>
      </one:OE>
    </one:OEChildren>
  </one:Outline>
</one:Page>
"@

  $OneNote.UpdatePageContent($pageXml, 0) | Out-Null
  return $pageId
}

# ---- Main ----
$OneNote = New-OneNoteApplication

$containerId = Ensure-Notebook -OneNote $OneNote -NotebookName $NotebookName

# Map folder names to sections
$sectionFolders = Get-ChildItem -Path $RootPath -Directory | Where-Object { $_.Name -match '^\d{2}_|^\d{2,}_|^0\d_|^0\d{1,}_|^03_|^04_|^05_|^06_|^07_' }

foreach($folder in $sectionFolders) {
  $sectionName = $folder.Name
  Write-Host "Creating section: $sectionName"
  $sectionId = Ensure-Section -OneNote $OneNote -ParentId $containerId -SectionName $sectionName

  $mdFiles = Get-ChildItem -Path $folder.FullName -Filter *.md | Sort-Object Name
  foreach($md in $mdFiles) {
    $text = Get-Content -Path $md.FullName -Raw
    # Title = first markdown heading if present
    $title = ($text -split "`n" | Select-Object -First 1) -replace '^#\s*',''
    if([string]::IsNullOrWhiteSpace($title)) { $title = $md.BaseName }
    $body = $text

    # Escape ']]>' edge case in CDATA
    $body = $body -replace '\]\]>', ']]]]><![CDATA[>'

    Write-Host "  Page: $title"
    New-PageWithText -OneNote $OneNote -SectionId $sectionId -Title $title -BodyText $body | Out-Null
  }
}

Write-Host "Done. Open OneNote and look for the new sections/pages under container section: $NotebookName"
