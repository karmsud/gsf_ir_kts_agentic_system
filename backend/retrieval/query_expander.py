"""Query Expander — Multi-Query Retrieval with 3-Tier Synonym Expansion.

Features:
1. 3-Tier regime-aware synonym expansion:
   - Tier 1: ``synonyms.json`` (human-approved, always used)
   - Tier 2: ``synonyms_learned.json`` (auto-learned, high-confidence)
   - Tier 3: NER-extracted entities and keyphrases

2. Multi-Query Generation:
   - Generates semantic variations of queries for improved recall
   - Domain-specific reformulations for financial/legal content
   - Question reformulation and keyword extraction

3. Reciprocal Rank Fusion (RRF):
   - Merges results from multiple query variations
   - Industry-standard fusion algorithm
   - Robust to score normalization issues
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


_DEFAULT_DICT_PATH = Path(__file__).resolve().parent.parent / "data" / "synonyms.json"


class QueryExpander:
    """3-tier regime-aware query expansion with multi-query generation."""

    # Domain-specific synonyms for multi-query generation
    DOMAIN_SYNONYMS = {
        "reporting requirements": [
            "statement requirements",
            "disclosure obligations",
            "periodic reports",
        ],
        "certificate holder": [
            "certificateholder",
            "holder of certificates",
            "beneficial owner",
        ],
        "servicer": [
            "master servicer",
            "loan servicer",
            "servicing agent",
        ],
        "distribution": [
            "payment",
            "remittance",
            "pass-through payment",
        ],
        "pool assets": [
            "mortgage loans",
            "collateral pool",
            "underlying assets",
        ],
        "trustee": [
            "indenture trustee",
            "trust administrator",
        ],
    }

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

    # ── Multi-Query Generation ────────────────────────────────────

    def generate_query_variations(
        self,
        query: str,
        max_variations: int = 3,
        doc_type: Optional[str] = None,
    ) -> List[str]:
        """
        Generate semantic variations of the query for multi-query retrieval.
        
        This enables improved recall by searching with multiple perspectives
        of the same information need, then merging results with RRF.
        
        Args:
            query: Original user query
            max_variations: Maximum number of variations to generate
            doc_type: Document type for regime-aware expansion
        
        Returns:
            List of query variations including the original
        """
        variations = [query]  # Always include original
        
        # Strategy 1: Domain synonym expansion
        synonym_variations = self._expand_with_domain_synonyms(query)
        variations.extend(synonym_variations[:max_variations])
        
        # Strategy 2: Question reformulation
        if self._is_question(query):
            reformulations = self._reformulate_question(query)
            variations.extend(reformulations[:max(1, max_variations - len(variations) + 1)])
        
        # Strategy 3: Keyword extraction (focuses on key entities)
        keyword_query = self._extract_keywords(query)
        if keyword_query and keyword_query not in variations:
            variations.append(keyword_query)
        
        # Deduplicate while preserving order
        seen = set()
        unique_variations = []
        for v in variations:
            v_normalized = v.lower().strip()
            if v_normalized not in seen:
                seen.add(v_normalized)
                unique_variations.append(v)
        
        return unique_variations[:max_variations + 1]
    
    def _expand_with_domain_synonyms(self, query: str) -> List[str]:
        """Expand query using domain-specific synonyms."""
        variations = []
        query_lower = query.lower()
        
        for term, synonyms in self.DOMAIN_SYNONYMS.items():
            if term in query_lower:
                for synonym in synonyms:
                    variation = re.sub(
                        re.escape(term),
                        synonym,
                        query_lower,
                        flags=re.IGNORECASE
                    )
                    if variation != query_lower:
                        variations.append(variation)
        
        return variations
    
    def _is_question(self, query: str) -> bool:
        """Check if query is a question."""
        question_words = ["what", "who", "where", "when", "why", "how", "which", 
                         "describe", "list", "explain", "show"]
        query_lower = query.lower().strip()
        return (
            query_lower.startswith(tuple(question_words)) or
            query_lower.endswith("?")
        )
    
    def _reformulate_question(self, query: str) -> List[str]:
        """Reformulate question in different ways for better matching."""
        reformulations = []
        query_lower = query.lower().strip()
        base = query_lower.rstrip("?")
        
        # "What are the X?" → "requirements for X", "X definition"
        if query_lower.startswith("what are the"):
            topic = base.replace("what are the", "").strip()
            reformulations.append(f"requirements for {topic}")
            reformulations.append(f"{topic} definition")
        
        elif query_lower.startswith("what is"):
            topic = base.replace("what is", "").strip()
            reformulations.append(f"{topic} definition")
            reformulations.append(f"information about {topic}")
        
        elif query_lower.startswith("how to"):
            action = base.replace("how to", "").strip()
            reformulations.append(f"procedure for {action}")
            reformulations.append(f"steps to {action}")
        
        elif query_lower.startswith("list all") or query_lower.startswith("list the"):
            items = re.sub(r"^list (all|the)\s+", "", base)
            reformulations.append(f"complete {items}")
            reformulations.append(f"all {items}")
        
        return reformulations
    
    def _extract_keywords(self, query: str) -> str:
        """Extract key terms from query, removing stop words and question words."""
        # Remove question words
        question_words = r"\b(what|who|where|when|why|how|which|describe|list|explain|show|tell)\b"
        cleaned = re.sub(question_words, "", query, flags=re.IGNORECASE)
        
        # Remove articles and common connectors
        articles = r"\b(the|a|an|are|is|was|were|be|been|have|has|had|do|does|did|to|of|for|in|on|at|by|with|from|also|called|as)\b"
        cleaned = re.sub(articles, " ", cleaned, flags=re.IGNORECASE)
        
        # Remove punctuation and extra whitespace
        cleaned = re.sub(r"[?.,;:]", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        
        return cleaned if cleaned else query


# ── Reciprocal Rank Fusion ────────────────────────────────────────

def reciprocal_rank_fusion(
    result_lists: List[List[Dict[str, Any]]],
    k: int = 60,
    chunk_id_key: str = "chunk_id",
    score_key: str = "score",
) -> List[Dict[str, Any]]:
    """
    Merge multiple ranked result lists using Reciprocal Rank Fusion (RRF).
    
    RRF is an industry-standard ranking fusion method that combines results
    from multiple searches without requiring normalized scores. It consistently
    outperforms simple score averaging.
    
    Formula: RRF_score(d) = Σ(1 / (k + rank(d)))
    
    Args:
        result_lists: List of result lists from different queries.
                     Each result must have chunk_id and score keys.
        k: RRF constant (typically 60). Lower values = more emphasis on top ranks.
        chunk_id_key: Key for unique document/chunk identifier
        score_key: Key for relevance score (preserved but not used in fusion)
    
    Returns:
        Merged and re-ranked result list with rrf_score and fusion_rank fields
    
    Reference:
        Cormack, G. V., Clarke, C. L., & Buettcher, S. (2009).
        "Reciprocal rank fusion outperforms condorcet and individual rank learning."
        SIGIR 2009.
    """
    if not result_lists:
        return []
    
    from typing import Tuple
    
    # Track RRF scores for each document
    rrf_scores: Dict[str, Tuple[float, Dict[str, Any]]] = {}
    
    for result_list in result_lists:
        for rank, result in enumerate(result_list, start=1):
            chunk_id = result.get(chunk_id_key)
            if not chunk_id:
                continue
            
            # RRF formula: 1 / (k + rank)
            rrf_contribution = 1.0 / (k + rank)
            
            if chunk_id in rrf_scores:
                # Accumulate RRF scores from multiple lists
                rrf_scores[chunk_id] = (
                    rrf_scores[chunk_id][0] + rrf_contribution,
                    result  # Keep one copy of the result dict
                )
            else:
                rrf_scores[chunk_id] = (rrf_contribution, result)
    
    # Sort by RRF score descending
    sorted_results = sorted(
        rrf_scores.items(),
        key=lambda x: x[1][0],
        reverse=True
    )
    
    # Rebuild result list with RRF metadata
    merged_results = []
    for chunk_id, (rrf_score, original_result) in sorted_results:
        merged_result = original_result.copy()
        merged_result["rrf_score"] = rrf_score
        merged_result["fusion_rank"] = len(merged_results) + 1
        merged_result["fusion_method"] = "rrf"
        merged_results.append(merged_result)
    
    return merged_results
