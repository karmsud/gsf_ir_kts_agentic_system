/**
 * absRequestHandler.js — Main request router for the @abs chat participant.
 *
 * Routes slash commands (/ingest, /generate, /audit, /status) and free-text
 * Q&A to the appropriate Python CLI subprocess via the shared KTS IPC layer.
 */

'use strict';

// ─── Session State ────────────────────────────────────────────────────────────
/** @type {{ activeDealId: string|null, lastQuery: string|null, ingestStatus: string, modelGenerated: boolean, lastModelPath: string|null }} */
const sessionState = {
    activeDealId: null,
    lastQuery: null,
    ingestStatus: 'not-started',
    modelGenerated: false,
    lastModelPath: null,
};

// ─── Main Router ─────────────────────────────────────────────────────────────

/**
 * Handle an @abs chat request.
 *
 * @param {typeof import('vscode')} vscode
 * @param {import('vscode').ChatRequest} request
 * @param {import('vscode').ChatContext} context
 * @param {import('vscode').ChatResponseStream} stream
 * @param {import('vscode').CancellationToken} token
 * @param {object} shared  - extension shared state (outputChannel, runAbsStreaming, etc.)
 * @returns {Promise<import('vscode').ChatResult>}
 */
async function handleABSRequest(vscode, request, context, stream, token, shared) {
    const prompt = (request.prompt || '').trim();
    const command = request.command || null;

    const dealId = detectDealId(vscode, prompt, context) || sessionState.activeDealId;

    try {
        switch (command) {
            case 'ingest':
                return await cmdIngest(vscode, dealId, prompt, stream, token, shared);
            case 'generate':
                return await cmdGenerate(vscode, dealId, stream, token, shared);
            case 'audit':
                return await cmdAudit(vscode, dealId, stream, token, shared);
            case 'status':
                return await cmdStatus(vscode, dealId, stream, token, shared);
            default:
                return await cmdQA(vscode, dealId, prompt, stream, token, shared);
        }
    } catch (err) {
        stream.markdown(`\n⚠️ **Error:** ${err.message}\n`);
        if (shared && shared.outputChannel) {
            shared.outputChannel.appendLine(`[ABS] Error in handleABSRequest: ${err.message}`);
        }
        return { metadata: { error: true } };
    }
}

// ─── /ingest ─────────────────────────────────────────────────────────────────

async function cmdIngest(vscode, dealId, prompt, stream, token, shared) {
    if (!dealId) {
        stream.markdown(
            'Please specify a deal ID: `@abs /ingest bear_stearns_2006_he1`\n\n' +
            'The deal ID should match the folder name in your deals directory.',
        );
        return { metadata: { command: 'ingest', error: true } };
    }

    sessionState.activeDealId = dealId;
    sessionState.ingestStatus = 'in-progress';
    stream.markdown(`📁 **Ingesting ${dealId}**\n\n`);

    await runAbsProcess(
        vscode,
        ['abs', 'ingest', '--deal-id', dealId, '--llm-mode', 'vscode', '--verbose'],
        stream, token, shared,
        {
            onProgress: (msg) => stream.progress(msg.message || `${msg.step || 'processing'}: ${msg.status || ''}`),
            onResult: (msg) => {
                stream.markdown(
                    `\n**Ingestion Summary:**\n\n| Metric | Value |\n|--------|-------|\n` +
                    `| Items | ${msg.item_count || 0} |\n` +
                    `| Sections | ${msg.section_count || 0} |\n` +
                    `| Graph Nodes | ${msg.node_count || 0} |\n` +
                    `| Graph Edges | ${msg.edge_count || 0} |\n`,
                );
                sessionState.ingestStatus = 'complete';
            },
        },
    );

    return { metadata: { command: 'ingest', dealId } };
}

// ─── /generate ───────────────────────────────────────────────────────────────

async function cmdGenerate(vscode, dealId, stream, token, shared) {
    if (!dealId) {
        stream.markdown(
            'Please specify a deal ID: `@abs /generate bear_stearns_2006_he1`\n\n' +
            'Make sure the deal has been ingested first.',
        );
        return { metadata: { command: 'generate', error: true } };
    }

    stream.markdown(`⚙️ **Generating Payment Model for ${dealId}**\n\n`);

    let modelPath = null;

    await runAbsProcess(
        vscode,
        ['abs', 'generate', '--deal-id', dealId, '--llm-mode', 'vscode', '--verbose'],
        stream, token, shared,
        {
            onProgress: (msg) => stream.progress(msg.message || msg.step || '...'),
            onCode: (msg) => stream.markdown(`\n\`\`\`python\n${msg.code}\n\`\`\`\n`),
            onResult: (msg) => {
                stream.markdown(`\n**Generation Complete**\n`);
                if (msg.output_path) {
                    stream.markdown(`- Output: \`${msg.output_path}\`\n`);
                    modelPath = msg.output_path;
                    sessionState.lastModelPath = msg.output_path;
                }
                if (msg.quality_score != null) stream.markdown(`- Quality Score: ${msg.quality_score}\n`);
                if (msg.validation) stream.markdown(`- Validation: ${msg.validation}\n`);
                sessionState.modelGenerated = true;
            },
        },
    );

    // Read and display the generated model code inline
    if (modelPath) {
        try {
            const fileUri = vscode.Uri.file(modelPath);
            const fileBytes = await vscode.workspace.fs.readFile(fileUri);
            const code = Buffer.from(fileBytes).toString('utf8');
            stream.markdown(`\n**Generated \`payment_model.py\`:**\n\n\`\`\`python\n${code}\n\`\`\`\n`);
            stream.button({
                command: 'vscode.open',
                arguments: [fileUri],
                title: '📄 Open in Editor',
            });
        } catch (_) {
            // Button API may not be available in older VS Code; skip inline display
        }
    }

    return { metadata: { command: 'generate', dealId } };
}

// ─── /audit ──────────────────────────────────────────────────────────────────

async function cmdAudit(vscode, dealId, stream, token, shared) {
    if (!dealId) {
        stream.markdown(
            'Please specify a deal ID: `@abs /audit bear_stearns_2006_he1`',
        );
        return { metadata: { command: 'audit', error: true } };
    }

    stream.markdown(`🔍 **Auditing ${dealId}**\n\n`);

    await runAbsProcess(
        vscode,
        ['abs', 'audit', '--deal-id', dealId, '--llm-mode', 'vscode'],
        stream, token, shared,
        {
            onProgress: (msg) => stream.progress(msg.message || msg.step || '...'),
            onResult: (msg) => {
                stream.markdown(msg.report || '*(No audit report returned)*');
                if (msg.confidence != null) stream.markdown(`\n\n**Audit Confidence:** ${msg.confidence}\n`);
            },
        },
    );

    return { metadata: { command: 'audit', dealId } };
}

// ─── /status ─────────────────────────────────────────────────────────────────

async function cmdStatus(vscode, dealId, stream, token, shared) {
    const args = dealId
        ? ['abs', 'status', '--deal-id', dealId]
        : ['abs', 'status'];

    stream.markdown(`📊 **ABS Deal Status**\n\n`);

    await runAbsProcess(vscode, args, stream, token, shared, {
        onResult: (msg) => stream.markdown(msg.status_report || '*(No status returned)*'),
    });

    return { metadata: { command: 'status', dealId } };
}

// ─── Free Text Q&A ────────────────────────────────────────────────────────────

async function cmdQA(vscode, dealId, query, stream, token, shared) {
    if (!dealId || !query) {
        stream.markdown(
            'Please specify a deal and question:\n' +
            '```\n@abs What is the Distribution Waterfall?\n```\n\n' +
            'Or ingest a deal first: `@abs /ingest <deal_id>`',
        );
        return { metadata: { command: 'qa', error: true } };
    }

    await runAbsProcess(
        vscode,
        ['abs', 'qa', '--deal-id', dealId, '--query', query, '--llm-mode', 'vscode', '--verbose'],
        stream, token, shared,
        {
            onStream: (msg) => stream.markdown(msg.text || ''),
            onResult: (msg) => {
                stream.markdown(msg.answer || '*(No answer returned)*');
                if (msg.sources && msg.sources.length > 0) {
                    stream.markdown('\n\n*Sources:*\n');
                    for (const src of msg.sources) stream.markdown(`- ${src}\n`);
                }
                if (msg.confidence != null) stream.markdown(`\n*Confidence: ${msg.confidence}*\n`);
            },
        },
    );

    sessionState.lastQuery = query;
    return { metadata: { command: 'qa', dealId } };
}

// ─── Core Backend Runner ──────────────────────────────────────────────────────

/**
 * Run an ABS CLI command using the streaming IPC layer.
 *
 * Handles LLM IPC round-trips (llm_request → vscode.lm → llm_response to stdin),
 * live progress, markdown, code, stream, and result messages.
 *
 * Falls back to shared.runCli (non-streaming, no LLM IPC) if runAbsStreaming
 * is not present in shared.
 *
 * @param {typeof import('vscode')} vscode
 * @param {string[]} args
 * @param {import('vscode').ChatResponseStream} stream
 * @param {import('vscode').CancellationToken} token
 * @param {object} shared
 * @param {{ onProgress?, onResult?, onCode?, onStream? }} handlers
 */
async function runAbsProcess(vscode, args, stream, token, shared, handlers = {}) {
    const { onProgress, onResult, onCode, onStream } = handlers;

    // ── Primary: streaming path with LLM IPC support ───────────────────────
    if (shared && shared.runAbsStreaming) {
        const model = await selectVSCodeModel(vscode, null);

        try {
            await shared.runAbsStreaming({
                args,
                onLine: (msg, writeToStdin) => {
                    if (token.isCancellationRequested) return;
                    switch (msg.type) {
                        case 'progress':
                            if (onProgress) onProgress(msg);
                            else stream.progress(msg.message || msg.step || '...');
                            break;
                        case 'markdown':
                            stream.markdown(msg.text || '');
                            break;
                        case 'code':
                            if (onCode) onCode(msg);
                            else stream.markdown(`\n\`\`\`python\n${msg.code}\n\`\`\`\n`);
                            break;
                        case 'stream':
                            if (onStream) onStream(msg);
                            else stream.markdown(msg.text || '');
                            break;
                        case 'result':
                            if (onResult) onResult(msg);
                            break;
                        case 'error':
                            stream.markdown(`\n⚠️ ${msg.message || 'Backend error'}\n`);
                            break;
                        case 'llm_request':
                            // LLM IPC round-trip — async; Python waits for llm_response on stdin
                            _handleLLMRequest(vscode, msg, model, writeToStdin, shared).catch((e) => {
                                if (shared.outputChannel) {
                                    shared.outputChannel.appendLine(`[ABS] LLM request failed: ${e.message}`);
                                }
                                writeToStdin({ type: 'llm_response', text: '', error: e.message });
                            });
                            break;
                        case 'text':
                            if (shared.outputChannel) shared.outputChannel.appendLine(`[ABS] ${msg.text}`);
                            break;
                        default:
                            break;
                    }
                },
                abortSignal: {
                    addEventListener: (_event, fn) => token.onCancellationRequested(fn),
                },
            });
        } catch (err) {
            stream.markdown(`\n⚠️ Backend error: ${err.message}\n`);
            if (shared.outputChannel) {
                shared.outputChannel.appendLine(`[ABS] runAbsStreaming error: ${err.message}`);
            }
        }
        return;
    }

    // ── Fallback: non-streaming via shared.runCli ──────────────────────────
    const runFn = shared && (shared.runCli || shared.runCliJson);
    if (!runFn) {
        stream.markdown(`\n> *(Backend IPC not available — run \`kts ${args.join(' ')}\` in terminal)*\n`);
        return;
    }

    try {
        const result = await runFn({ args, timeoutMs: 3600000 });
        if (result && onResult) onResult({ type: 'result', ...result });
    } catch (err) {
        stream.markdown(`\n⚠️ Backend error: ${err.message}\n`);
        if (shared.outputChannel) shared.outputChannel.appendLine(`[ABS] Backend error: ${err.message}`);
    }
}

// ─── LLM IPC Handler ─────────────────────────────────────────────────────────

/**
 * Handle one llm_request from the Python backend.
 * Calls vscode.lm model.sendRequest(), collects the streamed text,
 * and writes an llm_response JSON line back to backend stdin.
 */
async function _handleLLMRequest(vscode, req, model, writeToStdin, shared) {
    if (!model) {
        writeToStdin({ type: 'llm_response', text: '', error: 'No VS Code Copilot model available' });
        return;
    }

    const messages = [];
    if (req.system_prompt) {
        messages.push(vscode.LanguageModelChatMessage.Assistant(req.system_prompt));
    }
    messages.push(vscode.LanguageModelChatMessage.User(req.prompt || ''));

    try {
        const cts = new vscode.CancellationTokenSource();
        const response = await model.sendRequest(
            messages,
            { temperature: req.temperature ?? 0.0 },
            cts.token,
        );

        let text = '';
        for await (const chunk of response.text) {
            text += chunk;
        }

        writeToStdin({
            type: 'llm_response',
            text,
            input_tokens: messages.reduce((n, m) => n + (m.content || '').length, 0) / 4,
            output_tokens: text.length / 4,
        });
    } catch (err) {
        if (shared && shared.outputChannel) {
            shared.outputChannel.appendLine(`[ABS] vscode.lm.sendRequest failed: ${err.message}`);
        }
        writeToStdin({ type: 'llm_response', text: '', error: err.message });
    }
}

// ─── VS Code Model Selection ─────────────────────────────────────────────────

/**
 * Select best available VS Code Copilot model.
 * Mirrors the selectModel() strategy used by @kts (participant.js).
 */
async function selectVSCodeModel(vscode, requestModel) {
    if (requestModel && typeof requestModel.sendRequest === 'function') return requestModel;

    if (!vscode.lm || typeof vscode.lm.selectChatModels !== 'function') return null;

    try {
        const cfg = vscode.workspace.getConfiguration('kts');
        const modelSetting = cfg.get('model', 'auto');
        if (modelSetting && modelSetting !== 'auto') {
            const models = await vscode.lm.selectChatModels({ family: modelSetting });
            if (models && models.length > 0) return models[0];
        }
    } catch (_) {}

    const families = ['gpt-4.1', 'gpt-4o', 'claude-sonnet-4', 'gpt-4o-mini'];
    for (const family of families) {
        try {
            const models = await vscode.lm.selectChatModels({ vendor: 'copilot', family });
            if (models && models.length > 0) return models[0];
        } catch (_) {}
    }

    try {
        const models = await vscode.lm.selectChatModels({ vendor: 'copilot' });
        if (models && models.length > 0) return models[0];
    } catch (_) {}

    return null;
}

// ─── Deal ID Detection ────────────────────────────────────────────────────────

/**
 * Detect a deal ID from multiple sources, in priority order:
 *  1. Explicit pattern in prompt (e.g. "bear_stearns_2006_he1")
 *  2. Conversation history metadata
 *  3. Active editor file path (checks for deals/<id> segment)
 *  4. Workspace deals/ directory (returns first available deal)
 *
 * @param {typeof import('vscode')} vscode
 * @param {string} prompt
 * @param {import('vscode').ChatContext} context
 * @returns {string|null}
 */
function detectDealId(vscode, prompt, context) {
    // 1. Explicit pattern in prompt
    const match = prompt.match(/\b([a-z][a-z_]*_\d{4}_[a-z0-9]+)\b/i);
    if (match) return match[1].toLowerCase();

    // 2. Conversation history metadata
    if (context && Array.isArray(context.history)) {
        for (let i = context.history.length - 1; i >= 0; i--) {
            const turn = context.history[i];
            if (turn && turn.metadata && turn.metadata.dealId) return turn.metadata.dealId;
        }
    }

    // 3. Active editor file path — look for deals/<deal_id>/ segment
    try {
        const editor = vscode.window.activeTextEditor;
        if (editor) {
            const fsPath = editor.document.uri.fsPath.replace(/\\/g, '/');
            const dealsMatch = fsPath.match(/\/deals\/([a-z][a-z_0-9]*)/i);
            if (dealsMatch) return dealsMatch[1].toLowerCase();
        }
    } catch (_) {}

    // 4. Workspace deals/ directory — first available deal
    try {
        const nodeFsModule = require('fs');
        const nodePath = require('path');
        const folders = vscode.workspace.workspaceFolders;
        if (folders && folders.length > 0) {
            const dealsDir = nodePath.join(folders[0].uri.fsPath, 'deals');
            if (nodeFsModule.existsSync(dealsDir)) {
                const entries = nodeFsModule.readdirSync(dealsDir, { withFileTypes: true });
                const firstDeal = entries.find((e) => e.isDirectory() && !e.name.startsWith('.'));
                if (firstDeal) return firstDeal.name;
            }
        }
    } catch (_) {}

    return null;
}

module.exports = { handleABSRequest };

/** @internal Test-only helper — reset persistent session state between tests. */
module.exports._resetSessionState = function () {
    sessionState.activeDealId = null;
    sessionState.lastQuery = null;
    sessionState.ingestStatus = 'not-started';
    sessionState.modelGenerated = false;
    sessionState.lastModelPath = null;
};
