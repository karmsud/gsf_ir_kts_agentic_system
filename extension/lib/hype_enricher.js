/**
 * Phase 8.5 — Targeted HyPE Enricher
 *
 * Generates hypothetical questions for definition and trigger chunks via
 * VS Code Language Model API, stores them in the backend's item_questions
 * collection for question-aware retrieval.
 *
 * Batches of 5 chunks with 300 ms delay between batches.
 */

'use strict';

/**
 * Enrich chunks with HyPE questions.
 *
 * @param {import('vscode')} vscode
 * @param {object} model - VS Code LM model handle
 * @param {string[]} chunkIds - IDs of chunks to enrich
 * @param {object} backendClient - { storeItemQuestions(id, qs), markQuestionsPending(id), getChunkText(id) }
 * @param {object} [options]
 * @param {number} [options.batchSize=5]
 * @param {number} [options.delayMs=300]
 * @returns {Promise<{enriched: number, pending: number, skipped: number}>}
 */
async function enrichChunksWithQuestions(vscode, model, chunkIds, backendClient, options = {}) {
    const batchSize = options.batchSize || 5;
    const delayMs = options.delayMs || 300;

    let enriched = 0;
    let pending = 0;
    let skipped = 0;

    for (let i = 0; i < chunkIds.length; i += batchSize) {
        const batch = chunkIds.slice(i, i + batchSize);

        for (const chunkId of batch) {
            try {
                const text = await backendClient.getChunkText(chunkId);
                if (!text) { skipped++; continue; }

                const prompt = [
                    vscode.LanguageModelChatMessage.User(
                        `Generate 3-5 diverse questions that a user might ask and this text would answer. ` +
                        `Return ONLY a JSON array of strings.\n\nText:\n${text.slice(0, 1500)}`
                    ),
                ];

                const response = await model.sendRequest(prompt, {});
                let rawText = '';
                for await (const part of response.text) { rawText += part; }
                rawText = rawText.replace(/```json\n?/g, '').replace(/```/g, '').trim();

                const questions = JSON.parse(rawText);
                if (Array.isArray(questions) && questions.length >= 1) {
                    await backendClient.storeItemQuestions(chunkId, questions);
                    enriched++;
                } else {
                    await backendClient.markQuestionsPending(chunkId);
                    pending++;
                }
            } catch (err) {
                // Rate-limit or other error → mark pending, continue
                try { await backendClient.markQuestionsPending(chunkId); } catch (_) { /* ignore */ }
                pending++;
            }
        }

        // Inter-batch delay to avoid rate limits
        if (i + batchSize < chunkIds.length) {
            await new Promise(resolve => setTimeout(resolve, delayMs));
        }
    }

    return { enriched, pending, skipped };
}

module.exports = { enrichChunksWithQuestions };
