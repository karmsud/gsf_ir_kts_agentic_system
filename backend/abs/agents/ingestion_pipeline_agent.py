"""
IngestionPipelineAgent — Track A: Document Intelligence + Ingestion

Orchestrates the full ingestion lifecycle for a deal's documents:
classify -> hash -> split into sections -> parse each section -> validate
extractions -> save results -> generate governing docs.

No LLM / OpenAI dependency — all work is performed via deterministic
skill functions and the v2 parser layer.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from backend.agents.base_agent import AgentBase
from backend.agents.agent_tools import ToolRegistry
from backend.common.confidence import ConfidenceScore, ConfidenceTier
from backend.abs.config.constants import CANONICAL_SECTIONS
from backend.abs.config.section_maps import get_section_map
from backend.abs.deal_manifest import (
    DealManifest,
    DocumentEntry,
    DocumentType,
    IngestionStatus,
)
from backend.abs.deal_scope import DealScope
from backend.abs.skills.document_classifier import classify_document
from backend.abs.skills.document_hasher import compute_content_hash
from backend.abs.skills.csv_validator import validate_extraction_json
from backend.abs.skills.parsers import parse_section, split_into_sections, get_available_parsers
from backend.abs.skills.report_generator import generate_governing_docs
from config import KTSConfig


class IngestionPipelineAgent(AgentBase):
    """
    Orchestrate end-to-end ingestion of raw deal documents.

    Pipeline stages (executed in order for every document):
    1. **Classify** — determine document type via pattern matching.
    2. **Hash** — compute SHA-256 for integrity/dedup.
    3. **Split** — break the document into canonical sections using
       issuer-specific section maps.
    4. **Parse** — run the appropriate v2 parser on each section
       to produce structured extraction dicts.
    5. **Validate** — validate each extraction against its JSON schema.
    6. **Save** — persist extraction JSON files, update the deal manifest,
       and generate governing documents.
    """

    agent_name = "ingestion_pipeline"

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
            "Orchestrate the full ingestion pipeline for raw deal documents. "
            "Classify each document, split it into canonical sections, parse "
            "every section with the v2 extraction parsers, validate the output "
            "against JSON schemas, and persist both extraction artefacts and "
            "generated governing documents."
        )

    def _get_actions(self) -> list[str]:
        return [
            "Read raw documents from the deal's raw/ directory.",
            "Classify each document by type (PSA, indenture, ...).",
            "Compute content hash for each document.",
            "Determine the issuer-specific section map from the deal manifest.",
            "Split each document into canonical sections "
            "(definitions, waterfall, accounts, ...).",
            "Parse each section with the matching v2 parser.",
            "Validate each extraction against its JSON schema.",
            "Save extraction JSON files to deal_path/extractions/.",
            "Update the deal manifest with document entries and status.",
            "Generate governing documents to deal_path/governing_docs/.",
        ]

    def _get_output_spec(self) -> str:
        return (
            "dict with keys:\n"
            "  extractions: dict[section_name, list[dict]]  — parsed items\n"
            "  validation: dict[section_name, {valid: bool, errors: list[str]}]\n"
            "  documents_processed: list[str]  — filenames ingested\n"
            "  sections_found: list[str]\n"
            "  governing_docs: dict[doc_type, str(path)]\n"
            "  manifest_errors: list[str]\n"
        )

    def _get_validation_rules(self) -> list[str]:
        return [
            "Every raw document must be classified and split.",
            "At least one section must be extracted per payment-source document.",
            "All extractions must pass JSON schema validation.",
            "Extraction files must be written to deal_path/extractions/.",
            "Deal manifest must be updated with ingestion status.",
        ]

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    def _run(self, task: dict[str, Any]) -> dict[str, Any]:
        doc_paths = self._resolve_documents(task)
        issuer = self._resolve_issuer(task)
        section_map = self._build_section_map(issuer)
        available_parsers = set(get_available_parsers())

        all_extractions: dict[str, list[dict]] = {}
        validation_results: dict[str, dict[str, Any]] = {}
        documents_processed: list[str] = []
        sections_found: list[str] = []

        manifest = self._load_or_create_manifest(issuer)

        for doc_path in doc_paths:
            doc_result = self._ingest_document(
                doc_path, section_map, available_parsers, manifest,
            )

            for sec_name, items in doc_result["extractions"].items():
                all_extractions.setdefault(sec_name, []).extend(items)
            for sec_name, val in doc_result["validation"].items():
                validation_results[sec_name] = val

            documents_processed.append(doc_path.name)
            sections_found.extend(doc_result["sections_found"])

        sections_found = sorted(set(sections_found))

        self._save_extractions(all_extractions)
        gov_docs = self._generate_governing_docs(all_extractions)
        manifest.save(self.deal_scope.deal_path)
        manifest_errors = manifest.validate()

        return {
            "extractions": all_extractions,
            "validation": validation_results,
            "documents_processed": documents_processed,
            "sections_found": sections_found,
            "governing_docs": {k: str(v) for k, v in gov_docs.items()},
            "manifest_errors": manifest_errors,
        }

    # ------------------------------------------------------------------
    # Per-document ingestion
    # ------------------------------------------------------------------

    def _ingest_document(
        self,
        doc_path: Path,
        section_map: dict[str, list[str]],
        available_parsers: set[str],
        manifest: DealManifest,
    ) -> dict[str, Any]:
        classification = classify_document(doc_path)
        content_hash = compute_content_hash(doc_path)
        is_payment_source = classification.document_type.upper() in {"PSA", "INDENTURE"}

        try:
            content = doc_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = doc_path.read_text(encoding="latin-1")

        sections = split_into_sections(content, section_map)

        extractions: dict[str, list[dict]] = {}
        validation: dict[str, dict[str, Any]] = {}
        sections_found: list[str] = list(sections.keys())

        _parser_alias: dict[str, str] = {
            "waterfall": "waterfall_rules",
        }

        for sec_name, sec_text in sections.items():
            parser_key = _parser_alias.get(sec_name, sec_name)
            if parser_key not in available_parsers:
                continue

            try:
                items = parse_section(parser_key, sec_text)
            except Exception as exc:
                validation[sec_name] = {"valid": False, "errors": [str(exc)]}
                continue

            extractions[sec_name] = items

            try:
                valid, errors = validate_extraction_json(
                    {"section": sec_name, "items": items}, sec_name,
                )
                validation[sec_name] = {"valid": valid, "errors": errors}
            except Exception as exc:
                validation[sec_name] = {"valid": False, "errors": [str(exc)]}

        doc_key = doc_path.stem.lower().replace(" ", "_")
        try:
            detected_type = DocumentType(classification.document_type.lower())
        except ValueError:
            detected_type = DocumentType.UNKNOWN

        entry = DocumentEntry(
            original_filename=doc_path.name,
            detected_type=detected_type,
            detection_confidence=classification.confidence,
            content_hash=content_hash,
            ingestion_status=IngestionStatus.COMPLETE,
            is_payment_source=is_payment_source,
            ingested_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        manifest.add_document(doc_key, entry)

        return {
            "extractions": extractions,
            "validation": validation,
            "sections_found": sections_found,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_documents(self, task: dict[str, Any]) -> list[Path]:
        if "documents" in task and task["documents"]:
            return [Path(p) for p in task["documents"]]
        return self.deal_scope.list_documents()

    def _resolve_issuer(self, task: dict[str, Any]) -> str:
        if "issuer" in task and task["issuer"]:
            return str(task["issuer"])
        manifest_path = self.deal_scope.get_manifest_path()
        if manifest_path.exists():
            manifest = DealManifest.load(self.deal_scope.deal_path)
            if manifest.issuer:
                return manifest.issuer
        return "default"

    @staticmethod
    def _build_section_map(issuer: str) -> dict[str, list[str]]:
        raw_map = get_section_map(issuer)
        inverted: dict[str, list[str]] = {}
        for pattern, section_name in raw_map.items():
            inverted.setdefault(section_name, []).append(pattern)
        return inverted

    def _load_or_create_manifest(self, issuer: str) -> DealManifest:
        manifest_path = self.deal_scope.get_manifest_path()
        if manifest_path.exists():
            return DealManifest.load(self.deal_scope.deal_path)
        return DealManifest(
            deal_id=self.deal_scope.deal_id,
            deal_name=self.deal_scope.deal_id,
            issuer=issuer,
            series="",
            shelf="",
        )

    def _save_extractions(self, extractions: dict[str, list[dict]]) -> None:
        ext_dir = self.deal_scope.resolve("extractions")
        ext_dir.mkdir(parents=True, exist_ok=True)
        for section_name, items in extractions.items():
            out_path = ext_dir / f"{section_name}.json"
            out_path.write_text(
                json.dumps(items, indent=2, default=str),
                encoding="utf-8",
            )
        self._state["extractions_saved"] = list(extractions.keys())

    def _generate_governing_docs(
        self,
        extractions: dict[str, list[dict]],
    ) -> dict[str, Path]:
        gov_dir = self.deal_scope.resolve("governing_docs")
        return generate_governing_docs(
            extractions, gov_dir, deal_id=self.deal_scope.deal_id,
        )

    # ------------------------------------------------------------------
    # Quality gate overrides
    # ------------------------------------------------------------------

    def _score_completeness(self, result: Any, task: dict) -> float:
        docs_expected = len(self._resolve_documents(task))
        docs_actual = len(result.get("documents_processed", []))
        if docs_expected == 0:
            return 10.0
        doc_ratio = docs_actual / docs_expected
        sections_found = len(result.get("sections_found", []))
        section_ratio = min(sections_found / max(len(CANONICAL_SECTIONS), 1), 1.0)
        return min((doc_ratio * 7.0 + section_ratio * 3.0), 10.0)

    def _score_accuracy(self, result: Any, task: dict) -> float:
        validations = result.get("validation", {})
        if not validations:
            return 8.0
        valid_count = sum(1 for v in validations.values() if v.get("valid"))
        ratio = valid_count / len(validations)
        return min(ratio * 10.0, 10.0)

    def _score_confidence(self, result: Any, task: dict[str, Any]) -> ConfidenceScore:
        validations = result.get("validation", {})
        if not validations:
            return ConfidenceScore(0.80, ConfidenceTier.MEDIUM, "No validations run.")
        valid_count = sum(1 for v in validations.values() if v.get("valid"))
        ratio = valid_count / len(validations)
        tier = self._categorize_confidence(ratio)
        return ConfidenceScore(
            value=round(ratio, 4),
            tier=tier,
            reasoning=(
                f"{valid_count}/{len(validations)} sections passed validation."
            ),
        )

    def _get_artifacts(self, result: Any) -> list[str]:
        artifacts: list[str] = []
        for section in result.get("sections_found", []):
            artifacts.append(
                str(self.deal_scope.resolve(f"extractions/{section}.json"))
            )
        for path_str in result.get("governing_docs", {}).values():
            artifacts.append(path_str)
        return artifacts
