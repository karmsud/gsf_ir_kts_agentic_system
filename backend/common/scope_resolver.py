"""
Phase 17 — Scope Resolution Pipeline

Parses slash-token commands from user input into structured
``ParsedCommand`` objects and resolves wildcard scopes via the
deal catalog.

Syntax
------
::

    /scope_slug           → deal scope only
    /scope_slug/DOC_TYPE  → deal scope + doc filter
    //DOC_TYPE            → all deals, doc filter only
    /scope_wild*          → wildcard scope
    /scope_wild*/DOC_TYPE → wildcard + doc filter
    /compare, /diff, /aggregate, /audit, /list, /define → modes

Examples
--------
::

    "@kts /fin_deal1/PSA What is Distribution Date?"
    → ParsedCommand(mode="search", scopes=[ScopeExpr("fin_deal1", "PSA")],
                     query="What is Distribution Date?")

    "@kts /compare /bear_stearns_2006*/PSA What is Distribution Date?"
    → ParsedCommand(mode="compare",
                     scopes=[ScopeExpr("bear_stearns_2006", "PSA", is_wildcard=True)],
                     query="What is Distribution Date?")
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from backend.vector.deal_catalog import DealCatalog

logger = logging.getLogger(__name__)

# Recognised mode tokens (case-insensitive)
_MODE_TOKENS = frozenset({
    "compare", "diff", "aggregate", "audit", "list", "define",
})


@dataclass
class ScopeExpr:
    """One scope target parsed from user input."""

    slug: str  # e.g., "fin_deal1"
    doc_filter: str | None = None  # e.g., "PSA" or None
    is_wildcard: bool = False  # e.g., "bear_stearns_2006*"

    def __repr__(self) -> str:
        parts = [self.slug]
        if self.is_wildcard:
            parts[-1] += "*"
        if self.doc_filter:
            parts.append(self.doc_filter)
        return f"ScopeExpr({'/'.join(parts)})"


@dataclass
class ParsedCommand:
    """Fully parsed user command."""

    mode: str = "search"  # "search" | "compare" | "diff" | "aggregate" | "define" | "audit" | "list"
    scopes: List[ScopeExpr] = field(default_factory=list)
    query: str = ""
    raw_input: str = ""


# ── Parser ───────────────────────────────────────────────────

def parse_command(raw_input: str) -> ParsedCommand:
    """Parse slash-token commands from user input.

    Returns a ``ParsedCommand`` with mode, scopes, and query.
    Tokens that start with ``/`` are treated as commands or scope
    expressions; everything else is the query text.
    """
    # Strip leading @kts or @KTS prefix if present
    text = re.sub(r"^@kts\s*", "", raw_input.strip(), flags=re.IGNORECASE)

    cmd = ParsedCommand(raw_input=raw_input)

    # Tokenise: split on whitespace, separate slash-tokens from text
    tokens = text.split()
    query_parts: list[str] = []

    for token in tokens:
        if token.startswith("/"):
            _process_slash_token(token, cmd)
        else:
            query_parts.append(token)

    cmd.query = " ".join(query_parts).strip()

    # Default mode is "search" (already set)
    return cmd


def _process_slash_token(token: str, cmd: ParsedCommand) -> None:
    """Handle a single slash-prefixed token."""
    # Remove leading slash
    body = token[1:]

    if not body:
        return  # bare "/" — ignore

    # Check for global doc filter: "//DOC_TYPE"
    if body.startswith("/"):
        doc_filter = body[1:].upper().rstrip("*")
        if doc_filter:
            cmd.scopes.append(ScopeExpr(slug="*", doc_filter=doc_filter))
        return

    # Check for mode token
    body_lower = body.lower().rstrip("*")
    if body_lower in _MODE_TOKENS:
        cmd.mode = body_lower
        return

    # Scope expression (may contain internal "/")
    if "/" in body:
        parts = body.split("/", 1)
        slug_raw = parts[0]
        doc_filter = parts[1].upper() if parts[1] else None
        is_wildcard = "*" in slug_raw
        slug = slug_raw.rstrip("*").lower()
        cmd.scopes.append(ScopeExpr(slug=slug, doc_filter=doc_filter, is_wildcard=is_wildcard))
    else:
        is_wildcard = "*" in body
        slug = body.rstrip("*").lower()
        cmd.scopes.append(ScopeExpr(slug=slug, doc_filter=None, is_wildcard=is_wildcard))


# ── Resolver ─────────────────────────────────────────────────

def resolve_scopes(
    parsed: ParsedCommand,
    catalog: "DealCatalog",
    *,
    max_wildcard_matches: int = 20,
) -> list[ScopeExpr]:
    """Resolve wildcard and global scopes via the deal catalog.

    - Wildcard slugs (``bear_stearns_2006*``) are expanded via
      ``catalog.search_deals(pattern=...)``.
    - Global doc filters (slug ``*``) are expanded to all ingested deals.
    - Non-wildcard scopes are passed through unchanged.

    Args:
        parsed: The parsed command.
        catalog: Deal catalog for lookups.
        max_wildcard_matches: Cap on wildcard expansion to prevent runaway.

    Returns:
        Expanded list of ``ScopeExpr`` with ``is_wildcard=False``.
    """
    if not parsed.scopes:
        return []

    resolved: list[ScopeExpr] = []

    for scope in parsed.scopes:
        if scope.slug == "*":
            # Global doc filter — expand to all deals
            all_deals = catalog.list_all_deals()
            for deal in all_deals[:max_wildcard_matches]:
                resolved.append(ScopeExpr(
                    slug=deal["slug"],
                    doc_filter=scope.doc_filter,
                    is_wildcard=False,
                ))
            logger.info(
                "[Phase17] Global filter expanded to %d deals (filter=%s)",
                len(resolved),
                scope.doc_filter,
            )
        elif scope.is_wildcard:
            # Wildcard slug — search catalog
            matches = catalog.search_deals(pattern=f"{scope.slug}*")
            for match in matches[:max_wildcard_matches]:
                resolved.append(ScopeExpr(
                    slug=match["slug"],
                    doc_filter=scope.doc_filter,
                    is_wildcard=False,
                ))
            logger.info(
                "[Phase17] Wildcard '%s*' expanded to %d matches",
                scope.slug,
                len(matches),
            )
        else:
            # Concrete scope — pass through
            resolved.append(ScopeExpr(
                slug=scope.slug,
                doc_filter=scope.doc_filter,
                is_wildcard=False,
            ))

    return resolved
