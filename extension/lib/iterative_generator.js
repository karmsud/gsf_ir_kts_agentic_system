/**
 * Phase 8.8 — Self-RAG Iterative Generator
 *
 * Orchestrates the Self-RAG loop:
 *   1. Generate initial answer from retrieved context
 *   2. Analyze gaps via gap_analyzer
 *   3. Retrieve additional context for gap queries
 *   4. Re-generate with expanded context
 *   5. Repeat until no gaps or max rounds reached
 *
 * Carries exclude_chunk_ids AND content fingerprints to avoid re-fetching
 * the same information even when chunk IDs differ.
 * Enforces a token budget cap on accumulated context to prevent
 * "Message exceeds token limit" errors.
 */

'use strict';

const { analyzeGaps } = require('./gap_analyzer');

// Token estimation constants (must match participant.js)
const TOKEN_RATIO = 4;             // ~4 chars per token
const MAX_CONTEXT_CHARS = 600000;  // ~150K tokens — safe limit for Self-RAG accumulated context

/**
 * Create a content fingerprint for deduplication.
 * Uses first 200 chars (normalized) to detect semantically identical chunks
 * that may have different chunk_ids.
 */
function contentFingerprint(text) {
    if (!text) return '';
    return text.replace(/\s+/g, ' ').trim().slice(0, 200).toLowerCase();
}

/**
 * Calculate total character count of all chunks.
 */
function totalChunkChars(chunks) {
    return chunks.reduce((sum, c) => sum + (c.text || '').length, 0);
}

/**
 * @typedef {object} IterativeOptions
 * @property {number} [maxRounds=3] - Maximum Self-RAG iterations
 * @property {number} [maxContextChars=600000] - Max accumulated context chars before stopping
 * @property {Function} retrieveFn - async (query, excludeIds) => {chunks, chunkIds}
 * @property {Function} synthesizeFn - async (query, contextBlocks, previousAnswer?) => string
 * @property {Function} [onRound] - optional callback(roundNum, gaps) for progress reporting
 */

/**
 * Run the Self-RAG iterative generation loop.
 *
 * @param {import('vscode')} vscode
 * @param {object} model - VS Code LM model handle
 * @param {string} query - User query
 * @param {object[]} initialChunks - Initial context blocks from first retrieval
 * @param {IterativeOptions} options
 * @returns {Promise<{answer: string, rounds: number, totalChunks: number}>}
 */
async function generateIteratively(vscode, model, query, initialChunks, options) {
    const maxRounds = options.maxRounds || 3;
    const maxContextChars = options.maxContextChars || MAX_CONTEXT_CHARS;
    const retrieveFn = options.retrieveFn;
    const synthesizeFn = options.synthesizeFn;
    const onRound = options.onRound || (() => {});

    let allChunks = [...initialChunks];
    let excludeIds = new Set(initialChunks.map(c => c.id || c.chunk_id || '').filter(Boolean));
    // Content-based dedup: prevent re-adding chunks with same text but different IDs
    const seenFingerprints = new Set(initialChunks.map(c => contentFingerprint(c.text)).filter(Boolean));

    let answer = await synthesizeFn(query, allChunks, null);
    let rounds = 1;

    for (let round = 1; round < maxRounds; round++) {
        // Check accumulated context budget before analyzing gaps
        if (totalChunkChars(allChunks) >= maxContextChars) {
            break; // Context budget exhausted — stop to avoid token overflow
        }

        // Analyze gaps
        const gaps = await analyzeGaps(vscode, model, query, answer);
        onRound(round, gaps);

        if (!gaps || gaps.length === 0) {
            break; // No gaps — answer is complete
        }

        // Retrieve additional chunks for each gap query
        let newChunks = [];
        const remainingBudget = maxContextChars - totalChunkChars(allChunks);

        for (const gapQuery of gaps) {
            try {
                const result = await retrieveFn(gapQuery, Array.from(excludeIds));
                if (result && result.chunks) {
                    for (const chunk of result.chunks) {
                        const cid = chunk.id || chunk.chunk_id || '';
                        const fp = contentFingerprint(chunk.text);

                        // Skip if already seen by ID or content fingerprint
                        if (cid && excludeIds.has(cid)) continue;
                        if (fp && seenFingerprints.has(fp)) continue;

                        // Check if adding this chunk would exceed budget
                        const chunkLen = (chunk.text || '').length;
                        const currentTotal = totalChunkChars(allChunks) + totalChunkChars(newChunks);
                        if (currentTotal + chunkLen > maxContextChars) continue;

                        newChunks.push(chunk);
                        if (cid) excludeIds.add(cid);
                        if (fp) seenFingerprints.add(fp);
                    }
                }
            } catch (_) { /* skip failed sub-retrieval */ }
        }

        if (newChunks.length === 0) {
            break; // No new context found — stop
        }

        allChunks = allChunks.concat(newChunks);

        // Re-synthesize with expanded context
        answer = await synthesizeFn(query, allChunks, answer);
        rounds++;
    }

    return {
        answer,
        rounds,
        totalChunks: allChunks.length,
    };
}

module.exports = { generateIteratively };
