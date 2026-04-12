"""Phase 19.3 — Troubleshooting Graph Builder.

Builds a NetworkX DiGraph for non-legal troubleshooting documents by
extracting structured entities (error codes, symptoms, root causes,
solutions, workarounds, components) and linking them.

Two extraction strategies:
1. **Regex / heuristic** — fast, no LLM needed, works on structured docs
2. **LLM-assisted** — optional, called when ``llm_callable`` is provided

The builder stores its graph via the existing ``GraphStore`` persistence
layer (JSON node-link format) but writes to a **separate file** from
the legal knowledge graph.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set

import networkx as nx

from backend.graph.persistence import GraphStore
from backend.graph.troubleshooting_schema import (
    TS_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)


# ── Regex patterns for entity extraction ──────────────────────────

_ERROR_CODE_RE = re.compile(
    r'\b('
    r'ERR[-_]?[A-Z]*[-_]?\d{3,}'       # ERR-AUTH-001, ERR_DB_500
    r'|E[-_]?\d{3,}'                     # E-1234, E_500
    r'|HTTP\s*\d{3}'                     # HTTP 500, HTTP404
    r'|0x[0-9A-Fa-f]{4,}'               # 0xDEADBEEF
    r'|[A-Z]{2,}\d{3,4}'                # AUTH001, IO5090
    r'|Error\s+(?:Code\s+)?\d{3,}'      # Error 404, Error Code 503
    r')\b',
    re.IGNORECASE,
)

_SYMPTOM_PATTERNS = [
    re.compile(r'(?:symptom|symptoms?|displays?|shows?|appears?|manifests?)\s*[:—\-]\s*(.+)', re.I),
    re.compile(r'(?:user\s+(?:sees?|observes?|experiences?|reports?|encounters?))\s+(.+)', re.I),
    re.compile(r'(?:the\s+(?:system|application|service|page|screen))\s+(?:shows?|displays?|returns?)\s+(.+)', re.I),
    re.compile(r'(?:you\s+(?:may|might|will|could)\s+(?:see|get|receive|encounter))\s+(.+)', re.I),
]

_ROOT_CAUSE_PATTERNS = [
    re.compile(r'(?:root\s+cause|cause|caused\s+by|reason|because)\s*[:—\-]\s*(.+)', re.I),
    re.compile(r'(?:this\s+(?:occurs?|happens?|is\s+(?:caused|due)))\s+(?:when|because|due\s+to)\s+(.+)', re.I),
]

_SOLUTION_PATTERNS = [
    re.compile(r'(?:solution|resolution|fix|to\s+(?:resolve|fix))\s*[:—\-]\s*(.+)', re.I),
    re.compile(r'(?:steps?\s+to\s+(?:resolve|fix|repair))\s*[:—\-]?\s*(.+)', re.I),
]

_WORKAROUND_PATTERNS = [
    re.compile(r'(?:workaround|temporary\s+fix|mitigation|interim\s+solution)\s*[:—\-]\s*(.+)', re.I),
]

_COMPONENT_PATTERNS = [
    re.compile(r'(?:component|module|service|system|subsystem)\s*[:—\-]\s*(.+)', re.I),
    re.compile(r'(?:in\s+the\s+)(\w+(?:\s+\w+){0,2})(?:\s+(?:module|service|component|system))', re.I),
]


@dataclass
class ExtractedEntity:
    """A raw entity extracted from text."""
    entity_type: str       # "ERROR_CODE", "SYMPTOM", etc.
    text: str              # Surface text
    source_section: str    # Which section it came from
    confidence: float = 0.8

    @property
    def node_id(self) -> str:
        """Generate a deterministic node ID."""
        slug = re.sub(r'\W+', '_', self.text.lower())[:60]
        h = hashlib.md5(self.text.encode()).hexdigest()[:8]
        return f"{self.entity_type.lower()}:{slug}_{h}"


@dataclass
class ExtractedRelation:
    """A relationship between two entities."""
    source_id: str
    target_id: str
    edge_type: str
    confidence: float = 0.7


# ── LLM extraction prompt ─────────────────────────────────────────

_LLM_EXTRACTION_PROMPT = """\
You are a technical document analyst. Extract structured troubleshooting
information from the following section of a technical guide.

SECTION HEADING: {heading}
SECTION TEXT:
{text}

Extract ALL instances of:
1. ERROR_CODES — error identifiers, HTTP status codes, error names
2. SYMPTOMS — observable behaviors, error messages, user-visible issues
3. ROOT_CAUSES — why the error occurs, underlying technical reasons
4. SOLUTIONS — verified fixes, step-by-step resolutions
5. WORKAROUNDS — temporary mitigations
6. COMPONENTS — system modules, services, subsystems involved

Return valid JSON:
{{
  "entities": [
    {{"type": "ERROR_CODE", "text": "...", "confidence": 0.9}},
    {{"type": "SYMPTOM", "text": "...", "confidence": 0.8}},
    ...
  ],
  "relations": [
    {{"source": "ERROR_CODE:...", "target": "SYMPTOM:...", "edge": "MANIFESTS_AS"}},
    {{"source": "SYMPTOM:...", "target": "ROOT_CAUSE:...", "edge": "CAUSED_BY"}},
    {{"source": "ROOT_CAUSE:...", "target": "SOLUTION:...", "edge": "RESOLVED_BY"}},
    ...
  ]
}}

Only return the JSON object. No markdown fences."""


class TroubleshootingGraphBuilder:
    """Build a troubleshooting knowledge graph from non-legal documents.

    Parameters
    ----------
    store : GraphStore
        Persistence layer (writes to troubleshooting-specific JSON).
    llm_callable : callable | None
        Optional ``async def llm(prompt: str) -> str`` for richer extraction.
    """

    def __init__(
        self,
        store: GraphStore,
        llm_callable: Optional[Callable] = None,
    ) -> None:
        self.store = store
        self.llm_callable = llm_callable

    # ── Main entry point ──────────────────────────────────────────

    def build_troubleshooting_graph(
        self,
        document_id: str,
        source_path: str,
        sections: List[Dict[str, Any]],
        *,
        doc_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, int]:
        """Build troubleshooting graph for a non-legal document.

        Parameters
        ----------
        document_id : str
            Document identifier.
        source_path : str
            Source file path.
        sections : list of dict
            Each dict has ``section_number``, ``section_heading``,
            ``section_text`` keys.
        doc_metadata : dict | None
            Extra attributes for the DOCUMENT node.

        Returns
        -------
        dict
            Stats: ``{sections, error_codes, symptoms, root_causes,
            solutions, workarounds, components, edges}``
        """
        stats = {
            "sections": 0,
            "error_codes": 0,
            "symptoms": 0,
            "root_causes": 0,
            "solutions": 0,
            "workarounds": 0,
            "components": 0,
            "edges": 0,
        }

        G = self.store.load()

        # ── Document node ─────────────────────────────────────────
        doc_node_id = f"doc:{document_id}"
        G.add_node(doc_node_id, **{
            "type": "DOCUMENT",
            "title": doc_metadata.get("title", document_id) if doc_metadata else document_id,
            "path": source_path,
            "schema_version": TS_SCHEMA_VERSION,
            "regime": "GENERIC_GUIDE",
            **(doc_metadata or {}),
        })

        prev_section_id = None

        for section_idx, section_dict in enumerate(sections):
            heading = section_dict.get("section_heading", f"Section {section_idx}")
            text = section_dict.get("section_text", "")
            if not text.strip():
                continue

            # ── Section node ──────────────────────────────────────
            section_id = f"ts_sec:{document_id}:{section_idx:04d}"
            G.add_node(section_id, **{
                "type": "SECTION",
                "heading": heading,
                "doc_id": document_id,
                "section_index": section_idx,
            })
            G.add_edge(doc_node_id, section_id, type="CONTAINS")
            stats["edges"] += 1

            if prev_section_id:
                G.add_edge(prev_section_id, section_id, type="NEXT")
                stats["edges"] += 1
            prev_section_id = section_id

            stats["sections"] += 1

            # ── Extract entities ──────────────────────────────────
            entities = self._extract_entities(heading, text)
            relations = self._infer_relations(entities)

            # Merge LLM-extracted relations (set by _extract_entities)
            llm_rels = getattr(self, "_last_llm_relations", [])
            if llm_rels:
                relations.extend(llm_rels)

            # ── Add entities as nodes ─────────────────────────────
            for ent in entities:
                attrs = self._entity_to_attrs(ent)
                G.add_node(ent.node_id, **attrs)

                # Connect section → entity
                edge_type = self._section_edge_type(ent.entity_type)
                G.add_edge(section_id, ent.node_id, type=edge_type)
                stats["edges"] += 1

                # Update stats
                type_key = ent.entity_type.lower() + "s"
                if type_key in stats:
                    stats[type_key] += 1

            # ── Add inferred relations ────────────────────────────
            for rel in relations:
                if G.has_node(rel.source_id) and G.has_node(rel.target_id):
                    G.add_edge(
                        rel.source_id,
                        rel.target_id,
                        type=rel.edge_type,
                        confidence=rel.confidence,
                    )
                    stats["edges"] += 1

        # ── Cross-section error co-occurrence ─────────────────────
        error_nodes = [
            n for n, d in G.nodes(data=True) if d.get("type") == "ERROR_CODE"
        ]
        self._link_related_errors(G, error_nodes)

        self.store.save(G)

        logger.info(
            f"[Phase19-Graph] Built troubleshooting graph for {document_id}: "
            f"{stats}"
        )
        return stats

    # ── Entity extraction (heuristic) ─────────────────────────────

    def _extract_entities(
        self,
        heading: str,
        text: str,
    ) -> List[ExtractedEntity]:
        """Extract entities using regex patterns + optional LLM enrichment."""
        entities: List[ExtractedEntity] = []
        seen_texts: Set[str] = set()
        full_text = f"{heading}\n{text}"

        def _add(etype: str, txt: str, conf: float = 0.8):
            txt = txt.strip()[:200]  # Cap length
            if not txt or len(txt) < 3:
                return
            key = f"{etype}:{txt.lower()}"
            if key in seen_texts:
                return
            seen_texts.add(key)
            entities.append(ExtractedEntity(
                entity_type=etype,
                text=txt,
                source_section=heading,
                confidence=conf,
            ))

        # Error codes
        for m in _ERROR_CODE_RE.finditer(full_text):
            _add("ERROR_CODE", m.group(1), 0.95)

        # Symptoms
        for pattern in _SYMPTOM_PATTERNS:
            for m in pattern.finditer(full_text):
                _add("SYMPTOM", m.group(1), 0.8)

        # Root causes
        for pattern in _ROOT_CAUSE_PATTERNS:
            for m in pattern.finditer(full_text):
                _add("ROOT_CAUSE", m.group(1), 0.8)

        # Solutions
        for pattern in _SOLUTION_PATTERNS:
            for m in pattern.finditer(full_text):
                _add("SOLUTION", m.group(1), 0.85)

        # Workarounds
        for pattern in _WORKAROUND_PATTERNS:
            for m in pattern.finditer(full_text):
                _add("WORKAROUND", m.group(1), 0.8)

        # Components
        for pattern in _COMPONENT_PATTERNS:
            for m in pattern.finditer(full_text):
                _add("COMPONENT", m.group(1), 0.7)

        # ── LLM enrichment ────────────────────────────────────────
        # When an LLM is available, extract additional entities that
        # regex patterns miss (e.g. implied symptoms, nuanced root
        # causes) and merge them into the regex results.
        if self.llm_callable is not None:
            try:
                llm_entities, llm_relations = self._extract_entities_llm(
                    heading, text,
                )
                # Merge LLM entities — dedup against regex finds
                for ent in llm_entities:
                    _add(ent.entity_type, ent.text, ent.confidence)
                # Return combined; relations returned separately via
                # _infer_relations_llm which is called in the main loop
                self._last_llm_relations = llm_relations
            except Exception as exc:
                logger.debug(
                    "[Phase19-Graph] LLM entity extraction failed for '%s': %s",
                    heading[:60], exc,
                )
                self._last_llm_relations = []
        else:
            self._last_llm_relations = []

        return entities

    # ── LLM-assisted entity extraction ────────────────────────────

    def _extract_entities_llm(
        self,
        heading: str,
        text: str,
    ) -> tuple[List[ExtractedEntity], List[ExtractedRelation]]:
        """Call the LLM to extract structured entities + relations.

        Returns (entities, relations). On any error the caller falls
        back to regex-only gracefully.
        """
        import json as _json

        prompt = _LLM_EXTRACTION_PROMPT.format(heading=heading, text=text[:3000])

        raw = self.llm_callable(prompt)
        if not raw or not isinstance(raw, str):
            return [], []

        # Strip markdown fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

        data = _json.loads(raw)

        entities: List[ExtractedEntity] = []
        for e in data.get("entities", []):
            etype = (e.get("type") or "").upper()
            etext = (e.get("text") or "").strip()
            conf = float(e.get("confidence", 0.75))
            if etype and etext and len(etext) >= 3:
                allowed = {
                    "ERROR_CODE", "SYMPTOM", "ROOT_CAUSE",
                    "SOLUTION", "WORKAROUND", "COMPONENT",
                }
                if etype in allowed:
                    entities.append(ExtractedEntity(
                        entity_type=etype,
                        text=etext[:200],
                        source_section=heading,
                        confidence=min(conf, 0.90),  # cap LLM confidence
                    ))

        relations: List[ExtractedRelation] = []
        for r in data.get("relations", []):
            src = (r.get("source") or "").strip()
            tgt = (r.get("target") or "").strip()
            edge = (r.get("edge") or "").upper()
            if src and tgt and edge:
                # Resolve source/target to node IDs via entity text
                src_ent = self._resolve_entity_ref(src, entities)
                tgt_ent = self._resolve_entity_ref(tgt, entities)
                if src_ent and tgt_ent:
                    relations.append(ExtractedRelation(
                        source_id=src_ent.node_id,
                        target_id=tgt_ent.node_id,
                        edge_type=edge,
                        confidence=0.7,
                    ))

        logger.debug(
            "[Phase19-Graph] LLM extracted %d entities, %d relations",
            len(entities), len(relations),
        )
        return entities, relations

    @staticmethod
    def _resolve_entity_ref(
        ref: str,
        entities: List[ExtractedEntity],
    ) -> Optional[ExtractedEntity]:
        """Resolve a LLM relation reference like 'ERROR_CODE:ERR-RUN-204'
        to the matching ``ExtractedEntity``."""
        # Try TYPE:text format
        if ":" in ref:
            etype, etext = ref.split(":", 1)
            etype = etype.upper().strip()
            etext = etext.strip().lower()
            for ent in entities:
                if ent.entity_type == etype and ent.text.lower() == etext:
                    return ent
        # Fallback: fuzzy text match
        ref_lower = ref.lower()
        for ent in entities:
            if ent.text.lower() in ref_lower or ref_lower in ent.text.lower():
                return ent
        return None

    # ── Relation inference ────────────────────────────────────────

    def _infer_relations(
        self,
        entities: List[ExtractedEntity],
    ) -> List[ExtractedRelation]:
        """Infer edges between entities extracted from the same section.

        Heuristic rules:
        - ERROR_CODE → SYMPTOM  via MANIFESTS_AS
        - SYMPTOM → ROOT_CAUSE  via CAUSED_BY
        - ROOT_CAUSE → SOLUTION via RESOLVED_BY
        - ROOT_CAUSE → WORKAROUND via MITIGATED_BY
        - ROOT_CAUSE → COMPONENT via AFFECTS
        """
        relations: List[ExtractedRelation] = []

        by_type: Dict[str, List[ExtractedEntity]] = {}
        for ent in entities:
            by_type.setdefault(ent.entity_type, []).append(ent)

        error_codes = by_type.get("ERROR_CODE", [])
        symptoms = by_type.get("SYMPTOM", [])
        root_causes = by_type.get("ROOT_CAUSE", [])
        solutions = by_type.get("SOLUTION", [])
        workarounds = by_type.get("WORKAROUND", [])
        components = by_type.get("COMPONENT", [])

        # ERROR_CODE → each SYMPTOM
        for ec in error_codes:
            for sym in symptoms:
                relations.append(ExtractedRelation(
                    ec.node_id, sym.node_id, "MANIFESTS_AS", 0.8,
                ))

        # SYMPTOM → each ROOT_CAUSE
        for sym in symptoms:
            for rc in root_causes:
                relations.append(ExtractedRelation(
                    sym.node_id, rc.node_id, "CAUSED_BY", 0.75,
                ))

        # ROOT_CAUSE → each SOLUTION
        for rc in root_causes:
            for sol in solutions:
                relations.append(ExtractedRelation(
                    rc.node_id, sol.node_id, "RESOLVED_BY", 0.85,
                ))

        # ROOT_CAUSE → each WORKAROUND
        for rc in root_causes:
            for wa in workarounds:
                relations.append(ExtractedRelation(
                    rc.node_id, wa.node_id, "MITIGATED_BY", 0.7,
                ))

        # ROOT_CAUSE → each COMPONENT
        for rc in root_causes:
            for comp in components:
                relations.append(ExtractedRelation(
                    rc.node_id, comp.node_id, "AFFECTS", 0.65,
                ))

        # COMPONENT → each SYMPTOM (component has symptom)
        for comp in components:
            for sym in symptoms:
                relations.append(ExtractedRelation(
                    comp.node_id, sym.node_id, "HAS_SYMPTOM", 0.6,
                ))

        return relations

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _entity_to_attrs(ent: ExtractedEntity) -> Dict[str, Any]:
        """Convert an extracted entity to node attributes."""
        attrs: Dict[str, Any] = {
            "type": ent.entity_type,
            "confidence": ent.confidence,
            "source_section": ent.source_section,
        }
        if ent.entity_type in ("ERROR_CODE", "COMPONENT"):
            attrs["name"] = ent.text
        else:
            attrs["description"] = ent.text
        return attrs

    @staticmethod
    def _section_edge_type(entity_type: str) -> str:
        """Return the edge type from a section to an entity node."""
        mapping = {
            "ERROR_CODE": "ADDRESSES",
            "SYMPTOM": "CONTAINS",
            "ROOT_CAUSE": "CONTAINS",
            "SOLUTION": "CONTAINS",
            "WORKAROUND": "CONTAINS",
            "COMPONENT": "CONTAINS",
            "PREREQ": "CONTAINS",
        }
        return mapping.get(entity_type, "CONTAINS")

    @staticmethod
    def _link_related_errors(
        G: nx.DiGraph,
        error_nodes: List[str],
    ) -> None:
        """Create RELATED_ERROR edges between error codes that share sections."""
        # Group error codes by the sections that contain them
        section_to_errors: Dict[str, List[str]] = {}
        for err in error_nodes:
            for pred in G.predecessors(err):
                pred_data = G.nodes.get(pred, {})
                if pred_data.get("type") == "SECTION":
                    section_to_errors.setdefault(pred, []).append(err)

        # Link error codes that appear in the same section
        for section_id, errs in section_to_errors.items():
            for i in range(len(errs)):
                for j in range(i + 1, len(errs)):
                    if not G.has_edge(errs[i], errs[j]):
                        G.add_edge(
                            errs[i], errs[j],
                            type="RELATED_ERROR",
                            via_section=section_id,
                        )
