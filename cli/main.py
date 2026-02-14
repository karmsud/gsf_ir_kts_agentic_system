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
    
    # If no paths provided, ingest all pending files from manifest (doc_id is None)
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
    for source in source_paths:
        if source.suffix.lower() not in config.supported_extensions:
            continue

        ingest_result = ingestion.execute({"path": str(source)})
        document = ingest_result.data["document"]

        classify_result = taxonomy.execute({"text": document.extracted_text, "filename": source.name})
        metadata_path = Path(document.metadata_path)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["doc_type"] = classify_result.data["doc_type"]
        metadata["tags"] = classify_result.data["tags"]

        lowered = document.extracted_text.lower()
        metadata["tools"] = [tool for tool in ["ToolX", "ToolY", "ToolZ"] if tool.lower() in lowered]
        metadata["processes"] = [proc for proc in ["AuthProcess", "DeployProcess", "SupportProcess"] if proc.lower().replace("process", "") in lowered]
        metadata["topics"] = [
            topic
            for topic in ["onboarding", "authentication", "deployment", "support", "incident"]
            if topic in lowered
        ]
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        ingestion.vector_store.update_doc_metadata(document.doc_id, doc_type=metadata["doc_type"], tags=metadata["tags"])

        graph_builder.execute({"document": document, "metadata": metadata})
        vision.execute({"operation": "initialize", "doc_id": document.doc_id, "image_paths": document.image_paths, "descriptions": {}})

        file_info = FileInfo(
            path=str(source.resolve()),
            filename=source.name,
            extension=source.suffix.lower(),
            size_bytes=source.stat().st_size,
            modified_time="",
            hash="",
            doc_id=document.doc_id,
        )
        manifest.upsert_files([file_info])

        ingested_summary.append(
            {
                "doc_id": document.doc_id,
                "path": str(source),
                "chunk_count": ingest_result.data["chunk_count"],
                "doc_type": metadata["doc_type"],
            }
        )

    click.echo(json.dumps({"ingested": ingested_summary, "count": len(ingested_summary)}, indent=2))


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
