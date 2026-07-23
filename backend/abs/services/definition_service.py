"""
DefinitionService — defined-term graph + N-level resolution.

Pipeline
--------
1. Extract defined terms (``DefinedTermExtractor``).
2. Build the ``DEPENDS_ON`` dependency map (``reference_scanner``).
3. Persist definitions + edges into the deal store, with a source page when a
   page map is available.
4. Optionally resolve every term *bottom-up* (dependencies first) via the LLM,
   substituting resolved child meanings, and cache the resolved text.

The resolution order is a cycle-safe post-order DFS, so deeply nested and even
circular definitions terminate cleanly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from backend.abs.services.base import ABSService, ProgressFn, ServiceContext, ServiceResult
from backend.abs.services.llm_client import LLMClient
from backend.abs.services.pdf_extract import ExtractedDoc
from backend.abs.store import DealStore, new_id

_RESOLUTION_SYSTEM = (
    "You are a structured-finance analyst. Rewrite a legal defined term in clear, "
    "self-contained plain English. Substitute the resolved meaning of each referenced "
    "term. Be precise and concise. Return ONLY the resolved definition text."
)


def _topo_order(term_ids: list[str], deps: dict[str, list[str]]) -> list[str]:
    """Return term ids in dependency-first order (cycle-safe post-order DFS)."""
    order: list[str] = []
    state: dict[str, int] = {}  # 0=visiting, 1=done

    def visit(tid: str) -> None:
        s = state.get(tid)
        if s == 1 or s == 0:
            return  # done, or currently on stack (cycle) → skip to break it
        state[tid] = 0
        for child in deps.get(tid, []):
            visit(child)
        state[tid] = 1
        order.append(tid)

    for tid in term_ids:
        visit(tid)
    return order


class DefinitionService(ABSService):
    """Build and resolve the deal's defined-term graph."""

    name = "definition"

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)

    def context(self, deal_id: str) -> ServiceContext:
        return ServiceContext(deal_id=deal_id, deals_root=self.deals_root)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    async def build_definitions(
        self,
        deal_id: str,
        *,
        doc_id: Optional[str] = None,
        text: Optional[str] = None,
        extracted: Optional[ExtractedDoc] = None,
        llm: Optional[LLMClient] = None,
        resolve: bool = True,
        actor: str = "system",
        progress: Optional[ProgressFn] = None,
    ) -> ServiceResult:
        return await self.guard(
            self._build(deal_id, doc_id, text, extracted, llm, resolve, actor, progress)
        )

    async def _build(
        self,
        deal_id: str,
        doc_id: Optional[str],
        text: Optional[str],
        extracted: Optional[ExtractedDoc],
        llm: Optional[LLMClient],
        resolve: bool,
        actor: str,
        progress: Optional[ProgressFn] = None,
    ) -> dict[str, Any]:
        def emit(stage: str, status: str, **extra: Any) -> None:
            if progress is not None:
                progress({"stage": stage, "status": status, **extra})

        if extracted is not None and text is None:
            text = extracted.text

        emit("extract", "in-progress")
        # Persist graph (off-thread, pure CPU/disk).
        built = await self._to_thread(
            self._extract_and_store, deal_id, doc_id, text, extracted, actor
        )
        emit("extract", "done", terms=built.get("terms", 0), edges=built.get("edges", 0))

        resolved_count = 0
        if resolve and llm is not None:
            emit("resolve", "in-progress", total=built.get("terms", 0))
            resolved_count = await self._resolve_all(deal_id, llm, progress=progress)
            emit("resolve", "done", resolved=resolved_count)

        built["resolved"] = resolved_count
        return built

    def _extract_and_store(
        self,
        deal_id: str,
        doc_id: Optional[str],
        text: Optional[str],
        extracted: Optional[ExtractedDoc],
        actor: str,
    ) -> dict[str, Any]:
        from backend.graph.defined_term_extractor import DefinedTermExtractor
        from backend.graph.reference_scanner import build_reference_map

        store = self.context(deal_id).store()

        if text is None:
            # Reconstruct text from stored chunks for the document.
            chunks = store.list_chunks(doc_id) if doc_id else []
            text = "\n\n".join(c["text"] for c in chunks)

        terms = DefinedTermExtractor().extract(text or "")
        term_dictionary = {t.surface_form: t.definition_text for t in terms}

        # Map term name → row id as we insert.
        name_to_id: dict[str, str] = {}
        for t in terms:
            page = None
            if extracted is not None:
                pos = (text or "").find(t.surface_form)
                if pos >= 0:
                    page = extracted.char_to_page(pos)
            term_id = store.add_definition({
                "term_id": new_id("term_"),
                "deal_id": deal_id,
                "doc_id": doc_id,
                "term_name": t.surface_form,
                "raw_definition": t.definition_text,
                "page": page,
                "citation": f"p.{page}" if page else "",
                "status": "draft",
            })
            name_to_id[t.surface_form] = term_id

        # Edges (only between terms we actually stored).
        reference_map = build_reference_map(term_dictionary)
        edge_count = 0
        for from_name, refs in reference_map.items():
            from_id = name_to_id.get(from_name)
            if not from_id:
                continue
            for ref_name in refs:
                to_id = name_to_id.get(ref_name)
                if to_id and to_id != from_id:
                    store.add_definition_edge(from_id, to_id, "DEPENDS_ON")
                    edge_count += 1

        store.audit(
            "build_definitions",
            actor=actor,
            object_type="deal",
            object_id=deal_id,
            after={"terms": len(name_to_id), "edges": edge_count},
        )
        return {"terms": len(name_to_id), "edges": edge_count}

    # ------------------------------------------------------------------
    # Resolve
    # ------------------------------------------------------------------
    async def resolve_definitions(self, deal_id: str, llm: LLMClient, progress: Optional[ProgressFn] = None) -> ServiceResult:
        return await self.guard(self._resolve_all(deal_id, llm, progress=progress))

    async def _resolve_all(self, deal_id: str, llm: LLMClient, progress: Optional[ProgressFn] = None) -> int:
        store = self.context(deal_id).store(init=False)
        definitions = await self._to_thread(store.list_definitions, deal_id)
        if not definitions:
            return 0

        # Build dependency adjacency (term_id → [dependency term_ids]).
        deps: dict[str, list[str]] = {}
        for d in definitions:
            children = await self._to_thread(store.get_dependencies, d["term_id"])
            deps[d["term_id"]] = [c["term_id"] for c in children]

        order = _topo_order([d["term_id"] for d in definitions], deps)
        by_id = {d["term_id"]: d for d in definitions}
        resolved_text: dict[str, str] = {}
        total = len(order)

        count = 0
        for tid in order:
            node = by_id.get(tid)
            if node is None:
                continue
            child_resolved = {
                by_id[c]["term_name"]: resolved_text.get(c, by_id[c].get("raw_definition") or "")
                for c in deps.get(tid, [])
                if c in by_id
            }
            prompt = self._resolution_prompt(node["term_name"], node.get("raw_definition") or "", child_resolved)
            result = await llm.complete(prompt, system=_RESOLUTION_SYSTEM, temperature=0.0, max_tokens=600)
            resolved_text[tid] = result.text.strip()
            await self._to_thread(
                store.update_resolved_definition, tid, resolved_text[tid], depth=None
            )
            count += 1
            if progress is not None:
                progress({"stage": "resolve", "status": "in-progress", "resolved": count, "total": total, "term": node["term_name"]})
        return count

    @staticmethod
    def _resolution_prompt(term: str, raw: str, child_resolved: dict[str, str]) -> str:
        lines = [f'Defined term: "{term}"', f"Verbatim definition: {raw}", ""]
        if child_resolved:
            lines.append("Resolved meanings of referenced terms:")
            for name, meaning in child_resolved.items():
                snippet = meaning[:300]
                lines.append(f'- "{name}": {snippet}')
            lines.append("")
        lines.append("Resolved plain-English definition:")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    async def list_definitions(self, deal_id: str) -> ServiceResult:
        store = self.context(deal_id).store(init=False)
        return await self.guard(self._to_thread(store.list_definitions, deal_id))

    async def list_top_level(self, deal_id: str) -> ServiceResult:
        store = self.context(deal_id).store(init=False)
        return await self.guard(self._to_thread(store.list_top_level_definitions, deal_id))

    async def get_resolution_tree(self, deal_id: str, term_id: str) -> ServiceResult:
        store = self.context(deal_id).store(init=False)
        return await self.guard(self._to_thread(store.resolution_tree, term_id))
