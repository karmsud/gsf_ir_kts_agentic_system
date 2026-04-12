"""
Module 5: Resolution Tree — Query-Time DFS with Layered Format

Walks DEPENDS_ON edges live at query time instead of storing
pre-computed JSON on graph nodes.  Produces a two-layer format
that keeps token usage manageable even for deeply nested terms:

  Layer 1  — Full dependency chain (term names only, ~12 tok/term)
  Layer 2  — Priority-ordered definitions within a token budget

Public API
----------
- ``resolve_terms_for_context(graph, terms, …)``
    Bulk entry-point called by the retriever.  Deduplicates across
    multiple terms, formats once, respects a shared token budget.

- ``resolve_term(graph, term_name, …)``
    Single-term convenience wrapper (used by ``/define`` command).

- ``build_resolution_tree(graph, term_node, …)``
    Low-level DFS — returns the nested dict tree.  Kept for
    backward-compat and for callers that need the raw structure.

Backward-compat shims
---------------------
- ``precompute_all_resolution_trees(graph)``
    Now a **no-op** that logs a deprecation warning. Callers that
    still invoke it (older codepaths) will not crash.
- ``format_resolution_tree_for_llm(tree, …)``
    Thin wrapper around the new layered formatter.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

import networkx as nx

logger = logging.getLogger(__name__)

# Rough token estimate: 1 token ≈ 4 chars (GPT-family average)
_CHARS_PER_TOKEN = 4


# ───────────────────────────────────────────────────────────────
# Low-level DFS tree builder (kept for backward compat)
# ───────────────────────────────────────────────────────────────

def build_resolution_tree(
    graph: nx.DiGraph,
    term_node: str,
    visited: Optional[FrozenSet[str]] = None,
    memo: Optional[Dict[str, dict]] = None,
    max_depth: int = 10,
) -> dict:
    """Build the complete resolution tree for a single defined term.

    Uses DFS with memoisation: each subtree is computed once and shared.
    Now walks *live* edges; nothing is read from stored JSON attributes.
    """
    if visited is None:
        visited = frozenset()
    if memo is None:
        memo = {}

    if term_node in memo:
        return memo[term_node]

    if term_node in visited:
        return {
            "term": graph.nodes[term_node].get("term_name", term_node),
            "cycle_detected": True,
            "depth": 0,
            "dependencies": {},
        }

    if max_depth <= 0:
        nd = graph.nodes.get(term_node, {})
        return {
            "term": nd.get("term_name", term_node),
            "definition_text": nd.get("definition_text", ""),
            "depth": 0,
            "is_leaf": True,
            "dependency_count": 0,
            "transitive_count": 0,
            "dependencies": {},
            "truncated": True,
        }

    visited = visited | {term_node}
    nd = graph.nodes.get(term_node, {})

    tree: Dict[str, Any] = {
        "term": nd.get("term_name", term_node),
        "definition_text": nd.get("definition_text", ""),
        "depth": 0,
        "is_leaf": True,
        "dependency_count": 0,
        "transitive_count": 0,
        "dependencies": {},
    }

    for succ in graph.successors(term_node):
        if graph[term_node][succ].get("type") != "DEPENDS_ON":
            continue
        sub = build_resolution_tree(graph, succ, visited, memo, max_depth - 1)
        name = sub["term"]
        tree["dependencies"][name] = sub
        tree["depth"] = max(tree["depth"], 1 + sub.get("depth", 0))
        tree["is_leaf"] = False

    tree["dependency_count"] = len(tree["dependencies"])
    tree["transitive_count"] = sum(
        1 + s.get("transitive_count", 0) for s in tree["dependencies"].values()
    )

    memo[term_node] = tree
    return tree


# ───────────────────────────────────────────────────────────────
# Query-time BFS chain walker (deduplicating)
# ───────────────────────────────────────────────────────────────

def _walk_chains_bfs(
    graph: nx.DiGraph,
    seed_node_ids: List[str],
) -> Tuple[Dict[str, List[str]], Dict[str, str], List[str]]:
    """BFS walk across DEPENDS_ON edges starting from *seed_node_ids*.

    Returns
    -------
    chains : dict[term_name -> list[dep_name]]
        Direct dependencies for every reachable term.
    definitions : dict[term_name -> definition_text]
        Definition text for every reachable term (may be empty-string).
    topo_order : list[term_name]
        Breadth-first discovery order (seeds first, leaves last).
    """
    chains: Dict[str, List[str]] = {}
    definitions: Dict[str, str] = {}
    topo_order: List[str] = []
    visited: Set[str] = set()

    queue: deque[str] = deque()
    for nid in seed_node_ids:
        if nid not in visited and nid in graph:
            visited.add(nid)
            queue.append(nid)

    while queue:
        nid = queue.popleft()
        nd = graph.nodes[nid]
        name = nd.get("term_name", nid)
        topo_order.append(name)
        definitions[name] = nd.get("definition_text", "")

        deps: List[str] = []
        for succ in graph.successors(nid):
            if graph[nid][succ].get("type") != "DEPENDS_ON":
                continue
            dep_name = graph.nodes[succ].get("term_name", succ)
            deps.append(dep_name)
            if succ not in visited:
                visited.add(succ)
                queue.append(succ)
        chains[name] = deps

    return chains, definitions, topo_order


# ───────────────────────────────────────────────────────────────
# Layered formatter
# ───────────────────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _format_layered(
    seed_names: List[str],
    chains: Dict[str, List[str]],
    definitions: Dict[str, str],
    topo_order: List[str],
    *,
    token_budget: int = 50_000,
) -> str:
    """Produce the two-layer formatted string.

    Layer 1 — **Dependency Map** (always included, cheap)
        Lists every term and its direct dependencies.

    Layer 2 — **Priority Definitions** (budget-controlled)
        Emits definitions in BFS order (seeds first -> deepest last)
        until the budget is exhausted.  Each definition is truncated
        to 300 chars (~75 tokens) to maximise coverage.
    """
    lines: List[str] = []

    # ── Layer 1: Dependency Map ──────────────────────────────────
    lines.append("=== Defined-Term Dependency Map ===")
    for name in topo_order:
        deps = chains.get(name, [])
        if deps:
            lines.append(f"  {name} -> {', '.join(deps)}")
        else:
            lines.append(f"  {name} (leaf)")
    lines.append("")

    layer1_text = "\n".join(lines)
    budget_used = _estimate_tokens(layer1_text)
    remaining = token_budget - budget_used

    if remaining <= 0:
        return layer1_text

    # ── Layer 2: Priority Definitions ────────────────────────────
    # BFS order naturally puts seeds (most relevant) first.
    def_lines: List[str] = ["=== Key Definitions ==="]
    max_def_chars = 300  # ~75 tokens per definition

    for name in topo_order:
        defn = definitions.get(name, "")
        if not defn:
            continue
        snippet = defn[:max_def_chars]
        if len(defn) > max_def_chars:
            snippet += "..."
        entry = f"  [{name}]: {snippet}"
        entry_tokens = _estimate_tokens(entry)
        if entry_tokens > remaining:
            def_lines.append(
                f"  ... ({len(topo_order) - len(def_lines) + 1} more terms, budget exhausted)"
            )
            break
        def_lines.append(entry)
        remaining -= entry_tokens

    if len(def_lines) > 1:  # at least one definition was added
        return layer1_text + "\n".join(def_lines)
    return layer1_text


# ───────────────────────────────────────────────────────────────
# Public API: bulk resolver (primary entry-point)
# ───────────────────────────────────────────────────────────────

def resolve_terms_for_context(
    graph: nx.DiGraph,
    term_names: List[str],
    *,
    token_budget: int = 50_000,
    _cache: Optional[Dict[str, str]] = None,
) -> str:
    """Resolve multiple terms and return a single formatted context block.

    Deduplicates across all requested terms so shared sub-trees are
    described exactly once.

    Parameters
    ----------
    graph : nx.DiGraph
        The knowledge graph with DEPENDS_ON edges.
    term_names : list[str]
        Capitalised term names (e.g. ``["Current Interest", "Pass-Through Rate"]``).
    token_budget : int
        Maximum approximate tokens for the output block.
    _cache : dict, optional
        Session-level cache mapping ``frozenset(term_names) -> formatted_text``.
        Callers should create **one** dict per retrieval session and pass it
        to every call so repeated queries skip the walk.

    Returns
    -------
    str
        Formatted context block ready for LLM injection (may be empty string
        if no terms matched).
    """
    if not term_names:
        return ""

    # Session cache lookup
    cache_key = frozenset(term_names)
    if _cache is not None and cache_key in _cache:
        return _cache[cache_key]

    # Map term names -> TERM:: node IDs
    seed_ids: List[str] = []
    seed_names: List[str] = []
    for name in term_names:
        nid = f"TERM::{name}"
        if nid in graph:
            seed_ids.append(nid)
            seed_names.append(name)

    if not seed_ids:
        result = ""
        if _cache is not None:
            _cache[cache_key] = result
        return result

    chains, definitions, topo_order = _walk_chains_bfs(graph, seed_ids)

    result = _format_layered(
        seed_names, chains, definitions, topo_order,
        token_budget=token_budget,
    )

    if _cache is not None:
        _cache[cache_key] = result

    logger.debug(
        "resolve_terms_for_context: %d seeds -> %d unique terms, ~%d tokens",
        len(seed_names),
        len(topo_order),
        _estimate_tokens(result),
    )

    return result


# ───────────────────────────────────────────────────────────────
# Public API: single-term resolver (used by /define, backward compat)
# ───────────────────────────────────────────────────────────────

def resolve_term(
    graph: nx.DiGraph,
    term_name: str,
    *,
    token_budget: int = 50_000,
) -> Optional[dict]:
    """Resolve a single defined term at query time.

    Returns ``None`` if the term is not in the graph.
    """
    nid = f"TERM::{term_name}"
    if nid not in graph:
        return None

    formatted = resolve_terms_for_context(
        graph, [term_name], token_budget=token_budget,
    )

    # Also build the raw tree for callers that need depth/count metadata
    tree = build_resolution_tree(graph, nid)

    return {
        "term": term_name,
        "depth": tree.get("depth", 0),
        "dependency_count": tree.get("transitive_count", 0),
        "formatted_tree": formatted,
        "raw_tree": tree,
    }


# ───────────────────────────────────────────────────────────────
# Backward-compat shims
# ───────────────────────────────────────────────────────────────

def precompute_all_resolution_trees(graph: nx.DiGraph) -> Dict[str, dict]:
    """**Deprecated no-op.**  Resolution trees are now computed at query time.

    Kept so existing callers (older ingestion codepaths) will not crash.
    Returns an empty dict.  The stored ``resolution_tree`` JSON attribute
    on graph nodes is no longer written.
    """
    logger.info(
        "precompute_all_resolution_trees() is now a no-op — "
        "resolution trees are computed at query time."
    )
    return {}


def format_resolution_tree_for_llm(
    tree: dict,
    max_depth: int = 4,
    indent: int = 0,
) -> str:
    """**Deprecated** — thin wrapper that formats a raw tree dict.

    New code should use ``resolve_terms_for_context()`` instead.
    Kept for backward compatibility with callers that pass a raw tree.
    """
    name = tree.get("term", "?")
    chains: Dict[str, List[str]] = {}
    definitions: Dict[str, str] = {}
    order: List[str] = []

    def _walk(t: dict) -> None:
        tname = t.get("term", "?")
        if tname in chains:
            return
        order.append(tname)
        definitions[tname] = t.get("definition_text", "")
        deps = list(t.get("dependencies", {}).keys())
        chains[tname] = deps
        for sub in t.get("dependencies", {}).values():
            _walk(sub)

    _walk(tree)
    return _format_layered([name], chains, definitions, order, token_budget=50_000)
