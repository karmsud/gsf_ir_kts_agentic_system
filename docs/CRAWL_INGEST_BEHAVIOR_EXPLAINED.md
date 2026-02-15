# Crawl & Ingest Behavior Explanation

This document explains exactly how the system handles file lifecycle events (New, Modified, Deleted) based on the current codebase logic.

## 1. The Crawler (`backend/agents/crawler_agent.py`)

The Crawler is responsible for scanning the file system and maintaining the state of truth in `knowledge_base/manifest.json`.

### Identity & Detection
- **Identity**: A file is identified solely by its **absolute file path**.
- **Change Detection**: The crawler computes a SHA-256 hash of the file content.
    - **New File**: The path is not present in `manifest.json`.
    - **Modified File**: The path exists in `manifest.json`, but the computed SHA-256 hash differs from the stored hash.
    - **Unchanged File**: The path exists and the hash matches.

### Manifest Updates
1. **New Files**: Added to the manifest. The `doc_id` is naturally `None` initially.
2. **Modified Files**: The system updates the `hash`, `size`, and `last_modified` fields in the manifest. **Crucially, the existing `doc_id` is preserved.** This ensures that a modified file keeps its identity in the Knowledge Graph and Vector Store.
3. **Deleted Files**: If a file path in the manifest no longer exists on disk, it is removed from the manifest.

---

## 2. Ingestion Process (`backend/agents/ingestion_agent.py`)

The Ingestion Agent processes files to generate embeddings, chunks, and metadata.

### ID Generation
- If the file is **New** (no `doc_id` in manifest), the agent generates a deterministic ID based on the file path hash:
  ```python
  doc_id = f"doc_{abs(hash(str(source_path))) % 10_000_000:07d}"
  ```
- If the file is **Modified**, the existing `doc_id` from the manifest is reused. `backend/agents/ingestion_agent.py` accepts `doc_id` as an input parameter.

### File Processing logic
1. **Content Conversion**: The file is read and converted to Markdown (supporting PDF, DOCX, HTML, JSON, etc.).
2. **Storage**:
   - `knowledge_base/documents/{doc_id}/content.md`: **Overwritten** with new content.
   - `knowledge_base/documents/{doc_id}/metadata.json`: **Overwritten** with new metadata (including updated `modified_at` timestamp).

### Vector Store Updates (`backend/vector/store.py`)
the system uses a naive "Upsert" strategy for chunks:
- **Chunking Strategy**: Text is split into chunks. IDs are generated as: `{doc_id}_chunk_{index}` (e.g., `doc_123_chunk_0`, `doc_123_chunk_1`).
- **Upsert Failure Mode (Shrinking Files)**:
    - The system updates existing chunks by ID (`upsert_chunks`).
    - **Warning**: If a file *shrinks* (e.g., goes from 10 chunks to 5), the system updates chunks 0-4. **Chunks 5-9 remain in the vector store.** These remaining chunks are now "phantom" chunks that still point to the `doc_id` but reference content that no longer exists in `content.md`.
    - This means searching for deleted content might still return results pointing to the document.

## 3. Rename & Move Semantics

Since the system uses **absolute file path** as the unique identity key, renaming or moving a file is treated as two separate events:
1.  **Delete Event**: The old path is removed from the manifest.
2.  **New Event**: The new path is added as a brand new file.

**Consequences**:
- **ID Change**: The `doc_id` will change. The old ID is discarded, and a new one is generated.
- **Metadata Loss**: Any manual tags, categories, or `doc_type` assignments on the old `doc_id` are lost.
- **Vector Chunks**: The chunks associated with the old `doc_id` become orphaned in the vector store (unless garbage collection is run). The new file generates a fresh set of chunks.

## 4. Partial Copy / Locked File Handling

The Crawler attempts to read every file found in the scan path. If a file is locked, has permission issues, or triggers an I/O error:
- **Immediate Result**: The crawler catches the exception and logs an error in the `changes.errors` list.
- **Manifest Impact (Critical Risk)**: Because the file is not successfully read, it is **excluded from the `current` file list**.
    - The comparison logic sees the file is in `known` (manifest) but missing from `current`.
    - **Result**: The system treats the locked file as **DELETED**.
- **Recovery**: The next time the crawler runs and successfully reads the file, it will be treated as a **NEW** file (new `doc_id`).

## 5. Garbage Collection & Cleanup

The system currently **DOES NOT** perform automatic garbage collection.

### Orphaned Data Types
1.  **Orphaned Vector Chunks**:
    - **Cause**: Deleting a file or shrinking a file.
    - **Status**: Chunks remain in `backend/vector/store.py` (or ChromaDB) indefinitely.
2.  **Orphaned Document Folders**:
    - **Cause**: Deleting a file from the source.
    - **Status**: The folder `knowledge_base/documents/{old_doc_id}` remains on disk.

### Operational Cleanup Checklist
Maintainers should periodically run cleanup scripts (currently manual or custom scripts required):
- [ ] **Scan Vector Store for Orphaned IDs**: Identify chunk IDs where the prefix `doc_id` does not exist in `manifest.json`. Delete them.
- [ ] **Prune Document Folders**: Identify folders in `knowledge_base/documents/` whose names are not present in `manifest.json`. Archive or delete them.

## 6. Operational Best Practices

### Updating Existing Docs
- **Method**: Edit the file in place. Do not change the filename or path.
- **Result**: `doc_id` is preserved. History and metadata are maintained.

### Adding New Docs
- **Method**: Add the file to the source directory.
- **Result**: New `doc_id` generated.

### Renaming/Moving Docs
- **Recommendation**: **Avoid** renaming active documents if continuity is important.
- **Workaround (If Rename is Necessary)**:
    1.  Accept that it will be treated as a new document.
    2.  Manually re-apply any tags or metadata to the new `doc_id` after ingestion.

### Verifying Ingestion
1.  Run `python cli/main.py crawl` to update the manifest.
2.  Run `python cli/main.py ingest` to process the changes.
3.  Check `knowledge_base/manifest.json` to confirm the file has a valid `doc_id`.
4.  Check `knowledge_base/documents/{doc_id}/content.md` to verify content extraction.

## Summary Table

| Scenario | Manifest Action | Doc ID | Vector Store | Knowledge Base Files |
| :--- | :--- | :--- | :--- | :--- |
| **New File** | Added, `doc_id=null` | Generated from Path | All chunks added | Created |
| **Modified File** | Hash Updated | **Preserved** | Overwrites aligned chunks (0..N). **Does NOT delete tail chunks if file shrinks.** | `content.md` Overwritten |
| **Deleted File** | Removed | Lost | **Orphaned** (Chunks remain in vector store unless explicit cleanup runs) | Files remain in `documents/` |
| **Renamed File** | Delete Old + Add New | **New ID** | Old chunks orphaned; New chunks created | Old folder orphaned; New created |
| **Locked/Error** | **Removed** (Treated as Deleted) | Lost | **Orphaned** | Files remain in `documents/` |

> **Note**: The current system does not automatically garbage collect "orphaned" vector chunks or `documents/{doc_id}` folders when a file is deleted from the source or the manifest.

## Appendix: Traceability Matrix

| Feature | Behavior | Source Code Reference |
| :--- | :--- | :--- |
| **Identity** | Path-based identity | `backend/agents/crawler_agent.py` (Line 41: `current[info.path] = info`) |
| **Change Detection** | SHA-256 Hash | `backend/agents/crawler_agent.py` (Line 39: `hash=sha256_file(file_path)`) |
| **Rename=Delete+New** | No move logic | `backend/agents/crawler_agent.py` (Lines 51-60: explicit `new_files` / `deleted_files` lists) |
| **Locked=Deleted** | Exception handling causes exclusion | `backend/agents/crawler_agent.py` (Lines 32-48: `try/except` block and `if known_path not in current`) |
| **Shrinking Files** | Tail chunks persist | `backend/vector/store.py` (Method `upsert_chunks`: updates by ID, no delete-before-insert) |
| **Ingesiton Overwrites** | Content replacement | `backend/agents/ingestion_agent.py` (Line 72: `content_path.write_text(...)`) |
