# Troubleshoot: ToolY — ERR-UPL-013 (File type not allowed)

**Last updated:** 2026-02-14  
**Owner:** KTS Test Corpus Team  
**Applies to:** ToolY Upload workflow

## Symptoms
- Upload fails immediately with: `ERR-UPL-013: File type not allowed: .exe`
- User may be trying to upload a packaged report export.

**Screenshot reference:** `Reference/images/tooly_upload_blocked.png`

## Cause
Upload policy restricts executable and script file types.

## Resolution
1. Confirm the file extension is allowed: `.csv .xlsx .pdf`
2. If user has a zipped export, **extract** and upload only the report file.
3. If extension is blocked but business‑required, request policy change:
   - Provide: business justification, file type, retention need, malware scanning approach.

## Validation
- Upload succeeds and appears in **Recent uploads** list.
- User can open preview.

