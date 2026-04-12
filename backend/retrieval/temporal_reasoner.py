"""
Phase 14.2 — Temporal Reasoning.

Injects ``current_date`` into every LLM prompt so the model can reason
about whether dates have passed, how many days remain, and whether
time-based conditions are currently active.

Usage::

    reasoner = TemporalReasoner()
    if reasoner.is_temporal_query(query):
        extra_ctx = reasoner.get_temporal_context()
        # prepend to system prompt
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ── Temporal Signals ──────────────────────────────────────────

TEMPORAL_SIGNALS = [
    "has", "passed", "yet", "still", "current", "active", "expired",
    "how long", "when does", "is it", "open", "closed", "period",
    "remaining", "until", "since", "before", "after", "deadline",
    "overdue", "maturity", "termination date", "distribution date",
    "effective date", "closing date", "settlement date",
]


# ── System Context Template ──────────────────────────────────

TEMPORAL_SYSTEM_CONTEXT = """Today's date is {current_date}.
When answering questions about dates, deadlines, or time periods:
- If a date is in the past, state that explicitly ("this date has passed")
- If a date is in the future, state the time remaining ("X days / X months from today")
- If asked whether a condition based on a date is currently active, evaluate it
- Do not ask the user what today's date is"""


TEMPORAL_EVALUATION_INSTRUCTION = """
Additionally, the user's question appears to involve temporal reasoning.
Evaluate any dates mentioned in the context relative to today ({current_date}).
State explicitly whether each relevant date is in the past, present, or future,
and what that means for the user's question.
"""


# ── Temporal Reasoner ─────────────────────────────────────────

class TemporalReasoner:
    """
    Injects temporal awareness into prompts and detects temporal queries.

    Stateless — instantiate once and reuse across requests.
    """

    def __init__(self, current_date_override: Optional[date] = None) -> None:
        """
        Parameters
        ----------
        current_date_override : date, optional
            Override the date for testing; defaults to ``date.today()``.
        """
        self._date_override = current_date_override

    @property
    def current_date(self) -> date:
        return self._date_override or date.today()

    @property
    def current_date_str(self) -> str:
        return self.current_date.strftime("%B %d, %Y")  # e.g. "February 18, 2026"

    # ── Query Analysis ──────────────────────────────────────

    def is_temporal_query(self, query: str) -> bool:
        """Return True if the query contains temporal signals."""
        query_lower = query.lower()
        return any(signal in query_lower for signal in TEMPORAL_SIGNALS)

    # ── Context Injection ───────────────────────────────────

    def get_temporal_context(self) -> str:
        """Return the base temporal system context paragraph."""
        return TEMPORAL_SYSTEM_CONTEXT.format(current_date=self.current_date_str)

    def get_temporal_evaluation_instruction(self) -> str:
        """Return the evaluation addendum for temporal queries."""
        return TEMPORAL_EVALUATION_INSTRUCTION.format(
            current_date=self.current_date_str
        )

    def build_temporal_prompt_prefix(self, query: str) -> str:
        """
        Build a combined temporal prefix to prepend to the system prompt.

        Always includes the date context line.
        If the query is temporal, also includes evaluation instructions.
        """
        parts = [self.get_temporal_context()]
        if self.is_temporal_query(query):
            parts.append(self.get_temporal_evaluation_instruction())
        return "\n".join(parts)

    # ── Date Extraction Helpers ─────────────────────────────

    _DATE_PATTERNS = [
        # "March 15, 2023"
        re.compile(
            r"\b(January|February|March|April|May|June|July|August|September|"
            r"October|November|December)\s+\d{1,2},?\s+\d{4}\b",
            re.IGNORECASE,
        ),
        # "2023-03-15" or "03/15/2023"
        re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
        re.compile(r"\b\d{2}/\d{2}/\d{4}\b"),
    ]

    def extract_dates_from_text(self, text: str) -> list[str]:
        """Extract date-like strings from text (best effort)."""
        found: list[str] = []
        for pattern in self._DATE_PATTERNS:
            found.extend(pattern.findall(text))
        return found
