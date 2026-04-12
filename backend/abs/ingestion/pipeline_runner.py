"""
Pipeline Runner — Orchestrator for the full ingestion-to-generation pipeline.

Provides the top-level interface for all pipeline operations:
  ingest()     — Stages 1-5: raw document → ingested deal
  generate()   — Stages 6-8: deal data → payment model
  validate()   — Check model output against teaching
  run_monthly() — Stage 9: monthly production run
  compare()    — Cross-deal comparison
  status()     — Current pipeline status

Supports resume: tracks stage progress in pipeline_state.json.

Ported from PayGen pipeline.ingestion.pipeline_runner → backend.abs.ingestion
Import rewrites:
  pipeline.deal_scope          → backend.abs.deal_scope
  pipeline.deal_manifest       → backend.abs.deal_manifest
  pipeline.config.constants    → backend.abs.config.constants
  pipeline.config.pipeline_config → backend.abs.config.pipeline_config
  pipeline.ingestion.*         → backend.abs.ingestion.*
  pipeline.generation.*        → backend.abs.generation.*
  pipeline.skills.*            → backend.abs.skills.*
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.abs.deal_scope import DealScope
from backend.abs.deal_manifest import (
    DealManifest,
    DocumentEntry,
    DocumentType,
    IngestionStatus,
)
from backend.abs.config.constants import PIPELINE_VERSION

logger = logging.getLogger(__name__)


@dataclass
class PipelineState:
    """Tracks pipeline progress for resume capability."""
    deal_id: str
    current_stage: int
    completed_stages: list[int] = field(default_factory=list)
    stage_results: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    updated_at: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "deal_id": self.deal_id,
            "current_stage": self.current_stage,
            "completed_stages": self.completed_stages,
            "stage_results": self.stage_results,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PipelineState:
        return cls(
            deal_id=data.get("deal_id", ""),
            current_stage=data.get("current_stage", 0),
            completed_stages=data.get("completed_stages", []),
            stage_results=data.get("stage_results", {}),
            started_at=data.get("started_at", ""),
            updated_at=data.get("updated_at", ""),
            errors=data.get("errors", []),
        )

    def save(self, deal_path: Path) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()
        state_path = Path(deal_path) / "pipeline_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(self.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, deal_path: Path) -> PipelineState:
        state_path = Path(deal_path) / "pipeline_state.json"
        if state_path.exists():
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        return cls(deal_id="", current_stage=0)


class PipelineRunner:
    """
    Orchestrates the full ABS Waterfall AI pipeline.

    Usage:
        runner = PipelineRunner(deals_root=Path("deals"))
        manifest = runner.ingest("bear_stearns_2006_he2", Path("source.docx"))
        model_path = runner.generate("bear_stearns_2006_he2")
        result = runner.validate("bear_stearns_2006_he2", month=1)
    """

    def __init__(self, deals_root: Path):
        """
        Args:
            deals_root: Root path to deals/ directory
        """
        self.deals_root = Path(deals_root)
        self.deals_root.mkdir(parents=True, exist_ok=True)

    def ingest(
        self,
        deal_id: str,
        document_path: Path,
        issuer: str = "default",
        is_payment_source: bool = True,
    ) -> dict[str, Any]:
        """
        Run Stages 1-5: Ingest a raw document into a structured deal.

        Stage 1: Document Conversion (DOCX → MD + TXT + metadata)
        Stage 2: Section Splitting (full.md → sections/*.md)
        Stage 3: Structured Extraction (sections → JSON + CSV)
        Stage 4: Knowledge Store Build (Chroma + NetworkX)
        Stage 5: Governing Doc Generation

        Args:
            deal_id: Unique deal identifier
            document_path: Path to source document (.docx, .pdf, .md)
            issuer: Issuer name for section map lookup
            is_payment_source: Whether this is the payment source of truth

        Returns:
            Dict with ingestion result details
        """
        from backend.abs.ingestion.document_converter import convert_document
        from backend.abs.ingestion.section_splitter import split_document
        from backend.abs.ingestion.structured_extractor import extract_all_sections
        from backend.abs.ingestion.definition_resolution import build_definition_resolution_artifacts
        from backend.abs.ingestion.knowledge_store import build_knowledge_store
        from backend.abs.ingestion.governing_doc_generator import generate_governing_docs
        from backend.abs.ingestion.ingestion_validator import (
            validate_ingestion,
            save_ingestion_manifest,
        )
        from backend.abs.ingestion.document_intelligence import classify_and_check_duplicate

        document_path = Path(document_path)
        scope = DealScope.create(deal_id, self.deals_root)

        state = PipelineState(
            deal_id=deal_id,
            current_stage=0,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        result: dict[str, Any] = {
            "deal_id": deal_id,
            "document": document_path.name,
            "stages": {},
        }

        # Determine document sub-directory
        doc_type_dir = "psa" if is_payment_source else "supplementary"
        source_dir = scope.resolve(f"documents/{doc_type_dir}/source")
        source_dir = Path(source_dir)
        source_dir.mkdir(parents=True, exist_ok=True)

        sections_dir = scope.resolve(f"documents/{doc_type_dir}/sections")
        extractions_dir = scope.resolve(f"documents/{doc_type_dir}/extractions")
        data_dir = scope.resolve("data")
        vectorstore_dir = scope.resolve("vectorstore")
        graph_dir = scope.resolve("graph")
        governing_dir = scope.resolve("governing_docs")

        for d in [sections_dir, extractions_dir, data_dir,
                  vectorstore_dir, graph_dir, governing_dir]:
            Path(d).mkdir(parents=True, exist_ok=True)

        try:
            # ── Stage 1: Document Conversion ──────────────────
            state.current_stage = 1
            state.save(scope.deal_path)

            if 1 not in state.completed_stages:
                logger.info(f"[{deal_id}] Stage 1: Converting document...")
                conversion = convert_document(
                    source_path=document_path,
                    output_dir=source_dir,
                    deal_id=deal_id,
                )
                result["stages"]["stage_1"] = conversion.to_dict()
                state.completed_stages.append(1)
                state.stage_results["stage_1"] = conversion.to_dict()
                state.save(scope.deal_path)

            # ── Stage 2: Section Splitting ─────────────────────
            state.current_stage = 2
            state.save(scope.deal_path)

            if 2 not in state.completed_stages:
                logger.info(f"[{deal_id}] Stage 2: Splitting into sections...")
                full_md = source_dir / "full.md"
                split_result = split_document(
                    full_md_path=full_md,
                    output_dir=sections_dir,
                    issuer=issuer,
                )
                result["stages"]["stage_2"] = split_result.to_dict()
                state.completed_stages.append(2)
                state.stage_results["stage_2"] = split_result.to_dict()
                state.save(scope.deal_path)

            # ── Stage 3: Structured Extraction ─────────────────
            state.current_stage = 3
            state.save(scope.deal_path)

            if 3 not in state.completed_stages:
                logger.info(f"[{deal_id}] Stage 3: Extracting structured data...")
                extraction = extract_all_sections(
                    sections_dir=sections_dir,
                    output_dir=extractions_dir,
                    data_dir=data_dir,
                    deal_id=deal_id,
                )
                result["stages"]["stage_3"] = extraction.to_dict()
                state.completed_stages.append(3)
                state.stage_results["stage_3"] = extraction.to_dict()
                state.save(scope.deal_path)

            # ── Stage 3.5: Definition Resolution ───────────────
            from backend.abs.config.pipeline_config import get_config
            cfg = get_config()
            if cfg.definition_resolution.enabled and "stage_3_5" not in state.stage_results:
                logger.info(f"[{deal_id}] Stage 3.5: Building definition resolution artifacts...")
                resolution = build_definition_resolution_artifacts(
                    extractions_dir=extractions_dir,
                    graph_dir=graph_dir,
                    deal_id=deal_id,
                    min_confidence=cfg.definition_resolution.min_confidence,
                    max_depth=cfg.definition_resolution.max_depth,
                )
                result["stages"]["stage_3_5"] = resolution.to_dict()
                state.stage_results["stage_3_5"] = resolution.to_dict()
                state.save(scope.deal_path)

            # ── Stage 4: Knowledge Store ───────────────────────
            state.current_stage = 4
            state.save(scope.deal_path)

            if 4 not in state.completed_stages:
                # Check config to decide if vectorstore is enabled
                from backend.abs.config.pipeline_config import get_config
                cfg = get_config()

                if not cfg.vectorstore.enabled:
                    logger.info(
                        f"[{deal_id}] Stage 4: Vectorstore disabled in config; "
                        f"building graph only..."
                    )
                    # Build graph only (skip Chroma)
                    try:
                        from backend.abs.skills.graph_builder import build_graph, save_graph
                        ext_data: dict = {}
                        for jf in sorted(Path(extractions_dir).glob("*.json")):
                            import json as _json
                            data = _json.loads(jf.read_text(encoding="utf-8"))
                            if isinstance(data, list):
                                ext_data[jf.stem] = data
                        if ext_data:
                            graph = build_graph(ext_data, deal_id)
                            save_graph(graph, Path(graph_dir) / "deal_graph.json")
                            result["stages"]["stage_4"] = {
                                "vector_count": 0,
                                "graph_node_count": graph.number_of_nodes(),
                                "graph_edge_count": graph.number_of_edges(),
                                "vectorstore_skipped": True,
                            }
                        else:
                            result["stages"]["stage_4"] = {
                                "vector_count": 0,
                                "graph_node_count": 0,
                                "graph_edge_count": 0,
                                "vectorstore_skipped": True,
                            }
                    except Exception as e:
                        logger.warning(f"[{deal_id}] Stage 4: Graph-only build failed: {e}")
                        result["stages"]["stage_4"] = {"skipped": True, "reason": str(e)}
                else:
                    logger.info(f"[{deal_id}] Stage 4: Building knowledge store...")
                    try:
                        ks_result = build_knowledge_store(
                            sections_dir=sections_dir,
                            extractions_dir=extractions_dir,
                            vectorstore_dir=vectorstore_dir,
                            graph_dir=graph_dir,
                            deal_id=deal_id,
                        )
                        result["stages"]["stage_4"] = ks_result.to_dict()
                    except ImportError as e:
                        logger.warning(
                            f"[{deal_id}] Stage 4: Skipping vector store "
                            f"(dependency unavailable: {e})"
                        )
                        result["stages"]["stage_4"] = {"skipped": True, "reason": str(e)}

                state.completed_stages.append(4)
                state.stage_results["stage_4"] = result["stages"].get("stage_4", {})
                state.save(scope.deal_path)

            # ── Stage 5: Governing Doc Generation ──────────────
            state.current_stage = 5
            state.save(scope.deal_path)

            if 5 not in state.completed_stages:
                logger.info(f"[{deal_id}] Stage 5: Generating governing docs...")
                gov_result = generate_governing_docs(
                    extractions_dir=extractions_dir,
                    sections_dir=sections_dir,
                    output_dir=governing_dir,
                    deal_id=deal_id,
                )
                result["stages"]["stage_5"] = gov_result.to_dict()
                state.completed_stages.append(5)
                state.stage_results["stage_5"] = gov_result.to_dict()
                state.save(scope.deal_path)

            # ── Validation Gate ────────────────────────────────
            logger.info(f"[{deal_id}] Validating ingestion artifacts...")
            validation = validate_ingestion(
                deal_path=scope.deal_path,
                sections_dir=sections_dir,
                extractions_dir=extractions_dir,
                data_dir=data_dir,
                vectorstore_dir=vectorstore_dir,
                graph_dir=graph_dir,
            )
            result["validation"] = validation.to_dict()

            # Save ingestion manifest
            manifest_path = save_ingestion_manifest(
                deal_path=scope.deal_path,
                validation_result=validation,
                deal_id=deal_id,
                source_document=document_path.name,
            )
            result["ingestion_manifest"] = str(manifest_path)
            result["ready_for_model_generation"] = validation.is_ready

            state.current_stage = 6  # Ready for generation
            state.save(scope.deal_path)

        except Exception as e:
            state.errors.append(f"Stage {state.current_stage} failed: {e}")
            state.save(scope.deal_path)
            result["error"] = str(e)
            result["failed_stage"] = state.current_stage
            raise

        return result

    def generate(self, deal_id: str) -> Path:
        """
        Run Stages 6-8: Generate payment model from ingested deal data.

        Args:
            deal_id: Deal identifier

        Returns:
            Path to generated payment model
        """
        scope = DealScope.create(deal_id, self.deals_root)
        data_dir = scope.resolve("data")

        from backend.abs.generation.data_prep import (
            load_deal_setup,
            load_classes_setup,
            prepare_month_data,
        )

        # Stage 6: Data preparation
        deal_setup = load_deal_setup(data_dir)
        classes_setup = load_classes_setup(data_dir)

        # Stage 7: Model creation (placeholder — requires LLM)
        model_path = scope.resolve("models/payment_model.py")
        Path(model_path).parent.mkdir(parents=True, exist_ok=True)

        if not Path(model_path).exists():
            # Create a template model
            template = _generate_model_template(deal_id, deal_setup, classes_setup)
            Path(model_path).write_text(template, encoding="utf-8")

        return Path(model_path)

    def validate(self, deal_id: str, month: int = 1) -> dict:
        """
        Validate model output against expected (teaching) data.

        Args:
            deal_id: Deal identifier
            month: Month number to validate

        Returns:
            Dict with validation results
        """
        from backend.abs.generation.model_validator import validate_model_output

        scope = DealScope.create(deal_id, self.deals_root)
        output_path = scope.resolve(f"runs/month_{month}/output.csv")
        teaching_path = scope.resolve(f"data/month_{month}/output_teaching.csv")

        if not Path(output_path).exists():
            return {"valid": False, "error": "Model output not found"}
        if not Path(teaching_path).exists():
            return {"valid": False, "error": "Teaching data not found"}

        result = validate_model_output(Path(output_path), Path(teaching_path))
        return result.to_dict()

    def run_monthly(self, deal_id: str, month: int) -> Path:
        """
        Run Stage 9: Monthly production run.

        Args:
            deal_id: Deal identifier
            month: Month number

        Returns:
            Path to output CSV
        """
        from backend.abs.generation.model_runner import run_model_for_month

        scope = DealScope.create(deal_id, self.deals_root)
        model_path = scope.resolve("models/payment_model.py")
        data_dir = scope.resolve("data")
        output_dir = scope.resolve(f"runs/month_{month}")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        result = run_model_for_month(
            model_path=Path(model_path),
            data_dir=Path(data_dir),
            month=month,
            output_dir=Path(output_dir),
        )

        return Path(result.output_path) if result.output_path else Path(output_dir)

    def compare(self, deal_id: str) -> dict:
        """
        Run cross-deal comparison to find closest matching deal.

        Args:
            deal_id: Deal identifier to compare

        Returns:
            Dict with comparison results
        """
        from backend.abs.skills.deal_comparator import compare_deals

        scope = DealScope.create_read_only(deal_id, self.deals_root)

        # Find other deals to compare against
        other_deals = [
            d.name for d in self.deals_root.iterdir()
            if d.is_dir() and d.name != deal_id
        ]

        results = []
        for other_id in other_deals:
            try:
                other_scope = DealScope.create_read_only(other_id, self.deals_root)
                comparison = compare_deals(scope.deal_path, other_scope.deal_path)
                results.append({
                    "deal_id": other_id,
                    "similarity": comparison.get("overall_similarity", 0),
                    "details": comparison,
                })
            except Exception as e:
                logger.warning(f"Comparison with {other_id} failed: {e}")

        # Sort by similarity (descending)
        results.sort(key=lambda x: x["similarity"], reverse=True)

        return {
            "deal_id": deal_id,
            "comparisons": results,
            "closest_match": results[0] if results else None,
        }

    def status(self, deal_id: str) -> dict:
        """
        Get current pipeline status for a deal.

        Args:
            deal_id: Deal identifier

        Returns:
            Dict with status information
        """
        deal_path = self.deals_root / deal_id

        if not deal_path.exists():
            return {"deal_id": deal_id, "status": "not_found"}

        state = PipelineState.load(deal_path)

        # Check for ingestion manifest
        ingestion_manifest = deal_path / "ingestion_manifest.json"
        ingestion_ready = False
        if ingestion_manifest.exists():
            try:
                data = json.loads(ingestion_manifest.read_text(encoding="utf-8"))
                ingestion_ready = data.get("ready_for_model_generation", False)
            except Exception:
                pass

        # Check for model
        model_exists = (deal_path / "models" / "payment_model.py").exists()

        return {
            "deal_id": deal_id,
            "status": "active",
            "current_stage": state.current_stage,
            "completed_stages": state.completed_stages,
            "ingestion_ready": ingestion_ready,
            "model_exists": model_exists,
            "errors": state.errors,
            "pipeline_version": PIPELINE_VERSION,
        }


def _generate_model_template(
    deal_id: str,
    deal_setup: dict,
    classes_setup: list[dict] | "pd.DataFrame",
) -> str:
    """Generate a comprehensive payment_model.py from extracted deal data."""
    import csv as _csv_module
    from io import StringIO

    # ── Convert classes_setup to list of dicts if DataFrame ───────
    if hasattr(classes_setup, "to_dict"):
        classes_list = classes_setup.to_dict("records")
    elif isinstance(classes_setup, list):
        classes_list = classes_setup
    else:
        classes_list = []

    # ── Build margin dict ────────────────────────────────────────
    margin_lines = []
    class_name_lines = []
    group1_classes = []
    group2_classes = []
    mezzanine_classes = []
    idx = 1
    class_index_map: dict[str, int] = {}

    # Filter to actual certificate classes (has valid margin)
    import math
    def _has_valid_margin(val):
        if val is None or val == "":
            return False
        try:
            return not math.isnan(float(val)) and float(val) > 0
        except (ValueError, TypeError):
            return False

    actual_classes = [
        c for c in classes_list
        if c.get("class_type") in ("senior", "mezzanine")
        and _has_valid_margin(c.get("margin"))
    ]

    for c in actual_classes:
        name = c.get("class_name", "")
        margin = c.get("margin", "")
        group = c.get("group", "")
        ctype = c.get("class_type", "")

        margin_val = float(margin) if margin else 0.0
        margin_lines.append(f'    {idx}: {margin_val},  # {name}: {margin_val*100:.3f}%')
        class_name_lines.append(f'    {idx}: "{name}",')
        class_index_map[name] = idx

        # Normalize group: pandas may read as float (1.0) or int (1)
        try:
            group_norm = str(int(float(group))) if group not in (None, "", "nan") and str(group) not in ("nan", "NaN") else ""
        except (ValueError, TypeError):
            group_norm = str(group).strip()

        if group_norm == "1" and ctype == "senior":
            group1_classes.append(str(idx))
        elif group_norm == "2" and ctype == "senior":
            group2_classes.append(str(idx))
        elif ctype == "mezzanine":
            mezzanine_classes.append(str(idx))

        idx += 1

    # ── Pool balance ─────────────────────────────────────────────
    pool_g1 = deal_setup.get("pool_balance_group_I", "0")
    pool_g2 = deal_setup.get("pool_balance_group_II", "0")
    try:
        total_pool = float(pool_g1) + float(pool_g2)
    except (ValueError, TypeError):
        total_pool = 0.0

    svc_rate = deal_setup.get("servicing_fee_rate", "0.005")
    trustee_rate = deal_setup.get("trustee_fee_rate", "0.000058")
    reserve_g1 = deal_setup.get("reserve_fund_group_I", "5000")
    reserve_g2 = deal_setup.get("reserve_fund_group_II", "5000")
    closing = deal_setup.get("closing_date", "")
    cutoff = deal_setup.get("cutoff_date", "")
    dist_date = deal_setup.get("distribution_date", "")

    margins_block = "\n".join(margin_lines) if margin_lines else "    # No margins extracted"
    names_block = "\n".join(class_name_lines) if class_name_lines else "    # No classes extracted"
    g1_block = ", ".join(group1_classes) if group1_classes else "# Group 1 classes not identified"
    g2_block = ", ".join(group2_classes) if group2_classes else "# Group 2 classes not identified"
    mezz_block = ", ".join(mezzanine_classes) if mezzanine_classes else "# Mezzanine classes not identified"

    return f'''"""
================================================================================
PAYMENT MODEL: {deal_id}
================================================================================
Auto-generated from PSA extraction pipeline.

Deal: {deal_id}
Closing Date: {closing}
Cut-off Date: {cutoff}
Distribution Date: {dist_date}
Pool Balance Group I: ${float(pool_g1):,.2f}
Pool Balance Group II: ${float(pool_g2):,.2f}
Total Pool: ${total_pool:,.2f}

GENERATED FROM GOVERNING DOCUMENTS — Review before production use.
================================================================================
"""

import csv
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from pathlib import Path


# ==============================================================================
# SECTION 1: DEAL CONSTANTS (Extracted from PSA)
# ==============================================================================

DEAL_ID = "{deal_id}"
CLOSING_DATE = "{closing}"
CUTOFF_DATE = "{cutoff}"

# Pool balances
POOL_BALANCE_GROUP_1 = {float(pool_g1):.2f}
POOL_BALANCE_GROUP_2 = {float(pool_g2):.2f}
ORIGINAL_POOL_BALANCE = {total_pool:.2f}

# Fee rates
SERVICING_FEE_RATE = {float(svc_rate)}    # {float(svc_rate)*100:.3f}% per annum
TRUSTEE_FEE_RATE = {float(trustee_rate)}   # {float(trustee_rate)*100:.4f}% per annum

# Reserve fund
RESERVE_FUND_GROUP_1 = {float(reserve_g1):.2f}
RESERVE_FUND_GROUP_2 = {float(reserve_g2):.2f}

# Certificate Margins (LIBOR + Margin = Pass-Through Rate)
CERTIFICATE_MARGINS = {{{{
{margins_block}
}}}}

# Class names
CLASS_NAMES = {{{{
{names_block}
}}}}

# Loan group assignments
LOAN_GROUP_1_CLASSES = [{g1_block}]
LOAN_GROUP_2_CLASSES = [{g2_block}]
MEZZANINE_CLASSES = [{mezz_block}]

# Day count: actual/360 for A and M certificates
DAY_COUNT = "actual/360"


# ==============================================================================
# SECTION 2: DATA LOADING
# ==============================================================================

def load_data(base_path: str) -> dict:
    """Load all input data from CSV files."""
    path = Path(base_path)

    def load_kv(filepath):
        df = pd.read_csv(filepath)
        return {{{{row["Field"]: row["Value"] for _, row in df.iterrows()}}}}

    data = {{{{
        "monthly": load_kv(path / "monthly_input.csv"),
        "deal": load_kv(path.parent / "deal_setup.csv"),
    }}}}

    # Load class balances
    balances_df = pd.read_csv(path / "class_balances.csv")
    name_to_idx = {{{{v: k for k, v in CLASS_NAMES.items()}}}}
    data["balances"] = {{{{}}}}
    for _, row in balances_df.iterrows():
        cls_name = row["class_name"]
        if cls_name in name_to_idx:
            data["balances"][name_to_idx[cls_name]] = float(row["beginning_balance"])

    return data


# ==============================================================================
# SECTION 3: INTEREST CALCULATION
# ==============================================================================

def calculate_net_rate_caps(
    grp1_interest: float,
    grp2_interest: float,
    grp1_balance: float,
    grp2_balance: float,
    actual_days: int,
) -> Dict[int, float]:
    """Calculate Net Rate Cap for each class based on loan group yields."""
    day_factor = 30 / actual_days if actual_days > 0 else 1.0

    grp1_cap = (grp1_interest * 12 / grp1_balance) * day_factor if grp1_balance > 0 else 0
    grp2_cap = (grp2_interest * 12 / grp2_balance) * day_factor if grp2_balance > 0 else 0

    total_balance = grp1_balance + grp2_balance
    combined_cap = ((grp1_interest + grp2_interest) * 12 / total_balance) * day_factor if total_balance > 0 else 0

    caps = {{{{}}}}
    for i in LOAN_GROUP_1_CLASSES:
        caps[i] = grp1_cap
    for i in LOAN_GROUP_2_CLASSES:
        caps[i] = grp2_cap
    for i in MEZZANINE_CLASSES:
        caps[i] = combined_cap
    return caps


def calculate_pass_through_rates(
    libor: float, net_rate_caps: Dict[int, float],
) -> Dict[int, float]:
    """Calculate actual pass-through rate = min(LIBOR + Margin, Net Rate Cap)."""
    rates = {{{{}}}}
    for cls_idx, margin in CERTIFICATE_MARGINS.items():
        libor_plus = libor + margin
        cap = net_rate_caps.get(cls_idx, libor_plus)
        rates[cls_idx] = min(libor_plus, cap)
    return rates


def calculate_interest_due(
    balances: Dict[int, float],
    rates: Dict[int, float],
    actual_days: int,
) -> Dict[int, float]:
    """Calculate interest due for each class: balance * rate * days / 360."""
    interest = {{{{}}}}
    for cls_idx in CERTIFICATE_MARGINS:
        bal = balances.get(cls_idx, 0.0)
        rate = rates.get(cls_idx, 0.0)
        interest[cls_idx] = bal * rate * actual_days / 360
    return interest


# ==============================================================================
# SECTION 4: WATERFALL DISTRIBUTION
# ==============================================================================

def distribute_interest(
    interest_remittance: float,
    interest_due: Dict[int, float],
    balances: Dict[int, float],
) -> Tuple[Dict[int, float], float]:
    """
    Distribute interest per waterfall priority.
    Returns (amounts_paid, remaining).
    """
    paid = {{{{cls: 0.0 for cls in CERTIFICATE_MARGINS}}}}
    remaining = interest_remittance

    # Step 1: Senior classes from own loan group
    for cls_idx in LOAN_GROUP_1_CLASSES + LOAN_GROUP_2_CLASSES:
        due = interest_due.get(cls_idx, 0.0)
        payment = min(due, remaining)
        paid[cls_idx] = payment
        remaining -= payment

    # Step 2: Mezzanine classes sequentially
    for cls_idx in MEZZANINE_CLASSES:
        due = interest_due.get(cls_idx, 0.0)
        payment = min(due, remaining)
        paid[cls_idx] = payment
        remaining -= payment

    return paid, remaining


def distribute_principal(
    principal_distribution: float,
    balances: Dict[int, float],
    is_pre_stepdown: bool = True,
    trigger_active: bool = False,
) -> Tuple[Dict[int, float], float]:
    """
    Distribute principal per waterfall priority.
    Returns (amounts_paid, remaining).
    """
    paid = {{{{cls: 0.0 for cls in CERTIFICATE_MARGINS}}}}
    remaining = principal_distribution

    if is_pre_stepdown or trigger_active:
        # Sequential: seniors first, then mezzanine sequentially
        for cls_idx in LOAN_GROUP_1_CLASSES + LOAN_GROUP_2_CLASSES:
            bal = balances.get(cls_idx, 0.0)
            payment = min(bal, remaining)
            paid[cls_idx] = payment
            remaining -= payment

        for cls_idx in MEZZANINE_CLASSES:
            bal = balances.get(cls_idx, 0.0)
            payment = min(bal, remaining)
            paid[cls_idx] = payment
            remaining -= payment
    else:
        # Pro rata for seniors, then sequential mezzanine
        total_senior = sum(balances.get(c, 0) for c in LOAN_GROUP_1_CLASSES + LOAN_GROUP_2_CLASSES)
        if total_senior > 0:
            senior_payment = min(total_senior, remaining)
            for cls_idx in LOAN_GROUP_1_CLASSES + LOAN_GROUP_2_CLASSES:
                share = balances.get(cls_idx, 0) / total_senior
                paid[cls_idx] = senior_payment * share
            remaining -= senior_payment

        for cls_idx in MEZZANINE_CLASSES:
            bal = balances.get(cls_idx, 0.0)
            payment = min(bal, remaining)
            paid[cls_idx] = payment
            remaining -= payment

    return paid, remaining


# ==============================================================================
# SECTION 5: LOSS ALLOCATION
# ==============================================================================

def allocate_losses(
    loss_amount: float,
    balances: Dict[int, float],
) -> Dict[int, float]:
    """
    Allocate realized losses in reverse order (most junior first).
    """
    allocated = {{{{cls: 0.0 for cls in CERTIFICATE_MARGINS}}}}
    remaining = loss_amount

    # Reverse priority: most junior mezzanine first
    for cls_idx in reversed(MEZZANINE_CLASSES):
        bal = balances.get(cls_idx, 0.0)
        loss = min(bal, remaining)
        allocated[cls_idx] = loss
        remaining -= loss

    # Then seniors
    for cls_idx in reversed(LOAN_GROUP_2_CLASSES + LOAN_GROUP_1_CLASSES):
        bal = balances.get(cls_idx, 0.0)
        loss = min(bal, remaining)
        allocated[cls_idx] = loss
        remaining -= loss

    return allocated


# ==============================================================================
# SECTION 6: MAIN RUN FUNCTION
# ==============================================================================

def run(data_dir: str, month: int, output_path: str) -> None:
    """Run payment model for a given month."""
    data_dir = Path(data_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    month_dir = data_dir / f"month_{{{{month}}}}"
    if not month_dir.exists():
        raise FileNotFoundError(f"Month data not found: {{{{month_dir}}}}")

    data = load_data(str(month_dir))
    monthly = data["monthly"]
    balances = data["balances"]

    # Extract monthly inputs
    libor = float(monthly.get("libor", 0.05))
    actual_days = int(monthly.get("actual_days", 30))
    grp1_interest = float(monthly.get("group1_interest", 0))
    grp2_interest = float(monthly.get("group2_interest", 0))
    grp1_balance = float(monthly.get("group1_pool_balance", POOL_BALANCE_GROUP_1))
    grp2_balance = float(monthly.get("group2_pool_balance", POOL_BALANCE_GROUP_2))
    total_collections = float(monthly.get("total_collections", 0))
    loss_amount = float(monthly.get("loss_amount", 0))

    # Calculate rates
    net_rate_caps = calculate_net_rate_caps(
        grp1_interest, grp2_interest, grp1_balance, grp2_balance, actual_days,
    )
    rates = calculate_pass_through_rates(libor, net_rate_caps)
    interest_due = calculate_interest_due(balances, rates, actual_days)

    # Calculate fees
    total_balance = sum(balances.values())
    servicing_fee = total_balance * SERVICING_FEE_RATE * actual_days / 360
    trustee_fee = total_balance * TRUSTEE_FEE_RATE * actual_days / 360

    # Interest Remittance Amount
    interest_remittance = total_collections - servicing_fee - trustee_fee

    # Distribute interest
    interest_paid, remaining_interest = distribute_interest(
        interest_remittance, interest_due, balances,
    )

    # Principal distribution
    principal_collections = float(monthly.get("principal_collections", 0))
    principal_paid, remaining_principal = distribute_principal(
        principal_collections, balances,
    )

    # Allocate losses
    losses_allocated = allocate_losses(loss_amount, balances)

    # Calculate ending balances
    ending_balances = {{{{}}}}
    for cls_idx in CERTIFICATE_MARGINS:
        ending_balances[cls_idx] = (
            balances.get(cls_idx, 0.0)
            - principal_paid.get(cls_idx, 0.0)
            - losses_allocated.get(cls_idx, 0.0)
        )

    # Write output
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "class_name", "beginning_balance", "interest_due",
            "interest_paid", "principal_paid", "losses",
            "ending_balance", "pass_through_rate",
        ])
        for cls_idx in sorted(CERTIFICATE_MARGINS.keys()):
            writer.writerow([
                CLASS_NAMES[cls_idx],
                f"{{{{balances.get(cls_idx, 0):.2f}}}}",
                f"{{{{interest_due.get(cls_idx, 0):.2f}}}}",
                f"{{{{interest_paid.get(cls_idx, 0):.2f}}}}",
                f"{{{{principal_paid.get(cls_idx, 0):.2f}}}}",
                f"{{{{losses_allocated.get(cls_idx, 0):.2f}}}}",
                f"{{{{ending_balances.get(cls_idx, 0):.2f}}}}",
                f"{{{{rates.get(cls_idx, 0):.8f}}}}",
            ])


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 4:
        run(sys.argv[1], int(sys.argv[2]), sys.argv[3])
'''
