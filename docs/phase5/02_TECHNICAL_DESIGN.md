# Phase 5 — Technical Design

**Date**: 2026-02-16  
**Status**: Design — pending approval

---

## Table of Contents

1. [WS-1: Embedding Provider Swap](#ws-1-embedding-provider-swap)
2. [WS-2: Self-Query Metadata Filter Extraction](#ws-2-self-query-metadata-filter-extraction)
3. [WS-3: Confidence Score Overhaul](#ws-3-confidence-score-overhaul)
4. [WS-4: Query Decomposition + RRF Fusion](#ws-4-query-decomposition--rrf-fusion)
5. [WS-5: Self-RAG Retry Loop](#ws-5-self-rag-retry-loop)
6. [WS-6 / WS-7: Deferred (Sketch)](#ws-6--ws-7-deferred-sketch)

---

## WS-1: Embedding Provider Swap

### 1.1 Problem Statement

Current system uses `chromadb.utils.embedding_functions.DefaultEmbeddingFunction()` which wraps `ONNXMiniLM_L6_V2` (384-dim, FP32, 86.2 MB). No abstraction layer exists — ChromaDB manages embedding internally. We need to:

1. Replace with BAAI/bge-base-en-v1.5 ONNX INT8 (768-dim, ~110 MB)
2. Handle BGE-specific query prefix (`"Represent this sentence: "`)
3. Maintain 100% offline operation
4. Allow rollback to legacy via config

### 1.2 EmbeddingProvider Interface

**New file: `backend/vector/embedding_provider.py`**

```python
from abc import ABC, abstractmethod
from typing import List
import hashlib

class EmbeddingProvider(ABC):
    """Abstract embedding provider for KTS vector operations."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique string identifying this provider, e.g. 'bge_onnx_int8'."""

    @property
    @abstractmethod
    def dims(self) -> int:
        """Dimensionality of output vectors."""

    @property
    @abstractmethod
    def model_hash(self) -> str:
        """SHA-256 of the ONNX model file for index compatibility checks."""

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of document chunks. No prefix added."""

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """Embed a single query string. Provider may add model-specific prefix."""

    def as_chroma_ef(self) -> "ChromaEmbeddingAdapter":
        """Return a ChromaDB-compatible EmbeddingFunction wrapper."""
        return ChromaEmbeddingAdapter(self)


class ChromaEmbeddingAdapter:
    """Adapts EmbeddingProvider to chromadb.api.types.EmbeddingFunction."""

    def __init__(self, provider: EmbeddingProvider):
        self._provider = provider

    def __call__(self, input: List[str]) -> List[List[float]]:
        # ChromaDB calls this for both ingestion and query.
        # We use embed_documents because ChromaDB doesn't distinguish.
        # Query prefix is handled at VectorStore.search() level.
        return self._provider.embed_documents(input)
```

**Design notes:**
- `as_chroma_ef()` returns a callable that ChromaDB accepts as `embedding_function=`.
- For **queries**, `VectorStore.search()` will call `provider.embed_query(text)` directly and pass the pre-computed vector to `collection.query(query_embeddings=...)` instead of `query_texts=`.
- For **ingestion**, ChromaDB continues to call `ef(texts)` internally, which routes through `embed_documents()` (no prefix).

### 1.3 BGE ONNX INT8 Provider

**New file: `backend/vector/bge_onnx_provider.py`**

```python
import json
import hashlib
import numpy as np
from pathlib import Path
from typing import List

import onnxruntime as ort

class BgeOnnxInt8Provider(EmbeddingProvider):
    """BAAI/bge-base-en-v1.5 — ONNX INT8 quantized, 768-dim."""

    QUERY_PREFIX = "Represent this sentence: "
    MAX_SEQ_LEN = 512
    BATCH_SIZE = 32

    def __init__(self, model_dir: str | Path):
        self._model_dir = Path(model_dir)
        self._session = ort.InferenceSession(
            str(self._model_dir / "model.onnx"),
            providers=["CPUExecutionProvider"],
        )
        self._tokenizer = self._load_tokenizer()
        self._hash = self._compute_model_hash()

    @property
    def provider_id(self) -> str:
        return "bge_onnx_int8"

    @property
    def dims(self) -> int:
        return 768

    @property
    def model_hash(self) -> str:
        return self._hash

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        all_vecs = []
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]
            vecs = self._infer(batch)
            all_vecs.extend(vecs)
        return all_vecs

    def embed_query(self, text: str) -> List[float]:
        prefixed = f"{self.QUERY_PREFIX}{text}"
        return self._infer([prefixed])[0]

    def _infer(self, texts: List[str]) -> List[List[float]]:
        encoded = self._tokenize(texts)
        outputs = self._session.run(
            None,
            {
                "input_ids": encoded["input_ids"],
                "attention_mask": encoded["attention_mask"],
                "token_type_ids": encoded["token_type_ids"],
            },
        )
        # Mean pooling over last hidden state
        hidden = outputs[0]  # (batch, seq_len, 768)
        mask = encoded["attention_mask"]
        mask_expanded = np.expand_dims(mask, axis=-1)  # (batch, seq_len, 1)
        summed = np.sum(hidden * mask_expanded, axis=1)
        counts = np.clip(mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
        pooled = summed / counts
        # L2 normalize
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        norms = np.clip(norms, a_min=1e-9, a_max=None)
        normalized = pooled / norms
        return normalized.tolist()

    def _tokenize(self, texts: List[str]) -> dict:
        """Simple tokenizer using tokenizers library (offline)."""
        from tokenizers import Tokenizer

        if not hasattr(self, '_hf_tokenizer'):
            self._hf_tokenizer = Tokenizer.from_file(
                str(self._model_dir / "tokenizer.json")
            )
            self._hf_tokenizer.enable_truncation(max_length=self.MAX_SEQ_LEN)
            self._hf_tokenizer.enable_padding(
                pad_id=0, pad_token="[PAD]", length=None
            )

        encodings = self._hf_tokenizer.encode_batch(texts)
        max_len = max(len(e.ids) for e in encodings)

        input_ids = np.zeros((len(texts), max_len), dtype=np.int64)
        attention_mask = np.zeros((len(texts), max_len), dtype=np.int64)
        token_type_ids = np.zeros((len(texts), max_len), dtype=np.int64)

        for i, enc in enumerate(encodings):
            length = len(enc.ids)
            input_ids[i, :length] = enc.ids
            attention_mask[i, :length] = enc.attention_mask
            token_type_ids[i, :length] = enc.type_ids

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        }

    def _load_tokenizer(self):
        """Validate tokenizer files exist."""
        required = ["tokenizer.json", "vocab.txt"]
        for f in required:
            if not (self._model_dir / f).exists():
                raise FileNotFoundError(f"Missing {f} in {self._model_dir}")
        return True

    def _compute_model_hash(self) -> str:
        h = hashlib.sha256()
        model_path = self._model_dir / "model.onnx"
        with open(model_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return f"sha256:{h.hexdigest()[:16]}"
```

**Key design choices:**
- Uses HuggingFace `tokenizers` library (pure Rust, fast, no PyTorch dependency) — already available via `transformers` or standalone pip install.
- Mean pooling + L2 normalization matches BGE paper's recommended pooling.
- Query prefix `"Represent this sentence: "` added only in `embed_query()`, not `embed_documents()`.
- Batch inference with configurable `BATCH_SIZE=32` for throughput during ingestion.

### 1.4 Legacy Provider (Rollback)

```python
class LegacyChromaProvider(EmbeddingProvider):
    """Wraps chromadb.utils.embedding_functions.DefaultEmbeddingFunction
    (ONNXMiniLM_L6_V2, 384-dim) for rollback."""

    def __init__(self):
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        self._ef = DefaultEmbeddingFunction()
        self._hash = "legacy:default"

    @property
    def provider_id(self) -> str:
        return "legacy_chroma_default"

    @property
    def dims(self) -> int:
        return 384

    @property
    def model_hash(self) -> str:
        return self._hash

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._ef(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._ef([text])[0]
```

### 1.5 VectorStore Changes

Current `VectorStore.__init__()`:
```python
# Current (Phase 4)
self.collection = self.client.get_or_create_collection(
    name="kts_knowledge_base",
    embedding_function=DefaultEmbeddingFunction(),
    metadata={"hnsw:space": "cosine"}
)
```

Target `VectorStore.__init__()`:
```python
# Phase 5
def __init__(self, persist_dir: str, embedding_provider: EmbeddingProvider):
    self._provider = embedding_provider
    self.client = chromadb.PersistentClient(path=persist_dir)
    self.collection = self.client.get_or_create_collection(
        name="kts_knowledge_base",
        embedding_function=embedding_provider.as_chroma_ef(),
        metadata={"hnsw:space": "cosine"}
    )
    self._write_index_metadata(persist_dir)
```

Current `VectorStore.search()`:
```python
# Current: ChromaDB embeds the query internally
results = self.collection.query(
    query_texts=[query],
    n_results=top_k,
    where=where_arg,
    include=["documents", "metadatas", "distances"]
)
```

Target `VectorStore.search()`:
```python
# Phase 5: Pre-compute query embedding with provider (handles prefix)
query_vec = self._provider.embed_query(query)
results = self.collection.query(
    query_embeddings=[query_vec],
    n_results=top_k,
    where=where_arg,
    include=["documents", "metadatas", "distances"]
)
```

This ensures the BGE query prefix is applied for queries but not for documents.

### 1.6 TermRegistry Changes

Current `TermRegistry._embed()`:
```python
# Current: uses DefaultEmbeddingFunction directly
fn = DefaultEmbeddingFunction()
return fn(texts)
```

Target:
```python
# Phase 5: accept provider via constructor
def __init__(self, ..., embedding_provider: EmbeddingProvider):
    self._embed_provider = embedding_provider
    ...

def _embed(self, texts: list[str]) -> list[list[float]]:
    return self._embed_provider.embed_documents(texts)
```

### 1.7 Model Build Script

**New file: `scripts/model_build/build_bge_onnx_int8.ps1`**

One-time developer script (NOT shipped in VSIX):

```powershell
# 1. Download from HuggingFace
# 2. Export to ONNX via optimum
# 3. Quantize to INT8 via onnxruntime.quantization
# 4. Smoke test: embed "hello world", assert shape (1, 768)
# 5. Copy to assets/models/bge-base-en-v1.5/onnx-int8/
# 6. Generate model_manifest.json with sha256 hash
```

Output artifacts go into `assets/models/bge-base-en-v1.5/onnx-int8/`, which PyInstaller bundles.

### 1.8 PyInstaller Spec Changes

In `packaging/kts_backend.spec`:

```python
# Remove:
#   MiniLM model bundling from chroma cache

# Add:
datas += [
    ('assets/models/bge-base-en-v1.5/onnx-int8', 'models/bge-base-en-v1.5/onnx-int8'),
]
```

Runtime model path resolution:
```python
# In BgeOnnxInt8Provider or factory:
if getattr(sys, 'frozen', False):
    model_dir = Path(sys._MEIPASS) / "models" / "bge-base-en-v1.5" / "onnx-int8"
else:
    model_dir = Path("assets/models/bge-base-en-v1.5/onnx-int8")
```

### 1.9 Dependencies

| Package | Current | Phase 5 | Notes |
|---------|---------|---------|-------|
| `onnxruntime` | 1.24.1 | 1.24.1 | No change |
| `tokenizers` | — | ≥0.19.0 | HF tokenizers (Rust, fast, small), needed for BGE tokenization |
| `numpy` | present | present | No change |
| `chromadb` | present | present | No change |

`tokenizers` is ~5 MB wheel and has no PyTorch dependency.

---

## WS-2: Self-Query Metadata Filter Extraction

### 2.1 Problem Statement

Currently, `doc_type_filter` can only be supplied by the caller (extension → CLI → RetrievalService). Users must know the exact doc_type value. The system already computes `intent` internally (via `_detect_query_intent()`) but only uses it for post-retrieval boosting — it never maps intent to a pre-retrieval filter.

Similarly, error codes and tool names are extracted during scoring but not used to filter the initial vector search, wasting retrieval budget on irrelevant chunks.

### 2.2 Current State

In `retrieval_service.py`, `_detect_query_intent()` returns one of:
- `troubleshoot` → should map to `doc_type=TROUBLESHOOT`
- `how_to` → should map to `doc_type in [SOP, USER_GUIDE]`
- `error_lookup` → should map to `doc_type in [TROUBLESHOOT, REFERENCE]`
- `file_capability` → should map to `doc_type in [USER_GUIDE, RELEASE_NOTES]`
- `general` → no filter

Error codes are already detected via `_extract_error_codes()` (regex).

### 2.3 SelfQueryExtractor Design

**New file: `backend/retrieval/self_query_extractor.py`**

```python
@dataclass
class MetadataFilters:
    doc_type: list[str] | None = None      # ChromaDB $in filter
    tool: str | None = None                 # exact match
    error_code: str | None = None           # exact match
    cleaned_query: str = ""                 # query with filter tokens removed

class SelfQueryExtractor:
    """Rule-based extraction of metadata filters from natural language queries.
    No LLM required."""

    # Intent → filter mapping
    INTENT_FILTER_MAP = {
        "troubleshoot": ["TROUBLESHOOT"],
        "how_to": ["SOP", "USER_GUIDE"],
        "error_lookup": ["TROUBLESHOOT", "REFERENCE"],
        "file_capability": ["USER_GUIDE", "RELEASE_NOTES"],
        "general": None,
    }

    def extract(self, query: str, detected_intent: str | None = None) -> MetadataFilters:
        filters = MetadataFilters(cleaned_query=query)

        # 1. Error code extraction (strongest signal)
        error_match = re.search(
            r'(ERR-[A-Z]+-\d{3}|[A-Z]{3,}\d{3,})', query, re.IGNORECASE
        )
        if error_match:
            filters.error_code = error_match.group(0).upper()

        # 2. Tool name extraction (from known tool list)
        for tool_name in self._known_tools:
            if tool_name.lower() in query.lower():
                filters.tool = tool_name
                break

        # 3. Doc type from intent
        if detected_intent and detected_intent in self.INTENT_FILTER_MAP:
            filters.doc_type = self.INTENT_FILTER_MAP[detected_intent]

        # 4. Clean query (remove extracted tokens to improve embedding quality)
        filters.cleaned_query = self._clean_query(query, filters)

        return filters
```

### 2.4 VectorStore.search() Enhanced Where Clause

Current:
```python
where_clause = {}
if doc_type_filter:
    where_clause["doc_type"] = doc_type_filter
where_arg = where_clause if where_clause else None
```

Phase 5:
```python
def search(self, query: str, top_k: int = 5,
           filters: MetadataFilters | None = None,
           doc_type_filter: str | None = None) -> List[dict]:
    """Perform semantic search with optional metadata filters."""

    where_parts = []

    # Legacy single doc_type_filter (backward compat)
    if doc_type_filter:
        where_parts.append({"doc_type": doc_type_filter})

    # New self-query filters
    if filters:
        if filters.doc_type:
            if len(filters.doc_type) == 1:
                where_parts.append({"doc_type": filters.doc_type[0]})
            else:
                where_parts.append({"doc_type": {"$in": filters.doc_type}})
        if filters.error_code:
            # error_code stored in entities JSON; use content search fallback
            pass  # Handled by scoring, not ChromaDB filter
        if filters.tool:
            # Source path contains tool name in most cases
            where_parts.append({"source_path": {"$contains": filters.tool}})

    # Combine with $and if multiple
    if len(where_parts) > 1:
        where_arg = {"$and": where_parts}
    elif len(where_parts) == 1:
        where_arg = where_parts[0]
    else:
        where_arg = None

    # Use pre-computed query embedding for prefix handling
    query_vec = self._provider.embed_query(
        filters.cleaned_query if filters else query
    )
    results = self.collection.query(
        query_embeddings=[query_vec],
        n_results=top_k,
        where=where_arg,
        include=["documents", "metadatas", "distances"]
    )
    ...
```

### 2.5 Fallback Strategy

If a filtered search returns fewer than `min_filtered_results` (default 2):

```python
if len(hits) < self.config.min_filtered_results:
    # Retry without filters (broader search)
    fallback_hits = self.collection.query(
        query_embeddings=[query_vec],
        n_results=top_k,
        where=None,
        include=["documents", "metadatas", "distances"]
    )
    # Merge, deduplicate by chunk_id, keep filtered first
    hits = self._merge_deduplicate(hits, fallback_hits)
```

This prevents filter-induced recall drop for narrow corpora.

### 2.6 Integration Point in RetrievalService

```python
# In execute(), after acronym resolution, before vector search:
if self.config.self_query_enabled:
    intent, _ = self._detect_query_intent(query)
    extractor = SelfQueryExtractor(known_tools=self._known_tools)
    filters = extractor.extract(query, detected_intent=intent)
else:
    filters = None
```

---

## WS-3: Confidence Score Overhaul

### 3.1 Current Formula

```python
# Current (retrieval_service.py L555-559)
top_similarity = float(rows[0].get("score", 0.0))
confidence = min(1.0, max(0.3, top_similarity + (0.05 * (len(chunks) - 1))))
```

**Problems:**
- Only uses top vector similarity + a chunk count bonus
- Ignores cross-encoder score, graph boost, entity overlap, error code match, intent match, keyphrase overlap — all of which are already computed
- Floor at 0.3 regardless of evidence quality
- Ceiling hit too easily (two chunks with 0.9 similarity → 0.95)

### 3.2 Phase 5 Multi-Signal Formula

```python
def _compute_confidence(
    self,
    ranked_rows: list[dict],
    chunks: list[TextChunk],
    filters_engaged: bool,
    coverage: float | None = None,
) -> float:
    """
    Multi-signal confidence score.

    Signals and weights (sum to 1.0):
      vector_sim:       0.25  — top result cosine similarity
      cross_encoder:    0.25  — top result cross-encoder score (sigmoid-normalized)
      graph_boost:      0.10  — top result graph adjacency boost
      error_match:      0.10  — any error code exact match in top results
      intent_match:     0.10  — intent classification agrees with top doc_type
      entity_overlap:   0.10  — NER entity Jaccard overlap with top result
      keyphrase_overlap: 0.05 — keyphrase partial match
      filter_engaged:   0.05  — metadata filter was applied (higher precision signal)
    """
    if not ranked_rows:
        return 0.0

    top = ranked_rows[0]

    # Individual signals (all 0.0 → 1.0)
    sig_vec = min(1.0, max(0.0, float(top.get("score", 0.0))))

    ce_raw = top.get("cross_encoder_score")
    sig_ce = (1.0 / (1.0 + math.exp(-ce_raw))) if ce_raw is not None else sig_vec

    sig_graph = min(1.0, float(top.get("graph_boost", 0.0)))

    features = top.get("features", {})
    sig_error = 1.0 if features.get("error_code_exact_match", 0) > 0 else 0.0
    sig_intent = min(1.0, features.get("intent_doc_type_match", 0.0))
    sig_entity = min(1.0, features.get("entity_overlap", 0.0))
    sig_keyphrase = min(1.0, features.get("entity_keyphrase_match", 0.0))
    sig_filter = 1.0 if filters_engaged else 0.0

    # Weighted combination
    raw = (
        0.25 * sig_vec
        + 0.25 * sig_ce
        + 0.10 * sig_graph
        + 0.10 * sig_error
        + 0.10 * sig_intent
        + 0.10 * sig_entity
        + 0.05 * sig_keyphrase
        + 0.05 * sig_filter
    )

    # Chunk diversity bonus: +0.02 per additional supporting chunk, max 0.10
    chunk_bonus = min(0.10, 0.02 * (len(chunks) - 1)) if len(chunks) > 1 else 0.0
    raw += chunk_bonus

    # Coverage penalty (if evidence matching ran)
    if coverage is not None and coverage < 1.0:
        raw *= (0.5 + 0.5 * coverage)  # At 0% coverage → halved; at 100% → unchanged

    # Clamp to [0.0, 1.0]
    return round(min(1.0, max(0.0, raw)), 4)
```

### 3.3 Feature Storage

To support the multi-signal formula, `rerank_scorer()` must store computed features on the row:

```python
# In rerank_scorer(), after computing features:
row["features"] = features
row["graph_boost"] = graph_boost
```

This is already partially done (features are computed) — we just need to persist them on the row dict.

### 3.4 Calibration Targets

| Query Type | Current Confidence | Target Confidence |
|------------|-------------------|-------------------|
| Exact error code match, good chunks | 0.85-0.95 | 0.90-0.98 |
| Paraphrase match, decent chunks | 0.55-0.70 | 0.60-0.75 |
| Vague query, marginal chunks | 0.30-0.40 | 0.15-0.35 |
| No relevant results | 0.30 (floor) | 0.00-0.10 |

Key improvement: vague/irrelevant queries now score LOW instead of being floored at 0.3, giving the extension a clear signal to show "low confidence" warnings.

---

## WS-4: Query Decomposition + RRF Fusion

### 4.1 Problem Statement

Complex multi-part queries (e.g., "How do I fix AUTH401 and what is the escalation process?") currently become a single embedding vector. This often misses relevant chunks for one or both sub-topics.

### 4.2 QueryDecomposer Design

**New file: `backend/retrieval/query_decomposer.py`**

```python
@dataclass
class SubQuery:
    text: str
    origin: str           # "original" | "split" | "step_back" | "llm"
    filters: MetadataFilters | None = None

class QueryDecomposer:
    """Splits complex queries into sub-queries for multi-path retrieval."""

    # Conjunction patterns that indicate multi-part queries
    SPLIT_PATTERNS = [
        r'\band\b\s+(?:also|what|how|why|when|where)',
        r'\balso\b',
        r';\s*',
        r'\?\s+(?:And|Also|What|How)',
    ]

    def decompose(
        self,
        query: str,
        filters: MetadataFilters | None = None,
        use_llm: bool = False,
    ) -> list[SubQuery]:
        sub_queries = []

        # Always include original
        sub_queries.append(SubQuery(
            text=query, origin="original", filters=filters
        ))

        # Rule-based splitting
        for pattern in self.SPLIT_PATTERNS:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                parts = re.split(pattern, query, maxsplit=1, flags=re.IGNORECASE)
                parts = [p.strip() for p in parts if len(p.strip()) > 10]
                if len(parts) >= 2:
                    for part in parts:
                        sub_queries.append(SubQuery(
                            text=part, origin="split", filters=filters
                        ))
                break  # One split per query

        # Step-back query: generalize to broader topic
        step_back = self._generate_step_back(query)
        if step_back:
            sub_queries.append(SubQuery(
                text=step_back, origin="step_back", filters=None  # No filter for broad
            ))

        # Optional LLM decomposition (GHCP)
        if use_llm and len(sub_queries) <= 2:
            llm_parts = self._llm_decompose(query)
            for part in llm_parts:
                sub_queries.append(SubQuery(
                    text=part, origin="llm", filters=filters
                ))

        # Deduplicate + cap at 4
        return self._deduplicate(sub_queries)[:4]

    def _generate_step_back(self, query: str) -> str | None:
        """Generate a broader, more general version of the query."""
        # Remove specific identifiers (error codes, tool names, version numbers)
        generalized = re.sub(r'ERR-[A-Z]+-\d{3}', '', query)
        generalized = re.sub(r'v?\d+\.\d+(\.\d+)?', '', generalized)
        generalized = generalized.strip()

        if len(generalized) > 15 and generalized != query:
            return generalized
        return None
```

### 4.3 Reciprocal Rank Fusion (RRF)

**New file: `backend/retrieval/rank_fusion.py`**

```python
def reciprocal_rank_fusion(
    result_sets: list[list[dict]],
    k: int = 60,
    id_key: str = "chunk_id",
) -> list[dict]:
    """
    Merge multiple ranked result sets using RRF.

    RRF score for document d = Σ 1 / (k + rank_i(d))

    Parameters:
    - result_sets: list of ranked hit lists from different sub-queries
    - k: constant (60 is standard; higher = less top-heavy)
    - id_key: key to use for deduplication

    Returns:
    - Merged list sorted by RRF score descending
    """
    rrf_scores: dict[str, float] = {}
    doc_cache: dict[str, dict] = {}

    for result_set in result_sets:
        for rank, doc in enumerate(result_set, start=1):
            doc_id = doc[id_key]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            # Keep the version with highest original score
            if doc_id not in doc_cache or doc.get("score", 0) > doc_cache[doc_id].get("score", 0):
                doc_cache[doc_id] = doc

    # Sort by RRF score
    ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    merged = []
    for doc_id, rrf_score in ranked:
        entry = doc_cache[doc_id].copy()
        entry["rrf_score"] = rrf_score
        merged.append(entry)

    return merged
```

### 4.4 Integration in RetrievalService

```python
# In execute(), replacing the single vector search:

if self.config.query_decomposition_enabled:
    decomposer = QueryDecomposer()
    sub_queries = decomposer.decompose(
        query,
        filters=filters,
        use_llm=self.config.query_decomposition_use_llm
    )
else:
    sub_queries = [SubQuery(text=query, origin="original", filters=filters)]

# Parallel retrieval per sub-query
result_sets = []
for sq in sub_queries:
    expanded = self.query_expander.expand(sq.text, doc_type=corpus_regime)
    hits = self.vector_store.search(
        query=expanded,
        top_k=max_results * 4,
        filters=sq.filters
    )
    result_sets.append(hits)

# Fuse if multiple result sets
if len(result_sets) > 1:
    rows = reciprocal_rank_fusion(result_sets, k=self.config.rrf_k)
else:
    rows = result_sets[0]
```

### 4.5 Performance Budget

| Sub-queries | Vector Searches | Cross-encoder Passes | Max Latency Impact |
|---|---|---|---|
| 1 (no decomposition) | 1 | 1 | Baseline |
| 2 (original + split) | 2 | 1 (post-fusion) | +40-80ms |
| 3 (+ step-back) | 3 | 1 (post-fusion) | +80-120ms |
| 4 (+ LLM) | 4 | 1 (post-fusion) | +100-200ms + LLM latency |

Cross-encoder runs once on the fused result set, NOT per sub-query. This is critical for keeping latency reasonable.

---

## WS-5: Self-RAG Retry Loop

### 5.1 Problem Statement

Evidence matching currently runs once. If coverage is below threshold, the result is returned with a provenance error — no attempt is made to improve coverage by re-retrieving with a different query.

### 5.2 Architecture

```
┌──────────────────────────────────────────┐
│         Self-RAG Retry Controller        │
│                                          │
│  retry_budget = config.self_rag_max_retries (default: 1)
│  coverage_threshold = config.self_rag_coverage_threshold (default: 0.80)
│                                          │
│  LOOP:                                   │
│    1. Run evidence matching              │
│    2. IF coverage ≥ threshold → BREAK    │
│    3. IF retry_budget == 0 → BREAK       │
│    4. Analyze uncited claims             │
│    5. Rewrite query targeting gaps        │
│    6. Re-run retrieval (Stages A-D)      │
│    7. Merge new chunks with existing     │
│    8. Decrement retry_budget             │
│    9. GOTO 1                             │
└──────────────────────────────────────────┘
```

### 5.3 Query Rewriting Strategy

For each retry, construct a supplementary query from uncited claims:

```python
def _build_retry_query(
    self,
    original_query: str,
    uncited_claims: list[str],
    existing_chunks: list[TextChunk],
) -> str:
    """Build a targeted query focusing on information gaps."""
    # Take up to 2 uncited claims
    gap_text = " ".join(uncited_claims[:2])

    # Remove terms already well-covered in existing chunks
    covered_terms = set()
    for chunk in existing_chunks:
        covered_terms.update(
            re.findall(r'\b[a-z]{4,}\b', chunk.content.lower())
        )

    gap_tokens = re.findall(r'\b[a-z]{4,}\b', gap_text.lower())
    novel_tokens = [t for t in gap_tokens if t not in covered_terms]

    if novel_tokens:
        return f"{original_query} {' '.join(novel_tokens[:5])}"
    return original_query  # Unchanged — retry unlikely to help
```

### 5.4 Integration in RetrievalService

```python
# After initial evidence matching, if self-RAG enabled:
if self.config.self_rag_retry_enabled and ledger.coverage < self.config.self_rag_coverage_threshold:
    retry_budget = self.config.self_rag_max_retries

    while retry_budget > 0 and ledger.coverage < self.config.self_rag_coverage_threshold:
        retry_query = self._build_retry_query(query, ledger.uncited_claims, chunks)
        if retry_query == query:
            break  # No novel terms to retry with

        # Re-run stages A-D with retry query
        retry_rows = self._retrieve_and_rank(retry_query, filters, corpus_regime, graph_data)

        # Merge new chunks (deduplicate by chunk_id)
        new_chunks = self._rows_to_chunks(retry_rows)
        chunks = self._merge_chunks(chunks, new_chunks)

        # Re-run evidence matching
        ledger = matcher.match_claims_to_chunks(answer_text, chunks, query=query)
        retry_budget -= 1

    # Update confidence based on final coverage
    confidence = self._compute_confidence(
        ranked_rows, chunks, filters_engaged, coverage=ledger.coverage
    )
```

### 5.5 Guard Rails

| Guard | Mechanism |
|-------|-----------|
| **Max retries** | `self_rag_max_retries=1` (config, default 1) |
| **Same-query prevention** | Skip if retry_query == original_query |
| **Latency cap** | Total pipeline timeout applies (existing 30s) |
| **Disabled by default** | `self_rag_retry_enabled=False` until validated |
| **No LLM required** | Query rewriting is rule-based (extract uncited claim tokens) |

---

## WS-6 / WS-7: Deferred (Sketch)

These workstreams require a GitHub Copilot (GHCP) language model and are deferred until WS-1 through WS-5 are validated.

### WS-6: HyDE (Hypothetical Document Embedding)

**Concept:** Before embedding a query, ask GHCP to generate a hypothetical "perfect answer", then embed THAT instead of the raw query. This bridges the vocabulary gap between questions and answers.

**Sketch:**
```python
class HyDEQueryTransformer:
    def transform(self, query: str) -> str:
        prompt = f"Write a short technical paragraph that would answer: {query}"
        hypothetical_doc = ghcp.generate(prompt)
        return hypothetical_doc  # Embed this instead of the raw query
```

**Dependencies:** WS-1 (embedding provider), GHCP API access, latency budget (+500-1000ms).

### WS-7: RAPTOR-Lite Summary Index

**Concept:** During ingestion, generate hierarchical summaries of document clusters. At query time, first search the summary index to identify relevant clusters, then search within those clusters.

**Sketch:**
```python
class RaptorSummaryIndex:
    def build(self, chunks: list[TextChunk]) -> list[SummaryNode]:
        clusters = self._cluster_embeddings(chunks, n_clusters=10)
        summaries = []
        for cluster in clusters:
            summary_text = ghcp.summarize(cluster.chunks)
            summaries.append(SummaryNode(
                summary=summary_text,
                chunk_ids=[c.chunk_id for c in cluster.chunks]
            ))
        return summaries

    def search(self, query: str) -> list[str]:
        # Search summaries first → get relevant chunk_ids → search within
        ...
```

**Dependencies:** WS-1 (embedding provider), GHCP API access, ingestion-time cost.

---

## Appendix A: Data Model Changes

### New Dataclasses

```python
@dataclass
class MetadataFilters:
    """Extracted metadata filters for self-query."""
    doc_type: list[str] | None = None
    tool: str | None = None
    error_code: str | None = None
    cleaned_query: str = ""

@dataclass
class SubQuery:
    """A decomposed sub-query with associated filters."""
    text: str
    origin: str           # "original" | "split" | "step_back" | "llm"
    filters: MetadataFilters | None = None

@dataclass
class IndexMetadata:
    """Stored alongside ChromaDB to track embedding model provenance."""
    provider_id: str
    dims: int
    model_hash: str
    model_version: str
    created_at: str
    chunk_count: int
    doc_count: int
    last_ingest: str
```

### Modified Dataclasses

No changes to existing dataclasses. All new fields are on `dict` rows in the ranking pipeline (features, graph_boost, rrf_score), which are transient and never persisted.

---

## Appendix B: Error Handling Matrix

| Scenario | Response |
|----------|----------|
| BGE model file missing at startup | `FileNotFoundError` with message listing expected path |
| Index metadata mismatch (provider changed without reindex) | Refuse search, return `AgentResult(success=False)` with `"Run kts reindex"` message |
| Tokenizer file missing | `FileNotFoundError` at provider init |
| ONNX runtime failure | Catch `ort.OrtException`, log, return empty embeddings with error context |
| Self-query extracts invalid filter value | Log warning, proceed without filter (fallback to unfiltered) |
| Query decomposer produces empty sub-queries | Fall back to original query |
| RRF receives single result set | Skip fusion, return original set |
| Self-RAG retry produces identical query | Skip retry, return current result |
| Coverage still below threshold after all retries | Return result with low confidence + warning in SearchResult |
