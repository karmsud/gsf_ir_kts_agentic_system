/**
 * Phase 17 — participant.js attribution helpers unit tests.
 *
 * Covers: buildDiffBlock, buildAggregateBlock, buildMultiScopeAttribution.
 *
 * Run:  node --test extension/tests/participant_phase17.test.js
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
      lm: { selectChatModels: async () => [] },
      LanguageModelChatMessage: { User: () => ({}), Assistant: () => ({}) },
      chat: { createChatParticipant: () => ({ onDidReceiveFeedback: () => {} }) },
      Uri: { file: (p) => ({ fsPath: p }) },
      CancellationTokenSource: class { get token() { return { isCancellationRequested: false }; } },
    };
  }
  return originalLoad.apply(this, arguments);
};

const {
  buildDiffBlock,
  buildAggregateBlock,
  buildMultiScopeAttribution,
} = require('../chat/participant');

// ─────────────────────────────────────────────────────────────
// buildDiffBlock
// ─────────────────────────────────────────────────────────────
describe('buildDiffBlock', () => {
  it('returns empty string when no diff_result', () => {
    assert.equal(buildDiffBlock({}), '');
    assert.equal(buildDiffBlock({ search_result: {} }), '');
  });

  it('shows "no meaningful differences" for empty pairwise_diffs', () => {
    const result = { search_result: { diff_result: { pairwise_diffs: [] } } };
    const block = buildDiffBlock(result);
    assert.ok(block.includes('No meaningful differences'));
  });

  it('renders header and field diffs table', () => {
    const result = {
      search_result: {
        diff_result: {
          pairwise_diffs: [{
            scope_a: 'DealA',
            scope_b: 'DealB',
            field_diffs: [
              { field: 'Rate', value_a: '3.5%', value_b: '4.0%', significance: 'high' },
              { field: 'Term', value_a: '30yr', value_b: '30yr', significance: 'low' },
            ]
          }],
          summary: 'Key rate difference found.'
        }
      }
    };
    const block = buildDiffBlock(result);
    assert.ok(block.includes('## Diff Results'));
    assert.ok(block.includes('DealA vs DealB'));
    assert.ok(block.includes('Rate'));
    assert.ok(block.includes('3.5%'));
    assert.ok(block.includes('4.0%'));
    assert.ok(block.includes('🔴 High'));
    assert.ok(block.includes('🔵 Low'));
    assert.ok(block.includes('Key rate difference found.'));
  });

  it('shows "Identical" when a pair has no field_diffs', () => {
    const result = {
      search_result: {
        diff_result: {
          pairwise_diffs: [{
            scope_a: 'X', scope_b: 'Y', field_diffs: []
          }]
        }
      }
    };
    const block = buildDiffBlock(result);
    assert.ok(block.includes('Identical'));
  });

  it('renders medium significance', () => {
    const result = {
      search_result: {
        diff_result: {
          pairwise_diffs: [{
            scope_a: 'A', scope_b: 'B',
            field_diffs: [{ field: 'F', value_a: '1', value_b: '2', significance: 'medium' }]
          }]
        }
      }
    };
    assert.ok(buildDiffBlock(result).includes('⚠️ Medium'));
  });

  it('escapes pipe characters in values', () => {
    const result = {
      search_result: {
        diff_result: {
          pairwise_diffs: [{
            scope_a: 'A', scope_b: 'B',
            field_diffs: [{ field: 'F', value_a: 'a|b', value_b: 'c', significance: 'low' }]
          }]
        }
      }
    };
    const block = buildDiffBlock(result);
    assert.ok(block.includes('a\\|b'));
  });
});

// ─────────────────────────────────────────────────────────────
// buildAggregateBlock
// ─────────────────────────────────────────────────────────────
describe('buildAggregateBlock', () => {
  it('returns empty string when no aggregate_result', () => {
    assert.equal(buildAggregateBlock({}), '');
    assert.equal(buildAggregateBlock({ search_result: {} }), '');
  });

  it('renders consensus and scope count', () => {
    const result = {
      search_result: {
        aggregate_result: {
          scope_count: 5,
          consensus: 'Most deals use a 30-year fixed rate.',
          outliers: [],
          summary: 'Strong consensus.'
        }
      }
    };
    const block = buildAggregateBlock(result);
    assert.ok(block.includes('## Aggregate Analysis'));
    assert.ok(block.includes('5 deals'));
    assert.ok(block.includes('Consensus Pattern'));
    assert.ok(block.includes('30-year fixed rate'));
    assert.ok(block.includes('No outliers detected'));
    assert.ok(block.includes('Strong consensus.'));
  });

  it('renders outlier table', () => {
    const result = {
      search_result: {
        aggregate_result: {
          scope_count: 3,
          consensus: 'Standard terms',
          outliers: [
            { scope: 'DealX', deviation_type: 'Rate', detail: 'Higher than average' },
            { scope: 'DealY', deviation_type: 'Term', text: 'Shorter term' },
          ]
        }
      }
    };
    const block = buildAggregateBlock(result);
    assert.ok(block.includes('Outliers'));
    assert.ok(block.includes('DealX'));
    assert.ok(block.includes('Higher than average'));
    assert.ok(block.includes('DealY'));
    assert.ok(block.includes('Shorter term'));
  });
});

// ─────────────────────────────────────────────────────────────
// buildMultiScopeAttribution
// ─────────────────────────────────────────────────────────────
describe('buildMultiScopeAttribution', () => {
  it('returns empty string for single scope or missing data', () => {
    assert.equal(buildMultiScopeAttribution({}), '');
    assert.equal(buildMultiScopeAttribution({ search_result: { scopes_searched: [{ slug: 'a' }] } }), '');
    assert.equal(buildMultiScopeAttribution({ search_result: { scopes_searched: null } }), '');
  });

  it('renders multi-scope attribution with status icons', () => {
    const result = {
      search_result: {
        scopes_searched: [
          { slug: 'deal1', status: 'ok', result_count: 10 },
          { slug: 'deal2', status: 'timeout', result_count: 0 },
          { slug: 'deal3', status: 'error' },
        ]
      }
    };
    const block = buildMultiScopeAttribution(result);
    assert.ok(block.includes('Scopes Searched'));
    assert.ok(block.includes('✅'));
    assert.ok(block.includes('deal1'));
    assert.ok(block.includes('10 results'));
    assert.ok(block.includes('⏱️'));
    assert.ok(block.includes('deal2'));
    assert.ok(block.includes('❌'));
    assert.ok(block.includes('deal3'));
  });

  it('uses scope field as fallback for slug', () => {
    const result = {
      search_result: {
        scopes_searched: [
          { scope: 'first', status: 'ok' },
          { scope: 'second', status: 'ok' },
        ]
      }
    };
    const block = buildMultiScopeAttribution(result);
    assert.ok(block.includes('first'));
    assert.ok(block.includes('second'));
  });
});

// ─────────────────────────────────────────────────────────────
// Phase 18: Case-insensitive scope command matching
// ─────────────────────────────────────────────────────────────
describe('Phase 18: Case-insensitive scope command matching', () => {
  it('normalizes command to lowercase for scope matching', () => {
    // Simulate discovered scopes (backend returns lowercase slugs)
    const knownSlugs = new Set(['bear_stearns_2006_he1', 'bear_stearns_2006_he2']);
    
    // User types mixed-case command
    const userCommands = [
      'bear_stearns_2006_HE2',
      'Bear_Stearns_2006_HE2',
      'BEAR_STEARNS_2006_HE2',
      'bear_stearns_2006_he2',  // already lowercase
    ];
    
    // All should match after normalization
    for (const cmd of userCommands) {
      const normalized = cmd.toLowerCase();
      assert.ok(knownSlugs.has(normalized), 
        `Command "${cmd}" should match after lowercasing to "${normalized}"`);
    }
  });

  it('does not match unknown scopes regardless of case', () => {
    const knownSlugs = new Set(['bear_stearns_2006_he1']);
    
    const unknownCommands = [
      'bear_stearns_2006_he3',
      'Bear_Stearns_2006_HE3',
      'UNKNOWN_SCOPE',
    ];
    
    for (const cmd of unknownCommands) {
      const normalized = cmd.toLowerCase();
      assert.ok(!knownSlugs.has(normalized), 
        `Unknown command "${cmd}" should not match`);
    }
  });

  it('parses scope from prompt when request.command is empty (Phase 18.1)', () => {
    const { parseCommandTokens } = require('../lib/scope_discovery');
    const knownSlugs = new Set(['bear_stearns_2006_he1', 'bear_stearns_2006_he2']);
    
    // Simulate VS Code not recognizing slash command -> request.command is null/empty
    // Entire input goes into request.prompt
    const cmdName = '';  // empty because request.command was null
    const prompt = '/bear_stearns_2006_HE2 summary waterfall';
    
    const parsed = parseCommandTokens(cmdName, prompt, knownSlugs);
    
    // Should extract scope from prompt
    assert.strictEqual(parsed.scopes.length, 1);
    assert.strictEqual(parsed.scopes[0].slug, 'bear_stearns_2006_he2');  // normalized to lowercase
    
    // Should extract clean query without the slash command
    assert.strictEqual(parsed.query, 'summary waterfall');
  });});