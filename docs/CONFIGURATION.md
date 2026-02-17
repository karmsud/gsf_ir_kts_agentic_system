# KTS Configuration Guide

**Source of Truth**: `config/settings.py`  
**Last Updated**: 2026-02-15 (v1.2.0)

## 1. Environment Variables

The backend uses a single primary environment variable to control data location:

| Variable | Description | Default |
|----------|-------------|---------|
| `KTS_KB_PATH` | Path where the knowledge base folder is stored. | `.kts` in source folder root |

If `KTS_KB_PATH` is not set, the system defaults to `.kts/` relative to the source folder.

## 2. Supported File Formats

The backend uses specific Python libraries to parse these formats.

| Extension | Library | Tier A2 (Full) | Tier A3 (Light) |
|-----------|---------|----------------|-----------------|
| `.docx` | `python-docx` | ✅ | ✅ |
| `.pdf` | `PyMuPDF` | ✅ | ❌ |
| `.pptx` | `python-pptx` | ✅ | ❌ |
| `.html` | `beautifulsoup4` | ✅ | ✅ |
| `.md` | Built-in | ✅ | ✅ |
| `.txt` | Built-in | ✅ | ✅ |
| `.json` | Built-in | ✅ | ✅ |
| `.yaml` | `PyYAML` | ✅ | ✅ |
| `.ini` | Built-in | ✅ | ✅ |
| `.csv` | Built-in | ✅ | ✅ |
| `.png` | Built-in (as raw file) | ✅ | ✅ |

**Note**: Tier A3 builds exclude `PyMuPDF` and `python-pptx` to reduce executable size by ~60%. Attempting to ingest PDF/PPTX in A3 will result in a graceful skip or error log.

## 3. Extension Settings (VS Code)

Once installed, the KTS extension contributes the following settings (`.vscode/settings.json`):

- `kts.kbPath`: Overrides `KTS_KB_PATH`.
- `kts.logLevel`: Controls verbosity (`info`, `debug`, `error`).
- `kts.search.maxResults`: Limit number of search results (default: 5).
- `kts.crawl.auto`: Boolean to enable auto-crawl on folder open.

---

## 4. Knowledge Base Artifact Structure

**Version**: v1.2.0 (February 2026)

The knowledge base folder contains all indexed data. By default, it's located at `.kts/` inside the source folder (overrideable via `KTS_KB_PATH`).

### 4.1 Directory Layout

```
.kts/
├── manifest.json                    # Index of all ingested documents
├── documents/                       # Per-document storage
│   └── doc_<hash>/                  # One folder per document (SHA-256 hash of path)
│       ├── content.md               # Extracted text in Markdown format
│       ├── metadata.json            # Title, doc_type, keywords, timestamps
│       ├── descriptions.json        # AI-generated image descriptions (keyed by image hash)
│       └── images/                  # Embedded images (extracted from DOCX/PDF/PPTX)
│           ├── <hash>.png           # Content-addressed (SHA-256)
│           └── <hash>.jpg
├── vectors/
│   └── chroma/                      # ChromaDB persistent storage
│       ├── chroma.sqlite3           # SQLite index of embeddings
│       ├── *.parquet                # Compressed vector data
│       └── chroma.json              # Collection metadata
├── graph/
│   └── knowledge_graph.json         # NetworkX graph (JSON node-link format)
└── staging/                         # Temporary workspace during ingestion
    └── <doc_id>/                    # Deleted after atomic move to documents/
```

### 4.2 Artifact Descriptions

| File/Folder | Purpose | Format | Size (typical) |
|---|---|---|---|
| `manifest.json` | Master index of all documents (path, hash, last_modified) | JSON | ~1KB per 100 docs |
| `documents/<doc_id>/content.md` | Extracted text with Markdown formatting | Markdown | ~50% of source file |
| `documents/<doc_id>/metadata.json` | Title, doc_type, keywords, created/modified timestamps | JSON | ~1KB |
| `documents/<doc_id>/descriptions.json` | AI-generated image descriptions (for RAG) | JSON | ~500 bytes per image |
| `documents/<doc_id>/images/` | Extracted images from DOCX/PDF/PPTX | PNG/JPG | ~30% of source file |
| `vectors/chroma/` | Semantic embedding database | SQLite + Parquet | ~30% of text content |
| `graph/knowledge_graph.json` | NetworkX graph linking docs, terms, topics | JSON | ~20% of text content |

### 4.3 Content-Addressable Storage

**Images**: Deduplicated by SHA-256 content hash. If the same image appears in 5 documents, only 1 copy is stored.

**Documents**: Identified by SHA-256 hash of source file path. Ensures stable IDs even if title changes.

### 4.4 Atomic Ingestion

**Process**:
1. Write to `staging/<doc_id>/` (temporary)
2. Convert document, extract images, generate metadata
3. **Atomic move**: `staging/<doc_id>/ → documents/<doc_id>/`
4. Delete `staging/<doc_id>/`

**Guarantee**: No partial writes visible to search queries. Either document is fully indexed or not present.

---

## 5. ChromaDB Configuration

**Version**: v1.2.0 (February 2026)  
**Location**: `backend/vector/store.py`

### 5.1 Embedding Model

| Parameter | Value | Notes |
|---|---|---|
| **Model** | `all-MiniLM-L6-v2` | Sentence-BERT base model |
| **Dimensions** | 384 | Lower than BERT-base (768) for speed |
| **Format** | ONNX | Optimized for CPU-only inference |
| **Size** | 23 MB | Auto-downloaded on first use |
| **Performance** | ~1000 embeds/sec | On modern CPU (Intel i7/AMD Ryzen) |
| **Accuracy** | ~80% of full model | Acceptable for local deployment |

**Model Location**: `~/.cache/torch/sentence_transformers/` (auto-managed)

### 5.2 Collection Schema

**Collection Name**: `knowledge_chunks`  
**Distance Metric**: Cosine distance (L2 normalized)

**Metadata Schema**:
```json
{
  "doc_id": "doc_<hash>",        // Source document
  "title": "Document Title",     // For boosting
  "doc_type": "POLICY",          // For filtering
  "keywords": "term1,term2",     // For feature scoring
  "chunk_index": 0,              // Position in document
  "created_at": "2026-02-15T14:32:00"
}
```

**Filtering**: Supports `where` clauses for `doc_type`, `doc_id`

Example:
```python
results = collection.query(
    query_embeddings=[vector],
    n_results=20,
    where={"doc_type": "POLICY"}  # Only return POLICY documents
)
```

### 5.3 Performance Tuning

**Disk Usage**:
- SQLite: ~10% of text content
- Parquet (vectors): ~20% of text content
- **Total**: ~30% overhead

**Query Latency** (for 10,000 chunks):
- Cold query (first after restart): ~200ms (model loading)
- Warm query: ~80ms (pure vector search)

**RAM Usage**:
- Baseline: ~200MB (ChromaDB + ONNX runtime)
- Per 1,000 chunks: +1MB (in-memory index)
- **Example**: 10,000 chunks → ~210MB RAM

### 5.4 Advanced Settings (`config/settings.py`)

```python
# Chunk size for semantic splitting
CHUNK_SIZE = 1000          # Target chars per chunk
CHUNK_OVERLAP = 200        # Sliding window overlap

# Vector search parameters
VECTOR_TOP_K = 20          # Candidates before re-ranking
VECTOR_SIMILARITY_THRESHOLD = 0.5  # Min similarity (0-1)

# ChromaDB persistence
CHROMA_PERSIST_PATH = os.path.join(KB_PATH, "vectors", "chroma")
```

**Tuning Guidelines**:
- **Increase `CHUNK_SIZE`** → fewer, longer chunks → better context, but slower search
- **Increase `CHUNK_OVERLAP`** → more context continuity, but more storage
- **Increase `VECTOR_TOP_K`** → better recall, but slower re-ranking

---

## 6. Knowledge Graph Configuration

**Version**: v1.2.0 (February 2026)  
**Location**: `backend/graph/`

### 6.1 Graph Schema

**Node Types**:
- `DOCUMENT`: Source documents (e.g., `doc:9317868`)
- `TERM`: Defined terms (e.g., `term:servicer`)
- `TOPIC`: Concept clusters (e.g., `topic:pooling_agreements`)
- `TOOL`: Software systems (e.g., `tool:BatchBridge`)
- `ERROR_CODE`: Error identifiers (e.g., `error:E7042`)

**Edge Types**:
- `DEFINES`: Document defines a term
- `MENTIONS`: Document mentions a topic
- `COVERS`: Document covers a tool
- `ADDRESSES`: Document addresses an error code

### 6.2 Graph Build Settings (`config/settings.py`)

```python
# Term extraction patterns
TERM_PATTERN = r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b'  # "Master Servicer"
ERROR_CODE_PATTERN = r'\b[A-Z]\d{4,}\b'               # "E7042"

# Topic modeling (TF-IDF)
MAX_TOPICS = 100          # Max topics per document
MIN_TOPIC_FREQUENCY = 3   # Min occurrences to be a topic

# Graph boost parameters
GRAPH_BOOST_CAP = 0.5     # Max additive boost (50%)
GRAPH_BOOST_FACTOR = 0.01 # Boost per connection
```

### 6.3 Graph Persistence

**Format**: JSON node-link (NetworkX native)

**Serialization**:
```python
import networkx as nx
from networkx.readwrite import json_graph

# Save
data = json_graph.node_link_data(G)
with open("knowledge_graph.json", "w") as f:
    json.dump(data, f, indent=2)

# Load
with open("knowledge_graph.json") as f:
    data = json.load(f)
G = json_graph.node_link_graph(data)
```

**Advantages**:
- Human-readable (can inspect in text editor)
- Git-friendly (line-by-line diffs show changes)
- Zero-copy deserialization (NetworkX optimized)

### 6.4 Graph Query Performance

| Operation | Complexity | Latency (10k nodes) |
|---|---|---|
| **Get neighbors** | O(1) | <1ms |
| **Multi-hop traversal** (2 hops) | O(k²) where k=avg degree | ~10ms |
| **Shortest path** | O(n + m) | ~50ms |
| **Degree centrality** | O(n) | ~30ms |

**Tip**: For large graphs (>50k nodes), consider precomputing centrality and storing in node attributes.

---

## 7. RAG Fusion Configuration

**Version**: v1.2.0 (February 2026)  
**Location**: `backend/agents/retrieval_service.py`

### 7.1 Scoring Parameters

**Formula**: `FinalScore = VectorScore × (1 + GraphBoost) × FeatureBoosts`

**Settings** (`config/settings.py`):

```python
# Feature boost multipliers
FEATURE_BOOSTS = {
    "error_code_match": 2.0,      # Exact error code in query
    "intent_doc_type_match": 1.7, # Query intent matches doc_type
    "title_term_match": 1.3,      # Query term in document title
    "keyword_density_high": 1.2,  # High frequency of query terms
    "keyword_density_low": 1.0,   # Low frequency (no boost)
}

# Graph boost
GRAPH_BOOST_CAP = 0.5             # Max additive boost
GRAPH_BOOST_FACTOR = 0.01         # Boost per graph connection

# Deduplication
DEDUPLICATE_BY_DOC_ID = True      # Keep only top chunk per document
```

### 7.2 Intent Detection Patterns

**File**: `retrieval_service.py::_detect_intent()`

**Patterns** (regex):
```python
INTENT_PATTERNS = {
    "reference": [r"\bwhat is\b", r"\bdefinition\b", r"\bglossary\b"],
    "policy": [r"\bpolicy\b", r"\bguideline\b", r"\bstandard\b"],
    "sop": [r"\bprocedure\b", r"\bworkflow\b", r"\bhow to\b"],
    "guide": [r"\btutorial\b", r"\blearning\b", r"\bonboarding\b"],
}
```

**Effect**: If query matches pattern → boost docs with matching `doc_type` by 1.7×.

### 7.3 Tuning for Precision vs. Recall

**Increase Precision** (fewer, more relevant results):
- Lower `VECTOR_TOP_K` (e.g., 10 instead of 20)
- Increase `VECTOR_SIMILARITY_THRESHOLD` (e.g., 0.7 instead of 0.5)
- Increase feature boosts (error_code_match → 3.0)

**Increase Recall** (more results, some less relevant):
- Increase `VECTOR_TOP_K` (e.g., 50)
- Lower `VECTOR_SIMILARITY_THRESHOLD` (e.g., 0.3)
- Lower graph boost cap (prioritize semantic over connectivity)

---

## 8. Logging & Debugging

### 8.1 Log Levels

Set via environment variable or VS Code setting:

```powershell
# PowerShell
$env:KTS_LOG_LEVEL = "DEBUG"

# Or in .vscode/settings.json
{
  "kts.logLevel": "debug"
}
```

**Levels**:
- `ERROR`: Only critical failures
- `INFO` (default): Ingestion progress, search summaries
- `DEBUG`: Detailed scoring, graph queries, vector results

### 8.2 Log Output

**Backend**: stdout/stderr (captured by VS Code extension)

**Extension**: VS Code Output panel → "KTS Backend" channel

**File Logging** (optional):
```python
# config/settings.py
LOG_FILE = os.path.join(KB_PATH, "kts.log")
```

### 8.3 Debugging Search Quality

**Enable verbose mode**:
```powershell
python -m cli.main search --query "test query" --verbose
```

**Output includes**:
- Vector search candidates (top-20)
- Graph boost per document
- Feature boost breakdown
- Final scores after RAG fusion
- Deduplication report

**Example**:
```
[DEBUG] Vector search: 20 results, scores: [0.87, 0.82, 0.79, ...]
[DEBUG] Graph boost: doc_001 (+0.3), doc_002 (+0.1)
[DEBUG] Feature boost: doc_001 (title_match: 1.3×), doc_002 (no boost)
[DEBUG] Final scores: [1.44, 0.99, ...]
[DEBUG] Dedup: removed 3 duplicate doc_ids
[INFO] Returning top 5 results
```

---

## 9. Performance Optimization

### 9.1 Hardware Recommendations

**Minimum**:
- CPU: 2 cores, 2.0 GHz
- RAM: 4 GB
- Disk: HDD (acceptable but slow)

**Recommended**:
- CPU: 4+ cores, 3.0 GHz
- RAM: 8 GB
- Disk: SSD (5× faster ingestion)

**Large Corpora** (10,000+ documents):
- CPU: 8+ cores
- RAM: 16 GB
- Disk: NVMe SSD

### 9.2 Ingestion Performance

**Tips**:
1. **Use local disk**: Avoid network drives (SQLite locking issues)
2. **Close source files**: Locked files cause permission errors
3. **Batch ingestion**: Ingest 100 docs at a time (not 1 by 1)

**Expected Throughput** (modern laptop):
- DOCX: ~10 docs/sec
- PDF: ~5 docs/sec (PyMuPDF)
- PPTX: ~3 docs/sec

### 9.3 Search Performance

**Query Latency Breakdown** (10,000 chunks):
- **Cold start** (first query): ~250ms (model loading)
- **Warm query**: ~100ms
  - Vector search: 60ms (60%)
  - Graph queries: 20ms (20%)
  - Feature scoring: 10ms (10%)
  - Re-ranking: 10ms (10%)

**Optimization**:
- **Pre-warm embeddings**: Run dummy query on startup
- **Cache graph centrality**: Compute once, store in node attributes
- **Limit top-k**: Fetch only 10 candidates (not 20) if precision > recall

---

## 10. Security & Privacy

### 10.1 Data Isolation

✅ **All data local**: No cloud uploads, no network calls  
✅ **No telemetry**: Microsoft doesn't collect query logs  
✅ **No credentials**: Backend has no auth/API keys  
✅ **Process isolation**: Backend runs in separate process (can't access VS Code state)

### 10.2 File Access

**Backend can read**:
- Source documents (user-specified paths)
- Knowledge base folder (`KTS_KB_PATH`)

**Backend CANNOT read**:
- VS Code settings (except passed via IPC)
- User's home directory (unless `KTS_KB_PATH` set there)
- Network drives (unless user explicitly ingests from them)

### 10.3 Input Sanitization

**Queries**: Limited to 500 chars, SQL injection patterns removed  
**File paths**: Validated to prevent `../../../etc/passwd` traversal  
**Metadata**: JSON-escaped to prevent code injection

---

## 11. Migration from v1.0.x to v1.2.0

### 11.1 Breaking Changes

⚠️ **Knowledge base format changed**: v1.2.0 now uses `.kts/` inside the source folder (source-folder-scoped)

**Action Required**: Re-ingest corpus

```powershell
# Backup old KB (if upgrading from v1.0.x)
Copy-Item -Path ".kts" -Destination ".kts_backup" -Recurse

# Re-ingest with v1.2.0
python -m cli.main ingest --paths "C:\SourceDocs"
```

### 11.2 New Dependencies

**A2 and A3 tiers now require**:
- `chromadb>=0.4.0` (was optional, now mandatory)
- `onnxruntime>=1.14.0` (was missing, now required)
- `networkx>=3.0.0` (was dead code, now active)

**Reinstall**:
```powershell
# A2
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# A3
.\.venv_a3\Scripts\Activate.ps1
pip install -r requirements_a3.txt
```

---

**See Also**:
- [Recent Updates](RECENT_UPDATES.md) — Changelog
- [Architecture](ARCHITECTURE.md) — System design
- [Build Guide](BUILD_GUIDE.md) — Creating installers
- [User Guide](USER_GUIDE.md) — End-user documentation
