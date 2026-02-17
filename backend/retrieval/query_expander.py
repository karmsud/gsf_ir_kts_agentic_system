"""Query Expander — 3-Tier Regime-Aware Synonym Expansion (Option Prod).

Expands query terms using a three-tier synonym system:

1. ``synonyms.json``            — human-approved, always used  (highest priority)
2. ``synonyms_learned.json``    — auto-generated high-confidence, used at retrieval
3. ``synonyms_candidates.json`` — pending review, NOT used

Static synonyms (tier 1) always override learned synonyms (tier 2).
Gated behind ``config.query_expansion_enabled``.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


_DEFAULT_DICT_PATH = Path(__file__).resolve().parent.parent / "data" / "synonyms.json"


class QueryExpander:
    """3-tier regime-aware query expansion."""

    def __init__(
        self,
        dict_path: str | Path | None = None,
        kb_path: str | Path | None = None,
    ):
        # Tier 1: Static (human-approved) synonyms — flat dict
        path = Path(dict_path) if dict_path else _DEFAULT_DICT_PATH
        if path.exists():
            self._static: dict[str, list[str]] = json.loads(
                path.read_text(encoding="utf-8")
            )
        else:
            self._static = {}

        # Tier 2: Learned synonyms — regime-aware dict
        self._learned: dict[str, dict[str, dict]] = {}
        kb = Path(kb_path) if kb_path else Path(os.environ.get("KTS_KB_PATH", ".kts"))
        learned_path = kb / "synonyms_learned.json"
        if learned_path.exists():
            try:
                self._learned = json.loads(
                    learned_path.read_text(encoding="utf-8")
                )
            except Exception:
                self._learned = {}

    @property
    def dictionary(self) -> dict[str, list[str]]:
        """Return the static synonym dictionary (backward compat)."""
        return dict(self._static)

    def expand(
        self,
        query: str,
        max_expansions: int = 3,
        doc_type: Optional[str] = None,
        use_ner_entities: bool = False,
    ) -> str:
        """Return the query with synonym expansions appended.

        Each matched term contributes up to *max_expansions* synonyms.
        The original query is preserved; expansions are appended after
        ``" OR "`` to broaden the search without losing precision.

        Parameters
        ----------
        query : str
            The user query.
        max_expansions : int
            Max synonyms per matched term.
        doc_type : str | None
            If provided, also consult learned synonyms for this regime.
        use_ner_entities : bool
            If True, extract entities from query and include them as expansions.
        """
        tokens = re.findall(r"\b[a-z]{3,}\b", query.lower())
        expansions: list[str] = []
        seen: set[str] = set(tokens)

        # Tier 0: NER-extracted entities (if enabled)
        if use_ner_entities:
            try:
                from backend.ingestion.ner_extractor import extract_entities_and_keyphrases
                import os
                
                # Only use NER if model is available
                ner_enabled = bool(os.environ.get("KTS_SPACY_MODEL_PATH"))
                if ner_enabled:
                    result = extract_entities_and_keyphrases(query, max_keyphrases=5)
                    
                    # Add entity text as high-priority expansions
                    for entity in result.entities[:max_expansions]:
                        entity_lower = entity.text.lower()
                        if entity_lower not in seen and len(entity_lower) >= 3:
                            expansions.insert(0, entity_lower)  # Insert at front (highest priority)
                            seen.add(entity_lower)
                    
                    # Add keyphrases (lower priority than entities)
                    for kp in result.keyphrases[:max_expansions]:
                        kp_lower = kp.text.lower()
                        if kp_lower not in seen and len(kp_lower) >= 3:
                            expansions.append(kp_lower)
                            seen.add(kp_lower)
            except Exception:
                pass  # Graceful degradation if NER fails

        # Tier 1: Static synonyms (always, highest priority)
        for token in tokens:
            syns = self._static.get(token, [])
            for syn in syns[:max_expansions]:
                syn_lower = syn.lower()
                if syn_lower not in seen:
                    expansions.append(syn_lower)
                    seen.add(syn_lower)

        # Tier 2: Learned synonyms (if doc_type known)
        if doc_type and doc_type in self._learned:
            regime_learned = self._learned[doc_type]
            for token in tokens:
                if token in regime_learned:
                    syns = regime_learned[token].get("synonyms", [])
                    for syn in syns[:max_expansions]:
                        syn_lower = syn.lower()
                        if syn_lower not in seen:
                            expansions.append(syn_lower)
                            seen.add(syn_lower)

            # Also check multi-word matches from learned synonyms
            query_lower = query.lower()
            for term, record in regime_learned.items():
                if " " in term and term in query_lower:
                    syns = record.get("synonyms", [])
                    for syn in syns[:max_expansions]:
                        syn_lower = syn.lower()
                        if syn_lower not in seen:
                            expansions.append(syn_lower)
                            seen.add(syn_lower)

        if expansions:
            return f"{query} OR {' '.join(expansions)}"
        return query

    def get_synonyms(self, term: str) -> list[str]:
        """Return synonyms for a single term, or empty list."""
        return list(self._static.get(term.lower(), []))
