from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Tuple

import networkx as nx

from backend.common.models import AgentResult, Citation, SearchResult, TextChunk
from backend.common.doc_types import normalize_doc_type
from backend.graph import GraphQueries, GraphStore
from backend.retrieval.evidence_matcher import (
    EvidenceMatcher,
    ProvenanceError,
    enforce_provenance_contract,
)
from backend.retrieval.term_resolver import (
    TermResolver,
    extract_title_case_phrases,
    should_activate_resolver,
)
from backend.retrieval.query_expander import QueryExpander
from backend.retrieval.acronym_resolver import AcronymResolver
from backend.vector import VectorStore
from backend.retrieval.cross_encoder import rerank as cross_encoder_rerank
from .base_agent import AgentBase

logger = logging.getLogger(__name__)


class RetrievalService(AgentBase):
    agent_name = "retrieval-service"

    def __init__(self, config):
        super().__init__(config)
        self.vector_store = VectorStore(config.chroma_persist_dir)
        self.graph_store = GraphStore(config.graph_path)
        
        # Configurable ranking weights (tunable via environment or config)
        self.weights = {
            # Doc type base weights (higher = more important)
            "doc_type_troubleshoot": 1.0,
            "doc_type_sop": 1.0,
            "doc_type_user_guide": 1.0,
            "doc_type_training": 1.0,
            "doc_type_release_note": 1.0,
            "doc_type_reference": 1.0,
            
            # Feature boosts (multiplicative)
            "error_code_exact_match": 2.0,  # ERR-XXX-000 or HTTP 504 exact match
            "intent_doc_type_match": 1.7,   # Query intent matches doc_type (STABLE, safe for holdout)
            "title_term_match": 1.3,        # Query terms in doc_name/title
            "query_keyword_match": 1.2,     # Key terms from query in content
            "image_penalty": 0.95,           # De-boost image descriptions
        }

    def _extract_error_codes(self, text: str) -> List[str]:
        """Extract error codes from text (ERR-XXX-000, HTTP 504, AUTH401, etc.)"""
        patterns = [
            r'\bERR-[A-Z]+-\d{3}\b',     # ERR-UPL-013, ERR-PWD-007
            r'\bHTTP\s*\d{3}\b',         # HTTP 504, HTTP 401
            r'\b[A-Z]+\d{3,4}\b',        # AUTH401, XYZ999
        ]
        codes = []
        for pattern in patterns:
            codes.extend(re.findall(pattern, text, re.IGNORECASE))
        return [c.upper() for c in codes]
    
    def _detect_query_intent(self, query: str) -> Tuple[str, List[str]]:
        """
        Detect query intent and suggest prioritized doc_types.
        Returns: (intent, [expected_doc_types])
        """
        query_lower = query.lower()
        
        # Explicit doc_type mention in query (highest priority)
        if re.search(r'\btroubleshooting (guide|doc)', query_lower):
            return ("explicit_troubleshoot", ["TROUBLESHOOT", "SOP"])
        if re.search(r'\brelease\s+(note|doc|guide)', query_lower):
            return ("explicit_release", ["RELEASE_NOTE"])
        if re.search(r'\buser\s+guide', query_lower):
            return ("explicit_user_guide", ["USER_GUIDE"])
        
        # Legal/governing document queries (high priority)
        if re.search(r'\b(agreement|pooling|servicing|trust|indenture|psa|certificate\s*holder|trustee|obligor|servicer|depositor|beneficiary)\b', query_lower):
            return ("governing_doc", ["GOVERNING_DOC"])
        if re.search(r'\b(reporting\s+requirement|distribution\s+date|payment\s+date|record\s+date|remittance\s+report|statement\s+to\s+certificate)', query_lower):
            return ("governing_doc_detail", ["GOVERNING_DOC"])
        
        # List/reference queries (VERY HIGH priority, overrides error keywords)
        if re.search(r'\b(list|show)\s+(all|every)\s+\w+\s+codes?\b|\bcatalog\b|\ball\s+error\s+codes?\b', query_lower):
            return ("reference_catalog", ["REFERENCE"])  # Q7 fix: handle plural codes
        
        # UI navigation/access queries (specific pages/screens)
        if re.search(r'\b(access|navigate to|open|find).*(tickets?|dashboard|reports?|uploads?|admin|settings?).*pages?\b', query_lower):
            return ("ui_page_access", ["USER_GUIDE"])  # Q34 fix: case-insensitive, plural forms
        
        # Procedure/SOP queries (prioritize SOP over USER_GUIDE)
        if re.search(r'\bprocedure (for|to)|\bwhat.?s?\s+the\s+procedure', query_lower):
            return ("sop_procedure", ["SOP", "TROUBLESHOOT"])
        
        # Release/change/improvement queries (enhancement, improvement, logic)
        if re.search(r'\b(improvement|enhancement|new feature|retry logic)\b', query_lower):
            return ("release_improvement", ["RELEASE_NOTE"])  # Q35 fix: only RELEASE_NOTE
        if re.search(r'\bwhat.*(changed|new)\b|\brelease|\bversion\s*\d|\bbreaking\b', query_lower):
            return ("release_notes", ["RELEASE_NOTE"])
        
        # Active problem/error queries ("I'm getting...", "I have...")
        if re.search(r"\b(i'?m getting|i have|i'?m seeing)\s+\w+\s+(error|fail|issue|problem)", query_lower):
            return ("active_troubleshooting", ["TROUBLESHOOT", "SOP"])
        
        # Policy/rules queries (blocked, allowed, restrictions)
        if re.search(r'\b(blocked|allowed|restrict|prohibit|permission|policy|rule)\b', query_lower):
            return ("policy", ["TRAINING", "RELEASE_NOTE", "USER_GUIDE"])
        
        # Error/troubleshooting queries (general)
        if re.search(r'\berror\b|\bfail|\bbroken|\bfix\b|\bissue\b|\bproblem\b|\bcause\b', query_lower):
            return ("troubleshooting", ["TROUBLESHOOT", "SOP"])
        
        # How-to/procedural queries
        if re.search(r'\bhow (do|to|can)|\bsteps\b|\bprocess\b', query_lower):
            return ("how_to", ["SOP", "USER_GUIDE", "TRAINING"])
        
        # Access/navigation queries (more specific patterns)
        if re.search(r'\b(how|where).*(access|find|get to|navigate).*(page|screen|tab)', query_lower):
            return ("navigation_page", ["USER_GUIDE", "SOP"])
        if re.search(r'\baccess\b.*\bpage\b|\bnavigate\b|\bfind\b.*\bpage\b|\bgo to\b', query_lower):
            return ("navigation", ["USER_GUIDE", "SOP"])
        
        # Feature capability queries ("which X can I Y", "can I preview")
        # Q38 fix: prioritize TRAINING for file preview/capabilities, handle plurals
        if re.search(r'\b(which|what)\s+files?.*(preview|display|view|support)', query_lower):
            return ("file_capability", ["TRAINING", "USER_GUIDE"])
        if re.search(r'\b(which|what)\s+(files?|features?).*(can|preview|use|support)', query_lower):
            return ("feature_capability", ["USER_GUIDE", "TRAINING"])
        
        # Which/recommendation queries (files, browser, features)
        if re.search(r'\bwhich\s+(file|browser|feature)|\bcan\s+(i|we)\s+(preview|use|access)', query_lower):
            return ("recommendation", ["USER_GUIDE", "TRAINING", "RELEASE_NOTE"])
        
        # What/why educational queries
        if re.search(r'\bwhat (is|does|are)|\bwhy\b', query_lower):
            return ("educational", ["TRAINING", "USER_GUIDE", "TROUBLESHOOT"])
        
        # Default: general query
        return ("general", ["USER_GUIDE", "TROUBLESHOOT"])
    
    def _compute_feature_scores(self, query: str, row: dict, disable_intent: bool = False) -> Dict[str, float]:
        """Compute feature-based scores for a search result"""
        features = {}
        query_lower = query.lower()
        row_type = str(row.get("doc_type", "UNKNOWN"))
        content = str(row.get("content", ""))
        doc_name = str(row.get("source_path", ""))
        
        # Extract error codes from query and document
        query_error_codes = self._extract_error_codes(query)
        doc_error_codes = self._extract_error_codes(content + " " + doc_name)
        
        # Feature 0: Entity overlap (NER-aware scoring)
        features["entity_overlap"] = self._compute_entity_overlap(query, row)
        
        # Feature 1: Exact error code match
        if query_error_codes:
            exact_match = any(code in doc_error_codes for code in query_error_codes)
            features["error_code_exact_match"] = 1.0 if exact_match else 0.0
        else:
            features["error_code_exact_match"] = 0.0
        
        # Feature 2: Intent-based doc_type match
        if disable_intent:
            features["intent_doc_type_match"] = 0.0
        else:
            intent, expected_doc_types = self._detect_query_intent(query)
            if row_type in expected_doc_types:
                rank = expected_doc_types.index(row_type)
                base_feature = 1.0 / (rank + 1)
                high_confidence_intents = ["reference_catalog", "ui_page_access", "file_capability"]
                if intent in high_confidence_intents:
                    base_feature *= 1.5
                features["intent_doc_type_match"] = base_feature
            else:
                features["intent_doc_type_match"] = 0.0
        
        # Feature 3: Title/doc_name term matching
        # Extract significant terms from query (length >= 3, not stopwords)
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "for", "to", "of", "in", "on", "at", "by"}
        query_terms = [w for w in re.findall(r'\b\w{3,}\b', query_lower) if w not in stopwords]
        doc_name_lower = doc_name.lower()
        
        title_matches = sum(1 for term in query_terms if term in doc_name_lower)
        features["title_term_match"] = min(title_matches / max(len(query_terms), 1), 1.0)
        
        # Feature 4: Query keyword density in content
        content_lower = content.lower()
        content_matches = sum(1 for term in query_terms[:5] if term in content_lower)  # Top 5 terms
        features["query_keyword_match"] = min(content_matches / max(min(len(query_terms), 5), 1), 1.0)
        
        # Feature 5: Image description penalty
        features["image_penalty"] = 1.0 if row.get("is_image_desc") else 0.0
        
        # Feature 6: Entity-based keyphrases (semantic match)
        features["entity_keyphrase_match"] = self._compute_keyphrase_overlap(query, row)
        
        return features

    def _compute_graph_score(self, query: str, doc_id: str, G: nx.DiGraph) -> float:
        """Compute graph-based relevance boost using NetworkX O(1) look-ups.

        Walks the graph to find concept / tool / error nodes whose *name*
        appears in the query, then checks whether *doc_id* is connected to
        those nodes via a typed edge.
        """
        if G is None or G.number_of_nodes() == 0:
            return 0.0

        score = 0.0
        query_lower = query.lower()
        doc_node_id = f"doc:{doc_id}"

        if doc_node_id not in G:
            return 0.0

        # 1. Identify query-relevant concept nodes
        relevant_nodes: list[str] = []
        for node_id, attrs in G.nodes(data=True):
            if attrs.get("type") in ("DEFINED_TERM", "TERM", "TOOL", "ERROR_CODE", "TOPIC", "CONCEPT"):
                name = attrs.get("name", attrs.get("surface_form", "")).lower()
                if name and name in query_lower:
                    relevant_nodes.append(node_id)

        # 2. Score connections (O(1) per edge via nx adjacency)
        edge_weights = {
            "DEFINES": 0.3,
            "ADDRESSES": 0.25,
            "COVERS": 0.15,
            "MENTIONS": 0.1,
        }

        for concept in relevant_nodes:
            # doc → concept edge
            if G.has_edge(doc_node_id, concept):
                etype = G[doc_node_id][concept].get("type", "")
                score += edge_weights.get(etype, 0.05)
            # concept → doc edge (reverse)
            if G.has_edge(concept, doc_node_id):
                etype = G[concept][doc_node_id].get("type", "")
                score += edge_weights.get(etype, 0.05)

        return min(score, getattr(self, '_graph_boost_cap', 0.7))  # Cap per TD §6.5

    def _compute_entity_overlap(self, query: str, row: dict) -> float:
        """Compute entity overlap between query and chunk metadata.
        
        Uses NER-extracted entities from both query and chunk to compute
        semantic overlap score. Returns 0.0 if NER not enabled.
        """
        if not getattr(self.config, 'ner_enabled', False):
            return 0.0
        
        # Extract entities from query (cached per query)
        query_entities = self._extract_query_entities(query)
        if not query_entities:
            return 0.0
        
        # Get chunk entities from row (entities/keyphrases are top-level keys after VectorStore.search() unpacks metadata)
        chunk_entities_raw = row.get("entities", [])
        
        # Deserialize if stored as JSON string
        if isinstance(chunk_entities_raw, str):
            import json
            try:
                chunk_entities = json.loads(chunk_entities_raw)
            except (json.JSONDecodeError, ValueError):
                chunk_entities = []
        else:
            chunk_entities = chunk_entities_raw
        
        if not chunk_entities:
            return 0.0
        
        # Normalize entity text (lowercase, strip leading "the", remove possessive 's)
        def normalize_entity(text: str) -> str:
            normalized = text.lower().strip()
            # Remove leading "the "
            if normalized.startswith("the "):
                normalized = normalized[4:]
            # Remove possessive 's
            if normalized.endswith("'s"):
                normalized = normalized[:-2]
            elif normalized.endswith("s'"):
                normalized = normalized[:-2]
            return normalized.strip()
        
        # Extract and normalize entity text
        query_entity_texts = {normalize_entity(e["text"]) for e in query_entities if isinstance(e, dict)}
        chunk_entity_texts = {normalize_entity(e["text"]) for e in chunk_entities if isinstance(e, dict)}
        
        # Compute Jaccard overlap
        if not query_entity_texts or not chunk_entity_texts:
            return 0.0
        
        intersection = len(query_entity_texts & chunk_entity_texts)
        union = len(query_entity_texts | chunk_entity_texts)
        overlap = intersection / union if union > 0 else 0.0
        
        return overlap
    
    def _compute_keyphrase_overlap(self, query: str, row: dict) -> float:
        """Compute keyphrase overlap between query and chunk.
        
        Uses NER-extracted keyphrases from both query and chunk.
        Returns 0.0 if NER not enabled.
        """
        if not getattr(self.config, 'ner_enabled', False):
            return 0.0
        
        # Extract keyphrases from query
        query_keyphrases = self._extract_query_keyphrases(query)
        if not query_keyphrases:
            return 0.0
        
        # Get chunk keyphrases from row (keyphrases are top-level keys after VectorStore.search() unpacks metadata)
        chunk_keyphrases_raw = row.get("keyphrases", [])
        
        # Deserialize if stored as JSON string
        if isinstance(chunk_keyphrases_raw, str):
            import json
            try:
                chunk_keyphrases = json.loads(chunk_keyphrases_raw)
            except (json.JSONDecodeError, ValueError):
                chunk_keyphrases = []
        else:
            chunk_keyphrases = chunk_keyphrases_raw
        
        if not chunk_keyphrases:
            return 0.0
        
        # Extract keyphrase text (lowercase)
        query_kp_texts = {kp["text"].lower() for kp in query_keyphrases if isinstance(kp, dict)}
        chunk_kp_texts = {kp["text"].lower() for kp in chunk_keyphrases if isinstance(kp, dict)}
        
        # Check for partial matches (e.g., "master servicer" in "master servicer obligations")
        matches = 0
        for q_kp in query_kp_texts:
            for c_kp in chunk_kp_texts:
                if q_kp in c_kp or c_kp in q_kp:
                    matches += 1
                    break
        
        return min(matches / len(query_kp_texts), 1.0) if query_kp_texts else 0.0
    
    def _extract_query_entities(self, query: str) -> List[Dict[str, Any]]:
        """Extract entities from query using NER (cached)."""
        # Check cache
        cache_key = f"_query_entities_{hash(query)}"
        if hasattr(self, cache_key):
            return getattr(self, cache_key)
        
        # Extract entities
        from backend.ingestion.ner_extractor import extract_entities_and_keyphrases
        result = extract_entities_and_keyphrases(query, max_keyphrases=10)
        
        # Convert to dicts for JSON compatibility
        entities = [{"text": e.text, "label": e.label} for e in result.entities]
        
        # Cache result
        setattr(self, cache_key, entities)
        return entities
    
    def _extract_query_keyphrases(self, query: str) -> List[Dict[str, Any]]:
        """Extract keyphrases from query using NER (cached)."""
        # Check cache
        cache_key = f"_query_keyphrases_{hash(query)}"
        if hasattr(self, cache_key):
            return getattr(self, cache_key)
        
        # Extract keyphrases
        from backend.ingestion.ner_extractor import extract_entities_and_keyphrases
        result = extract_entities_and_keyphrases(query, max_keyphrases=10)
        
        # Convert to dicts
        keyphrases = [{"text": kp.text, "score": kp.score} for kp in result.keyphrases]
        
        # Cache result
        setattr(self, cache_key, keyphrases)
        return keyphrases
    
    # =========================================================================
    # Smart Context Expansion - Industry Standard RAG Techniques
    # =========================================================================
    
    def _has_continuation_signal(self, text: str) -> bool:
        """
        Detect if chunk content likely continues in the next chunk.
        
        Checks for:
          - Mid-sentence endings (commas, semicolons, conjunctions)
          - List continuations (enumeration starts)
          - Incomplete clauses (colon introducing list/explanation)
        
        Returns:
            True if content appears incomplete and likely continues
        """
        if not text or len(text) < 50:
            return False
        
        # Check last 150 characters for continuation signals
        ending = text.strip()[-150:]
        
        # Strong continuation signals
        strong_signals = [
            ending.endswith(':'),      # List introduction
            ending.endswith(';'),      # Clause continuation
            ending.endswith(','),      # Mid-sentence
            ending.endswith(' and'),   # Conjunction
            ending.endswith(' or'),    # Alternative
            ending.endswith(' but'),   # Contrast
            ending.endswith(' which'), # Relative clause
            ending.endswith(' that'),  # Relative clause
        ]
        
        if any(strong_signals):
            return True
        
        # Enumeration patterns (list starts but may continue)
        enum_patterns = [
            r'\([a-z]\)\s*[^.]{0,50}$',  # (a) at end
            r'\([ivxlc]+\)\s*[^.]{0,50}$',  # (i) at end
            r'\(\d+\)\s*[^.]{0,50}$',    # (1) at end
            r'\b\d+\.\s+[^.]{0,50}$',    # 1. at end
        ]
        
        for pattern in enum_patterns:
            if re.search(pattern, ending, re.IGNORECASE):
                return True
        
        # Multi-word phrase incomplete (no period for 50+ chars)
        if not ending.endswith('.') and not ending.endswith('?') and not ending.endswith('!'):
            # Check if there's a sentence-like structure (3+ words without period)
            words = ending.split()
            if len(words) >= 3:
                return True
        
        return False
    
    def _same_section_context(self, chunk1: dict, chunk2: dict) -> bool:
        """
        Check if two chunks are from the same legal section based on metadata.
        
        Uses the [LEGAL_SECTION] headers added by LegalChunker to determine
        if chunks are semantically related (same ARTICLE, Section, etc.)
        
        Args:
            chunk1: First chunk dictionary
            chunk2: Second chunk dictionary
        
        Returns:
            True if chunks appear to be from the same section
        """
        # Must be from same document
        if chunk1.get("doc_id") != chunk2.get("doc_id"):
            return False
        
        # Extract section headers from content
        content1 = chunk1.get("content", "")
        content2 = chunk2.get("content", "")
        
        # Look for [LEGAL_SECTION] markers
        section_pattern = r'\[LEGAL_SECTION\]\s*(ARTICLE|SECTION|SUBSECTION)\s+([^\n]+)'
        
        match1 = re.search(section_pattern, content1)
        match2 = re.search(section_pattern, content2)
        
        if not match1 or not match2:
            # No section markers, assume might be related
            return True
        
        level1, section1 = match1.groups()
        level2, section2 = match2.groups()
        
        # Same level and same section? Definitely related
        if level1 == level2 and section1.strip() == section2.strip():
            return True
        
        # Subsection following section? Related
        # Example: "Section 2.03" followed by "Subsection (a)"
        if level1 == "SECTION" and level2 == "SUBSECTION":
            return True
        if level1 == "SUBSECTION" and level2 == "SECTION":
            # Subsection before section might be end of previous section
            return False
        
        # Same ARTICLE? Consider related (e.g., Section 2.03 and Section 2.04)
        article_num_pattern = r'(\d+)\.'
        art_match1 = re.search(article_num_pattern, section1)
        art_match2 = re.search(article_num_pattern, section2)
        
        if art_match1 and art_match2:
            if art_match1.group(1) == art_match2.group(1):
                return True
        
        return False
    
    def _expand_context_window(
        self,
        hit_chunks: List[dict],
        base_window: int = 1,
        min_confidence: float = 0.0,
    ) -> List[dict]:
        """
        Expand context window around hit chunks with intelligent strategies.
        
        Implements multiple industry-standard RAG expansion techniques:
          1. Fixed window expansion (±N chunks)
          2. Adaptive expansion based on confidence scores
          3. Continuation-based expansion (detect incomplete content)
          4. Metadata-guided expansion (same section boundaries)
        
        Args:
            hit_chunks: Initial retrieval results
            base_window: Base number of chunks to retrieve before/after (±N)
            min_confidence: Minimum confidence score from initial retrieval
        
        Returns:
            Expanded list of chunks with deduplication
        """
        if not hit_chunks:
            return hit_chunks
        
        # Check config flags
        expansion_enabled = getattr(self.config, 'context_expansion_enabled', True)
        if not expansion_enabled:
            return hit_chunks
        
        adaptive_enabled = getattr(self.config, 'adaptive_expansion_enabled', True)
        continuation_enabled = getattr(self.config, 'continuation_detection_enabled', True)
        metadata_guided = getattr(self.config, 'metadata_guided_expansion', True)
        
        # Determine window size (adaptive or fixed)
        window_size = base_window
        
        if adaptive_enabled and min_confidence > 0:
            # Adaptive window based on confidence score
            # High confidence (>0.85): narrow window (0 = just the hit)
            # Medium confidence (0.70-0.85): base window (1 = ±1)
            # Low confidence (<0.70): expanded window (2 = ±2)
            if min_confidence > 0.85:
                window_size = 0  # High confidence, precise result
                logger.debug(f"Adaptive expansion: high confidence ({min_confidence:.2f}) → window=0")
            elif min_confidence > 0.70:
                window_size = base_window  # Medium confidence, normal window
                logger.debug(f"Adaptive expansion: medium confidence ({min_confidence:.2f}) → window={base_window}")
            else:
                window_size = base_window + 1  # Low confidence, expand more
                logger.debug(f"Adaptive expansion: low confidence ({min_confidence:.2f}) → window={base_window + 1}")
        
        expanded_chunks = []
        processed_chunk_ids = set()
        
        for hit in hit_chunks:
            doc_id = hit.get("doc_id")
            chunk_idx = int(hit.get("chunk_index", 0))
            
            # Add the hit chunk itself
            if hit["chunk_id"] not in processed_chunk_ids:
                expanded_chunks.append(hit)
                processed_chunk_ids.add(hit["chunk_id"])
            
            # Skip expansion if window is 0
            if window_size == 0:
                continue
            
            # Strategy 1: Fixed Window Expansion
            # Retrieve ±window_size chunks from vector store
            start_idx = chunk_idx - window_size
            end_idx = chunk_idx + window_size
            
            neighbor_chunks = self.vector_store.get_chunks_by_indices(
                doc_id=doc_id,
                start_index=start_idx,
                end_index=end_idx
            )
            
            for neighbor in neighbor_chunks:
                if neighbor["chunk_id"] not in processed_chunk_ids:
                    # Mark as expanded chunk (lower priority than direct hits)
                    neighbor["_is_expanded"] = True
                    expanded_chunks.append(neighbor)
                    processed_chunk_ids.add(neighbor["chunk_id"])
            
            # Strategy 2: Continuation-Based Expansion
            if continuation_enabled:
                # Check if hit chunk has continuation signal
                if self._has_continuation_signal(hit.get("content", "")):
                    # Retrieve next chunk beyond window
                    next_idx = chunk_idx + window_size + 1
                    next_chunks = self.vector_store.get_chunks_by_indices(
                        doc_id=doc_id,
                        start_index=next_idx,
                        end_index=next_idx
                    )
                    
                    for next_chunk in next_chunks:
                        if next_chunk["chunk_id"] not in processed_chunk_ids:
                            # Check metadata guidance
                            if metadata_guided and not self._same_section_context(hit, next_chunk):
                                logger.debug(f"Continuation detected but different section → skip")
                                break
                            
                            next_chunk["_is_expanded"] = True
                            next_chunk["_expansion_reason"] = "continuation"
                            expanded_chunks.append(next_chunk)
                            processed_chunk_ids.add(next_chunk["chunk_id"])
                            logger.debug(f"Continuation expansion: added chunk {next_idx}")
                            
                            # Recursive check: does the next chunk also continue?
                            if self._has_continuation_signal(next_chunk.get("content", "")):
                                next_idx += 1
                                more_chunks = self.vector_store.get_chunks_by_indices(
                                    doc_id=doc_id,
                                    start_index=next_idx,
                                    end_index=next_idx
                                )
                                for more in more_chunks:
                                    if more["chunk_id"] not in processed_chunk_ids:
                                        if metadata_guided and not self._same_section_context(hit, more):
                                            break
                                        more["_is_expanded"] = True
                                        more["_expansion_reason"] = "continuation_recursive"
                                        expanded_chunks.append(more)
                                        processed_chunk_ids.add(more["chunk_id"])
                                        logger.debug(f"Recursive continuation: added chunk {next_idx}")
        
        logger.debug(f"Context expansion: {len(hit_chunks)} hits → {len(expanded_chunks)} total ({len(expanded_chunks) - len(hit_chunks)} added)")
        return expanded_chunks

    def execute(self, request: dict) -> AgentResult:
        query = request["query"]
        max_results = int(request.get("max_results", 5))
        doc_type_filter = request.get("doc_type_filter")
        tool_filter = request.get("tool_filter")
        disable_graph_boost = bool(request.get("no_graph_boost", False))
        disable_auto_filter = bool(request.get("no_auto_filter", False))
        strict_mode = bool(request.get("strict", False))
        generated_answer = request.get("generated_answer")
        disable_term_resolution = bool(request.get("no_term_resolution", False))

        # Apply configurable graph boost cap (TD §6.5, default 0.7)
        self._graph_boost_cap = getattr(self.config, 'graph_boost_cap', 0.7)

        # ── Phase 4: Acronym Resolution (TD §6.2) ──────────────────
        if getattr(self.config, 'acronym_resolver_enabled', True):
            try:
                acronym_resolver = AcronymResolver()
                query = acronym_resolver.expand(query)
            except Exception as exc:
                logger.debug("Acronym resolution skipped: %s", exc)

        # ── Phase 4: Query Expansion (TD §6.3) ─────────────────────
        # Two modes:
        # 1. Simple expansion: append synonyms to query (traditional)
        # 2. Multi-query: generate variations + RRF fusion (advanced)
        query_variations = [query]  # Start with original
        use_multi_query = False
        
        if getattr(self.config, 'query_expansion_enabled', True):
            try:
                kb_path = getattr(self.config, 'knowledge_base_path', '.kts')
                expander = QueryExpander(kb_path=kb_path)
                
                # Check if multi-query mode is enabled
                query_expansion_count = getattr(self.config, 'query_expansion_count', 1)
                
                if query_expansion_count > 1:
                    # Multi-query mode: generate variations for RRF fusion
                    use_multi_query = True
                    query_variations = expander.generate_query_variations(
                        query,
                        max_variations=query_expansion_count,
                        doc_type=doc_type_filter,
                    )
                    logger.debug(f"Multi-query retrieval: generated {len(query_variations)} variations")
                else:
                    # Traditional mode: expand with synonyms
                    query = expander.expand(
                        query,
                        doc_type=doc_type_filter,
                        use_ner_entities=getattr(self.config, 'ner_enabled', False),
                    )
                    query_variations = [query]
            except Exception as exc:
                logger.debug("Query expansion skipped: %s", exc)

        # 1. Vector Search (Retrieval) - With Multi-Query support
        max_per_doc = int(request.get("max_chunks_per_doc", getattr(self.config, 'max_chunks_per_doc', 3)))
        top_k_multiplier = 6 if request.get("deep_mode") else 4
        
        if use_multi_query and len(query_variations) > 1:
            # Multi-query retrieval: search with each variation
            all_result_lists = []
            for q_var in query_variations:
                variant_results = self.vector_store.search(
                    query=q_var,
                    top_k=max_results * max_per_doc * top_k_multiplier,
                    doc_type_filter=doc_type_filter
                )
                all_result_lists.append(variant_results)
            
            # Merge results using Reciprocal Rank Fusion
            from backend.retrieval.query_expander import reciprocal_rank_fusion
            rows = reciprocal_rank_fusion(
                all_result_lists,
                k=60,
                chunk_id_key="chunk_id",
                score_key="score"
            )
            
            # Limit to reasonable pool size after fusion
            rows = rows[:max_results * max_per_doc * top_k_multiplier]
            logger.debug(f"RRF fusion: merged {len(all_result_lists)} result lists → {len(rows)} final candidates")
        else:
            # Single query retrieval (traditional)
            rows = self.vector_store.search(
                query=query_variations[0], 
                top_k=max_results * max_per_doc * top_k_multiplier, 
                doc_type_filter=doc_type_filter
            )
        
        # Load Graph (now an nx.DiGraph) for boosting
        graph_data: nx.DiGraph = self.graph_store.load()
        
        # 1a. Smart Context Expansion (Industry-Standard RAG Technique)
        # Expand context window around initial hits with intelligent strategies:
        #   - Adaptive windowing based on confidence
        #   - Continuation detection (mid-sentence, lists, etc.)
        #   - Metadata-guided expansion (same section boundaries)
        if rows:
            # Determine window size from config
            base_window_size = getattr(self.config, 'context_window_size', 1)
            
            # Calculate initial confidence for adaptive expansion
            top_score = rows[0].get("score", 0.0) if rows else 0.0
            
            # Expand context
            rows = self._expand_context_window(
                hit_chunks=rows,
                base_window=base_window_size,
                min_confidence=top_score,
            )

        # 1b. Cross-Encoder Re-ranking (if model available)
        cross_encoder_active = getattr(self.config, 'cross_encoder_enabled', False)
        if cross_encoder_active and rows:
            rows = cross_encoder_rerank(query, rows, content_key="content")

        # 2. RAG Fusion & Re-ranking
        def rerank_scorer(row: dict) -> float:
            """
            Hybrid Score = Vector Similarity * (1 + Graph Boost + Feature Boosts)
            """
            base_score = float(row.get("score", 0.0)) # Chroma returns 'score' (similarity)
            doc_id = row.get("doc_id")
            
            # Compute all textual features (keyword matches, etc.)
            features = self._compute_feature_scores(query, row, disable_intent=disable_auto_filter)
            
            # Store features on row for multi-signal confidence computation
            row["_features"] = features
            
            # Compute Graph Relevance
            graph_boost = 0.0 if disable_graph_boost else self._compute_graph_score(query, doc_id, graph_data)
            
            # Start with Vector Score
            final_score = base_score
            
            # Apply Graph Boost (Additive to base, then multiplicative overall?)
            # Let's use multiplicative boost: Score * (1 + GraphScore)
            final_score *= (1.0 + graph_boost)

            # Apply Cross-Encoder score (blend with vector similarity)
            ce_score = row.get("cross_encoder_score")
            if ce_score is not None:
                # Normalize CE score to 0-1 range via sigmoid
                import math
                ce_norm = 1.0 / (1.0 + math.exp(-ce_score))
                # Blend: 60% cross-encoder + 40% vector similarity * boosts
                final_score = 0.6 * ce_norm + 0.4 * final_score

            # Apply existing Heuristic Boosts
            if features["error_code_exact_match"] > 0:
                final_score *= 1.5 # 50% boost for error code
            
            # Intent-based doc_type boost
            if features["intent_doc_type_match"] > 0:
                 # intent_doc_type_match returns a float 0.0-1.0 from rank
                 final_score *= (1.0 + features["intent_doc_type_match"]) 
            
            # Entity overlap boost (NER-aware scoring)
            if features.get("entity_overlap", 0.0) > 0:
                # Strong boost for entity matches (domain-specific terms)
                final_score *= (1.0 + 0.5 * features["entity_overlap"])
            
            # Keyphrase overlap boost
            if features.get("entity_keyphrase_match", 0.0) > 0:
                # Moderate boost for keyphrase matches (semantic relevance)
                final_score *= (1.0 + 0.3 * features["entity_keyphrase_match"])
            
            # Q38 fix: De-boost TROUBLESHOOT for capability queries
            intent, _ = self._detect_query_intent(query)
            if intent == "file_capability" and row.get("doc_type") == "TROUBLESHOOT":
                final_score *= 0.6

            # Protect GOVERNING_DOC from intent-based de-boosting:
            # General/educational/troubleshooting intents should NOT penalize
            # legal docs since their content naturally contains words like
            # "error", "failure", "issue" in governance contexts.
            row_doc_type = row.get("doc_type", "UNKNOWN")
            if row_doc_type == "GOVERNING_DOC":
                # Neutral intent handling: don't let troubleshoot-intent boost
                # hurt legal docs, and give a mild boost when query mentions
                # legal-specific terms
                legal_terms = {"agreement", "pooling", "servicing", "trust",
                               "certificate", "trustee", "indenture", "mortgage",
                               "obligor", "servicer", "depositor", "beneficiary",
                               "reporting", "statement", "distribution"}
                query_words = set(query.lower().split())
                if query_words & legal_terms:
                    final_score *= 1.3  # boost for legal-term queries
            
            # Store final rerank score on row for confidence computation
            row["_rerank_score"] = final_score
                
            return final_score

        # Sort by fused score
        rows.sort(key=rerank_scorer, reverse=True)
        
        # Deduplicate by doc_id (keep top N chunks per document, not just 1)
        max_per_doc = int(request.get("max_chunks_per_doc", getattr(self.config, 'max_chunks_per_doc', 3)))
        doc_counts: dict[str, int] = {}
        deduped_rows = []
        for row in rows:
            doc_id = row.get("doc_id")
            doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1
            if doc_counts[doc_id] <= max_per_doc:
                deduped_rows.append(row)
            if len(deduped_rows) >= max_results * max_per_doc:
                break
        
        rows = deduped_rows[:max_results * max_per_doc]

        chunks: list[TextChunk] = []
        citations: list[Citation] = []
        image_notes: list[str] = []
        for row in rows:
            chunk = TextChunk(
                chunk_id=row["chunk_id"],
                doc_id=row["doc_id"],
                content=row["content"],
                source_path=row["source_path"],
                chunk_index=row["chunk_index"],
                doc_type=normalize_doc_type(row.get("doc_type", "UNKNOWN")),
            )
            chunks.append(chunk)

            source_path = row["source_path"]
            citations.append(
                Citation(
                    doc_id=row["doc_id"],
                    doc_name=Path(source_path).name,
                    source_path=source_path,
                    uri=f"file:///{source_path.replace('\\\\', '/')}",
                    version=1,
                    section=None,
                    page=None,
                    last_updated=None,
                    image_note=f"See source image context for {row.get('image_id')}" if row.get("is_image_desc") else None,
                )
            )
            if row.get("is_image_desc"):
                image_notes.append(f"Image context available for {row.get('image_id')} in {Path(source_path).name}")

        related_topics: list[str] = []
        if tool_filter:
            docs = GraphQueries.find_docs_for_tool(graph_data, tool_filter)
            allowed_sources = {doc.get("path") for doc in docs}
            filtered_pairs = [(chunk, citation) for chunk, citation in zip(chunks, citations) if chunk.source_path in allowed_sources]
            chunks = [chunk for chunk, _ in filtered_pairs]
            citations = [citation for _, citation in filtered_pairs]
            related_topics = sorted({tag for doc in docs for tag in doc.get("tags", []) if tag})

        if chunks and rows:
            # Multi-signal confidence formula: combines vector similarity,
            # cross-encoder score, graph boost, entity overlap, keyword match,
            # intent match, error code match, and chunk diversity.
            top_row = rows[0]
            top_similarity = float(top_row.get("score", 0.0))
            features = top_row.get("_features", {})
            
            # Signal weights (sum to ~1.0 for base signals)
            w_vector = 0.30       # raw cosine similarity
            w_rerank = 0.25       # fused rerank score (incorporates graph, CE, etc.)
            w_keyword = 0.15      # query keyword density in content
            w_intent = 0.10       # intent-doc_type alignment
            w_entity = 0.10       # entity/keyphrase overlap
            w_error = 0.10        # error code exact match
            
            # Normalize rerank score to 0-1 (rerank scores can exceed 1.0)
            rerank_score = float(top_row.get("_rerank_score", top_similarity))
            rerank_norm = min(1.0, rerank_score)
            
            # Cross-encoder signal (if available, already blended into rerank)
            ce_score = top_row.get("cross_encoder_score")
            if ce_score is not None:
                import math
                ce_norm = 1.0 / (1.0 + math.exp(-ce_score))
                # Replace vector weight partially with CE
                w_vector = 0.15
                w_ce = 0.15
                base_confidence = (
                    w_vector * top_similarity
                    + w_ce * ce_norm
                    + w_rerank * rerank_norm
                    + w_keyword * features.get("query_keyword_match", 0.0)
                    + w_intent * features.get("intent_doc_type_match", 0.0)
                    + w_entity * max(features.get("entity_overlap", 0.0), features.get("entity_keyphrase_match", 0.0))
                    + w_error * features.get("error_code_exact_match", 0.0)
                )
            else:
                base_confidence = (
                    w_vector * top_similarity
                    + w_rerank * rerank_norm
                    + w_keyword * features.get("query_keyword_match", 0.0)
                    + w_intent * features.get("intent_doc_type_match", 0.0)
                    + w_entity * max(features.get("entity_overlap", 0.0), features.get("entity_keyphrase_match", 0.0))
                    + w_error * features.get("error_code_exact_match", 0.0)
                )
            
            # Chunk diversity bonus: more relevant chunks = higher confidence
            chunk_bonus = min(0.10, 0.02 * (len(chunks) - 1))
            
            # Score spread penalty: if top scores are very close, less confident
            if len(rows) >= 2:
                score_gap = float(rows[0].get("_rerank_score", 0)) - float(rows[-1].get("_rerank_score", 0))
                spread_bonus = min(0.05, score_gap * 0.1)
            else:
                spread_bonus = 0.0
            
            confidence = min(1.0, max(0.15, base_confidence + chunk_bonus + spread_bonus))
        else:
            confidence = 0.15
        result_obj = SearchResult(
            context_chunks=chunks,
            confidence=confidence,
            citations=citations,
            image_notes=image_notes,
            freshness={"current": len(citations), "aging": 0, "stale": 0},
            related_topics=related_topics,
        )

        # ── Phase 4: Term Resolution (TD §6.8–§6.9) ────────────────
        term_resolution_payload = None
        if (
            getattr(self.config, 'phase4_enabled', False)
            and getattr(self.config, 'term_resolution_enabled', False)
            and not disable_term_resolution
        ):
            # Compute corpus regime — auto-detect from graph metadata or config
            corpus_regime = getattr(self.config, 'corpus_regime_override', '') or ''
            if not corpus_regime:
                # Auto-detect from persisted corpus regime in graph
                corpus_regime = graph_data.graph.get('corpus_regime', '') if graph_data else ''
            if not corpus_regime:
                corpus_regime = 'MIXED'  # Default to MIXED so term resolution can activate

            intent, _ = self._detect_query_intent(query)
            activate, reason = should_activate_resolver(
                query=query,
                intent=intent,
                corpus_regime=corpus_regime,
                initial_results=rows,
                term_graph=graph_data,
            )
            if activate:
                resolver = TermResolver(
                    max_depth=5,
                    max_token_budget=2000,
                )
                phrases = extract_title_case_phrases(query)
                resolutions = []
                for phrase in phrases[:5]:  # cap to 5 phrases
                    resolution = resolver.resolve_term(phrase, graph_data)
                    if resolution.closure:
                        resolutions.append({
                            "root_term": resolution.root_term,
                            "closure": resolution.closure,
                            "explanation": resolution.stitched_explanation,
                            "depth": resolution.depth_reached,
                            "truncated": resolution.truncated,
                            "cycles": resolution.cycles_detected,
                        })
                if resolutions:
                    term_resolution_payload = {
                        "activated": True,
                        "reason": reason,
                        "resolutions": resolutions,
                    }

        payload = {
            "search_result": result_obj,
            "feature_flags": {
                "no_graph_boost": disable_graph_boost,
                "no_auto_filter": disable_auto_filter,
                "no_term_resolution": disable_term_resolution,
                "strict": strict_mode,
            },
        }
        if term_resolution_payload:
            payload["term_resolution"] = term_resolution_payload

        if strict_mode or generated_answer:
            matcher = EvidenceMatcher(
                casefolding_enabled=self.config.evidence_casefolding,
                numeric_tolerance=self.config.evidence_numeric_tolerance,
                code_normalization=self.config.evidence_code_normalization,
            )
            answer_text = generated_answer or " ".join(chunk.content for chunk in chunks[:2])
            ledger = matcher.match_claims_to_chunks(answer_text, chunks, query=query)

            ledger_path = Path(self.config.knowledge_base_path) / "logs" / "provenance_ledger.jsonl"
            matcher.append_ledger(ledger_path, ledger)

            try:
                validation = enforce_provenance_contract(
                    ledger,
                    strict_mode=strict_mode or self.config.strict_provenance_mode,
                    production_threshold=self.config.min_provenance_coverage,
                )
                ledger.strict_mode_passed = validation.passed
                payload["provenance"] = {
                    "ledger": ledger,
                    "validation": validation,
                }
            except ProvenanceError as exc:
                payload["provenance"] = {
                    "ledger": ledger,
                    "error": exc.to_error_payload(),
                }
                return self.quality_check(
                    AgentResult(
                        success=False,
                        confidence=0.0,
                        data=payload,
                        citations=citations,
                        reasoning="Strict provenance validation failed.",
                    )
                )

        return self.quality_check(
            AgentResult(
                success=True,
                confidence=confidence,
                data=payload,
                citations=citations,
                reasoning="Retrieved relevant context chunks and citations for Copilot.",
            )
        )
