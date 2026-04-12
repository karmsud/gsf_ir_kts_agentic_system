"""
Phase 12.4 — Scope Router & Deal Catalog Routing.

Routes queries to the correct scope(s):
  1. Exact scope match (user specified /scope slug)
  2. Keyword matching via deal catalog
  3. No-scope fallback (prompt user to narrow)

Also provides federated fan-out for cross-scope queries.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


# ── Data Structures ───────────────────────────────────────────

@dataclass
class ScopeMatch:
    """A matched scope from routing."""

    slug: str
    folder_name: str
    kts_path: str
    match_type: str  # "exact", "keyword", "issuer", "fallback"
    confidence: float = 1.0


@dataclass
class RoutingResult:
    """Result of scope routing."""

    scopes: List[ScopeMatch] = field(default_factory=list)
    needs_user_clarification: bool = False
    message: str = ""

    @property
    def is_single_scope(self) -> bool:
        return len(self.scopes) == 1

    @property
    def is_multi_scope(self) -> bool:
        return len(self.scopes) > 1

    @property
    def slugs(self) -> List[str]:
        return [s.slug for s in self.scopes]


@dataclass
class FederatedResult:
    """Result of a federated cross-scope search."""

    scope_slug: str
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


# ── Scope Router ──────────────────────────────────────────────

class ScopeRouter:
    """
    Routes queries to the correct ChromaDB scope(s).

    Requires a deal catalog to perform keyword routing.
    Without catalog, only exact slug matching is supported.

    Usage::

        router = ScopeRouter(catalog=my_catalog)
        result = router.route(query="Tell me about bear stearns 2006-HE1",
                              explicit_scope=None)
        if result.is_single_scope:
            # search that one scope
        elif result.is_multi_scope:
            # federated search across matched scopes
        elif result.needs_user_clarification:
            # ask user to specify scope
    """

    MAX_FEDERATED_SCOPES = 100  # safety cap

    def __init__(self, catalog=None, all_scopes: Optional[List[Dict]] = None) -> None:
        """
        Parameters
        ----------
        catalog : DealCatalog, optional
            Deal catalog for keyword routing.
        all_scopes : list[dict], optional
            Fallback list of scopes if catalog unavailable.
            Each dict: {"slug": str, "folder_name": str, "kts_path": str}
        """
        self.catalog = catalog
        self._all_scopes = all_scopes or []

    def route(
        self,
        query: str,
        *,
        explicit_scope: Optional[str] = None,
        doc_type_filter: Optional[str] = None,
    ) -> RoutingResult:
        """Route '*query*' to the correct scope(s)."""

        # ── 1. Exact scope from slash command ────────────────
        if explicit_scope:
            match = self._find_scope_by_slug(explicit_scope)
            if match:
                return RoutingResult(scopes=[match])
            # Explicit scope not found — could be a typo
            return RoutingResult(
                needs_user_clarification=True,
                message=f"Scope '{explicit_scope}' not found. "
                        f"Use /kts refreshScopes to discover available scopes.",
            )

        # ── 2. Try exact scope mention in query ─────────────
        for scope_info in self._iter_all_scopes():
            slug = scope_info.get("slug", "")
            if slug and slug.lower() in query.lower().replace(" ", "_"):
                return RoutingResult(scopes=[
                    ScopeMatch(
                        slug=slug,
                        folder_name=scope_info.get("folder_name", slug),
                        kts_path=scope_info.get("kts_path", ""),
                        match_type="exact",
                    )
                ])

        # ── 3. Catalog keyword search ────────────────────────
        if self.catalog is not None:
            matches = self.catalog.search(query)
            if 0 < len(matches) <= self.MAX_FEDERATED_SCOPES:
                return RoutingResult(scopes=[
                    ScopeMatch(
                        slug=m.get("slug", ""),
                        folder_name=m.get("folder_name", ""),
                        kts_path=m.get("kts_path", ""),
                        match_type="keyword",
                        confidence=m.get("score", 0.8),
                    )
                    for m in matches
                ])
            if len(matches) > self.MAX_FEDERATED_SCOPES:
                return RoutingResult(
                    needs_user_clarification=True,
                    message=f"Query matched {len(matches)} scopes — too many for "
                            f"federated search. Please specify a deal scope.",
                )

        # ── 4. No scope found ────────────────────────────────
        # Fall back to global collection
        return RoutingResult(
            scopes=[
                ScopeMatch(
                    slug="__global__",
                    folder_name="global",
                    kts_path="",
                    match_type="fallback",
                    confidence=0.5,
                )
            ],
            message="No specific scope detected — searching global knowledge base.",
        )

    # ── Federated Search ────────────────────────────────────

    async def federated_search(
        self,
        query: str,
        scope_slugs: List[str],
        search_fn: Callable,
        top_k: int = 5,
    ) -> List[FederatedResult]:
        """
        Search multiple scopes in parallel.

        Parameters
        ----------
        search_fn : callable
            ``async def search_fn(query, scope_slug, top_k) -> list[dict]``
        """
        async def _search_one(slug: str) -> FederatedResult:
            try:
                chunks = await search_fn(query, slug, top_k)
                return FederatedResult(scope_slug=slug, chunks=chunks)
            except Exception as exc:
                logger.warning("[ScopeRouter] Federated search failed for %s: %s", slug, exc)
                return FederatedResult(scope_slug=slug, error=str(exc))

        tasks = [_search_one(slug) for slug in scope_slugs]
        return await asyncio.gather(*tasks)

    # ── Helpers ─────────────────────────────────────────────

    def _iter_all_scopes(self):
        """Iterate all known scopes from catalog or fallback list."""
        if self.catalog is not None:
            yield from self.catalog.all_scopes()
        else:
            yield from self._all_scopes

    def _find_scope_by_slug(self, slug: str) -> Optional[ScopeMatch]:
        """Find scope by slug."""
        for scope_info in self._iter_all_scopes():
            s = scope_info.get("slug", "")
            if s.lower() == slug.lower():
                return ScopeMatch(
                    slug=s,
                    folder_name=scope_info.get("folder_name", s),
                    kts_path=scope_info.get("kts_path", ""),
                    match_type="exact",
                )
        return None


# ── Two-Level Scope Parser ────────────────────────────────────

def parse_two_level_scope(command: str, prompt: str) -> Dict[str, Optional[str]]:
    """
    Parse two-level scope from chat participant request.

    Parameters
    ----------
    command : str
        The slash command name (first scope slug).
    prompt : str
        The raw prompt text (may start with ``/doctype``).

    Returns
    -------
    dict
        ``{"scope": str, "doc_type_filter": str|None, "query": str}``
    """
    doc_type_match = re.match(r"^/(\w+)\s+(.*)", prompt, re.DOTALL)
    if doc_type_match:
        return {
            "scope": command,
            "doc_type_filter": doc_type_match.group(1).upper(),
            "query": doc_type_match.group(2).strip(),
        }
    return {
        "scope": command,
        "doc_type_filter": None,
        "query": prompt.strip(),
    }
