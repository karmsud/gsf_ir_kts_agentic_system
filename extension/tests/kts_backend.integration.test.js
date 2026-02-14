const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');

const { runCliJson } = require('../lib/kts_backend');
const ktsTool = require('../copilot/kts_tool');

const workspaceRoot = path.resolve(__dirname, '..', '..');
const fixturesPath = path.join('tests', 'fixtures', 'simple');

test('extension backend bridge returns real status payload', async () => {
  const status = await runCliJson({
    workspaceRoot,
    args: ['status'],
  });

  assert.equal(typeof status, 'object');
  assert.equal(typeof status.documents, 'number');
  assert.equal(typeof status.graph_nodes, 'number');
});

test('@kts bridge executes real retrieval search', async () => {
  await runCliJson({ workspaceRoot, args: ['ingest', '--paths', fixturesPath] });

  const result = await ktsTool('How do I reset password in ToolX?', {
    workspaceRoot,
    maxResults: 3,
  });

  assert.equal(result.tool, '@kts');
  assert.equal(result.status, 'ok');
  assert.ok(result.search_result);
  assert.ok(Array.isArray(result.search_result.context_chunks));
  assert.ok(Array.isArray(result.search_result.citations));
  assert.ok(result.search_result.context_chunks.length >= 1);
});
