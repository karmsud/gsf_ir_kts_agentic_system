"""Phase 19.1 — Corrective RAG (CRAG).

Complements the Directed Critique Loop (Phase 9.2).  While the critique
loop verifies *coverage* ("did the answer address the expected questions?"),
CRAG verifies *correctness* ("are the claims in the answer actually
supported by the retrieved evidence?").

Pipeline:
    1. **Claim Extraction** — Parse the generated answer into individual,
       atomic factual claims.
    2. **Per-Claim Evidence Retrieval** — For each claim, retrieve evidence
       from the vector store using the claim as a query.
    3. **Claim Verification** — Check whether the retrieved evidence
       supports, contradicts, or is ambiguous about each claim.
    4. **Answer Rewriting** — Rewrite the answer, dropping unsupported
       claims and strengthening supported ones with citations.

The module is designed to work with BOTH legal and non-legal documents.
It is invoked AFTER the initial answer generation and BEFORE/ALONGSIDE
the critique loop.

Reference: Yan et al. 2024 — "Corrective Retrieval Augmented Generation."
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Enums & Data Models ──────────────────────────────────────────

class ClaimVerdict(Enum):
    """Verification result for a single claim."""
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    AMBIGUOUS = "ambiguous"
    NO_EVIDENCE = "no_evidence"


@dataclass
class Claim:
    """A single atomic factual claim extracted from an answer."""
    text: str
    claim_index: int
    source_sentence: str = ""


@dataclass
class VerifiedClaim:
    """A claim with its verification result."""
    claim: Claim
    verdict: ClaimVerdict
    evidence_chunks: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    explanation: str = ""


@dataclass
class CRAGResult:
    """Result of the full CRAG pipeline."""
    original_answer: str
    corrected_answer: str
    claims: List[VerifiedClaim] = field(default_factory=list)
    supported_count: int = 0
    contradicted_count: int = 0
    ambiguous_count: int = 0
    no_evidence_count: int = 0
    total_claims: int = 0
    correction_applied: bool = False

    @property
    def accuracy_ratio(self) -> float:
        """Fraction of claims that are supported."""
        if self.total_claims == 0:
            return 1.0
        return self.supported_count / self.total_claims

    @property
    def needs_correction(self) -> bool:
        """True if any claims are contradicted or have no evidence."""
        return self.contradicted_count > 0 or self.no_evidence_count > 0


# ── Configuration ─────────────────────────────────────────────────

@dataclass
class CRAGConfig:
    """Configuration for Corrective RAG pipeline."""
    enabled: bool = True
    # Claim extraction
    max_claims: int = 20                        # Cap claims per answer
    min_claim_length: int = 10                  # Ignore trivially short claims
    # Evidence retrieval
    evidence_top_k: int = 5                     # Top-k per claim retrieval
    evidence_min_similarity: float = 0.3        # Minimum similarity threshold
    # Verification thresholds
    support_threshold: float = 0.65             # Above = SUPPORTED
    contradiction_threshold: float = 0.4        # Below = CONTRADICTED
    # Rewriting
    drop_contradicted: bool = True              # Remove contradicted claims
    flag_no_evidence: bool = True               # Mark no-evidence claims
    # Performance
    max_parallel_claims: int = 5                # Concurrent evidence lookups


# ── Prompt Templates ──────────────────────────────────────────────

CLAIM_EXTRACTION_PROMPT = """Extract all individual factual claims from the following answer.
Each claim should be a single, atomic, verifiable factual statement.
DO NOT include opinions, hedging, or meta-statements about the answer itself.
Return ONLY a JSON array of strings, one per claim.

Answer:
{answer}

Claims (JSON array):"""


CLAIM_VERIFICATION_PROMPT = """You are a claim verification assistant. Given a factual claim and a set of evidence passages, determine if the evidence SUPPORTS, CONTRADICTS, or is AMBIGUOUS about the claim.

Claim: {claim}

Evidence passages:
{evidence}

Respond with EXACTLY one of these JSON objects:
- {{"verdict": "supported", "confidence": 0.0-1.0, "explanation": "brief reason"}}
- {{"verdict": "contradicted", "confidence": 0.0-1.0, "explanation": "brief reason"}}
- {{"verdict": "ambiguous", "confidence": 0.0-1.0, "explanation": "brief reason"}}
- {{"verdict": "no_evidence", "confidence": 0.0, "explanation": "no relevant evidence found"}}

JSON response:"""


ANSWER_REWRITE_PROMPT = """Rewrite the following answer to correct any unsupported or contradicted claims.
Keep all supported claims intact with their original wording.
Remove or hedge contradicted claims.
Mark claims with no evidence as uncertain.
Maintain the same overall structure and flow.

Original Answer:
{original_answer}

Claim Verification Results:
{verification_results}

Corrected Answer:"""


# ── Claim Extractor ───────────────────────────────────────────────

class ClaimExtractor:
    """Extract atomic factual claims from a generated answer."""

    # Regex-based fallback: split on sentence boundaries
    _SENTENCE_RE = re.compile(
        r'(?<=[.!?])\s+(?=[A-Z])'
        r'|(?<=\n)\s*[-•]\s*'          # bullet points
        r'|(?<=\n)\s*\d+[.)]\s*'       # numbered lists
    )

    def __init__(self, config: CRAGConfig):
        self.config = config

    def extract_with_llm(
        self,
        answer: str,
        llm_callable: Callable[[str], str],
    ) -> List[Claim]:
        """Extract claims using an LLM call.

        Parameters
        ----------
        answer : str
            The generated answer to decompose.
        llm_callable : callable
            Function ``(prompt: str) -> str`` that calls an LLM.

        Returns
        -------
        List[Claim]
            Extracted atomic claims.
        """
        prompt = CLAIM_EXTRACTION_PROMPT.format(answer=answer)
        try:
            response = llm_callable(prompt)
            claims_raw = self._parse_json_array(response)
            claims = []
            for i, text in enumerate(claims_raw[:self.config.max_claims]):
                text = text.strip()
                if len(text) >= self.config.min_claim_length:
                    claims.append(Claim(
                        text=text,
                        claim_index=i,
                        source_sentence=text,
                    ))
            if claims:
                logger.info("[CRAG] Extracted %d claims via LLM", len(claims))
                return claims
        except Exception as e:
            logger.warning("[CRAG] LLM claim extraction failed: %s — falling back to regex", e)

        # Fallback to regex-based extraction
        return self.extract_with_regex(answer)

    def extract_with_regex(self, answer: str) -> List[Claim]:
        """Fallback: split answer into sentences as claims."""
        sentences = self._SENTENCE_RE.split(answer)
        claims = []
        for i, sent in enumerate(sentences[:self.config.max_claims]):
            sent = sent.strip()
            # Remove markdown formatting
            sent = re.sub(r'\*\*|__|~~|`', '', sent)
            sent = re.sub(r'^\s*[-•]\s*', '', sent)
            sent = re.sub(r'^\s*\d+[.)]\s*', '', sent)
            if len(sent) >= self.config.min_claim_length:
                claims.append(Claim(
                    text=sent,
                    claim_index=i,
                    source_sentence=sent,
                ))
        logger.info("[CRAG] Extracted %d claims via regex fallback", len(claims))
        return claims

    @staticmethod
    def _parse_json_array(response: str) -> List[str]:
        """Parse a JSON array from LLM response, tolerating markdown fences."""
        text = response.strip()
        # Strip markdown code fences
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            # Try to find array in response
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                    if isinstance(parsed, list):
                        return [str(item) for item in parsed]
                except json.JSONDecodeError:
                    pass
        return []


# ── Claim Verifier ────────────────────────────────────────────────

class ClaimVerifier:
    """Verify individual claims against retrieved evidence."""

    def __init__(self, config: CRAGConfig):
        self.config = config

    def verify_with_llm(
        self,
        claim: Claim,
        evidence_chunks: List[Dict[str, Any]],
        llm_callable: Callable[[str], str],
    ) -> VerifiedClaim:
        """Verify a claim using LLM-based evaluation.

        Parameters
        ----------
        claim : Claim
            The claim to verify.
        evidence_chunks : list
            Retrieved evidence chunks.
        llm_callable : callable
            ``(prompt: str) -> str``
        """
        if not evidence_chunks:
            return VerifiedClaim(
                claim=claim,
                verdict=ClaimVerdict.NO_EVIDENCE,
                evidence_chunks=[],
                confidence=0.0,
                explanation="No relevant evidence found for this claim.",
            )

        # Build evidence text
        evidence_text = ""
        for i, chunk in enumerate(evidence_chunks[:self.config.evidence_top_k]):
            content = chunk.get("content") or chunk.get("text") or ""
            source = chunk.get("source_path") or chunk.get("metadata", {}).get("source_path", "")
            evidence_text += f"\n[{i + 1}] {content[:500]}"
            if source:
                evidence_text += f"\n    Source: {source}"
            evidence_text += "\n"

        prompt = CLAIM_VERIFICATION_PROMPT.format(
            claim=claim.text,
            evidence=evidence_text,
        )

        try:
            response = llm_callable(prompt)
            result = self._parse_verdict(response)

            verdict = ClaimVerdict.AMBIGUOUS
            if result.get("verdict") == "supported":
                verdict = ClaimVerdict.SUPPORTED
            elif result.get("verdict") == "contradicted":
                verdict = ClaimVerdict.CONTRADICTED
            elif result.get("verdict") == "no_evidence":
                verdict = ClaimVerdict.NO_EVIDENCE

            return VerifiedClaim(
                claim=claim,
                verdict=verdict,
                evidence_chunks=evidence_chunks,
                confidence=float(result.get("confidence", 0.5)),
                explanation=result.get("explanation", ""),
            )
        except Exception as e:
            logger.warning("[CRAG] LLM verification failed for claim %d: %s", claim.claim_index, e)
            return self.verify_with_heuristic(claim, evidence_chunks)

    def verify_with_heuristic(
        self,
        claim: Claim,
        evidence_chunks: List[Dict[str, Any]],
    ) -> VerifiedClaim:
        """Heuristic fallback: keyword overlap scoring."""
        if not evidence_chunks:
            return VerifiedClaim(
                claim=claim,
                verdict=ClaimVerdict.NO_EVIDENCE,
                confidence=0.0,
                explanation="No evidence chunks provided.",
            )

        claim_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', claim.text.lower()))
        stop = {
            "the", "and", "for", "that", "this", "with", "from", "have",
            "has", "are", "was", "were", "been", "will", "would", "could",
            "should", "not", "but", "also", "can", "may", "its", "their",
        }
        claim_words -= stop

        if not claim_words:
            return VerifiedClaim(
                claim=claim,
                verdict=ClaimVerdict.AMBIGUOUS,
                confidence=0.3,
                explanation="Claim too short for heuristic verification.",
            )

        best_overlap = 0.0
        for chunk in evidence_chunks:
            content = (chunk.get("content") or chunk.get("text") or "").lower()
            chunk_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', content))
            overlap = len(claim_words & chunk_words) / len(claim_words) if claim_words else 0
            best_overlap = max(best_overlap, overlap)

        if best_overlap >= self.config.support_threshold:
            verdict = ClaimVerdict.SUPPORTED
        elif best_overlap < self.config.contradiction_threshold:
            verdict = ClaimVerdict.NO_EVIDENCE
        else:
            verdict = ClaimVerdict.AMBIGUOUS

        return VerifiedClaim(
            claim=claim,
            verdict=verdict,
            evidence_chunks=evidence_chunks,
            confidence=best_overlap,
            explanation=f"Heuristic keyword overlap: {best_overlap:.2f}",
        )

    @staticmethod
    def _parse_verdict(response: str) -> Dict[str, Any]:
        """Parse LLM verdict response as JSON."""
        text = response.strip()
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return {"verdict": "ambiguous", "confidence": 0.5, "explanation": "Parse error"}


# ── Answer Rewriter ───────────────────────────────────────────────

class AnswerRewriter:
    """Rewrite an answer based on claim verification results."""

    def __init__(self, config: CRAGConfig):
        self.config = config

    def rewrite_with_llm(
        self,
        original_answer: str,
        verified_claims: List[VerifiedClaim],
        llm_callable: Callable[[str], str],
    ) -> str:
        """Rewrite the answer using LLM, informed by verification results."""
        # Build verification summary
        verification_lines = []
        for vc in verified_claims:
            status = vc.verdict.value.upper()
            verification_lines.append(
                f"- [{status}] \"{vc.claim.text}\" — {vc.explanation}"
            )
        verification_text = "\n".join(verification_lines)

        prompt = ANSWER_REWRITE_PROMPT.format(
            original_answer=original_answer,
            verification_results=verification_text,
        )

        try:
            corrected = llm_callable(prompt)
            if corrected and len(corrected) > 50:
                logger.info("[CRAG] Answer rewritten by LLM (%d→%d chars)",
                            len(original_answer), len(corrected))
                return corrected.strip()
        except Exception as e:
            logger.warning("[CRAG] LLM rewrite failed: %s — using heuristic", e)

        return self.rewrite_with_heuristic(original_answer, verified_claims)

    def rewrite_with_heuristic(
        self,
        original_answer: str,
        verified_claims: List[VerifiedClaim],
    ) -> str:
        """Heuristic rewrite: annotate unsupported claims inline."""
        result = original_answer

        for vc in reversed(verified_claims):
            if vc.verdict == ClaimVerdict.CONTRADICTED and self.config.drop_contradicted:
                # Strike through contradicted claims
                result = result.replace(
                    vc.claim.source_sentence,
                    f"~~{vc.claim.source_sentence}~~ *(contradicted by source evidence)*",
                )
            elif vc.verdict == ClaimVerdict.NO_EVIDENCE and self.config.flag_no_evidence:
                # Flag no-evidence claims
                result = result.replace(
                    vc.claim.source_sentence,
                    f"{vc.claim.source_sentence} *(⚠ unverified — no supporting evidence found)*",
                )

        return result


# ── CRAG Pipeline Orchestrator ────────────────────────────────────

class CRAGProcessor:
    """Orchestrate the full Corrective RAG pipeline.

    Designed to complement the Directed Critique Loop:
    - Critique loop asks: "Did the answer cover required topics?"
    - CRAG asks: "Are the specific claims in the answer factually correct?"

    Usage::

        processor = CRAGProcessor(config)
        result = processor.run(
            answer=generated_answer,
            retrieve_fn=my_retrieve_function,
            llm_callable=my_llm_function,
        )
        if result.needs_correction:
            final_answer = result.corrected_answer
    """

    def __init__(self, config: Optional[CRAGConfig] = None):
        self.config = config or CRAGConfig()
        self.extractor = ClaimExtractor(self.config)
        self.verifier = ClaimVerifier(self.config)
        self.rewriter = AnswerRewriter(self.config)

    def run(
        self,
        answer: str,
        retrieve_fn: Callable[[str, int], List[Dict[str, Any]]],
        llm_callable: Optional[Callable[[str], str]] = None,
        source_chunks: Optional[List[Dict[str, Any]]] = None,
    ) -> CRAGResult:
        """Execute the full CRAG pipeline.

        Parameters
        ----------
        answer : str
            The generated answer to verify and correct.
        retrieve_fn : callable
            ``(query: str, top_k: int) -> List[Dict]`` — retrieves evidence
            chunks from the vector store for a given query.
        llm_callable : callable, optional
            ``(prompt: str) -> str`` — calls an LLM. If None, uses heuristic
            fallbacks for all steps.
        source_chunks : list, optional
            Original retrieved chunks (used as first-pass evidence before
            additional retrieval).

        Returns
        -------
        CRAGResult
            Full verification and correction result.
        """
        if not answer or not answer.strip():
            return CRAGResult(
                original_answer=answer,
                corrected_answer=answer,
            )

        logger.info("[CRAG] Starting corrective RAG pipeline on %d-char answer", len(answer))

        # ── Step 1: Extract claims ────────────────────────────────
        if llm_callable:
            claims = self.extractor.extract_with_llm(answer, llm_callable)
        else:
            claims = self.extractor.extract_with_regex(answer)

        if not claims:
            logger.info("[CRAG] No claims extracted — skipping verification")
            return CRAGResult(
                original_answer=answer,
                corrected_answer=answer,
            )

        logger.info("[CRAG] Step 1 complete: %d claims extracted", len(claims))

        # ── Step 2+3: Per-claim evidence retrieval + verification ─
        verified: List[VerifiedClaim] = []
        for claim in claims:
            # First check source chunks (already retrieved)
            evidence = self._find_evidence_in_sources(claim, source_chunks or [])

            # If insufficient evidence from sources, retrieve more
            if len(evidence) < 2:
                try:
                    additional = retrieve_fn(claim.text, self.config.evidence_top_k)
                    # Deduplicate by content
                    seen_content = {(c.get("content") or c.get("text", ""))[:100] for c in evidence}
                    for chunk in additional:
                        content = (chunk.get("content") or chunk.get("text", ""))[:100]
                        if content not in seen_content:
                            evidence.append(chunk)
                            seen_content.add(content)
                except Exception as e:
                    logger.warning("[CRAG] Evidence retrieval failed for claim %d: %s",
                                   claim.claim_index, e)

            # Verify claim against evidence
            if llm_callable:
                vc = self.verifier.verify_with_llm(claim, evidence, llm_callable)
            else:
                vc = self.verifier.verify_with_heuristic(claim, evidence)
            verified.append(vc)

        # ── Tally results ─────────────────────────────────────────
        supported = sum(1 for v in verified if v.verdict == ClaimVerdict.SUPPORTED)
        contradicted = sum(1 for v in verified if v.verdict == ClaimVerdict.CONTRADICTED)
        ambiguous = sum(1 for v in verified if v.verdict == ClaimVerdict.AMBIGUOUS)
        no_evidence = sum(1 for v in verified if v.verdict == ClaimVerdict.NO_EVIDENCE)

        logger.info(
            "[CRAG] Step 2-3 complete: %d supported, %d contradicted, %d ambiguous, %d no-evidence",
            supported, contradicted, ambiguous, no_evidence,
        )

        # ── Step 4: Rewrite if needed ─────────────────────────────
        needs_correction = contradicted > 0 or no_evidence > 0
        corrected_answer = answer

        if needs_correction:
            if llm_callable:
                corrected_answer = self.rewriter.rewrite_with_llm(
                    answer, verified, llm_callable
                )
            else:
                corrected_answer = self.rewriter.rewrite_with_heuristic(
                    answer, verified
                )
            logger.info("[CRAG] Step 4 complete: answer rewritten")
        else:
            logger.info("[CRAG] Step 4: no correction needed — all claims supported or ambiguous")

        return CRAGResult(
            original_answer=answer,
            corrected_answer=corrected_answer,
            claims=verified,
            supported_count=supported,
            contradicted_count=contradicted,
            ambiguous_count=ambiguous,
            no_evidence_count=no_evidence,
            total_claims=len(verified),
            correction_applied=needs_correction,
        )

    def _find_evidence_in_sources(
        self,
        claim: Claim,
        source_chunks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Check existing source chunks for evidence of a claim."""
        if not source_chunks:
            return []

        claim_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', claim.text.lower()))
        stop = {
            "the", "and", "for", "that", "this", "with", "from", "have",
            "has", "are", "was", "were", "been", "will", "would", "could",
        }
        claim_words -= stop

        if not claim_words:
            return []

        scored = []
        for chunk in source_chunks:
            content = (chunk.get("content") or chunk.get("text") or "").lower()
            chunk_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', content))
            overlap = len(claim_words & chunk_words) / len(claim_words) if claim_words else 0
            if overlap >= self.config.evidence_min_similarity:
                scored.append((overlap, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [chunk for _, chunk in scored[:self.config.evidence_top_k]]

    def run_sync(
        self,
        answer: str,
        retrieve_fn: Callable[[str, int], List[Dict[str, Any]]],
        llm_callable: Optional[Callable[[str], str]] = None,
        source_chunks: Optional[List[Dict[str, Any]]] = None,
    ) -> CRAGResult:
        """Synchronous alias for ``run()``."""
        return self.run(answer, retrieve_fn, llm_callable, source_chunks)
