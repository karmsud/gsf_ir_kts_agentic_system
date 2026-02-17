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
    
    SECTION_PATTERN = re.compile(
        r"(?m)^\s*(?:SECTION|Section|§)\s+(\d+(?:\.\d+)?(?:\([a-z0-9]+\))?)[.\s:]?\s*(.{0,120}?)(?:\s*\.{3,}|\n|$)",
        re.IGNORECASE
    )
    
    SUBSECTION_PATTERN = re.compile(
        r"(?m)^\s*\(([a-z]|[ivxlc]+|[0-9]+)\)\s+(.{0,120}?)(?:\.|\n|$)",
        re.IGNORECASE
    )
    
    # TOC pattern (matches: "Article I - Definitions .... 5")
    TOC_ENTRY_PATTERN = re.compile(
        r"(?m)^(.{10,80}?)[.·]{3,}\s*(\d+)\s*$"
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
            page_num = int(match.group(2))
            
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
        
        return TableOfContents(entries=entries, has_toc=len(entries) > 0)
    
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
        
        # Note: TOC extraction for reference - could be used for future enhancements
        # like intelligent section boundary detection or page-based chunking
        # toc = self.extract_toc(text) if use_toc else TableOfContents([], False)
        
        # Find all articles
        article_matches = list(self.ARTICLE_PATTERN.finditer(text))
        
        if article_matches:
            # Document has article structure
            for i, match in enumerate(article_matches):
                article_num = match.group(2).strip()
                article_title = match.group(3).strip() if match.group(3) else ""
                start_pos = match.start()
                end_pos = article_matches[i + 1].start() if i + 1 < len(article_matches) else len(text)
                
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
            # No articles, look for section-level structure
            section_matches = list(self.SECTION_PATTERN.finditer(text))
            
            if section_matches:
                for i, match in enumerate(section_matches):
                    section_num = match.group(1).strip()
                    section_title = match.group(2).strip() if match.group(2) else ""
                    start_pos = match.start()
                    end_pos = section_matches[i + 1].start() if i + 1 < len(section_matches) else len(text)
                    
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
