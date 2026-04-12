"""
Phase 15.1 — Cross-Deal Comparison Mode (/compare).

Retrieves the same concept from multiple scopes and generates a side-by-side
comparison table with divergence analysis.

Usage::

    mode = ComparisonMode(llm_call_fn=my_llm)
    result = await mode.compare(
        concept="Servicer Advance definition",
        scope_chunks={"bear_2006_HE1": [...], "bear_2006_HE2": [...]},
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Prompt Templates ──────────────────────────────────────────

COMPARISON_PROMPT = """The following are definitions/clauses about "{concept}" from {n} different legal documents.
Compare them:
1. Identify what is the same across all versions
2. Identify meaningful differences (not just wording — substantive legal differences)
3. Flag any definition that is materially narrower or broader than the others
4. If any definition is missing a component present in others, flag it

{per_scope_definitions}

Output as a markdown table followed by a bullet-point divergence summary.
Use ⚠️ to flag material divergences."""


# ── Data Structures ───────────────────────────────────────────

@dataclass
class ScopeDefinition:
    """A concept definition from a single scope."""

    scope_slug: str
    text: str
    source_section: str = ""


@dataclass
class ComparisonResult:
    """Result of a cross-deal comparison."""

    concept: str
    scopes_compared: List[str] = field(default_factory=list)
    raw_markdown: str = ""
    definitions: List[ScopeDefinition] = field(default_factory=list)
    has_divergences: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "concept": self.concept,
            "scopes_compared": self.scopes_compared,
            "raw_markdown": self.raw_markdown,
            "has_divergences": self.has_divergences,
            "definitions": [
                {"scope": d.scope_slug, "text": d.text, "source": d.source_section}
                for d in self.definitions
            ],
        }


# ── Comparison Mode ───────────────────────────────────────────

class ComparisonMode:
    """
    Cross-deal comparison mode for /compare slash command.

    Given a concept and per-scope chunks, generates a side-by-side
    comparison with divergence analysis.
    """

    def __init__(
        self,
        llm_call_fn=None,
        max_tokens: int = 3000,
        temperature: float = 0.3,
        top_k_per_scope: int = 2,
    ) -> None:
        self.llm_call_fn = llm_call_fn
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_k_per_scope = top_k_per_scope

    async def compare(
        self,
        concept: str,
        scope_chunks: Dict[str, List[Dict[str, Any]]],
        *,
        content_key: str = "content",
    ) -> ComparisonResult:
        """
        Compare a concept across scopes.

        Parameters
        ----------
        concept : str
            The concept / term to compare.
        scope_chunks : dict
            ``{scope_slug: [chunk_dict, ...]}`` — top chunks per scope.
        """
        if self.llm_call_fn is None:
            return ComparisonResult(
                concept=concept,
                raw_markdown="No LLM available for comparison.",
            )

        # Build per-scope definitions
        definitions: List[ScopeDefinition] = []
        per_scope_parts: List[str] = []

        for slug, chunks in scope_chunks.items():
            top_chunks = chunks[: self.top_k_per_scope]
            if not top_chunks:
                per_scope_parts.append(f"**{slug}**: [No relevant content found]")
                definitions.append(ScopeDefinition(scope_slug=slug, text="[not found]"))
                continue

            combined_text = "\n".join(
                c.get(content_key) or c.get("text") or "" for c in top_chunks
            )
            section = (
                top_chunks[0].get("section")
                or top_chunks[0].get("metadata", {}).get("section_number", "")
                or "Unknown"
            )
            per_scope_parts.append(f"**{slug}** (Source: {section}):\n{combined_text}")
            definitions.append(
                ScopeDefinition(scope_slug=slug, text=combined_text, source_section=section)
            )

        prompt = COMPARISON_PROMPT.format(
            concept=concept,
            n=len(scope_chunks),
            per_scope_definitions="\n\n---\n\n".join(per_scope_parts),
        )

        try:
            raw = await self.llm_call_fn(prompt, self.max_tokens, self.temperature)
            has_divergences = "⚠️" in raw or "divergen" in raw.lower()

            return ComparisonResult(
                concept=concept,
                scopes_compared=list(scope_chunks.keys()),
                raw_markdown=raw.strip(),
                definitions=definitions,
                has_divergences=has_divergences,
            )

        except Exception as exc:
            logger.error("[ComparisonMode] LLM call failed: %s", exc)
            return ComparisonResult(
                concept=concept,
                scopes_compared=list(scope_chunks.keys()),
                raw_markdown=f"Comparison failed: {exc}",
            )

    def compare_sync(
        self, concept: str, scope_chunks: Dict[str, List[Dict]]
    ) -> ComparisonResult:
        """Synchronous fallback."""
        return ComparisonResult(
            concept=concept,
            raw_markdown="Sync mode — LLM requires async",
        )
