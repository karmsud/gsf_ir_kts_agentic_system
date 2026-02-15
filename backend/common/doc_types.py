"""
Canonical DocType vocabulary with alias normalization.

This module defines the single source of truth for document type classification.
All ingestion, retrieval, and scoring operations must use normalize_doc_type()
to ensure consistent doc_type values across the system.
"""

from __future__ import annotations
from typing import Final

# Canonical DocType constants
TROUBLESHOOT: Final[str] = "TROUBLESHOOT"
SOP: Final[str] = "SOP"
USER_GUIDE: Final[str] = "USER_GUIDE"
TRAINING: Final[str] = "TRAINING"
RELEASE_NOTE: Final[str] = "RELEASE_NOTE"
REFERENCE: Final[str] = "REFERENCE"
INCIDENT: Final[str] = "INCIDENT"
ARCHITECTURE: Final[str] = "ARCHITECTURE"
CONFIG: Final[str] = "CONFIG"
ASSET_IMAGE: Final[str] = "ASSET_IMAGE"
UNKNOWN: Final[str] = "UNKNOWN"

# All recognized canonical types
CANONICAL_TYPES: Final[set[str]] = {
    TROUBLESHOOT,
    SOP,
    USER_GUIDE,
    TRAINING,
    RELEASE_NOTE,
    REFERENCE,
    INCIDENT,
    ARCHITECTURE,
    CONFIG,
    ASSET_IMAGE,
    UNKNOWN,
}

# Alias mappings: variant -> canonical
# This handles plural/singular variations, spacing, and common synonyms
ALIASES: Final[dict[str, str]] = {
    # Release note variants (most common mismatch source)
    "RELEASE_NOTES": RELEASE_NOTE,
    "RELEASE": RELEASE_NOTE,
    "RELEASENOTE": RELEASE_NOTE,
    "RELEASENOTES": RELEASE_NOTE,
    "RELEASE_NOTE": RELEASE_NOTE,  # Identity mapping (already canonical)
    "CHANGELOG": RELEASE_NOTE,
    "CHANGELOGS": RELEASE_NOTE,
    
    # SOP variants
    "SOP": SOP,  # Identity
    "SOPS": SOP,
    "STANDARD_OPERATING_PROCEDURE": SOP,
    "STANDARD_OPERATING_PROCEDURES": SOP,
    "PROCEDURE": SOP,
    "PROCEDURES": SOP,
    "RUNBOOK": SOP,
    "RUNBOOKS": SOP,
    
    # User guide variants
    "USER_GUIDE": USER_GUIDE,  # Identity
    "USERGUIDE": USER_GUIDE,
    "USER_GUIDES": USER_GUIDE,
    "USERGUIDES": USER_GUIDE,
    "GUIDE": USER_GUIDE,
    "GUIDES": USER_GUIDE,
    "DOCUMENTATION": USER_GUIDE,
    
    # Troubleshoot variants
    "TROUBLESHOOT": TROUBLESHOOT,  # Identity
    "TROUBLESHOOTING": TROUBLESHOOT,
    "TROUBLESHOOTS": TROUBLESHOOT,
    "TROUBLESHOOTINGS": TROUBLESHOOT,
    "TROUBLESHOOTING_GUIDE": TROUBLESHOOT,
    
    # Training variants
    "TRAINING": TRAINING,  # Identity
    "TRAININGS": TRAINING,
    "TRAINING_MATERIAL": TRAINING,
    "TRAINING_MATERIALS": TRAINING,
    "COURSE": TRAINING,
    "COURSES": TRAINING,
    
    # Reference variants
    "REFERENCE": REFERENCE,  # Identity
    "REFERENCES": REFERENCE,
    "REFERENCE_CATALOG": REFERENCE,
    "REFERENCE_CATALOGS": REFERENCE,
    "CATALOG": REFERENCE,
    "CATALOGS": REFERENCE,
    
    # Incident variants
    "INCIDENT": INCIDENT,  # Identity
    "INCIDENTS": INCIDENT,
    "INCIDENT_REPORT": INCIDENT,
    "INCIDENT_REPORTS": INCIDENT,
    
    # Architecture variants
    "ARCHITECTURE": ARCHITECTURE,  # Identity
    "ARCHITECTURES": ARCHITECTURE,
    "ARCHITECTURE_DOC": ARCHITECTURE,
    "ARCHITECTURE_DOCS": ARCHITECTURE,
    "DESIGN": ARCHITECTURE,
    "DESIGNS": ARCHITECTURE,
    
    # Config variants
    "CONFIG": CONFIG,  # Identity
    "CONFIGS": CONFIG,
    "CONFIGURATION": CONFIG,
    "CONFIGURATIONS": CONFIG,
    "CONFIG_FILE": CONFIG,
    "CONFIG_FILES": CONFIG,
    
    # Asset variants
    "ASSET_IMAGE": ASSET_IMAGE,  # Identity
    "ASSET": ASSET_IMAGE,
    "IMAGE": ASSET_IMAGE,
    "PNG": ASSET_IMAGE,
    "SCREENSHOT": ASSET_IMAGE,
    
    # Unknown variants
    "UNKNOWN": UNKNOWN,  # Identity
    "UNCLASSIFIED": UNKNOWN,
    "OTHER": UNKNOWN,
}


def normalize_doc_type(value: str | None) -> str:
    """
    Normalize a document type string to its canonical form.
    
    Normalization steps:
    1. Convert to uppercase
    2. Strip whitespace
    3. Replace hyphens/spaces with underscores
    4. Apply alias mapping
    5. Return UNKNOWN if not recognized
    
    Args:
        value: Raw document type string (can be None)
    
    Returns:
        Canonical document type string (always uppercase, underscore-separated)
    
    Examples:
        >>> normalize_doc_type("release notes")
        'RELEASE_NOTE'
        >>> normalize_doc_type("Release-Note")
        'RELEASE_NOTE'
        >>> normalize_doc_type("sop")
        'SOP'
        >>> normalize_doc_type("troubleshooting")
        'TROUBLESHOOT'
        >>> normalize_doc_type("unknown_type_x")
        'UNKNOWN'
        >>> normalize_doc_type(None)
        'UNKNOWN'
    """
    if not value:
        return UNKNOWN
    
    # Step 1-3: Normalize formatting
    normalized = value.upper().strip()
    normalized = normalized.replace("-", "_").replace(" ", "_")
    
    # Step 4: Apply alias mapping
    if normalized in ALIASES:
        return ALIASES[normalized]
    
    # Step 5: Check if already canonical
    if normalized in CANONICAL_TYPES:
        return normalized
    
    # Unrecognized type
    return UNKNOWN


def is_canonical(value: str) -> bool:
    """
    Check if a document type string is already in canonical form.
    
    Args:
        value: Document type string to check
    
    Returns:
        True if value is a canonical type, False otherwise
    """
    return value in CANONICAL_TYPES
