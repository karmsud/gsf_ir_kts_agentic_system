import os, re, json, unicodedata, math, collections, hashlib
from typing import List, Dict, Any, Tuple
import streamlit as st
import networkx as nx

# ---------- Optional, graceful imports ----------
try:
    import numpy as np
except Exception:
    np = None

try:
    from rapidfuzz import fuzz
    def fuzz_sim(a, b): return fuzz.token_set_ratio(a, b) / 100.0
except Exception:
    from difflib import SequenceMatcher
    def fuzz_sim(a, b): return SequenceMatcher(None, a.lower(), b.lower()).ratio()

# =========================
# Utilities
# =========================
def normalize_ws(t: str) -> str:
    t = unicodedata.normalize("NFKC", t or "")
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\r\n?', '\n', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()

def stable_id(*parts: str) -> str:
    base = "::".join([p for p in parts if p])
    h = hashlib.md5(base.encode('utf-8')).hexdigest()[:10]
    slugs = []
    for p in parts:
        if not p: continue
        p = re.sub(r'\s+', '_', p)
        p = re.sub(r'[^A-Za-z0-9_\-.:]', '', p)
        slugs.append(p[:40])
    return "-".join(slugs + [h])

# =========================
# Load extracted items
# =========================
def enforce_schema(it: Dict[str, Any]) -> Dict[str, Any]:
    # Normalize required keys and defaults
    it["id"] = it.get("id") or stable_id("item", it.get("text","")[:40])
    it["type"] = (it.get("type") or "").strip()  # "Rule" or "Definition" preferred
    it["text"] = normalize_ws(it.get("text",""))
    it["document_id"] = it.get("document_id") or "UNKNOWN_DOC"
    it["section_heading"] = it.get("section_heading") or ""
    it["section_number"] = it.get("section_number")
    # Be tolerant to missing indices
    try:
        it["section_index"] = int(it.get("section_index", -1))
    except Exception:
        it["section_index"] = -1
    try:
        it["item_index"] = int(it.get("item_index", -1))
    except Exception:
        it["item_index"] = -1
    return it

@st.cache_data(show_spinner=False)
def load_items_from_bytes(file_bytes: bytes) -> List[Dict[str, Any]]:
    items = json.loads(file_bytes.decode("utf-8"))
    items = [enforce_schema(x) for x in items]
    return items

@st.cache_data(show_spinner=False)
def load_items_from_path(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        items = json.load(f)
    items = [enforce_schema(x) for x in items]
    return items

# =========================
# Build graph from items
# =========================
def extract_defined_term(def_sentence: str) -> str:
    s = def_sentence.strip()
    # quoted “Term” means ...
    m = re.search(r'([“"\'’])([^"”’]{2,80})\1\s+(means|is defined as)\b', s, re.IGNORECASE)
    if m:
        return m.group(2).strip()
    # TERM means ...
    parts = re.split(r'\b(means|is defined as)\b', s, flags=re.IGNORECASE)
    if parts:
        left = parts[0].strip()
        cand = re.findall(r'([A-Z][A-Za-z0-9 _-]{1,60})$', left)
        if cand:
            return cand[-1].strip()
    return ""

@st.cache_data(show_spinner=False)
def build_graph_from_items(items: List[Dict[str, Any]], add_cross_refs: bool = True) -> Dict[str, Any]:
    """
    Returns a dict { 'graph': nx.DiGraph, 'doc_ids': List[str] }
    """
    G = nx.DiGraph()

    # Document and Section scaffolding
    for it in items:
        doc_node = f"doc::{it['document_id']}"
        if not G.has_node(doc_node):
            G.add_node(doc_node, type="Document", name=it["document_id"], document_id=it["document_id"])

        if it["section_index"] >= 0:
            sec_node = f"sec::{it['document_id']}::{it['section_index']:04d}"
            if not G.has_node(sec_node):
                G.add_node(
                    sec_node,
                    type="Section",
                    document_id=it["document_id"],
                    section_heading=it["section_heading"],
                    section_number=it["section_number"],
                    section_index=int(it["section_index"])
                )
                G.add_edge(doc_node, sec_node, type="CONTAINS")

    # Attach Items
    for it in items:
        node_id = it["id"]
        ntype = it["type"] or "Item"
        G.add_node(
            node_id,
            type=ntype,
            text=it["text"],
            document_id=it["document_id"],
            section_heading=it["section_heading"],
            section_number=it["section_number"],
            section_index=it["section_index"],
            item_index=it["item_index"],
        )
        if it["section_index"] >= 0:
            sec_node = f"sec::{it['document_id']}::{it['section_index']:04d}"
            edge_t = "HAS_RULE" if ntype.lower()=="rule" else ("HAS_DEFINITION" if ntype.lower()=="definition" else "HAS_ITEM")
            if G.has_node(sec_node):
                G.add_edge(sec_node, node_id, type=edge_t)
        else:
            G.add_edge(f"doc::{it['document_id']}", node_id, type="CONTAINS")

    # NEXT edges for sections
    for doc in {it["document_id"] for it in items}:
        sec_nodes = sorted(
            [n for n, d in G.nodes(data=True) if d.get("type")=="Section" and d.get("document_id")==doc],
            key=lambda n: G.nodes[n].get("section_index", 0)
        )
        for i in range(1, len(sec_nodes)):
            G.add_edge(sec_nodes[i-1], sec_nodes[i], type="NEXT")

    # Rule -> Definition REFERENCES (by term mention)
    if add_cross_refs:
        def_nodes = [(n,d) for n,d in G.nodes(data=True) if d.get("type")=="Definition"]
        term_cache = {}
        for n, d in def_nodes:
            term = d.get("term") or extract_defined_term(d.get("text",""))
            if term:
                term_cache[n] = term
        for rnode, rdata in G.nodes(data=True):
            if rdata.get("type") != "Rule": continue
            rtext = rdata.get("text","")
            for dnode, term in term_cache.items():
                if term and re.search(r'\b' + re.escape(term) + r'\b', rtext):
                    G.add_edge(rnode, dnode, type="REFERENCES")

    return {"graph": G, "doc_ids": sorted({it["document_id"] for it in items})}

# =========================
# Retrieval (GraphRAG)
# =========================
def tokenize(text: str) -> List[str]:
    return [t for t in re.split(r'[^A-Za-z0-9]+', (text or "").lower()) if t and len(t) > 1]

def build_inverted_index(G: nx.DiGraph, node_types=("Rule","Definition","Section")):
    docs = []
    for n, data in G.nodes(data=True):
        if data.get("type") in node_types:
            content = data.get("text") if data.get("type")!="Section" else (data.get("section_heading") or "")
            docs.append((n, content))
    N = len(docs)
    df = collections.Counter()
    toks_per_doc = {}
    for nid, content in docs:
        toks = set(tokenize(content))
        toks_per_doc[nid] = toks
        for t in toks:
            df[t] += 1
    idf = {t: math.log((N + 1) / (df_t + 1)) + 1.0 for t, df_t in df.items()}
    return toks_per_doc, idf

def score_nodes_by_query(query: str, G: nx.DiGraph, toks_per_doc, idf, prefer_types=("Rule","Definition")):
    q_tokens = tokenize(query)
    base_scores = {}
    for nid, toks in toks_per_doc.items():
        overlap = set(q_tokens) & toks
        s = sum(idf.get(t, 0.0) for t in overlap)
        if s > 0:
            ntype = G.nodes[nid].get("type")
            if ntype in prefer_types: s *= 1.15
            base_scores[nid] = s
    return base_scores

def subgraph_by_doc(G: nx.DiGraph, doc_id: str) -> nx.DiGraph:
    if not doc_id: return G
    doc_node = f"doc::{doc_id}"
    if not G.has_node(doc_node):
        return nx.DiGraph()  # empty
    allowed = set([doc_node])
    queue = [doc_node]
    while queue:
        cur = queue.pop(0)
        for nb in list(G.successors(cur)) + list(G.predecessors(cur)):
            if nb not in allowed:
                allowed.add(nb)
                queue.append(nb)
    return G.subgraph(allowed).copy()

def graphrag_retrieve(G: nx.DiGraph, query: str, top_k=8, hops=1, pr_alpha=0.15, restrict_doc_id=None):
    H_full = subgraph_by_doc(G, restrict_doc_id)
    if H_full.number_of_nodes() == 0:
        return []

    toks_per_doc, idf = build_inverted_index(H_full)
    base = score_nodes_by_query(query, H_full, toks_per_doc, idf)

    if not base:
        cands = [n for n, d in H_full.nodes(data=True) if d.get("type") in {"Rule","Definition"}]
        scores = {n: fuzz_sim(query, H_full.nodes[n].get("text","")) for n in cands}
        seeds = dict(sorted(scores.items(), key=lambda x: -x[1])[:max(5, top_k)])
    else:
        seeds = dict(sorted(base.items(), key=lambda x: -x[1])[:max(5, top_k)])

    nodeset = set(seeds.keys())
    frontier = set(seeds.keys())
    for _ in range(hops):
        newf = set()
        for n in frontier:
            newf.update(list(H_full.predecessors(n)))
            newf.update(list(H_full.successors(n)))
        frontier = newf - nodeset
        nodeset |= frontier

    H = H_full.subgraph(nodeset).copy()

    # Personalized PageRank
    try:
        personalization = {n: float(seeds.get(n, 0.0)) for n in H.nodes()}
        ssum = sum(personalization.values()) or 1.0
        personalization = {n: v/ssum for n, v in personalization.items()}
        pr = nx.pagerank(H, alpha=1.0 - pr_alpha, personalization=personalization, max_iter=200)
    except Exception:
        pr = {n: 0.0 for n in H.nodes()}
        for n in seeds: pr[n] = 1.0 / len(seeds)

    # Combine base + PageRank; prefer Rule/Definition
    combined = {}
    for n in H.nodes():
        base_s = base.get(n, 0.0)
        pr_s = pr.get(n, 0.0)
        ntype = H.nodes[n].get("type")
        type_w = 1.2 if ntype in {"Rule","Definition"} else 1.0
        combined[n] = type_w * (0.7 * base_s + 0.3 * pr_s)

    ranked = sorted(combined.items(), key=lambda x: -x[1])
    def torder(n):
        t = H.nodes[n].get("type")
        return {"Rule":0,"Definition":1,"Section":2,"Document":3}.get(t,9)
    ranked_nodes = [n for n,_ in ranked]
    ranked_nodes = sorted(ranked_nodes, key=torder)
    top_nodes = ranked_nodes[:top_k]

    out = []
    for n in top_nodes:
        d = H.nodes[n]
        if d.get("type") in {"Rule","Definition","Section"}:
            txt = d.get("text") if d.get("type")!="Section" else (d.get("section_heading") or "")
            out.append({
                "node_id": n,
                "type": d.get("type"),
                "text": txt,
                "document_id": d.get("document_id"),
                "section_heading": d.get("section_heading"),
                "section_number": d.get("section_number"),
                "section_index": d.get("section_index"),
                "score": round(combined.get(n,0.0), 6),
            })
    return out

# =========================
# OpenAI answer (optional)
# =========================
def openai_answer(query: str, contexts: List[Dict[str,Any]], model_name: str = "gpt-4o-mini") -> str:
    api_key = os.getenv("OPENAI_API_KEY") or st.session_state.get("OPENAI_API_KEY")
    if not api_key:
        return "OpenAI API key not set. Enter it in the sidebar or set OPENAI_API_KEY env var."

    try:
        from openai import OpenAI
    except Exception:
        return "openai package not installed. Run: pip install openai"

    client = OpenAI(api_key=api_key)

    ctx = "\n".join([f"[{i+1}] ({c['type']}) {c['text']}" for i, c in enumerate(contexts)])
    sysmsg = ("You answer strictly using the provided context. Quote verbatim where possible. "
              "If the answer is missing from the context, say so explicitly.")
    prompt = f"Context:\n{ctx}\n\nQuestion: {query}\nAnswer:"

    try:
        resp = client.chat.completions.create(
            model=model_name,
            temperature=0.0,
            messages=[{"role":"system","content":sysmsg},{"role":"user","content":prompt}]
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"[OpenAI error] {e}"

# =========================
# Streamlit UI
# =========================
st.set_page_config(page_title="GraphRAG (from JSON) — Local", layout="wide")

st.title("GraphRAG (from JSON) — Local, No DB")

with st.sidebar:
    st.header("1) Data Source")
    uploaded = st.file_uploader("Upload extracted JSON (e.g., azure_search_upload.json)", type=["json"])
    path = st.text_input("…or path to JSON on disk", value="")
    use_cross_refs = st.checkbox("Add Rule→Definition REFERENCES edges", value=True)

    st.header("2) Retrieval Settings")
    top_k = st.slider("Top-K items", min_value=3, max_value=30, value=10, step=1)
    hops = st.slider("Graph expansion hops", min_value=0, max_value=3, value=1, step=1)
    pr_alpha = st.slider("PageRank teleport prob (0.15≈classic)", min_value=0.05, max_value=0.5, value=0.15, step=0.05)

    st.header("3) OpenAI (optional)")
    use_llm = st.checkbox("Use OpenAI LLM for final answer", value=False)
    if use_llm:
        _k = st.text_input("OpenAI API Key (kept in session only)", type="password", value=os.getenv("OPENAI_API_KEY",""))
        if _k:
            st.session_state["OPENAI_API_KEY"] = _k
        model_name = st.text_input("Model name", value="gpt-4o-mini")
    else:
        model_name = "gpt-4o-mini"

# Load items
items = None
if uploaded is not None:
    try:
        items = load_items_from_bytes(uploaded.getvalue())
    except Exception as e:
        st.error(f"Failed to load uploaded JSON: {e}")
elif path:
    try:
        items = load_items_from_path(path)
    except Exception as e:
        st.error(f"Failed to load JSON from path: {e}")

if items is None:
    st.info("Upload or specify a JSON path to begin.")
    st.stop()

st.success(f"Loaded {len(items)} items from JSON.")

# Build graph
built = build_graph_from_items(items, add_cross_refs=use_cross_refs)
G = built["graph"]
doc_ids = built["doc_ids"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Nodes", G.number_of_nodes())
c2.metric("Edges", G.number_of_edges())
c3.metric("Documents", len(doc_ids))
c4.metric("Rule/Def nodes", sum(1 for _,d in G.nodes(data=True) if d.get("type") in {"Rule","Definition"}))

st.divider()

# Query UI
st.subheader("Ask a question")
query = st.text_input("Your question", value="What must the Trustee establish on the Closing Date?")
doc_filter = st.selectbox("Restrict to a single document (optional)", options=["(All documents)"] + doc_ids, index=0)

if st.button("Retrieve"):
    st.write("Running GraphRAG retrieval…")
    restrict_id = None if doc_filter == "(All documents)" else doc_filter
    ctx = graphrag_retrieve(G, query, top_k=top_k, hops=hops, pr_alpha=pr_alpha, restrict_doc_id=restrict_id)

    if not ctx:
        st.warning("No relevant context found. Try increasing Top-K or Hops.")
    else:
        st.write(f"### Retrieved context ({len(ctx)})")
        st.dataframe([{k:v for k,v in it.items() if k in ("type","document_id","section_heading","section_number","score","text")} for it in ctx])

        st.write("### Answer")
        if use_llm:
            ans = openai_answer(query, ctx, model_name=model_name)
            st.write(ans)
        else:
            # Deterministic, extractive-style
            lines = [f"Q: {query}", "", "Top supporting items:"]
            for it in ctx:
                where = it.get("section_heading") or it.get("document_id") or ""
                lines.append(f"- {it['type']} [{where}]: {it['text']}")
            lines.append("")
            lines.append("Answer (based on items above): Review the listed rules/definitions. "
                         "For a fluent summary, enable 'Use OpenAI LLM'.")
            st.code("\n".join(lines), language="markdown")

st.divider()

# Downloads
st.subheader("Download graph data")
nodes = [{"id": n, **G.nodes[n]} for n in G.nodes]
edges = [{"src": u, "dst": v, **G.edges[(u,v)]} for (u,v) in G.edges]

st.download_button("Download nodes.json", data=json.dumps(nodes, indent=2).encode("utf-8"), file_name="nodes.json", mime="application/json")
st.download_button("Download edges.json", data=json.dumps(edges, indent=2).encode("utf-8"), file_name="edges.json", mime="application/json")