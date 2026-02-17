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

# Bundle ChromaDB embedding model for offline operation
chroma_model_cached = os.path.join(base_path, 'models', 'chroma', 'all-MiniLM-L6-v2')
if os.path.exists(chroma_model_cached) and os.listdir(chroma_model_cached):
    # Mirror the structure ChromaDB expects at ~/.cache/chroma/onnx_models/
    datas.append((chroma_model_cached, os.path.join('chroma_models', 'all-MiniLM-L6-v2')))
    print(f"[BUILD] Bundling ChromaDB model from: {chroma_model_cached}")
else:
    # Fallback: Check user cache locations (ChromaDB default download path)
    from pathlib import Path as _Path
    user_cache = _Path.home() / '.cache' / 'chroma' / 'onnx_models' / 'all-MiniLM-L6-v2'
    if user_cache.exists() and any(user_cache.iterdir()):
        datas.append((str(user_cache), os.path.join('chroma_models', 'all-MiniLM-L6-v2')))
        print(f"[BUILD] Bundling ChromaDB model from user cache: {user_cache}")
    else:
        print("[BUILD WARNING] ChromaDB model not found!")
        print("[BUILD WARNING] Run: .\\scripts\\download_models.ps1")
        print("[BUILD WARNING] System will require internet on first run.")

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
