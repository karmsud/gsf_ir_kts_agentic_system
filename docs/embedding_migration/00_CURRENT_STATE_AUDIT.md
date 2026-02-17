# Phase 0 — Current State Audit: Embedding Implementation

**Date**: 2026-02-16  
**Status**: Complete — review before proceeding to Phase 1

---

## 1. Current Embedding Provider

| Property | Value |
|----------|-------|
| **Model** | `all-MiniLM-L6-v2` (Sentence Transformers) |
| **Format** | ONNX FP32 |
| **Dimensions** | 384 |
| **Max sequence length** | 256 tokens |
| **ONNX model size** | 86.2 MB |
| **ChromaDB wrapper** | `ONNXMiniLM_L6_V2` (ChromaDB's `DefaultEmbeddingFunction`) |
| **Runtime** | `onnxruntime` 1.24.1 (CPU) |

### Proposed Replacement

| Property | Value |
|----------|-------|
| **Model** | `BAAI/bge-base-en-v1.5` |
| **Format** | ONNX **INT8** (quantized) |
| **Dimensions** | **768** |
| **Max sequence length** | 512 tokens |
| **Expected ONNX INT8 size** | ~110 MB (vs 440 MB FP32) |
| **Runtime** | `onnxruntime` (same version, CPU) |

---

## 2. Embedding Usage Map

There are **3 distinct embedding call sites** in the codebase. All currently use the same model via ChromaDB's `DefaultEmbeddingFunction`.

### 2a. Document Ingestion (implicit via ChromaDB)

| File | Function | How |
|------|----------|-----|
| `backend/vector/store.py:59` | `VectorStore.__init__()` | Creates `embedding_functions.DefaultEmbeddingFunction()` as `self.ef` |
| `backend/vector/store.py:61-64` | `VectorStore.__init__()` | Passes `self.ef` to `get_or_create_collection()` |
| `backend/vector/store.py:91-106` | `VectorStore.add_chunks()` | Calls `collection.upsert(documents=...)` — ChromaDB auto-embeds |
| `backend/vector/store.py:210` | `VectorStore.add_image_description()` | Same pattern — auto-embedded |

Embedding is **never called explicitly** during ingestion. ChromaDB handles it internally via the collection's `embedding_function`.

### 2b. Query / Search (implicit via ChromaDB)

| File | Function | How |
|------|----------|-----|
| `backend/vector/store.py:109-117` | `VectorStore.search()` | Calls `collection.query(query_texts=[query])` — ChromaDB auto-embeds the query |
| `backend/agents/retrieval_service.py:422` | `RetrievalService.execute()` | Calls `self.vector_store.search(query=...)` |

Query embedding is **entirely implicit** — delegated to ChromaDB.

### 2c. Term Registry (explicit call, separate path)

| File | Function | How |
|------|----------|-----|
| `backend/retrieval/term_registry.py:103-107` | `TermRegistry._get_embed_fn()` | Lazy-loads `DefaultEmbeddingFunction()` independently |
| `backend/retrieval/term_registry.py:111-118` | `TermRegistry._embed()` | Explicitly calls `fn(texts)` to get embeddings for synonym clustering |

This is the **only explicit embedding call** in the codebase. It's used for cosine similarity comparison between keyphrases, not for vector search.

---

## 3. ChromaDB Collection Configuration

```python
# backend/vector/store.py:61-64
self.collection = self.client.get_or_create_collection(
    name="kts_knowledge_base",
    embedding_function=self.ef,       # DefaultEmbeddingFunction
    metadata={"hnsw:space": "cosine"} # Cosine distance metric
)
```

| Property | Value |
|----------|-------|
| **Collection name** | `kts_knowledge_base` |
| **Distance metric** | Cosine |
| **Score conversion** | `score = 1.0 - distance` (store.py:124) |
| **Persistence dir** | `{kb_path}/vectors/chroma` |

### Index Reset Behavior

```python
# backend/vector/store.py:139-148 — reset_index()
self.client.delete_collection("kts_knowledge_base")
self.collection = self.client.get_or_create_collection(
    name="kts_knowledge_base",
    embedding_function=self.ef,
    metadata={"hnsw:space": "cosine"}
)
```

**No index metadata is stored** about which embedding model was used to build the index. This is a key gap that Phase 4 must address.

---

## 4. Model Loading at Runtime

### Development Mode
ChromaDB's `DefaultEmbeddingFunction` auto-downloads the model to:
```
~/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx/
```

### PyInstaller Bundled Mode
```python
# backend/vector/store.py:34-44
if getattr(sys, 'frozen', False):
    bundle_dir = Path(sys._MEIPASS)
    model_cache = bundle_dir / 'chroma_models' / 'all-MiniLM-L6-v2'
    if model_cache.exists():
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
        ONNXMiniLM_L6_V2.DOWNLOAD_PATH = model_cache
```

This **monkey-patches** the ChromaDB class to load from the bundled directory.

---

## 5. VSIX Build Pipeline

### Model Bundling (kts_backend.spec:84-98)

```python
chroma_model_cached = os.path.join(base_path, 'models', 'chroma', 'all-MiniLM-L6-v2')
# Bundles to: dist/kts-backend/_internal/chroma_models/all-MiniLM-L6-v2/
```

Sources (priority order):
1. `packaging/models/chroma/all-MiniLM-L6-v2/` (build staging)
2. `~/.cache/chroma/onnx_models/all-MiniLM-L6-v2/` (user cache fallback)

### Current Bundled Model Files

```
dist/kts-backend/_internal/chroma_models/all-MiniLM-L6-v2/onnx/
├── config.json                 0 KB
├── model.onnx                 86.2 MB    ← FP32 weights
├── special_tokens_map.json     0 KB
├── tokenizer.json              0.68 MB
├── tokenizer_config.json       0 KB
└── vocab.txt                   0.22 MB
                         Total: ~87.1 MB
```

### Other Models Bundled

| Model | Location in Build | Size |
|-------|-------------------|------|
| spaCy `en_core_web_sm` | `_internal/spacy_models/en_core_web_sm/` | ~14.5 MB |
| Cross-encoder (optional) | external path via config | N/A |

### VSIX Total Size

| Component | Size |
|-----------|------|
| **Current VSIX** | 222.63 MB |
| Backend exe + deps | ~450 MB (before VSIX compression) |
| ChromaDB model | 87.1 MB |
| spaCy model | 14.5 MB |

---

## 6. Config Surface (current)

### config/settings.py — KTSConfig

| Field | Default | Role |
|-------|---------|------|
| `chroma_persist_dir` | `.kts/vectors/chroma` | ChromaDB storage |
| `chunk_size` | 1000 | Chars per chunk |
| `chunk_overlap` | 200 | Overlap chars |

### Missing Config (needed for migration)

- **No embedding provider selection** — hardcoded to ChromaDB default
- **No embedding dimension constant** — implicit from model
- **No model path override** — only PyInstaller monkey-patch
- **No index metadata** — nothing records which model built the index

---

## 7. CRITICAL Observations for Migration

### 7a. Dimension Change: 384 → 768
The proposed BGE model produces **768-dim** vectors vs current **384-dim**. This means:
- **All existing ChromaDB indexes are incompatible** — must be fully rebuilt
- **Term registry embeddings** (cached in registry JSON) are incompatible — must be regenerated
- **Score magnitudes may shift** — cosine similarity distributions will differ; confidence thresholds in `retrieval_service.py` may need retuning

### 7b. ChromaDB Embedding Function Architecture
Currently the code lets ChromaDB handle embedding internally via `DefaultEmbeddingFunction`. Two options for BGE:
1. **Custom ChromaDB `EmbeddingFunction`** — implement the ChromaDB interface, ChromaDB calls it
2. **Pre-compute embeddings externally** — pass `embeddings=` to `upsert()` and `query_embeddings=` to `query()` instead of `documents=`/`query_texts=`

Option 1 is cleaner for minimal code change.

### 7c. Monkey-Patching Won't Work
The current PyInstaller bundling monkey-patches `ONNXMiniLM_L6_V2.DOWNLOAD_PATH`. For BGE, we need our own embedding class — can't monkey-patch ChromaDB's internal class.

### 7d. Tokenizer Change
MiniLM uses `tokenizers` library (via ChromaDB). BGE also uses `tokenizers` (HuggingFace). Both are compatible with the `tokenizers` package already bundled in PyInstaller. However:
- MiniLM tokenizer is loaded internally by ChromaDB
- BGE tokenizer must be loaded explicitly by our code

### 7e. ONNXRuntime Already Bundled
`onnxruntime` 1.24.1 is already in the build environment and in the PyInstaller bundle. No new dependency needed.

### 7f. VSIX Size Impact
| Scenario | Model Size | VSIX Change |
|----------|-----------|-------------|
| Current (MiniLM FP32) | 86.2 MB | baseline |
| BGE FP32 | ~440 MB | **+354 MB** (too large) |
| **BGE INT8** | **~110 MB** | **+24 MB** (acceptable) |

INT8 quantization is essential for VSIX size.

### 7g. No Rollback Mechanism
There is currently **no way to switch embedding providers** without losing data. Phase 1 must introduce a config flag + Phase 4 must add index metadata validation to prevent silent corruption.

---

## 8. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Existing indexes silently corrupted by dim mismatch | **CRITICAL** | Phase 4: index metadata + mismatch refusal |
| Score threshold drift (768-dim cosine ≠ 384-dim cosine) | **HIGH** | Phase 6: full retest with golden queries; retune if needed |
| VSIX size bloat | **MEDIUM** | INT8 quantization limits increase to ~24 MB |
| PyTorch import at runtime (optimum/transformers) | **HIGH** | Must NOT import torch; use tokenizers + onnxruntime only |
| Build reproducibility | **MEDIUM** | Phase 2: deterministic build script with version pinning |
| Rollback breaks user KBs | **MEDIUM** | Phase 4: provider ID in index metadata; refuse mismatch |

---

## 9. Files That Must Change

| Phase | File | Change |
|-------|------|--------|
| 1 | `config/settings.py` | Add `embed_provider`, `embed_model_path`, `embed_dims` |
| 1 | NEW: `backend/vector/embedding_provider.py` | Abstract interface + factory |
| 1 | `backend/vector/store.py` | Accept provider from config instead of hardcoded |
| 1 | `backend/retrieval/term_registry.py` | Use provider instead of `DefaultEmbeddingFunction` |
| 2 | NEW: `scripts/model_build/build_bge_onnx_int8.ps1` | Build-time model pipeline |
| 2 | NEW: `assets/models/bge-base-en-v1.5/onnx-int8/` | Model artifacts |
| 3 | NEW: `backend/vector/bge_onnx_provider.py` | BGE ONNX INT8 runtime |
| 4 | `backend/vector/store.py` | Index metadata storage + validation |
| 4 | `cli/main.py` | `--rebuild-index` flag |
| 5 | `packaging/kts_backend.spec` | Bundle BGE model artifacts |
| 5 | `backend/vector/store.py` or provider | Resolve bundled path at runtime |
| 6 | Tests | Full retest with 3 source folders |

---

## 10. Decision Points for Discussion

**Before proceeding to Phase 1, these decisions need alignment:**

1. **Default provider after migration**: Should the default flip to `bge_onnx_int8` immediately, or remain `legacy_chroma_default` with opt-in?
   - Recommendation: Default remains `legacy_chroma_default` until Phase 6 validates. Then flip.

2. **Existing user KBs**: When a user upgrades their VSIX, their existing `.kts/vectors/chroma` index is invalid.
   - Option A: Auto-rebuild on first query (slow, silent)
   - Option B: Refuse with clear error + `kts reindex` command
   - Recommendation: **Option B** — explicit is better

3. **BGE query prefix**: BGE-base-en-v1.5 recommends prepending `"Represent this sentence: "` for queries. Do we want to handle this in the provider or let it be implicit?
   - Recommendation: Provider handles it internally; caller doesn't need to know

4. **Term registry compatibility**: Term registry caches 384-dim embeddings in JSON. On provider switch, these are invalid.
   - Recommendation: Invalidate and rebuild automatically on mismatch

5. **Keep MiniLM in VSIX?**: If we ship BGE, do we also keep MiniLM for rollback?
   - Recommendation: **No** — ship only one model to keep VSIX small. Rollback means re-downloading MiniLM via ChromaDB default behavior (requires network).
   - Alternative: Ship both models (+87 MB). Safer but larger.

6. **VSIX size budget**: Current = 222.63 MB. BGE INT8 adds ~24 MB net. Acceptable?
