"""NER Graph Enricher — Layers 2, 3, and 4.

Runs spaCy NER over every section and every defined-term definition in
the knowledge graph, then wires results into the graph as ENTITY nodes
and MENTIONS / ASSIGNED_ROLE edges.

Layers implemented here
-----------------------
Layer 2 — Section-level NER
    Each SECTION node gets MENTIONS edges to ENTITY nodes (one per
    unique entity found in that section's item texts).

Layer 3 — Role assignment
    Detects "X, as Trustee" / "X acting as Servicer" patterns and
    creates ASSIGNED_ROLE edges: ENTITY → TERM::* node.

Layer 4 — Custom entity ruler (DEFINED_TERM type)
    Before running the statistical NER model, injects every
    ``defined_term`` node name as a custom pattern so spaCy labels
    those spans as ``DEFINED_TERM`` instead of (or in addition to)
    the default label.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx

logger = logging.getLogger(__name__)

# Regex for "X, as <Role>" or "X acting as <Role>" patterns.
# Groups: (1) entity surface form, (2) role label
_ROLE_RE = re.compile(
    r'([A-Z][A-Za-z0-9 ,\.&]{2,80}?)'        # entity name (not greedy)
    r',?\s+(?:acting\s+as|as)\s+'             # ", as" or "acting as"
    r'([A-Z][A-Za-z ]+?)(?=[,\.;\)\n]|$)',    # role name
    re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class NERGraphEnricher:
    """Enriches the knowledge graph with entity and role information.

    Usage::

        NERGraphEnricher.enrich(G, sections)

    All operations are **in-place** on *G*.  Returns a statistics dict.
    """

    # ── Public entry point ────────────────────────────────────────

    @classmethod
    def enrich(
        cls,
        G: nx.DiGraph,
        sections: Optional[List[Dict]] = None,
        *,
        spacy_model_path: Optional[str] = None,
    ) -> Dict:
        """Run all NER enrichment layers on *G*.

        Parameters
        ----------
        G : nx.DiGraph
            The knowledge graph (modified in-place).
        sections : list of dicts, optional
            Raw section dicts from the ingestion pipeline, each with
            at least ``section_number`` and ``section_text`` keys.
            When provided the full section text is used for NER; when
            absent only item-node texts stored on the graph are used.
        spacy_model_path : str, optional
            Explicit path to a spaCy model directory (forwarded to
            ``NERExtractor``).  Falls back to package / env-var lookup.

        Returns
        -------
        dict
            Enrichment statistics.
        """
        stats: Dict = {
            "entity_nodes_created": 0,
            "entity_nodes_updated": 0,
            "section_mentions_added": 0,
            "term_mentions_added": 0,
            "role_assignments_added": 0,
            "sections_processed": 0,
            "terms_processed": 0,
            "ner_available": False,
        }

        # ── Load spaCy (lazy singleton from ner_extractor) ────────
        nlp = cls._load_nlp(spacy_model_path)
        if nlp is None:
            logger.warning(
                "[NER Enricher] spaCy model not available — NER graph enrichment skipped. "
                "Install en_core_web_sm: pip install en_core_web_sm"
            )
            return stats
        stats["ner_available"] = True

        # ── Layer 4: Inject custom entity ruler from TERM::* names ─
        term_names = cls._collect_term_names(G)
        if term_names:
            try:
                from backend.ingestion.ner_extractor import create_term_entity_ruler
                create_term_entity_ruler(nlp, term_names)
                logger.debug(
                    "[NER Enricher] Entity ruler injected with %d defined-term patterns",
                    len(term_names),
                )
            except Exception as exc:
                logger.debug("[NER Enricher] Entity ruler setup failed (non-fatal): %s", exc)

        # ── Layer 2: Section-level NER ─────────────────────────────
        section_text_map = cls._build_section_text_map(G, sections or [])
        for sec_node_id, sec_text in section_text_map.items():
            if not sec_text.strip():
                continue
            entities = cls._run_ner(nlp, sec_text)
            for ent_text, ent_label in entities:
                ent_node_id = cls._get_or_create_entity(G, ent_text, ent_label, stats)
                if not G.has_edge(sec_node_id, ent_node_id):
                    G.add_edge(sec_node_id, ent_node_id, type="MENTIONS")
                    stats["section_mentions_added"] += 1
            stats["sections_processed"] += 1

        # ── Layer 2: defined_term NER ──────────────────────────────
        for node_id, data in list(G.nodes(data=True)):
            if data.get("type") != "defined_term":
                continue
            def_text = data.get("definition_text", "")
            if not def_text:
                continue
            entities = cls._run_ner(nlp, def_text)
            for ent_text, ent_label in entities:
                ent_node_id = cls._get_or_create_entity(G, ent_text, ent_label, stats)
                if not G.has_edge(node_id, ent_node_id):
                    G.add_edge(node_id, ent_node_id, type="MENTIONS")
                    stats["term_mentions_added"] += 1
            stats["terms_processed"] += 1

        # ── Layer 3: Role assignment (ASSIGNED_ROLE edges) ────────
        term_names_lower: Dict[str, str] = {
            tn.lower(): nid
            for nid, tn in (
                (n, G.nodes[n].get("term_name", ""))
                for n in G.nodes
                if G.nodes[n].get("type") == "defined_term"
            )
            if tn
        }

        all_texts = list(section_text_map.values())
        for node_id, data in G.nodes(data=True):
            if data.get("type") == "defined_term":
                def_text = data.get("definition_text", "")
                if def_text:
                    all_texts.append(def_text)

        for text in all_texts:
            added = cls._detect_role_assignments(text, G, term_names_lower, stats)
            stats["role_assignments_added"] += added

        # ── Clean up ruler ─────────────────────────────────────────
        if term_names:
            try:
                from backend.ingestion.ner_extractor import remove_term_entity_ruler
                remove_term_entity_ruler(nlp)
            except Exception:
                pass

        logger.info(
            "[NER Enricher] Done — %d entity nodes, %d section mentions, "
            "%d term mentions, %d role assignments",
            stats["entity_nodes_created"] + stats["entity_nodes_updated"],
            stats["section_mentions_added"],
            stats["term_mentions_added"],
            stats["role_assignments_added"],
        )
        return stats

    # ── Internal helpers ──────────────────────────────────────────

    @staticmethod
    def _load_nlp(model_path: Optional[str] = None):
        """Return the spaCy model (None if unavailable)."""
        try:
            from backend.ingestion.ner_extractor import _load_model
            return _load_model(model_path)
        except Exception as exc:
            logger.debug("[NER Enricher] Could not import ner_extractor: %s", exc)
            return None

    @staticmethod
    def _collect_term_names(G: nx.DiGraph) -> List[str]:
        """Return all defined_term names from the graph."""
        names = []
        for _, data in G.nodes(data=True):
            if data.get("type") == "defined_term":
                tn = data.get("term_name", "")
                if tn:
                    names.append(tn)
        return names

    @staticmethod
    def _build_section_text_map(
        G: nx.DiGraph,
        sections: List[Dict],
    ) -> Dict[str, str]:
        """Map section node_id → full text for NER.

        Combines the raw ``section_text`` from the ingestion pipeline
        (rich, full text) with any ITEM texts stored as graph nodes.
        """
        # Build a lookup: section_number → raw text from ingestion
        raw_by_num: Dict[str, str] = {}
        for sec in sections:
            num = str(sec.get("section_number", "")).strip()
            txt = sec.get("section_text", "")
            if num and txt:
                raw_by_num[num] = txt

        result: Dict[str, str] = {}
        for node_id, data in G.nodes(data=True):
            if data.get("type", "").upper() != "SECTION":
                continue

            sec_num = str(data.get("section_number", "")).strip()

            # Prefer raw ingestion text (richest)
            if sec_num in raw_by_num:
                result[node_id] = raw_by_num[sec_num]
                continue

            # Fall back: concatenate texts from ITEM children
            child_texts: List[str] = []
            for _, child_id, edata in G.out_edges(node_id, data=True):
                if edata.get("type") in ("HAS_ITEM", "HAS_RULE", "HAS_DEFINITION"):
                    child_text = G.nodes[child_id].get("text", "")
                    if child_text:
                        child_texts.append(child_text)
            if child_texts:
                result[node_id] = " ".join(child_texts)

        return result

    @staticmethod
    def _run_ner(nlp, text: str) -> List[Tuple[str, str]]:
        """Run spaCy NER; return list of (surface_form, label) pairs."""
        # Truncate very long texts to avoid spaCy memory issues
        max_chars = 100_000
        if len(text) > max_chars:
            text = text[:max_chars]
        try:
            doc = nlp(text)
            seen: Set[Tuple[str, str]] = set()
            results = []
            for ent in doc.ents:
                surface = ent.text.strip()
                label = ent.label_
                if len(surface) < 2:
                    continue
                key = (surface.lower(), label)
                if key not in seen:
                    seen.add(key)
                    results.append((surface, label))
            return results
        except Exception as exc:
            logger.debug("[NER Enricher] NER failed on text snippet: %s", exc)
            return []

    @staticmethod
    def _get_or_create_entity(
        G: nx.DiGraph,
        surface: str,
        label: str,
        stats: Dict,
    ) -> str:
        """Return the entity node ID, creating or updating it as needed."""
        ent_id = f"entity:{label.lower()}:{surface.lower().replace(' ', '_')}"
        if G.has_node(ent_id):
            # Increment mention counter
            G.nodes[ent_id]["mention_count"] = G.nodes[ent_id].get("mention_count", 1) + 1
            stats["entity_nodes_updated"] += 1
        else:
            G.add_node(
                ent_id,
                type="ENTITY",
                entity_type=label,
                surface_form=surface,
                mention_count=1,
            )
            stats["entity_nodes_created"] += 1
        return ent_id

    @staticmethod
    def _detect_role_assignments(
        text: str,
        G: nx.DiGraph,
        term_names_lower: Dict[str, str],
        stats: Dict,
    ) -> int:
        """Find 'X, as <Role>' patterns and add ASSIGNED_ROLE edges.

        Returns the number of new edges added.
        """
        added = 0
        for m in _ROLE_RE.finditer(text):
            entity_surface = m.group(1).strip()
            role_label = m.group(2).strip()

            # Check if role_label corresponds to a known defined term
            term_node_id = term_names_lower.get(role_label.lower())
            if term_node_id is None:
                continue

            # Create/find entity node
            ent_id = f"entity:ORG:{entity_surface.lower().replace(' ', '_')}"
            if not G.has_node(ent_id):
                G.add_node(
                    ent_id,
                    type="ENTITY",
                    entity_type="ORG",
                    surface_form=entity_surface,
                    mention_count=1,
                )
                stats["entity_nodes_created"] += 1

            # Add ASSIGNED_ROLE edge if not yet present
            if not G.has_edge(ent_id, term_node_id):
                G.add_edge(ent_id, term_node_id, type="ASSIGNED_ROLE")
                added += 1

        return added
