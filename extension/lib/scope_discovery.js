/**
 * Phase 12.2 — Scope Discovery.
 *
 * Scans the configured knowledgeSourceRoot at extension activation time
 * and discovers folders with .kts/ sub-directories.
 * Each discovered scope becomes a dynamic slash command.
 *
 * Also exports `refreshScopes()` for the `kts.refreshScopes` command.
 */

const vscode = require('vscode');
const path = require('path');
const fs = require('fs');

/**
 * Slugify a folder name into a valid slash command name.
 *
 * Rules: lowercase, spaces → underscore, hyphens → underscore,
 * strip non-alphanumeric/underscore chars.
 *
 * @param {string} name - Folder name.
 * @returns {string} Slug suitable for a slash command.
 */
function slugify(name) {
    return name
        .trim()
        .toLowerCase()
        .replace(/[\s\-]+/g, '_')
        .replace(/[^a-z0-9_]/g, '')
        .replace(/_+/g, '_')
        .replace(/^_|_$/g, '');
}

/**
 * Check if a path exists (async wrapper).
 *
 * @param {string} p - File or directory path.
 * @returns {Promise<boolean>}
 */
async function pathExists(p) {
    try {
        await fs.promises.access(p);
        return true;
    } catch {
        return false;
    }
}

/**
 * Discover scopes by scanning the knowledge source root directory.
 *
 * @param {string} knowledgeSourceRoot - Absolute path to scan.
 * @returns {Promise<Array<{name: string, slug: string, ktsPath: string, indexed: boolean}>>}
 */
async function discoverScopes(knowledgeSourceRoot) {
    if (!knowledgeSourceRoot) {
        return [];
    }

    const scopes = [];

    try {
        const entries = await fs.promises.readdir(knowledgeSourceRoot, { withFileTypes: true });

        for (const entry of entries) {
            if (!entry.isDirectory()) continue;

            const ktsPath = path.join(knowledgeSourceRoot, entry.name, '.kts');
            const hasIndex = await pathExists(ktsPath);

            const scope = {
                name: entry.name,
                slug: slugify(entry.name),
                ktsPath: ktsPath,
                indexed: hasIndex,
                docTypes: [],
            };

            // Phase 17: Discover document types per scope from doc_graphs/
            if (hasIndex) {
                const docGraphsDir = path.join(ktsPath, 'graph', 'doc_graphs');
                try {
                    const docGraphFiles = await fs.promises.readdir(docGraphsDir);
                    scope.docTypes = docGraphFiles
                        .filter(f => f.endsWith('.json'))
                        .map(f => f.replace('.json', ''));
                } catch {
                    // doc_graphs/ may not exist yet
                    scope.docTypes = [];
                }
            }

            scopes.push(scope);
        }
    } catch (err) {
        console.error('[ScopeDiscovery] Failed to scan knowledge source root:', err.message);
    }

    return scopes;
}

/**
 * Build dynamic slash command descriptors from discovered scopes.
 *
 * Only includes scopes that have been indexed (.kts/ exists).
 *
 * @param {Array} scopes - Array from discoverScopes().
 * @returns {Array<{name: string, description: string}>}
 */
function buildDynamicCommands(scopes) {
    const commands = [];
    for (const s of scopes) {
        if (!s.indexed || !s.slug) continue;
        commands.push({
            name: s.slug,
            description: `Query the ${s.name} knowledge base`
        });
        // Phase 17: Add doc-type sub-commands for autocomplete
        if (s.docTypes && s.docTypes.length > 0) {
            for (const dt of s.docTypes) {
                commands.push({
                    name: `${s.slug}_${dt.toLowerCase()}`,
                    description: `Query ${s.name} — ${dt} documents only`
                });
            }
        }
    }
    return commands;
}

/**
 * Refresh scopes and update the participant's command list.
 *
 * Call this on activation and when `kts.refreshScopes` is executed.
 *
 * NOTE: The stable VS Code Chat API does NOT support dynamic slash commands.
 * `ChatParticipant` only exposes `followupProvider`, `iconPath`, `id`,
 * `requestHandler`, and `onDidReceiveFeedback`.  There is no
 * `commandProvider` property.  Scope-based routing still works because
 * the request handler (participant.js) parses any unknown command as a
 * scope slug via `parseCommandTokens()`.  Users type `@kts /deal_slug`
 * manually — it won't autocomplete but will resolve correctly.
 *
 * @param {vscode.ChatParticipant} participant - The registered chat participant (unused but kept for API compat).
 * @param {Array} baseCommands - The built-in slash commands (unused but kept for API compat).
 * @returns {Promise<Array>} The discovered scopes.
 */
async function refreshScopes(participant, baseCommands) {
    const config = vscode.workspace.getConfiguration('kts');
    const root = config.get('knowledgeSourceRoot', '');

    if (!root) {
        return [];
    }

    const scopes = await discoverScopes(root);
    // Dynamic commands are still built for reference / logging
    const dynamicCommands = buildDynamicCommands(scopes);

    // NOTE: participant.commandProvider is NOT part of the stable VS Code
    // Chat API.  Scope routing works via parseCommandTokens() in the
    // request handler — users type @kts /slug_name and it resolves.
    // Dynamic autocomplete is not possible without the proposed
    // chatParticipantAdditions API.

    const indexedCount = scopes.filter(s => s.indexed).length;
    // Scope count is logged by the caller via outputChannel

    return scopes;
}

/**
 * Parse two-level scope from a chat request.
 *
 * @param {string} command - The first slash command (scope slug).
 * @param {string} prompt  - The raw prompt text after the command.
 * @returns {{scope: string, doc_type_filter: string|null, query: string}}
 */
function parseTwoLevelScope(command, prompt) {
    const match = (prompt || '').match(/^\/(\w+)\s+([\s\S]*)/);
    if (match) {
        return {
            scope: command,
            doc_type_filter: match[1].toUpperCase(),
            query: match[2].trim()
        };
    }
    return {
        scope: command,
        doc_type_filter: null,
        query: (prompt || '').trim()
    };
}

// ---------- Phase 17 mode tokens ----------
const MODE_TOKENS = new Set([
    'compare', 'diff', 'aggregate', 'audit', 'define', 'list'
]);

/**
 * Phase 18 — Split a compound command like "deal_slug_doctype" into
 * { slug, docFilter } using known scope slugs for disambiguation.
 *
 * Tries longest-match: if "bear_stearns_2006_he1" is a known scope slug
 * and the command is "bear_stearns_2006_he1_psa", returns
 * { slug: 'bear_stearns_2006_he1', docFilter: 'PSA' }.
 *
 * Falls back to the full string as slug with no docFilter.
 *
 * @param {string} command - The slash command name (lowercase).
 * @param {Set<string>} knownSlugs - Known scope slugs from discoverScopes().
 * @returns {{slug: string, docFilter: string|null}}
 */
function splitCompoundCommand(command, knownSlugs) {
    if (!knownSlugs || knownSlugs.size === 0) {
        return { slug: command, docFilter: null };
    }

    // Exact match — no split needed
    if (knownSlugs.has(command)) {
        return { slug: command, docFilter: null };
    }

    // Try splitting at each underscore from the right to find longest slug match
    const parts = command.split('_');
    for (let i = parts.length - 1; i >= 1; i--) {
        const candidate = parts.slice(0, i).join('_');
        if (knownSlugs.has(candidate)) {
            const suffix = parts.slice(i).join('_').toUpperCase();
            return { slug: candidate, docFilter: suffix || null };
        }
    }

    return { slug: command, docFilter: null };
}

/**
 * Phase 17 — Parse command tokens from a chat request.
 *
 * Handles:
 *   - Mode tokens:  /compare, /diff, /aggregate, /audit, /define, /list
 *   - Scope expressions:  /scope_slug, /scope_slug/DOC_TYPE
 *   - Global doc filter:  //DOC_TYPE
 *   - Wildcards:  /scope*
 *
 * Grammar (applied to prompt text AFTER the initial slash command):
 *   prompt  := (token)* query
 *   token   := "/" identifier [ "/" identifier ]
 *   token   := "//" identifier             (global doc filter)
 *
 * The first slash command (request.command) is treated as the primary scope
 * unless it matches a known mode token.
 *
 * @param {string|null} command - The first slash command (e.g. "compare" or "deal_2024_he1").
 * @param {string} prompt       - The raw prompt text after the slash command.
 * @param {Array}  [scopes]     - Discovered scopes for validation (optional).
 * @returns {{
 *   mode: string|null,
 *   scopes: Array<{slug: string, docFilter: string|null, isWildcard: boolean}>,
 *   globalDocFilter: string|null,
 *   query: string
 * }}
 */
function parseCommandTokens(command, prompt, knownSlugs) {
    const result = {
        mode: null,
        scopes: [],
        globalDocFilter: null,
        query: ''
    };

    // Phase 18: Build known slug set for compound command splitting
    const slugSet = knownSlugs instanceof Set ? knownSlugs
        : Array.isArray(knownSlugs) ? new Set(knownSlugs.map(s => (s.slug || s).toString().toLowerCase()))
        : new Set();

    // 1. Handle the primary slash command
    if (command) {
        const lower = command.toLowerCase();
        if (MODE_TOKENS.has(lower)) {
            result.mode = lower;
        } else {
            // Phase 18: Split compound commands (e.g. deal_slug_psa → slug + docFilter)
            const { slug, docFilter } = splitCompoundCommand(lower, slugSet);
            result.scopes.push({
                slug,
                docFilter,
                isWildcard: slug.includes('*')
            });
        }
    }

    if (!prompt) {
        return result;
    }

    // 2. Tokenize the prompt — extract slash tokens from front
    let remaining = prompt.trim();
    const slashTokenRe = /^\/(\/?[\w*]+(?:\/[\w*]+)?)\s*/;

    while (true) {
        const m = remaining.match(slashTokenRe);
        if (!m) break;

        const raw = m[1]; // e.g. "compare", "deal/PSA", "/PSA" (global), "deal*"
        remaining = remaining.slice(m[0].length);

        // Global doc filter: //DOC_TYPE (raw starts with /)
        if (raw.startsWith('/')) {
            result.globalDocFilter = raw.slice(1).toUpperCase();
            continue;
        }

        // Mode token
        const lower = raw.toLowerCase();
        if (MODE_TOKENS.has(lower) && !result.mode) {
            result.mode = lower;
            continue;
        }

        // Scope expression: slug or slug/DOC_TYPE
        const parts = raw.split('/');
        const slug = parts[0].toLowerCase();
        const docFilter = parts.length > 1 ? parts[1].toUpperCase() : null;
        result.scopes.push({
            slug,
            docFilter,
            isWildcard: slug.includes('*')
        });
    }

    result.query = remaining.trim();

    return result;
}

/**
 * Phase 17 — Build CLI arguments from parsed command tokens.
 *
 * @param {{mode: string|null, scopes: Array, globalDocFilter: string|null, query: string}} parsed
 * @returns {Array<string>} Extra CLI args to append.
 */
function buildCliArgsFromTokens(parsed) {
    const args = [];

    if (parsed.mode) {
        args.push('--mode', parsed.mode);
    }

    // If there's a global doc filter or any scope-level doc filter, use the first one found
    const docFilter = parsed.globalDocFilter
        || (parsed.scopes.find(s => s.docFilter) || {}).docFilter
        || null;
    if (docFilter) {
        args.push('--doc-filter', docFilter);
    }

    // Multi-scope: pass all scope slugs
    if (parsed.scopes.length > 1) {
        const slugs = parsed.scopes.map(s => s.slug).join(',');
        args.push('--scopes', slugs);
    }

    return args;
}

module.exports = {
    slugify,
    discoverScopes,
    buildDynamicCommands,
    refreshScopes,
    parseTwoLevelScope,
    parseCommandTokens,
    buildCliArgsFromTokens,
    splitCompoundCommand,
    pathExists,
};
