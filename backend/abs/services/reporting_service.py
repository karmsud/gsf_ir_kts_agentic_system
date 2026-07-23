"""
ReportingService — monthly distribution-statement generation.

Assembles a class-level distribution statement (modelled on the US Bank C-BASS
2002-CB4 format) from a monthly run's results enriched with certificate
metadata (CUSIP, original balance, pass-through rate), renders it as styled HTML
for the WebView, and produces a paginated PDF via PyMuPDF. The output PDF path
is recorded on the monthly run. Stateless + async.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.abs.services.base import ABSService, ProgressFn, ServiceContext, ServiceResult
from backend.abs.services.pdf_render import html_to_pdf
from backend.abs.store import DealStore


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _money(value: float) -> str:
    return f"{value:,.2f}"


class ReportingService(ABSService):
    """Generate investor distribution statements (HTML + PDF)."""

    name = "reporting"

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)

    def context(self, deal_id: str) -> ServiceContext:
        return ServiceContext(deal_id=deal_id, deals_root=self.deals_root)

    async def generate_statement(
        self,
        deal_id: str,
        *,
        run_id: Optional[str] = None,
        results: Optional[dict[str, Any]] = None,
        distribution_date: str = "",
        deal_name: str = "",
        series: str = "",
        actor: str = "system",
        progress: Optional[ProgressFn] = None,
    ) -> ServiceResult:
        return await self.guard(
            self._generate(deal_id, run_id, results, distribution_date, deal_name, series, actor, progress)
        )

    async def _generate(
        self,
        deal_id: str,
        run_id: Optional[str],
        results: Optional[dict[str, Any]],
        distribution_date: str,
        deal_name: str,
        series: str,
        actor: str,
        progress: Optional[ProgressFn],
    ) -> dict[str, Any]:
        if progress:
            progress({"stage": "report", "status": "in-progress"})

        rows, dist_date = await self._to_thread(
            self._build_rows, deal_id, run_id, results, distribution_date
        )
        html = self._render_html(deal_name or deal_id, series, dist_date, rows)

        scope = self.context(deal_id).scope()
        safe_date = (dist_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")).replace("/", "-")
        pdf_path = scope.resolve(f"reports/{safe_date}_distribution_statement.pdf")
        html_path = scope.resolve(f"reports/{safe_date}_distribution_statement.html")
        await self._to_thread(html_path.write_text, html, "utf-8")
        produced_pdf = await self._to_thread(html_to_pdf, html, pdf_path)

        await self._to_thread(
            self._record, deal_id, run_id, dist_date, str(pdf_path) if produced_pdf else "", rows, actor
        )
        if progress:
            progress({"stage": "report", "status": "done", "pdf": bool(produced_pdf)})
        return {
            "rows": rows,
            "html_path": str(html_path),
            "pdf_path": str(pdf_path) if produced_pdf else "",
            "pdf_generated": bool(produced_pdf),
            "distribution_date": dist_date,
        }

    # ------------------------------------------------------------------
    # Sync helpers
    # ------------------------------------------------------------------
    def _build_rows(
        self,
        deal_id: str,
        run_id: Optional[str],
        results: Optional[dict[str, Any]],
        distribution_date: str,
    ) -> tuple[list[dict[str, Any]], str]:
        store = self.context(deal_id).store(init=False)
        dist_date = distribution_date

        if results is None:
            runs = store.list_monthly_runs(deal_id)
            run = None
            if run_id:
                run = next((r for r in runs if r["run_id"] == run_id), None)
            elif runs:
                run = runs[0]
            if run is not None:
                results = json.loads(run["results"]) if run.get("results") else {}
                dist_date = dist_date or run.get("run_date", "")
            else:
                results = {}

        # Certificate metadata by class name.
        cert_meta: dict[str, dict[str, Any]] = {}
        for art in store.list_sep_artifacts(deal_id, "certificates"):
            try:
                v = json.loads(art["value"]) if art.get("value") else {}
            except (json.JSONDecodeError, TypeError):
                v = {}
            name = v.get("class_name") or v.get("class")
            if name:
                cert_meta[str(name)] = v

        rows: list[dict[str, Any]] = []
        for class_name, vals in (results or {}).items():
            vals = vals if isinstance(vals, dict) else {}
            meta = cert_meta.get(str(class_name), {})
            interest = _num(vals.get("interest", vals.get("interest_paid")))
            principal = _num(vals.get("principal", vals.get("principal_paid")))
            ending = _num(vals.get("ending_balance"))
            rows.append({
                "class_name": class_name,
                "cusip": meta.get("cusip", ""),
                "original_balance": _num(meta.get("original_balance")),
                "beginning_balance": _num(vals.get("beginning_balance")),
                "principal_distribution": principal,
                "interest_distribution": interest,
                "total_distribution": principal + interest,
                "ending_balance": ending,
                "pass_through_rate": meta.get("accrual_formula", meta.get("pass_through_rate", "")),
            })
        return rows, dist_date

    def _render_html(self, deal_name: str, series: str, dist_date: str, rows: list[dict[str, Any]]) -> str:
        header_cells = (
            "<th>Class</th><th>CUSIP</th><th>Original Face</th><th>Beginning Balance</th>"
            "<th>Principal</th><th>Interest</th><th>Total Distribution</th>"
            "<th>Ending Balance</th><th>Pass-Through Rate</th>"
        )
        body_rows = []
        totals = {"orig": 0.0, "beg": 0.0, "prin": 0.0, "int": 0.0, "tot": 0.0, "end": 0.0}
        for r in rows:
            totals["orig"] += r["original_balance"]
            totals["beg"] += r["beginning_balance"]
            totals["prin"] += r["principal_distribution"]
            totals["int"] += r["interest_distribution"]
            totals["tot"] += r["total_distribution"]
            totals["end"] += r["ending_balance"]
            body_rows.append(
                "<tr>"
                f"<td>{r['class_name']}</td><td>{r['cusip']}</td>"
                f"<td class='n'>{_money(r['original_balance'])}</td>"
                f"<td class='n'>{_money(r['beginning_balance'])}</td>"
                f"<td class='n'>{_money(r['principal_distribution'])}</td>"
                f"<td class='n'>{_money(r['interest_distribution'])}</td>"
                f"<td class='n'>{_money(r['total_distribution'])}</td>"
                f"<td class='n'>{_money(r['ending_balance'])}</td>"
                f"<td>{r['pass_through_rate']}</td>"
                "</tr>"
            )
        total_row = (
            "<tr class='total'>"
            "<td>Total</td><td></td>"
            f"<td class='n'>{_money(totals['orig'])}</td>"
            f"<td class='n'>{_money(totals['beg'])}</td>"
            f"<td class='n'>{_money(totals['prin'])}</td>"
            f"<td class='n'>{_money(totals['int'])}</td>"
            f"<td class='n'>{_money(totals['tot'])}</td>"
            f"<td class='n'>{_money(totals['end'])}</td>"
            "<td></td></tr>"
        )
        return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
        body {{ font-family: Helvetica, Arial, sans-serif; color: #1d1d1f; }}
        h1 {{ font-size: 18px; margin: 0; }}
        h2 {{ font-size: 13px; color: #555; margin: 2px 0 12px; font-weight: 500; }}
        .meta {{ font-size: 11px; color: #666; margin-bottom: 14px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 10px; }}
        th, td {{ border: 0.5px solid #ccc; padding: 4px 6px; text-align: left; }}
        th {{ background: #f2f2f7; }}
        td.n {{ text-align: right; font-variant-numeric: tabular-nums; }}
        tr.total td {{ font-weight: 700; background: #fafafa; }}
        </style></head><body>
        <h1>Distribution Statement</h1>
        <h2>{deal_name} {('— Series ' + series) if series else ''}</h2>
        <div class="meta">Distribution Date: {dist_date or 'N/A'}</div>
        <table><thead><tr>{header_cells}</tr></thead>
        <tbody>{''.join(body_rows)}{total_row}</tbody></table>
        </body></html>"""

    def _record(
        self,
        deal_id: str,
        run_id: Optional[str],
        dist_date: str,
        pdf_path: str,
        rows: list[dict[str, Any]],
        actor: str,
    ) -> None:
        store: DealStore = self.context(deal_id).store()
        store.add_monthly_run({
            "deal_id": deal_id,
            "run_date": dist_date or "",
            "output_pdf_path": pdf_path,
            "results": {r["class_name"]: r for r in rows},
        })
        store.audit("generate_report", actor=actor, object_type="deal", object_id=deal_id,
                    after={"pdf": pdf_path, "rows": len(rows)})
