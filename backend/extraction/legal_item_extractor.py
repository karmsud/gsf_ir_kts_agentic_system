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

from __future__ import annotations

import re
from typing import Any, Dict, List

from backend.extraction.item_extractor_base import Item, ItemExtractor


class LegalItemExtractor(ItemExtractor):
    """
    Legal document item extractor.

    Identifies legal semantic items using modal verb patterns and
    legal conventions. Extracts rich metadata including actors (parties),
    modal verbs, and defined term references.
    """

    def __init__(self) -> None:
        super().__init__()

        # Legal modal verb patterns
        self.obligation_patterns = [
            r"\bshall\b",
            r"\bmust\b",
            r"\b(?:is|are)\s+required\s+to\b",
            r"\b(?:is|are)\s+obligated\s+to\b",
        ]

        self.prohibition_patterns = [
            r"\bshall\s+not\b",
            r"\bmust\s+not\b",
            r"\bmay\s+not\b",
            r"\b(?:is|are)\s+prohibited\s+from\b",
        ]

        self.right_patterns = [
            r"\bmay\b",
            r"\b(?:is|are)\s+permitted\s+to\b",
            r"\b(?:is|are)\s+authorized\s+to\b",
            r"\b(?:is|are)\s+entitled\s+to\b",
        ]

        self.definition_patterns = [
            r"\bmeans\b",
            r"\bdefined\s+as\b",
            r"\brefers\s+to\b",
            r'"\s*means\s+',
            r"\bshall\s+mean\b",
            r"\bshall\s+have\s+the\s+meaning\b",
            r"\bhas\s+the\s+meaning\b",
            r"\bis\s+referred\s+to\s+as\b",
            r'"[^"]{2,60}"\s*:\s+',  # colon-based definitions: "Term": description
        ]

        self.condition_patterns = [
            r"^if\b",
            r"\bunless\b",
            r"\bprovided\s+that\b",
            r"\bsubject\s+to\b",
            r"\bin\s+the\s+event\b",
        ]

        # Legal actor patterns (parties common in contracts)
        self.actor_patterns = [
            r"\bTrustee\b",
            r"\bServicer\b",
            r"\bBorrower\b",
            r"\bLender\b",
            r"\bIssuer\b",
            r"\bInvestor\b",
            r"\bAgent\b",
            r"\bCustodian\b",
            r"\bDepositor\b",
            r"\bHolder\b",
        ]

    def get_supported_types(self) -> List[str]:
        return [
            "Obligation",
            "Prohibition",
            "Right",
            "Definition",
            "Condition",
            "Statement",
        ]

    def extract_items(
        self,
        section_text: str,
        section_number: str,
        section_heading: str,
        section_index: int,
        document_id: str,
    ) -> List[Item]:
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
        items: list[Item] = []

        for item_index, sentence in enumerate(sentences):
            item_type = self.classify_item_type(sentence)
            metadata = self._extract_legal_metadata(sentence)
            item_id = self._generate_item_id(
                document_id, section_index, item_type, item_index, sentence
            )

            item = Item(
                id=item_id,
                item_type=item_type,
                text=sentence,
                document_id=document_id,
                section_number=section_number,
                section_heading=section_heading,
                section_index=section_index,
                item_index=item_index,
                metadata=metadata,
            )
            items.append(item)

        self.logger.debug(
            f"Extracted {len(items)} items from section {section_number}"
        )
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
            metadata with keys: actors, verbs, defined_terms, section_refs
        """
        metadata: Dict[str, Any] = {
            "actors": [],
            "verbs": [],
            "defined_terms": [],
            "section_refs": [],
        }

        # Extract actors (parties)
        for pattern in self.actor_patterns:
            matches = re.findall(pattern, text)
            metadata["actors"].extend(matches)
        metadata["actors"] = list(set(metadata["actors"]))

        # Extract modal verbs
        modal_verbs = ["shall", "must", "may", "should", "will"]
        for verb in modal_verbs:
            if re.search(rf"\b{verb}\b", text, re.IGNORECASE):
                metadata["verbs"].append(verb)

        # Extract defined terms (quoted terms)
        defined_terms = re.findall(r'"([^"]+)"', text)
        metadata["defined_terms"] = defined_terms

        # Extract section references
        metadata["section_refs"] = self._extract_section_references(text)

        return metadata
