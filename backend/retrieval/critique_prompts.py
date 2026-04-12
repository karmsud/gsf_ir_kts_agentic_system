"""Phase 9.2 — Prompt templates for the directed critique loop.

Three prompt templates:
1. Single-question critique — binary evaluation
2. Gap-to-query translation — convert gap into retrieval query
3. Re-synthesis — integrate new chunks to fill a gap

Aliases:
    ``CRITIQUE_EVAL_PROMPT`` → ``CRITIQUE_PROMPT``
    ``RE_SYNTHESIS_PROMPT``  → ``RESYNTHESIS_PROMPT``
"""

from __future__ import annotations

# ── 1. Single-question critique prompt ────────────────────────────

CRITIQUE_PROMPT = """System: You are a document quality reviewer. Evaluate ONLY the specific \
question below. Do not evaluate anything else.

Question: {question}

Answer under review:
{answer}

Source content (retrieved chunks):
{chunks}

Instructions:
- Answer the question with "pass" or "fail"
- If "fail", describe the specific gap in 1-2 sentences
- Be strict: if the answer is vague where the source is specific, fail

Output format (JSON only):
{{"pass": true}}
or
{{"pass": false, "gap_description": "The answer omits the CAUTION about..."}}
"""

# ── 2. Gap→Query translation prompt ──────────────────────────────

GAP_TO_QUERY_PROMPT = """System: Convert a gap description into a retrieval search query.

Gap found in answer: {gap_description}
Original user question: {user_query}

Generate a 5-10 word search query that targets the missing information.
Return ONLY the query string — no explanation, no formatting.
"""

# ── 3. Re-synthesis prompt ────────────────────────────────────────

RESYNTHESIS_PROMPT = """System: You are a document analyst. Integrate new context into an \
existing answer to fill a specific gap.

Original question: {user_query}

Current answer (has a gap):
{current_answer}

Gap identified: {gap_description}

New context retrieved to fill the gap:
{new_chunks}

Instructions:
1. Integrate the new context into the current answer
2. Specifically address the identified gap
3. Do not remove correct existing content — only add and refine
4. Maintain the same answer format and citation style
5. Update confidence and source references
"""


# ── Spec-name aliases ─────────────────────────────────────────────
CRITIQUE_EVAL_PROMPT = CRITIQUE_PROMPT
RE_SYNTHESIS_PROMPT = RESYNTHESIS_PROMPT


# ── Formatting helpers ────────────────────────────────────────────

def format_chunks(chunks: list[dict]) -> str:
    """Concatenate chunk contents into a single string for prompts."""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        content = chunk.get("content", chunk.get("text", ""))
        doc_id = chunk.get("doc_id", chunk.get("metadata", {}).get("doc_id", "?"))
        parts.append(f"[Chunk {i} — doc {doc_id}]\n{content}")
    return "\n\n".join(parts)


def build_critique_prompt(question: str, answer: str, chunks: list[dict]) -> str:
    """Build a complete single-question critique prompt."""
    return CRITIQUE_PROMPT.format(
        question=question,
        answer=answer,
        chunks=format_chunks(chunks),
    )


def build_gap_to_query_prompt(gap_description: str, user_query: str) -> str:
    """Build a gap→query translation prompt."""
    return GAP_TO_QUERY_PROMPT.format(
        gap_description=gap_description,
        user_query=user_query,
    )


def build_resynthesis_prompt(
    user_query: str,
    current_answer: str,
    gap_description: str,
    new_chunks: list[dict],
) -> str:
    """Build a re-synthesis prompt to fill a gap."""
    return RESYNTHESIS_PROMPT.format(
        user_query=user_query,
        current_answer=current_answer,
        gap_description=gap_description,
        new_chunks=format_chunks(new_chunks),
    )
