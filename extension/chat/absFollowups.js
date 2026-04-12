/**
 * absFollowups.js — Provide contextual follow-up suggestions after @abs responses.
 *
 * VS Code calls provideFollowups() after each @abs response to show
 * suggested next actions in the chat UI.
 */

'use strict';

/**
 * Provide follow-up suggestions based on the result of the last @abs command.
 *
 * @param {import('vscode').ChatResult} result
 * @param {import('vscode').ChatContext} _context
 * @param {import('vscode').CancellationToken} _token
 * @returns {import('vscode').ChatFollowup[]}
 */
function provideABSFollowups(result, _context, _token) {
    const meta = (result && result.metadata) || {};
    const cmd = meta.command;

    if (meta.error) {
        return [
            { prompt: '@abs /status', label: 'Check Deal Status' },
        ];
    }

    switch (cmd) {
        case 'ingest':
            return [
                { prompt: `@abs /generate`, label: 'Generate Payment Model' },
                { prompt: '@abs /status', label: 'Check Status' },
                {
                    prompt: meta.dealId
                        ? `@abs What is the Distribution Waterfall for ${meta.dealId}?`
                        : '@abs What is the Distribution Waterfall?',
                    label: 'View Waterfall',
                },
            ];

        case 'generate':
            return [
                { prompt: `@abs /audit`, label: 'Audit Generated Model' },
                {
                    prompt: meta.dealId
                        ? `@abs What are the waterfall rules for ${meta.dealId}?`
                        : '@abs What are the waterfall rules?',
                    label: 'Review Waterfall Rules',
                },
            ];

        case 'audit':
            return [
                { prompt: '@abs /generate', label: 'Regenerate Model' },
                {
                    prompt: meta.dealId
                        ? `@abs What are the triggers for ${meta.dealId}?`
                        : '@abs What are the triggers?',
                    label: 'Review Event Triggers',
                },
            ];

        case 'status':
            return [
                { prompt: '@abs /ingest', label: 'Ingest a Deal' },
            ];

        case 'qa':
            return [
                { prompt: '@abs /status', label: 'Deal Status' },
                {
                    prompt: meta.dealId
                        ? `@abs What are the key parties for ${meta.dealId}?`
                        : '@abs What are the key parties?',
                    label: 'Key Parties',
                },
            ];

        default:
            return [
                { prompt: '@abs /status', label: 'Deal Status' },
                { prompt: '@abs What is the Distribution Waterfall?', label: 'Waterfall' },
                { prompt: '@abs What are the triggers?', label: 'Triggers' },
            ];
    }
}

module.exports = { provideABSFollowups };
