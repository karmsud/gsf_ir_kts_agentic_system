from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
from backend.vector.embedding_provider import get_embedding_provider
from backend.retrieval.cross_encoder import rerank as cross_encoder_rerank
from backend.retrieval.critique_merger import merge_critique_questions
from backend.agents.critique_question_generator import CritiqueQuestionGenerator
from backend.retrieval.crag import CRAGProcessor, CRAGConfig, CRAGResult

# ── Phase 10-15 imports ───────────────────────────────────────────
from backend.retrieval.confidence_scorer import ConfidenceScorer
from backend.retrieval.gap_detector import GapDetector, extract_entities
from backend.retrieval.hyde import HyDEProcessor
from backend.retrieval.query_rewriter import QueryRewriter
from backend.retrieval.session_memory import SessionStore, apply_document_bias, should_summarise, build_summary_prompt, apply_summary
from backend.retrieval.temporal_reasoner import TemporalReasoner
from backend.retrieval.extraction_mode import ExtractionMode
from backend.retrieval.audit_mode import AuditMode
from backend.retrieval.summary_mode import SummaryMode
from backend.retrieval.definition_mode import DefinitionMode
from backend.retrieval.scope_router import ScopeRouter, parse_two_level_scope
from backend.retrieval.comparison_mode import ComparisonMode
from backend.retrieval.contradiction_detector import ContradictionDetector
from backend.retrieval.anomaly_scorer import AnomalyScorer
from backend.retrieval.baseline_corpus import BaselineCorpus

# ── Hybrid Retrieval Engine (Graph + Vector + BM25) ──────────────
from backend.retrieval.hybrid_retrieval_engine import (
    HybridRetrievalEngine,
    create_hybrid_engine,
)

from .base_agent import AgentBase

logger = logging.getLogger(__name__)


# ── Phase 10.4: Heuristic Summarisation ───────────────────────

_DATE_RE = re.compile(
    r'\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|(?:January|February|March|April|May|June'
    r'|July|August|September|October|November|December)\s+\d{1,2},?\s*\d{2,4})\b',
    re.IGNORECASE,
)
_AMOUNT_RE = re.compile(r'\$[\d,.]+(?:\s*(?:million|billion|MM|M|B))?', re.IGNORECASE)
_PARTY_ROLES = [
    "Depositor", "Trustee", "Master Servicer", "Servicer",
    "Certificate Registrar", "Issuer", "Sponsor", "Seller",
]


def _heuristic_summarise(existing_summary: str, turns: list[dict]) -> str:
    """Extract key facts from conversation turns into a compact summary.

    Preserves: defined terms, dates, amounts, party names, documents mentioned.
    Falls back to truncated concatenation when extraction yields nothing.
    """
    facts: list[str] = []

    # Carry over existing summary
    if existing_summary:
        facts.append(existing_summary.strip())

    for turn in turns:
        text = turn.get("content", "")
        if not text:
            continue

        # Extract dates
        for m in _DATE_RE.finditer(text):
            facts.append(f"Date: {m.group()}")

        # Extract amounts
        for m in _AMOUNT_RE.finditer(text):
            facts.append(f"Amount: {m.group()}")

        # Extract party assignments
        for role in _PARTY_ROLES:
            pat = rf"{role}\s*(?::|is|—)\s*([A-Z][A-Za-z\s&.,]+?)(?:\.|,|\n|$)"
            m = re.search(pat, text)
            if m:
                facts.append(f"{role}: {m.group(1).strip().rstrip('.,')}")

        # Extract quoted defined terms
        for m in re.finditer(r'"([A-Z][A-Za-z\s]+?)"\s+(?:means|is defined as)', text):
            facts.append(f'"{m.group(1)}" defined')

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for f in facts:
        norm = f.lower().strip()
        if norm not in seen:
            seen.add(norm)
            unique.append(f)

    if unique:
        return "; ".join(unique)[:1000]

    # Fallback: simple truncated concatenation
    return "; ".join(
        t.get("content", "")[:150] for t in turns if t.get("content")
    )[:1000]


class RetrievalService(AgentBase):
    agent_name = "retrieval-service"

    def __init__(self, config):
        super().__init__(config)
        # Initialize embedding provider (supports BGE ONNX or legacy MiniLM)
        self._embedding_provider = get_embedding_provider(config)
        self.vector_store = VectorStore(
            config.chroma_persist_dir,
            embedding_provider=self._embedding_provider
        )
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

        # ── Phase 10-15: Module Singletons ────────────────────────
        self._session_memory = SessionStore(ttl_hours=getattr(config, 'session_memory_ttl_hours', 4.0)) if getattr(config, 'session_memory_enabled', True) else None
        self._query_rewriter = QueryRewriter() if getattr(config, 'query_rewriting_enabled', True) else None
        self._confidence_scorer = ConfidenceScorer()
        self._gap_detector = GapDetector()
        self._temporal_reasoner = TemporalReasoner() if getattr(config, 'temporal_reasoning_enabled', True) else None
        self._hyde_processor = HyDEProcessor() if getattr(config, 'hyde_enabled', False) else None
        self._crag_processor = CRAGProcessor(CRAGConfig(
            enabled=getattr(config, 'crag_enabled', True),
            max_claims=getattr(config, 'crag_max_claims', 20),
            evidence_top_k=getattr(config, 'crag_evidence_top_k', 5),
        )) if getattr(config, 'crag_enabled', True) else None
        self._scope_router = None  # Lazily initialized when catalog is ready
        self._deal_catalog = None   # Lazily initialized with scope router

        # ── Phase 15: Cross-Deal Intelligence Singletons ──────────
        self._extraction_mode = ExtractionMode() if getattr(config, 'extraction_mode_enabled', True) else None
        self._summary_mode = SummaryMode(
            temporal_context=self._temporal_reasoner.get_temporal_context() if self._temporal_reasoner else ""
        ) if getattr(config, 'summary_mode_enabled', True) else None
        self._comparison_mode = ComparisonMode() if getattr(config, 'comparison_mode_enabled', True) else None
        self._audit_mode = AuditMode() if getattr(config, 'audit_mode_enabled', True) else None
        self._definition_mode = DefinitionMode() if getattr(config, 'definition_mode_enabled', True) else None
        self._contradiction_detector = ContradictionDetector() if getattr(config, 'contradiction_detection_enabled', True) else None
        self._baseline_corpus = BaselineCorpus() if getattr(config, 'baseline_corpus_enabled', False) else None
        self._anomaly_scorer = (
            AnomalyScorer(
                baseline_corpus=self._baseline_corpus,
                embed_fn=self._embedding_provider.embed_query if self._embedding_provider else None,
            )
            if getattr(config, 'anomaly_detection_enabled', True)
            else None
        )

        # ── Hybrid Retrieval Engine (Graph + Vector + BM25) ───────
        # Unified three-signal engine for financial & legal documents.
        # Replaces the ad-hoc BM25 gating in human_like_retriever.
        self._hybrid_engine: Optional[HybridRetrievalEngine] = None
        if getattr(config, 'hybrid_engine_enabled', True):
            try:
                self._hybrid_engine = create_hybrid_engine(
                    config,
                    self.vector_store,
                    self.graph_store,
                )
                logger.info("[HybridEngine] Initialized (vector+BM25+graph)")
            except Exception as _exc:
                logger.warning("[HybridEngine] Init failed, falling back: %s", _exc)
                self._hybrid_engine = None
        # end __init__

    def _get_scope_router(self) -> ScopeRouter:
        """Lazily initialize and return the scope router (Phase 12.4).

        Creates a DealCatalog instance if *deal_catalog_enabled* is True,
        then wraps it in a ScopeRouter.  Subsequent calls return the cached
        instance.
        """
        if self._scope_router is not None:
            return self._scope_router

        from backend.vector.deal_catalog import DealCatalog

        catalog = None
        if getattr(self.config, 'deal_catalog_enabled', True):
            try:
                catalog_path = getattr(self.config, 'deal_catalog_path', '')
                catalog = DealCatalog(db_path=catalog_path)
                self._deal_catalog = catalog
                logger.debug("[Phase12] Deal catalog initialized: %d entries", catalog.count())
            except Exception as exc:
                logger.warning("[Phase12] Deal catalog init failed: %s", exc)

        self._scope_router = ScopeRouter(catalog=catalog)
        return self._scope_router

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

    # ------------------------------------------------------------------
    # Phase 6: Build Response from Iterative Retrieval Results
    # ------------------------------------------------------------------
    def _build_phase6_response(
        self,
        request: dict,
        phase6_result: dict,
        query: str,
        strict_mode: bool,
        generated_answer: str | None,
        disable_term_resolution: bool,
    ) -> AgentResult:
        """Convert Phase 6 orchestrator results to standard AgentResult."""
        from pathlib import Path
        
        results = phase6_result.get("results", [])
        confidence = phase6_result.get("confidence", 0.0)
        trace = phase6_result.get("trace", {})
        iterations = phase6_result.get("iterations", 1)
        retrieval_mode = request.get("retrieval_mode")  # extract, audit, summary, compare, define

        # ── Phase 13.3: Parent-child expansion ────────────────────
        # If parent-child chunking is enabled, replace child text with
        # the parent's full-section text for richer LLM context.
        if getattr(self.config, 'parent_child_chunking_enabled', False) and results:
            parent_ids_to_fetch = []
            for hit in results:
                meta = hit.get("metadata", {})
                if not isinstance(meta, dict):
                    meta = {}
                pid = meta.get("parent_id") or hit.get("parent_id")
                if pid:
                    parent_ids_to_fetch.append(pid)
            if parent_ids_to_fetch:
                try:
                    parents_map = {}
                    fetched = self.vector_store.fetch_parent_chunks(parent_ids_to_fetch)
                    for p in fetched:
                        parents_map[p["parent_id"]] = p["content"]
                    # Expand: swap child text for parent text where available
                    for hit in results:
                        meta = hit.get("metadata", {})
                        if not isinstance(meta, dict):
                            meta = {}
                        pid = meta.get("parent_id") or hit.get("parent_id")
                        if pid and pid in parents_map:
                            hit["_child_text"] = hit.get("text", hit.get("content", ""))
                            hit["text"] = parents_map[pid]
                            hit["_parent_expanded"] = True
                    logger.info(
                        "[Phase13.3] Parent expansion: %d / %d results expanded",
                        sum(1 for h in results if h.get("_parent_expanded")),
                        len(results),
                    )
                except Exception as exc:
                    logger.debug("[Phase13.3] Parent expansion skipped: %s", exc)
        
        # NOTE: Cross-encoder reranking is already applied inside HumanLikeRetriever
        # (step 6 — cross_encoder_rerank). Applying it again here would double-rerank
        # and distort the carefully tuned hybrid scores. We keep only trace info.
        # The second CE pass in the legacy pipeline (below) still applies when
        # Phase 6 is NOT used.
        
        max_per_doc = int(request.get("max_chunks_per_doc", getattr(self.config, 'max_chunks_per_doc', 3)))
        max_results = int(request.get("max_results", 5))
        
        chunks: list[TextChunk] = []
        citations: list[Citation] = []
        seen_chunk_ids: set[str] = set()
        doc_counts: dict[str, int] = {}
        
        for hit in results:
            # Extract fields from Phase 6 hit format
            # Phase 6 hits have: id, text, similarity, metadata (dict), type
            hit_id = hit.get("id", "")
            text = hit.get("text", hit.get("content", ""))
            
            # Metadata can be either in a nested dict or at top level
            meta = hit.get("metadata", {})
            if not isinstance(meta, dict):
                meta = {}
            
            doc_id = meta.get("document_id") or hit.get("document_id") or hit.get("doc_id", "")
            source_path = meta.get("source_path") or hit.get("source_path", "")
            item_type = meta.get("item_type") or hit.get("item_type", hit.get("type", ""))
            section_number = meta.get("section_number") or hit.get("section_number", "")
            # Prefer the enriched section_label (e.g. "Article III — ACCOUNTS")
            # over the raw section_number for better LLM citations.
            section_label = meta.get("section_label") or hit.get("section_label", "")
            section_for_citation = section_label or section_number
            chunk_index = meta.get("chunk_index", 0) or hit.get("chunk_index", 0)
            
            # Deduplicate by chunk_id
            chunk_id = hit_id or f"{doc_id}_{chunk_index}"
            if chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk_id)
            
            # Enforce max_chunks_per_doc
            doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1
            if doc_counts[doc_id] > max_per_doc:
                continue
            
            # Stop once we have enough results
            if len(chunks) >= max_results:
                break
            
            # If source_path is missing, try to reconstruct from doc_id
            if not source_path and doc_id:
                # Check graph for path
                graph = self.graph_store.load()
                if doc_id in graph:
                    node_data = graph.nodes[doc_id]
                    source_path = node_data.get("path", node_data.get("source_path", ""))
            
            chunk = TextChunk(
                chunk_id=chunk_id,
                doc_id=doc_id,
                content=text,
                source_path=source_path,
                chunk_index=chunk_index,
                doc_type=normalize_doc_type(meta.get("doc_type") or hit.get("doc_type") or "UNKNOWN"),
            )
            chunks.append(chunk)
            
            citations.append(
                Citation(
                    doc_id=doc_id,
                    doc_name=Path(source_path).name if source_path else doc_id,
                    source_path=source_path,
                    uri=f"file:///{source_path.replace(chr(92), '/')}" if source_path else "",
                    version=1,
                    section=section_for_citation or None,
                    page=None,
                    last_updated=None,
                    image_note=None,
                )
            )
        
        result_obj = SearchResult(
            context_chunks=chunks,
            confidence=confidence,
            citations=citations,
            image_notes=[],
            freshness={"current": len(citations), "aging": 0, "stale": 0},
            related_topics=[],
            definitions_glossary=phase6_result.get("definitions_glossary", ""),
            entity_roles=phase6_result.get("entity_roles", []),
        )
        
        payload = {
            "search_result": result_obj,
            "feature_flags": {
                "no_graph_boost": bool(request.get("no_graph_boost", False)),
                "no_auto_filter": bool(request.get("no_auto_filter", False)),
                "no_term_resolution": disable_term_resolution,
                "strict": strict_mode,
            },
            "phase6": {
                "enabled": True,
                "iterations": iterations,
                "confidence": confidence,
                "trace": trace,  # Full explainability trace for VS Code output
            },
        }

        # ── Phase 9.3: Inject critique questions into payload ──────
        try:
            kb_path = getattr(self.config, 'knowledge_base_path', '.kts')
            cq_gen = CritiqueQuestionGenerator.__new__(CritiqueQuestionGenerator)
            unique_doc_ids = {c.doc_id for c in chunks if c.doc_id}
            critique_stores = {}
            for did in unique_doc_ids:
                loaded = cq_gen.load(did, kb_path)
                if loaded:
                    critique_stores[did] = loaded
            if critique_stores:
                chunk_dicts = [{"doc_id": c.doc_id, "section_id": getattr(c, "section_id", "sec000")} for c in chunks]
                merged_cqs = merge_critique_questions(chunk_dicts, critique_stores)
                payload["critique_questions"] = [
                    {"id": q.id, "question": q.question, "trigger_keywords": q.trigger_keywords,
                     "trigger_logic": q.trigger_logic, "priority": q.priority}
                    for q in merged_cqs
                ]
                logger.info("[Phase9.3] Injected %d critique questions from %d docs", len(merged_cqs), len(critique_stores))
        except Exception as exc:
            logger.debug("[Phase9.3] Critique question injection skipped: %s", exc)

        # ── Phase 19.1: CRAG configuration for extension ──────────
        if self._crag_processor:
            payload["crag_config"] = {
                "enabled": True,
                "max_claims": self._crag_processor.config.max_claims,
                "evidence_top_k": self._crag_processor.config.evidence_top_k,
                "drop_contradicted": self._crag_processor.config.drop_contradicted,
                "flag_no_evidence": self._crag_processor.config.flag_no_evidence,
            }

        # ── Phase 13.1: Confidence scoring ─────────────────────────
        if getattr(self.config, 'confidence_scoring_enabled', True) and results:
            try:
                confidence_result = self._confidence_scorer.score(results, score_key="_final_score")
                payload["confidence_tier"] = {
                    "tier": confidence_result.tier.value,
                    "display": confidence_result.display_text,
                    "icon": confidence_result.display_icon,
                    "top_score": confidence_result.top_score,
                    "n_direct_matches": confidence_result.n_direct_matches,
                }
            except Exception as exc:
                logger.debug("[Phase13.1] Confidence scoring skipped: %s", exc)

        # ── Phase 13.2: Gap detection ──────────────────────────────
        if getattr(self.config, 'gap_detection_enabled', True) and results:
            try:
                gap_result = self._gap_detector.detect(query, results, content_key="text")
                if gap_result.has_gaps:
                    payload["gap_alert"] = {
                        "missing_terms": gap_result.gaps,
                        "display": gap_result.display_text,
                    }
            except Exception as exc:
                logger.debug("[Phase13.2] Gap detection skipped: %s", exc)

        # ── Phase 14.2: Temporal context ───────────────────────────
        if self._temporal_reasoner:
            payload["temporal_context"] = self._temporal_reasoner.get_temporal_context()
            if self._temporal_reasoner.is_temporal_query(query):
                payload["temporal_evaluation"] = self._temporal_reasoner.get_temporal_evaluation_instruction()

        # ── Phase 15.4: Anomaly scoring for /audit mode ────────────
        if retrieval_mode == "audit" and self._anomaly_scorer and results:
            try:
                anomaly_results = []
                deal_type = request.get("deal_type", "PSA_HELOC")
                for r in results:
                    clause_type = r.get("clause_type", r.get("section_type", ""))
                    if clause_type:
                        ar = self._anomaly_scorer.score(
                            r.get("text", r.get("content", "")),
                            clause_type=clause_type,
                            deal_type=deal_type,
                        )
                        anomaly_results.append(ar.to_dict())
                if anomaly_results:
                    payload["anomaly_scores"] = anomaly_results
                    logger.info("[Phase15.4] Scored %d clauses for anomalies", len(anomaly_results))
            except Exception as exc:
                logger.debug("[Phase15.4] Anomaly scoring skipped: %s", exc)
        
        # Term resolution (same as legacy path)
        if (
            getattr(self.config, 'phase4_enabled', False)
            and getattr(self.config, 'term_resolution_enabled', False)
            and not disable_term_resolution
        ):
            graph_data = self.graph_store.load()
            corpus_regime = getattr(self.config, 'corpus_regime_override', '') or ''
            if not corpus_regime:
                corpus_regime = graph_data.graph.get('corpus_regime', '') if graph_data else ''
            if not corpus_regime:
                corpus_regime = 'MIXED'
            
            intent, _ = self._detect_query_intent(query)
            activate, reason = should_activate_resolver(
                query=query,
                intent=intent,
                corpus_regime=corpus_regime,
                initial_results=[],  # Phase 6 results are already filtered
                term_graph=graph_data,
            )
            if activate:
                resolver = TermResolver(max_depth=5, max_token_budget=2000)
                phrases = extract_title_case_phrases(query)
                resolutions = []
                for phrase in phrases[:5]:
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
                    payload["term_resolution"] = {
                        "activated": True,
                        "reason": reason,
                        "resolutions": resolutions,
                    }
        
        # Strict mode / provenance validation
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
                payload["provenance"] = {"ledger": ledger, "validation": validation}
            except ProvenanceError as exc:
                payload["provenance"] = {"ledger": ledger, "error": exc.to_error_payload()}
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
                reasoning=f"Phase 6 retrieval: {len(results)} results in {iterations} iterations.",
            )
        )

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Phase 13.5: Regime-Aware Retrieval Router
    # ------------------------------------------------------------------
    def _resolve_corpus_regime(self) -> str:
        """Determine the corpus regime from config override or graph metadata.

        Returns one of: GOVERNING_DOC_LEGAL, GENERIC_GUIDE, MIXED.
        """
        regime = (getattr(self.config, 'corpus_regime_override', '') or '').upper()
        if regime:
            return regime

        try:
            graph = self.graph_store.load()
            if graph is not None:
                regime = (graph.graph.get('corpus_regime', '') or '').upper()
        except Exception:
            pass

        return regime or 'MIXED'

    def _should_use_guide_strategy(self, query: str, corpus_regime: str) -> bool:
        """Decide whether to use the vector-first *guide* strategy.

        Decision matrix:
            GOVERNING_DOC_LEGAL  → always graph-first (HumanLikeRetriever)
            GENERIC_GUIDE        → always vector-first (GuideRetriever)
            MIXED                → use query intent to decide:
                                   - governing_doc / definition intents  → graph-first
                                   - troubleshooting / how-to / general  → vector-first

        Feature-flagged via ``regime_aware_retrieval`` config key (default ON).
        When disabled, falls back to the previous default (HumanLikeRetriever).
        """
        if not getattr(self.config, 'regime_aware_retrieval', True):
            return False  # feature disabled → legacy behaviour (graph-first always)

        if corpus_regime == 'GOVERNING_DOC_LEGAL':
            return False
        if corpus_regime == 'GENERIC_GUIDE':
            return True

        # MIXED corpus — use query intent as tie-breaker
        intent, _ = self._detect_query_intent(query)
        legal_intents = {
            'governing_doc', 'governing_doc_detail',
            'explicit_troubleshoot',   # explicit mention → keep in legal path (may reference PSA)
        }
        return intent not in legal_intents

    # ------------------------------------------------------------------
    # Phase 18: Auto-scope discovery + federated retrieval
    # ------------------------------------------------------------------
    def _discover_scope_kts_paths(self) -> list[tuple[str, str]]:
        """Auto-discover per-scope ``.kts`` directories.

        When per-folder isolation (Phase 12.1) is active, each deal
        subfolder has its own ``.kts`` directory with vectors, graph, and
        manifest.  The **root** ``.kts`` has no vectors — so this method
        discovers sibling scope directories by scanning the parent of
        ``knowledge_base_path``.

        Returns
        -------
        list of (slug, kts_path)
            Each entry gives the lowercase slug and the absolute path
            to  the scope's ``.kts`` directory.  Returns an empty list
            if no scope directories are found.
        """
        kb_path = Path(getattr(self.config, 'knowledge_base_path', '.kts'))
        if not kb_path.exists():
            return []

        # Parent of .kts/ is the source root (e.g. kb_test/)
        source_root = kb_path.parent
        if not source_root.exists():
            return []

        scopes: list[tuple[str, str]] = []
        for child in sorted(source_root.iterdir()):
            if not child.is_dir() or child.name.startswith('.'):
                continue
            scope_kts = child / '.kts'
            if scope_kts.exists() and scope_kts.is_dir():
                # Presence of vectors or graph confirms this is an indexed scope
                has_vectors = (scope_kts / 'vectors' / 'phase6').exists()
                has_graph = (scope_kts / 'graph' / 'knowledge_graph.json').exists()
                if has_vectors or has_graph:
                    slug = child.name.lower().replace(' ', '_')
                    scopes.append((slug, str(scope_kts)))

        if scopes:
            logger.info(
                "[Phase18] Auto-discovered %d scope(s): %s",
                len(scopes),
                [s for s, _ in scopes],
            )
        return scopes

    def _resolve_scope_kts_path(self, scope_slug: str) -> str | None:
        """Resolve a scope slug to its ``.kts`` directory path.

        Uses :meth:`_discover_scope_kts_paths` to find the matching scope.
        Returns ``None`` if the slug is not found.
        """
        scopes = self._discover_scope_kts_paths()
        for slug, kts_path in scopes:
            if slug == scope_slug:
                return kts_path
        return None

    def _federated_scope_retrieve(
        self,
        query: str,
        scope_paths: list[tuple[str, str]],
        *,
        max_results: int = 10,
        extra_queries: list | None = None,
        doc_type_filter: str | None = None,
        conversation_history: list | None = None,
        doc_name_prefix: str | None = None,
    ) -> dict | None:
        """Fan-out Phase 6 retrieval across all discovered scopes.

        Creates a per-scope ``RetrievalService`` with scoped config and
        merges results sorted by score.
        """
        from config.settings import scope_config

        all_results: list = []
        best_confidence = 0.0
        all_definitions: list[str] = []
        all_entity_roles: list = []
        combined_trace: list = []

        for slug, kts_path in scope_paths:
            try:
                scfg = scope_config(self.config, kts_path)
                scope_svc = RetrievalService(scfg)
                result = scope_svc._phase6_retrieve(
                    query,
                    max_results=max_results,
                    extra_queries=extra_queries,
                    doc_type_filter=doc_type_filter,
                    conversation_history=conversation_history,
                    doc_name_prefix=doc_name_prefix,
                )
                if result and result.get('results'):
                    # Tag each result with scope attribution
                    for r in result['results']:
                        if hasattr(r, 'metadata'):
                            r.metadata['scope'] = slug
                        elif isinstance(r, dict):
                            r['scope'] = slug
                    all_results.extend(result['results'])
                    best_confidence = max(best_confidence, result.get('confidence', 0))
                    if result.get('definitions_glossary'):
                        all_definitions.append(result['definitions_glossary'])
                    if result.get('entity_roles'):
                        all_entity_roles.extend(result['entity_roles'])
                    combined_trace.extend(result.get('trace', []))
                    logger.info(
                        "[Phase18] Scope %s: %d results (confidence=%.3f)",
                        slug, len(result['results']), result.get('confidence', 0),
                    )
            except Exception as exc:
                logger.warning("[Phase18] Federated search failed for scope %s: %s", slug, exc)

        if not all_results:
            return None

        # Sort by score descending and truncate
        def _score(r):
            if hasattr(r, 'score'):
                return r.score
            if isinstance(r, dict):
                return r.get('score', 0)
            return 0

        all_results.sort(key=_score, reverse=True)
        all_results = all_results[:max_results]

        logger.info(
            "[Phase18] Federated search: %d total results from %d scopes (best conf=%.3f)",
            len(all_results), len(scope_paths), best_confidence,
        )

        return {
            'results': all_results,
            'confidence': best_confidence,
            'iterations': 1,
            'trace': combined_trace,
            'strategy': 'federated_multi_scope',
            'definitions_glossary': '\n'.join(all_definitions),
            'entity_roles': all_entity_roles,
        }

    # ------------------------------------------------------------------
    # Phase 17: Graph path selection (doc graph vs deal graph)
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Phase 17: Multi-scope result collection helper
    # ------------------------------------------------------------------
    def _collect_multi_scope_results(
        self,
        query: str,
        scope_slugs: list[str],
        max_results: int,
        *,
        doc_name_prefix: str | None = None,
    ) -> dict[str, list]:
        """Collect retrieval results across multiple scope slugs.

        Returns a dict mapping ``scope_slug → list[result_dict]``.
        Each scope is searched independently with the standard Phase 6 pipeline.
        Errors for individual scopes are logged and skipped.
        """
        from config.settings import scope_config

        results_by_scope: dict[str, list] = {}
        for slug in scope_slugs:
            try:
                scfg = scope_config(self.config, slug)
                svc = RetrievalService(scfg)
                result = svc.execute({
                    "query": query,
                    "max_results": max_results,
                    "doc_name_prefix": doc_name_prefix,
                    "scope_override": slug,
                })
                if result and result.success:
                    payload = result.payload or result.data or {}
                    results_by_scope[slug] = payload.get("results", [])
                else:
                    results_by_scope[slug] = []
            except Exception as exc:
                logger.warning("[Phase17] Multi-scope search failed for %s: %s", slug, exc)
                results_by_scope[slug] = []
        return results_by_scope

    async def _multi_scope_search(
        self,
        query: str,
        scope_exprs: list[dict],
        max_results_per_scope: int = 5,
        doc_name_prefix: str | None = None,
    ) -> list[dict]:
        """Execute search across multiple scopes in parallel.

        Each scope gets its own ``RetrievalService`` instance with scoped
        config.  Results are tagged with ``deal_scope`` and
        ``doc_filter_applied`` for attribution.  Scores are normalised
        per-scope then merged.

        Args:
            query: User's query text.
            scope_exprs: List of ``{"slug": str, "doc_filter": str|None, "kts_path": str}``.
            max_results_per_scope: Results per deal.
            doc_name_prefix: Override doc filter if needed.

        Returns:
            Merged result list sorted by normalised score descending.
        """
        import asyncio
        from config.settings import scope_config

        sem = asyncio.Semaphore(
            getattr(self.config, 'phase17_max_parallel_scopes', 5)
        )
        timeout_ms = getattr(self.config, 'phase17_multi_scope_timeout_ms', 30000)

        async def _search_one(expr: dict) -> list[dict]:
            async with sem:
                loop = asyncio.get_event_loop()
                scfg = scope_config(self.config, expr.get("kts_path", ""))
                svc = RetrievalService(scfg)

                def _do_search():
                    return svc.execute({
                        "query": query,
                        "max_results": max_results_per_scope,
                        "doc_name_prefix": expr.get("doc_filter") or doc_name_prefix,
                        "scope_override": expr["slug"],
                    })

                result = await asyncio.wait_for(
                    loop.run_in_executor(None, _do_search),
                    timeout=timeout_ms / 1000.0,
                )
                hits: list[dict] = []
                if result and result.success:
                    payload = result.payload or result.data or {}
                    hits = payload.get("results", [])
                for hit in hits:
                    hit["deal_scope"] = expr["slug"]
                    hit["doc_filter_applied"] = expr.get("doc_filter", "")
                return hits

        tasks = [_search_one(expr) for expr in scope_exprs]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Merge and sort
        merged: list[dict] = []
        for r in all_results:
            if isinstance(r, Exception):
                logger.error("[Phase17] Multi-scope search error: %s", r)
                continue
            merged.extend(r)

        merged.sort(key=lambda h: h.get("score", 0), reverse=True)
        cap = max_results_per_scope * len(scope_exprs)
        return merged[:cap]

    def _select_graph_path(self, kb_path: str, doc_name_prefix: str | None) -> str:
        """Select deal-level or doc-level graph based on doc_name_prefix.

        If doc_name_prefix is present AND a doc-specific graph exists,
        use the doc graph for tighter traversal. Otherwise fall back
        to the deal-level graph.
        """
        import os
        if doc_name_prefix and getattr(self.config, 'phase17_graph_routing_enabled', True):
            doc_graph_path = os.path.join(
                kb_path, "graph", "doc_graphs", f"{doc_name_prefix}.json"
            )
            if os.path.exists(doc_graph_path):
                logger.info("[Phase17] Using doc-specific graph: %s", doc_graph_path)
                return doc_graph_path

        # Default: deal-level graph
        return getattr(self.config, 'graph_path', os.path.join(kb_path, "graph", "knowledge_graph.json"))

    # ------------------------------------------------------------------
    # Phase 6: Iterative Multi-Hop Retrieval (with regime routing)
    # ------------------------------------------------------------------
    def _phase6_retrieve(self, query: str, *, max_results: int = 10, extra_queries: list | None = None, doc_type_filter: str | None = None, scope: str | None = None, conversation_history: list | None = None, doc_name_prefix: str | None = None) -> dict | None:
        """Run Phase 6 retrieval, routing to the optimal strategy per regime.

        Phase 13.5 regime-aware routing:
            GOVERNING_DOC_LEGAL → Graph-first  (HumanLikeRetriever)
            GENERIC_GUIDE       → Vector-first (GuideRetriever)
            MIXED               → Query-intent heuristic selects strategy

        Phase 12 additions:
            doc_type_filter: Optional doc-type metadata filter.
            scope:           Optional scope slug for scoped collection routing.

        Phase 17 additions:
            doc_name_prefix: Optional doc-level filter (e.g., "PSA").
        """
        from backend.common.config_phase6 import Phase6Config
        from backend.vector.dual_vector_store import DualVectorStore
        from backend.retrieval.iterative_orchestrator import IterativeOrchestrator

        kb_path = getattr(self.config, 'knowledge_base_path', '.kts')
        use_human_like = getattr(self.config, 'human_like_retrieval', True)  # Default ON

        # ── Phase 13.4: HyDE query expansion ─────────────────────
        # Generate a hypothetical answer paragraph and use it as the query
        # for embedding, bridging vocabulary mismatch on definition queries.
        hyde_result = None
        effective_query = query
        if self._hyde_processor:
            try:
                hyde_result = self._hyde_processor.process_sync(query)
                if hyde_result.hyde_applied:
                    effective_query = hyde_result.query_for_embedding
                    logger.info(
                        "[Phase13.4] HyDE applied: hypothetical=%d chars for query: '%s'",
                        len(hyde_result.hypothetical or ""), query[:60],
                    )
            except Exception as exc:
                logger.debug("[Phase13.4] HyDE skipped: %s", exc)

        # ── Phase 13.5: Regime-aware strategy selection ───────────
        corpus_regime = self._resolve_corpus_regime()
        use_guide = use_human_like and self._should_use_guide_strategy(effective_query, corpus_regime)

        if use_guide:
            logger.info(
                "[Phase13.5] Regime=%s → vector-first GuideRetriever for query: %s",
                corpus_regime, query[:80],
            )
            result = self._guide_retrieve(effective_query, kb_path=kb_path, max_results=max_results, doc_name_prefix=doc_name_prefix)
            if result and hyde_result:
                result["hyde"] = hyde_result.to_dict()
            return result

        if use_human_like:
            logger.info(
                "[Phase13.5] Regime=%s → graph-first HumanLikeRetriever for query: %s",
                corpus_regime, query[:80],
            )
            # Extract defined terms from prior conversation turns for
            # follow-up enrichment (so nested terms like Certificate
            # Principal Balance get resolved even in follow-ups)
            prior_terms = self._extract_terms_from_history(conversation_history or [])
            result = self._human_like_retrieve(
                effective_query,
                kb_path=kb_path,
                max_results=max_results,
                extra_queries=extra_queries,
                prior_context_terms=prior_terms,
                doc_name_prefix=doc_name_prefix,
            )
            if result and hyde_result:
                result["hyde"] = hyde_result.to_dict()
            return result

        # Fallback: IterativeOrchestrator (non-human-like mode)
        phase6_cfg = Phase6Config(
            enabled=True,
            chroma_dir=getattr(self.config, 'phase6_chroma_dir', f'{kb_path}/vectors/phase6'),
            max_iterations=getattr(self.config, 'phase6_max_iterations', 5),
            min_confidence=getattr(self.config, 'phase6_min_confidence', 0.85),
            min_improvement=getattr(self.config, 'phase6_min_improvement', 0.05),
            result_threshold=getattr(self.config, 'phase6_result_threshold', 0.70),
            content_weight=getattr(self.config, 'phase6_content_weight', 0.6),
            pagerank_weight=getattr(self.config, 'phase6_pagerank_weight', 0.2),
            graph_proximity_weight=getattr(self.config, 'phase6_graph_proximity_weight', 0.2),
            pagerank_alpha=getattr(self.config, 'phase6_pagerank_alpha', 0.85),
            bfs_depth_limit=getattr(self.config, 'phase6_bfs_depth', 2),
            verbose_logging=getattr(self.config, 'phase6_verbose_logging', True),
        )

        dual_store = DualVectorStore(phase6_cfg.chroma_dir, embedding_provider=self._embedding_provider)
        graph = self.graph_store.load()

        orchestrator = IterativeOrchestrator(dual_store, graph, phase6_cfg, kb_path=kb_path)
        return orchestrator.retrieve(query, max_results=max_results)
    
    @staticmethod
    def _extract_terms_from_history(
        conversation_history: list[dict],
        max_turns: int = 3,
    ) -> list[str]:
        """Extract capitalized defined terms from recent assistant turns.

        Returns a deduplicated list of Title Case multi-word terms that
        are likely defined terms (e.g. "Certificate Principal Balance").
        """
        import re as _re
        terms: list[str] = []
        seen: set[str] = set()
        common = {"The", "This", "That", "A", "An", "Each", "Any", "Such",
                  "Section", "Article", "In", "For", "By", "With", "From", "To"}

        for turn in conversation_history[-max_turns:]:
            role = turn.get("role", turn.get("name", ""))
            if role not in ("assistant", "model"):
                continue
            text = turn.get("content", turn.get("message", ""))
            if not text:
                continue
            # Pattern for capitalized multi-word terms
            for m in _re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', text):
                # Strip leading articles
                parts = m.split()
                while parts and parts[0] in common:
                    parts = parts[1:]
                term = " ".join(parts)
                if term and len(term) > 3 and term.lower() not in seen:
                    seen.add(term.lower())
                    terms.append(term)
        return terms

    def _human_like_retrieve(self, query: str, *, kb_path: str, max_results: int = 10, extra_queries: list[str] | None = None, prior_context_terms: list[str] | None = None, doc_name_prefix: str | None = None) -> dict | None:
        """Run human-like Graph-First retrieval.

        Phase 17: doc_name_prefix is forwarded to the HumanLikeRetriever
        and also used for graph selection (doc graph vs deal graph).
        """
        from backend.vector.dual_vector_store import DualVectorStore
        from backend.retrieval.human_like_retriever import HumanLikeRetriever, RetrievalConfig
        
        # Load dual store and graph
        chroma_dir = getattr(self.config, 'phase6_chroma_dir', f'{kb_path}/vectors/phase6')
        dual_store = DualVectorStore(chroma_dir, embedding_provider=self._embedding_provider)

        # Phase 17: Graph selection — use doc-specific graph when available
        graph_path = self._select_graph_path(kb_path, doc_name_prefix)
        _graph_store = GraphStore(graph_path)
        graph = _graph_store.load()
        
        # Configure retriever
        config = RetrievalConfig(
            enable_self_query_filters=getattr(self.config, 'self_query_filters', True),
            enable_query_decomposition=getattr(self.config, 'query_decomposition', True),
            graph_keyword_search=getattr(self.config, 'graph_first_lookup', True),
            section_scoped_search=getattr(self.config, 'section_scoped_search', True),
            inject_definitions=getattr(self.config, 'definition_enrichment', True),
            use_cross_encoder=getattr(self.config, 'cross_encoder_enabled', True),
            items_per_section=getattr(self.config, 'items_per_section', 10),
        )
        
        retriever = HumanLikeRetriever(dual_store, graph, config)

        # Phase 8.1: BM25 hybrid — load or build BM25 index
        bm25 = None
        if getattr(self.config, 'enable_bm25_hybrid', False):
            try:
                from backend.retrieval.bm25_retriever import BM25Retriever
                bm25 = BM25Retriever(
                    persist_dir=chroma_dir,
                    k1=getattr(self.config, 'bm25_k1', 1.5),
                    b=getattr(self.config, 'bm25_b', 0.75),
                )
                if not bm25.load_index():
                    # Auto-build from ChromaDB items
                    items = dual_store.get_document_chunks("*") if hasattr(dual_store, 'get_document_chunks') else []
                    if not items:
                        # Fallback: pull all items from item_collection
                        try:
                            all_data = dual_store.item_collection.get(include=["documents", "metadatas"])
                            items = [
                                {"id": all_data["ids"][i], "content": all_data["documents"][i],
                                 "metadata": all_data["metadatas"][i]}
                                for i in range(len(all_data["ids"]))
                            ]
                        except Exception:
                            items = []
                    if items:
                        docs_for_bm25 = [
                            {"id": it.get("id", ""), "content": it.get("text", it.get("content", ""))}
                            for it in items
                        ]
                        bm25.build_index(docs_for_bm25)
                        bm25.save_index()
            except Exception as exc:
                logger.debug("[Phase8] BM25 init failed, continuing without: %s", exc)
                bm25 = None

        result = retriever.retrieve(
            query,
            max_results=max_results,
            bm25_retriever=bm25,
            config=self.config,
            extra_queries=extra_queries,
            prior_context_terms=prior_context_terms,
            doc_name_prefix=doc_name_prefix,
        )
        
        # Convert to standard Phase 6 result format
        return {
            "results": result.results,
            "confidence": result.confidence,
            "iterations": 1,  # Human-like is single-pass
            "trace": result.trace,
            "strategy": "graph_first_legal",
            "definitions_glossary": result.definitions_glossary,
            "entity_roles": result.entity_roles,
        }

    def _guide_retrieve(self, query: str, *, kb_path: str, max_results: int = 10, doc_name_prefix: str | None = None) -> dict | None:
        """Run vector-first retrieval optimised for guide / troubleshooting docs.

        Phase 13.5: Selected automatically when corpus_regime is GENERIC_GUIDE
        or when query intent is non-legal in a MIXED corpus.
        Phase 17: doc_name_prefix forwarded for document-level filtering.
        Phase 19: Merges results from NonLegalTripleStore + troubleshooting graph.
        """
        from backend.vector.dual_vector_store import DualVectorStore
        from backend.retrieval.guide_retriever import GuideRetriever, GuideRetrievalConfig

        chroma_dir = getattr(self.config, 'phase6_chroma_dir', f'{kb_path}/vectors/phase6')
        dual_store = DualVectorStore(chroma_dir, embedding_provider=self._embedding_provider)
        graph = self.graph_store.load()

        config = GuideRetrievalConfig(
            items_top_k=getattr(self.config, 'guide_items_top_k', 30),
            sections_top_k=getattr(self.config, 'guide_sections_top_k', 10),
            graph_expansion_enabled=getattr(self.config, 'guide_graph_expansion', True),
            bfs_depth=getattr(self.config, 'guide_bfs_depth', 2),
            error_code_boost=getattr(self.config, 'guide_error_code_boost', 0.35),
            use_cross_encoder=getattr(self.config, 'cross_encoder_enabled', True),
            step_sequence_ordering=getattr(self.config, 'guide_step_ordering', True),
            enable_query_decomposition=getattr(self.config, 'query_decomposition', True),
        )

        retriever = GuideRetriever(dual_store, graph, config)
        result = retriever.retrieve(query, max_results=max_results)

        base_results = result.results
        trace = dict(result.trace) if isinstance(result.trace, dict) else {"guide": result.trace}

        # ── Phase 19: Non-legal triple-store augmentation ─────────
        triple_store_results = []
        if getattr(self.config, 'nonlegal_triple_store_enabled', False):
            try:
                from backend.vector.nonlegal_triple_store import NonLegalTripleStore
                triple_store = NonLegalTripleStore(chroma_dir, embedding_provider=self._embedding_provider)
                triple_store_results = triple_store.search(query, top_k=max_results)
                trace["phase19_triple_store_hits"] = len(triple_store_results)
                logger.info(
                    "[Phase19] Triple-store returned %d results for: %s",
                    len(triple_store_results), query[:80],
                )
            except Exception as exc:
                logger.debug("[Phase19] Triple-store query failed: %s", exc)

        # ── Phase 19: Troubleshooting graph traversal ─────────────
        ts_context_text = ""
        if getattr(self.config, 'troubleshooting_graph_enabled', False):
            try:
                from backend.graph.troubleshooting_traversal import resolve_troubleshooting_context
                from backend.graph.persistence import GraphStore as _GraphStore

                ts_graph_path = getattr(self.config, 'troubleshooting_graph_path', '')
                if not ts_graph_path:
                    ts_graph_path = str(Path(kb_path) / "graph" / "troubleshooting_graph.json")

                if Path(ts_graph_path).exists():
                    ts_store = _GraphStore(ts_graph_path)
                    ts_graph = ts_store.load()
                    ts_context = resolve_troubleshooting_context(ts_graph, query)
                    if ts_context.has_results:
                        ts_context_text = ts_context.formatted_text
                        trace["phase19_ts_paths"] = len(ts_context.results)
                        trace["phase19_ts_tokens"] = ts_context.token_count
                        logger.info(
                            "[Phase19] Troubleshooting graph: %d paths, %d tokens",
                            len(ts_context.results), ts_context.token_count,
                        )
            except Exception as exc:
                logger.debug("[Phase19] Troubleshooting graph traversal failed: %s", exc)

        # ── Merge: triple-store results into base results ─────────
        if triple_store_results:
            # Convert triple-store format to guide-result format
            seen_ids = {r.get("id", "") for r in base_results}
            for ts_hit in triple_store_results:
                if ts_hit["id"] not in seen_ids:
                    base_results.append({
                        "id": ts_hit["id"],
                        "text": ts_hit.get("text", ""),
                        "score": ts_hit.get("similarity", 0.0),
                        "metadata": ts_hit.get("metadata", {}),
                        "source": f"triple_store:{ts_hit.get('store', 'unknown')}",
                    })
                    seen_ids.add(ts_hit["id"])

        # ── Phase 19: Unified cross-encoder rerank on merged results ─
        # GuideRetriever already ran cross-encoder on DualVectorStore
        # results, but triple-store results were merged after that pass.
        # Re-score the whole pool so triple-store hits compete fairly.
        if triple_store_results and getattr(self.config, 'cross_encoder_enabled', True):
            try:
                from backend.retrieval.cross_encoder import rerank as _ce_rerank
                base_results = _ce_rerank(query, base_results, content_key="text")
                base_results.sort(
                    key=lambda r: r.get("cross_encoder_score", 0),
                    reverse=True,
                )
                trace["phase19_unified_rerank"] = True
                trace["phase19_reranked_count"] = len(base_results)
                logger.info(
                    "[Phase19] Unified cross-encoder rerank on %d merged results",
                    len(base_results),
                )
            except Exception as exc:
                logger.debug("[Phase19] Unified rerank failed: %s", exc)
                # Fallback: simple score-based sort
                base_results.sort(
                    key=lambda r: r.get("score", r.get("similarity", 0)),
                    reverse=True,
                )

        # Truncate after reranking
        base_results = base_results[:max_results]

        # ── Prepend troubleshooting context as a synthetic result ──
        if ts_context_text:
            base_results.insert(0, {
                "id": "_ts_graph_context",
                "text": ts_context_text,
                "score": 1.0,
                "metadata": {"source": "troubleshooting_graph", "synthetic": True},
                "source": "troubleshooting_graph",
            })

        return {
            "results": base_results,
            "confidence": result.confidence,
            "iterations": 1,
            "trace": trace,
            "strategy": "vector_first_guide_phase19",
        }

    # ── Hybrid Retrieval Engine (public API) ───────────────────────────

    def hybrid_search(
        self,
        query: str,
        *,
        top_k: int = 10,
        scope: Optional[str] = None,
        doc_type_filter: Optional[str] = None,
        include_graph: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Three-signal hybrid search: dense vector + BM25 sparse + graph expansion.

        This is the primary retrieval entry-point for financial and legal
        documents.  It fuses all three signals via Reciprocal Rank Fusion,
        applies financial/legal domain boosts, and optionally re-ranks with
        a cross-encoder.

        Falls back to plain vector search if the hybrid engine is unavailable.

        Parameters
        ----------
        query : str
            Natural-language query (financial/legal domain).
        top_k : int
            Number of results to return.
        scope : str | None
            Deal scope identifier (e.g. ``"bear_stearns_2006_he1"``).
        doc_type_filter : str | None
            Optional filter to a single document type.
        include_graph : bool
            Whether to use graph-expansion as the third retrieval signal.

        Returns
        -------
        List[Dict]
            Ranked list of result dicts with keys:
            chunk_id, content, score, rrf_score, vector_rank, bm25_rank,
            graph_rank, metadata, retrieval_signals.
        """
        if self._hybrid_engine is not None:
            try:
                return self._hybrid_engine.retrieve(
                    query,
                    top_k=top_k,
                    scope=scope,
                    doc_type_filter=doc_type_filter,
                    include_graph=include_graph,
                )
            except Exception as exc:
                logger.warning("[HybridEngine] retrieve() failed, using fallback: %s", exc)

        # Fallback: plain vector search
        try:
            raw = self.vector_store.search(
                query, top_k=top_k, doc_type_filter=doc_type_filter, scope=scope
            )
            return raw or []
        except Exception as exc:
            logger.error("[HybridEngine] Fallback vector search also failed: %s", exc)
            return []

    def rebuild_bm25_index(self) -> bool:
        """Rebuild the BM25 index from current vector store contents.

        Call this after a fresh ingestion batch to keep BM25 in sync.

        Returns True if successful, False otherwise.
        """
        if self._hybrid_engine is None:
            return False
        try:
            # Pull all chunks from the vector store for BM25 indexing
            def _get_chunks():
                raw = self.vector_store.search("", top_k=50_000)
                return raw or []

            return self._hybrid_engine.load_or_build_bm25_index(_get_chunks)
        except Exception as exc:
            logger.warning("[HybridEngine] BM25 rebuild failed: %s", exc)
            return False

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

        # ── Phase 11.3: Progress callback for SSE streaming ───────
        progress_callback = request.get("progress_callback")
        def _emit_progress(message: str) -> None:
            """Send progress message to client if callback is provided and SSE is enabled."""
            if progress_callback and callable(progress_callback) and getattr(self.config, 'sse_progress_enabled', True):
                try:
                    progress_callback(message)
                except Exception:
                    pass  # Never fail on progress

        _emit_progress(f"Parsing query: {query[:80]}...")

        # ── Phase 10.1/10.2: Session memory & query rewriting ─────
        session_id = request.get("session_id", "default")
        conversation_history = request.get("conversation_history", [])
        retrieval_mode = request.get("retrieval_mode")  # extract, audit, summary, compare, define

        # Phase 10.2: Rewrite follow-up queries with coreference resolution
        original_query = query
        if self._query_rewriter and conversation_history:
            try:
                rw_result = self._query_rewriter.rewrite_sync(query, conversation_history)
                if rw_result.was_rewritten:
                    logger.info("[Phase10.2] Query rewritten: '%s' → '%s'", query[:60], rw_result.rewritten_query[:60])
                    query = rw_result.rewritten_query
            except Exception as exc:
                logger.debug("[Phase10.2] Query rewriting skipped: %s", exc)

        # Phase 14.1: Cache-first retrieval from session deal summary
        cached_terms: dict = {}
        if self._session_memory and getattr(self.config, 'deal_summary_cache_enabled', True):
            try:
                mem = self._session_memory.get_or_create(session_id)
                # Use Phase 13 entity extraction for proper multi-word terms
                requested_terms = extract_entities(query)
                for term in requested_terms:
                    cached_val = mem.get_cached_term(term)
                    if cached_val:
                        cached_terms[term] = cached_val
                if cached_terms:
                    logger.info("[Phase14.1] Cache hit for %d terms: %s", len(cached_terms), list(cached_terms.keys()))
            except Exception as exc:
                logger.debug("[Phase14.1] Cache lookup skipped: %s", exc)

        # ── Phase 12.4: Scope Routing ──────────────────────────────
        scope_override = request.get("scope_override") or request.get("scope", "")
        resolved_scope = ""  # Phase 12: effective scope slug for all downstream searches
        if scope_override and getattr(self.config, 'per_folder_kts_enabled', True):
            router = self._get_scope_router()
            routing = router.route(query, explicit_scope=scope_override, doc_type_filter=doc_type_filter)
            if routing.needs_user_clarification:
                return AgentResult(
                    success=True,
                    data={"message": routing.message, "needs_scope_clarification": True},
                )
            if routing.is_single_scope and routing.scopes[0].match_type != "fallback":
                resolved_scope = routing.scopes[0].slug
            logger.info("[Phase12] Scope routing: %s → %s", scope_override, routing.slugs)

        # ── Phase 15.1: Cross-Deal Comparison (/compare) ──────────
        if retrieval_mode == "compare" and self._comparison_mode:
            try:
                compare_scopes = request.get("compare_scopes", [])
                concept = query
                router = self._get_scope_router()
                if compare_scopes and router:
                    import asyncio
                    # Fan-out search across target scopes
                    async def _search_scope(q, slug, k):
                        return self.vector_store.search(q, top_k=k, scope=slug)
                    fed_results = asyncio.get_event_loop().run_until_complete(
                        router.federated_search(
                            concept, compare_scopes,
                            search_fn=_search_scope,
                            top_k=self._comparison_mode.top_k_per_scope,
                        )
                    )
                    scope_chunks = {
                        fr.scope_slug: fr.chunks
                        for fr in fed_results if not fr.error
                    }
                    # Run comparison
                    comparison = asyncio.get_event_loop().run_until_complete(
                        self._comparison_mode.compare(concept, scope_chunks)
                    )
                    payload = {
                        "comparison_result": comparison.to_dict(),
                        "retrieval_mode": "compare",
                    }
                    # Phase 15.2: Contradiction detection on comparison results
                    if self._contradiction_detector and comparison.definitions:
                        defs = {d.scope_slug: d.text for d in comparison.definitions}
                        contradictions = asyncio.get_event_loop().run_until_complete(
                            self._contradiction_detector.detect_batch(concept, defs)
                        )
                        payload["contradictions"] = [c.to_dict() for c in contradictions]
                    return AgentResult(success=True, data=payload)
                else:
                    logger.info("[Phase15.1] /compare requires scopes — falling through to standard retrieval")
            except Exception as exc:
                logger.warning("[Phase15.1] Comparison failed, falling through: %s", exc)

        # ── Phase 14.3: Structured Extraction (/extract) ──────────
        if retrieval_mode == "extract" and self._extraction_mode:
            try:
                import asyncio
                # Retrieve chunks first using standard vector search
                extract_chunks = self.vector_store.search(
                    query=query,
                    top_k=self._extraction_mode.config.chunk_budget,
                    doc_type_filter=request.get("doc_type_filter"),
                    scope=resolved_scope or None,
                )
                extract_result = asyncio.get_event_loop().run_until_complete(
                    self._extraction_mode.extract(extract_chunks)
                )
                payload = {
                    "extraction_result": extract_result.to_dict(),
                    "retrieval_mode": "extract",
                }
                # Include temporal context if available
                if self._temporal_reasoner:
                    payload["temporal_context"] = self._temporal_reasoner.get_temporal_context()
                # Update session memory with extracted data
                if self._session_memory and extract_result.parsed_ok:
                    try:
                        data = extract_result.data
                        mem = self._session_memory.get_or_create(session_id)
                        mem.deal_summary.update_from_answer(
                            terms=data.get("defined_terms"),
                            parties=data.get("parties"),
                            dates=data.get("key_dates"),
                            amounts=data.get("key_amounts"),
                            sections=data.get("source_sections"),
                        )
                    except Exception:
                        pass
                return AgentResult(success=True, data=payload)
            except Exception as exc:
                logger.warning("[Phase14.3] Extraction failed, falling through: %s", exc)

        # ── Phase 14.4: Deal Summary (/summary) ───────────────────
        if retrieval_mode == "summary" and self._summary_mode:
            try:
                import asyncio
                scope = request.get("scope_override") or request.get("scope", "")
                summary_chunks = self.vector_store.search(
                    query=query or "deal overview parties dates amounts obligations",
                    top_k=self._summary_mode.config.chunk_budget,
                    doc_type_filter=request.get("doc_type_filter"),
                    scope=resolved_scope or None,
                )
                summary_result = asyncio.get_event_loop().run_until_complete(
                    self._summary_mode.summarize(scope=scope, chunks=summary_chunks)
                )
                payload = {
                    "summary_result": summary_result.to_dict(),
                    "retrieval_mode": "summary",
                }
                if self._temporal_reasoner:
                    payload["temporal_context"] = self._temporal_reasoner.get_temporal_context()
                return AgentResult(success=True, data=payload)
            except Exception as exc:
                logger.warning("[Phase14.4] Summary failed, falling through: %s", exc)

        # ── Phase 11.4: Audit Mode (/audit) ───────────────────────
        if retrieval_mode == "audit" and self._audit_mode:
            try:
                import asyncio
                audit_chunks = self.vector_store.search(
                    query=query,
                    top_k=self._audit_mode.config.chunk_budget,
                    doc_type_filter=request.get("doc_type_filter"),
                    scope=resolved_scope or None,
                )
                audit_result = asyncio.get_event_loop().run_until_complete(
                    self._audit_mode.audit(query, audit_chunks)
                )
                payload = {
                    "audit_result": audit_result.to_dict(),
                    "retrieval_mode": "audit",
                }
                return AgentResult(success=True, data=payload)
            except Exception as exc:
                logger.warning("[Phase11.4] Audit failed, falling through: %s", exc)

        # ── Phase 11.4: Definition Mode (/define) ─────────────────
        if retrieval_mode == "define" and self._definition_mode:
            try:
                import asyncio
                define_chunks = self.vector_store.search(
                    query=query,
                    top_k=self._definition_mode.config.chunk_budget,
                    doc_type_filter=request.get("doc_type_filter"),
                    scope=resolved_scope or None,
                )
                define_result = asyncio.get_event_loop().run_until_complete(
                    self._definition_mode.define(query, define_chunks)
                )
                payload = {
                    "definition_result": define_result.to_dict(),
                    "retrieval_mode": "define",
                }
                return AgentResult(success=True, data=payload)
            except Exception as exc:
                logger.warning("[Phase11.4] Definition failed, falling through: %s", exc)

        # Phase 17: Mode extraction (from scope resolver or CLI --mode)
        phase17_mode = request.get("phase17_mode") or request.get("mode", "search")
        phase17_scopes = request.get("phase17_scopes") or []
        if retrieval_mode and retrieval_mode != "search":
            phase17_mode = retrieval_mode  # Legacy mode takes precedence

        # ── Phase 17: /diff mode ──────────────────────────────────
        if phase17_mode == "diff" and getattr(self.config, 'phase17_diff_mode_enabled', True):
            try:
                from backend.agents.diff_engine import DiffEngine
                engine = DiffEngine(config=self.config)
                results_by_scope = self._collect_multi_scope_results(
                    query, phase17_scopes, max_results,
                    doc_name_prefix=request.get("doc_name_prefix"),
                )
                diff_result = engine.diff(results_by_scope, query)
                return AgentResult(
                    success=True,
                    data={"diff_result": diff_result, "retrieval_mode": "diff"},
                )
            except Exception as exc:
                logger.warning("[Phase17] /diff mode failed, falling through: %s", exc)

        # ── Phase 17: /aggregate mode ─────────────────────────────
        if phase17_mode == "aggregate" and getattr(self.config, 'phase17_aggregate_mode_enabled', True):
            try:
                from backend.agents.aggregation_engine import AggregationEngine
                engine = AggregationEngine(config=self.config)
                results_by_scope = self._collect_multi_scope_results(
                    query, phase17_scopes, max_results,
                    doc_name_prefix=request.get("doc_name_prefix"),
                )
                agg_result = engine.aggregate(results_by_scope, query)
                return AgentResult(
                    success=True,
                    data={"aggregation_result": agg_result, "retrieval_mode": "aggregate"},
                )
            except Exception as exc:
                logger.warning("[Phase17] /aggregate mode failed, falling through: %s", exc)

        # ── Phase 17: /list mode ──────────────────────────────────
        if phase17_mode == "list":
            try:
                from backend.vector.deal_catalog import DealCatalog
                catalog_path = getattr(self.config, 'deal_catalog_path', '')
                catalog = DealCatalog(db_path=catalog_path)
                if phase17_scopes:
                    # List specific deals matching the scopes
                    deals = []
                    for scope in phase17_scopes:
                        deals.extend(catalog.search_deals(pattern=scope))
                else:
                    deals = catalog.list_all_deals()
                return AgentResult(
                    success=True,
                    data={"deals": deals, "retrieval_mode": "list"},
                )
            except Exception as exc:
                logger.warning("[Phase17] /list mode failed: %s", exc)
                return AgentResult(success=False, data={"error": str(exc)})

        # ── Phase 6: Primary Iterative Multi-Hop Retrieval ─────────
        # Phase 6 is now ALWAYS the primary retrieval path. It provides:
        # - Query expansion with term registry
        # - Dual store search (items + sections)
        # - Graph-based multi-hop traversal
        # - Hybrid re-ranking (PageRank + proximity)
        # - Confidence-targeted iteration
        # - Full explainability trace
        phase6_trace = None
        extra_queries = request.get("extra_queries") or []
        # Phase 17: Extract doc_name_prefix for document-level isolation
        doc_name_prefix = request.get("doc_name_prefix") or None
        if doc_name_prefix and getattr(self.config, 'phase17_doc_filter_enabled', True):
            logger.info("[Phase17] doc_name_prefix filter active: %s", doc_name_prefix)
        elif doc_name_prefix:
            doc_name_prefix = None  # Feature disabled
        _emit_progress(f"Searching knowledge base...")
        try:
            # ── Phase 18: Auto-scope federation ───────────────────
            # When per-folder isolation is active (Phase 12.1), the root
            # .kts has no vectors.  Detect this and fan-out across all
            # discovered scope directories automatically.
            use_federation = False
            auto_scopes: list[tuple[str, str]] = []
            if not resolved_scope:
                auto_scopes = self._discover_scope_kts_paths()
                if auto_scopes:
                    use_federation = True
                    _emit_progress(f"Searching {len(auto_scopes)} scope(s)...")

            if use_federation:
                phase6_result = self._federated_scope_retrieve(
                    query, auto_scopes,
                    max_results=max_results,
                    extra_queries=extra_queries or None,
                    doc_type_filter=doc_type_filter,
                    conversation_history=conversation_history,
                    doc_name_prefix=doc_name_prefix,
                )
            elif resolved_scope:
                # Phase 18-fix: When an explicit scope is resolved, route
                # through single-scope federation so that kb_path points
                # to the correct per-folder .kts/ (not the root .kts/).
                scope_kts = self._resolve_scope_kts_path(resolved_scope)
                if scope_kts:
                    phase6_result = self._federated_scope_retrieve(
                        query, [(resolved_scope, scope_kts)],
                        max_results=max_results,
                        extra_queries=extra_queries or None,
                        doc_type_filter=doc_type_filter,
                        conversation_history=conversation_history,
                        doc_name_prefix=doc_name_prefix,
                    )
                else:
                    # Scope resolved but no .kts/ found — fall back to root
                    phase6_result = self._phase6_retrieve(
                        query, max_results=max_results,
                        extra_queries=extra_queries or None,
                        doc_type_filter=doc_type_filter,
                        scope=resolved_scope,
                        conversation_history=conversation_history,
                        doc_name_prefix=doc_name_prefix,
                    )
            else:
                phase6_result = self._phase6_retrieve(
                    query, max_results=max_results,
                    extra_queries=extra_queries or None,
                    doc_type_filter=doc_type_filter,
                    scope=None,
                    conversation_history=conversation_history,
                    doc_name_prefix=doc_name_prefix,
                )
            if phase6_result and phase6_result.get("results"):
                _emit_progress(f"Reranking {len(phase6_result['results'])} candidates...")
                phase6_trace = phase6_result.get("trace")
                logger.info(
                    "[Phase6-Retrieval] %d results in %d iterations (confidence=%.3f)",
                    len(phase6_result["results"]),
                    phase6_result.get("iterations", 0),
                    phase6_result.get("confidence", 0),
                )
                
                # Convert Phase 6 results to standard SearchResult + citations
                return self._build_phase6_response(
                    request=request,
                    phase6_result=phase6_result,
                    query=query,
                    strict_mode=strict_mode,
                    generated_answer=generated_answer,
                    disable_term_resolution=disable_term_resolution,
                )
        except Exception as exc:
            logger.warning("[Phase6-Retrieval] Failed, falling back to legacy: %s", exc)
            # Fall through to legacy pipeline

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
                    doc_type_filter=doc_type_filter,
                    scope=resolved_scope or None,
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
                doc_type_filter=doc_type_filter,
                scope=resolved_scope or None,
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

        # ── Phase 10.3: Apply document bias for in-context documents ──
        if self._session_memory and getattr(self.config, 'session_memory_enabled', True):
            try:
                session = self._session_memory.get_or_create(session_id)
                if session.active_documents:
                    rows = apply_document_bias(rows, session, score_key="_rerank_score")
                    logger.debug("[Phase10.3] Applied document bias for %d active docs", len(session.active_documents))
            except Exception as exc:
                logger.debug("[Phase10.3] Document bias skipped: %s", exc)

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
                    uri="file:///" + source_path.replace("\\\\", "/"),
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

        # ── Phase 9.3: Inject critique questions into payload (legacy) ─
        try:
            kb_path_cq = getattr(self.config, 'knowledge_base_path', '.kts')
            cq_gen = CritiqueQuestionGenerator.__new__(CritiqueQuestionGenerator)
            unique_doc_ids = {c.doc_id for c in chunks if c.doc_id}
            critique_stores = {}
            for did in unique_doc_ids:
                loaded = cq_gen.load(did, kb_path_cq)
                if loaded:
                    critique_stores[did] = loaded
            if critique_stores:
                chunk_dicts = [{"doc_id": c.doc_id, "section_id": getattr(c, "section_id", "sec000")} for c in chunks]
                merged_cqs = merge_critique_questions(chunk_dicts, critique_stores)
                payload["critique_questions"] = [
                    {"id": q.id, "question": q.question, "trigger_keywords": q.trigger_keywords,
                     "trigger_logic": q.trigger_logic, "priority": q.priority}
                    for q in merged_cqs
                ]
                logger.info("[Phase9.3] Injected %d critique questions from %d docs (legacy)", len(merged_cqs), len(critique_stores))
        except Exception as exc:
            logger.debug("[Phase9.3] Critique question injection skipped (legacy): %s", exc)

        # ── Phase 13.1: Confidence scoring (legacy path) ──────────
        if getattr(self.config, 'confidence_scoring_enabled', True) and rows:
            try:
                confidence_result = self._confidence_scorer.score(rows, score_key="_rerank_score")
                payload["confidence_tier"] = {
                    "tier": confidence_result.tier.value,
                    "display": confidence_result.display_text,
                    "top_score": confidence_result.top_score,
                    "n_direct_matches": confidence_result.n_direct_matches,
                }
            except Exception as exc:
                logger.debug("[Phase13.1] Confidence scoring skipped: %s", exc)

        # ── Phase 13.2: Gap detection (legacy path) ───────────────
        if getattr(self.config, 'gap_detection_enabled', True) and rows:
            try:
                gap_result = self._gap_detector.detect(query, rows, content_key="content")
                if gap_result.has_gaps:
                    payload["gap_alert"] = {
                        "missing_terms": gap_result.gaps,
                        "display": gap_result.display_text,
                    }
            except Exception as exc:
                logger.debug("[Phase13.2] Gap detection skipped: %s", exc)

        # ── Phase 14.2: Temporal context (legacy path) ─────────────
        if self._temporal_reasoner:
            payload["temporal_context"] = self._temporal_reasoner.get_temporal_context()
            if self._temporal_reasoner.is_temporal_query(query):
                payload["temporal_evaluation"] = self._temporal_reasoner.get_temporal_evaluation_instruction()

        # ── Phase 14.1: Update session memory with results ─────────
        if self._session_memory and chunks:
            try:
                answer_text = generated_answer or ""
                self._session_memory.update_from_answer(
                    session_id, answer_text,
                    [{"content": c.content, "source": c.source_path} for c in chunks],
                )
                # Phase 10.4: Store verbatim turns and trigger summarization
                if getattr(self.config, 'history_summarization_enabled', True):
                    session = self._session_memory.get_or_create(session_id)
                    # Store verbatim turns from the conversation history
                    for turn in conversation_history[-2:]:
                        if isinstance(turn, dict) and turn.get("content"):
                            session.verbatim_recent_turns.append(turn)
                    # Check if summarization compression is needed
                    if should_summarise(session):
                        prompt = build_summary_prompt(session)
                        if prompt:
                            # NOTE: Backend is stateless — no LLM available here.
                            # Heuristic extraction preserves key facts from turns
                            # being compressed (terms, dates, entities).  When an
                            # LLM callable is available, `prompt` can be sent to it
                            # for higher-quality compression.
                            compressed = _heuristic_summarise(
                                session.rolling_summary,
                                session.verbatim_recent_turns[:4],
                            )
                            apply_summary(session, compressed)
                            logger.debug("[Phase10.4] Applied history summarization for session %s", session_id)
            except Exception as exc:
                logger.debug("[Phase14.1] Session memory update skipped: %s", exc)

        # ── Phase 10.3: Session document bias ─────────────────────
        if self._session_memory and cached_terms:
            payload["cached_terms"] = cached_terms

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
