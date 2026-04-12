"""Graph Schema v2.1 — Phase 4 (TD §4).

Defines the canonical node types, edge types, required properties per node
type, and a ``validate_node`` helper used by ``GraphBuilder`` to reject
malformed entries at upsert time.
"""

from __future__ import annotations

SCHEMA_VERSION = "2.2"

# ── 14 Node Types (TD §4.1 + Phase 6) ─────────────────────────────
NODE_TYPES = {
    "DOCUMENT",
    "SECTION",
    "CLAUSE",
    "DEFINED_TERM",
    "ENTITY",
    "KEYPHRASE",
    "ALIAS",
    "FORMULA",
    "TOOL",
    "PROCESS",
    "ERROR_CODE",
    "CONCEPT",
    "TOPIC",
    # Phase 6 — granular items extracted from sections
    "ITEM",    # definition-graph (lowercase convention matches definition_graph_builder)
    "defined_term",}

# ── Edge Types (TD §4.2 + Phase 6) ────────────────────────────────
EDGE_TYPES = {
    # Original 10 + USES
    "DEFINES",
    "DESCRIBES",
    "ADDRESSES",
    "COVERS",
    "MENTIONS",
    "REFERS_TO",
    "DEPENDS_ON",
    "AUTHORED_BY",
    "MAINTAINS",
    "HAS_CHILD",
    "USES",
    # Phase 6 — hierarchical & typed edges
    "CONTAINS",       # Document → Section
    "NEXT",           # Section → Section (sequential)
    "HAS_ITEM",       # Section → Item (generic)
    "HAS_RULE",       # Section → Item (Obligation / Prohibition)
    "HAS_DEFINITION", # Section → Item (Definition)
    "HAS_RIGHT",      # Section → Item (Right)
    "HAS_CONDITION",  # Section → Item (Condition)
    "HAS_REQUIREMENT",# Section → Item (Requirement)
    "HAS_PROCEDURE",  # Section → Item (Procedure)
    "HAS_CONFIGURATION",  # Section → Item (Configuration)
    "HAS_WARNING",    # Section → Item (Warning)
    "HAS_THEOREM",    # Section → Item (Theorem)
    "HAS_PROOF",      # Section → Item (Proof)
    "HAS_LEMMA",      # Section → Item (Lemma)
    "HAS_ALGORITHM",  # Section → Item (Algorithm)
    "REFERENCES",     # Item → Item (cross-reference / dependency)
    # NER enrichment edges (Layers 2–3)
    "ASSIGNED_ROLE",  # ENTITY → defined_term ("X, as Trustee" pattern)
}

# ── Required properties by node type (TD §4.3) ────────────────────
REQUIRED_PROPERTIES: dict[str, set[str]] = {
    "DOCUMENT": {"title", "path"},
    "SECTION": {"heading", "doc_id"},
    "CLAUSE": {"heading", "doc_id"},
    "DEFINED_TERM": {"surface_form", "confidence", "extraction_strategy"},
    "ENTITY": {"entity_type", "surface_form"},
    "KEYPHRASE": {"surface_form", "score"},
    "ALIAS": {"surface_form", "canonical_id"},
    "FORMULA": {"expression", "doc_id"},
    "TOOL": {"name"},
    "PROCESS": {"name"},
    "ERROR_CODE": {"name"},
    "CONCEPT": {"name"},
    "TOPIC": {"name"},
    # Phase 6
    "ITEM": {"item_type", "document_id"},
}


class SchemaValidationError(ValueError):
    """Raised when a node fails schema validation."""


def validate_node(node_type: str, attrs: dict) -> None:
    """Raise ``SchemaValidationError`` if *node_type* is unknown or
    *attrs* is missing a required property.
    """
    if node_type not in NODE_TYPES:
        raise SchemaValidationError(
            f"Unknown node type '{node_type}'. Valid types: {sorted(NODE_TYPES)}"
        )
    required = REQUIRED_PROPERTIES.get(node_type, set())
    missing = required - set(attrs.keys())
    if missing:
        raise SchemaValidationError(
            f"Node type '{node_type}' missing required properties: {sorted(missing)}"
        )


def validate_edge(edge_type: str) -> None:
    """Raise ``SchemaValidationError`` if *edge_type* is not in the schema."""
    if edge_type not in EDGE_TYPES:
        raise SchemaValidationError(
            f"Unknown edge type '{edge_type}'. Valid types: {sorted(EDGE_TYPES)}"
        )
