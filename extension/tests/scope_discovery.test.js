/**
 * Phase 17 — scope_discovery.js unit tests.
 *
 * Covers: slugify, parseCommandTokens, buildCliArgsFromTokens,
 *         buildDynamicCommands, parseTwoLevelScope.
 *
 * Run:  node --test extension/tests/scope_discovery.test.js
 */

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');

// Mock vscode module before requiring extension code
const Module = require('module');
const originalLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'vscode') {
    return {
      workspace: { getConfiguration: () => ({ get: () => '' }) },
      commands: { registerCommand: () => ({ dispose() {} }) },
      window: { showErrorMessage() {}, showInformationMessage() {} },
    };
  }
  return originalLoad.apply(this, arguments);
};

const {
  slugify,
  parseCommandTokens,
  buildCliArgsFromTokens,
  buildDynamicCommands,
  parseTwoLevelScope,
  splitCompoundCommand,
} = require('../lib/scope_discovery');

// ─────────────────────────────────────────────────────────────
// slugify
// ─────────────────────────────────────────────────────────────
describe('slugify', () => {
  it('lowercases and replaces spaces with underscores', () => {
    assert.equal(slugify('Deal 2024 HE1'), 'deal_2024_he1');
  });

  it('replaces hyphens with underscores', () => {
    assert.equal(slugify('my-deal-folder'), 'my_deal_folder');
  });

  it('strips non-alphanumeric/underscore chars', () => {
    assert.equal(slugify('Deal (2024)!'), 'deal_2024');
  });

  it('collapses consecutive underscores', () => {
    assert.equal(slugify('a   b---c'), 'a_b_c');
  });

  it('trims leading/trailing underscores', () => {
    assert.equal(slugify(' _test_ '), 'test');
  });

  it('handles empty string', () => {
    assert.equal(slugify(''), '');
  });
});

// ─────────────────────────────────────────────────────────────
// parseTwoLevelScope (pre-Phase 17 compat)
// ─────────────────────────────────────────────────────────────
describe('parseTwoLevelScope', () => {
  it('parses scope + doc_type + query', () => {
    const r = parseTwoLevelScope('deal1', '/PSA What is the waterfall?');
    assert.equal(r.scope, 'deal1');
    assert.equal(r.doc_type_filter, 'PSA');
    assert.equal(r.query, 'What is the waterfall?');
  });

  it('returns null doc_type when no sub-command', () => {
    const r = parseTwoLevelScope('deal1', 'What is the waterfall?');
    assert.equal(r.scope, 'deal1');
    assert.equal(r.doc_type_filter, null);
    assert.equal(r.query, 'What is the waterfall?');
  });

  it('handles null prompt', () => {
    const r = parseTwoLevelScope('deal1', null);
    assert.equal(r.query, '');
  });
});

// ─────────────────────────────────────────────────────────────
// parseCommandTokens
// ─────────────────────────────────────────────────────────────
describe('parseCommandTokens', () => {
  it('parses mode token from command', () => {
    const r = parseCommandTokens('compare', 'What is the waterfall?');
    assert.equal(r.mode, 'compare');
    assert.equal(r.scopes.length, 0);
    assert.equal(r.query, 'What is the waterfall?');
  });

  it('parses scope slug from command', () => {
    const r = parseCommandTokens('deal_2024_he1', 'What is the waterfall?');
    assert.equal(r.mode, null);
    assert.deepEqual(r.scopes, [
      { slug: 'deal_2024_he1', docFilter: null, isWildcard: false }
    ]);
    assert.equal(r.query, 'What is the waterfall?');
  });

  it('parses mode + scope from prompt', () => {
    const r = parseCommandTokens('diff', '/deal1 /deal2 Show rate differences');
    assert.equal(r.mode, 'diff');
    assert.equal(r.scopes.length, 2);
    assert.equal(r.scopes[0].slug, 'deal1');
    assert.equal(r.scopes[1].slug, 'deal2');
    assert.equal(r.query, 'Show rate differences');
  });

  it('parses scope with doc filter /scope/DOC_TYPE', () => {
    const r = parseCommandTokens('deal1', '/deal1/PSA What is the waterfall?');
    assert.equal(r.scopes.length, 2); // command scope + explicit scope
    assert.equal(r.scopes[1].slug, 'deal1');
    assert.equal(r.scopes[1].docFilter, 'PSA');
  });

  it('parses global doc filter //DOC_TYPE', () => {
    const r = parseCommandTokens('compare', '//PSA /deal1 /deal2 Compare PSA clauses');
    assert.equal(r.mode, 'compare');
    assert.equal(r.globalDocFilter, 'PSA');
    assert.equal(r.scopes.length, 2);
  });

  it('detects wildcard scope', () => {
    const r = parseCommandTokens(null, '/deal* What is the interest rate?');
    assert.equal(r.scopes.length, 1);
    assert.equal(r.scopes[0].slug, 'deal*');
    assert.equal(r.scopes[0].isWildcard, true);
  });

  it('handles null command and null prompt', () => {
    const r = parseCommandTokens(null, null);
    assert.equal(r.mode, null);
    assert.equal(r.scopes.length, 0);
    assert.equal(r.query, '');
  });

  it('handles empty prompt with command', () => {
    const r = parseCommandTokens('deal1', '');
    assert.equal(r.scopes.length, 1);
    assert.equal(r.query, '');
  });

  it('does not duplicate mode token from prompt', () => {
    const r = parseCommandTokens('diff', '/diff /deal1 query');
    // /diff in prompt should NOT override mode since it was already set
    assert.equal(r.mode, 'diff');
  });

  it('handles all six modes', () => {
    for (const mode of ['compare', 'diff', 'aggregate', 'audit', 'define', 'list']) {
      const r = parseCommandTokens(mode, 'test');
      assert.equal(r.mode, mode, `mode ${mode} should be recognized`);
    }
  });
});

// ─────────────────────────────────────────────────────────────
// buildCliArgsFromTokens
// ─────────────────────────────────────────────────────────────
describe('buildCliArgsFromTokens', () => {
  it('returns --mode for mode token', () => {
    const parsed = { mode: 'diff', scopes: [], globalDocFilter: null, query: '' };
    const args = buildCliArgsFromTokens(parsed);
    assert.deepEqual(args, ['--mode', 'diff']);
  });

  it('returns --doc-filter for global doc filter', () => {
    const parsed = { mode: null, scopes: [], globalDocFilter: 'PSA', query: '' };
    const args = buildCliArgsFromTokens(parsed);
    assert.deepEqual(args, ['--doc-filter', 'PSA']);
  });

  it('prefers global doc filter over scope-level', () => {
    const parsed = {
      mode: null,
      scopes: [{ slug: 'deal1', docFilter: 'SA', isWildcard: false }],
      globalDocFilter: 'PSA',
      query: ''
    };
    const args = buildCliArgsFromTokens(parsed);
    assert.ok(args.includes('PSA'));
    assert.ok(!args.includes('SA'));
  });

  it('returns --scopes for multi-scope', () => {
    const parsed = {
      mode: 'compare',
      scopes: [
        { slug: 'deal1', docFilter: null, isWildcard: false },
        { slug: 'deal2', docFilter: null, isWildcard: false }
      ],
      globalDocFilter: null,
      query: ''
    };
    const args = buildCliArgsFromTokens(parsed);
    assert.ok(args.includes('--mode'));
    assert.ok(args.includes('--scopes'));
    assert.ok(args.includes('deal1,deal2'));
  });

  it('returns empty array for no mode/filter/scopes', () => {
    const parsed = { mode: null, scopes: [{ slug: 'x', docFilter: null, isWildcard: false }], globalDocFilter: null, query: '' };
    const args = buildCliArgsFromTokens(parsed);
    assert.deepEqual(args, []);
  });

  it('combines all options', () => {
    const parsed = {
      mode: 'aggregate',
      scopes: [
        { slug: 'a', docFilter: 'PSA', isWildcard: false },
        { slug: 'b', docFilter: null, isWildcard: false }
      ],
      globalDocFilter: null,
      query: ''
    };
    const args = buildCliArgsFromTokens(parsed);
    assert.ok(args.includes('--mode'));
    assert.ok(args.includes('aggregate'));
    assert.ok(args.includes('--doc-filter'));
    assert.ok(args.includes('PSA'));
    assert.ok(args.includes('--scopes'));
    assert.ok(args.includes('a,b'));
  });
});

// ─────────────────────────────────────────────────────────────
// buildDynamicCommands
// ─────────────────────────────────────────────────────────────
describe('buildDynamicCommands', () => {
  it('generates commands for indexed scopes', () => {
    const scopes = [
      { name: 'Deal 1', slug: 'deal_1', indexed: true, docTypes: [] },
      { name: 'Deal 2', slug: 'deal_2', indexed: false, docTypes: [] },
    ];
    const cmds = buildDynamicCommands(scopes);
    assert.equal(cmds.length, 1);
    assert.equal(cmds[0].name, 'deal_1');
  });

  it('generates doc-type sub-commands', () => {
    const scopes = [
      { name: 'Deal 1', slug: 'deal_1', indexed: true, docTypes: ['PSA', 'SA'] },
    ];
    const cmds = buildDynamicCommands(scopes);
    // deal_1 + deal_1_psa + deal_1_sa
    assert.equal(cmds.length, 3);
    assert.equal(cmds[1].name, 'deal_1_psa');
    assert.equal(cmds[2].name, 'deal_1_sa');
  });

  it('returns empty for no scopes', () => {
    assert.deepEqual(buildDynamicCommands([]), []);
  });

  it('skips scopes with empty slug', () => {
    const scopes = [{ name: '', slug: '', indexed: true, docTypes: [] }];
    assert.deepEqual(buildDynamicCommands(scopes), []);
  });
});

// ─────────────────────────────────────────────────────────────
// splitCompoundCommand (Phase 18)
// ─────────────────────────────────────────────────────────────
describe('splitCompoundCommand', () => {
  const knownSlugs = new Set(['bear_stearns_2006_he1', 'deal_2024_abc', 'simple']);

  it('returns exact match with no docFilter', () => {
    const r = splitCompoundCommand('bear_stearns_2006_he1', knownSlugs);
    assert.equal(r.slug, 'bear_stearns_2006_he1');
    assert.equal(r.docFilter, null);
  });

  it('splits compound command into slug + docFilter', () => {
    const r = splitCompoundCommand('bear_stearns_2006_he1_psa', knownSlugs);
    assert.equal(r.slug, 'bear_stearns_2006_he1');
    assert.equal(r.docFilter, 'PSA');
  });

  it('handles multi-word doc filter suffix', () => {
    const r = splitCompoundCommand('simple_prosupp', knownSlugs);
    assert.equal(r.slug, 'simple');
    assert.equal(r.docFilter, 'PROSUPP');
  });

  it('falls back to full string when no known slug matches', () => {
    const r = splitCompoundCommand('unknown_deal_psa', knownSlugs);
    assert.equal(r.slug, 'unknown_deal_psa');
    assert.equal(r.docFilter, null);
  });

  it('handles empty knownSlugs set', () => {
    const r = splitCompoundCommand('deal_psa', new Set());
    assert.equal(r.slug, 'deal_psa');
    assert.equal(r.docFilter, null);
  });

  it('handles null knownSlugs', () => {
    const r = splitCompoundCommand('deal_psa', null);
    assert.equal(r.slug, 'deal_psa');
    assert.equal(r.docFilter, null);
  });
});

// ─────────────────────────────────────────────────────────────
// parseCommandTokens with knownSlugs (Phase 18)
// ─────────────────────────────────────────────────────────────
describe('parseCommandTokens with knownSlugs', () => {
  const knownSlugs = new Set(['bear_stearns_2006_he1', 'deal_2024_abc']);

  it('splits compound command via knownSlugs', () => {
    const r = parseCommandTokens('bear_stearns_2006_he1_psa', 'What is the waterfall?', knownSlugs);
    assert.equal(r.mode, null);
    assert.equal(r.scopes.length, 1);
    assert.equal(r.scopes[0].slug, 'bear_stearns_2006_he1');
    assert.equal(r.scopes[0].docFilter, 'PSA');
    assert.equal(r.query, 'What is the waterfall?');
  });

  it('exact scope match passes through without docFilter', () => {
    const r = parseCommandTokens('deal_2024_abc', 'test query', knownSlugs);
    assert.equal(r.scopes[0].slug, 'deal_2024_abc');
    assert.equal(r.scopes[0].docFilter, null);
  });

  it('still works with no knownSlugs (backward compat)', () => {
    const r = parseCommandTokens('deal_psa', 'some query');
    assert.equal(r.scopes[0].slug, 'deal_psa');
    assert.equal(r.scopes[0].docFilter, null);
  });
});
