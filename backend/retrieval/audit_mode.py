"""
Phase 11.4 — Audit Mode (/audit).

Retrieves all clauses related to a topic (risk, liability, indemnification)
and presents them as a structured bullet list with risk tags.

Topic-clustering groups retrieved chunks by section/topic so the user sees
a coherent audit view rather than random chunk order.
"""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Prompt Template ───────────────────────────────────────────

AUDIT_PROMPT = """List all clauses related to "{topic}" from the provided document context.
For each clause found:
1. State the section number and heading
2. Provide a one-sentence summary of the clause
3. Assess the risk level: Low, Medium, or High
4. Quote the key phrase that supports the risk assessment

Output as a structured bullet list. If no relevant clauses are found, state that explicitly.

Document context:
{context}

Topic to audit: {topic}"""

AUDIT_PROMPT_WITH_ANOMALY = """List all clauses related to "{topic}" from the provided document context.
For each clause found:
1. State the section number and heading
2. Provide a one-sentence summary of the clause
3. Assess the risk level: Low, Medium, or High
4. Quote the key phrase that supports the risk assessment
5. If the clause deviates from standard market language, note the deviation

Output as a structured bullet list. If no relevant clauses are found, state that explicitly.

Document context:
{context}

Topic to audit: {topic}"""


# ── Configuration ─────────────────────────────────────────────

@dataclass
class AuditConfig:
    """Configuration for audit mode."""

    chunk_budget: int = 15
    temperature: float = 0.2
    max_output_tokens: int = 3000
    include_anomaly_flags: bool = False  # Phase 15.4 integration


# ── Result ────────────────────────────────────────────────────

@dataclass
class AuditClause:
    """A single clause found during audit."""

    section: str
    summary: str
    risk_level: str  # Low, Medium, High
    key_phrase: str
    anomaly_note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "section": self.section,
            "summary": self.summary,
            "risk_level": self.risk_level,
            "key_phrase": self.key_phrase,
        }
        if self.anomaly_note:
            d["anomaly_note"] = self.anomaly_note
        return d


@dataclass
class AuditResult:
    """Result of audit mode."""

    topic: str
    clauses: List[AuditClause] = field(default_factory=list)
    raw_response: str = ""
    total_sections_scanned: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "clauses": [c.to_dict() for c in self.clauses],
            "total_sections_scanned": self.total_sections_scanned,
        }


# ── Section Clustering ───────────────────────────────────────

def cluster_by_section(chunks: List[Dict[str, Any]]) -> OrderedDict:
    """Group chunks by their section for coherent audit presentation."""
    clusters: OrderedDict[str, List[Dict]] = OrderedDict()
    for chunk in chunks:
        section = (
            chunk.get("section")
            or chunk.get("metadata", {}).get("section_number", "")
            or "Unknown Section"
        )
        clusters.setdefault(section, []).append(chunk)
    return clusters


# ── Clause Parsing ────────────────────────────────────────────

_CLAUSE_SECTION_RE = re.compile(
    r'(?:^|\n)\s*[-*]\s*\*?\*?(?:Section\s+)?(\d+[\d.]*(?:\([a-z]\))?[^:]*?)\*?\*?\s*[:\u2013\u2014-]\s*(.+)',
    re.IGNORECASE,
)
_RISK_LEVEL_RE = re.compile(r'\b(Low|Medium|High)\b', re.IGNORECASE)


def _parse_audit_clauses(raw_response: str) -> List[AuditClause]:
    """Best-effort extraction of structured clauses from LLM bullet-list output."""
    clauses: List[AuditClause] = []
    lines = raw_response.split('\n')
    current_section = ""
    current_summary = ""
    current_risk = "Medium"
    current_phrase = ""

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Try to match section header pattern
        m = _CLAUSE_SECTION_RE.match(stripped)
        if m:
            # Save previous clause if any
            if current_section and current_summary:
                clauses.append(AuditClause(
                    section=current_section,
                    summary=current_summary,
                    risk_level=current_risk,
                    key_phrase=current_phrase or current_summary,
                ))
            current_section = m.group(1).strip()
            current_summary = m.group(2).strip()
            current_risk = "Medium"
            current_phrase = ""
            # Check if risk level is on same line
            rm = _RISK_LEVEL_RE.search(stripped)
            if rm:
                current_risk = rm.group(1).capitalize()
            continue

        # Check for risk level line
        rm = _RISK_LEVEL_RE.search(stripped)
        if rm and current_section:
            current_risk = rm.group(1).capitalize()

        # Check for key phrase (quoted text)
        quote_match = re.search(r'["\u201c](.+?)["\u201d]', stripped)
        if quote_match and current_section:
            current_phrase = quote_match.group(1)

    # Don't forget the last clause
    if current_section and current_summary:
        clauses.append(AuditClause(
            section=current_section,
            summary=current_summary,
            risk_level=current_risk,
            key_phrase=current_phrase or current_summary,
        ))

    return clauses


# ── Audit Mode ────────────────────────────────────────────────

class AuditMode:
    """
    Audit mode for /audit slash command.

    Retrieves all clauses related to a topic and presents them as
    a structured bullet list with risk tags.

    Usage::

        mode = AuditMode(llm_call_fn=my_llm_call)
        result = await mode.audit("indemnification", chunks)
    """

    def __init__(
        self,
        llm_call_fn=None,
        config: Optional[AuditConfig] = None,
    ) -> None:
        self.llm_call_fn = llm_call_fn
        self.config = config or AuditConfig()

    async def audit(
        self,
        topic: str,
        chunks: List[Dict[str, Any]],
        *,
        content_key: str = "content",
    ) -> AuditResult:
        """Run audit for the given topic against provided chunks."""
        if self.llm_call_fn is None:
            return AuditResult(topic=topic, raw_response="No LLM available")

        # Cluster and build context
        clustered = cluster_by_section(chunks[:self.config.chunk_budget])
        context_parts = []
        for section, section_chunks in clustered.items():
            for chunk in section_chunks:
                text = chunk.get(content_key) or chunk.get("text") or ""
                context_parts.append(f"[Section: {section}]\n{text}")
        context = "\n\n".join(context_parts)

        prompt_template = (
            AUDIT_PROMPT_WITH_ANOMALY if self.config.include_anomaly_flags
            else AUDIT_PROMPT
        )
        prompt = prompt_template.format(topic=topic, context=context)

        try:
            raw = await self.llm_call_fn(
                prompt,
                self.config.max_output_tokens,
                self.config.temperature,
            )

            return AuditResult(
                topic=topic,
                clauses=_parse_audit_clauses(raw.strip()),
                raw_response=raw.strip(),
                total_sections_scanned=len(clustered),
            )

        except Exception as exc:
            logger.error("[AuditMode] LLM call failed: %s", exc)
            return AuditResult(
                topic=topic,
                raw_response=f"Audit failed: {exc}",
            )

    def audit_sync(self, topic: str, chunks: List[Dict[str, Any]]) -> AuditResult:
        """Synchronous fallback."""
        return AuditResult(topic=topic, raw_response="Sync mode — LLM requires async")
