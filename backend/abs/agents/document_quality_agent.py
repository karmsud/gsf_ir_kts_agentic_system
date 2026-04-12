"""
DocumentQualityAgent — Track A: Document Intelligence + Ingestion

Assesses document quality, classifies document types, detects duplicates,
and validates readability for all incoming deal documents.

No LLM / OpenAI dependency — all work is performed via deterministic
skill functions (classify_document, compute_content_hash, check_duplicates).
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from backend.agents.base_agent import AgentBase
from backend.agents.agent_tools import ToolRegistry
from backend.common.confidence import ConfidenceScore, ConfidenceTier
from backend.abs.deal_scope import DealScope
from backend.abs.deal_manifest import DealManifest, DocumentEntry, DocumentType, IngestionStatus
from backend.abs.skills.document_classifier import classify_document, ClassificationResult
from backend.abs.skills.document_hasher import (
    compute_content_hash,
    check_duplicates,
    register_hash,
    DuplicateCheckResult,
)
from config import KTSConfig


# Minimum file size (bytes) to consider a document non-empty.
_MIN_FILE_SIZE_BYTES = 10
# Confidence threshold below which a classification is flagged as uncertain.
_CLASSIFICATION_CONFIDENCE_THRESHOLD = 0.40


class DocumentQualityAgent(AgentBase):
    """
    Assess quality of every document destined for a deal folder.

    Responsibilities:
    1. Classify each document by type (PSA, indenture, prospectus, ...).
    2. Compute content hashes for integrity & duplicate detection.
    3. Check for duplicate documents across the portfolio.
    4. Rate readable quality (non-empty, parseable, not corrupted).
    5. Flag any issues (unknown type, low confidence, duplicates).
    """

    agent_name = "document_quality"

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
            "Assess document quality for every raw document in the deal folder. "
            "Classify document types, compute content hashes, check for duplicates "
            "across the portfolio, and validate readability. Produce a structured "
            "quality report that downstream agents use to decide which documents "
            "to ingest."
        )

    def _get_actions(self) -> list[str]:
        return [
            "Enumerate all documents in the deal's raw/ directory.",
            "Classify each document using filename + content pattern matching.",
            "Compute SHA-256 content hash for every document.",
            "Check each hash against the portfolio hash registry for duplicates.",
            "Register new hashes in the portfolio registry.",
            "Assess readability: file size, encoding, and parseable content.",
            "Rate overall quality per document (0-10 scale).",
            "Flag issues: unknown type, low classification confidence, duplicates, empty files.",
        ]

    def _get_output_spec(self) -> str:
        return (
            "dict with keys:\n"
            "  documents: dict[filename, DocumentAssessment]\n"
            "    DocumentAssessment:\n"
            "      classification: {document_type, confidence, matched_patterns}\n"
            "      content_hash: str\n"
            "      is_duplicate: bool\n"
            "      duplicate_info: {matching_deal_id, matching_document} | null\n"
            "      readability: {size_bytes, is_readable, encoding_ok}\n"
            "      quality_score: float (0-10)\n"
            "      issues: list[str]\n"
            "  summary:\n"
            "    total_documents: int\n"
            "    classified: int\n"
            "    duplicates_found: int\n"
            "    issues_flagged: int\n"
            "    overall_quality: float (0-10)\n"
        )

    def _get_validation_rules(self) -> list[str]:
        return [
            "Every document in raw/ must have a corresponding assessment.",
            "Content hash must be a valid 64-char hex SHA-256 string.",
            "Classification confidence must be between 0.0 and 1.0.",
            "Quality score must be between 0 and 10.",
            "Duplicates must reference the matching deal_id and document.",
        ]

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    def _run(self, task: dict[str, Any]) -> dict[str, Any]:
        doc_paths: list[Path] = self._resolve_documents(task)
        hash_registry_path = self.deal_scope.resolve("runs/hash_registry.json")

        assessments: dict[str, dict[str, Any]] = {}
        total_quality = 0.0
        duplicates_found = 0
        issues_flagged = 0
        classified_count = 0

        for doc_path in doc_paths:
            assessment = self._assess_document(doc_path, hash_registry_path)
            assessments[doc_path.name] = assessment

            total_quality += assessment["quality_score"]
            if assessment["is_duplicate"]:
                duplicates_found += 1
            if assessment["issues"]:
                issues_flagged += 1
            if assessment["classification"]["document_type"] != "UNKNOWN":
                classified_count += 1

        n = max(len(doc_paths), 1)
        summary = {
            "total_documents": len(doc_paths),
            "classified": classified_count,
            "duplicates_found": duplicates_found,
            "issues_flagged": issues_flagged,
            "overall_quality": round(total_quality / n, 2),
        }

        self._save_quality_report(assessments, summary)

        return {"documents": assessments, "summary": summary}

    # ------------------------------------------------------------------
    # Per-document assessment
    # ------------------------------------------------------------------

    def _assess_document(
        self,
        doc_path: Path,
        hash_registry_path: Path,
    ) -> dict[str, Any]:
        issues: list[str] = []

        # ---- Classification ---------------------------------------------------
        classification = classify_document(doc_path)
        if classification.document_type == "UNKNOWN":
            issues.append("Document type could not be determined.")
        elif classification.confidence < _CLASSIFICATION_CONFIDENCE_THRESHOLD:
            issues.append(
                f"Low classification confidence ({classification.confidence:.2f})."
            )

        # ---- Content hash ------------------------------------------------------
        try:
            content_hash = compute_content_hash(doc_path)
        except FileNotFoundError:
            content_hash = ""
            issues.append("File not found — cannot compute hash.")

        # ---- Duplicate check ---------------------------------------------------
        duplicate_info: dict[str, str] | None = None
        is_duplicate = False
        if content_hash:
            dup_result: DuplicateCheckResult = check_duplicates(
                doc_path, hash_registry_path, deal_id=self.deal_scope.deal_id,
            )
            is_duplicate = dup_result.is_duplicate
            if is_duplicate:
                duplicate_info = {
                    "matching_deal_id": dup_result.matching_deal_id,
                    "matching_document": dup_result.matching_document,
                }
                issues.append(
                    f"Duplicate of {dup_result.matching_document} "
                    f"in deal {dup_result.matching_deal_id}."
                )

            register_hash(
                doc_path,
                hash_registry_path,
                deal_id=self.deal_scope.deal_id,
                document_type=classification.document_type,
            )

        # ---- Readability -------------------------------------------------------
        readability = self._check_readability(doc_path)
        if not readability["is_readable"]:
            issues.append("Document is not readable (empty or too small).")
        if not readability["encoding_ok"]:
            issues.append("Document has encoding issues.")

        # ---- Quality score (0-10) -----------------------------------------------
        quality_score = self._compute_quality_score(
            classification, is_duplicate, readability, issues,
        )

        return {
            "classification": {
                "document_type": classification.document_type,
                "confidence": classification.confidence,
                "matched_patterns": classification.matched_patterns,
            },
            "content_hash": content_hash,
            "is_duplicate": is_duplicate,
            "duplicate_info": duplicate_info,
            "readability": readability,
            "quality_score": round(quality_score, 2),
            "issues": issues,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_documents(self, task: dict[str, Any]) -> list[Path]:
        if "documents" in task and task["documents"]:
            return [Path(p) for p in task["documents"]]
        return self.deal_scope.list_documents()

    @staticmethod
    def _check_readability(doc_path: Path) -> dict[str, Any]:
        result: dict[str, Any] = {
            "size_bytes": 0,
            "is_readable": False,
            "encoding_ok": False,
        }
        if not doc_path.exists():
            return result

        result["size_bytes"] = doc_path.stat().st_size
        if result["size_bytes"] < _MIN_FILE_SIZE_BYTES:
            return result

        try:
            doc_path.read_text(encoding="utf-8")
            result["is_readable"] = True
            result["encoding_ok"] = True
        except UnicodeDecodeError:
            result["is_readable"] = True
            result["encoding_ok"] = False

        return result

    @staticmethod
    def _compute_quality_score(
        classification: ClassificationResult,
        is_duplicate: bool,
        readability: dict[str, Any],
        issues: list[str],
    ) -> float:
        score = 0.0
        score += min(classification.confidence, 1.0) * 4.0
        if readability["is_readable"]:
            score += 2.0
        if readability["encoding_ok"]:
            score += 1.0
        if not is_duplicate:
            score += 2.0
        if not issues:
            score += 1.0
        return min(score, 10.0)

    def _save_quality_report(
        self,
        assessments: dict[str, Any],
        summary: dict[str, Any],
    ) -> None:
        report_dir = self.deal_scope.resolve("reports")
        report_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
        report_path = report_dir / f"document_quality_{ts}.json"
        report_path.write_text(
            json.dumps({"documents": assessments, "summary": summary}, indent=2, default=str),
            encoding="utf-8",
        )
        self._state["last_quality_report"] = str(report_path)

    # ------------------------------------------------------------------
    # Quality gate overrides
    # ------------------------------------------------------------------

    def _score_completeness(self, result: Any, task: dict) -> float:
        expected = len(self._resolve_documents(task))
        actual = len(result.get("documents", {}))
        if expected == 0:
            return 10.0
        ratio = actual / expected
        return min(ratio * 10.0, 10.0)

    def _score_accuracy(self, result: Any, task: dict) -> float:
        docs = result.get("documents", {})
        if not docs:
            return 10.0
        total_conf = sum(
            d["classification"]["confidence"] for d in docs.values()
        )
        avg_conf = total_conf / len(docs)
        issue_count = sum(1 for d in docs.values() if d["issues"])
        issue_penalty = min(issue_count / len(docs) * 3.0, 3.0)
        return min(max(avg_conf * 10.0 - issue_penalty, 0.0), 10.0)

    def _score_confidence(self, result: Any, task: dict[str, Any]) -> ConfidenceScore:
        docs = result.get("documents", {})
        if not docs:
            return ConfidenceScore(1.0, ConfidenceTier.HIGH, "No documents to assess.")
        avg = sum(
            d["classification"]["confidence"] for d in docs.values()
        ) / len(docs)
        tier = self._categorize_confidence(avg)
        return ConfidenceScore(
            value=round(avg, 4),
            tier=tier,
            reasoning=(
                f"Average classification confidence across {len(docs)} documents."
            ),
        )

    def _get_artifacts(self, result: Any) -> list[str]:
        return [self._state.get("last_quality_report", "")]
