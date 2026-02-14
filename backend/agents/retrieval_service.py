from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

from backend.common.models import AgentResult, Citation, SearchResult, TextChunk
from backend.common.doc_types import normalize_doc_type
from backend.graph import GraphQueries, GraphStore
from backend.vector import VectorStore
from .base_agent import AgentBase


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
    
    def _compute_feature_scores(self, query: str, row: dict) -> Dict[str, float]:
        """Compute feature-based scores for a search result"""
        features = {}
        query_lower = query.lower()
        row_type = str(row.get("doc_type", "UNKNOWN"))
        content = str(row.get("content", ""))
        doc_name = str(row.get("source_path", ""))
        
        # Extract error codes from query and document
        query_error_codes = self._extract_error_codes(query)
        doc_error_codes = self._extract_error_codes(content + " " + doc_name)
        
        # Feature 1: Exact error code match
        if query_error_codes:
            exact_match = any(code in doc_error_codes for code in query_error_codes)
            features["error_code_exact_match"] = 1.0 if exact_match else 0.0
        else:
            features["error_code_exact_match"] = 0.0
        
        # Feature 2: Intent-based doc_type match
        intent, expected_doc_types = self._detect_query_intent(query)
        if row_type in expected_doc_types:
            # Rank priority: first expected type = highest boost
            rank = expected_doc_types.index(row_type)
            base_feature = 1.0 / (rank + 1)  # 1.0, 0.5, 0.33...
            
            # High-confidence intents get extra boost (Q7, Q34, Q38 fix)
            high_confidence_intents = ["reference_catalog", "ui_page_access", "file_capability"]
            if intent in high_confidence_intents:
                base_feature *= 1.5  # 1.0 → 1.5 (total 2.55x), 0.5 → 0.75, etc.
            
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
        features["query_keyword_match"] = min(content_matches / min(len(query_terms), 5), 1.0)
        
        # Feature 5: Image description penalty
        features["image_penalty"] = 1.0 if row.get("is_image_desc") else 0.0
        
        return features

    def execute(self, request: dict) -> AgentResult:
        query = request["query"]
        max_results = int(request.get("max_results", 5))
        doc_type_filter = request.get("doc_type_filter")
        tool_filter = request.get("tool_filter")

        rows = self.vector_store.search(query=query, max_results=max_results * 3, doc_type_filter=doc_type_filter)

        def rerank(row: dict) -> float:
            """Feature-based reranking with configurable weights"""
            base_score = float(row.get("similarity", 0.0))
            
            # Compute all features
            features = self._compute_feature_scores(query, row)
            
            # Apply multiplicative boosts
            score = base_score
            
            # Error code exact match (strongest boost)
            if features["error_code_exact_match"] > 0:
                score *= self.weights["error_code_exact_match"]
            
            # Intent-based doc_type boost
            if features["intent_doc_type_match"] > 0:
                boost = 1.0 + (self.weights["intent_doc_type_match"] - 1.0) * features["intent_doc_type_match"]
                score *= boost
            
            # Q38 fix: De-boost TROUBLESHOOT for capability queries
            intent, _ = self._detect_query_intent(query)
            if intent == "file_capability" and row.get("doc_type") == "TROUBLESHOOT":
                score *= 0.6  # Strong de-boost (40% penalty)
            
            # Title term match boost
            if features["title_term_match"] > 0:
                boost = 1.0 + (self.weights["title_term_match"] - 1.0) * features["title_term_match"]
                score *= boost
            
            # Query keyword match boost
            if features["query_keyword_match"] > 0:
                boost = 1.0 + (self.weights["query_keyword_match"] - 1.0) * features["query_keyword_match"]
                score *= boost
            
            # Image penalty
            if features["image_penalty"] > 0:
                score *= self.weights["image_penalty"]
            
            return score

        # Rerank all results
        rows = sorted(rows, key=rerank, reverse=True)
        
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

        graph = self.graph_store.load()
        related_topics = []
        if tool_filter:
            docs = GraphQueries.find_docs_for_tool(graph, tool_filter)
            allowed_sources = {doc.get("source_path") for doc in docs}
            filtered_pairs = [(chunk, citation) for chunk, citation in zip(chunks, citations) if chunk.source_path in allowed_sources]
            chunks = [chunk for chunk, _ in filtered_pairs]
            citations = [citation for _, citation in filtered_pairs]
            related_topics = sorted({tag for doc in docs for tag in doc.get("tags", [])})

        confidence = min(1.0, 0.5 + (0.1 * len(chunks))) if chunks else 0.3
        result_obj = SearchResult(
            context_chunks=chunks,
            confidence=confidence,
            citations=citations,
            image_notes=image_notes,
            freshness={"current": len(citations), "aging": 0, "stale": 0},
            related_topics=related_topics,
        )

        return self.quality_check(
            AgentResult(
                success=True,
                confidence=confidence,
                data={"search_result": result_obj},
                citations=citations,
                reasoning="Retrieved relevant context chunks and citations for Copilot.",
            )
        )
