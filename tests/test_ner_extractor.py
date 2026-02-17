"""Unit tests for backend.ingestion.ner_extractor — spaCy NER + noun-chunk keyphrases.

Tests both the *with-model* path (if spaCy + en_core_web_sm are available)
and the *graceful-degradation* path (model absent → returns empty NERResult).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Reset global singleton between tests
import backend.ingestion.ner_extractor as ner_mod
from backend.ingestion.ner_extractor import (
    ExtractedEntity,
    ExtractedKeyphrase,
    NERResult,
    _dedupe_entities,
    _rank_noun_chunks,
    extract_entities_and_keyphrases,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the lazy-loaded spaCy model between tests."""
    ner_mod._nlp = None
    yield
    ner_mod._nlp = None


# ---------------------------------------------------------------------------
# Pure helper tests (no spaCy required)
# ---------------------------------------------------------------------------

class TestDedupeEntities:
    def test_empty(self):
        assert _dedupe_entities([]) == []

    def test_keeps_unique(self):
        entities = [
            ExtractedEntity(text="LaSalle Bank", label="ORG"),
            ExtractedEntity(text="EMC Mortgage", label="ORG"),
        ]
        result = _dedupe_entities(entities)
        assert len(result) == 2

    def test_removes_case_duplicates(self):
        entities = [
            ExtractedEntity(text="LaSalle Bank", label="ORG"),
            ExtractedEntity(text="lasalle bank", label="ORG"),
            ExtractedEntity(text="LASALLE BANK", label="ORG"),
        ]
        result = _dedupe_entities(entities)
        assert len(result) == 1

    def test_same_text_different_label_kept(self):
        entities = [
            ExtractedEntity(text="2006", label="DATE"),
            ExtractedEntity(text="2006", label="CARDINAL"),
        ]
        result = _dedupe_entities(entities)
        assert len(result) == 2


class TestRankNounChunks:
    def test_empty(self):
        assert _rank_noun_chunks([]) == []

    def test_frequency_ranking(self):
        chunks = ["mortgage loans", "trust fund", "mortgage loans", "mortgage loans"]
        result = _rank_noun_chunks(chunks)
        assert len(result) == 2
        assert result[0].text == "mortgage loans"
        assert result[0].count == 3
        assert result[0].score == 1.0

    def test_max_keyphrases_limit(self):
        chunks = [f"term {i}" for i in range(100)]
        result = _rank_noun_chunks(chunks, max_keyphrases=5)
        assert len(result) == 5

    def test_score_normalisation(self):
        chunks = ["term a", "term a", "term b"]
        result = _rank_noun_chunks(chunks, max_keyphrases=10)
        # "term a" appears 2x (score=1.0), "term b" 1x (score=0.5)
        scores = {r.text: r.score for r in result}
        assert scores["term a"] == 1.0
        assert scores["term b"] == 0.5


# ---------------------------------------------------------------------------
# Graceful degradation when model is absent
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    def test_no_env_var_returns_empty(self):
        """When KTS_SPACY_MODEL_PATH is not set, returns empty NERResult."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("KTS_SPACY_MODEL_PATH", None)
            result = extract_entities_and_keyphrases("Some document text here.")
            assert isinstance(result, NERResult)
            assert result.entities == []
            assert result.keyphrases == []

    def test_invalid_path_returns_empty(self):
        """When model path is invalid, returns empty NERResult."""
        result = extract_entities_and_keyphrases(
            "Some document text here.",
            model_path="/nonexistent/path/to/model",
        )
        assert isinstance(result, NERResult)
        assert result.entities == []
        assert result.keyphrases == []

    def test_empty_text_returns_empty(self):
        """Empty text should not crash — returns empty NERResult."""
        result = extract_entities_and_keyphrases("")
        assert isinstance(result, NERResult)
        assert result.entities == []
        assert result.keyphrases == []


# ---------------------------------------------------------------------------
# With spaCy model (skipped if en_core_web_sm not installed)
# ---------------------------------------------------------------------------

_HAS_SPACY = False
try:
    import spacy
    spacy.load("en_core_web_sm")
    _HAS_SPACY = True
except Exception:
    pass


PSA_EXCERPT = """
POOLING AND SERVICING AGREEMENT
dated as of February 1, 2006

among

BEAR STEARNS ASSET BACKED SECURITIES I LLC
as Depositor,

EMC MORTGAGE CORPORATION
as Master Servicer and Sponsor,

and

LASALLE BANK NATIONAL ASSOCIATION
as Trustee

Section 1.01. Definitions.
"Certificateholder" means any Person in whose name a Certificate is
registered in the Certificate Register.
"Distribution Account" means the account established and maintained
pursuant to Section 3.05 hereof.
"Protected Account" means the Collection Account and the Distribution Account.
The Trustee shall distribute on each Distribution Date from amounts
on deposit in the Distribution Account the following amounts in the
following order of priority: first, to the Class A Certificateholders,
the Class A Interest Distribution Amount; second, to the Class M
Certificateholders, the applicable Class M Interest Distribution Amount;
third, principal amounts as calculated per Schedule III.
"""


@pytest.mark.skipif(not _HAS_SPACY, reason="spaCy en_core_web_sm not installed")
class TestWithSpacyModel:
    def test_extracts_entities(self):
        result = extract_entities_and_keyphrases(PSA_EXCERPT, model_path="en_core_web_sm")
        assert isinstance(result, NERResult)
        assert len(result.entities) > 0
        entity_texts = [e.text.lower() for e in result.entities]
        # Should find at least some of these organisations / dates
        found_org = any("emc" in t or "lasalle" in t or "bear stearns" in t for t in entity_texts)
        found_date = any(e.label == "DATE" for e in result.entities)
        assert found_org, f"Expected ORG entities, got: {entity_texts}"
        assert found_date, f"Expected DATE entity, got labels: {[e.label for e in result.entities]}"

    def test_extracts_keyphrases(self):
        result = extract_entities_and_keyphrases(PSA_EXCERPT, model_path="en_core_web_sm")
        assert len(result.keyphrases) > 0
        kp_texts = [kp.text for kp in result.keyphrases]
        # Should extract multi-word legal noun chunks
        assert any(len(k.split()) >= 2 for k in kp_texts), \
            f"Expected multi-word keyphrases, got: {kp_texts}"

    def test_entity_labels_are_useful(self):
        result = extract_entities_and_keyphrases(PSA_EXCERPT, model_path="en_core_web_sm")
        allowed = {"ORG", "PERSON", "GPE", "MONEY", "DATE", "PERCENT",
                    "PRODUCT", "EVENT", "LAW", "NORP", "FAC", "WORK_OF_ART"}
        for ent in result.entities:
            assert ent.label in allowed, f"Unexpected label: {ent.label} for '{ent.text}'"

    def test_max_text_chars_truncation(self):
        result = extract_entities_and_keyphrases(
            PSA_EXCERPT * 100,  # ~100k+ chars
            model_path="en_core_web_sm",
            max_text_chars=500,
        )
        assert isinstance(result, NERResult)
        # Should still work, just on truncated text

    def test_keyphrase_scores_normalised(self):
        result = extract_entities_and_keyphrases(PSA_EXCERPT, model_path="en_core_web_sm")
        for kp in result.keyphrases:
            assert 0.0 <= kp.score <= 1.0, f"Score out of range: {kp.score}"
            assert kp.count >= 1

    def test_entities_have_positions(self):
        result = extract_entities_and_keyphrases(PSA_EXCERPT, model_path="en_core_web_sm")
        for ent in result.entities:
            assert ent.start_char >= 0
            assert ent.end_char > ent.start_char
