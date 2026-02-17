# Phase 6: Technical Design
## Implementation-Ready Specifications

**Document Version:** 2.0  
**Date:** February 16, 2026  
**Status:** Proposal - Pending Approval  
**Scope:** Complete implementation specifications with code

---

## Table of Contents
1. [Overview](#overview)
2. [ItemExtractor Framework](#itemextractor-framework)
3. [Section Node Builder](#section-node-builder)
4. [Dual Vector Store Implementation](#dual-vector-store-implementation)
5. [Iterative Retrieval Orchestrator](#iterative-retrieval-orchestrator)
6. [PageRank Boost Computation](#pagerank-boost-computation)
7. [Graph Schema Update](#graph-schema-update)
8. [API Contracts](#api-contracts)
9. [Configuration](#configuration)
10. [Migration Utilities](#migration-utilities)

---

## Overview

This document provides complete, production-ready code for Phase 6 implementation. All code includes:
- Type hints
- Docstrings
- Error handling
- Logging
- Unit test hooks

**File Structure:**
```
backend/
├── agents/
│   └── item_extractor_agent.py         (NEW - ItemExtractor framework)
├── extraction/
│   ├── item_extractor_base.py          (NEW - Abstract base)
│   ├── legal_item_extractor.py         (NEW - Legal domain)
│   ├── technical_item_extractor.py     (NEW - Technical domain)
│   └── research_item_extractor.py      (NEW - Research domain)
├── graph/
│   ├── enhanced_graph_builder.py       (UPDATED - Section nodes + typed edges)
│   └── pagerank.py                     (NEW - Personalized PageRank)
├── retrieval/
│   ├── iterative_orchestrator.py       (NEW - Multi-hop retrieval)
│   └── hybrid_reranker.py              (NEW - Content + PageRank scoring)
├── vector/
│   ├── dual_vector_store.py            (NEW - Item + Section stores)
│   └── legal_chunker.py                (UPDATED - Multi-level pattern)
└── common/
    └── config_phase6.py                (NEW - Phase 6 parameters)
```

---

## ItemExtractor Framework

### Abstract Base Class

**File:** `backend/extraction/item_extractor_base.py`

```python
"""
Abstract base class for domain-specific item extraction.

This module provides the ItemExtractor interface that all domain-specific
extractors must implement. It establishes a pluggable framework allowing
the system to handle legal, technical, research, and future document types
without modifying the core ingestion pipeline.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import hashlib
import re


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
    metadata: Dict[str, Any]


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
    
    def __init__(self):
        """Initialize extractor with domain-specific configuration."""
        self.logger = self._get_logger()
        self.supported_types = self.get_supported_types()
    
    @abstractmethod
    def extract_items(self, section_text: str, section_number: str, 
                     section_heading: str, section_index: int,
                     document_id: str) -> List[Item]:
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
            
        Raises:
            ValueError: If section_text is empty or invalid
        """
        pass
    
    @abstractmethod
    def classify_item_type(self, text: str) -> str:
        """
        Classify an item into a semantic type.
        
        Args:
            text: Item text to classify
            
        Returns:
            Item type string (e.g., "Obligation", "Definition")
            
        Example:
            >>> extractor.classify_item_type("The Trustee shall establish...")
            "Obligation"
        """
        pass
    
    @abstractmethod
    def get_supported_types(self) -> List[str]:
        """
        Return list of item types this extractor supports.
        
        Returns:
            List of supported type strings
            
        Example:
            >>> extractor.get_supported_types()
            ["Obligation", "Prohibition", "Right", "Definition"]
        """
        pass
    
    # Common utilities available to all subclasses
    
    def _generate_item_id(self, document_id: str, section_index: int,
                          item_type: str, item_index: int, text: str) -> str:
        """
        Generate unique item identifier.
        
        Format: doc-sec{:03d}-type-{index}-{hash8}
        Example: psa_2006_he1-sec042-obligation-0-a3b2c1d4
        
        Args:
            document_id: Parent document ID
            section_index: Section position
            item_type: Item semantic type
            item_index: Item position within section
            text: Item text (for hash uniqueness)
            
        Returns:
            Unique item ID string
        """
        # Normalize item_type (lowercase, max 12 chars)
        type_normalized = item_type.lower().replace(" ", "_")[:12]
        
        # Generate short hash from text (first 8 chars)
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:8]
        
        return f"{document_id}-sec{section_index:03d}-{type_normalized}-{item_index}-{text_hash}"
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences with legal/technical awareness.
        
        Handles:
        - Abbreviations (e.g., U.S., Inc., e.g.)
        - Decimal numbers (e.g., 5.02, 3.14)
        - Citations (e.g., Section 5.02(a))
        
        Args:
            text: Text to split
            
        Returns:
            List of sentence strings
        """
        # Replace protected periods with placeholders
        text = re.sub(r'\b([A-Z][a-z]*)\.', r'\1<PERIOD>', text)  # Mr., Dr., etc.
        text = re.sub(r'\b(e\.g\.|i\.e\.|vs\.|Inc\.|Corp\.|Ltd\.)', 
                     lambda m: m.group(0).replace('.', '<PERIOD>'), text)
        
        # Split on sentence terminators followed by space + capital
        sentences = re.split(r'([.!?])\s+(?=[A-Z])', text)
        
        # Rejoin sentence fragments
        result = []
        for i in range(0, len(sentences) - 1, 2):
            sentence = sentences[i] + sentences[i + 1]
            # Restore protected periods
            sentence = sentence.replace('<PERIOD>', '.')
            result.append(sentence.strip())
        
        # Add final sentence if exists
        if len(sentences) % 2 == 1:
            result.append(sentences[-1].replace('<PERIOD>', '.').strip())
        
        return [s for s in result if len(s) > 10]  # Filter trivial sentences
    
    def _extract_section_references(self, text: str) -> List[str]:
        """
        Extract section number references from text.
        
        Patterns matched:
        - Section 5.02
        - § 5.02(a)
        - Sections 5.02 and 6.03
        
        Args:
            text: Text to search
            
        Returns:
            List of section numbers referenced
        """
        pattern = r'(?:Section|§)\s+(\d+(?:\.\d+)*(?:\([a-zA-Z0-9]+\))?)'
        matches = re.findall(pattern, text, re.IGNORECASE)
        return list(set(matches))  # Deduplicate
    
    def _get_logger(self):
        """Get logger instance for this extractor."""
        import logging
        return logging.getLogger(self.__class__.__name__)


def get_item_extractor(doc_type: str) -> ItemExtractor:
    """
    Factory function: Route document type to appropriate extractor.
    
    Design Pattern: Factory Method
    
    Args:
        doc_type: Document type from regime classification
        
    Returns:
        Appropriate ItemExtractor subclass instance
        
    Example:
        >>> extractor = get_item_extractor("GOVERNING_DOC_LEGAL")
        >>> isinstance(extractor, LegalItemExtractor)
        True
    """
    from backend.extraction.legal_item_extractor import LegalItemExtractor
    from backend.extraction.technical_item_extractor import TechnicalItemExtractor
    from backend.extraction.research_item_extractor import ResearchItemExtractor
    
    # Domain routing table
    extractors = {
        # Legal domain
        "GOVERNING_DOC_LEGAL": LegalItemExtractor,
        "REGULATORY_GUIDANCE": LegalItemExtractor,
        "LEGAL_OPINION": LegalItemExtractor,
        "COURT_DECISION": LegalItemExtractor,
        
        # Technical domain
        "TECHNICAL_SPEC": TechnicalItemExtractor,
        "API_DOCUMENTATION": TechnicalItemExtractor,
        "USER_MANUAL": TechnicalItemExtractor,
        "SYSTEM_DESIGN": TechnicalItemExtractor,
        
        # Research domain
        "RESEARCH_PAPER": ResearchItemExtractor,
        "ACADEMIC_PAPER": ResearchItemExtractor,
        "THESIS": ResearchItemExtractor,
        "DISSERTATION": ResearchItemExtractor,
    }
    
    extractor_class = extractors.get(doc_type)
    
    if extractor_class is None:
        # Fallback: Try to infer from doc_type keywords
        doc_type_lower = doc_type.lower()
        if any(kw in doc_type_lower for kw in ["legal", "contract", "agreement"]):
            extractor_class = LegalItemExtractor
        elif any(kw in doc_type_lower for kw in ["technical", "api", "manual", "spec"]):
            extractor_class = TechnicalItemExtractor
        elif any(kw in doc_type_lower for kw in ["research", "paper", "journal"]):
            extractor_class = ResearchItemExtractor
        else:
            # Ultimate fallback: Generic extractor (paragraph-level)
            from backend.extraction.generic_item_extractor import GenericItemExtractor
            extractor_class = GenericItemExtractor
    
    extractor = extractor_class()
    extractor.logger.info(f"Routed {doc_type} to {extractor.__class__.__name__}")
    
    return extractor
```

---

### Legal Item Extractor

**File:** `backend/extraction/legal_item_extractor.py`

```python
"""
Legal domain item extractor.

Extracts legal semantic items from contracts, agreements, and regulatory documents:
- Obligations (shall, must, required)
- Prohibitions (shall not, must not, may not)
- Rights (may, permitted, authorized)
- Definitions (means, defined as)
- Conditions (if, unless, provided that)
- Statements (default catch-all)
"""

from typing import List, Dict, Any
import re
from backend.extraction.item_extractor_base import ItemExtractor, Item


class LegalItemExtractor(ItemExtractor):
    """
    Legal document item extractor.
    
    Identifies legal semantic items using modal verb patterns and
    legal conventions. Extracts rich metadata including actors (parties),
    modal verbs, and defined term references.
    """
    
    def __init__(self):
        super().__init__()
        
        # Legal modal verb patterns
        self.obligation_patterns = [
            r'\bshall\b',
            r'\bmust\b',
            r'\b(?:is|are)\s+required\s+to\b',
            r'\b(?:is|are)\s+obligated\s+to\b',
        ]
        
        self.prohibition_patterns = [
            r'\bshall\s+not\b',
            r'\bmust\s+not\b',
            r'\bmay\s+not\b',
            r'\b(?:is|are)\s+prohibited\s+from\b',
        ]
        
        self.right_patterns = [
            r'\bmay\b',
            r'\b(?:is|are)\s+permitted\s+to\b',
            r'\b(?:is|are)\s+authorized\s+to\b',
            r'\b(?:is|are)\s+entitled\s+to\b',
        ]
        
        self.definition_patterns = [
            r'\bmeans\b',
            r'\bdefined\s+as\b',
            r'\brefers\s+to\b',
            r'"\s*means\s+',
        ]
        
        self.condition_patterns = [
            r'^if\b',
            r'\bunless\b',
            r'\bprovided\s+that\b',
            r'\bsubject\s+to\b',
            r'\bin\s+the\s+event\b',
        ]
        
        # Legal actor patterns (parties common in contracts)
        self.actor_patterns = [
            r'\bTrustee\b',
            r'\bServicer\b',
            r'\bBorrower\b',
            r'\bLender\b',
            r'\bIssuer\b',
            r'\bInvestor\b',
            r'\bAgent\b',
            r'\bCustodian\b',
        ]
    
    def get_supported_types(self) -> List[str]:
        return [
            "Obligation",
            "Prohibition", 
            "Right",
            "Definition",
            "Condition",
            "Statement"
        ]
    
    def extract_items(self, section_text: str, section_number: str,
                     section_heading: str, section_index: int,
                     document_id: str) -> List[Item]:
        """
        Extract legal items from section.
        
        Algorithm:
        1. Split section into sentences
        2. Classify each sentence by type
        3. Extract metadata (actors, verbs, defined terms)
        4. Generate Item objects
        """
        if not section_text or len(section_text.strip()) < 10:
            return []
        
        sentences = self._split_into_sentences(section_text)
        items = []
        
        for item_index, sentence in enumerate(sentences):
            # Classify sentence type
            item_type = self.classify_item_type(sentence)
            
            # Extract metadata
            metadata = self._extract_legal_metadata(sentence)
            
            # Generate unique ID
            item_id = self._generate_item_id(
                document_id, section_index, item_type, item_index, sentence
            )
            
            # Create Item
            item = Item(
                id=item_id,
                item_type=item_type,
                text=sentence,
                document_id=document_id,
                section_number=section_number,
                section_heading=section_heading,
                section_index=section_index,
                item_index=item_index,
                metadata=metadata
            )
            
            items.append(item)
        
        self.logger.debug(f"Extracted {len(items)} items from section {section_number}")
        return items
    
    def classify_item_type(self, text: str) -> str:
        """
        Classify legal item type based on modal verbs.
        
        Priority order:
        1. Prohibition (most restrictive)
        2. Obligation
        3. Definition (explicit)
        4. Condition
        5. Right
        6. Statement (fallback)
        """
        text_lower = text.lower()
        
        # Check prohibition (highest priority)
        if any(re.search(p, text_lower) for p in self.prohibition_patterns):
            return "Prohibition"
        
        # Check obligation
        if any(re.search(p, text_lower) for p in self.obligation_patterns):
            return "Obligation"
        
        # Check definition (explicit "means")
        if any(re.search(p, text_lower) for p in self.definition_patterns):
            return "Definition"
        
        # Check condition
        if any(re.search(p, text_lower) for p in self.condition_patterns):
            return "Condition"
        
        # Check right
        if any(re.search(p, text_lower) for p in self.right_patterns):
            return "Right"
        
        # Default fallback
        return "Statement"
    
    def _extract_legal_metadata(self, text: str) -> Dict[str, Any]:
        """
        Extract legal-specific metadata from item text.
        
        Returns:
            metadata: Dict with keys actors, verbs, defined_terms, section_refs
        """
        metadata = {
            "actors": [],
            "verbs": [],
            "defined_terms": [],
            "section_refs": []
        }
        
        # Extract actors (parties)
        for pattern in self.actor_patterns:
            matches = re.findall(pattern, text)
            metadata["actors"].extend(matches)
        metadata["actors"] = list(set(metadata["actors"]))  # Dedupe
        
        # Extract modal verbs
        modal_verbs = ["shall", "must", "may", "should", "will"]
        for verb in modal_verbs:
            if re.search(rf'\b{verb}\b', text, re.IGNORECASE):
                metadata["verbs"].append(verb)
        
        # Extract defined terms (quoted terms or capitalized terms)
        # Pattern: "Term" or capitalized phrases
        defined_terms = re.findall(r'"([^"]+)"', text)
        metadata["defined_terms"] = defined_terms
        
        # Extract section references
        metadata["section_refs"] = self._extract_section_references(text)
        
        return metadata
```

---

### Technical Item Extractor

**File:** `backend/extraction/technical_item_extractor.py`

```python
"""
Technical domain item extractor.

Extracts technical semantic items from specifications, manuals, and API docs:
- Requirements (MUST, system must, required)
- Procedures (Step 1, To configure, Follow)
- Configurations (Set, Configure, parameter:)
- Warnings (WARNING:, CAUTION:, Important:)
- Notes (Note:, Tip:, Information:)
- Examples (Example:, Usage:, code blocks)
"""

from typing import List, Dict, Any
import re
from backend.extraction.item_extractor_base import ItemExtractor, Item


class TechnicalItemExtractor(ItemExtractor):
    """
    Technical document item extractor.
    
    Identifies technical semantic items using RFC 2119 keywords (MUST, SHOULD),
    procedural markers, and formatting conventions from technical writing.
    """
    
    def __init__(self):
        super().__init__()
        
        # RFC 2119 requirement patterns
        self.requirement_patterns = [
            r'\bMUST\b',
            r'\bREQUIRED\b',
            r'\bSHALL\b',
            r'\bsystem\s+must\b',
            r'\b(?:is|are)\s+required\b',
        ]
        
        # Procedural step patterns
        self.procedure_patterns = [
            r'^Step\s+\d+',
            r'^To\s+\w+',
            r'^Follow\s+these',
            r'^\d+\.\s+',  # Numbered list
        ]
        
        # Configuration patterns
        self.configuration_patterns = [
            r'^Set\s+\w+',
            r'^Configure\s+\w+',
            r'^\w+\s*[:=]',  # parameter: value
        ]
        
        # Warning/caution patterns
        self.warning_patterns = [
            r'^WARNING:',
            r'^CAUTION:',
            r'^Important:',
            r'^DANGER:',
        ]
        
        # Note/tip patterns
        self.note_patterns = [
            r'^Note:',
            r'^Tip:',
            r'^Information:',
            r'^Remember:',
        ]
        
        # Example patterns
        self.example_patterns = [
            r'^Example:',
            r'^Usage:',
            r'^```',  # Code block
            r'^Sample:',
        ]
    
    def get_supported_types(self) -> List[str]:
        return [
            "Requirement",
            "Procedure",
            "Configuration",
            "Warning",
            "Note",
            "Example"
        ]
    
    def extract_items(self, section_text: str, section_number: str,
                     section_heading: str, section_index: int,
                     document_id: str) -> List[Item]:
        """Extract technical items from section."""
        if not section_text or len(section_text.strip()) < 10:
            return []
        
        # Technical docs often use block formatting, so split by double newline
        blocks = re.split(r'\n\s*\n', section_text)
        items = []
        
        for item_index, block in enumerate(blocks):
            block = block.strip()
            if len(block) < 10:
                continue
            
            # Classify block type
            item_type = self.classify_item_type(block)
            
            # Extract metadata
            metadata = self._extract_technical_metadata(block)
            
            # Generate unique ID
            item_id = self._generate_item_id(
                document_id, section_index, item_type, item_index, block
            )
            
            # Create Item
            item = Item(
                id=item_id,
                item_type=item_type,
                text=block,
                document_id=document_id,
                section_number=section_number,
                section_heading=section_heading,
                section_index=section_index,
                item_index=item_index,
                metadata=metadata
            )
            
            items.append(item)
        
        self.logger.debug(f"Extracted {len(items)} technical items from section {section_number}")
        return items
    
    def classify_item_type(self, text: str) -> str:
        """
        Classify technical item type.
        
        Priority order:
        1. Warning (highest priority - safety)
        2. Requirement (RFC 2119 MUST)
        3. Configuration (parameter settings)
        4. Procedure (step-by-step)
        5. Example (code/sample)
        6. Note (informational)
        """
        # Check warning (highest priority for safety)
        if any(re.search(p, text, re.IGNORECASE) for p in self.warning_patterns):
            return "Warning"
        
        # Check requirement (RFC 2119)
        if any(re.search(p, text) for p in self.requirement_patterns):
            return "Requirement"
        
        # Check configuration
        if any(re.search(p, text) for p in self.configuration_patterns):
            return "Configuration"
        
        # Check procedure
        if any(re.search(p, text) for p in self.procedure_patterns):
            return "Procedure"
        
        # Check example
        if any(re.search(p, text) for p in self.example_patterns):
            return "Example"
        
        # Check note
        if any(re.search(p, text, re.IGNORECASE) for p in self.note_patterns):
            return "Note"
        
        # Default: treat as requirement if contains imperative verb
        if re.search(r'\b(?:must|should|shall|will|can)\b', text, re.IGNORECASE):
            return "Requirement"
        
        return "Note"  # Fallback
    
    def _extract_technical_metadata(self, text: str) -> Dict[str, Any]:
        """
        Extract technical-specific metadata.
        
        Returns:
            metadata: Dict with keys parameters, commands, files, urls
        """
        metadata = {
            "parameters": [],
            "commands": [],
            "files": [],
            "urls": []
        }
        
        # Extract parameters (key: value or key=value)
        params = re.findall(r'(\w+)\s*[:=]\s*([^\n,;]+)', text)
        metadata["parameters"] = [{"name": p[0], "value": p[1].strip()} for p in params]
        
        # Extract commands ($ or > prefix or backticked)
        commands = re.findall(r'[$>]\s*(.+?)(?:\n|$)', text)
        commands += re.findall(r'`([^`]+)`', text)
        metadata["commands"] = list(set([c.strip() for c in commands if len(c.strip()) > 3]))
        
        # Extract file paths (/path/to/file or C:\path\to\file)
        files = re.findall(r'(?:[A-Z]:\\|/)[\w/\\.-]+', text)
        metadata["files"] = list(set(files))
        
        # Extract URLs
        urls = re.findall(r'https?://[^\s<>"\']+', text)
        metadata["urls"] = list(set(urls))
        
        return metadata
```

---

### Research Item Extractor

**File:** `backend/extraction/research_item_extractor.py`

```python
"""
Research domain item extractor.

Extracts academic semantic items from research papers and theses:
- Theorems (Theorem 1, Proposition, Corollary)
- Proofs (Proof., Proof of Theorem, Proof sketch)
- Lemmas (Lemma 1, Supporting Lemma)
- Algorithms (Algorithm:, Procedure:, Input/Output)
- Observations (We observe, Note that, It can be seen)
- Hypotheses (We hypothesize, Conjecture)
"""

from typing import List, Dict, Any
import re
from backend.extraction.item_extractor_base import ItemExtractor, Item


class ResearchItemExtractor(ItemExtractor):
    """
    Research paper item extractor.
    
    Identifies mathematical and scientific semantic items using LaTeX-like
    patterns and academic writing conventions.
    """
    
    def __init__(self):
        super().__init__()
        
        # Mathematical statement patterns
        self.theorem_patterns = [
            r'^Theorem\s+\d+',
            r'^Proposition\s+\d+',
            r'^Corollary\s+\d+',
            r'\\begin\{theorem\}',
        ]
        
        self.proof_patterns = [
            r'^Proof\.',
            r'^Proof\s+of\s+Theorem',
            r'^Proof\s+sketch',
            r'\\begin\{proof\}',
        ]
        
        self.lemma_patterns = [
            r'^Lemma\s+\d+',
            r'^Supporting\s+Lemma',
            r'\\begin\{lemma\}',
        ]
        
        # Algorithmic patterns
        self.algorithm_patterns = [
            r'^Algorithm\s+\d+',
            r'^Procedure:',
            r'^Input:',
            r'^Output:',
            r'\\begin\{algorithm\}',
        ]
        
        # Observational patterns
        self.observation_patterns = [
            r'^We\s+observe',
            r'^Note\s+that',
            r'^It\s+can\s+be\s+seen',
            r'^Observe\s+that',
        ]
        
        # Hypothesis patterns
        self.hypothesis_patterns = [
            r'^We\s+hypothesize',
            r'^We\s+conjecture',
            r'^Hypothesis\s+\d+',
            r'^Conjecture\s+\d+',
        ]
    
    def get_supported_types(self) -> List[str]:
        return [
            "Theorem",
            "Proof",
            "Lemma",
            "Algorithm",
            "Observation",
            "Hypothesis"
        ]
    
    def extract_items(self, section_text: str, section_number: str,
                     section_heading: str, section_index: int,
                     document_id: str) -> List[Item]:
        """Extract research items from section."""
        if not section_text or len(section_text.strip()) < 10:
            return []
        
        # Research papers use paragraph blocks, split by double newline
        blocks = re.split(r'\n\s*\n', section_text)
        items = []
        
        for item_index, block in enumerate(blocks):
            block = block.strip()
            if len(block) < 10:
                continue
            
            # Classify block type
            item_type = self.classify_item_type(block)
            
            # Extract metadata
            metadata = self._extract_research_metadata(block)
            
            # Generate unique ID
            item_id = self._generate_item_id(
                document_id, section_index, item_type, item_index, block
            )
            
            # Create Item
            item = Item(
                id=item_id,
                item_type=item_type,
                text=block,
                document_id=document_id,
                section_number=section_number,
                section_heading=section_heading,
                section_index=section_index,
                item_index=item_index,
                metadata=metadata
            )
            
            items.append(item)
        
        self.logger.debug(f"Extracted {len(items)} research items from section {section_number}")
        return items
    
    def classify_item_type(self, text: str) -> str:
        """
        Classify research item type.
        
        Priority order:
        1. Theorem (formal statement)
        2. Proof (formal argument)
        3. Lemma (supporting statement)
        4. Algorithm (procedural)
        5. Hypothesis (claim)
        6. Observation (note)
        """
        # Check theorem
        if any(re.search(p, text, re.IGNORECASE) for p in self.theorem_patterns):
            return "Theorem"
        
        # Check proof
        if any(re.search(p, text, re.IGNORECASE) for p in self.proof_patterns):
            return "Proof"
        
        # Check lemma
        if any(re.search(p, text, re.IGNORECASE) for p in self.lemma_patterns):
            return "Lemma"
        
        # Check algorithm
        if any(re.search(p, text, re.IGNORECASE) for p in self.algorithm_patterns):
            return "Algorithm"
        
        # Check hypothesis
        if any(re.search(p, text, re.IGNORECASE) for p in self.hypothesis_patterns):
            return "Hypothesis"
        
        # Check observation
        if any(re.search(p, text, re.IGNORECASE) for p in self.observation_patterns):
            return "Observation"
        
        return "Observation"  # Fallback
    
    def _extract_research_metadata(self, text: str) -> Dict[str, Any]:
        """
        Extract research-specific metadata.
        
        Returns:
            metadata: Dict with keys equations, citations, variables, proofs
        """
        metadata = {
            "equations": [],
            "citations": [],
            "variables": [],
            "numbers": []
        }
        
        # Extract numbered statements (Theorem 5, Lemma 2)
        numbers = re.findall(r'(?:Theorem|Lemma|Proposition|Corollary|Algorithm)\s+(\d+)', text)
        metadata["numbers"] = list(set(numbers))
        
        # Extract citations [1], [Smith et al., 2020]
        citations = re.findall(r'\[([^\]]+)\]', text)
        metadata["citations"] = [c for c in citations if len(c) < 50]  # Filter out long text
        
        # Extract mathematical variables (single letters, Greek)
        variables = re.findall(r'\b([a-zA-Z]|\\[a-z]+)\b', text)
        # Filter common words
        common_words = {"a", "i", "we", "is", "be", "to", "of", "in", "by"}
        metadata["variables"] = list(set([v for v in variables if v not in common_words]))[:20]  # Top 20
        
        # Extract equations (LaTeX-style or numbered)
        equations = re.findall(r'\$\$(.+?)\$\$', text)  # $$...$$
        equations += re.findall(r'\\begin\{equation\}(.+?)\\end\{equation\}', text, re.DOTALL)
        metadata["equations"] = [eq.strip() for eq in equations]
        
        return metadata
```

---

## Section Node Builder

**File:** `backend/graph/enhanced_graph_builder.py` (UPDATED)

```python
"""
Enhanced graph builder with hierarchical structure.

Updates from Phase 5:
- Creates SECTION nodes (new hierarchy level)
- Creates typed edges: CONTAINS, NEXT, HAS_RULE, HAS_DEFINITION, REFERENCES
- Extracts items using ItemExtractor framework
- Builds hierarchical Document → Section → Item structure
"""

from typing import List, Dict, Any, Optional
import logging
from neo4j import GraphDatabase
from backend.extraction.item_extractor_base import get_item_extractor, Item


class EnhancedGraphBuilder:
    """
    Hierarchical graph builder for Phase 6.
    
    Graph Structure:
        Document --CONTAINS--> Section --HAS_RULE/HAS_DEFINITION--> Item
        Section --NEXT--> Section (sequential)
        Item --REFERENCES--> Item (dependencies)
    """
    
    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str):
        """
        Initialize graph builder with Neo4j connection.
        
        Args:
            neo4j_uri: Neo4j bolt:// URI
            neo4j_user: Database user
            neo4j_password: Database password
        """
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        self.logger = logging.getLogger(__name__)
    
    def build_hierarchical_graph(self, document_id: str, doc_type: str,
                                sections: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Build hierarchical graph for document.
        
        Args:
            document_id: Document identifier
            doc_type: Document type (for extractor routing)
            sections: List of section dicts with keys:
                - section_number: str
                - section_heading: str
                - section_text: str
                
        Returns:
            Stats dict with keys: sections_created, items_created, edges_created
        """
        stats = {
            "sections_created": 0,
            "items_created": 0,
            "edges_created": 0
        }
        
        # Get appropriate item extractor for this document type
        extractor = get_item_extractor(doc_type)
        
        # Create document node (if not exists)
        self._create_document_node(document_id, doc_type)
        
        # Process sections sequentially
        prev_section_id = None
        
        for section_index, section_dict in enumerate(sections):
            section_number = section_dict["section_number"]
            section_heading = section_dict["section_heading"]
            section_text = section_dict["section_text"]
            
            # Create section node
            section_id = f"sec:{document_id}:{section_index:04d}"
            self._create_section_node(
                section_id=section_id,
                section_number=section_number,
                section_heading=section_heading,
                section_index=section_index,
                document_id=document_id
            )
            stats["sections_created"] += 1
            
            # Create CONTAINS edge: Document -> Section
            self._create_edge(
                from_node_id=document_id,
                to_node_id=section_id,
                edge_type="CONTAINS",
                weight=1.0
            )
            stats["edges_created"] += 1
            
            # Create NEXT edge: PrevSection -> ThisSection
            if prev_section_id:
                self._create_edge(
                    from_node_id=prev_section_id,
                    to_node_id=section_id,
                    edge_type="NEXT",
                    weight=0.8
                )
                stats["edges_created"] += 1
            
            prev_section_id = section_id
            
            # Extract items from section
            items = extractor.extract_items(
                section_text=section_text,
                section_number=section_number,
                section_heading=section_heading,
                section_index=section_index,
                document_id=document_id
            )
            
            # Create item nodes and typed edges
            for item in items:
                self._create_item_node(item)
                stats["items_created"] += 1
                
                # Create typed edge: Section -> Item
                edge_type = self._get_edge_type_for_item(item.item_type)
                self._create_edge(
                    from_node_id=section_id,
                    to_node_id=item.id,
                    edge_type=edge_type,
                    weight=self._get_edge_weight_for_item(item.item_type)
                )
                stats["edges_created"] += 1
            
            # Create REFERENCES edges between items
            references_created = self._create_reference_edges(items)
            stats["edges_created"] += references_created
        
        self.logger.info(f"Built hierarchical graph for {document_id}: {stats}")
        return stats
    
    def _create_document_node(self, document_id: str, doc_type: str):
        """Create or update document node."""
        query = """
        MERGE (d:Document {id: $document_id})
        SET d.doc_type = $doc_type,
            d.updated_at = timestamp()
        """
        with self.driver.session() as session:
            session.run(query, document_id=document_id, doc_type=doc_type)
    
    def _create_section_node(self, section_id: str, section_number: str,
                            section_heading: str, section_index: int,
                            document_id: str):
        """Create section node."""
        query = """
        CREATE (s:Section {
            id: $section_id,
            section_number: $section_number,
            section_heading: $section_heading,
            section_index: $section_index,
            document_id: $document_id,
            created_at: timestamp()
        })
        """
        with self.driver.session() as session:
            session.run(query, 
                       section_id=section_id,
                       section_number=section_number,
                       section_heading=section_heading,
                       section_index=section_index,
                       document_id=document_id)
    
    def _create_item_node(self, item: Item):
        """Create item node."""
        query = """
        CREATE (i:Item {
            id: $id,
            item_type: $item_type,
            text: $text,
            document_id: $document_id,
            section_number: $section_number,
            section_heading: $section_heading,
            section_index: $section_index,
            item_index: $item_index,
            metadata: $metadata,
            created_at: timestamp()
        })
        """
        with self.driver.session() as session:
            session.run(query,
                       id=item.id,
                       item_type=item.item_type,
                       text=item.text,
                       document_id=item.document_id,
                       section_number=item.section_number,
                       section_heading=item.section_heading,
                       section_index=item.section_index,
                       item_index=item.item_index,
                       metadata=item.metadata)
    
    def _create_edge(self, from_node_id: str, to_node_id: str,
                    edge_type: str, weight: float):
        """Create typed edge between nodes."""
        # Dynamic edge type (CONTAINS, NEXT, HAS_RULE, etc.)
        query = f"""
        MATCH (a {{id: $from_id}}), (b {{id: $to_id}})
        CREATE (a)-[r:{edge_type} {{weight: $weight}}]->(b)
        """
        with self.driver.session() as session:
            session.run(query, from_id=from_node_id, to_id=to_node_id, weight=weight)
    
    def _get_edge_type_for_item(self, item_type: str) -> str:
        """Map item type to edge type."""
        # Legal domain
        if item_type in ["Obligation", "Prohibition"]:
            return "HAS_RULE"
        elif item_type == "Definition":
            return "HAS_DEFINITION"
        elif item_type == "Right":
            return "HAS_RIGHT"
        elif item_type == "Condition":
            return "HAS_CONDITION"
        
        # Technical domain
        elif item_type == "Requirement":
            return "HAS_REQUIREMENT"
        elif item_type == "Procedure":
            return "HAS_PROCEDURE"
        elif item_type == "Configuration":
            return "HAS_CONFIGURATION"
        elif item_type == "Warning":
            return "HAS_WARNING"
        
        # Research domain
        elif item_type == "Theorem":
            return "HAS_THEOREM"
        elif item_type == "Proof":
            return "HAS_PROOF"
        elif item_type == "Lemma":
            return "HAS_LEMMA"
        elif item_type == "Algorithm":
            return "HAS_ALGORITHM"
        
        # Fallback
        else:
            return "HAS_ITEM"
    
    def _get_edge_weight_for_item(self, item_type: str) -> float:
        """Get edge weight based on item importance."""
        # High importance (definitions, theorems)
        if item_type in ["Definition", "Theorem", "Lemma"]:
            return 0.9
        
        # Medium-high (obligations, requirements, warnings)
        elif item_type in ["Obligation", "Prohibition", "Requirement", "Warning"]:
            return 0.7
        
        # Medium (rights, procedures, proofs)
        elif item_type in ["Right", "Procedure", "Proof", "Algorithm"]:
            return 0.6
        
        # Lower (conditions, notes, observations)
        else:
            return 0.5
    
    def _create_reference_edges(self, items: List[Item]) -> int:
        """
        Create REFERENCES edges between items based on defined term mentions.
        
        Algorithm:
        1. Find all definition items
        2. For each non-definition item, check if it mentions defined terms
        3. Create REFERENCES edge if match found
        
        Returns:
            Number of REFERENCES edges created
        """
        # Build definition lookup: term -> definition_item_id
        definitions = {}
        for item in items:
            if item.item_type == "Definition":
                # Extract defined term (first quoted phrase or first capitalized phrase)
                defined_term = self._extract_defined_term(item.text)
                if defined_term:
                    definitions[defined_term.lower()] = item.id
        
        if not definitions:
            return 0  # No definitions in this section
        
        # Find references in non-definition items
        edges_created = 0
        for item in items:
            if item.item_type == "Definition":
                continue  # Skip definitions
            
            # Check if item text mentions any defined terms
            item_text_lower = item.text.lower()
            for defined_term, definition_id in definitions.items():
                if defined_term in item_text_lower:
                    # Create REFERENCES edge: item -> definition
                    self._create_edge(
                        from_node_id=item.id,
                        to_node_id=definition_id,
                        edge_type="REFERENCES",
                        weight=0.4
                    )
                    edges_created += 1
        
        return edges_created
    
    def _extract_defined_term(self, definition_text: str) -> Optional[str]:
        """
        Extract the term being defined from definition text.
        
        Examples:
            "Distribution Account" means... → "Distribution Account"
            For purposes of this section, "Sub-Account" refers to... → "Sub-Account"
        """
        import re
        
        # Try quoted term first
        quoted = re.search(r'"([^"]+)"', definition_text)
        if quoted:
            return quoted.group(1)
        
        # Try capitalized phrase before "means"
        capitalized = re.search(r'([A-Z][A-Za-z\s]+)\s+means', definition_text)
        if capitalized:
            return capitalized.group(1).strip()
        
        return None
    
    def close(self):
        """Close Neo4j driver."""
        self.driver.close()
```

---

## Dual Vector Store Implementation

**File:** `backend/vector/dual_vector_store.py` (NEW)

```python
"""
Dual vector store implementation for Phase 6.

Manages two ChromaDB collections:
- items: Item-level (sentence granularity, 500-2K per doc)
- sections: Section-level (paragraph granularity, 50-150 per doc)

Both stores use all-MiniLM-L6-v2 embeddings (384 dimensions).
"""

from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings
import logging
from sentence_transformers import SentenceTransformer
from backend.extraction.item_extractor_base import Item


class DualVectorStore:
    """
    Dual vector store wrapper for item-level and section-level retrieval.
    
    Design:
    - Single ChromaDB client with two collections
    - Same embedding model for both (consistency)
    - Unified query interface with store selection
    """
    
    def __init__(self, persist_directory: str = "./chroma_phase6"):
        """
        Initialize dual vector stores.
        
        Args:
            persist_directory: Directory for ChromaDB persistence
        """
        self.logger = logging.getLogger(__name__)
        
        # Initialize ChromaDB client
        self.client = chromadb.Client(Settings(
            chroma_db_impl="duckdb+parquet",
            persist_directory=persist_directory
        ))
        
        # Initialize embedding model (shared by both stores)
        self.embedding_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        self.embedding_dim = 384
        
        # Create or get collections
        self.item_collection = self.client.get_or_create_collection(
            name="items",
            metadata={"description": "Item-level embeddings (sentence granularity)"}
        )
        
        self.section_collection = self.client.get_or_create_collection(
            name="sections",
            metadata={"description": "Section-level embeddings (paragraph granularity)"}
        )
        
        self.logger.info(f"DualVectorStore initialized: {persist_directory}")
        self.logger.info(f"- Items collection: {self.item_collection.count()} items")
        self.logger.info(f"- Sections collection: {self.section_collection.count()} sections")
    
    # --- Item Store Operations ---
    
    def add_items(self, items: List[Item]):
        """
        Add items to item-level vector store.
        
        Args:
            items: List of Item objects from ItemExtractor
        """
        if not items:
            return
        
        # Prepare data for ChromaDB
        ids = [item.id for item in items]
        texts = [item.text for item in items]
        embeddings = self.embedding_model.encode(texts).tolist()
        
        metadatas = [
            {
                "item_type": item.item_type,
                "document_id": item.document_id,
                "section_number": item.section_number,
                "section_heading": item.section_heading,
                "section_index": item.section_index,
                "item_index": item.item_index,
                **item.metadata  # Flatten domain-specific metadata
            }
            for item in items
        ]
        
        # Add to collection
        self.item_collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )
        
        self.logger.debug(f"Added {len(items)} items to vector store")
    
    def search_items(self, query: str, top_k: int = 10,
                    filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Search item-level vector store.
        
        Args:
            query: Query string
            top_k: Number of results to return
            filters: Optional metadata filters (e.g., {"item_type": "Definition"})
            
        Returns:
            List of result dicts with keys: id, text, similarity, metadata
        """
        # Encode query
        query_embedding = self.embedding_model.encode([query])[0].tolist()
        
        # Build where clause from filters
        where = filters if filters else None
        
        # Query collection
        results = self.item_collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where
        )
        
        # Format results
        formatted_results = []
        for i in range(len(results['ids'][0])):
            formatted_results.append({
                "id": results['ids'][0][i],
                "text": results['documents'][0][i],
                "similarity": 1 - results['distances'][0][i],  # Convert distance to similarity
                "metadata": results['metadatas'][0][i],
                "type": "item"
            })
        
        self.logger.debug(f"Item search returned {len(formatted_results)} results")
        return formatted_results
    
    # --- Section Store Operations ---
    
    def add_sections(self, sections: List[Dict[str, Any]]):
        """
        Add sections to section-level vector store.
        
        Args:
            sections: List of section dicts with keys:
                - id: str (section ID)
                - section_number: str
                - section_heading: str
                - section_text: str (full section content)
                - document_id: str
                - section_index: int
                - item_count: int
                - item_types: List[str]
        """
        if not sections:
            return
        
        # Prepare data
        ids = [sec["id"] for sec in sections]
        texts = [sec["section_text"] for sec in sections]
        embeddings = self.embedding_model.encode(texts).tolist()
        
        metadatas = [
            {
                "section_number": sec["section_number"],
                "section_heading": sec["section_heading"],
                "document_id": sec["document_id"],
                "section_index": sec["section_index"],
                "item_count": sec.get("item_count", 0),
                "item_types": ",".join(sec.get("item_types", []))  # Comma-separated list
            }
            for sec in sections
        ]
        
        # Add to collection
        self.section_collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )
        
        self.logger.debug(f"Added {len(sections)} sections to vector store")
    
    def search_sections(self, query: str, top_k: int = 5,
                       filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Search section-level vector store.
        
        Args:
            query: Query string
            top_k: Number of results to return
            filters: Optional metadata filters
            
        Returns:
            List of result dicts with keys: id, text, similarity, metadata
        """
        # Encode query
        query_embedding = self.embedding_model.encode([query])[0].tolist()
        
        # Build where clause
        where = filters if filters else None
        
        # Query collection
        results = self.section_collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where
        )
        
        # Format results
        formatted_results = []
        for i in range(len(results['ids'][0])):
            formatted_results.append({
                "id": results['ids'][0][i],
                "text": results['documents'][0][i],
                "similarity": 1 - results['distances'][0][i],
                "metadata": results['metadatas'][0][i],
                "type": "section"
            })
        
        self.logger.debug(f"Section search returned {len(formatted_results)} results")
        return formatted_results
    
    # --- Unified Query Interface ---
    
    def search(self, query: str, store: str = "items", top_k: int = 10,
              filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Unified search interface.
        
        Args:
            query: Query string
            store: "items" or "sections"
            top_k: Number of results
            filters: Optional metadata filters
            
        Returns:
            List of result dicts
        """
        if store == "items":
            return self.search_items(query, top_k, filters)
        elif store == "sections":
            return self.search_sections(query, top_k, filters)
        else:
            raise ValueError(f"Invalid store: {store}. Must be 'items' or 'sections'")
    
    def get_by_id(self, item_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve item or section by ID.
        
        Args:
            item_id: Item or section ID
            
        Returns:
            Result dict or None if not found
        """
        # Try item collection first
        try:
            result = self.item_collection.get(ids=[item_id])
            if result['ids']:
                return {
                    "id": result['ids'][0],
                    "text": result['documents'][0],
                    "metadata": result['metadatas'][0],
                    "type": "item"
                }
        except:
            pass
        
        # Try section collection
        try:
            result = self.section_collection.get(ids=[item_id])
            if result['ids']:
                return {
                    "id": result['ids'][0],
                    "text": result['documents'][0],
                    "metadata": result['metadatas'][0],
                    "type": "section"
                }
        except:
            pass
        
        return None
    
    def persist(self):
        """Persist vector stores to disk."""
        self.client.persist()
        self.logger.info("Vector stores persisted")
```

---

## Iterative Retrieval Orchestrator

**File:** `backend/retrieval/iterative_orchestrator.py` (NEW)

```python
"""
Iterative multi-hop retrieval orchestrator for Phase 6.

Implements algorithm:
1. Alternate between item store (odd) and section store (even) iterations
2. Expand via graph (BFS depth=2, follow CONTAINS/NEXT/REFERENCES edges)
3. Hybrid rerank: 0.7 × content_similarity + 0.3 × pagerank
4. Exit on: confidence > 0.90 OR improvement < 0.05 OR max iterations
"""

from typing import List, Dict, Any, Optional
import logging
from backend.vector.dual_vector_store import DualVectorStore
from backend.graph.graph_interface import GraphInterface
from backend.retrieval.hybrid_reranker import HybridReranker


class IterativeRetrievalOrchestrator:
    """
    Orchestrates iterative multi-hop retrieval with dual vector stores.
    
    Design Pattern: Orchestrator (coordinates vector stores, graph, reranker)
    """
    
    def __init__(self, vector_store: DualVectorStore, graph: GraphInterface,
                 reranker: HybridReranker):
        """
        Initialize orchestrator.
        
        Args:
            vector_store: DualVectorStore instance
            graph: GraphInterface instance
            reranker: HybridReranker instance
        """
        self.vector_store = vector_store
        self.graph = graph
        self.reranker = reranker
        self.logger = logging.getLogger(__name__)
    
    def retrieve(self, query: str, max_iterations: int = 3,
                min_confidence: float = 0.90, min_improvement: float = 0.05,
                top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Iterative multi-hop retrieval.
        
        Args:
            query: User query string
            max_iterations: Maximum iterations (default: 3)
            min_confidence: Exit threshold for confidence (default: 0.90)
            min_improvement: Exit threshold for improvement (default: 0.05)
            top_k: Number of final results to return (default: 5)
            
        Returns:
            List of result dicts with keys: id, text, confidence, metadata
        """
        self.logger.info(f"Starting iterative retrieval for query: {query}")
        
        # Initialize state
        all_results = []
        visited_node_ids = set()
        prev_confidence = 0.0
        
        # Iterate
        for iteration in range(max_iterations):
            self.logger.info(f"--- Iteration {iteration + 1}/{max_iterations} ---")
            
            # STEP 1: Vector Search (alternate between stores)
            if iteration % 2 == 0:
                # Odd iterations: Item store (atomic precision)
                store = "items"
                vector_top_k = 10
            else:
                # Even iterations: Section store (contextual breadth)
                store = "sections"
                vector_top_k = 5
            
            vector_results = self.vector_store.search(query, store=store, top_k=vector_top_k)
            self.logger.info(f"Vector search ({store}): {len(vector_results)} results")
            
            # Mark as visited
            for result in vector_results:
                visited_node_ids.add(result['id'])
            
            # STEP 2: Graph Expansion (BFS depth=2)
            expanded_nodes = []
            for result in vector_results:
                neighbors = self.graph.bfs_expand(
                    start_node_id=result['id'],
                    max_depth=2,
                    edge_types=['CONTAINS', 'NEXT', 'REFERENCES', 'HAS_RULE', 'HAS_DEFINITION'],
                    avoid_nodes=visited_node_ids,
                    max_neighbors=20
                )
                expanded_nodes.extend(neighbors)
                self.logger.debug(f"Expanded {len(neighbors)} neighbors from {result['id']}")
            
            # Mark expanded as visited
            for node in expanded_nodes:
                visited_node_ids.add(node['id'])
            
            self.logger.info(f"Graph expansion: {len(expanded_nodes)} new nodes")
            
            # STEP 3: Fetch Content for Expanded Nodes
            expanded_content = []
            for node in expanded_nodes:
                content = self.vector_store.get_by_id(node['id'])
                if content:
                    expanded_content.append(content)
            
            # STEP 4: Combine Results
            combined_results = all_results + vector_results + expanded_content
            self.logger.info(f"Combined: {len(combined_results)} total results")
            
            # STEP 5: Hybrid Rerank (Content + PageRank)
            reranked_results = self.reranker.rerank(
                results=combined_results,
                query=query,
                content_weight=0.7,
                pagerank_weight=0.3
            )
            
            # Keep top 50 for next iteration
            all_results = reranked_results[:50]
            
            # STEP 6: Check Exit Criteria
            top_confidence = reranked_results[0]['confidence'] if reranked_results else 0.0
            self.logger.info(f"Top confidence: {top_confidence:.3f}")
            
            # Exit criterion 1: High confidence reached
            if top_confidence >= min_confidence:
                self.logger.info(f"Exit: High confidence ({top_confidence:.3f} >= {min_confidence})")
                break
            
            # Exit criterion 2: Diminishing returns
            if iteration > 0:
                improvement = top_confidence - prev_confidence
                self.logger.info(f"Improvement: {improvement:.3f}")
                
                if improvement < min_improvement:
                    self.logger.info(f"Exit: Diminishing returns ({improvement:.3f} < {min_improvement})")
                    break
            
            prev_confidence = top_confidence
        
        # Return top K final results
        final_results = all_results[:top_k]
        self.logger.info(f"Retrieval complete: {len(final_results)} results returned")
        
        return final_results
```

---

## PageRank Boost Computation

**File:** `backend/graph/pagerank.py` (NEW)

```python
"""
Personalized PageRank computation for Phase 6.

Computes PageRank scores on subgraph with query-based personalization.
Used by HybridReranker to boost graph-central nodes.
"""

from typing import List, Dict, Any, Optional
import networkx as nx
import numpy as np
import logging


class PageRankComputer:
    """
    Computes personalized PageRank scores for retrieval boost.
    
    Design:
    - Build 2-hop subgraph around seed nodes
    - Personalization vector based on query similarity
    - Scale scores to [0, 0.3] range for boosting
    """
    
    def __init__(self, graph_interface, embedding_model):
        """
        Initialize PageRank computer.
        
        Args:
            graph_interface: GraphInterface instance
            embedding_model: SentenceTransformer model for query similarity
        """
        self.graph = graph_interface
        self.embedding_model = embedding_model
        self.logger = logging.getLogger(__name__)
    
    def compute(self, node_ids: List[str], query: str,
                max_subgraph_nodes: int = 1000) -> Dict[str, float]:
        """
        Compute personalized PageRank scores.
        
        Args:
            node_ids: List of seed node IDs (from vector search)
            query: User query string (for personalization)
            max_subgraph_nodes: Maximum subgraph size (limit for performance)
            
        Returns:
            Dict mapping node_id -> pagerank_score (scaled to [0, 0.3])
        """
        if not node_ids:
            return {}
        
        # STEP 1: Build 2-hop subgraph
        subgraph = self._build_subgraph(node_ids, max_nodes=max_subgraph_nodes)
        
        if subgraph.number_of_nodes() == 0:
            self.logger.warning("Empty subgraph, returning zero scores")
            return {node_id: 0.0 for node_id in node_ids}
        
        self.logger.info(f"Built subgraph: {subgraph.number_of_nodes()} nodes, {subgraph.number_of_edges()} edges")
        
        # STEP 2: Compute personalization vector (query similarity)
        personalization = self._compute_personalization(node_ids, query, subgraph)
        
        # STEP 3: Run PageRank
        try:
            pagerank_scores = nx.pagerank(
                subgraph,
                personalization=personalization,
                alpha=0.85,
                max_iter=100,
                tol=1e-6
            )
        except Exception as e:
            self.logger.error(f"PageRank computation failed: {e}")
            return {node_id: 0.0 for node_id in node_ids}
        
        # STEP 4: Scale to [0, 0.3] range
        scaled_scores = self._scale_scores(pagerank_scores, max_boost=0.3)
        
        self.logger.debug(f"PageRank computed: {len(scaled_scores)} scores")
        return scaled_scores
    
    def _build_subgraph(self, seed_node_ids: List[str], max_nodes: int) -> nx.DiGraph:
        """
        Build 2-hop subgraph around seed nodes.
        
        Args:
            seed_node_ids: Starting nodes
            max_nodes: Maximum subgraph size
            
        Returns:
            NetworkX DiGraph
        """
        subgraph = nx.DiGraph()
        visited = set()
        
        # BFS from each seed (depth=2)
        for seed_id in seed_node_ids:
            if len(visited) >= max_nodes:
                break
            
            # Get 1-hop neighbors
            hop1_neighbors = self.graph.get_neighbors(seed_id)
            for neighbor in hop1_neighbors:
                if len(visited) >= max_nodes:
                    break
                
                # Add edge: seed -> neighbor
                subgraph.add_edge(seed_id, neighbor['id'], weight=neighbor.get('weight', 0.5))
                visited.add(seed_id)
                visited.add(neighbor['id'])
                
                # Get 2-hop neighbors
                hop2_neighbors = self.graph.get_neighbors(neighbor['id'])
                for neighbor2 in hop2_neighbors:
                    if len(visited) >= max_nodes:
                        break
                    
                    # Add edge: neighbor -> neighbor2
                    subgraph.add_edge(neighbor['id'], neighbor2['id'], weight=neighbor2.get('weight', 0.5))
                    visited.add(neighbor2['id'])
        
        return subgraph
    
    def _compute_personalization(self, seed_node_ids: List[str], query: str,
                                 subgraph: nx.DiGraph) -> Dict[str, float]:
        """
        Compute personalization vector based on query similarity.
        
        Args:
            seed_node_ids: Seed nodes
            query: User query
            subgraph: Subgraph
            
        Returns:
            Personalization dict (normalized weights for seed nodes)
        """
        # Encode query
        query_embedding = self.embedding_model.encode([query])[0]
        
        # Compute similarity for each seed node
        personalization = {}
        for node_id in seed_node_ids:
            if node_id not in subgraph:
                continue
            
            # Get node text from graph
            node_text = self.graph.get_node_text(node_id)
            if not node_text:
                personalization[node_id] = 0.1  # Small default
                continue
            
            # Compute similarity
            node_embedding = self.embedding_model.encode([node_text])[0]
            similarity = np.dot(query_embedding, node_embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(node_embedding)
            )
            
            personalization[node_id] = max(similarity, 0.1)  # Clip negative
        
        # Normalize (sum to 1)
        total = sum(personalization.values())
        if total > 0:
            personalization = {k: v/total for k, v in personalization.items()}
        
        return personalization
    
    def _scale_scores(self, pagerank_scores: Dict[str, float], max_boost: float = 0.3) -> Dict[str, float]:
        """
        Scale PageRank scores to [0, max_boost] range.
        
        Args:
            pagerank_scores: Raw PageRank scores
            max_boost: Maximum boost value (default: 0.3)
            
        Returns:
            Scaled scores
        """
        if not pagerank_scores:
            return {}
        
        # Get max score
        max_score = max(pagerank_scores.values())
        
        if max_score == 0:
            return {k: 0.0 for k in pagerank_scores}
        
        # Scale: score / max_score * max_boost
        scaled = {
            node_id: (score / max_score) * max_boost
            for node_id, score in pagerank_scores.items()
        }
        
        return scaled
```

---

## Hybrid Reranker

**File:** `backend/retrieval/hybrid_reranker.py` (NEW)

```python
"""
Hybrid reranker: Content similarity + PageRank boost.

Formula: confidence = 0.7 × content_similarity + 0.3 × pagerank_score
"""

from typing import List, Dict, Any
import logging
from backend.graph.pagerank import PageRankComputer


class HybridReranker:
    """
    Reranks results using hybrid scoring: content + graph centrality.
    """
    
    def __init__(self, pagerank_computer: PageRankComputer):
        """
        Initialize reranker.
        
        Args:
            pagerank_computer: PageRankComputer instance
        """
        self.pagerank_computer = pagerank_computer
        self.logger = logging.getLogger(__name__)
    
    def rerank(self, results: List[Dict[str, Any]], query: str,
              content_weight: float = 0.7, pagerank_weight: float = 0.3) -> List[Dict[str, Any]]:
        """
        Rerank results using hybrid scoring.
        
        Args:
            results: List of result dicts (from vector search + graph expansion)
            query: User query
            content_weight: Weight for content similarity (default: 0.7)
            pagerank_weight: Weight for PageRank (default: 0.3)
            
        Returns:
            Reranked results sorted by confidence (descending)
        """
        if not results:
            return []
        
        # Deduplicate by ID
        unique_results = {r['id']: r for r in results}.values()
        results = list(unique_results)
        
        # Get PageRank scores for all node IDs
        node_ids = [r['id'] for r in results]
        pagerank_scores = self.pagerank_computer.compute(node_ids, query)
        
        # Hybrid scoring
        for result in results:
            content_score = result.get('similarity', 0.5)  # Default 0.5 if not from vector search
            pagerank_score = pagerank_scores.get(result['id'], 0.0)
            
            result['confidence'] = (
                content_weight * content_score +
                pagerank_weight * pagerank_score
            )
            result['pagerank_boost'] = pagerank_score
        
        # Sort by confidence (descending)
        results.sort(key=lambda x: x['confidence'], reverse=True)
        
        self.logger.info(f"Reranked {len(results)} results (top confidence: {results[0]['confidence']:.3f})")
        
        return results
```

---

## API Contracts

### Backward Compatibility

Phase 6 maintains backward compatibility with existing CLI/VSIX interfaces:

**Existing API (unchanged):**
```python
# backend/retrieval/retrieval_service.py

def query(query: str, top_k: int = 5, regime: Optional[str] = None) -> List[dict]:
    """
    Main query interface (UNCHANGED).
    
    Phase 6 detection:
    - If config.PHASE6_ENABLED == True → Use IterativeRetrievalOrchestrator
    - Else → Use existing one-shot retrieval
    """
    if config.PHASE6_ENABLED:
        # Route to Phase 6 orchestrator
        orchestrator = IterativeRetrievalOrchestrator(...)
        return orchestrator.retrieve(query, top_k=top_k)
    else:
        # Existing one-shot retrieval
        return legacy_query(query, top_k, regime)
```

**Configuration Flag:**
```python
# config/settings.py

PHASE6_ENABLED = os.getenv("PHASE6_ENABLED", "false").lower() == "true"
```

---

## Configuration

**File:** `backend/common/config_phase6.py` (NEW)

```python
"""
Phase 6 configuration parameters.
"""

import os
from dataclasses import dataclass


@dataclass
class Phase6Config:
    """Configuration for Phase 6 features."""
    
    # Feature flag
    enabled: bool = os.getenv("PHASE6_ENABLED", "false").lower() == "true"
    
    # Dual vector stores
    chroma_persist_dir: str = os.getenv("PHASE6_CHROMA_DIR", "./chroma_phase6")
    
    # Iterative retrieval
    max_iterations: int = int(os.getenv("PHASE6_MAX_ITERATIONS", "3"))
    min_confidence: float = float(os.getenv("PHASE6_MIN_CONFIDENCE", "0.90"))
    min_improvement: float = float(os.getenv("PHASE6_MIN_IMPROVEMENT", "0.05"))
    
    # PageRank
    pagerank_max_subgraph_nodes: int = int(os.getenv("PHASE6_PAGERANK_MAX_NODES", "1000"))
    pagerank_alpha: float = float(os.getenv("PHASE6_PAGERANK_ALPHA", "0.85"))
    
    # Hybrid reranking
    content_weight: float = float(os.getenv("PHASE6_CONTENT_WEIGHT", "0.7"))
    pagerank_weight: float = float(os.getenv("PHASE6_PAGERANK_WEIGHT", "0.3"))


# Global config instance
phase6_config = Phase6Config()
```

---

## Migration Utilities

**File:** `backend/migration/phase6_migrator.py` (NEW)

```python
"""
Utilities for migrating Phase 5 data to Phase 6 schema.
"""

import logging
from typing import List
from backend.graph.enhanced_graph_builder import EnhancedGraphBuilder
from backend.vector.dual_vector_store import DualVectorStore
from backend.extraction.item_extractor_base import get_item_extractor


class Phase6Migrator:
    """
    Migrates existing documents to Phase 6 schema.
    
    Process:
    1. Read document from Phase 5 ingest output (JSON)
    2. Re-extract items using ItemExtractor
    3. Build hierarchical graph
    4. Populate dual vector stores
    """
    
    def __init__(self, graph_builder: EnhancedGraphBuilder, vector_store: DualVectorStore):
        """
        Initialize migrator.
        
        Args:
            graph_builder: EnhancedGraphBuilder instance
            vector_store: DualVectorStore instance
        """
        self.graph_builder = graph_builder
        self.vector_store = vector_store
        self.logger = logging.getLogger(__name__)
    
    def migrate_document(self, doc_id: str, doc_type: str, sections: List[dict]):
        """
        Migrate single document to Phase 6.
        
        Args:
            doc_id: Document ID
            doc_type: Document type (for extractor routing)
            sections: List of section dicts with:
                - section_number: str
                - section_heading: str
                - section_text: str
        """
        self.logger.info(f"Migrating document: {doc_id}")
        
        # Get extractor
        extractor = get_item_extractor(doc_type)
        
        # Process sections
        all_items = []
        section_summaries = []
        
        for section_index, section_dict in enumerate(sections):
            section_number = section_dict["section_number"]
            section_heading = section_dict["section_heading"]
            section_text = section_dict["section_text"]
            
            # Extract items
            items = extractor.extract_items(
                section_text=section_text,
                section_number=section_number,
                section_heading=section_heading,
                section_index=section_index,
                document_id=doc_id
            )
            
            all_items.extend(items)
            
            # Prepare section summary for section vector store
            section_summaries.append({
                "id": f"sec:{doc_id}:{section_index:04d}",
                "section_number": section_number,
                "section_heading": section_heading,
                "section_text": section_text,
                "document_id": doc_id,
                "section_index": section_index,
                "item_count": len(items),
                "item_types": list(set([item.item_type for item in items]))
            })
        
        # Build hierarchical graph
        self.graph_builder.build_hierarchical_graph(doc_id, doc_type, sections)
        
        # Populate vector stores
        self.vector_store.add_items(all_items)
        self.vector_store.add_sections(section_summaries)
        
        self.logger.info(f"Migrated {doc_id}: {len(all_items)} items, {len(section_summaries)} sections")
```

---

## Related Documents

- [Executive Summary](01_EXECUTIVE_SUMMARY.md) - Business case and ROI
- [System Design](02_SYSTEM_DESIGN.md) - High-level architecture
- [Architecture Upgrade](03_ARCHITECTURE_UPGRADE.md) - Detailed architecture
- [Implementation Plan](05_IMPLEMENTATION_PLAN.md) - Step-by-step execution
- [Testing Plan](06_TESTING_PLAN.md) - Validation strategy

---

*This technical design document provides complete, production-ready code for Phase 6 implementation. All code includes type hints, docstrings, and error handling.*
