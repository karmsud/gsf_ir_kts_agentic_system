"""Phase 19.3 — Troubleshooting Graph Schema Extension.

Adds node types and edge types specific to non-legal troubleshooting
documents (GENERIC_GUIDE regime).  These augment the core schema v2.2
without modifying it — the troubleshooting graph is stored in a
*separate* JSON file from the legal knowledge graph.

Node types added
~~~~~~~~~~~~~~~~
- SYMPTOM      — observable symptom described by user/system
- ROOT_CAUSE   — underlying technical cause
- SOLUTION     — verified fix / resolution
- WORKAROUND   — temporary mitigation (not a permanent fix)
- PREREQ       — prerequisite step or condition
- COMPONENT    — system component / module / service

Edge types added
~~~~~~~~~~~~~~~~
- MANIFESTS_AS  — ERROR_CODE → SYMPTOM
- HAS_SYMPTOM   — COMPONENT → SYMPTOM
- CAUSED_BY     — SYMPTOM → ROOT_CAUSE
- RESOLVED_BY   — ROOT_CAUSE → SOLUTION
- MITIGATED_BY  — ROOT_CAUSE → WORKAROUND
- INDICATES     — SYMPTOM → ROOT_CAUSE  (weaker than CAUSED_BY)
- REQUIRES      — SOLUTION → PREREQ
- AFFECTS       — ROOT_CAUSE → COMPONENT
- RELATED_ERROR — ERROR_CODE → ERROR_CODE  (co-occurrence)
"""

from __future__ import annotations

from typing import Dict, Set

# Schema version for the troubleshooting graph
TS_SCHEMA_VERSION = "1.0"

# ── Node types ────────────────────────────────────────────────────
TS_NODE_TYPES: Set[str] = {
    # Inherited from core schema (shared)
    "DOCUMENT",
    "SECTION",
    "ERROR_CODE",
    # New — troubleshooting-specific
    "SYMPTOM",
    "ROOT_CAUSE",
    "SOLUTION",
    "WORKAROUND",
    "PREREQ",
    "COMPONENT",
}

# ── Edge types ────────────────────────────────────────────────────
TS_EDGE_TYPES: Set[str] = {
    # Core structural edges (reused)
    "CONTAINS",       # Document → Section
    "NEXT",           # Section → Section
    "ADDRESSES",      # Section → ERROR_CODE
    # New — troubleshooting-specific
    "MANIFESTS_AS",   # ERROR_CODE → SYMPTOM
    "HAS_SYMPTOM",    # COMPONENT → SYMPTOM
    "CAUSED_BY",      # SYMPTOM → ROOT_CAUSE
    "RESOLVED_BY",    # ROOT_CAUSE → SOLUTION
    "MITIGATED_BY",   # ROOT_CAUSE → WORKAROUND
    "INDICATES",      # SYMPTOM → ROOT_CAUSE (weaker)
    "REQUIRES",       # SOLUTION → PREREQ
    "AFFECTS",        # ROOT_CAUSE → COMPONENT
    "RELATED_ERROR",  # ERROR_CODE → ERROR_CODE
}

# ── Required properties per node type ─────────────────────────────
TS_REQUIRED_PROPERTIES: Dict[str, Set[str]] = {
    "DOCUMENT": {"title", "path"},
    "SECTION": {"heading", "doc_id"},
    "ERROR_CODE": {"name"},
    "SYMPTOM": {"description"},
    "ROOT_CAUSE": {"description"},
    "SOLUTION": {"description"},
    "WORKAROUND": {"description"},
    "PREREQ": {"description"},
    "COMPONENT": {"name"},
}


class TSSchemaValidationError(ValueError):
    """Raised when a troubleshooting node/edge fails validation."""


def validate_ts_node(node_type: str, attrs: dict) -> None:
    """Validate a troubleshooting graph node."""
    if node_type not in TS_NODE_TYPES:
        raise TSSchemaValidationError(
            f"Unknown TS node type '{node_type}'. "
            f"Valid: {sorted(TS_NODE_TYPES)}"
        )
    required = TS_REQUIRED_PROPERTIES.get(node_type, set())
    missing = required - set(attrs.keys())
    if missing:
        raise TSSchemaValidationError(
            f"TS node '{node_type}' missing: {sorted(missing)}"
        )


def validate_ts_edge(edge_type: str) -> None:
    """Validate a troubleshooting graph edge type."""
    if edge_type not in TS_EDGE_TYPES:
        raise TSSchemaValidationError(
            f"Unknown TS edge type '{edge_type}'. "
            f"Valid: {sorted(TS_EDGE_TYPES)}"
        )
