# KTS Backend CLI Reference

This documents the commands available in the `kts-backend` executable (or `cli/main.py`).

**Base Command**: `kts-backend` (or `python -m cli.main` if running source)
**Global Flags**: `--help`, `--version`

## 1. Crawl (`crawl`)
Scans source paths and updates the internal manifest (`.kts/manifest.json`). Does NOT modify the source documents.

```bash
kts-backend crawl --paths "C:/Docs" [--dry-run] [--force]
```
- `--paths`: Specify one or more paths to scan. If omitted, uses configured defaults.
- `--dry-run`: Evaluate changes without updating the manifest.
- `--force`: Force update even if file hash matches.

## 2. Ingest (`ingest`)
Converts, extracts images, chunks, and indexes documents found in the manifest (or specified paths).

```bash
kts-backend ingest --paths "C:/Docs"
```
- `--paths`: Explicitly ingest specific files/folders. If omitted, ingests all "pending" files from manifest (files without `doc_id`).
- **Features**: 
  - Extracts embedded images (SHA-256 deduplicated) to `.kts/documents/<doc_id>/images/`.
  - Updates knowledge graph and vector store.
  - Skips `.kts` internal folder automatically.

## 3. Search (`search`)
Retrieves documents relevant to a query.

```bash
kts-backend search "How do I reset my password?"
```
- Returns JSON with `results` array containing `doc_id`, `score`, `chunk_text`, `source_path`.
- Uses hybrid retrieval (embedding similarity + keyword matching).

## 4. Status (`status`)
Reports overall system health and statistics.

```bash
kts-backend status
```
- **Output**: JSON containing:
  - `total_documents`: Count of indexed documents.
  - `total_chunks`: Count of vector chunks.
  - `total_images_pending`: Number of extracted images needing description.
  - `last_crawl`: Timestamp.

## 5. Describe Images (`describe`)
Manages the image description workflow.

### Pending
Lists images extracted but not yet described by AI.
```bash
kts-backend describe pending
```
- Returns JSON list of image paths and associated doc_ids.

### Complete
Submit an AI-generated description for a specific image.
```bash
kts-backend describe complete --image-path "..." --description "..."
```
- Updates `descriptions.json` and adds description to vector store for retrieval.

## 6. Evaluate (`eval`)
Run internal quality suites (dev use only).
```bash
kts-backend eval suite
```
