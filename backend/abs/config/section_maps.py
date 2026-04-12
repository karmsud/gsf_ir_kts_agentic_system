"""
Section maps — per-issuer section header patterns for document splitting.
Maps section header patterns to canonical section names.
Ported from AI Payment Generator pipeline.config.section_maps.
"""

from __future__ import annotations

# Default section map (works for most PSAs)
DEFAULT_SECTION_MAP: dict[str, str] = {
    r"^ARTICLE\s+I\b[\s\S]{0,40}DEFINITION": "definitions",
    r"^ARTICLE\s+(?:IV|V)\b[\s\S]{0,50}DISTRIBUT": "waterfall",
    r"^ARTICLE\s+(?:IV|V)\b[\s\S]{0,50}WATERFALL": "waterfall",
    r"^ARTICLE\s+(?:III|IV)\b[\s\S]{0,40}ACCOUNT": "accounts",
    r"^ARTICLE\s+(?:V|VI)\b[\s\S]{0,40}LOSS": "loss_allocations",
    r"^ARTICLE[\s\S]{0,30}TRIGGER": "triggers",
    r"^ARTICLE[\s\S]{0,30}TERMINATION": "triggers",
    r"^ARTICLE[\s\S]{0,30}REPORT": "reporting_requirements",
    r"^ARTICLE[\s\S]{0,40}CREDIT\s+ENHANCE": "credit_enhancement",
    r"^ARTICLE[\s\S]{0,40}SUBORDINAT": "credit_enhancement",
    r"^ARTICLE[\s\S]{0,40}SERVIC": "servicing",
    r"^ARTICLE[\s\S]{0,40}DEFAULT": "events_of_default",
}

# Bear Stearns-specific map
BEAR_STEARNS_SECTION_MAP: dict[str, str] = {
    r"^ARTICLE\s+I\b(?!\s*[IVXLC])": "definitions",
    r"^ARTICLE\s+III\b": "servicing",
    r"^ARTICLE\s+IV\b": "accounts",
    r"^ARTICLE\s+V\b(?!\s*I)": "waterfall",
    r"^ARTICLE\s+VIII\b": "events_of_default",
    r"^ARTICLE\s+IX\b": "other",
    r"^ARTICLE\s+X\b(?!\s*I)": "triggers",
    r"^ARTICLE\s+XI\b": "other",
    r"^Section\s+5\.05[A-Z]": "loss_allocations",
    r"^Section\s+5\.06[A-Z]": "reporting_requirements",
    r"^Section\s+5\.07[A-Z]": "other",
}

# WHFSC-specific overrides
WHFSC_SECTION_MAP: dict[str, str] = {
    **DEFAULT_SECTION_MAP,
}

# Registry of per-issuer maps
SECTION_MAP_REGISTRY: dict[str, dict[str, str]] = {
    "default": DEFAULT_SECTION_MAP,
    "bear_stearns": BEAR_STEARNS_SECTION_MAP,
    "whfsc": WHFSC_SECTION_MAP,
}


def get_section_map(issuer: str) -> dict[str, str]:
    """Get the section map for a given issuer. Falls back to default."""
    key = issuer.lower().replace(" ", "_").replace("-", "_")
    return SECTION_MAP_REGISTRY.get(key, DEFAULT_SECTION_MAP)
