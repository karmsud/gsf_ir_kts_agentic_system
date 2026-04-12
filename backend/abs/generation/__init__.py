# backend/abs/generation/__init__.py
"""ABS payment model generation — data prep, model runner, model validator.

Ported from PayGen pipeline.generation → backend.abs.generation
"""

from backend.abs.generation.data_prep import (
    load_classes_setup,
    load_deal_setup,
    prepare_month_data,
    validate_monthly_inputs,
)
from backend.abs.generation.model_runner import (
    RunResult,
    run_model_for_month,
    run_model_sequence,
)
from backend.abs.generation.model_validator import (
    ValidationResult,
    compare_csv_outputs,
    generate_validation_notes,
    validate_model_output,
)

__all__ = [
    "load_classes_setup",
    "load_deal_setup",
    "prepare_month_data",
    "validate_monthly_inputs",
    "RunResult",
    "run_model_for_month",
    "run_model_sequence",
    "ValidationResult",
    "compare_csv_outputs",
    "generate_validation_notes",
    "validate_model_output",
]
