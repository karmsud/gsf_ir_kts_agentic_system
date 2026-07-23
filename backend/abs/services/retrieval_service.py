"""
RetrievalService — hybrid dense + sparse + keyword retrieval over the store.

``index`` embeds every chunk (BGE in production, hash fallback otherwise),
optionally generates keyword-rich *enhancement markdown* per chunk via the LLM,
and persists the dense vectors. ``search`` fuses three signals with Reciprocal
Rank Fusion:

* **Dense** — cosine similarity over the stored embeddings.
* **Sparse** — Okapi BM25 (the existing :class:`BM25Retriever`).
* **Keyword** — token-overlap, a cheap robustness backstop.

Every hit carries a section/page citation so downstream answers stay traceable.
Stateless + async.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from backend.abs.services.base import ABSService, ProgressFn, ServiceContext, ServiceResult
from backend.abs.services.embedding import Embedder, cosine, get_default_embedder
from backend.abs.services.llm_client import LLMClient
from backend.abs.store import DealStore

_RRF_K = 60
_ENHANCE_SYSTEM = (
    "You expand a passage from a structured-finance document into a compact, keyword-rich "
    "summary for search indexing. Preserve every defined term, section heading, party, account, "
    "and number. Return only the keywords/short phrases, comma-separated. No prose."
)


def _citation(row: dict[str, Any]) -> str:
    sp = row.get("section_path") or ""
    page = row.get("page_start")
    return (f"{sp} p.{page}" if page else sp).strip()


def _keyword_tokens(text: str) -> set[str]:
    from backend.abs.services.embedding import _tokens  # reuse tokenizer

    return set(_tokens(text))


class RetrievalService(ABSService):
    """Index and hybrid-search a deal's chunks."""

    name = "retrieval"

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)

    def context(self, deal_id: str) -> ServiceContext:
        return ServiceContext(deal_id=deal_id, deals_root=self.deals_root)

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------
    async def index(
        self,
        deal_id: str,
        *,
        embedder: Optional[Embedder] = None,
        llm: Optional[LLMClient] = None,
        enhance: bool = False,
        actor: str = "system",
        progress: Optional[ProgressFn] = None,
    ) -> ServiceResult:
        embedder = embedder or get_default_embedder()
        return await self.guard(self._index(deal_id, embedder, llm, enhance, actor, progress))

    async def _index(
        self,
        deal_id: str,
        embedder: Embedder,
        llm: Optional[LLMClient],
        enhance: bool,
        actor: str,
        progress: Optional[ProgressFn],
    ) -> dict[str, Any]:
        store = self.context(deal_id).store(init=False)
        chunks = await self._to_thread(store.list_chunks_for_deal, deal_id)
        if progress:
            progress({"stage": "index", "status": "in-progress", "chunks": len(chunks)})

        # Optional LLM enhancement markdown (keyword enrichment).
        enhanced = 0
        if enhance and llm is not None:
            for c in chunks:
                result = await llm.complete(c["text"][:1500], system=_ENHANCE_SYSTEM, temperature=0.0, max_tokens=200)
                md = result.text.strip()
                await self._to_thread(store.set_chunk_enhancement, c["chunk_id"], md)
                c["enhancement_md"] = md
                enhanced += 1

        # Embed (use enhancement + text so keyword signal informs the vector).
        texts = [((c.get("enhancement_md") or "") + "\n" + (c.get("text") or "")).strip() for c in chunks]
        if texts:
            # Build a thread-safe progress callback: embed_documents runs in a
            # worker thread, but progress() uses asyncio.ensure_future which must
            # execute on the event-loop thread — use call_soon_threadsafe.
            _loop = asyncio.get_running_loop() if progress else None
            def _embed_cb(done: int, total: int) -> None:
                pct = done * 100 // total
                _loop.call_soon_threadsafe(
                    progress,
                    {"stage": "embed", "status": "in-progress", "done": done, "total": total, "pct": pct},
                )
            def _call_embed() -> list:
                try:
                    return embedder.embed_documents(texts, on_progress=_embed_cb if progress else None)
                except TypeError:
                    return embedder.embed_documents(texts)  # embedder doesn't support on_progress
            vectors = await self._to_thread(_call_embed)
        else:
            vectors = []
        pairs = [(chunks[i]["chunk_id"], vectors[i]) for i in range(len(vectors))]
        stored = await self._to_thread(store.set_chunk_vectors, deal_id, embedder.provider_id, pairs)

        await self._to_thread(
            store.audit, "index_deal", actor=actor, object_type="deal", object_id=deal_id,
            after={"vectors": stored, "enhanced": enhanced, "provider": embedder.provider_id},
        )
        if progress:
            progress({"stage": "index", "status": "done", "vectors": stored})
        return {"vectors": stored, "enhanced": enhanced, "provider": embedder.provider_id}

    # ------------------------------------------------------------------
    # Search (hybrid RRF)
    # ------------------------------------------------------------------
    async def search(
        self,
        deal_id: str,
        query: str,
        *,
        embedder: Optional[Embedder] = None,
        top_k: int = 8,
    ) -> ServiceResult:
        embedder = embedder or get_default_embedder()
        return await self.guard(self._search(deal_id, query, embedder, top_k))

    async def _search(
        self, deal_id: str, query: str, embedder: Embedder, top_k: int
    ) -> list[dict[str, Any]]:
        store = self.context(deal_id).store(init=False)
        vec_rows = await self._to_thread(store.get_chunk_vectors, deal_id)
        # Fall back to raw chunks (sparse/keyword only) if not yet embedded.
        if not vec_rows:
            vec_rows = await self._to_thread(store.list_chunks_for_deal, deal_id)
        if not vec_rows:
            return []

        by_id = {r["chunk_id"]: r for r in vec_rows}

        # 1. Dense (cosine).
        dense_ranked: list[str] = []
        if vec_rows and vec_rows[0].get("vector"):
            qv = await self._to_thread(embedder.embed_query, query)
            scored = [(r["chunk_id"], cosine(qv, r.get("vector") or [])) for r in vec_rows]
            scored.sort(key=lambda x: x[1], reverse=True)
            dense_ranked = [cid for cid, s in scored if s > 0]

        # 2. Sparse (BM25).
        sparse_ranked = await self._to_thread(self._bm25_rank, deal_id, query, vec_rows)

        # 3. Keyword overlap.
        q_tokens = _keyword_tokens(query)
        kw_scored = [
            (r["chunk_id"], len(q_tokens & _keyword_tokens(r.get("text") or "")))
            for r in vec_rows
        ]
        kw_scored.sort(key=lambda x: x[1], reverse=True)
        keyword_ranked = [cid for cid, s in kw_scored if s > 0]

        # RRF fusion.
        fused: dict[str, float] = {}
        signals: dict[str, dict[str, int]] = {}
        for name, ranked in (("dense", dense_ranked), ("sparse", sparse_ranked), ("keyword", keyword_ranked)):
            for rank, cid in enumerate(ranked):
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (_RRF_K + rank + 1)
                signals.setdefault(cid, {})[name] = rank + 1

        if not fused:  # nothing matched any signal — return first chunks
            order = [r["chunk_id"] for r in vec_rows[:top_k]]
        else:
            order = [cid for cid, _ in sorted(fused.items(), key=lambda x: x[1], reverse=True)]

        hits: list[dict[str, Any]] = []
        for cid in order[:top_k]:
            r = by_id.get(cid)
            if not r:
                continue
            hits.append({
                "chunk_id": cid,
                "text": r.get("text", ""),
                "section_id": r.get("section_id"),
                "page_start": r.get("page_start"),
                "citation": _citation(r),
                "score": round(fused.get(cid, 0.0), 6),
                "signals": signals.get(cid, {}),
            })
        return hits

    def _bm25_rank(self, deal_id: str, query: str, rows: list[dict[str, Any]]) -> list[str]:
        try:
            from backend.retrieval.bm25_retriever import BM25Retriever

            persist = str(self.context(deal_id).deal_path / ".abs")
            bm25 = BM25Retriever(persist)
            docs = [
                {"id": r["chunk_id"],
                 "content": ((r.get("enhancement_md") or "") + " " + (r.get("text") or "")).strip(),
                 "metadata": {}}
                for r in rows
            ]
            bm25.build_index(docs)
            return [hit["id"] for hit in bm25.search(query, top_k=len(docs))]
        except Exception:  # noqa: BLE001 - sparse is optional
            return []
