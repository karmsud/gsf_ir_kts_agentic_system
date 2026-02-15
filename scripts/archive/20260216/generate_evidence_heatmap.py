import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

# Import normalize_text and rules from scorer for consistency
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.score_queries import parse_evidence_rules, evaluate_term_rule, evaluate_regex_rule, normalize_text

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

SCENARIOS = {
    "v1": {
        "ledger": ROOT / "data/evidence_ledger_after_v1.json",
        "name": "V1 Isolated",
    },
    "v2": {
        "ledger": ROOT / "data/evidence_ledger_after_v2.json",
        "name": "V2 Isolated",
    },
    "mixed": {
        "ledger": ROOT / "data/evidence_ledger_after_mixed.json",
        "name": "Mixed Realism",
    },
}

def check_content_matches(content: str, rules: Dict[str, Any]) -> bool:
    """Return True if content satisfies ALL evidence rules."""
    text = normalize_text(content)
    
    # Check all_of terms
    for term in rules.get("all_of_terms", []):
        if not evaluate_term_rule(term, text):
            return False
            
    # Check all_of regex
    for regex in rules.get("all_of_regex", []):
        if not evaluate_regex_rule(regex, text):
            return False
            
    # Check any_of groups (simplified structure based on scorer output)
    # The ledger might store raw requirements in a different format than parsed rules
    # But here we pass the PARSED rules object from parse_evidence_rules
    
    # Note from previous turn: parser returns any_of_terms and any_of_regex lists
    any_hits = []
    if rules.get("any_of_terms"):
        any_hits.extend(evaluate_term_rule(t, text) for t in rules["any_of_terms"])
    if rules.get("any_of_regex"):
        any_hits.extend(evaluate_regex_rule(r, text) for r in rules["any_of_regex"])
        
    if (rules.get("any_of_terms") or rules.get("any_of_regex")) and not any(any_hits):
        return False
        
    return True

def analyze_full_doc(file_path: str, rules: Dict[str, Any]) -> bool:
    """Load file from disk and check if evidence exists anywhere in it."""
    path = Path(file_path)
    if not path.exists():
        # Try relative to repo root if absolute fail
        path = ROOT / file_path
        if not path.exists():
            return False
            
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        return check_content_matches(content, rules)
    except Exception:
        return False

def generate_heatmap_md(audit_dir: Path):
    lines = []
    lines.append("# EVIDENCE FAILURE HEATMAP")
    lines.append("")
    lines.append("## Classification Key")
    lines.append("- **Type A (Not Found)**: Evidence missing from excerpts AND full text (or file unreachable). Grounding impossible.")
    lines.append("- **Type B (Serialization Gap)**: Evidence present in full text file, but missing from retrieved chunk excerpt/content.")
    lines.append("- **Type C (Chunking Gap)**: Evidence present in full doc, but requires combining multiple chunks to satisfy (split across boundaries).")
    lines.append("- **Type D (Extraction/Data Gap)**: Evidence absent from the doc entirely (or extraction failed to see it).")
    lines.append("")
    
    stats = {"A": 0, "B": 0, "C": 0, "D": 0}

    for key, cfg in SCENARIOS.items():
        # Prefer audit dir ledgers if available (normalized schema)
        normalized_ledger = audit_dir / f"evidence_ledger_after_{key}.json"
        
        if normalized_ledger.exists():
            ledger_path = normalized_ledger
            print(f"Using normalized ledger: {ledger_path}")
        elif cfg["ledger"].exists():
            ledger_path = cfg["ledger"]
            print(f"Using raw ledger: {ledger_path}")
        else:
            lines.append(f"## {cfg['name']} (Ledger missing)")
            continue
            
        with open(ledger_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        queries = data.get("queries", [])
        failures = [q for q in queries if not q.get("overall_evidence_found", False)]
        
        lines.append(f"## {cfg['name']}")
        if not failures:
            lines.append("- All queries satisfied evidence requirements.")
            lines.append("")
            continue
            
        lines.append(f"- **Total Failures**: {len(failures)}")
        lines.append("")
        lines.append("| Query ID | Type | Missing Term | Top Chunk ID | Doc Path | Analysis |")
        lines.append("| :--- | :---: | :--- | :--- | :--- | :--- |")
        
        for q in failures:
            # 1. Parse rules
            # We need to reconstruction 'golden' style dict for parse_evidence_rules
            # The ledger has "raw_evidence_requirements" which matches golden structure usually
            reqs = q.get("raw_evidence_requirements", {})
            # Ensure keys map correctly if differ
            parsed_rules = parse_evidence_rules(reqs)
            
            top_chunks = q.get("top5_chunks", [])
            if not top_chunks:
                lines.append(f"| {q['query_id']} | A | (No chunks) | - | - | Retrieval failed completely |")
                stats["A"] += 1
                continue
                
            # Check the best chunk (Rank 1) validation
            best_chunk = top_chunks[0]
            ptr = best_chunk.get("pointer_to_full_text")
            
            # Analyze
            # Check full text if pointer exists
            in_full_doc = False
            if ptr:
                in_full_doc = analyze_full_doc(ptr, parsed_rules)
            
            # Since overall_evidence_found is False, we know NO SINGLE chunk satisfied it.
            # But maybe multiple chunks together do?
            # Or maybe the doc has it but no chunk has it.
            
            # Type detection
            if not ptr:
                # No pointer -> can't verify full text -> Type A (default assumption if invalid source)
                # But actually, chunker usually provides source. If missing, it's problematic.
                fail_type = "A"
                note = "No source pointer available"
            elif in_full_doc:
                # It IS in the document. Why didn't we match?
                # 1. Is it in the chunk content provided in ledger?
                # We know scorer said NO.
                # So either scorer bug (unlikely with our fixes) OR it's missing from chunk content.
                
                # Check if it was "split". 
                # Does the combination of all retrieved chunks from this doc satisfy it?
                # Gather content from all top 5 chunks for this doc
                doc_id = best_chunk.get("doc_id")
                combined_content = ""
                for c in top_chunks:
                    if c.get("doc_id") == doc_id:
                        combined_content += "\n" + (c.get("content_excerpt_head", "") + c.get("content_excerpt_tail", ""))
                
                if check_content_matches(combined_content, parsed_rules):
                    fail_type = "C" # Split across retrieved chunks
                    note = "Present in combined retrieved chunks"
                else:
                    fail_type = "B" # In doc, but not in retrieved chunks (serialization/windowing gap)
                    note = "Found in source file, missing from chunk text"
            else:
                # Not in full doc (or at least our text extraction of it)
                fail_type = "D" 
                note = "Term not found in source file text"

            # Determine missing term for display
            # Just grab the first one that fails in the top chunk
            missing = []
            content_preview = best_chunk.get("content_excerpt_head", "")
            text_preview = normalize_text(content_preview)
            for t in parsed_rules.get("all_of_terms", []):
                if not evaluate_term_rule(t, text_preview):
                    missing.append(t)
            
            missing_str = ", ".join(missing[:3]) if missing else "Complex/Regex"
            
            lines.append(f"| {q['query_id']} | **{fail_type}** | `{missing_str}` | {best_chunk.get('chunk_id')} | `{str(ptr)[-30:] if ptr else 'None'}` | {note} |")
            stats[fail_type] += 1
            
        lines.append("")

    lines.append("## Summary Statistics")
    lines.append(f"- **Type A (Not Found/No Pointer)**: {stats['A']}")
    lines.append(f"- **Type B (Serialization Gap)**: {stats['B']}")
    lines.append(f"- **Type C (Chunking Gap)**: {stats['C']}")
    lines.append(f"- **Type D (Extraction/Data Gap)**: {stats['D']}")
    
    # Write to audit dir
    out_path = audit_dir / "EVIDENCE_FAILURE_HEATMAP.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated {out_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("audit_dir", help="Path to audit artifacts directory")
    args = parser.parse_args()
    
    generate_heatmap_md(Path(args.audit_dir))
