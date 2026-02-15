const { runCliJson, getWorkspaceRoot } = require('../lib/kts_backend');

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function buildStatusReportHtml(statusData) {
  const prettyJson = escapeHtml(JSON.stringify(statusData, null, 2));
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>KTS Status Report</title>
  <style>
    body { font-family: var(--vscode-font-family); padding: 16px; color: var(--vscode-foreground); }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(140px, 1fr)); gap: 8px; margin-bottom: 12px; }
    .card { border: 1px solid var(--vscode-editorWidget-border); border-radius: 6px; padding: 10px; }
    .label { font-size: 12px; opacity: 0.8; }
    .value { font-size: 18px; font-weight: 600; }
    pre { background: var(--vscode-editor-background); border: 1px solid var(--vscode-editorWidget-border); border-radius: 6px; padding: 12px; overflow: auto; }
  </style>
</head>
<body>
  <h2>KTS Status Report</h2>
  <div class="grid">
    <div class="card"><div class="label">Documents</div><div class="value">${escapeHtml(statusData.documents ?? 0)}</div></div>
    <div class="card"><div class="label">Manifest Files</div><div class="value">${escapeHtml(statusData.manifest_files ?? 0)}</div></div>
    <div class="card"><div class="label">Graph Nodes</div><div class="value">${escapeHtml(statusData.graph_nodes ?? 0)}</div></div>
    <div class="card"><div class="label">Graph Edges</div><div class="value">${escapeHtml(statusData.graph_edges ?? 0)}</div></div>
  </div>
  <h3>Raw JSON</h3>
  <pre>${prettyJson}</pre>
</body>
</html>`;
}

async function openStatusReportPanel({ vscode, workspaceRoot, sourcePath, runCli = runCliJson, statusData = null } = {}) {
  const root = getWorkspaceRoot(workspaceRoot);
  const status = statusData || (await runCli({ workspaceRoot: root, sourcePath, args: ['status'] }));

  const panel = vscode.window.createWebviewPanel(
    'ktsStatusReport',
    'KTS Status Report',
    vscode.ViewColumn.Beside,
    { enableScripts: false }
  );

  panel.webview.html = buildStatusReportHtml(status);
  return status;
}

module.exports = {
  buildStatusReportHtml,
  openStatusReportPanel,
};
