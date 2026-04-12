/**
 * Phase 19.1 — CRAG Client (JavaScript side)
 *
 * Corrective RAG — complements the Directed Critique Loop (Phase 9.2).
 * While the critique loop verifies coverage ("did the answer address
 * the expected questions?"), CRAG verifies correctness ("are the
 * claims in the answer supported by retrieved evidence?").
 *
 * Pipeline:
 *   1. Extract claims from the generated answer (via LLM)
 *   2. For each claim, retrieve evidence from the backend
 *   3. Verify each claim against evidence (via LLM)
 *   4. Rewrite the answer dropping/fixing unsupported claims
 *
 * Designed to run AFTER generateAnswer() and BEFORE or ALONGSIDE
 * the critique loop.  Both can be active simultaneously.
 */

const vscode = require('vscode');

// ── LLM call helper (shared with critique_client) ────────────────

/**
 * Send a prompt to a VS Code LM model and return the text response.
 * @param {import('vscode').LanguageModelChat} model
 * @param {string} prompt
 * @param {import('vscode').CancellationToken} token
 * @returns {Promise<string>}
 */
async function _callModel(model, prompt, token) {
  const messages = [vscode.LanguageModelChatMessage.User(prompt)];
  const response = await model.sendRequest(messages, {}, token);
  let text = '';
  for await (const chunk of response.text) {
    text += chunk;
  }
  return text.trim();
}

// ── Claim extraction prompt ──────────────────────────────────────

const CLAIM_EXTRACTION_PROMPT = `Extract all individual factual claims from the following answer.
Each claim should be a single, atomic, verifiable factual statement.
DO NOT include opinions, hedging, or meta-statements about the answer itself.
Return ONLY a JSON array of strings, one per claim.

Answer:
{answer}

Claims (JSON array):`;

// ── Claim verification prompt ────────────────────────────────────

const CLAIM_VERIFICATION_PROMPT = `You are a claim verification assistant. Given a factual claim and a set of evidence passages, determine if the evidence SUPPORTS, CONTRADICTS, or is AMBIGUOUS about the claim.

Claim: {claim}

Evidence passages:
{evidence}

Respond with EXACTLY one of these JSON objects:
- {"verdict": "supported", "confidence": 0.0-1.0, "explanation": "brief reason"}
- {"verdict": "contradicted", "confidence": 0.0-1.0, "explanation": "brief reason"}
- {"verdict": "ambiguous", "confidence": 0.0-1.0, "explanation": "brief reason"}
- {"verdict": "no_evidence", "confidence": 0.0, "explanation": "no relevant evidence found"}

JSON response:`;

// ── Answer rewrite prompt ────────────────────────────────────────

const ANSWER_REWRITE_PROMPT = `Rewrite the following answer to correct any unsupported or contradicted claims.
Keep all supported claims intact with their original wording.
Remove or hedge contradicted claims.
Mark claims with no evidence as uncertain.
Maintain the same overall structure and flow.

Original Answer:
{original_answer}

Claim Verification Results:
{verification_results}

Corrected Answer:`;

// ── Parse helpers ────────────────────────────────────────────────

function parseJsonArray(response) {
  let text = response.trim();
  // Strip markdown fences
  text = text.replace(/^```(?:json)?\s*/m, '');
  text = text.replace(/\s*```$/m, '');
  try {
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed)) return parsed.map(String);
  } catch {
    // Try to find array
    const match = text.match(/\[[\s\S]*\]/);
    if (match) {
      try {
        const parsed = JSON.parse(match[0]);
        if (Array.isArray(parsed)) return parsed.map(String);
      } catch { /* fall through */ }
    }
  }
  return [];
}

function parseVerdict(response) {
  let text = response.trim();
  text = text.replace(/^```(?:json)?\s*/m, '');
  text = text.replace(/\s*```$/m, '');
  try {
    return JSON.parse(text);
  } catch {
    const match = text.match(/\{[\s\S]*\}/);
    if (match) {
      try { return JSON.parse(match[0]); } catch { /* fall through */ }
    }
  }
  return { verdict: 'ambiguous', confidence: 0.5, explanation: 'Parse error' };
}

// ── CRAG Pipeline ────────────────────────────────────────────────

/**
 * Run the Corrective RAG pipeline.
 *
 * @param {object}  opts
 * @param {import('vscode').LanguageModelChat} opts.model       LLM for extraction/verification/rewriting
 * @param {import('vscode').ChatResponseStream} opts.stream     Chat response stream for progress
 * @param {import('vscode').CancellationToken}  opts.token      Cancellation token
 * @param {string}  opts.answer           Generated answer to verify
 * @param {Array}   opts.sourceChunks     Original retrieved chunks
 * @param {Function} [opts.retrieveFn]    async (query, excludeIds) => {chunks, chunkIds}
 * @param {object}  [opts.config]         CRAG config from backend payload
 * @returns {Promise<{answer: string, trace: object} | null>}
 */
async function runCRAG(opts) {
  const {
    model,
    stream,
    token,
    answer,
    sourceChunks = [],
    retrieveFn = null,
    config = {},
  } = opts;

  if (!model || !answer || answer.trim().length === 0) {
    return null;
  }

  const maxClaims = config.max_claims || 20;
  const evidenceTopK = config.evidence_top_k || 5;
  const dropContradicted = config.drop_contradicted !== false;
  const flagNoEvidence = config.flag_no_evidence !== false;

  const trace = {
    model: model.id || 'unknown',
    totalClaims: 0,
    supported: 0,
    contradicted: 0,
    ambiguous: 0,
    noEvidence: 0,
    correctionApplied: false,
    status: 'running',
  };

  try {
    // ── Step 1: Extract claims ─────────────────────────────────
    stream.progress('CRAG: Extracting factual claims from answer...');

    const extractPrompt = CLAIM_EXTRACTION_PROMPT.replace('{answer}', answer);
    let claimsRaw;
    try {
      const claimResponse = await _callModel(model, extractPrompt, token);
      claimsRaw = parseJsonArray(claimResponse);
    } catch {
      claimsRaw = [];
    }

    // Fallback: split by sentences
    if (claimsRaw.length === 0) {
      claimsRaw = answer
        .split(/(?<=[.!?])\s+(?=[A-Z])/)
        .filter(s => s.trim().length >= 10)
        .slice(0, maxClaims);
    }

    const claims = claimsRaw.slice(0, maxClaims);
    trace.totalClaims = claims.length;

    if (claims.length === 0) {
      trace.status = 'no_claims_extracted';
      return null;
    }

    stream.progress(`CRAG: Verifying ${claims.length} claims against evidence...`);

    // ── Step 2+3: Per-claim verification ───────────────────────
    const verifiedClaims = [];

    for (let i = 0; i < claims.length; i++) {
      if (token.isCancellationRequested) break;

      const claim = claims[i];

      // Gather evidence: first from source chunks, then retrieve more
      let evidenceChunks = [];

      // Check source chunks for relevance
      const claimWords = new Set(
        claim.toLowerCase().match(/\b[a-z]{3,}\b/g) || [],
      );
      const stopWords = new Set([
        'the', 'and', 'for', 'that', 'this', 'with', 'from', 'have',
        'has', 'are', 'was', 'were', 'been', 'will', 'would', 'could',
      ]);
      for (const sw of stopWords) claimWords.delete(sw);

      for (const chunk of sourceChunks) {
        const content = (chunk.content || chunk.text || '').toLowerCase();
        const chunkWords = new Set(content.match(/\b[a-z]{3,}\b/g) || []);
        const overlap = [...claimWords].filter(w => chunkWords.has(w)).length;
        const ratio = claimWords.size > 0 ? overlap / claimWords.size : 0;
        if (ratio >= 0.3) {
          evidenceChunks.push(chunk);
        }
      }

      // Retrieve additional evidence if needed
      if (evidenceChunks.length < 2 && retrieveFn) {
        try {
          const retrieved = await retrieveFn(claim, []);
          if (retrieved && retrieved.chunks) {
            const seen = new Set(evidenceChunks.map(c => (c.content || c.text || '').substring(0, 100)));
            for (const c of retrieved.chunks.slice(0, evidenceTopK)) {
              const key = (c.content || c.text || '').substring(0, 100);
              if (!seen.has(key)) {
                evidenceChunks.push(c);
                seen.add(key);
              }
            }
          }
        } catch { /* use what we have */ }
      }

      // Verify claim against evidence
      let verdict;
      if (evidenceChunks.length === 0) {
        verdict = { verdict: 'no_evidence', confidence: 0, explanation: 'No relevant evidence found' };
      } else {
        const evidenceText = evidenceChunks
          .slice(0, evidenceTopK)
          .map((c, idx) => `[${idx + 1}] ${(c.content || c.text || '').substring(0, 500)}`)
          .join('\n');

        const verifyPrompt = CLAIM_VERIFICATION_PROMPT
          .replace('{claim}', claim)
          .replace('{evidence}', evidenceText);

        try {
          const verifyResponse = await _callModel(model, verifyPrompt, token);
          verdict = parseVerdict(verifyResponse);
        } catch {
          verdict = { verdict: 'ambiguous', confidence: 0.5, explanation: 'Verification error' };
        }
      }

      verifiedClaims.push({
        claim,
        verdict: verdict.verdict,
        confidence: verdict.confidence || 0,
        explanation: verdict.explanation || '',
      });

      // Tally
      switch (verdict.verdict) {
        case 'supported': trace.supported++; break;
        case 'contradicted': trace.contradicted++; break;
        case 'no_evidence': trace.noEvidence++; break;
        default: trace.ambiguous++; break;
      }
    }

    // ── Step 4: Rewrite if needed ──────────────────────────────
    const needsCorrection = trace.contradicted > 0 || trace.noEvidence > 0;

    if (needsCorrection) {
      stream.progress(
        `CRAG: ${trace.contradicted} contradicted + ${trace.noEvidence} unsupported claims — rewriting...`,
      );

      const verificationLines = verifiedClaims.map(vc => {
        const status = vc.verdict.toUpperCase();
        return `- [${status}] "${vc.claim}" — ${vc.explanation}`;
      }).join('\n');

      const rewritePrompt = ANSWER_REWRITE_PROMPT
        .replace('{original_answer}', answer)
        .replace('{verification_results}', verificationLines);

      try {
        const corrected = await _callModel(model, rewritePrompt, token);
        if (corrected && corrected.length > 50) {
          trace.correctionApplied = true;
          trace.status = 'corrected';

          stream.progress(
            `CRAG complete: ${trace.supported} supported, ${trace.contradicted} contradicted, ${trace.noEvidence} no-evidence → answer corrected`,
          );

          return {
            answer: corrected,
            trace,
          };
        }
      } catch { /* fall through to heuristic */ }

      // Heuristic fallback: annotate inline
      let heuristicAnswer = answer;
      for (const vc of verifiedClaims) {
        if (vc.verdict === 'contradicted' && dropContradicted) {
          heuristicAnswer = heuristicAnswer.replace(
            vc.claim,
            `~~${vc.claim}~~ *(contradicted by source evidence)*`,
          );
        } else if (vc.verdict === 'no_evidence' && flagNoEvidence) {
          heuristicAnswer = heuristicAnswer.replace(
            vc.claim,
            `${vc.claim} *(⚠ unverified — no supporting evidence found)*`,
          );
        }
      }

      trace.correctionApplied = true;
      trace.status = 'corrected_heuristic';

      return {
        answer: heuristicAnswer,
        trace,
      };
    }

    // All claims supported
    trace.status = 'all_supported';
    stream.progress(
      `CRAG complete: all ${trace.totalClaims} claims verified as supported`,
    );

    return {
      answer,
      trace,
    };
  } catch (err) {
    trace.status = `error: ${err.message || String(err)}`;
    return null;
  }
}

// ── Exports ──────────────────────────────────────────────────────

module.exports = {
  runCRAG,
  parseJsonArray,
  parseVerdict,
};
