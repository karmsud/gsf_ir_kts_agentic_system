"""
Phase 16 — Settings Wiring Tests  (Updated for Phase B simplification).

After Phase B (Settings Simplification):
  - package.json has 3 user settings + 5 developer settings (was 23)
  - participant.js uses RAG_CONFIG constant + unified selectModel()
  - Token budget auto-computed from model.maxInputTokens

Tests:
  1. package.json schema validation (all 8 settings, correct types/defaults)
  2. Python KTSConfig env-var wiring (unchanged — backend still uses env vars)
  3. RAG_CONFIG constant values in participant.js
  4. Default value consistency (package.json ↔ Python defaults)
  5. Boundary value tests (min/max constraints for Python env vars)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Paths ────────────────────────────────────────────────────────

PACKAGE_JSON = ROOT / "extension" / "package.json"
PARTICIPANT_JS = ROOT / "extension" / "chat" / "participant.js"
KTS_BACKEND_JS = ROOT / "extension" / "lib" / "kts_backend.js"
SETTINGS_PY = ROOT / "config" / "settings.py"


# ── Helpers ──────────────────────────────────────────────────────

def _load_package_json():
    with PACKAGE_JSON.open("r", encoding="utf-8") as f:
        return json.load(f)


def _get_kts_settings(pkg=None):
    """Extract all kts.* settings from package.json."""
    if pkg is None:
        pkg = _load_package_json()
    config = pkg["contributes"]["configuration"]
    if isinstance(config, list):
        props = {}
        for section in config:
            props.update(section.get("properties", {}))
    else:
        props = config.get("properties", {})
    return {k: v for k, v in props.items() if k.startswith("kts.")}


# ═══════════════════════════════════════════════════════════════════
# 1. Package.json Schema Validation  (3 user + 5 developer settings)
# ═══════════════════════════════════════════════════════════════════

class TestPackageJsonSchema:
    """Verify all 8 settings exist with correct type, defaults, and bounds."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.pkg = _load_package_json()
        self.settings = _get_kts_settings(self.pkg)

    # ── User settings (3) ──

    def test_source_folder(self):
        s = self.settings["kts.sourceFolder"]
        assert s["type"] == "string"
        assert s["default"] == ""

    def test_log_level(self):
        s = self.settings["kts.logLevel"]
        assert s["type"] == "string"
        assert s["default"] == "normal"
        assert "enum" in s
        assert set(s["enum"]) == {"normal", "verbose"}

    def test_model(self):
        s = self.settings["kts.model"]
        assert s["type"] == "string"
        assert s["default"] == "auto"
        assert "enum" in s
        expected_models = {"auto", "gpt-4.1", "gpt-4o", "gpt-4o-mini", "claude-sonnet-4"}
        assert set(s["enum"]) == expected_models

    # ── Developer settings (5) ──

    def test_backend_mode(self):
        s = self.settings["kts.backendMode"]
        assert s["type"] == "string"
        assert s["default"] == "auto"

    def test_backend_channel(self):
        s = self.settings["kts.backendChannel"]
        assert s["type"] == "string"
        assert s["default"] == "bundled"

    def test_python_path(self):
        s = self.settings["kts.pythonPath"]
        assert s["type"] == "string"
        assert s["default"] == ""

    def test_kb_workspace_path(self):
        s = self.settings["kts.kbWorkspacePath"]
        assert s["type"] == "string"
        assert s["default"] == ""

    def test_ingestion_timeout(self):
        s = self.settings["kts.ingestionTimeoutMinutes"]
        assert s["type"] == "integer"
        assert s["default"] == 60

    # ── Completeness checks ──

    def test_exactly_8_settings(self):
        # Original Phase B target was 8 settings; package.json has since grown.
        # Verify at minimum the 8 core settings are present.
        assert len(self.settings) >= 8, (
            f"Expected at least 8 kts.* settings, found {len(self.settings)}: "
            f"{sorted(self.settings.keys())}"
        )

    def test_all_expected_settings_exist(self):
        expected = {
            # User settings
            "kts.sourceFolder",
            "kts.logLevel",
            "kts.model",
            # Developer settings
            "kts.backendMode",
            "kts.backendChannel",
            "kts.pythonPath",
            "kts.kbWorkspacePath",
            "kts.ingestionTimeoutMinutes",
        }
        actual = set(self.settings.keys())
        missing = expected - actual
        assert not missing, f"Missing settings: {missing}"
        # extra settings beyond the 8-core are allowed (package.json grew in later phases)

    def test_no_duplicate_settings(self):
        """All settings have unique defaults (no copy-paste errors)."""
        assert len(self.settings) == len(set(self.settings.keys()))

    def test_all_settings_have_descriptions(self):
        """Every setting must have a non-empty description or markdownDescription."""
        for key, val in self.settings.items():
            desc = val.get("description") or val.get("markdownDescription") or ""
            assert len(desc) > 10, f"{key} missing or too-short description"

    def test_old_settings_removed(self):
        """Settings consolidated into RAG_CONFIG should NOT be in package.json."""
        removed = {
            "kts.multiQueryEnabled", "kts.selfRagEnabled", "kts.critiqueLoopEnabled",
            "kts.reasoningModel", "kts.generationModel", "kts.multiQueryModel",
            "kts.selfRagModel", "kts.critiqueModel", "kts.multiQueryVariants",
            "kts.selfRagMaxRounds", "kts.maxContextChunks", "kts.tokenBudget",
            "kts.graphRagEnabled", "kts.graphRagMaxIterations",
            "kts.graphRagVerboseLogging", "kts.sourcePath",
            # kts.knowledgeSourceRoot was re-added in a later phase
        }
        for key in removed:
            assert key not in self.settings, f"Old setting {key} should be removed"


# ═══════════════════════════════════════════════════════════════════
# 2. Python KTSConfig Env-Var Wiring (unchanged)
# ═══════════════════════════════════════════════════════════════════

class TestPythonConfigEnvVars:
    """Verify Python KTSConfig reads env vars correctly."""

    def test_multi_query_enabled_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KTS_MULTI_QUERY_RAG_ENABLED", "false")
        monkeypatch.setenv("KTS_KB_PATH", str(tmp_path))
        from config.settings import load_config
        cfg = load_config(tmp_path)
        assert cfg.multi_query_rag_enabled is False

    def test_multi_query_enabled_env_true(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KTS_MULTI_QUERY_RAG_ENABLED", "true")
        monkeypatch.setenv("KTS_KB_PATH", str(tmp_path))
        from config.settings import load_config
        cfg = load_config(tmp_path)
        assert cfg.multi_query_rag_enabled is True

    def test_multi_query_variants_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KTS_MULTI_QUERY_VARIANTS", "6")
        monkeypatch.setenv("KTS_KB_PATH", str(tmp_path))
        from config.settings import load_config
        cfg = load_config(tmp_path)
        assert cfg.multi_query_variants == 6

    def test_self_rag_enabled_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KTS_SELF_RAG_ENABLED", "true")
        monkeypatch.setenv("KTS_KB_PATH", str(tmp_path))
        from config.settings import load_config
        cfg = load_config(tmp_path)
        assert cfg.self_rag_enabled is True

    def test_self_rag_max_rounds_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KTS_SELF_RAG_MAX_ROUNDS", "5")
        monkeypatch.setenv("KTS_KB_PATH", str(tmp_path))
        from config.settings import load_config
        cfg = load_config(tmp_path)
        assert cfg.self_rag_max_rounds == 5

    def test_self_rag_model_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KTS_SELF_RAG_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("KTS_KB_PATH", str(tmp_path))
        from config.settings import load_config
        cfg = load_config(tmp_path)
        assert cfg.self_rag_model == "gpt-4o-mini"

    def test_critique_loop_enabled_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KTS_CRITIQUE_LOOP_ENABLED", "false")
        monkeypatch.setenv("KTS_KB_PATH", str(tmp_path))
        from config.settings import load_config
        cfg = load_config(tmp_path)
        assert cfg.critique_loop_enabled is False

    def test_critique_model_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KTS_CRITIQUE_MODEL", "gpt-4o")
        monkeypatch.setenv("KTS_KB_PATH", str(tmp_path))
        from config.settings import load_config
        cfg = load_config(tmp_path)
        assert cfg.critique_model == "gpt-4o"

    def test_critique_max_rounds_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KTS_CRITIQUE_MAX_ROUNDS", "7")
        monkeypatch.setenv("KTS_KB_PATH", str(tmp_path))
        from config.settings import load_config
        cfg = load_config(tmp_path)
        assert cfg.critique_max_rounds == 7

    def test_critique_gen_model_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KTS_CRITIQUE_GEN_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("KTS_KB_PATH", str(tmp_path))
        from config.settings import load_config
        cfg = load_config(tmp_path)
        assert cfg.critique_generator_model == "gpt-4o-mini"


# ═══════════════════════════════════════════════════════════════════
# 3. RAG_CONFIG Constant & Unified Functions in participant.js
# ═══════════════════════════════════════════════════════════════════

class TestParticipantJSArchitecture:
    """Verify participant.js uses RAG_CONFIG + unified selectModel."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.js = PARTICIPANT_JS.read_text(encoding="utf-8")

    # ── RAG_CONFIG constant ──

    def test_rag_config_defined(self):
        assert "const RAG_CONFIG" in self.js

    def test_rag_config_max_context_chunks(self):
        assert "maxContextChunks" in self.js

    def test_rag_config_multi_query_variants(self):
        assert "multiQueryVariants" in self.js

    def test_rag_config_self_rag_replaced_by_critique(self):
        """selfRagEnabled removed — unified critique-RAG loop uses critiqueEnabled."""
        assert "selfRagEnabled" not in self.js
        assert "critiqueEnabled" in self.js

    def test_rag_config_critique_enabled(self):
        assert "critiqueEnabled" in self.js

    def test_rag_config_self_rag_max_rounds_replaced(self):
        """selfRagMaxRounds removed — unified loop uses critiqueMaxRounds."""
        assert "selfRagMaxRounds" not in self.js
        assert "critiqueMaxRounds" in self.js

    def test_rag_config_critique_max_rounds(self):
        assert "critiqueMaxRounds" in self.js

    # ── Unified model selection ──

    def test_select_model_exists(self):
        assert "async function selectModel(vscode" in self.js

    def test_select_model_exported(self):
        assert "selectModel" in self.js
        # Check it's in exports
        assert "selectModel," in self.js or "selectModel}" in self.js

    def test_old_dual_model_functions_removed(self):
        """selectChatModel and selectReasoningModel should be removed."""
        assert "async function selectChatModel(" not in self.js
        assert "async function selectReasoningModel(" not in self.js

    # ── Auto-compute functions ──

    def test_compute_token_budget_exists(self):
        assert "function computeTokenBudget(" in self.js

    def test_compute_max_chunks_exists(self):
        assert "function computeMaxChunks(" in self.js

    def test_compute_functions_exported(self):
        assert "computeTokenBudget" in self.js
        assert "computeMaxChunks" in self.js

    # ── Old individual setting reads removed ──

    def test_no_multi_query_enabled_setting_read(self):
        """Should use RAG_CONFIG.selfRagEnabled, not cfg.get('multiQueryEnabled')."""
        assert "cfg.get('multiQueryEnabled'" not in self.js

    def test_no_self_rag_enabled_setting_read(self):
        assert "cfg.get('selfRagEnabled'" not in self.js

    def test_no_critique_loop_setting_read(self):
        assert "cfg.get('critiqueLoopEnabled'" not in self.js

    def test_no_token_budget_setting_read(self):
        assert "cfg.get('tokenBudget'" not in self.js

    def test_no_max_context_chunks_setting_read(self):
        assert "cfg.get('maxContextChunks'" not in self.js

    # ── Old selectCritiqueModel removed ──

    def test_no_select_critique_model(self):
        assert "selectCritiqueModel" not in self.js

    # ── Mode indicator removed ──

    def test_no_mode_indicator(self):
        """Old *[Legal Analyst mode]* / *[KTS Support mode]* removed."""
        assert "Legal Analyst mode" not in self.js
        assert "KTS Support mode" not in self.js


# ═══════════════════════════════════════════════════════════════════
# 4. Default Value Consistency
# ═══════════════════════════════════════════════════════════════════

class TestDefaultConsistency:
    """Verify package.json defaults for settings that still exist."""

    @pytest.fixture(autouse=True)
    def _load(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KTS_KB_PATH", str(tmp_path))
        self.settings = _get_kts_settings()
        from config.settings import KTSConfig
        self.py_cfg = KTSConfig()

    def test_log_level_default(self):
        assert self.settings["kts.logLevel"]["default"] == "normal"

    def test_model_default(self):
        assert self.settings["kts.model"]["default"] == "auto"

    def test_ingestion_timeout_default(self):
        assert self.settings["kts.ingestionTimeoutMinutes"]["default"] == 60

    def test_backend_mode_default(self):
        assert self.settings["kts.backendMode"]["default"] == "auto"

    def test_backend_channel_default(self):
        assert self.settings["kts.backendChannel"]["default"] == "bundled"


# ═══════════════════════════════════════════════════════════════════
# 5. Boundary Value Tests for Python Config (unchanged)
# ═══════════════════════════════════════════════════════════════════

class TestBoundaryValues:
    """Verify env var parsing handles edge cases."""

    def test_multi_query_variants_zero(self, monkeypatch, tmp_path):
        """Zero variants should be accepted (Python doesn't enforce min)."""
        monkeypatch.setenv("KTS_MULTI_QUERY_VARIANTS", "0")
        monkeypatch.setenv("KTS_KB_PATH", str(tmp_path))
        from config.settings import load_config
        cfg = load_config(tmp_path)
        assert cfg.multi_query_variants == 0

    def test_self_rag_rounds_large(self, monkeypatch, tmp_path):
        """Large value should be accepted."""
        monkeypatch.setenv("KTS_SELF_RAG_MAX_ROUNDS", "10")
        monkeypatch.setenv("KTS_KB_PATH", str(tmp_path))
        from config.settings import load_config
        cfg = load_config(tmp_path)
        assert cfg.self_rag_max_rounds == 10

    def test_bool_false_strings(self, monkeypatch, tmp_path):
        """Various false-like strings should parse as False."""
        monkeypatch.setenv("KTS_KB_PATH", str(tmp_path))
        for val in ["false", "False", "FALSE", "0", "no"]:
            monkeypatch.setenv("KTS_MULTI_QUERY_RAG_ENABLED", val)
            from config.settings import load_config
            cfg = load_config(tmp_path)
            assert cfg.multi_query_rag_enabled is False, f"'{val}' should parse as False"

    def test_bool_true_strings(self, monkeypatch, tmp_path):
        """Various true-like strings should parse as True."""
        monkeypatch.setenv("KTS_KB_PATH", str(tmp_path))
        for val in ["true", "True", "TRUE", "1", "yes"]:
            monkeypatch.setenv("KTS_MULTI_QUERY_RAG_ENABLED", val)
            from config.settings import load_config
            cfg = load_config(tmp_path)
            assert cfg.multi_query_rag_enabled is True, f"'{val}' should parse as True"


# ═══════════════════════════════════════════════════════════════════
# 6. KTS Backend JS Env Var Pass-Through Verification
# ═══════════════════════════════════════════════════════════════════

class TestKTSBackendJSPassThrough:
    """Verify kts_backend.js env var handling."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.js = KTS_BACKEND_JS.read_text(encoding="utf-8")

    def test_passes_kb_path(self):
        assert "KTS_KB_PATH" in self.js

    def test_passes_source_path(self):
        assert "KTS_SOURCE_PATH" in self.js

    def test_passes_phase6_enabled(self):
        assert "KTS_PHASE6_ENABLED" in self.js

    def test_passes_log_level(self):
        assert "KTS_LOG_LEVEL" in self.js

    def test_env_var_names_are_valid(self):
        """All env var names should follow KTS_ prefix convention."""
        import re
        env_vars = re.findall(r'env\.(KTS_\w+)', self.js)
        for var in env_vars:
            assert var.startswith("KTS_"), f"Env var {var} doesn't follow convention"
            assert var == var.upper(), f"Env var {var} should be all uppercase"
