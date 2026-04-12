"""CLI command: kts abs generate

Generate a payment waterfall Python model from ingested deal documents.
Requires that the deal has been ingested first (`kts abs ingest`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from config.settings import KTSConfig
from backend.abs.llm_bridge import create_llm_callable


@click.command("generate")
@click.option("--deal-id", required=True, help="Deal identifier")
@click.option(
    "--output-dir",
    default=None,
    type=click.Path(),
    help="Output directory for the generated model (default: <deal_dir>/models/)",
)
@click.option(
    "--llm-mode",
    default="vscode",
    type=click.Choice(["vscode", "mock", "none"]),
    show_default=True,
    help="LLM backend mode (vscode=use Copilot model, mock=deterministic, none=no LLM)",
)
@click.option(
    "--max-retries",
    default=3,
    type=int,
    show_default=True,
    help="Maximum model-generation retry attempts",
)
@click.option("--verbose", "-v", is_flag=True, default=False)
def abs_generate(
    deal_id: str,
    output_dir: str | None,
    llm_mode: str,
    max_retries: int,
    verbose: bool,
) -> None:
    """Generate a payment waterfall model for DEAL_ID.

    The deal must be ingested first.  With --llm-mode mock the model is
    generated deterministically (no external API calls).

    \b
    Examples:
        kts abs generate --deal-id bear_stearns_2006_he1 --llm-mode mock
        kts abs generate --deal-id bear_stearns_2006_he1 --output-dir /tmp/models -v
    """
    config = KTSConfig()
    config.abs_llm_mode = llm_mode
    llm = create_llm_callable(mode=llm_mode)

    from backend.abs.orchestrator import ABSOrchestrator

    orch = ABSOrchestrator(config=config, llm_callable=llm)
    click.echo(f"⚙️  Generating payment model for '{deal_id}'")

    def _cb(step: str, status: str) -> None:
        click.echo(f"  [{step}] {status}")

    try:
        result = orch.generate(
            deal_id=deal_id,
            output_dir=Path(output_dir) if output_dir else None,
            max_retries=max_retries,
            progress_callback=_cb if verbose else None,
        )
    except Exception as exc:
        click.echo(f"\n❌ Generation failed: {exc}", err=True)
        sys.exit(1)

    click.echo(f"\n✅ Model generated ({result.elapsed_seconds:.1f}s)")
    click.echo(f"   Output:     {result.output_path}")
    click.echo(f"   Validation: {result.validation_summary}")
    click.echo(f"   Quality:    {result.quality_score:.2f}")
