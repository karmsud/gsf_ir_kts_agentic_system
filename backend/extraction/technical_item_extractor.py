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

from __future__ import annotations

import re
from typing import Any, Dict, List

from backend.extraction.item_extractor_base import Item, ItemExtractor


class TechnicalItemExtractor(ItemExtractor):
    """
    Technical document item extractor.

    Identifies technical semantic items using RFC 2119 keywords (MUST, SHOULD),
    procedural markers, and formatting conventions from technical writing.
    """

    def __init__(self) -> None:
        super().__init__()

        # RFC 2119 requirement patterns
        self.requirement_patterns = [
            r"\bMUST\b",
            r"\bREQUIRED\b",
            r"\bSHALL\b",
            r"\bsystem\s+must\b",
            r"\b(?:is|are)\s+required\b",
        ]

        # Procedural step patterns
        self.procedure_patterns = [
            r"^Step\s+\d+",
            r"^To\s+\w+",
            r"^Follow\s+these",
            r"^\d+\.\s+",
        ]

        # Configuration patterns
        self.configuration_patterns = [
            r"^Set\s+\w+",
            r"^Configure\s+\w+",
            r"^\w+\s*[:=]\s*\S",
        ]

        # Warning/caution patterns
        self.warning_patterns = [
            r"^WARNING:",
            r"^CAUTION:",
            r"^Important:",
            r"^DANGER:",
        ]

        # Note/tip patterns
        self.note_patterns = [
            r"^Note:",
            r"^Tip:",
            r"^Information:",
            r"^Remember:",
        ]

        # Example patterns
        self.example_patterns = [
            r"^Example:",
            r"^Usage:",
            r"^```",
            r"^Sample:",
        ]

    def get_supported_types(self) -> List[str]:
        return [
            "Requirement",
            "Procedure",
            "Configuration",
            "Warning",
            "Note",
            "Example",
        ]

    def extract_items(
        self,
        section_text: str,
        section_number: str,
        section_heading: str,
        section_index: int,
        document_id: str,
    ) -> List[Item]:
        """Extract technical items from section."""
        if not section_text or len(section_text.strip()) < 10:
            return []

        # Technical docs often use block formatting
        blocks = re.split(r"\n\s*\n", section_text)
        items: list[Item] = []

        for item_index, block in enumerate(blocks):
            block = block.strip()
            if len(block) < 10:
                continue

            item_type = self.classify_item_type(block)
            metadata = self._extract_technical_metadata(block)
            item_id = self._generate_item_id(
                document_id, section_index, item_type, item_index, block
            )

            item = Item(
                id=item_id,
                item_type=item_type,
                text=block,
                document_id=document_id,
                section_number=section_number,
                section_heading=section_heading,
                section_index=section_index,
                item_index=item_index,
                metadata=metadata,
            )
            items.append(item)

        self.logger.debug(
            f"Extracted {len(items)} technical items from section {section_number}"
        )
        return items

    def classify_item_type(self, text: str) -> str:
        """
        Classify technical item type.

        Priority order:
        1. Warning (highest priority — safety)
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
        if re.search(r"\b(?:must|should|shall|will|can)\b", text, re.IGNORECASE):
            return "Requirement"

        return "Note"

    def _extract_technical_metadata(self, text: str) -> Dict[str, Any]:
        """
        Extract technical-specific metadata.

        Returns:
            metadata with keys: parameters, commands, files, urls
        """
        metadata: Dict[str, Any] = {
            "parameters": [],
            "commands": [],
            "files": [],
            "urls": [],
        }

        # Extract parameters (key: value or key=value)
        params = re.findall(r"(\w+)\s*[:=]\s*([^\n,;]+)", text)
        metadata["parameters"] = [
            {"name": p[0], "value": p[1].strip()} for p in params
        ]

        # Extract commands ($ or > prefix or backticked)
        commands = re.findall(r"[$>]\s*(.+?)(?:\n|$)", text)
        commands += re.findall(r"`([^`]+)`", text)
        metadata["commands"] = list(
            {c.strip() for c in commands if len(c.strip()) > 3}
        )

        # Extract file paths (/path/to/file or C:\path\to\file)
        files = re.findall(r"(?:[A-Z]:\\|/)[\w/\\.-]+", text)
        metadata["files"] = list(set(files))

        # Extract URLs
        urls = re.findall(r"https?://[^\s<>\"']+", text)
        metadata["urls"] = list(set(urls))

        return metadata
