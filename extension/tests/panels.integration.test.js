const test = require('node:test');
const assert = require('node:assert/strict');

const { buildStatusReportHtml, openStatusReportPanel } = require('../panels/status_report');
const { buildImageDescriptionHtml, openImageDescriptionPanel } = require('../panels/image_description');

function createVscodeMock() {
  const panels = [];
  return {
    ViewColumn: { Beside: 2 },
    window: {
      createWebviewPanel: (_id, _title, _column, _options) => {
        const panel = { webview: { html: '' } };
        panels.push(panel);
        return panel;
      },
    },
    _panels: panels,
  };
}

test('status report panel renders key metrics', () => {
  const html = buildStatusReportHtml({ documents: 5, manifest_files: 5, graph_nodes: 12, graph_edges: 20 });
  assert.match(html, /KTS Status Report/);
  assert.match(html, /Documents/);
  assert.match(html, /graph_nodes|Graph Nodes/);
});

test('image description panel renders pending rows', () => {
  const html = buildImageDescriptionHtml({
    count: 1,
    documents: [{ doc_id: 'doc_1', pending_count: 2, described_count: 0 }],
  });
  assert.match(html, /KTS Image Description Queue/);
  assert.match(html, /doc_1/);
  assert.match(html, /Pending/);
});

test('openStatusReportPanel invokes backend and writes webview html', async () => {
  const vscode = createVscodeMock();
  const runCli = async () => ({ documents: 2, manifest_files: 2, graph_nodes: 4, graph_edges: 5 });

  const status = await openStatusReportPanel({
    vscode,
    workspaceRoot: process.cwd(),
    runCli,
  });

  assert.equal(status.documents, 2);
  assert.equal(vscode._panels.length, 1);
  assert.match(vscode._panels[0].webview.html, /KTS Status Report/);
});

test('openImageDescriptionPanel invokes backend and writes webview html', async () => {
  const vscode = createVscodeMock();
  const runCli = async () => ({ count: 1, documents: [{ doc_id: 'doc_9', pending_count: 3, described_count: 1 }] });

  const pending = await openImageDescriptionPanel({
    vscode,
    workspaceRoot: process.cwd(),
    runCli,
  });

  assert.equal(pending.count, 1);
  assert.equal(vscode._panels.length, 1);
  assert.match(vscode._panels[0].webview.html, /doc_9/);
});
