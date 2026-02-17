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

# Collect all backend modules
backend_hidden_imports = [
    'cli',
    'cli.main',
    'backend',
    'backend.agents',
    'backend.agents.crawler_agent',
    'backend.agents.ingestion_agent',
    'backend.agents.retrieval_agent',
    'backend.agents.taxonomy_agent',
    'backend.common',
    'backend.common.doc_types',
    'backend.common.models',
    'backend.graph',
    'backend.ingestion',
    'backend.ingestion.base',
    'backend.ingestion.markdown',
    'backend.ingestion.docx_converter',
    'backend.ingestion.pdf_converter',
    'backend.ingestion.png_converter',
    'backend.ingestion.csv_converter',
    'backend.ingestion.config_converter',
    'backend.vector',
    'backend.vector.chunker',
    'backend.vector.embedder',
    'backend.vector.store',
    'backend.retrieval',
    'backend.retrieval.query_expander',
    'backend.retrieval.cross_encoder',
    'backend.retrieval.term_registry',
    'backend.ingestion.ner_extractor',
    'config',
    'config.settings',
]

# Add common dependencies (only packages actually imported by the code)
# NOTE: Processor-specific packages are excluded and bundled in separate extensions
common_hidden_imports = [
    # Base converters (included in core)
    'bs4',            # Core: HTML parsing
    'yaml',           # Core: YAML/INI config parsing
    # NOTE: json, csv are stdlib - no import needed
    
    # Core functionality
    'click',          # Core: CLI framework
    'tqdm',           # Core: progress bars
    'networkx',       # Core: graph operations
    
    # Vector database and embeddings — collect chromadb submodules selectively
    # to avoid dynamic-import failures while keeping bundle size reasonable.
    # Excludes: test, server, async, fastapi, grpc modules (not needed locally).
    *[m for m in collect_submodules('chromadb')
      if not any(x in m for x in ('test', 'server', 'async', 'fastapi', 'cli.cli'))],
    'posthog',                                # posthog SDK (chromadb dependency)
    'onnxruntime',    # Core: ONNX runtime for embeddings
    'tokenizers',     # Core: tokenization
    
    # EXCLUDED - in processor extensions:
    # 'docx',   # → office processor extension
    # 'pptx',   # → office processor extension
    # 'fitz',   # → pdf processor extension
    # 'spacy',  # → nlp processor extension
]

# Collect data files
datas = [
    (os.path.join(repo_root, 'config', 'taxonomy_rules.json'), 'config'),
    (os.path.join(repo_root, 'config', 'file_share_paths.json'), 'config'),
    (os.path.join(repo_root, 'config', 'acronyms.json'), 'config'),
]

# Try to include prompts if they exist
prompts_dir = os.path.join(repo_root, 'prompts')
if os.path.exists(prompts_dir):
    datas.append((prompts_dir, 'prompts'))

# Bundle ChromaDB embedding model for offline operation
# Check common cache locations
model_cache_paths = []
if sys.platform == "win32":
    localappdata = os.environ.get('LOCALAPPDATA')
    if localappdata:
        model_cache_paths.append(os.path.join(localappdata, 'chroma', 'onnx_models'))

# Also check user home
home = os.path.expanduser('~')
model_cache_paths.extend([
    os.path.join(home, '.cache', 'chroma', 'onnx_models'),
    os.path.join(home, '.chroma', 'onnx_models'),
])

# Find and bundle the model cache
for model_cache in model_cache_paths:
    if os.path.exists(model_cache) and os.listdir(model_cache):
        datas.append((model_cache, 'chroma_models'))
        print(f"[BUILD] Bundling ChromaDB model from: {model_cache}")
        break
else:
    print("[BUILD WARNING] ChromaDB model cache not found!")
    print("[BUILD WARNING] Run: python scripts/download_chromadb_model.py")
    print("[BUILD WARNING] System will require internet on first run.")

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
        'matplotlib',
        'scipy',
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
        # Processor-specific packages (bundled in separate extensions):
        'docx',           # → office processor
        'pptx',           # → office processor
        'PIL',            # → office processor (Pillow)
        'Pillow',         # → office processor
        'lxml',           # → office processor (XML for docx/pptx)
        'fitz',           # → pdf processor (PyMuPDF)
        'pymupdf',        # → pdf processor
        'spacy',          # → nlp processor
        'blis',           # → nlp processor (spaCy dependency)
        'thinc',          # → nlp processor (spaCy dependency)
        # NOTE: PIL/Pillow must NOT be excluded — python-pptx depends on it
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
