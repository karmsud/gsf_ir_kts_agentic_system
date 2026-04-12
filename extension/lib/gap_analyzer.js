/**
 * Phase 8.8 — Self-RAG Gap Analyzer
 *
 * After an initial answer is generated, uses the LLM to identify
 * information gaps that require additional retrieval rounds.
 * Returns an array of follow-up queries (max 5) for the iterative loop.
 */

'use strict';

/**
 * Analyze an answer for information gaps and return follow-up queries.
 *
 * @param {import('vscode')} vscode
 * @param {object} model - VS Code LM model handle
 * @param {string} query - Original user query
 * @param {string} answer - Current generated answer
 * @param {number} [maxGaps=3]
 * @returns {Promise<string[]>} Array of gap-filling queries (may be empty)
 */
async function analyzeGaps(vscode, model, query, answer, maxGaps = 3) {
    try {
        const prompt = [
            vscode.LanguageModelChatMessage.User(
                `You are a legal/financial document analyst. Given the original question and the current answer, ` +
                `identify specific information gaps or unsupported claims.\n\n` +
                `Question: "${query}"\n\n` +
                `Answer:\n${answer.slice(0, 3000)}\n\n` +
                `Rules:\n` +
                `- Only flag genuine gaps where information is missing or unsupported.\n` +
                `- Do NOT flag gaps that are already addressed in the answer.\n` +
                `- Each follow-up query must be materially different from the others.\n` +
                `- If the answer is complete and well-supported, return an empty array [].\n\n` +
                `Return a JSON array of up to ${maxGaps} concise follow-up search queries that would fill the gaps. ` +
                `Return ONLY the JSON array, no explanation.`
            ),
        ];

        const response = await model.sendRequest(prompt, {});
        let rawText = '';
        for await (const part of response.text) { rawText += part; }

        // Strip markdown code fences
        rawText = rawText.replace(/```json\n?/g, '').replace(/```/g, '').trim();

        const gaps = JSON.parse(rawText);
        if (Array.isArray(gaps) && gaps.every(g => typeof g === 'string')) {
            return gaps.slice(0, maxGaps);
        }
        return [];
    } catch (err) {
        // Graceful fallback — no gaps detected
        return [];
    }
}

module.exports = { analyzeGaps };
