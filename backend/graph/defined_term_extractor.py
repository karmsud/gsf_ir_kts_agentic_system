"""Defined-Term Extractor — Strategies 1-4 (TD §5.4–§5.6).

Extracts defined terms from document text using multiple strategies,
each producing ``DefinedTerm`` instances with confidence scores.

Strategies implemented:
  1. ``"X" means …`` regex                    (confidence 0.95)
  2. Definitions-section header detection      (confidence 0.90)
  3. Bold / italic marker detection            (confidence 0.85)
  4. Inline reference pattern (``defined in``) (confidence 0.80)

Strategies 5-6 (table-based, titlecase heuristic) deferred to Phase 4.1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DefinedTerm:
    """Structured output for a single extracted defined term."""
    surface_form: str
    definition_text: str
    confidence: float
    extraction_strategy: str
    source_section_id: str | None = None
    source_line: int | None = None


class DefinedTermExtractor:
    """Multi-strategy defined-term extractor."""

    def extract(self, text: str, filename: str = "") -> list[DefinedTerm]:
        """Run all strategies and return de-duplicated terms ordered by confidence."""
        terms: list[DefinedTerm] = []
        terms.extend(self._strategy1_means_pattern(text))
        terms.extend(self._strategy2_definitions_section(text))
        terms.extend(self._strategy3_bold_italic(text))
        terms.extend(self._strategy4_inline_reference(text))
        return self._deduplicate(terms)

    # ── Strategy 1: "X" means … (confidence 0.95) ────────────────
    def _strategy1_means_pattern(self, text: str) -> list[DefinedTerm]:
        results: list[DefinedTerm] = []
        patterns = [
            # "Term" means …
            (r'["\u201c]([^"\u201d]{2,80})["\u201d]\s+(means|shall mean|is defined as|has the meaning)\s+(.{10,300}?)(?:\.|$)',
             re.IGNORECASE | re.MULTILINE),
            # Term is defined as …
            (r'\b([A-Z][A-Za-z0-9 _-]{1,60})\s+(means|is defined as)\s+(.{10,300}?)(?:\.|$)',
             re.IGNORECASE),
        ]
        for pattern, flags in patterns:
            for m in re.finditer(pattern, text, flags):
                term = m.group(1).strip().strip('""\u201c\u201d')
                definition = m.group(3).strip() if m.lastindex >= 3 else ""
                if len(term) < 2 or len(term) > 80:
                    continue
                results.append(DefinedTerm(
                    surface_form=term,
                    definition_text=definition[:500],
                    confidence=0.95,
                    extraction_strategy="regex_means",
                ))
        return results

    # ── Strategy 2: Definitions section entries (confidence 0.90) ─
    def _strategy2_definitions_section(self, text: str) -> list[DefinedTerm]:
        results: list[DefinedTerm] = []
        # Find a definitions section
        section_match = re.search(
            r'(?m)^#{0,4}\s*(?:ARTICLE|SECTION)?\s*[IVXLC0-9.]*\s*DEFINITIONS?\s*$',
            text,
            re.IGNORECASE,
        )
        if not section_match:
            return results

        # Grab text after the heading until the next top-level section
        start = section_match.end()
        next_section = re.search(
            r'(?m)^#{0,4}\s*(?:ARTICLE|SECTION)\s+[IVXLC0-9]+[.\s]',
            text[start:],
            re.IGNORECASE,
        )
        end = start + next_section.start() if next_section else min(start + 10000, len(text))
        section_text = text[start:end]

        # Extract terms that appear at the start of paragraphs/lines with a definition
        for m in re.finditer(
            r'(?m)^\s*["\u201c]?([A-Z][A-Za-z0-9 /\'-]{1,80})["\u201d]?\s*[:.\u2014\u2013\-]+\s*(.{10,500})',
            section_text,
        ):
            term = m.group(1).strip().strip('""\u201c\u201d')
            definition = m.group(2).strip()
            if len(term) < 2:
                continue
            results.append(DefinedTerm(
                surface_form=term,
                definition_text=definition[:500],
                confidence=0.90,
                extraction_strategy="definitions_section",
                source_section_id="DEFINITIONS",
            ))
        return results

    # ── Strategy 3: Bold/italic markers (confidence 0.85) ─────────
    def _strategy3_bold_italic(self, text: str) -> list[DefinedTerm]:
        results: list[DefinedTerm] = []
        # Markdown bold: **Term** or __Term__
        for m in re.finditer(
            r'(?:\*\*|__)((?:[A-Z][A-Za-z0-9 /\'-]{1,80}))(?:\*\*|__)\s*[:.\u2014\u2013\-]+\s*(.{10,400})',
            text,
        ):
            term = m.group(1).strip()
            definition = m.group(2).strip()
            results.append(DefinedTerm(
                surface_form=term,
                definition_text=definition[:500],
                confidence=0.85,
                extraction_strategy="bold_italic_marker",
            ))
        return results

    # ── Strategy 4: Inline reference (confidence 0.80) ────────────
    def _strategy4_inline_reference(self, text: str) -> list[DefinedTerm]:
        results: list[DefinedTerm] = []
        # "as defined in Section X" / "defined in the Agreement"
        for m in re.finditer(
            r'["\u201c]([A-Z][A-Za-z0-9 /\'-]{1,80})["\u201d]\s*'
            r'(?:\(as defined (?:in|herein|above|below)(?:\s+(?:Section|Article)\s+[IVXLC0-9.]+)?\))',
            text,
            re.IGNORECASE,
        ):
            term = m.group(1).strip()
            results.append(DefinedTerm(
                surface_form=term,
                definition_text=f"(cross-reference — defined elsewhere in the document)",
                confidence=0.80,
                extraction_strategy="inline_reference",
            ))
        return results

    # ── De-duplication (§5.6: keep highest confidence) ────────────
    @staticmethod
    def _deduplicate(terms: list[DefinedTerm]) -> list[DefinedTerm]:
        best: dict[str, DefinedTerm] = {}
        for t in terms:
            key = t.surface_form.lower().strip()
            if key not in best or t.confidence > best[key].confidence:
                best[key] = t
        return sorted(best.values(), key=lambda x: (-x.confidence, x.surface_form))
