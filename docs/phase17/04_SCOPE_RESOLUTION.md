# Phase 17: Scope Resolution Pipeline
## Unified Token Parsing and Scope Resolution

**Document Version:** 1.0  
**Date:** February 22, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** Token parsing, scope resolution, catalog queries, and the unified pipeline that handles all 14 use cases

---

## Table of Contents
1. [Overview](#overview)
2. [Token Grammar](#token-grammar)
3. [Token Parser Specification](#token-parser-specification)
4. [Scope Resolver Specification](#scope-resolver-specification)
5. [Resolved Scope Data Structure](#resolved-scope-data-structure)
6. [Integration Points](#integration-points)
7. [Error Handling](#error-handling)
8. [Examples: All 14 Use Cases](#examples-all-14-use-cases)

---

## Overview

### The Problem

User commands can express:
- A single deal scope (`/fin_deal1`)
- A deal + document filter (`/fin_deal1/PSA`)
- All deals with a doc filter (`//PSA`)
- Wildcard matching (`/bear_stearns_2006*`)
- Wildcard + doc filter (`/bear_stearns_2006*/PSA`)
- Structured catalog queries (`/vintage:2006 /issuer:bear_stearns`)
- Mode prefixes (`/compare`, `/diff`, `/aggregate`, `/audit`, `/define`, `/list`)
- Combinations of the above

We need a single, deterministic parser that handles all of these and produces a uniform output consumed by the retrieval service.

### Design Goals

1. **Single code path** — one parser for CLI and extension
2. **Deterministic** — same input always produces same output
3. **Composable** — modes, scopes, doc filters combine orthogonally
4. **Fail-fast** — invalid tokens produce clear error messages
5. **Extensible** — new modes or token types can be added without restructuring

---

## Token Grammar

### Formal Grammar (EBNF-like)

```
command     := mode? scope_expr* query
mode        := "/" MODE_NAME
scope_expr  := scope_token ("/" doc_filter)?
scope_token := "/" SCOPE_SLUG
             | "/" SCOPE_SLUG "*"          # wildcard
             | "/" "/" DOC_TYPE             # all-deals shorthand
             | "/" KEY ":" VALUE           # structured catalog query
doc_filter  := DOC_TYPE_NAME              # uppercase doc prefix
query       := FREE_TEXT                  # everything remaining

MODE_NAME   := "compare" | "diff" | "aggregate" | "audit" | "define" 
             | "list" | "extract" | "summary"
SCOPE_SLUG  := [a-z0-9_]+                # lowercase slug from deal catalog
DOC_TYPE    := [A-Z][A-Z0-9_]*           # uppercase doc prefix (PSA, PROSUPP, etc.)
KEY         := "vintage" | "issuer" | "series" | "collateral"
VALUE       := [a-zA-Z0-9_]+
```

### Disambiguation Rules

Since scopes and modes both start with `/`, the parser uses the following precedence:

1. **Mode names are reserved** — if a token matches a known mode, it's always a mode
2. **`//` prefix** — always means "all deals" + the following text is a doc filter
3. **`*` suffix** — always means wildcard
4. **`:` in token** — always means structured catalog query
5. **Known scope slug** — matched against deal catalog
6. **Uppercase after scope** — doc filter (e.g., `/fin_deal1/PSA`)
7. **Unknown token** — treated as part of the query text

### Examples

```
@kts /fin_deal1/PSA What is the Distribution Date?
      ┌──────────┐ ┌──────────────────────────────┐
      scope_expr   query
      ┌────────┐┌───┐
      scope     doc_filter

@kts /compare /bear_stearns_2006*/PSA What is the Distribution Date?
      ┌──────┐ ┌────────────────────┐ ┌──────────────────────────────┐
      mode     scope_expr             query
               ┌────────────────┐┌───┐
               scope (wildcard)  doc_filter

@kts /vintage:2006 /issuer:bear_stearns What is the servicer?
      ┌───────────┐ ┌─────────────────┐ ┌─────────────────────┐
      catalog_key    catalog_key         query

@kts //PSA What is the Distribution Date?
      ┌────┐ ┌──────────────────────────────┐
      all_deals+doc_filter  query
```

---

## Token Parser Specification

### Input/Output

```python
@dataclass
class ParsedCommand:
    """Output of the token parser."""
    
    mode: str = "search"                # "search", "compare", "diff", "aggregate", "audit", "define", "list"
    scope_expressions: list[ScopeExpression] = field(default_factory=list)
    query: str = ""
    raw_input: str = ""                 # Original user input for debugging

@dataclass 
class ScopeExpression:
    """A single scope token parsed from user input."""
    
    scope_slug: str = ""                # e.g., "fin_deal1" or "bear_stearns_2006" (without *)
    doc_filter: str | None = None       # e.g., "PSA" or None
    is_wildcard: bool = False           # True if slug ended with *
    is_all_deals: bool = False          # True if // prefix
    catalog_filters: dict[str, str] = field(default_factory=dict)  # {"vintage": "2006", "issuer": "bear_stearns"}
```

### Parser Algorithm

```python
KNOWN_MODES = {"compare", "diff", "aggregate", "audit", "define", "list", "extract", "summary"}
CATALOG_KEYS = {"vintage", "issuer", "series", "collateral"}

def parse_command(raw_input: str, known_scopes: set[str] | None = None) -> ParsedCommand:
    """Parse a user command into mode, scopes, and query.
    
    Args:
        raw_input: Full user input string (after @kts prefix is stripped)
        known_scopes: Set of valid scope slugs (from deal catalog). 
                      If None, all /tokens are treated as potential scopes.
    
    Returns:
        ParsedCommand with mode, scope_expressions, and query
    """
    result = ParsedCommand(raw_input=raw_input)
    tokens = tokenize(raw_input)
    
    remaining_tokens = []
    
    for token in tokens:
        if not token.startswith("/"):
            remaining_tokens.append(token)
            continue
        
        stripped = token[1:]  # Remove leading /
        
        # Rule 1: Mode detection
        if stripped.lower() in KNOWN_MODES:
            result.mode = stripped.lower()
            continue
        
        # Rule 2: // prefix → all deals + doc filter
        if token.startswith("//"):
            doc_type = token[2:].upper()
            result.scope_expressions.append(ScopeExpression(
                is_all_deals=True,
                doc_filter=doc_type if doc_type else None,
            ))
            continue
        
        # Rule 3: Structured catalog filter (key:value)
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            if key.lower() in CATALOG_KEYS:
                # Find or create a catalog-filter scope expression
                catalog_expr = _find_or_create_catalog_expr(result.scope_expressions)
                catalog_expr.catalog_filters[key.lower()] = value
                continue
        
        # Rule 4: Scope with optional doc filter (/scope or /scope/DOC)
        parts = stripped.split("/", 1)
        scope_part = parts[0]
        doc_part = parts[1] if len(parts) > 1 else None
        
        # Wildcard detection
        is_wildcard = scope_part.endswith("*")
        if is_wildcard:
            scope_part = scope_part[:-1]  # Remove trailing *
        
        # Validate scope against known scopes (if provided)
        scope_slug = scope_part.lower().replace("-", "_").replace(" ", "_")
        
        result.scope_expressions.append(ScopeExpression(
            scope_slug=scope_slug,
            doc_filter=doc_part.upper() if doc_part else None,
            is_wildcard=is_wildcard,
        ))
    
    result.query = " ".join(remaining_tokens).strip()
    return result


def tokenize(raw_input: str) -> list[str]:
    """Split input into tokens, preserving /scope/DOC as single tokens.
    
    Examples:
        "What is X?" → ["What", "is", "X?"]
        "/fin_deal1/PSA What is X?" → ["/fin_deal1/PSA", "What", "is", "X?"]
        "/compare /d1 /d2 What?" → ["/compare", "/d1", "/d2", "What?"]
        "//PSA What?" → ["//PSA", "What?"]
    """
    import re
    # Match: /something (including /a/b, //c, /a:b)
    # Or: regular words
    pattern = r'(/[^\s]+|\S+)'
    return re.findall(pattern, raw_input)
```

---

## Scope Resolver Specification

### Purpose

The Scope Resolver takes `ParsedCommand.scope_expressions` and resolves each into one or more `ResolvedScope` objects by querying the deal catalog.

### Input/Output

```python
@dataclass
class ResolvedScope:
    """A fully resolved scope ready for retrieval."""
    
    scope_slug: str                     # "fin_deal1"
    folder_name: str                    # "Fin_deal1"
    kb_path: str                        # "kb_test/Fin_deal1/.kts/"
    doc_filter: str | None              # "PSA" or None
    graph_path: str                     # Path to appropriate graph JSON
    chroma_dir: str                     # Path to ChromaDB directory
    vector_filter: dict | None          # {"doc_name_prefix": "PSA"} or None
```

### Resolution Algorithm

```python
class ScopeResolver:
    """Resolve scope expressions into concrete retrieval targets."""
    
    def __init__(self, catalog: DealCatalog, knowledge_source_root: str, config: KTSConfig):
        self.catalog = catalog
        self.root = Path(knowledge_source_root)
        self.config = config
    
    def resolve(self, expressions: list[ScopeExpression]) -> list[ResolvedScope]:
        """Resolve all scope expressions into ResolvedScope objects.
        
        Resolution rules:
        1. Explicit slug → direct lookup in catalog
        2. Wildcard slug → catalog search with prefix match
        3. All-deals (// prefix) → return ALL scopes from catalog
        4. Catalog filters → structured query on catalog
        5. Empty expressions → use default scope from config
        """
        resolved: list[ResolvedScope] = []
        
        for expr in expressions:
            if expr.is_all_deals:
                # //DOC → all deals with optional doc filter
                all_scopes = self.catalog.all_scopes()
                for scope in all_scopes:
                    resolved.append(self._build_resolved(scope, expr.doc_filter))
            
            elif expr.catalog_filters:
                # /vintage:2006 → structured catalog query
                matches = self._catalog_structured_query(expr.catalog_filters)
                for scope in matches:
                    resolved.append(self._build_resolved(scope, expr.doc_filter))
            
            elif expr.is_wildcard:
                # /bear_stearns_2006* → prefix match in catalog
                matches = self.catalog.search(expr.scope_slug)
                for match in matches[:self.config.wildcard_max_matches]:
                    resolved.append(self._build_resolved(match, expr.doc_filter))
            
            else:
                # /fin_deal1 → direct lookup
                entry = self.catalog.get_by_slug(expr.scope_slug)
                if entry:
                    scope_dict = {
                        "slug": entry.slug,
                        "folder_name": entry.folder_name,
                        "kts_path": entry.kts_path,
                    }
                    resolved.append(self._build_resolved(scope_dict, expr.doc_filter))
                else:
                    logger.warning("[Phase17] Unknown scope: %s", expr.scope_slug)
        
        # Deduplicate (same scope+doc combination)
        seen = set()
        deduped = []
        for r in resolved:
            key = (r.scope_slug, r.doc_filter)
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        
        return deduped
    
    def _build_resolved(self, scope_dict: dict, doc_filter: str | None) -> ResolvedScope:
        """Build a ResolvedScope from a catalog entry + doc filter."""
        kts_path = scope_dict["kts_path"]
        base_graph_dir = str(Path(kts_path) / "graph")
        chroma_dir = str(Path(kts_path) / "vectors" / "phase6")
        
        # Select graph based on doc filter
        if doc_filter and self.config.doc_graphs_enabled:
            doc_graph = str(Path(base_graph_dir) / "doc_graphs" / f"{doc_filter}.json")
            if Path(doc_graph).exists():
                graph_path = doc_graph
            else:
                graph_path = str(Path(base_graph_dir) / "knowledge_graph.json")
        else:
            graph_path = str(Path(base_graph_dir) / "knowledge_graph.json")
        
        # Build vector filter
        vector_filter = None
        if doc_filter and self.config.doc_filter_enabled:
            vector_filter = {"doc_name_prefix": doc_filter}
        
        return ResolvedScope(
            scope_slug=scope_dict["slug"],
            folder_name=scope_dict["folder_name"],
            kb_path=kts_path,
            doc_filter=doc_filter,
            graph_path=graph_path,
            chroma_dir=chroma_dir,
            vector_filter=vector_filter,
        )
    
    def _catalog_structured_query(self, filters: dict[str, str]) -> list[dict]:
        """Query catalog with structured filters (vintage, issuer, etc.)."""
        # Build SQL WHERE clauses
        all_scopes = self.catalog.all_scopes_detailed()
        results = []
        for entry in all_scopes:
            match = True
            if "vintage" in filters:
                if filters["vintage"] not in entry.get("years", []):
                    match = False
            if "issuer" in filters:
                issuer_query = filters["issuer"].lower()
                if not any(issuer_query in i.lower() for i in entry.get("issuers", [])):
                    match = False
            if "series" in filters:
                series_query = filters["series"].lower()
                if series_query not in entry.get("slug", ""):
                    match = False
            if "collateral" in filters:
                coll_query = filters["collateral"].lower()
                if not any(coll_query in c.lower() for c in entry.get("collateral_types", [])):
                    match = False
            if match:
                results.append(entry)
        return results
```

---

## Resolved Scope Data Structure

### Complete Flow Example

```
User Input:
  @kts /compare /bear_stearns_2006*/PSA What is the Distribution Date?

After Token Parser:
  ParsedCommand(
    mode="compare",
    scope_expressions=[
      ScopeExpression(
        scope_slug="bear_stearns_2006",
        doc_filter="PSA",
        is_wildcard=True,
      )
    ],
    query="What is the Distribution Date?"
  )

After Scope Resolver:
  [
    ResolvedScope(
      scope_slug="bear_stearns_2006he1",
      folder_name="Bear Stearns 2006-HE1",
      kb_path="kb_test/Bear_Stearns_2006_HE1/.kts/",
      doc_filter="PSA",
      graph_path="kb_test/Bear_Stearns_2006_HE1/.kts/graph/doc_graphs/PSA.json",
      chroma_dir="kb_test/Bear_Stearns_2006_HE1/.kts/vectors/phase6/",
      vector_filter={"doc_name_prefix": "PSA"},
    ),
    ResolvedScope(
      scope_slug="bear_stearns_2006he2",
      folder_name="Bear Stearns 2006-HE2",
      kb_path="kb_test/Bear_Stearns_2006_HE2/.kts/",
      doc_filter="PSA",
      graph_path="kb_test/Bear_Stearns_2006_HE2/.kts/graph/doc_graphs/PSA.json",
      chroma_dir="kb_test/Bear_Stearns_2006_HE2/.kts/vectors/phase6/",
      vector_filter={"doc_name_prefix": "PSA"},
    ),
    # ... more resolved scopes
  ]
```

---

## Integration Points

### CLI Integration (`cli/main.py`)

```python
@cli.command()
@click.argument("query")
@click.option("--scope-override", default=None)
@click.option("--doc-filter", default=None, help="Phase 17: Document name prefix filter (e.g., PSA, PROSUPP).")
@click.option("--mode", default="search", help="Phase 17: Retrieval mode (search, compare, diff, aggregate, audit, define, list).")
@click.option("--compare-scopes", default=None, help="Phase 15: Comma-separated scope slugs for /compare.")
def search(query, scope_override, doc_filter, mode, compare_scopes, ...):
    # Build ParsedCommand from CLI args
    parsed = ParsedCommand(
        mode=mode,
        query=query,
        scope_expressions=[],
    )
    
    if scope_override:
        parsed.scope_expressions.append(ScopeExpression(
            scope_slug=scope_override,
            doc_filter=doc_filter,
        ))
    
    if compare_scopes:
        for slug in compare_scopes.split(","):
            slug = slug.strip()
            # Check for /DOC suffix
            if "/" in slug:
                parts = slug.split("/", 1)
                parsed.scope_expressions.append(ScopeExpression(
                    scope_slug=parts[0],
                    doc_filter=parts[1].upper(),
                ))
            else:
                parsed.scope_expressions.append(ScopeExpression(scope_slug=slug))
    
    # Resolve scopes
    resolver = ScopeResolver(catalog, knowledge_source_root, config)
    resolved = resolver.resolve(parsed.scope_expressions)
    
    # Execute retrieval per scope
    # ...
```

### Extension Integration (`participant.js`)

```javascript
// Parse slash tokens from user prompt
function parsePhase17Tokens(prompt) {
    const KNOWN_MODES = new Set([
        'compare', 'diff', 'aggregate', 'audit', 'define', 'list', 'extract', 'summary'
    ]);
    
    const result = {
        mode: 'search',
        scopeExpressions: [],
        query: '',
    };
    
    const tokens = prompt.match(/\/[^\s]+|\S+/g) || [];
    const queryParts = [];
    
    for (const token of tokens) {
        if (!token.startsWith('/')) {
            queryParts.push(token);
            continue;
        }
        
        const stripped = token.slice(1);
        
        // Mode detection
        if (KNOWN_MODES.has(stripped.toLowerCase())) {
            result.mode = stripped.toLowerCase();
            continue;
        }
        
        // All-deals: //DOC
        if (token.startsWith('//')) {
            result.scopeExpressions.push({
                isAllDeals: true,
                docFilter: token.slice(2).toUpperCase() || null,
            });
            continue;
        }
        
        // Scope with optional doc filter: /scope/DOC or /scope*/DOC
        const parts = stripped.split('/');
        let scopePart = parts[0];
        const docPart = parts.length > 1 ? parts[1].toUpperCase() : null;
        const isWildcard = scopePart.endsWith('*');
        if (isWildcard) scopePart = scopePart.slice(0, -1);
        
        // Catalog filter: /key:value
        if (scopePart.includes(':')) {
            const [key, value] = scopePart.split(':');
            result.scopeExpressions.push({
                catalogFilter: { [key]: value },
            });
            continue;
        }
        
        result.scopeExpressions.push({
            scopeSlug: scopePart,
            docFilter: docPart,
            isWildcard,
        });
    }
    
    result.query = queryParts.join(' ').trim();
    return result;
}
```

---

## Error Handling

### Invalid Scope Errors

| Error | User Input | Message |
|-------|-----------|---------|
| Unknown scope | `@kts /unknown_deal What?` | "Scope 'unknown_deal' not found in deal catalog. Use `@kts /list` to see available deals." |
| No wildcard matches | `@kts /nonexistent_2099* What?` | "No deals matching 'nonexistent_2099*'. Use `@kts /list` to see available deals." |
| Unknown doc type | `@kts /fin_deal1/UNKNOWN What?` | "Document type 'UNKNOWN' not found in deal fin_deal1. Available: PSA, PROSUPP." |
| No scopes configured | `@kts What?` | "No knowledge source configured. Use 'Select Source Folder' command first." |
| Empty result | `@kts /vintage:2099 What?` | "No deals found with vintage 2099." |

### Graceful Degradation

If scope resolution partially fails:
- Skip failed scopes, proceed with successfully resolved ones
- Report which scopes failed in the response metadata
- If ALL scopes fail, fall back to global search with a warning

---

## Examples: All 14 Use Cases

### UC1: One Doc in One Deal

```
Input:  @kts /fin_deal1/PSA What is the Distribution Date?
Parsed: mode=search, scopes=[ScopeExpr(slug=fin_deal1, doc=PSA)], query="What is the Distribution Date?"
Resolved: [ResolvedScope(slug=fin_deal1, doc_filter=PSA, graph=doc_graphs/PSA.json, filter={doc_name_prefix: PSA})]
```

### UC2: All Docs in One Deal

```
Input:  @kts /fin_deal1 What is the Distribution Date?
Parsed: mode=search, scopes=[ScopeExpr(slug=fin_deal1)], query="What is the Distribution Date?"
Resolved: [ResolvedScope(slug=fin_deal1, doc_filter=None, graph=knowledge_graph.json, filter=None)]
```

### UC3: One Doc Type Across All Deals

```
Input:  @kts //PSA What is the Distribution Date?
Parsed: mode=search, scopes=[ScopeExpr(is_all_deals=True, doc=PSA)], query="What is the Distribution Date?"
Resolved: [ResolvedScope(slug=deal1, doc=PSA, ...), ResolvedScope(slug=deal2, doc=PSA, ...), ...]
```

### UC4: Wildcard Deals

```
Input:  @kts /bear_stearns_2006* What is the Distribution Date?
Parsed: mode=search, scopes=[ScopeExpr(slug=bear_stearns_2006, is_wildcard=True)], query="..."
Resolved: [ResolvedScope(slug=bear_stearns_2006he1, ...), ResolvedScope(slug=bear_stearns_2006he2, ...), ...]
```

### UC5: Wildcard + Doc Filter

```
Input:  @kts /bear_stearns_2006*/PSA What is the Distribution Date?
Parsed: mode=search, scopes=[ScopeExpr(slug=bear_stearns_2006, is_wildcard=True, doc=PSA)], query="..."
Resolved: [ResolvedScope(slug=he1, doc=PSA, graph=doc_graphs/PSA.json, ...), ...]
```

### UC6: Compare Wildcards

```
Input:  @kts /compare /bear_stearns_2006* What is the Distribution Date?
Parsed: mode=compare, scopes=[ScopeExpr(slug=bear_stearns_2006, is_wildcard=True)], query="..."
Resolved: [ResolvedScope(slug=he1, ...), ResolvedScope(slug=he2, ...), ...]
→ ComparisonEngine processes all resolved results
```

### UC7: Compare with Doc Filter

```
Input:  @kts /compare /bear_stearns_2006*/PSA What is the Distribution Date?
Parsed: mode=compare, scopes=[ScopeExpr(slug=bear_stearns_2006, is_wildcard=True, doc=PSA)], query="..."
Resolved: [ResolvedScope(slug=he1, doc=PSA, ...), ResolvedScope(slug=he2, doc=PSA, ...), ...]
→ ComparisonEngine with PSA-only results
```

### UC8: Define Across Docs in Deal

```
Input:  @kts /fin_deal1 /define Distribution Date
Parsed: mode=define, scopes=[ScopeExpr(slug=fin_deal1)], query="Distribution Date"
Resolved: [ResolvedScope(slug=fin_deal1, graph=knowledge_graph.json, filter=None)]
→ DefinitionResolver uses deal graph to follow cross-doc TERM_CROSS_DOC_REF edges
```

### UC9: Audit One Doc

```
Input:  @kts /audit /fin_deal1/PSA
Parsed: mode=audit, scopes=[ScopeExpr(slug=fin_deal1, doc=PSA)], query=""
Resolved: [ResolvedScope(slug=fin_deal1, doc=PSA, graph=doc_graphs/PSA.json)]
→ AnomalyScorer + completeness check on PSA only
```

### UC10: Diff Two Docs in Same Deal

```
Input:  @kts /diff /fin_deal1/PSA /fin_deal1/PROSUPP Distribution Date
Parsed: mode=diff, scopes=[ScopeExpr(slug=fin_deal1, doc=PSA), ScopeExpr(slug=fin_deal1, doc=PROSUPP)], query="Distribution Date"
Resolved: [ResolvedScope(slug=fin_deal1, doc=PSA, ...), ResolvedScope(slug=fin_deal1, doc=PROSUPP, ...)]
→ DiffEngine aligns and compares
```

### UC11: Diff Same Doc Across Deals

```
Input:  @kts /diff /fin_deal1/PSA /fin_deal2/PSA Distribution Date
Parsed: mode=diff, scopes=[ScopeExpr(slug=fin_deal1, doc=PSA), ScopeExpr(slug=fin_deal2, doc=PSA)], query="Distribution Date"
Resolved: [ResolvedScope(slug=fin_deal1, doc=PSA, ...), ResolvedScope(slug=fin_deal2, doc=PSA, ...)]
→ DiffEngine compares PSA-to-PSA across deals
```

### UC12: Structured Catalog Query

```
Input:  @kts /vintage:2006 /issuer:bear_stearns What is the servicer?
Parsed: mode=search, scopes=[ScopeExpr(catalog_filters={vintage:2006, issuer:bear_stearns})], query="What is the servicer?"
Resolved: [matching deals from catalog]
```

### UC13: List Docs in Deal

```
Input:  @kts /list /fin_deal1
Parsed: mode=list, scopes=[ScopeExpr(slug=fin_deal1)], query=""
→ Returns catalog entry with doc_types, ingestion date, chunk count
```

### UC14: Aggregate Across Wildcard

```
Input:  @kts /aggregate /bear_stearns_2006* How is Realized Loss defined?
Parsed: mode=aggregate, scopes=[ScopeExpr(slug=bear_stearns_2006, is_wildcard=True)], query="How is Realized Loss defined?"
Resolved: [all matching deals]
→ AggregationEngine detects patterns + outliers
```

---

*End of Document — 04_SCOPE_RESOLUTION.md*
