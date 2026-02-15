# Robust Lifecycle & Ingestion Design Note

## 1. Problem Statement
The current system relies on absolute file paths for identity and simple upserts for ingestion. This leads to:
- **Identity Loss**: Renaming a file deletes the old ID and creates a new one, breaking history and relationships.
- **Data Loss Risk**: Transient file lock errors during crawling cause the system to treat files as deleted.
- **Phantom Artifacts**: Shrinking a file leaves "tail chunks" in the vector store from previous longer versions.
- **Incomplete Cleanup**: Deleted files leave orphaned folders and vector data.

## 2. Solution Architecture

### 2.1 Identity Model: Source ID
We introduce `source_id` as the stable identifier for file lineage.
- **Creation**: `source_id` is generated deterministically from the file's initial content hash (SHA-256) or a UUID upon first discovery.
- **Persistence**: The manifest maps `path` -> `doc_id` (which effectively acts as our stable ID in the rest of the system).
- **Rename Handling**: If a new file appears with a hash matching a `deleted` or `missing` file's hash, we treat it as a **MOVE** or **RESTORE** event of the existing `doc_id`, preserving its history.

### 2.2 Manifest Schema Updates (`manifest.json`)
The `files` dictionary will remain keyed by `path` for fast lookups, but the value object will be enriched.

**New Fields**:
- `doc_id`: The stable ID used in vector store/graph (existing).
- `content_hash`: SHA-256 of the file content (existing as `hash`).
- **`status`**: Current state: `active`, `missing`, `error`, `deleted`.
- **`last_seen`**: Timestamp of last successful crawl verification.
- **`retry_count`**: Number of consecutive failures (for grace period).
- **`versions`**: List of historical version snapshots `{version_id, date, hash}`.

### 2.3 Robust Crawler Logic (`CrawlerAgent`)
The crawler lifecycle changes from "Snapshot & Diff" to "Mark & Sweep":

1.  **Mark**:
    *   Iterate all files in source paths.
    *   **Success**: Calculate hash. Update `last_seen`. If hash changed -> `Modified`. If new path -> `New`.
    *   **Locked/Error**: **DO NOT** remove from manifest. Mark status=`error`. Increment `retry_count`.
2.  **Sweep**:
    *   Identify manifest entries not seen in this run.
    *   If `status` was `active`: Mark as `missing` (soft delete). Start grace period timer.
    *   If `status` is `missing` > N runs or > T time: Mark as `deleted`.

### 2.4 Atomic Ingestion & Versioning (`IngestionAgent`)
1.  **Staging**: Ingestion writes to a temp directory (`.staging/{doc_id}`).
2.  **Vector Store Correctness**:
    *   **Delete-Before-Upsert**: Explicitly delete all chunks for `doc_id` before inserting new ones.
    *   *Alt*: Use version-scoped IDs `doc_id_vX_chunk_Y` and clean up old versions.
3.  **Commit**:
    *   Move `.staging` contents to `knowledge_base/documents/{doc_id}` (Atomic rename).
    *   Update `manifest.json`.
4.  **Versioning**:
    *   Keep previous `content.md` as `versions/{version_id}/content.md`.

### 2.5 Garbage Collection (GC)
New `cli/main.py maintenance` command:
1.  **Prune Manifest**: Remove entries marked `deleted` for > X days.
2.  **Prune Vector Store**: Delete chunks for `doc_id`s not in manifest.
3.  **Prune Storage**: Delete folders in `documents/` not in manifest.

## 3. Implementation Phases

### Phase 1: Robust Manifest & Crawler
- Update `FileInfo` model.
- Rewrite `CrawlerAgent` to use Mark & Sweep and handle errors gracefully.
- Implement `migration` to upgrade existing manifest.

### Phase 2: Correctness & Atomicity
- Update `VectorStore` to support `delete_doc_chunks(doc_id)`.
- Update `IngestionAgent` to use staging and atomic commit.

### Phase 3: GC & Maintenance
- Implement `maintenance` CLI.

## 4. Migration Plan
1.  **Backup**: Copy existing `manifest.json` and `knowledge_base`.
2.  **Upgrade**: Run a migration script that adds default fields (`status='active'`, `last_seen=now`, `retry_count=0`) to existing manifest entries.
