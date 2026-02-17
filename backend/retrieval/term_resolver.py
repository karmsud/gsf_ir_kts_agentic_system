from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Iterable

import networkx as nx


def normalize_term(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip()).lower()


def extract_title_case_phrases(query: str) -> list[str]:
    pattern = r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b"
    phrases = re.findall(pattern, query)
    return [p.strip() for p in phrases if p.strip()]


def _fuzzy_match_defterm(phrase: str, term_graph: nx.DiGraph, threshold: float = 0.85) -> list[str]:
    phrase_norm = normalize_term(phrase)
    matches: list[tuple[str, float]] = []
    for node in term_graph.nodes:
        node_str = str(node)
        if not (node_str.startswith("defterm:") or node_str.startswith("term:")):
            continue
        label = node_str.split(":", 1)[1].replace("_", " ")
        ratio = SequenceMatcher(None, phrase_norm, label.lower()).ratio()
        if ratio >= threshold:
            matches.append((node_str, ratio))
    matches.sort(key=lambda item: item[1], reverse=True)
    return [node for node, _ in matches]


def should_activate_resolver(
    query: str,
    intent: str,
    corpus_regime: str,
    initial_results: list[Any] | None,
    term_graph: nx.DiGraph | None,
) -> tuple[bool, str]:
    regime = (corpus_regime or "").upper()
    if regime == "GENERIC_GUIDE" or regime == "GENERIC":
        return (False, "corpus_regime=GENERIC, term graph not loaded")

    reasons: list[str] = []

    definitional_intents = {"define", "explain_term", "what_is", "means", "definition", "educational"}
    if intent in definitional_intents:
        reasons.append(f"intent={intent}")

    graph = term_graph if term_graph is not None else nx.DiGraph()
    for phrase in extract_title_case_phrases(query):
        node_id = f"defterm:{normalize_term(phrase).replace(' ', '_')}"
        node_id_alt = f"term:{normalize_term(phrase).replace(' ', '_')}"
        if node_id in graph.nodes or node_id_alt in graph.nodes:
            reasons.append(f"title_case_match='{phrase}'")
            break

        fuzzy_matches = _fuzzy_match_defterm(phrase, graph, threshold=0.85)
        if fuzzy_matches:
            reasons.append(f"fuzzy_match='{phrase}' -> {fuzzy_matches[0]}")
            break

    legal_hits = 0
    for row in initial_results or []:
        if isinstance(row, dict):
            metadata = row.get("metadata") or row
            score = float(row.get("score", 0.0))
        else:
            metadata = getattr(row, "metadata", {}) or {}
            score = float(getattr(row, "score", 0.0))

        doc_regime = str(metadata.get("doc_regime", "")).upper()
        has_defterm_ref = bool(metadata.get("defterm_ref"))
        if doc_regime in {"GOVERNING_DOC_LEGAL", "LEGAL"} and has_defterm_ref and score >= 0.75:
            legal_hits += 1

    if legal_hits > 0:
        reasons.append(f"high_conf_legal_chunks={legal_hits}")

    if reasons:
        return (True, " AND ".join(reasons))
    return (False, "no query-level triggers matched")


@dataclass
class ResolutionCitation:
    section_id: str | None = None
    page: int | None = None
    chunk_id: str | None = None
    source_uri: str | None = None


@dataclass
class TermResolution:
    root_term: str
    closure: list[str]
    stitched_explanation: str
    citations: list[ResolutionCitation] = field(default_factory=list)
    depth_reached: int = 0
    truncated: bool = False
    cycles_detected: list[str] = field(default_factory=list)
    provenance_coverage: float | None = None


class TermResolver:
    def __init__(self, max_depth: int = 5, max_token_budget: int = 2000):
        self.max_depth = max_depth
        self.max_token_budget = max_token_budget

    def _candidate_node_ids(self, term: str) -> list[str]:
        """Return candidate node IDs with defterm: as primary (TD §5.8)."""
        normalized = normalize_term(term).replace(" ", "_")
        return [
            f"defterm:{normalized}",   # primary prefix per spec
            f"term:{normalized}",      # legacy fallback
            normalized,
            normalize_term(term),
        ]

    def _pick_start_node(self, graph: nx.DiGraph, term: str) -> str | None:
        """Prefer defterm: nodes over term: nodes when both exist."""
        for node_id in self._candidate_node_ids(term):
            if node_id in graph.nodes:
                return node_id

        # Fallback: scan all defterm:/term: nodes for label match
        term_norm = normalize_term(term)
        # First pass: prefer defterm:
        for node in graph.nodes:
            node_str = str(node)
            if node_str.startswith("defterm:"):
                label = node_str.split(":", 1)[1].replace("_", " ").lower()
                if label == term_norm:
                    return node_str
        # Second pass: allow term: fallback
        for node in graph.nodes:
            node_str = str(node)
            if node_str.startswith("term:"):
                label = node_str.split(":", 1)[1].replace("_", " ").lower()
                if label == term_norm:
                    return node_str
        return None

    @staticmethod
    def _iter_dependency_neighbors(graph: nx.DiGraph, node: str) -> Iterable[str]:
        for succ in graph.successors(node):
            edge_type = str(graph[node][succ].get("type", "")).upper()
            # TD §5.8: Only follow REFERS_TO and DEPENDS_ON edges for term resolution
            if edge_type in {"REFERS_TO", "DEPENDS_ON"}:
                yield succ

    @staticmethod
    def _format_node_term(node_id: str, attrs: dict[str, Any]) -> str:
        if attrs.get("name"):
            return str(attrs["name"])
        if ":" in str(node_id):
            return str(node_id).split(":", 1)[1].replace("_", " ")
        return str(node_id)

    def resolve_term(
        self,
        term: str,
        graph: nx.DiGraph,
        max_depth: int | None = None,
        max_token_budget: int | None = None,
        deal_context: str | None = None,
    ) -> TermResolution:
        depth_limit = max_depth if max_depth is not None else self.max_depth
        token_budget = max_token_budget if max_token_budget is not None else self.max_token_budget

        start_node = self._pick_start_node(graph, term)
        if start_node is None:
            return TermResolution(
                root_term=term,
                closure=[],
                stitched_explanation=f"{term} not found in term graph.",
                citations=[],
                depth_reached=0,
                truncated=False,
                cycles_detected=[],
            )

        queue: list[tuple[str, int]] = [(start_node, 0)]
        visited: set[str] = set()
        active_path: set[str] = set()

        closure: list[str] = []
        citations: list[ResolutionCitation] = []
        cycles_detected: list[str] = []

        total_tokens = 0
        depth_reached = 0
        truncated = False

        while queue:
            node, depth = queue.pop(0)
            depth_reached = max(depth_reached, depth)
            if depth > depth_limit:
                continue

            if node in active_path:
                cycles_detected.append(node)
                continue

            if node in visited:
                continue

            visited.add(node)
            active_path.add(node)

            attrs = graph.nodes[node]

            if deal_context:
                node_deal = str(attrs.get("deal_context") or attrs.get("deal") or "")
                if node_deal and node_deal != deal_context:
                    active_path.discard(node)
                    continue

            term_text = self._format_node_term(node, attrs)
            closure.append(term_text)

            definition_text = str(attrs.get("defined_text") or attrs.get("extract_source") or "")
            token_estimate = max(1, len(definition_text.split()))
            total_tokens += token_estimate
            if total_tokens > token_budget:
                truncated = True
                active_path.discard(node)
                break

            citation = ResolutionCitation(
                section_id=attrs.get("section_id"),
                page=attrs.get("page"),
                chunk_id=attrs.get("chunk_id"),
                source_uri=attrs.get("source_uri"),
            )
            if citation.section_id or citation.page is not None or citation.chunk_id:
                citations.append(citation)

            for nbr in self._iter_dependency_neighbors(graph, node):
                if nbr == node:
                    continue
                if nbr in active_path:
                    cycles_detected.append(str(nbr))
                    continue
                if nbr in visited:
                    cycles_detected.append(str(nbr))
                    continue
                queue.append((nbr, depth + 1))

            active_path.discard(node)

        stitched_lines = []
        for idx, closure_term in enumerate(closure, start=1):
            stitched_lines.append(f"{idx}. {closure_term}")
        explanation = (
            f"Resolved '{term}' with {len(closure)} dependent term(s).\nWhere:\n" + "\n".join(stitched_lines)
            if closure
            else f"{term} not found in term graph."
        )

        return TermResolution(
            root_term=term,
            closure=closure,
            stitched_explanation=explanation,
            citations=citations,
            depth_reached=depth_reached,
            truncated=truncated,
            cycles_detected=sorted(set(cycles_detected)),
        )
