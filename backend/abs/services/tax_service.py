"""
TaxService — Layer A.8: Tax processing and reporting integration.

Drives the cashflow_projection_agent's tax sub-agent to produce:
- OID (Original Issue Discount) cash-flow outputs
- CUSIP/tranche-level projection data for 8-K / 10-K tax support
- NPV calculations per class
- Monthly/quarterly/annual tax support summaries

Stores results in agent_results so the WebView can display them.
Stateless + async.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from backend.abs.services.base import ABSService, ProgressFn, ServiceContext, ServiceResult
from backend.abs.services.json_utils import parse_json_lenient
from backend.abs.services.model_run_service import _parse_amount, _parse_rate
from backend.abs.store import DealStore


class TaxService(ABSService):
    """Generate tax-support outputs (OID, 8-K/10-K, NPV) from deal projections."""

    name = "tax"

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)

    def context(self, deal_id: str) -> ServiceContext:
        return ServiceContext(deal_id=deal_id, deals_root=self.deals_root)

    # ------------------------------------------------------------------
    # Generate tax outputs
    # ------------------------------------------------------------------
    async def generate(
        self,
        deal_id: str,
        *,
        scenario_name: str = "base",
        discount_rate: float = 0.05,
        actor: str = "system",
        progress: Optional[ProgressFn] = None,
    ) -> ServiceResult:
        return await self.guard(self._generate(deal_id, scenario_name, discount_rate, actor, progress))

    async def _generate(
        self, deal_id: str, scenario_name: str, discount_rate: float, actor: str, progress: Optional[ProgressFn]
    ) -> dict[str, Any]:
        if progress:
            progress({"stage": "tax", "status": "in-progress"})
        result = await self._to_thread(self._build, deal_id, scenario_name, discount_rate, actor)
        if progress:
            progress({"stage": "tax", "status": "done"})
        return result

    def _build(self, deal_id: str, scenario_name: str, discount_rate: float, actor: str) -> dict[str, Any]:
        store = self.context(deal_id).store(init=False)

        # Get projection results for the scenario
        projection_result = store.get_latest_agent_result(deal_id, f"projection:{scenario_name}")
        if not projection_result:
            raise ValueError(f"No projection results for scenario '{scenario_name}'. Run projections first.")

        proj_data = json.loads(projection_result["result_json"] or "{}")
        months_data = proj_data.get("months_summary") or proj_data.get("months") or []

        # Get classes for OID / NPV calculation
        classes = []
        for art in store.list_sep_artifacts(deal_id, "certificates"):
            v = parse_json_lenient(art.get("value") or "") or {}
            if not isinstance(v, dict):
                continue
            name = v.get("class_name") or v.get("class")
            if not name:
                continue
            classes.append({
                "class_name": str(name), "cusip": str(v.get("cusip", "")),
                "original_balance": _parse_amount(v.get("original_balance")),
                "coupon_rate": _parse_rate(v.get("accrual_formula", v.get("certificate_rate"))),
                "seniority": str(v.get("seniority", "")),
            })

        # ── OID calculation (simplified: issue price vs par) ───────────
        oid_outputs: list[dict[str, Any]] = []
        for cls in classes:
            orig_bal = cls["original_balance"]
            coupon = cls["coupon_rate"]
            # OID arises when issue price < par; simplified: assume no discount
            oid_amount = 0.0  # Would be: par - issue_price; use 0 unless issue_price data available
            oid_outputs.append({
                "class_name": cls["class_name"], "cusip": cls["cusip"],
                "original_balance": orig_bal, "coupon_rate": coupon,
                "oid_amount": oid_amount, "oid_rate": oid_amount / orig_bal if orig_bal else 0.0,
                "note": "OID=0 (issue at par); update when issue_price data is available",
            })

        # ── NPV calculation per class ──────────────────────────────────
        npv_outputs: list[dict[str, Any]] = []
        for cls in classes:
            npv = 0.0
            for i, month in enumerate(months_data, 1):
                # Extract distributions to this class
                distributions = month.get("distributions") or []
                class_dist = sum(float(d.get("amount", 0) or 0)
                                 for d in distributions if d.get("target") == cls["class_name"])
                discount_factor = 1.0 / ((1 + discount_rate / 12) ** i)
                npv += class_dist * discount_factor
            npv_outputs.append({
                "class_name": cls["class_name"], "cusip": cls["cusip"],
                "npv": round(npv, 2), "discount_rate": discount_rate,
                "scenario": scenario_name, "months_projected": len(months_data),
            })

        # ── 8-K / 10-K style summary ──────────────────────────────────
        summary_8k = self._build_8k_summary(deal_id, scenario_name, oid_outputs, npv_outputs, months_data)

        tax_result = {
            "deal_id": deal_id, "scenario": scenario_name, "discount_rate": discount_rate,
            "oid_outputs": oid_outputs, "npv_outputs": npv_outputs,
            "filing_summary": summary_8k,
        }

        # Persist
        store.add_agent_result(deal_id, "tax", {"scenario": scenario_name, "discount_rate": discount_rate}, tax_result)
        store.audit("generate_tax", actor=actor, object_type="tax", object_id=deal_id,
                    after={"classes": len(classes), "scenario": scenario_name})

        # Write to artifacts folder
        ctx = self.context(deal_id)
        out_dir = ctx.scope().deal_path / "artifacts" / "tax"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"tax_{scenario_name}.json").write_text(json.dumps(tax_result, indent=2, default=str), encoding="utf-8")
        (out_dir / "8k_summary.txt").write_text(summary_8k, encoding="utf-8")
        tax_result["json_path"] = str(out_dir / f"tax_{scenario_name}.json")
        tax_result["summary_path"] = str(out_dir / "8k_summary.txt")
        return tax_result

    def _build_8k_summary(self, deal_id: str, scenario: str,
                           oid: list, npv: list, months: list) -> str:
        lines = [
            f"STRUCTURED FINANCE TAX SUPPORT OUTPUT",
            f"Deal: {deal_id} | Scenario: {scenario}",
            "=" * 60,
            "",
            "OID / ORIGINAL ISSUE DISCOUNT SUMMARY:",
        ]
        for o in oid:
            lines.append(f"  {o['class_name']} ({o['cusip']}): OID={o['oid_amount']:.2f}")
        lines += ["", "NPV BY CLASS:"]
        for n in npv:
            lines.append(f"  {n['class_name']} ({n['cusip']}): NPV={n['npv']:,.2f} at {n['discount_rate']*100:.2f}%")
        lines += ["", f"MONTHS PROJECTED: {len(months)}", "", "NOTE: Full 8-K/10-K filing data requires review by tax counsel."]
        return "\n".join(lines)

    async def get_results(self, deal_id: str) -> ServiceResult:
        store = self.context(deal_id).store(init=False)
        result = store.get_latest_agent_result(deal_id, "tax")
        if result:
            try:
                result["result_parsed"] = json.loads(result["result_json"] or "{}")
            except Exception:
                pass
        return ServiceResult.success(result)
