"""CLI command: kts abs audit

Audit a generated payment model against the deal's governing documents.
Reports rule-match coverage, confidence score, and any discrepancies.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from config.settings import KTSConfig
from backend.abs.llm_bridge import create_llm_callable


@click.command("audit")
@click.option("--deal-id", required=True, help="Deal identifier")
@click.option(
    "--model-path",
    default=None,
    type=click.Path(),
    help="Path to the Python model file (default: auto-detect from deal directory)",
)
@click.option(
    "--expected-csv",
    default=None,
    type=click.Path(),
    help="Expected payment results CSV for comparison (optional)",
)
@click.option(
    "--llm-mode",
    default="vscode",
    type=click.Choice(["vscode", "mock", "none"]),
    show_default=True,
    help="LLM backend mode (vscode=use Copilot model, mock=deterministic, none=no LLM)",
)
@click.option("--verbose", "-v", is_flag=True, default=False)
def abs_audit(
    deal_id: str,
    model_path: str | None,
    expected_csv: str | None,
    llm_mode: str,
    verbose: bool,
) -> None:
    """Audit the generated payment model for DEAL_ID.

    Compares the model's waterfall logic against governing document rules
    and (if provided) an expected results CSV.

    \b
    Examples:
        kts abs audit --deal-id bear_stearns_2006_he1 --llm-mode mock
        kts abs audit --deal-id bear_stearns_2006_he1 \\
            --model-path ./models/bear_model.py \\
            --expected-csv ./test_data/expected.csv
    """
    config = KTSConfig()
    config.abs_llm_mode = llm_mode
    llm = create_llm_callable(mode=llm_mode)

    from backend.abs.orchestrator import ABSOrchestrator

    orch = ABSOrchestrator(config=config, llm_callable=llm)
    click.echo(f"🔍 Auditing '{deal_id}'")

    def _cb(step: str, status: str) -> None:
        click.echo(f"  [{step}] {status}")

    try:
        result = orch.audit(
            deal_id=deal_id,
            model_path=Path(model_path) if model_path else None,
            expected_csv=Path(expected_csv) if expected_csv else None,
            progress_callback=_cb if verbose else None,
        )
    except Exception as exc:
        click.echo(f"\n❌ Audit failed: {exc}", err=True)
        sys.exit(1)

    click.echo(result.report)
    click.echo(f"\nRules matched: {result.rules_matched}/{result.rules_total}")
    click.echo(f"Confidence:    {result.confidence:.2f}")
