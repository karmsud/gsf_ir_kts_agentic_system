"""
ABSDispatcher — the integration gateway (one async entry point for the UI).

The VS Code extension speaks to the backend over JSON-lines IPC. Every UI action
becomes a ``{command, params}`` message that this dispatcher routes to the right
stateless service and returns as a uniform ``ServiceResult`` dict. Because all
services are stateless, a single dispatcher instance can serve any deal and any
number of concurrent requests.

Commands (``area.action``)::

    deal.create | deal.list | deal.status
    ingest.document
    definitions.build | definitions.list | definitions.top_level | definitions.tree
    sep.run | sep.run_all | sep.list | sep.approve | sep.reject | sep.override
    governing.generate | governing.list
    qa.ask | qa.explain
    model.generate | model.audit
    report.generate
    audit.list
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from backend.abs.services.base import ProgressFn, ServiceResult
from backend.abs.services.assumptions_service import AssumptionsService
from backend.abs.services.agent_service import AgentService
from backend.abs.services.command_center_service import CommandCenterService
from backend.abs.services.deal_service import DealService
from backend.abs.services.deal_setup_service import DealSetupService
from backend.abs.services.definition_service import DefinitionService
from backend.abs.services.embedding import Embedder  # noqa: F401 (re-export convenience)
from backend.abs.services.evidence_service import EvidencePackageService
from backend.abs.services.excel_bridge_service import ExcelBridgeService
from backend.abs.services.governance_service import GovernanceService
from backend.abs.services.governing_doc_service import GoverningDocService
from backend.abs.services.ingestion_service import IngestionService
from backend.abs.services.llm_client import LLMClient
from backend.abs.services.job_queue_service import JobQueueService
from backend.abs.services.model_service import ModelService
from backend.abs.services.model_run_service import ModelRunService
from backend.abs.services.pdf_extract import ExtractedDoc
from backend.abs.services.projection_service import ProjectionService
from backend.abs.services.qa_service import QAService
from backend.abs.services.regeneration_service import RegenerationService
from backend.abs.services.reporting_service import ReportingService
from backend.abs.services.retrieval_service import RetrievalService
from backend.abs.services.sep_profiles import CORE_PROFILES  # noqa: F401
from backend.abs.services.sep_service import SEPService
from backend.abs.services.source_hierarchy_service import SourceHierarchyService
from backend.abs.services.tax_service import TaxService
from backend.abs.services.sep_service import SEPService
from backend.abs.store import DealStore


class ABSDispatcher:
    """Route ``{command, params}`` UI messages to stateless services."""

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)
        self.deal = DealService(self.deals_root)
        self.ingestion = IngestionService(self.deals_root)
        self.definitions = DefinitionService(self.deals_root)
        self.sep = SEPService(self.deals_root)
        self.governing = GoverningDocService(self.deals_root)
        self.qa = QAService(self.deals_root)
        self.model = ModelService(self.deals_root)
        self.model_run = ModelRunService(self.deals_root)
        self.reporting = ReportingService(self.deals_root)
        self.retrieval = RetrievalService(self.deals_root)
        self.agents = AgentService(self.deals_root)
        self.governance = GovernanceService(self.deals_root)
        self.regeneration = RegenerationService(self.deals_root)
        self.deal_setup = DealSetupService(self.deals_root)
        self.evidence = EvidencePackageService(self.deals_root)
        self.excel = ExcelBridgeService(self.deals_root)
        self.source_hierarchy = SourceHierarchyService(self.deals_root)
        self.command_center = CommandCenterService(self.deals_root)
        self.assumptions = AssumptionsService(self.deals_root)
        self.projection = ProjectionService(self.deals_root)
        self.tax = TaxService(self.deals_root)
        self.job_queue = JobQueueService(self.deals_root)

    async def dispatch(
        self,
        command: str,
        params: Optional[dict[str, Any]] = None,
        *,
        llm: Optional[LLMClient] = None,
        progress: Optional[ProgressFn] = None,
    ) -> dict[str, Any]:
        params = params or {}
        handler = self._ROUTES.get(command)
        if handler is None:
            return ServiceResult.failure(f"Unknown command: {command}").to_dict()
        # Transparently track LLM cost per deal/command.
        if llm is not None and params.get("deal_id"):
            llm = _CostTrackingLLM(llm, self.deals_root, str(params["deal_id"]), command)
        try:
            result = await handler(self, params, llm, progress)
        except KeyError as exc:
            return ServiceResult.failure(f"Missing required param: {exc}").to_dict()
        except Exception as exc:  # noqa: BLE001 — boundary
            return ServiceResult.failure(f"{type(exc).__name__}: {exc}").to_dict()
        if isinstance(result, ServiceResult):
            return result.to_dict()
        return result

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    async def _deal_create(self, p, llm, progress):
        return await self.deal.create_deal(
            p["deal_id"], deal_name=p.get("deal_name", ""), issuer=p.get("issuer", ""),
            series=p.get("series", ""), actor=p.get("actor", "user"),
        )

    async def _deal_list(self, p, llm, progress):
        return await self.deal.list_deals()

    async def _deal_status(self, p, llm, progress):
        return await self.deal.get_status(p["deal_id"])

    async def _deal_portfolio(self, p, llm, progress):
        return await self.deal.portfolio()

    async def _ingest_document(self, p, llm, progress):
        extracted = None
        if p.get("pages") is not None:
            from backend.abs.services.pdf_extract import extracted_from_pages
            extracted = extracted_from_pages(list(p["pages"]))
        pdf_path = Path(p["pdf_path"]) if p.get("pdf_path") else None
        result = await self.ingestion.ingest_document(
            p["deal_id"], pdf_path=pdf_path, extracted=extracted,
            doc_type=p.get("doc_type", "PSA"), title=p.get("title", ""),
            actor=p.get("actor", "user"), progress=progress,
        )
        # Auto-index for hybrid retrieval (dense + sparse) so Q&A works immediately.
        if result.ok:
            await self.retrieval.index(p["deal_id"], progress=progress)
        return result

    async def _retrieval_index(self, p, llm, progress):
        return await self.retrieval.index(
            p["deal_id"], llm=llm, enhance=bool(p.get("enhance", False)),
            actor=p.get("actor", "user"), progress=progress,
        )

    async def _retrieval_search(self, p, llm, progress):
        return await self.retrieval.search(p["deal_id"], p["query"], top_k=int(p.get("top_k", 8)))

    async def _definitions_build(self, p, llm, progress):
        return await self.definitions.build_definitions(
            p["deal_id"], doc_id=p.get("doc_id"), text=p.get("text"), llm=llm,
            resolve=bool(p.get("resolve", True)) and llm is not None,
            actor=p.get("actor", "user"), progress=progress,
        )

    async def _definitions_list(self, p, llm, progress):
        return await self.definitions.list_definitions(p["deal_id"])

    async def _definitions_top_level(self, p, llm, progress):
        return await self.definitions.list_top_level(p["deal_id"])

    async def _definitions_tree(self, p, llm, progress):
        return await self.definitions.get_resolution_tree(p["deal_id"], p["term_id"])

    async def _sep_run(self, p, llm, progress):
        return await self.sep.run_sep(p["deal_id"], p["sep_name"], self._require_llm(llm),
                                      actor=p.get("actor", "user"), progress=progress)

    async def _sep_run_all(self, p, llm, progress):
        return await self.sep.run_all(p["deal_id"], self._require_llm(llm),
                                      actor=p.get("actor", "user"), progress=progress)

    async def _sep_list(self, p, llm, progress):
        return await self.sep.list_artifacts(p["deal_id"], p.get("sep_name"))

    async def _sep_approve(self, p, llm, progress):
        return await self.sep.approve(p["deal_id"], p["artifact_id"], actor=p.get("actor", "user"))

    async def _sep_reject(self, p, llm, progress):
        return await self.sep.reject(p["deal_id"], p["artifact_id"], actor=p.get("actor", "user"),
                                     rationale=p.get("rationale", ""))

    async def _sep_override(self, p, llm, progress):
        return await self.sep.override(p["deal_id"], p["artifact_id"], new_value=p["new_value"],
                                       rationale=p["rationale"], actor=p.get("actor", "user"))

    async def _governing_generate(self, p, llm, progress):
        return await self.governing.generate(p["deal_id"], self._require_llm(llm),
                                             actor=p.get("actor", "user"), progress=progress)

    async def _governing_list(self, p, llm, progress):
        return await self.governing.list_clauses(p["deal_id"])

    async def _qa_ask(self, p, llm, progress):
        return await self.qa.ask(p["deal_id"], p["question"], self._require_llm(llm),
                                 top_k=int(p.get("top_k", 8)))

    async def _qa_explain(self, p, llm, progress):
        return await self.qa.explain(p["deal_id"], p["target"], self._require_llm(llm),
                                     top_k=int(p.get("top_k", 6)))

    async def _model_generate(self, p, llm, progress):
        return await self.model.generate(p["deal_id"], self._require_llm(llm),
                                         actor=p.get("actor", "user"), progress=progress)

    async def _model_audit(self, p, llm, progress):
        return await self.model.audit(p["deal_id"], self._require_llm(llm),
                                      actor=p.get("actor", "user"), progress=progress)

    async def _model_run(self, p, llm, progress):
        return await self.model_run.run(
            p["deal_id"], monthly_inputs=p.get("monthly_inputs"), csv_path=p.get("csv_path"),
            classes_setup=p.get("classes_setup"), waterfall_rules=p.get("waterfall_rules"),
            run_date=p.get("run_date", ""), scenario=p.get("scenario", "base"),
            actor=p.get("actor", "user"), progress=progress,
        )

    async def _model_readiness(self, p, llm, progress):
        return await self.model_run.check_readiness(
            monthly_inputs=p.get("monthly_inputs"), csv_path=p.get("csv_path")
        )

    async def _model_spec(self, p, llm, progress):
        return await self.model.generate_spec(p["deal_id"], self._require_llm(llm), actor=p.get("actor", "user"), progress=progress)

    async def _setup_generate(self, p, llm, progress):
        return await self.deal_setup.generate(p["deal_id"], actor=p.get("actor", "user"), progress=progress)

    async def _evidence_generate(self, p, llm, progress):
        return await self.evidence.generate(p["deal_id"], actor=p.get("actor", "user"), progress=progress)

    async def _excel_generate(self, p, llm, progress):
        return await self.excel.generate(p["deal_id"], actor=p.get("actor", "user"), progress=progress)

    async def _hierarchy_detect(self, p, llm, progress):
        return await self.source_hierarchy.detect_conflicts(p["deal_id"])

    async def _hierarchy_get(self, p, llm, progress):
        return await self.source_hierarchy.get_hierarchy(p["deal_id"])

    async def _hierarchy_confirm(self, p, llm, progress):
        return await self.source_hierarchy.confirm_operative(
            p["deal_id"], p["doc_id"], logic_area=p.get("logic_area", ""), actor=p.get("actor", "reviewer"))

    async def _command_center(self, p, llm, progress):
        return await self.command_center.queue(actor=p.get("actor", "user"))

    async def _assumptions_seed(self, p, llm, progress):
        return await self.assumptions.seed_defaults(p["deal_id"], actor=p.get("actor", "system"))

    async def _assumptions_add(self, p, llm, progress):
        return await self.assumptions.add(p["deal_id"], scenario_name=p["scenario_name"],
                                           assumption_type=p["assumption_type"], value=p["value"],
                                           actor=p.get("actor", "user"))

    async def _assumptions_list(self, p, llm, progress):
        return await self.assumptions.list(p["deal_id"], p.get("scenario_name"))

    async def _assumptions_scenarios(self, p, llm, progress):
        return await self.assumptions.list_scenarios(p["deal_id"])

    async def _projection_run(self, p, llm, progress):
        return await self.projection.run(p["deal_id"], scenarios=p.get("scenarios"),
                                          months=int(p.get("months", 12)), actor=p.get("actor", "system"), progress=progress)

    async def _projection_results(self, p, llm, progress):
        return await self.projection.get_results(p["deal_id"], p.get("scenario_name"))

    async def _projection_baseline_save(self, p, llm, progress):
        return await self.projection.save_baseline(p["deal_id"], p.get("scenario_name", "base"), actor=p.get("actor", "user"))

    async def _projection_baseline_compare(self, p, llm, progress):
        return await self.projection.compare_baseline(p["deal_id"], p.get("scenario_name", "base"))

    async def _tax_generate(self, p, llm, progress):
        return await self.tax.generate(p["deal_id"], scenario_name=p.get("scenario_name", "base"),
                                        discount_rate=float(p.get("discount_rate", 0.05)),
                                        actor=p.get("actor", "system"), progress=progress)

    async def _tax_results(self, p, llm, progress):
        return await self.tax.get_results(p["deal_id"])

    async def _agent_results(self, p, llm, progress):
        return await self.agents.get_results(p["deal_id"], p.get("agent_name"))

    async def _run_details(self, p, llm, progress):
        import asyncio
        def _work():
            store = DealStore.for_deal_dir(self.deals_root / p["deal_id"], init=False)
            run_id = p.get("run_id")
            if not run_id:
                runs = store.list_monthly_runs(p["deal_id"])
                run_id = runs[0]["run_id"] if runs else None
            return store.get_run_details(run_id) if run_id else []
        data = await asyncio.to_thread(_work)
        return ServiceResult.success(data)

    async def _jobs_enqueue(self, p, llm, progress):
        return await self.job_queue.enqueue(p["command"], p.get("params", {}), actor=p.get("actor", "user"))

    async def _jobs_list(self, p, llm, progress):
        return await self.job_queue.list_jobs(p.get("deal_id"), status=p.get("status"))

    async def _jobs_get(self, p, llm, progress):
        return await self.job_queue.get_job(p["job_id"], p.get("deal_id"))

    async def _report_generate(self, p, llm, progress):
        return await self.reporting.generate_statement(
            p["deal_id"], run_id=p.get("run_id"), results=p.get("results"),
            distribution_date=p.get("distribution_date", ""), deal_name=p.get("deal_name", ""),
            series=p.get("series", ""), actor=p.get("actor", "user"), progress=progress,
        )

    async def _agent_list(self, p, llm, progress):
        return ServiceResult.success(AgentService.list_agents())

    async def _agent_run(self, p, llm, progress):
        return await self.agents.run_agent(
            p["deal_id"], p["agent_name"], task=p.get("task"), llm=llm,
            materialize=bool(p.get("materialize", True)), actor=p.get("actor", "user"),
            progress=progress,
        )

    async def _source_get(self, p, llm, progress):
        import asyncio

        def _work():
            store = DealStore.for_deal_dir(self.deals_root / p["deal_id"], init=False)
            return store.get_source_context(chunk_id=p.get("chunk_id"), section_id=p.get("section_id"))
        data = await asyncio.to_thread(_work)
        if data is None:
            return ServiceResult.failure("Source not found")
        return ServiceResult.success(data)

    async def _govern_corrections(self, p, llm, progress):
        return await self.governance.list_corrections(p["deal_id"])

    async def _govern_log_correction(self, p, llm, progress):
        return await self.governance.log_correction(
            p["deal_id"], object_type=p.get("object_type", ""), object_id=p.get("object_id", ""),
            lifecycle_stage=p.get("lifecycle_stage", ""), original_value=p.get("original_value"),
            corrected_value=p.get("corrected_value"), root_cause=p.get("root_cause", ""),
            severity=p.get("severity", "medium"), actor=p.get("actor", "user"))

    async def _govern_cost(self, p, llm, progress):
        return await self.governance.cost_summary(p["deal_id"])

    async def _govern_grant(self, p, llm, progress):
        return await self.governance.grant(p["deal_id"], actor=p["actor"], role=p["role"],
                                           by=p.get("by", "admin"))

    async def _govern_check(self, p, llm, progress):
        return await self.governance.check(p["deal_id"], actor=p["actor"], permission=p["permission"])

    async def _regenerate(self, p, llm, progress):
        return await self.regeneration.regenerate(
            p["deal_id"], p["target"], llm=llm, reason=p.get("reason", ""),
            actor=p.get("actor", "user"), progress=progress)

    async def _audit_list(self, p, llm, progress):
        def _work():
            store = DealStore.for_deal_dir(self.deals_root / p["deal_id"], init=False)
            return store.list_audit(object_type=p.get("object_type", ""),
                                    object_id=p.get("object_id", ""), limit=int(p.get("limit", 500)))
        import asyncio
        data = await asyncio.to_thread(_work)
        return ServiceResult.success(data)

    @staticmethod
    def _require_llm(llm: Optional[LLMClient]) -> LLMClient:
        if llm is None:
            raise ValueError("This command requires an LLM connection (GitHub Copilot).")
        return llm

    # Route table (built after methods are defined).
    _ROUTES: dict[str, Callable[..., Awaitable[Any]]] = {}


ABSDispatcher._ROUTES = {
    "deal.create": ABSDispatcher._deal_create,
    "deal.list": ABSDispatcher._deal_list,
    "deal.status": ABSDispatcher._deal_status,
    "deal.portfolio": ABSDispatcher._deal_portfolio,
    "ingest.document": ABSDispatcher._ingest_document,
    "retrieval.index": ABSDispatcher._retrieval_index,
    "retrieval.search": ABSDispatcher._retrieval_search,
    "definitions.build": ABSDispatcher._definitions_build,
    "definitions.list": ABSDispatcher._definitions_list,
    "definitions.top_level": ABSDispatcher._definitions_top_level,
    "definitions.tree": ABSDispatcher._definitions_tree,
    "sep.run": ABSDispatcher._sep_run,
    "sep.run_all": ABSDispatcher._sep_run_all,
    "sep.list": ABSDispatcher._sep_list,
    "sep.approve": ABSDispatcher._sep_approve,
    "sep.reject": ABSDispatcher._sep_reject,
    "sep.override": ABSDispatcher._sep_override,
    "governing.generate": ABSDispatcher._governing_generate,
    "governing.list": ABSDispatcher._governing_list,
    "qa.ask": ABSDispatcher._qa_ask,
    "qa.explain": ABSDispatcher._qa_explain,
    "model.generate": ABSDispatcher._model_generate,
    "model.audit": ABSDispatcher._model_audit,
    "model.run": ABSDispatcher._model_run,
    "model.readiness": ABSDispatcher._model_readiness,
    "model.spec": ABSDispatcher._model_spec,
    "setup.generate": ABSDispatcher._setup_generate,
    "evidence.generate": ABSDispatcher._evidence_generate,
    "excel.generate": ABSDispatcher._excel_generate,
    "hierarchy.detect": ABSDispatcher._hierarchy_detect,
    "hierarchy.get": ABSDispatcher._hierarchy_get,
    "hierarchy.confirm": ABSDispatcher._hierarchy_confirm,
    "command_center.queue": ABSDispatcher._command_center,
    "assumptions.seed": ABSDispatcher._assumptions_seed,
    "assumptions.add": ABSDispatcher._assumptions_add,
    "assumptions.list": ABSDispatcher._assumptions_list,
    "assumptions.scenarios": ABSDispatcher._assumptions_scenarios,
    "projection.run": ABSDispatcher._projection_run,
    "projection.results": ABSDispatcher._projection_results,
    "projection.baseline.save": ABSDispatcher._projection_baseline_save,
    "projection.baseline.compare": ABSDispatcher._projection_baseline_compare,
    "tax.generate": ABSDispatcher._tax_generate,
    "tax.results": ABSDispatcher._tax_results,
    "agent.results": ABSDispatcher._agent_results,
    "run.details": ABSDispatcher._run_details,
    "jobs.enqueue": ABSDispatcher._jobs_enqueue,
    "jobs.list": ABSDispatcher._jobs_list,
    "jobs.get": ABSDispatcher._jobs_get,
    "report.generate": ABSDispatcher._report_generate,
    "source.get": ABSDispatcher._source_get,
    "governance.corrections": ABSDispatcher._govern_corrections,
    "governance.log_correction": ABSDispatcher._govern_log_correction,
    "governance.cost": ABSDispatcher._govern_cost,
    "governance.grant": ABSDispatcher._govern_grant,
    "governance.check": ABSDispatcher._govern_check,
    "regenerate": ABSDispatcher._regenerate,
    "agent.list": ABSDispatcher._agent_list,
    "agent.run": ABSDispatcher._agent_run,
    "audit.list": ABSDispatcher._audit_list,
}


class _CostTrackingLLM:
    """Wrap an LLMClient to record token usage per deal/command (AI cost mgmt)."""

    def __init__(self, inner: LLMClient, deals_root: Path, deal_id: str, command: str) -> None:
        self._inner = inner
        self._deals_root = deals_root
        self._deal_id = deal_id
        self._command = command

    async def complete(self, prompt, *, system=None, temperature=0.0, max_tokens=2048):
        result = await self._inner.complete(prompt, system=system, temperature=temperature, max_tokens=max_tokens)
        try:
            import asyncio

            def _record():
                store = DealStore.for_deal_dir(self._deals_root / self._deal_id, init=False)
                store.record_llm_cost(
                    deal_id=self._deal_id, command=self._command, model=result.model,
                    input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                )
            await asyncio.to_thread(_record)
        except Exception:  # noqa: BLE001 - cost tracking must never break a command
            pass
        return result
