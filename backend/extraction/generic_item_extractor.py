"""Generic item extractor (paragraph-level fallback)."""

from __future__ import annotations

from typing import List

from backend.extraction.item_extractor_base import Item, ItemExtractor


class GenericItemExtractor(ItemExtractor):
    """
    Generic fallback extractor for unsupported document types.

    Extracts paragraph-level items without semantic classification.
    """

    def __init__(self) -> None:
        super().__init__()

    def get_supported_types(self) -> List[str]:
        return ["Paragraph"]

    def extract_items(
        self,
        section_text: str,
        section_number: str,
        section_heading: str,
        section_index: int,
        document_id: str,
    ) -> List[Item]:
        """Extract paragraph-level items."""
        if not section_text or len(section_text.strip()) < 10:
            return []

        paragraphs = section_text.split("\n\n")
        items: list[Item] = []

        for item_index, para in enumerate(paragraphs):
            para = para.strip()
            if len(para) < 10:
                continue

            item_id = self._generate_item_id(
                document_id, section_index, "paragraph", item_index, para
            )

            item = Item(
                id=item_id,
                item_type="Paragraph",
                text=para,
                document_id=document_id,
                section_number=section_number,
                section_heading=section_heading,
                section_index=section_index,
                item_index=item_index,
                metadata={},
            )
            items.append(item)

        return items

    def classify_item_type(self, text: str) -> str:
        return "Paragraph"
