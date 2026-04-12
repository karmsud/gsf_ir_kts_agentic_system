"""
Module 2: Preliminary Statement Table Extraction

Parses the linearised Preliminary Statement table to extract per-class metadata
(initial CPB, pass-through rate, rate type, notional flag, CUSIP).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ClassMetadata:
    class_name: str
    initial_cpb: Decimal = Decimal(0)
    is_notional: bool = False
    initial_rate: Decimal = Decimal(0)
    rate_type: str = 'fixed'           # "fixed" | "floating"
    margin: Optional[Decimal] = None   # basis-points for floating
    cusip: Optional[str] = None


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

CLASS_NAME_PATTERN = re.compile(r'Class\s+([A-Z0-9][\w-]*)')
DOLLAR_AMOUNT = re.compile(r'\$([\d,]+(?:\.\d{2})?)')
PERCENTAGE = re.compile(r'(\d+\.\d+)\s*%')
CUSIP_PATTERN = re.compile(r'\b([A-Z0-9]{9})\b')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_preliminary_statement(text: str) -> str:
    """Locate and return the Preliminary Statement section text."""
    start_patterns = [
        r'PRELIMINARY\s+STATEMENT',
        r'Preliminary\s+Statement',
        r'The\s+following\s+table\s+sets\s+forth',
    ]

    for pattern in start_patterns:
        match = re.search(pattern, text)
        if match:
            section_end = re.search(
                r'ARTICLE\s+[IVX]+|(?:SECTION|Section)\s+\d+\.\d+',
                text[match.end():],
            )
            end = match.end() + section_end.start() if section_end else match.end() + 20_000
            return text[match.start():end]

    return ''


def parse_class_table(prelim_text: str) -> Dict[str, ClassMetadata]:
    """
    Parse the linearised Preliminary Statement table into structured class metadata.

    Expects lines like::

        Class I-A-1    $417,353,000    5.250%    Fixed
    """
    classes: Dict[str, ClassMetadata] = {}

    for line in prelim_text.split('\n'):
        class_match = CLASS_NAME_PATTERN.search(line)
        if not class_match:
            continue

        class_name = class_match.group(1)

        # Dollar amount
        dollar_match = DOLLAR_AMOUNT.search(line)
        try:
            initial_cpb = Decimal(dollar_match.group(1).replace(',', '')) if dollar_match else Decimal(0)
        except InvalidOperation:
            initial_cpb = Decimal(0)

        # Percentage (rate)
        pct_match = PERCENTAGE.search(line)
        try:
            initial_rate = Decimal(pct_match.group(1)) / 100 if pct_match else Decimal(0)
        except InvalidOperation:
            initial_rate = Decimal(0)

        # Rate type
        rate_type = 'floating' if re.search(r'(?i)float|LIBOR|SOFR|variable', line) else 'fixed'

        # Notional flag
        is_notional = bool(re.search(r'(?i)notional', line)) or initial_cpb == 0

        # CUSIP
        cusip_match = CUSIP_PATTERN.search(line)
        cusip = cusip_match.group(1) if cusip_match else None

        # Margin (floating only)
        margin: Optional[Decimal] = None
        if rate_type == 'floating':
            margin_match = re.search(r'(\d+\.?\d*)\s*(?:bps|basis\s+points)', line)
            if margin_match:
                try:
                    margin = Decimal(margin_match.group(1))
                except InvalidOperation:
                    margin = None

        classes[class_name] = ClassMetadata(
            class_name=class_name,
            initial_cpb=initial_cpb,
            is_notional=is_notional,
            initial_rate=initial_rate,
            rate_type=rate_type,
            margin=margin,
            cusip=cusip,
        )

    logger.info('Parsed %d certificate classes from Preliminary Statement.', len(classes))
    return classes


def extract_and_parse(text: str) -> Dict[str, ClassMetadata]:
    """Convenience: locate the Preliminary Statement section and parse it."""
    section = extract_preliminary_statement(text)
    if not section:
        logger.warning('Could not locate Preliminary Statement section.')
        return {}
    return parse_class_table(section)
