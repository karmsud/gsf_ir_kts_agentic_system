"""Phase 9.3 — Provenance-filtered multi-doc critique question merging.

When a query retrieves chunks from multiple documents, each document's
critique_questions.json must be consulted.  Pure union generates 70%+
false gaps.  This module implements provenance-filtered union with
trigger-keyword pre-filtering and chunk-count-weighted ordering.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Any

from backend.common.models import CritiqueQuestion, DocCritique

logger = logging.getLogger(__name__)


def merge_critique_questions(
    retrieved_chunks: list[dict],
    critique_stores: dict[str, DocCritique],
) -> list[CritiqueQuestion]:
    """Provenance-filtered union with chunk-count-weighted ordering.

    Algorithm:
    1. Map each chunk to (doc_id, section_id).
    2. Include doc-level questions for all docs with >=1 chunk.
    3. Include section-level questions ONLY for sections with >=1 chunk.
    4. Order: doc-level first, then section-level by chunk count desc.
    5. Within each group, order by priority.

    Returns
    -------
    list[CritiqueQuestion]
        Ordered, provenance-filtered questions ready for the critique loop.
    """
    # Step 1: Build provenance map
    doc_section_map: dict[str, set[str]] = defaultdict(set)
    doc_chunk_counts: Counter = Counter()

    for chunk in retrieved_chunks:
        doc_id = (
            chunk.get("doc_id")
            or chunk.get("metadata", {}).get("doc_id")
        )
        section_id = (
            chunk.get("section_id")
            or chunk.get("metadata", {}).get("section_id", "sec000")
        )
        if doc_id:
            doc_section_map[doc_id].add(section_id)
            doc_chunk_counts[doc_id] += 1

    # Step 2: Collect doc-level questions (always included for retrieved docs)
    doc_level: list[CritiqueQuestion] = []
    seen_texts: set[str] = set()
    for doc_id in doc_section_map:
        if doc_id not in critique_stores:
            continue
        for q in critique_stores[doc_id].doc_level_questions:
            if q.question in seen_texts:
                continue
            seen_texts.add(q.question)
            # Tag with provenance for early-exit logic
            q._source_doc_id = doc_id  # type: ignore[attr-defined]
            q._source_doc_chunk_count = doc_chunk_counts[doc_id]  # type: ignore[attr-defined]
            doc_level.append(q)

    doc_level.sort(key=lambda q: q.priority)

    # Step 3: Collect section-level questions (provenance-filtered)
    section_level: list[CritiqueQuestion] = []

    for doc_id, _count in doc_chunk_counts.most_common():
        if doc_id not in critique_stores:
            continue
        retrieved_sections = doc_section_map[doc_id]
        for section_crit in critique_stores[doc_id].section_questions:
            if section_crit.section_id not in retrieved_sections:
                continue
            for q in section_crit.questions:
                # Deduplicate identical question text
                if q.question in seen_texts:
                    continue
                seen_texts.add(q.question)
                q._source_doc_id = doc_id  # type: ignore[attr-defined]
                q._source_doc_chunk_count = doc_chunk_counts[doc_id]  # type: ignore[attr-defined]
                q._source_section_id = section_crit.section_id  # type: ignore[attr-defined]
                section_level.append(q)

    # Sort section-level: chunk count desc, then priority asc
    section_level.sort(
        key=lambda q: (-getattr(q, "_source_doc_chunk_count", 0), q.priority),
    )

    # Step 4: Combine
    return doc_level + section_level


def should_early_exit(
    current_confidence: float,
    remaining_questions: list[CritiqueQuestion],
    threshold: float = 0.90,
) -> bool:
    """Exit early if confidence is high and remaining questions are from
    low-contribution (tail) documents.

    Tail questions = from docs contributing <= 1 chunk to retrieval.
    """
    if current_confidence < threshold:
        return False
    return all(
        getattr(q, "_source_doc_chunk_count", 0) <= 1
        for q in remaining_questions
    )
