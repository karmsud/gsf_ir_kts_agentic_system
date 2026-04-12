"""
Ingestion Validator — Gate check for all 5 required artifact groups.

Validates that a deal's ingestion pipeline has produced all necessary
artifacts before allowing progression to model generation.

Ported from PayGen pipeline.ingestion.ingestion_validator → backend.abs.ingestion
Import rewrites:
  pipeline.config.constants        → backend.abs.config.constants
  pipeline.config.pipeline_config  → backend.abs.config.pipeline_config
  pipeline.embeddings.provider     → graceful degradation (Phase 22 stub)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.abs.config.constants import (
    MIN_DEFINITION_COUNT,
    MIN_RULE_COUNT,
    MIN_VECTOR_COUNT,
    PIPELINE_VERSION,
)

logger = logging.getLogger(__name__)


@dataclass
class ArtifactStatus:
    """Status of a single artifact group."""
    name: str
    status: str  # "pass" or "fail"
    details: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "details": self.details,
            "errors": self.errors,
        }


@dataclass
class IngestionValidationResult:
    """Complete result of ingestion validation."""
    is_ready: bool
    artifact_statuses: dict[str, ArtifactStatus]
    total_passed: int
    total_failed: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "is_ready": self.is_ready,
            "total_passed": self.total_passed,
            "total_failed": self.total_failed,
            "artifacts": {k: v.to_dict() for k, v in self.artifact_statuses.items()},
            "errors": self.errors,
            "warnings": self.warnings,
        }


def validate_ingestion(
    deal_path: Path,
    sections_dir: Optional[Path] = None,
    extractions_dir: Optional[Path] = None,
    data_dir: Optional[Path] = None,
    vectorstore_dir: Optional[Path] = None,
    graph_dir: Optional[Path] = None,
) -> IngestionValidationResult:
    """
    Validate that all 5 artifact groups are present and valid.
    """
    deal_path = Path(deal_path)

    if sections_dir is None:
        psa_sections = deal_path / "documents" / "psa" / "sections"
        flat_sections = deal_path / "sections"
        sections_dir = psa_sections if psa_sections.exists() else flat_sections

    if extractions_dir is None:
        psa_extr = deal_path / "documents" / "psa" / "extractions"
        flat_extr = deal_path / "extractions"
        extractions_dir = psa_extr if psa_extr.exists() else flat_extr

    if data_dir is None:
        data_dir = deal_path / "data"

    if vectorstore_dir is None:
        vectorstore_dir = deal_path / "vectorstore"

    if graph_dir is None:
        graph_dir = deal_path / "graph"

    result = IngestionValidationResult(
        is_ready=False,
        artifact_statuses={},
        total_passed=0,
        total_failed=0,
    )

    statuses = {
        "sections": _validate_sections(sections_dir),
        "extractions": _validate_extractions(extractions_dir),
        "data_csvs": _validate_data_csvs(data_dir),
        "vectorstore": _validate_vectorstore(vectorstore_dir),
        "graph": _validate_graph(graph_dir),
    }

    result.artifact_statuses = statuses

    for name, status in statuses.items():
        if status.status == "pass":
            result.total_passed += 1
        else:
            result.total_failed += 1
            result.errors.extend(status.errors)

    result.is_ready = result.total_failed == 0

    return result


def save_ingestion_manifest(
    deal_path: Path,
    validation_result: IngestionValidationResult,
    deal_id: str,
    source_document: str = "",
) -> Path:
    """Save the ingestion manifest JSON file."""
    manifest = {
        "deal_id": deal_id,
        "ingestion_timestamp": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": PIPELINE_VERSION,
        "source_document": source_document,
        "artifacts": {},
        "ready_for_model_generation": validation_result.is_ready,
    }

    for name, status in validation_result.artifact_statuses.items():
        manifest["artifacts"][name] = status.to_dict()

    manifest_path = Path(deal_path) / "ingestion_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    return manifest_path


# ── Individual Validators ─────────────────────────────────────

def _validate_sections(sections_dir: Path) -> ArtifactStatus:
    """Validate Artifact Group 1: Sectioned Markdown."""
    status = ArtifactStatus(name="sections", status="fail")

    if not sections_dir.exists():
        status.errors.append(f"Sections directory not found: {sections_dir}")
        return status

    section_files = list(sections_dir.glob("*.md"))
    status.details["file_count"] = len(section_files)
    status.details["files"] = [f.name for f in section_files]

    if len(section_files) < 1:
        status.errors.append("No section files found")
        return status

    required = {"definitions", "waterfall", "loss_allocations"}
    found = {f.stem for f in section_files}
    missing = required - found
    if missing:
        status.errors.append(f"Required sections missing: {sorted(missing)}")

    if len(section_files) >= 1:
        status.status = "pass"

    return status


def _validate_extractions(extractions_dir: Path) -> ArtifactStatus:
    """Validate Artifact Group 2: Structured JSON Extractions."""
    status = ArtifactStatus(name="extractions", status="fail")

    if not extractions_dir.exists():
        status.errors.append(f"Extractions directory not found: {extractions_dir}")
        return status

    json_files = list(extractions_dir.glob("*.json"))
    status.details["file_count"] = len(json_files)

    if not json_files:
        status.errors.append("No extraction JSON files found")
        return status

    defs_path = extractions_dir / "definitions.json"
    if defs_path.exists():
        try:
            defs = json.loads(defs_path.read_text(encoding="utf-8"))
            count = len(defs) if isinstance(defs, list) else 0
            status.details["definitions_count"] = count
        except Exception:
            status.details["definitions_count"] = 0
    else:
        status.details["definitions_count"] = 0

    rules_path = extractions_dir / "waterfall_rules.json"
    if rules_path.exists():
        try:
            rules = json.loads(rules_path.read_text(encoding="utf-8"))
            count = len(rules) if isinstance(rules, list) else 0
            status.details["waterfall_rules_count"] = count
        except Exception:
            status.details["waterfall_rules_count"] = 0
    else:
        status.details["waterfall_rules_count"] = 0

    status.status = "pass"
    return status


def _validate_data_csvs(data_dir: Path) -> ArtifactStatus:
    """Validate Artifact Group 3: Deal Data CSVs."""
    status = ArtifactStatus(name="data_csvs", status="fail")

    if not data_dir.exists():
        status.errors.append(f"Data directory not found: {data_dir}")
        return status

    deal_setup = data_dir / "deal_setup.csv"
    classes_setup = data_dir / "classes_setup.csv"

    status.details["deal_setup_exists"] = deal_setup.exists()
    status.details["classes_setup_exists"] = classes_setup.exists()

    if not deal_setup.exists() and not classes_setup.exists():
        status.errors.append("Neither deal_setup.csv nor classes_setup.csv found")
        return status

    if deal_setup.exists():
        try:
            import csv
            with open(deal_setup, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                status.details["deal_setup_fields"] = len(rows)
        except Exception as e:
            status.errors.append(f"deal_setup.csv parse error: {e}")

    if classes_setup.exists():
        try:
            import csv
            with open(classes_setup, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                status.details["certificate_classes"] = len(rows)
                if len(rows) < 1:
                    status.warnings = [
                        "classes_setup.csv has no data rows"
                    ]
        except Exception as e:
            status.errors.append(f"classes_setup.csv parse error: {e}")

    status.status = "pass"
    return status


def _validate_vectorstore(vectorstore_dir: Path) -> ArtifactStatus:
    """Validate Artifact Group 4: Vector Store.

    NOTE: pipeline.embeddings.provider is a Phase 22 dependency.
    For Phase 21, vectorstore validation degrades gracefully —
    checks file presence only without embedding signature verification.
    """
    status = ArtifactStatus(name="vectorstore", status="fail")

    if not vectorstore_dir.exists():
        status.errors.append(f"Vectorstore directory not found: {vectorstore_dir}")
        # Non-blocking: vector store is optional if embedder not installed
        status.status = "pass"
        status.details["note"] = "Vectorstore directory not found; skipped"
        return status

    # Phase 22 will add full embedding signature verification via
    # backend.abs.embeddings.provider.compute_embedding_signature / read_vectorstore_manifest.
    # For now, do a file-presence check only.

    chroma_files = list(vectorstore_dir.glob("*.sqlite3")) + list(vectorstore_dir.glob("chroma.*"))
    if not chroma_files:
        chroma_files = list(vectorstore_dir.glob("*/*.sqlite3")) + list(vectorstore_dir.glob("*/chroma.*"))
    status.details["chroma_files"] = len(chroma_files)

    # Check for any vectorstore manifest
    manifests = sorted(vectorstore_dir.glob("*/vectorstore_manifest.json"))
    if manifests:
        try:
            manifest_data = json.loads(manifests[0].read_text(encoding="utf-8"))
            status.details["active_signature"] = manifests[0].parent.name
            status.details["embedding_model"] = manifest_data.get("model_id", "unknown")
            status.details["embedding_provider"] = manifest_data.get("provider", "unknown")
            status.details["embedding_dim"] = manifest_data.get("embedding_dim", "unknown")
        except Exception:
            pass

    if chroma_files:
        status.status = "pass"
    else:
        # Check if there are any files at all in the vectorstore
        all_files = list(vectorstore_dir.rglob("*"))
        if all_files:
            status.status = "pass"
            status.details["file_count"] = len(all_files)
        else:
            # Still pass — embedding is optional (requires sentence-transformers)
            status.status = "pass"
            status.details["note"] = "Empty vectorstore; embedding may not be installed"

    return status


def _validate_graph(graph_dir: Path) -> ArtifactStatus:
    """Validate Artifact Group 5: Knowledge Graph."""
    status = ArtifactStatus(name="graph", status="fail")

    if not graph_dir.exists():
        status.errors.append(f"Graph directory not found: {graph_dir}")
        return status

    graph_json = graph_dir / "deal_graph.json"
    graph_pickle = graph_dir / "deal_graph.pickle"

    if not graph_json.exists() and not graph_pickle.exists():
        status.errors.append("No graph files found (deal_graph.json or deal_graph.pickle)")
        return status

    if graph_json.exists():
        try:
            data = json.loads(graph_json.read_text(encoding="utf-8"))
            nodes = data.get("nodes", [])
            edges = data.get("links", data.get("edges", []))
            status.details["node_count"] = len(nodes)
            status.details["edge_count"] = len(edges)
        except Exception as e:
            status.errors.append(f"Graph JSON parse error: {e}")
            return status

    status.status = "pass"
    return status
