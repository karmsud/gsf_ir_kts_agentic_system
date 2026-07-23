"""
SEPService — run Search & Extraction Profiles against a deal.

For a given profile the service selects the most relevant source chunks
(keyword relevance over the stored, page-cited chunks), asks the LLM to emit a
bounded JSON array of items, and persists each item as a ``sep_artifact`` in
``pending_review`` status with a citation — ready for human-in-the-loop
approval. Stateless + async.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from backend.abs.services.base import ABSService, ProgressFn, ServiceContext, ServiceResult
from backend.abs.services.json_utils import extract_items
from backend.abs.services.llm_client import LLMClient
from backend.abs.services.sep_profiles import CORE_PROFILES, SEPProfile, get_profile
from backend.abs.store import DealStore

_MAX_CONTEXT_CHUNKS = 14

_SEP_SYSTEM = (
    "You are a meticulous structured-finance extraction agent. You read excerpts "
    "from a governing legal document and return STRICT JSON only — a JSON array of "
    "objects with exactly the requested fields. Every object MUST include a "
    "'citation' field identifying the section and page it came from. If a value is "
    "not present, use null. Do not invent data."
)


def _citation_for(chunk: dict[str, Any], section_path: str) -> str:
    page = chunk.get("page_start")
    parts = []
    if section_path:
        parts.append(section_path)
    if page:
        parts.append(f"p.{page}")
    return " ".join(parts)


class SEPService(ABSService):
    """Run structured-artifact extraction profiles."""

    name = "sep"

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)

    def context(self, deal_id: str) -> ServiceContext:
        return ServiceContext(deal_id=deal_id, deals_root=self.deals_root)

    # ------------------------------------------------------------------
    # Run a single SEP
    # ------------------------------------------------------------------
    async def run_sep(
        self,
        deal_id: str,
        sep_name: str,
        llm: LLMClient,
        *,
        actor: str = "system",
        progress: Optional[ProgressFn] = None,
    ) -> ServiceResult:
        return await self.guard(self._run_sep(deal_id, sep_name, llm, actor, progress))

    async def _run_sep(
        self,
        deal_id: str,
        sep_name: str,
        llm: LLMClient,
        actor: str,
        progress: Optional[ProgressFn],
    ) -> dict[str, Any]:
        profile = get_profile(sep_name)
        if progress:
            progress({"stage": f"sep:{sep_name}", "status": "in-progress"})

        context_chunks = await self._to_thread(self._select_chunks, deal_id, profile)
        prompt = self._build_prompt(profile, context_chunks)
        result = await llm.complete(prompt, system=_SEP_SYSTEM, temperature=0.0, max_tokens=2000)
        items = extract_items(result.text, list_key=profile.list_key)

        stored = await self._to_thread(self._store_items, deal_id, profile, items, actor)
        if progress:
            progress({"stage": f"sep:{sep_name}", "status": "done", "items": stored})
        return {"sep_name": sep_name, "items": stored}

    # ------------------------------------------------------------------
    # Run all SEPs
    # ------------------------------------------------------------------
    async def run_all(
        self,
        deal_id: str,
        llm: LLMClient,
        *,
        actor: str = "system",
        progress: Optional[ProgressFn] = None,
    ) -> ServiceResult:
        async def _all() -> dict[str, Any]:
            summary: dict[str, int] = {}
            for profile in CORE_PROFILES:
                res = await self._run_sep(deal_id, profile.name, llm, actor, progress)
                summary[profile.name] = res["items"]
            return {"profiles": summary, "total": sum(summary.values())}

        return await self.guard(_all())

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    async def list_artifacts(self, deal_id: str, sep_name: Optional[str] = None) -> ServiceResult:
        store = self.context(deal_id).store(init=False)
        return await self.guard(self._to_thread(store.list_sep_artifacts, deal_id, sep_name))

    # ------------------------------------------------------------------
    # Human-in-the-loop approval workflow
    # ------------------------------------------------------------------
    async def approve(self, deal_id: str, artifact_id: str, *, actor: str) -> ServiceResult:
        store = self.context(deal_id).store(init=False)
        return await self.guard(self._to_thread(store.approve_sep_artifact, artifact_id, actor=actor))

    async def reject(self, deal_id: str, artifact_id: str, *, actor: str, rationale: str = "") -> ServiceResult:
        store = self.context(deal_id).store(init=False)
        return await self.guard(
            self._to_thread(store.reject_sep_artifact, artifact_id, actor=actor, rationale=rationale)
        )

    async def override(
        self, deal_id: str, artifact_id: str, *, new_value: Any, rationale: str, actor: str
    ) -> ServiceResult:
        store = self.context(deal_id).store(init=False)
        return await self.guard(
            self._to_thread(
                store.override_sep_artifact,
                artifact_id,
                new_value=new_value,
                rationale=rationale,
                actor=actor,
            )
        )

    # ------------------------------------------------------------------
    # Sync helpers
    # ------------------------------------------------------------------
    def _select_chunks(self, deal_id: str, profile: SEPProfile) -> list[dict[str, Any]]:
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
            return sum(text.count(kw) for kw in profile.keywords)

        scored = sorted(chunks, key=score, reverse=True)
        relevant = [c for c in scored if score(c) > 0][:_MAX_CONTEXT_CHUNKS]
        if not relevant:
            relevant = scored[:_MAX_CONTEXT_CHUNKS]
        # Attach citation strings.
        for c in relevant:
            c["_citation"] = _citation_for(c, section_path.get(c.get("section_id"), ""))
        return relevant

    def _build_prompt(self, profile: SEPProfile, chunks: list[dict[str, Any]]) -> str:
        ctx_lines = []
        for i, c in enumerate(chunks, 1):
            ctx_lines.append(f"[Excerpt {i} — {c.get('_citation', '')}]\n{c.get('text', '')}")
        context_block = "\n\n".join(ctx_lines) if ctx_lines else "(no source excerpts found)"
        return (
            f"TASK: {profile.instruction}\n\n"
            f"Return a JSON array. Each object MUST have these fields: {profile.field_list()}.\n"
            f"The 'citation' field must reference the excerpt's section and page.\n\n"
            f"SOURCE EXCERPTS:\n{context_block}\n\n"
            f"JSON array:"
        )

    def _store_items(
        self, deal_id: str, profile: SEPProfile, items: list[dict[str, Any]], actor: str
    ) -> int:
        store: DealStore = self.context(deal_id).store()
        count = 0
        for item in items:
            citation = str(item.get("citation") or "")
            store.add_sep_artifact({
                "deal_id": deal_id,
                "sep_name": profile.name,
                "field_path": str(item.get(profile.fields[0]) or ""),
                "value": item,
                "citation": citation,
                "confidence": float(item.get("confidence", 0.8) or 0.8),
                "status": "pending_review",
            })
            count += 1
        store.audit(
            "run_sep",
            actor=actor,
            object_type="sep",
            object_id=f"{deal_id}:{profile.name}",
            after={"items": count},
        )
        return count
