"""
ABS Pipeline Configuration Loader — reads pipeline_config.yaml and provides
a typed interface for all ABS pipeline settings.
Ported from AI Payment Generator pipeline.config.pipeline_config.

Usage:
    from backend.abs.config.pipeline_config import get_config, PipelineConfig
    cfg = get_config()
    cfg.extraction.mode
    cfg.vectorstore.enabled
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

# ── YAML loader (built-in fallback if PyYAML unavailable) ────

_HAS_YAML = False
try:
    import yaml
    _HAS_YAML = True
except ImportError:
    pass


def _load_yaml(path: Path) -> dict:
    """Load a YAML file. Falls back to simple key:value parser if PyYAML missing."""
    text = path.read_text(encoding="utf-8")
    if _HAS_YAML:
        return yaml.safe_load(text) or {}
    return _simple_yaml_parse(text)


def _simple_yaml_parse(text: str) -> dict:
    """Minimal YAML-like parser for simple nested structures."""
    result: dict[str, Any] = {}
    current_section: Optional[str] = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" ") and stripped.endswith(":"):
            current_section = stripped.rstrip(":").strip()
            result[current_section] = {}
            continue
        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            parsed_val: Any = val
            if val.lower() in ("true", "yes"):
                parsed_val = True
            elif val.lower() in ("false", "no"):
                parsed_val = False
            elif val.replace(".", "", 1).isdigit():
                parsed_val = float(val) if "." in val else int(val)
            if current_section and current_section in result:
                result[current_section][key] = parsed_val
            else:
                result[key] = parsed_val
    return result


# ── Configuration Dataclasses ─────────────────────────────────

@dataclass
class ExtractionConfig:
    """Extraction mode settings."""
    mode: str = "manual"
    llm_provider: str = "copilot"
    llm_model: str = "gpt-4o"

    @property
    def is_manual(self) -> bool:
        return self.mode == "manual"

    @property
    def is_llm(self) -> bool:
        return self.mode == "llm"


@dataclass
class VectorstoreConfig:
    """Vector store settings."""
    enabled: bool = True
    provider: str = "onnx"
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dim: int = 768
    model_dir: str = "models/embeddings/bge-base-en-v1.5/onnx-int8"
    normalize_embeddings: bool = True
    quantization: str = "int8"
    max_length: int = 512
    batch_size: int = 32
    pooling: str = "mean"
    chunk_max_chars: int = 1000
    chunk_overlap: int = 100


@dataclass
class PdfConfig:
    """PDF processing settings."""
    enabled: bool = True
    detect_tables: bool = True
    infer_headings: bool = True


@dataclass
class PipelineSettings:
    """General pipeline settings."""
    version: str = "0.1.0"
    deals_root: str = "deals"
    log_level: str = "INFO"


@dataclass
class QualityConfig:
    """Quality gate settings."""
    min_score: float = 8.0
    max_retries: int = 3
    confidence_high: float = 0.90
    confidence_low: float = 0.66


@dataclass
class ValidationConfig:
    """Validation thresholds."""
    output_tolerance: float = 0.01
    min_definitions: int = 5
    min_waterfall_rules: int = 3
    min_vectors: int = 100


@dataclass
class DefinitionResolutionConfig:
    """Definition dependency resolution settings."""
    enabled: bool = True
    min_confidence: float = 0.5
    max_depth: int = 12


@dataclass
class PipelineConfig:
    """Root configuration object."""
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    vectorstore: VectorstoreConfig = field(default_factory=VectorstoreConfig)
    pdf: PdfConfig = field(default_factory=PdfConfig)
    pipeline: PipelineSettings = field(default_factory=PipelineSettings)
    quality: QualityConfig = field(default_factory=QualityConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    definition_resolution: DefinitionResolutionConfig = field(default_factory=DefinitionResolutionConfig)

    @classmethod
    def from_dict(cls, data: dict) -> PipelineConfig:
        """Build config from a flat or nested dict."""
        def _section(key: str, klass):
            section_data = data.get(key, {})
            if isinstance(section_data, dict):
                valid_fields = {f.name for f in klass.__dataclass_fields__.values()}
                filtered = {k: v for k, v in section_data.items() if k in valid_fields}
                return klass(**filtered)
            return klass()

        return cls(
            extraction=_section("extraction", ExtractionConfig),
            vectorstore=_section("vectorstore", VectorstoreConfig),
            pdf=_section("pdf", PdfConfig),
            pipeline=_section("pipeline", PipelineSettings),
            quality=_section("quality", QualityConfig),
            validation=_section("validation", ValidationConfig),
            definition_resolution=_section("definition_resolution", DefinitionResolutionConfig),
        )

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return asdict(self)


# ── Singleton Loader ──────────────────────────────────────────

_CONFIG_INSTANCE: Optional[PipelineConfig] = None
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "pipeline_config.yaml"


def _resolve_deals_root(raw: str) -> str:
    """Normalize the configured deals root path."""
    if not raw:
        return "deals"
    expanded = os.path.expandvars(str(raw)).strip().strip('"').strip("'")
    try:
        return str(Path(expanded).expanduser())
    except Exception:
        return expanded


def get_config(
    config_path: Optional[Path] = None,
    reload: bool = False,
) -> PipelineConfig:
    """Load pipeline configuration (singleton)."""
    global _CONFIG_INSTANCE

    if _CONFIG_INSTANCE is not None and not reload:
        return _CONFIG_INSTANCE

    path = config_path
    if path is None:
        env_path = os.environ.get("PIPELINE_CONFIG")
        if env_path:
            path = Path(env_path)
        else:
            path = _DEFAULT_CONFIG_PATH

    if path.exists():
        raw = _load_yaml(path)
        _CONFIG_INSTANCE = PipelineConfig.from_dict(raw)
    else:
        _CONFIG_INSTANCE = PipelineConfig()

    env_deals_root = os.environ.get("ABS_WATERFALL_DEALS_ROOT") or os.environ.get("ABS_DEALS_ROOT")
    if env_deals_root and _CONFIG_INSTANCE is not None:
        _CONFIG_INSTANCE.pipeline.deals_root = _resolve_deals_root(env_deals_root)
    elif _CONFIG_INSTANCE is not None:
        _CONFIG_INSTANCE.pipeline.deals_root = _resolve_deals_root(_CONFIG_INSTANCE.pipeline.deals_root)

    return _CONFIG_INSTANCE


def reset_config() -> None:
    """Reset singleton for testing."""
    global _CONFIG_INSTANCE
    _CONFIG_INSTANCE = None
