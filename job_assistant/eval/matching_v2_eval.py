"""
匹配评测 v2: 6 维缩减版 (删除 skill + company_preference)
对比 v1(8维) 基线
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATA_DIR"] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

import scorer
from eval.matching_v1_eval import load_evalset, run_eval, compute_metrics, print_report

# v2 权重: 删除 skill + company_preference, 重分配
V2_WEIGHTS = {
    # 删除: "skill": 0.10,
    # 删除: "company_preference": 0.10,
    "hard_skill": 0.20,       # 0.15 → 0.20 (+0.05, 吸收 skill 精确技能信号)
    "education": 0.15,        # 不变
    "major": 0.10,            # 不变
    "city": 0.05,             # 不变
    "role": 0.20,             # 0.15 → 0.20 (+0.05, 强化方向对齐)
    "competitiveness": 0.30,  # 0.20 → 0.30 (+0.10, 吸收 company_preference 公司对齐)
}


def run_v2_eval():
    # 保存原始权重
    original_weights = scorer.DIMENSION_WEIGHTS.copy()

    # 替换为 v2 权重
    scorer.DIMENSION_WEIGHTS = V2_WEIGHTS.copy()
    print(f"v2 权重已替换: {V2_WEIGHTS}")
    print(f"  删除维度: skill, company_preference")
    print(f"  权重变化: competitiveness 0.20→0.30, hard_skill 0.15→0.20, role 0.15→0.20")

    evalset = load_evalset()
    results = run_eval(evalset, "v2")
    metrics = compute_metrics(results, "v2")
    print_report(results, metrics, "v2(6维缩减)")

    # 恢复原始权重
    scorer.DIMENSION_WEIGHTS = original_weights

    # 存报告
    report = {
        "label": "v2_reduced_6dim",
        "weights": V2_WEIGHTS,
        "removed": ["skill", "company_preference"],
        "metrics": metrics,
        "top10": [{k: v for k, v in r.items() if k != "ground_truth_label"} for r in results[:10]],
        "full_results": results,
    }
    with open("eval/matching_v2_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 报告已保存到 eval/matching_v2_report.json")

    return metrics


if __name__ == "__main__":
    v2_metrics = run_v2_eval()

    # 对比 v1
    with open("eval/matching_v1_report.json", "r") as f:
        v1 = json.load(f)

    print(f"\n{'='*70}")
    print(f"  v1 vs v2 对比")
    print(f"{'='*70}")
    print(f"  {'指标':<35} {'v1(8维)':<12} {'v2(6维)':<12} {'变化':<10}")
    print(f"  {'-'*70}")
    for k in v1["metrics"]:
        if k in ("label", "n_total", "n_relevant_2", "n_partial_1", "n_irrelevant_0"):
            continue
        old = v1["metrics"][k]
        new = v2_metrics[k]
        diff = new - old
        arrow = "↑" if diff > 0 else ("↓" if diff < 0 else "→")
        print(f"  {k:<35} {old:<12} {new:<12} {arrow} {abs(diff):.3f}")
