"""
Search & Extraction Profiles (SEPs).

Each profile is a bounded extraction task: a focused instruction + a fixed
output field set + keywords used to select relevant source chunks. Keeping each
SEP granular makes it easy to test, govern, and evaluate — and every emitted
item must carry a ``citation`` back to a section/page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class SEPProfile:
    """A single Search & Extraction Profile."""

    name: str
    title: str
    keywords: tuple[str, ...]
    fields: tuple[str, ...]
    instruction: str
    list_key: Optional[str] = None  # if the model wraps items under a key

    def field_list(self) -> str:
        return ", ".join(self.fields)


# ---------------------------------------------------------------------------
# The core SEP catalog
# ---------------------------------------------------------------------------

FEES = SEPProfile(
    name="fees",
    title="Fees",
    keywords=("fee", "servicing", "trustee", "administ", "expense", "compensation"),
    fields=("fee_name", "parties", "frequency", "formula", "citation"),
    instruction=(
        "Extract every fee payable in the deal. For each fee capture who is paid, "
        "the payment frequency, and the exact mathematical formula or rate used to "
        "compute it."
    ),
)

CERTIFICATES = SEPProfile(
    name="certificates",
    title="Certificates & CUSIPs",
    keywords=("certificate", "class", "cusip", "balance", "rate", "senior", "subordinate", "notional"),
    fields=("class_name", "cusip", "seniority", "accrual_formula", "original_balance", "citation"),
    instruction=(
        "Extract every certificate class. Capture its CUSIP, seniority "
        "(senior / subordinate / residual / notional), the interest accrual-rate "
        "formula, and the original (beginning) balance."
    ),
)

ACCOUNTS = SEPProfile(
    name="accounts",
    title="Accounts & Fund Flows",
    keywords=("account", "fund", "deposit", "reserve", "collection", "withdraw"),
    fields=("account_name", "account_type", "inflows", "outflows", "priority", "citation"),
    instruction=(
        "Extract every account in the deal. Capture its type and how funds move "
        "into and out of it, including any priority of movement."
    ),
)

WATERFALL = SEPProfile(
    name="waterfall_rules",
    title="Waterfall Payment Rules",
    keywords=("distribut", "waterfall", "priority", "payment", "allocat", "order"),
    fields=("priority", "section", "verbatim", "interpreted", "citation"),
    instruction=(
        "Extract the priority of payments (waterfall). For each step capture its "
        "priority order, the verbatim rule text, and a plain-English interpretation. "
        "Preserve section/subsection hierarchy."
    ),
)

REPORTING = SEPProfile(
    name="reporting",
    title="Reporting Requirements",
    keywords=("report", "statement", "certificateholder", "distribution date", "notice", "remittance"),
    fields=("report_name", "frequency", "recipients", "data_fields", "citation"),
    instruction=(
        "Extract every reporting / statement-to-certificateholders requirement. "
        "Capture the report name, its frequency, recipients, and the data fields "
        "it must contain."
    ),
)

TERM_FUNCTIONS = SEPProfile(
    name="term_functions",
    title="Term Functions",
    keywords=("means", "calculated", "equal to", "product of", "sum of", "rate"),
    fields=("term", "kind", "formula", "dependencies", "citation"),
    instruction=(
        "For each computed defined term, classify it as a constant or a function. "
        "For functions capture the formula and the terms it depends on so it can be "
        "implemented in Python."
    ),
)

DEAL_PARTIES = SEPProfile(
    name="deal_parties",
    title="Deal Parties",
    keywords=("depositor", "trustee", "servicer", "master servicer", "administrator", "underwriter", "insurer", "issuer"),
    fields=("party_name", "role", "entity_type", "contact_section", "citation"),
    instruction=(
        "Extract every party to the deal. Capture their role (Depositor, Trustee, Servicer, "
        "Master Servicer, Certificate Administrator, Calculation Agent, Paying Agent, "
        "Underwriter, Insurer), legal entity name, and the section that names them."
    ),
)

TRIGGERS = SEPProfile(
    name="triggers",
    title="Trigger Conditions & Tests",
    keywords=("trigger", "test", "threshold", "stepdown", "breach", "overcollateralization", "delinquency", "clean-up"),
    fields=("trigger_name", "trigger_type", "test_formula", "breach_consequence", "cure_condition", "citation"),
    instruction=(
        "Extract every trigger, performance test, or stepdown condition. "
        "Capture the trigger name, type (OC test, delinquency test, clean-up call, stepdown), "
        "the mathematical test formula, what happens on breach, and any cure condition."
    ),
)

AUTO_DISCOVER = SEPProfile(
    name="auto_discover",
    title="Auto-Discovery (Additional SEPs)",
    keywords=("shall", "must", "required", "responsible", "obligation", "duty", "administrator", "agent"),
    fields=("proposed_sep", "duty_category", "responsible_party", "rationale", "citation"),
    instruction=(
        "Read the table of contents and operative sections. Identify any additional structured "
        "extraction categories NOT covered by the standard profiles (Fees, Certificates, Accounts, "
        "Waterfall, Reporting, Term Functions, Deal Parties, Triggers). Focus on duties of the "
        "Certificate Administrator, Calculation Agent, Paying Agent, and Reporting Agent. "
        "Return proposals as a JSON array."
    ),
)

GAP_REVIEW = SEPProfile(
    name="gap_review",
    title="Synthesis & Gap Review",
    keywords=("definition", "fee", "certificate", "account", "waterfall", "trigger", "report"),
    fields=("gap_description", "affected_sep", "severity", "recommendation", "citation"),
    instruction=(
        "You are a structured-finance reviewer. Given the extracted artifacts so far, "
        "identify: (1) important clauses that were not extracted, (2) apparent conflicts between "
        "extracted values, (3) low-confidence items that need SME review. "
        "Return findings as a JSON array."
    ),
)

CORE_PROFILES: tuple[SEPProfile, ...] = (
    FEES,
    CERTIFICATES,
    ACCOUNTS,
    WATERFALL,
    REPORTING,
    TERM_FUNCTIONS,
    DEAL_PARTIES,
    TRIGGERS,
    AUTO_DISCOVER,
    GAP_REVIEW,
)

PROFILES_BY_NAME: dict[str, SEPProfile] = {p.name: p for p in CORE_PROFILES}


def get_profile(name: str) -> SEPProfile:
    if name not in PROFILES_BY_NAME:
        raise KeyError(f"Unknown SEP profile: {name!r}. Known: {list(PROFILES_BY_NAME)}")
    return PROFILES_BY_NAME[name]
