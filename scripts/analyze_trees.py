"""One-time analysis of resolution tree storage."""
import json

graph_path = r"Knowledge Base test\Fin_deal1\.kts\graph\knowledge_graph.json"
with open(graph_path, "r", encoding="utf-8") as f:
    data = json.load(f)

nodes = data["nodes"]
term_nodes = {nid: ndata for nid, ndata in nodes.items() if ndata.get("type") == "defined_term"}

# Measure current stored tree sizes
sizes = []
for nid, ndata in term_nodes.items():
    tree_json = ndata.get("resolution_tree", "")
    sizes.append(len(tree_json))

print("Current stored trees (depth-2 shallow):")
print(f"  Total bytes: {sum(sizes):,}")
print(f"  Avg per term: {sum(sizes)//len(sizes):,} bytes")
print(f"  Max per term: {max(sizes):,} bytes")
print(f"  Graph file total: 10,741,115 bytes")
print(f"  Trees as % of graph: {sum(sizes)*100/10741115:.1f}%")

# Show examples for the failing golden questions
targets = {
    "Prepayment Interest Shortfall": None,
    "Current Interest": None,
    "Net Mortgage Rate": None,
    "Stated Principal Balance": None,
    "Distribution Date": None,
}

for nid, ndata in term_nodes.items():
    for tgt in targets:
        if tgt in nid and targets[tgt] is None:
            tree = json.loads(ndata["resolution_tree"])
            targets[tgt] = tree

for tgt_name, tree in targets.items():
    if tree is None:
        print(f"\n{tgt_name}: NOT FOUND in graph")
        continue
    print(f"\n=== {tgt_name} ===")
    depth = tree.get("depth", 0)
    trans = tree.get("transitive_count", 0)
    print(f"  depth={depth}, direct_deps={tree.get('dependency_count',0)}, transitive={trans}")
    
    deps = tree.get("dependencies", {})
    for dname, dtree in deps.items():
        subdeps = dtree.get("dependencies", {})
        lost_names = dtree.get("dependency_names", [])
        print(f"  |- {dname}: depth={dtree.get('depth',0)}, stored_children={len(subdeps)}, LOST={lost_names}")
        for sname, stree in subdeps.items():
            lost2 = stree.get("dependency_names", [])
            print(f"     |- {sname}: depth={stree.get('depth',0)}, LOST={lost2}")
