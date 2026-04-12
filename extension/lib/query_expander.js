/**
 * Phase 8.6 — Multi-Query RAG Fusion (JS side)
 *
 * Uses VS Code LM API to generate query variants for multi-query retrieval.
 * Falls back to empty array on any error.
 */

'use strict';

/**
 * Expand a user query into multiple variants via LLM.
 *
 * @param {import('vscode')} vscode
 * @param {object} model - VS Code LM model handle
 * @param {string} query - Original user query
 * @param {number} [numVariants=2]
 * @returns {Promise<string[]>} Array of variant queries (may be empty)
 */
async function expandQueryWithLLM(vscode, model, query, numVariants = 2) {
    try {
        const prompt = [
            vscode.LanguageModelChatMessage.User(
                `Given this legal/financial query, generate ${numVariants} semantically different rephrasings ` +
                `that would help retrieve complementary relevant sections. ` +
                `Return ONLY a JSON array of strings, no explanation.\n\nQuery: "${query}"`
            ),
        ];

        const response = await model.sendRequest(prompt, {});
        let rawText = '';
        for await (const part of response.text) { rawText += part; }

        // Strip markdown code fences if present
        rawText = rawText.replace(/```json\n?/g, '').replace(/```/g, '').trim();

        const variants = JSON.parse(rawText);
        if (Array.isArray(variants) && variants.every(v => typeof v === 'string')) {
            return variants.slice(0, numVariants);
        }
        return [];
    } catch (err) {
        // Graceful degradation — upstream caller uses original query alone
        return [];
    }
}

module.exports = { expandQueryWithLLM };
