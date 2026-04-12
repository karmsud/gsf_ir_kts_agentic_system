"""
DealAmendmentAgent — Track A: Document Intelligence + Ingestion

Tracks and applies document amendments, maintains a full version chain,
snapshots originals, and re-processes affected sections so downstream
agents always operate on the active version of a deal.

No LLM / OpenAI dependency — all work is performed via the deterministic
amendment_manager and parser skill functions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.agents.base_agent import AgentBase
from backend.agents.agent_tools import ToolRegistry
from backend.common.confidence import ConfidenceScore, ConfidenceTier
from backend.abs.deal_manifest import DealManifest
from backend.abs.deal_scope import DealScope
from backend.abs.skills.amendment_manager import (
    AmendmentRecord,
    snapshot_original,
    apply_amendment,
    get_active_version,
    get_version_chain,
)
from backend.abs.skills.parsers import parse_section, get_available_parsers
from backend.abs.skills.csv_validator import validate_extraction_json
from config import KTSConfig


class DealAmendmentAgent(AgentBase):
    """
    Manage the amendment lifecycle for a deal.

    Responsibilities:
    1. **Snapshot** — preserve the original (or current) extractions before
       any modification.
    2. **Apply** — record the amendment, merge changes into extractions,
       and create a versioned snapshot.
    3. **Re-extract** — re-parse affected sections from the amendment
       source document so extractions stay accurate.
    4. **Version chain** — maintain an ordered chain of amendments with
       full audit trail.
    5. **Validate** — re-validate affected sections after amendment.

    The agent is fully deterministic (no LLM calls).
    """

    agent_name = "deal_amendment"

    def __init__(
        self,
        config: KTSConfig,
        deal_scope: DealScope,
        tool_registry: ToolRegistry,
        llm_callable=None,
    ) -> None:
        super().__init__(config, deal_scope=deal_scope, tool_registry=tool_registry, llm_callable=llm_callable)

    # ------------------------------------------------------------------
    # Prompt structure
    # ------------------------------------------------------------------

    def _get_mission(self) -> str:
        return (
            "Track and apply document amendments for the deal. Snapshot the "
            "current version before changes, apply amendments to the extraction "
            "data, re-parse affected sections from the amendment source, maintain "
            "a version chain for full auditability, and validate all updated "
            "extractions."
        )

    def _get_actions(self) -> list[str]:
        return [
            "Load the current active version of the deal extractions.",
            "Snapshot the current version to preserve a rollback point.",
            "Apply the amendment changes to the extraction data.",
            "Re-parse affected sections from the amendment source document.",
            "Validate re-extracted sections against JSON schemas.",
            "Update the version chain with the new amendment record.",
            "Update the deal manifest amendment history.",
            "Persist updated extractions to deal_path/extractions/.",
        ]

    def _get_output_spec(self) -> str:
        return (
            "dict with keys:\n"
            "  amendment_id: str\n"
            "  version: int  — new version number\n"
            "  snapshot_path: str  — path to pre-amendment snapshot\n"
            "  affected_sections: list[str]\n"
            "  re_extracted: dict[section, list[dict]]  — re-parsed items\n"
            "  validation: dict[section, {valid: bool, errors: list[str]}]\n"
            "  version_chain_length: int\n"
            "  status: str  — 'applied' | 'failed'\n"
        )

    def _get_validation_rules(self) -> list[str]:
        return [
            "A pre-amendment snapshot must be created before any changes.",
            "The amendment must produce a new version number > current.",
            "All affected sections must be re-validated after amendment.",
            "The version chain must be consistent (no gaps).",
            "Deal manifest amendment_history must be updated.",
        ]

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    def _run(self, task: dict[str, Any]) -> dict[str, Any]:
        description: str = task.get("description", "Unnamed amendment")
        affected_sections: list[str] = task.get("affected_sections", [])
        changes: dict[str, Any] = task.get("changes", {})
        source_document: str = task.get("source_document", "")
        applied_by: str = task.get("applied_by", "deal_amendment")

        deal_path = self.deal_scope.deal_path

        # ---- 1. Snapshot current state -----------------------------------------
        current_extractions = get_active_version(deal_path)
        snapshot_path = snapshot_original(
            deal_path,
            current_extractions,
            deal_id=self.deal_scope.deal_id,
        )

        # ---- 2. Re-extract from source document (if provided) ------------------
        re_extracted: dict[str, list[dict]] = {}
        if source_document:
            re_extracted = self._re_extract_sections(
                source_document, affected_sections,
            )
            for sec_name, items in re_extracted.items():
                changes[sec_name] = items

        # ---- 3. Apply amendment ------------------------------------------------
        try:
            record: AmendmentRecord = apply_amendment(
                deal_path=deal_path,
                amendment_description=description,
                changes=changes,
                affected_sections=affected_sections,
                source_document=source_document,
                applied_by=applied_by,
            )
            status = "applied"
        except Exception as exc:
            return {
                "amendment_id": "",
                "version": -1,
                "snapshot_path": str(snapshot_path),
                "affected_sections": affected_sections,
                "re_extracted": re_extracted,
                "validation": {},
                "version_chain_length": 0,
                "status": "failed",
                "error": str(exc),
            }

        # ---- 4. Validate affected sections -------------------------------------
        validation = self._validate_sections(changes, affected_sections)

        # ---- 5. Persist updated extraction files --------------------------------
        self._update_extraction_files(changes)

        # ---- 6. Update deal manifest -------------------------------------------
        self._update_manifest(record, affected_sections, description)

        # ---- 7. Get version chain length ----------------------------------------
        chain = get_version_chain(deal_path)
        chain_length = chain.current_version if chain else record.version

        return {
            "amendment_id": record.amendment_id,
            "version": record.version,
            "snapshot_path": str(snapshot_path),
            "affected_sections": affected_sections,
            "re_extracted": re_extracted,
            "validation": validation,
            "version_chain_length": chain_length,
            "status": status,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _re_extract_sections(
        self,
        source_document: str,
        affected_sections: list[str],
    ) -> dict[str, list[dict]]:
        doc_path = Path(source_document)
        if not doc_path.exists():
            return {}

        try:
            content = doc_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = doc_path.read_text(encoding="latin-1")

        available = set(get_available_parsers())
        _parser_alias: dict[str, str] = {
            "waterfall": "waterfall_rules",
        }

        extracted: dict[str, list[dict]] = {}
        for section_name in affected_sections:
            parser_key = _parser_alias.get(section_name, section_name)
            if parser_key not in available:
                continue
            try:
                items = parse_section(parser_key, content)
                if items:
                    extracted[section_name] = items
            except Exception:
                continue

        return extracted

    @staticmethod
    def _validate_sections(
        changes: dict[str, Any],
        affected_sections: list[str],
    ) -> dict[str, dict[str, Any]]:
        validation: dict[str, dict[str, Any]] = {}

        for sec_name in affected_sections:
            items = changes.get(sec_name)
            if items is None:
                validation[sec_name] = {
                    "valid": False,
                    "errors": ["No extraction data for this section after amendment."],
                }
                continue
            try:
                valid, errors = validate_extraction_json(
                    {"section": sec_name, "items": items}, sec_name,
                )
                validation[sec_name] = {"valid": valid, "errors": errors}
            except Exception as exc:
                validation[sec_name] = {"valid": False, "errors": [str(exc)]}

        return validation

    def _update_extraction_files(self, changes: dict[str, Any]) -> None:
        ext_dir = self.deal_scope.resolve("extractions")
        ext_dir.mkdir(parents=True, exist_ok=True)

        for section_name, items in changes.items():
            out_path = ext_dir / f"{section_name}.json"
            out_path.write_text(
                json.dumps(items, indent=2, default=str),
                encoding="utf-8",
            )

    def _update_manifest(
        self,
        record: AmendmentRecord,
        affected_sections: list[str],
        description: str,
    ) -> None:
        manifest_path = self.deal_scope.get_manifest_path()
        if not manifest_path.exists():
            return

        manifest = DealManifest.load(self.deal_scope.deal_path)
        manifest.add_amendment(
            version_label=record.amendment_id,
            description=description,
            sections_changed=affected_sections,
        )
        manifest.save(self.deal_scope.deal_path)

    # ------------------------------------------------------------------
    # Quality gate overrides
    # ------------------------------------------------------------------

    def _score_completeness(self, result: Any, task: dict) -> float:
        if result.get("status") == "failed":
            return 0.0
        expected = set(task.get("affected_sections", []))
        validated = set(result.get("validation", {}).keys())
        if not expected:
            return 10.0
        ratio = len(expected & validated) / len(expected)
        return min(ratio * 10.0, 10.0)

    def _score_accuracy(self, result: Any, task: dict) -> float:
        if result.get("status") == "failed":
            return 0.0
        validations = result.get("validation", {})
        if not validations:
            return 8.0
        valid_count = sum(1 for v in validations.values() if v.get("valid"))
        ratio = valid_count / len(validations)
        return min(ratio * 10.0, 10.0)

    def _score_confidence(self, result: Any, task: dict[str, Any]) -> ConfidenceScore:
        if result.get("status") == "failed":
            return ConfidenceScore(
                0.20, ConfidenceTier.LOW,
                f"Amendment failed: {result.get('error', 'unknown')}",
            )
        validations = result.get("validation", {})
        if not validations:
            return ConfidenceScore(
                0.80, ConfidenceTier.MEDIUM,
                "Amendment applied but no validations ran.",
            )
        valid_count = sum(1 for v in validations.values() if v.get("valid"))
        ratio = valid_count / len(validations)
        tier = self._categorize_confidence(ratio)
        return ConfidenceScore(
            value=round(ratio, 4),
            tier=tier,
            reasoning=(
                f"{valid_count}/{len(validations)} affected sections passed "
                f"post-amendment validation."
            ),
        )

    def _get_artifacts(self, result: Any) -> list[str]:
        artifacts: list[str] = []
        snap = result.get("snapshot_path", "")
        if snap:
            artifacts.append(snap)
        for section in result.get("affected_sections", []):
            artifacts.append(
                str(self.deal_scope.resolve(f"extractions/{section}.json"))
            )
        return artifacts
