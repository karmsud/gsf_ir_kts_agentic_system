"""Token budget analysis for layered definition tree format."""
import json

G_data = json.load(open(
    r"Knowledge Base test\Fin_deal1\.kts\graph\knowledge_graph.json",
    encoding="utf-8",
))
edges = G_data["edges"]

depends_on: dict = {}
for e in edges:
    if e.get("type") == "DEPENDS_ON":
        src = e.get("source", e.get("src", ""))
        tgt = e.get("target", e.get("tgt", ""))
        if src:
            depends_on.setdefault(src, []).append(tgt)

CHAIN_ONLY_PER_NODE = 12   # "Term Name -> Dep1, Dep2, Dep3" ~ 12 tokens
DEFINITION_PER_NODE = 55   # 200 chars / 4 + formatting
FULL_PER_NODE = 65         # chain + definition combined


def unique_at_depth(start, max_d):
    visited = set()
    level = [start]
    total = 0
    for d in range(max_d + 1):
        new_nodes = [n for n in level if n not in visited]
        total += len(new_nodes)
        visited.update(new_nodes)
        next_level = []
        for n in new_nodes:
            for succ in depends_on.get(n, []):
                if succ not in visited:
                    next_level.append(succ)
        level = next_level
    return total


def all_reachable(start):
    visited = set()
    stack = [start]
    while stack:
        n = stack.pop()
        if n in visited:
            continue
        visited.add(n)
        for succ in depends_on.get(n, []):
            if succ not in visited:
                stack.append(succ)
    return visited


targets = [
    "Prepayment Interest Shortfall",
    "Current Interest",
    "Net Mortgage Rate",
    "Stated Principal Balance",
]

print("=" * 70)
print("LAYERED FORMAT: Full chain (names) + selective definitions")
print("=" * 70)
print()

for t in targets:
    nid = f"TERM::{t}"
    total_unique = len(all_reachable(nid))
    chain_cost = total_unique * CHAIN_ONLY_PER_NODE

    print(f"{t} ({total_unique} unique reachable terms):")
    print(f"  Layer 1 (FULL chain, names only):  {chain_cost:>6,} tokens")

    for n_defs in [10, 20, 30, 50]:
        actual_defs = min(n_defs, total_unique)
        layer2_cost = actual_defs * DEFINITION_PER_NODE
        total = chain_cost + layer2_cost
        print(f"  + Layer 2 ({actual_defs:>2} definitions):       {total:>6,} tokens total")

    old_d4 = unique_at_depth(nid, 4) * FULL_PER_NODE
    print(f"  (Compare: old deduped depth=4:      {old_d4:>6,} tokens)")
    print()

print()
print("=" * 70)
print("MULTI-QUERY SCENARIO: 3 terms enriched")
print("=" * 70)
print()

scenario_terms = ["Prepayment Interest Shortfall", "Net Mortgage Rate", "Distribution Date"]
combined = set()
for t in scenario_terms:
    combined.update(all_reachable(f"TERM::{t}"))

deduped = len(combined)
chain_total = deduped * CHAIN_ONLY_PER_NODE
print(f"3 terms combined, deduped across terms: {deduped} unique nodes")
print(f"  Full chain (names only):    {chain_total:>6,} tokens")
print(f"  + 20 priority definitions:  {chain_total + 20 * DEFINITION_PER_NODE:>6,} tokens")
print(f"  + 50 priority definitions:  {chain_total + 50 * DEFINITION_PER_NODE:>6,} tokens")
print(f"  + ALL definitions:          {deduped * FULL_PER_NODE:>6,} tokens")
print()

print()
print("=" * 70)
print("BUDGET ANALYSIS FOR 100K")
print("=" * 70)
print()
print("Context window allocations:")
print(f"  System prompt:               ~2,000 tokens")
print(f"  Conversation history:        ~5,000 tokens")
print(f"  Retrieved chunks (25 x 500):~12,500 tokens")
print(f"  Definition trees (100K):    100,000 tokens")
print(f"  Answer generation:           ~2,000 tokens")
print(f"  TOTAL:                     ~121,500 tokens")
print(f"  GPT-4.1 capacity:        1,047,576 tokens")
print(f"  Utilization:                  11.6%")
print()

print("What 100K buys with layered format:")
print(f"  ALL 248 chains = {248 * CHAIN_ONLY_PER_NODE:,} tokens")
remaining = 100000 - 248 * CHAIN_ONLY_PER_NODE
n_full_defs = remaining // DEFINITION_PER_NODE
print(f"  Remaining for definitions: {remaining:,} tokens")
print(f"  That buys: {n_full_defs} full definition excerpts out of 248 = {n_full_defs/248*100:.0f}%")
print()

print()
print("=" * 70)
print("SELFRAG MULTI-PASS SIMULATION")
print("=" * 70)
print()
print("Pass 1: Chain for ALL 248 terms + definitions for top 30 priority")
pass1 = 248 * CHAIN_ONLY_PER_NODE + 30 * DEFINITION_PER_NODE
print(f"  Token cost: {pass1:,} tokens")
print("  LLM sees: full dependency structure + 30 key definitions")
print("  LLM identifies: needs Mortgage Rate, Mortgage Loan Schedule, etc.")
print()
print("Pass 2: SelfRAG fetches 5-10 specific missing definitions")
pass2_add = 10 * DEFINITION_PER_NODE
print(f"  Additional cost: {pass2_add:,} tokens")
print(f"  Total across 2 passes: {pass1 + pass2_add:,} tokens")
print(f"  That is {(pass1 + pass2_add) / 1000:.1f}K tokens - well under ANY budget")
print()

print()
print("=" * 70)
print("TOKEN BUDGET RECOMMENDATION")
print("=" * 70)
print()
print("With layered format (chain + selective defs):")
print("  Even at 20K budget we can serve ANY query with full chains + 30 defs")
print("  The 100K budget is overkill but harmless (11.6% of 1M context)")
print("  Attention dilution risk: minimal because chain is structured, not prose")
print()
print("Recommendation: 50K budget with adaptive allocation")
print("  - Always include FULL chain for all queried terms (cost: 2-5K)")
print("  - Fill remaining budget with definitions, priority-ordered:")
print("    1. Direct dependencies of queried term")
print("    2. Terms mentioned in retrieved chunks")
print("    3. Breadth-first from root")
print("  - SelfRAG can request specific missing definitions in pass 2+")
