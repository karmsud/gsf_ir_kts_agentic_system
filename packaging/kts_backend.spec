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
    'config',
    'config.settings',
]

# Add common dependencies (only packages actually imported by the code)
common_hidden_imports = [
    'docx',
    'pptx',
    'fitz',
    'bs4',
    'yaml',
    'click',
    'tqdm',
]

# Collect data files
datas = [
    (os.path.join(repo_root, 'config', 'taxonomy_rules.json'), 'config'),
    (os.path.join(repo_root, 'config', 'file_share_paths.json'), 'config'),
]

# Try to include prompts if they exist
prompts_dir = os.path.join(repo_root, 'prompts')
if os.path.exists(prompts_dir):
    datas.append((prompts_dir, 'prompts'))

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
        'numpy',
        'torch',
        'transformers',
        'sentence_transformers',
        'sklearn',
        'scikit-learn',
        'tiktoken',
        'networkx',
        'chromadb',
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
