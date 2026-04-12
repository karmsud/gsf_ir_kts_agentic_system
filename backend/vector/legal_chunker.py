"""
Legal Document Semantic Chunker — Section-Aware Chunking

Industry-standard implementation for chunking legal, financial, and regulatory documents  
based on their inherent structure (TOC, sections, articles) rather than arbitrary
character counts.

Key Features:
  * TOC extraction from document structure
  * Hierarchical section parsing (ARTICLE → Section → Subsection)
  * Boundary-aware chunking (respects section boundaries)
  * Adaptive sizing with min/max constraints
  * Fallback to character-based chunking for unstructured content

Usage:
    from backend.vector.legal_chunker import LegalChunker
    
    chunker = LegalChunker(min_chunk_size=500, max_chunk_size=5000)
    sections = chunker.extract_sections(text)
    chunks = chunker.chunk_by_sections(doc_id, source_path, sections)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

from backend.common.models import TextChunk
from backend.common.text_utils import chunk_text


# ── Phase 8.0: Contextual Chunk Headers (CCH) ──────────────────

def build_cch_header(
    doc_name: str | None = None,
    doc_type: str | None = None,
    section_title: str | None = None,
    max_section_len: int = 80,
) -> str:
    """Build a ``[DOC: … | TYPE: … | SECTION: …]`` header for embedding enrichment.

    Returns empty string when all inputs are empty/None (no-op fallback).
    """
    parts: list[str] = []
    if doc_name:
        parts.append(f"DOC: {doc_name}")
    if doc_type:
        parts.append(f"TYPE: {doc_type}")
    if section_title:
        truncated = section_title[:max_section_len]
        parts.append(f"SECTION: {truncated}")

    if not parts:
        return ""
    return "[" + " | ".join(parts) + "]\n"


def _create_chunk_for_embedding(
    text: str,
    metadata: dict,
    *,
    enable_cch: bool = True,
    max_section_len: int = 80,
) -> str:
    """Return text suitable for vector embedding — with optional CCH header prepended.

    The *original* text (without header) should be stored in metadata["text"]
    for display so the user never sees the synthetic header.
    """
    if not enable_cch:
        return text

    header = build_cch_header(
        doc_name=metadata.get("doc_name") or metadata.get("document_id", ""),
        doc_type=metadata.get("doc_type", ""),
        section_title=(
            metadata.get("section_title")
            or metadata.get("section_heading", "")
        ),
        max_section_len=max_section_len,
    )
    if not header:
        return text
    return header + text


@dataclass
class DocumentSection:
    """Represents a hierarchical section in a legal document."""
    level: int  # 1=Article, 2=Section, 3=Subsection
    number: str  # e.g., "I", "2.01", "3.05(a)"
    title: str
    content: str
    start_pos: int
    end_pos: int
    parent_number: Optional[str] = None
    children: List[DocumentSection] = field(default_factory=list)


@dataclass
class TableOfContents:
    """Extracted table of contents structure."""
    entries: List[Tuple[str, str, int]]  # (section_number, title, page_or_pos)
    has_toc: bool = False
    header_start: int = 0  # char position of TOC header (e.g. "Contents\n") in the full text


class LegalChunker:
    """
    Semantic chunker for legal/financial documents.
    
    Implements best practices from legal document processing:
      1. Respect document structure (articles, sections, subsections)
      2. Preserve context within sections
      3. Balance chunk sizes while maintaining semantic boundaries
      4. Extract and utilize TOC information when available
    """
    
    # Hierarchical section patterns (ordered by precedence)
    ARTICLE_PATTERN = re.compile(
        r"(?m)^\s*(ARTICLE|PART)\s+([IVXLC]+|[0-9]+)[.\s:]?\s*(.{0,120}?)(?:\s*\.{3,}|\n|$)",
        re.IGNORECASE
    )

    # Body-level heading: all-caps line preceded by a blank line.
    # Used when ARTICLE headings are only in the TOC and the body text
    # uses bare all-caps titles (e.g. "DEFINITIONS", "ACCOUNTS").
    _BODY_HEADING_RE = re.compile(
        r"\n\n([A-Z][A-Z ,;:&\-\u2013\u2014()/]{7,79})\s*\n"
    )
    
    SECTION_PATTERN = re.compile(
        r"(?m)^\s*(?:SECTION|Section|§)\s+(\d+(?:\.\d+)*(?:\([a-zA-Z0-9]+\))?)[.\s:]?\s*(.{0,120}?)(?:\s*\.{3,}|\n|$)",
        re.IGNORECASE
    )
    # Chapter-based structure (troubleshooting guides, user manuals, etc.)
    CHAPTER_PATTERN = re.compile(
        r"(?m)^\s*(?:CHAPTER|Chapter)\s+([IVXLC]+|[0-9]+)[\.\s:\-\u2013\u2014]?\s*(.{0,120}?)(?:\s*\.{3,}|\n|$)",
        re.IGNORECASE
    )

    # Numbered heading pattern: "1 Title", "2.1 Title", "1. Title" etc.
    # Requires a preceding blank line to avoid false positives on numbered lists.
    NUMBERED_HEADING_PATTERN = re.compile(
        r"(?m)(?:^|\n)\n(\d+(?:\.\d+)?)[\.\s:\-\u2013\u2014]+\s*([A-Z][A-Za-z0-9 ,;:&\-\u2013\u2014()/]{3,79})\s*(?:\n|$)"
    )

    # Split-line heading: number/letter alone on a line, heading on the next.
    # Common in PDF-extracted tech manuals (e.g. HP guides) where pagination
    # inserts the chapter digit/letter on its own line.
    # Heading must be 19+ chars to avoid matching error-code tables.
    SPLIT_LINE_HEADING_PATTERN = re.compile(
        r"(?m)^(\d{1,2}|[A-Z])\s*\n([A-Z][A-Za-z0-9 ()/]{18,79})\s*$"
    )

    SUBSECTION_PATTERN = re.compile(
        r"(?m)^\s*\(([a-z]|[ivxlc]+|[0-9]+)\)\s+(.{0,120}?)(?:\.|\n|$)",
        re.IGNORECASE
    )
    
    # TOC pattern (matches: "Article I - Definitions .... 5" or ". . . . 1–2")
    TOC_ENTRY_PATTERN = re.compile(
        r"(?m)^(.{10,80}?)(?:[.\u00b7]\s*){3,}\s*(\d+(?:[\u2013\u2014\-]\d+)?)\s*$"
    )
    
    def __init__(
        self,
        min_chunk_size: int = 500,
        max_chunk_size: int = 5000,
        target_chunk_size: int = 2500,
        enable_subsection_merging: bool = True,
    ):
        """
        Initialize LegalChunker.
        
        Args:
            min_chunk_size: Minimum characters per chunk (will merge small sections)
            max_chunk_size: Maximum characters per chunk (will split large sections)
            target_chunk_size: Target size for balanced chunks
            enable_subsection_merging: Merge subsections into parent section when small
        """
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.target_chunk_size = target_chunk_size
        self.enable_subsection_merging = enable_subsection_merging
    
    def extract_toc(self, text: str) -> TableOfContents:
        """
        Extract table of contents from document.
        
        Returns:
            TableOfContents with entries if found, empty otherwise
        """
        # Look for TOC header in first 10K chars
        toc_start = None
        toc_header_match = re.search(
            r"(?m)^\s*(TABLE\s+OF\s+CONTENTS?|CONTENTS?|INDEX)\s*$",
            text[:10000],
            re.IGNORECASE
        )
        
        if not toc_header_match:
            return TableOfContents(entries=[], has_toc=False)
        
        toc_start = toc_header_match.end()
        
        # Extract TOC entries (lines with dots leading to page numbers)
        # Typical pattern: "Article I - Definitions ............ 5"
        toc_text = text[toc_start:toc_start + 10000]  # Scan next 10K chars
        
        entries = []
        for match in self.TOC_ENTRY_PATTERN.finditer(toc_text):
            entry_text = match.group(1).strip()
            page_raw = match.group(2).strip()
            # Page number may be plain "5" or chapter-page "1–2", "A–14"
            try:
                page_num = int(page_raw)
            except ValueError:
                # Extract the leading number for ordering purposes
                m = re.match(r"(\d+)", page_raw)
                page_num = int(m.group(1)) if m else 0
            
            # Parse section number and title
            section_match = re.match(
                r"^(ARTICLE|SECTION|PART)?\s*([IVXLC0-9.()]+)[\s\-–—:]+(.+)$",
                entry_text,
                re.IGNORECASE
            )
            
            if section_match:
                section_num = section_match.group(2).strip()
                section_title = section_match.group(3).strip()
                entries.append((section_num, section_title, page_num))
            else:
                # Non-legal TOC entry (no ARTICLE/SECTION prefix) — use
                # the raw entry text as the title with an empty section number.
                entries.append(("", entry_text, page_num))
        
        return TableOfContents(
            entries=entries,
            has_toc=len(entries) > 0,
            header_start=toc_header_match.start(),
        )
    
    def extract_sections(self, text: str, use_toc: bool = True) -> List[DocumentSection]:
        """
        Extract hierarchical sections from document text.
        
        Args:
            text: Full document text
            use_toc: Whether to use TOC information for section boundaries
        
        Returns:
            List of DocumentSection objects in document order
        """
        sections: List[DocumentSection] = []

        # ── Pre-TOC preamble ─────────────────────────────────────
        # Text before the TOC header (copyright page, document conventions,
        # WARNING/CAUTION definitions) is captured here and later prepended
        # to sections as a "Document Conventions" chunk so it is searchable.
        pre_toc_text: str = ""
        pre_toc_end: int = 0

        # ── TOC exclusion ──────────────────────────────────────────
        # Detect Table of Contents region and skip it so ARTICLE/SECTION
        # patterns inside the TOC don't produce hollow header-only chunks.
        body_start = 0
        if use_toc:
            toc = self.extract_toc(text)
            if toc.has_toc:
                # Capture content before the TOC header (copyright page,
                # document conventions with WARNING/CAUTION definitions, etc.)
                if toc.header_start > 50:
                    candidate = text[:toc.header_start].strip()
                    if candidate and len(candidate) >= 80:
                        pre_toc_text = candidate
                        pre_toc_end = toc.header_start

                # Find the end of the TOC region: after the last TOC entry line
                # (scan for last dotted entry within the first 20K chars)
                last_toc_match = None
                for m in self.TOC_ENTRY_PATTERN.finditer(text[:20000]):
                    last_toc_match = m
                if last_toc_match:
                    body_start = last_toc_match.end()
                    # Skip any blank lines / page breaks after TOC
                    while body_start < len(text) and text[body_start] in ('\n', '\r', '\x0c', ' '):
                        body_start += 1
        
        # Safety check: don't let the TOC skip past the first real ARTICLE heading
        if body_start > 0:
            first_article_in_full = self.ARTICLE_PATTERN.search(text)
            if first_article_in_full and first_article_in_full.start() < body_start:
                body_start = first_article_in_full.start()

        # Work only on the body text (after TOC)
        body_text = text[body_start:]
        
        # Find all articles
        article_matches = list(self.ARTICLE_PATTERN.finditer(body_text))
        
        if article_matches:
            # ── Check if ARTICLE matches are in a TOC region ──────
            # .doc conversions may place TOC headings first in the text
            # while the body uses bare all-caps headings without "ARTICLE".
            if self._articles_in_toc_region(body_text, article_matches):
                body_sections = self._extract_body_sections(
                    text, body_start, body_text, article_matches
                )
                if body_sections:
                    return body_sections

            # Capture pre-article preamble (Preliminary Statement, etc.)
            preamble_end = article_matches[0].start()
            preamble_text = body_text[:preamble_end].strip()
            if preamble_text and len(preamble_text) >= 200:
                preamble = DocumentSection(
                    level=1,
                    number="PREAMBLE",
                    title="Preliminary Statement",
                    content=preamble_text,
                    start_pos=body_start,
                    end_pos=body_start + preamble_end,
                )
                sections.append(preamble)

            # Document has article structure
            for i, match in enumerate(article_matches):
                article_num = match.group(2).strip()
                article_title = match.group(3).strip() if match.group(3) else ""
                start_pos = body_start + match.start()
                end_pos = body_start + (article_matches[i + 1].start() if i + 1 < len(article_matches) else len(body_text))
                
                content = text[start_pos:end_pos]
                
                article = DocumentSection(
                    level=1,
                    number=article_num,
                    title=article_title,
                    content=content,
                    start_pos=start_pos,
                    end_pos=end_pos,
                )
                
                # Extract sections within this article
                article.children = self._extract_subsections(content, article_num, start_pos)
                sections.append(article)
        
        else:
            # No articles — try section, chapter, and numbered heading patterns
            section_matches = list(self.SECTION_PATTERN.finditer(body_text))

            if not section_matches:
                # Try chapter-based structure (Chapter 1, Chapter 2, etc.)
                section_matches = list(self.CHAPTER_PATTERN.finditer(body_text))

            if not section_matches:
                # Try numbered headings (1 Title, 2. Title, etc.)
                section_matches = list(self.NUMBERED_HEADING_PATTERN.finditer(body_text))

            if not section_matches:
                # Try split-line headings (number/letter on own line, heading on next)
                section_matches = list(self.SPLIT_LINE_HEADING_PATTERN.finditer(body_text))

            if section_matches:
                for i, match in enumerate(section_matches):
                    section_num = match.group(1).strip()
                    section_title = match.group(2).strip() if match.group(2) else ""
                    start_pos = body_start + match.start()
                    end_pos = body_start + (section_matches[i + 1].start() if i + 1 < len(section_matches) else len(body_text))
                    
                    content = text[start_pos:end_pos]
                    
                    section = DocumentSection(
                        level=2,
                        number=section_num,
                        title=section_title,
                        content=content,
                        start_pos=start_pos,
                        end_pos=end_pos,
                    )
                    
                    # Extract subsections within this section
                    section.children = self._extract_subsections(content, section_num, start_pos, level=3)
                    sections.append(section)

        # ── Prepend pre-TOC Document Conventions section ──────────
        # Insert the copyright/preface block at position 0 so it is indexed
        # alongside the body sections and retrievable for questions about
        # WARNING/CAUTION definitions, safety symbols, or document scope.
        if pre_toc_text:
            sections.insert(
                0,
                DocumentSection(
                    level=1,
                    number="PREFACE",
                    title="Document Conventions",
                    content=pre_toc_text,
                    start_pos=0,
                    end_pos=pre_toc_end,
                ),
            )

        # ── Deduplicate TOC-fragment sections ─────────────────────
        # When the same title appears twice (once as a short TOC entry and
        # once as the real body section), keep the longer one.
        if len(sections) > 1:
            by_title: dict[str, list[int]] = {}
            for idx, s in enumerate(sections):
                key = s.title.strip().lower()
                by_title.setdefault(key, []).append(idx)

            remove_idxs: set[int] = set()
            for key, idxs in by_title.items():
                if len(idxs) > 1:
                    # Keep the section with the most content
                    best = max(idxs, key=lambda i: len(sections[i].content))
                    for i in idxs:
                        if i != best:
                            remove_idxs.add(i)

            if remove_idxs:
                sections = [s for i, s in enumerate(sections) if i not in remove_idxs]

        return sections

    # ── TOC-cluster detection & body-heading fallback ──────────────

    def _articles_in_toc_region(
        self, body_text: str, article_matches: list
    ) -> bool:
        """Return *True* when ARTICLE headings are clustered in a TOC region.

        Indicators (all must hold):
        * All ARTICLE matches fall within the first 5 % of the text.
        * The last "section" would swallow > 50 % of the document.
        * Content between consecutive articles is dominated by "Section X.Y"
          listing lines (classic TOC format), not prose.
        """
        if len(article_matches) < 3:
            return False

        text_len = len(body_text)
        if text_len < 10_000:
            return False

        # Cluster test — all articles in first 5 %
        if article_matches[-1].start() > text_len * 0.05:
            return False

        # Imbalance test — last section > 50 % of document
        if (text_len - article_matches[-1].start()) < text_len * 0.50:
            return False

        # Content test — inter-article text is mostly Section listings
        toc_like = 0
        for i in range(min(len(article_matches) - 1, 5)):
            between = body_text[
                article_matches[i].end() : article_matches[i + 1].start()
            ]
            lines = [l.strip() for l in between.split("\n") if l.strip()]
            if not lines:
                continue
            sec_lines = sum(
                1
                for l in lines
                if re.match(r"Section\s+\d+", l, re.IGNORECASE)
            )
            if sec_lines / len(lines) > 0.4:
                toc_like += 1

        return toc_like >= 2

    _NOISE_PREFIXES = frozenset(
        [
            "REMIC",
            "EXHIBIT",
            "PAGE ",
            "BEAR ",
            "STATE OF",
            "COUNTY OF",
            "SECURITIES",
        ]
    )

    def _extract_body_sections(
        self,
        full_text: str,
        body_start: int,
        body_text: str,
        toc_article_matches: list,
    ) -> List[DocumentSection]:
        """Build sections from body headings when ARTICLE matches are TOC entries.

        Strategy
        --------
        1. Build a *title → article number* map from TOC ARTICLE entries.
        2. Find the end of the TOC cluster (+ exhibits / blanks).
        3. Scan the remainder for all-caps heading lines (``_BODY_HEADING_RE``).
        4. Match each heading to a TOC entry; unmatched headings get the next
           available Roman numeral (handles articles missing from a truncated TOC).
        5. Build ``DocumentSection`` objects with child sub-sections.
        """
        # ── 1. Title → number from TOC ────────────────────────────
        toc_titles: dict[str, str] = {}          # UPPERCASE_TITLE → "IV"
        for m in toc_article_matches:
            num = m.group(2).strip()
            title = (m.group(3) or "").strip()
            if title:
                toc_titles[title.upper().rstrip(".").strip()] = num

        # ── 2. Body starts after the TOC cluster ──────────────────
        toc_cluster_end = body_start + toc_article_matches[-1].end()
        search_text = full_text[toc_cluster_end:]

        # ── 3. Find all-caps heading lines in the body ────────────
        body_headings: list[tuple[int, str]] = []   # (abs_pos, heading)
        for m in self._BODY_HEADING_RE.finditer(search_text):
            heading = m.group(1).strip()
            if any(heading.startswith(p) for p in self._NOISE_PREFIXES):
                continue
            if "_" in heading or "*" in heading or heading.endswith(","):
                continue
            # absolute position — heading starts after the two newlines
            abs_pos = toc_cluster_end + m.start() + 2
            body_headings.append((abs_pos, heading))

        if not body_headings:
            return []

        # ── 4. Match headings → TOC entries ───────────────────────
        found: list[tuple[int, str | None, str]] = []   # (pos, num|None, title)
        used_toc: set[str] = set()

        for pos, heading in body_headings:
            h_upper = heading.upper().strip()
            matched_num: str | None = None
            matched_key: str | None = None
            for toc_title, num in toc_titles.items():
                if toc_title in used_toc:
                    continue
                if (
                    toc_title == h_upper
                    or toc_title in h_upper
                    or h_upper in toc_title
                ):
                    matched_num = num
                    matched_key = toc_title
                    break
            if matched_key:
                used_toc.add(matched_key)
            found.append((pos, matched_num, heading))

        # ── 5. Assign Roman numerals to unmatched headings ────────
        used_nums = {n for _, n, _ in found if n is not None}
        roman = [
            "I", "II", "III", "IV", "V", "VI", "VII", "VIII",
            "IX", "X", "XI", "XII", "XIII", "XIV", "XV",
        ]
        for idx in range(len(found)):
            pos, num, title = found[idx]
            if num is not None:
                continue
            for rom in roman:
                if rom not in used_nums:
                    found[idx] = (pos, rom, title)
                    used_nums.add(rom)
                    break

        # Drop anything still unassigned; sort by position
        found = [(p, n, t) for p, n, t in found if n is not None]
        found.sort(key=lambda x: x[0])
        if not found:
            return []

        # ── 6. Preamble ──────────────────────────────────────────
        sections: List[DocumentSection] = []
        preamble_text = full_text[toc_cluster_end : found[0][0]].strip()
        if preamble_text and len(preamble_text) >= 200:
            sections.append(
                DocumentSection(
                    level=1,
                    number="PREAMBLE",
                    title="Preliminary Statement",
                    content=preamble_text,
                    start_pos=toc_cluster_end,
                    end_pos=found[0][0],
                )
            )

        # ── 7. Article sections ───────────────────────────────────
        for i, (pos, num, title) in enumerate(found):
            end_pos = (
                found[i + 1][0] if i + 1 < len(found) else len(full_text)
            )
            content = full_text[pos:end_pos]
            article = DocumentSection(
                level=1,
                number=num,
                title=title,
                content=content,
                start_pos=pos,
                end_pos=end_pos,
            )
            article.children = self._extract_subsections(content, num, pos)
            sections.append(article)

        return sections

    def _extract_subsections(
        self,
        parent_text: str,
        parent_number: str,
        parent_start_pos: int,
        level: int = 2
    ) -> List[DocumentSection]:
        """Extract subsections within a parent section."""
        subsections: List[DocumentSection] = []
        
        if level == 2:
            # Extract Section X.Y within Article
            pattern = self.SECTION_PATTERN
        else:
            # Extract (a), (b), (c) subsections
            pattern = self.SUBSECTION_PATTERN
        
        matches = list(pattern.finditer(parent_text))
        
        for i, match in enumerate(matches):
            sub_num = match.group(1).strip()
            sub_title = match.group(2).strip() if len(match.groups()) > 1 and match.group(2) else ""
            
            # Calculate absolute position
            start_pos = parent_start_pos + match.start()
            end_pos = parent_start_pos + (matches[i + 1].start() if i + 1 < len(matches) else len(parent_text))
            
            # Extract content
            local_start = match.start()
            local_end = matches[i + 1].start() if i + 1 < len(matches) else len(parent_text)
            content = parent_text[local_start:local_end]
            
            subsection = DocumentSection(
                level=level,
                number=sub_num,
                title=sub_title,
                content=content,
                start_pos=start_pos,
                end_pos=end_pos,
                parent_number=parent_number,
            )
            
            subsections.append(subsection)
        
        return subsections
    
    def chunk_by_sections(
        self,
        doc_id: str,
        source_path: str,
        sections: List[DocumentSection],
    ) -> List[TextChunk]:
        """
        Create chunks based on document sections with adaptive sizing.
        
        Strategy:
          1. Use section boundaries as primary chunk boundaries
          2. Merge small adjacent sections to meet min_chunk_size
          3. Split large sections to respect max_chunk_size
          4. Preserve section headers in each chunk for context
        
        Args:
            doc_id: Document identifier
            source_path: Source file path
            sections: List of extracted sections
        
        Returns:
            List of TextChunk objects
        """
        chunks: List[TextChunk] = []
        chunk_index = 0
        
        # Flatten section hierarchy for processing
        flat_sections = self._flatten_sections(sections)
        
        i = 0
        while i < len(flat_sections):
            section = flat_sections[i]
            section_size = len(section.content)
            
            # Case 1: Section is within target range
            if self.min_chunk_size <= section_size <= self.max_chunk_size:
                chunk = self._create_chunk(doc_id, source_path, section, chunk_index)
                chunks.append(chunk)
                chunk_index += 1
                i += 1
            
            # Case 2: Section is too small - merge with adjacent sections
            elif section_size < self.min_chunk_size:
                merged_content = section.content
                merged_title = f"{section.number} {section.title}".strip()
                j = i + 1
                
                # Merge subsequent sections until we reach min size
                while j < len(flat_sections) and len(merged_content) < self.target_chunk_size:
                    next_section = flat_sections[j]
                    if len(merged_content) + len(next_section.content) > self.max_chunk_size:
                        break
                    merged_content += "\n\n" + next_section.content
                    j += 1
                
                # Create merged chunk
                merged_section = DocumentSection(
                    level=section.level,
                    number=section.number,
                    title=merged_title,
                    content=merged_content,
                    start_pos=section.start_pos,
                    end_pos=flat_sections[j-1].end_pos if j > i + 1 else section.end_pos,
                )
                
                chunk = self._create_chunk(doc_id, source_path, merged_section, chunk_index)
                chunks.append(chunk)
                chunk_index += 1
                i = j
            
            # Case 3: Section is too large - split it
            else:
                # Try to split on subsections if available
                if section.children:
                    for child in section.children:
                        chunk = self._create_chunk(doc_id, source_path, child, chunk_index)
                        chunks.append(chunk)
                        chunk_index += 1
                else:
                    # Fall back to character-based splitting
                    sub_chunks = chunk_text(
                        section.content,
                        chunk_size=self.target_chunk_size,
                        chunk_overlap=500
                    )
                    
                    for sub_chunk_text in sub_chunks:
                        chunk = TextChunk(
                            chunk_id=f"{doc_id}_chunk_{chunk_index}",
                            doc_id=doc_id,
                            content=self._add_section_header(section, sub_chunk_text),
                            source_path=source_path,
                            chunk_index=chunk_index,
                        )
                        chunks.append(chunk)
                        chunk_index += 1
                
                i += 1
        
        return chunks
    
    def _flatten_sections(self, sections: List[DocumentSection]) -> List[DocumentSection]:
        """Flatten hierarchical sections into a linear list."""
        flat: List[DocumentSection] = []
        
        for section in sections:
            if self.enable_subsection_merging and section.children:
                # If subsections are small, keep parent with all children merged
                total_children_size = sum(len(c.content) for c in section.children)
                
                if total_children_size < self.max_chunk_size:
                    # Merge children into parent
                    merged_content = section.content
                    for child in section.children:
                        merged_content += "\n\n" + child.content
                    
                    section.content = merged_content
                    section.children = []
                    flat.append(section)
                else:
                    # Add section and children separately
                    flat.append(section)
                    flat.extend(section.children)
            else:
                flat.append(section)
                if section.children:
                    flat.extend(section.children)
        
        # Filter out header-only stubs (e.g. TOC fragments or empty articles)
        # A section needs at least 100 chars of body beyond its heading to be useful
        MIN_BODY_LENGTH = 100
        flat = [
            s for s in flat
            if len(s.content.strip()) >= MIN_BODY_LENGTH
        ]
        
        return flat
    
    def _create_chunk(
        self,
        doc_id: str,
        source_path: str,
        section: DocumentSection,
        chunk_index: int,
    ) -> TextChunk:
        """Create a TextChunk from a DocumentSection."""
        # Add section header for context
        content_with_header = self._add_section_header(section, section.content)
        
        return TextChunk(
            chunk_id=f"{doc_id}_chunk_{chunk_index}",
            doc_id=doc_id,
            content=content_with_header,
            source_path=source_path,
            chunk_index=chunk_index,
        )
    
    def _add_section_header(self, section: DocumentSection, content: str) -> str:
        """Add semantic header to chunk for context preservation."""
        level_name = {1: "ARTICLE", 2: "SECTION", 3: "SUBSECTION"}.get(section.level, "SECTION")
        
        section_label = f"{level_name} {section.number}"
        if section.title:
            section_label += f" - {section.title}"
        
        header = f"[LEGAL_SECTION] {section_label}"
        
        # Don't duplicate if header already exists
        if content.strip().startswith("[LEGAL_SECTION]"):
            return content
        
        return f"{header}\n\n{content}"

    # -----------------------------------------------------------------
    # Phase 13.3: Parent-Child Chunking
    # -----------------------------------------------------------------

    def chunk_by_sections_parent_child(
        self,
        doc_id: str,
        source_path: str,
        sections: List[DocumentSection],
        child_target_size: int = 600,
        child_overlap: int = 100,
    ):
        """Two-pass parent-child chunking.

        Pass 1 — parents: one chunk per section (may be large, ~2000-5000 chars).
        Pass 2 — children: each parent is split into smaller child chunks
                 (~600 chars) that are stored in the similarity index.

        Returns:
            (child_chunks: List[TextChunk], parent_records: List[dict])
            child_chunks  → store in the main vector collection (for search)
            parent_records → store in the parent collection (for LLM context)
        """
        child_chunks: List[TextChunk] = []
        parent_records: list[dict] = []
        chunk_index = 0

        flat_sections = self._flatten_sections(sections)

        for section in flat_sections:
            parent_id = f"{doc_id}_parent_{section.number or chunk_index}"
            parent_content = self._add_section_header(section, section.content)

            # --- children from this parent ---
            sub_texts = chunk_text(
                parent_content,
                chunk_size=child_target_size,
                chunk_overlap=child_overlap,
            )
            child_ids: list[str] = []
            for sub in sub_texts:
                child_id = f"{doc_id}_chunk_{chunk_index}"
                tc = TextChunk(
                    chunk_id=child_id,
                    doc_id=doc_id,
                    content=sub,
                    source_path=source_path,
                    chunk_index=chunk_index,
                )
                # Attach parent_id so store can persist it
                tc.parent_id = parent_id  # type: ignore[attr-defined]
                child_chunks.append(tc)
                child_ids.append(child_id)
                chunk_index += 1

            parent_records.append({
                "parent_id": parent_id,
                "content": parent_content,
                "doc_id": doc_id,
                "section": section.number or "",
                "child_ids": child_ids,
            })

        return child_chunks, parent_records


def chunk_legal_document(
    doc_id: str,
    source_path: str,
    text: str,
    min_chunk_size: int = 500,
    max_chunk_size: int = 5000,
) -> List[TextChunk]:
    """
    Convenience function for chunking legal documents.
    
    Args:
        doc_id: Document identifier
        source_path: Source file path
        text: Full document text
        min_chunk_size: Minimum chunk size in characters
        max_chunk_size: Maximum chunk size in characters
    
    Returns:
        List of TextChunk objects
    """
    chunker = LegalChunker(
        min_chunk_size=min_chunk_size,
        max_chunk_size=max_chunk_size,
        target_chunk_size=(min_chunk_size + max_chunk_size) // 2,
    )
    
    sections = chunker.extract_sections(text)
    
    # Fall back to character-based chunking if no structure detected
    if not sections:
        from backend.vector.chunker import chunk_document
        return chunk_document(
            doc_id=doc_id,
            source_path=source_path,
            text=text,
            chunk_size=max_chunk_size,
            chunk_overlap=500,
        )
    
    return chunker.chunk_by_sections(doc_id, source_path, sections)


def chunk_legal_document_parent_child(
    doc_id: str,
    source_path: str,
    text: str,
    min_chunk_size: int = 500,
    max_chunk_size: int = 5000,
    child_target_size: int = 600,
):
    """Convenience function for parent-child chunking (Phase 13.3).

    Returns:
        (child_chunks: List[TextChunk], parent_records: List[dict])
    """
    chunker = LegalChunker(
        min_chunk_size=min_chunk_size,
        max_chunk_size=max_chunk_size,
        target_chunk_size=(min_chunk_size + max_chunk_size) // 2,
    )
    sections = chunker.extract_sections(text)
    if not sections:
        # No structure detected — fall back to flat chunking with no parents
        from backend.vector.chunker import chunk_document
        children = chunk_document(
            doc_id=doc_id,
            source_path=source_path,
            text=text,
            chunk_size=max_chunk_size,
            chunk_overlap=500,
        )
        return children, []

    return chunker.chunk_by_sections_parent_child(
        doc_id, source_path, sections, child_target_size=child_target_size
    )
