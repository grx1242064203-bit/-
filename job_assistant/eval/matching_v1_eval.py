"""
匹配评测 v1 基线: 跑当前 8 维 scorer 对 48 个岗位打分
对比 ground truth relevance (0/1/2)
输出: Precision@10 / NDCG@10 / Recall@30 / Bad Case 分析
"""
import json
import sys
import math
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 修正路径:让 settings 指向 /workspace/job_assistant/data 而非 /opt/job_assistant/data
os.environ["DATA_DIR"] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

from scorer import score_job, DIMENSION_WEIGHTS
from models import UserProfile, KeywordTag
from test_scorer_linxuyan import FIT_DIRS_COMPLETE, build_profile


def load_evalset():
    with open("eval/evalset_matching.json", "r", encoding="utf-8") as f:
        return json.load(f)


def run_eval(evalset, label="v1"):
    """跑评测,返回结果列表(按分数降序)"""
    profile = build_profile(FIT_DIRS_COMPLETE)

    results = []
    for job_meta in evalset["jobs"]:
        # 构造 scorer 需要的 job dict
        job = {
            "position_title": job_meta["position_title"],
            "company_name": job_meta["company_name"],
            "job_category": job_meta["job_category"],
            "job_subcategory": job_meta["job_subcategory"],
            "hard_skills": job_meta["hard_skills"],
            "keywords": job_meta["hard_skills"],
            "soft_skills": "",
            "certifications": [],
            "languages": [],
            "min_education": job_meta.get("min_education", "") or "",
            "city": job_meta.get("city", "") or "",
            "major_category": job_meta.get("major_category", "") or "",
            "major_required": job_meta.get("major_required", "") or "",
            "industry": "互联网",
            "company_type": "民企",
        }
        job_meta_full = {**job_meta, **job}

        r = score_job(job, profile)
        results.append({
            "eval_id": job_meta["eval_id"],
            "company_name": job_meta["company_name"],
            "position_title": job_meta["position_title"],
            "job_subcategory": job_meta["job_subcategory"],
            "ground_truth": job_meta["ground_truth_relevance"],
            "ground_truth_label": job_meta["ground_truth_label"],
            "score": r["相关性评分"],
            "recommendation": r["综合推荐度"],
            "role_score": r["维度分"].get("role", 0),
            "hard_skill_score": r["维度分"].get("hard_skill", 0),
            "skill_score": r["维度分"].get("skill", 0),
            "education_score": r["维度分"].get("education", 0),
            "competitiveness_score": r["维度分"].get("competitiveness", 0),
            "major_score": r["维度分"].get("major", 0),
            "city_score": r["维度分"].get("city", 0),
            "company_pref_score": r["维度分"].get("company_preference", 0),
            "role_gated": r.get("方向门槛触发", False),
        })

    # 按分数降序
    results.sort(key=lambda x: -x["score"])
    return results


def compute_metrics(results, label="v1"):
    """计算 Precision@10 / NDCG@10 / Recall@30 / Hard Gate / Direction Mismatch"""
    n = len(results)
    top10 = results[:10]
    top30 = results[:30] if n >= 30 else results

    # Precision@10: Top-10 中 relevant(2) 数 / 10
    p10 = sum(1 for r in top10 if r["ground_truth"] >= 2) / 10

    # Precision@10 (含 partial): Top-10 中 relevant+partial 数 / 10
    p10_loose = sum(1 for r in top10 if r["ground_truth"] >= 1) / 10

    # NDCG@10
    def dcg(rels):
        s = 0
        for i, r in enumerate(rels):
            s += (2**r - 1) / math.log2(i + 2)
        return s

    actual_rels = [r["ground_truth"] for r in top10]
    ideal_rels = sorted([r["ground_truth"] for r in results], reverse=True)[:10]
    ndcg10 = dcg(actual_rels) / dcg(ideal_rels) if dcg(ideal_rels) > 0 else 0

    # Recall@30: Top-30 中 relevant 数 / 总 relevant 数
    total_relevant = sum(1 for r in results if r["ground_truth"] >= 2)
    top30_relevant = sum(1 for r in top30 if r["ground_truth"] >= 2)
    recall30 = top30_relevant / total_relevant if total_relevant > 0 else 0

    # Hard Gate Accuracy: Top-30 中硬门槛违规(学历不达标)的比例
    # 这里用 education_score == 0 作为代理
    hard_gate_violation = sum(1 for r in top30 if r["education_score"] == 0) / len(top30)

    # Direction Mismatch Rate: Top-10 中 role < 40 的比例
    dir_mismatch = sum(1 for r in top10 if r["role_score"] < 40) / 10

    # F3 泛技能刷分: Top-10 中 ground_truth=0 但 score > 60 的数量
    f3_cases = [r for r in top10 if r["ground_truth"] == 0 and r["score"] > 60]

    # F1 方向错配: Top-10 中 ground_truth=0 的数量
    f1_cases = [r for r in top10 if r["ground_truth"] == 0]

    metrics = {
        "label": label,
        "n_total": n,
        "n_relevant_2": total_relevant,
        "n_partial_1": sum(1 for r in results if r["ground_truth"] == 1),
        "n_irrelevant_0": sum(1 for r in results if r["ground_truth"] == 0),
        "precision_at_10": round(p10, 3),
        "precision_at_10_loose": round(p10_loose, 3),
        "ndcg_at_10": round(ndcg10, 3),
        "recall_at_30": round(recall30, 3),
        "hard_gate_violation_rate": round(hard_gate_violation, 3),
        "direction_mismatch_rate_top10": round(dir_mismatch, 3),
        "f3_skill_inflation_count": len(f3_cases),
        "f1_direction_mismatch_count": len(f1_cases),
    }
    return metrics


def print_report(results, metrics, label="v1"):
    print(f"\n{'='*70}")
    print(f"  匹配评测 {label} 报告")
    print(f"{'='*70}")

    print(f"\n📊 核心指标:")
    print(f"  Precision@10 (strict, relevant=2):  {metrics['precision_at_10']:.1%}  目标 >70%")
    print(f"  Precision@10 (loose,  >=partial):  {metrics['precision_at_10_loose']:.1%}")
    print(f"  NDCG@10:                            {metrics['ndcg_at_10']:.3f}  目标 >0.65")
    print(f"  Recall@30:                          {metrics['recall_at_30']:.1%}  目标 >80%")
    print(f"  Hard Gate 违规率(Top-30):           {metrics['hard_gate_violation_rate']:.1%}  目标 <5%")
    print(f"  方向错配率(Top-10):                 {metrics['direction_mismatch_rate_top10']:.1%}  目标 <10%")
    print(f"  F3 泛技能刷分数(Top-10):            {metrics['f3_skill_inflation_count']}")
    print(f"  F1 方向错配数(Top-10):              {metrics['f1_direction_mismatch_count']}")

    print(f"\n📋 样本分布:")
    print(f"  总岗位: {metrics['n_total']}")
    print(f"  relevant(2) 强相关:   {metrics['n_relevant_2']}")
    print(f"  partial(1) 部分相关:  {metrics['n_partial_1']}")
    print(f"  irrelevant(0) 不对口:  {metrics['n_irrelevant_0']}")

    print(f"\n🏆 Top-10 详情:")
    print(f"  {'#':<3} {'Score':>6} {'GT':<3} {'Label':<20} {'Role':>5} {'HardSk':>6} {'Skill':>5} {'Gate':<4} 公司-岗位")
    print(f"  {'-'*90}")
    for i, r in enumerate(results[:10]):
        gt = "✓" if r["ground_truth"] >= 2 else ("~" if r["ground_truth"] == 1 else "✗")
        gate = "🔒" if r["role_gated"] else ""
        print(f"  {i+1:<3} {r['score']:>6.1f} {gt:<3} {r['ground_truth_label']:<20} "
              f"{r['role_score']:>5.1f} {r['hard_skill_score']:>6.1f} {r['skill_score']:>5.1f} {gate:<4} "
              f"{r['company_name']}-{r['position_title'][:20]}")

    # Bad Case 分析
    print(f"\n⚠️ Bad Case 分析:")
    bad_cases = [r for r in results[:10] if r["ground_truth"] == 0]
    if bad_cases:
        print(f"  Top-10 中有 {len(bad_cases)} 个不对口岗位:")
        for r in bad_cases:
            print(f"    {r['eval_id']} score={r['score']:.1f} role={r['role_score']:.1f} "
                  f"skill={r['skill_score']:.1f} hard_sk={r['hard_skill_score']:.1f} "
                  f"| {r['company_name']}-{r['position_title']}({r['job_subcategory']})")
            # 诊断
            if r["skill_score"] > 30 and r["ground_truth"] == 0:
                print(f"      → 诊断: F3 泛技能刷分 (skill={r['skill_score']:.1f} 拉高总分)")
            if r["role_score"] >= 40 and r["ground_truth"] == 0:
                print(f"      → 诊断: F1 方向错配但 role gate 未触发")
    else:
        print(f"  ✅ Top-10 无不对口岗位")

    # 漏推分析
    missed = [r for r in results[10:] if r["ground_truth"] >= 2]
    if missed:
        print(f"\n📉 漏推的相关岗位(Top-10 之外): {len(missed)} 个")
        for r in missed[:5]:
            rank = results.index(r) + 1
            print(f"  排名#{rank} score={r['score']:.1f} | {r['company_name']}-{r['position_title']}({r['job_subcategory']})")


if __name__ == "__main__":
    evalset = load_evalset()
    results = run_eval(evalset, "v1")
    metrics = compute_metrics(results, "v1")
    print_report(results, metrics, "v1(8维基线)")

    # 存报告
    report = {
        "label": "v1_baseline_8dim",
        "weights": DIMENSION_WEIGHTS,
        "metrics": metrics,
        "top10": [{k: v for k, v in r.items() if k != "ground_truth_label"} for r in results[:10]],
        "full_results": results,
    }
    with open("eval/matching_v1_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 报告已保存到 eval/matching_v1_report.json")
