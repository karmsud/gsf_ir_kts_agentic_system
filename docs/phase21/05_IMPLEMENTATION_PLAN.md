# Phase 21: Implementation Plan
## Step-by-Step Execution Guide

**Document Version:** 1.0  
**Date:** February 26, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** Detailed implementation roadmap with file paths and timeline

---

## Table of Contents
1. [Overview](#overview)
2. [Step 1: Scaffold backend/abs/](#step-1-scaffold-backendabs)
3. [Step 2: Copy Domain Logic](#step-2-copy-domain-logic)
4. [Step 3: Create Temporary Stubs](#step-3-create-temporary-stubs)
5. [Step 4: Rewrite Imports (ABS Modules)](#step-4-rewrite-imports-abs-modules)
6. [Step 5: Merge AgentBase](#step-5-merge-agentbase)
7. [Step 6: Merge Quality Infrastructure](#step-6-merge-quality-infrastructure)
8. [Step 7: Add KTSConfig Properties](#step-7-add-ktsconfig-properties)
9. [Timeline & Dependencies](#timeline--dependencies)
10. [Validation Checkpoints](#validation-checkpoints)
11. [Rollback Strategy](#rollback-strategy)

---

## Overview

### Implementation Philosophy

**Sequential execution with validation checkpoints:**
- Each step produces a testable state
- Run `pytest` after each step to catch regressions early
- Keep existing KTS tests green throughout
- No feature flags needed — ABS code is additive

**Quality Gates:**
- Step 2 complete: All files present under `backend/abs/`
- Step 4 complete: All imports resolve (no `ModuleNotFoundError`)
- Step 5 complete: All KTS agents still instantiate
- Step 6 complete: Both KTS and ABS quality gates work
- Step 7 complete: Full `pytest` pass (KTS + ABS)

### Estimated Effort

| Step | Description | Estimated Time | Risk Level |
|------|-------------|----------------|------------|
| Step 1 | Scaffold directories | 15 minutes | ⚪ Very Low |
| Step 2 | Copy domain logic files | 30 minutes | ⚪ Very Low |
| Step 3 | Create temporary stubs | 15 minutes | ⚪ Very Low |
| Step 4 | Rewrite imports | 3–4 hours | 🟡 Medium (tedious) |
| Step 5 | Merge AgentBase | 2–3 hours | 🟠 Medium-High |
| Step 6 | Merge quality infrastructure | 2–3 hours | 🟡 Medium |
| Step 7 | Add KTSConfig properties | 1–2 hours | ⚪ Low |
| **TOTAL** | | **10–14 hours** | **🟡 Overall Medium** |

**Timeline:** 3–4 work days (4 hours/day)

---

## Step 1: Scaffold backend/abs/

### Objective
Create empty directory structure for ABS domain subpackage.

### Risk Assessment
- **Risk Level:** ⚪ Very Low
- **Impact:** New directories only, no existing code touched
- **Rollback:** `rm -rf backend/abs/` (<1 second)

### Execution

```powershell
# Run from gsf_ir_kts_agentic_system/
$dirs = @(
    "backend/abs",
    "backend/abs/agents",
    "backend/abs/skills",
    "backend/abs/generation",
    "backend/abs/ingestion",
    "backend/abs/config"
)
foreach ($d in $dirs) {
    New-Item -ItemType Directory -Path $d -Force
}
```

### Create Init Files

Create the 6 `__init__.py` files as specified in `04_TECHNICAL_DESIGN.md` Section "Init Files".

### Validation
```powershell
# Verify structure
Get-ChildItem -Recurse backend/abs -Filter "*.py" | Select-Object FullName
# Expected: 6 __init__.py files
```

**Estimated Time:** 15 minutes

---

## Step 2: Copy Domain Logic

### Objective
Copy all PayGen source files into the `backend/abs/` structure.

### Risk Assessment
- **Risk Level:** ⚪ Very Low
- **Impact:** New files only, no existing code touched
- **Rollback:** Delete copied files

### File Copy Map

```powershell
$root_src = "c:\Users\Karmsud\New Project\AI Payment Generator\pipeline"
$root_dst = "c:\Users\Karmsud\New Project\gsf_ir_kts_agentic_system\backend\abs"

# Agents (12 files — agent_base and agent_tools go to backend/agents/)
$agent_files = @(
    "cashflow_projection_agent.py",
    "deal_amendment_agent.py",
    "deal_lifecycle_agent.py",
    "document_comparison_agent.py",
    "document_quality_agent.py",
    "ingestion_pipeline_agent.py",
    "investor_reporting_agent.py",
    "model_auditor_agent.py",
    "model_creation_agent.py",
    "qa_agent.py",
    "regression_testing_agent.py",
    "stress_testing_agent.py"
)
foreach ($f in $agent_files) {
    Copy-Item "$root_src\agents\$f" "$root_dst\agents\$f"
}

# Skills (11 files — embedder, graph_builder, vector_search are stubs)
$skill_files = @(
    "amendment_manager.py",
    "cashflow_engine.py",
    "csv_validator.py",
    "deal_comparator.py",
    "deal_setup_extractor.py",
    "document_classifier.py",
    "document_hasher.py",
    "document_tools.py",
    "output_comparator.py",
    "parsers.py",
    "report_generator.py"
)
foreach ($f in $skill_files) {
    Copy-Item "$root_src\skills\$f" "$root_dst\skills\$f"
}

# Generation (3 files)
$gen_files = @("data_prep.py", "model_runner.py", "model_validator.py")
foreach ($f in $gen_files) {
    Copy-Item "$root_src\generation\$f" "$root_dst\generation\$f"
}

# Ingestion (8 files)
$ingest_files = @(
    "definition_resolution.py",
    "document_converter.py",
    "document_intelligence.py",
    "governing_doc_generator.py",
    "ingestion_validator.py",
    "knowledge_store.py",
    "pipeline_runner.py",
    "section_splitter.py",
    "structured_extractor.py"
)
foreach ($f in $ingest_files) {
    Copy-Item "$root_src\ingestion\$f" "$root_dst\ingestion\$f"
}

# Scoping & Errors
Copy-Item "$root_src\deal_scope.py" "$root_dst\deal_scope.py"
Copy-Item "$root_src\deal_manifest.py" "$root_dst\deal_manifest.py"
Copy-Item "$root_src\errors.py" "$root_dst\errors.py"

# Config domain files
$config_files = @("constants.py", "schemas.py", "section_maps.py")
foreach ($f in $config_files) {
    Copy-Item "$root_src\config\$f" "$root_dst\config\$f"
}

# AgentBase and ToolRegistry → backend/agents/ (not abs/)
Copy-Item "$root_src\agents\agent_tools.py" `
    "c:\Users\Karmsud\New Project\gsf_ir_kts_agentic_system\backend\agents\agent_tools.py"

# Quality modules → backend/common/
$quality_files = @(
    "confidence.py",
    "output_contracts.py",
    "pre_mortem.py",
    "refine_loop.py"
)
foreach ($f in $quality_files) {
    Copy-Item "$root_src\quality\$f" `
        "c:\Users\Karmsud\New Project\gsf_ir_kts_agentic_system\backend\common\$f"
}
```

### Validation
```powershell
# Count files
(Get-ChildItem -Recurse backend/abs -Filter "*.py").Count
# Expected: 6 init + 12 agents + 11 skills + 3 gen + 9 ingest + 3 scope/errors + 3 config = 47

# Verify agent_tools.py in backend/agents/
Test-Path backend/agents/agent_tools.py  # Expected: True

# Verify quality modules in backend/common/
Test-Path backend/common/confidence.py    # Expected: True
Test-Path backend/common/pre_mortem.py    # Expected: True
```

**Estimated Time:** 30 minutes

---

## Step 3: Create Temporary Stubs

### Objective
Create stub files for the 3 modules that will be replaced by KTS infrastructure in Phase 22.

### Execution

Create these 3 files as specified in `04_TECHNICAL_DESIGN.md` Section "Temporary Stubs":
- `backend/abs/skills/embedder.py`
- `backend/abs/skills/graph_builder.py`
- `backend/abs/skills/vector_search.py`

### Validation
```python
# Quick import check
from backend.abs.skills.embedder import embed_and_store
try:
    embed_and_store()
except NotImplementedError as e:
    assert "Phase 22" in str(e)  # ✅
```

**Estimated Time:** 15 minutes

---

## Step 4: Rewrite Imports (ABS Modules)

### Objective
Systematically rewrite all `from pipeline.*` imports to use KTS paths.

### Risk Assessment
- **Risk Level:** 🟡 Medium
- **Impact:** Every ABS module is modified
- **Rollback:** Re-copy original files from PayGen
- **Testing:** Import each module individually

### Strategy

Use `grep` to find all PayGen imports, then apply transformations:

```powershell
# Find all pipeline imports in abs/
Select-String -Path "backend\abs\**\*.py" -Pattern "from pipeline\." -Recurse
```

### Import Transformation Rules

Apply these regex replacements across ALL files in `backend/abs/`:

```
# Agent framework
s/from pipeline\.agents\.agent_base import/from backend.agents.base_agent import/g
s/from pipeline\.agents\.agent_tools import/from backend.agents.agent_tools import/g

# Scoping
s/from pipeline\.deal_scope import/from backend.abs.deal_scope import/g
s/from pipeline\.deal_manifest import/from backend.abs.deal_manifest import/g

# Errors
s/from pipeline\.errors import/from backend.abs.errors import/g

# Config
s/from pipeline\.config\.pipeline_config import get_config/from config.settings import load_config/g
s/from pipeline\.config\.pipeline_config import PipelineConfig/# PipelineConfig replaced by KTSConfig/g
s/from pipeline\.config\.constants import/from backend.abs.config.constants import/g
s/from pipeline\.config\.schemas import/from backend.abs.config.schemas import/g
s/from pipeline\.config\.section_maps import/from backend.abs.config.section_maps import/g

# Quality
s/from pipeline\.quality\.quality_gate import/from backend.common.quality_gate import/g
s/from pipeline\.quality\.confidence import/from backend.common.confidence import/g
s/from pipeline\.quality\.escalation import/from backend.common.escalation import/g
s/from pipeline\.quality\.output_contracts import/from backend.common.output_contracts import/g
s/from pipeline\.quality\.pre_mortem import/from backend.common.pre_mortem import/g
s/from pipeline\.quality\.refine_loop import/from backend.common.refine_loop import/g

# Skills — stubs (will become real in Phase 22)
s/from pipeline\.skills\.embedder import/from backend.abs.skills.embedder import/g
s/from pipeline\.skills\.graph_builder import/from backend.abs.skills.graph_builder import/g
s/from pipeline\.skills\.vector_search import/from backend.abs.skills.vector_search import/g

# Skills — real copies
s/from pipeline\.skills\./from backend.abs.skills./g

# Generation
s/from pipeline\.generation\./from backend.abs.generation./g

# Ingestion
s/from pipeline\.ingestion\./from backend.abs.ingestion./g

# Catch-all for any remaining pipeline.* references
s/from pipeline import/from backend.abs import/g
```

### Per-Module Verification

After applying replacements, verify each module imports cleanly:

```python
# Run from gsf_ir_kts_agentic_system/ root
import importlib
modules = [
    "backend.abs.deal_scope",
    "backend.abs.deal_manifest",
    "backend.abs.errors",
    "backend.abs.config.constants",
    "backend.abs.config.schemas",
    "backend.abs.config.section_maps",
    "backend.abs.skills.cashflow_engine",
    "backend.abs.skills.parsers",
    "backend.abs.skills.csv_validator",
    # ... all modules
]
for mod in modules:
    try:
        importlib.import_module(mod)
        print(f"  ✅ {mod}")
    except Exception as e:
        print(f"  ❌ {mod}: {e}")
```

### Special Cases

1. **`get_config()` → `load_config()`**: PayGen uses `get_config()` singleton; KTS uses `load_config(root_dir)`. Every call site needs the root_dir parameter added.

2. **`PipelineConfig` references**: Replace with `KTSConfig` and use `abs_*` property names. Example:
   ```python
   # BEFORE:
   config = get_config()
   threshold = config.quality.min_score
   
   # AFTER:
   from config.settings import KTSConfig
   # config passed as parameter
   threshold = config.abs_min_quality_score
   ```

3. **Relative imports within skills/**: Some PayGen modules use relative imports (`from .parsers import split_into_sections`). These work as-is inside `backend/abs/skills/`.

**Estimated Time:** 3–4 hours (most labor-intensive step)

---

## Step 5: Merge AgentBase

### Objective
Replace KTS's 24-line `base_agent.py` with the merged 450-line version.

### Risk Assessment
- **Risk Level:** 🟠 Medium-High
- **Impact:** Every KTS agent inherits from AgentBase
- **Rollback:** Restore from git: `git checkout -- backend/agents/base_agent.py`
- **Testing:** Instantiate all 15 KTS agents + 12 ABS agents

### Execution

1. **Backup existing file:**
   ```powershell
   Copy-Item backend/agents/base_agent.py backend/agents/base_agent.py.bak
   ```

2. **Replace with merged version** from `04_TECHNICAL_DESIGN.md` and `03_ARCHITECTURE_UPGRADE.md`.

3. **Update imports in existing KTS agents:**
   
   For each KTS agent, verify the `super().__init__()` call. The merged AgentBase expects `(agent_name, config)` as the first two positional args.
   
   ```python
   # Verify pattern in each agent file:
   class SomeAgent(AgentBase):
       def __init__(self, config):
           super().__init__("agent-name", config)
   ```

4. **Add `agent_tools.py` to `backend/agents/`:**
   Already copied in Step 2. Verify imports resolve.

5. **Update `backend/agents/__init__.py`:**
   Add `AgentOutput`, `ConfidenceTier`, `QualityDimension`, `EscalationType` to exports.

### Validation

```python
# Test KTS agent instantiation
from config.settings import load_config
config = load_config(".")

from backend.agents.crawler_agent import CrawlerAgent
agent = CrawlerAgent(config)
assert agent.agent_name == "crawler"
assert agent.deal_scope is None
assert agent.tool_registry is None
print("✅ CrawlerAgent instantiates with merged AgentBase")

# Test ABS agent instantiation
from backend.abs.deal_scope import DealScope
scope = DealScope("test_deal", config)
from backend.abs.agents.model_creation_agent import ModelCreationAgent
agent = ModelCreationAgent(scope, config)
assert agent.deal_scope is not None
print("✅ ModelCreationAgent instantiates with merged AgentBase")
```

**Estimated Time:** 2–3 hours

---

## Step 6: Merge Quality Infrastructure

### Objective
Replace KTS's 63-line quality_gate.py with PayGen's 5-dimension version and add supporting modules.

### Risk Assessment
- **Risk Level:** 🟡 Medium
- **Impact:** All agents that call `quality_check()` need compatible interface
- **Rollback:** Restore from git: `git checkout -- backend/common/quality_gate.py`

### Execution

1. **Backup existing quality_gate.py:**
   ```powershell
   Copy-Item backend/common/quality_gate.py backend/common/quality_gate.py.bak
   ```

2. **Replace with merged version** from `04_TECHNICAL_DESIGN.md` Section "Quality Gate Merge Implementation".

3. **Rewrite imports in quality modules** (`confidence.py`, `output_contracts.py`, `pre_mortem.py`, `refine_loop.py`):
   Apply same import transformation rules from Step 4.

4. **Merge escalation.py:**
   - Read existing `backend/common/escalation.py`
   - Read PayGen's `pipeline/quality/escalation.py`
   - Merge: keep existing KTS functions, add PayGen's `EscalationReport` dataclass and additional functions

5. **Update `backend/common/__init__.py`:**
   Add new exports: `QualityResult`, `QualityDimension`

### Validation

```python
from config.settings import load_config
config = load_config(".")

from backend.common.quality_gate import QualityGate, QualityResult
gate = QualityGate(config)

# Test legacy KTS interface
from backend.common.models import AgentResult
result = AgentResult(content="test", confidence=0.88)
checked = gate.apply(result)
assert checked.quality_tier == "medium"
print("✅ Legacy apply() works")

# Test 5-dimension ABS interface
qr = gate.evaluate({"answer": "test"}, {"query": "test"})
assert isinstance(qr, QualityResult)
assert qr.passed  # default scores are 8.0, threshold is 8.0
print("✅ 5-dimension evaluate() works")
```

**Estimated Time:** 2–3 hours

---

## Step 7: Add KTSConfig Properties

### Objective
Add `abs_*` configuration properties to `KTSConfig` dataclass.

### Risk Assessment
- **Risk Level:** ⚪ Low
- **Impact:** Additive only — all new properties have defaults
- **Rollback:** Remove added lines
- **Testing:** Existing config loading works without `abs_*` keys

### Execution

1. **Edit `config/settings.py`:**
   Add the 20 `abs_*` properties as specified in `04_TECHNICAL_DESIGN.md` Section "KTSConfig Additions".

2. **Add env-var overrides** in the `_load_from_env()` method:
   ```python
   # Add to _load_from_env():
   if "KTS_ABS_ENABLED" in os.environ:
       self.abs_enabled = os.environ["KTS_ABS_ENABLED"].lower() == "true"
   if "KTS_ABS_DEALS_ROOT" in os.environ:
       self.abs_deals_root = os.environ["KTS_ABS_DEALS_ROOT"]
   # ... pattern for all abs_* properties
   ```

### Validation

```python
from config.settings import load_config

# Test default loading (no abs_ keys in existing config files)
config = load_config(".")
assert config.abs_enabled is False
assert config.abs_deals_root == "deals"
assert config.abs_min_quality_score == 8.0
print("✅ KTSConfig loads with abs_* defaults")

# Test env-var override
import os
os.environ["KTS_ABS_ENABLED"] = "true"
config = load_config(".")
assert config.abs_enabled is True
print("✅ Env-var override works")
del os.environ["KTS_ABS_ENABLED"]
```

**Estimated Time:** 1–2 hours

---

## Timeline & Dependencies

```
Day 1 (4 hours):
  Step 1: Scaffold ────► Step 2: Copy files ────► Step 3: Stubs
  (15 min)               (30 min)                 (15 min)
                                                       │
                                                       ▼
Day 2 (4 hours):                              Step 4: Rewrite imports
                                               (3-4 hours)
                                                       │
Day 3 (4 hours):                                       ▼
                                              Step 5: Merge AgentBase
                                               (2-3 hours)
                                                       │
Day 4 (4 hours):                                       ▼
                                              Step 6: Merge Quality
                                               (2-3 hours)
                                                       │
                                                       ▼
                                              Step 7: KTSConfig
                                               (1-2 hours)
```

### Dependencies

| Step | Depends On |
|------|-----------|
| Step 1 | None |
| Step 2 | Step 1 |
| Step 3 | Step 1 |
| Step 4 | Steps 2, 3 |
| Step 5 | Step 4 |
| Step 6 | Step 5 |
| Step 7 | Step 4 |

Steps 5 and 7 can run in parallel. Step 6 depends on Step 5 (quality_gate uses AgentBase types).

---

## Validation Checkpoints

### Checkpoint 1: After Step 3 (Files Present)
```powershell
# All source files exist
(Get-ChildItem -Recurse backend/abs -Filter "*.py").Count  # >= 50
Test-Path backend/agents/agent_tools.py                     # True
Test-Path backend/common/confidence.py                      # True
```

### Checkpoint 2: After Step 4 (Imports Resolve)
```python
# No pipeline.* imports remain
import subprocess
result = subprocess.run(
    ["grep", "-r", "from pipeline", "backend/abs/"],
    capture_output=True, text=True
)
assert result.stdout == ""  # No matches
```

### Checkpoint 3: After Step 5 (Agents Instantiate)
```python
# All 15 KTS agents + 12 ABS agents instantiate
# See Step 5 validation code
```

### Checkpoint 4: After Step 7 (Full Test Suite)
```powershell
# Run full KTS test suite — zero failures
pytest tests/ -v --tb=short
```

---

## Rollback Strategy

### Per-Step Rollback

| Step | Rollback Command | Time |
|------|-----------------|------|
| Step 1 | `Remove-Item -Recurse backend/abs` | <1 sec |
| Step 2 | `Remove-Item -Recurse backend/abs; git checkout -- backend/agents/ backend/common/` | <5 sec |
| Step 3 | Re-copy from PayGen (stubs are new files) | <1 min |
| Step 4 | Re-copy from PayGen (overwrites import changes) | <5 min |
| Step 5 | `git checkout -- backend/agents/base_agent.py` | <1 sec |
| Step 6 | `git checkout -- backend/common/quality_gate.py backend/common/escalation.py` | <1 sec |
| Step 7 | `git checkout -- config/settings.py` | <1 sec |

### Full Phase 21 Rollback

```powershell
# Remove all Phase 21 changes
Remove-Item -Recurse -Force backend/abs
git checkout -- backend/agents/base_agent.py
git checkout -- backend/agents/agent_tools.py
git checkout -- backend/common/quality_gate.py
git checkout -- backend/common/escalation.py
git checkout -- backend/common/confidence.py
git checkout -- backend/common/output_contracts.py
git checkout -- backend/common/pre_mortem.py
git checkout -- backend/common/refine_loop.py
git checkout -- config/settings.py
```

Time: <30 seconds. Zero risk to existing functionality.
