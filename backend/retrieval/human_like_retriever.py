"""
Human-Like Retrieval Strategy for Legal Documents.

Mimics how a human reads legal docs:
1. Graph-First: Query graph for relevant sections (like TOC lookup)
2. Section-Scoped Search: Search items within identified sections
3. Definition Enrichment: Inject term definitions into context
4. Cross-Encoder Rerank: Final precision pass
5. Answer Synthesis: (optional) Rewrite with definitions inline

This strategy maximizes the dual vector store by using sections to scope
item searches, dramatically reducing search space and improving precision.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from backend.common.explainability import ExplainabilityLogger
from backend.retrieval.cross_encoder import rerank as cross_encoder_rerank
from backend.vector.dual_vector_store import DualVectorStore

logger = logging.getLogger(__name__)


@dataclass
class RetrievalConfig:
    """Configuration for human-like retrieval."""
    # Graph-first settings
    graph_keyword_search: bool = True
    max_section_candidates: int = 5
    
    # Section-scoped search
    section_scoped_search: bool = True
    items_per_section: int = 20
    min_chunks_per_section: int = 3         # floor guarantee per section
    max_chunks_per_doc: int = 25            # total budget (stratified)
    fallback_to_global: bool = True
    
    # Definition enrichment
    inject_definitions: bool = True
    max_definitions_per_chunk: int = 3
    definition_tree_token_budget: int = 50_000  # token budget for layered trees
    
    # Cross-encoder
    use_cross_encoder: bool = True
    
    # Confidence
    min_confidence: float = 0.7
    
    # Query processing
    enable_query_decomposition: bool = True
    enable_self_query_filters: bool = True


@dataclass
class RetrievalResult:
    """Result from human-like retrieval."""
    results: List[Dict[str, Any]]
    confidence: float
    trace: Dict[str, Any]
    enriched_context: Optional[str] = None
    definitions_glossary: str = ""          # Shared glossary block (sent once to LLM)
    entity_roles: List[Dict[str, str]] = field(default_factory=list)  # [{entity, term}, ...]


class HumanLikeRetriever:
    """
    Human-like retrieval strategy that mimics how humans read legal documents.
    
    Flow:
    1. Extract filters from query (section numbers, item types)
    2. Query graph for relevant sections (TOC-like lookup)
    3. Search items scoped to identified sections
    4. Enrich results with definitions from graph
    5. Cross-encoder rerank with enriched context
    """
    
    def __init__(
        self,
        dual_store: DualVectorStore,
        graph: nx.DiGraph,
        config: Optional[RetrievalConfig] = None,
    ) -> None:
        self.dual_store = dual_store
        self.graph = graph
        self.config = config or RetrievalConfig()
        
        # Build indexes for fast lookup
        self._section_index: Dict[str, str] = {}  # section_number -> node_id
        self._definition_index: Dict[str, str] = {}  # term (lowercase) -> node_id
        self._term_node_index: Dict[str, str] = {}  # term (lowercase) -> TERM:: node_id
        # Q1: keyword → list of TERM:: node_ids that have that keyword
        self._term_keyword_index: Dict[str, List[str]] = {}
        # NER: ASSIGNED_ROLE index — term_lower → [(entity_surface_form, entity_node_id)]
        self._role_index: Dict[str, List[Tuple[str, str]]] = {}
        # NER: entity surface_form_lower → set of section node_ids (from MENTIONS edges)
        self._entity_section_index: Dict[str, Set[str]] = {}
        # Section label map: section_number → "Article X — HEADING" (for citations)
        self._section_label_map: Dict[str, str] = {}
        self._build_indexes()
    
    def _build_indexes(self) -> None:
        """Build fast lookup indexes from graph."""
        # Ensure all index dicts exist (some test helpers bypass __init__)
        for attr, factory in [
            ("_section_index", dict), ("_definition_index", dict),
            ("_term_node_index", dict), ("_term_keyword_index", dict),
            ("_role_index", dict), ("_entity_section_index", dict),
            ("_section_label_map", dict),
        ]:
            if not hasattr(self, attr):
                setattr(self, attr, factory())

        _roman_numeral_re = re.compile(
            r'^(I{1,3}|IV|V|VI{0,3}|IX|X|XI{0,3})$'
        )

        for node_id, data in self.graph.nodes(data=True):
            node_type = data.get("type", "")
            
            # Handle both uppercase (SECTION) and title case (Section)
            if node_type.upper() == "SECTION":
                # Graph uses "heading" or "section_heading"
                sec_num = data.get("section_number", "")
                if sec_num:
                    self._section_index[sec_num] = node_id

                    # Build section label map for proper citations
                    heading = data.get("heading", "") or data.get("section_heading", "")
                    if sec_num == "PREAMBLE":
                        self._section_label_map[sec_num] = f"Preamble — {heading}" if heading else "Preamble"
                    elif _roman_numeral_re.match(sec_num):
                        # Top-level Roman numeral → "Article X — HEADING"
                        self._section_label_map[sec_num] = f"Article {sec_num} — {heading}" if heading else f"Article {sec_num}"
                    else:
                        self._section_label_map[sec_num] = f"Section {sec_num} — {heading}" if heading else f"Section {sec_num}"
            
            elif node_type.upper() == "ITEM":
                # Check item_type for definitions
                item_type = data.get("item_type", "")
                if item_type.lower() == "definition":
                    text = data.get("text", "")
                    term = self._extract_defined_term(text)
                    if term:
                        self._definition_index[term.lower()] = node_id
            
            elif node_type.lower() == "definition":
                # Direct Definition node type (for compatibility)
                text = data.get("text", "")
                term = self._extract_defined_term(text)
                if term:
                    self._definition_index[term.lower()] = node_id

            elif node_type.lower() == "defined_term":
                # TERM:: nodes created by definition_graph_builder (Module 4)
                term_name = data.get("term_name", "")
                if term_name:
                    self._term_node_index[term_name.lower()] = node_id

        # ── Q1: Build keyword → TERM:: node_id inverted index ────
        # Per-definition keywords are stored on TERM::* nodes by
        # ConceptVocabularyBuilder.apply_term_keywords().
        total_term_kws = 0
        for node_id, data in self.graph.nodes(data=True):
            if data.get("type", "").lower() != "defined_term":
                continue
            concept_kws = data.get("concept_keywords", [])
            if not concept_kws:
                continue
            for kw in concept_kws:
                kw_lower = kw.lower() if isinstance(kw, str) else str(kw).lower()
                self._term_keyword_index.setdefault(kw_lower, []).append(node_id)
                total_term_kws += 1

        # ── NER: Build ASSIGNED_ROLE index ────────────────────────
        # ASSIGNED_ROLE edges: entity:ORG:X → TERM::Y
        # Maps term_name (lowercase) → [(entity surface_form, entity_node_id)]
        total_roles = 0
        for src, tgt, edata in self.graph.edges(data=True):
            if edata.get("type") != "ASSIGNED_ROLE":
                continue
            src_data = self.graph.nodes.get(src, {})
            tgt_data = self.graph.nodes.get(tgt, {})
            entity_surface = src_data.get("surface_form", "") or src_data.get("name", "")
            term_name = tgt_data.get("term_name", "")
            if entity_surface and term_name:
                self._role_index.setdefault(term_name.lower(), []).append(
                    (entity_surface, src)
                )
                total_roles += 1

        # ── NER: Build entity → section index ────────────────────
        # MENTIONS edges: section → entity (section MENTIONS entity)
        # Maps entity surface_form (lowercase) → set of section node_ids
        total_ent_sec = 0
        for node_id, data in self.graph.nodes(data=True):
            if data.get("type") != "ENTITY":
                continue
            surface = (data.get("surface_form", "") or data.get("name", "")).lower()
            if not surface:
                continue
            # predecessors of entity via MENTIONS = sections
            for pred in self.graph.predecessors(node_id):
                edge = self.graph[pred][node_id]
                if edge.get("type") == "MENTIONS":
                    pred_type = self.graph.nodes[pred].get("type", "").upper()
                    if pred_type == "SECTION":
                        self._entity_section_index.setdefault(surface, set()).add(pred)
                        total_ent_sec += 1

        logger.debug(
            f"[HumanLike] Built indexes: {len(self._section_index)} sections, "
            f"{len(self._definition_index)} definitions, "
            f"{len(self._term_node_index)} TERM:: nodes, "
            f"{len(self._term_keyword_index)} term keywords ({total_term_kws} mappings), "
            f"{len(self._role_index)} role assignments ({total_roles} edges), "
            f"{len(self._entity_section_index)} entity-section mappings ({total_ent_sec} links)"
        )
    
    # ── Phase 17: Filter merging helper ───────────────────────────

    def _merge_doc_filter(self, filters: Dict[str, Any] | None) -> Dict[str, Any] | None:
        """Merge doc_name_prefix into a filters dict for ChromaDB where clause.

        If Phase 17 doc_name_prefix is active, add it to the filters dict.
        ChromaDB handles multiple keys in the where dict as implicit AND.
        """
        prefix = getattr(self, '_doc_name_prefix', None)
        if not prefix:
            return filters
        if filters is None:
            return {"doc_name_prefix": prefix}
        merged = dict(filters)
        merged["doc_name_prefix"] = prefix
        return merged

    def _extract_defined_term(self, definition_text: str) -> str:
        """Extract the defined term from a definition sentence."""
        # Pattern: "Term" means/shall mean ... or TERM means ...
        m = re.search(r'["\u201c\u201d\'\u2018\u2019]([^"\u201c\u201d\'\u2018\u2019]{2,60})["\u201c\u201d\'\u2018\u2019]\s+(means|shall\s+mean|is\s+defined\s+as|shall\s+have\s+the\s+meaning|has\s+the\s+meaning)', definition_text, re.I)
        if m:
            return m.group(1).strip()
        
        # Pattern: "Term": description (colon-based definition)
        m2 = re.search(r'["\u201c][^"\u201d]{2,60}["\u201d]\s*:', definition_text)
        if m2:
            inner = re.search(r'["\u201c]([^"\u201d]{2,60})["\u201d]', definition_text)
            if inner:
                return inner.group(1).strip()
        
        # Phase 8.7: Plain-colon PSA pattern — "Current Interest: As of any..."
        # Must be Title Case (not ALL CAPS or lowercase). 1-5 words before colon.
        m3 = re.match(
            r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,4})\s*:\s+\S',
            definition_text,
        )
        if m3:
            return m3.group(1).strip()

        # Pattern: TERM means/shall mean ...
        parts = re.split(r'\b(means|shall\s+mean|is\s+defined\s+as)\b', definition_text, flags=re.I)
        if parts:
            left = parts[0].strip()
            # Look for capitalized term at end of left part
            caps = re.findall(r'([A-Z][A-Za-z0-9 -]{1,40})$', left)
            if caps:
                return caps[-1].strip()
        
        return ""
    
    # ══════════════════════════════════════════════════════════════
    # STEP 1: Self-Query Filter Extraction
    # ══════════════════════════════════════════════════════════════
    
    def extract_query_filters(self, query: str) -> Dict[str, Any]:
        """
        Extract metadata filters from query text.
        
        Examples:
        - "Section 5.05 loss allocation" → {"section_number": "5.05"}
        - "definition of Realized Loss" → {"item_type": "Definition"}
        - "rules for distributions" → {"item_type": "Rule"}
        """
        filters: Dict[str, Any] = {}
        
        # Section number extraction
        sec_match = re.search(r'Section\s+(\d+(?:\.\d+)*)', query, re.I)
        if sec_match:
            filters["section_number"] = sec_match.group(1)
        
        # Item type extraction
        # NOTE: We intentionally do NOT set item_type="Definition" for
        # definition queries.  The ingestion pipeline classifies defined-term
        # paragraphs as "Statement" (e.g. "Distribution Date: The 25th day
        # …").  Filtering by item_type="Definition" would exclude every
        # item in the DEFINITIONS section and force a costly global
        # fallback that drowns the actual definition among 100+ referencing
        # chunks.  Section-level scoping (graph_section_lookup always injects
        # the DEFINITIONS section for definition queries) is sufficient to
        # find the right items.
        if re.search(r'\b(rule|rules|shall|must|required|may not)\b', query, re.I):
            filters["item_type"] = "Rule"
        
        # Document type hints
        if re.search(r'\b(PSA|pooling|servicing)\b', query, re.I):
            filters["doc_type_hint"] = "PSA"
        
        return filters
    
    # ══════════════════════════════════════════════════════════════
    # STEP 2: Query Decomposition
    # ══════════════════════════════════════════════════════════════
    
    def decompose_query(self, query: str) -> List[str]:
        """
        Decompose compound queries into sub-queries.
        
        Examples:
        - "losses and distributions" → ["losses", "distributions"]
        - "certificate holder payments" → ["certificate holder payments"]
        """
        sub_queries = [query]
        query_lower = query.lower()
        
        # Split on "and" / "or" if they separate distinct concepts
        if re.search(r'\band\b|\bor\b', query_lower):
            parts = re.split(r'\s+(?:and|or)\s+', query_lower)
            if len(parts) > 1 and all(len(p.strip()) > 3 for p in parts):
                # Only split if each part is substantial
                sub_queries = [p.strip() for p in parts if p.strip()]
        
        # Add step-back query for vague / short queries
        if len(query.split()) <= 6:
            step_back = self._generate_step_back_query(query)
            if step_back and step_back != query:
                sub_queries.append(step_back)
        
        # Definition-aware: add a targeted "definition of <term>" sub-query
        # so dual-store also retrieves definition items directly.
        if self._is_definition_query(query):
            # Strip common question preamble to isolate the term
            term = re.sub(
                r'^(what\s+(?:is|are|does)\s+(?:the\s+)?|'
                r'defin(?:ition|e)\s+(?:of\s+)?(?:the\s+)?)',
                '', query, flags=re.I,
            ).strip().rstrip('?')
            if term and term.lower() != query_lower:
                sub_queries.append(f"definition of {term}")
        
        return sub_queries[:4]  # Cap at 4 sub-queries
    
    def _generate_step_back_query(self, query: str) -> str:
        """Generate a broader 'step-back' query from the document's own
        vocabulary.

        Instead of hard-coded domain-specific broadening, this method
        looks up the *step_back_vocabulary* that was built during
        ingestion by :class:`ConceptVocabularyBuilder`.  The vocabulary
        maps keywords → section headings derived from the actual
        document, so it works equally well for legal, IT, research, or
        any other corpus.

        Falls back to lightweight heuristics only when the vocabulary is
        empty (e.g. graph was built before the vocabulary enrichment was
        added).
        """
        query_lower = query.lower()

        # Definition queries always get a definition-focused step-back
        if re.search(
            r"\b(what\s+does\b.*\bmean|defin(?:ition|ed|e)\b|means\b|meaning\b)",
            query,
            re.I,
        ):
            return "defined terms and definitions"

        # ── Try doc-aware vocabulary first ────────────────────────
        vocab: Dict[str, List[str]] = self.graph.graph.get(
            "step_back_vocabulary", {}
        )
        if vocab:
            query_keywords = self._extract_keywords(query)
            matched_headings: List[str] = []
            for kw in query_keywords:
                for heading in vocab.get(kw, []):
                    if heading not in matched_headings:
                        matched_headings.append(heading)
            if matched_headings:
                # Return the top headings as a broadening phrase
                return " ".join(matched_headings[:3]).lower()

        # ── Q1: Term-aware step-back via per-definition keywords ──
        # When section-level vocabulary doesn't match, check if any
        # query keywords match TERM::* concept_keywords and broaden
        # the step-back query with the matched term names.
        if self._term_keyword_index:
            query_keywords = self._extract_keywords(query)
            broadening_terms: List[str] = []
            seen_nids: set = set()
            for kw in query_keywords:
                for nid in self._term_keyword_index.get(kw, []):
                    if nid not in seen_nids:
                        seen_nids.add(nid)
                        tname = self.graph.nodes[nid].get("term_name", "")
                        if tname and tname not in broadening_terms:
                            broadening_terms.append(tname)
            if broadening_terms:
                # Use the top 3 term names as a broadening phrase
                return " ".join(broadening_terms[:3]).lower()

        # ── Lightweight fallback (pre-enrichment graphs) ──────────
        # Only fires when no concept vocabulary exists on the graph.
        # Intentionally minimal — just enough to avoid a blank
        # step-back for very common query patterns.
        if "loss" in query_lower:
            return "allocation of losses and shortfalls"
        if "distribution" in query_lower:
            return "payment distribution waterfall"
        if "certificate" in query_lower:
            return "certificate holder rights and payments"
        if "servicer" in query_lower:
            return "servicer duties and obligations"
        if "date" in query_lower:
            return "dates and timing definitions"
        if "statement" in query_lower or "report" in query_lower:
            return "monthly statements reporting obligations"

        return ""
    
    # ══════════════════════════════════════════════════════════════
    # STEP 3: Graph-First Section Discovery
    # ══════════════════════════════════════════════════════════════
    
    def graph_section_lookup(
        self, 
        query: str, 
        xlog: ExplainabilityLogger
    ) -> List[Dict[str, Any]]:
        """
        Query graph to find relevant sections (like TOC lookup).
        
        Returns section nodes ranked by:
        1. Keyword match in section heading
        2. PageRank authority score
        """
        keywords = self._extract_keywords(query)
        
        section_scores: List[Tuple[str, float, Dict]] = []
        
        for node_id, data in self.graph.nodes(data=True):
            node_type = data.get("type", "")
            if node_type.upper() != "SECTION":
                continue
            
            # Handle both "heading" and "section_heading" keys
            heading = (data.get("heading", "") or data.get("section_heading", "")).lower()
            sec_num = data.get("section_number", "")
            
            # ── Concept-keyword matching (doc-aware) ──────────────
            # Match against the heading, enriched concept_keywords,
            # AND the section_synopsis (first ~200 chars of body text).
            concept_kws: set = set(data.get("concept_keywords", []))
            heading_words = set(re.findall(r'[a-zA-Z]{3,}', heading))

            # Section synopsis: heading + opening body text
            synopsis = (data.get("section_synopsis", "") or "").lower()
            synopsis_words = set(re.findall(r'[a-zA-Z]{3,}', synopsis))

            # Union of heading words + concept keywords + synopsis words
            matchable_words = heading_words | concept_kws | synopsis_words

            keyword_hits = 0
            concept_only_hits = 0  # hits from concept_kws/synopsis not in heading
            for kw in keywords:
                # Direct substring in heading (original — highest confidence)
                if kw in heading:
                    keyword_hits += 1
                    continue
                # Direct substring in synopsis (body text — good confidence)
                if kw in synopsis:
                    keyword_hits += 1
                    concept_only_hits += 1
                    continue
                # Direct match in concept keywords
                if kw in concept_kws:
                    keyword_hits += 1
                    concept_only_hits += 1
                    continue
                # Shared-root matching against all matchable words
                for hw in matchable_words:
                    common_len = 0
                    for c1, c2 in zip(kw, hw):
                        if c1 == c2:
                            common_len += 1
                        else:
                            break
                    min_len = min(len(kw), len(hw))
                    if common_len >= 6 and common_len >= 0.6 * min_len:
                        keyword_hits += 1
                        if hw not in heading_words:
                            concept_only_hits += 1
                        break

            # Concept-only hits get a slight discount (0.8x) vs heading
            # hits so that a section whose heading directly mentions the
            # keyword still ranks above a section matched only through
            # enriched vocabulary.
            effective_hits = (keyword_hits - concept_only_hits) + concept_only_hits * 0.8
            keyword_score = effective_hits / max(len(keywords), 1)
            
            # PageRank score (if available)
            pagerank = data.get("pagerank", 0.0)
            
            # Combined score
            score = 0.7 * keyword_score + 0.3 * pagerank
            
            if keyword_hits > 0 or pagerank > 0.01:
                section_scores.append((node_id, score, {
                    "section_number": sec_num,
                    "section_heading": data.get("heading", data.get("section_heading", "")),
                    "keyword_hits": keyword_hits,
                    "concept_only_hits": concept_only_hits,
                    "pagerank": pagerank,
                }))
        
        # ── Layer 5: Entity-based boost ────────────────────────────
        # Match query keywords against ENTITY surface_form nodes,
        # then follow MENTIONS edges back to SECTION nodes for a score boost.
        # Weight the boost inversely by how many sections the entity
        # appears in: entities mentioned in fewer sections are more
        # discriminative (e.g., an entity in only the Preamble is a
        # stronger signal than one in all 12 sections).
        keywords_lower = [kw.lower() for kw in keywords]
        entity_boost: dict = {}
        for ent_node_id, ent_data in self.graph.nodes(data=True):
            if ent_data.get("type") != "ENTITY":
                continue
            surface = (ent_data.get("surface_form", "") or "").lower()
            if not any(kw in surface or surface in kw for kw in keywords_lower if len(kw) >= 3):
                continue
            # Entity matches a query keyword — propagate boost to mentioning sections
            # Collect all mentioning sections first to compute specificity
            mention_sections: List[str] = []
            for src_id in self.graph.predecessors(ent_node_id):
                edge = self.graph[src_id].get(ent_node_id, {})
                if edge.get("type") == "MENTIONS":
                    if self.graph.nodes[src_id].get("type", "").upper() == "SECTION":
                        mention_sections.append(src_id)
            n_mentions = max(len(mention_sections), 1)
            # Specificity-weighted boost: 0.30 for 1 section, ≈0.03 for 12 sections
            per_section_boost = 0.30 / n_mentions
            for sec_id in mention_sections:
                entity_boost[sec_id] = entity_boost.get(sec_id, 0.0) + per_section_boost

        # Apply entity boosts to section_scores list
        boosted_ids = {nid for nid, _, _ in section_scores}
        for sec_id, boost in entity_boost.items():
            updated = False
            for i, (nid, sc, meta) in enumerate(section_scores):
                if nid == sec_id:
                    section_scores[i] = (nid, min(1.0, sc + boost), meta)
                    updated = True
                    break
            if not updated:
                # Entity-only match — insert as new candidate
                nd = self.graph.nodes[sec_id]
                section_scores.append((sec_id, min(1.0, boost), {
                    "section_number": nd.get("section_number", ""),
                    "section_heading": nd.get("heading", nd.get("section_heading", "")),
                    "keyword_hits": 0,
                    "concept_only_hits": 0,
                    "pagerank": nd.get("pagerank", 0.0),
                }))

        # Sort by score descending
        section_scores.sort(key=lambda x: x[1], reverse=True)
        top_sections = section_scores[:self.config.max_section_candidates]
        
        results = []
        for node_id, score, meta in top_sections:
            results.append({
                "node_id": node_id,
                "score": score,
                **meta
            })
        
        # ── Definition-aware: always include DEFINITIONS section ──
        # If the query looks like a definition lookup ("what is X",
        # "definition of Y", etc.) and no DEFINITIONS section was
        # already matched, inject it so section-scoped search can
        # find items inside the definitions article.
        if self._is_definition_query(query):
            defs_already = any(
                "definition" in (r.get("section_heading") or "").lower()
                for r in results
            )
            if not defs_already:
                for node_id, data in self.graph.nodes(data=True):
                    if data.get("type", "").upper() != "SECTION":
                        continue
                    heading = (data.get("heading", "") or data.get("section_heading", "")).lower()
                    if "definition" in heading:
                        results.insert(0, {
                            "node_id": node_id,
                            "score": 1.0,
                            "section_number": data.get("section_number", ""),
                            "section_heading": data.get("heading", data.get("section_heading", "")),
                            "keyword_hits": 0,
                            "pagerank": data.get("pagerank", 0.0),
                        })
                        break  # Only inject the first DEFINITIONS section

        # ── Reporting-aware: always include DISTRIBUTIONS section ──────
        # If the query is about statements, reporting, or monthly
        # obligations, inject the distributions/advances section so
        # section-scoped search can find items like Section 5.06.
        if self._is_reporting_query(query):
            dist_already = any(
                "distribution" in (r.get("section_heading") or "").lower()
                for r in results
            )
            if not dist_already:
                for node_id, data in self.graph.nodes(data=True):
                    if data.get("type", "").upper() != "SECTION":
                        continue
                    heading = (data.get("heading", "") or data.get("section_heading", "")).lower()
                    if "distribution" in heading:
                        results.insert(0, {
                            "node_id": node_id,
                            "score": 0.9,
                            "section_number": data.get("section_number", ""),
                            "section_heading": data.get("heading", data.get("section_heading", "")),
                            "keyword_hits": 0,
                            "pagerank": data.get("pagerank", 0.0),
                        })
                        break
            # Also inject THE CERTIFICATES section for certificate-related reporting
            cert_already = any(
                "certificate" in (r.get("section_heading") or "").lower()
                for r in results
            )
            if not cert_already:
                for node_id, data in self.graph.nodes(data=True):
                    if data.get("type", "").upper() != "SECTION":
                        continue
                    heading = (data.get("heading", "") or data.get("section_heading", "")).lower()
                    if "certificate" in heading:
                        results.append({
                            "node_id": node_id,
                            "score": 0.8,
                            "section_number": data.get("section_number", ""),
                            "section_heading": data.get("heading", data.get("section_heading", "")),
                            "keyword_hits": 0,
                            "pagerank": data.get("pagerank", 0.0),
                        })
                        break

        # ── Loss/subordination-aware: inject DISTRIBUTIONS section ──
        # This is a DEFENSIVE FALLBACK for graphs built before the
        # ConceptVocabularyBuilder was added.  In enriched graphs, the
        # concept_keywords matching above already finds DISTRIBUTIONS for
        # loss queries.  This block ensures backward compatibility.
        if self._is_loss_query(query):
            dist_already = any(
                "distribution" in (r.get("section_heading") or "").lower()
                for r in results
            )
            if not dist_already:
                for node_id, data in self.graph.nodes(data=True):
                    if data.get("type", "").upper() != "SECTION":
                        continue
                    heading = (data.get("heading", "") or data.get("section_heading", "")).lower()
                    if "distribution" in heading:
                        results.insert(0, {
                            "node_id": node_id,
                            "score": 0.9,
                            "section_number": data.get("section_number", ""),
                            "section_heading": data.get("heading", data.get("section_heading", "")),
                            "keyword_hits": 0,
                            "pagerank": data.get("pagerank", 0.0),
                        })
                        break
            defs_already = any(
                "definition" in (r.get("section_heading") or "").lower()
                for r in results
            )
            if not defs_already:
                for node_id, data in self.graph.nodes(data=True):
                    if data.get("type", "").upper() != "SECTION":
                        continue
                    heading = (data.get("heading", "") or data.get("section_heading", "")).lower()
                    if "definition" in heading:
                        results.append({
                            "node_id": node_id,
                            "score": 0.8,
                            "section_number": data.get("section_number", ""),
                            "section_heading": data.get("heading", data.get("section_heading", "")),
                            "keyword_hits": 0,
                            "pagerank": data.get("pagerank", 0.0),
                        })
                        break

        xlog.step(
            "graph_section_lookup",
            f"Found {len(results)} relevant sections via graph",
            detail={
                "keywords": keywords,
                "top_sections": [r["section_heading"][:50] for r in results[:3]],
                "concept_vocab_available": bool(self.graph.graph.get("step_back_vocabulary")),
                "definition_inject": self._is_definition_query(query),
                "loss_inject_fallback": self._is_loss_query(query),
            },
            why="Graph-first lookup with doc-aware concept keywords for section discovery"
        )
        
        return results

    # ══════════════════════════════════════════════════════════════
    # STEP 3b: Term-Keyword Lookup (Q1 Per-Definition Retrieval)
    # ══════════════════════════════════════════════════════════════

    def term_keyword_lookup(
        self,
        query: str,
        xlog: ExplainabilityLogger,
        *,
        max_terms: int = 5,
    ) -> List[str]:
        """Match query keywords against TERM::* per-definition keywords.

        Scans the inverted ``_term_keyword_index`` built during init and
        returns the top *max_terms* term names ranked by keyword overlap.
        These terms feed directly into the resolution tree in Step 7 so
        their definitions (and dependency chains) are included in the
        LLM context.

        Parameters
        ----------
        query : str
            The user query.
        xlog : ExplainabilityLogger
            Explainability logger for tracing.
        max_terms : int
            Maximum number of matched terms to return (default 5).

        Returns
        -------
        list[str]
            Capitalised term names (e.g. ``["Realized Loss", "Pass-Through Rate"]``).
        """
        if not self._term_keyword_index:
            return []

        query_keywords = self._extract_keywords(query)
        if not query_keywords:
            return []

        # Score each TERM:: node by number of keyword hits
        term_hits: Dict[str, int] = {}  # node_id → hit count
        matched_kws: Dict[str, List[str]] = {}  # node_id → matched keywords
        for kw in query_keywords:
            # Exact match
            node_ids = self._term_keyword_index.get(kw, [])
            # Also try shared-root matching (≥6 chars, ≥60% overlap)
            if not node_ids:
                for idx_kw, idx_nodes in self._term_keyword_index.items():
                    common_len = 0
                    for c1, c2 in zip(kw, idx_kw):
                        if c1 == c2:
                            common_len += 1
                        else:
                            break
                    min_len = min(len(kw), len(idx_kw))
                    if common_len >= 6 and common_len >= 0.6 * min_len:
                        node_ids = idx_nodes
                        break
            for nid in node_ids:
                term_hits[nid] = term_hits.get(nid, 0) + 1
                matched_kws.setdefault(nid, []).append(kw)

        if not term_hits:
            return []

        # Rank by hit count descending, break ties by PageRank
        ranked = sorted(
            term_hits.items(),
            key=lambda item: (
                item[1],
                self.graph.nodes[item[0]].get("pagerank", 0.0),
            ),
            reverse=True,
        )

        # Extract term names for top matches
        result_terms: List[str] = []
        for node_id, hits in ranked[:max_terms]:
            term_name = self.graph.nodes[node_id].get("term_name", "")
            if term_name:
                result_terms.append(term_name)

        xlog.step(
            "term_keyword_lookup",
            f"Matched {len(result_terms)} terms via per-definition keywords",
            detail={
                "query_keywords": query_keywords,
                "matched_terms": result_terms[:5],
                "top_hits": {
                    self.graph.nodes[nid].get("term_name", nid): cnt
                    for nid, cnt in ranked[:5]
                },
            },
            why="Per-definition keyword matching finds terms whose definitions "
                "are semantically relevant to the query, even when the term "
                "name itself does not appear in the query text."
        )

        return result_terms
    
    # ══════════════════════════════════════════════════════════════
    # STEP 3c: NER Entity Role Resolution
    # ══════════════════════════════════════════════════════════════

    _PARTY_QUERY_RE = re.compile(
        r'\b(who\s+is|who\s+are|identify|name\s+of|party|parties|'
        r'which\s+entity|which\s+company|which\s+organization|'
        r'role\s+of|acting\s+as|serves?\s+as|appointed\s+as)\b',
        re.I,
    )

    def _is_party_query(self, query: str) -> bool:
        """Return True if the query asks about a party / entity identity."""
        return bool(self._PARTY_QUERY_RE.search(query))

    def entity_role_lookup(
        self,
        query: str,
        xlog: ExplainabilityLogger,
    ) -> Dict[str, Any]:
        """Resolve party/entity identity via NER ASSIGNED_ROLE edges.

        For queries like "Who is the Depositor?", this method:
        1. Extracts candidate role terms from the query
        2. Checks ``_role_index`` for ASSIGNED_ROLE entity assignments
        3. Returns entity names + sections where those entities appear

        Returns
        -------
        dict with keys:
            role_entities : list[dict]
                Each dict: ``{"term": str, "entity": str, "entity_id": str}``
            section_node_ids : list[str]
                Section node_ids mentioning the assigned entities (Preamble priority)
            extra_search_terms : list[str]
                Entity surface forms to add to search queries
        """
        result: Dict[str, Any] = {
            "role_entities": [],
            "section_node_ids": [],
            "extra_search_terms": [],
        }
        if not self._role_index:
            return result

        # Extract candidate terms from the query
        # E.g. "Who is the Depositor?" → ["depositor"]
        # E.g. "Who is the Master Servicer?" → ["master servicer"]
        query_lower = query.lower()
        matched_roles: List[Dict[str, str]] = []
        sections_to_add: List[str] = []
        extra_terms: List[str] = []

        for term_lower, entities in self._role_index.items():
            if term_lower in query_lower:
                for surface_form, ent_id in entities:
                    matched_roles.append({
                        "term": term_lower,
                        "entity": surface_form,
                        "entity_id": ent_id,
                    })
                    extra_terms.append(surface_form)
                    # Find sections where this entity is mentioned
                    sf_lower = surface_form.lower()
                    for ent_sf, sec_ids in self._entity_section_index.items():
                        if sf_lower in ent_sf or ent_sf in sf_lower:
                            sections_to_add.extend(sec_ids)

        if not matched_roles:
            # Fallback: check query keywords against term_node_index
            # for partial matches (e.g., "trustee" → TERM::Trustee)
            keywords = self._extract_keywords(query)
            for kw in keywords:
                if kw in self._role_index:
                    for surface_form, ent_id in self._role_index[kw]:
                        matched_roles.append({
                            "term": kw,
                            "entity": surface_form,
                            "entity_id": ent_id,
                        })
                        extra_terms.append(surface_form)
                        sf_lower = surface_form.lower()
                        for ent_sf, sec_ids in self._entity_section_index.items():
                            if sf_lower in ent_sf or ent_sf in sf_lower:
                                sections_to_add.extend(sec_ids)

        # Always prioritize PREAMBLE for party identification
        if matched_roles:
            for sec_num, sec_nid in self._section_index.items():
                if sec_num.upper() == "PREAMBLE":
                    if sec_nid not in sections_to_add:
                        sections_to_add.insert(0, sec_nid)
                    break

        # Deduplicate
        seen_secs: set = set()
        deduped_secs: List[str] = []
        for s in sections_to_add:
            if s not in seen_secs:
                seen_secs.add(s)
                deduped_secs.append(s)

        result["role_entities"] = matched_roles
        result["section_node_ids"] = deduped_secs
        result["extra_search_terms"] = list(dict.fromkeys(extra_terms))  # dedup

        if matched_roles:
            xlog.step(
                "entity_role_lookup",
                f"Found {len(matched_roles)} role assignments via NER ASSIGNED_ROLE",
                detail={
                    "roles": [
                        f"{r['entity']} → {r['term']}" for r in matched_roles[:5]
                    ],
                    "sections_added": len(deduped_secs),
                    "extra_search_terms": result["extra_search_terms"][:3],
                },
                why="ASSIGNED_ROLE edges map entity names to their document roles "
                    "(e.g. 'Bear Stearns Asset Backed Securities I LLC' → Depositor)"
            )

        return result

    def _extract_section_refs_from_keywords(
        self,
        matched_term_names: List[str],
    ) -> List[str]:
        """Extract section number references from Q1 per-definition keywords.

        Some term keywords contain section references like "section 5.06 statement".
        This method extracts those section numbers and returns them so they can
        be added to the section discovery candidates.

        Returns a list of section_number strings (e.g. ["V", "5.06"]).
        """
        sec_ref_re = re.compile(r'section\s+(\d+(?:\.\d+)*)', re.I)
        found_refs: List[str] = []

        for term_name in matched_term_names:
            term_lower = term_name.lower()
            nid = self._term_node_index.get(term_lower, "")
            if not nid:
                continue
            concept_kws = self.graph.nodes[nid].get("concept_keywords", [])
            for kw in concept_kws:
                m = sec_ref_re.search(str(kw))
                if m:
                    sec_num = m.group(1)
                    if sec_num not in found_refs:
                        found_refs.append(sec_num)
                        # Also add the parent article (e.g. "5.06" → "V")
                        try:
                            article_num = int(sec_num.split(".")[0])
                            roman = self._int_to_roman(article_num)
                            if roman and roman not in found_refs:
                                found_refs.append(roman)
                        except (ValueError, IndexError):
                            pass

        return found_refs

    @staticmethod
    def _int_to_roman(num: int) -> str:
        """Convert integer to Roman numeral (1-20)."""
        vals = [
            (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
        ]
        result = ""
        for val, symbol in vals:
            while num >= val:
                result += symbol
                num -= val
        return result

    def get_section_label(self, section_number: str) -> str:
        """Return a human-friendly section label like 'Article III — ACCOUNTS'.

        Falls back to the raw section_number if no label is available.
        """
        return self._section_label_map.get(section_number, section_number)
    
    @staticmethod
    def _is_definition_query(query: str) -> bool:
        """Return True if the query is asking about a defined term."""
        return bool(re.search(
            r'\b(what\s+(?:is|are|does)|defin(?:ition|ed|e)|means|meaning)\b',
            query, re.I,
        ))

    @staticmethod
    def _is_loss_query(query: str) -> bool:
        """Return True if the query is about losses, subordination, or credit enhancement."""
        return bool(re.search(
            r'\b(realized\s+loss|loss\s+alloc|subordinat|credit\s+enhance|'
            r'write.?down|loss.?absorb|overcollateral|undercollateral)\b',
            query, re.I,
        ))

    @staticmethod
    def _is_reporting_query(query: str) -> bool:
        """Return True if the query is about reporting, statements, or notices."""
        return bool(re.search(
            r'\b(statement|statements|monthly|report(?:ing|ed|s)?|'
            r'certificateholder|notice|deliver(?:y|ed|s)?|'
            r'certificate\s+factor|information.*(?:included|required))\b',
            query, re.I,
        ))
    
    def _extract_keywords(self, query: str) -> List[str]:
        """Extract search keywords from query."""
        # Remove stop words and extract meaningful terms
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "for", "of", "to", "in", "on", "at", "by", "with", "from",
            "what", "how", "when", "where", "why", "which", "who",
            "does", "do", "did", "will", "would", "could", "should",
            "and", "or", "but", "not", "if", "then", "than",
        }
        
        words = re.findall(r'\b[a-zA-Z]{3,}\b', query.lower())
        keywords = [w for w in words if w not in stop_words]
        
        return keywords
    
    # ══════════════════════════════════════════════════════════════
    # STEP 4: Section-Scoped Item Search
    # ══════════════════════════════════════════════════════════════
    
    def section_scoped_search(
        self,
        query: str,
        section_numbers: List[str],
        xlog: ExplainabilityLogger,
        item_type_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search items scoped to specific sections with **stratified allocation**.
        
        Guarantees a floor of ``min_chunks_per_section`` (default 3) items from
        each qualifying section so that no single dominant section crowds out
        the others.  The remaining budget (up to ``max_chunks_per_doc``) is
        filled by global similarity ranking.
        
        If an exact section_number match yields 0 results we expand to
        child section numbers discovered from the graph.
        """
        # Floor per section (configurable, default 3)
        floor = getattr(self.config, "min_chunks_per_section", 3)
        budget = getattr(self.config, "max_chunks_per_doc", 25)

        # ── Phase 1: collect candidates per section ──────────────
        per_section: Dict[str, List[Dict[str, Any]]] = {}
        
        for sec_num in section_numbers:
            filters: Dict[str, Any] = {"section_number": sec_num}
            if item_type_filter:
                filters["item_type"] = item_type_filter
            # Phase 17: merge doc_name_prefix
            filters = self._merge_doc_filter(filters) or filters
            
            try:
                items = self.dual_store.search_items(
                    query,
                    top_k=self.config.items_per_section,
                    filters=filters
                )
                
                # ── Fallback: expand to child section numbers ────────
                if not items and self.graph is not None:
                    child_sec_nums = self._get_child_section_numbers(sec_num)
                    for child_num in child_sec_nums:
                        child_filters: Dict[str, Any] = {"section_number": child_num}
                        if item_type_filter:
                            child_filters["item_type"] = item_type_filter
                        # Phase 17: merge doc_name_prefix
                        child_filters = self._merge_doc_filter(child_filters) or child_filters
                        try:
                            child_items = self.dual_store.search_items(
                                query,
                                top_k=self.config.items_per_section,
                                filters=child_filters
                            )
                            items.extend(child_items)
                        except Exception:
                            pass
                
                for item in items:
                    item["scoped_to_section"] = sec_num

                # Sort per-section by similarity descending
                items.sort(key=lambda r: r.get("similarity", 0), reverse=True)
                if items:
                    per_section[sec_num] = items
                    
            except Exception as exc:
                logger.debug(f"Section-scoped search failed for {sec_num}: {exc}")

        # ── Phase 2: Stratified allocation ───────────────────────
        # Step A — guarantee floor items from each section
        selected: List[Dict[str, Any]] = []
        selected_ids: Set[str] = set()
        overflow: List[Dict[str, Any]] = []

        for sec_num, items in per_section.items():
            taken = 0
            for item in items:
                item_id = item.get("id", id(item))
                if taken < floor:
                    selected.append(item)
                    selected_ids.add(item_id)
                    taken += 1
                else:
                    overflow.append(item)

        # Step B — fill remaining budget from overflow by similarity
        overflow.sort(key=lambda r: r.get("similarity", 0), reverse=True)
        remaining = budget - len(selected)
        for item in overflow:
            if remaining <= 0:
                break
            item_id = item.get("id", id(item))
            if item_id not in selected_ids:
                selected.append(item)
                selected_ids.add(item_id)
                remaining -= 1

        # Final sort by similarity for downstream pipeline
        selected.sort(key=lambda r: r.get("similarity", 0), reverse=True)

        # Section diversity stats for explainability
        section_counts = {}
        for item in selected:
            sec = item.get("scoped_to_section", "?")
            section_counts[sec] = section_counts.get(sec, 0) + 1
        
        xlog.step(
            "section_scoped_search",
            f"Searched {len(section_numbers)} sections, selected {len(selected)}/{sum(len(v) for v in per_section.values())} items (floor={floor})",
            detail={
                "sections": section_numbers,
                "item_count": len(selected),
                "section_distribution": section_counts,
                "top_similarity": selected[0]["similarity"] if selected else 0,
            },
            why="Stratified allocation guarantees representation from every matching "
                "section while filling remaining budget by similarity."
        )
        
        return selected
    
    def _get_child_section_numbers(self, parent_sec_num: str) -> List[str]:
        """
        Find child section numbers from the graph for a parent section.
        E.g. Article "V" → ["5.01", "5.02", "5.03", "5.04", ...].
        """
        child_nums: List[str] = []
        if self.graph is None:
            return child_nums
        
        # Find the section node by section_number
        parent_node = None
        for node_id, data in self.graph.nodes(data=True):
            if data.get("type", "").upper() == "SECTION" and data.get("section_number") == parent_sec_num:
                parent_node = node_id
                break
        
        if not parent_node:
            return child_nums
        
        # Collect section_numbers from ITEM children of this section node
        seen: set = set()
        for _, child_id, edge_data in self.graph.edges(parent_node, data=True):
            child_data = self.graph.nodes.get(child_id, {})
            child_sec = child_data.get("section_number", "")
            if child_sec and child_sec != parent_sec_num and child_sec not in seen:
                seen.add(child_sec)
                child_nums.append(child_sec)
        
        return child_nums
    
    # ══════════════════════════════════════════════════════════════
    # STEP 5: Definition Enrichment
    # ══════════════════════════════════════════════════════════════
    
    def enrich_with_definitions(
        self,
        results: List[Dict[str, Any]],
        xlog: ExplainabilityLogger,
        *,
        prior_context_terms: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find capitalized terms in results and inject their definitions.
        
        Uses the bulk ``resolve_terms_for_context()`` API which:
        - Walks DEPENDS_ON edges live (no stored JSON)
        - Deduplicates across all terms
        - Produces a two-layer format (dependency map + priority defs)
        - Respects a shared token budget (default 50 000)
        """
        from backend.graph.resolution_tree import resolve_terms_for_context

        enriched_results = []
        all_definitions_found: Set[str] = set()

        # ── Phase 1: Collect ALL unique capitalized terms across ALL chunks ──
        all_terms: List[str] = []
        seen_terms: Set[str] = set()

        # Include terms from prior conversation turns (follow-up enrichment)
        for term in (prior_context_terms or []):
            if term.lower() not in seen_terms:
                seen_terms.add(term.lower())
                all_terms.append(term)

        for result in results:
            text = result.get("text", "")
            for term in self._extract_capitalized_terms(text)[:10]:
                if term.lower() not in seen_terms:
                    seen_terms.add(term.lower())
                    all_terms.append(term)

        # ── Phase 2: Split into graph-known vs vector-fallback ───
        graph_terms: List[str] = []
        flat_definitions: Dict[str, str] = {}  # term -> short def for non-tree terms

        for term in all_terms:
            term_lower = term.lower()
            if term_lower in self._term_node_index:
                graph_terms.append(term)
                all_definitions_found.add(term)
            elif term_lower in self._definition_index:
                node_id = self._definition_index[term_lower]
                node_data = self.graph.nodes[node_id]
                flat_definitions[term] = node_data.get("text", "")[:200]
                all_definitions_found.add(term)
            else:
                # Phase 8.7 Path B: ChromaDB vector fallback
                fallback_def = self._resolve_term_from_vector(term)
                if fallback_def:
                    flat_definitions[term] = fallback_def[:200]
                    all_definitions_found.add(term)

        # ── Phase 3: Bulk-resolve all graph terms in one pass ────
        # Session cache is per-retrieval so repeated queries are free
        resolution_context = ""
        if graph_terms:
            resolution_context = resolve_terms_for_context(
                self.graph,
                graph_terms,
                token_budget=50_000,
            )

        # ── Phase 4: Build per-result enriched text ──────────────
        # Design: enriched_text is used ONLY for cross-encoder reranking.
        # It gets per-chunk flat definitions (lightweight, specific to that chunk).
        # The shared resolution_context (dependency trees) is NOT duplicated
        # per chunk — it's hoisted to the RetrievalResult level as
        # definitions_glossary and sent once to the LLM as a preamble.
        for result in results:
            text = result.get("text", "")
            chunk_terms = self._extract_capitalized_terms(text)[:10]

            # Per-chunk flat definitions (non-tree terms only)
            def_parts: List[str] = []
            chunk_defs: List[Dict[str, str]] = []
            for term in chunk_terms[:self.config.max_definitions_per_chunk]:
                if term in flat_definitions:
                    def_parts.append(f"[{term}: {flat_definitions[term]}]")
                    chunk_defs.append({"term": term, "definition": flat_definitions[term]})

            enriched = dict(result)
            enriched["injected_definitions"] = chunk_defs

            # enriched_text = original + per-chunk flat defs ONLY
            # (shared resolution_context is NOT appended here — it's a
            #  separate glossary sent once to the LLM)
            parts = [text]
            if def_parts:
                parts.append(f"\n\nDefinitions: {' '.join(def_parts)}")
            enriched["enriched_text"] = "".join(parts)

            enriched_results.append(enriched)
        
        xlog.step(
            "definition_enrichment",
            f"Injected {len(all_definitions_found)} unique definitions "
            f"({len(graph_terms)} with resolution trees)",
            detail={
                "terms_found": list(all_definitions_found)[:10],
                "graph_terms_resolved": len(graph_terms),
                "flat_definitions": len(flat_definitions),
            },
            why="Definition injection provides context for understanding legal jargon. "
                "Resolution trees show full dependency chains for nested terms."
        )
        
        return enriched_results, resolution_context
    
    def _extract_capitalized_terms(self, text: str) -> List[str]:
        """Extract capitalized multi-word terms (likely defined terms)."""
        # Pattern for defined terms: "Realized Loss", "Certificate Holder", etc.
        pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'
        matches = re.findall(pattern, text)
        
        # Strip leading common words (e.g. "The Current Interest" → "Current Interest")
        leading_articles = {"The", "This", "That", "A", "An", "Each", "Any", "Such", "All", "No"}
        stripped: List[str] = []
        for m in matches:
            parts = m.split()
            while parts and parts[0] in leading_articles:
                parts = parts[1:]
            stripped.append(" ".join(parts)) if parts else None

        # Filter out common words and very short terms
        common_caps = {"Section", "Article", "In", "For", "By", "With", "From", "To"}
        terms = [m for m in stripped if m and m not in common_caps and len(m) > 3]
        
        # Deduplicate while preserving order
        seen: Set[str] = set()
        unique: List[str] = []
        for t in terms:
            if t not in seen:
                seen.add(t)
                unique.append(t)
        
        return unique
    
    # ══════════════════════════════════════════════════════════════
    # Phase 8.7: ChromaDB Fallback for Definition Traversal
    # ══════════════════════════════════════════════════════════════

    def _resolve_term_from_vector(
        self,
        term: str,
        *,
        score_threshold: float = 0.7,
    ) -> Optional[str]:
        """Fallback: resolve a term via vector search when graph has no match.

        Returns the definition text if a sufficiently close match is found,
        else ``None``.
        """
        try:
            hits = self.dual_store.search_items(
                f"definition of {term}",
                top_k=3,
                filters=self._merge_doc_filter(None),
            )
            for hit in hits:
                if hit.get("similarity", 0) >= score_threshold:
                    return hit.get("text", "")
        except Exception:
            pass
        return None

    # ══════════════════════════════════════════════════════════════
    # Phase 8.4: Parent-Child Document Expansion
    # ══════════════════════════════════════════════════════════════

    def _expand_items_to_parent_sections(
        self,
        items: List[Dict[str, Any]],
        *,
        max_parents: int = 10,
    ) -> List[Dict[str, Any]]:
        """Expand matched items to their parent sections for richer context.

        Each unique ``parent_section_id`` in item metadata is resolved to a
        section record.  Deduplicated and capped at *max_parents*.
        """
        seen_parents: set[str] = set()
        parents: list[dict] = []

        for item in items:
            meta = item.get("metadata") or {}
            pid = meta.get("parent_section_id", "")
            if not pid or pid in seen_parents:
                continue
            seen_parents.add(pid)

            section = self.dual_store.get_section_by_id(pid)
            if section is None:
                continue

            section["_child_match_score"] = item.get("similarity", item.get("score", 0))
            section["_matched_via"] = "parent_expansion"
            parents.append(section)

            if len(parents) >= max_parents:
                break

        return parents

    # ══════════════════════════════════════════════════════════════
    # Phase 8.6: Weighted RRF Merge (multi-lane)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def _rrf_merge(
        ranked_lists: List[List[Dict[str, Any]]],
        weights: Optional[List[float]] = None,
        k: int = 60,
    ) -> List[Dict[str, Any]]:
        """Weighted Reciprocal Rank Fusion across *N* ranked lists.

        ``weights`` – per-list multiplier (e.g. ``[0.6, 0.4]`` for vector + BM25).
        Falls back to uniform ``1.0`` when not supplied.
        """
        if not ranked_lists:
            return []

        if weights is None:
            weights = [1.0] * len(ranked_lists)

        scores: Dict[str, float] = {}
        result_map: Dict[str, Dict] = {}

        for lane_idx, rlist in enumerate(ranked_lists):
            w = weights[lane_idx] if lane_idx < len(weights) else 1.0
            for rank, item in enumerate(rlist):
                item_id = item.get("id", str(id(item)))
                scores[item_id] = scores.get(item_id, 0.0) + w / (k + rank + 1)
                if item_id not in result_map:
                    result_map[item_id] = item

        sorted_ids = sorted(scores, key=scores.get, reverse=True)  # type: ignore
        merged: list[dict] = []
        for rid in sorted_ids:
            r = dict(result_map[rid])
            r["rrf_score"] = scores[rid]
            merged.append(r)
        return merged

    # ══════════════════════════════════════════════════════════════
    # STEP 5a: Doc-Category Routing Helpers
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def _detect_doc_category(source_path: str) -> str:
        """Classify a document based on its filename.

        Returns one of: glossary, architecture, sop, rca, faq,
        user_guide, training, config_ref, best_practices, release_note,
        onboarding, jira, or unknown.
        """
        import os
        fname = os.path.basename(source_path).lower()
        if "glossary" in fname:
            return "glossary"
        if "architecture" in fname:
            return "architecture"
        if "sop" in fname or "incident_response" in fname:
            return "sop"
        if "rca" in fname or "root_cause" in fname:
            return "rca"
        if "faq" in fname:
            return "faq"
        if "training" in fname:
            return "training"
        if "config" in fname or "configuration" in fname:
            return "config_ref"
        if "best_practice" in fname:
            return "best_practices"
        if "release" in fname:
            return "release_note"
        if "onboarding" in fname:
            return "onboarding"
        if "jira" in fname or "epic" in fname:
            return "jira"
        if "userguide" in fname or "user_guide" in fname:
            return "user_guide"
        if "api" in fname:
            return "api_ref"
        return "unknown"

    @staticmethod
    def _detect_routing_intent(query: str):
        """Detect query intent and return (intent, expected_categories).

        Returns:
            (intent_name: str, expected_doc_categories: list[str])
        """
        q = query.lower()

        # Definition / acronym / glossary queries
        if re.search(r'\b(definition|define|glossary|abbreviation|acronym)\b', q):
            return ("definition", ["glossary"])
        # "What is PKI?" or "What is PKI in …?" — require all-caps acronym
        # to be the MAIN subject (followed by end-of-query, "?", or
        # context prepositions "in"/"for"), NOT a qualifier before another
        # noun (e.g. "What is the API rate limit?" is about rate limits).
        if re.search(r'\b[Ww]hat is (a |an |the )?([A-Z]{2,5})\s*(\?|$|in\b|for\b)', query):
            return ("acronym", ["glossary"])
        # "What does RRF stand for?" — short queries about a term
        if len(q.split()) <= 6:
            m = re.search(r'\bwhat (is|does|are)\s+(a |an |the )?(\w{2,5})\b', q)
            if m:
                target = m.group(3)
                _stop = {"the", "this", "that", "with", "from", "about",
                         "some", "each", "when", "used", "make", "does"}
                if target not in _stop:
                    return ("what_is", ["glossary", "user_guide"])

        # Technology / architecture / stack / version queries
        if re.search(r'\b(technology|tech stack|backend|architecture|version|deployment|infrastructure|platform.*stack|stack.*platform)\b', q):
            return ("architecture", ["architecture"])

        # Rollback / procedure / SOP queries
        if re.search(r'\b(rollback|procedure|incident.*response|recovery procedure|restore|failover|sop)\b', q):
            return ("sop", ["sop"])

        # How long / duration — only SOP when combined with operational terms
        if re.search(r'\bhow long\b.*\b(take|last|duration)\b', q):
            if re.search(r'\b(rollback|failover|restore|incident|deploy|recover)', q):
                return ("sop", ["sop"])

        return ("general", [])

    def _generate_routing_queries(
        self, query: str, intent: str, expected_categories: List[str]
    ) -> List[str]:
        """Generate supplemental queries targeting expected doc categories.

        These queries reformulate the original to pull results from the
        expected document categories, improving recall for cross-product
        queries (e.g., PKI definition lives in Glossary, not SecureVault).
        """
        routing_queries: List[str] = []
        q = query.lower()

        # Extract the core topic (remove product names)
        product_names = ["opsflow", "datadesk", "securevault", "batchbridge", "finreport"]
        core = query
        for pn in product_names:
            core = re.sub(re.escape(pn), "", core, flags=re.IGNORECASE).strip()

        if intent in ("definition", "acronym", "what_is") and "glossary" in expected_categories:
            # Add multiple glossary-focused queries for better recall
            routing_queries.append(f"glossary definition {core}")
            # Also try the exact term from the query (e.g. "RPO" or "PKI")
            key_terms = re.findall(r'\b[A-Z]{2,6}\b', query)
            for kt in key_terms[:2]:
                routing_queries.append(f"{kt} glossary term definition meaning")
        if intent == "architecture" and "architecture" in expected_categories:
            routing_queries.append(f"architecture technology stack {core}")
            routing_queries.append(f"component summary infrastructure {core}")
        if intent == "sop" and "sop" in expected_categories:
            routing_queries.append(f"SOP procedure rollback {core}")

        return routing_queries

    # ══════════════════════════════════════════════════════════════
    # STEP 5b: Keyword-Match Reranking
    # ══════════════════════════════════════════════════════════════
    
    def _keyword_boost_rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        xlog: ExplainabilityLogger,
    ) -> List[Dict[str, Any]]:
        """
        Re-score results based on keyword overlap with the query.
        
        This promotes specific detail chunks over overview/intro paragraphs
        by boosting chunks that contain exact query keywords (error codes,
        product names, numeric values, etc.).
        """
        import re
        if not results:
            return results
        
        # Extract meaningful query terms (skip stopwords)
        stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "what", "which",
            "how", "when", "where", "who", "why", "does", "do", "did", "can",
            "could", "should", "would", "in", "on", "at", "to", "for", "of",
            "with", "by", "from", "as", "or", "and", "not", "be", "been",
            "this", "that", "it", "its", "i", "my", "me", "we", "our",
            "you", "your", "many", "much", "used", "available",
        }
        
        query_lower = query.lower()
        query_words = [w for w in re.findall(r'\b[\w\-\.]+\b', query_lower) if w not in stopwords and len(w) > 1]
        
        # Extract high-value identifiers from query
        error_codes = re.findall(r'[A-Z]{2,}[\-_][A-Z0-9\-_]+', query, re.IGNORECASE)
        version_nums = re.findall(r'v?\d+\.\d+', query)
        specific_ids = re.findall(r'[A-Z]+-\d+', query)
        
        # Priority keywords (specific identifiers get strong boost)
        priority_terms = [t.lower() for t in error_codes + version_nums + specific_ids]
        
        # Detect if this is a definition/glossary query
        definition_patterns = {"definition", "define", "mean", "stands for", "what is a ",
                               "what does", "glossary", "abbreviation", "acronym"}
        is_definition_query = any(p in query_lower for p in definition_patterns)
        
        # Detect product names in query for product-scoped boosting
        product_names = ["opsflow", "datadesk", "securevault", "batchbridge", "finreport"]
        query_products = [p for p in product_names if p in query_lower]
        
        for result in results:
            text = result.get("text", result.get("content", "")).lower()
            # Use cross-encoder score if available, otherwise vector similarity
            ce_score = result.get("cross_encoder_score")
            if ce_score is not None:
                import math
                base_score = 1.0 / (1.0 + math.exp(-ce_score))  # Sigmoid normalize
            else:
                base_score = result.get("similarity", 0.5)
            
            if not text:
                continue
            
            meta = result.get("metadata", {})
            if not isinstance(meta, dict):
                meta = {}
            
            # 1. Keyword overlap score (fraction of important query words found)
            matched = sum(1 for w in query_words if w in text)
            keyword_overlap = matched / max(len(query_words), 1)
            
            # 2. Priority term boost (error codes, IDs, version numbers)
            priority_boost = 0.0
            for pt in priority_terms:
                if pt in text:
                    priority_boost += 0.25  # Strong boost for each matched ID/code
            
            # 3. Exact phrase match bonus (multi-word query phrases in text)
            phrase_boost = 0.0
            if len(query_words) >= 2:
                for i in range(len(query_words) - 1):
                    bigram = f"{query_words[i]} {query_words[i+1]}"
                    if bigram in text:
                        phrase_boost += 0.08
            
            # 4. Glossary/reference handling: boost glossary for definition queries,
            #    penalize for non-definition queries
            gloss_penalty = 0.0
            if not is_definition_query:
                doc_type = result.get("doc_type", result.get("type", ""))
                source = meta.get("source_path", "")
                # Check if this result is from a glossary-like document
                is_glossary = ("glossary" in source.lower() or 
                              doc_type in ("REFERENCE", "GLOSSARY") or
                              "glossary" in text[:200])
                if is_glossary:
                    gloss_penalty = -0.15  # Penalize glossary for non-definition queries
            else:
                # For definition queries, BOOST glossary/reference docs
                doc_type = result.get("doc_type", result.get("type", ""))
                source = meta.get("source_path", "")
                is_glossary = ("glossary" in source.lower() or 
                              doc_type in ("REFERENCE", "GLOSSARY") or
                              "glossary" in text[:200])
                if is_glossary:
                    gloss_penalty = 0.20  # Strong boost for glossary on definition queries
            
            # 5. Specificity bonus: chunks with numbers/codes/proper nouns
            #    are more likely to contain specific answers than overviews
            specificity_bonus = 0.0
            num_count = len(re.findall(r'\b\d+[\.,]?\d*\b', text[:500]))
            code_count = len(re.findall(r'[A-Z]{2,}[\-_]\w+', text[:500]))
            if num_count >= 3:
                specificity_bonus += 0.03
            if code_count >= 2:
                specificity_bonus += 0.03
            
            # 6. Section heading match: if chunk's section heading contains
            #    query-significant terms, this is likely the answer section
            section_heading_boost = 0.0
            section_heading = (meta.get("section_heading", "") or "").lower()
            if section_heading:
                heading_matched = sum(1 for w in query_words if w in section_heading)
                if heading_matched >= 1:
                    section_heading_boost = 0.03 * heading_matched
            
            # 7. Doc-category routing boost
            #    Apply intent-aware routing: definition queries boost glossary,
            #    tech queries boost architecture, procedure queries boost SOP.
            routing_intent, routing_categories = self._detect_routing_intent(query)
            routing_boost = 0.0
            source = meta.get("source_path", "") if isinstance(meta, dict) else ""
            doc_cat = self._detect_doc_category(source)

            if routing_categories:  # We have a routing signal
                if doc_cat in routing_categories:
                    routing_boost = 0.30  # Strong boost for matching category
                elif routing_intent in ("definition", "acronym", "what_is"):
                    # For definition queries, non-glossary docs get a penalty
                    routing_boost = -0.12
                elif routing_intent == "architecture":
                    routing_boost = -0.10
                elif routing_intent == "sop":
                    if doc_cat == "rca":
                        routing_boost = -0.12  # RCA is what-happened, not procedure
                    else:
                        routing_boost = -0.05

            # 8. Product-name routing (CONDITIONAL — only when intent is
            #    product-specific, NOT for cross-product intents like
            #    definition/architecture/SOP where answers may be in
            #    platform-level docs)
            product_boost = 0.0
            if query_products and routing_intent == "general":
                source_lower = source.lower()
                if any(p in source_lower for p in query_products):
                    product_boost = 0.12  # Boost matching product docs
                elif not any(kw in source_lower for kw in ["esp_", "platform"]):
                    product_boost = -0.04  # Slight penalty for wrong product

            # 9. Definition-term anchor boost
            #    For definition queries ("What does X mean?"), massively
            #    boost chunks whose text starts with the queried term
            #    followed by a colon or "means" — these are the actual
            #    definitions, not paragraphs that merely reference the term.
            definition_anchor_boost = 0.0
            if is_definition_query:
                # Extract the term being queried
                term_match = re.sub(
                    r'^(what\s+(?:is|are|does)\s+(?:the\s+)?|'
                    r'defin(?:ition|e)\s+(?:of\s+)?(?:the\s+)?|'
                    r'(?:the\s+)?meaning\s+of\s+(?:the\s+)?)',
                    '', query, flags=re.I,
                ).strip().rstrip('?').strip('"\'')
                # Also strip trailing "mean/means/meaning" left over
                term_match = re.sub(r'\s+(?:mean|means|meaning)$', '', term_match, flags=re.I).strip()
                if term_match and len(term_match) >= 3:
                    term_lower = term_match.lower()
                    # Strip the [DOC: ... | SECTION: ...] header to get body
                    body = text
                    bracket_end = text.find(']')
                    if bracket_end > 0 and bracket_end < 300:
                        body = text[bracket_end + 1:].strip().lower()
                    # Check if body starts with the queried term (the defining paragraph)
                    if body.startswith(term_lower):
                        # Check for definition pattern: term followed by colon, "means", "shall mean"
                        after_term = body[len(term_lower):len(term_lower) + 30]
                        if re.match(r'\s*(?::|means|shall\s+mean|is\s+defined)', after_term):
                            definition_anchor_boost = 0.60  # Very strong — this IS the definition
                        else:
                            definition_anchor_boost = 0.20  # Moderate — starts with term but no colon
                    # Also boost chunks in the DEFINITIONS section
                    elif 'definition' in section_heading:
                        if term_lower in body[:200]:
                            definition_anchor_boost = 0.08  # Mild — in definitions, mentions term
            
            # Combine: multiplicative + additive hybrid
            # keyword_boost scales with overlap and is multiplicative on base score
            keyword_multiplier = 1.0 + (keyword_overlap * 0.55)  # Up to 1.55x
            additive_boost = (
                min(priority_boost, 0.5) + 
                min(phrase_boost, 0.15) + 
                specificity_bonus + 
                gloss_penalty +
                section_heading_boost +
                routing_boost +
                product_boost +
                definition_anchor_boost
            )
            
            result["_final_score"] = base_score * keyword_multiplier + additive_boost
            result["_keyword_overlap"] = keyword_overlap
            result["_priority_boost"] = priority_boost
        
        # Re-sort by final combined score
        results.sort(key=lambda r: r.get("_final_score", 0), reverse=True)
        
        xlog.step(
            "keyword_boost",
            f"Keyword-boost reranked {len(results)} results",
            detail={
                "query_terms": query_words[:10],
                "priority_terms": priority_terms,
                "is_definition_query": is_definition_query,
            },
            why="Keyword overlap promotes specific detail chunks over overviews"
        )
        
        return results
    
    # ══════════════════════════════════════════════════════════════
    # STEP 10: Document Drill-Down
    # ══════════════════════════════════════════════════════════════
    
    def _document_drill_down(
        self,
        query: str,
        results: List[Dict[str, Any]],
        xlog: ExplainabilityLogger,
        *,
        force: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        For the top-ranked document, fetch ALL chunks from that document
        and check if a different chunk is a better keyword match for the
        query. This fixes the 'right doc, wrong chunk' pattern where an
        overview or adjacent chunk beats the specific detail chunk.

        Only swaps if the alternative chunk has strictly better keyword
        overlap with the query terms.
        """
        import re
        if not results or len(results) < 1:
            return results

        top = results[0]
        top_meta = top.get("metadata", {})
        # Support both "document_id" (Phase 6 native) and "doc_id" (migrated)
        top_doc_id = (
            top_meta.get("document_id", "") or top_meta.get("doc_id", "")
        ) if isinstance(top_meta, dict) else ""
        
        if not top_doc_id:
            return results

        # Get the set of existing chunk IDs already in results (to avoid duplicates)
        existing_ids = {r.get("id", "") for r in results}

        # Extract meaningful query terms
        stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "what", "which",
            "how", "when", "where", "who", "why", "does", "do", "did", "can",
            "could", "should", "would", "in", "on", "at", "to", "for", "of",
            "with", "by", "from", "as", "or", "and", "not", "be", "been",
            "this", "that", "it", "its", "i", "my", "me", "we", "our",
            "you", "your", "many", "much", "used", "available",
        }
        query_lower = query.lower()
        query_words = [w for w in re.findall(r'\b[\w\-\.]+\b', query_lower) 
                       if w not in stopwords and len(w) > 1]

        if not query_words:
            return results

        # Helper: word-boundary match (avoids false positives like
        # "rpo" matching inside "corporate")
        def _word_in(word: str, text: str) -> bool:
            return bool(re.search(r'\b' + re.escape(word) + r'\b', text))

        # Score the current top chunk
        top_text = top.get("text", top.get("content", "")).lower()
        top_matched = sum(1 for w in query_words if _word_in(w, top_text))
        top_overlap = top_matched / len(query_words)

        # Only consider drill-down if top chunk might be an overview/intro
        # (chunk_index 0 is typically the overview/title) or the top overlap
        # is low (meaning the chunk lacks specific query terms).
        # When force=True (after re-routing), skip this check.
        top_chunk_idx = top_meta.get("chunk_index", top_meta.get("section_index", -1)) if isinstance(top_meta, dict) else -1
        is_likely_overview = (top_chunk_idx == 0 or top_overlap < 0.5)
        
        if not is_likely_overview and not force:
            xlog.step(
                "document_drill_down",
                f"Skipped drill-down: top chunk not overview (idx={top_chunk_idx}, overlap={top_overlap:.2f})",
                detail={"doc_id": top_doc_id, "top_chunk_id": top.get("id", ""), "skip_reason": "not_overview"},
                why="Top chunk appears specific enough, no drill-down needed"
            )
            return results

        # Fetch ALL chunks from the top document
        try:
            all_doc_chunks = self.dual_store.get_document_chunks(top_doc_id)
        except Exception:
            return results

        if not all_doc_chunks:
            return results

        # Score each chunk by keyword overlap
        # Identify priority terms in the query (acronyms, identifiers)
        # These get extra weight in overlap tiebreaking.
        priority_words = set()
        for w in query_words:
            # If the word appears as uppercase in the original query, it's
            # likely a proper noun / acronym and more important
            if w.upper() in query:
                priority_words.add(w)

        # Count total frequency of priority words for tiebreaking
        def _priority_freq(text: str) -> int:
            """Total occurrence count of all priority words in text."""
            return sum(
                len(re.findall(r'\b' + re.escape(w) + r'\b', text))
                for w in priority_words
            )

        best_chunk = None
        best_overlap = top_overlap
        best_matched = top_matched
        best_priority_matched = sum(1 for w in priority_words if _word_in(w, top_text))
        best_priority_freq = _priority_freq(top_text)

        for chunk in all_doc_chunks:
            cid = chunk.get("id", "")
            if cid == top.get("id", ""):
                continue  # Skip the current top chunk
            
            chunk_text = chunk.get("text", "").lower()
            matched = sum(1 for w in query_words if _word_in(w, chunk_text))
            overlap = matched / len(query_words)
            priority_matched = sum(1 for w in priority_words if _word_in(w, chunk_text))

            # Swap if strictly better keyword overlap, or same overlap
            # but more priority terms matched (acronyms/identifiers),
            # or same priority match count but higher frequency of
            # priority terms (the dedicated definition chunk mentions
            # the term more often than a passing reference).
            if overlap > best_overlap:
                pass  # always swap
            elif overlap == best_overlap and priority_matched > best_priority_matched:
                pass  # more distinct priority terms
            elif (overlap == best_overlap and priority_matched == best_priority_matched):
                pf = _priority_freq(chunk_text)
                if pf > best_priority_freq:
                    pass  # higher frequency of priority terms
                elif pf == best_priority_freq and matched > best_matched:
                    pass  # more total keyword matches
                else:
                    continue
            else:
                continue

            best_overlap = overlap
            best_matched = matched
            best_priority_matched = priority_matched
            best_priority_freq = _priority_freq(chunk_text)
            best_chunk = chunk

        swap_performed = False
        min_gap = 0.1  # Require at least 10% improvement to justify swap
        if best_chunk and (best_overlap - top_overlap) >= min_gap:
            # Build a result dict from the better chunk
            new_top = {
                "id": best_chunk["id"],
                "text": best_chunk["text"],
                "metadata": best_chunk.get("metadata", {}),
                "type": best_chunk.get("type", "item"),
                "similarity": top.get("similarity", 0.5),
                "_final_score": top.get("_final_score", 0.5) + 0.01,
                "_drill_down_swap": True,
                "_drill_down_overlap": best_overlap,
                "cross_encoder_score": top.get("cross_encoder_score"),
                "enriched_text": best_chunk["text"],
            }
            # Copy doc_type if present
            if "doc_type" in top:
                new_top["doc_type"] = top["doc_type"]
            
            # If the swapped-in chunk was already in results, remove it
            # to avoid duplicates
            results = [r for r in results if r.get("id", "") != best_chunk["id"]]
            
            # Insert the better chunk at position 0, push old top down
            results.insert(0, new_top)
            swap_performed = True

        xlog.step(
            "document_drill_down",
            f"Drill-down on doc '{top_doc_id}': "
            f"{'swapped' if swap_performed else 'kept'} top chunk "
            f"(top_overlap={top_overlap:.2f}"
            f"{', new_overlap=' + f'{best_overlap:.2f}' if swap_performed else ''})",
            detail={
                "doc_id": top_doc_id,
                "top_chunk_id": top.get("id", ""),
                "top_overlap": round(top_overlap, 3),
                "swap_performed": swap_performed,
                "new_chunk_id": best_chunk["id"] if swap_performed and best_chunk else None,
                "new_overlap": round(best_overlap, 3) if swap_performed else None,
                "doc_total_chunks": len(all_doc_chunks),
            },
            why="Drill into top document to find the best-matching chunk"
        )

        return results
    
    # ══════════════════════════════════════════════════════════════
    # STEP 6: Cross-Encoder Rerank
    # ══════════════════════════════════════════════════════════════
    
    def cross_encoder_rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        xlog: ExplainabilityLogger,
    ) -> List[Dict[str, Any]]:
        """
        Rerank using cross-encoder with enriched context.
        """
        if not self.config.use_cross_encoder or not results:
            return results
        
        # Use enriched_text if available
        reranked = cross_encoder_rerank(
            query, 
            results, 
            content_key="enriched_text"
        )
        
        # Sort by cross-encoder score
        reranked.sort(key=lambda r: r.get("cross_encoder_score", 0), reverse=True)
        
        if reranked and reranked[0].get("cross_encoder_score") is not None:
            top_ce = reranked[0]["cross_encoder_score"]
            xlog.step(
                "cross_encoder_rerank",
                f"Cross-encoder reranked {len(results)} results",
                detail={
                    "top_score": round(top_ce, 4),
                    "score_range": [
                        round(reranked[-1].get("cross_encoder_score", 0), 4),
                        round(top_ce, 4),
                    ],
                },
                why="Cross-encoder provides high-precision semantic matching"
            )
        
        return reranked
    
    # ══════════════════════════════════════════════════════════════
    # STEP 7: RRF Fusion (for multiple sub-queries)
    # ══════════════════════════════════════════════════════════════
    
    def reciprocal_rank_fusion(
        self,
        result_sets: List[List[Dict[str, Any]]],
        k: int = 60,
    ) -> List[Dict[str, Any]]:
        """
        Merge multiple result sets using Reciprocal Rank Fusion.
        
        RRF formula: score = sum(1 / (k + rank)) for each list
        """
        if len(result_sets) == 1:
            return result_sets[0]
        
        rrf_scores: Dict[str, float] = {}
        result_map: Dict[str, Dict] = {}
        
        for result_list in result_sets:
            for rank, result in enumerate(result_list):
                result_id = result.get("id", str(id(result)))
                
                # RRF score contribution
                rrf_scores[result_id] = rrf_scores.get(result_id, 0) + 1 / (k + rank + 1)
                
                # Keep best version of each result
                if result_id not in result_map:
                    result_map[result_id] = result
        
        # Sort by RRF score
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
        
        merged = []
        for result_id in sorted_ids:
            result = result_map[result_id]
            result["rrf_score"] = rrf_scores[result_id]
            merged.append(result)
        
        return merged
    
    # ══════════════════════════════════════════════════════════════
    # MAIN RETRIEVAL FLOW
    # ══════════════════════════════════════════════════════════════
    
    def retrieve(
        self,
        query: str,
        *,
        max_results: int = 10,
        exclude_chunk_ids: set | None = None,
        extra_queries: list[str] | None = None,
        bm25_retriever=None,
        config=None,
        prior_context_terms: list[str] | None = None,
        doc_name_prefix: str | None = None,
    ) -> RetrievalResult:
        """
        Human-like retrieval flow.
        
        Parameters
        ----------
        query : str
            User query text.
        max_results : int
            Maximum results to return.
        exclude_chunk_ids : set | None
            Chunk IDs to exclude from results (Phase 9 re-retrieval).
        extra_queries : list[str] | None
            Phase 8.6 — additional query variants from multi-query expansion.
        bm25_retriever : BM25Retriever | None
            Phase 8.1 — optional BM25 retriever for hybrid search.
        config : KTSConfig | None
            Phase 8 — configuration for feature flags.
        prior_context_terms : list[str] | None
            Defined terms extracted from prior conversation turns.
            These are resolved alongside chunk-extracted terms in the
            definition enrichment step (Step 7) so follow-up queries
            about nested terms get full dependency chains.
        doc_name_prefix : str | None
            Phase 17 — filter results to a specific document prefix (e.g. "PSA").
            When set, all ChromaDB queries include this as a ``where`` filter
            so only chunks from the specified document are returned.
        
        Steps:
        1. Extract filters from query (section numbers, item types)
        2. Decompose compound queries
        3. Graph-first section discovery
        3b. Term-keyword lookup (Q1 per-definition retrieval)
        3c. NER entity role resolution (ASSIGNED_ROLE lookup)
        3d. Q1 section reference extraction
        4. Section-scoped item search (with entity query expansion)
        5. Fallback to global search if needed
        5b. Routing-aware supplemental queries
        6. RRF fusion if multiple result sets
        6a. Phase 8.1 — BM25 hybrid fusion
        6b. Phase 8.2 — MMR diversity selection
        6c. Phase 8.4 — Parent-child expansion
        7. Definition enrichment (with Phase 8.7 TermResolver wiring)
        8. Cross-encoder rerank
        9. Keyword-boost rerank
        10. Document drill-down (conditional)
        11. Compute confidence
        12. Phase 9 exclude_chunk_ids filter
        """
        start_time = time.perf_counter()
        xlog = ExplainabilityLogger(
            "human_like_retrieval",
            doc_id=f"query:{query[:50]}",
            verbose=True,
        )
        
        xlog.step(
            "start",
            f"Human-like retrieval started: '{query}'",
            detail={"max_results": max_results},
            why="Human-like flow mimics TOC lookup → section read → term lookup"
        )
        
        # ── Step 1: Extract filters ───────────────────────────────
        if self.config.enable_self_query_filters:
            filters = self.extract_query_filters(query)
            xlog.step(
                "filter_extraction",
                f"Extracted filters: {filters}",
                detail=filters,
                why="Auto-detect section numbers and item types from query text"
            )
        else:
            filters = {}

        # ── Phase 17: Inject doc_name_prefix into filters ─────────
        if doc_name_prefix:
            filters["doc_name_prefix"] = doc_name_prefix
            xlog.step(
                "doc_filter",
                f"Phase 17 doc filter active: doc_name_prefix={doc_name_prefix}",
                detail={"doc_name_prefix": doc_name_prefix},
                why="Restrict all ChromaDB queries to a single document type"
            )

        # Phase 17: Store base filters for use by all internal search calls
        self._doc_name_prefix = doc_name_prefix
        
        # ── Step 2: Decompose query ───────────────────────────────
        if self.config.enable_query_decomposition:
            sub_queries = self.decompose_query(query)
            xlog.step(
                "query_decomposition",
                f"Decomposed into {len(sub_queries)} sub-queries",
                detail={"sub_queries": sub_queries},
                why="Compound queries benefit from separate retrieval + fusion"
            )
        else:
            sub_queries = [query]
        
        # ── Step 3: Graph-first section discovery ─────────────────
        section_numbers: List[str] = []
        
        # Check if section explicitly mentioned in filters
        if "section_number" in filters:
            section_numbers = [filters["section_number"]]
        else:
            # Graph lookup for relevant sections
            graph_sections = self.graph_section_lookup(query, xlog)
            section_numbers = [s["section_number"] for s in graph_sections if s.get("section_number")]
        
        # ── Step 3b: Term-keyword lookup (Q1) ─────────────────────
        # Scan TERM::* per-definition keywords to find terms whose
        # definitions are semantically relevant to the query.  These
        # feed into the resolution tree in Step 7.
        keyword_matched_terms: List[str] = self.term_keyword_lookup(query, xlog)
        if keyword_matched_terms:
            # Merge with any prior_context_terms so they get resolved
            _prior = list(prior_context_terms or [])
            for t in keyword_matched_terms:
                if t not in _prior:
                    _prior.append(t)
            prior_context_terms = _prior

        # ── Step 3c: NER Entity Role Resolution ──────────────────
        # For party/entity queries, use ASSIGNED_ROLE edges to find
        # which entity fills a role (e.g. Depositor → "SECURITIES I LLC")
        # and boost sections where that entity is formally identified.
        role_result: Dict[str, Any] = {}
        if self._is_party_query(query) or self._is_definition_query(query):
            role_result = self.entity_role_lookup(query, xlog)
            if role_result.get("section_node_ids"):
                # Inject role-matched sections (Preamble first) into
                # section_numbers so section-scoped search includes them
                role_sec_nums: List[str] = []
                for sec_nid in role_result["section_node_ids"]:
                    sn = self.graph.nodes[sec_nid].get("section_number", "")
                    if sn and sn not in section_numbers:
                        role_sec_nums.append(sn)
                if role_sec_nums:
                    # Prepend role sections (Preamble priority)
                    section_numbers = role_sec_nums + section_numbers
                    xlog.step(
                        "entity_section_inject",
                        f"Injected {len(role_sec_nums)} sections from NER role resolution",
                        detail={"injected_sections": role_sec_nums},
                        why="Party queries benefit from sections where the entity is formally identified"
                    )

        # ── Step 3d: Q1 Section Reference Extraction ─────────────
        # When Q1 keywords contain section references (e.g. "section 5.06
        # statement"), extract those section numbers and add them to
        # section discovery so scoped search covers them.
        if keyword_matched_terms:
            q1_sec_refs = self._extract_section_refs_from_keywords(keyword_matched_terms)
            if q1_sec_refs:
                for sec_ref in q1_sec_refs:
                    if sec_ref not in section_numbers:
                        section_numbers.append(sec_ref)
                xlog.step(
                    "q1_section_extraction",
                    f"Extracted {len(q1_sec_refs)} section refs from Q1 term keywords",
                    detail={"section_refs": q1_sec_refs, "source_terms": keyword_matched_terms[:5]},
                    why="Q1 keywords like 'section 5.06 statement' bridge to specific sub-sections"
                )

        # ── Step 4: Section-scoped search ─────────────────────────
        all_result_sets: List[List[Dict]] = []
        
        if section_numbers and self.config.section_scoped_search:
            # Use up to 5 sections (expanded from 3) when NER or Q1
            # have injected extra section candidates
            _max_scoped = 5 if (role_result.get("section_node_ids") or keyword_matched_terms) else 3
            for sub_query in sub_queries:
                # For party queries, also search with entity names
                _queries_to_scope = [sub_query]
                for et in role_result.get("extra_search_terms", [])[:2]:
                    _queries_to_scope.append(f"{sub_query} {et}")

                for sq in _queries_to_scope:
                    scoped_results = self.section_scoped_search(
                        sq,
                        section_numbers[:_max_scoped],
                        xlog,
                        item_type_filter=filters.get("item_type"),
                    )
                    if scoped_results:
                        all_result_sets.append(scoped_results)
        
        # ── Step 5: Fallback to global search if needed ───────────
        if not all_result_sets or (
            self.config.fallback_to_global and 
            sum(len(rs) for rs in all_result_sets) < max_results
        ):
            xlog.step(
                "global_fallback",
                "Falling back to global dual-store search",
                detail={"reason": "insufficient scoped results"},
                why="Global search ensures recall when section scoping is too narrow"
            )
            
            for sub_query in sub_queries:
                # Global item search — Phase 17: apply doc_name_prefix
                item_filters = {"item_type": filters["item_type"]} if "item_type" in filters else None
                item_filters = self._merge_doc_filter(item_filters)
                global_items = self.dual_store.search_items(
                    sub_query, 
                    top_k=max_results * 2,
                    filters=item_filters
                )
                
                # Section search — Phase 17: apply doc_name_prefix
                section_filters = self._merge_doc_filter(None)
                global_sections = self.dual_store.search_sections(
                    sub_query,
                    top_k=max_results,
                    filters=section_filters,
                )
                
                if global_items or global_sections:
                    all_result_sets.append(global_items + global_sections)
        
        # ── Step 5b: Routing-aware supplemental queries ───────────
        #    Detects query intent (definition, architecture, SOP) and
        #    checks if the expected doc category appears in initial results.
        #    If missing, issues a reformulated query targeting that category
        #    to improve recall for cross-product queries.
        routing_intent, routing_categories = self._detect_routing_intent(query)
        if routing_categories:
            # Check if expected category is present in current results
            all_current = [r for rs in all_result_sets for r in rs]
            current_categories = set()
            for r in all_current:
                meta = r.get("metadata", {})
                sp = meta.get("source_path", "") if isinstance(meta, dict) else ""
                if sp:
                    current_categories.add(self._detect_doc_category(sp))
            
            missing_cats = [c for c in routing_categories if c not in current_categories]
            if missing_cats:
                routing_queries = self._generate_routing_queries(
                    query, routing_intent, routing_categories
                )
                for rq in routing_queries:
                    rq_items = self.dual_store.search_items(rq, top_k=max_results, filters=self._merge_doc_filter(None))
                    rq_sections = self.dual_store.search_sections(rq, top_k=5, filters=self._merge_doc_filter(None))
                    if rq_items or rq_sections:
                        all_result_sets.append(rq_items + rq_sections)
                
                xlog.step(
                    "routing_supplemental",
                    f"Added {len(routing_queries)} routing queries for missing '{missing_cats}'",
                    detail={
                        "intent": routing_intent,
                        "missing_categories": missing_cats,
                        "routing_queries": routing_queries,
                    },
                    why="Supplemental routing queries improve recall for cross-product queries"
                )
        
        # ── Step 6: RRF fusion if multiple result sets ────────────
        if len(all_result_sets) > 1:
            merged = self.reciprocal_rank_fusion(all_result_sets)
            xlog.step(
                "rrf_fusion",
                f"Merged {len(all_result_sets)} result sets via RRF",
                detail={"total_results": len(merged)},
                why="RRF gives consistent ranking across multiple sub-query results"
            )
        elif all_result_sets:
            merged = all_result_sets[0]
        else:
            merged = []
        
        # Deduplicate by "id" (same chunk appearing via section + global paths)
        seen_ids: set[str] = set()
        deduped: list[dict] = []
        for r in merged:
            rid = r.get("id", "")
            if rid and rid in seen_ids:
                continue
            if rid:
                seen_ids.add(rid)
            deduped.append(r)
        merged = deduped
        
        # Limit to top results
        merged = merged[:max_results * 2]

        # ── Phase 8.6: Multi-Query RAG Fusion ─────────────────────
        # If extra_queries were supplied by the JS query_expander, run the
        # same pipeline for each variant and RRF-merge with the primary.
        _cfg = config  # Phase 8 KTSConfig
        if extra_queries and _cfg and getattr(_cfg, "multi_query_rag_enabled", False):
            extra_queries = extra_queries[:getattr(_cfg, "multi_query_variants", 4)]
            variant_lists: list[list[dict]] = [merged]
            pool = getattr(_cfg, "multi_query_pool_size", 30)
            for vq in extra_queries:
                vq_items = self.dual_store.search_items(vq, top_k=pool, filters=self._merge_doc_filter(None))
                if vq_items:
                    variant_lists.append(vq_items)
            if len(variant_lists) > 1:
                merged = self._rrf_merge(variant_lists, k=getattr(_cfg, "rrf_constant", 60))
                xlog.step(
                    "multi_query_fusion",
                    f"Fused {len(variant_lists)} query variants via RRF",
                    detail={"extra_queries": extra_queries, "merged_count": len(merged)},
                    why="Multi-query improves recall by covering paraphrase, definitional, and exception angles"
                )

        # ── Phase 8.1: BM25 Hybrid Fusion ────────────────────────
        if bm25_retriever and _cfg and getattr(_cfg, "enable_bm25_hybrid", False):
            bm25_results = bm25_retriever.search(query, top_k=20)
            if bm25_results:
                bm25_w = getattr(_cfg, "bm25_weight", 0.4)
                vec_w = getattr(_cfg, "vector_weight", 0.6)
                rrf_k = getattr(_cfg, "rrf_constant", 60)
                merged = self._rrf_merge([merged, bm25_results], weights=[vec_w, bm25_w], k=rrf_k)
                xlog.step(
                    "bm25_hybrid",
                    f"BM25 hybrid: fused {len(bm25_results)} keyword hits (w={bm25_w}/{vec_w})",
                    detail={"bm25_count": len(bm25_results), "merged_count": len(merged)},
                    why="BM25 captures exact keyword matches missed by dense embeddings"
                )

        # ── Phase 8.5: HyPE (item_questions search lane) ─────────
        if _cfg and getattr(_cfg, "enable_hype", False):
            hype_results = self.dual_store.search_item_questions(query, top_k=10)
            if hype_results:
                # Map question hits back to source chunks
                hype_chunks: list[dict] = []
                for qr in hype_results:
                    src_id = (qr.get("metadata") or {}).get("source_chunk_id", "")
                    if src_id:
                        chunk = self.dual_store.get_by_id(src_id)
                        if chunk:
                            chunk["_matched_via"] = "hype"
                            hype_chunks.append(chunk)
                if hype_chunks:
                    merged = self._rrf_merge(
                        [merged, hype_chunks],
                        weights=[0.7, 0.3],
                        k=getattr(_cfg, "rrf_constant", 60),
                    )

        # ── Phase 8.2: MMR Diversity Selection ────────────────────
        if _cfg and getattr(_cfg, "enable_mmr", False) and merged:
            try:
                lam = getattr(_cfg, "mmr_lambda", 0.7)
                mult = getattr(_cfg, "mmr_fetch_multiplier", 3)
                # Re-query with embeddings for MMR if enough candidates
                if len(merged) > max_results:
                    mmr_items = self.dual_store.search_items_mmr(
                        query,
                        top_k=max_results * 2,
                        fetch_multiplier=mult,
                        lambda_mult=lam,
                    )
                    if mmr_items:
                        merged = mmr_items
                        xlog.step(
                            "mmr_diversity",
                            f"MMR selected {len(mmr_items)} diverse results (lambda={lam})",
                            detail={"lambda": lam, "count": len(mmr_items)},
                            why="MMR reduces redundancy between top results"
                        )
            except Exception as exc:
                logger.debug("[Phase8] MMR skipped: %s", exc)

        # ── Phase 8.4: Parent-Child Expansion ─────────────────────
        if _cfg and getattr(_cfg, "enable_parent_expansion", False) and merged:
            max_p = getattr(_cfg, "max_parent_sections", 10)
            parents = self._expand_items_to_parent_sections(merged, max_parents=max_p)
            if parents:
                merged.extend(parents)
                xlog.step(
                    "parent_expansion",
                    f"Expanded {len(parents)} parent sections from item matches",
                    detail={"parent_count": len(parents), "max_parents": max_p},
                    why="Parent sections provide surrounding context for item-level matches"
                )
        
        # ── Step 7: Definition enrichment ─────────────────────────
        shared_glossary = ""
        if self.config.inject_definitions:
            merged, shared_glossary = self.enrich_with_definitions(
                merged, xlog,
                prior_context_terms=prior_context_terms,
            )
        
        # ── Step 8: Cross-encoder rerank ──────────────────────────
        if self.config.use_cross_encoder:
            merged = self.cross_encoder_rerank(query, merged, xlog)
        
        # ── Step 9: Keyword-match reranking (post cross-encoder) ──
        # Applied AFTER cross-encoder to fine-tune the final ranking
        # with keyword signals that the CE model may underweight.
        merged = self._keyword_boost_rerank(query, merged, xlog)
        
        # ── Step 10: Conditional document drill-down ─────────────
        #    Re-enabled ONLY for queries with strong routing signals
        #    (definition/acronym queries into Glossary, tech queries into
        #    Architecture) where the top result is an overview chunk
        #    (chunk_index=0). This fixes "right doc, wrong chunk" without
        #    the regressions that full drill-down caused.
        routing_intent_dd, routing_cats_dd = self._detect_routing_intent(query)
        if routing_intent_dd in ("definition", "acronym", "what_is", "architecture") and merged:
            top_meta = merged[0].get("metadata", {})
            if isinstance(top_meta, dict):
                top_source = top_meta.get("source_path", "")
                top_cat = self._detect_doc_category(top_source)
                # Support both item chunks (chunk_index) and section results (section_index)
                top_idx = top_meta.get("chunk_index", top_meta.get("section_index", -1))
                logger.debug(
                    "[Step10] intent=%s cats=%s top_cat=%s top_idx=%s source=%s",
                    routing_intent_dd, routing_cats_dd, top_cat, top_idx,
                    top_source[-40:] if top_source else "EMPTY"
                )
                # Drill down if:
                #   (a) top result is from the expected category AND is an
                #       overview chunk (index 0) — classic "right doc, wrong chunk"
                #   (b) top result is from a WRONG category but the expected
                #       category exists somewhere in the top 5 — re-route the
                #       drill-down into that document instead
                if top_cat in routing_cats_dd and top_idx == 0:
                    merged = self._document_drill_down(query, merged, xlog)
                elif top_cat not in routing_cats_dd:
                    # Find the first result from the expected category and
                    # try to drill down into THAT document instead
                    for alt_i, alt_r in enumerate(merged[1:6], start=1):
                        alt_meta = alt_r.get("metadata", {})
                        if not isinstance(alt_meta, dict):
                            continue
                        alt_cat = self._detect_doc_category(alt_meta.get("source_path", ""))
                        if alt_cat in routing_cats_dd:
                            # Swap this result to position 0 and drill-down
                            merged.insert(0, merged.pop(alt_i))
                            merged = self._document_drill_down(query, merged, xlog, force=True)
                            xlog.step(
                                "document_drill_down",
                                f"Re-routed from {top_cat} to {alt_cat} (rank {alt_i+1}→1)",
                                detail={"original_top_cat": top_cat, "new_top_cat": alt_cat},
                                why="Wrong-doc re-routing: the expected category was found lower in results"
                            )
                            break
                    else:
                        xlog.step(
                            "document_drill_down",
                            f"Skipped: top_cat={top_cat} (expected {routing_cats_dd}), no alt found",
                            detail={"top_source": top_source[-60:], "top_cat": top_cat, "top_idx": top_idx},
                            why="Expected category not in top results"
                        )
                else:
                    xlog.step(
                        "document_drill_down",
                        f"Skipped: top_cat={top_cat} matches but idx={top_idx} (not overview)",
                        detail={"top_source": top_source[-60:], "top_cat": top_cat, "top_idx": top_idx},
                        why="Right category but not an overview chunk — specific enough"
                    )
        
        # ── Step 11: Compute confidence ───────────────────────────
        final_results = merged[:max_results]

        # ── Step 11b: Enrich section labels for proper citations ──
        # Normalise section_number to human-friendly labels (e.g.
        # "Article III — ACCOUNTS") so the LLM cites correctly.
        if self._section_label_map:
            for r in final_results:
                meta = r.get("metadata", {})
                if isinstance(meta, dict):
                    sec_num = meta.get("section_number", "") or r.get("section_number", "")
                    sec_heading = meta.get("section_heading", "") or r.get("section_heading", "")
                    if sec_num:
                        label = self._section_label_map.get(sec_num, "")
                        if label:
                            r["section_label"] = label
                            if isinstance(meta, dict):
                                meta["section_label"] = label
                        if sec_heading and isinstance(meta, dict) and "section_heading" not in meta:
                            meta["section_heading"] = sec_heading

        # ── Step 11c: Collect NER role context ────────────────────
        # Entity role mappings are collected as structured data and
        # sent once as a preamble — NOT duplicated into every chunk.
        collected_entity_roles: List[Dict[str, str]] = []
        if role_result.get("role_entities"):
            for re_entry in role_result["role_entities"]:
                collected_entity_roles.append({
                    "entity": re_entry["entity"],
                    "term": re_entry["term"].title(),
                })
        
        if final_results:
            top_ce = final_results[0].get("cross_encoder_score")
            if top_ce is not None:
                import math
                confidence = 1.0 / (1.0 + math.exp(-top_ce))  # Sigmoid
            else:
                confidence = final_results[0].get("similarity", 0.0)
        else:
            confidence = 0.0
        
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        
        # ── Phase 9: Exclude already-seen chunk IDs (re-retrieval) ──
        if exclude_chunk_ids:
            final_results = [
                r for r in final_results
                if r.get("id", r.get("metadata", {}).get("id", "")) not in exclude_chunk_ids
            ]

        xlog.step(
            "complete",
            f"Retrieval complete: {len(final_results)} results, confidence={confidence:.3f}",
            detail={
                "elapsed_ms": round(elapsed_ms, 2),
                "confidence": round(confidence, 4),
                "sections_used": section_numbers[:3],
                "definitions_injected": sum(
                    len(r.get("injected_definitions", [])) 
                    for r in final_results
                ),
            },
            why="Human-like retrieval complete"
        )
        
        trace_data = xlog.done()
        return RetrievalResult(
            results=final_results,
            confidence=confidence,
            trace=trace_data.get("steps", []),
            definitions_glossary=shared_glossary,
            entity_roles=collected_entity_roles,
        )
