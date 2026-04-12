"""Phase 19.3 — Troubleshooting Graph Traversal.

Query-time graph walker that takes a user's question (possibly
containing error codes, symptoms, or component names) and walks
the troubleshooting graph to find:

1. Matching ERROR_CODE / SYMPTOM / COMPONENT nodes
2. Linked ROOT_CAUSE nodes
3. SOLUTION and WORKAROUND nodes attached to those causes

The output is structured context that the retriever can inject
alongside vector-search results before the LLM generates an answer.

Adapts the DFS pattern from ``resolution_tree.py`` but follows
the troubleshooting-specific edge types.
"""

from __future__ import annotations

import logging
import re
from collections import deque
from dataclasses import dataclass, field
from typing import List, Set, Tuple

import networkx as nx

logger = logging.getLogger(__name__)

# Rough token estimate: 1 token ≈ 4 chars
_CHARS_PER_TOKEN = 4


@dataclass
class TroubleshootingResult:
    """A single troubleshooting resolution path."""
    error_codes: List[str] = field(default_factory=list)
    symptoms: List[str] = field(default_factory=list)
    root_causes: List[str] = field(default_factory=list)
    solutions: List[str] = field(default_factory=list)
    workarounds: List[str] = field(default_factory=list)
    components: List[str] = field(default_factory=list)
    path: List[str] = field(default_factory=list)  # Node IDs traversed
    confidence: float = 0.0

    @property
    def has_solution(self) -> bool:
        return len(self.solutions) > 0

    @property
    def summary(self) -> str:
        """Brief text summary of the resolution path."""
        parts = []
        if self.error_codes:
            parts.append(f"Error: {', '.join(self.error_codes)}")
        if self.symptoms:
            parts.append(f"Symptom: {'; '.join(self.symptoms[:2])}")
        if self.root_causes:
            parts.append(f"Cause: {'; '.join(self.root_causes[:2])}")
        if self.solutions:
            parts.append(f"Fix: {'; '.join(self.solutions[:2])}")
        elif self.workarounds:
            parts.append(f"Workaround: {'; '.join(self.workarounds[:1])}")
        return " → ".join(parts) if parts else "(no path)"


@dataclass
class TraversalContext:
    """Formatted context block ready for LLM injection."""
    results: List[TroubleshootingResult] = field(default_factory=list)
    token_count: int = 0
    formatted_text: str = ""

    @property
    def has_results(self) -> bool:
        return len(self.results) > 0


# ── Error code extraction from query ──────────────────────────────

_QUERY_ERROR_RE = re.compile(
    r'\b('
    r'ERR[-_]?[A-Z]*[-_]?\d{3,}'
    r'|E[-_]?\d{3,}'
    r'|HTTP\s*\d{3}'
    r'|0x[0-9A-Fa-f]{4,}'
    r'|[A-Z]{2,}\d{3,4}'
    r')\b',
    re.IGNORECASE,
)


def _extract_query_error_codes(query: str) -> List[str]:
    """Extract error codes from a user query."""
    return [m.group(1) for m in _QUERY_ERROR_RE.finditer(query)]


# ── Graph search helpers ──────────────────────────────────────────

def _find_matching_nodes(
    G: nx.DiGraph,
    query: str,
    error_codes: List[str],
) -> List[Tuple[str, float]]:
    """Find nodes in the graph that match the query.

    Returns (node_id, relevance_score) pairs sorted by score.
    """
    matches: List[Tuple[str, float]] = []
    query_lower = query.lower()
    query_tokens = set(query_lower.split())

    for node_id, attrs in G.nodes(data=True):
        node_type = attrs.get("type", "")
        score = 0.0

        # Exact error-code match (highest priority)
        if node_type == "ERROR_CODE":
            name = attrs.get("name", "").upper()
            for ec in error_codes:
                if ec.upper() in name or name in ec.upper():
                    score = 1.0
                    break

        # Text similarity for descriptive nodes
        if node_type in ("SYMPTOM", "ROOT_CAUSE", "SOLUTION", "WORKAROUND", "COMPONENT"):
            desc = attrs.get("description", attrs.get("name", "")).lower()
            desc_tokens = set(desc.split())
            if desc_tokens:
                overlap = query_tokens & desc_tokens
                if overlap:
                    score = max(score, len(overlap) / max(len(query_tokens), 1) * 0.7)

        # Name match for COMPONENT
        if node_type == "COMPONENT":
            name = attrs.get("name", "").lower()
            if name and name in query_lower:
                score = max(score, 0.85)

        if score > 0.1:
            matches.append((node_id, score))

    matches.sort(key=lambda x: x[1], reverse=True)
    return matches[:20]  # Cap for performance


# ── BFS resolution walker ─────────────────────────────────────────

# Edge types to follow for each direction of traversal
_FORWARD_EDGES = {
    "MANIFESTS_AS",  # ERROR_CODE → SYMPTOM
    "CAUSED_BY",     # SYMPTOM → ROOT_CAUSE
    "INDICATES",     # SYMPTOM → ROOT_CAUSE
    "RESOLVED_BY",   # ROOT_CAUSE → SOLUTION
    "MITIGATED_BY",  # ROOT_CAUSE → WORKAROUND
    "AFFECTS",       # ROOT_CAUSE → COMPONENT
    "HAS_SYMPTOM",   # COMPONENT → SYMPTOM
    "REQUIRES",      # SOLUTION → PREREQ
}

_REVERSE_EDGES = {
    "MANIFESTS_AS",  # Walk backwards: SYMPTOM → ERROR_CODE
    "CAUSED_BY",     # Walk backwards: ROOT_CAUSE → SYMPTOM
    "RESOLVED_BY",   # Walk backwards: SOLUTION → ROOT_CAUSE
}


def _walk_resolution_paths(
    G: nx.DiGraph,
    start_nodes: List[Tuple[str, float]],
    max_depth: int = 5,
    max_paths: int = 10,
) -> List[TroubleshootingResult]:
    """BFS walk from starting nodes to find resolution paths.

    Strategy:
    1. From ERROR_CODE: follow MANIFESTS_AS → CAUSED_BY → RESOLVED_BY
    2. From SYMPTOM: follow CAUSED_BY → RESOLVED_BY
    3. From COMPONENT: follow HAS_SYMPTOM → CAUSED_BY → RESOLVED_BY
    4. Reverse walk if starting from SOLUTION/WORKAROUND
    """
    results: List[TroubleshootingResult] = []
    visited_paths: Set[frozenset] = set()

    for start_id, start_score in start_nodes:
        if len(results) >= max_paths:
            break

        # Forward BFS
        result = TroubleshootingResult(confidence=start_score)
        _collect_node(G, start_id, result)

        # BFS queue: (node_id, depth)
        queue = deque([(start_id, 0)])
        visited: Set[str] = {start_id}

        while queue:
            current_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            # Follow forward edges
            for _, neighbor, edge_data in G.out_edges(current_id, data=True):
                edge_type = edge_data.get("type", "")
                if edge_type in _FORWARD_EDGES and neighbor not in visited:
                    visited.add(neighbor)
                    _collect_node(G, neighbor, result)
                    result.path.append(neighbor)
                    queue.append((neighbor, depth + 1))

            # Follow reverse edges (walk incoming)
            for predecessor, _, edge_data in G.in_edges(current_id, data=True):
                edge_type = edge_data.get("type", "")
                if edge_type in _REVERSE_EDGES and predecessor not in visited:
                    visited.add(predecessor)
                    _collect_node(G, predecessor, result)
                    result.path.append(predecessor)
                    queue.append((predecessor, depth + 1))

        # Only keep paths with at least one solution or workaround,
        # or paths with meaningful content
        path_key = frozenset(result.path)
        if path_key not in visited_paths and (
            result.has_solution
            or len(result.root_causes) > 0
            or len(result.symptoms) > 0
        ):
            visited_paths.add(path_key)
            results.append(result)

    # Sort by: has_solution first, then confidence
    results.sort(
        key=lambda r: (r.has_solution, r.confidence),
        reverse=True,
    )
    return results[:max_paths]


def _collect_node(G: nx.DiGraph, node_id: str, result: TroubleshootingResult) -> None:
    """Add a node's content to the appropriate list in the result."""
    attrs = G.nodes.get(node_id, {})
    node_type = attrs.get("type", "")
    text = attrs.get("description", attrs.get("name", ""))

    if not text:
        return

    if node_type == "ERROR_CODE" and text not in result.error_codes:
        result.error_codes.append(text)
    elif node_type == "SYMPTOM" and text not in result.symptoms:
        result.symptoms.append(text)
    elif node_type == "ROOT_CAUSE" and text not in result.root_causes:
        result.root_causes.append(text)
    elif node_type == "SOLUTION" and text not in result.solutions:
        result.solutions.append(text)
    elif node_type == "WORKAROUND" and text not in result.workarounds:
        result.workarounds.append(text)
    elif node_type == "COMPONENT" and text not in result.components:
        result.components.append(text)


# ── Formatting ────────────────────────────────────────────────────

def _format_results(
    results: List[TroubleshootingResult],
    token_budget: int = 800,
) -> str:
    """Format resolution paths into LLM-injectable context.

    Uses a two-layer format similar to resolution_tree.py:
    - Layer 1: Path summaries
    - Layer 2: Detailed content (within token budget)
    """
    if not results:
        return ""

    lines = ["=== TROUBLESHOOTING CONTEXT ===\n"]
    used_chars = len(lines[0])
    budget_chars = token_budget * _CHARS_PER_TOKEN

    for i, result in enumerate(results):
        if used_chars >= budget_chars:
            break

        header = f"--- Path {i + 1} (confidence: {result.confidence:.0%}) ---"
        lines.append(header)
        used_chars += len(header) + 1

        if result.error_codes:
            line = f"Error Code(s): {', '.join(result.error_codes)}"
            lines.append(line)
            used_chars += len(line) + 1

        if result.components:
            line = f"Component(s): {', '.join(result.components[:3])}"
            lines.append(line)
            used_chars += len(line) + 1

        if result.symptoms:
            for sym in result.symptoms[:3]:
                if used_chars >= budget_chars:
                    break
                line = f"  Symptom: {sym}"
                lines.append(line)
                used_chars += len(line) + 1

        if result.root_causes:
            for rc in result.root_causes[:2]:
                if used_chars >= budget_chars:
                    break
                line = f"  Root Cause: {rc}"
                lines.append(line)
                used_chars += len(line) + 1

        if result.solutions:
            for sol in result.solutions[:3]:
                if used_chars >= budget_chars:
                    break
                line = f"  ✓ Solution: {sol}"
                lines.append(line)
                used_chars += len(line) + 1

        if result.workarounds:
            for wa in result.workarounds[:2]:
                if used_chars >= budget_chars:
                    break
                line = f"  ⚡ Workaround: {wa}"
                lines.append(line)
                used_chars += len(line) + 1

        lines.append("")

    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────

def resolve_troubleshooting_context(
    graph: nx.DiGraph,
    query: str,
    *,
    max_paths: int = 5,
    max_depth: int = 5,
    token_budget: int = 800,
) -> TraversalContext:
    """Main entry point — resolve troubleshooting context for a query.

    Parameters
    ----------
    graph : nx.DiGraph
        The troubleshooting knowledge graph.
    query : str
        User's question / error description.
    max_paths : int
        Maximum resolution paths to return.
    max_depth : int
        BFS depth limit per starting node.
    token_budget : int
        Approximate token budget for formatted output.

    Returns
    -------
    TraversalContext
        Contains resolution paths and formatted text for LLM injection.
    """
    # Step 1: Extract error codes from query
    error_codes = _extract_query_error_codes(query)

    # Step 2: Find matching start nodes
    matches = _find_matching_nodes(graph, query, error_codes)

    if not matches:
        return TraversalContext()

    # Step 3: Walk resolution paths
    results = _walk_resolution_paths(graph, matches, max_depth, max_paths)

    if not results:
        return TraversalContext()

    # Step 4: Format for LLM
    formatted = _format_results(results, token_budget)
    token_count = len(formatted) // _CHARS_PER_TOKEN

    return TraversalContext(
        results=results,
        token_count=token_count,
        formatted_text=formatted,
    )


def find_related_errors(
    graph: nx.DiGraph,
    error_code: str,
) -> List[str]:
    """Find error codes related to the given one via RELATED_ERROR edges.

    Useful for suggesting "you might also see..." in responses.
    """
    related = []
    for node_id, attrs in graph.nodes(data=True):
        if attrs.get("type") != "ERROR_CODE":
            continue
        name = attrs.get("name", "")
        if error_code.upper() in name.upper():
            # Found the matching error node — get RELATED_ERROR neighbors
            for _, neighbor, edge_data in graph.out_edges(node_id, data=True):
                if edge_data.get("type") == "RELATED_ERROR":
                    neighbor_name = graph.nodes[neighbor].get("name", neighbor)
                    related.append(neighbor_name)
            for predecessor, _, edge_data in graph.in_edges(node_id, data=True):
                if edge_data.get("type") == "RELATED_ERROR":
                    pred_name = graph.nodes[predecessor].get("name", predecessor)
                    related.append(pred_name)
            break
    return list(set(related))
