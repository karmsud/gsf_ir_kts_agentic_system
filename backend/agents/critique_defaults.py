"""Phase 9.1 — Default critique question library by doc_type.

These static questions are used as fallback when LLM-generated
critique questions are unavailable (generation failed, disabled,
or critique_questions.json missing).
"""

from __future__ import annotations

from backend.common.models import CritiqueQuestion

DEFAULT_QUESTIONS: dict[str, list[CritiqueQuestion]] = {
    "GOVERNING_DOC": [
        CritiqueQuestion(
            id="default_gd_001",
            question="Are all Capitalized Terms used in the answer traced to their defined meanings?",
            trigger_keywords=[],
            trigger_logic="always",
            priority=1,
        ),
        CritiqueQuestion(
            id="default_gd_002",
            question="Are cross-references to other Sections or Articles resolved or flagged?",
            trigger_keywords=["Section", "Article", "pursuant to"],
            trigger_logic="any_in_source",
            priority=2,
        ),
        CritiqueQuestion(
            id="default_gd_003",
            question="Are conflicting or ambiguous provisions both cited rather than only one interpretation presented?",
            trigger_keywords=["notwithstanding", "except", "provided however"],
            trigger_logic="any_in_source",
            priority=2,
        ),
    ],
    "TROUBLESHOOT": [
        CritiqueQuestion(
            id="default_ts_001",
            question="Does the answer preserve all CAUTION and WARNING annotations from the source?",
            trigger_keywords=["CAUTION", "WARNING", "\u26a0"],
            trigger_logic="any_in_source",
            priority=1,
        ),
        CritiqueQuestion(
            id="default_ts_002",
            question="Are troubleshooting steps presented in the same order as the source document?",
            trigger_keywords=[],
            trigger_logic="always",
            priority=2,
        ),
        CritiqueQuestion(
            id="default_ts_003",
            question="Does the answer reference specific page numbers or section references for each solution step?",
            trigger_keywords=[],
            trigger_logic="always",
            priority=3,
        ),
    ],
    "SUPPLEMENT": [
        CritiqueQuestion(
            id="default_su_001",
            question="Does the answer reference the specific supplement date and amendment number?",
            trigger_keywords=["dated", "supplement", "amendment"],
            trigger_logic="any_in_source",
            priority=1,
        ),
        CritiqueQuestion(
            id="default_su_002",
            question="Are modifications to base document terms clearly distinguished from original terms?",
            trigger_keywords=["amended", "modified", "replaced", "deleted"],
            trigger_logic="any_in_source",
            priority=2,
        ),
    ],
    "GENERIC_GUIDE": [
        CritiqueQuestion(
            id="default_gg_001",
            question="Does the answer preserve all NOTE and IMPORTANT callouts from the source?",
            trigger_keywords=["NOTE:", "IMPORTANT:", "TIP:"],
            trigger_logic="any_in_source",
            priority=1,
        ),
        CritiqueQuestion(
            id="default_gg_002",
            question="Are procedural steps presented in the correct order from the source?",
            trigger_keywords=[],
            trigger_logic="always",
            priority=2,
        ),
    ],
}


def get_default_questions(doc_type: str) -> list[CritiqueQuestion]:
    """Return default critique questions for a doc_type.

    Falls back to GENERIC_GUIDE if the doc_type is not in the library.
    """
    return DEFAULT_QUESTIONS.get(doc_type, DEFAULT_QUESTIONS.get("GENERIC_GUIDE", []))
