"""
Phase 11.4 / 14.3 — Structured Extraction Mode (/extract).

Produces machine-readable JSON from retrieved context, extracting:
- Deal name, type, closing date
- Parties and roles
- Key dates, amounts
- Defined terms
- Source sections
- Extraction gaps (fields not found)

JSON schema is enforced at the prompt level.  LLM output is parsed with
``json.loads()``; if parsing fails the raw response is returned with a flag.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Extraction Schema ─────────────────────────────────────────

EXTRACTION_SCHEMA = {
    "deal_name": "string or null",
    "deal_type": "string or null",
    "closing_date": "ISO date string or null",
    "parties": {
        "Depositor": "string or null",
        "Trustee": "string or null",
        "Master Servicer": "string or null",
        "Servicer": "string or null",
        "Certificate Registrar": "string or null",
    },
    "key_dates": {
        "Closing Date": "string or null",
        "Distribution Date": "string or null",
        "Determination Date": "string or null",
        "Record Date": "string or null",
        "Optional Termination Date": "string or null",
    },
    "key_amounts": {},
    "defined_terms": {},
    "source_sections": ["list of section references"],
    "confidence": "High | Medium | Low",
    "extraction_gaps": ["list of fields not found"],
}

EXTRACTION_PROMPT = """Extract all available information from the provided document context and fill
the following JSON schema. Use null for fields not found. Do not invent data.

Schema:
{schema_json}

For extraction_gaps: list field names where you searched but found no answer.

Return ONLY the JSON object. No preamble, no explanation.

Document context:
{context}"""


# ── Configuration ─────────────────────────────────────────────

@dataclass
class ExtractionConfig:
    """Configuration for extraction mode."""

    chunk_budget: int = 10
    temperature: float = 0.0
    max_output_tokens: int = 2000


# ── Result ────────────────────────────────────────────────────

@dataclass
class ExtractionResult:
    """Result of structured extraction."""

    data: Dict[str, Any]
    raw_response: str
    parsed_ok: bool
    extraction_gaps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data": self.data,
            "parsed_ok": self.parsed_ok,
            "extraction_gaps": self.extraction_gaps,
        }


# ── Extraction Mode ──────────────────────────────────────────

class ExtractionMode:
    """
    Structured extraction mode for /extract slash command.

    Usage::

        mode = ExtractionMode(llm_call_fn=my_llm_call)
        result = await mode.extract(chunks)
    """

    def __init__(
        self,
        llm_call_fn=None,
        config: Optional[ExtractionConfig] = None,
    ) -> None:
        self.llm_call_fn = llm_call_fn
        self.config = config or ExtractionConfig()

    async def extract(
        self,
        chunks: List[Dict[str, Any]],
        *,
        content_key: str = "content",
    ) -> ExtractionResult:
        """Run structured extraction against provided chunks."""
        if self.llm_call_fn is None:
            return ExtractionResult(
                data={},
                raw_response="",
                parsed_ok=False,
                extraction_gaps=["No LLM available"],
            )

        # Build context from chunks
        context_parts = []
        for i, chunk in enumerate(chunks[:self.config.chunk_budget]):
            text = chunk.get(content_key) or chunk.get("text") or ""
            source = chunk.get("source_path", f"chunk-{i}")
            context_parts.append(f"[{source}]\n{text}")
        context = "\n\n".join(context_parts)

        prompt = EXTRACTION_PROMPT.format(
            schema_json=json.dumps(EXTRACTION_SCHEMA, indent=2),
            context=context,
        )

        try:
            raw = await self.llm_call_fn(
                prompt,
                self.config.max_output_tokens,
                self.config.temperature,
            )
            raw = raw.strip()

            # Try to parse JSON
            try:
                # Handle markdown code blocks
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                    if raw.endswith("```"):
                        raw = raw[:-3]
                    raw = raw.strip()

                data = json.loads(raw)
                gaps = data.get("extraction_gaps", [])
                return ExtractionResult(
                    data=data,
                    raw_response=raw,
                    parsed_ok=True,
                    extraction_gaps=gaps,
                )
            except json.JSONDecodeError:
                logger.warning("[ExtractionMode] JSON parse failed, returning raw")
                return ExtractionResult(
                    data={"raw_text": raw},
                    raw_response=raw,
                    parsed_ok=False,
                    extraction_gaps=["JSON parse failed"],
                )

        except Exception as exc:
            logger.error("[ExtractionMode] LLM call failed: %s", exc)
            return ExtractionResult(
                data={},
                raw_response="",
                parsed_ok=False,
                extraction_gaps=[f"LLM error: {exc}"],
            )

    def extract_sync(self, chunks: List[Dict[str, Any]]) -> ExtractionResult:
        """Synchronous fallback — returns empty."""
        return ExtractionResult(
            data={},
            raw_response="",
            parsed_ok=False,
            extraction_gaps=["Sync mode — LLM call requires async"],
        )
