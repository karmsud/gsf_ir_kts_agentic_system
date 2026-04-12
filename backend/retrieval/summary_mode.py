"""
Phase 14.4 — Deal Summary Mode (/summary).

Generates a fixed 5-section structured deal summary against up to 30 chunks:

1. Parties
2. Key Dates
3. Key Amounts
4. Key Obligations
5. Risk Factors

Integrates with TemporalReasoner to annotate dates with "passed" / "future" status.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Prompt Template ───────────────────────────────────────────

SUMMARY_PROMPT = """Generate a structured deal summary from the following document context.
Use ONLY facts present in the provided context. Do not invent information.

{temporal_context}

The summary must contain exactly these five sections:

### 1. Parties
A markdown table with columns: Role | Entity

### 2. Key Dates
A markdown table with columns: Date Name | Value | Status
(Status = "Passed" if the date is before today, "Upcoming" if after, "Recurring" if periodic)

### 3. Key Amounts
A markdown table with columns: Item | Amount

### 4. Key Obligations
Bullet list of the most important obligations, duties, and covenants found.

### 5. Risk Factors
Bullet list of risk factors, limitations of liability, and material conditions.

At the end, add a confidence line:
*Confidence: [High/Medium/Low] | Sources: [list of section numbers] | Extraction gaps: [fields not found]*

Document context:
{context}
"""


# ── Configuration ─────────────────────────────────────────────

@dataclass
class SummaryConfig:
    """Configuration for summary mode."""

    chunk_budget: int = 20
    temperature: float = 0.5
    max_output_tokens: int = 4000


# ── Result ────────────────────────────────────────────────────

@dataclass
class SummaryResult:
    """Result of summary mode."""

    scope: str
    raw_markdown: str = ""
    sections_found: List[str] = field(default_factory=list)
    source_sections: List[str] = field(default_factory=list)
    confidence: str = "Low"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "raw_markdown": self.raw_markdown,
            "sections_found": self.sections_found,
            "source_sections": self.source_sections,
            "confidence": self.confidence,
        }


# ── Summary Mode ──────────────────────────────────────────────

class SummaryMode:
    """
    Summary mode for /summary slash command.

    Generates a fixed 5-section deal summary from retrieved context.

    Usage::

        mode = SummaryMode(llm_call_fn=my_llm_call)
        result = await mode.summarize(scope="bear_stearns_2006_HE1", chunks=chunks)
    """

    def __init__(
        self,
        llm_call_fn=None,
        config: Optional[SummaryConfig] = None,
        temporal_context: str = "",
    ) -> None:
        self.llm_call_fn = llm_call_fn
        self.config = config or SummaryConfig()
        self.temporal_context = temporal_context

    def _build_context(
        self, chunks: List[Dict[str, Any]], content_key: str = "content"
    ) -> str:
        """Build the context string from chunks."""
        parts: list[str] = []
        for i, chunk in enumerate(chunks[: self.config.chunk_budget], 1):
            text = chunk.get(content_key) or chunk.get("text") or ""
            section = (
                chunk.get("section")
                or chunk.get("metadata", {}).get("section_number", "")
                or f"Chunk {i}"
            )
            source = chunk.get("source") or chunk.get("metadata", {}).get("source", "")
            header = f"[{section}]"
            if source:
                header += f" (Source: {source})"
            parts.append(f"{header}\n{text}")
        return "\n\n---\n\n".join(parts)

    async def summarize(
        self,
        scope: str,
        chunks: List[Dict[str, Any]],
        *,
        content_key: str = "content",
    ) -> SummaryResult:
        """Generate the 5-section deal summary."""
        if self.llm_call_fn is None:
            return SummaryResult(scope=scope, raw_markdown="No LLM available")

        context = self._build_context(chunks, content_key)
        prompt = SUMMARY_PROMPT.format(
            temporal_context=self.temporal_context,
            context=context,
        )

        try:
            raw = await self.llm_call_fn(
                prompt,
                self.config.max_output_tokens,
                self.config.temperature,
            )

            # Parse which sections are present
            section_headers = [
                "Parties", "Key Dates", "Key Amounts",
                "Key Obligations", "Risk Factors",
            ]
            sections_found = [
                h for h in section_headers if h.lower() in raw.lower()
            ]

            # Try to extract confidence line
            confidence = "Medium"
            if "confidence: high" in raw.lower():
                confidence = "High"
            elif "confidence: low" in raw.lower():
                confidence = "Low"

            # Parse source sections from confidence footer
            import re
            source_sections: list[str] = []
            src_match = re.search(r"Sources?:\s*([^|*]+)", raw)
            if src_match:
                source_sections = [
                    s.strip() for s in src_match.group(1).split(",")
                    if s.strip()
                ]

            return SummaryResult(
                scope=scope,
                raw_markdown=raw.strip(),
                sections_found=sections_found,
                source_sections=source_sections,
                confidence=confidence,
            )

        except Exception as exc:
            logger.error("[SummaryMode] LLM call failed: %s", exc)
            return SummaryResult(
                scope=scope,
                raw_markdown=f"Summary generation failed: {exc}",
            )

    def summarize_sync(self, scope: str, chunks: List[Dict[str, Any]]) -> SummaryResult:
        """Synchronous fallback."""
        return SummaryResult(scope=scope, raw_markdown="Sync mode — LLM requires async")
