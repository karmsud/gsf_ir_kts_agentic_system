"""
ModelService — generate and audit the Python payment (waterfall) model.

``generate`` compiles the reviewed governing-document clauses + approved SEP
artifacts (certificates, fees, accounts, waterfall) into a ``WaterfallModel``
Python module, recording a formula→citation map. ``audit`` runs an *independent*
check that every formula/constant traces to a source (separation of concerns,
mirroring the two-analyst control). Stateless + async.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from backend.abs.services.base import ABSService, ProgressFn, ServiceContext, ServiceResult
from backend.abs.services.json_utils import parse_json_lenient
from backend.abs.services.llm_client import LLMClient
from backend.abs.store import DealStore

_GEN_SYSTEM = (
    "You are a senior structured-finance model engineer. Generate a single, self-contained "
    "Python module defining `class WaterfallModel` with a `run_month(self, inputs: dict) -> dict` "
    "method that returns class-level interest, principal, and ending balances. Every constant and "
    "formula MUST have an inline comment citing its source section/page. Return ONLY Python code."
)
_AUDIT_SYSTEM = (
    "You are an independent model auditor. Given a payment model and the governing clauses it was "
    "built from, verify that every formula and constant has a cited source and matches the legal "
    "text. Return STRICT JSON: {\"checks\": [{\"item\": str, \"pass\": bool, \"source\": str, "
    "\"note\": str}], \"verdict\": \"pass\"|\"fail\"}."
)


_SPEC_SYSTEM = (
    "You are a senior structured-finance model architect. Given approved deal artifacts, "
    "produce a human-readable MODEL SPECIFICATION — a concise summary of: waterfall steps in order, "
    "interest/principal formulas per class, fee deductions, trigger tests, key constants, "
    "and any assumptions made. This spec will be reviewed by a human before code generation. "
    "Return plain text (not code). Use numbered sections. "
    "IMPORTANT: Every formula must cite its source section/page."
)

_MAX_SELF_HEAL_ITERS = 3
_TOLERANCE = 0.01  # dollar tolerance for self-validation

_SELF_HEAL_SYSTEM = (
    "You are fixing a Python payment model. The auditor found issues. "
    "Correct ONLY the identified problems. Return ONLY the corrected Python code."
)


class ModelService(ABSService):
    """Generate + audit the deal's Python payment model."""

    name = "model"

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)

    def context(self, deal_id: str) -> ServiceContext:
        return ServiceContext(deal_id=deal_id, deals_root=self.deals_root)

    # ------------------------------------------------------------------
    # Model specification (human-reviewable intermediate)
    # ------------------------------------------------------------------
    async def generate_spec(
        self,
        deal_id: str,
        llm: LLMClient,
        *,
        actor: str = "system",
        progress: Optional[ProgressFn] = None,
    ) -> ServiceResult:
        return await self.guard(self._generate_spec(deal_id, llm, actor, progress))

    async def _generate_spec(self, deal_id: str, llm: LLMClient, actor: str, progress: Optional[ProgressFn]) -> dict[str, Any]:
        contract = await self._to_thread(self._build_contract, deal_id)
        if progress:
            progress({"stage": "model:spec", "status": "in-progress"})
        prompt = self._gen_prompt(contract)
        result = await llm.complete(prompt, system=_SPEC_SYSTEM, temperature=0.0, max_tokens=2000)
        spec_text = result.text.strip()
        spec_path = self.context(deal_id).scope().deal_path / "artifacts" / "model_spec.txt"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(spec_text, encoding="utf-8")
        if progress:
            progress({"stage": "model:spec", "status": "done"})
        return {"spec": spec_text, "spec_path": str(spec_path)}

    # ------------------------------------------------------------------
    # Generate (with self-heal loop, up to 3 iterations, $0.01 tolerance)
    # ------------------------------------------------------------------
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
        contract = await self._to_thread(self._build_contract, deal_id)
        if progress:
            progress({"stage": "model:generate", "status": "in-progress"})
        prompt = self._gen_prompt(contract)
        result = await llm.complete(prompt, system=_GEN_SYSTEM, temperature=0.0, max_tokens=4000)
        source = self._strip_code_fence(result.text)

        # Self-heal loop: run audit, fix issues, retry up to 3 times.
        healed_iters = 0
        for i in range(_MAX_SELF_HEAL_ITERS):
            clauses = contract.get("governing_clauses") or []
            audit_prompt = self._audit_prompt(source, clauses)
            audit_result = await llm.complete(audit_prompt, system=_AUDIT_SYSTEM, temperature=0.0, max_tokens=1500)
            from backend.abs.services.json_utils import parse_json_lenient
            audit_data = parse_json_lenient(audit_result.text) or {}
            verdict = audit_data.get("verdict", "fail") if isinstance(audit_data, dict) else "fail"
            if verdict == "pass":
                break
            # Collect failing items and ask LLM to fix them.
            failing = [c for c in (audit_data.get("checks", []) if isinstance(audit_data, dict) else []) if not c.get("pass")]
            if not failing:
                break
            heal_prompt = (
                f"ORIGINAL CODE:\n{source}\n\nAUDIT ISSUES:\n"
                + "\n".join(f"- {c.get('item')}: {c.get('note')}" for c in failing[:10])
                + "\n\nFixed code:"
            )
            fix = await llm.complete(heal_prompt, system=_SELF_HEAL_SYSTEM, temperature=0.0, max_tokens=4000)
            source = self._strip_code_fence(fix.text)
            healed_iters += 1
            if progress:
                progress({"stage": "model:generate", "status": "healing", "iter": i + 1})

        model_id = await self._to_thread(self._store_model, deal_id, source, contract, actor)
        if progress:
            progress({"stage": "model:generate", "status": "done", "model_id": model_id, "heal_iters": healed_iters})
        return {"model_id": model_id, "lines": source.count("\n") + 1, "heal_iters": healed_iters}

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------
    async def audit(
        self,
        deal_id: str,
        llm: LLMClient,
        *,
        actor: str = "system",
        progress: Optional[ProgressFn] = None,
    ) -> ServiceResult:
        return await self.guard(self._audit(deal_id, llm, actor, progress))

    async def _audit(
        self, deal_id: str, llm: LLMClient, actor: str, progress: Optional[ProgressFn]
    ) -> dict[str, Any]:
        store = self.context(deal_id).store(init=False)
        model = await self._to_thread(store.get_latest_payment_model, deal_id)
        if not model:
            raise FileNotFoundError("No payment model to audit. Generate one first.")
        clauses = await self._to_thread(store.list_governing_clauses, deal_id)
        if progress:
            progress({"stage": "model:audit", "status": "in-progress"})

        prompt = self._audit_prompt(model.get("python_source", ""), clauses)
        result = await llm.complete(prompt, system=_AUDIT_SYSTEM, temperature=0.0, max_tokens=2000)
        report = parse_json_lenient(result.text) or {"checks": [], "verdict": "fail"}
        verdict = report.get("verdict", "fail") if isinstance(report, dict) else "fail"
        validation = "approved" if verdict == "pass" else "exception"

        await self._to_thread(self._store_audit, deal_id, model, report, validation, actor)
        if progress:
            progress({"stage": "model:audit", "status": "done", "verdict": verdict})
        return {"verdict": verdict, "checks": (report.get("checks", []) if isinstance(report, dict) else [])}

    # ------------------------------------------------------------------
    # Sync helpers
    # ------------------------------------------------------------------
    def _build_contract(self, deal_id: str) -> dict[str, Any]:
        store = self.context(deal_id).store(init=False)
        return {
            "governing_clauses": store.list_governing_clauses(deal_id),
            "certificates": store.list_sep_artifacts(deal_id, "certificates"),
            "fees": store.list_sep_artifacts(deal_id, "fees"),
            "accounts": store.list_sep_artifacts(deal_id, "accounts"),
            "waterfall": store.list_sep_artifacts(deal_id, "waterfall_rules"),
        }

    def _gen_prompt(self, contract: dict[str, Any]) -> str:
        parts = ["Build the WaterfallModel from this approved data contract.\n"]
        for key in ("certificates", "fees", "accounts", "waterfall"):
            items = contract.get(key) or []
            if items:
                parts.append(f"\n{key.upper()}:")
                for a in items[:30]:
                    parts.append(f"- {a.get('value')}  (cite: {a.get('citation')})")
        clauses = contract.get("governing_clauses") or []
        if clauses:
            parts.append("\nGOVERNING CLAUSES:")
            for c in clauses[:30]:
                parts.append(f"- {c.get('plain_english')} | formula: {c.get('math_formula')} (cite: {c.get('citation')})")
        parts.append("\nReturn the complete Python module:")
        return "\n".join(parts)

    def _audit_prompt(self, source: str, clauses: list[dict[str, Any]]) -> str:
        parts = ["PAYMENT MODEL:\n", source[:6000], "\n\nGOVERNING CLAUSES:"]
        for c in clauses[:30]:
            parts.append(f"- {c.get('plain_english')} | formula: {c.get('math_formula')} (cite: {c.get('citation')})")
        parts.append("\nReturn the audit JSON:")
        return "\n".join(parts)

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        t = text.strip()
        if t.startswith("```"):
            lines = t.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            return "\n".join(lines)
        return t

    def _store_model(self, deal_id: str, source: str, contract: dict[str, Any], actor: str) -> str:
        store: DealStore = self.context(deal_id).store()
        prior = store.get_latest_payment_model(deal_id)
        version = (prior["version"] + 1) if prior else 1
        formula_map = {
            f"clause_{i}": c.get("citation", "")
            for i, c in enumerate(contract.get("governing_clauses") or [])
        }
        model_id = store.add_payment_model({
            "deal_id": deal_id,
            "python_source": source,
            "formula_map": formula_map,
            "validation_status": "pending_review",
            "version": version,
        })
        store.audit("generate_payment_model", actor=actor, object_type="payment_model",
                    object_id=model_id, after={"version": version})
        return model_id

    def _store_audit(self, deal_id: str, model: dict[str, Any], report: Any, validation: str, actor: str) -> None:
        store: DealStore = self.context(deal_id).store()
        # Attach the audit report + verdict to the existing model in place.
        store.set_model_audit(
            model["model_id"], audit_report=report, validation_status=validation
        )
        store.audit("audit_payment_model", actor=actor, object_type="payment_model",
                    object_id=model.get("model_id", ""), after={"validation_status": validation})
