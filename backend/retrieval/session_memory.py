"""
Phase 10.3 — Entity Session Memory & Document Bias.
Phase 14.1 — Session Deal Summary Cache (integrated).

In-process session dictionary keyed by ``session_id``.  Tracks:
- Resolved defined terms → cached answers (zero-cost recall on subsequent turns)
- Active documents → retrieval bias (15% boost for in-context docs)
- Active sections → scope awareness
- Deal summary (Phase 14.1) → progressive population from answers

TTL: 4 hours since last access.  VS Code window lifetime is the session.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ── Constants ─────────────────────────────────────────────────

DEFAULT_TTL_HOURS = 4
MAX_SESSIONS = 100  # Evict oldest when exceeded
DOCUMENT_BIAS_BOOST = 1.15  # 15% boost for in-context documents


# ── Deal Summary (Phase 14.1) ────────────────────────────────

@dataclass
class DealSummary:
    """Progressive deal summary built from resolved queries."""

    scope: str = ""
    deal_name: Optional[str] = None
    doc_types_present: List[str] = field(default_factory=list)

    # Populated progressively as user asks questions
    parties: Dict[str, str] = field(default_factory=dict)
    key_dates: Dict[str, str] = field(default_factory=dict)
    key_amounts: Dict[str, str] = field(default_factory=dict)
    defined_terms: Dict[str, str] = field(default_factory=dict)
    cited_sections: Set[str] = field(default_factory=set)

    turn_count: int = 0
    last_updated: Optional[datetime] = None

    def update_from_answer(
        self,
        *,
        terms: Optional[Dict[str, str]] = None,
        parties: Optional[Dict[str, str]] = None,
        dates: Optional[Dict[str, str]] = None,
        amounts: Optional[Dict[str, str]] = None,
        sections: Optional[List[str]] = None,
    ) -> None:
        """Incrementally update the deal summary from answer content."""
        if terms:
            self.defined_terms.update(terms)
        if parties:
            self.parties.update(parties)
        if dates:
            self.key_dates.update(dates)
        if amounts:
            self.key_amounts.update(amounts)
        if sections:
            self.cited_sections.update(sections)
        self.turn_count += 1
        self.last_updated = datetime.now()

    def lookup_term(self, term: str) -> Optional[str]:
        """Check if a term has been resolved in this session."""
        key = term.lower().strip()
        for k, v in self.defined_terms.items():
            if k.lower().strip() == key:
                return v
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "deal_name": self.deal_name,
            "doc_types_present": self.doc_types_present,
            "parties": self.parties,
            "key_dates": self.key_dates,
            "key_amounts": self.key_amounts,
            "defined_terms": self.defined_terms,
            "cited_sections": list(self.cited_sections),
            "turn_count": self.turn_count,
        }


# ── Session Memory ────────────────────────────────────────────

@dataclass
class SessionMemory:
    """Per-session state tracking for conversation intelligence."""

    session_id: str
    resolved_terms: Dict[str, str] = field(default_factory=dict)
    active_documents: List[str] = field(default_factory=list)
    active_sections: List[str] = field(default_factory=list)
    turn_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)

    # Phase 10.4: History summarisation
    rolling_summary: str = ""
    verbatim_recent_turns: List[Dict[str, str]] = field(default_factory=list)

    # Phase 14.1: Deal summary cache
    deal_summary: DealSummary = field(default_factory=DealSummary)

    def touch(self) -> None:
        """Update last-accessed timestamp."""
        self.last_accessed = datetime.now()
        self.turn_count += 1

    def add_active_document(self, doc_path: str) -> None:
        """Track a document seen in this session."""
        if doc_path and doc_path not in self.active_documents:
            self.active_documents.append(doc_path)
            # Keep recent 50
            if len(self.active_documents) > 50:
                self.active_documents = self.active_documents[-50:]

    def add_active_section(self, section_id: str) -> None:
        """Track a section retrieved in this session."""
        if section_id and section_id not in self.active_sections:
            self.active_sections.append(section_id)
            if len(self.active_sections) > 100:
                self.active_sections = self.active_sections[-100:]

    def resolve_term(self, term: str, definition: str) -> None:
        """Cache a resolved defined term."""
        self.resolved_terms[term] = definition

    def get_cached_term(self, term: str) -> Optional[str]:
        """Check session cache for a previously resolved term."""
        key = term.lower().strip()
        for k, v in self.resolved_terms.items():
            if k.lower().strip() == key:
                return v
        # Also check deal summary
        return self.deal_summary.lookup_term(term)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn_count": self.turn_count,
            "resolved_terms_count": len(self.resolved_terms),
            "active_documents": self.active_documents[:10],
            "active_sections": self.active_sections[:10],
            "deal_summary": self.deal_summary.to_dict(),
        }


# ── History Summarisation (Phase 10.4) ───────────────────────

SUMMARY_PROMPT = """You are maintaining a compact memory of a legal document Q&A session.

Existing summary: {existing_summary}
New turns to incorporate:
{new_turns}

Update the summary to include key facts established, defined terms resolved,
and documents discussed. Be concise — max 200 words. Preserve all specific
values (dates, amounts, party names). Return only the updated summary."""

MAX_VERBATIM_TURNS = 4


def should_summarise(session: SessionMemory) -> bool:
    """Check if verbatim history should be compressed into summary."""
    return len(session.verbatim_recent_turns) > MAX_VERBATIM_TURNS * 2


def build_summary_prompt(session: SessionMemory) -> Optional[str]:
    """Build the summarisation prompt if compression is needed."""
    if not should_summarise(session):
        return None

    # Oldest turns to compress
    to_compress = session.verbatim_recent_turns[:4]
    turns_text = "\n".join(
        f"{t.get('role', 'user').capitalize()}: {t.get('content', '')[:300]}"
        for t in to_compress
    )

    return SUMMARY_PROMPT.format(
        existing_summary=session.rolling_summary or "(none yet)",
        new_turns=turns_text,
    )


def apply_summary(session: SessionMemory, summary_text: str) -> None:
    """Apply the compressed summary and trim verbatim history."""
    session.rolling_summary = summary_text.strip()[:1000]
    # Keep only the most recent turns as verbatim
    session.verbatim_recent_turns = session.verbatim_recent_turns[4:]


def get_conversation_context(session: SessionMemory) -> List[Dict[str, str]]:
    """Build the conversation context to send with retrieval requests."""
    context = []

    # Include rolling summary as a system turn if available
    if session.rolling_summary:
        context.append({
            "role": "system",
            "content": f"Session summary: {session.rolling_summary}",
        })

    # Include verbatim recent turns
    context.extend(session.verbatim_recent_turns[-MAX_VERBATIM_TURNS * 2:])

    return context


# ── Document Bias ─────────────────────────────────────────────

def apply_document_bias(
    results: List[Dict[str, Any]],
    session: SessionMemory,
    *,
    boost_factor: float = DOCUMENT_BIAS_BOOST,
    score_key: str = "score",
) -> List[Dict[str, Any]]:
    """
    Boost scores for chunks from documents already seen in this session.

    Conservative: 15% boost, never filters.  New documents can still
    appear if they score well enough.
    """
    if not session.active_documents:
        return results

    active_set = set(session.active_documents)
    for chunk in results:
        source = chunk.get("source_path", "")
        doc_id = chunk.get("doc_id", "")
        if source in active_set or doc_id in active_set:
            original = chunk.get(score_key, 0.0)
            chunk[score_key] = original * boost_factor
            chunk["_document_biased"] = True

    results.sort(key=lambda c: c.get(score_key, 0), reverse=True)
    return results


# ── Session Store ─────────────────────────────────────────────

class SessionStore:
    """
    In-process session store keyed by session_id.

    Thread-safe for single-process use (GIL).  For multi-process,
    use a shared cache (not needed for VS Code extension architecture).

    Usage::

        store = SessionStore(ttl_hours=4)
        session = store.get_or_create("abc-123")
        session.resolve_term("Determination Date", "25th of month...")
        session.touch()
    """

    def __init__(self, ttl_hours: float = DEFAULT_TTL_HOURS) -> None:
        self._sessions: OrderedDict[str, SessionMemory] = OrderedDict()
        self._ttl = timedelta(hours=ttl_hours)

    def get_or_create(self, session_id: str) -> SessionMemory:
        """Get an existing session or create a new one."""
        self._evict_expired()

        if session_id in self._sessions:
            session = self._sessions[session_id]
            session.touch()
            # Move to end (most recently accessed)
            self._sessions.move_to_end(session_id)
            return session

        session = SessionMemory(session_id=session_id)
        self._sessions[session_id] = session

        # Enforce max sessions
        while len(self._sessions) > MAX_SESSIONS:
            self._sessions.popitem(last=False)

        logger.debug("[SessionStore] Created new session: %s", session_id)
        return session

    def get(self, session_id: str) -> Optional[SessionMemory]:
        """Get a session without creating one."""
        self._evict_expired()
        session = self._sessions.get(session_id)
        if session:
            session.touch()
        return session

    def remove(self, session_id: str) -> None:
        """Remove a session."""
        self._sessions.pop(session_id, None)

    def _evict_expired(self) -> None:
        """Remove sessions that have exceeded TTL."""
        now = datetime.now()
        expired = [
            sid for sid, s in self._sessions.items()
            if (now - s.last_accessed) > self._ttl
        ]
        for sid in expired:
            del self._sessions[sid]
            logger.debug("[SessionStore] Evicted expired session: %s", sid)

    def update_from_answer(
        self,
        session_id: str,
        answer_text: str,
        chunks: List[Dict[str, Any]],
    ) -> None:
        """
        Progressive population of session deal summary from an answer + chunks.

        Extracts parties, dates, amounts, and defined terms from the answer text
        and updates the session's DealSummary incrementally.
        """
        session = self.get_or_create(session_id)

        # Heuristic entity extraction from the answer text
        terms: Dict[str, str] = {}
        parties: Dict[str, str] = {}
        dates: Dict[str, str] = {}
        amounts: Dict[str, str] = {}
        sections: List[str] = []

        if answer_text:
            import re

            # Extract party assignments ("Trustee: Deutsche Bank" or "Trustee is Deutsche Bank")
            party_roles = [
                "Depositor", "Trustee", "Master Servicer", "Servicer",
                "Certificate Registrar", "Issuer", "Sponsor", "Seller",
            ]
            for role in party_roles:
                pattern = rf"{role}\s*(?::|is|—|–)\s*([A-Z][A-Za-z\s&.,]+?)(?:\.|,|\n|$)"
                m = re.search(pattern, answer_text)
                if m:
                    parties[role] = m.group(1).strip().rstrip(".,")

            # Extract defined terms ("Term" means / "Term" is defined as)
            dt_pattern = r'"([A-Z][A-Za-z\s]+?)"\s+(?:means|is defined as|shall mean)\s+(.+?)(?:\.|$)'
            for m in re.finditer(dt_pattern, answer_text, re.MULTILINE):
                terms[m.group(1).strip()] = m.group(2).strip()[:300]

            # Extract date references (Key Date Name: value)
            date_keywords = [
                "Closing Date", "Distribution Date", "Determination Date",
                "Record Date", "Optional Termination Date", "Settlement Date",
                "Effective Date", "Cut-Off Date",
            ]
            for dk in date_keywords:
                pattern = rf"{dk}\s*(?::|is|—|–)\s*([A-Za-z0-9,\s]+?)(?:\.|,|\n|$)"
                m = re.search(pattern, answer_text, re.IGNORECASE)
                if m:
                    dates[dk] = m.group(1).strip().rstrip(".,")

            # Extract section references
            sec_pattern = r"Section\s+(\d+\.\d+)"
            sections = re.findall(sec_pattern, answer_text)

        # Track source documents from chunks
        for chunk in chunks:
            source = chunk.get("source", "")
            if source:
                session.add_active_document(source)

        # Update the deal summary progressively
        session.deal_summary.update_from_answer(
            terms=terms or None,
            parties=parties or None,
            dates=dates or None,
            amounts=amounts or None,
            sections=sections or None,
        )

    @property
    def session_count(self) -> int:
        return len(self._sessions)
