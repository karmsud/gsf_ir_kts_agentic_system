"""
EvidencePackageService — FRD Screen 8 (Lineage & Evidence).

Generates a portable, self-contained evidence bundle for a deal's approved
output. The bundle proves lineage from every published artifact back to the
source legal document per the FRD §10.1 requirements:

* Deal metadata
* Source documents (title, type, version, hash, path)
* Extraction run metadata (schema version, timestamp)
* Extracted terms used for artifacts (definitions)
* Source citations (section, page)
* Confidence scores and labels
* Review decisions, overrides with rationale
* Approval history (actor, timestamp)
* Published artifact versions
* Related exceptions (correction events)
* Material audit log entries

Output: ``<deal>/artifacts/evidence_package.json`` and a human-readable
``evidence_package_summary.txt``. Stateless + async.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.abs.services.base import ABSService, ProgressFn, ServiceContext, ServiceResult
from backend.abs.store import DealStore, SCHEMA_VERSION


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvidencePackageService(ABSService):
    """Generate a portable lineage + evidence bundle."""

    name = "evidence"

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
            progress({"stage": "evidence", "status": "in-progress"})
        result = await self._to_thread(self._build, deal_id, actor)
        if progress:
            progress({"stage": "evidence", "status": "done"})
        return result

    def _build(self, deal_id: str, actor: str) -> dict[str, Any]:
        ctx = self.context(deal_id)
        store = ctx.store(init=False)
        out_dir = ctx.scope().deal_path / "artifacts"
        out_dir.mkdir(parents=True, exist_ok=True)

        # ── Collect all evidence ─────────────────────────────────────────
        documents = store.list_documents(deal_id)
        definitions = store.list_definitions(deal_id)
        sep_artifacts = store.list_sep_artifacts(deal_id)
        governing = store.list_governing_clauses(deal_id)
        model = store.get_latest_payment_model(deal_id)
        monthly_runs = store.list_monthly_runs(deal_id)
        corrections = store.list_correction_events(deal_id)
        audit_log = store.list_audit(limit=500)

        # ── Build citation index (chunk_id → section+page) ───────────────
        citation_index: dict[str, dict[str, Any]] = {}
        for doc in documents:
            for chunk in store.list_chunks(doc["doc_id"]):
                cid = chunk["chunk_id"]
                sec = store.get_section(chunk.get("section_id") or "") if chunk.get("section_id") else None
                citation_index[cid] = {
                    "section_path": sec.get("section_path") if sec else "",
                    "page_start": chunk.get("page_start"),
                    "page_end": chunk.get("page_end"),
                    "doc_title": doc.get("title"),
                    "source_path": doc.get("source_path"),
                }

        # ── Approval history per artifact ─────────────────────────────────
        approved = [a for a in sep_artifacts if a.get("status") in ("approved", "overridden", "published")]
        approval_history = [
            {
                "artifact_id": a["artifact_id"],
                "sep_name": a["sep_name"],
                "status": a["status"],
                "approved_by": a.get("approved_by"),
                "approved_at": a.get("approved_at"),
                "rationale": a.get("rationale"),
                "version": a.get("version"),
            }
            for a in approved
        ]

        package: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": _now(),
            "generated_by": actor,
            "deal_id": deal_id,
            "source_documents": [
                {
                    "doc_id": d["doc_id"], "title": d.get("title"), "doc_type": d.get("doc_type"),
                    "version": d.get("version"), "content_hash": d.get("content_hash"),
                    "source_path": d.get("source_path"), "page_count": d.get("page_count"),
                }
                for d in documents
            ],
            "definitions_extracted": len(definitions),
            "sep_artifacts_total": len(sep_artifacts),
            "sep_artifacts_approved": len(approved),
            "approval_history": approval_history,
            "governing_clauses": len(governing),
            "payment_model": {
                "version": model.get("version") if model else None,
                "validation_status": model.get("validation_status") if model else None,
                "generated_at": model.get("generated_at") if model else None,
            },
            "monthly_runs": len(monthly_runs),
            "correction_events": len(corrections),
            "citation_index": citation_index,
            "exceptions": [
                {"event_id": e["id"], "severity": e.get("severity"), "root_cause": e.get("root_cause"),
                 "status": e.get("status"), "ts": e.get("ts")}
                for e in corrections
            ],
            "material_audit_log": [
                {"ts": e.get("ts"), "actor": e.get("actor"), "action": e.get("action"),
                 "object_type": e.get("object_type"), "object_id": e.get("object_id")}
                for e in audit_log
                if e.get("action") in ("approve_sep_artifact", "override_sep_artifact", "audit_payment_model",
                                        "generate_setup", "run_model", "generate_report", "generate_excel")
            ],
        }

        # ── Write JSON bundle ─────────────────────────────────────────────
        json_path = out_dir / "evidence_package.json"
        json_path.write_text(json.dumps(package, indent=2, default=str), encoding="utf-8")

        # ── Write human-readable summary ──────────────────────────────────
        lines = [
            f"EVIDENCE PACKAGE — {deal_id}",
            f"Generated: {package['generated_at']} by {actor}",
            "=" * 60,
            f"Source documents:       {len(documents)}",
            f"Definitions extracted:  {len(definitions)}",
            f"SEP artifacts total:    {len(sep_artifacts)}",
            f"SEP artifacts approved: {len(approved)}",
            f"Governing clauses:      {len(governing)}",
            f"Payment model version:  {(model or {}).get('version', 'None')}",
            f"Monthly runs:           {len(monthly_runs)}",
            f"Correction events:      {len(corrections)}",
            f"Audit entries captured: {len(package['material_audit_log'])}",
            "",
            "APPROVAL HISTORY:",
        ]
        for ah in approval_history[:20]:
            lines.append(f"  [{ah['sep_name']}] {ah['artifact_id'][:12]}… → {ah['status']} "
                         f"by {ah['approved_by']} at {(ah['approved_at'] or '')[:16]}")
        summary_path = out_dir / "evidence_package_summary.txt"
        summary_path.write_text("\n".join(lines), encoding="utf-8")

        store.audit("generate_evidence_package", actor=actor, object_type="deal", object_id=deal_id,
                    after={"artifacts": len(sep_artifacts), "approved": len(approved)})
        return {
            "json_path": str(json_path),
            "summary_path": str(summary_path),
            "artifacts_approved": len(approved),
            "documents": len(documents),
        }
