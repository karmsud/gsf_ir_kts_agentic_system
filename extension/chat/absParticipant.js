/**
 * absParticipant.js — Register the @abs chat participant.
 *
 * Called from extension.js activate() alongside registerChatParticipant().
 * Pattern mirrors the existing @kts registration in chat/participant.js.
 */

'use strict';

const { handleABSRequest } = require('./absRequestHandler');
const { provideABSFollowups } = require('./absFollowups');

/**
 * Register the @abs chat participant with VS Code.
 *
 * @param {typeof import('vscode')} vscode
 * @param {import('vscode').ExtensionContext} context
 * @param {object} shared  - shared state from extension.js (outputChannel, etc.)
 */
function registerABSParticipant(vscode, context, shared) {
    try {
        const participant = vscode.chat.createChatParticipant(
            'abs.assistant',
            (request, ctx, stream, token) =>
                handleABSRequest(vscode, request, ctx, stream, token, shared),
        );

        // Icon — falls back gracefully if file doesn't exist
        try {
            const path = require('path');
            participant.iconPath = vscode.Uri.joinPath(
                context.extensionUri,
                'media',
                'abs-icon.svg',
            );
        } catch (_) {
            // Icon is cosmetic — ignore if missing
        }

        participant.followupProvider = {
            provideFollowups: (result, ctx, token) =>
                provideABSFollowups(result, ctx, token),
        };

        context.subscriptions.push(participant);

        if (shared && shared.outputChannel) {
            shared.outputChannel.appendLine('[ABS] @abs chat participant registered');
        }
    } catch (err) {
        // createChatParticipant may be unavailable in older VS Code builds
        if (shared && shared.outputChannel) {
            shared.outputChannel.appendLine(
                `[ABS] Warning: could not register @abs chat participant: ${err.message}`,
            );
        }
    }
}

module.exports = { registerABSParticipant };
