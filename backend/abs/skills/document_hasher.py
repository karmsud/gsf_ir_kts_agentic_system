"""
Document Hasher — SHA-256 content hashing and MinHash/Jaccard
near-duplicate detection for document deduplication and version
tracking across deals.

Three-layer detection:
  1. SHA-256 exact hash — byte-identical duplicates
  2. MinHash signature — fast approximate Jaccard similarity
  3. Content overlap — word-level Jaccard for confirmation

Ported from PayGen pipeline.skills.document_hasher → backend.abs.skills
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class DuplicateCheckResult:
    """Result of duplicate checking."""
    is_duplicate: bool
    content_hash: str
    matching_deal_id: str = ""
    matching_document: str = ""
    similarity_note: str = ""


@dataclass
class HashRecord:
    """Single hash entry in the registry."""
    content_hash: str
    deal_id: str
    document_path: str
    document_type: str
    hashed_at: str = ""
    file_size_bytes: int = 0

    def to_dict(self) -> dict:
        return {
            "content_hash": self.content_hash,
            "deal_id": self.deal_id,
            "document_path": self.document_path,
            "document_type": self.document_type,
            "hashed_at": self.hashed_at,
            "file_size_bytes": self.file_size_bytes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HashRecord":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def compute_content_hash(
    file_path: Path,
    algorithm: str = "sha256",
) -> str:
    """
    Compute content hash of a file.

    Args:
        file_path: Path to file
        algorithm: Hash algorithm (default: sha256)

    Returns:
        Hexadecimal hash string
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Cannot hash: {file_path}")

    hasher = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)

    return hasher.hexdigest()


def compute_text_hash(text: str, algorithm: str = "sha256") -> str:
    """Compute hash of text content directly."""
    hasher = hashlib.new(algorithm)
    hasher.update(text.encode("utf-8"))
    return hasher.hexdigest()


def check_duplicates(
    file_path: Path,
    hash_registry_path: Path,
    deal_id: str = "",
) -> DuplicateCheckResult:
    """
    Check if a document is a duplicate of any previously ingested document.

    Args:
        file_path: Path to document to check
        hash_registry_path: Path to hash registry JSON file
        deal_id: Current deal ID (skip self-matches)

    Returns:
        DuplicateCheckResult with match details
    """
    content_hash = compute_content_hash(file_path)

    registry = _load_registry(hash_registry_path)

    for record in registry:
        if record.content_hash == content_hash:
            # Skip self-matches (same deal, same document)
            if record.deal_id == deal_id and record.document_path == str(file_path):
                continue
            return DuplicateCheckResult(
                is_duplicate=True,
                content_hash=content_hash,
                matching_deal_id=record.deal_id,
                matching_document=record.document_path,
                similarity_note="Exact content match (SHA-256)",
            )

    return DuplicateCheckResult(
        is_duplicate=False,
        content_hash=content_hash,
    )


def check_portfolio_duplicates(
    file_path: Path,
    deal_paths: list[Path],
) -> list[DuplicateCheckResult]:
    """
    Check a document against all deals in the portfolio.

    Args:
        file_path: Path to document to check
        deal_paths: List of all deal directory paths

    Returns:
        List of DuplicateCheckResult (one per matching deal)
    """
    content_hash = compute_content_hash(file_path)
    results: list[DuplicateCheckResult] = []

    for deal_path in deal_paths:
        registry_path = deal_path / "runs" / "hash_registry.json"
        if not registry_path.exists():
            continue

        registry = _load_registry(registry_path)
        for record in registry:
            if record.content_hash == content_hash:
                results.append(DuplicateCheckResult(
                    is_duplicate=True,
                    content_hash=content_hash,
                    matching_deal_id=record.deal_id,
                    matching_document=record.document_path,
                    similarity_note="Exact content match (SHA-256)",
                ))

    return results


def register_hash(
    file_path: Path,
    hash_registry_path: Path,
    deal_id: str,
    document_type: str = "",
) -> HashRecord:
    """
    Register a document's hash in the registry.

    Args:
        file_path: Path to document
        hash_registry_path: Path to hash registry JSON
        deal_id: Deal ID
        document_type: Document type classification

    Returns:
        The created HashRecord
    """
    content_hash = compute_content_hash(file_path)
    file_path = Path(file_path)

    record = HashRecord(
        content_hash=content_hash,
        deal_id=deal_id,
        document_path=str(file_path),
        document_type=document_type,
        hashed_at=datetime.now(timezone.utc).isoformat(),
        file_size_bytes=file_path.stat().st_size,
    )

    registry = _load_registry(hash_registry_path)

    # Avoid duplicate entries in registry
    existing_hashes = {(r.content_hash, r.deal_id, r.document_path) for r in registry}
    if (record.content_hash, record.deal_id, record.document_path) not in existing_hashes:
        registry.append(record)
        _save_registry(registry, hash_registry_path)

    return record


# ── Registry I/O ──────────────────────────────────────────────

def _load_registry(path: Path) -> list[HashRecord]:
    """Load hash registry from JSON."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [HashRecord.from_dict(d) for d in data]
    except (json.JSONDecodeError, KeyError):
        return []


def _save_registry(registry: list[HashRecord], path: Path) -> None:
    """Save hash registry to JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [r.to_dict() for r in registry]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── MinHash Near-Duplicate Detection ─────────────────────────

# Number of hash functions for MinHash signature
_NUM_HASHES = 128
# Large prime for universal hashing
_LARGE_PRIME = (1 << 61) - 1
# Pre-generated hash coefficients (a, b pairs)
_HASH_COEFFICIENTS: list[tuple[int, int]] | None = None


def _get_hash_coefficients() -> list[tuple[int, int]]:
    """Get or generate deterministic hash coefficients."""
    global _HASH_COEFFICIENTS
    if _HASH_COEFFICIENTS is None:
        import random
        rng = random.Random(42)  # deterministic seed
        _HASH_COEFFICIENTS = [
            (rng.randint(1, _LARGE_PRIME - 1), rng.randint(0, _LARGE_PRIME - 1))
            for _ in range(_NUM_HASHES)
        ]
    return _HASH_COEFFICIENTS


def _text_to_shingles(text: str, k: int = 5) -> set[int]:
    """
    Convert text to a set of k-shingle hashes.

    Args:
        text: Input text
        k: Shingle size (number of words)

    Returns:
        Set of 64-bit shingle hashes
    """
    # Normalize: lowercase, strip punctuation, collapse whitespace
    cleaned = re.sub(r'[^\w\s]', ' ', text.lower())
    words = cleaned.split()

    if len(words) < k:
        # For very short texts, use individual words
        return {
            int(hashlib.md5(w.encode()).hexdigest()[:16], 16)
            for w in words
        }

    shingles: set[int] = set()
    for i in range(len(words) - k + 1):
        shingle = " ".join(words[i:i + k])
        h = int(hashlib.md5(shingle.encode()).hexdigest()[:16], 16)
        shingles.add(h)

    return shingles


def compute_minhash_signature(text: str, k: int = 5) -> list[int]:
    """
    Compute MinHash signature for a text document.

    Args:
        text: Document text content
        k: Shingle size (number of words per shingle)

    Returns:
        List of _NUM_HASHES minimum hash values
    """
    shingles = _text_to_shingles(text, k)

    if not shingles:
        return [0] * _NUM_HASHES

    coefficients = _get_hash_coefficients()
    signature: list[int] = []

    for a, b in coefficients:
        min_hash = float('inf')
        for shingle in shingles:
            h = (a * shingle + b) % _LARGE_PRIME
            if h < min_hash:
                min_hash = h
        signature.append(int(min_hash))

    return signature


def estimate_jaccard_from_signatures(
    sig_a: list[int],
    sig_b: list[int],
) -> float:
    """
    Estimate Jaccard similarity from two MinHash signatures.

    Args:
        sig_a: MinHash signature of document A
        sig_b: MinHash signature of document B

    Returns:
        Estimated Jaccard similarity (0.0 to 1.0)
    """
    if not sig_a or not sig_b:
        return 0.0
    if len(sig_a) != len(sig_b):
        min_len = min(len(sig_a), len(sig_b))
        sig_a = sig_a[:min_len]
        sig_b = sig_b[:min_len]

    matches = sum(1 for a, b in zip(sig_a, sig_b) if a == b)
    return matches / len(sig_a)


def compute_word_jaccard(text_a: str, text_b: str) -> float:
    """
    Compute exact word-level Jaccard similarity between two texts.

    Used as a confirmation step after MinHash flags a near-duplicate.
    """
    words_a = set(re.sub(r'[^\w\s]', ' ', text_a.lower()).split())
    words_b = set(re.sub(r'[^\w\s]', ' ', text_b.lower()).split())

    if not words_a and not words_b:
        return 1.0
    if not words_a or not words_b:
        return 0.0

    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


@dataclass
class MinHashRecord:
    """MinHash signature entry in the registry."""
    content_hash: str
    deal_id: str
    document_path: str
    signature: list[int] = field(default_factory=list)
    shingle_count: int = 0

    def to_dict(self) -> dict:
        return {
            "content_hash": self.content_hash,
            "deal_id": self.deal_id,
            "document_path": self.document_path,
            "signature": self.signature,
            "shingle_count": self.shingle_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> MinHashRecord:
        return cls(
            content_hash=d.get("content_hash", ""),
            deal_id=d.get("deal_id", ""),
            document_path=d.get("document_path", ""),
            signature=d.get("signature", []),
            shingle_count=d.get("shingle_count", 0),
        )


def register_minhash(
    file_path: Path,
    minhash_registry_path: Path,
    deal_id: str,
    k: int = 5,
) -> MinHashRecord:
    """
    Compute and register a MinHash signature for a document.

    Args:
        file_path: Path to text document
        minhash_registry_path: Path to MinHash registry JSON
        deal_id: Deal identifier
        k: Shingle size

    Returns:
        MinHashRecord with signature
    """
    file_path = Path(file_path)
    text = file_path.read_text(encoding="utf-8", errors="replace")
    content_hash = compute_content_hash(file_path)
    signature = compute_minhash_signature(text, k)
    shingles = _text_to_shingles(text, k)

    record = MinHashRecord(
        content_hash=content_hash,
        deal_id=deal_id,
        document_path=str(file_path),
        signature=signature,
        shingle_count=len(shingles),
    )

    # Load existing registry
    registry = _load_minhash_registry(minhash_registry_path)

    # Avoid duplicate entries
    existing = {(r.content_hash, r.deal_id) for r in registry}
    if (record.content_hash, record.deal_id) not in existing:
        registry.append(record)
        _save_minhash_registry(registry, minhash_registry_path)

    return record


def check_near_duplicates(
    file_path: Path,
    minhash_registry_path: Path,
    deal_id: str = "",
    threshold: float = 0.85,
    k: int = 5,
) -> Optional[dict[str, Any]]:
    """
    Check if a document is a near-duplicate of any registered document
    using MinHash signatures.

    Args:
        file_path: Path to document to check
        minhash_registry_path: Path to MinHash registry JSON
        deal_id: Current deal ID (skip self-matches)
        threshold: Jaccard similarity threshold for near-duplicate
        k: Shingle size

    Returns:
        Dict with match details if near-duplicate found, None otherwise
    """
    file_path = Path(file_path)
    text = file_path.read_text(encoding="utf-8", errors="replace")
    query_sig = compute_minhash_signature(text, k)
    content_hash = compute_content_hash(file_path)

    registry = _load_minhash_registry(minhash_registry_path)

    best_match: Optional[dict[str, Any]] = None
    best_similarity = 0.0

    for record in registry:
        # Skip self
        if record.deal_id == deal_id and record.content_hash == content_hash:
            continue

        jaccard = estimate_jaccard_from_signatures(query_sig, record.signature)

        if jaccard >= threshold and jaccard > best_similarity:
            best_similarity = jaccard
            best_match = {
                "matching_deal_id": record.deal_id,
                "matching_document": record.document_path,
                "jaccard_similarity": jaccard,
                "content_hash": record.content_hash,
            }

    return best_match


def _load_minhash_registry(path: Path) -> list[MinHashRecord]:
    """Load MinHash registry from JSON."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [MinHashRecord.from_dict(d) for d in data]
    except (json.JSONDecodeError, KeyError):
        return []


def _save_minhash_registry(registry: list[MinHashRecord], path: Path) -> None:
    """Save MinHash registry to JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [r.to_dict() for r in registry]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
