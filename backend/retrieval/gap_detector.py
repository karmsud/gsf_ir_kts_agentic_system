"""
Phase 13.2 — Proactive Gap Detection.

After retrieval, compares requested entities (NER on query) against found
entities (NER on retrieved chunks).  Any terms mentioned in the query but
not present in the retrieved context are reported as *gaps*.

Gaps are surfaced to the user as explicit "not found" notices, which is
more honest than a hallucinated answer and builds durable trust.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)


# ── Result ────────────────────────────────────────────────────

@dataclass
class GapResult:
    """Result of gap analysis between query and retrieved context."""

    gaps: List[str]
    requested_terms: List[str]
    found_terms: List[str]
    coverage: float  # fraction of requested terms found
    display_text: str
    has_gaps: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gaps": self.gaps,
            "requested_terms": self.requested_terms,
            "found_terms": self.found_terms,
            "coverage": round(self.coverage, 3),
            "display_text": self.display_text,
            "has_gaps": self.has_gaps,
        }


# ── Entity Extraction (lightweight, no spaCy dependency) ─────

# Patterns for structured finance / legal terms
_TITLE_CASE_RE = re.compile(
    r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b'
)
_QUOTED_TERM_RE = re.compile(
    r'["\u201c]([^"\u201d]+)["\u201d]'
)
_DEFINED_TERM_RE = re.compile(
    r'\b([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*){1,5})\b'
)
_ERROR_CODE_RE = re.compile(
    r'\bERR-[A-Z]+-\d{3}\b'
    r'|\bHTTP\s*\d{3}\b'
    r'|\b[A-Z]+\d{3,4}\b',
    re.IGNORECASE,
)

# Common words that look like Title Case terms but aren't
_STOP_PHRASES = {
    "the", "this", "that", "these", "those", "what", "which",
    "where", "when", "how", "who", "does", "has", "have",
    "section", "article", "page", "document", "file",
    "please", "thank", "show", "tell", "find", "list",
    "also", "between", "under", "above", "below",
}


def extract_entities(text: str) -> List[str]:
    """
    Extract candidate entities from text using heuristic patterns.

    Extracts:
    - Title Case multi-word phrases (e.g. "Determination Date")
    - Quoted terms
    - Error codes
    - Capital-letter defined terms (e.g. "DSCR")

    Returns deduplicated list ordered by position of first appearance.
    """
    entities: List[str] = []
    seen: Set[str] = set()

    def _add(term: str) -> None:
        normalised = term.strip()
        key = normalised.lower()
        if key in seen or len(normalised) < 3:
            return
        # Filter stop phrases
        if key in _STOP_PHRASES:
            return
        # Filter single very common words
        if len(normalised.split()) == 1 and key.lower() in _STOP_PHRASES:
            return
        seen.add(key)
        entities.append(normalised)

    # Priority 1: Quoted terms
    for m in _QUOTED_TERM_RE.finditer(text):
        _add(m.group(1))

    # Priority 2: Error codes
    for m in _ERROR_CODE_RE.finditer(text):
        _add(m.group())

    # Priority 3: Title Case phrases (multi-word)
    for m in _TITLE_CASE_RE.finditer(text):
        _add(m.group(1))

    # Priority 4: All-caps abbreviations (DSCR, REMIC, WAC, etc.)
    for m in re.finditer(r'\b([A-Z]{2,6})\b', text):
        term = m.group(1)
        if term not in {"THE", "AND", "FOR", "NOT", "BUT", "ARE", "WAS", "HAS", "ALL"}:
            _add(term)

    return entities


# ── Gap Detector ──────────────────────────────────────────────

class GapDetector:
    """
    Detect terms mentioned in the query but absent from retrieved context.

    Usage::

        detector = GapDetector()
        result = detector.detect(query, retrieved_chunks)
        if result.has_gaps:
            print(result.display_text)
    """

    def __init__(
        self,
        *,
        min_term_length: int = 3,
        fuzzy_match: bool = True,
    ) -> None:
        self.min_term_length = min_term_length
        self.fuzzy_match = fuzzy_match

    def detect(
        self,
        query: str,
        retrieved_chunks: List[Dict[str, Any]],
        *,
        content_key: str = "content",
        text_key: str = "text",
    ) -> GapResult:
        """
        Compare requested entities (from query) against found entities
        (from retrieved chunks).  Return gaps.
        """
        # Extract entities from query
        requested = extract_entities(query)
        if not requested:
            return GapResult(
                gaps=[],
                requested_terms=[],
                found_terms=[],
                coverage=1.0,
                display_text="",
                has_gaps=False,
            )

        # Build combined text from retrieved chunks
        chunk_texts = []
        for c in retrieved_chunks:
            text = c.get(content_key) or c.get(text_key) or ""
            chunk_texts.append(text)
        combined = " ".join(chunk_texts).lower()

        # Check each requested term against combined text
        found: List[str] = []
        gaps: List[str] = []
        for term in requested:
            if self._term_found(term, combined):
                found.append(term)
            else:
                gaps.append(term)

        coverage = len(found) / len(requested) if requested else 1.0

        # Build display text
        display = ""
        if gaps:
            gap_list = ", ".join(f"**{g}**" for g in gaps)
            display = (
                f"> ⚠️ Note: The following terms were requested but could not be "
                f"located in the indexed documents: {gap_list}. These may be "
                f"defined using alternate terminology or located in a section "
                f"not yet indexed."
            )

        return GapResult(
            gaps=gaps,
            requested_terms=requested,
            found_terms=found,
            coverage=coverage,
            display_text=display,
            has_gaps=bool(gaps),
        )

    def _term_found(self, term: str, combined_lower: str) -> bool:
        """Check if a term appears in the combined chunk text."""
        term_lower = term.lower()

        # Exact substring match
        if term_lower in combined_lower:
            return True

        # Fuzzy: check each word of multi-word term
        if self.fuzzy_match and len(term.split()) > 1:
            words = term_lower.split()
            found_count = sum(1 for w in words if w in combined_lower)
            # If most words of the term are found, it's probably there
            if found_count >= len(words) * 0.7:
                return True

        return False
