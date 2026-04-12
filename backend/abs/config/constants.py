"""
Pipeline constants — single source for all magic numbers, thresholds, and defaults.
Ported from AI Payment Generator pipeline.config.constants.
"""

# =============================================================================
# Quality Gate Thresholds
# =============================================================================

QUALITY_GATE_MIN_SCORE = 8.0
QUALITY_GATE_MAX_RETRIES = 3

# =============================================================================
# Confidence Tiers (Decision D7: 90/66/0)
# =============================================================================

CONFIDENCE_HIGH_THRESHOLD = 0.90
CONFIDENCE_LOW_THRESHOLD = 0.66

# =============================================================================
# Output Contract Prefixes (Decision D8)
# =============================================================================

OUTPUT_PREFIXES = {
    "definition": "DEF-",
    "rule": "RULE-",
    "account": "ACC-",
    "loss": "LOSS-",
    "trigger": "TRIG-",
    "section": "SEC-",
    "report": "RPT-",
}

# =============================================================================
# Embedding & Vector
# =============================================================================

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
CHUNK_MAX_CHARS = 1000
CHUNK_OVERLAP = 100

# =============================================================================
# Validation
# =============================================================================

OUTPUT_TOLERANCE = 0.01
MIN_DEFINITION_COUNT = 5
MIN_RULE_COUNT = 3
MIN_VECTOR_COUNT = 100

# =============================================================================
# Generate-Evaluate-Refine Loop
# =============================================================================

GER_MAX_ITERATIONS = 3
GER_CONVERGENCE_THRESHOLD = 0.5

# =============================================================================
# Section Names (Canonical)
# =============================================================================

CANONICAL_SECTIONS = [
    "definitions",
    "waterfall",
    "accounts",
    "collections",
    "loss_allocations",
    "triggers",
    "reporting_requirements",
    "credit_enhancement",
    "servicing",
    "events_of_default",
]

# =============================================================================
# File Names (within deal folder)
# =============================================================================

MANIFEST_FILENAME = "deal_manifest.json"
INGESTION_MANIFEST_FILENAME = "ingestion_manifest.json"
GRAPH_FILENAME = "deal_graph.json"
ESCALATION_DIR = "logs/escalations"
ERROR_LOG_FILENAME = "logs/errors.jsonl"

# =============================================================================
# Comparison Weights
# =============================================================================

COMPARISON_WEIGHTS = {
    "definitions": 0.30,
    "waterfall": 0.25,
    "classes": 0.20,
    "triggers": 0.15,
    "accounts": 0.10,
}

# =============================================================================
# Pipeline Version
# =============================================================================

PIPELINE_VERSION = "0.1.0"
