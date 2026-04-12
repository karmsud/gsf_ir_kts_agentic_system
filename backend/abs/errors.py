"""
Error hierarchy for the ABS Waterfall AI pipeline.
All exceptions inherit from BaseWaterfallError.
Ported from AI Payment Generator pipeline.errors.
"""

from __future__ import annotations

import datetime
import functools
import json
import time
import traceback
from pathlib import Path
from typing import Any, Optional


# =============================================================================
# Base Exception
# =============================================================================

class BaseWaterfallError(Exception):
    """Base exception for all pipeline errors."""

    def __init__(
        self,
        message: str,
        agent: str = "",
        deal_id: str = "",
        context: dict[str, Any] | None = None,
        recoverable: bool = False,
    ):
        self.message = message
        self.agent = agent
        self.deal_id = deal_id
        self.context = context or {}
        self.recoverable = recoverable
        super().__init__(self.format())

    def format(self) -> str:
        parts = [self.message]
        if self.agent:
            parts.append(f"agent={self.agent}")
        if self.deal_id:
            parts.append(f"deal={self.deal_id}")
        return " | ".join(parts)

    def to_dict(self) -> dict:
        return {
            "error_type": type(self).__name__,
            "message": self.message,
            "agent": self.agent,
            "deal_id": self.deal_id,
            "context": self.context,
            "recoverable": self.recoverable,
        }


# =============================================================================
# Scoping Errors
# =============================================================================

class ScopingError(BaseWaterfallError):
    """Base class for deal scoping errors."""
    pass


class DealScopingViolation(ScopingError):
    """Raised when an operation attempts to escape deal boundaries."""
    pass


# =============================================================================
# Extraction Errors
# =============================================================================

class ExtractionError(BaseWaterfallError):
    """Base class for extraction-related errors."""
    pass


class SectionNotFoundError(ExtractionError):
    """Required section not found in document."""
    def __init__(self, section_name: str, **kwargs):
        super().__init__(
            message=f"Required section not found: '{section_name}'",
            recoverable=True,
            **kwargs,
        )
        self.section_name = section_name


class ParserError(ExtractionError):
    """Regex/LLM parser failure."""
    def __init__(self, parser_name: str, message: str = "", **kwargs):
        super().__init__(
            message=f"{parser_name}: {message}" if message else f"{parser_name} failed",
            recoverable=True,
            **kwargs,
        )
        self.parser_name = parser_name


class EmptyExtractionError(ExtractionError):
    """Parser returned zero results."""
    def __init__(self, parser_name: str, **kwargs):
        super().__init__(
            message=f"{parser_name} returned 0 results",
            recoverable=True,
            **kwargs,
        )
        self.parser_name = parser_name


# =============================================================================
# Ingestion Errors
# =============================================================================

class IngestionError(BaseWaterfallError):
    """Base class for ingestion-related errors."""
    pass


class DocumentClassificationError(IngestionError):
    """Cannot determine document type."""
    def __init__(self, filename: str, **kwargs):
        super().__init__(
            message=f"Cannot classify document: '{filename}'",
            recoverable=True,
            **kwargs,
        )
        self.filename = filename


class DuplicateDocumentError(IngestionError):
    """Document has already been ingested."""
    def __init__(self, filename: str, match_type: str = "exact", **kwargs):
        super().__init__(
            message=f"Duplicate document detected ({match_type}): '{filename}'",
            recoverable=False,
            **kwargs,
        )
        self.filename = filename
        self.match_type = match_type


class HashMismatchError(IngestionError):
    """Re-ingestion content mismatch."""
    def __init__(self, filename: str, **kwargs):
        super().__init__(
            message=f"Content hash mismatch on re-ingestion: '{filename}'",
            recoverable=False,
            **kwargs,
        )


class SectionSplitError(IngestionError):
    """Section splitter failure."""
    def __init__(self, message: str = "Section splitting failed", **kwargs):
        super().__init__(message=message, recoverable=True, **kwargs)


# =============================================================================
# Vector Errors
# =============================================================================

class VectorError(BaseWaterfallError):
    """Base class for vector store errors."""
    pass


class ChromaConnectionError(VectorError):
    """Chroma DB unreachable."""
    def __init__(self, **kwargs):
        super().__init__(
            message="Cannot connect to Chroma DB",
            recoverable=True,
            **kwargs,
        )


class EmbeddingError(VectorError):
    """Sentence-transformers failure."""
    def __init__(self, message: str = "Embedding generation failed", **kwargs):
        super().__init__(message=message, recoverable=True, **kwargs)


class CollectionNotFoundError(VectorError):
    """No Chroma collection for this deal."""
    def __init__(self, collection_name: str, **kwargs):
        super().__init__(
            message=f"Chroma collection not found: '{collection_name}'",
            recoverable=False,
            **kwargs,
        )


# =============================================================================
# Graph Errors
# =============================================================================

class GraphError(BaseWaterfallError):
    """Base class for graph-related errors."""
    pass


class GraphBuildError(GraphError):
    """NetworkX graph construction failure."""
    def __init__(self, message: str = "Graph construction failed", **kwargs):
        super().__init__(message=message, recoverable=False, **kwargs)


class GraphQueryError(GraphError):
    """Graph traversal failure."""
    def __init__(self, term: str, **kwargs):
        super().__init__(
            message=f"Graph query failed for term: '{term}'",
            recoverable=False,
            **kwargs,
        )


# =============================================================================
# Validation Errors
# =============================================================================

class ValidationError(BaseWaterfallError):
    """Base class for validation-related errors."""
    pass


class CSVSchemaError(ValidationError):
    """CSV does not match expected schema."""
    def __init__(self, csv_name: str, errors: list[str], **kwargs):
        super().__init__(
            message=f"CSV schema validation failed for '{csv_name}': {'; '.join(errors[:3])}",
            recoverable=False,
            **kwargs,
        )
        self.csv_name = csv_name
        self.schema_errors = errors


class OutputMismatchError(ValidationError):
    """Model output differs from expected."""
    def __init__(self, max_diff: float, **kwargs):
        super().__init__(
            message=f"Model output mismatch: max_diff=${max_diff:.4f}",
            recoverable=False,
            **kwargs,
        )
        self.max_diff = max_diff


class QualityGateError(ValidationError):
    """Quality gate check failed."""
    def __init__(self, scores: dict, **kwargs):
        super().__init__(
            message=f"Quality gate failed: {scores}",
            recoverable=True,
            **kwargs,
        )
        self.scores = scores


# =============================================================================
# Generation Errors
# =============================================================================

class GenerationError(BaseWaterfallError):
    """Base class for generation-related errors."""
    pass


class ModelGenerationError(GenerationError):
    """Payment model creation failure."""
    def __init__(self, message: str = "Payment model generation failed", **kwargs):
        super().__init__(message=message, recoverable=True, **kwargs)


class GoverningDocError(GenerationError):
    """Governing document generation failure."""
    def __init__(self, section: str, **kwargs):
        super().__init__(
            message=f"Governing doc generation failed for section: '{section}'",
            recoverable=True,
            **kwargs,
        )
        self.section = section


class TemplateError(GenerationError):
    """Template rendering failure."""
    def __init__(self, template_name: str, **kwargs):
        super().__init__(
            message=f"Template rendering failed: '{template_name}'",
            recoverable=False,
            **kwargs,
        )


# =============================================================================
# Comparison Errors
# =============================================================================

class ComparisonError(BaseWaterfallError):
    """Base class for comparison-related errors."""
    pass


class DealNotFoundError(ComparisonError):
    """Deal not found for comparison."""
    def __init__(self, deal_id: str, **kwargs):
        super().__init__(
            message=f"Deal not found: '{deal_id}'",
            recoverable=False,
            **kwargs,
        )


# =============================================================================
# Escalation Errors
# =============================================================================

class EscalationError(BaseWaterfallError):
    """Base class for escalation-related errors."""
    pass


class EscalationRequired(EscalationError):
    """Agent blocked, needs human review."""
    def __init__(self, report: dict, **kwargs):
        super().__init__(
            message=f"Escalation required: {report.get('root_blocker', 'unknown')}",
            recoverable=False,
            **kwargs,
        )
        self.report = report


# =============================================================================
# Configuration Errors
# =============================================================================

class ConfigurationError(BaseWaterfallError):
    """Base class for configuration errors."""
    pass


class MissingConfigError(ConfigurationError):
    """Required config file missing."""
    def __init__(self, config_name: str, **kwargs):
        super().__init__(
            message=f"Required configuration missing: '{config_name}'",
            recoverable=False,
            **kwargs,
        )


class InvalidSchemaError(ConfigurationError):
    """Config schema validation failed."""
    def __init__(self, schema_name: str, errors: list[str], **kwargs):
        super().__init__(
            message=f"Schema validation failed for '{schema_name}': {'; '.join(errors[:3])}",
            recoverable=False,
            **kwargs,
        )


# =============================================================================
# Structured Error Logger
# =============================================================================

class StructuredErrorLogger:
    """JSON-lines error logger per deal."""

    def __init__(self, deal_path: Path):
        self.log_path = deal_path / "logs" / "errors.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_error(self, error: BaseWaterfallError, stack_trace: str = "") -> None:
        """Log an error as structured JSON."""
        entry = error.to_dict()
        entry["timestamp"] = datetime.datetime.now(datetime.UTC).isoformat()
        entry["level"] = "ERROR"
        entry["stack_trace"] = stack_trace or traceback.format_exc()
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def log_warning(
        self,
        agent: str,
        deal_id: str,
        message: str,
        context: dict | None = None,
    ) -> None:
        """Log a warning as structured JSON."""
        entry = {
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "level": "WARNING",
            "error_type": "Warning",
            "agent": agent,
            "deal_id": deal_id,
            "message": message,
            "context": context or {},
            "recoverable": True,
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read_errors(self) -> list[dict]:
        """Read all logged errors."""
        if not self.log_path.exists():
            return []
        errors = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    errors.append(json.loads(line))
        return errors


# =============================================================================
# Retry Decorator
# =============================================================================

def with_retry(
    max_retries: int = 3,
    backoff_seconds: float = 0.0,
    exponential: bool = False,
    on_retry: Any = None,
):
    """
    Retry decorator for recoverable errors.

    Args:
        max_retries: Maximum retry attempts
        backoff_seconds: Base wait between retries
        exponential: If True, backoff doubles each retry
        on_retry: Optional callback(exception, attempt) for logging
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except BaseWaterfallError as e:
                    if not e.recoverable or attempt == max_retries:
                        raise
                    last_exc = e
                    if on_retry:
                        on_retry(e, attempt + 1)
                    if backoff_seconds > 0:
                        wait = backoff_seconds * (2 ** attempt if exponential else 1)
                        time.sleep(wait)
            raise last_exc  # type: ignore
        return wrapper
    return decorator
