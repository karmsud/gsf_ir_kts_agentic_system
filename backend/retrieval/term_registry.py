"""Term Registry — 3-Tier Learned Synonym System (Option Prod).

Collects noun-chunk keyphrases from each ingested document, clusters
them by embedding similarity (using ChromaDB's built-in all-MiniLM-L6-v2),
and maintains three synonym tiers:

1. ``synonyms.json``            — human-approved, always used (ships in backend/data/)
2. ``synonyms_learned.json``    — auto-generated, confidence ≥ LEARN_THRESHOLD, used at retrieval
3. ``synonyms_candidates.json`` — below threshold, pending human review, NOT used at retrieval

All three files are **regime-aware** — keyed by ``doc_type``.
"""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds (anti-overfitting guardrails)
# ---------------------------------------------------------------------------
LEARN_CONFIDENCE_THRESHOLD = 0.85   # auto-use at retrieval
LEARN_MIN_DOC_COUNT = 3             # must appear in ≥ N docs
SIMILARITY_THRESHOLD = 0.82         # cosine similarity for clustering
MAX_CLUSTER_SIZE = 8                # cap synonyms per term
MIN_TERM_WORDS = 2                  # ignore single-word noun chunks
MAX_TERM_WORDS = 6                  # ignore overly long phrases


# ---------------------------------------------------------------------------
# Pure-Python cosine similarity (no numpy dependency)
# ---------------------------------------------------------------------------

def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors (pure Python)."""
    # Defensive: ensure values are float (may be str after JSON round-trip)
    a = [float(x) for x in a]
    b = [float(x) for x in b]
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Term Registry
# ---------------------------------------------------------------------------

class TermRegistry:
    """Manages the per-KB term registry and synonym generation.

    The registry is stored at ``<kb_path>/term_registry.json`` and
    contains every extracted keyphrase with its doc_type, embedding,
    and the set of document IDs where it appeared.
    """

    def __init__(self, kb_path: str | Path, embed_fn=None):
        """
        Parameters
        ----------
        kb_path : str | Path
            Knowledge base root (typically ``.kts``).
        embed_fn : callable | None
            Embedding function that accepts ``List[str]`` and returns
            ``List[List[float]]``.  If *None*, uses ChromaDB's
            ``DefaultEmbeddingFunction``.
        """
        self.kb_path = Path(kb_path)
        self._registry_path = self.kb_path / "term_registry.json"
        self._learned_path = self.kb_path / "synonyms_learned.json"
        self._candidates_path = self.kb_path / "synonyms_candidates.json"
        self._embed_fn = embed_fn
        self._registry: Dict[str, Dict] = self._load_registry()

    # -- persistence ---------------------------------------------------------

    def _load_registry(self) -> Dict[str, Dict]:
        if self._registry_path.exists():
            try:
                return json.loads(self._registry_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_registry(self) -> None:
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        self._registry_path.write_text(
            json.dumps(self._registry, indent=2, default=str), encoding="utf-8"
        )

    # -- embedding -----------------------------------------------------------

    def _get_embed_fn(self):
        """Lazy-load ChromaDB's default embedding function."""
        if self._embed_fn is None:
            try:
                from chromadb.utils import embedding_functions
                self._embed_fn = embedding_functions.DefaultEmbeddingFunction()
            except Exception:
                logger.warning("Cannot load ChromaDB embedding function for term registry.")
                return None
        return self._embed_fn

    def _embed(self, texts: List[str]) -> Optional[List[List[float]]]:
        fn = self._get_embed_fn()
        if fn is None:
            return None
        try:
            return fn(texts)
        except Exception as exc:
            logger.warning("Embedding failed: %s", exc)
            return None

    # -- registration --------------------------------------------------------

    def register_terms(
        self,
        terms: List[str],
        doc_id: str,
        doc_type: str,
    ) -> int:
        """Register a list of keyphrases from one document.

        Returns the number of **new** terms added.
        """
        added = 0
        now = datetime.now(timezone.utc).isoformat()

        for raw_term in terms:
            term = raw_term.strip().lower()
            word_count = len(term.split())
            if word_count < MIN_TERM_WORDS or word_count > MAX_TERM_WORDS:
                continue

            key = f"{doc_type}::{term}"

            if key not in self._registry:
                self._registry[key] = {
                    "term": term,
                    "doc_type": doc_type,
                    "doc_ids": [doc_id],
                    "first_seen": now,
                    "last_seen": now,
                    "embedding": None,      # computed lazily during clustering
                }
                added += 1
            else:
                entry = self._registry[key]
                if doc_id not in entry["doc_ids"]:
                    entry["doc_ids"].append(doc_id)
                entry["last_seen"] = now

        if added:
            self._save_registry()

        return added

    # -- clustering & synonym generation ------------------------------------

    def rebuild_synonyms(self) -> Dict[str, Any]:
        """Cluster all registered terms by embedding similarity and
        write ``synonyms_learned.json`` and ``synonyms_candidates.json``.

        Returns a summary dict with counts.
        """
        # Group terms by doc_type
        by_regime: Dict[str, List[str]] = defaultdict(list)
        for key, entry in self._registry.items():
            by_regime[entry["doc_type"]].append(key)

        learned: Dict[str, Dict] = {}
        candidates: Dict[str, Dict] = {}
        total_learned = 0
        total_candidates = 0

        for doc_type, keys in by_regime.items():
            if len(keys) < 2:
                continue

            # Compute embeddings for terms that don't have one yet
            terms_needing_embed = [
                k for k in keys if self._registry[k].get("embedding") is None
            ]
            if terms_needing_embed:
                texts = [self._registry[k]["term"] for k in terms_needing_embed]
                embeddings = self._embed(texts)
                if embeddings:
                    for k, emb in zip(terms_needing_embed, embeddings):
                        self._registry[k]["embedding"] = [float(v) for v in emb]

            # Build entries with embeddings
            entries = [
                (k, self._registry[k])
                for k in keys
                if self._registry[k].get("embedding") is not None
            ]
            if len(entries) < 2:
                continue

            # Greedy clustering
            clusters = self._cluster(entries)

            # Classify clusters into learned vs candidates
            regime_learned: Dict[str, Dict] = {}
            regime_candidates: Dict[str, Dict] = {}

            for cluster in clusters:
                if len(cluster) < 2:
                    continue

                # Pick the most-seen term as the canonical term
                cluster.sort(key=lambda x: len(x[1]["doc_ids"]), reverse=True)
                canonical_key, canonical_entry = cluster[0]
                synonyms = [
                    entry["term"] for _, entry in cluster[1 : MAX_CLUSTER_SIZE + 1]
                ]

                if not synonyms:
                    continue

                # Compute confidence = average pairwise similarity in cluster
                confidence = self._cluster_confidence(cluster)
                total_doc_count = sum(
                    len(entry["doc_ids"]) for _, entry in cluster
                )
                avg_doc_count = total_doc_count / len(cluster)

                record = {
                    "synonyms": synonyms,
                    "confidence": round(confidence, 3),
                    "doc_count": int(avg_doc_count),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "status": "auto",
                }

                if (
                    confidence >= LEARN_CONFIDENCE_THRESHOLD
                    and avg_doc_count >= LEARN_MIN_DOC_COUNT
                ):
                    regime_learned[canonical_entry["term"]] = record
                    total_learned += 1
                else:
                    record["status"] = "pending"
                    regime_candidates[canonical_entry["term"]] = record
                    total_candidates += 1

            if regime_learned:
                learned[doc_type] = regime_learned
            if regime_candidates:
                candidates[doc_type] = regime_candidates

        # Persist
        self._save_registry()
        self._write_synonym_file(self._learned_path, learned)
        self._merge_candidates(candidates)

        summary = {
            "learned_clusters": total_learned,
            "candidate_clusters": total_candidates,
            "total_terms": len(self._registry),
        }
        logger.info(
            "Synonym rebuild: %d learned, %d candidates, %d total terms",
            total_learned,
            total_candidates,
            len(self._registry),
        )
        return summary

    def _cluster(
        self, entries: List[Tuple[str, Dict]]
    ) -> List[List[Tuple[str, Dict]]]:
        """Greedy single-linkage clustering by cosine similarity."""
        assigned: Set[int] = set()
        clusters: List[List[Tuple[str, Dict]]] = []

        for i, (ki, ei) in enumerate(entries):
            if i in assigned:
                continue
            cluster = [(ki, ei)]
            assigned.add(i)

            for j, (kj, ej) in enumerate(entries):
                if j in assigned:
                    continue
                sim = _cosine_similarity(ei["embedding"], ej["embedding"])
                if sim >= SIMILARITY_THRESHOLD:
                    cluster.append((kj, ej))
                    assigned.add(j)
                    if len(cluster) >= MAX_CLUSTER_SIZE + 1:
                        break

            clusters.append(cluster)

        return clusters

    def _cluster_confidence(
        self, cluster: List[Tuple[str, Dict]]
    ) -> float:
        """Average pairwise cosine similarity within the cluster."""
        if len(cluster) < 2:
            return 1.0
        total = 0.0
        count = 0
        for i in range(len(cluster)):
            for j in range(i + 1, len(cluster)):
                emb_i = cluster[i][1].get("embedding")
                emb_j = cluster[j][1].get("embedding")
                if emb_i is not None and emb_j is not None:
                    total += _cosine_similarity(emb_i, emb_j)
                    count += 1
        return total / count if count else 0.0

    # -- file I/O ------------------------------------------------------------

    @staticmethod
    def _write_synonym_file(path: Path, data: Dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def _merge_candidates(self, new_candidates: Dict[str, Dict]) -> None:
        """Merge new candidates into existing file, preserving
        previously rejected entries."""
        existing: Dict = {}
        if self._candidates_path.exists():
            try:
                existing = json.loads(
                    self._candidates_path.read_text(encoding="utf-8")
                )
            except Exception:
                existing = {}

        for doc_type, terms in new_candidates.items():
            if doc_type not in existing:
                existing[doc_type] = {}
            for term, record in terms.items():
                # Don't overwrite a rejected entry
                if term in existing[doc_type]:
                    if existing[doc_type][term].get("status") == "rejected":
                        continue
                existing[doc_type][term] = record

        self._write_synonym_file(self._candidates_path, existing)

    # -- approval helpers (called from CLI) ---------------------------------

    def get_pending_candidates(self) -> Dict[str, Dict]:
        """Return all pending candidates grouped by doc_type."""
        if not self._candidates_path.exists():
            return {}
        data = json.loads(self._candidates_path.read_text(encoding="utf-8"))
        result: Dict[str, Dict] = {}
        for doc_type, terms in data.items():
            pending = {
                t: r for t, r in terms.items() if r.get("status") == "pending"
            }
            if pending:
                result[doc_type] = pending
        return result

    def approve_candidate(self, term: str, doc_type: str, target_path: str | Path) -> bool:
        """Move a candidate to the static synonyms file and mark approved."""
        # Update candidates file
        if not self._candidates_path.exists():
            return False
        cand_data = json.loads(self._candidates_path.read_text(encoding="utf-8"))
        regime = cand_data.get(doc_type, {})
        if term not in regime:
            return False

        record = regime[term]
        record["status"] = "approved"
        self._write_synonym_file(self._candidates_path, cand_data)

        # Add to static synonyms
        target = Path(target_path)
        static: Dict = {}
        if target.exists():
            static = json.loads(target.read_text(encoding="utf-8"))

        # Static synonyms are flat (term → [synonyms]) for backward compat;
        # we put the approved synonyms there.
        for syn in record.get("synonyms", []):
            existing = static.get(term, [])
            if syn not in existing:
                existing.append(syn)
            static[term] = existing

        target.write_text(json.dumps(static, indent=2), encoding="utf-8")
        return True

    def reject_candidate(self, term: str, doc_type: str) -> bool:
        """Mark a candidate as rejected (will not be suggested again)."""
        if not self._candidates_path.exists():
            return False
        data = json.loads(self._candidates_path.read_text(encoding="utf-8"))
        regime = data.get(doc_type, {})
        if term not in regime:
            return False
        regime[term]["status"] = "rejected"
        self._write_synonym_file(self._candidates_path, data)
        return True
