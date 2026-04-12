"""
Enhanced graph builder with hierarchical structure for Phase 6.

Adapted from the Phase 6 design to use the existing NetworkX-based
GraphStore instead of Neo4j.  All operations are pure-NetworkX so no
external database is required.

Graph Structure:
    Document --CONTAINS--> Section --HAS_RULE/HAS_DEFINITION--> Item
    Section --NEXT--> Section (sequential)
    Item --REFERENCES--> Item (dependencies)

Phase 19 addition:
    LLM-assisted entity extraction adds ENTITY, KEYPHRASE, and
    CROSS_REFERENCE nodes that regex item extractors miss.
"""

from __future__ import annotations

import hashlib
import json as _json
import logging
import re
from typing import Any, Dict, List, Optional

import networkx as nx

from backend.extraction.item_extractor_base import Item, get_item_extractor
from backend.graph.concept_vocabulary import ConceptVocabularyBuilder
from backend.graph.persistence import GraphStore

logger = logging.getLogger(__name__)

# ── LLM extraction prompt for legal / governing documents ─────────
_LEGAL_LLM_EXTRACTION_PROMPT = """\
You are a legal document analyst.  From the following section of a
governing / legal document, extract structured entities that a
keyword-based extractor would miss.

SECTION NUMBER: {section_number}
SECTION HEADING: {heading}
SECTION TEXT:
{text}

Extract ALL instances of:
1. ENTITY — named parties, organisations, regulatory bodies, statutes
2. KEYPHRASE — domain-specific terms, defined terms not in quotes,
   important legal concepts (e.g. "force majeure", "material adverse change")
3. CROSS_REFERENCE — references to other sections, clauses, schedules,
   appendices, or external acts/regulations
4. OBLIGATION — implicit obligations not beginning with "shall"/"must"
5. CONDITION — triggering conditions (if … then, subject to, provided that)

Return valid JSON:
{{
  "entities": [
    {{"type": "ENTITY", "text": "...", "confidence": 0.85}},
    {{"type": "KEYPHRASE", "text": "...", "confidence": 0.8}},
    {{"type": "CROSS_REFERENCE", "text": "Section 4.2", "confidence": 0.9}},
    ...
  ]
}}

Only return the JSON object.  No markdown fences."""


class EnhancedGraphBuilder:
    """
    Hierarchical graph builder for Phase 6.

    Uses the existing project ``GraphStore`` (NetworkX + JSON persistence)
    so the build is fully offline — no Neo4j required.
    """

    def __init__(self, store: GraphStore) -> None:
        self.store = store

    # ── Main entry point ──────────────────────────────────────────

    def build_hierarchical_graph(
        self,
        document_id: str,
        doc_type: str,
        sections: List[Dict[str, Any]],
        *,
        doc_metadata: Optional[Dict[str, Any]] = None,
        doc_name_prefix: str = "",
        llm_callable: Any | None = None,
    ) -> Dict[str, int]:
        """
        Build hierarchical graph for document.

        Args:
            document_id: Document identifier
            doc_type: Document type (for extractor routing)
            sections: List of section dicts with keys:
                - section_number: str
                - section_heading: str
                - section_text: str
            doc_metadata: Optional extra attributes for the document node

        Returns:
            Stats dict with keys: sections_created, items_created, edges_created
        """
        stats = {"sections_created": 0, "items_created": 0, "edges_created": 0}

        G: nx.DiGraph = self.store.load()

        # Get appropriate item extractor for this document type
        extractor = get_item_extractor(doc_type)

        # Create / update document node
        doc_node_id = f"doc:{document_id}"
        doc_attrs: dict[str, Any] = {
            "type": "DOCUMENT",
            "doc_type": doc_type,
            "doc_name_prefix": doc_name_prefix,
            **(doc_metadata or {}),
        }
        G.add_node(doc_node_id, **doc_attrs)

        logger.info(
            f"[Phase6-Graph] Building hierarchical graph for {document_id} "
            f"({len(sections)} sections, doc_type={doc_type})"
        )

        prev_section_id: str | None = None
        all_items: list[Item] = []

        for section_index, section_dict in enumerate(sections):
            section_number = section_dict["section_number"]
            section_heading = section_dict["section_heading"]
            section_text = section_dict["section_text"]

            # ── Section node ──────────────────────────────────────
            section_id = f"sec:{document_id}:{section_index:04d}"

            # Build a short synopsis from the first ~200 chars of the
            # section body.  This enables query-time matching against
            # section *content* (not just headings), which is critical
            # for sections like "Preamble" whose heading is generic but
            # whose body identifies the parties.
            synopsis = self._build_section_synopsis(section_heading, section_text)

            G.add_node(
                section_id,
                type="SECTION",
                heading=section_heading,
                section_number=section_number,
                section_index=section_index,
                doc_id=document_id,
                doc_name_prefix=doc_name_prefix,
                section_synopsis=synopsis,
            )
            stats["sections_created"] += 1

            # CONTAINS edge: Document → Section
            G.add_edge(doc_node_id, section_id, type="CONTAINS", weight=1.0, doc_name_prefix=doc_name_prefix)
            stats["edges_created"] += 1

            # NEXT edge: PrevSection → ThisSection
            if prev_section_id:
                G.add_edge(prev_section_id, section_id, type="NEXT", weight=0.8, doc_name_prefix=doc_name_prefix)
                stats["edges_created"] += 1
            prev_section_id = section_id

            # ── Extract items from section ────────────────────────
            items = extractor.extract_items(
                section_text=section_text,
                section_number=section_number,
                section_heading=section_heading,
                section_index=section_index,
                document_id=document_id,
            )

            for item in items:
                # Item node
                G.add_node(
                    item.id,
                    type="ITEM",
                    item_type=item.item_type,
                    text=item.text[:500],
                    document_id=item.document_id,
                    section_number=item.section_number,
                    section_heading=item.section_heading,
                    section_index=item.section_index,
                    item_index=item.item_index,
                    doc_name_prefix=doc_name_prefix,
                )
                stats["items_created"] += 1

                # Typed edge: Section → Item
                edge_type = self._get_edge_type_for_item(item.item_type)
                edge_weight = self._get_edge_weight_for_item(item.item_type)
                G.add_edge(section_id, item.id, type=edge_type, weight=edge_weight, doc_name_prefix=doc_name_prefix)
                stats["edges_created"] += 1

            all_items.extend(items)

        # ── REFERENCES edges (cross-item) ─────────────────────────
        refs_created = self._create_reference_edges(G, all_items, doc_name_prefix=doc_name_prefix)
        stats["edges_created"] += refs_created

        # ── Phase 19: LLM-assisted entity extraction ─────────────
        # Discover ENTITY, KEYPHRASE, CROSS_REFERENCE nodes that the
        # regex item extractors miss.  Runs per-section and attaches
        # new nodes to the corresponding section node.
        if llm_callable is not None:
            llm_stats = self._llm_enrich_sections(
                G, document_id, sections, llm_callable,
                doc_name_prefix=doc_name_prefix,
            )
            stats["llm_entities"] = llm_stats.get("entities_created", 0)
            stats["llm_edges"] = llm_stats.get("edges_created", 0)

        # ── Concept vocabulary enrichment ─────────────────────────
        # Enrich section nodes with concept_keywords derived from their
        # items, defined terms, and cross-references.  This makes
        # graph_section_lookup() doc-aware — no hardcoded vocabulary.
        try:
            vocab_stats = ConceptVocabularyBuilder.enrich(
                G, llm_callable=llm_callable,
            )
            stats["concept_keywords"] = vocab_stats.get("total_concept_keywords", 0)
            stats["step_back_entries"] = vocab_stats.get("step_back_entries", 0)
            stats["llm_term_synonyms"] = vocab_stats.get("llm_term_synonyms", 0)
            stats["llm_skipped"] = vocab_stats.get("llm_skipped", False)
        except Exception:
            logger.warning("[Phase6-Graph] Concept vocabulary enrichment failed", exc_info=True)

        # Persist
        self.store.save(G)
        logger.info(f"[Phase6-Graph] Done — {stats}")
        return stats

    # ── Phase 19: LLM entity enrichment ─────────────────────────────

    def _llm_enrich_sections(
        self,
        G: nx.DiGraph,
        document_id: str,
        sections: List[Dict[str, Any]],
        llm_callable: Any,
        *,
        doc_name_prefix: str = "",
    ) -> Dict[str, int]:
        """Use LLM to extract additional entities per section.

        Adds ENTITY / KEYPHRASE / CROSS_REFERENCE / OBLIGATION /
        CONDITION nodes that the regex item extractor missed.

        Returns stats ``{entities_created, edges_created}``.
        """
        stats = {"entities_created": 0, "edges_created": 0}
        allowed_types = {
            "ENTITY", "KEYPHRASE", "CROSS_REFERENCE",
            "OBLIGATION", "CONDITION",
        }

        for section_index, section_dict in enumerate(sections):
            section_number = section_dict.get("section_number", "")
            heading = section_dict.get("section_heading", "")
            text = section_dict.get("section_text", "")
            if not text.strip():
                continue

            section_id = f"sec:{document_id}:{section_index:04d}"
            if section_id not in G:
                continue

            try:
                prompt = _LEGAL_LLM_EXTRACTION_PROMPT.format(
                    section_number=section_number,
                    heading=heading,
                    text=text[:3000],
                )
                raw = llm_callable(prompt)
                if not raw or not isinstance(raw, str):
                    continue

                # Strip markdown fences
                raw = raw.strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^```(?:json)?\s*", "", raw)
                    raw = re.sub(r"\s*```$", "", raw)

                data = _json.loads(raw)

                seen_keys: set[str] = set()
                for e in data.get("entities", []):
                    etype = (e.get("type") or "").upper()
                    etext = (e.get("text") or "").strip()
                    conf = float(e.get("confidence", 0.75))

                    if not etext or len(etext) < 2 or etype not in allowed_types:
                        continue

                    dedup_key = f"{etype}:{etext.lower()}"
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    node_id = self._make_llm_entity_id(etype, etext, document_id)

                    # Avoid overwriting existing nodes
                    if node_id not in G:
                        G.add_node(
                            node_id,
                            type=etype,
                            text=etext[:300],
                            document_id=document_id,
                            section_number=section_number,
                            confidence=min(conf, 0.90),
                            source="llm",
                            doc_name_prefix=doc_name_prefix,
                        )
                        stats["entities_created"] += 1

                    # Section → entity edge
                    edge_type = self._get_edge_type_for_item(etype)
                    if not G.has_edge(section_id, node_id):
                        G.add_edge(
                            section_id, node_id,
                            type=edge_type,
                            weight=0.5,
                            source="llm",
                            doc_name_prefix=doc_name_prefix,
                        )
                        stats["edges_created"] += 1

            except Exception as exc:
                logger.debug(
                    "[Phase19-Graph] LLM enrichment failed for section %d: %s",
                    section_index, exc,
                )
                continue

        logger.info(
            "[Phase19-Graph] LLM enrichment: %d entities, %d edges for %s",
            stats["entities_created"], stats["edges_created"], document_id,
        )
        return stats

    @staticmethod
    def _make_llm_entity_id(etype: str, text: str, doc_id: str) -> str:
        """Generate a deterministic node ID for an LLM-extracted entity."""
        slug = re.sub(r'\W+', '_', text.lower())[:50]
        h = hashlib.md5(f"{doc_id}:{etype}:{text}".encode()).hexdigest()[:8]
        return f"llm_{etype.lower()}:{slug}_{h}"

    # ── REFERENCES edges ──────────────────────────────────────────

    def _create_reference_edges(self, G: nx.DiGraph, items: List[Item], *, doc_name_prefix: str = "") -> int:
        """
        Create REFERENCES edges between items based on defined-term mentions.
        """
        # Build definition lookup: term_lower → item_id
        definitions: dict[str, str] = {}
        for item in items:
            if item.item_type == "Definition":
                defined_term = self._extract_defined_term(item.text)
                if defined_term:
                    definitions[defined_term.lower()] = item.id

        if not definitions:
            return 0

        edges_created = 0
        for item in items:
            if item.item_type == "Definition":
                continue
            item_text_lower = item.text.lower()
            for defined_term, definition_id in definitions.items():
                if defined_term in item_text_lower:
                    G.add_edge(item.id, definition_id, type="REFERENCES", weight=0.4, doc_name_prefix=doc_name_prefix)
                    edges_created += 1

        return edges_created

    @staticmethod
    def _extract_defined_term(definition_text: str) -> Optional[str]:
        """Extract the term being defined from definition text."""
        quoted = re.search(r'"([^"]+)"', definition_text)
        if quoted:
            return quoted.group(1)
        capitalized = re.search(r"([A-Z][A-Za-z\s]+)\s+means", definition_text)
        if capitalized:
            return capitalized.group(1).strip()
        return None

    # ── Edge-type / weight helpers ────────────────────────────────

    @staticmethod
    def _build_section_synopsis(heading: str, section_text: str) -> str:
        """Build a short synopsis from the section heading + opening text.

        The synopsis captures the first ~200 chars of the section body
        (to the nearest sentence boundary) and prepends the heading.
        This is stored on the graph node and used at query time for
        content-level section matching.
        """
        # Take first ~200 chars, try to break at sentence boundary
        snippet = section_text[:250].strip()
        # Find last sentence-ending period within 200 chars
        for end_char in (".\n", ". ", ".\r"):
            last_period = snippet[:200].rfind(end_char)
            if last_period > 50:
                snippet = snippet[: last_period + 1]
                break
        else:
            snippet = snippet[:200]

        return f"{heading}: {snippet}" if heading else snippet

    @staticmethod
    def _get_edge_type_for_item(item_type: str) -> str:
        mapping: dict[str, str] = {
            # Legal
            "Obligation": "HAS_RULE",
            "Prohibition": "HAS_RULE",
            "Definition": "HAS_DEFINITION",
            "Right": "HAS_RIGHT",
            "Condition": "HAS_CONDITION",
            # Technical
            "Requirement": "HAS_REQUIREMENT",
            "Procedure": "HAS_PROCEDURE",
            "Configuration": "HAS_CONFIGURATION",
            "Warning": "HAS_WARNING",
            # Research
            "Theorem": "HAS_THEOREM",
            "Proof": "HAS_PROOF",
            "Lemma": "HAS_LEMMA",
            "Algorithm": "HAS_ALGORITHM",
        }
        return mapping.get(item_type, "HAS_ITEM")

    @staticmethod
    def _get_edge_weight_for_item(item_type: str) -> float:
        if item_type in {"Definition", "Theorem", "Lemma"}:
            return 0.9
        if item_type in {"Obligation", "Prohibition", "Requirement", "Warning"}:
            return 0.7
        if item_type in {"Right", "Procedure", "Proof", "Algorithm"}:
            return 0.6
        return 0.5
