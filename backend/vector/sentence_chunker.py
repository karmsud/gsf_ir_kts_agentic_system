"""Phase 19.2 — Sentence-Level Chunker (Non-Legal Store 2).

Splits document text into fine-grained sentence-level chunks for
maximum retrieval precision.  Each chunk is a single sentence (or
a small group of 2–3 sentences) with a reference back to its
parent context.

This is the most granular of the three non-legal stores.  It trades
context for precision: when a user asks about a specific error code or
step, the sentence that mentions it will rank highest.

The parent expansion mechanism (Phase 8.4) can later expand matched
sentences back to their surrounding context.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from backend.common.models import TextChunk

# ── Sentence detection ────────────────────────────────────────────

# Primary: split on sentence-ending punctuation followed by space + uppercase
_SENTENCE_SPLIT_RE = re.compile(
    r'(?<=[.!?])\s+(?=[A-Z])'
    r'|(?<=\n)\s*(?=[-•]\s+\S)'          # Bullet points
    r'|(?<=\n)\s*(?=\d+[.)]\s+\S)'       # Numbered lists
)

# Fallback: split on double-newlines (paragraph boundaries)
_PARAGRAPH_SPLIT_RE = re.compile(r'\n\s*\n')


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences with fallback strategies."""
    sentences = _SENTENCE_SPLIT_RE.split(text)

    # If very few sentences found, try paragraph split
    if len(sentences) <= 2 and len(text) > 500:
        sentences = _PARAGRAPH_SPLIT_RE.split(text)

    # Filter empty / trivially short
    return [s.strip() for s in sentences if s.strip() and len(s.strip()) >= 10]


def _extract_parent_context(
    sentences: List[str],
    index: int,
    window: int = 3,
) -> str:
    """Get surrounding context for a sentence (parent window)."""
    start = max(0, index - window)
    end = min(len(sentences), index + window + 1)
    return " ".join(sentences[start:end])


def _extract_error_codes(text: str) -> List[str]:
    """Extract error codes from text."""
    patterns = [
        r'\bERR[-_]?[A-Z]*[-_]?\d{3,}\b',
        r'\bHTTP\s*\d{3}\b',
        r'\b[A-Z]{2,}\d{3,4}\b',
        r'\bError\s+(?:Code\s*)?(\d{3,})\b',
        r'\b0x[0-9A-Fa-f]{4,}\b',
    ]
    codes = set()
    for p in patterns:
        for m in re.finditer(p, text, re.IGNORECASE):
            codes.add(m.group().strip())
    return sorted(codes)


def chunk_by_sentences(
    doc_id: str,
    source_path: str,
    text: str,
    target_chunk_size: int = 200,
    overlap_sentences: int = 1,
    max_sentences_per_chunk: int = 3,
    parent_context_window: int = 5,
) -> Tuple[List[TextChunk], List[dict]]:
    """Chunk a document into sentence-level pieces with parent records.

    Parameters
    ----------
    doc_id : str
        Document identifier.
    source_path : str
        Source file path.
    text : str
        Full document text.
    target_chunk_size : int
        Target character size per chunk. Sentences are grouped until
        this target is met.
    overlap_sentences : int
        Number of trailing sentences from previous chunk to include.
    max_sentences_per_chunk : int
        Maximum sentences per chunk (cap regardless of size).
    parent_context_window : int
        Number of surrounding sentences to include in parent record.

    Returns
    -------
    Tuple[List[TextChunk], List[dict]]
        (child_chunks, parent_records) where parent_records have:
        ``{parent_id, text, chunk_ids: [child_ids]}``
    """
    if not text or not text.strip():
        return [], []

    sentences = _split_sentences(text)
    if not sentences:
        return [], []

    # Group sentences into chunks
    child_chunks: List[TextChunk] = []
    parent_records: List[dict] = []
    chunk_index = 0
    i = 0

    while i < len(sentences):
        # Collect sentences for this chunk
        group = []
        group_len = 0
        j = i
        while j < len(sentences) and len(group) < max_sentences_per_chunk:
            sent = sentences[j]
            if group_len + len(sent) > target_chunk_size * 1.5 and group:
                break
            group.append(sent)
            group_len += len(sent)
            j += 1
            if group_len >= target_chunk_size:
                break

        if not group:
            i += 1
            continue

        chunk_text = " ".join(group)
        error_codes = _extract_error_codes(chunk_text)

        # Build evidence header
        header_parts = [f"[EVIDENCE] source={source_path}"]
        if error_codes:
            header_parts.append(f"error_codes={','.join(error_codes)}")
        header_parts.append("granularity=sentence")
        header = " | ".join(header_parts)

        chunk_id = f"{doc_id}_sent_{chunk_index:04d}"
        child_chunks.append(TextChunk(
            chunk_id=chunk_id,
            doc_id=doc_id,
            content=f"{header}\n{chunk_text}",
            source_path=source_path,
            chunk_index=chunk_index,
            doc_type="GENERIC_GUIDE",
        ))

        # Build parent record (wider context around this sentence group)
        parent_context = _extract_parent_context(sentences, i, parent_context_window)
        parent_id = f"{doc_id}_sent_parent_{chunk_index:04d}"
        parent_records.append({
            "parent_id": parent_id,
            "text": parent_context,
            "chunk_ids": [chunk_id],
            "source_path": source_path,
            "doc_id": doc_id,
        })

        chunk_index += 1
        # Advance with overlap – MUST always move forward by at least 1
        next_i = j - overlap_sentences if overlap_sentences > 0 and j > i else j
        i = max(i + 1, next_i)

    return child_chunks, parent_records
