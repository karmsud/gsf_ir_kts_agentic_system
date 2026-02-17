from __future__ import annotations

import re
import logging
from typing import List, Dict, Any, Set
import networkx as nx

from backend.common.models import IngestedDocument
from .persistence import GraphStore
from .schema import (
    SCHEMA_VERSION,
    NODE_TYPES,
    EDGE_TYPES,
    validate_node,
    validate_edge,
    SchemaValidationError,
)

logger = logging.getLogger(__name__)


def extract_defined_term(text: str) -> str:
    """
    Extracts defined terms from text using heuristic patterns.
    Matches:
    - "Term" means ...
    - Term is defined as ...
    """
    s = text.strip()
    # Pattern 1: quoted term followed by "means" or "is defined as"
    m = re.search(r'["\']+([^"\']{2,80})["\']+\s+(means|is defined as)\b', s, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # Pattern 2: Term means ... (Capitalized)
    parts = re.split(r'\b(means|is defined as)\b', s, flags=re.IGNORECASE)
    if parts:
        left = parts[0].strip()
        cand = re.findall(r'([A-Z][A-Za-z0-9 _-]{1,60})$', left)
        if cand:
            return cand[-1].strip()
    return ""


class GraphBuilder:
    """
    Constructs a knowledge graph from ingested documents using NetworkX.

    Node types : DOCUMENT, TERM, TOOL, TOPIC, ERROR_CODE
    Edge types : DEFINES, MENTIONS, COVERS, ADDRESSES
    """

    def __init__(self, store: GraphStore):
        self.store = store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upsert_document(self, doc: IngestedDocument, metadata: dict) -> nx.DiGraph:
        """Parse *doc* and upsert nodes/edges into the persistent graph.

        Returns the updated `nx.DiGraph` instance.
        """
        G: nx.DiGraph = self.store.load()

        # Ensure schema version is stored on the graph
        G.graph.setdefault("schema_version", SCHEMA_VERSION)

        # 1. Document node
        doc_node_id = f"doc:{doc.doc_id}"
        doc_attrs = {
            "type": "DOCUMENT",
            "title": metadata.get("title", doc.doc_id),
            "path": doc.source_path,
            "doc_type": metadata.get("doc_type", "UNKNOWN"),
            "doc_regime": metadata.get("doc_regime", "UNKNOWN"),
        }
        G.add_node(doc_node_id, **doc_attrs)

        # 2. Extract terms from body text (Strategy 1 — basic regex)
        for line in doc.extracted_text.split("\n"):
            line = line.strip()
            if not line:
                continue

            term = extract_defined_term(line)
            if term and len(term) > 2:
                term_id = f"defterm:{term.lower().replace(' ', '_')}"
                G.add_node(
                    term_id,
                    type="DEFINED_TERM",
                    name=term,
                    surface_form=term,
                    confidence=0.95,
                    extraction_strategy="regex_means",
                    extract_source=line[:200],
                )
                self._ensure_edge(G, doc_node_id, term_id, "DEFINES")

        # 3. Metadata-driven links
        for tool in metadata.get("tools", []):
            tool_id = f"tool:{tool.lower()}"
            G.add_node(tool_id, type="TOOL", name=tool)
            self._ensure_edge(G, doc_node_id, tool_id, "MENTIONS")

        process_ids: list[str] = []
        for process in metadata.get("processes", []):
            process_id = f"process:{str(process).lower()}"
            process_ids.append(process_id)
            G.add_node(process_id, type="PROCESS", name=process)
            self._ensure_edge(G, doc_node_id, process_id, "COVERS")

        if process_ids and metadata.get("tools", []):
            for process_id in process_ids:
                for tool in metadata.get("tools", []):
                    tool_id = f"tool:{tool.lower()}"
                    self._ensure_edge(G, process_id, tool_id, "USES")

        for topic in metadata.get("topics", []):
            topic_id = f"topic:{topic.lower()}"
            G.add_node(topic_id, type="TOPIC", name=topic)
            self._ensure_edge(G, doc_node_id, topic_id, "COVERS")

        for error in metadata.get("error_codes", []):
            err_id = f"error:{error}"
            G.add_node(err_id, type="ERROR_CODE", name=error)
            self._ensure_edge(G, doc_node_id, err_id, "ADDRESSES")

        # 4. Persist
        self.store.save(G)
        logger.info(
            "Graph updated for %s: %d nodes, %d edges",
            doc.doc_id,
            G.number_of_nodes(),
            G.number_of_edges(),
        )
        return G

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_edge(G: nx.DiGraph, src: str, tgt: str, edge_type: str) -> None:
        """Add an edge only if source != target and no duplicate exists."""
        if src == tgt:
            return
        if G.has_edge(src, tgt) and G[src][tgt].get("type") == edge_type:
            return
        G.add_edge(src, tgt, type=edge_type)
