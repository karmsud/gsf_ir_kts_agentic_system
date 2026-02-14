# GSF IR KTS — Multi-Modal Pipeline Diagnostics

**Version:** 1.0  
**Date:** 2026-02-14  
**Purpose:** Troubleshooting guide for the image extraction and vision workflow

---

## Quick Diagnosis Decision Tree

```
START: describe pending returns 0 images
│
├─→ Are there image files in the corpus?
│   ├─→ NO: Expected behavior (no images to describe)
│   └─→ YES: Continue...
│
├─→ Are images embedded in documents (DOCX/PDF/PPTX)?
│   ├─→ YES: Check EXTRACTION FAILURE (see Section 1)
│   └─→ NO: Continue...
│
├─→ Are images referenced in Markdown (![](image.png))?
│   ├─→ YES: Check MARKDOWN REFERENCE PARSING (see Section 2)
│   └─→ NO: Continue...
│
├─→ Are images standalone files (PNG/JPG next to MD)?
│   ├─→ YES: Check STANDALONE IMAGE DISCOVERY (see Section 3)
│   └─→ NO: No images in corpus (expected behavior)
│
└─→ Check MANIFEST CORRUPTION (see Section 4)
```

---

## Section 1: Embedded Image Extraction Failure

### Symptom
- DOCX/PDF/PPTX files ingested successfully
- `describe pending` returns 0 images
- Expected: Images embedded in Office documents should be extracted

### Root Cause
**Current Implementation**: The converters return empty image lists.

- **DOCX converter** (`backend/ingestion/docx_converter.py`):
  ```python
  return text, []  # ← Always returns empty image list
  ```

- **PDF converter** (`backend/ingestion/pdf_converter.py`):
  ```python
  return "\n".join(parts), []  # ← Always returns empty image list
  ```

- **PPTX converter** (`backend/ingestion/pptx_converter.py`):
  ```python
  return "\n".join(parts), []  # ← Always returns empty image list
  ```

### Diagnosis Commands

**1. Inspect ingested document folder:**
```powershell
# Check if images were saved to disk
Get-ChildItem -Path .\knowledge_base\documents\* -Include *.png, *.jpg, *.jpeg -Recurse | Select-Object FullName, Length
```

**Expected**: If extraction worked, you'd see PNG/JPG files in document folders  
**Actual (current)**: No image files found

**2. Check converter source:**
```powershell
# View DOCX converter implementation
Get-Content .\backend\ingestion\docx_converter.py | Select-String -Pattern "return.*\[\]"
```

**Expected**: Should see extraction logic saving images and returning paths  
**Actual (current)**: `return text, []`

**3. Check pending manifest:**
```powershell
# Inspect pending descriptions manifest
if (Test-Path .\knowledge_base\pending_descriptions.json) {
    Get-Content .\knowledge_base\pending_descriptions.json | ConvertFrom-Json | Select-Object -ExpandProperty pending
} else {
    Write-Host "Manifest doesn't exist yet (expected on first run)"
}
```

**Expected**: List of image IDs with doc_id, image_path, surrounding_text  
**Actual (current)**: Empty array or file doesn't exist

### Fix Implementation

**DOCX Image Extraction** (example):
```python
# In backend/ingestion/docx_converter.py

from docx.opc.constants import RELATIONSHIP_TYPE as RT

def extract_images_from_docx(doc_path: str, output_dir: str) -> list[tuple[str, str]]:
    """
    Extract embedded images from DOCX.
    Returns: [(image_id, saved_path), ...]
    """
    doc = Document(doc_path)
    images = []
    
    for rel in doc.part.rels.values():
        if "image" in rel.target_ref:
            image_data = rel.target_part.blob
            image_ext = rel.target_ref.split('.')[-1]
            image_id = f"img_{len(images):03d}"
            image_path = os.path.join(output_dir, f"{image_id}.{image_ext}")
            
            with open(image_path, 'wb') as f:
                f.write(image_data)
            
            images.append((image_id, image_path))
    
    return images

# Update convert() method:
def convert(self, file_path: str, output_dir: str) -> tuple[str, list[str]]:
    doc = Document(file_path)
    text = extract_text(doc)
    
    # Extract images
    images = extract_images_from_docx(file_path, output_dir)
    image_refs = [img_path for _, img_path in images]
    
    return text, image_refs  # ← Now returns actual image paths
```

**PDF Image Extraction** (requires PyMuPDF):
```python
# In backend/ingestion/pdf_converter.py

def extract_images_from_pdf(pdf_path: str, output_dir: str) -> list[str]:
    """Extract embedded images from PDF."""
    doc = fitz.open(pdf_path)
    images = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images(full=True)
        
        for img_idx, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_data = base_image["image"]
            image_ext = base_image["ext"]
            
            image_id = f"img_p{page_num+1}_{img_idx}"
            image_path = os.path.join(output_dir, f"{image_id}.{image_ext}")
            
            with open(image_path, 'wb') as f:
                f.write(image_data)
            
            images.append(image_path)
    
    return images
```

**PPTX Image Extraction** (similar pattern):
```python
# In backend/ingestion/pptx_converter.py

def extract_images_from_pptx(pptx_path: str, output_dir: str) -> list[str]:
    """Extract embedded images from PPTX."""
    prs = Presentation(pptx_path)
    images = []
    
    for slide_num, slide in enumerate(prs.slides):
        for shape in slide.shapes:
            if hasattr(shape, "image"):
                image_data = shape.image.blob
                image_ext = shape.image.ext
                image_id = f"img_slide{slide_num+1}_{len(images)}"
                image_path = os.path.join(output_dir, f"{image_id}.{image_ext}")
                
                with open(image_path, 'wb') as f:
                    f.write(image_data)
                
                images.append(image_path)
    
    return images
```

---

## Section 2: Markdown Image Reference Parsing

### Symptom
- Markdown files contain `![alt text](image.png)` references
- Images exist as separate PNG/JPG files
- `describe pending` returns 0 images

### Root Cause
**Current Implementation**: Markdown converter reads text but doesn't parse image references.

### Diagnosis Commands

**1. Check Markdown files for image references:**
```powershell
# Search for image links in Markdown files
Get-ChildItem -Path .\kts_test_corpus -Filter *.md -Recurse | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    if ($content -match '!\[.*?\]\((.*?)\)') {
        Write-Host "$($_.Name): Found image references"
        $content | Select-String -Pattern '!\[.*?\]\((.*?)\)' -AllMatches | ForEach-Object {
            $_.Matches | ForEach-Object { Write-Host "  - $($_.Groups[1].Value)" }
        }
    }
}
```

**2. Verify referenced images exist:**
```powershell
# Check if referenced images are on disk
$mdFile = ".\kts_test_corpus\User_Guides\UserGuide_ToolX_Onboarding.md"
if (Test-Path $mdFile) {
    $content = Get-Content $mdFile -Raw
    if ($content -match '!\[.*?\]\((.*?)\)') {
        $imagePath = $Matches[1]
        $fullPath = Join-Path (Split-Path $mdFile) $imagePath
        if (Test-Path $fullPath) {
            Write-Host "Image exists: $fullPath"
        } else {
            Write-Host "Image MISSING: $fullPath"
        }
    }
}
```

### Fix Implementation

**Update Markdown Converter:**
```python
# In backend/ingestion/html_converter.py (also handles Markdown)

import re
from pathlib import Path

def extract_markdown_image_refs(markdown_text: str, source_file: str) -> list[str]:
    """
    Parse Markdown image references: ![alt](path)
    Returns absolute paths to referenced images.
    """
    image_pattern = r'!\[.*?\]\((.*?)\)'
    matches = re.findall(image_pattern, markdown_text)
    
    source_dir = Path(source_file).parent
    image_paths = []
    
    for match in matches:
        # Resolve relative path
        if not match.startswith('http'):
            image_path = (source_dir / match).resolve()
            if image_path.exists():
                image_paths.append(str(image_path))
    
    return image_paths

# Update convert() method:
def convert(self, file_path: str, output_dir: str) -> tuple[str, list[str]]:
    with open(file_path, 'r', encoding='utf-8') as f:
        markdown_text = f.read()
    
    # Parse image references
    image_refs = extract_markdown_image_refs(markdown_text, file_path)
    
    return markdown_text, image_refs  # ← Now returns referenced images
```

---

## Section 3: Standalone Image Discovery

### Symptom
- PNG/JPG files exist in corpus (e.g., `Reference/images/toolx_auth_401.png`)
- Not referenced by any document
- `describe pending` returns 0 images

### Root Cause
**Current Implementation**: Crawler only processes files with registered extensions (DOCX, PDF, MD, etc.). Standalone images are ignored.

### Diagnosis Commands

**1. List all images in corpus:**
```powershell
# Find all image files
Get-ChildItem -Path .\kts_test_corpus -Include *.png, *.jpg, *.jpeg -Recurse | Select-Object FullName, Length
```

**Expected**: Should see images in `Reference/images/` folder  
**Actual**: Images exist but aren't processed

**2. Check crawler file extensions:**
```powershell
# View supported extensions in config
Get-Content .\config\settings.py | Select-String -Pattern "SUPPORTED_EXTENSIONS"
```

**Expected**: Should include `.png`, `.jpg`, `.jpeg` for standalone images

### Fix Implementation

**Option A: Include Images in Crawler**
```python
# In config/settings.py

SUPPORTED_EXTENSIONS = {
    ".docx", ".pdf", ".pptx", ".html", ".htm", ".md", ".txt", ".json",
    ".png", ".jpg", ".jpeg"  # ← Add image extensions
}

# In backend/agents/ingestion_agent.py

def ingest_standalone_image(file_info: FileInfo) -> IngestedDocument:
    """
    Create a minimal document for standalone images.
    These images have no surrounding context but should still be described.
    """
    doc_id = generate_doc_id(file_info.path)
    
    # No text extraction, just metadata
    metadata = DocumentMetadata(
        doc_id=doc_id,
        title=file_info.filename,
        doc_type="IMAGE",
        source_path=file_info.path,
        # ... other fields
    )
    
    # Copy image to knowledge base
    doc_dir = get_doc_dir(doc_id)
    image_dest = os.path.join(doc_dir, file_info.filename)
    shutil.copy(file_info.path, image_dest)
    
    return IngestedDocument(
        doc_id=doc_id,
        title=file_info.filename,
        markdown_path=None,  # No markdown
        images=[image_dest],  # Single image
        # ... other fields
    )
```

**Option B: Post-Ingestion Image Discovery**
```python
# In backend/agents/vision_agent.py

def discover_orphan_images(knowledge_base_path: str) -> list[dict]:
    """
    Find images in corpus that aren't linked to any document.
    Create pending entries for them.
    """
    corpus_images = []
    for root, dirs, files in os.walk(knowledge_base_path):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                corpus_images.append(os.path.join(root, file))
    
    # Check which images are already in manifest
    manifest = load_image_manifest()
    known_images = {img['image_path'] for img in manifest['pending'] + manifest['described']}
    
    orphan_images = [img for img in corpus_images if img not in known_images]
    
    # Add to pending
    for image_path in orphan_images:
        manifest['pending'].append({
            'image_id': generate_image_id(image_path),
            'doc_id': 'orphan',
            'doc_name': os.path.basename(os.path.dirname(image_path)),
            'image_path': image_path,
            'surrounding_text': 'Standalone image (no surrounding text)',
            'status': 'pending'
        })
    
    save_image_manifest(manifest)
    return orphan_images
```

---

## Section 4: Manifest Corruption

### Symptom
- Images were extracted in previous runs
- `describe pending` now returns 0 incorrectly
- Re-running ingest doesn't repopulate

### Diagnosis Commands

**1. Check manifest integrity:**
```powershell
# Inspect pending descriptions manifest
Get-Content .\knowledge_base\pending_descriptions.json | ConvertFrom-Json | ConvertTo-Json -Depth 5
```

**Look for**:
- Empty `pending` array when images exist
- Malformed JSON structure
- Missing required fields (image_id, doc_id, image_path)

**2. Check image files vs. manifest:**
```powershell
# Count images in documents folder
$imageCount = (Get-ChildItem -Path .\knowledge_base\documents\* -Include *.png, *.jpg -Recurse).Count
Write-Host "Images on disk: $imageCount"

# Count pending in manifest
$manifest = Get-Content .\knowledge_base\pending_descriptions.json | ConvertFrom-Json
Write-Host "Pending in manifest: $($manifest.pending.Count)"

# If mismatch, manifest may be corrupt
```

**3. Check for locked files:**
```powershell
# Check if manifest is locked (file handle open)
$manifestPath = ".\knowledge_base\pending_descriptions.json"
try {
    [System.IO.File]::OpenWrite($manifestPath).Close()
    Write-Host "Manifest is writable"
} catch {
    Write-Host "Manifest is LOCKED: $($_.Exception.Message)"
}
```

### Fix Steps

**1. Backup current manifest:**
```powershell
Copy-Item .\knowledge_base\pending_descriptions.json .\knowledge_base\pending_descriptions.backup.json
```

**2. Reset manifest:**
```powershell
# Create empty manifest
@{
    pending = @()
    described = @()
    indexed = @()
} | ConvertTo-Json | Out-File .\knowledge_base\pending_descriptions.json -Encoding utf8
```

**3. Re-run ingestion with force:**
```powershell
.\.venv\Scripts\python.exe -m cli.main ingest --paths .\kts_test_corpus --force
```

**4. Verify repopulation:**
```powershell
.\.venv\Scripts\python.exe -m cli.main describe pending
```

---

## Section 5: Expected Outputs Reference

### Test Corpus Expected Behavior

**Files with Images:**
- `Reference/SOP_ToolX_Login_Failures_v1.docx` — May contain embedded screenshots (TBD based on document content)
- `Reference/images/toolx_auth_401.png` — Standalone image (401 error screenshot)
- `Reference/images/toolx_timeout_dashboard.png` — Standalone image (timeout dashboard)
- `Reference/images/tooly_upload_blocked.png` — Standalone image (upload blocked)
- `Reference/images/toolz_password_policy.png` — Standalone image (password policy)
- `Training/Training_ToolX_Troubleshooting_Pack.pdf` — May contain embedded diagrams
- `Training/Training_ToolY_Upload_Policy.pptx` — May contain embedded screenshots

**Expected `describe pending` Output** (after fixes implemented):
```json
{
  "pending_count": 4,
  "described_count": 0,
  "pending_images": [
    {
      "image_id": "img_001",
      "doc_id": "doc_orphan_001",
      "doc_name": "Reference/images",
      "image_path": "C:/Users/.../kts_test_corpus/Reference/images/toolx_auth_401.png",
      "surrounding_text": "Standalone image (no surrounding text)",
      "status": "pending"
    },
    {
      "image_id": "img_002",
      "doc_id": "doc_orphan_002",
      "doc_name": "Reference/images",
      "image_path": "C:/Users/.../kts_test_corpus/Reference/images/toolx_timeout_dashboard.png",
      "surrounding_text": "Standalone image (no surrounding text)",
      "status": "pending"
    },
    ...
  ]
}
```

---

## Section 6: Testing Image Extraction

### Test Harness

**Create test script** `scripts/test_image_extraction.ps1`:
```powershell
# Test image extraction for each format

Write-Host "Testing DOCX image extraction..." -ForegroundColor Cyan
$testDocx = ".\kts_test_corpus\Reference\SOP_ToolX_Login_Failures_v1.docx"
.\.venv\Scripts\python.exe -m cli.main ingest --paths $testDocx --force
$docId = # ... extract doc_id from output
Get-ChildItem -Path ".\knowledge_base\documents\$docId" -Filter *.png

Write-Host "`nTesting standalone image discovery..." -ForegroundColor Cyan
.\.venv\Scripts\python.exe -m cli.main describe pending
```

### Manual Validation Workflow

1. **Extract sample DOCX manually:**
   - Rename `.docx` to `.zip`
   - Extract `word/media/` folder
   - Count images → compare to extraction output

2. **Verify image metadata:**
   - Open extracted image in viewer
   - Confirm resolution, format, size matches original

3. **Test description workflow:**
   - Pick one pending image
   - Describe it: "Screenshot showing ToolX login error 401 with red error banner and username field highlighted"
   - Complete: `python -m cli.main describe complete <doc_id> --descriptions-file descriptions.json`
   - Search: `python -m cli.main search --query "401 error screenshot"`
   - Verify: Search result includes image_note referencing the image

---

## Section 7: Recommended Implementation Order

1. **Phase 1: Standalone Image Discovery** (easiest, highest visible impact)
   - Implement Option B in Section 3
   - Test with `Reference/images/` folder
   - Validate `describe pending` populates

2. **Phase 2: Markdown Image Reference Parsing** (medium complexity)
   - Update Markdown converter per Section 2
   - Test with any MD files that have `![](image.png)` refs
   - Validate referenced images appear in pending

3. **Phase 3: Embedded DOCX Image Extraction** (higher complexity)
   - Implement DOCX extraction per Section 1
   - Test with `SOP_ToolX_Login_Failures_v1.docx`
   - Validate embedded images saved and added to pending

4. **Phase 4: PDF and PPTX Extraction** (highest complexity)
   - Implement PDF extraction (requires careful page/position tracking)
   - Implement PPTX extraction (requires slide/shape traversal)
   - Test with training materials

5. **Phase 5: End-to-End Validation**
   - Re-run full test suite
   - Validate `describe pending` returns >0 images
   - Complete sample descriptions
   - Validate retrieval includes image notes

---

## Section 8: Exit Criteria for Multi-Modal Pipeline

✅ **Ready for Production** if:
- `describe pending` returns images from all sources (embedded, referenced, standalone)
- Completed descriptions are indexed in vector store
- Retrieval results include `image_note` when relevant
- Image URIs in citations point to actual files
- Re-ingesting same document doesn't create duplicate image entries

❌ **Not Ready** if:
- `describe pending` returns 0 for corpus with images
- Images extracted but not indexed
- Retrieval returns image content without `image_note` citation
- Manifest corruption on re-runs

---

**Document Owner**: Test Lead  
**Last Updated**: 2026-02-14  
**Next Review**: After Phase 1 implementation
