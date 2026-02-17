from pathlib import Path

import pytest

from backend.common.models import TextChunk
from backend.retrieval.evidence_matcher import (
    EvidenceMatcher,
    ProvenanceError,
    enforce_provenance_contract,
)


def _chunks() -> list[TextChunk]:
    return [
        TextChunk(
            chunk_id="chunk_1",
            doc_id="doc_1",
            content="A Certificateholder is any Person in whose name a Certificate is registered.",
            source_path="Pooling_Agreement.pdf",
            chunk_index=0,
            doc_type="LEGAL",
        ),
        TextChunk(
            chunk_id="chunk_2",
            doc_id="doc_1",
            content="Error code AUTH401 indicates authentication failure.",
            source_path="Troubleshoot_ToolX_AUTH401.md",
            chunk_index=1,
            doc_type="TROUBLESHOOT",
        ),
    ]


def test_evidence_matcher_exact_rule_hits_with_score_1():
    matcher = EvidenceMatcher()
    answer = "A Certificateholder is any Person in whose name a Certificate is registered."
    ledger = matcher.match_claims_to_chunks(answer, _chunks(), query="What is Certificateholder?")

    assert ledger.coverage == 1.0
    assert len(ledger.evidence_matches) == 1
    assert ledger.evidence_matches[0].match_method == "exact"
    assert ledger.evidence_matches[0].match_score == 1.0


def test_evidence_matcher_casefolded_rule_matches_case_change():
    matcher = EvidenceMatcher()
    answer = "a certificateholder is any person in whose name a certificate is registered."
    ledger = matcher.match_claims_to_chunks(answer, _chunks(), query="define certificateholder")

    assert ledger.coverage == 1.0
    assert ledger.evidence_matches[0].match_method in {"casefolded", "token_boundary"}


def test_production_contract_passes_at_or_above_threshold():
    matcher = EvidenceMatcher()
    answer = "A Certificateholder is any Person in whose name a Certificate is registered."
    ledger = matcher.match_claims_to_chunks(answer, _chunks(), query="define certificateholder")
    result = enforce_provenance_contract(ledger, strict_mode=False, production_threshold=0.95)
    assert result.passed is True


def test_strict_contract_raises_on_uncited_claims():
    matcher = EvidenceMatcher()
    answer = "A Certificateholder is any Person in whose name a Certificate is registered. This sentence is unsupported."
    ledger = matcher.match_claims_to_chunks(answer, _chunks(), query="define certificateholder")

    with pytest.raises(ProvenanceError) as exc_info:
        enforce_provenance_contract(ledger, strict_mode=True)

    payload = exc_info.value.to_error_payload()
    assert payload["error"]["code"] == "E_INCOMPLETE_PROVENANCE"


def test_provenance_ledger_append_writes_jsonl(tmp_path: Path):
    matcher = EvidenceMatcher()
    answer = "Error code AUTH401 indicates authentication failure."
    ledger = matcher.match_claims_to_chunks(answer, _chunks(), query="What is AUTH401?")

    ledger_path = tmp_path / "provenance_ledger.jsonl"
    matcher.append_ledger(ledger_path, ledger)

    lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert "AUTH401" in lines[0]
