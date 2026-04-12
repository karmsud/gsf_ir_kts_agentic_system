"""
Phase 13.4 — Hypothetical Document Embeddings (HyDE).

Instead of embedding the raw user query, generate a *hypothetical* answer
paragraph using a fast LLM call, then embed that paragraph and use it as the
query vector for similarity search.

The hypothetical is domain-specific, dense with legal terminology, and
semantically close to what a real answer chunk looks like.  This bridges
the vocabulary mismatch between user queries ("What is the Determination Date?")
and document text ("Determination Date means the 25th day of each calendar
month…").

Feature-flagged: ``enable_hyde`` (default ON for definition/lookup queries).
Falls back to direct query embedding on LLM failure.

Reference: Gao et al. 2022 — "Precise Zero-Shot Dense Retrieval without
Relevance Labels" (HyDE).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ── HyDE Prompt Templates ────────────────────────────────────

HYDE_PROMPT_LEGAL = """Generate a single paragraph that would perfectly answer the following question about a legal/financial document. Write in formal document language matching the style of a {doc_type}. Be specific and use domain terminology.

Question: {query}

Hypothetical answer paragraph:"""

HYDE_PROMPT_GUIDE = """Generate a single paragraph that would perfectly answer the following question from an internal knowledge base or troubleshooting guide. Write in clear technical language matching internal documentation.

Question: {query}

Hypothetical answer paragraph:"""


# ── Configuration ─────────────────────────────────────────────

@dataclass
class HyDEConfig:
    """Configuration for Hypothetical Document Embeddings."""

    enabled: bool = True
    max_tokens: int = 150
    temperature: float = 0.3

    # Only apply HyDE to certain query types
    definition_queries_only: bool = False  # False = apply to all queries when enabled

    # Fallback behaviour
    fallback_on_failure: bool = True  # Use original query on LLM error

    # Cost control
    max_query_length: int = 200  # Skip HyDE for very long queries (already specific)


# ── Result ────────────────────────────────────────────────────

@dataclass
class HyDEResult:
    """Result of HyDE processing."""

    original_query: str
    hypothetical: Optional[str]
    query_for_embedding: str  # Either hypothetical or original
    hyde_applied: bool
    skip_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_query": self.original_query,
            "hypothetical": self.hypothetical,
            "query_for_embedding": self.query_for_embedding,
            "hyde_applied": self.hyde_applied,
            "skip_reason": self.skip_reason,
        }


# ── Query Classification ─────────────────────────────────────

_DEFINITION_SIGNALS = re.compile(
    r'\b(what\s+(?:is|does|are)|define|definition\s+of|meaning\s+of|means?\b'
    r'|term\s|who\s+is|when\s+is|where\s+is)\b',
    re.IGNORECASE,
)

_LOOKUP_SIGNALS = re.compile(
    r'\b(what\s+(?:is|are)|who\s+(?:is|are)|when\s+(?:is|does)|where|which\s+section'
    r'|find|locate|show\s+me|obligations?\s+of)\b',
    re.IGNORECASE,
)


def is_definition_query(query: str) -> bool:
    """Check if the query is asking for a definition or term lookup."""
    return bool(_DEFINITION_SIGNALS.search(query))


def is_lookup_query(query: str) -> bool:
    """Check if the query is a factual lookup (definition, date, party, etc.)."""
    return bool(_LOOKUP_SIGNALS.search(query))


# ── HyDE Processor ───────────────────────────────────────────

class HyDEProcessor:
    """
    Hypothetical Document Embedding processor.

    Generates a hypothetical answer paragraph, which is then used as the
    embedding query instead of the raw user question.

    Usage::

        hyde = HyDEProcessor(llm_call_fn=my_llm_call)
        result = await hyde.process(query, doc_type="PSA")
        # result.query_for_embedding — use this for vector search
    """

    def __init__(
        self,
        llm_call_fn=None,
        config: Optional[HyDEConfig] = None,
    ) -> None:
        """
        Parameters
        ----------
        llm_call_fn : callable or None
            An async function ``(prompt: str, max_tokens: int, temperature: float) -> str``
            that calls the LLM.  If None, HyDE is a no-op (passthrough).
        config : HyDEConfig or None
            Configuration.  Defaults used if None.
        """
        self.llm_call_fn = llm_call_fn
        self.config = config or HyDEConfig()

    async def process(
        self,
        query: str,
        *,
        doc_type: str = "Pooling and Servicing Agreement",
        corpus_regime: str = "MIXED",
    ) -> HyDEResult:
        """
        Generate a hypothetical answer and return it for embedding.

        Returns the original query if HyDE is disabled, the query is
        already too specific, or the LLM call fails.
        """
        # Check: enabled?
        if not self.config.enabled:
            return HyDEResult(
                original_query=query,
                hypothetical=None,
                query_for_embedding=query,
                hyde_applied=False,
                skip_reason="HyDE disabled",
            )

        # Check: LLM available?
        if self.llm_call_fn is None:
            return HyDEResult(
                original_query=query,
                hypothetical=None,
                query_for_embedding=query,
                hyde_applied=False,
                skip_reason="No LLM function provided",
            )

        # Check: query too long (already specific)?
        if len(query) > self.config.max_query_length:
            return HyDEResult(
                original_query=query,
                hypothetical=None,
                query_for_embedding=query,
                hyde_applied=False,
                skip_reason=f"Query too long ({len(query)} chars > {self.config.max_query_length})",
            )

        # Check: definition-only mode?
        if self.config.definition_queries_only and not is_definition_query(query):
            return HyDEResult(
                original_query=query,
                hypothetical=None,
                query_for_embedding=query,
                hyde_applied=False,
                skip_reason="Not a definition query (def-only mode)",
            )

        # Select prompt template based on corpus regime
        if corpus_regime in ("GOVERNING_DOC_LEGAL", "MIXED"):
            prompt = HYDE_PROMPT_LEGAL.format(query=query, doc_type=doc_type)
        else:
            prompt = HYDE_PROMPT_GUIDE.format(query=query)

        # Call LLM
        try:
            hypothetical = await self.llm_call_fn(
                prompt,
                self.config.max_tokens,
                self.config.temperature,
            )
            hypothetical = hypothetical.strip()

            if not hypothetical or len(hypothetical) < 20:
                logger.warning("[HyDE] LLM returned empty/short hypothetical, using original query")
                return HyDEResult(
                    original_query=query,
                    hypothetical=None,
                    query_for_embedding=query,
                    hyde_applied=False,
                    skip_reason="LLM returned empty hypothetical",
                )

            logger.debug("[HyDE] Generated hypothetical (%d chars) for query: '%s'", len(hypothetical), query[:60])
            return HyDEResult(
                original_query=query,
                hypothetical=hypothetical,
                query_for_embedding=hypothetical,
                hyde_applied=True,
            )

        except Exception as exc:
            logger.warning("[HyDE] LLM call failed: %s — falling back to original query", exc)
            if self.config.fallback_on_failure:
                return HyDEResult(
                    original_query=query,
                    hypothetical=None,
                    query_for_embedding=query,
                    hyde_applied=False,
                    skip_reason=f"LLM error: {exc}",
                )
            raise

    def process_sync(
        self,
        query: str,
        *,
        doc_type: str = "Pooling and Servicing Agreement",
        corpus_regime: str = "MIXED",
    ) -> HyDEResult:
        """
        Synchronous wrapper for environments without an event loop.

        Falls back to passthrough (no HyDE) since LLM calls are async.
        """
        if not self.config.enabled:
            return HyDEResult(
                original_query=query,
                hypothetical=None,
                query_for_embedding=query,
                hyde_applied=False,
                skip_reason="HyDE disabled (sync mode)",
            )

        return HyDEResult(
            original_query=query,
            hypothetical=None,
            query_for_embedding=query,
            hyde_applied=False,
            skip_reason="Sync mode — LLM call requires async",
        )
