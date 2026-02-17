from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class EvidenceMatch:
    claim_text: str
    matched_chunk_id: str
    source_uri: str
    match_span: tuple[int, int]
    match_score: float
    match_method: str
    citation: str


@dataclass
class ProvenanceLedger:
    query: str
    generated_answer: str
    claims: list[str]
    evidence_matches: list[EvidenceMatch]
    coverage: float
    uncited_claims: list[str]
    timestamp: str
    strict_mode_passed: bool | None = None


@dataclass
class ValidationResult:
    passed: bool
    coverage: float
    uncited_claims: list[str]
    message: str


class ProvenanceError(RuntimeError):
    def __init__(self, message: str, error_code: str = "E_INCOMPLETE_PROVENANCE", details: dict[str, Any] | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}

    def to_error_payload(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.error_code,
                "message": str(self),
                "details": self.details,
            }
        }


class EvidenceMatcher:
    def __init__(self, casefolding_enabled: bool = True, numeric_tolerance: float = 0.01, code_normalization: bool = True):
        self.casefolding_enabled = casefolding_enabled
        self.numeric_tolerance = numeric_tolerance
        self.code_normalization = code_normalization

    @staticmethod
    def split_into_claims(answer: str) -> list[str]:
        text = (answer or "").strip()
        if not text:
            return []

        claims = re.split(r"(?<=[.!?])\s+(?=[A-Z\[])", text)
        return [c.strip() for c in claims if c and c.strip()]

    @staticmethod
    def _normalize_tokens(text: str) -> str:
        lowered = text.lower()
        lowered = re.sub(r"\s+", " ", lowered)
        lowered = re.sub(r"[\t\n\r]+", " ", lowered)
        lowered = re.sub(r"\s*([.,;:!?])\s*", r"\1 ", lowered)
        return re.sub(r"\s+", " ", lowered).strip()

    @staticmethod
    def _normalize_codes(text: str) -> str:
        normalized = text.upper()
        normalized = re.sub(r"[-_\s]+", "", normalized)
        return normalized

    def _format_citation(self, chunk: Any) -> str:
        section = None
        page = None
        source = None

        if isinstance(chunk, dict):
            section = chunk.get("section_id") or chunk.get("section")
            page = chunk.get("page")
            source = chunk.get("source_uri") or chunk.get("source_path") or chunk.get("doc_id")
        else:
            section = getattr(chunk, "section_id", None) or getattr(chunk, "section", None)
            page = getattr(chunk, "page", None)
            source = getattr(chunk, "source_uri", None) or getattr(chunk, "source_path", None) or getattr(chunk, "doc_id", None)

        parts = []
        if source:
            parts.append(str(source))
        if section:
            parts.append(str(section))
        if page is not None:
            parts.append(f"p.{page}")
        return f"[{', '.join(parts)}]" if parts else "[citation]"

    def _make_match(self, claim: str, chunk: Any, start: int, end: int, score: float, method: str) -> EvidenceMatch:
        if isinstance(chunk, dict):
            chunk_id = str(chunk.get("chunk_id", ""))
            source_uri = str(chunk.get("source_uri") or chunk.get("source_path") or chunk.get("doc_id") or "")
        else:
            chunk_id = str(getattr(chunk, "chunk_id", ""))
            source_uri = str(getattr(chunk, "source_uri", None) or getattr(chunk, "source_path", None) or getattr(chunk, "doc_id", ""))
        return EvidenceMatch(
            claim_text=claim,
            matched_chunk_id=chunk_id,
            source_uri=source_uri,
            match_span=(start, end),
            match_score=score,
            match_method=method,
            citation=self._format_citation(chunk),
        )

    def find_match(self, claim: str, chunk: Any) -> EvidenceMatch | None:
        chunk_text = chunk.get("content", "") if isinstance(chunk, dict) else getattr(chunk, "content", "")
        if not claim or not chunk_text:
            return None

        # R1 exact
        idx = chunk_text.find(claim)
        if idx >= 0:
            return self._make_match(claim, chunk, idx, idx + len(claim), 1.0, "exact")

        # R2 casefolded
        if self.casefolding_enabled:
            claim_cf = claim.casefold()
            chunk_cf = chunk_text.casefold()
            idx_cf = chunk_cf.find(claim_cf)
            if idx_cf >= 0:
                return self._make_match(claim, chunk, idx_cf, idx_cf + len(claim), 0.95, "casefolded")

        # R3 token boundary / normalized punctuation+spaces
        norm_claim = self._normalize_tokens(claim)
        norm_chunk = self._normalize_tokens(chunk_text)
        idx_norm = norm_chunk.find(norm_claim)
        if idx_norm >= 0:
            return self._make_match(claim, chunk, idx_norm, idx_norm + len(norm_claim), 0.90, "token_boundary")

        # R4 numeric tolerance
        claim_numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", claim)]
        chunk_numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", chunk_text)]
        if claim_numbers and chunk_numbers:
            all_numbers_match = True
            for value in claim_numbers:
                matched = False
                for candidate in chunk_numbers:
                    tolerance = max(self.numeric_tolerance, value * self.numeric_tolerance)
                    if abs(candidate - value) <= tolerance:
                        matched = True
                        break
                if not matched:
                    all_numbers_match = False
                    break
            if all_numbers_match:
                return self._make_match(claim, chunk, 0, min(len(claim), len(chunk_text)), 0.85, "numeric_tolerance")

        # R5 code normalized
        if self.code_normalization:
            norm_code_claim = self._normalize_codes(claim)
            norm_code_chunk = self._normalize_codes(chunk_text)
            idx_code = norm_code_chunk.find(norm_code_claim)
            if idx_code >= 0 and norm_code_claim:
                return self._make_match(claim, chunk, idx_code, idx_code + len(norm_code_claim), 0.85, "code_normalized")

        return None

    @staticmethod
    def has_match(claim: str, matches: list[EvidenceMatch]) -> bool:
        return any(m.claim_text == claim for m in matches)

    def match_claims_to_chunks(self, generated_answer: str, retrieved_chunks: list[Any], query: str = "") -> ProvenanceLedger:
        claims = self.split_into_claims(generated_answer)
        evidence_matches: list[EvidenceMatch] = []

        for claim in claims:
            best_match: EvidenceMatch | None = None
            for chunk in retrieved_chunks:
                match = self.find_match(claim, chunk)
                if not match:
                    continue
                if best_match is None or match.match_score > best_match.match_score:
                    best_match = match
            if best_match:
                evidence_matches.append(best_match)

        coverage = (len(evidence_matches) / len(claims)) if claims else 0.0
        uncited = [claim for claim in claims if not self.has_match(claim, evidence_matches)]

        return ProvenanceLedger(
            query=query,
            generated_answer=generated_answer,
            claims=claims,
            evidence_matches=evidence_matches,
            coverage=coverage,
            uncited_claims=uncited,
            timestamp=datetime.now(timezone.utc).isoformat(),
            strict_mode_passed=None,
        )

    @staticmethod
    def compute_provenance_coverage_from_text(answer_text: str, citations: list[str] | list[dict[str, Any]]) -> float:
        claims = EvidenceMatcher.split_into_claims(answer_text)
        if not claims:
            return 0.0

        citation_strings: list[str] = []
        for c in citations:
            if isinstance(c, dict):
                joined = " ".join(str(v) for v in c.values() if v is not None)
                citation_strings.append(joined)
            else:
                citation_strings.append(str(c))

        covered = 0
        for claim in claims:
            if re.search(r"\[[^\]]+\]", claim):
                covered += 1
                continue
            claim_tokens = set(re.findall(r"[A-Za-z0-9_]+", claim.lower()))
            if not claim_tokens:
                continue
            if any(claim_tokens & set(re.findall(r"[A-Za-z0-9_]+", c.lower())) for c in citation_strings):
                covered += 1
        return covered / len(claims)

    @staticmethod
    def append_ledger(path: str | Path, ledger: ProvenanceLedger) -> None:
        ledger_path = Path(path)
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(ledger)
        with ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def validate_strict_mode(ledger: ProvenanceLedger) -> ValidationResult:
    if ledger.coverage < 1.0:
        return ValidationResult(
            passed=False,
            coverage=ledger.coverage,
            uncited_claims=ledger.uncited_claims,
            message=f"STRICT MODE VIOLATION: {len(ledger.uncited_claims)} uncited claims",
        )
    return ValidationResult(
        passed=True,
        coverage=1.0,
        uncited_claims=[],
        message="All claims cited",
    )


def enforce_provenance_contract(
    ledger: ProvenanceLedger,
    strict_mode: bool = False,
    production_threshold: float = 0.95,
) -> ValidationResult:
    if strict_mode:
        result = validate_strict_mode(ledger)
        if not result.passed:
            raise ProvenanceError(
                message=f"Strict mode enabled: {len(result.uncited_claims)} sentence(s) lack citations",
                details={
                    "total_sentences": len(ledger.claims),
                    "cited_sentences": len(ledger.claims) - len(result.uncited_claims),
                    "uncited_sentences": result.uncited_claims,
                    "coverage": ledger.coverage,
                    "resolution_attempted": True,
                    "partial_answer": ledger.generated_answer,
                },
            )
        return result

    passed = ledger.coverage >= production_threshold
    return ValidationResult(
        passed=passed,
        coverage=ledger.coverage,
        uncited_claims=ledger.uncited_claims,
        message=(
            f"Production coverage {ledger.coverage:.2%} is below threshold {production_threshold:.2%}"
            if not passed
            else "Production provenance coverage passed"
        ),
    )
