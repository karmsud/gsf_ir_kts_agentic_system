"""
AgentService — bridge the existing ABS agents into the new service/UI layer.

The dormant agents (comparison, amendment, stress, regression, projection,
lifecycle) were written against the file-based deal layout (``deal_setup.csv``,
``classes_setup.csv``, ``extractions/*.json``) and a *synchronous* ``llm_callable``.
This service:

* **Materialises** the inputs those agents expect from the SQLite ``deal_store``
  (so they operate on the same governed artifacts the rest of the system uses).
* **Bridges** the async GHCP :class:`LLMClient` to the synchronous callable the
  agents expect, via ``run_coroutine_threadsafe`` onto the running loop.
* Constructs the agent (config + deal scope + tool registry) and runs it.

Stateless + async.
"""

from __future__ import annotations

import asyncio
import csv as _csv
import json
from pathlib import Path
from typing import Any, Callable, Optional

from backend.abs.services.base import ABSService, ProgressFn, ServiceContext, ServiceResult
from backend.abs.services.json_utils import parse_json_lenient
from backend.abs.services.llm_client import LLMClient
from backend.abs.store import DealStore

# agent_name → (module path, class name)
AGENT_REGISTRY: dict[str, tuple[str, str]] = {
    "comparison": ("backend.abs.agents.document_comparison_agent", "DocumentComparisonAgent"),
    "amendment": ("backend.abs.agents.deal_amendment_agent", "DealAmendmentAgent"),
    "stress": ("backend.abs.agents.stress_testing_agent", "StressTestingAgent"),
    "regression": ("backend.abs.agents.regression_testing_agent", "RegressionTestingAgent"),
    "projection": ("backend.abs.agents.cashflow_projection_agent", "CashflowProjectionAgent"),
    "lifecycle": ("backend.abs.agents.deal_lifecycle_agent", "DealLifecycleAgent"),
}


def _parse_rate(value: Any) -> float:
    from backend.abs.services.model_run_service import _parse_rate as pr

    return pr(value)


def _parse_amount(value: Any) -> float:
    from backend.abs.services.model_run_service import _parse_amount as pa

    return pa(value)


class AgentService(ABSService):
    """Run the existing ABS agents against the SQLite-backed deal."""

    name = "agent"

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)

    def context(self, deal_id: str) -> ServiceContext:
        return ServiceContext(deal_id=deal_id, deals_root=self.deals_root)

    @staticmethod
    def list_agents() -> list[dict[str, str]]:
        labels = {
            "comparison": "Document Comparison", "amendment": "Deal Amendment",
            "stress": "Stress Testing", "regression": "Regression Testing",
            "projection": "Cash Flow Projection", "lifecycle": "Lifecycle Monitor",
        }
        return [{"name": n, "label": labels.get(n, n)} for n in AGENT_REGISTRY]

    async def get_results(self, deal_id: str, agent_name: Optional[str] = None) -> ServiceResult:
        import json as _json
        def _work() -> list[dict]:
            store = self.context(deal_id).store(init=False)
            results = store.list_agent_results(deal_id, agent_name)
            for r in results:
                try:
                    r["result_parsed"] = _json.loads(r.get("result_json") or "{}")
                except Exception:
                    pass
            return results
        return await self.guard(self._to_thread(_work))

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    async def run_agent(
        self,
        deal_id: str,
        agent_name: str,
        *,
        task: Optional[dict[str, Any]] = None,
        llm: Optional[LLMClient] = None,
        materialize: bool = True,
        actor: str = "system",
        progress: Optional[ProgressFn] = None,
    ) -> ServiceResult:
        if agent_name not in AGENT_REGISTRY:
            return ServiceResult.failure(
                f"Unknown agent: {agent_name!r}. Known: {list(AGENT_REGISTRY)}"
            )
        loop = asyncio.get_running_loop()

        sync_llm: Optional[Callable[..., str]] = None
        if llm is not None:
            def sync_llm(prompt: str, system_prompt: Optional[str] = None,
                         temperature: float = 0.0, max_tokens: int = 2048, **_: Any) -> str:
                fut = asyncio.run_coroutine_threadsafe(
                    llm.complete(prompt, system=system_prompt, temperature=temperature, max_tokens=max_tokens),
                    loop,
                )
                return fut.result(timeout=180).text

        if progress:
            progress({"stage": f"agent:{agent_name}", "status": "in-progress"})
        result = await self.guard(
            self._to_thread(self._run_sync, deal_id, agent_name, task or {}, sync_llm, materialize, actor)
        )
        if progress:
            progress({"stage": f"agent:{agent_name}", "status": "done"})
        return result

    # ------------------------------------------------------------------
    # Sync execution (off-thread)
    # ------------------------------------------------------------------
    def _run_sync(
        self, deal_id: str, agent_name: str, task: dict[str, Any],
        sync_llm: Optional[Callable[..., str]], materialize: bool, actor: str,
    ) -> dict[str, Any]:
        import importlib

        from backend.agents.agent_tools import ToolRegistry
        from config import KTSConfig

        ctx = self.context(deal_id)
        scope = ctx.scope()
        store = ctx.store(init=False)

        if materialize:
            self._materialize(store, deal_id, scope.deal_path)

        module_path, class_name = AGENT_REGISTRY[agent_name]
        agent_cls = getattr(importlib.import_module(module_path), class_name)
        agent = agent_cls(
            KTSConfig(),
            deal_scope=scope,
            tool_registry=ToolRegistry(),
            llm_callable=sync_llm,
        )
        raw = agent._run(task)

        # Persist result so the WebView can retrieve it later
        store.add_agent_result(deal_id, agent_name, task, raw)
        store.audit("run_agent", actor=actor, object_type="agent",
                    object_id=f"{deal_id}:{agent_name}", after={"ok": True})
        return {"agent": agent_name, "result": raw}

    # ------------------------------------------------------------------
    # Materialise store artifacts → file layout the agents expect
    # ------------------------------------------------------------------
    def _materialize(self, store: DealStore, deal_id: str, deal_path: Path) -> None:
        classes = self._classes(store, deal_id)
        # deal_setup.csv (field,value)
        total_balance = sum(c["original_balance"] for c in classes) or 0.0
        deal_setup = {
            "deal_name": deal_id, "issuer": "", "series": "", "shelf": "",
            "closing_date": "", "initial_pool_balance": total_balance,
            "servicer_fee_rate": 0.005, "trustee_fee_rate": 0.0,
        }
        with open(deal_path / "deal_setup.csv", "w", newline="", encoding="utf-8") as f:
            w = _csv.writer(f)
            w.writerow(["field", "value"])
            for k, v in deal_setup.items():
                w.writerow([k, v])

        # classes_setup.csv
        with open(deal_path / "classes_setup.csv", "w", newline="", encoding="utf-8") as f:
            w = _csv.writer(f)
            w.writerow(["class_name", "class_type", "original_balance", "certificate_rate", "certificate_margin"])
            for c in classes:
                w.writerow([c["class_name"], c.get("class_type", "senior"),
                            c["original_balance"], c["coupon_rate"], 0.0])

        # extractions/*.json
        ext_dir = deal_path / "extractions"
        ext_dir.mkdir(parents=True, exist_ok=True)
        waterfall = self._waterfall(store, deal_id, classes)
        (ext_dir / "waterfall_rules.json").write_text(json.dumps(waterfall, indent=2), encoding="utf-8")
        (ext_dir / "triggers.json").write_text(json.dumps([], indent=2), encoding="utf-8")

    def _classes(self, store: DealStore, deal_id: str) -> list[dict[str, Any]]:
        classes: list[dict[str, Any]] = []
        for art in store.list_sep_artifacts(deal_id, "certificates"):
            v = parse_json_lenient(art.get("value") or "") or {}
            if not isinstance(v, dict):
                continue
            name = v.get("class_name") or v.get("class")
            if not name:
                continue
            classes.append({
                "class_name": str(name),
                "class_type": str(v.get("seniority", "senior")),
                "original_balance": _parse_amount(v.get("original_balance")),
                "coupon_rate": _parse_rate(v.get("accrual_formula", v.get("certificate_rate"))),
            })
        return classes

    def _waterfall(self, store: DealStore, deal_id: str, classes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rules: list[dict[str, Any]] = []
        for c in classes:
            rules.append({"step": f"int_{c['class_name']}", "target": c["class_name"], "amount_type": "interest"})
        for c in classes:
            rules.append({"step": f"prin_{c['class_name']}", "target": c["class_name"], "amount_type": "principal"})
        return rules
