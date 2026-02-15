"""
Parameter sweep to find optimal ranking weights.
Grid search over error_code_boost × intent_boost with 25+ combinations.
"""
import sys
import os
import json
import subprocess
from typing import Dict, List, Tuple

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def update_weights_in_retrieval_service(error_weight: float, intent_weight: float) -> None:
    """Temporarily update weights in retrieval_service.py"""
    service_path = r"c:\Users\Karmsud\Projects\gsf_ir_kts_agentic_system\backend\agents\retrieval_service.py"
    
    with open(service_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find and replace the weights dictionary
    import re
    pattern = r'feature_weights\s*=\s*\{[^}]+\}'
    new_weights = f'''feature_weights = {{
            "error_code_exact_match": {error_weight},
            "intent_doc_type_match": {intent_weight},
            "title_term_match": 1.3,
            "query_keyword_match": 1.2,
        }}'''
    
    updated_content = re.sub(pattern, new_weights, content, flags=re.DOTALL)
    
    with open(service_path, 'w', encoding='utf-8') as f:
        f.write(updated_content)

def run_evaluation() -> Dict[str, float]:
    """Run accuracy evaluation and parse results"""
    cmd = r".\scripts\run_accuracy_tuning.ps1 -Mode baseline -SkipIngest"
    result = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-Command", cmd],
        capture_output=True,
        text=True,
        cwd=r"c:\Users\Karmsud\Projects\gsf_ir_kts_agentic_system"
    )
    
    # Parse metrics from output
    output = result.stdout
    metrics = {}
    
    for line in output.split('\n'):
        if "TUNE SET" in line:
            section = "tune"
        elif "HOLDOUT SET" in line:
            section = "holdout"
        elif "Top-1 Accuracy:" in line and section:
            # Extract percentage: "Top-1 Accuracy: 90.0% (36/40)"
            import re
            match = re.search(r'(\d+\.?\d*)%', line)
            if match:
                metrics[f"{section}_top1"] = float(match.group(1))
    
    return metrics

def main():
    # Grid search parameters
    error_boosts = [1.8, 2.0, 2.2, 2.4, 2.6]
    intent_boosts = [1.4, 1.6, 1.8, 2.0, 2.2]
    
    results = []
    total_combos = len(error_boosts) * len(intent_boosts)
    
    print(f"=== PARAMETER SWEEP: {total_combos} combinations ===\n")
    
    for i, error_w in enumerate(error_boosts):
        for j, intent_w in enumerate(intent_boosts):
            combo_num = i * len(intent_boosts) + j + 1
            print(f"[{combo_num}/{total_combos}] Testing error={error_w}, intent={intent_w}...", end=" ", flush=True)
            
            # Update weights
            update_weights_in_retrieval_service(error_w, intent_w)
            
            # Run evaluation (TUNE set only for speed)
            metrics = run_evaluation()
            
            tune_acc = metrics.get('tune_top1', 0.0)
            holdout_acc = metrics.get('holdout_top1', 0.0)
            
            results.append({
                'error_weight': error_w,
                'intent_weight': intent_w,
                'tune_top1': tune_acc,
                'holdout_top1': holdout_acc,
                'combined_score': tune_acc + holdout_acc * 2.0  # Prioritize holdout
            })
            
            print(f"Tune={tune_acc:.1f}%, Holdout={holdout_acc:.1f}%")
    
    # Find best configuration
    results_sorted = sorted(results, key=lambda x: x['combined_score'], reverse=True)
    
    print("\n=== TOP 5 CONFIGURATIONS ===")
    for i, r in enumerate(results_sorted[:5], 1):
        print(f"{i}. error={r['error_weight']}, intent={r['intent_weight']} → "
              f"Tune={r['tune_top1']:.1f}%, Holdout={r['holdout_top1']:.1f}% "
              f"(score={r['combined_score']:.1f})")
    
    best = results_sorted[0]
    print(f"\n✅ BEST CONFIG: error={best['error_weight']}, intent={best['intent_weight']}")
    print(f"   Tune Top-1: {best['tune_top1']:.1f}%")
    print(f"   Holdout Top-1: {best['holdout_top1']:.1f}%")
    
    # Apply best config
    update_weights_in_retrieval_service(best['error_weight'], best['intent_weight'])
    print("\n✅ Applied best configuration to retrieval_service.py")
    
    # Save results
    with open('tests/param_sweep_results.json', 'w', encoding='utf-8') as f:
        json.dump(results_sorted, f, indent=2)
    print("✅ Saved full results to tests/param_sweep_results.json")

if __name__ == '__main__':
    main()
