"""
Phase 11.4 — Definition Mode (/define).

Retrieves only definitional chunks for a term and outputs:
  term + definition + source section.

No inference — direct extraction from retrieved context.
Temperature is pinned at 0.0 for deterministic output.
Chunk budget is small (3) since definitions are tightly scoped.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Prompt Template ───────────────────────────────────────────

DEFINITION_PROMPT = """You are a legal-term definition extractor. Your task is to \
provide the precise definition of the term "{term}" based ONLY on the provided \
document context. Do NOT infer or paraphrase — extract the definition verbatim.

Output format:
**{term}** — <verbatim definition from the source>

Source: <section number and document name where the definition appears>

If the term appears in multiple sections, list each occurrence separately.
If the term is not found in the context, state: "Term not found in current scope."

Document context:
{context}
"""


# ── Configuration ─────────────────────────────────────────────

@dataclass
class DefinitionConfig:
    """Configuration for definition mode."""

    chunk_budget: int = 3
    temperature: float = 0.0
    max_output_tokens: int = 1000


# ── Result ────────────────────────────────────────────────────

@dataclass
class DefinitionEntry:
    """A single term definition found."""

    term: str
    definition: str
    source_section: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "term": self.term,
            "definition": self.definition,
            "source_section": self.source_section,
        }


@dataclass
class DefinitionResult:
    """Result of definition mode."""

    term: str
    entries: List[DefinitionEntry] = field(default_factory=list)
    raw_response: str = ""
    found: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "term": self.term,
            "entries": [e.to_dict() for e in self.entries],
            "raw_response": self.raw_response,
            "found": self.found,
        }


# ── Definition Extraction ────────────────────────────────────

# Pattern to detect definitions in legal text: "Term" means ...
_DEFINITION_RE = re.compile(
    r'["\u201c]([A-Z][A-Za-z\s]+?)["\u201d]\s+(?:means|shall mean|is defined as|refers to)\s+(.+?)(?:\.|$)',
    re.MULTILINE,
)


def extract_definitions_from_text(text: str, target_term: str = "") -> List[DefinitionEntry]:
    """Extract term definitions from raw text using regex patterns."""
    entries: List[DefinitionEntry] = []
    target_lower = target_term.lower().strip()

    for m in _DEFINITION_RE.finditer(text):
        term = m.group(1).strip()
        definition = m.group(2).strip()
        if target_lower and term.lower() != target_lower:
            continue
        entries.append(DefinitionEntry(
            term=term,
            definition=definition,
            source_section="",
        ))

    return entries


# ── Definition Mode ──────────────────────────────────────────

class DefinitionMode:
    """
    Definition mode for /define slash command.

    Retrieves definitional chunks for a term and outputs
    term + definition + source section with zero inference.

    Usage::

        mode = DefinitionMode(llm_call_fn=my_llm_call)
        result = await mode.define("Servicer", chunks)
    """

    def __init__(
        self,
        llm_call_fn=None,
        config: Optional[DefinitionConfig] = None,
    ) -> None:
        self.llm_call_fn = llm_call_fn
        self.config = config or DefinitionConfig()

    async def define(
        self,
        term: str,
        chunks: List[Dict[str, Any]],
        *,
        content_key: str = "content",
    ) -> DefinitionResult:
        """Look up the definition of a term from provided chunks."""
        # First, try direct regex extraction from chunk text
        all_text = "\n".join(
            c.get(content_key) or c.get("text") or "" for c in chunks[:self.config.chunk_budget]
        )
        direct_entries = extract_definitions_from_text(all_text, term)

        if direct_entries:
            # Annotate with section info from chunks
            for entry in direct_entries:
                for chunk in chunks:
                    text = chunk.get(content_key) or chunk.get("text") or ""
                    if entry.definition in text:
                        entry.source_section = (
                            chunk.get("section")
                            or chunk.get("metadata", {}).get("section_number", "")
                            or "Unknown Section"
                        )
                        break
            return DefinitionResult(
                term=term,
                entries=direct_entries,
                raw_response="\n".join(
                    f'**{e.term}** \u2014 {e.definition} (Source: {e.source_section})'
                    for e in direct_entries
                ),
                found=True,
            )

        # Fallback to LLM if available
        if self.llm_call_fn is None:
            return DefinitionResult(term=term, raw_response="No LLM available and term not found via regex")

        context_parts = []
        for chunk in chunks[:self.config.chunk_budget]:
            section = (
                chunk.get("section")
                or chunk.get("metadata", {}).get("section_number", "")
                or "Unknown Section"
            )
            text = chunk.get(content_key) or chunk.get("text") or ""
            context_parts.append(f"[Section: {section}]\n{text}")
        context = "\n\n".join(context_parts)

        prompt = DEFINITION_PROMPT.format(term=term, context=context)

        try:
            raw = await self.llm_call_fn(
                prompt,
                self.config.max_output_tokens,
                self.config.temperature,
            )
            found = "not found" not in raw.lower()
            return DefinitionResult(
                term=term,
                raw_response=raw.strip(),
                found=found,
            )
        except Exception as exc:
            logger.error("[DefinitionMode] LLM call failed: %s", exc)
            return DefinitionResult(
                term=term,
                raw_response=f"Definition lookup failed: {exc}",
            )

    def define_sync(self, term: str, chunks: List[Dict[str, Any]]) -> DefinitionResult:
        """Synchronous fallback."""
        return DefinitionResult(term=term, raw_response="Sync mode \u2014 LLM requires async")
