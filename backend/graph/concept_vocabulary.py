"""
Concept Vocabulary Builder — Document-Aware Section Keyword Enrichment.

Runs after graph construction to analyse each SECTION node and enrich it
with *concept_keywords*: a set of keywords derived from the section's own
content, defined terms, and items.  These keywords go far beyond the
section heading, letting the retriever's ``graph_section_lookup()`` find
sections even when the query uses vocabulary that doesn't appear in any
heading.

Concept keywords are a **retrieval index, not content**.  They tell the
retriever *which section to look in* for a query — the final answer is
always generated from real document text, never from concept keywords.

Example
-------
The PSA section "DISTRIBUTIONS AND ADVANCES" contains items about
*Realized Loss*, *Loss Allocation*, *Subordination*, etc.  After
enrichment its ``concept_keywords`` attribute includes ``loss``,
``realized``, ``subordination``, ``allocation``, ``overcollateral`` …
so a query "How are realized losses allocated?" now matches the section
purely through keyword overlap — no hardcoded heuristics needed.

With LLM enrichment the vocabulary is even richer: the LLM generates
synonyms like ``credit loss``, ``net loss``, ``applied loss`` for the
defined term "Realized Loss" — vocabulary that never appears verbatim
in the document but that a human reader would associate.

Design
------
Enrichment runs in four phases, combined with union + dedup:

1. **Phase 1 — LLM term synonym expansion** (primary, requires llm_callable)
   For every defined term, the LLM generates 5-8 alternate keywords
   (synonyms, abbreviations, related concepts, plurals).  Terms are
   batched 15-20 per call.  Synonyms are propagated to BOTH the section
   that defines the term AND every section that references it.

2. **Phase 2 — LLM section-level enrichment** (sparse sections only)
   Sections with fewer than 5 LLM-propagated keywords get a single
   section-level LLM call (heading + excerpt → topic keywords).

3. **Phase 3 — Deterministic extraction** (always runs, no LLM needed)
   Keywords from section headings, item text, defined terms,
   cross-references, and DEFINED_TERM nodes.

4. **Phase 4 — Union + dedup + cap**
   All three sources are merged per section, deduplicated, and capped
   at ``max_keywords_per_section`` (default 100).

If ``llm_callable`` is ``None`` (CLI / headless mode), Phases 1-2 are
skipped with a WARNING log, and only deterministic extraction runs.

The builder also produces a **step_back_vocabulary**: a flat mapping
``keyword → [broadening phrases]`` stored as a graph-level attribute,
consumed by the retriever's ``_generate_step_back_query()`` at query
time.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Set

import networkx as nx

logger = logging.getLogger(__name__)

# ── Stop-words stripped from extracted keywords ────────────────────
_STOP_WORDS: Set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "for", "of", "to", "in", "on", "at", "by", "with", "from",
    "and", "or", "but", "not", "if", "then", "than", "that", "this",
    "such", "any", "each", "all", "one", "two", "its", "may", "shall",
    "will", "can", "has", "had", "have", "does", "did", "do",
    "which", "who", "whom", "whose", "what", "how", "when", "where",
    "why", "would", "could", "should", "must", "might",
    "means", "defined", "herein", "hereof", "thereof", "therein",
    "pursuant", "section", "article", "paragraph", "clause",
    "respect", "under", "upon", "into", "out", "about", "between",
    "through", "during", "before", "after", "above", "below",
    "other", "same", "more", "less", "only", "also", "still",
    "just", "even", "very", "most", "some", "many", "much",
    "set", "forth", "made", "make", "date", "provided", "however",
}

# ── LLM prompt templates ──────────────────────────────────────────

_TERM_SYNONYM_PROMPT = """\
For each defined term below, list 5-8 alternate search keywords or \
phrases (synonyms, abbreviations, related concepts, plural forms) \
a reader might use when searching for information about this concept.

Terms:
{numbered_terms}

Return ONLY valid JSON — no markdown fences, no explanation:
{{"Term Name": ["keyword1", "keyword2", ...], ...}}"""

_SECTION_KEYWORD_PROMPT = """\
Given this document section:
Heading: "{heading}"
Excerpt: "{excerpt}"

List 10-15 keywords or short phrases a reader might search for when \
looking for information in this section.

Return ONLY valid JSON — no markdown fences, no explanation:
["keyword1", "keyword2", ...]"""


def _tokenize(text: str) -> List[str]:
    """Extract meaningful lowercase keywords (>= 3 chars, not stop-words)."""
    return [
        w for w in re.findall(r"[a-zA-Z]{3,}", text.lower())
        if w not in _STOP_WORDS
    ]


class ConceptVocabularyBuilder:
    """Enriches SECTION nodes with *concept_keywords* and builds a
    flat *step_back_vocabulary* stored on the graph object.

    Call :meth:`enrich` after the :class:`EnhancedGraphBuilder` has
    finished constructing the hierarchical graph.
    """

    # ── Public API ────────────────────────────────────────────────

    @classmethod
    def enrich(
        cls,
        G: nx.DiGraph,
        *,
        llm_callable: Optional[Callable[[str], str]] = None,
        max_keywords_per_section: int = 100,
        max_broadening_phrases: int = 8,
    ) -> Dict[str, Any]:
        """Enrich *G* in-place and return enrichment statistics.

        Parameters
        ----------
        G : nx.DiGraph
            The hierarchical graph produced by :class:`EnhancedGraphBuilder`.
        llm_callable : callable, optional
            ``llm_callable(prompt: str) -> str``.  When provided, Phases 1
            and 2 (LLM enrichment) run.  When ``None``, only deterministic
            Phase 3 runs, with a warning log.
        max_keywords_per_section : int
            Hard cap on concept keywords per section after union + dedup.
        max_broadening_phrases : int
            Max entries in the step-back vocabulary per keyword.
        """
        stats: Dict[str, Any] = {
            "sections_enriched": 0,
            "total_concept_keywords": 0,
            "step_back_entries": 0,
            "llm_term_batches": 0,
            "llm_term_synonyms": 0,
            "llm_section_calls": 0,
            "llm_skipped": False,
        }

        # ── Pre-compute graph mappings ────────────────────────────
        section_items: Dict[str, List[str]] = defaultdict(list)
        section_defs: Dict[str, List[str]] = defaultdict(list)

        for src, tgt, edata in G.edges(data=True):
            etype = edata.get("type", "")
            if etype == "HAS_DEFINITION":
                section_items[src].append(tgt)
                section_defs[src].append(tgt)
            elif etype.startswith("HAS_"):
                section_items[src].append(tgt)

        item_references: Dict[str, List[str]] = defaultdict(list)
        for src, tgt, edata in G.edges(data=True):
            if edata.get("type") == "REFERENCES":
                item_references[src].append(tgt)

        def_item_names: Dict[str, str] = {}
        for node_id, data in G.nodes(data=True):
            if data.get("type") == "ITEM" and data.get("item_type") == "Definition":
                def_item_names[node_id] = data.get("text", "")[:200]

        defterm_nodes: Dict[str, Dict[str, Any]] = {}
        for node_id, data in G.nodes(data=True):
            if data.get("type") == "DEFINED_TERM":
                defterm_nodes[node_id] = data

        # ── Build defined-term catalog ────────────────────────────
        # term_name → { "def_node_id": ..., "defining_section": ..., "referencing_sections": set() }
        term_catalog: Dict[str, Dict[str, Any]] = {}

        for sec_id, def_ids in section_defs.items():
            for def_id in def_ids:
                def_text = G.nodes.get(def_id, {}).get("text", "")
                term_name = cls._extract_term_name(def_text)
                if term_name:
                    term_catalog[term_name] = {
                        "def_node_id": def_id,
                        "defining_section": sec_id,
                        "referencing_sections": set(),
                    }

        # Map: which sections reference which terms (via REFERENCES edges)
        for sec_id, item_ids in section_items.items():
            for item_id in item_ids:
                for ref_id in item_references.get(item_id, []):
                    ref_text = G.nodes.get(ref_id, {}).get("text", "")
                    ref_term = cls._extract_term_name(ref_text)
                    if ref_term and ref_term in term_catalog:
                        term_catalog[ref_term]["referencing_sections"].add(sec_id)

        # ── Phase 1: LLM term synonym expansion ──────────────────
        # term_name → [lowercased keyword strings]
        term_synonyms: Dict[str, List[str]] = {}

        if llm_callable is not None:
            term_synonyms = cls._llm_term_synonyms(
                {name: def_item_names.get(info["def_node_id"], "")
                 for name, info in term_catalog.items()},
                llm_callable,
            )
            stats["llm_term_batches"] = max(
                1, (len(term_catalog) + 16) // 17
            ) if term_catalog else 0
            stats["llm_term_synonyms"] = sum(len(v) for v in term_synonyms.values())
        else:
            # Phase 18: LLM enrichment is handled externally via the
            # enrich-vocabulary CLI commands (extract-terms → JS LLM →
            # apply-synonyms).  Deterministic concept extraction runs
            # unconditionally in Phase 3 below.
            logger.debug(
                "[ConceptVocabulary] No inline LLM — deterministic concept "
                "extraction only (use enrich-vocabulary CLI for LLM enrichment)"
            )

        # Build per-section LLM keyword sets by propagating synonyms
        # to both defining AND referencing sections.
        section_llm_kws: Dict[str, Set[str]] = defaultdict(set)
        for term_name, syns in term_synonyms.items():
            info = term_catalog.get(term_name, {})
            target_sections = set()
            if info.get("defining_section"):
                target_sections.add(info["defining_section"])
            target_sections.update(info.get("referencing_sections", set()))
            for sec_id in target_sections:
                section_llm_kws[sec_id].update(syns)

        # ── Phase 2: LLM section-level enrichment (sparse) ───────
        if llm_callable is not None:
            all_section_ids = [
                nid for nid, d in G.nodes(data=True)
                if d.get("type", "").upper() == "SECTION"
            ]
            sparse_sections = [
                sid for sid in all_section_ids
                if len(section_llm_kws.get(sid, set())) < 5
            ]
            if sparse_sections:
                sparse_kws = cls._llm_section_keywords(
                    G, sparse_sections, section_items, llm_callable,
                )
                for sid, kws in sparse_kws.items():
                    section_llm_kws[sid].update(kws)
                stats["llm_section_calls"] = len(sparse_sections)

        # ── Phase 3: Deterministic extraction + Phase 4: Union ────
        keyword_to_sections: Dict[str, Set[str]] = defaultdict(set)

        for node_id, data in list(G.nodes(data=True)):
            if data.get("type", "").upper() != "SECTION":
                continue

            heading = (data.get("heading", "") or data.get("section_heading", "")).lower()
            concept_kws: Set[str] = set()

            # ── Deterministic Source 1: Heading keywords ──────────
            concept_kws.update(_tokenize(heading))

            # ── Deterministic Source 2: Defined terms (HAS_DEFINITION)
            for def_id in section_defs.get(node_id, []):
                def_text = G.nodes[def_id].get("text", "") if def_id in G else ""
                term_name = cls._extract_term_name(def_text)
                if term_name:
                    concept_kws.update(_tokenize(term_name))
                concept_kws.update(_tokenize(def_text)[:5])

            # ── Deterministic Source 3: Item text ─────────────────
            for item_id in section_items.get(node_id, []):
                item_data = G.nodes.get(item_id, {})
                item_text = item_data.get("text", "")
                item_kws = _tokenize(item_text)
                concept_kws.update(item_kws[:8])

            # ── Deterministic Source 4: Referenced terms ───────────
            for item_id in section_items.get(node_id, []):
                for ref_id in item_references.get(item_id, []):
                    ref_text = G.nodes.get(ref_id, {}).get("text", "")
                    term_name = cls._extract_term_name(ref_text)
                    if term_name:
                        concept_kws.update(_tokenize(term_name))

            # ── Deterministic Source 5: DEFINED_TERM nodes ────────
            sec_number = data.get("section_number", "")
            for dt_id, dt_data in defterm_nodes.items():
                dt_section = dt_data.get("section_id", "")
                if dt_section and sec_number and dt_section == sec_number:
                    surface = dt_data.get("surface_form", "") or dt_data.get("name", "")
                    concept_kws.update(_tokenize(surface))

            # ── Phase 4: Union LLM keywords + deterministic ──────
            concept_kws.update(section_llm_kws.get(node_id, set()))

            # Cap at budget
            concept_list = sorted(concept_kws)[:max_keywords_per_section]

            G.nodes[node_id]["concept_keywords"] = concept_list

            for kw in concept_list:
                keyword_to_sections[kw].add(node_id)

            stats["sections_enriched"] += 1
            stats["total_concept_keywords"] += len(concept_list)

        # ── Build step-back vocabulary (graph-level attribute) ────
        step_back_vocab: Dict[str, List[str]] = {}

        for kw, sec_ids in keyword_to_sections.items():
            headings: List[str] = []
            for sid in sec_ids:
                h = G.nodes[sid].get("heading", "") or G.nodes[sid].get("section_heading", "")
                if h and h not in headings:
                    headings.append(h)
            if headings:
                broadening: List[str] = list(headings)
                for sid in sec_ids:
                    for _, neighbor, edata in G.edges(sid, data=True):
                        if edata.get("type") == "NEXT":
                            nh = G.nodes[neighbor].get("heading", "")
                            if nh and nh not in broadening:
                                broadening.append(nh)
                step_back_vocab[kw] = broadening[:max_broadening_phrases]

        G.graph["step_back_vocabulary"] = step_back_vocab
        stats["step_back_entries"] = len(step_back_vocab)

        logger.info(
            "[ConceptVocabulary] Enriched %d sections with %d concept keywords, "
            "%d step-back entries, LLM batches=%d, LLM synonyms=%d, "
            "LLM section calls=%d, LLM skipped=%s",
            stats["sections_enriched"],
            stats["total_concept_keywords"],
            stats["step_back_entries"],
            stats["llm_term_batches"],
            stats["llm_term_synonyms"],
            stats["llm_section_calls"],
            stats["llm_skipped"],
        )
        return stats

    # ── Phase 1 helper: LLM term synonym expansion ────────────────

    @classmethod
    def _llm_term_synonyms(
        cls,
        defined_terms: Dict[str, str],
        llm_callable: Callable[[str], str],
        batch_size: int = 17,
    ) -> Dict[str, List[str]]:
        """Call LLM to generate synonym keywords for defined terms.

        Terms are sent in batches of *batch_size* to keep per-call token
        cost manageable.  Returns ``{term_name: [lowered_keywords]}``.
        """
        all_synonyms: Dict[str, List[str]] = {}
        term_list = list(defined_terms.items())

        if not term_list:
            return all_synonyms

        for batch_start in range(0, len(term_list), batch_size):
            batch = term_list[batch_start : batch_start + batch_size]
            numbered = "\n".join(
                f"{i + 1}. {name}" for i, (name, _) in enumerate(batch)
            )
            prompt = _TERM_SYNONYM_PROMPT.format(numbered_terms=numbered)

            try:
                raw = llm_callable(prompt)
                parsed = cls._parse_json_response(raw, expect_dict=True)
                if not isinstance(parsed, dict):
                    logger.warning(
                        "[ConceptVocabulary] LLM returned non-dict for term batch"
                    )
                    continue

                for term_name, synonyms in parsed.items():
                    if not isinstance(synonyms, list):
                        continue
                    kws: List[str] = []
                    for syn in synonyms:
                        kws.extend(_tokenize(str(syn)))
                    if kws:
                        # Match to the original term name (best-effort)
                        matched = cls._match_term_name(term_name, [n for n, _ in batch])
                        all_synonyms[matched] = kws

                logger.debug(
                    "[ConceptVocabulary] LLM batch %d-%d: %d terms → %d synonym sets",
                    batch_start,
                    batch_start + len(batch),
                    len(batch),
                    len([n for n, _ in batch if n in all_synonyms]),
                )
            except Exception as exc:
                logger.warning(
                    "[ConceptVocabulary] LLM term synonym batch %d failed: %s",
                    batch_start // batch_size,
                    exc,
                )
                continue

        return all_synonyms

    # ── Phase 2 helper: LLM section-level keywords ────────────────

    @classmethod
    def _llm_section_keywords(
        cls,
        G: nx.DiGraph,
        section_ids: List[str],
        section_items: Dict[str, List[str]],
        llm_callable: Callable[[str], str],
    ) -> Dict[str, Set[str]]:
        """Call LLM for section-level keyword extraction on sparse sections.

        Only called for sections that received fewer than 5 LLM-propagated
        keywords from Phase 1 (term synonyms).
        """
        result: Dict[str, Set[str]] = {}

        for sec_id in section_ids:
            data = G.nodes.get(sec_id, {})
            heading = data.get("heading", "") or data.get("section_heading", "")

            # Build excerpt from first few items in this section
            excerpt_parts: List[str] = []
            for item_id in section_items.get(sec_id, []):
                child_text = G.nodes.get(item_id, {}).get("text", "")
                if child_text:
                    excerpt_parts.append(child_text[:200])
                if sum(len(p) for p in excerpt_parts) > 500:
                    break
            excerpt = " ".join(excerpt_parts)[:500]

            if not heading and not excerpt:
                continue

            prompt = _SECTION_KEYWORD_PROMPT.format(
                heading=heading,
                excerpt=excerpt,
            )

            try:
                raw = llm_callable(prompt)
                parsed = cls._parse_json_response(raw, expect_dict=False)
                if isinstance(parsed, list):
                    kws: Set[str] = set()
                    for item in parsed:
                        kws.update(_tokenize(str(item)))
                    result[sec_id] = kws
            except Exception as exc:
                logger.warning(
                    "[ConceptVocabulary] LLM section keyword call failed "
                    "for %s (%s): %s",
                    sec_id,
                    heading[:40],
                    exc,
                )

        return result

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _parse_json_response(raw: str, *, expect_dict: bool = True) -> Any:
        """Parse a JSON response from the LLM, tolerating markdown fences."""
        text = raw.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json or ```) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find the first { or [ and parse from there
            for i, ch in enumerate(text):
                if (expect_dict and ch == "{") or (not expect_dict and ch == "["):
                    try:
                        return json.loads(text[i:])
                    except json.JSONDecodeError:
                        continue
            raise ValueError(f"Could not parse JSON from LLM response: {text[:200]}")

    @staticmethod
    def _match_term_name(llm_name: str, original_names: List[str]) -> str:
        """Best-effort match an LLM-returned term name to the original.

        The LLM may slightly alter casing or spacing.  We do a
        case-insensitive match and fall back to the LLM name.
        """
        lower = llm_name.strip().lower()
        for orig in original_names:
            if orig.strip().lower() == lower:
                return orig
        return llm_name.strip()

    @staticmethod
    def _extract_term_name(definition_text: str) -> str:
        """Extract the defined term from a definition's text.

        Handles patterns like:
        - ``"Distribution Date" means ...``
        - ``Distribution Date: The 25th day ...``
        - ``Certificate Principal Balance shall mean ...``
        """
        if not definition_text:
            return ""
        # Quoted term: "Some Term" means …
        m = re.search(r'["\u201c]([^"\u201d]{2,80})["\u201d]', definition_text)
        if m:
            return m.group(1).strip()
        # Term: definition (colon separator)
        m = re.match(r'^([A-Z][A-Za-z\s/\-]{2,60}):', definition_text)
        if m:
            return m.group(1).strip()
        # Term means / shall mean
        m = re.match(r'^([A-Z][A-Za-z\s/\-]{2,60})\s+(?:means|shall\s+mean)\b', definition_text)
        if m:
            return m.group(1).strip()
        return ""

    # ── External enrichment (CLI two-phase flow) ──────────────────

    @classmethod
    def extract_defined_terms(cls, G: nx.DiGraph) -> Dict[str, str]:
        """Extract all defined terms from the graph for external LLM calls.

        Returns ``{term_name: definition_excerpt}`` — the JS extension can
        send these to the Copilot LLM and pass results back via
        :meth:`apply_external_synonyms`.
        """
        terms: Dict[str, str] = {}

        # ── Primary source: TERM::* nodes (type="defined_term") ──
        # These are created by the definition_extractor and have clean
        # term_name + definition_text attributes.
        for node_id, data in G.nodes(data=True):
            if data.get("type") == "defined_term":
                term_name = data.get("term_name", "")
                definition_text = data.get("definition_text", "")
                if term_name and definition_text:
                    terms[term_name] = definition_text[:200]

        # ── Fallback: ITEM nodes with item_type="Definition" ─────
        # Rare, but a few items are classified as Definition by the
        # item extractor.  Use regex to pull out the term name.
        for node_id, data in G.nodes(data=True):
            if data.get("type") == "ITEM" and data.get("item_type") == "Definition":
                text = data.get("text", "")
                term_name = cls._extract_term_name(text)
                if term_name and term_name not in terms:
                    terms[term_name] = text[:200]

        return terms

    @classmethod
    def apply_external_synonyms(
        cls,
        G: nx.DiGraph,
        synonyms: Dict[str, List[str]],
        *,
        max_keywords_per_section: int = 500,
    ) -> Dict[str, Any]:
        """Merge externally-generated LLM synonyms into the graph.

        Called by the CLI ``enrich-vocabulary --apply-synonyms`` command
        after the JS extension has made the Copilot LLM calls.

        Parameters
        ----------
        G : nx.DiGraph
            Graph that already has deterministic concept_keywords.
        synonyms : dict
            ``{term_name: ["keyword1", "keyword2", ...]}`` from the LLM.
        max_keywords_per_section : int
            Hard cap per section (default 500).  Higher than the
            deterministic-only cap (100) because LLM synonyms add
            valuable alias/plain-language tokens.

        Returns statistics about how many keywords were added.
        """
        stats = {"terms_matched": 0, "keywords_added": 0}

        # ── Collect all TERM::* term names ────────────────────────
        all_term_names: Dict[str, str] = {}  # lower → canonical
        for node_id, data in G.nodes(data=True):
            if data.get("type") == "defined_term":
                tn = data.get("term_name", "")
                if tn:
                    all_term_names[tn.lower()] = tn

        # ── Build section → item_texts and section IDs ────────────
        section_ids: List[str] = []
        section_item_texts: Dict[str, str] = {}  # sec_id → concatenated item text
        for node_id, data in G.nodes(data=True):
            if data.get("type", "").upper() == "SECTION":
                section_ids.append(node_id)

        section_items: Dict[str, List[str]] = defaultdict(list)
        for src, tgt, edata in G.edges(data=True):
            if edata.get("type", "").startswith("HAS_"):
                section_items[src].append(tgt)

        for sec_id in section_ids:
            texts = []
            for item_id in section_items.get(sec_id, []):
                t = G.nodes.get(item_id, {}).get("text", "")
                if t:
                    texts.append(t)
            section_item_texts[sec_id] = " ".join(texts).lower()

        # ── Map each term → sections that mention it ──────────────
        term_sections: Dict[str, Set[str]] = defaultdict(set)
        for term_lower, term_canonical in all_term_names.items():
            for sec_id in section_ids:
                if term_lower in section_item_texts.get(sec_id, ""):
                    term_sections[term_canonical].add(sec_id)

        # ── Apply synonyms to matched sections ────────────────────
        for term_name, syn_list in synonyms.items():
            matched = cls._match_term_name(term_name, list(term_sections.keys()))
            target_secs = term_sections.get(matched, set())
            if not target_secs:
                continue
            stats["terms_matched"] += 1

            kws: List[str] = []
            for syn in syn_list:
                kws.extend(_tokenize(str(syn)))
            if not kws:
                continue

            for sec_id in target_secs:
                existing = set(G.nodes[sec_id].get("concept_keywords", []))
                before = len(existing)
                existing.update(kws)
                G.nodes[sec_id]["concept_keywords"] = sorted(existing)[:max_keywords_per_section]
                stats["keywords_added"] += len(existing) - before

        # Rebuild step-back vocabulary with new keywords
        keyword_to_sections: Dict[str, Set[str]] = defaultdict(set)
        for nid, data in G.nodes(data=True):
            if data.get("type", "").upper() == "SECTION":
                for kw in data.get("concept_keywords", []):
                    keyword_to_sections[kw].add(nid)

        step_back_vocab: Dict[str, List[str]] = {}
        for kw, sec_ids in keyword_to_sections.items():
            headings: List[str] = []
            for sid in sec_ids:
                h = G.nodes[sid].get("heading", "") or G.nodes[sid].get("section_heading", "")
                if h and h not in headings:
                    headings.append(h)
            if headings:
                broadening = list(headings)
                for sid in sec_ids:
                    for _, neighbor, edata in G.edges(sid, data=True):
                        if edata.get("type") == "NEXT":
                            nh = G.nodes[neighbor].get("heading", "")
                            if nh and nh not in broadening:
                                broadening.append(nh)
                step_back_vocab[kw] = broadening[:8]

        G.graph["step_back_vocabulary"] = step_back_vocab

        logger.info(
            "[ConceptVocabulary] Applied external synonyms: %d terms matched, "
            "%d keywords added",
            stats["terms_matched"],
            stats["keywords_added"],
        )
        return stats

    # ── Q1: Per-definition keyword storage ────────────────────────

    @classmethod
    def apply_term_keywords(
        cls,
        G: nx.DiGraph,
        keywords_dict: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        """Store per-term LLM-generated keywords directly on TERM::* nodes.

        Unlike :meth:`apply_external_synonyms`, which propagates keywords
        to SECTION nodes, this method stores keywords on the *defining* node
        itself (``type='defined_term'``).  This captures "what does this term
        *mean*" rather than "which sections discuss it."

        Parameters
        ----------
        G : nx.DiGraph
            The knowledge graph (modified in-place).
        keywords_dict : dict
            ``{term_name: ["keyword1", "keyword2", ...], ...}`` as produced
            by the per-definition LLM call (one call per term).

        Returns
        -------
        dict
            Statistics: ``terms_matched``, ``keywords_stored``.
        """
        stats: Dict[str, Any] = {
            "terms_matched": 0,
            "keywords_stored": 0,
        }

        # Build lookup: term_name (lower) → node_id
        term_node_map: Dict[str, str] = {}
        for nid, data in G.nodes(data=True):
            if data.get("type") == "defined_term":
                tn = data.get("term_name", "")
                if tn:
                    term_node_map[tn.lower()] = nid

        for term_name, keyword_list in keywords_dict.items():
            if not isinstance(keyword_list, list):
                continue
            keywords_clean = [str(k).strip().lower() for k in keyword_list if str(k).strip()]
            if not keywords_clean:
                continue

            # Exact match first, then fuzzy
            nid = term_node_map.get(term_name.lower())
            if nid is None:
                match_key = cls._match_term_name(term_name, list(term_node_map.keys()))
                nid = term_node_map.get(match_key)

            if nid is None:
                continue

            existing = set(G.nodes[nid].get("concept_keywords", []))
            before = len(existing)
            existing.update(keywords_clean)
            G.nodes[nid]["concept_keywords"] = sorted(existing)
            stats["terms_matched"] += 1
            stats["keywords_stored"] += len(existing) - before

        logger.info(
            "[ConceptVocabulary] apply_term_keywords: %d terms matched, %d keywords stored",
            stats["terms_matched"],
            stats["keywords_stored"],
        )
        return stats
