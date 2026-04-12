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

from __future__ import annotations

import re
from typing import Any, Dict, List

from backend.extraction.item_extractor_base import Item, ItemExtractor


class ResearchItemExtractor(ItemExtractor):
    """
    Research paper item extractor.

    Identifies mathematical and scientific semantic items using LaTeX-like
    patterns and academic writing conventions.
    """

    def __init__(self) -> None:
        super().__init__()

        self.theorem_patterns = [
            r"^Theorem\s+\d+",
            r"^Proposition\s+\d+",
            r"^Corollary\s+\d+",
            r"\\begin\{theorem\}",
        ]

        self.proof_patterns = [
            r"^Proof[.:]",
            r"^Proof\s+of\s+Theorem",
            r"^Proof\s+sketch",
            r"\\begin\{proof\}",
        ]

        self.lemma_patterns = [
            r"^Lemma\s+\d+",
            r"^Supporting\s+Lemma",
            r"\\begin\{lemma\}",
        ]

        self.algorithm_patterns = [
            r"^Algorithm\s+\d+",
            r"^Procedure:",
            r"^Input:",
            r"^Output:",
            r"\\begin\{algorithm\}",
        ]

        self.observation_patterns = [
            r"^We\s+observe",
            r"^Note\s+that",
            r"^It\s+can\s+be\s+seen",
            r"^Observe\s+that",
        ]

        self.hypothesis_patterns = [
            r"^We\s+hypothesize",
            r"^We\s+conjecture",
            r"^Hypothesis\s+\d+",
            r"^Conjecture\s+\d+",
        ]

    def get_supported_types(self) -> List[str]:
        return [
            "Theorem",
            "Proof",
            "Lemma",
            "Algorithm",
            "Observation",
            "Hypothesis",
        ]

    def extract_items(
        self,
        section_text: str,
        section_number: str,
        section_heading: str,
        section_index: int,
        document_id: str,
    ) -> List[Item]:
        """Extract research items from section."""
        if not section_text or len(section_text.strip()) < 10:
            return []

        blocks = re.split(r"\n\s*\n", section_text)
        items: list[Item] = []

        for item_index, block in enumerate(blocks):
            block = block.strip()
            if len(block) < 10:
                continue

            item_type = self.classify_item_type(block)
            metadata = self._extract_research_metadata(block)
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
            f"Extracted {len(items)} research items from section {section_number}"
        )
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
        if any(re.search(p, text, re.IGNORECASE) for p in self.theorem_patterns):
            return "Theorem"

        if any(re.search(p, text, re.IGNORECASE) for p in self.proof_patterns):
            return "Proof"

        if any(re.search(p, text, re.IGNORECASE) for p in self.lemma_patterns):
            return "Lemma"

        if any(re.search(p, text, re.IGNORECASE) for p in self.algorithm_patterns):
            return "Algorithm"

        if any(re.search(p, text, re.IGNORECASE) for p in self.hypothesis_patterns):
            return "Hypothesis"

        if any(re.search(p, text, re.IGNORECASE) for p in self.observation_patterns):
            return "Observation"

        return "Observation"  # Fallback

    def _extract_research_metadata(self, text: str) -> Dict[str, Any]:
        """
        Extract research-specific metadata.

        Returns:
            metadata with keys: equations, citations, variables, numbers
        """
        metadata: Dict[str, Any] = {
            "equations": [],
            "citations": [],
            "variables": [],
            "numbers": [],
        }

        # Extract numbered statements (Theorem 5, Lemma 2)
        numbers = re.findall(
            r"(?:Theorem|Lemma|Proposition|Corollary|Algorithm)\s+(\d+)", text
        )
        metadata["numbers"] = list(set(numbers))

        # Extract citations [1], [Smith et al., 2020]
        citations = re.findall(r"\[([^\]]+)\]", text)
        metadata["citations"] = [c for c in citations if len(c) < 50]

        # Extract mathematical variables (single letters)
        variables = re.findall(r"\b([a-zA-Z])\b", text)
        common_words = {"a", "i", "I", "A"}
        metadata["variables"] = list(
            {v for v in variables if v not in common_words}
        )[:20]

        # Extract equations (LaTeX-style)
        equations = re.findall(r"\$\$(.+?)\$\$", text)
        equations += re.findall(
            r"\\begin\{equation\}(.+?)\\end\{equation\}", text, re.DOTALL
        )
        metadata["equations"] = [eq.strip() for eq in equations]

        return metadata
