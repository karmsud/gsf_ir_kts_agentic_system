"""
GoverningDocService — generate the reviewed "governing document" bridge.

For each operative (waterfall/distribution) excerpt, the service produces a
structured clause pairing the *verbatim* legal text with a plain-English
interpretation, a math formula, and a code hint — enriched with the resolved
meanings of the capitalized terms it references. This reviewed artifact is the
controlled data contract the payment-model generator compiles from.

Stateless + async.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from backend.abs.services.base import ABSService, ProgressFn, ServiceContext, ServiceResult
from backend.abs.services.json_utils import parse_json_lenient
from backend.abs.services.llm_client import LLMClient
from backend.abs.store import DealStore

_WATERFALL_KEYWORDS = ("distribut", "waterfall", "priority", "payment", "allocat", "shall pay", "order")
_MAX_CLAUSES = 20
_CAP_TERM_RE = re.compile(r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,4})\b")

_GD_SYSTEM = (
    "You convert a verbatim clause from a structured-finance governing document into a "
    "precise operational specification. Return STRICT JSON with keys: plain_english "
    "(clear interpretation), math_formula (an equation or empty string), code_hint "
    "(a one-line Python expression sketch or empty string). Do not invent obligations."
)


class GoverningDocService(ABSService):
    """Build the governing-document clause bridge."""

    name = "governing_doc"

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)

    def context(self, deal_id: str) -> ServiceContext:
        return ServiceContext(deal_id=deal_id, deals_root=self.deals_root)

    async def generate(
        self,
        deal_id: str,
        llm: LLMClient,
        *,
        actor: str = "system",
        progress: Optional[ProgressFn] = None,
    ) -> ServiceResult:
        return await self.guard(self._generate(deal_id, llm, actor, progress))

    async def _generate(
        self, deal_id: str, llm: LLMClient, actor: str, progress: Optional[ProgressFn]
    ) -> dict[str, Any]:
        chunks = await self._to_thread(self._select_operative_chunks, deal_id)
        definitions = await self._to_thread(self._definition_lookup, deal_id)

        if progress:
            progress({"stage": "governing_doc", "status": "in-progress", "clauses": len(chunks)})

        clauses: list[dict[str, Any]] = []
        for ordinal, chunk in enumerate(chunks):
            verbatim = chunk["text"]
            resolved_terms = self._resolved_terms_in(verbatim, definitions)
            prompt = self._clause_prompt(verbatim, resolved_terms)
            result = await llm.complete(prompt, system=_GD_SYSTEM, temperature=0.0, max_tokens=700)
            parsed = parse_json_lenient(result.text) or {}
            clauses.append({
                "gd_id": None,
                "deal_id": deal_id,
                "doc_id": chunk.get("doc_id"),
                "section_id": chunk.get("section_id"),
                "ordinal": ordinal,
                "verbatim": verbatim,
                "plain_english": str(parsed.get("plain_english", "")) if isinstance(parsed, dict) else "",
                "math_formula": str(parsed.get("math_formula", "")) if isinstance(parsed, dict) else "",
                "code_hint": str(parsed.get("code_hint", "")) if isinstance(parsed, dict) else "",
                "resolved_terms": resolved_terms,
                "citation": chunk.get("_citation", ""),
                "status": "pending_review",
            })

        stored = await self._to_thread(self._store_clauses, deal_id, clauses, actor)
        if progress:
            progress({"stage": "governing_doc", "status": "done", "clauses": stored})
        return {"clauses": stored}

    async def list_clauses(self, deal_id: str) -> ServiceResult:
        store = self.context(deal_id).store(init=False)
        return await self.guard(self._to_thread(store.list_governing_clauses, deal_id))

    # ------------------------------------------------------------------
    # Sync helpers
    # ------------------------------------------------------------------
    def _select_operative_chunks(self, deal_id: str) -> list[dict[str, Any]]:
        store = self.context(deal_id).store(init=False)
        documents = store.list_documents(deal_id)
        section_path: dict[str, str] = {}
        chunks: list[dict[str, Any]] = []
        for doc in documents:
            for sec in store.list_sections(doc["doc_id"]):
                section_path[sec["section_id"]] = sec["section_path"]
            chunks.extend(store.list_chunks(doc["doc_id"]))

        def score(chunk: dict[str, Any]) -> int:
            text = (chunk.get("text") or "").lower()
            return sum(text.count(kw) for kw in _WATERFALL_KEYWORDS)

        relevant = sorted(chunks, key=score, reverse=True)
        relevant = [c for c in relevant if score(c) > 0][:_MAX_CLAUSES]
        for c in relevant:
            sp = section_path.get(c.get("section_id"), "")
            page = c.get("page_start")
            c["_citation"] = (f"{sp} p.{page}" if page else sp).strip()
        return relevant

    def _definition_lookup(self, deal_id: str) -> dict[str, str]:
        store = self.context(deal_id).store(init=False)
        out: dict[str, str] = {}
        for d in store.list_definitions(deal_id):
            out[d["term_name"]] = d.get("resolved_definition") or d.get("raw_definition") or ""
        return out

    def _resolved_terms_in(self, text: str, definitions: dict[str, str]) -> dict[str, str]:
        found: dict[str, str] = {}
        for term, meaning in definitions.items():
            if term and term in text:
                found[term] = meaning[:400]
        return found

    def _clause_prompt(self, verbatim: str, resolved_terms: dict[str, str]) -> str:
        lines = [f"VERBATIM CLAUSE:\n{verbatim}\n"]
        if resolved_terms:
            lines.append("RESOLVED DEFINED TERMS:")
            for term, meaning in list(resolved_terms.items())[:10]:
                lines.append(f'- "{term}": {meaning}')
            lines.append("")
        lines.append("Return JSON with keys plain_english, math_formula, code_hint:")
        return "\n".join(lines)

    def _store_clauses(self, deal_id: str, clauses: list[dict[str, Any]], actor: str) -> int:
        store: DealStore = self.context(deal_id).store()
        for clause in clauses:
            store.add_governing_clause(clause)
        store.audit(
            "generate_governing_doc",
            actor=actor,
            object_type="deal",
            object_id=deal_id,
            after={"clauses": len(clauses)},
        )
        return len(clauses)
