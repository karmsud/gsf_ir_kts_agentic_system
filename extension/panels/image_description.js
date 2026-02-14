const { runCliJson, getWorkspaceRoot } = require('../lib/kts_backend');

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function buildImageDescriptionHtml(pendingData) {
  const documents = Array.isArray(pendingData.documents) ? pendingData.documents : [];
  const rows = documents
    .map((doc) => {
      const pendingCount = doc.pending_count ?? 0;
      const describedCount = doc.described_count ?? 0;
      return `<tr><td>${escapeHtml(doc.doc_id)}</td><td>${escapeHtml(pendingCount)}</td><td>${escapeHtml(describedCount)}</td></tr>`;
    })
    .join('');

  const table = documents.length
    ? `<table><thead><tr><th>Document</th><th>Pending</th><th>Described</th></tr></thead><tbody>${rows}</tbody></table>`
    : '<p>No pending image descriptions.</p>';

  const prettyJson = escapeHtml(JSON.stringify(pendingData, null, 2));
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>KTS Image Description</title>
  <style>
    body { font-family: var(--vscode-font-family); padding: 16px; color: var(--vscode-foreground); }
    table { border-collapse: collapse; width: 100%; margin-top: 8px; }
    th, td { border: 1px solid var(--vscode-editorWidget-border); text-align: left; padding: 8px; }
    th { background: var(--vscode-editor-background); }
    pre { margin-top: 12px; background: var(--vscode-editor-background); border: 1px solid var(--vscode-editorWidget-border); border-radius: 6px; padding: 10px; overflow: auto; }
  </style>
</head>
<body>
  <h2>KTS Image Description Queue</h2>
  <p>Documents with pending image descriptions: <strong>${escapeHtml(pendingData.count ?? 0)}</strong></p>
  <p><a href="command:kts.imageDescriptionComplete">Complete Descriptions</a></p>
  ${table}
  <h3>Raw JSON</h3>
  <pre>${prettyJson}</pre>
</body>
</html>`;
}

async function openImageDescriptionPanel({ vscode, workspaceRoot, runCli = runCliJson, pendingData = null } = {}) {
  const root = getWorkspaceRoot(workspaceRoot);
  const pending = pendingData || (await runCli({ workspaceRoot: root, args: ['describe', 'pending'] }));

  const panel = vscode.window.createWebviewPanel(
    'ktsImageDescription',
    'KTS Image Description',
    vscode.ViewColumn.Beside,
    { enableScripts: false, enableCommandUris: true }
  );

  panel.webview.html = buildImageDescriptionHtml(pending);
  return pending;
}

module.exports = {
  buildImageDescriptionHtml,
  openImageDescriptionPanel,
};
