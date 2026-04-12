# Phase 17 — Extension UX & Autocomplete

> **Document**: 09_EXTENSION_UX.md
> **Phase**: 17 — Document-Level Isolation & Cross-Deal Intelligence
> **Status**: Design Specification
> **Last Updated**: 2025-07-14

---

## Table of Contents

1. [Overview](#1-overview)
2. [Current Extension Architecture](#2-current-extension-architecture)
3. [Token Parsing Enhancements](#3-token-parsing-enhancements)
4. [Scope Autocomplete](#4-scope-autocomplete)
5. [Doc-Type Autocomplete](#5-doc-type-autocomplete)
6. [Mode & Filter Autocomplete](#6-mode--filter-autocomplete)
7. [Result Attribution](#7-result-attribution)
8. [Comparison Mode UX](#8-comparison-mode-ux)
9. [Catalog Panel](#9-catalog-panel)
10. [Error Handling & Guidance](#10-error-handling--guidance)
11. [Settings & Configuration](#11-settings--configuration)
12. [File Change Summary](#12-file-change-summary)

---

## 1. Overview

Phase 17 enhances the VS Code extension to provide a rich, guided user
experience for document-level scoping. The key UX improvements are:

| Feature | Description |
|---------|-------------|
| Doc-type autocomplete | After typing `/scope /`, show available doc types |
| Mode autocomplete | After `/`, show `/compare`, `/diff`, `/aggregate`, etc. |
| Result attribution | Every result shows its source document |
| Comparison UX | Rich side-by-side comparison display |
| Catalog panel | Visual deal/document browser |
| Error guidance | Actionable error messages with suggestions |

### Design Principles

1. **Progressive disclosure** — Simple queries work with no tokens; power
   users can add scope/doc/mode tokens for precision.
2. **Autocomplete-driven** — Users discover capabilities through suggestions,
   not documentation.
3. **Clear provenance** — Every result is traceable to a specific document
   and section.
4. **Graceful degradation** — Missing optional tokens produce broader results,
   not errors.

---

## 2. Current Extension Architecture

### 2.1 File Layout

```
extension/
├── extension.js              ← Entry point, activation
├── chat/
│   └── participant.js        ← Chat participant handler (1685 lines)
├── copilot/
│   └── kts_tool.js           ← Backend CLI bridge
├── commands/
│   └── select_source.js      ← Source folder selection
├── lib/
│   ├── scope_discovery.js    ← Scope scanning & slug generation
│   ├── query_expander.js     ← Multi-query RAG fusion
│   ├── critique_client.js    ← Critique loop
│   └── image_describer.js    ← Image auto-description
└── panels/
    └── ...                   ← Webview panels
```

### 2.2 Current Scope Discovery Flow

```javascript
// extension.js activation:
const scopes = await refreshScopes(participant, baseCommands);
// → Scans knowledgeSourceRoot for folders with .kts/
// → Creates dynamic slash commands per scope

// participant.js handler:
const { scope, doc_type_filter, query } = parseTwoLevelScope(command, prompt);
// → Parses /DOC_TYPE sub-token from prompt
```

### 2.3 Current Data Flow

```
User types: @kts /bear_stearns_2006_he1 /PSA what is Realized Loss?

1. VS Code routes to participant.js handler
2. command = "bear_stearns_2006_he1"
3. prompt = "/PSA what is Realized Loss?"
4. parseTwoLevelScope extracts:
   { scope: "bear_stearns_2006_he1",
     doc_type_filter: "PSA",
     query: "what is Realized Loss?" }
5. kts_tool.call() sends to backend CLI
6. Results streamed back to chat
```

---

## 3. Token Parsing Enhancements

### 3.1 Enhanced `parseTwoLevelScope()`

The existing function handles simple `/DOC_TYPE query` patterns. Phase 17
extends it to parse mode tokens, key-value filters, and comparison scopes:

```javascript
/**
 * Phase 17: Enhanced token parser for multi-token commands.
 *
 * Parses: [/DOC_TYPE] [/MODE] [/key:value ...] [/SCOPE2 ...] QUERY
 *
 * @param {string} command - Primary scope slug
 * @param {string} prompt  - Raw prompt text after the command
 * @returns {ParsedCommand}
 */
function parseCommandTokens(command, prompt) {
    const result = {
        scope: command,
        doc_type_filter: null,
        mode: null,
        filters: {},
        compare_scopes: [],
        query: '',
    };

    if (!prompt) return result;

    const tokens = prompt.trim().split(/\s+/);
    const queryParts = [];
    let i = 0;

    while (i < tokens.length) {
        const token = tokens[i];

        if (token.startsWith('/')) {
            const inner = token.slice(1);

            // Mode tokens
            if (['compare', 'diff', 'aggregate', 'extract',
                 'audit', 'define', 'summary', 'catalog'].includes(inner.toLowerCase())) {
                result.mode = inner.toLowerCase();
                i++;
                continue;
            }

            // Key-value filter
            if (inner.includes(':')) {
                const [key, value] = inner.split(':', 2);
                result.filters[key.toLowerCase()] = value;
                i++;
                continue;
            }

            // Uppercase = doc type filter
            if (inner === inner.toUpperCase() && /^[A-Z]/.test(inner)) {
                result.doc_type_filter = inner;
                i++;
                continue;
            }

            // Lowercase = additional scope (for compare)
            if (result.mode === 'compare' || result.mode === 'diff') {
                result.compare_scopes.push(inner);
                i++;
                continue;
            }
        }

        // Everything else is part of the query
        queryParts.push(token);
        i++;
    }

    result.query = queryParts.join(' ').trim();

    // If primary scope looks like /compare, shift scopes
    if (command === 'compare' || command === 'diff' || command === 'aggregate') {
        result.mode = command;
        result.scope = null; // Multi-scope mode
    }

    return result;
}
```

### 3.2 Backward Compatibility

The new `parseCommandTokens()` handles all existing patterns:

| Existing Pattern | Parsed As |
|-----------------|-----------|
| `/scope query` | `{scope, query}` |
| `/scope /DOC_TYPE query` | `{scope, doc_type_filter, query}` |

New patterns:

| New Pattern | Parsed As |
|------------|-----------|
| `/scope /PSA /audit Section 4.01` | `{scope, doc_type_filter: "PSA", mode: "audit", query: "Section 4.01"}` |
| `/compare /s1 /s2 concept` | `{mode: "compare", compare_scopes: ["s1", "s2"], query: "concept"}` |
| `/year:2006 query` | `{filters: {year: "2006"}, query}` |

---

## 4. Scope Autocomplete

### 4.1 How Scope Autocomplete Works

When the user types `@kts /`, the VS Code Chat Participant API provides
scope suggestions via the `commandProvider`:

```javascript
// Current implementation in scope_discovery.js:
function buildDynamicCommands(scopes) {
    return scopes
        .filter(s => s.indexed && s.slug)
        .map(s => ({
            name: s.slug,
            description: `Query the ${s.name} knowledge base`
        }));
}
```

### 4.2 Phase 17 Enhanced Scope Commands

```javascript
/**
 * Phase 17: Build enhanced dynamic commands with document counts.
 */
function buildDynamicCommands(scopes, catalog) {
    const commands = scopes
        .filter(s => s.indexed && s.slug)
        .map(s => {
            const entry = catalog ? catalog[s.slug] : null;
            const docCount = entry ? entry.doc_count : 0;
            const docTypes = entry ? entry.doc_types.join(', ') : '';

            return {
                name: s.slug,
                description: docCount > 0
                    ? `${s.name} (${docCount} docs: ${docTypes})`
                    : `Query the ${s.name} knowledge base`,
            };
        });

    // Add built-in mode commands
    commands.push(
        { name: 'compare', description: 'Compare a concept across deals' },
        { name: 'diff', description: 'Find material differences between deals' },
        { name: 'aggregate', description: 'Analyze patterns across many deals' },
        { name: 'catalog', description: 'Browse indexed deals and documents' },
    );

    return commands;
}
```

### 4.3 Scope Display

```
User types: @kts /

Autocomplete shows:
  /bear_stearns_2006_he1     Bear Stearns 2006-HE1 (4 docs: PSA, PROSUPP, INDENTURE, SAA)
  /morgan_stanley_2006_he2   Morgan Stanley 2006-HE2 (3 docs: PSA, PROSUPP, INDENTURE)
  /lehman_2006_he4           Lehman 2006-HE4 (5 docs: PSA, PROSUPP, INDENTURE, SAA, SERVICING)
  ──────────────────
  /compare                   Compare a concept across deals
  /diff                      Find material differences between deals
  /aggregate                 Analyze patterns across many deals
  /catalog                   Browse indexed deals and documents
```

---

## 5. Doc-Type Autocomplete

### 5.1 Trigger Condition

After the user selects a scope and types another `/`, show available
document types for that scope.

### 5.2 Implementation

The VS Code Chat Participant API `commandProvider` returns commands at
the top level. For second-level doc-type autocomplete, we use the
`followupProvider`:

```javascript
/**
 * Phase 17: Suggest doc types and modes after scope selection.
 *
 * When the user has already selected a scope, suggest doc types
 * and modes as follow-up actions.
 */
function provideSuggestions(scope, catalog) {
    const suggestions = [];

    // Doc types for this scope
    if (catalog && catalog[scope]) {
        const docTypes = catalog[scope].doc_types || [];
        for (const dt of docTypes) {
            const doc = catalog[scope].documents?.find(d => d.doc_type === dt);
            const chunkInfo = doc ? ` (${doc.chunks} chunks)` : '';
            suggestions.push({
                label: `/${dt}`,
                description: `Search only ${dt}${chunkInfo}`,
            });
        }
    }

    // Mode suggestions
    suggestions.push(
        { label: '/define', description: 'Look up a defined term' },
        { label: '/extract', description: 'Extract structured data' },
        { label: '/audit', description: 'Audit for anomalies' },
        { label: '/summary', description: 'Generate a summary' },
    );

    return suggestions;
}
```

### 5.3 Doc-Type Display

```
User types: @kts /bear_stearns_2006_he1 /

Suggestions show:
  /PSA          Search only PSA (450 chunks)
  /PROSUPP      Search only PROSUPP (180 chunks)
  /INDENTURE    Search only INDENTURE (320 chunks)
  /SAA          Search only SAA (95 chunks)
  ──────────────────
  /define       Look up a defined term
  /extract      Extract structured data
  /audit        Audit for anomalies
  /summary      Generate a summary
```

### 5.4 Fetching Doc Types from Backend

```javascript
/**
 * Fetch doc types for a scope from the backend catalog.
 *
 * @param {string} scope - Scope slug
 * @returns {Promise<Array<{doc_type: string, chunks: number}>>}
 */
async function fetchDocTypes(scope) {
    try {
        const result = await ktsBackend.call({
            command: 'catalog',
            subcommand: 'doc-types',
            scope: scope,
        });
        return result.documents || [];
    } catch {
        return [];
    }
}
```

---

## 6. Mode & Filter Autocomplete

### 6.1 Mode Suggestions

When the user types `/` in a context where mode tokens are valid:

```
User types: @kts /bear_stearns_2006_he1 /PSA /

Shows:
  /define       Look up a defined term from PSA
  /extract      Extract structured data from PSA
  /audit        Audit PSA sections for anomalies
  /summary      Generate a PSA summary
```

### 6.2 Filter Suggestions (Unscoped)

When the user starts with `@kts /` and types a key with no scope match:

```
User types: @kts /year:

Shows:
  /year:2004    All 2004 deals
  /year:2005    All 2005 deals
  /year:2006    All 2006 deals (3 deals)
  /year:2007    All 2007 deals (1 deal)
```

### 6.3 Compare Mode Suggestions

```
User types: @kts /compare /bear_stearns_2006_he1 /

Shows:
  /morgan_stanley_2006_he2   Compare with Morgan Stanley 2006-HE2
  /lehman_2006_he4           Compare with Lehman 2006-HE4
  /PSA                       Constrain to PSA documents only
```

---

## 7. Result Attribution

### 7.1 Purpose

Every search result must show which document it came from. This is critical
for document-level isolation — users need to know if a result is from the
PSA, Indenture, or Prospectus Supplement.

### 7.2 Attribution Format

```markdown
📄 **Source**: PSA_2006-HE1 > Section 5.05(a) > Item 3
📊 **Confidence**: 0.94 | **Strategy**: graph_first_legal
```

### 7.3 Implementation in `participant.js`

```javascript
/**
 * Phase 17: Format a result with document attribution.
 *
 * @param {Object} result - A retrieval result from the backend
 * @param {boolean} showScore - Whether to show confidence score
 * @returns {string} Formatted markdown string
 */
function formatResultWithAttribution(result, showScore = true) {
    const parts = [];

    // Content
    parts.push(result.content || result.text || '');

    // Attribution line
    const source = result.doc_name_prefix || result.source_doc || '';
    const section = result.section_number
        || result.metadata?.section_number
        || '';
    const itemType = result.item_type
        || result.metadata?.item_type
        || '';

    if (source || section) {
        let attribution = '📄 **Source**:';
        if (source) attribution += ` ${source}`;
        if (section) attribution += ` > Section ${section}`;
        if (itemType) attribution += ` (${itemType})`;
        parts.push(attribution);
    }

    // Score line (optional)
    if (showScore) {
        const confidence = (
            result.score || result.confidence || 0
        ).toFixed(2);
        const strategy = result.strategy || '';
        let scoreLine = `📊 **Confidence**: ${confidence}`;
        if (strategy) scoreLine += ` | **Strategy**: ${strategy}`;
        parts.push(scoreLine);
    }

    // Cross-doc note (when definition from different doc)
    if (result.cross_doc_note) {
        parts.push(`ℹ️ ${result.cross_doc_note}`);
    }

    return parts.join('\n\n');
}
```

### 7.4 Multi-Scope Result Attribution

When results come from multiple scopes (wildcard, global):

```markdown
📁 **Deal**: Bear Stearns 2006-HE1
📄 **Source**: PSA_2006-HE1 > Section 1.01
📊 **Confidence**: 0.94

---

📁 **Deal**: Morgan Stanley 2006-HE2
📄 **Source**: PSA_2006-HE2 > Section 1.01
📊 **Confidence**: 0.91
```

```javascript
function formatMultiScopeResult(result) {
    const dealName = result._scope_name || result._scope_slug || '';
    const parts = [];

    if (dealName) {
        parts.push(`📁 **Deal**: ${dealName}`);
    }

    parts.push(formatResultWithAttribution(result));
    return parts.join('\n');
}
```

---

## 8. Comparison Mode UX

### 8.1 Compare Display

```javascript
/**
 * Format comparison results for chat display.
 */
function formatComparisonResult(comparisonPayload) {
    const { comparison_result, contradictions } = comparisonPayload;

    const parts = [];

    // Header
    parts.push(`## Comparison: "${comparison_result.concept}"`);
    parts.push(`Scopes: ${comparison_result.scopes_compared.join(' vs ')}`);

    // Main comparison markdown (from LLM)
    parts.push(comparison_result.raw_markdown);

    // Contradictions
    if (contradictions && contradictions.length > 0) {
        parts.push('\n### ⚠️ Contradictions Detected\n');
        for (const c of contradictions) {
            const icon = c.severity === 'high' ? '🔴' : '⚠️';
            parts.push(`${icon} **${c.description}** (${c.severity})`);
            if (c.legal_impact) {
                parts.push(`   Impact: ${c.legal_impact}`);
            }
        }
    }

    return parts.join('\n\n');
}
```

### 8.2 Diff Display

```javascript
function formatDiffResult(diffPayload) {
    const { diff_result } = diffPayload;
    const parts = [];

    parts.push(`## Diff: ${diff_result.topic}`);
    parts.push(`${diff_result.scope_a} vs ${diff_result.scope_b}`);

    if (diff_result.has_material_differences) {
        parts.push('🔴 **Material differences detected**\n');
    } else {
        parts.push('✅ **No material differences found**\n');
    }

    parts.push(diff_result.raw_markdown);

    return parts.join('\n\n');
}
```

### 8.3 Aggregate Display

```javascript
function formatAggregateResult(aggPayload) {
    const { aggregate_result } = aggPayload;
    const parts = [];

    parts.push(`## Aggregate: ${aggregate_result.concept}`);
    parts.push(`Analyzed ${aggregate_result.total_scopes} deals`);

    if (aggregate_result.outlier_count > 0) {
        parts.push(
            `⚠️ ${aggregate_result.outlier_count} outliers ` +
            `(${aggregate_result.outlier_percentage.toFixed(0)}%)`
        );
    }

    parts.push(aggregate_result.raw_markdown);

    return parts.join('\n\n');
}
```

---

## 9. Catalog Panel

### 9.1 Purpose

The `/catalog` command provides a visual browser for indexed deals and
documents directly in the chat interface.

### 9.2 Chat-Based Catalog

```javascript
/**
 * Handle /catalog commands in chat.
 */
async function handleCatalogCommand(subcommand, scope, stream) {
    switch (subcommand) {
        case 'list':
            const deals = await ktsBackend.call({ command: 'catalog', subcommand: 'list' });
            stream.markdown(formatCatalogList(deals));
            break;

        case 'docs':
            if (!scope) {
                stream.markdown('⚠️ Please specify a scope: `/catalog docs /scope_name`');
                return;
            }
            const docs = await ktsBackend.call({
                command: 'catalog', subcommand: 'docs', scope
            });
            stream.markdown(formatDocList(docs));
            break;

        case 'stats':
            const stats = await ktsBackend.call({ command: 'catalog', subcommand: 'stats' });
            stream.markdown(formatCatalogStats(stats));
            break;

        default:
            stream.markdown(
                '📖 **Catalog Commands**\n' +
                '- `/catalog list` — List all indexed deals\n' +
                '- `/catalog docs /scope` — List documents in a deal\n' +
                '- `/catalog stats` — Show knowledge base statistics\n'
            );
    }
}
```

### 9.3 Catalog Format Functions

```javascript
function formatCatalogList(deals) {
    if (!deals || deals.length === 0) {
        return '📁 No deals indexed. Use `kts ingest <path>` to index a deal.';
    }

    const lines = [`📁 **Indexed Deals** (${deals.length} deals)\n`];

    for (let i = 0; i < deals.length; i++) {
        const d = deals[i];
        lines.push(`**${i + 1}. ${d.folder_name}** (\`${d.slug}\`)`);
        if (d.doc_types && d.doc_types.length > 0) {
            lines.push(`   📄 ${d.doc_count} docs: ${d.doc_types.join(', ')}`);
        }
        if (d.total_chunks) {
            lines.push(
                `   📊 ${d.total_chunks} chunks | ` +
                `${d.total_definitions || 0} definitions | ` +
                `${d.total_rules || 0} rules`
            );
        }
        if (d.last_indexed) {
            lines.push(`   📅 Indexed: ${d.last_indexed}`);
        }
        lines.push('');
    }

    return lines.join('\n');
}

function formatDocList(docs) {
    if (!docs || !docs.documents || docs.documents.length === 0) {
        return '📄 No documents found in this deal.';
    }

    const lines = [
        `📁 **${docs.scope}** — Documents\n`,
        '| Doc Type | File | Chunks | Definitions | Rules |',
        '|----------|------|--------|-------------|-------|',
    ];

    for (const d of docs.documents) {
        lines.push(
            `| ${d.doc_type} | ${d.original_filename || d.doc_name_prefix} | ` +
            `${d.chunk_count} | ${d.definition_count} | ${d.rule_count} |`
        );
    }

    return lines.join('\n');
}
```

---

## 10. Error Handling & Guidance

### 10.1 User-Friendly Error Messages

```javascript
/**
 * Phase 17: Generate helpful error messages with suggestions.
 */
function formatError(error, context) {
    const { scope, doc_type_filter, mode } = context;

    // Scope not found
    if (error.code === 'SCOPE_NOT_FOUND') {
        return (
            `⚠️ Scope \`${scope}\` not found.\n\n` +
            `**Available scopes:**\n` +
            error.available_scopes.map(s => `- \`/${s.slug}\` — ${s.name}`).join('\n') +
            `\n\nUse \`/catalog list\` to see all indexed deals.`
        );
    }

    // Doc type not found in scope
    if (error.code === 'DOC_TYPE_NOT_FOUND') {
        return (
            `⚠️ Doc type \`${doc_type_filter}\` not found in \`${scope}\`.\n\n` +
            `**Available doc types:**\n` +
            error.available_doc_types.map(dt => `- \`/${dt}\``).join('\n')
        );
    }

    // No results
    if (error.code === 'NO_RESULTS') {
        const suggestions = [];
        if (doc_type_filter) {
            suggestions.push(`Try without doc filter: \`@kts /${scope} ${context.query}\``);
        }
        if (scope) {
            suggestions.push(`Try global search: \`@kts ${context.query}\``);
        }
        return (
            `🔍 No results found for "${context.query}".\n\n` +
            `**Suggestions:**\n` +
            suggestions.map(s => `- ${s}`).join('\n')
        );
    }

    // Generic error
    return `❌ ${error.message || 'An error occurred during retrieval.'}`;
}
```

### 10.2 Scope Clarification

When multiple scopes match and clarification is needed:

```javascript
function formatScopeClarification(routing) {
    return (
        `🔍 Multiple deals match your query:\n\n` +
        routing.scopes.map((s, i) =>
            `${i + 1}. \`/${s.slug}\` — ${s.folder_name} ` +
            `(${s.match_type}, confidence: ${s.confidence.toFixed(2)})`
        ).join('\n') +
        `\n\nPlease specify a deal scope, e.g.:\n` +
        `\`@kts /${routing.scopes[0].slug} ${routing.query}\``
    );
}
```

---

## 11. Settings & Configuration

### 11.1 New Extension Settings

```json
{
    "kts.knowledgeSourceRoot": {
        "type": "string",
        "description": "Root directory containing deal folders"
    },
    "kts.showDocAttribution": {
        "type": "boolean",
        "default": true,
        "description": "Show document source attribution in results"
    },
    "kts.showConfidenceScores": {
        "type": "boolean",
        "default": true,
        "description": "Show confidence scores in results"
    },
    "kts.maxCompareScopes": {
        "type": "number",
        "default": 10,
        "description": "Maximum scopes for wildcard comparison"
    },
    "kts.enableDocTypeAutocomplete": {
        "type": "boolean",
        "default": true,
        "description": "Show doc type suggestions after scope selection"
    }
}
```

### 11.2 Configuration in `package.json`

```json
{
    "contributes": {
        "configuration": {
            "title": "KTS Knowledge Assistant",
            "properties": {
                "kts.knowledgeSourceRoot": { "..." },
                "kts.showDocAttribution": { "..." },
                "kts.showConfidenceScores": { "..." },
                "kts.maxCompareScopes": { "..." },
                "kts.enableDocTypeAutocomplete": { "..." }
            }
        }
    }
}
```

---

## 12. File Change Summary

### 12.1 Modified Files

| File | Changes |
|------|---------|
| `extension/chat/participant.js` | New `parseCommandTokens()`, result attribution formatting, comparison/diff/aggregate display, catalog handler |
| `extension/copilot/kts_tool.js` | Forward `doc_filter`, `mode`, `compare_scopes`, `filters` to backend |
| `extension/lib/scope_discovery.js` | Enhanced `buildDynamicCommands()` with doc counts, doc-type fetching |
| `extension/package.json` | New settings: `showDocAttribution`, `showConfidenceScores`, `maxCompareScopes`, `enableDocTypeAutocomplete` |
| `extension/commands/select_source.js` | Trigger scope refresh after source change |

### 12.2 New Files

| File | Purpose |
|------|---------|
| `extension/lib/token_parser.js` | Extracted token parsing logic |
| `extension/lib/result_formatter.js` | Result attribution and display formatting |
| `extension/lib/catalog_client.js` | Backend catalog query helpers |

### 12.3 Estimated Effort

| File | Lines Changed | Complexity |
|------|--------------|-----------|
| `participant.js` | ~200 lines | Medium |
| `kts_tool.js` | ~30 lines | Low |
| `scope_discovery.js` | ~50 lines | Low |
| `package.json` | ~20 lines | Low |
| `token_parser.js` (new) | ~120 lines | Medium |
| `result_formatter.js` (new) | ~150 lines | Medium |
| `catalog_client.js` (new) | ~80 lines | Low |

---

*End of Document — 09_EXTENSION_UX.md*
