"""NER & Keyphrase Extractor — spaCy (Option Prod).

Extracts named entities and noun-chunk keyphrases from document text
using a spaCy model provided by the gsf.kts-models-spacy extension.

- Entities  → stored as ENTITY graph nodes
- Keyphrases → stored as KEYPHRASE graph nodes

Gated behind ``config.ner_enabled`` and the ``KTS_SPACY_MODEL_PATH``
environment variable (set by the core extension when the spaCy addon
is registered).
"""

from __future__ import annotations

import logging
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singleton — the spaCy model is expensive to load; do it once.
# ---------------------------------------------------------------------------
_nlp = None


def _load_model(model_path: Optional[str] = None) -> object:
    """Load the spaCy model.  Returns ``None`` if spaCy or the model
    is unavailable (graceful degradation)."""
    global _nlp
    if _nlp is not None:
        return _nlp

    model_path = model_path or os.environ.get("KTS_SPACY_MODEL_PATH")
    if not model_path:
        logger.debug("NER disabled — KTS_SPACY_MODEL_PATH not set.")
        return None

    try:
        import spacy  # noqa: E402  — intentionally lazy

        if Path(model_path).is_dir():
            _nlp = spacy.load(model_path)
        else:
            # Fallback: treat as installed package name
            _nlp = spacy.load(model_path)
        logger.info("spaCy model loaded from %s", model_path)
        return _nlp
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to load spaCy model: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ExtractedEntity:
    """A single named entity extracted by spaCy."""
    text: str
    label: str           # e.g. ORG, MONEY, DATE, PERCENT, PERSON
    start_char: int = 0
    end_char: int = 0


@dataclass
class ExtractedKeyphrase:
    """A noun-chunk keyphrase ranked by frequency."""
    text: str
    score: float         # normalised frequency 0.0–1.0
    count: int = 1


@dataclass
class NERResult:
    """Container for all NER + keyphrase outputs from one document."""
    entities: List[ExtractedEntity] = field(default_factory=list)
    keyphrases: List[ExtractedKeyphrase] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

# Entity labels we care about (skip CARDINAL, ORDINAL, etc.)
_USEFUL_LABELS = {
    "ORG", "PERSON", "GPE", "MONEY", "DATE", "PERCENT",
    "PRODUCT", "EVENT", "LAW", "NORP", "FAC", "WORK_OF_ART",
}

# Stop-phrase filter for noun chunks (too generic to be useful)
_STOPCHUNK_WORDS = {
    "it", "this", "that", "which", "they", "them", "we", "you",
    "he", "she", "i", "me", "the", "a", "an",
}


def _dedupe_entities(entities: List[ExtractedEntity]) -> List[ExtractedEntity]:
    """Keep one entity per (normalised_text, label) pair."""
    seen: set[Tuple[str, str]] = set()
    result = []
    for ent in entities:
        key = (ent.text.lower().strip(), ent.label)
        if key not in seen:
            seen.add(key)
            result.append(ent)
    return result


def _rank_noun_chunks(chunks: List[str], max_keyphrases: int = 30) -> List[ExtractedKeyphrase]:
    """Rank noun chunks by frequency; normalise score 0–1."""
    counter = Counter(c.lower().strip() for c in chunks)
    if not counter:
        return []
    max_count = counter.most_common(1)[0][1]
    ranked = []
    for text, count in counter.most_common(max_keyphrases):
        ranked.append(ExtractedKeyphrase(
            text=text,
            score=round(count / max_count, 3),
            count=count,
        ))
    return ranked


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_entities_and_keyphrases(
    text: str,
    model_path: Optional[str] = None,
    max_text_chars: int = 100_000,
    min_chunk_words: int = 2,
    max_keyphrases: int = 30,
) -> NERResult:
    """Run spaCy NER + noun-chunk keyphrase extraction on *text*.

    Returns ``NERResult`` with empty lists if the model is unavailable
    (graceful degradation — caller should check before storing).

    Parameters
    ----------
    text : str
        Document text to process.
    model_path : str | None
        Override path to spaCy model directory.
    max_text_chars : int
        Truncate text to this length before sending to spaCy (perf guard).
    min_chunk_words : int
        Minimum word count for a noun chunk to qualify as a keyphrase.
    max_keyphrases : int
        Maximum keyphrases to return.
    """
    nlp = _load_model(model_path)
    if nlp is None:
        return NERResult()

    # Truncate very long documents (spaCy can be slow on huge texts)
    if len(text) > max_text_chars:
        text = text[:max_text_chars]

    try:
        doc = nlp(text)
    except Exception as exc:
        logger.warning("spaCy processing failed: %s", exc)
        return NERResult()

    # 1. Named entities
    entities = [
        ExtractedEntity(
            text=ent.text.strip(),
            label=ent.label_,
            start_char=ent.start_char,
            end_char=ent.end_char,
        )
        for ent in doc.ents
        if ent.label_ in _USEFUL_LABELS and len(ent.text.strip()) >= 2
    ]
    entities = _dedupe_entities(entities)

    # 2. Noun-chunk keyphrases
    raw_chunks = []
    for chunk in doc.noun_chunks:
        # Strip leading determiners/pronouns
        tokens = [t for t in chunk if not t.is_stop and not t.is_punct]
        if len(tokens) >= min_chunk_words:
            clean = " ".join(t.text for t in tokens)
            # Skip chunks that are just a pronoun/stop word
            if clean.lower().split()[0] not in _STOPCHUNK_WORDS:
                raw_chunks.append(clean)

    keyphrases = _rank_noun_chunks(raw_chunks, max_keyphrases)

    logger.info("NER extracted %d entities, %d keyphrases", len(entities), len(keyphrases))
    return NERResult(entities=entities, keyphrases=keyphrases)
