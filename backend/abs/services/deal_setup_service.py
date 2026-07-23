"""
DealSetupService — Layer A.3: Deal Setup Automation.

Converts approved structured artifacts into operational setup packages:
``tblCertInfo``-style certificate load files, CUSIP setup, rate setup, fee
setup, account setup, reporting setup, trigger setup, and a validation report.
Also produces a portable evidence manifest so every setup value traces back to
an approved SEP artifact (and through it to the source PDF).

Output artifacts are written to ``<deal>/artifacts/setup/`` and catalogued in
the deal store. Stateless + async.
"""

from __future__ import annotations

import csv as _csv
import json
from pathlib import Path
from typing import Any, Optional

from backend.abs.services.base import ABSService, ProgressFn, ServiceContext, ServiceResult
from backend.abs.services.json_utils import parse_json_lenient
from backend.abs.store import DealStore

# --------------- helpers ---------------------------------------------------

def _parse_amount(v: Any) -> float:
    try:
        s = str(v).replace(",", "").replace("$", "")
        import re; m = re.search(r"-?\d+(?:\.\d+)?", s)
        return float(m.group(0)) if m else 0.0
    except Exception:
        return 0.0

def _parse_rate(v: Any) -> float:
    import re
    if v is None: return 0.0
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*%", str(v))
    if m: return float(m.group(1)) / 100.0
    m = re.search(r"-?\d+(?:\.\d+)?", str(v))
    return float(m.group(0)) if m else 0.0


class DealSetupService(ABSService):
    """Generate deal setup load files from approved SEP artifacts."""

    name = "deal_setup"

    def __init__(self, deals_root: Path) -> None:
        self.deals_root = Path(deals_root)

    def context(self, deal_id: str) -> ServiceContext:
        return ServiceContext(deal_id=deal_id, deals_root=self.deals_root)

    async def generate(
        self,
        deal_id: str,
        *,
        actor: str = "system",
        progress: Optional[ProgressFn] = None,
    ) -> ServiceResult:
        return await self.guard(self._generate(deal_id, actor, progress))

    async def _generate(self, deal_id: str, actor: str, progress: Optional[ProgressFn]) -> dict[str, Any]:
        if progress:
            progress({"stage": "setup", "status": "in-progress"})
        result = await self._to_thread(self._build_all, deal_id, actor)
        if progress:
            progress({"stage": "setup", "status": "done", "files": list(result["files"].keys())})
        return result

    def _build_all(self, deal_id: str, actor: str) -> dict[str, Any]:
        ctx = self.context(deal_id)
        store = ctx.store(init=False)
        setup_dir = ctx.scope().deal_path / "artifacts" / "setup"
        setup_dir.mkdir(parents=True, exist_ok=True)

        files: dict[str, str] = {}
        validation: list[dict[str, Any]] = []

        # 1. tblCertInfo — certificate load file
        cert_path, cert_issues = self._build_certinfo(store, deal_id, setup_dir)
        if cert_path:
            files["cert_info_csv"] = str(cert_path)
        validation.extend(cert_issues)

        # 2. Fee setup
        fee_path, fee_issues = self._build_fees(store, deal_id, setup_dir)
        if fee_path:
            files["fee_setup_csv"] = str(fee_path)
        validation.extend(fee_issues)

        # 3. Account setup
        acct_path, acct_issues = self._build_accounts(store, deal_id, setup_dir)
        if acct_path:
            files["account_setup_csv"] = str(acct_path)
        validation.extend(acct_issues)

        # 4. Trigger setup
        trig_path, trig_issues = self._build_triggers(store, deal_id, setup_dir)
        if trig_path:
            files["trigger_setup_csv"] = str(trig_path)
        validation.extend(trig_issues)

        # 5. Reporting setup
        rep_path, rep_issues = self._build_reporting(store, deal_id, setup_dir)
        if rep_path:
            files["reporting_setup_csv"] = str(rep_path)
        validation.extend(rep_issues)

        # 6. Evidence manifest (every field → artifact_id → citation → doc+page)
        manifest = self._build_manifest(store, deal_id, files)
        manifest_path = setup_dir / "setup_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        files["manifest"] = str(manifest_path)

        # 7. Validation report
        val_path = setup_dir / "validation_report.json"
        val_path.write_text(json.dumps({"issues": validation, "ok": not validation}, indent=2), encoding="utf-8")
        files["validation_report"] = str(val_path)

        store.audit("generate_setup", actor=actor, object_type="deal", object_id=deal_id,
                    after={"files": list(files.keys()), "validation_issues": len(validation)})
        return {"files": files, "validation_issues": validation, "ok": len([v for v in validation if v.get("severity") == "error"]) == 0}

    # ---------- individual file builders -----------------------------------

    def _build_certinfo(self, store: DealStore, deal_id: str, out: Path) -> tuple[Optional[Path], list]:
        arts = store.list_sep_artifacts(deal_id, "certificates")
        issues: list[dict[str, Any]] = []
        rows = []
        REQUIRED = ["class_name", "original_balance"]
        for art in arts:
            v = parse_json_lenient(art.get("value") or "") or {}
            if not isinstance(v, dict):
                continue
            name = v.get("class_name") or v.get("class")
            if not name:
                issues.append({"field": "class_name", "sep": "certificates", "severity": "error",
                                "message": "Missing class_name", "citation": art.get("citation")})
                continue
            row = {
                "class_name": str(name),
                "cusip": str(v.get("cusip", "")),
                "original_balance": _parse_amount(v.get("original_balance")),
                "certificate_rate": _parse_rate(v.get("accrual_formula", v.get("certificate_rate", 0))),
                "seniority": str(v.get("seniority", "")),
                "citation": str(art.get("citation", "")),
                "artifact_id": art.get("artifact_id", ""),
            }
            if not row["cusip"]:
                issues.append({"field": "cusip", "class": name, "severity": "warning",
                                "message": "CUSIP missing", "citation": art.get("citation")})
            rows.append(row)
        if not rows:
            return None, [{"field": "certificates", "severity": "error", "message": "No certificate artifacts found"}]
        path = out / "tblCertInfo.csv"
        _write_csv(path, rows)
        return path, issues

    def _build_fees(self, store: DealStore, deal_id: str, out: Path) -> tuple[Optional[Path], list]:
        arts = store.list_sep_artifacts(deal_id, "fees")
        issues: list[dict[str, Any]] = []
        rows = []
        for art in arts:
            v = parse_json_lenient(art.get("value") or "") or {}
            if not isinstance(v, dict):
                continue
            name = v.get("fee_name") or v.get("name")
            if not name:
                continue
            row = {"fee_name": str(name), "parties": str(v.get("parties", "")),
                   "frequency": str(v.get("frequency", "")), "formula": str(v.get("formula", "")),
                   "citation": str(art.get("citation", "")), "artifact_id": art.get("artifact_id", "")}
            if not row["formula"]:
                issues.append({"field": "formula", "fee": name, "severity": "warning",
                                "message": "No formula captured", "citation": art.get("citation")})
            rows.append(row)
        if not rows:
            return None, []
        path = out / "fee_setup.csv"
        _write_csv(path, rows)
        return path, issues

    def _build_accounts(self, store: DealStore, deal_id: str, out: Path) -> tuple[Optional[Path], list]:
        arts = store.list_sep_artifacts(deal_id, "accounts")
        rows = []
        for art in arts:
            v = parse_json_lenient(art.get("value") or "") or {}
            if not isinstance(v, dict):
                continue
            name = v.get("account_name") or v.get("account")
            if not name:
                continue
            rows.append({"account_name": str(name), "account_type": str(v.get("account_type", "")),
                         "inflows": str(v.get("inflows", "")), "outflows": str(v.get("outflows", "")),
                         "priority": str(v.get("priority", "")), "citation": str(art.get("citation", ""))})
        if not rows:
            return None, []
        path = out / "account_setup.csv"
        _write_csv(path, rows)
        return path, []

    def _build_triggers(self, store: DealStore, deal_id: str, out: Path) -> tuple[Optional[Path], list]:
        arts = store.list_sep_artifacts(deal_id, "triggers")
        rows = []
        for art in arts:
            v = parse_json_lenient(art.get("value") or "") or {}
            if not isinstance(v, dict):
                continue
            rows.append({"trigger_name": str(v.get("trigger_name", "")),
                         "trigger_type": str(v.get("trigger_type", "")),
                         "test_formula": str(v.get("test_formula", "")),
                         "breach_consequence": str(v.get("breach_consequence", "")),
                         "citation": str(art.get("citation", ""))})
        if not rows:
            return None, []
        path = out / "trigger_setup.csv"
        _write_csv(path, rows)
        return path, []

    def _build_reporting(self, store: DealStore, deal_id: str, out: Path) -> tuple[Optional[Path], list]:
        arts = store.list_sep_artifacts(deal_id, "reporting")
        rows = []
        for art in arts:
            v = parse_json_lenient(art.get("value") or "") or {}
            if not isinstance(v, dict):
                continue
            rows.append({"report_name": str(v.get("report_name", "")), "frequency": str(v.get("frequency", "")),
                         "recipients": str(v.get("recipients", "")), "data_fields": str(v.get("data_fields", "")),
                         "citation": str(art.get("citation", ""))})
        if not rows:
            return None, []
        path = out / "reporting_setup.csv"
        _write_csv(path, rows)
        return path, []

    def _build_manifest(self, store: DealStore, deal_id: str, files: dict) -> dict[str, Any]:
        """Every setup file → artifact_id → citation → doc title + page (full lineage chain)."""
        all_arts = store.list_sep_artifacts(deal_id)
        by_id = {a["artifact_id"]: a for a in all_arts}
        docs = {d["doc_id"]: d for d in store.list_documents(deal_id)}
        entries: list[dict[str, Any]] = []
        for art in all_arts:
            doc = docs.get(art.get("doc_id") or "") or {}
            entries.append({
                "artifact_id": art["artifact_id"],
                "sep_name": art["sep_name"],
                "field_path": art.get("field_path"),
                "citation": art.get("citation"),
                "status": art.get("status"),
                "doc_title": doc.get("title"),
                "source_path": doc.get("source_path"),
            })
        return {"deal_id": deal_id, "artifacts": entries, "setup_files": list(files.keys())}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
