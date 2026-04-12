# Phase 21: Architecture Upgrade
## AgentBase Merge & Quality Infrastructure Unification

**Document Version:** 1.0  
**Date:** February 26, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** Detailed architecture transformations for agent framework and quality infrastructure

---

## Table of Contents
1. [Overview](#overview)
2. [AgentBase Evolution](#agentbase-evolution)
3. [Quality Infrastructure Merge](#quality-infrastructure-merge)
4. [ToolRegistry Integration](#toolregistry-integration)
5. [DealScope Adaptation](#dealscope-adaptation)
6. [DealManifest Adaptation](#dealmanifest-adaptation)
7. [Error Hierarchy Merge](#error-hierarchy-merge)
8. [Config Merge](#config-merge)
9. [Import Rewrite Map](#import-rewrite-map)

---

## Overview

Phase 21 involves three fundamental architecture transformations:

**Transformation 1: Agent Framework**
- FROM: Two incompatible AgentBase classes (KTS = 24 lines, PayGen = 414 lines)
- TO: Single enriched AgentBase serving both KTS and ABS agents

**Transformation 2: Quality Infrastructure**
- FROM: KTS = 63 lines / 2 modules; PayGen = 800 lines / 6 modules
- TO: Unified 5-dimension quality system in `backend/common/`

**Transformation 3: Domain Logic Packaging**
- FROM: Separate `pipeline/` package
- TO: `backend/abs/` subpackage with rewritten imports

---

## AgentBase Evolution

### Current State: Two Incompatible Bases

**KTS AgentBase** (`backend/agents/base_agent.py` — 24 lines):
```python
class AgentBase(ABC):
    agent_name: str = "base-agent"
    agent_version: str = "1.0.0"

    def __init__(self, config: KTSConfig):
        self.config = config
        self.quality_gate = QualityGate(config)

    @abstractmethod
    def execute(self, request: dict) -> AgentResult: ...

    def quality_check(self, result: AgentResult) -> AgentResult:
        return self.quality_gate.apply(result)
```

**PayGen AgentBase** (`pipeline/agents/agent_base.py` — 414 lines):
```python
class AgentBase(ABC):
    MAX_RETRIES = 3
    MIN_QUALITY_SCORE = 8.0

    def __init__(self, agent_name, deal_scope, tool_registry): ...
    
    # Structured prompt system (Decision D11)
    @property system_prompt -> str
    @abstractmethod _get_mission() -> str
    @abstractmethod _get_actions() -> list[str]
    @abstractmethod _get_output_spec() -> str
    @abstractmethod _get_validation_rules() -> list[str]
    
    # Quality-gated execution with retry
    def execute(self, task) -> AgentOutput
    @abstractmethod _run(self, task) -> Any
    
    # 5-dimension quality scoring
    def _evaluate_quality(result, task) -> QualityResult
    def _score_completeness(result, task) -> float     # default 8.0
    def _score_accuracy(result, task) -> float          # default 8.0
    def _score_citations(result, task) -> float         # default 8.0
    def _score_structure(result, task) -> float         # default 8.0
    def _score_scope(result, task) -> float             # default 10.0
    
    # Confidence scoring
    def _score_confidence(result, task) -> ConfidenceScore
    @staticmethod _categorize_confidence(score) -> ConfidenceTier
    
    # State persistence (Decision D12)
    def _load_state() -> dict
    def _save_state() -> None
    
    # Tool access
    def use_tool(tool_name, **kwargs) -> Any
    def available_tools() -> list[str]
```

### Proposed: Merged AgentBase

```python
"""
backend/agents/base_agent.py — MERGED (~450 lines)

Design decisions:
1. KTSConfig is required (all agents need config)
2. DealScope is optional (None for KTS agents, required for ABS agents)
3. ToolRegistry is optional (None for KTS agents, used by ABS agents)
4. All abstract methods have default implementations (backward compat)
5. execute() signature unified: accepts dict, returns AgentOutput
6. quality_check() wraps legacy KTS interface
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional
from pathlib import Path
import json, time, logging

from config.settings import KTSConfig
from backend.common.models import AgentResult
from backend.common.quality_gate import QualityGate

logger = logging.getLogger(__name__)


class ConfidenceTier(str, Enum):
    HIGH = "high"       # >= 90%
    MEDIUM = "medium"   # 66-89%
    LOW = "low"         # < 66%


class QualityDimension(str, Enum):
    COMPLETENESS = "completeness"
    ACCURACY = "accuracy"
    CITATION_FIDELITY = "citation_fidelity"
    STRUCTURAL_CONFORMANCE = "structural_conformance"
    DEAL_SCOPE_COMPLIANCE = "deal_scope_compliance"


class EscalationType(str, Enum):
    EXTRACTION_AMBIGUITY = "extraction_ambiguity"
    CONFIDENCE_LOW = "confidence_low"
    QUALITY_GATE_FAILURE = "quality_gate_failure"
    CONTRADICTORY_DATA = "contradictory_data"
    MISSING_DATA = "missing_data"
    SCOPE_VIOLATION = "scope_violation"


@dataclass
class QualityResult:
    passed: bool
    scores: dict[str, float]
    retry_count: int
    feedback: str


@dataclass
class ConfidenceScore:
    value: float
    tier: ConfidenceTier
    reasoning: str


@dataclass
class EscalationReport:
    escalation_type: EscalationType
    agent: str
    deal_id: str
    context: dict
    solutions_attempted: list[str]
    root_blocker: str
    impact: str
    recommended_action: str


@dataclass
class AgentOutput:
    agent_name: str
    deal_id: Optional[str]
    result: Any
    quality: Optional[QualityResult]
    confidence: Optional[ConfidenceScore]
    artifacts_produced: list[str]
    timestamp: float


class AgentBase(ABC):
    """Unified agent base for KTS and ABS agents.
    
    KTS agents: __init__(agent_name, config)
    ABS agents: __init__(agent_name, config, deal_scope, tool_registry)
    """

    MAX_RETRIES = 3
    MIN_QUALITY_SCORE = 8.0
    agent_version: str = "1.0.0"

    def __init__(
        self,
        agent_name: str,
        config: KTSConfig,
        deal_scope: Optional[Any] = None,        # Optional[DealScope]
        tool_registry: Optional[Any] = None,      # Optional[ToolRegistry]
    ):
        self.agent_name = agent_name
        self.config = config
        self.deal_scope = deal_scope
        self.tool_registry = tool_registry
        self.quality_gate = QualityGate(config)

    # ── Prompt Structure (default no-ops for KTS agents) ──

    @property
    def system_prompt(self) -> str:
        """Build structured system prompt from mission/actions/output/rules."""
        mission = self._get_mission()
        actions = self._get_actions()
        output_spec = self._get_output_spec()
        rules = self._get_validation_rules()
        
        parts = [f"MISSION: {mission}"]
        if actions:
            parts.append("ACTIONS:\n" + "\n".join(f"  - {a}" for a in actions))
        parts.append(f"OUTPUT: {output_spec}")
        if rules:
            parts.append("RULES:\n" + "\n".join(f"  - {r}" for r in rules))
        return "\n\n".join(parts)

    def _get_mission(self) -> str:
        """Override in subclass to define agent mission."""
        return "No mission defined"

    def _get_actions(self) -> list[str]:
        """Override in subclass to define available actions."""
        return []

    def _get_output_spec(self) -> str:
        """Override in subclass to define output format."""
        return "No output spec"

    def _get_validation_rules(self) -> list[str]:
        """Override in subclass to define validation rules."""
        return []

    # ── Core Execution ──

    def execute(self, task: dict[str, Any]) -> AgentOutput:
        """Execute with quality gate and retry loop."""
        deal_id = None
        if self.deal_scope:
            deal_id = self.deal_scope.deal_id

        for attempt in range(self.MAX_RETRIES):
            result = self._run(task)
            quality = self._evaluate_quality(result, task)

            if quality.passed:
                confidence = self._score_confidence(result, task)
                return AgentOutput(
                    agent_name=self.agent_name,
                    deal_id=deal_id,
                    result=result,
                    quality=quality,
                    confidence=confidence,
                    artifacts_produced=self._get_artifacts(result),
                    timestamp=time.time(),
                )

            logger.warning(
                f"[{self.agent_name}] Quality gate failed (attempt {attempt + 1}/"
                f"{self.MAX_RETRIES}): {quality.feedback}"
            )

        # Final attempt failed — return with failed quality
        return AgentOutput(
            agent_name=self.agent_name,
            deal_id=deal_id,
            result=result,
            quality=quality,
            confidence=self._score_confidence(result, task),
            artifacts_produced=self._get_artifacts(result),
            timestamp=time.time(),
        )

    @abstractmethod
    def _run(self, task: dict[str, Any]) -> Any:
        """Core agent logic. Override in every subclass."""
        ...

    # ── Quality Gate (5 dimensions) ──

    def _evaluate_quality(self, result: Any, task: dict) -> QualityResult:
        scores = {
            QualityDimension.COMPLETENESS.value: self._score_completeness(result, task),
            QualityDimension.ACCURACY.value: self._score_accuracy(result, task),
            QualityDimension.CITATION_FIDELITY.value: self._score_citations(result, task),
            QualityDimension.STRUCTURAL_CONFORMANCE.value: self._score_structure(result, task),
            QualityDimension.DEAL_SCOPE_COMPLIANCE.value: self._score_scope(result, task),
        }
        avg = sum(scores.values()) / len(scores)
        passed = avg >= self.MIN_QUALITY_SCORE
        return QualityResult(
            passed=passed,
            scores=scores,
            retry_count=0,
            feedback="" if passed else f"Average score {avg:.1f} < {self.MIN_QUALITY_SCORE}",
        )

    def _score_completeness(self, result, task) -> float:
        return 8.0

    def _score_accuracy(self, result, task) -> float:
        return 8.0

    def _score_citations(self, result, task) -> float:
        return 8.0

    def _score_structure(self, result, task) -> float:
        return 8.0

    def _score_scope(self, result, task) -> float:
        return 10.0

    # ── Confidence Scoring ──

    def _score_confidence(self, result, task) -> ConfidenceScore:
        return ConfidenceScore(value=0.80, tier=ConfidenceTier.MEDIUM, reasoning="default")

    @staticmethod
    def _categorize_confidence(score: float) -> ConfidenceTier:
        if score >= 0.90:
            return ConfidenceTier.HIGH
        elif score >= 0.66:
            return ConfidenceTier.MEDIUM
        return ConfidenceTier.LOW

    # ── State Persistence ──

    def _load_state(self) -> dict[str, Any]:
        if not self.deal_scope:
            return {}
        state_path = Path(self.deal_scope.deal_path) / ".agent_state" / f"{self.agent_name}.json"
        if state_path.exists():
            return json.loads(state_path.read_text())
        return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        if not self.deal_scope:
            return
        state_dir = Path(self.deal_scope.deal_path) / ".agent_state"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / f"{self.agent_name}.json"
        state_path.write_text(json.dumps(state, indent=2))

    # ── Artifacts & Tools ──

    def _get_artifacts(self, result) -> list[str]:
        return []

    def use_tool(self, tool_name: str, **kwargs) -> Any:
        if not self.tool_registry:
            raise RuntimeError(f"No tool registry for agent {self.agent_name}")
        return self.tool_registry.execute(tool_name, self.agent_name, **kwargs)

    def available_tools(self) -> list[str]:
        if not self.tool_registry:
            return []
        return self.tool_registry.list_tools(self.agent_name)

    # ── Legacy KTS interface ──

    def quality_check(self, result: AgentResult) -> AgentResult:
        """Backward-compatible quality check for KTS agents."""
        return self.quality_gate.apply(result)
```

### Migration Impact on Existing KTS Agents

| KTS Agent | Changes Required |
|-----------|-----------------|
| `CrawlerAgent` | `__init__` signature: add `agent_name` as first arg |
| `IngestionAgent` | Same |
| `TaxonomyAgent` | Same |
| `GraphBuilderAgent` | Same |
| `RetrievalService` | Not an agent (service class) — no change |
| `TrainingPathAgent` | Same |
| `ChangeImpactAgent` | Same |
| `FreshnessAgent` | Same |
| `VersionAgent` | Same |
| `VisionAgent` | Same |
| `DescribeAgent` | Same |
| `DiffAgent` | Same |
| `OneNoteAgent` | Same |
| `ItemExtractorAgent` | Same |
| `VocabularyEnricherAgent` | Same |

**Change pattern** (applies to all 15 KTS agents):
```python
# BEFORE:
class CrawlerAgent(AgentBase):
    def __init__(self, config):
        super().__init__("crawler", config)

# AFTER:
class CrawlerAgent(AgentBase):
    def __init__(self, config):
        super().__init__("crawler", config)  # identical — backward compatible
```

Because the merged AgentBase defaults `deal_scope=None` and `tool_registry=None`, existing KTS agents need **no constructor changes**. The only required change is if any existing agent calls `self.execute(request)` and expects `AgentResult` — it now returns `AgentOutput`. This is handled by the `quality_check()` backward-compat method.

---

## Quality Infrastructure Merge

### Current State

**KTS Quality** (`backend/common/quality_gate.py` — 63 lines):
```python
class QualityGate:
    def __init__(self, config):
        self.confidence_high = config.confidence_high     # 0.90
        self.confidence_medium = config.confidence_medium  # 0.66
    
    def apply(self, result: AgentResult) -> AgentResult:
        """Simple threshold check on result.confidence."""
        ...
```

**PayGen Quality** (`pipeline/quality/` — 6 modules, ~800 lines):
```
quality/
├── quality_gate.py      — 5-dimension scoring engine
├── confidence.py        — Confidence tier classification + scoring
├── escalation.py        — Escalation detection + reporting
├── output_contracts.py  — Output schema validation
├── pre_mortem.py        — Risk analysis before execution
└── refine_loop.py       — Quality-driven refinement loop
```

### Proposed: Merged Quality in `backend/common/`

```
backend/common/
├── quality_gate.py      ← REPLACED: PayGen's 5-dimension version
├── confidence.py        ← NEW: from PayGen
├── escalation.py        ← EXISTING + PayGen additions
├── output_contracts.py  ← NEW: from PayGen
├── pre_mortem.py        ← NEW: from PayGen
├── refine_loop.py       ← NEW: from PayGen
├── models.py            ← EXISTING (add AgentOutput, QualityResult, etc.)
└── ...existing files...
```

**Key merge detail:** KTS's existing `QualityGate.apply(result: AgentResult)` method is preserved as a wrapper that calls the 5-dimension scoring internally:

```python
class QualityGate:
    def apply(self, result: AgentResult) -> AgentResult:
        """Legacy KTS interface — delegates to 5-dimension scoring."""
        quality = self.evaluate(result, task={})
        result.confidence = quality.scores.get("accuracy", result.confidence)
        return result
    
    def evaluate(self, result: Any, task: dict) -> QualityResult:
        """Full 5-dimension evaluation (PayGen interface)."""
        ...
```

---

## ToolRegistry Integration

### Design

The `ToolRegistry` and `@agent_tool` decorator (168 lines) are placed at `backend/agents/agent_tools.py`:

```python
# backend/agents/agent_tools.py

@dataclass
class ToolMetadata:
    name: str
    description: str
    function: Callable
    allowed_agents: list[str]
    parameters: dict[str, Any]


class ToolAccessDenied(Exception): ...


class ToolRegistry:
    """Per-agent tool allowlist manager."""
    
    def register(self, name, description, function, allowed_agents, parameters): ...
    def execute(self, tool_name, agent_name, **kwargs): ...
    def list_tools(self, agent_name) -> list[str]: ...
    def get_tool(self, tool_name) -> ToolMetadata: ...


def agent_tool(name, description, allowed_agents, parameters=None):
    """Decorator to register a function as an agent tool."""
    ...


_global_registry: Optional[ToolRegistry] = None

def get_global_registry() -> ToolRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry
```

**KTS agents are not required to use the ToolRegistry.** It's available for ABS agents that need structured tool access patterns.

---

## DealScope Adaptation

### Changes from PayGen Version

PayGen's `DealScope` (251 lines) is copied to `backend/abs/deal_scope.py` with these adaptations:

| Aspect | PayGen Original | KTS Adaptation |
|--------|----------------|----------------|
| `deals_root` default | From `PipelineConfig.pipeline.deals_root` | From `KTSConfig.abs_deals_root` |
| Vectorstore dir | `{deal}/vectorstore/` | `{deal}/vectorstore/` (unchanged) |
| Graph dir | `{deal}/graph/` | `{deal}/graph/` (unchanged) |
| Knowledge base | N/A | Optionally registers with KTS `ScopeResolver` |
| Manifest path | `{deal}/manifest.json` | `{deal}/manifest.json` (unchanged) |

```python
# backend/abs/deal_scope.py — adapted version
class DealScope:
    def __init__(self, deal_id: str, config: KTSConfig, read_only: bool = False):
        self.deal_id = deal_id
        self.deals_root = Path(config.abs_deals_root)
        self.deal_path = self.deals_root / deal_id
        self.read_only = read_only
        self._config = config
    
    @classmethod
    def create(cls, deal_id: str, config: KTSConfig) -> 'DealScope':
        scope = cls(deal_id, config, read_only=False)
        scope.ensure_dirs()
        return scope
```

---

## DealManifest Adaptation

### Changes from PayGen Version

PayGen's `DealManifest` (256 lines) is copied to `backend/abs/deal_manifest.py` with these adaptations:

| Aspect | PayGen Original | KTS Adaptation |
|--------|----------------|----------------|
| Storage | JSON file per deal | JSON file per deal (unchanged) |
| Integration with ManifestStore | N/A | Optional: DealManifest registers with KTS's `ManifestStore` |
| DocumentType enum | 6 types (PSA, INDENTURE, ...) | 6 types (unchanged, ABS-specific) |

---

## Config Merge

### PayGen PipelineConfig → KTSConfig `abs_*` Properties

PayGen's `PipelineConfig` (300 lines, 7 dataclasses) is **not copied as a separate config system**. Instead, its properties are flattened into KTSConfig with `abs_*` prefix:

| PipelineConfig Property | KTSConfig Property |
|------------------------|-------------------|
| `extraction.mode` | `abs_extraction_mode` |
| `extraction.llm_provider` | (not needed — VS Code LM API) |
| `extraction.llm_model` | (not needed — GPT-4.1 via LM API) |
| `vectorstore.enabled` | `abs_vectorstore_enabled` |
| `vectorstore.embedding_dim` | `abs_embedding_dim` |
| `vectorstore.chunk_max_chars` | `abs_chunk_max_chars` |
| `vectorstore.chunk_overlap` | `abs_chunk_overlap` |
| `vectorstore.normalize_embeddings` | `abs_normalize_embeddings` |
| `pipeline.deals_root` | `abs_deals_root` |
| `pipeline.log_level` | (uses KTS's existing `debug_level`) |
| `quality.min_score` | `abs_min_quality_score` |
| `quality.max_retries` | `abs_max_retries` |
| `quality.confidence_high` | `abs_confidence_high` |
| `quality.confidence_low` | `abs_confidence_low` |
| `validation.output_tolerance` | `abs_output_tolerance` |
| `validation.min_definitions` | `abs_min_definitions` |
| `validation.min_waterfall_rules` | `abs_min_waterfall_rules` |
| `validation.min_vectors` | `abs_min_vectors` |
| `definition_resolution.enabled` | `abs_definition_resolution_enabled` |
| `definition_resolution.min_confidence` | `abs_definition_resolution_confidence` |
| `definition_resolution.max_depth` | `abs_definition_resolution_depth` |

**PayGen's `config/constants.py`, `config/schemas.py`, `config/section_maps.py`** are copied as-is to `backend/abs/config/` — they contain ABS domain constants, not infrastructure config.

---

## Import Rewrite Map

### Systematic Import Transformations

Every PayGen file has its imports rewritten using these rules:

| PayGen Import | KTS Import |
|--------------|-----------|
| `from pipeline.agents.agent_base import AgentBase` | `from backend.agents.base_agent import AgentBase` |
| `from pipeline.agents.agent_base import AgentOutput` | `from backend.agents.base_agent import AgentOutput` |
| `from pipeline.agents.agent_tools import ToolRegistry` | `from backend.agents.agent_tools import ToolRegistry` |
| `from pipeline.agents.agent_tools import get_global_registry` | `from backend.agents.agent_tools import get_global_registry` |
| `from pipeline.deal_scope import DealScope` | `from backend.abs.deal_scope import DealScope` |
| `from pipeline.deal_manifest import DealManifest` | `from backend.abs.deal_manifest import DealManifest` |
| `from pipeline.errors import *` | `from backend.abs.errors import *` |
| `from pipeline.config.pipeline_config import get_config` | `from config.settings import load_config` |
| `from pipeline.config.constants import *` | `from backend.abs.config.constants import *` |
| `from pipeline.config.schemas import *` | `from backend.abs.config.schemas import *` |
| `from pipeline.config.section_maps import *` | `from backend.abs.config.section_maps import *` |
| `from pipeline.quality.quality_gate import *` | `from backend.common.quality_gate import *` |
| `from pipeline.quality.confidence import *` | `from backend.common.confidence import *` |
| `from pipeline.quality.escalation import *` | `from backend.common.escalation import *` |
| `from pipeline.skills.embedder import *` | `from backend.vector.embedding_provider import *` (Phase 22) |
| `from pipeline.skills.graph_builder import *` | `from backend.graph.enhanced_graph_builder import *` (Phase 22) |
| `from pipeline.skills.vector_search import *` | `from backend.retrieval.retrieval_service import *` (Phase 22) |
| `from pipeline.skills.X import Y` | `from backend.abs.skills.X import Y` |
| `from pipeline.generation.X import Y` | `from backend.abs.generation.X import Y` |
| `from pipeline.ingestion.X import Y` | `from backend.abs.ingestion.X import Y` |

### Phase 21 vs Phase 22 Import Boundary

In Phase 21, the three replaced modules (`embedder`, `graph_builder`, `vector_search`) are temporarily stubbed:

```python
# backend/abs/skills/embedder.py (TEMPORARY STUB — replaced in Phase 22)
"""Temporary stub. Will be replaced by backend.vector.embedding_provider in Phase 22."""

def embed_and_store(*args, **kwargs):
    raise NotImplementedError("Wired to KTS embedding_provider in Phase 22")
```

This allows all imports to resolve in Phase 21, while actual infrastructure wiring happens in Phase 22.
