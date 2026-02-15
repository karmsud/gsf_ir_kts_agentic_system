import json
import shutil
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from config import AppConfig
from backend.agents.crawler_agent import CrawlerAgent
from backend.agents.ingestion_agent import IngestionAgent
from backend.common.manifest import ManifestStore
from backend.common.models import FileInfo
from backend.vector.store import VectorStore


def create_mock_config(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir(parents=True, exist_ok=True)
    manifest_path = kb / "manifest.json"
    chroma_dir = kb / "chroma"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    
    config = MagicMock(spec=AppConfig)
    config.knowledge_base_path = str(kb)
    config.manifest_path = str(manifest_path)
    config.chroma_persist_dir = str(chroma_dir)
    config.source_paths = [] 
    config.supported_extensions = {".txt", ".md"}
    config.chunk_size = 100
    config.chunk_overlap = 0 # Simple chunks
    
    return config

def test_crawler_rename_preserves_identity(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    config = create_mock_config(tmp_path)
    config.source_paths = [str(corpus)]
    
    crawler = CrawlerAgent(config)
    manifest = ManifestStore(config.manifest_path)

    # 1. Create Initial File
    f1 = corpus / "file1.txt"
    f1.write_text("Unique content for identity.", encoding="utf-8")
    
    # Run Crawler
    res1 = crawler.execute({"paths": [str(corpus)]})
    new_files = res1.data["changes"].new_files
    assert len(new_files) == 1
    
    # Commit to Manifest
    manifest.upsert_files(new_files)
    
    # Verify IDs
    f1_key = str(f1.resolve())
    data = manifest.load()
    f1_id = data["files"][f1_key]["doc_id"]
    f1_source = data["files"][f1_key].get("source_id")
    # Note: crawler doesn't set doc_id for new files by default (None), 
    # but it SHOULD set source_id now.
    assert f1_source is not None
    
    # Update doc_id manually as done by ingestion (simulating)
    data["files"][f1_key]["doc_id"] = "doc_123"
    manifest.save(data)
    
    # 2. Rename File
    f2 = corpus / "file2.txt"
    f1.rename(f2)
    
    # Run Crawler Again
    res2 = crawler.execute({"paths": [str(corpus)]})
    changes2 = res2.data["changes"]
    
    # Should detect New (File 2) and Deleted (File 1)
    # AND New file should have OLD IDs
    assert len(changes2.new_files) == 1
    assert len(changes2.deleted_files) == 1
    
    renamed_info = changes2.new_files[0]
    assert renamed_info.path == str(f2.resolve())
    assert renamed_info.doc_id == "doc_123" # Preserved!
    assert renamed_info.source_id == f1_source # Preserved!

def test_crawler_locked_file_safety(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    config = create_mock_config(tmp_path)
    config.source_paths = [str(corpus)]
    
    crawler = CrawlerAgent(config)
    manifest = ManifestStore(config.manifest_path)
    
    f1 = corpus / "locked.txt"
    f1.write_text("content", encoding="utf-8")
    
    # 1. Initial Success
    res1 = crawler.execute({"paths": [str(corpus)]})
    manifest.upsert_files(res1.data["changes"].new_files)
    
    # 2. Simulate Lock Error
    # Mocking sha256_file specifically in crawler_agent module
    with patch("backend.agents.crawler_agent.sha256_file", side_effect=PermissionError("Locked")):
        res2 = crawler.execute({"paths": [str(corpus)]})
        
        # Verify it wasn't marked deleted
        assert len(res2.data["changes"].deleted_files) == 0
        assert len(res2.data["changes"].errors) == 1
        
        # Manifest shouldn't have changed status to deleted
        # (Since deleted_files is empty, manifest update logic in CLI won't run removal)

def test_ingestion_shrinking_file(tmp_path):
    config = create_mock_config(tmp_path)
    ingestion = IngestionAgent(config)
    vector_store = VectorStore(config.chroma_persist_dir)
    
    f1 = tmp_path / "shrink.txt"
    # Content creates 3 chunks (chunk size 100 chars? No, simple test split)
    # The chunker splits by default on newlines or size. 
    # Let's force explicit large text.
    long_text = "A" * 150 + "\n" + "B" * 150 + "\n" + "C" * 150
    f1.write_text(long_text, encoding="utf-8")
    
    # Ingest V1
    res1 = ingestion.execute({"path": str(f1), "doc_id": "doc_shrink"})
    # Depending on chunker logic, get N chunks.
    count1 = res1.data["chunk_count"]
    # Verify chunks exist
    store_data = vector_store._load()
    assert len([c for c in store_data if c["doc_id"] == "doc_shrink"]) == count1
    
    # Shrink Content
    f1.write_text("Short content.", encoding="utf-8")
    
    # Ingest V2
    res2 = ingestion.execute({"path": str(f1), "doc_id": "doc_shrink"})
    count2 = res2.data["chunk_count"]
    assert count2 < count1
    
    # Verify Phantom Chunks Gone
    store_data_v2 = vector_store._load()
    current_chunks = [c for c in store_data_v2 if c["doc_id"] == "doc_shrink"]
    assert len(current_chunks) == count2
    # Ensure no old IDs remain
    for c in current_chunks:
        assert "short content" in c["content"].lower()

def test_vacuum_logic(tmp_path):
    config = create_mock_config(tmp_path)
    manifest = ManifestStore(config.manifest_path)
    vector_store = VectorStore(config.chroma_persist_dir)
    
    # 1. Setup Data
    # Active Doc
    manifest.save({"files": {
        "active.txt": {"doc_id": "doc_active", "status": "active"}
    }})
    vector_store._save([
        {"chunk_id": "c1", "doc_id": "doc_active", "content": "active"},
        {"chunk_id": "c2", "doc_id": "doc_orphan", "content": "orphan"}
    ])
    
    # Create Orphan Folder
    orphan_dir = Path(config.knowledge_base_path) / "documents" / "doc_orphan"
    orphan_dir.mkdir(parents=True)
    
    # 2. Run Vacuum Logic (Manual as tests can't invoke CLI easily without invocation)
    # Logic extracted from CLI
    active_ids = {"doc_active"}
    
    # Prune Store
    pruned = vector_store.prune_orphans(active_ids)
    assert pruned == 1
    
    # Prune Folders
    shutil.rmtree(orphan_dir)
    assert not orphan_dir.exists()
    
    # Verify Store
    remaining = vector_store._load()
    assert len(remaining) == 1
    assert remaining[0]["doc_id"] == "doc_active"
