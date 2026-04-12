"""
Abstract base class for domain-specific item extraction.

This module provides the ItemExtractor interface that all domain-specific
extractors must implement. It establishes a pluggable framework allowing
the system to handle legal, technical, research, and future document types
without modifying the core ingestion pipeline.
"""

from __future__ import annotations

import hashlib
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Item:
    """
    Domain-agnostic item representation.

    All extractors produce items with this consistent structure, enabling
    uniform storage in vector stores and graph databases regardless of
    source domain.

    Attributes:
        id: Unique identifier (format: doc-sec042-type-0-hash)
        item_type: Semantic type (Obligation, Requirement, Theorem, etc.)
        text: Item content (sentence-level, 50-200 chars typically)
        document_id: Parent document identifier
        section_number: Section containing this item (e.g., "5.02")
        section_heading: Full section heading
        section_index: Sequential section position in document
        item_index: Sequential item position within section
        metadata: Domain-specific attributes (actors, verbs, terms, etc.)
    """

    id: str
    item_type: str
    text: str
    document_id: str
    section_number: str
    section_heading: str
    section_index: int
    item_index: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class ItemExtractor(ABC):
    """
    Abstract base class for item extraction from structured documents.

    Subclasses implement domain-specific extraction logic for legal contracts,
    technical manuals, research papers, etc. Each extractor identifies semantic
    items (obligations, requirements, theorems) and produces uniform Item objects.

    Design Pattern:
        - Strategy Pattern: Encapsulates extraction algorithms per domain
        - Factory Pattern: Router selects appropriate extractor
        - Template Method: Base class provides common utilities
    """

    def __init__(self) -> None:
        """Initialize extractor with domain-specific configuration."""
        self.logger = self._get_logger()
        self.supported_types = self.get_supported_types()

    @abstractmethod
    def extract_items(
        self,
        section_text: str,
        section_number: str,
        section_heading: str,
        section_index: int,
        document_id: str,
    ) -> List[Item]:
        """
        Extract semantic items from a section.

        Args:
            section_text: Full text of the section
            section_number: Section identifier (e.g., "5.02")
            section_heading: Section heading text
            section_index: Sequential section position
            document_id: Parent document identifier

        Returns:
            List of Item objects extracted from the section
        """
        ...

    @abstractmethod
    def classify_item_type(self, text: str) -> str:
        """
        Classify an item into a semantic type.

        Args:
            text: Item text to classify

        Returns:
            Item type string (e.g., "Obligation", "Definition")
        """
        ...

    @abstractmethod
    def get_supported_types(self) -> List[str]:
        """
        Return list of item types this extractor supports.

        Returns:
            List of supported type strings
        """
        ...

    # ── Common utilities available to all subclasses ──────────────

    def _generate_item_id(
        self,
        document_id: str,
        section_index: int,
        item_type: str,
        item_index: int,
        text: str,
    ) -> str:
        """
        Generate unique item identifier.

        Format: doc-sec{:03d}-type-{index}-{hash8}
        Example: psa_2006_he1-sec042-obligation-0-a3b2c1d4
        """
        type_normalized = item_type.lower().replace(" ", "_")[:12]
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:8]
        return f"{document_id}-sec{section_index:03d}-{type_normalized}-{item_index}-{text_hash}"

    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences with legal/technical awareness.

        Handles abbreviations, decimal numbers, and citations so they
        are not mistaken for sentence boundaries.
        """
        # Replace protected periods with placeholders
        protected = text
        protected = re.sub(
            r"\b(e\.g\.|i\.e\.|vs\.|Inc\.|Corp\.|Ltd\.|No\.|Dr\.|Mr\.|Mrs\.|Ms\.)",
            lambda m: m.group(0).replace(".", "<PERIOD>"),
            protected,
        )
        # Protect decimal numbers like 5.02
        protected = re.sub(r"(\d)\.(\d)", r"\1<PERIOD>\2", protected)

        # Split on sentence-ending punctuation followed by whitespace + capital
        parts = re.split(r"([.!?])\s+(?=[A-Z])", protected)

        result: list[str] = []
        i = 0
        while i < len(parts):
            if i + 1 < len(parts) and len(parts[i + 1]) == 1:
                sentence = parts[i] + parts[i + 1]
                i += 2
            else:
                sentence = parts[i]
                i += 1
            sentence = sentence.replace("<PERIOD>", ".").strip()
            if len(sentence) > 10:
                result.append(sentence)
        return result

    def _extract_section_references(self, text: str) -> List[str]:
        """
        Extract section number references from text.

        Patterns matched:
        - Section 5.02
        - § 5.02(a)
        - Sections 5.02 and 6.03
        """
        pattern = r"(?:Section|§)\s+(\d+(?:\.\d+)*(?:\([a-zA-Z0-9]+\))?)"
        matches = re.findall(pattern, text, re.IGNORECASE)
        return list(set(matches))

    def _get_logger(self) -> logging.Logger:
        """Get logger instance for this extractor."""
        return logging.getLogger(self.__class__.__name__)


def get_item_extractor(doc_type: str) -> ItemExtractor:
    """
    Factory function: Route document type to appropriate extractor.

    Args:
        doc_type: Document type from regime classification

    Returns:
        Appropriate ItemExtractor subclass instance
    """
    from backend.extraction.legal_item_extractor import LegalItemExtractor
    from backend.extraction.technical_item_extractor import TechnicalItemExtractor
    from backend.extraction.research_item_extractor import ResearchItemExtractor

    # Domain routing table
    extractors: dict[str, type[ItemExtractor]] = {
        # Legal domain
        "GOVERNING_DOC_LEGAL": LegalItemExtractor,
        "GOVERNING_DOC": LegalItemExtractor,
        "REGULATORY_GUIDANCE": LegalItemExtractor,
        "LEGAL_OPINION": LegalItemExtractor,
        "COURT_DECISION": LegalItemExtractor,
        "PSA": LegalItemExtractor,
        "INDENTURE": LegalItemExtractor,
        "TRUST_AGREEMENT": LegalItemExtractor,
        "CONTRACT": LegalItemExtractor,
        "AGREEMENT": LegalItemExtractor,
        # Technical domain
        "TECHNICAL_SPEC": TechnicalItemExtractor,
        "API_DOCUMENTATION": TechnicalItemExtractor,
        "API_DOC": TechnicalItemExtractor,
        "USER_MANUAL": TechnicalItemExtractor,
        "SYSTEM_DESIGN": TechnicalItemExtractor,
        "SOP": TechnicalItemExtractor,
        "SPEC": TechnicalItemExtractor,
        "TROUBLESHOOT": TechnicalItemExtractor,
        "USER_GUIDE": TechnicalItemExtractor,
        # Enterprise knowledge doc types
        "TRAINING": TechnicalItemExtractor,
        "RELEASE_NOTE": TechnicalItemExtractor,
        "RELEASE_NOTES": TechnicalItemExtractor,
        "REFERENCE": TechnicalItemExtractor,
        "INCIDENT": TechnicalItemExtractor,
        "ARCHITECTURE": TechnicalItemExtractor,
        "CONFIG": TechnicalItemExtractor,
        # Research domain
        "RESEARCH_PAPER": ResearchItemExtractor,
        "ACADEMIC_PAPER": ResearchItemExtractor,
        "THESIS": ResearchItemExtractor,
        "DISSERTATION": ResearchItemExtractor,
        "RESEARCH": ResearchItemExtractor,
        "PAPER": ResearchItemExtractor,
    }

    extractor_class = extractors.get(doc_type)

    if extractor_class is None:
        doc_type_lower = doc_type.lower()
        if any(kw in doc_type_lower for kw in ["legal", "contract", "agreement", "governing", "psa", "indenture", "trust", "pooling"]):
            extractor_class = LegalItemExtractor
        elif any(kw in doc_type_lower for kw in ["technical", "api", "manual", "spec", "sop"]):
            extractor_class = TechnicalItemExtractor
        elif any(kw in doc_type_lower for kw in ["research", "paper", "journal", "thesis"]):
            extractor_class = ResearchItemExtractor
        else:
            from backend.extraction.generic_item_extractor import GenericItemExtractor
            extractor_class = GenericItemExtractor

    extractor = extractor_class()
    extractor.logger.info(f"Routed {doc_type} to {extractor.__class__.__name__}")
    return extractor
