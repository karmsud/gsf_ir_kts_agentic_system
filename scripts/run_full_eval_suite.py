
import os
import shutil
import subprocess
import json
import re
from pathlib import Path
import sys

# Configuration
SCENARIOS = [
    {
        "name": "V1 Isolated",
        "kb_path": "knowledge_base_v1",
        "corpora": ["kts_test_corpus"],
        "eval_script": "scripts/evaluate_v1.py",
        "golden_queries": "tests/golden_queries.json",
        "results_dir": "tests/accuracy_tuning_output",
        "report_file": "docs/EVAL_REPORT_V1_ISOLATED.md"
    },
    {
        "name": "V2 Isolated",
        "kb_path": "knowledge_base_v2",
        "corpora": ["kts_synthetic_corpus_v2"],
        "eval_script": "scripts/evaluate_v2.py",
        "golden_queries": "tests/golden_queries_v2.json",
        "results_dir": "tests/accuracy_tuning_output_v2",
        "report_file": "docs/EVAL_REPORT_V2_ISOLATED.md"
    },
    {
        "name": "Mixed (Realism)",
        "kb_path": "knowledge_base_mixed",
        "corpora": ["kts_test_corpus", "kts_synthetic_corpus_v2"],
        "eval_script": "scripts/evaluate_v2.py", # Evaluating V2 queries in environment
        "golden_queries": "tests/golden_queries_v2.json",
        "results_dir": "tests/accuracy_tuning_output_v2",
        "report_file": "docs/EVAL_REPORT_MIXED.md"
    }
]

def run_command(cmd, env=None):
    print(f">> Running: {cmd}")
    env_vars = os.environ.copy()
    if env:
        env_vars.update(env)
    
    # Python on Windows needs explicit python command usually, assuming 'python' is in path
    result = subprocess.run(cmd, check=False, shell=True, env=env_vars, capture_output=True, text=True)
    if result.returncode != 0 and result.returncode != 1: # score_queries returns 1 on failure to meet targets
        print(f"WARN: Command failed with code {result.returncode}")
        print(result.stderr)
    return result.stdout + "\n" + result.stderr

def parse_metrics(output, scenario_name):
    # Extract simple metrics for summary
    metrics = {
        "scenario": scenario_name,
        "top1": "N/A",
        "top3": "N/A",
        "evidence": "N/A", 
        "holdout_top1": "N/A"
    }
    
    # Regex for standard score report format
    # Top-1 Accuracy: 98.0% (49/50)
    # Evidence Found: 82.0%
    # Holdout Top-1 ...: 100.0%
    
    overall_pattern = r"--- OVERALL .*?Top-1 Accuracy: ([\d.]+)%.*?Top-3 Accuracy: ([\d.]+)%.*?Evidence Found: ([\d.]+)%"
    holdout_pattern = r"--- HOLDOUT SET .*?Top-1 Accuracy: ([\d.]+)%"
    
    m_overall = re.search(overall_pattern, output, re.DOTALL)
    if m_overall:
        metrics["top1"] = m_overall.group(1) + "%"
        metrics["top3"] = m_overall.group(2) + "%"
        metrics["evidence"] = m_overall.group(3) + "%"
        
    m_holdout = re.search(holdout_pattern, output, re.DOTALL)
    if m_holdout:
        metrics["holdout_top1"] = m_holdout.group(1) + "%"
        
    return metrics

def main():
    summary_metrics = []
    
    for scenario in SCENARIOS:
        print(f"\n{'='*60}\nSTARTING SCENARIO: {scenario['name']}\n{'='*60}")
        
        kb_path = scenario["kb_path"]
        env = {"KTS_KB_PATH": kb_path}
        
        # 1. Clean KB
        if Path(kb_path).exists():
            print(f"Cleaning {kb_path}...")
            shutil.rmtree(kb_path)
        Path(kb_path).mkdir(parents=True, exist_ok=True)
        
        # 2. Crawl
        paths_arg = " ".join([f'--paths "{p}"' for p in scenario["corpora"]])
        run_command(f"python cli/main.py crawl {paths_arg}", env=env)
        
        # 3. Ingest
        run_command(f"python cli/main.py ingest", env=env)
        
        # 4. Evaluate (Generate Search Results)
        run_command(f"python {scenario['eval_script']}", env=env)
        
        # 5. Score
        results_file = Path(scenario["results_dir"]) / "search_results.json"
        score_cmd = f"python tests/score_queries.py {scenario['golden_queries']} {results_file}"
        score_output = run_command(score_cmd, env=env)
        
        # 6. Write Report
        report_content = f"# Evaluation Report: {scenario['name']}\n\n"
        report_content += f"**Date**: {subprocess.check_output('date /t', shell=True, text=True).strip()}\n"
        report_content += f"**Corpora**: {', '.join(scenario['corpora'])}\n"
        report_content += f"**Knowledge Base**: {kb_path}\n"
        report_content += f"**Query Pack**: {scenario['golden_queries']}\n\n"
        report_content += "## Raw Scoring Output\n\n```text\n"
        report_content += score_output
        report_content += "\n```\n"
        
        Path(scenario["report_file"]).write_text(report_content, encoding="utf-8")
        print(f"Report written to {scenario['report_file']}")
        
        # 7. Collect Metrics
        summary_metrics.append(parse_metrics(score_output, scenario["name"]))

    # Write Summary
    summary_path = "docs/EVAL_REPORT_SUMMARY.md"
    summary_md = "# Evaluation Summary Report\n\n"
    summary_md += "| Scenario | Corpus Mode | Top-1 Accuracy | Top-3 Accuracy | Evidence Found | Holdout Top-1 |\n"
    summary_md += "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
    
    for m in summary_metrics:
        # Infer corpus mode
        mode = "Mixed" if "Mixed" in m["scenario"] else "Isolated"
        summary_md += f"| **{m['scenario']}** | {mode} | {m['top1']} | {m['top3']} | {m['evidence']} | {m['holdout_top1']} |\n"
        
    Path(summary_path).write_text(summary_md, encoding="utf-8")
    print(f"\nSummary table written to {summary_path}")

if __name__ == "__main__":
    main()
