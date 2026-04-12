"""
DealScope — Deal boundary enforcer.
Every file, vector, and graph operation passes through DealScope.
Prevents cross-deal data contamination.
Ported from AI Payment Generator pipeline.deal_scope.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class DealScopingViolation(Exception):
    """Raised when an operation attempts to escape deal boundaries."""
    pass


class DealScope:
    """
    Enforces deal boundary for all file, vector, and graph operations.

    Every agent, skill, and pipeline stage receives a DealScope instance
    and must use scope.resolve() for any path operations.

    Usage:
        scope = DealScope.create("bear_stearns_2006_he2", Path("deals"))
        path = scope.resolve("sections/definitions.md")
        collection = scope.get_vector_collection()
    """

    REQUIRED_SUBDIRS = [
        "documents/psa/source",
        "documents/psa/sections",
        "documents/psa/extractions",
        "documents/supplementary/source",
        "documents/supplementary/sections",
        "documents/supplementary/extractions",
        "data",
        "vectorstore",
        "graph",
        "governing_docs",
        "runs",
        "logs",
        "reports",
        "versions",
    ]

    def __init__(
        self,
        deal_id: str,
        deals_root: Path,
        read_only: bool = False,
    ):
        if not deal_id or not deal_id.strip():
            raise ValueError("deal_id cannot be empty")

        self.deal_id = deal_id.strip()
        self.deals_root = Path(deals_root).resolve()
        self.deal_path = self.deals_root / self.deal_id
        self.read_only = read_only

    @classmethod
    def create(cls, deal_id: str, deals_root: Path) -> DealScope:
        """Create a writable DealScope. Creates the deal folder if needed."""
        scope = cls(deal_id, deals_root, read_only=False)
        scope.ensure_dirs()
        return scope

    @classmethod
    def create_read_only(cls, deal_id: str, deals_root: Path) -> DealScope:
        """Create a read-only DealScope for cross-deal access."""
        scope = cls(deal_id, deals_root, read_only=True)
        if not scope.deal_path.exists():
            raise FileNotFoundError(
                f"Deal folder not found: {scope.deal_path}. "
                f"Cannot create read-only scope for non-existent deal."
            )
        return scope

    def resolve(self, relative_path: str) -> Path:
        """Resolve a path within the deal folder with escape prevention."""
        resolved = (self.deal_path / relative_path).resolve()
        try:
            resolved.relative_to(self.deal_path)
        except ValueError:
            raise DealScopingViolation(
                f"Path escape detected: '{relative_path}' resolves to "
                f"'{resolved}' which is outside deal boundary '{self.deal_path}'"
            )
        return resolved

    def get_vector_collection(self) -> str:
        """Returns the Chroma collection name for this deal."""
        sanitized = self.deal_id.replace("-", "_").replace(" ", "_")
        if len(sanitized) < 3:
            sanitized = sanitized + "_deal"
        if len(sanitized) > 63:
            sanitized = sanitized[:63]
        return sanitized

    def get_graph_path(self) -> Path:
        """Returns: Path to deal_graph.json within deal folder."""
        return self.resolve("graph/deal_graph.json")

    def get_vectorstore_dir(self) -> Path:
        """Return the preferred vectorstore directory for this deal."""
        preferred = self.resolve("vectorstore")
        legacy = self.resolve("vectors")
        if preferred.exists():
            return preferred
        if legacy.exists():
            return legacy
        return preferred

    def get_psa_sections_dir(self) -> Path:
        """Return PSA sections directory (canonical, with legacy fallback)."""
        preferred = self.resolve("documents/psa/sections")
        legacy = self.resolve("sections")
        if preferred.exists():
            return preferred
        if legacy.exists():
            return legacy
        return preferred

    def get_psa_extractions_dir(self) -> Path:
        """Return PSA extractions directory (canonical, with legacy fallback)."""
        preferred = self.resolve("documents/psa/extractions")
        legacy = self.resolve("extractions")
        if preferred.exists():
            return preferred
        if legacy.exists():
            return legacy
        return preferred

    def get_manifest_path(self) -> Path:
        """Returns: Path to deal_manifest.json within deal folder."""
        return self.resolve("deal_manifest.json")

    def get_ingestion_manifest_path(self) -> Path:
        """Returns: Path to ingestion_manifest.json within deal folder."""
        return self.resolve("ingestion_manifest.json")

    def get_escalation_dir(self) -> Path:
        """Returns: Path to escalations directory within deal folder."""
        return self.resolve("logs/escalations")

    def ensure_dirs(self) -> None:
        """Create all required subdirectories for a deal folder."""
        if self.read_only:
            raise DealScopingViolation(
                f"Cannot create directories in read-only scope for deal '{self.deal_id}'"
            )
        self.deal_path.mkdir(parents=True, exist_ok=True)
        for subdir in self.REQUIRED_SUBDIRS:
            (self.deal_path / subdir).mkdir(parents=True, exist_ok=True)

    def exists(self) -> bool:
        """Check if the deal folder exists."""
        return self.deal_path.exists()

    def list_documents(self) -> list[Path]:
        """List source documents for this deal."""
        sources: list[Path] = []
        for source_dir in (
            self.deal_path / "documents" / "psa" / "source",
            self.deal_path / "documents" / "supplementary" / "source",
        ):
            if source_dir.exists():
                sources.extend([p for p in source_dir.iterdir() if p.is_file()])
        raw_dir = self.deal_path / "raw"
        if raw_dir.exists():
            sources.extend([p for p in raw_dir.iterdir() if p.is_file()])
        return sorted({p.resolve() for p in sources})

    def __repr__(self) -> str:
        mode = "RO" if self.read_only else "RW"
        return f"DealScope({self.deal_id}, {mode})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DealScope):
            return NotImplemented
        return self.deal_id == other.deal_id and self.deals_root == other.deals_root

    def __hash__(self) -> int:
        return hash((self.deal_id, self.deals_root))
