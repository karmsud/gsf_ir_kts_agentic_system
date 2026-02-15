from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path

import click

from config import load_config
from backend.agents import (
    ChangeImpactAgent,
    CrawlerAgent,
    FreshnessAgent,
    GraphBuilderAgent,
    IngestionAgent,
    RetrievalService,
    TaxonomyAgent,
    TrainingPathAgent,
    VersionAgent,
    VisionAgent,
)
from backend.common.manifest import ManifestStore
from backend.common.models import FileInfo


def _serialize(value):
    if is_dataclass(value):
        return {k: _serialize(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    return value


def _ctx(root: str | None = None):
    if root:
        Path(root).mkdir(parents=True, exist_ok=True)
    config = load_config(Path(root) if root else None)
    return config


@click.group()
@click.version_option(version="1.1.0", prog_name="kts-backend")
def cli():
    pass


@cli.command()
@click.option("--paths", multiple=True, help="One or more source paths")
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--force", is_flag=True, default=False)
def crawl(paths, dry_run, force):
    config = _ctx()
    crawler = CrawlerAgent(config)
    result = crawler.execute({"paths": list(paths) if paths else config.source_paths, "dry_run": dry_run, "force": force})

    changes = result.data["changes"]
    if not dry_run:
        manifest = ManifestStore(config.manifest_path)
        current_infos = changes.new_files + changes.modified_files
        manifest.upsert_files(current_infos)
        manifest.remove_paths([row.path for row in changes.deleted_files])

    click.echo(json.dumps(_serialize(result.data), indent=2))


@cli.command()
@click.option("--paths", multiple=True, help="One or more files or folders to ingest")
def ingest(paths):
    config = _ctx()
    ingestion = IngestionAgent(config)
    taxonomy = TaxonomyAgent(config)
    graph_builder = GraphBuilderAgent(config)
    vision = VisionAgent(config)
    manifest = ManifestStore(config.manifest_path)

    source_paths: list[Path] = []
    
    # If no paths provided, ingest all pending files from manifest (doc_id is not set OR explicit request)
    if not paths:
        manifest_data = manifest.load()
        for file_path, file_info in manifest_data.get("files", {}).items():
            if not file_info.get("doc_id"):  # Not yet ingested
                p = Path(file_path)
                if p.exists() and p.suffix.lower() in config.supported_extensions:
                    source_paths.append(p)
    else:
        # Explicit paths provided
        for raw in paths:
            p = Path(raw)
            if p.is_dir():
                source_paths.extend([file for file in p.rglob("*") if file.is_file()])
            elif p.is_file():
                source_paths.append(p)

    ingested_summary = []
    
    # Pre-load manifest once for efficiency if many files
    manifest_data = manifest.load()

    for source in source_paths:
        if source.suffix.lower() not in config.supported_extensions:
            continue
            
        # Lookup existing doc_id if available to update same document
        s_abs = str(source.resolve())
        existing_info = manifest_data.get("files", {}).get(s_abs)
        target_doc_id = existing_info.get("doc_id") if existing_info else None
        
        click.echo(f"Ingesting {source.name}... (Target ID: {target_doc_id or 'Auto'})")
        
        # Call Ingestion Agent
        ingest_result = ingestion.execute({"path": str(source), "doc_id": target_doc_id})
        
        if not ingest_result.success or "document" not in ingest_result.data:
            click.echo(f"Skipping {source.name}: {ingest_result.data.get('error', 'Unknown error')}")
            continue
            
        document = ingest_result.data["document"]
        
        # Robustness: Ensure manifest has source_id and doc_id updated
        # Reload manifest in case parallel updates (unlikely here but good practice)
        manifest_data = manifest.load()
        if s_abs in manifest_data.get("files", {}):
             info = manifest_data["files"][s_abs]
             info["doc_id"] = document.doc_id
             info["status"] = "active"
             # If source_id missing, generate based on content hash
             if not info.get("source_id"):
                 from backend.common.hashing import sha256_file
                 # Re-hashing here is expensive but safer for source_id generation if not done by crawler.
                 info["source_id"] = f"src_{sha256_file(source)[:16]}"
             manifest.save(manifest_data)
        elif s_abs not in manifest_data.get("files", {}) and target_doc_id is None:
             # Case: Ingesting a file not in manifest (e.g. manual path not crawled)
             from backend.common.hashing import sha256_file
             from datetime import datetime, timezone
             file_hash = sha256_file(source)
             source_id = f"src_{file_hash[:16]}"
             new_info = FileInfo(
                 path=s_abs,
                 filename=source.name,
                 extension=source.suffix.lower(),
                 size_bytes=source.stat().st_size,
                 modified_time=datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc).isoformat(),
                 hash=file_hash,
                 doc_id=document.doc_id, # Doc ID from ingestion result
                 source_id=source_id,
                 status="active",
                 last_seen=datetime.now(timezone.utc).isoformat(),
                 retry_count=0
             )
             manifest.upsert_files([new_info])

        # Classification & Metadata
        classify_result = taxonomy.execute({"text": document.extracted_text, "filename": source.name})
        
        # Read metadata from disk to update it (it was written by ingestion agent)
        metadata_path = Path(document.metadata_path)
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["doc_type"] = classify_result.data.get("doc_type", "UNKNOWN")
            metadata["tags"] = classify_result.data.get("tags", [])
            
            # Simple keyword extraction (fallback)
            lowered = document.extracted_text.lower()
            metadata["tools"] = [tool for tool in ["ToolX", "ToolY", "ToolZ"] if tool.lower() in lowered]
            metadata["processes"] = [proc for proc in ["AuthProcess", "DeployProcess", "SupportProcess"] if proc.lower().replace("process", "") in lowered]
            metadata["topics"] = [
                topic
                for topic in ["onboarding", "authentication", "deployment", "support", "incident"]
                if topic in lowered
            ]
            metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            
            # Update Vector Store Metadata
            ingestion.vector_store.update_doc_metadata(document.doc_id, doc_type=metadata["doc_type"], tags=metadata["tags"])
            
            # Graph Builder
            graph_builder.execute({"document": document, "metadata": metadata})

        # Vision
        vision.execute({"operation": "initialize", "doc_id": document.doc_id, "image_paths": document.image_paths, "descriptions": {}})

        ingested_summary.append(
            {
                "doc_id": document.doc_id,
                "path": str(source),
                "chunk_count": ingest_result.data.get("chunk_count", 0),
                "doc_type": metadata.get("doc_type", "UNKNOWN"),
            }
        )

    click.echo(json.dumps({"ingested": ingested_summary, "count": len(ingested_summary)}, indent=2))


@cli.command()
@click.option("--dry-run", is_flag=True, default=False)
def vacuum(dry_run):
    """Garbage collects orphaned documents and vector chunks."""
    import shutil
    from backend.vector import VectorStore

    config = _ctx()
    manifest_store = ManifestStore(config.manifest_path)
    manifest = manifest_store.load()
    files_map = manifest.get("files", {})

    active_doc_ids = set()
    paths_to_remove = []

    # 1. Identify active doc_ids and deleted entries
    for path, info in files_map.items():
        if info.get("status") == "deleted":
            paths_to_remove.append(path)
        elif info.get("doc_id"):
            active_doc_ids.add(info["doc_id"])

    click.echo(f"Found {len(active_doc_ids)} active documents.")
    click.echo(f"Found {len(paths_to_remove)} deleted entries in manifest.")

    # 2. Identify Orphaned Folders
    docs_root = Path(config.knowledge_base_path) / "documents"
    orphaned_folders = []
    if docs_root.exists():
        for item in docs_root.iterdir():
            if item.is_dir() and item.name not in active_doc_ids:
                orphaned_folders.append(item)

    click.echo(f"Found {len(orphaned_folders)} orphaned document folders.")

    # 3. Prune Vector Store
    vector_store = VectorStore(config.chroma_persist_dir)
    
    if dry_run:
        click.echo("[DRY RUN] Would remove:")
        for p in paths_to_remove:
            click.echo(f"  - Manifest Entry: {p}")
        for f in orphaned_folders:
            click.echo(f"  - Doc Folder: {f.name}")
        click.echo("  - Orphaned vector chunks (count unknown without scan)")
    else:
        # Commit
        if paths_to_remove:
            manifest_store.remove_paths(paths_to_remove)
            click.echo(f"Removed {len(paths_to_remove)} manifest entries.")
        
        for f in orphaned_folders:
            shutil.rmtree(f)
            click.echo(f"Removed folder: {f.name}")
            
        pruned_count = vector_store.prune_orphans(active_doc_ids)
        click.echo(f"Removed {pruned_count} orphaned vector chunks.")


@cli.command()
@click.argument("query")
@click.option("--max-results", default=5, show_default=True)
@click.option("--doc-type", default=None)
@click.option("--tool-filter", default=None)
def search(query, max_results, doc_type, tool_filter):
    config = _ctx()
    retrieval = RetrievalService(config)
    result = retrieval.execute({"query": query, "max_results": max_results, "doc_type_filter": doc_type, "tool_filter": tool_filter})
    click.echo(json.dumps(_serialize(result.data["search_result"]), indent=2))


@cli.command()
@click.option("--topic", required=True)
@click.option("--level", default="beginner", show_default=True)
def training(topic, level):
    config = _ctx()
    agent = TrainingPathAgent(config)
    result = agent.execute({"topic": topic, "level": level})
    click.echo(json.dumps(_serialize(result.data["training_path"]), indent=2))


@cli.command()
@click.option("--entity", required=True)
def impact(entity):
    config = _ctx()
    agent = ChangeImpactAgent(config)
    result = agent.execute({"entity": entity})
    click.echo(json.dumps(_serialize(result.data["impact_report"]), indent=2))


@cli.command(name="freshness")
@click.option("--scope", default="all")
@click.option("--threshold-days", default=None, type=int)
@click.option("--include-images/--exclude-images", default=True)
def freshness_cmd(scope, threshold_days, include_images):
    config = _ctx()
    agent = FreshnessAgent(config)
    payload = {"scope": scope, "include_images": include_images}
    if threshold_days is not None:
        payload["threshold_days"] = threshold_days
    result = agent.execute(payload)
    click.echo(json.dumps(_serialize(result.data["freshness_report"]), indent=2))


@cli.group()
def describe():
    """Vision workflow operations."""


@describe.command(name="pending")
@click.option("--doc-id", default=None)
def describe_pending(doc_id):
    config = _ctx()
    agent = VisionAgent(config)
    if doc_id:
        result = agent.execute({"operation": "list_pending", "doc_id": doc_id})
        click.echo(json.dumps(_serialize(result.data), indent=2))
        return

    docs_root = Path(config.knowledge_base_path) / "documents"
    summary = []
    for doc_dir in docs_root.glob("*"):
        if not doc_dir.is_dir():
            continue
        result = agent.execute({"operation": "list_pending", "doc_id": doc_dir.name})
        if result.data.get("pending_count", 0):
            summary.append({"doc_id": doc_dir.name, **_serialize(result.data)})
    click.echo(json.dumps({"documents": summary, "count": len(summary)}, indent=2))


@describe.command(name="complete")
@click.option("--doc-id", required=True)
@click.option("--descriptions-file", required=True)
def describe_complete(doc_id, descriptions_file):
    config = _ctx()
    agent = VisionAgent(config)
    payload = json.loads(Path(descriptions_file).read_text(encoding="utf-8"))
    result = agent.execute({"operation": "complete", "doc_id": doc_id, "descriptions": payload})
    click.echo(json.dumps(_serialize(result.data), indent=2))


@describe.command(name="status")
@click.option("--doc-id", required=True)
def describe_status(doc_id):
    config = _ctx()
    agent = VisionAgent(config)
    result = agent.execute({"operation": "status", "doc_id": doc_id})
    click.echo(json.dumps(_serialize(result.data), indent=2))


@cli.command(name="status")
def status_cmd():
    config = _ctx()
    manifest = ManifestStore(config.manifest_path).load()
    graph_stats = GraphBuilderAgent(config).builder.store.load()
    documents_count = len([item for item in (Path(config.knowledge_base_path) / "documents").glob("*") if item.is_dir()])
    click.echo(
        json.dumps(
            {
                "documents": documents_count,
                "manifest_files": len(manifest.get("files", {})),
                "graph_nodes": len(graph_stats.get("nodes", {})),
                "graph_edges": len(graph_stats.get("edges", [])),
            },
            indent=2,
        )
    )


@cli.command(name="diff")
@click.option("--old-file", required=True)
@click.option("--new-file", required=True)
def diff_cmd(old_file, new_file):
    config = _ctx()
    agent = VersionAgent(config)
    old_text = Path(old_file).read_text(encoding="utf-8", errors="ignore")
    new_text = Path(new_file).read_text(encoding="utf-8", errors="ignore")
    result = agent.execute({"old_text": old_text, "new_text": new_text, "old_version": 1})
    click.echo(json.dumps(result.data, indent=2))


if __name__ == "__main__":
    cli()
