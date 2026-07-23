from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from pathlib import Path

import click

logger = logging.getLogger("kts.cli")

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
from backend.vector import VectorStore
from backend.vector.embedding_provider import get_embedding_provider


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
@click.option("--doc-type", default=None, help="Override automatic doc_type classification (Phase 11.7 HITL).")
@click.option("--force", is_flag=True, default=False, help="Re-ingest all files even if unchanged (Phase 18).")
def ingest(paths, doc_type, force):
    from collections import defaultdict
    from config import scope_config

    config = _ctx()

    # Regime classifier for corpus-level regime detection
    from backend.ingestion.regime_classifier import RegimeClassifier

    source_paths: list[Path] = []
    ingest_root: Path | None = None

    # If no paths provided, ingest all pending files from manifest (single-scope mode)
    if not paths:
        manifest = ManifestStore(config.manifest_path)
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
                if ingest_root is None:
                    ingest_root = p.resolve()
                source_paths.extend([
                    file for file in p.rglob("*")
                    if file.is_file() and ".kts" not in file.parts
                ])
            elif p.is_file():
                source_paths.append(p)

    # ── Phase 12.1: Group files by scope (per-subfolder isolation) ─
    per_folder = getattr(config, 'per_folder_kts_enabled', True)

    if per_folder and ingest_root:
        root = ingest_root
        scope_groups: dict[Path | None, list[Path]] = defaultdict(list)
        for source in source_paths:
            resolved = source.resolve()
            try:
                relative = resolved.relative_to(root)
            except ValueError:
                scope_groups[None].append(source)
                continue
            parts = relative.parts
            if len(parts) <= 1:
                # File directly in root → root scope
                scope_groups[None].append(source)
            else:
                # Group by first subfolder under root
                scope_folder = root / parts[0]
                scope_groups[scope_folder].append(source)
        click.echo(f"[Phase 12.1] Per-folder isolation: {len(scope_groups)} scope(s) detected", err=True)
    else:
        scope_groups = {None: source_paths}

    all_ingested = []
    all_regime_results = []

    for scope_folder, scope_files in scope_groups.items():
        # ── Build scoped config for this folder ────────────────────
        if scope_folder is not None:
            scfg = scope_config(config, str(scope_folder / ".kts"))
            click.echo(f"── Scope: {scope_folder.name} → {scope_folder / '.kts'}", err=True)
        else:
            scfg = config

        ingestion = IngestionAgent(scfg)
        taxonomy = TaxonomyAgent(scfg)
        graph_builder = GraphBuilderAgent(scfg)
        vision = VisionAgent(scfg)
        manifest = ManifestStore(scfg.manifest_path)

        # Term registry for learned synonym generation
        from backend.retrieval.term_registry import TermRegistry
        term_registry = TermRegistry(scfg.knowledge_base_path)

        regime_results = []  # collect per-doc regime results for corpus vote
        ingested_summary = []

        # Pre-load manifest once for efficiency if many files
        manifest_data = manifest.load()

        for source in scope_files:
            if source.suffix.lower() not in config.supported_extensions:
                continue

            # Lookup existing doc_id if available to update same document
            s_abs = str(source.resolve())
            existing_info = manifest_data.get("files", {}).get(s_abs)
            target_doc_id = existing_info.get("doc_id") if existing_info else None

            # ── Phase 18: Skip unchanged files (ONLY with --force=false) ──
            # Change detection is handled by the JS-side crawl step which
            # decides whether to invoke ingest at all.  The CLI no longer
            # blocks re-ingestion by default because:
            #   1. "KTS: Ingest" is an explicit user action — they WANT to ingest.
            #   2. "KTS: Crawl & Ingest" already skips ingest when 0 changes.
            #   3. The hash-check here caused every ingest call to silently
            #      skip all files, making the Ingest command appear broken.
            # The --force flag is kept for forward compat but has no special
            # behavior now — all files are always processed when ingest runs.

            click.echo(f"Ingesting {source.name}... (Target ID: {target_doc_id or 'Auto'})", err=True)

            # Warn about large files
            try:
                fsize_mb = source.stat().st_size / (1024 * 1024)
                if fsize_mb > 20:
                    click.echo(f"  Large file: {fsize_mb:.1f} MB — this may take several minutes", err=True)
            except Exception:
                fsize_mb = 0

            # Call Ingestion Agent
            ingest_result = ingestion.execute({"path": str(source), "doc_id": target_doc_id})

            if not ingest_result.success or "document" not in ingest_result.data:
                click.echo(f"Skipping {source.name}: {ingest_result.data.get('error', 'Unknown error')}")
                continue

            document = ingest_result.data["document"]

            # Robustness: Ensure manifest has source_id and doc_id updated
            manifest_data = manifest.load()
            if s_abs in manifest_data.get("files", {}):
                 info = manifest_data["files"][s_abs]
                 info["doc_id"] = document.doc_id
                 info["status"] = "active"
                 if not info.get("source_id"):
                     from backend.common.hashing import sha256_file
                     info["source_id"] = f"src_{sha256_file(source)[:16]}"
                 manifest.save(manifest_data)
            elif s_abs not in manifest_data.get("files", {}) and target_doc_id is None:
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
                     doc_id=document.doc_id,
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

                # Phase 11.7: HITL doc_type override from CLI --doc-type flag
                if doc_type:
                    logger.info("HITL doc_type override: %s → %s (was %s)",
                                source.name, doc_type, metadata["doc_type"])
                    metadata["doc_type"] = doc_type
                    metadata["doc_type_source"] = "user"
                else:
                    metadata.setdefault("doc_type_source", "auto")

                # Collect regime result from ingestion agent's classification
                doc_regime = metadata.get("doc_regime", "UNKNOWN")
                if doc_regime and doc_regime != "UNKNOWN":
                    regime_results.append(doc_regime)

                # Regime→taxonomy override
                if doc_regime == "GOVERNING_DOC_LEGAL" and metadata["doc_type"] not in ("GOVERNING_DOC",):
                    logger.info("Regime override: %s → GOVERNING_DOC (regime=%s, taxonomy=%s)",
                                source.name, doc_regime, metadata["doc_type"])
                    metadata["doc_type"] = "GOVERNING_DOC"

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

                # Register keyphrases for learned synonym generation
                keyphrases = metadata.get("keyphrases", [])
                if keyphrases:
                    term_texts = [kp["text"] for kp in keyphrases]
                    term_registry.register_terms(term_texts, document.doc_id, metadata.get("doc_type", "UNKNOWN"))

            # Vision
            vision.execute({"operation": "initialize", "doc_id": document.doc_id, "image_paths": document.image_paths, "descriptions": {}})

            ingested_summary.append(
                {
                    "doc_id": document.doc_id,
                    "path": str(source),
                    "chunk_count": ingest_result.data.get("chunk_count", 0),
                    "doc_type": metadata.get("doc_type", "UNKNOWN"),
                    "extracted_image_count": ingest_result.data.get("extracted_image_count", 0),
                    "scope": scope_folder.name if scope_folder else "root",
                }
            )

        # ── Per-scope post-processing ─────────────────────────────
        # Rebuild learned synonym clusters after ingestion batch
        synonym_summary = term_registry.rebuild_synonyms()

        # Compute and persist corpus regime in graph for retrieval auto-detection
        corpus_regime = RegimeClassifier.corpus_regime(regime_results) if regime_results else "GENERIC_GUIDE"
        try:
            from backend.graph import GraphStore
            gs = GraphStore(scfg.graph_path)
            G = gs.load()
            G.graph["corpus_regime"] = corpus_regime
            gs.save(G)
        except Exception:
            pass  # graph persistence is best-effort

        if scope_folder is not None:
            click.echo(f"── Scope {scope_folder.name}: {len(ingested_summary)} docs, regime={corpus_regime}", err=True)

        all_ingested.extend(ingested_summary)
        all_regime_results.extend(regime_results)

    total_images = sum(d.get("extracted_image_count", 0) for d in all_ingested)
    overall_regime = RegimeClassifier.corpus_regime(all_regime_results) if all_regime_results else "GENERIC_GUIDE"

    click.echo(json.dumps({"ingested": all_ingested, "count": len(all_ingested), "total_images_pending": total_images, "corpus_regime": overall_regime}, indent=2))


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
    embedding_provider = get_embedding_provider(config)
    vector_store = VectorStore(config.chroma_persist_dir, embedding_provider=embedding_provider)
    
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
@click.option("--strict", is_flag=True, default=False, help="Enforce strict provenance (100% cited claims).")
@click.option("--no-graph-boost", is_flag=True, default=False)
@click.option("--no-auto-filter", is_flag=True, default=False)
@click.option("--no-term-resolution", is_flag=True, default=False, help="Disable term resolution pipeline.")
@click.option("--no-query-expansion", is_flag=True, default=False, help="Disable query expansion via synonyms.")
@click.option("--no-acronym-resolution", is_flag=True, default=False, help="Disable acronym expansion.")
@click.option("--regime-override", default=None, help="Force corpus regime (GOVERNING_DOC_LEGAL, GENERIC_GUIDE, MIXED).")
@click.option("--debug-level", type=click.IntRange(0, 2), default=None, help="Debug verbosity: 0=off, 1=summary, 2=verbose.")
@click.option("--explain", is_flag=True, default=False, help="Show scoring explanation per result.")
@click.option("--provenance-detail", is_flag=True, default=False, help="Include full provenance ledger in output.")
@click.option("--section-filter", default=None, help="Restrict results to a specific section heading.")
@click.option("--graph-only", is_flag=True, default=False, help="Use graph-based retrieval only (no vector search).")
@click.option("--deep", is_flag=True, default=False, help="Deep retrieval mode: more chunks per document, wider candidate pool.")
@click.option("--answer-text", default=None, help="Optional generated answer text to validate provenance against.")
@click.option("--session-id", default=None, help="Phase 10.1: Session ID for conversation memory.")
@click.option("--conversation-history", default=None, help="Phase 10.1: JSON-encoded conversation history.")
@click.option("--retrieval-mode", default=None, help="Phase 11.4: Retrieval mode (extract, audit, summary, compare, define).")
@click.option("--scope-override", default=None, help="Phase 12.2: Scope override for scoped retrieval.")
@click.option("--source-doc-hint", default=None, help="Phase 11.1: Source document hint from #file references.")
@click.option("--extra-queries", default=None, help="Phase 8.6: JSON-encoded list of multi-query variants.")
@click.option("--compare-scopes", default=None, help="Phase 15.1: Comma-separated scope slugs for /compare.")
@click.option("--doc-filter", default=None, help="Phase 17: Filter to specific doc type (e.g., PSA, PROSUPP).")
@click.option("--mode", "search_mode", default="search",
              type=click.Choice(["search", "compare", "diff", "aggregate", "define", "audit", "list"]),
              help="Phase 17: Query mode.")
@click.option("--scopes", default=None, help="Phase 17: Comma-separated scope slugs or wildcard pattern.")
# ── VS Code Settings pass-through ─────────────────────────────────────────
@click.option("--guide-items-top-k", default=None, type=int, help="[Settings] Override guide/legal items candidate pool size.")
@click.option("--guide-sections-top-k", default=None, type=int, help="[Settings] Override guide/legal sections candidate pool size.")
@click.option("--no-hyde", is_flag=True, default=False, help="[Settings] Disable HyDE (hypothetical document embeddings).")
@click.option("--no-cross-encoder", is_flag=True, default=False, help="[Settings] Disable cross-encoder reranking.")
@click.option("--cross-encoder-pool", default=None, type=int, help="[Settings] Cross-encoder candidate pool size.")
@click.option("--no-bm25", is_flag=True, default=False, help="[Settings] Disable BM25 hybrid search.")
@click.option("--bm25-weight", default=None, type=float, help="[Settings] BM25 lane weight in RRF fusion (0–1).")
@click.option("--bm25-k1", default=None, type=float, help="[Settings] BM25 term-saturation constant.")
@click.option("--bm25-b", default=None, type=float, help="[Settings] BM25 length-normalization factor.")
@click.option("--no-triple-store", is_flag=True, default=False, help="[Settings] Disable Phase 19 non-legal triple store.")
@click.option("--no-troubleshooting-graph", is_flag=True, default=False, help="[Settings] Disable Phase 19.3 troubleshooting graph.")
@click.option("--no-cch", is_flag=True, default=False, help="[Settings] Disable Contextual Chunk Headers (CCH) at retrieval.")
def search(query, max_results, doc_type, tool_filter, strict, no_graph_boost, no_auto_filter,
           no_term_resolution, no_query_expansion, no_acronym_resolution,
           regime_override, debug_level, explain, provenance_detail,
           section_filter, graph_only, deep, answer_text,
           session_id, conversation_history, retrieval_mode, scope_override, source_doc_hint,
           extra_queries, compare_scopes, doc_filter, search_mode, scopes,
           guide_items_top_k, guide_sections_top_k,
           no_hyde, no_cross_encoder, cross_encoder_pool,
           no_bm25, bm25_weight, bm25_k1, bm25_b,
           no_triple_store, no_troubleshooting_graph, no_cch):
    config = _ctx()

    # Apply CLI overrides to config
    if regime_override:
        config.corpus_regime_override = regime_override
    if debug_level is not None:
        config.debug_level = debug_level
    if no_query_expansion:
        config.query_expansion_enabled = False
    if no_acronym_resolution:
        config.acronym_resolver_enabled = False

    # ── VS Code Settings pass-through ────────────────────────────────────
    if guide_items_top_k is not None:
        config.guide_items_top_k = guide_items_top_k
    if guide_sections_top_k is not None:
        config.guide_sections_top_k = guide_sections_top_k
    if no_hyde:
        config.hyde_enabled = False
    if no_cross_encoder:
        config.cross_encoder_enabled = False
    if cross_encoder_pool is not None:
        config.guide_items_top_k = cross_encoder_pool  # reuse as rerank pool cap
    if no_bm25:
        config.enable_bm25_hybrid = False
    if bm25_weight is not None:
        config.bm25_weight = bm25_weight
        config.vector_weight = round(1.0 - bm25_weight, 6)
    if bm25_k1 is not None:
        config.bm25_k1 = bm25_k1
    if bm25_b is not None:
        config.bm25_b = bm25_b
    if no_triple_store:
        config.nonlegal_triple_store_enabled = False
    if no_troubleshooting_graph:
        config.troubleshooting_graph_enabled = False
    if no_cch:
        config.enable_cch = False

    retrieval = RetrievalService(config)
    
    # Deep mode: increase per-doc chunk limit and candidate pool
    chunks_per_doc = config.deep_max_chunks_per_doc if deep else config.max_chunks_per_doc
    
    result = retrieval.execute(
        {
            "query": query,
            "max_results": max_results,
            "max_chunks_per_doc": chunks_per_doc,
            "deep_mode": deep,
            "doc_type_filter": doc_type,
            "tool_filter": tool_filter,
            "strict": strict,
            "no_graph_boost": no_graph_boost,
            "no_auto_filter": no_auto_filter,
            "no_term_resolution": no_term_resolution,
            "generated_answer": answer_text,
            "explain": explain,
            "section_filter": section_filter,
            "graph_only": graph_only,
            # Phase 10.1: Session context forwarded from extension
            "session_id": session_id or "default",
            "conversation_history": json.loads(conversation_history) if conversation_history else [],
            "retrieval_mode": retrieval_mode or (search_mode if search_mode != "search" else None),
            "scope_override": scope_override,
            "source_doc_hint": source_doc_hint,
            "extra_queries": json.loads(extra_queries) if extra_queries else [],
            "compare_scopes": [s.strip() for s in compare_scopes.split(",")] if compare_scopes else [],
            # Phase 17: Document-level isolation + multi-deal
            "doc_name_prefix": doc_filter.upper() if doc_filter else None,
            "phase17_mode": search_mode,
            "phase17_scopes": [s.strip() for s in scopes.split(",")] if scopes else [],
        }
    )
    # ── Early-exit for non-search-result responses ─────────────────────────
    # Modes like /list, /diff, /aggregate, /extract, /summary, /audit, /define,
    # and scope-clarification responses all return result.data WITHOUT a
    # "search_result" key.  Serialise and emit them directly so a missing key
    # never causes a KeyError crash for the caller (e.g. the VS Code extension).
    if "search_result" not in result.data:
        if not result.success:
            click.echo(json.dumps(_serialize(result.data), indent=2))
            raise SystemExit(1)
        click.echo(json.dumps(_serialize(result.data), indent=2))
        return

    if not result.success and result.data.get("provenance", {}).get("error"):
        click.echo(json.dumps(result.data["provenance"]["error"], indent=2))
        raise SystemExit(1)

    output = _serialize(result.data["search_result"])

    if provenance_detail and "provenance" in result.data:
        output = {"search_result": output, "provenance": _serialize(result.data["provenance"])}
    if result.data.get("term_resolution"):
        if isinstance(output, dict) and "search_result" in output:
            output["term_resolution"] = result.data["term_resolution"]
        else:
            output = {"search_result": output, "term_resolution": result.data["term_resolution"]}
    
    # Include Phase 6 explainability trace in output
    if result.data.get("phase6"):
        phase6_info = result.data["phase6"]
        if isinstance(output, dict) and "search_result" in output:
            output["phase6"] = phase6_info
        else:
            output = {"search_result": output, "phase6": phase6_info}

    # Backward-compat: when output was wrapped, promote context_chunks/confidence
    # to top-level so CLI consumers can always access them directly.
    if isinstance(output, dict) and "search_result" in output:
        sr = output["search_result"]
        if isinstance(sr, dict):
            for key in ("context_chunks", "confidence", "citations"):
                if key in sr and key not in output:
                    output[key] = sr[key]

    click.echo(json.dumps(output, indent=2))


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


def _resolve_scope_for_doc(config, doc_id: str):
    """Auto-discover the per-scope .kts that houses *doc_id*.

    Searches root .kts/documents/ first.  If the doc_id isn't there,
    iterates sibling scope directories looking for a .kts/documents/<doc_id>
    subfolder and returns a scope_config pointing at that .kts/.
    """
    from config.settings import scope_config as _scope_config

    kb_path = Path(config.knowledge_base_path)
    # Root check
    if (kb_path / "documents" / doc_id).exists():
        return config
    # Per-scope search
    source_root = kb_path.parent
    for child in sorted(source_root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        scope_kts = child / ".kts"
        if (scope_kts / "documents" / doc_id).exists():
            return _scope_config(config, str(scope_kts))
    # Fallback — use root config unchanged
    return config


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

    # Phase 18: Scan both root and per-scope .kts directories for pending images
    from config.settings import scope_config as _scope_config

    summary = []
    kb_path = Path(config.knowledge_base_path)

    def _scan_docs_root(docs_root, vision_agent, scope_kts_path=None):
        """Scan a documents/ directory for pending images."""
        if not docs_root.exists():
            return
        for doc_dir in docs_root.glob("*"):
            if not doc_dir.is_dir():
                continue
            result = vision_agent.execute({"operation": "list_pending", "doc_id": doc_dir.name})
            if result.data.get("pending_count", 0):
                entry = {"doc_id": doc_dir.name, **_serialize(result.data)}
                if scope_kts_path:
                    entry["scope_kts"] = scope_kts_path
                summary.append(entry)

    # 1. Scan root .kts/documents/
    _scan_docs_root(kb_path / "documents", agent)

    # 2. Scan per-scope .kts/documents/ (Phase 12.1 per-folder isolation)
    source_root = kb_path.parent
    if source_root.exists():
        for child in sorted(source_root.iterdir()):
            if not child.is_dir() or child.name.startswith('.'):
                continue
            scope_kts = child / '.kts'
            if scope_kts.exists() and (scope_kts / 'documents').exists():
                scfg = _scope_config(config, str(scope_kts))
                scope_agent = VisionAgent(scfg)
                _scan_docs_root(scope_kts / "documents", scope_agent, scope_kts_path=str(scope_kts))

    click.echo(json.dumps({"documents": summary, "count": len(summary)}, indent=2))


@describe.command(name="complete")
@click.option("--doc-id", required=True)
@click.option("--descriptions-file", required=True)
@click.option("--scope-kts", default=None, help="Path to the scoped .kts directory")
def describe_complete(doc_id, descriptions_file, scope_kts):
    config = _ctx()

    # Phase 18-fix: Resolve per-scope config so descriptions are persisted
    # to the correct .kts/documents/<doc_id>/ instead of the root .kts/.
    if scope_kts:
        from config.settings import scope_config as _scope_config
        config = _scope_config(config, scope_kts)
    else:
        # Auto-discover: search per-scope dirs for the doc_id
        config = _resolve_scope_for_doc(config, doc_id)

    agent = VisionAgent(config)
    payload = json.loads(Path(descriptions_file).read_text(encoding="utf-8-sig"))
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
    graph = GraphBuilderAgent(config).builder.store.load()
    documents_count = len([item for item in (Path(config.knowledge_base_path) / "documents").glob("*") if item.is_dir()])
    click.echo(
        json.dumps(
            {
                "documents": documents_count,
                "manifest_files": len(manifest.get("files", {})),
                "graph_nodes": graph.number_of_nodes(),
                "graph_edges": graph.number_of_edges(),
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


# ── Concept Vocabulary LLM Enrichment (two-phase CLI ↔ JS flow) ──

@cli.group(name="enrich-vocabulary")
def enrich_vocabulary():
    """Manage LLM-enriched concept vocabulary for the knowledge graph."""
    pass


@enrich_vocabulary.command(name="extract-terms")
def enrich_extract_terms():
    """Extract defined terms from the graph for external LLM enrichment.

    Outputs JSON: {"terms": {"Term Name": "definition excerpt", ...}}
    The JS extension sends these to the Copilot LLM and passes results
    back via ``enrich-vocabulary apply-synonyms``.
    """
    config = _ctx()
    from backend.graph.persistence import GraphStore
    from backend.graph.concept_vocabulary import ConceptVocabularyBuilder

    graph_store = GraphStore(config.graph_path)
    G = graph_store.load()

    terms = ConceptVocabularyBuilder.extract_defined_terms(G)
    click.echo(json.dumps({"terms": terms, "count": len(terms)}, indent=2))


@enrich_vocabulary.command(name="apply-synonyms")
@click.option("--synonyms-file", required=True, type=click.Path(exists=True),
              help="JSON file with {term_name: [synonym1, synonym2, ...], ...}")
def enrich_apply_synonyms(synonyms_file):
    """Merge LLM-generated term synonyms into the knowledge graph.

    Reads the synonyms JSON file, propagates keywords to all sections
    that define or reference each term, and rebuilds the step-back
    vocabulary.
    """
    config = _ctx()
    from backend.graph.persistence import GraphStore
    from backend.graph.concept_vocabulary import ConceptVocabularyBuilder

    synonyms_path = Path(synonyms_file)
    synonyms = json.loads(synonyms_path.read_text(encoding="utf-8"))

    graph_store = GraphStore(config.graph_path)
    G = graph_store.load()

    stats = ConceptVocabularyBuilder.apply_external_synonyms(G, synonyms)
    graph_store.save(G)

    click.echo(json.dumps(stats, indent=2))


@enrich_vocabulary.command(name="apply-term-keywords")
@click.option("--keywords-file", required=True, type=click.Path(exists=True),
              help="JSON file with {term_name: [keyword1, keyword2, ...], ...} — one entry per defined term")
def enrich_apply_term_keywords(keywords_file):
    """Store per-definition LLM-generated keywords directly on TERM::* nodes.

    Each entry in the keywords file maps a defined term name to a list of
    keywords produced by one focused LLM call for that term alone (Q1
    per-definition enrichment).  Keywords are stored on the ``defined_term``
    node's ``concept_keywords`` attribute, not propagated to sections.
    """
    config = _ctx()
    from backend.graph.persistence import GraphStore
    from backend.graph.concept_vocabulary import ConceptVocabularyBuilder

    kw_path = Path(keywords_file)
    keywords_dict = json.loads(kw_path.read_text(encoding="utf-8"))

    graph_store = GraphStore(config.graph_path)
    G = graph_store.load()

    stats = ConceptVocabularyBuilder.apply_term_keywords(G, keywords_dict)
    graph_store.save(G)

    click.echo(json.dumps(stats, indent=2))


# ── Phase 17: Deal catalog listing command ────────────────────
@cli.command(name="list-deals")
@click.option("--scope", default=None, help="Filter by scope slug or wildcard pattern (e.g., 'bear_stearns*').")
@click.option("--format", "output_format", default="table",
              type=click.Choice(["table", "json"]),
              help="Output format.")
def list_deals(scope, output_format):
    """List all ingested deals with metadata."""
    config = _ctx()
    from backend.vector.deal_catalog import DealCatalog

    catalog_path = getattr(config, 'deal_catalog_path', '')
    catalog = DealCatalog(db_path=catalog_path)

    if scope:
        deals = catalog.search_deals(pattern=scope)
    else:
        deals = catalog.list_all_deals()

    if output_format == "json":
        click.echo(json.dumps(deals, indent=2))
    else:
        # Table format
        if not deals:
            click.echo("No deals found.")
            return
        click.echo(f"{'Slug':<30} {'Deal Name':<25} {'Vintage':<8} {'Docs':<6} {'Status':<8}")
        click.echo("-" * 80)
        for deal in deals:
            slug = deal.get("slug", "")[:29]
            name = deal.get("deal_name", "")[:24]
            vintage = deal.get("vintage", 0) or ""
            doc_count = deal.get("doc_count", 0)
            status = deal.get("status", "")[:7]
            click.echo(f"{slug:<30} {name:<25} {str(vintage):<8} {doc_count:<6} {status:<8}")
        click.echo(f"\nTotal: {len(deals)} deal(s)")


@cli.command("ingest-onenote")
@click.argument("notebook_path", type=click.Path(exists=True))
@click.option("--notebook-name", default=None,
              help="Display name for this notebook (default: folder name).")
@click.option("--delta/--full", default=True, show_default=True,
              help="Delta: only re-ingest changed/new pages. Full: wipe and re-ingest everything.")
@click.option("--skip-images", is_flag=True, default=False,
              help="Skip GPT-4.1 vision OCR for embedded images.")
@click.option("--vision-model", default="gpt-4.1", show_default=True,
              help="OpenAI model to use for image OCR.")
@click.option("--kb-path", default=None,
              help="Override knowledge-base path (default: from config).")
@click.option("--dry-run", is_flag=True, default=False,
              help="Parse and report what would be ingested without writing anything.")
def ingest_onenote(notebook_path, notebook_name, delta, skip_images, vision_model, kb_path, dry_run):
    """Phase 19: Ingest a OneNote notebook folder (.one / .onetoc2 files).

    NOTEBOOK_PATH should be the folder on the network share that contains
    the .onetoc2 Table-of-Contents file and the .one Section files.

    Examples:\n
        kts ingest-onenote "N:\\IR Knowledge\\GSF IR Support"

        kts ingest-onenote "N:\\IR Knowledge\\GSF IR Support" --full

        kts ingest-onenote "N:\\IR Knowledge\\GSF IR Support" --skip-images
    """
    import sys
    from pathlib import Path as _Path

    from backend.ingestion.onenote_converter import parse_onetoc2, parse_one_section
    from backend.ingestion.onenote_chunker import chunk_onenote_page
    from backend.ingestion.onenote_manifest import OneNoteManifest
    from backend.ingestion.onenote_vision import describe_images_for_page
    from backend.vector import VectorStore
    from backend.vector.embedding_provider import get_embedding_provider

    config = _ctx()
    nb_folder = _Path(notebook_path).resolve()
    effective_kb = _Path(kb_path) if kb_path else _Path(config.knowledge_base_path)
    nb_name = notebook_name or nb_folder.name

    click.echo(f"\n[Phase 19] OneNote Ingestion — {nb_name}")
    click.echo(f"  Source  : {nb_folder}")
    click.echo(f"  KB path : {effective_kb}")
    click.echo(f"  Mode    : {'DELTA' if delta else 'FULL'}")
    click.echo(f"  Images  : {'SKIP' if skip_images else f'GPT-4.1 vision ({vision_model})'}")
    click.echo(f"  Dry run : {dry_run}\n")

    # ── Discover .one files ────────────────────────────────────────────────
    toc_files = list(nb_folder.glob("*.onetoc2"))
    one_files  = sorted(nb_folder.glob("*.one"))

    if not one_files:
        click.secho("No .one files found in the specified folder.", fg="red")
        raise SystemExit(1)

    click.echo(f"Found {len(one_files)} section file(s)"
               + (f" + 1 .onetoc2 TOC" if toc_files else " (no .onetoc2 — using filename order)"))

    # ── Section order from TOC ─────────────────────────────────────────────
    if toc_files:
        ordered_names = parse_onetoc2(str(toc_files[0]))
        # Map name → Path
        name_to_path: dict[str, _Path] = {f.stem: f for f in one_files}
        ordered_files: list[_Path] = []
        for name in ordered_names:
            if name in name_to_path:
                ordered_files.append(name_to_path[name])
        # Append any .one files not in TOC (safety net)
        toc_stems = {f.stem for f in ordered_files}
        for f in one_files:
            if f.stem not in toc_stems:
                ordered_files.append(f)
    else:
        ordered_files = list(one_files)

    click.echo(f"Section order: {[f.stem for f in ordered_files]}\n")

    # ── Initialise manifest + vector store ────────────────────────────────
    manifest = OneNoteManifest(effective_kb)

    if not dry_run:
        ep = get_embedding_provider(config)
        vector_store = VectorStore(config.chroma_persist_dir, embedding_provider=ep)

    # ── Full wipe if --full ────────────────────────────────────────────────
    if not delta and not dry_run:
        click.echo("FULL mode: clearing all OneNote entries from vector store...")
        for of in ordered_files:
            old_ids = manifest.clear_section(of)
            if old_ids:
                try:
                    vector_store.collection.delete(ids=old_ids)
                except Exception as exc:
                    click.secho(f"  Warning: could not delete old chunks for {of.name}: {exc}", fg="yellow")
        manifest.save()
        click.echo("  Done.\n")

    # ── Per-section ingestion ──────────────────────────────────────────────
    stats = {"sections": 0, "pages_skipped": 0, "pages_ingested": 0,
             "chunks_added": 0, "images_described": 0, "errors": 0}

    for sec_idx, one_path in enumerate(ordered_files):
        section_name = one_path.stem
        click.echo(f"[{sec_idx + 1}/{len(ordered_files)}] Section: {section_name!r}")

        # Section-level delta check (file mtime)
        if delta and not manifest.section_needs_scan(one_path):
            click.echo(f"  -> Unchanged (mtime match) -- skipping entire section\n")
            stats["sections"] += 1
            continue

        # Parse pages from .one file
        try:
            pages = parse_one_section(str(one_path))
        except Exception as exc:
            click.secho(f"  ERROR parsing {one_path.name}: {exc}", fg="red")
            stats["errors"] += 1
            continue

        click.echo(f"  Parsed {len(pages)} page(s)")

        manifest.update_section_mtime(one_path, section_name)

        page_chunks_new: list = []   # list of TextChunk for batch insert

        for page in pages:
            page_hash = page.content_hash()

            # Page-level delta check (content hash)
            if delta and not manifest.page_needs_ingest(one_path, page.guid, page_hash):
                stats["pages_skipped"] += 1
                continue

            # Delete old chunks for this page before re-inserting
            if not dry_run:
                old_ids = manifest.get_chunk_ids(one_path, page.guid)
                if old_ids:
                    try:
                        vector_store.collection.delete(ids=old_ids)
                    except Exception as exc:
                        click.secho(f"    Warning: delete old chunks for page '{page.title}': {exc}",
                                    fg="yellow")

            # Vision OCR for images
            image_descriptions: list[str] = []
            if page.images and not skip_images and not dry_run:
                try:
                    image_descriptions = describe_images_for_page(
                        page.images,
                        page_title=page.title,
                        section_name=section_name,
                        model=vision_model,
                        skip_on_error=True,
                    )
                    stats["images_described"] += len([d for d in image_descriptions if d])
                except Exception as exc:
                    click.secho(f"    Warning: vision OCR failed for '{page.title}': {exc}", fg="yellow")

            # Chunk the page
            chunks = chunk_onenote_page(
                page,
                section_name=section_name,
                one_file_path=str(one_path),
                notebook_name=nb_name,
                section_order=sec_idx,
                image_descriptions=image_descriptions or None,
            )

            if dry_run:
                click.echo(f"    [dry-run] Page '{page.title}' -> {len(chunks)} chunk(s), "
                           f"{len(page.images)} image(s)")
                stats["pages_ingested"] += 1
                stats["chunks_added"] += len(chunks)
                continue

            page_chunks_new.extend(chunks)

            # Track in manifest (will be saved after batch insert)
            manifest.upsert_page(
                one_path,
                page_guid=page.guid,
                title=page.title,
                content_hash=page_hash,
                chunk_ids=[c.chunk_id for c in chunks],
                image_count=len(page.images),
            )

            stats["pages_ingested"] += 1
            stats["chunks_added"] += len(chunks)

            click.echo(f"    ✓ '{page.title}'  chunks={len(chunks)}  images={len(page.images)}")

        # Batch-insert all new chunks for this section
        if page_chunks_new and not dry_run:
            try:
                vector_store.add_chunks(page_chunks_new)
                click.echo(f"  -> Inserted {len(page_chunks_new)} chunk(s) into vector store")
            except Exception as exc:
                click.secho(f"  ERROR inserting chunks for {section_name}: {exc}", fg="red")
                stats["errors"] += 1

        # Save manifest after each section (so progress is not lost on interruption)
        if not dry_run:
            manifest.save()

        stats["sections"] += 1
        click.echo()

    # ── Final ──────────────────────────────────────────────────────────────
    if not delta and not dry_run:
        manifest.mark_full_ingest()
        manifest.save()

    click.echo("=" * 60)
    click.echo(f"OneNote ingestion complete ({nb_name})")
    click.echo(f"  Sections processed : {stats['sections']}")
    click.echo(f"  Pages ingested     : {stats['pages_ingested']}")
    click.echo(f"  Pages skipped      : {stats['pages_skipped']}  (delta: unchanged)")
    click.echo(f"  Chunks added       : {stats['chunks_added']}")
    click.echo(f"  Images described   : {stats['images_described']}")
    click.echo(f"  Errors             : {stats['errors']}")
    click.echo("=" * 60)

    if not dry_run:
        summary = manifest.summary()
        click.echo(json.dumps(summary, indent=2))


# ─── ABS command group (Phase 23) ────────────────────────────────────────────
from cli.abs import abs_group  # noqa: E402

cli.add_command(abs_group, "abs")


# ─── ABS IPC serve command ────────────────────────────────────────────────────
@cli.command("abs-serve")
@click.option("--deals-root", required=True, help="Root folder containing deal sub-directories.")
def abs_serve_cmd(deals_root: str) -> None:
    """ABS Waterfall backend IPC server (JSON-lines stdio).

    Launched by the VS Code extension as a long-running child process.
    Reads JSON-line requests from stdin, writes JSON-line responses to stdout.
    All diagnostic/log output goes to stderr.
    """
    from backend.abs.serve import main  # noqa: PLC0415

    raise SystemExit(main(["--deals-root", deals_root]))


if __name__ == "__main__":
    cli()
