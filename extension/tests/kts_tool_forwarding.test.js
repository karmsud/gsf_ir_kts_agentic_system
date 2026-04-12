/**
 * Phase 17 — kts_tool.js CLI argument forwarding tests.
 *
 * Validates that Phase 17 options (mode, doc-filter, scopes, extra args)
 * are correctly forwarded to the CLI backend.
 *
 * Run:  node --test extension/tests/kts_tool_forwarding.test.js
 */

const { describe, it, beforeEach } = require('node:test');
const assert = require('node:assert/strict');

// We test the arg-building logic without requiring vscode or a real backend.
// Extract the arg-building by importing the module and capturing calls.

let capturedArgs = null;
let capturedWorkspace = null;

// Mock runCliJson before requiring kts_tool
const Module = require('module');
const originalLoad = Module._load;

Module._load = function (request, parent, isMain) {
  if (request === '../lib/kts_backend' || request.endsWith('kts_backend')) {
    return {
      runCliJson: async function (opts) {
        capturedArgs = opts.args;
        capturedWorkspace = opts.workspaceRoot;
        return { mocked: true };
      },
      getWorkspaceRoot: function (override) {
        return override || '/test-workspace';
      }
    };
  }
  // Mock vscode so kts_tool.js doesn't crash
  if (request === 'vscode') {
    return {
      workspace: {
        getConfiguration: () => ({ get: () => '' })
      }
    };
  }
  return originalLoad.apply(this, arguments);
};

// Now require the real kts_tool
const ktsTool = require('../copilot/kts_tool');

describe('ktsTool Phase 17 forwarding', () => {
  beforeEach(() => {
    capturedArgs = null;
    capturedWorkspace = null;
  });

  it('forwards --mode when phase17Mode is set', async () => {
    await ktsTool('test query', { phase17Mode: 'diff' });
    assert.ok(capturedArgs.includes('--mode'));
    assert.ok(capturedArgs.includes('diff'));
  });

  it('forwards --doc-filter when phase17DocFilter set', async () => {
    await ktsTool('test query', { phase17DocFilter: 'PSA' });
    assert.ok(capturedArgs.includes('--doc-filter'));
    assert.ok(capturedArgs.includes('PSA'));
  });

  it('forwards --scopes for multi-scope array', async () => {
    await ktsTool('test query', { phase17Scopes: ['deal1', 'deal2'] });
    assert.ok(capturedArgs.includes('--scopes'));
    assert.ok(capturedArgs.includes('deal1,deal2'));
  });

  it('does not forward --scopes for empty array', async () => {
    await ktsTool('test query', { phase17Scopes: [] });
    assert.ok(!capturedArgs.includes('--scopes'));
  });

  it('forwards phase17ExtraCliArgs', async () => {
    await ktsTool('test query', { phase17ExtraCliArgs: ['--extra', 'value'] });
    assert.ok(capturedArgs.includes('--extra'));
    assert.ok(capturedArgs.includes('value'));
  });

  it('combines all Phase 17 opts together', async () => {
    await ktsTool('waterfall provisions', {
      phase17Mode: 'aggregate',
      phase17DocFilter: 'SA',
      phase17Scopes: ['a', 'b', 'c'],
      phase17ExtraCliArgs: ['--verbose']
    });
    assert.ok(capturedArgs.includes('--mode'));
    assert.ok(capturedArgs.includes('aggregate'));
    assert.ok(capturedArgs.includes('--doc-filter'));
    assert.ok(capturedArgs.includes('SA'));
    assert.ok(capturedArgs.includes('--scopes'));
    assert.ok(capturedArgs.includes('a,b,c'));
    assert.ok(capturedArgs.includes('--verbose'));
  });

  it('always includes search command and query', async () => {
    await ktsTool('my question', {});
    assert.equal(capturedArgs[0], 'search');
    assert.equal(capturedArgs[1], 'my question');
  });

  it('returns error for empty query', async () => {
    const result = await ktsTool('', {});
    assert.equal(result.status, 'error');
  });

  it('returns error for null query', async () => {
    const result = await ktsTool(null, {});
    assert.equal(result.status, 'error');
  });

  it('does not forward Phase 17 opts when not provided', async () => {
    await ktsTool('basic query', { deepMode: true });
    assert.ok(!capturedArgs.includes('--mode'));
    assert.ok(!capturedArgs.includes('--doc-filter'));
    assert.ok(!capturedArgs.includes('--scopes'));
    assert.ok(capturedArgs.includes('--deep'));
  });

  it('forwards legacy options alongside Phase 17', async () => {
    await ktsTool('test', {
      deepMode: true,
      docType: 'PSA',
      phase17Mode: 'compare',
      compareScopes: ['x', 'y'],
    });
    assert.ok(capturedArgs.includes('--deep'));
    assert.ok(capturedArgs.includes('--doc-type'));
    assert.ok(capturedArgs.includes('--compare-scopes'));
    assert.ok(capturedArgs.includes('--mode'));
    assert.ok(capturedArgs.includes('compare'));
  });
});
