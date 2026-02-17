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
        
        # 1. Vector Search (Retrieval) - Get Top 20 Candidates
        rows = self.vector_store.search(
            query=query, 
            top_k=max_results * 4, 
            doc_type_filter=doc_type_filter
        )
        
        # Load Graph (now an nx.DiGraph) for boosting
        graph_data: nx.DiGraph = self.graph_store.load()

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
                
            return final_score

        # Sort by fused score
        rows.sort(key=rerank_scorer, reverse=True)
        
        # Deduplicate by doc_id (keep highest-scored chunk per document)
        seen_docs = set()
        deduped_rows = []
        for row in rows:
            doc_id = row.get("doc_id")
            if doc_id not in seen_docs:
                deduped_rows.append(row)
                seen_docs.add(doc_id)
            if len(deduped_rows) >= max_results:
                break
        
        rows = deduped_rows[:max_results]

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
            top_similarity = float(rows[0].get("score", 0.0))
            confidence = min(1.0, max(0.3, top_similarity + (0.05 * (len(chunks) - 1))))
        else:
            confidence = 0.3
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
            # Compute corpus regime
            corpus_regime = getattr(self.config, 'corpus_regime_override', '') or 'GENERIC_GUIDE'
            if not corpus_regime or corpus_regime == '':
                corpus_regime = 'GENERIC_GUIDE'

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
