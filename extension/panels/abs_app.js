/**
 * abs_app.js — ABS Waterfall WebView controller.
 *
 * Responsibilities:
 *   1. Spawn / manage the Python backend IPC server (`abs-serve`).
 *   2. Create the WebView panel (Apple-style SPA) with a strict CSP.
 *   3. Route WebView `command` messages → backend dispatcher and stream
 *      `progress` / `result` back.
 *   4. Bridge backend `llm_request` messages → GitHub Copilot (VS Code LM API)
 *      and return `llm_response`.
 *   5. Handle native affordances: pick PDF, prompt deal id, open files/logs,
 *      and inject pre-made prompts into the GHCP chat.
 *
 * Every action is logged to the "ABS Waterfall" output channel — the
 * traceability backbone.
 */

'use strict';

const vscode = require('vscode');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

let panel = null;
let backend = null; // { proc, sendLine }
let outputChannel = null;

function log(message) {
  if (!outputChannel) outputChannel = vscode.window.createOutputChannel('ABS Waterfall');
  const ts = new Date().toISOString();
  outputChannel.appendLine(`[${ts}] ${message}`);
}

// ── Deal folder resolution ────────────────────────────────────────────────
function dealsRoot() {
  const folders = vscode.workspace.workspaceFolders;
  if (folders && folders.length) return folders[0].uri.fsPath;
  return path.join(require('os').homedir(), 'ABS_Deals');
}

// ── Backend process (JSON-lines IPC) ──────────────────────────────────────
function startBackend(context, onMessage) {
  const root = dealsRoot();
  fs.mkdirSync(root, { recursive: true });

  // Production: bundled frozen executable. Development: module entry.
  const exe = locateBackendExe(context);
  let proc;
  if (exe) {
    log(`Starting backend (frozen): ${exe}`);
    proc = spawn(exe, ['abs-serve', '--deals-root', root], { cwd: context.extensionPath });
  } else {
    const py = process.env.ABS_PYTHON || 'python3';
    const repoRoot = path.resolve(context.extensionPath, '..');
    log(`Starting backend (dev): ${py} -m backend.abs.serve`);
    proc = spawn(py, ['-m', 'backend.abs.serve', '--deals-root', root], { cwd: repoRoot });
  }

  let buffer = '';
  proc.stdout.on('data', (data) => {
    buffer += data.toString('utf8');
    let idx;
    while ((idx = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 1);
      if (!line) continue;
      try { onMessage(JSON.parse(line)); }
      catch (e) { log(`Bad backend line: ${line.slice(0, 160)}`); }
    }
  });
  proc.stderr.on('data', (d) => log(`[backend stderr] ${d.toString('utf8').trim()}`));
  proc.on('exit', (code) => log(`Backend exited (code ${code})`));

  const sendLine = (obj) => {
    try { proc.stdin.write(JSON.stringify(obj) + '\n'); }
    catch (e) { log(`Failed to write to backend: ${e.message}`); }
  };
  return { proc, sendLine, root };
}

function locateBackendExe(context) {
  const plats = Array.from(new Set([
    `${process.platform}-${process.arch}`,
    process.platform === 'darwin' ? `macos-${process.arch}` : null,
    process.platform === 'win32' ? `win-${process.arch}` : null,
    'darwin-arm64',
    'darwin-x64',
    'macos-arm64',
    'macos-x64',
    'win32-x64',
    'win-x64',
    'linux-x64',
  ].filter(Boolean)));
  const exeName = process.platform === 'win32' ? '.exe' : '';
  // The bundled PyInstaller binary is named "kts-backend" (shared backend);
  // "abs-backend" is accepted as a future alias.
  for (const p of plats) {
    for (const base of ['kts-backend', 'abs-backend']) {
      const candidate = path.join(context.extensionPath, 'bin', p, base, base + exeName);
      if (fs.existsSync(candidate)) return candidate;
    }
  }
  return null;
}

// ── LLM bridge → GitHub Copilot ───────────────────────────────────────────
async function fulfillLLM(req) {
  try {
    // Prefer Claude Haiku 4.5 for bulk backend operations (definition resolution, Q&A etc.).
    // Try all Haiku family aliases before falling back to any GPT model.
    const PREFERRED_FAMILIES = ['claude-haiku-4-5', 'claude-3-5-haiku', 'claude-haiku', 'gpt-4o-mini', 'claude-sonnet-4'];
    let model = null;
    for (const family of PREFERRED_FAMILIES) {
      const hits = await vscode.lm.selectChatModels({ vendor: 'copilot', family });
      if (hits && hits.length) { model = hits[0]; break; }
    }
    if (!model) {
      const all = await vscode.lm.selectChatModels({ vendor: 'copilot' });
      if (!all || !all.length) {
        return { llm_id: req.llm_id, text: '', model: 'none', error: 'No Copilot model available. Please sign in to GitHub Copilot.' };
      }
      model = all[0];
    }
    const messages = [];
    if (req.system_prompt) messages.push(vscode.LanguageModelChatMessage.User('SYSTEM: ' + req.system_prompt));
    messages.push(vscode.LanguageModelChatMessage.User(req.prompt));
    log(`LLM request ${req.llm_id} → ${model.id} (${(req.prompt || '').length} chars)`);
    const resp = await model.sendRequest(messages, {}, new vscode.CancellationTokenSource().token);
    let text = '';
    for await (const frag of resp.text) text += frag;
    log(`LLM response ${req.llm_id} ← ${text.length} chars`);
    return { llm_id: req.llm_id, text, model: model.id, input_tokens: 0, output_tokens: 0 };
  } catch (e) {
    log(`LLM error ${req.llm_id}: ${e.message}`);
    return { llm_id: req.llm_id, text: '', model: 'error', error: String(e.message || e) };
  }
}

// ── WebView messages ──────────────────────────────────────────────────────
async function handleWebviewMessage(context, msg) {
  switch (msg.type) {
    case 'ready':
      panel.webview.postMessage({ type: 'init', dealsRoot: backend.root });
      return;
    case 'command':
      log(`command ${msg.id}: ${msg.command}`);
      backend.sendLine({ type: 'command', id: msg.id, command: msg.command, params: msg.params });
      return;
    case 'pickPdf': {
      const picked = await vscode.window.showOpenDialog({
        canSelectMany: false, openLabel: 'Ingest',
        filters: { 'Documents': ['pdf', 'PDF'] },
      });
      panel.webview.postMessage({ type: 'extResult', id: msg.id, result: picked && picked.length ? picked[0].fsPath : null });
      return;
    }
    case 'pickCsv': {
      const picked = await vscode.window.showOpenDialog({
        canSelectMany: false, openLabel: 'Select Monthly CSV',
        filters: { 'CSV Files': ['csv'] },
      });
      panel.webview.postMessage({ type: 'extResult', id: msg.id, result: picked && picked.length ? picked[0].fsPath : null });
      return;
    }
    case 'promptDealId': {
      const id = await vscode.window.showInputBox({ prompt: 'New deal id (folder name)', placeHolder: 'cbass_2002_cb4' });
      panel.webview.postMessage({ type: 'extResult', id: msg.id, result: id ? id.trim().replace(/\s+/g, '_') : null });
      return;
    }
    case 'openLogs':
      if (outputChannel) outputChannel.show(true);
      return;
    case 'openFile':
      if (msg.path && fs.existsSync(msg.path)) vscode.commands.executeCommand('vscode.open', vscode.Uri.file(msg.path));
      return;
    case 'revealCitation':
      vscode.window.showInformationMessage(`Source: ${msg.citation}`);
      return;
    case 'askCopilot': {
      const query = `@abs /explain (deal ${msg.deal_id}) ${msg.prompt}`;
      vscode.commands.executeCommand('workbench.action.chat.open', { query }).then(undefined, () => {
        vscode.window.showInformationMessage('Open the Chat view and ask @abs: ' + msg.prompt);
      });
      return;
    }
    default:
      log(`Unknown webview message: ${msg.type}`);
  }
}

// ── Backend → WebView routing ─────────────────────────────────────────────
function onBackendMessage(msg) {
  if (msg.type === 'llm_request') {
    fulfillLLM(msg).then((resp) => backend.sendLine({ type: 'llm_response', ...resp }));
  } else if (msg.type === 'progress') {
    if (panel) panel.webview.postMessage({ type: 'progress', id: msg.id, event: msg.event });
  } else if (msg.type === 'result') {
    if (panel) panel.webview.postMessage({ type: 'result', id: msg.id, result: msg.result });
  } else if (msg.type === 'ready') {
    log('Backend reports ready.');
  } else if (msg.type === 'log') {
    log(`[backend] ${msg.level}: ${msg.message}`);
  }
}

// ── HTML ──────────────────────────────────────────────────────────────────
function getHtml(webview, context) {
  const nonce = String(Math.random()).slice(2);
  const cssUri = webview.asWebviewUri(vscode.Uri.file(path.join(context.extensionPath, 'media', 'abs', 'app.css')));
  const jsUri = webview.asWebviewUri(vscode.Uri.file(path.join(context.extensionPath, 'media', 'abs', 'app.js')));
  const csp = `default-src 'none'; img-src ${webview.cspSource} https: data:; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';`;
  return `<!DOCTYPE html><html lang="en"><head>
    <meta charset="UTF-8"/>
    <meta http-equiv="Content-Security-Policy" content="${csp}"/>
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <link rel="stylesheet" href="${cssUri}"/>
    <title>ABS Waterfall</title></head>
    <body><div id="app" class="app"></div>
    <script nonce="${nonce}" src="${jsUri}"></script></body></html>`;
}

// ── Entry point ───────────────────────────────────────────────────────────
async function openAbsApp(context) {
  log('Opening ABS Waterfall…');
  if (panel) { panel.reveal(vscode.ViewColumn.One); return; }

  panel = vscode.window.createWebviewPanel('absWaterfall', 'ABS Waterfall', vscode.ViewColumn.One, {
    enableScripts: true, retainContextWhenHidden: true,
    localResourceRoots: [vscode.Uri.file(path.join(context.extensionPath, 'media'))],
  });
  panel.webview.html = getHtml(panel.webview, context);

  // Show the ABS Waterfall log channel so users can follow pipeline progress.
  if (!outputChannel) outputChannel = vscode.window.createOutputChannel('ABS Waterfall');
  outputChannel.show(true);

  if (!backend) backend = startBackend(context, onBackendMessage);

  panel.webview.onDidReceiveMessage((msg) => handleWebviewMessage(context, msg));
  panel.onDidDispose(() => {
    panel = null;
    if (backend && backend.proc) { try { backend.proc.kill(); } catch (e) {} backend = null; }
  });

  // Preflight: warn if Copilot is unavailable (the LLM layer).
  try {
    const models = await vscode.lm.selectChatModels({ vendor: 'copilot' });
    if (!models || !models.length) {
      vscode.window.showWarningMessage('ABS Waterfall: GitHub Copilot is required for AI features. Please sign in.');
    }
  } catch (e) { /* LM API may be unavailable in older VS Code */ }
}

module.exports = { openAbsApp };
