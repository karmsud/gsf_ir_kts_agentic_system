"""CLI command: kts abs status

Show processing status for one or all ingested deals.
Reads DealManifest files from the deals directory.
"""

from __future__ import annotations

import sys

import click

from config.settings import KTSConfig


@click.command("status")
@click.option(
    "--deal-id",
    default=None,
    help="Deal identifier (omit to list all deals)",
)
@click.option("--verbose", "-v", is_flag=True, default=False, help="Show additional details")
def abs_status(deal_id: str | None, verbose: bool) -> None:
    """Show deal processing status.

    Without --deal-id, lists all deals found in the deals directory.
    With --deal-id, shows detailed status for that specific deal.

    \b
    Examples:
        kts abs status
        kts abs status --deal-id bear_stearns_2006_he1 -v
    """
    config = KTSConfig()

    from backend.abs.orchestrator import ABSOrchestrator

    orch = ABSOrchestrator(config=config)

    try:
        result = orch.status(deal_id=deal_id)
    except Exception as exc:
        click.echo(f"❌ Status failed: {exc}", err=True)
        sys.exit(1)

    click.echo(result.status_report)

    if verbose and result.deals:
        click.echo("\nDetails:")
        for d in result.deals:
            click.echo(f"  {d['deal_id']}")
            click.echo(f"    Path:      {d['deal_path']}")
            click.echo(f"    Documents: {d['document_count']}")
            click.echo(f"    Ready:     {d['ready']}")
            click.echo(f"    Status:    {d['status']}")
