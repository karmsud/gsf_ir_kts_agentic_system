"""CLI command: kts abs qa

Ask a natural-language question about an ingested deal.
Delegates to the QAAgent which searches the vector store and
knowledge graph before producing an answer.
"""

from __future__ import annotations

import sys

import click

from config.settings import KTSConfig
from backend.abs.llm_bridge import create_llm_callable


@click.command("qa")
@click.option("--deal-id", required=True, help="Deal identifier")
@click.option("--query", "-q", required=True, help="Question text")
@click.option(
    "--max-results",
    default=10,
    type=int,
    show_default=True,
    help="Maximum retrieval results to consider",
)
@click.option(
    "--llm-mode",
    default="vscode",
    type=click.Choice(["vscode", "mock", "none"]),
    show_default=True,
    help="LLM backend mode (vscode=use Copilot model, mock=deterministic, none=no LLM)",
)
@click.option("--verbose", "-v", is_flag=True, default=False, help="Show sources and confidence")
def abs_qa(
    deal_id: str,
    query: str,
    max_results: int,
    llm_mode: str,
    verbose: bool,
) -> None:
    """Ask a question about an ingested DEAL_ID.

    \b
    Examples:
        kts abs qa --deal-id bear_stearns_2006_he1 -q "What is the Distribution Waterfall?"
        kts abs qa --deal-id smoke_test -q "Who is the servicer?" --llm-mode mock -v
    """
    config = KTSConfig()
    config.abs_llm_mode = llm_mode
    config.abs_retrieval_max_results = max_results
    llm = create_llm_callable(mode=llm_mode)

    from backend.abs.orchestrator import ABSOrchestrator

    orch = ABSOrchestrator(config=config, llm_callable=llm)

    try:
        result = orch.qa(deal_id=deal_id, query=query, max_results=max_results)
    except Exception as exc:
        click.echo(f"\n❌ Q&A failed: {exc}", err=True)
        sys.exit(1)

    click.echo(f"\n{result.answer}")

    if verbose:
        click.echo(f"\nConfidence: {result.confidence:.2f}")
        if result.sources:
            click.echo("\nSources:")
            for src in result.sources:
                click.echo(f"  - {src}")
        if result.follow_ups:
            click.echo("\nSuggested follow-ups:")
            for q in result.follow_ups:
                click.echo(f"  • {q}")
