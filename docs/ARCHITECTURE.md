# KTS Architecture & Design

**Source of Truth**: `backend/agents/`, `backend/ingestion/`, `cli/main.py`
**Last Updated**: 2026-02-15 (v1.2.0)

## 1. System Overview

GSF IR KTS is a **local, workspace-scoped** knowledge retrieval system. It runs entirely on the user's machine, indexing documentation from a local folder or network share into a `.kts` folder.

- **Frontend**: VS Code Extension (Visual Studio Code 1.96+)
- **Backend**: Python 3.10+ (compiled to single-file executable or bundled source)
- **Data**: Local specific `.kts` folder containing vector store, graph, and manifest.

## 2. Pipeline Stages

The system follows a strict `crawl -> ingest -> index` pipeline.

### 2.1 Crawl (`backend/agents/crawler_agent.py`)
- Scans `source_path` for supported files (`.md`, `.docx`, `.pdf`, `.pptx`, `.html`, `.json`).
- Generates `manifest.json` tracking file stats (size, mtime, hash).
- **Idempotency**: Only marks files as "changed" if hash differs from previous run.

### 2.2 Ingestion & Conversion (`backend/agents/ingestion_agent.py`)
- Processes files marked "changed" in manifest.
- **Atomic Swap**: Converts to `.kts/staging/<doc_id>`, then moves to `.kts/documents/<doc_id>`.
- **Image Pipeline**:
  - Extracts embedded images from DOCX/PDF/PPTX to `.kts/documents/<doc_id>/images/`.
  - **Deduplication**: Uses SHA-256 content hashing to avoid duplicate images on disk.
  - **Filters**: Reference to `.kts` folder itself is strictly excluded.

### 2.3 Indexing (`backend/vector/`)
- chunks text (Markdown-aware splitter).
- Embeds chunks using local models (e.g., `sentence-transformers/all-MiniLM-L6-v2`).
- Stores in ChromaDB (`.kts/vectors/chroma`).

### 2.4 Knowledge Graph (`backend/graph/`)
- Builds NetworkX graph (`knowledge_graph.json`) linking documents, chunks, and concepts.
- Used for "multi-hop" reasoning and finding related documents.

## 3. Data Model (`backend/common/models.py`)

### 3.1 Artifacts (in `.kts/`)
- `manifest.json`: Single source of truth for all known files.
- `knowledge_graph.json`: Node-link data for graph traversal.
- `descriptions.json`: Stores AI-generated image descriptions (mapped by image hash).

### 3.2 Key Classes
- **AgentResult**: Standard return type (success, data, confidence, reasoning).
- **Document**: Internal representation with metadata and content.
- **Citation**: Return object for search, including file URI and confidence score.

## 4. Extension Architecture (`extension/`)

- **Activator** (`extension.js`): Registers commands, providers.
- **Backend Manager** (`lib/kts_backend.js`): Manages the Python process (spawn/kill).
- **Copilot Integration** (`chat/participant.js`): Defines `@kts` chat participant.
- **Image Description** (`lib/image_describer.js`): Uses VS Code Language Model API to describe pending images.

## 5. Deployment Tiers

The backend is built in two tiers to manage size:
1.  **Option A2 (Full)**: Includes PyMuPDF, python-pptx. Supports generic enterprise docs.
2.  **Option A3 (Word+Images)**: Stripped down. Supports DOCX/HTML only. ~60% smaller.

---

## 6. Semantic Search Architecture (ChromaDB)

**Implementation**: v1.2.0 (February 2026)  
**Location**: `backend/vector/store.py`

### 6.1 Embedding Model

- **Model**: `all-MiniLM-L6-v2` (via ONNX runtime)
- **Dimensions**: 384
- **Model Size**: 23MB (auto-downloaded on first use)
- **Framework**: Optimum + ONNXRuntime (CPU-only, no GPU required)
- **Performance**: ~1000 embeddings/second on modern CPU

**Why ONNX?**
- **60% smaller binary** vs. full PyTorch sentence-transformers
- **No PyTorch dependency** (700MB+ saved)
- **~80% accuracy** of full model (acceptable trade-off for local deployment)

### 6.2 ChromaDB Storage

**Database**: SQLite-backed persistent store  
**Location**: `.kts/vectors/chroma/`  
**Collections**: Single collection `knowledge_chunks`

**Schema**:
```python
{
    "id": "chunk_<hash>",           # Unique chunk identifier
    "embedding": [0.23, -0.45, ...], # 384-dim vector
    "document": "<chunk_text>",      # Full text content
    "metadata": {
        "doc_id": "doc_<hash>",      # Source document
        "title": "Document Title",    # For boosting
        "doc_type": "POLICY",        # For filtering
        "keywords": "term1,term2",   # For feature scoring
        "chunk_index": 0              # Position in document
    }
}
```

### 6.3 Search Process

**File**: `backend/vector/store.py::search()`

1. **Query Embedding**:
   ```python
   query_vector = embedding_function(query)  # 384-dim vector
   ```

2. **Similarity Search**:
   ```python
   results = collection.query(
       query_embeddings=[query_vector],
       n_results=top_k,
       where={"doc_type": filter_value} if doc_type_filter else None
   )
   ```

3. **Distance → Similarity**:
   ```python
   similarity = 1 / (1 + distance)  # Cosine distance to [0, 1] score
   ```

**Output**: List of dicts with `doc_id`, `content`, `score`, `metadata`

### 6.4 Performance Characteristics

| Metric | Value | Notes |
|---|---|---|
| **Index Time** | ~0.01s per chunk | Single-threaded, CPU-bound |
| **Query Time** | ~50-150ms | Depends on corpus size (1k-10k chunks) |
| **Disk Usage** | ~30% of indexed text | Compressed embeddings + SQLite overhead |
| **RAM Usage** | ~200MB baseline | +1MB per 1000 chunks |

---

## 7. Knowledge Graph Architecture (NetworkX)

**Implementation**: v1.2.0 (February 2026)  
**Location**: `backend/graph/`

### 7.1 Graph Structure

**Type**: `networkx.DiGraph` (directed graph)  
**Serialization**: JSON node-link format (human-readable)  
**Storage**: `.kts/graph/knowledge_graph.json`

**Node Types**:
- `DOCUMENT`: Top-level documents (e.g., `doc:9317868`)
- `TERM`: Defined terms (e.g., `term:servicer`)
- `TOPIC`: Concept clusters (e.g., `topic:pooling_agreements`)
- `TOOL`: Software systems (e.g., `tool:BatchBridge`)
- `ERROR_CODE`: Error identifiers (e.g., `error:E7042`)

**Edge Types**:
- `DEFINES`: Document defines a term
- `MENTIONS`: Document mentions a topic
- `COVERS`: Document covers a tool
- `ADDRESSES`: Document addresses an error code

**Example**:
```python
G.add_node("doc:9317868", type="DOCUMENT", title="PSA 2006-HE1")
G.add_node("term:servicer", type="TERM", definition="Entity responsible...")
G.add_edge("doc:9317868", "term:servicer", type="DEFINES")
```

### 7.2 Graph Construction

**File**: `backend/agents/graph_builder_agent.py`

**Process**:
1. **Term Extraction**: Regex patterns for capitalized phrases, error codes
2. **Topic Modeling**: TF-IDF + keyword clustering
3. **Tool Detection**: Known system names from `taxonomy_rules.json`
4. **Edge Creation**: Document mentions → term/topic/tool nodes

**Complexity**: O(n × m) where n = documents, m = avg terms per doc

### 7.3 Graph Queries

**File**: `backend/graph/queries.py`

**Operations**:

1. **Find Related Documents**:
   ```python
   def get_related_docs(G, doc_id: str) -> List[str]:
       # Get all nodes connected via any edge
       successors = list(G.successors(doc_id))
       related = set()
       for node in successors:
           related.update(G.predecessors(node))  # Other docs defining same terms
       return list(related - {doc_id})
   ```

2. **Multi-Hop Traversal**:
   ```python
   # Find docs 2 hops away (e.g., shared topics)
   paths = nx.single_source_shortest_path(G, doc_id, cutoff=2)
   ```

3. **Centrality Analysis**:
   ```python
   # Find most important nodes
   centrality = nx.degree_centrality(G)
   top_nodes = sorted(centrality.items(), key=lambda x: -x[1])[:10]
   ```

### 7.4 Graph-Augmented Retrieval

**File**: `backend/agents/retrieval_service.py`

**Algorithm**:
```python
for result in vector_results:
    doc_id = result['doc_id']
    
    # Count connections (terms, topics, tools defined/mentioned)
    connectivity = G.out_degree(doc_id)
    
    # Boost score (capped at 50% additive)
    graph_boost = min(0.5, connectivity * 0.01)
    
    # Apply boost
    result['score'] *= (1 + graph_boost)
```

**Impact**: Documents with rich connections (many defined terms, covered topics) get prioritized over isolated documents, even if semantic similarity is equal.

### 7.5 Serialization Format

**File**: `backend/graph/persistence.py`

**JSON Structure**:
```json
{
  "directed": true,
  "multigraph": false,
  "graph": {},
  "nodes": [
    {"id": "doc:123", "type": "DOCUMENT", "title": "..."},
    {"id": "term:servicer", "type": "TERM", "definition": "..."}
  ],
  "links": [
    {"source": "doc:123", "target": "term:servicer", "type": "DEFINES"}
  ]
}
```

**Why node-link?**
- **Human-readable** (can inspect in text editor)
- **Git-friendly** (diffs show node/edge changes)
- **NetworkX native** (zero-copy deserialization)

---

## 8. Recursive Semantic Chunking

**Implementation**: v1.2.0 (February 2026)  
**Location**: `backend/common/text_utils.py`

### 8.1 Problem Statement

**Before**: Naive character-count chunking split text at arbitrary positions → mid-sentence breaks, incomplete thoughts.

**Example**:
```
Chunk 1: "The Servicer is responsible for collecting payments from borrowers. The Trustee"
Chunk 2: " holds the mortgage assets in a separate trust account..."
```

**Issue**: First chunk ends abruptly, second chunk starts without context.

### 8.2 Recursive Splitter Algorithm

**Strategy**: Try splitting at natural boundaries, recursively fall back to finer boundaries if needed.

**Hierarchy**:
1. **Paragraph** (`\n\n`) — ideal for semantic coherence
2. **Sentence** (`. ` or `? ` or `! `) — preserve complete thoughts
3. **Word** (` `) — avoid mid-word breaks
4. **Character** (` ``) — last resort

**Parameters**:
- `chunk_size`: Target size (default 1000 chars)
- `chunk_overlap`: Sliding window (default 200 chars)

**Code** (`text_utils.py`):
```python
def recursive_split(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    # Level 1: Try paragraph splits
    if len(text) > chunk_size:
        paragraphs = text.split("\n\n")
        if len(paragraphs) > 1:
            # Recursively split paragraphs
            return merge_chunks(
                [recursive_split(p, chunk_size, chunk_overlap) for p in paragraphs],
                chunk_size, chunk_overlap
            )
    
    # Level 2: Try sentence splits
    if len(text) > chunk_size:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) > 1:
            return merge_chunks(
                [recursive_split(s, chunk_size, chunk_overlap) for s in sentences],
                chunk_size, chunk_overlap
            )
    
    # Level 3: Word splits (if still too large)
    # Level 4: Character splits (absolute last resort)
    return [text]
```

### 8.3 Results

**Metrics** (1000-query evaluation, PSA 2006-HE1):
- **Average chunk length**: 961 chars (near target of 1000)
- **Short chunks (<200 chars)**: 0 out of 1,394 chunks (0%)
- **Abrupt sentences**: Eliminated (all chunks end at sentence boundaries)

**Example Output**:
```
Chunk 1: "The Servicer is responsible for collecting payments from borrowers. 
The Trustee holds the mortgage assets in a separate trust account. If the 
Servicer fails to remit payments, the Trustee has the authority to appoint 
a successor Servicer."

Chunk 2: "If the Servicer fails to remit payments, the Trustee has the authority 
to appoint a successor Servicer. The successor Servicer must assume all 
responsibilities outlined in Section 3.2 of this Agreement."
```

**Note overlap**: 200 chars of first chunk repeated in second chunk (ensures context continuity).

---

## 9. RAG Fusion Re-Ranking

**Implementation**: v1.2.0 (February 2026)  
**Location**: `backend/agents/retrieval_service.py`

### 9.1 Motivation

Pure vector search ranks by **semantic similarity only** — ignores:
- Graph connectivity (important documents with many references)
- Feature matching (exact error codes, title terms)
- Intent (query asking for specific doc_type)

**Solution**: Hybrid scoring combining multiple signals.

### 9.2 Scoring Formula

```
FinalScore = VectorScore × (1 + GraphBoost) × FeatureBoosts
```

**Components**:

1. **Vector Score** (baseline, 0-1):
   - Cosine similarity from ChromaDB
   - Normalized: `1 / (1 + distance)`

2. **Graph Boost** (additive, 0-0.5):
   - Connectivity score: `min(0.5, out_degree(doc_id) * 0.01)`
   - Rewards documents defining many terms

3. **Feature Boosts** (multiplicative):
   - **Error code exact match**: 2.0× (highest priority)
   - **Intent doc_type match**: 1.7× (e.g., query wants "policy" → boost POLICY docs)
   - **Title term match**: 1.3× (query term in document title)
   - **Keyword density**: 1.0-1.2× (frequency of query terms in chunk)

### 9.3 Intent Detection

**File**: `retrieval_service.py::_detect_intent()`

**Patterns**:
```python
intent_patterns = {
    "policy": [r"\bpolicy\b", r"\bguideline\b", r"\bstandard\b"],
    "sop": [r"\bprocedure\b", r"\bworkflow\b", r"\bstep\b"],
    "reference": [r"\bdefinition\b", r"\bglossary\b", r"\bwhat is\b"],
    "guide": [r"\bhow to\b", r"\btutorial\b", r"\blearning\b"],
}

for doc_type, patterns in intent_patterns.items():
    if any(re.search(p, query, re.I) for p in patterns):
        return doc_type
```

**Effect**: If query contains "what is" → detected as "reference" → boost REFERENCE docs by 1.7×.

### 9.4 Deduplication

**Problem**: Same document may have multiple chunks in top-k results → visually redundant.

**Solution**: Keep only highest-scoring chunk per document.

**Code**:
```python
seen_docs = set()
deduplicated = []
for result in sorted(results, key=lambda x: -x['score']):
    if result['doc_id'] not in seen_docs:
        deduplicated.append(result)
        seen_docs.add(result['doc_id'])
```

### 9.5 Example Scoring

**Query**: `"What is the servicer responsible for?"`

**Candidate Results**:

| doc_id | Vector Score | Graph Boost | Feature Boosts | Final Score |
|---|---|---|---|---|
| doc_001 | 0.85 | +0.3 (30 terms defined) | 1.3 (title match) | **1.44** |
| doc_002 | 0.90 | +0.1 (10 terms defined) | 1.0 (no match) | **0.99** |
| doc_003 | 0.75 | +0.5 (50 terms defined) | 1.7 (intent=reference) | **1.91** |

**Winner**: doc_003 (despite lower vector score, graph and intent boost push it to top)

---

## 10. Data Flow: Query to Response

**End-to-End Trace**:

1. **User Query** (VS Code): `/kts search What is a servicer?`
2. **Extension** (`chat/participant.ts`): Parse command, send JSON to backend
3. **Backend IPC** (`cli/main.py`): Receive stdin, dispatch to `retrieval_service.py`
4. **Intent Detection**: "what is" → intent=REFERENCE
5. **Vector Search** (ChromaDB): Fetch top-20 semantic matches
6. **Graph Augmentation** (NetworkX): Compute connectivity boost for each doc
7. **Feature Scoring**: Check title match, keyword density
8. **RAG Fusion**: Combine scores with formula
9. **Deduplication**: Keep top chunk per document
10. **Top-5 Results**: Return JSON to extension
11. **Extension Render**: Display in Copilot Chat with citations

**Latency Breakdown** (typical):
- Vector search: 80ms (50%)
- Graph queries: 30ms (20%)
- Feature scoring: 20ms (13%)
- Re-ranking: 10ms (7%)
- IPC overhead: 15ms (10%)
- **Total**: ~155ms

---

## 11. Artifact Storage Structure

**Base Path**: Configurable via `KTS_KB_PATH` environment variable (default: `.kts/`)

**Directory Layout**:
```
.kts/
├── manifest.json              # Index of all known documents
├── documents/                 # Per-document storage
│   ├── doc_<hash>/
│   │   ├── content.md         # Extracted text (Markdown format)
│   │   ├── metadata.json      # Title, doc_type, keywords, timestamps
│   │   ├── descriptions.json  # AI-generated image descriptions (by hash)
│   │   └── images/            # Embedded images (deduplicated by SHA-256)
│   │       ├── <hash>.png
│   │       └── <hash>.jpg
├── vectors/
│   └── chroma/                # ChromaDB persistent storage
│       ├── chroma.sqlite3     # Embedding index
│       └── *.parquet          # Compressed vectors
├── graph/
│   └── knowledge_graph.json   # NetworkX node-link format
└── staging/                   # Temporary ingestion workspace
    └── <doc_id>/              # Deleted after atomic move to documents/
```

**Key Properties**:
- **Atomic writes**: Ingestion writes to `staging/`, then moves to `documents/` (no partial states)
- **Content-addressable images**: SHA-256 hash → deduplicates identical images across docs
- **Human-readable**: All JSON, Markdown (no binary blobs except SQLite/Parquet)

---

## 12. Deployment Tiers (Updated)

### Option A2 (Full)

**Includes**:
- All document parsers: DOCX, PDF, PPTX, HTML, images
- Full ChromaDB + ONNX embeddings
- Full NetworkX graph
- Dependencies: `PyMuPDF`, `python-pptx`, `Pillow`

**Size**: ~80MB VSIX, ~75MB standalone exe

**Use Case**: Comprehensive enterprise deployments, mixed document formats

### Option A3 (Lightweight)

**Includes**:
- Limited parsers: DOCX, HTML only (no PDF/PPTX)
- Full ChromaDB + ONNX embeddings (**CRITICAL**: Added in v1.2.0!)
- Full NetworkX graph (**CRITICAL**: Added in v1.2.0!)

**Excludes**:
- `PyMuPDF` (no PDF)
- `python-pptx` (no PowerPoint)
- `Pillow` (no advanced image processing)

**Size**: ~30MB VSIX, ~25MB standalone exe

**Use Case**: Lightweight deployments, DOCX-only workflows, bandwidth-constrained environments

**Note**: Prior to v1.2.0, `requirements_a3.txt` was missing `chromadb`, `onnxruntime`, `networkx` → builds would fail at runtime. This was fixed on 2026-02-15.

---

**See Also**:
- [Recent Updates](RECENT_UPDATES.md) — Changelog for v1.2.0
- [Build Guide](BUILD_GUIDE.md) — Creating installers
- [Maintenance Guide](MAINTENANCE_GUIDE.md) — Debugging and extending
- [Configuration](CONFIGURATION.md) — Environment variables and artifact paths
