"""ABS CLI command group — Click subgroup registered under the main KTS CLI."""

from __future__ import annotations

import click

from cli.abs.ingest_cmd import abs_ingest
from cli.abs.generate_cmd import abs_generate
from cli.abs.audit_cmd import abs_audit
from cli.abs.qa_cmd import abs_qa
from cli.abs.status_cmd import abs_status


@click.group("abs")
def abs_group() -> None:
    """ABS Payment Model Generator commands.

    Ingest deal documents, generate payment waterfall models,
    audit results against governing documents, and ask questions.

    \b
    Quick-start:
        kts abs ingest --deal-id bear_stearns_2006_he1 --source-dir ./deals/bear/
        kts abs generate --deal-id bear_stearns_2006_he1 --llm-mode mock
        kts abs qa --deal-id bear_stearns_2006_he1 -q "What is the waterfall?"
        kts abs status
    """


abs_group.add_command(abs_ingest, "ingest")
abs_group.add_command(abs_generate, "generate")
abs_group.add_command(abs_audit, "audit")
abs_group.add_command(abs_qa, "qa")
abs_group.add_command(abs_status, "status")

__all__ = ["abs_group"]
