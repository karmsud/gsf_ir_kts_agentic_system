"""
JSON schemas for pipeline artifacts.
Used by csv_validator and ingestion_validator.
Ported from AI Payment Generator pipeline.config.schemas.
"""

from __future__ import annotations

# =============================================================================
# CSV Schemas — column definitions for each CSV type
# =============================================================================

DEAL_SETUP_SCHEMA = {
    "required_columns": [
        "deal_name", "issuer", "series", "shelf", "closing_date",
        "initial_pool_balance", "servicer_fee_rate", "trustee_fee_rate",
    ],
    "optional_columns": [
        "master_servicer_fee_rate", "insurance_fee_rate", "cutoff_date",
        "first_payment_date", "payment_frequency", "day_count_convention", "accrual_period",
    ],
    "types": {
        "initial_pool_balance": "float", "servicer_fee_rate": "float",
        "trustee_fee_rate": "float", "master_servicer_fee_rate": "float",
        "insurance_fee_rate": "float",
    },
}

CLASSES_SETUP_SCHEMA = {
    "required_columns": [
        "class_name", "class_type", "original_balance",
        "certificate_rate", "certificate_margin",
    ],
    "optional_columns": [
        "rate_type", "rate_cap", "rate_floor", "group", "priority",
        "accrual_type", "step_down_date", "target_oc_amount",
    ],
    "types": {
        "original_balance": "float", "certificate_rate": "float",
        "certificate_margin": "float", "rate_cap": "float",
        "rate_floor": "float", "priority": "int", "target_oc_amount": "float",
    },
}

MONTHLY_INPUT_SCHEMA = {
    "required_columns": [
        "month", "beginning_pool_balance", "scheduled_principal",
        "prepayments", "realized_losses", "recoveries", "interest_collected",
    ],
    "optional_columns": [
        "one_month_libor", "one_month_sofr", "delinquency_30",
        "delinquency_60", "delinquency_90", "delinquency_90plus",
        "foreclosures", "reo",
    ],
    "types": {
        "month": "int", "beginning_pool_balance": "float",
        "scheduled_principal": "float", "prepayments": "float",
        "realized_losses": "float", "recoveries": "float",
        "interest_collected": "float", "one_month_libor": "float",
        "one_month_sofr": "float",
    },
}

CLASS_BALANCES_SCHEMA = {
    "required_columns": ["class_name", "beginning_balance"],
    "optional_columns": [
        "accrued_interest", "cumulative_losses",
        "write_down_amount", "overcollateralization_amount",
    ],
    "types": {
        "beginning_balance": "float", "accrued_interest": "float",
        "cumulative_losses": "float", "write_down_amount": "float",
        "overcollateralization_amount": "float",
    },
}

OUTPUT_TEACHING_SCHEMA = {
    "required_columns": [
        "class_name", "interest_paid", "principal_paid", "ending_balance",
    ],
    "optional_columns": [
        "interest_shortfall", "principal_shortfall",
        "losses_allocated", "write_down", "certificate_rate",
    ],
    "types": {
        "interest_paid": "float", "principal_paid": "float",
        "ending_balance": "float", "interest_shortfall": "float",
        "principal_shortfall": "float", "losses_allocated": "float",
        "write_down": "float", "certificate_rate": "float",
    },
}

SCHEMA_REGISTRY: dict[str, dict] = {
    "deal_setup": DEAL_SETUP_SCHEMA,
    "classes_setup": CLASSES_SETUP_SCHEMA,
    "monthly_input": MONTHLY_INPUT_SCHEMA,
    "class_balances": CLASS_BALANCES_SCHEMA,
    "output_teaching": OUTPUT_TEACHING_SCHEMA,
}

# =============================================================================
# Extraction JSON Schemas
# =============================================================================

DEFINITIONS_SCHEMA = {
    "required_fields": ["external_id", "name", "definition_text"],
    "optional_fields": [
        "python_name", "concise_definition", "data_type",
        "depends_on", "is_calculated", "source_section",
    ],
    "id_prefix": "DEF-",
}

WATERFALL_RULES_SCHEMA = {
    "required_fields": ["rule_id", "priority", "description"],
    "optional_fields": [
        "payment_type", "target_class", "formula",
        "condition", "source_section",
    ],
    "id_prefix": "RULE-",
}

ACCOUNTS_SCHEMA = {
    "required_fields": ["account_name", "purpose"],
    "optional_fields": [
        "external_id", "funding_source", "disbursement_rules", "source_section",
    ],
    "id_prefix": "ACC-",
}

LOSS_ALLOCATIONS_SCHEMA = {
    "required_fields": ["rule_id", "description"],
    "optional_fields": [
        "allocation_order", "classes_affected", "formula", "source_section",
    ],
    "id_prefix": "LOSS-",
}

TRIGGERS_SCHEMA = {
    "required_fields": ["trigger_name", "condition"],
    "optional_fields": [
        "external_id", "threshold", "consequence", "source_section",
    ],
    "id_prefix": "TRIG-",
}

REPORTING_REQUIREMENTS_SCHEMA = {
    "required_fields": ["requirement", "frequency"],
    "optional_fields": [
        "external_id", "responsible_party", "format", "source_section",
    ],
    "id_prefix": "RPT-",
}

EXTRACTION_SCHEMA_REGISTRY: dict[str, dict] = {
    "definitions": DEFINITIONS_SCHEMA,
    "waterfall_rules": WATERFALL_RULES_SCHEMA,
    "accounts": ACCOUNTS_SCHEMA,
    "loss_allocations": LOSS_ALLOCATIONS_SCHEMA,
    "triggers": TRIGGERS_SCHEMA,
    "reporting_requirements": REPORTING_REQUIREMENTS_SCHEMA,
}

# =============================================================================
# Document Type Signatures
# =============================================================================

DOC_TYPE_SIGNATURES = {
    "psa": {
        "filename_patterns": [r"pooling.*servicing", r"psa", r"pool.*serv"],
        "content_patterns": [
            r"pooling\s+and\s+servicing\s+agreement",
            r"distribution\s+date", r"waterfall",
            r"certificate\s+balance", r"servicer\s+shall",
        ],
        "min_matches": 2,
    },
    "indenture": {
        "filename_patterns": [r"indenture", r"trust\s*indenture"],
        "content_patterns": [
            r"indenture", r"trustee", r"noteholder", r"event\s+of\s+default",
        ],
        "min_matches": 2,
    },
    "prospectus_supplement": {
        "filename_patterns": [r"prospectus\s*supplement", r"prosup"],
        "content_patterns": [
            r"prospectus\s+supplement", r"securit", r"offering", r"risk\s+factor",
        ],
        "min_matches": 2,
    },
    "trust_agreement": {
        "filename_patterns": [r"trust\s*agreement"],
        "content_patterns": [
            r"trust\s+agreement", r"certificate", r"beneficial\s+interest",
        ],
        "min_matches": 2,
    },
    "servicing_agreement": {
        "filename_patterns": [r"servicing\s*agreement", r"sub.?servicing"],
        "content_patterns": [
            r"servicing\s+agreement", r"servicer",
            r"servicing\s+fee", r"collection",
        ],
        "min_matches": 2,
    },
}
