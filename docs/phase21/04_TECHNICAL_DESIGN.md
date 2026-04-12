# Phase 21: Technical Design
## Implementation-Ready Specifications

**Document Version:** 1.0  
**Date:** February 26, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** Complete implementation specifications with file paths and code

---

## Table of Contents
1. [Overview](#overview)
2. [File Structure](#file-structure)
3. [AgentBase Merge Implementation](#agentbase-merge-implementation)
4. [Quality Gate Merge Implementation](#quality-gate-merge-implementation)
5. [DealScope Implementation](#dealscope-implementation)
6. [DealManifest Implementation](#dealmanifest-implementation)
7. [Error Hierarchy Implementation](#error-hierarchy-implementation)
8. [ABS Config Implementation](#abs-config-implementation)
9. [Temporary Stubs](#temporary-stubs)
10. [Init Files](#init-files)
11. [KTSConfig Additions](#ktsconfig-additions)

---

## Overview

This document provides complete, production-ready specifications for Phase 21 implementation. Every file change includes:
- Exact file path
- Full code or diff
- Import statements
- Type hints and docstrings

---

## File Structure

### New Files Created

```
backend/
├── abs/
│   ├── __init__.py                              NEW  (~30 lines)
│   ├── deal_scope.py                            COPY+ADAPT  (~260 lines)
│   ├── deal_manifest.py                         COPY+ADAPT  (~260 lines)
│   ├── errors.py                                COPY  (~464 lines)
│   ├── agents/
│   │   ├── __init__.py                          NEW  (~30 lines)
│   │   ├── cashflow_projection_agent.py         COPY+REWRITE  
│   │   ├── deal_amendment_agent.py              COPY+REWRITE
│   │   ├── deal_lifecycle_agent.py              COPY+REWRITE
│   │   ├── document_comparison_agent.py         COPY+REWRITE
│   │   ├── document_quality_agent.py            COPY+REWRITE
│   │   ├── ingestion_pipeline_agent.py          COPY+REWRITE
│   │   ├── investor_reporting_agent.py          COPY+REWRITE
│   │   ├── model_auditor_agent.py               COPY+REWRITE
│   │   ├── model_creation_agent.py              COPY+REWRITE
│   │   ├── qa_agent.py                          COPY+REWRITE
│   │   ├── regression_testing_agent.py          COPY+REWRITE
│   │   └── stress_testing_agent.py              COPY+REWRITE
│   ├── skills/
│   │   ├── __init__.py                          NEW
│   │   ├── amendment_manager.py                 COPY+REWRITE
│   │   ├── cashflow_engine.py                   COPY  (557 lines, pure domain)
│   │   ├── csv_validator.py                     COPY+REWRITE
│   │   ├── deal_comparator.py                   COPY+REWRITE
│   │   ├── deal_setup_extractor.py              COPY+REWRITE
│   │   ├── document_classifier.py               COPY+REWRITE
│   │   ├── document_hasher.py                   COPY+REWRITE
│   │   ├── document_tools.py                    COPY+REWRITE
│   │   ├── embedder.py                          STUB  (Phase 22 replacement)
│   │   ├── graph_builder.py                     STUB  (Phase 22 replacement)
│   │   ├── output_comparator.py                 COPY+REWRITE
│   │   ├── parsers.py                           COPY  (pure text, no deps)
│   │   ├── report_generator.py                  COPY+REWRITE
│   │   └── vector_search.py                     STUB  (Phase 22 replacement)
│   ├── generation/
│   │   ├── __init__.py                          NEW
│   │   ├── data_prep.py                         COPY+REWRITE
│   │   ├── model_runner.py                      COPY+REWRITE
│   │   └── model_validator.py                   COPY+REWRITE
│   ├── ingestion/
│   │   ├── __init__.py                          NEW
│   │   ├── definition_resolution.py             COPY+REWRITE
│   │   ├── document_converter.py                COPY+REWRITE
│   │   ├── document_intelligence.py             COPY+REWRITE
│   │   ├── governing_doc_generator.py           COPY+REWRITE  (931 lines)
│   │   ├── ingestion_validator.py               COPY+REWRITE
│   │   ├── knowledge_store.py                   COPY+REWRITE
│   │   ├── pipeline_runner.py                   COPY+REWRITE
│   │   ├── section_splitter.py                  COPY+REWRITE
│   │   └── structured_extractor.py              COPY+REWRITE
│   └── config/
│       ├── __init__.py                          NEW
│       ├── constants.py                         COPY
│       ├── schemas.py                           COPY
│       └── section_maps.py                      COPY
├── agents/
│   ├── base_agent.py                            MODIFIED  (~450 lines, merged)
│   └── agent_tools.py                           NEW  (168 lines from PayGen)
└── common/
    ├── quality_gate.py                          MODIFIED  (PayGen's 5-dim version)
    ├── confidence.py                            NEW  (from PayGen)
    ├── escalation.py                            MODIFIED  (PayGen additions)
    ├── output_contracts.py                      NEW  (from PayGen)
    ├── pre_mortem.py                            NEW  (from PayGen)
    └── refine_loop.py                           NEW  (from PayGen)
```

### Files Modified

```
config/
└── settings.py                                  MODIFIED  (add ~20 abs_* properties)
```

---

## AgentBase Merge Implementation

**File:** `backend/agents/base_agent.py`  
**Action:** Replace entire file content  
**Source:** See `03_ARCHITECTURE_UPGRADE.md` Section "Proposed: Merged AgentBase" for complete code (~450 lines)

### Key Decisions

1. **`_run()` is the only required abstract method.** All other methods (`_get_mission`, `_get_actions`, etc.) have default implementations returning safe no-op values.

2. **`execute()` returns `AgentOutput` (not `AgentResult`).** Existing KTS agents that call `quality_check()` continue using `AgentResult`. The `quality_check()` method is preserved as a backward-compatibility wrapper.

3. **State persistence uses `deal_scope`.** If `deal_scope is None` (KTS agents), `_load_state()` returns `{}` and `_save_state()` is a no-op.

### Existing KTS Agent Compatibility Check

For each of the 15 existing KTS agents, verify:

```python
# Pattern to verify for each agent:
class SomeKTSAgent(AgentBase):
    def __init__(self, config: KTSConfig):
        # Must call: super().__init__("name", config)
        super().__init__("agent-name", config)
    
    def execute(self, request: dict) -> AgentResult:
        # This still works — AgentResult is still accepted
        ...
```

If any KTS agent overrides `execute()` directly (returning `AgentResult`), it continues to work — Python doesn't enforce return type annotations at runtime.

---

## Quality Gate Merge Implementation

**File:** `backend/common/quality_gate.py`  
**Action:** Replace content with PayGen's 5-dimension version + backward-compat wrapper

```python
"""
Unified Quality Gate — 5-dimension scoring.

Replaces the original 63-line simple threshold gate.
Preserves the legacy apply(result) interface for backward compatibility.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from config.settings import KTSConfig

logger = logging.getLogger(__name__)


class QualityDimension:
    COMPLETENESS = "completeness"
    ACCURACY = "accuracy"
    CITATION_FIDELITY = "citation_fidelity"
    STRUCTURAL_CONFORMANCE = "structural_conformance"
    DEAL_SCOPE_COMPLIANCE = "deal_scope_compliance"


@dataclass
class QualityResult:
    passed: bool
    scores: dict[str, float] = field(default_factory=dict)
    retry_count: int = 0
    feedback: str = ""


class QualityGate:
    """5-dimension quality evaluation gate.
    
    Used by both KTS agents (via legacy apply()) and ABS agents 
    (via 5-dimension evaluate()).
    """

    DIMENSIONS = [
        QualityDimension.COMPLETENESS,
        QualityDimension.ACCURACY,
        QualityDimension.CITATION_FIDELITY,
        QualityDimension.STRUCTURAL_CONFORMANCE,
        QualityDimension.DEAL_SCOPE_COMPLIANCE,
    ]

    def __init__(self, config: KTSConfig):
        self.config = config
        self.confidence_high = config.confidence_high
        self.confidence_medium = config.confidence_medium
        # ABS-specific threshold (defaults to 8.0)
        self.min_score = getattr(config, 'abs_min_quality_score', 8.0)

    def apply(self, result) -> Any:
        """Legacy KTS interface — simple confidence threshold.
        
        Preserves backward compatibility with existing KTS agents
        that call quality_check(result).
        """
        confidence = getattr(result, 'confidence', 0.0)
        if confidence >= self.confidence_high:
            result.quality_tier = "high"
        elif confidence >= self.confidence_medium:
            result.quality_tier = "medium"
        else:
            result.quality_tier = "low"
        return result

    def evaluate(
        self,
        result: Any,
        task: dict,
        scorers: Optional[dict] = None,
    ) -> QualityResult:
        """Full 5-dimension quality evaluation (ABS interface).
        
        Args:
            result: Agent execution result
            task: Original task dict
            scorers: Optional dict of dimension -> scoring function
                     Each function: (result, task) -> float (0-10)
        """
        scores = {}
        for dim in self.DIMENSIONS:
            if scorers and dim in scorers:
                scores[dim] = scorers[dim](result, task)
            else:
                scores[dim] = 8.0  # default safe score

        avg = sum(scores.values()) / len(scores)
        passed = avg >= self.min_score

        feedback = ""
        if not passed:
            low_dims = [d for d, s in scores.items() if s < self.min_score]
            feedback = (
                f"Average score {avg:.1f} < {self.min_score}. "
                f"Low dimensions: {', '.join(low_dims)}"
            )

        return QualityResult(
            passed=passed,
            scores=scores,
            retry_count=0,
            feedback=feedback,
        )
```

### Additional Quality Modules

**File:** `backend/common/confidence.py`  
Copy from `pipeline/quality/confidence.py` with import rewrites.

**File:** `backend/common/output_contracts.py`  
Copy from `pipeline/quality/output_contracts.py` with import rewrites.

**File:** `backend/common/pre_mortem.py`  
Copy from `pipeline/quality/pre_mortem.py` with import rewrites.

**File:** `backend/common/refine_loop.py`  
Copy from `pipeline/quality/refine_loop.py` with import rewrites.

**File:** `backend/common/escalation.py`  
Merge PayGen's escalation logic into KTS's existing `escalation.py` (additive — new functions alongside existing ones).

---

## DealScope Implementation

**File:** `backend/abs/deal_scope.py`

Key adaptation: Constructor takes `KTSConfig` instead of `deals_root: Path`.

```python
"""
ABS Deal Scope — Filesystem isolation per deal.

Adapted from AI Payment Generator's pipeline/deal_scope.py.
Changed: Constructor takes KTSConfig; deals_root comes from config.abs_deals_root.
"""

from pathlib import Path
from typing import Optional
import logging

from config.settings import KTSConfig

logger = logging.getLogger(__name__)


class DealScopingViolation(Exception):
    """Attempt to access files outside deal directory."""
    pass


class DealScope:
    """Filesystem isolation for a single ABS deal.
    
    Manages directory structure:
        {deals_root}/{deal_id}/
            documents/psa/source/
            documents/psa/sections/
            documents/psa/extractions/
            data/
            vectorstore/
            graph/
            models/
            outputs/
            reports/
            escalations/
            governing_docs/
            amendments/
            manifest.json
    """

    REQUIRED_SUBDIRS = [
        "documents/psa/source",
        "documents/psa/sections",
        "documents/psa/extractions",
        "data",
        "vectorstore",
        "graph",
        "models",
        "outputs",
        "reports",
        "escalations",
        "governing_docs",
        "amendments",
    ]

    def __init__(self, deal_id: str, config: KTSConfig, read_only: bool = False):
        self.deal_id = deal_id
        self.deals_root = Path(config.abs_deals_root)
        self.deal_path = self.deals_root / deal_id
        self.read_only = read_only
        self._config = config

    @classmethod
    def create(cls, deal_id: str, config: KTSConfig) -> 'DealScope':
        """Create a writable deal scope, initializing directory structure."""
        scope = cls(deal_id, config, read_only=False)
        scope.ensure_dirs()
        return scope

    @classmethod
    def create_read_only(cls, deal_id: str, config: KTSConfig) -> 'DealScope':
        """Create a read-only deal scope."""
        return cls(deal_id, config, read_only=True)

    def resolve(self, relative_path: str) -> Path:
        """Resolve path within deal directory, preventing escapes."""
        resolved = (self.deal_path / relative_path).resolve()
        if not str(resolved).startswith(str(self.deal_path.resolve())):
            raise DealScopingViolation(
                f"Path escape detected: {relative_path} resolves outside {self.deal_path}"
            )
        return resolved

    def get_vector_collection(self) -> str:
        return f"abs_{self.deal_id}"

    def get_graph_path(self) -> Path:
        return self.deal_path / "graph" / "deal_graph.graphml"

    def get_vectorstore_dir(self) -> Path:
        canonical = self.deal_path / "vectorstore"
        if canonical.exists():
            return canonical
        legacy = self.deal_path / "chroma"
        if legacy.exists():
            return legacy
        return canonical

    def get_psa_sections_dir(self) -> Path:
        return self.deal_path / "documents" / "psa" / "sections"

    def get_psa_extractions_dir(self) -> Path:
        return self.deal_path / "documents" / "psa" / "extractions"

    def get_manifest_path(self) -> Path:
        return self.deal_path / "manifest.json"

    def get_ingestion_manifest_path(self) -> Path:
        return self.deal_path / "ingestion_manifest.json"

    def get_escalation_dir(self) -> Path:
        return self.deal_path / "escalations"

    def ensure_dirs(self) -> None:
        """Create all required subdirectories."""
        if self.read_only:
            raise DealScopingViolation("Cannot create dirs in read-only scope")
        for subdir in self.REQUIRED_SUBDIRS:
            (self.deal_path / subdir).mkdir(parents=True, exist_ok=True)

    def exists(self) -> bool:
        return self.deal_path.exists()

    def list_documents(self) -> list[Path]:
        """List all source documents."""
        source_dir = self.deal_path / "documents" / "psa" / "source"
        if source_dir.exists():
            return list(source_dir.iterdir())
        raw_dir = self.deal_path / "raw"
        if raw_dir.exists():
            return list(raw_dir.iterdir())
        return []
```

---

## DealManifest Implementation

**File:** `backend/abs/deal_manifest.py`

Copy from `pipeline/deal_manifest.py` with minimal changes:
- Import `from config.settings import KTSConfig` instead of `from pipeline.config.pipeline_config import get_config`
- No other structural changes needed — DealManifest is self-contained

---

## Error Hierarchy Implementation

**File:** `backend/abs/errors.py`

Copy from `pipeline/errors.py` (464 lines) with these import rewrites:
- `from pipeline.config.pipeline_config import get_config` → `from config.settings import load_config`
- All other imports are stdlib (json, logging, pathlib) — no changes needed

The `StructuredErrorLogger` writes JSON-lines to `{deal_scope.deal_path}/logs/errors.jsonl`.

---

## ABS Config Implementation

**File:** `backend/abs/config/constants.py`  
Copy verbatim from `pipeline/config/constants.py`.

**File:** `backend/abs/config/schemas.py`  
Copy verbatim from `pipeline/config/schemas.py`.

**File:** `backend/abs/config/section_maps.py`  
Copy verbatim from `pipeline/config/section_maps.py`.

---

## Temporary Stubs

Three modules are replaced by KTS infrastructure in Phase 22. In Phase 21, they exist as stubs to keep imports clean.

**File:** `backend/abs/skills/embedder.py`
```python
"""
Temporary stub — replaced by backend.vector.embedding_provider in Phase 22.

This file exists so that ABS modules importing embedder functions
can resolve imports during Phase 21. All functions raise NotImplementedError.
"""


def chunk_text(*args, **kwargs):
    raise NotImplementedError("Wired to KTS embedding_provider in Phase 22")


def embed(*args, **kwargs):
    raise NotImplementedError("Wired to KTS embedding_provider in Phase 22")


def upsert_to_chroma(*args, **kwargs):
    raise NotImplementedError("Wired to KTS embedding_provider in Phase 22")


def embed_and_store(*args, **kwargs):
    raise NotImplementedError("Wired to KTS embedding_provider in Phase 22")
```

**File:** `backend/abs/skills/graph_builder.py`
```python
"""
Temporary stub — replaced by backend.graph.enhanced_graph_builder in Phase 22.
"""


def build_graph(*args, **kwargs):
    raise NotImplementedError("Wired to KTS enhanced_graph_builder in Phase 22")


def save_graph(*args, **kwargs):
    raise NotImplementedError("Wired to KTS enhanced_graph_builder in Phase 22")


def load_graph(*args, **kwargs):
    raise NotImplementedError("Wired to KTS enhanced_graph_builder in Phase 22")


def query_graph(*args, **kwargs):
    raise NotImplementedError("Wired to KTS enhanced_graph_builder in Phase 22")
```

**File:** `backend/abs/skills/vector_search.py`
```python
"""
Temporary stub — replaced by backend.retrieval.retrieval_service in Phase 22.
"""

from dataclasses import dataclass


@dataclass
class SearchResult:
    text: str = ""
    score: float = 0.0
    metadata: dict = None


def vector_search(*args, **kwargs):
    raise NotImplementedError("Wired to KTS retrieval_service in Phase 22")


def search_by_section(*args, **kwargs):
    raise NotImplementedError("Wired to KTS retrieval_service in Phase 22")
```

---

## Init Files

**File:** `backend/abs/__init__.py`
```python
"""
ABS Domain Logic — Asset-Backed Securities Payment Model Generation.

Ported from AI Payment Generator project into KTS as a domain subpackage.
Uses KTS's shared infrastructure (vector, graph, retrieval, embedding).

Phase 21: Structure + imports
Phase 22: Infrastructure wiring + LLM
Phase 23: CLI + Extension + Packaging
"""

__version__ = "0.1.0"
```

**File:** `backend/abs/agents/__init__.py`
```python
"""ABS domain agents for payment model generation."""

from backend.abs.agents.cashflow_projection_agent import CashflowProjectionAgent
from backend.abs.agents.deal_amendment_agent import DealAmendmentAgent
from backend.abs.agents.deal_lifecycle_agent import DealLifecycleAgent
from backend.abs.agents.document_comparison_agent import DocumentComparisonAgent
from backend.abs.agents.document_quality_agent import DocumentQualityAgent
from backend.abs.agents.ingestion_pipeline_agent import IngestionPipelineAgent
from backend.abs.agents.investor_reporting_agent import InvestorReportingAgent
from backend.abs.agents.model_auditor_agent import ModelAuditorAgent
from backend.abs.agents.model_creation_agent import ModelCreationAgent
from backend.abs.agents.qa_agent import QAAgent
from backend.abs.agents.regression_testing_agent import RegressionTestingAgent
from backend.abs.agents.stress_testing_agent import StressTestingAgent

__all__ = [
    "CashflowProjectionAgent",
    "DealAmendmentAgent",
    "DealLifecycleAgent",
    "DocumentComparisonAgent",
    "DocumentQualityAgent",
    "IngestionPipelineAgent",
    "InvestorReportingAgent",
    "ModelAuditorAgent",
    "ModelCreationAgent",
    "QAAgent",
    "RegressionTestingAgent",
    "StressTestingAgent",
]
```

**File:** `backend/abs/skills/__init__.py`
```python
"""ABS domain skills — cashflow engine, parsers, validators."""
```

**File:** `backend/abs/generation/__init__.py`
```python
"""ABS payment model generation — data prep, model runner, validator."""
```

**File:** `backend/abs/ingestion/__init__.py`
```python
"""ABS document ingestion — converters, splitters, extractors."""
```

**File:** `backend/abs/config/__init__.py`
```python
"""ABS domain configuration — constants, schemas, section maps."""
```

---

## KTSConfig Additions

**File:** `config/settings.py`  
**Action:** Add `abs_*` properties to KTSConfig dataclass

```python
# Add to KTSConfig dataclass body, after existing phase properties:

# ── Phase 21: ABS Domain Integration ──
abs_enabled: bool = False
abs_deals_root: str = "deals"
abs_extraction_mode: str = "hybrid"           # "template" | "llm" | "hybrid"
abs_min_quality_score: float = 8.0
abs_max_retries: int = 3
abs_confidence_high: float = 0.90
abs_confidence_low: float = 0.66
abs_vectorstore_enabled: bool = True
abs_graph_enabled: bool = True
abs_embedding_dim: int = 768
abs_chunk_max_chars: int = 3000
abs_chunk_overlap: int = 500
abs_normalize_embeddings: bool = True
abs_definition_resolution_enabled: bool = True
abs_definition_resolution_depth: int = 5
abs_definition_resolution_confidence: float = 0.80
abs_output_tolerance: float = 0.01
abs_min_definitions: int = 10
abs_min_waterfall_rules: int = 5
abs_min_vectors: int = 50
```

Environment variable overrides follow existing pattern:
```
KTS_ABS_ENABLED=true
KTS_ABS_DEALS_ROOT=deals
KTS_ABS_EXTRACTION_MODE=hybrid
KTS_ABS_MIN_QUALITY_SCORE=8.0
...
```
