"""
Financial & Legal Domain Specialization for Hybrid Retrieval.

This module provides domain-specific constants, term boosts, and query
enrichment for financial (ABS/MBS/structured finance) and legal (PSA,
indenture, trust deed) documents.

All retrieval in this system is scoped exclusively to financial and legal
documents.  Generic or unrelated document types are down-weighted or
excluded at the retrieval layer.
"""

from __future__ import annotations

import re
from typing import Dict, FrozenSet, List, Optional, Tuple

# ── Domain-Specific Stopwords ──────────────────────────────────────────
# These common legal/financial filler words add noise to BM25 scoring and
# should be removed from query and document tokens before indexing.

FINANCIAL_LEGAL_STOPWORDS: FrozenSet[str] = frozenset({
    # Standard English stopwords
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "this", "that", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "will", "would", "shall", "should", "may", "might", "can",
    "could", "not", "no", "so", "if", "as", "its", "such",
    # Legal boilerplate filler
    "herein", "hereof", "hereto", "hereby", "hereinafter", "hereinbefore",
    "hereunder", "therefor", "thereof", "thereto", "therein", "whereby",
    "whereof", "whereas", "thereafter", "thereunder", "aforesaid",
    "aforementioned", "notwithstanding", "pursuant", "provided", "however",
    "further", "following", "set", "forth", "accordance", "relation",
    "respect", "connection", "paragraph", "section", "subsection",
    "clause", "subclause", "article", "exhibit", "schedule", "annex",
    # Financial boilerplate
    "per", "pro", "rata", "basis", "aggregate", "amount", "amounts",
    "total", "net", "gross", "certain", "any", "all", "each", "every",
    "other", "such", "than", "then", "when", "upon", "under", "over",
    "below", "above", "within", "without", "between", "among", "after",
    "before", "during", "through", "until", "unless", "including",
    "subject", "whether", "whichever", "whoever", "whatever",
})

# ── High-Value Financial/Legal Terms (BM25 boost multipliers) ──────────
# Terms that, when matched, should receive a score boost because they are
# highly discriminative in financial/legal document retrieval.

FINANCIAL_TERM_BOOSTS: Dict[str, float] = {
    # ABS/MBS structural terms
    "waterfall": 2.5,
    "priority": 2.0,
    "subordination": 2.5,
    "overcollateralization": 2.5,
    "credit_enhancement": 2.5,
    "reserve_fund": 2.2,
    "trigger": 2.2,
    "performance_trigger": 2.5,
    "sequential_pay": 2.2,
    "pro_rata": 2.0,
    "tranche": 2.0,
    "class_a": 1.8,
    "class_b": 1.8,
    "class_m": 1.8,
    "class_c": 1.8,
    "senior": 1.7,
    "subordinate": 1.7,
    "residual": 1.7,
    "pari_passu": 2.2,
    "turbo": 2.0,
    "step_down": 2.0,
    "step_up": 2.0,
    # PSA / Pooling & Servicing Agreement terms
    "psa": 2.0,
    "pooling": 2.0,
    "servicing_agreement": 2.2,
    "master_servicer": 2.0,
    "servicer": 1.8,
    "trustee": 1.8,
    "depositor": 1.8,
    "sponsor": 1.7,
    "seller": 1.5,
    "issuer": 1.8,
    "certificate": 1.7,
    "certificateholder": 2.0,
    "distribution": 1.7,
    "distribution_date": 2.0,
    "payment_date": 2.0,
    "record_date": 2.0,
    "determination_date": 2.0,
    "closing_date": 2.0,
    "cut-off_date": 2.2,
    "remittance": 2.0,
    # Cashflow/financial mechanics
    "interest": 1.5,
    "principal": 1.7,
    "interest_shortfall": 2.2,
    "principal_shortfall": 2.2,
    "carryover": 2.2,
    "realized_loss": 2.5,
    "writedown": 2.3,
    "allocation": 1.8,
    "available_funds": 2.0,
    "net_monthly_excess": 2.3,
    "excess_cashflow": 2.2,
    "prepayment": 1.8,
    "prepayment_penalty": 2.0,
    "prepayment_speed": 2.0,
    "cpr": 2.0,
    "psa_speed": 2.2,
    "collateral": 1.8,
    "mortgage": 1.7,
    "loan": 1.5,
    "pool": 1.7,
    "balance": 1.5,
    # Legal enforcement terms
    "default": 2.0,
    "event_of_default": 2.5,
    "acceleration": 2.2,
    "enforcement": 2.0,
    "indemnification": 2.0,
    "indemnity": 2.0,
    "representations": 1.8,
    "warranties": 1.8,
    "covenants": 1.8,
    "conditions_precedent": 2.3,
    "remedy": 1.8,
    "remedies": 1.8,
    "cure": 1.7,
    "notice": 1.5,
    # Defined term indicators
    "means": 1.3,
    "defined": 1.3,
    "definition": 1.5,
}

# ── Regime Allowlist ───────────────────────────────────────────────────
# Only these document regime types are valid for financial/legal retrieval.
# Others will be deprioritized in hybrid scoring.

ALLOWED_DOC_REGIMES: FrozenSet[str] = frozenset({
    "GOVERNING_DOC",
    "GOVERNING_DOC_LEGAL",
    "LEGAL",
    "FINANCIAL",
    "ABS",
    "PSA",
    "INDENTURE",
    "TRUST_AGREEMENT",
    "PROSPECTUS",
    "PROSPECTUS_SUPPLEMENT",
    "PROSUPP",
    "OFFERING_MEMORANDUM",
    "CREDIT_AGREEMENT",
    "LOAN_AGREEMENT",
    "REGULATORY",
    "COMPLIANCE",
    "RISK",
    "AUDIT",
    "UNKNOWN",  # allow unknowns through; classifier may not have fired
})

# Down-weight (not excluded) doc types that are clearly off-domain
OFF_DOMAIN_PENALTY: float = 0.4
OFF_DOMAIN_REGIMES: FrozenSet[str] = frozenset({
    "TROUBLESHOOT",
    "SOP",
    "USER_GUIDE",
    "TRAINING",
    "RELEASE_NOTE",
    "GENERIC_GUIDE",
    "TECHNICAL",
})

# ── Query Intent Detection ─────────────────────────────────────────────

# Financial/legal intent patterns mapped to priority retrieval signals
_FINANCIAL_INTENT_PATTERNS: List[Tuple[str, str, List[str]]] = [
    # (intent_name, regex_pattern, priority_doc_types)
    # Waterfall / payment priority
    (
        "payment_waterfall",
        r"\b(waterfall|payment\s+order|payment\s+priority|priority\s+of\s+payment|"
        r"distribution\s+waterfall|sequential|pro.?rata)\b",
        ["GOVERNING_DOC", "PSA"],
    ),
    # Cashflow mechanics
    (
        "cashflow_mechanics",
        r"\b(available\s+funds?|net\s+monthly|excess\s+cashflow|interest\s+shortfall|"
        r"principal\s+shortfall|carryover|realized\s+loss|write.?down|allocation|"
        r"remittance|distribution\s+amount)\b",
        ["GOVERNING_DOC", "PSA"],
    ),
    # Deal triggers / performance tests
    (
        "deal_triggers",
        r"\b(trigger|performance\s+test|overcollateralization|o[/\\]c\s+ratio|"
        r"delinquency|credit\s+enhancement|reserve|turbo|step.?down|step.?up)\b",
        ["GOVERNING_DOC", "PSA"],
    ),
    # Defined terms
    (
        "defined_terms",
        r"\b(define[sd]?\s+term|what\s+(is|does|means?)|meaning\s+of|"
        r"definition\s+of|"
        r'"[A-Z][A-Za-z\s]+")\b',
        ["GOVERNING_DOC", "PSA", "INDENTURE"],
    ),
    # Parties / roles
    (
        "deal_parties",
        r"\b(trustee|master\s+servicer|servicer|depositor|sponsor|seller|issuer|"
        r"certificate\s*(holder)?|investor|obligor|guarantor|rating\s+agency)\b",
        ["GOVERNING_DOC", "PSA", "PROSPECTUS"],
    ),
    # Key dates
    (
        "deal_dates",
        r"\b(closing\s+date|cut.?off\s+date|distribution\s+date|payment\s+date|"
        r"record\s+date|determination\s+date|transfer\s+date|accrual\s+period)\b",
        ["GOVERNING_DOC", "PSA"],
    ),
    # Representations & warranties
    (
        "reps_warranties",
        r"\b(representations?|warranties?|covenants?|conditions\s+precedent|"
        r"eligibility\s+criteria|representations\s+and\s+warranties)\b",
        ["GOVERNING_DOC", "PSA", "INDENTURE"],
    ),
    # Defaults / enforcement
    (
        "default_enforcement",
        r"\b(event\s+of\s+default|acceleration|enforcement|remedy|remedies|"
        r"cure\s+period|notice\s+of\s+default|insolvency|bankruptcy)\b",
        ["GOVERNING_DOC", "PSA", "INDENTURE"],
    ),
    # Reporting
    (
        "investor_reporting",
        r"\b(investor\s+report|distribution\s+report|remittance\s+report|"
        r"monthly\s+statement|certificate\s+payment|trustee\s+report)\b",
        ["GOVERNING_DOC", "PSA", "PROSPECTUS"],
    ),
    # Collateral / pool characteristics
    (
        "pool_collateral",
        r"\b(collateral|mortgage\s+loan|pool|cut.?off\s+pool|balance|wac|wam|"
        r"prepayment|cpr|psa.?speed|ltv|loan.?to.?value)\b",
        ["PROSPECTUS", "PROSUPP", "GOVERNING_DOC"],
    ),
]

_INTENT_RE_COMPILED: List[Tuple[str, re.Pattern, List[str]]] = [
    (name, re.compile(pat, re.IGNORECASE), doc_types)
    for name, pat, doc_types in _FINANCIAL_INTENT_PATTERNS
]


def detect_financial_intent(query: str) -> Tuple[str, List[str]]:
    """Detect financial/legal query intent and return priority doc types.

    Returns:
        (intent_name, priority_doc_types)
        Falls back to ("general_financial", ["GOVERNING_DOC"]) if no match.
    """
    for intent_name, pattern, doc_types in _INTENT_RE_COMPILED:
        if pattern.search(query):
            return intent_name, doc_types
    return "general_financial", ["GOVERNING_DOC"]


# ── Domain Synonym Expansion ────────────────────────────────────────────
# Expand financial/legal abbreviations and synonyms before BM25 search.

FINANCIAL_SYNONYMS: Dict[str, List[str]] = {
    "psa": ["pooling and servicing agreement", "pooling & servicing agreement"],
    "oc": ["overcollateralization", "over-collateralization", "o/c ratio"],
    "cpr": ["conditional prepayment rate", "prepayment speed"],
    "wac": ["weighted average coupon", "weighted average interest rate"],
    "wam": ["weighted average maturity", "weighted average remaining term"],
    "ltv": ["loan to value", "loan-to-value ratio"],
    "remic": ["real estate mortgage investment conduit"],
    "rmbs": ["residential mortgage backed securities", "residential mbs"],
    "cmbs": ["commercial mortgage backed securities", "commercial mbs"],
    "clo": ["collateralized loan obligation"],
    "cdo": ["collateralized debt obligation"],
    "abs": ["asset backed securities", "asset-backed securities"],
    "ce": ["credit enhancement"],
    "rf": ["reserve fund", "cash reserve fund"],
    "oc trigger": ["overcollateralization trigger", "oc test"],
    "step down": ["step-down date", "shifting interest step-down"],
    "pro rata": ["pro-rata", "proportional allocation", "pari passu"],
    "sequential": ["sequential pay", "senior sequential"],
    "turbo": ["turbo payment", "turbo structure"],
    "servicer advance": ["servicer advancing", "P&I advance"],
    "msr": ["mortgage servicing rights"],
    "net loss": ["realized net loss", "net realized loss"],
    "senior": ["class a", "senior tranche", "senior notes"],
    "sub": ["subordinate", "subordinated", "junior tranche"],
}


def expand_financial_query(query: str) -> str:
    """Expand abbreviations and add domain synonyms to query text.

    Modifies the query in-place style: appends synonym terms.
    """
    expanded_terms: List[str] = []
    query_lower = query.lower()

    for abbrev, synonyms in FINANCIAL_SYNONYMS.items():
        # Only expand if the abbreviation is present as a whole word
        if re.search(rf'\b{re.escape(abbrev)}\b', query_lower):
            expanded_terms.extend(synonyms[:1])  # add first synonym only

    if expanded_terms:
        return query + " " + " ".join(expanded_terms)
    return query


# ── Section-Aware Metadata Boosts ──────────────────────────────────────
# Sections of a legal/financial document that are most likely to contain
# authoritative definitions of payment mechanics.

HIGH_VALUE_SECTIONS: FrozenSet[str] = frozenset({
    # PSA waterfall sections
    "distribution", "priority of distributions", "payment waterfall",
    "section 4", "section 5", "section 6", "article iv", "article v",
    "available funds", "net monthly excess", "allocation of losses",
    # Definition sections
    "definitions", "article i", "section 1", "defined terms",
    # Key parties
    "parties", "the trustee", "the servicer", "the depositor",
    # Triggers and tests
    "credit enhancement", "overcollateralization", "triggers",
    "performance tests", "step-down conditions",
    # Events of default
    "events of default", "remedies", "enforcement",
})


def score_section_boost(section_heading: Optional[str]) -> float:
    """Return a multiplicative boost (1.0 = no boost) based on section heading.

    High-value sections for financial/legal retrieval receive up to 1.5x boost.
    """
    if not section_heading:
        return 1.0
    heading_lower = section_heading.lower().strip()
    for high_val in HIGH_VALUE_SECTIONS:
        if high_val in heading_lower:
            return 1.4
    return 1.0


def get_doc_regime_weight(doc_regime: Optional[str]) -> float:
    """Return a score multiplier based on the document regime.

    Financial/legal documents get 1.0 (no penalty).
    Off-domain documents get OFF_DOMAIN_PENALTY (0.4).
    Unknown/unclassified documents pass through at 0.9.
    """
    if not doc_regime:
        return 0.9
    regime_upper = doc_regime.upper()
    if regime_upper in ALLOWED_DOC_REGIMES:
        return 1.0
    if regime_upper in OFF_DOMAIN_REGIMES:
        return OFF_DOMAIN_PENALTY
    return 0.85  # unrecognized regime — mild penalty
