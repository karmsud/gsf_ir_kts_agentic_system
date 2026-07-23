# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for KTS Backend
Builds a onedir distribution for Windows x64
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Determine base path
base_path = os.path.abspath(SPECPATH)
repo_root = os.path.dirname(base_path)  # Parent of packaging/

# Collect all backend modules dynamically (avoids stale/missing imports)
backend_hidden_imports = [
    *collect_submodules('backend'),
    *collect_submodules('cli'),
    'config',
    'config.settings',
    # Phase 6: Explicit imports for ItemExtractor framework + dual stores
    'backend.extraction',
    'backend.extraction.item_extractor_base',
    'backend.extraction.legal_item_extractor',
    'backend.extraction.technical_item_extractor',
    'backend.extraction.research_item_extractor',
    'backend.extraction.generic_item_extractor',
    'backend.vector.dual_vector_store',
    'backend.graph.enhanced_graph_builder',
    'backend.graph.pagerank',
    'backend.retrieval.hybrid_reranker',
    'backend.retrieval.iterative_orchestrator',
    'backend.common.config_phase6',
    'backend.common.explainability',
    # Phase 5 WS-1: Embedding provider abstraction
    'backend.vector.embedding_provider',
    'backend.vector.bge_onnx_provider',
    # ABS Waterfall platform: store + services + IPC entry point
    'backend.abs.serve',
    'backend.abs.store',
    'backend.abs.store.schema',
    'backend.abs.store.deal_store',
    'backend.abs.services',
    'backend.abs.services.dispatcher',
    'backend.abs.services.ipc_server',
    'backend.abs.services.deal_service',
    'backend.abs.services.ingestion_service',
    'backend.abs.services.definition_service',
    'backend.abs.services.sep_service',
    'backend.abs.services.governing_doc_service',
    'backend.abs.services.qa_service',
    'backend.abs.services.model_service',
    'backend.abs.services.reporting_service',
    'backend.abs.services.pdf_render',
]

# Add common dependencies - ALL INCLUDED for single VSIX build
common_hidden_imports = [
    # Base converters
    'bs4',            # HTML parsing
    'yaml',           # YAML/INI config parsing
    
    # Core functionality
    'click',          # CLI framework
    'tqdm',           # Progress bars
    'tqdm.auto',      # tqdm auto-select
    'networkx',       # Graph operations
    'scipy',          # PageRank (networkx dependency)
    'scipy.sparse',
    'scipy.sparse.linalg',
    
    # Vector database and embeddings — collect chromadb submodules
    # Excludes: test, server, async, fastapi, grpc modules (not needed locally).
    *[m for m in collect_submodules('chromadb')
      if not any(x in m for x in ('test', 'server', 'async', 'fastapi', 'cli.cli'))],
    'chromadb.api',
    'chromadb.db.impl.sqlite',
    'chromadb.segment.impl.vector.local_hnsw',
    'chromadb.segment.impl.vector.local_persistent_hnsw',
    'posthog',        # posthog SDK (chromadb dependency)
    'onnxruntime',    # ONNX runtime for embeddings
    'onnxruntime.capi._pybind_state',
    'tokenizers',     # Tokenization
    'sqlite3',        # SQLite for ChromaDB
    
    # Document processors - NOW INCLUDED in single VSIX
    'docx',           # DOCX converter
    'pptx',           # PPTX converter
    'PIL',            # Image processing (Pillow)
    'PIL.Image',
    'PIL.ImageDraw',
    'lxml',           # XML parsing for office docs
    'lxml.etree',
    'fitz',           # PDF parsing (PyMuPDF)
    'pymupdf',        # PyMuPDF alternative import
    'olefile',        # Legacy .doc (OLE2 binary) parsing
    
    # NLP - spaCy for NER
    'spacy',          # spaCy NER
    'spacy.lang.en',
    'blis',           # spaCy dependency
    'thinc',          # spaCy dependency
    'catalogue',      # spaCy dependency
    'cymem',          # spaCy dependency
    'murmurhash',     # spaCy dependency
    'preshed',        # spaCy dependency
    'srsly',          # spaCy dependency
    'wasabi',         # spaCy dependency
]

# Collect data files
datas = [
    (os.path.join(repo_root, 'config', 'taxonomy_rules.json'), 'config'),
    (os.path.join(repo_root, 'config', 'file_share_paths.json'), 'config'),
    (os.path.join(repo_root, 'config', 'acronyms.json'), 'config'),
    (os.path.join(repo_root, 'backend', 'data'), 'backend/data'),
]

# NOTE: Legacy ChromaDB MiniLM-L6-v2 model removed in Phase 5 WS-1
# Now using BGE ONNX INT8 (768-dim) exclusively - see below

# Bundle Cross-Encoder ONNX model for high-precision reranking
ce_model_cached = os.path.join(base_path, 'models', 'cross_encoder')
if os.path.exists(ce_model_cached) and os.path.exists(os.path.join(ce_model_cached, 'model.onnx')):
    datas.append((ce_model_cached, os.path.join('models', 'cross-encoder')))
    print(f"[BUILD] Bundling Cross-Encoder ONNX model from: {ce_model_cached}")
else:
    print("[BUILD WARNING] Cross-encoder model not found at packaging/models/cross_encoder/")
    print("[BUILD WARNING] Cross-encoder reranking will be disabled at runtime.")
    print("[BUILD WARNING] Run: python scripts/download_cross_encoder.py to download.")

# Bundle spaCy model for offline NER
spacy_model_cached = os.path.join(base_path, 'models', 'spacy', 'en_core_web_sm')
if os.path.exists(spacy_model_cached):
    datas.append((spacy_model_cached, 'spacy_models/en_core_web_sm'))
    print(f"[BUILD] Bundling spaCy model from: {spacy_model_cached}")
else:
    # Try to find installed spacy model
    try:
        import en_core_web_sm
        spacy_model_path = en_core_web_sm.__path__[0]
        datas.append((spacy_model_path, 'spacy_models/en_core_web_sm'))
        print(f"[BUILD] Bundling spaCy model from site-packages: {spacy_model_path}")
    except ImportError:
        print("[BUILD WARNING] spaCy model (en_core_web_sm) not found!")
        print("[BUILD WARNING] Run: python scripts/download_models.ps1")
        print("[BUILD WARNING] NER features will not work.")

# Bundle BGE ONNX INT8 model for Phase 5 (REQUIRED - no fallback)
# 768-dim embeddings with better semantic understanding
bge_model_cached = os.path.join(base_path, 'models', 'bge')
if os.path.exists(bge_model_cached) and os.path.exists(os.path.join(bge_model_cached, 'model.onnx')):
    datas.append((bge_model_cached, os.path.join('models', 'bge-base-en-v1.5', 'onnx-int8')))
    print(f"[BUILD] Bundling BGE ONNX INT8 model from: {bge_model_cached}")
else:
    print("[BUILD ERROR] BGE model not found at packaging/models/bge/")
    print("[BUILD ERROR] This model is REQUIRED for the build.")
    print("[BUILD ERROR] Run: .\\scripts\\download_bge_model.ps1")
    raise FileNotFoundError("BGE ONNX INT8 model required. Run scripts/download_bge_model.ps1")


a = Analysis(
    ['backend_cli_entry.py'],
    pathex=[base_path, repo_root],
    binaries=[],
    datas=datas,
    hiddenimports=backend_hidden_imports + common_hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude large unused packages to save space
        'matplotlib',
        # 'scipy',  # DO NOT EXCLUDE - required by networkx PageRank
        'pytest',
        'IPython',
        'pandas',
        # 'numpy',  # DO NOT EXCLUDE - required by chromadb, onnxruntime
        'torch',
        'transformers',
        'sentence_transformers',
        'sklearn',
        'scikit-learn',
        'keybert',
        'nltk',
        'tiktoken',
        '_pytest',
        'setuptools',
        'distutils',
        # NOTE: docx, pptx, fitz, spacy are NOW INCLUDED for single VSIX
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='kts-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='kts-backend',
)
