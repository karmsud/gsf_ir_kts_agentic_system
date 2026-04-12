"""CLI command: kts abs ingest

Ingest deal documents (PDF, text) into the ABS knowledge base.
Builds a vector store, knowledge graph, and extraction artefacts
for the given deal identifier.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import click

from config.settings import KTSConfig
from backend.abs.llm_bridge import create_llm_callable


@click.command("ingest")
@click.option("--deal-id", required=True, help="Deal identifier (e.g. bear_stearns_2006_he1)")
@click.option(
    "--source-dir",
    required=True,
    type=click.Path(exists=True),
    help="Directory containing deal documents (PDF / text)",
)
@click.option(
    "--llm-mode",
    default="vscode",
    type=click.Choice(["vscode", "mock", "none"]),
    show_default=True,
    help="LLM backend mode (vscode=use Copilot model, mock=deterministic, none=no LLM)",
)
@click.option("--force", is_flag=True, default=False, help="Re-ingest even if already complete")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Show per-step progress")
def abs_ingest(
    deal_id: str,
    source_dir: str,
    llm_mode: str,
    force: bool,
    verbose: bool,
) -> None:
    """Ingest deal documents (PSA, Indenture, Supplements) into the knowledge base.

    Processes each document found in SOURCE_DIR, extracts structured data,
    and persists a vector store + knowledge graph for DEAL_ID.

    \b
    Examples:
        kts abs ingest --deal-id bear_stearns_2006_he1 --source-dir ./deals/bear/
        kts abs ingest --deal-id smoke_test --source-dir ./deals/smoke_test --llm-mode mock -v
    """
    config = KTSConfig()
    config.abs_llm_mode = llm_mode
    llm = create_llm_callable(mode=llm_mode)

    # Lazy import to keep startup fast
    from backend.abs.orchestrator import ABSOrchestrator

    orch = ABSOrchestrator(config=config, llm_callable=llm)

    start = time.time()
    click.echo(f"📁 Ingesting '{deal_id}' from {source_dir}")

    def _cb(step: str, status: str) -> None:
        click.echo(f"  [{step}] {status}")

    try:
        result = orch.ingest(
            deal_id=deal_id,
            source_dir=Path(source_dir),
            force=force,
            progress_callback=_cb if verbose else None,
        )
    except Exception as exc:
        click.echo(f"\n❌ Ingestion failed: {exc}", err=True)
        sys.exit(1)

    elapsed = time.time() - start

    if result.skipped:
        click.echo(f"\n⏭️  Skipped — {result.message}")
        click.echo("   Use --force to re-ingest.")
        return

    click.echo(f"\n✅ Ingestion complete ({elapsed:.1f}s)")
    click.echo(f"   Items:       {result.item_count}")
    click.echo(f"   Sections:    {result.section_count}")
    click.echo(f"   Graph nodes: {result.node_count}")
    click.echo(f"   Graph edges: {result.edge_count}")
