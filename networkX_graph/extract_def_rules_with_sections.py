import os, re, json, argparse, hashlib, unicodedata
from typing import List, Dict, Any

RULE_MARKERS = [r'\bshall\b', r'\bmust\b', r'\bwill\b', r'\brequired\b', r'\bentitled\b', r'\bshall not\b', r'\bmay not\b', r'\bshould\b']
DEF_MARKERS   = [r'\bmeans\b', r'\bis defined as\b']

def normalize_ws(t: str) -> str:
    t = unicodedata.normalize("NFKC", t or "")
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\r\n?', '\n', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()

def parse_section_number(heading: str):
    m = re.search(r'^Section\s+([0-9]+(?:\.[0-9]+)*(?:\([a-zA-Z0-9]+\))?)', heading, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r'^ARTICLE\s+([IVXLC]+)\b', heading, re.IGNORECASE)
    return m.group(1).upper() if m else None

def slice_sections(text: str, include_articles: bool) -> List[Dict[str, Any]]:
    text = normalize_ws(text)
    pats = [r'(?m)^(Section\s+\d+(?:\.\d+)*(?:\([a-zA-Z0-9]+\))?(?:\.)?\s+.*)$']
    if include_articles:
        pats.append(r'(?m)^(ARTICLE\s+[IVXLC]+\b.*)$')
    matches = []
    for p in pats:
        matches.extend(re.finditer(p, text))
    matches.sort(key=lambda m: m.start())
    if not matches:
        return [{"heading":"DOCUMENT", "body":text, "section_number":None}]
    secs = []
    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        body = text[start:end].strip()
        secs.append({"heading": heading, "body": body, "section_number": parse_section_number(heading)})
    return secs

def sentence_candidates(body: str) -> List[str]:
    b = re.sub(r'\s*\n\s*', ' ', body)
    parts = re.split(r'(?<=[.])\s+(?=[A-Z(“"\'\[])', b)
    return [p.strip() for p in parts if p.strip()]

def clean_sentence(s: str) -> str:
    s = normalize_ws(s)
    return re.sub(r'^\(?[ivx]+\)|^\(?[a-z]\)|^\d+[\.\)]|^[•\-–]\s*', '', s, flags=re.IGNORECASE).strip()

def extract_rules_from_section(body: str) -> List[str]:
    sentences = sentence_candidates(body) or [body]
    reg = re.compile('(' + '|'.join(RULE_MARKERS) + ')', re.IGNORECASE)
    out, seen = [], set()
    for s in sentences:
        if reg.search(s):
            c = clean_sentence(s)
            k = c.lower()
            if k not in seen:
                seen.add(k)
                out.append(c)
    return out

def extract_definitions_from_section(body: str) -> List[str]:
    sentences = sentence_candidates(body) or [body]
    reg = re.compile('(' + '|'.join(DEF_MARKERS) + ')', re.IGNORECASE)
    out, seen = [], set()
    for s in sentences:
        if reg.search(s):
            c = clean_sentence(s)
            k = c.lower()
            if k not in seen:
                seen.add(k)
                out.append(c)
    return out

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

def process_document(doc_id: str, text: str, include_articles: bool):
    items = []
    sections = slice_sections(text, include_articles)
    for sidx, sec in enumerate(sections):
        rules = extract_rules_from_section(sec["body"])
        defs  = extract_definitions_from_section(sec["body"])
        for ridx, r in enumerate(rules):
            items.append({
                "id": stable_id(doc_id, f"sec{sidx:03d}", "rule", str(ridx)),
                "type": "Rule",
                "text": r,
                "document_id": doc_id,
                "section_heading": sec["heading"],
                "section_number": sec["section_number"],
                "section_index": sidx,
                "item_index": ridx
            })
        for didx, d in enumerate(defs):
            items.append({
                "id": stable_id(doc_id, f"sec{sidx:03d}", "def", str(didx)),
                "type": "Definition",
                "text": d,
                "document_id": doc_id,
                "section_heading": sec["heading"],
                "section_number": sec["section_number"],
                "section_index": sidx,
                "item_index": didx
            })
    return items

def load_texts_from_dir(input_dir: str) -> Dict[str, str]:
    out = {}
    for fn in sorted(os.listdir(input_dir)):
        if not fn.lower().endswith(".txt"): continue
        path = os.path.join(input_dir, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                txt = f.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="latin-1") as f:
                txt = f.read()
        out[fn] = txt
    return out

def main():
    print ("raghu")
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-json", default="azure_search_upload.json")
    ap.add_argument("--include-articles", action="store_true")
    args = ap.parse_args()
    texts = load_texts_from_dir("C:\\Users\\admin_user\\rkcheli\\graphRag\\txts")
    if not texts:
        return
    all_items = []
    for doc_id, text in texts.items():
        if doc_id.lower().endswith("definitions.txt"):
            sections = slice_sections(text, args.include_articles)
            for sidx, sec in enumerate(sections):
                defs = extract_definitions_from_section(sec["body"])
                for didx, d in enumerate(defs):
                    all_items.append({
                        "id": stable_id(doc_id, f"sec{sidx:03d}", "def", str(didx)),
                        "type": "Definition",
                        "text": d,
                        "document_id": doc_id,
                        "section_heading": sec["heading"],
                        "section_number": sec["section_number"],
                        "section_index": sidx,
                        "item_index": didx
                    })
            print(f"[OK] {doc_id}: definitions={len(all_items)} total")
        elif doc_id.lower().endswith("waterfall.txt"):
            sections = slice_sections(text, args.include_articles)
            for sidx, sec in enumerate(sections):
                rules = extract_rules_from_section(sec["body"])
                for ridx, r in enumerate(rules):
                    all_items.append({
                        "id": stable_id(doc_id, f"sec{sidx:03d}", "rule", str(ridx)),
                        "type": "Rule",
                        "text": r,
                        "document_id": doc_id,
                        "section_heading": sec["heading"],
                        "section_number": sec["section_number"],
                        "section_index": sidx,
                        "item_index": ridx
                    })
            print(f"[OK] {doc_id}: rules={len(all_items)} total")
        else:
            print(f"[SKIP] {doc_id}: not definitions.txt or waterfall.txt")
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    print(f"[DONE] Wrote {len(all_items)} items -> {args.output_json}")

if __name__ == "__main__":
    main()