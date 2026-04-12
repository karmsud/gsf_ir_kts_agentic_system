"""
Phase 10.2 — Query Rewriting via Coreference Resolution.

When a user's follow-up question contains coreferences ("it", "same rule",
"which"), this module rewrites the question as a fully standalone query by
incorporating context from the conversation history.

Signal-gated: Only invokes the LLM when coreference signals are detected.
Falls back to the original query on LLM failure.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Coreference Signals ───────────────────────────────────────

COREFERENCE_SIGNALS = [
    "it", "this", "that", "they", "them", "its",
    "same", "which", "those", "both", "either",
    "the above", "the same", "as well", "too",
    "also", "likewise", "one", "ones",
    "here", "there", "so",
]

_SIGNAL_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(s) for s in COREFERENCE_SIGNALS) + r')\b',
    re.IGNORECASE,
)


# ── Prompt Template ───────────────────────────────────────────

REWRITE_PROMPT = """You are helping a legal document retrieval system.
Given a conversation history and a new question, rewrite the question as a
fully self-contained, specific query that can be answered without any context
from the conversation history. Resolve all pronouns and references.

If the question is already standalone, return it unchanged.
Return ONLY the rewritten query, no explanation.

Conversation history:
{history}

New question: {query}

Standalone query:"""


# ── Configuration ─────────────────────────────────────────────

@dataclass
class QueryRewriterConfig:
    """Configuration for query rewriting."""

    enabled: bool = True
    max_history_turns: int = 6  # Last 3 exchanges (6 turns)
    max_output_tokens: int = 150
    min_query_words_skip: int = 8  # Skip rewrite for long specific queries
    temperature: float = 0.1


# ── Result ────────────────────────────────────────────────────

@dataclass
class RewriteResult:
    """Result of query rewriting."""

    original_query: str
    rewritten_query: str
    was_rewritten: bool
    skip_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_query": self.original_query,
            "rewritten_query": self.rewritten_query,
            "was_rewritten": self.was_rewritten,
            "skip_reason": self.skip_reason,
        }


# ── History Formatting ────────────────────────────────────────

def format_history(turns: List[Dict[str, str]], max_turns: int = 6) -> str:
    """Format conversation turns for the rewrite prompt."""
    recent = turns[-max_turns:] if len(turns) > max_turns else turns
    lines = []
    for turn in recent:
        role = turn.get("role", "user").capitalize()
        content = turn.get("content", "")[:500]  # Truncate long responses
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _needs_rewrite(query: str, min_words_skip: int) -> bool:
    """Check if the query contains coreference signals."""
    # Short queries with pronouns almost always need rewriting
    if _SIGNAL_PATTERN.search(query):
        return True

    # Very short queries (1-3 words) often need context
    if len(query.split()) <= 3:
        return True

    # Long specific queries are usually standalone
    if len(query.split()) > min_words_skip:
        return False

    return False


# ── QueryRewriter ─────────────────────────────────────────────

class QueryRewriter:
    """
    Resolve coreferences in follow-up questions using conversation history.

    Usage::

        rewriter = QueryRewriter(llm_call_fn=my_llm_call)
        result = await rewriter.rewrite(
            query="And what happens if it falls on a weekend?",
            history=[
                {"role": "user", "content": "What is the Determination Date?"},
                {"role": "assistant", "content": "The Determination Date is..."}
            ]
        )
        # result.rewritten_query ==
        # "What happens if the Determination Date falls on a non-business day?"
    """

    def __init__(
        self,
        llm_call_fn: Optional[Callable] = None,
        config: Optional[QueryRewriterConfig] = None,
    ) -> None:
        self.llm_call_fn = llm_call_fn
        self.config = config or QueryRewriterConfig()

    async def rewrite(
        self,
        query: str,
        history: List[Dict[str, str]],
    ) -> RewriteResult:
        """
        Rewrite a query to be standalone using conversation history.

        Returns the original query unchanged if:
        - History is empty (first turn)
        - No coreference signals detected
        - LLM is not available
        - LLM call fails
        """
        # Fast path: no history = first turn, nothing to resolve
        if not history:
            return RewriteResult(
                original_query=query,
                rewritten_query=query,
                was_rewritten=False,
                skip_reason="No history (first turn)",
            )

        # Fast path: disabled
        if not self.config.enabled:
            return RewriteResult(
                original_query=query,
                rewritten_query=query,
                was_rewritten=False,
                skip_reason="Rewriting disabled",
            )

        # Fast path: no coreference signals
        if not _needs_rewrite(query, self.config.min_query_words_skip):
            return RewriteResult(
                original_query=query,
                rewritten_query=query,
                was_rewritten=False,
                skip_reason="No coreference signals detected",
            )

        # Fast path: no LLM
        if self.llm_call_fn is None:
            return RewriteResult(
                original_query=query,
                rewritten_query=query,
                was_rewritten=False,
                skip_reason="No LLM function provided",
            )

        # Build prompt
        history_text = format_history(history, self.config.max_history_turns)
        prompt = REWRITE_PROMPT.format(history=history_text, query=query)

        try:
            rewritten = await self.llm_call_fn(
                prompt,
                self.config.max_output_tokens,
                self.config.temperature,
            )
            rewritten = rewritten.strip()

            # Sanity check: LLM should return something reasonable
            if not rewritten or len(rewritten) < 3:
                logger.warning("[QueryRewriter] LLM returned empty, using original")
                return RewriteResult(
                    original_query=query,
                    rewritten_query=query,
                    was_rewritten=False,
                    skip_reason="LLM returned empty rewrite",
                )

            # Check if rewrite is identical to original
            if rewritten.lower().strip("?.! ") == query.lower().strip("?.! "):
                return RewriteResult(
                    original_query=query,
                    rewritten_query=query,
                    was_rewritten=False,
                    skip_reason="Rewrite identical to original",
                )

            logger.debug(
                "[QueryRewriter] Rewrote '%s' → '%s'",
                query[:60], rewritten[:60],
            )
            return RewriteResult(
                original_query=query,
                rewritten_query=rewritten,
                was_rewritten=True,
            )

        except Exception as exc:
            logger.warning("[QueryRewriter] LLM call failed: %s", exc)
            return RewriteResult(
                original_query=query,
                rewritten_query=query,
                was_rewritten=False,
                skip_reason=f"LLM error: {exc}",
            )

    def rewrite_sync(
        self,
        query: str,
        history: List[Dict[str, str]],
    ) -> RewriteResult:
        """
        Synchronous heuristic rewrite — no LLM required.

        Uses rule-based coreference resolution:
        1. Detects coreference signals in the query.
        2. Extracts the likely subject from the last user turn.
        3. Replaces pronouns with the extracted subject.

        This is a best-effort approach for the sync pipeline. The async
        ``rewrite()`` method with an LLM produces better results when available.
        """
        # Fast path: no history
        if not history:
            return RewriteResult(
                original_query=query,
                rewritten_query=query,
                was_rewritten=False,
                skip_reason="No history (first turn)",
            )

        # Fast path: disabled
        if not self.config.enabled:
            return RewriteResult(
                original_query=query,
                rewritten_query=query,
                was_rewritten=False,
                skip_reason="Rewriting disabled",
            )

        # Fast path: no coreference signals
        if not _needs_rewrite(query, self.config.min_query_words_skip):
            return RewriteResult(
                original_query=query,
                rewritten_query=query,
                was_rewritten=False,
                skip_reason="No coreference signals detected",
            )

        # Extract subject from the last user query in history
        subject = _extract_subject_from_history(history)
        if not subject:
            return RewriteResult(
                original_query=query,
                rewritten_query=query,
                was_rewritten=False,
                skip_reason="Could not extract subject from history",
            )

        # Apply heuristic pronoun replacement
        rewritten = _heuristic_rewrite(query, subject)
        if rewritten and rewritten.lower().strip() != query.lower().strip():
            logger.debug(
                "[QueryRewriter.sync] Heuristic rewrite: '%s' → '%s'",
                query[:60], rewritten[:60],
            )
            return RewriteResult(
                original_query=query,
                rewritten_query=rewritten,
                was_rewritten=True,
            )

        return RewriteResult(
            original_query=query,
            rewritten_query=query,
            was_rewritten=False,
            skip_reason="Heuristic rewrite produced no change",
        )


def _extract_subject_from_history(
    history: List[Dict[str, str]],
) -> Optional[str]:
    """
    Extract the most likely subject/entity from the last user turn in history.

    Looks for quoted terms, capitalised noun phrases, and common patterns
    like "What is the X?" or "Tell me about X".
    """
    # Walk backwards to find the last user turn
    last_user = None
    for turn in reversed(history):
        if turn.get("role") == "user":
            last_user = turn.get("content", "")
            break

    if not last_user:
        return None

    # Try common question patterns: "What is the X?", "Tell me about X"
    patterns = [
        r"(?:what|who|where|when|how)\s+(?:is|are|was|were)\s+(?:the\s+)?(.+?)(?:\?|$)",
        r"(?:tell|explain|describe|define)\s+(?:me\s+)?(?:about\s+)?(?:the\s+)?(.+?)(?:\?|$)",
        r"(?:what|how)\s+(?:does|do|did)\s+(?:the\s+)?(.+?)\s+(?:work|mean|look|apply)",
        r'"([^"]+)"',  # Quoted terms
    ]

    for p in patterns:
        m = re.search(p, last_user, re.IGNORECASE)
        if m:
            subject = m.group(1).strip().rstrip("?.!, ")
            if 2 <= len(subject.split()) <= 8:
                return subject

    # Fallback: extract the longest capitalised phrase (likely a proper noun / defined term)
    cap_phrases = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', last_user)
    if cap_phrases:
        return max(cap_phrases, key=len)

    # Last resort: take the noun-like core of the last user query
    # Strip question words and return the rest
    stripped = re.sub(
        r'^(?:what|who|where|when|how|tell|explain|describe|can you)\s+(?:is|are|was|were|me|about|the)?\s*',
        '', last_user, flags=re.IGNORECASE,
    ).strip().rstrip("?.!, ")
    if stripped and len(stripped.split()) <= 6:
        return stripped

    return None


def _heuristic_rewrite(query: str, subject: str) -> str:
    """
    Replace coreference pronouns in *query* with *subject*.

    Conservative: only replaces whole-word pronouns bound to the subject.
    """
    # Map of pronouns to replacement patterns
    pronoun_map = {
        r'\bit\b': subject,
        r'\bits\b': f"{subject}'s",
        r'\bthis\b': f"the {subject}" if not subject.lower().startswith("the ") else subject,
        r'\bthat\b': f"the {subject}" if not subject.lower().startswith("the ") else subject,
        r'\bthe above\b': f"the {subject}" if not subject.lower().startswith("the ") else subject,
        r'\bthe same\b': f"the same {subject}",
    }

    rewritten = query
    for pattern, replacement in pronoun_map.items():
        rewritten = re.sub(pattern, replacement, rewritten, count=1, flags=re.IGNORECASE)

    return rewritten
