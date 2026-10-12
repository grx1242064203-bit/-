"""
v2 优化量化测试

v1(当前): role gate 阈值 40, competitiveness 无硬门槛, major 权重 0.10
v2(优化): role gate 阈值 60, competitiveness 硬门槛(diff>60→cap 50), major 权重 0.15

三个场景基线 vs v2 量化对比
"""
import json
import sys
import os
import copy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATA_DIR"] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

import scorer
from scorer import score_job, DIMENSION_WEIGHTS
from models import UserProfile, KeywordTag
import job_tree


# ============================================================
# 三个用户画像(复用 scenario_2_3_test + major_ab_test)
# ============================================================
def build_accounting_profile():
    keywords = [
        KeywordTag(kw="会计", standard="会计", category="hard_skill", weight=3.0),
        KeywordTag(kw="财务分析", standard="财务分析", category="hard_skill", weight=2.5),
        KeywordTag(kw="Excel", standard="Excel", category="hard_skill", weight=2.5),
        KeywordTag(kw="财务建模", standard="财务建模", category="hard_skill", weight=2.0),
        KeywordTag(kw="审计", standard="审计", category="hard_skill", weight=2.0),
        KeywordTag(kw="税务", standard="税务", category="hard_skill", weight=2.0),
        KeywordTag(kw="SQL", standard="SQL", category="hard_skill", weight=1.5),
        KeywordTag(kw="Python", standard="Python", category="hard_skill", weight=1.5),
        KeywordTag(kw="数据分析", standard="数据分析", category="hard_skill", weight=2.0),
        KeywordTag(kw="ERP", standard="ERP", category="hard_skill", weight=2.0),
        KeywordTag(kw="本科", standard="本科", category="education", weight=1.0),
        KeywordTag(kw="上海立信会计金融学院", standard="上海立信会计金融学院", category="education", weight=2.0),
    ]
    fit_dirs = [
        {"direction": "财务", "cat_key": "corporate", "sub_key": "finance_acc",
         "category_name": "职能", "weight": 0.95, "evidence": "会计学专业+财务分析实习"},
        {"direction": "审计", "cat_key": "corporate", "sub_key": "audit",
         "category_name": "职能", "weight": 0.85, "evidence": "审计课程+会计师事务所实习"},
        {"direction": "投行", "cat_key": "finance", "sub_key": "ibd",
         "category_name": "金融", "weight": 0.60, "evidence": "金融建模课程+券商投行部实习"},
        {"direction": "量化研究", "cat_key": "finance", "sub_key": "quant_research",
         "category_name": "金融", "weight": 0.40, "evidence": "Python+数据分析+统计学课程"},
    ]
    return UserProfile(
        role="财务/会计", degree="本科", major="会计学",
        graduation_year="2026", graduation_date="2026-06",
        target_cities=["上海", "北京", "深圳", "杭州"],
        resume_text="", structured_keywords=keywords, fit_directions=fit_dirs,
        core_skills=["会计", "财务分析", "Excel", "财务建模", "审计", "税务", "SQL", "Python", "数据分析"],
        direction_keywords={"skill": ["会计", "财务分析", "Excel", "财务建模", "审计", "税务", "SQL", "Python"]},
    )


def build_weak_candidate():
    keywords = [
        KeywordTag(kw="Python", standard="Python", category="hard_skill", weight=2.0),
        KeywordTag(kw="C++", standard="C++", category="hard_skill", weight=2.0),
        KeywordTag(kw="数据结构", standard="数据结构", category="hard_skill", weight=1.5),
        KeywordTag(kw="算法", standard="算法", category="hard_skill", weight=1.5),
        KeywordTag(kw="MySQL", standard="MySQL", category="hard_skill", weight=1.5),
        KeywordTag(kw="本科", standard="本科", category="education", weight=1.0),
        KeywordTag(kw="某双非院校", standard="某双非院校", category="education", weight=1.0),
    ]
    fit_dirs = [
        {"direction": "后端开发", "cat_key": "development", "sub_key": "backend",
         "category_name": "开发", "weight": 0.90, "evidence": "Python+MySQL课程项目"},
        {"direction": "嵌入式软件", "cat_key": "development", "sub_key": "embedded_sw",
         "category_name": "开发", "weight": 0.70, "evidence": "C++课程+单片机课设"},
    ]
    return UserProfile(
        role="后端开发", degree="本科", major="计算机科学与技术",
        graduation_year="2026", graduation_date="2026-06",
        target_cities=["上海", "北京", "深圳", "杭州"],
        resume_text="", structured_keywords=keywords, fit_directions=fit_dirs,
        core_skills=["Python", "C++", "数据结构", "算法", "MySQL"],
        direction_keywords={"skill": ["Python", "C++", "数据结构", "算法", "MySQL"]},
    )


def build_embedded_user():
    keywords = [
        KeywordTag(kw="C++", standard="C++", category="hard_skill", weight=3.0),
        KeywordTag(kw="C", standard="C", category="hard_skill", weight=3.0),
        KeywordTag(kw="嵌入式", standard="嵌入式", category="hard_skill", weight=3.0),
        KeywordTag(kw="RTOS", standard="RTOS", category="hard_skill", weight=2.5),
        KeywordTag(kw="Linux", standard="Linux", category="hard_skill", weight=2.5),
        KeywordTag(kw="Python", standard="Python", category="hard_skill", weight=2.0),
        KeywordTag(kw="数据结构", standard="数据结构", category="hard_skill", weight=2.0),
        KeywordTag(kw="算法", standard="算法", category="hard_skill", weight=2.0),
        KeywordTag(kw="STM32", standard="STM32", category="hard_skill", weight=2.5),
        KeywordTag(kw="本科", standard="本科", category="education", weight=1.0),
        KeywordTag(kw="某211", standard="某211", category="education", weight=2.0),
    ]
    fit_dirs = [
        {"direction": "嵌入式软件", "cat_key": "development", "sub_key": "embedded_sw",
         "category_name": "开发", "weight": 0.95, "evidence": "嵌入式课程+STM32项目"},
        {"direction": "后端开发", "cat_key": "development", "sub_key": "backend",
         "category_name": "开发", "weight": 0.50, "evidence": "Python+C++课程"},
    ]
    return UserProfile(
        role="嵌入式软件", degree="本科", major="电子信息工程",
        graduation_year="2026", graduation_date="2026-06",
        target_cities=["上海", "深圳", "北京", "杭州"],
        resume_text="", structured_keywords=keywords, fit_directions=fit_dirs,
        core_skills=["C++", "C", "嵌入式", "RTOS", "Linux", "Python", "数据结构", "算法", "STM32"],
        direction_keywords={"skill": ["C++", "C", "嵌入式", "RTOS", "Linux", "Python", "数据结构", "算法", "STM32"]},
    )


# ============================================================
# v2 优化: patch scorer 的三个参数
# ============================================================
def apply_v2_optimizations():
    """应用 v2 优化:
    1. role gate 阈值 40 → 60
    2. competitiveness 硬门槛 (comp<40 → 总分 cap 50)
    3. major 权重 0.10 → 0.15
    """
    # 保存原始值
    original_threshold = scorer.ROLE_GATE_THRESHOLD
    original_weights = dict(scorer.DIMENSION_WEIGHTS) if hasattr(scorer, 'DIMENSION_WEIGHTS') else None

    # v2-1: role gate 阈值 40 → 60
    scorer.ROLE_GATE_THRESHOLD = 60.0

    # v2-3: major 权重调整
    # 找到权重定义的位置
    if hasattr(scorer, 'DIMENSION_WEIGHTS') and isinstance(scorer.DIMENSION_WEIGHTS, dict):
        scorer.DIMENSION_WEIGHTS['major'] = 0.15
        # 重新归一化
        total = sum(scorer.DIMENSION_WEIGHTS.values())
        for k in scorer.DIMENSION_WEIGHTS:
            scorer.DIMENSION_WEIGHTS[k] = scorer.DIMENSION_WEIGHTS[k] / total * 1.0

    original_score_job = scorer.score_job

    def v2_score_job(job, profile):
        result = original_score_job(job, profile)

        # v2-2: competitiveness 硬门槛
        # comp<40 → 总分 cap 50
        dims = result.get("维度分", {})
        comp_score = dims.get("competitiveness", 0)
        if comp_score < 40:
            if result["相关性评分"] > 50:
                result["相关性评分"] = 50
                result["竞争力硬门槛"] = True

        return result

    scorer.score_job = v2_score_job

    return (original_threshold, original_weights, original_score_job)


def restore_v1(state):
    original_threshold, original_weights, original_fn = state
    scorer.ROLE_GATE_THRESHOLD = original_threshold
    if original_weights:
        scorer.DIMENSION_WEIGHTS.clear()
        scorer.DIMENSION_WEIGHTS.update(original_weights)
    scorer.score_job = original_fn


# ============================================================
# 评测集(复用)
# ============================================================
def load_jobs_for_accounting():
    import sqlite3
    conn = sqlite3.connect("data/jobs.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    def select(sql):
        c.execute(sql)
        return [dict(r) for r in c.fetchall()]
    jobs = []
    jobs += select("SELECT * FROM positions WHERE job_subcategory='财务' AND hard_skills != '[]' LIMIT 8")
    jobs += select("SELECT * FROM positions WHERE job_subcategory IN ('投行','量化研究','风控') AND hard_skills != '[]' LIMIT 6")
    jobs += select("SELECT * FROM positions WHERE job_subcategory='市场营销' AND hard_skills != '[]' LIMIT 5")
    jobs += select("SELECT * FROM positions WHERE job_subcategory='人力资源' LIMIT 4")
    jobs += select("SELECT * FROM positions WHERE job_subcategory IN ('嵌入式软件','机器学习算法','后端开发') AND hard_skills != '[]' LIMIT 10")
    jobs += select("SELECT * FROM positions WHERE job_subcategory='法务' LIMIT 2")
    jobs += select("SELECT * FROM positions WHERE job_subcategory LIKE '%管培%' LIMIT 5")
    conn.close()
    for j in jobs:
        if isinstance(j.get("hard_skills"), str):
            try: j["hard_skills"] = json.loads(j["hard_skills"])
            except: j["hard_skills"] = []
        if isinstance(j.get("keywords"), str):
            try: j["keywords"] = json.loads(j["keywords"])
            except: j["keywords"] = []
    return jobs


def load_jobs_for_weak():
    import sqlite3
    conn = sqlite3.connect("data/jobs.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    def select(sql):
        c.execute(sql)
        return [dict(r) for r in c.fetchall()]
    jobs = []
    jobs += select("SELECT * FROM positions WHERE company_tier='顶' AND job_subcategory IN ('后端开发','机器学习算法') AND hard_skills != '[]' LIMIT 6")
    jobs += select("SELECT * FROM positions WHERE company_tier='中' AND job_subcategory='后端开发' AND hard_skills != '[]' LIMIT 4")
    jobs += select("SELECT * FROM positions WHERE company_tier='保底' AND job_subcategory='后端开发' AND hard_skills != '[]' LIMIT 4")
    conn.close()
    for j in jobs:
        if isinstance(j.get("hard_skills"), str):
            try: j["hard_skills"] = json.loads(j["hard_skills"])
            except: j["hard_skills"] = []
        if isinstance(j.get("keywords"), str):
            try: j["keywords"] = json.loads(j["keywords"])
            except: j["keywords"] = []
    return jobs


def load_jobs_for_embedded():
    import sqlite3
    conn = sqlite3.connect("data/jobs.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    def select(sql):
        c.execute(sql)
        return [dict(r) for r in c.fetchall()]
    jobs = []
    jobs += select("SELECT * FROM positions WHERE job_subcategory='嵌入式软件' AND hard_skills != '[]' LIMIT 6")
    jobs += select("SELECT * FROM positions WHERE job_subcategory='后端开发' AND hard_skills != '[]' LIMIT 8")
    jobs += select("SELECT * FROM positions WHERE job_subcategory='机器学习算法' AND hard_skills != '[]' LIMIT 4")
    jobs += select("SELECT * FROM positions WHERE company_tier='顶' AND job_subcategory='后端开发' AND hard_skills != '[]' LIMIT 4")
    conn.close()
    for j in jobs:
        if isinstance(j.get("hard_skills"), str):
            try: j["hard_skills"] = json.loads(j["hard_skills"])
            except: j["hard_skills"] = []
        if isinstance(j.get("keywords"), str):
            try: j["keywords"] = json.loads(j["keywords"])
            except: j["keywords"] = []
    return jobs


# ============================================================
# 跑评测
# ============================================================
def run_eval(jobs, profile):
    results = []
    for job in jobs:
        job["keywords"] = job.get("hard_skills", [])
        job["soft_skills"] = ""
        job["certifications"] = []
        job["languages"] = []
        job["industry"] = "互联网"
        job["company_type"] = "民企"
        r = score_job(job, profile)
        results.append({
            "id": job["id"],
            "company_name": job["company_name"],
            "position_title": job["position_title"],
            "job_subcategory": job.get("job_subcategory", ""),
            "company_tier": job.get("company_tier", ""),
            "score": r["相关性评分"],
            "role_score": r["维度分"].get("role", 0),
            "hard_skill_score": r["维度分"].get("hard_skill", 0),
            "competitiveness_score": r["维度分"].get("competitiveness", 0),
            "major_score": r["维度分"].get("major", 0),
            "role_gated": r.get("方向门槛触发", False),
        })
    results.sort(key=lambda x: -x["score"])
    return results


def compute_metrics(results, scenario):
    """计算四类量化指标"""
    n = len(results)
    top5 = results[:5]
    top10 = results[:10]

    # 用户 fit_directions
    if scenario == "accounting":
        fit_dirs = {"财务", "审计"}
        relevant_label = "财务"
    elif scenario == "weak":
        fit_dirs = {"后端开发"}
        relevant_label = "后端开发"
    elif scenario == "embedded":
        fit_dirs = {"嵌入式软件"}
        relevant_label = "嵌入式软件"

    # 1. 方向命中率@5
    hit5 = sum(1 for r in top5 if r["job_subcategory"] in fit_dirs)
    hit_rate_5 = hit5 / 5

    # 2. 方向命中率@10
    hit10 = sum(1 for r in top10 if r["job_subcategory"] in fit_dirs)
    hit_rate_10 = hit10 / 10

    # 3. 档位错配率@10 (comp<40)
    mismatch10 = sum(1 for r in top10 if r["competitiveness_score"] < 40)
    mismatch_rate_10 = mismatch10 / 10

    # 4. 泛技能刷分率@5 (role<60 AND skill>80)
    inflation5 = sum(1 for r in top5 if r["role_score"] < 60 and r["hard_skill_score"] > 80)
    inflation_rate_5 = inflation5 / 5

    # 5. 分差区分度
    relevant_scores = [r["score"] for r in results if r["job_subcategory"] in fit_dirs]
    irrelevant_scores = [r["score"] for r in results if r["job_subcategory"] not in fit_dirs]
    score_gap = (sum(relevant_scores)/len(relevant_scores) - sum(irrelevant_scores)/len(irrelevant_scores)) if relevant_scores and irrelevant_scores else 0

    return {
        "方向命中率@5": hit_rate_5,
        "方向命中率@10": hit_rate_10,
        "档位错配率@10": mismatch_rate_10,
        "泛技能刷分率@5": inflation_rate_5,
        "分差区分度": score_gap,
        f"Top5_{relevant_label}占比": hit5 / 5,
    }


def print_comparison(scenario_name, metrics_v1, metrics_v2):
    print(f"\n{'='*70}")
    print(f"  {scenario_name}")
    print(f"{'='*70}")
    print(f"  {'指标':<25} {'v1':<12} {'v2':<12} {'变化':<12}")
    print(f"  {'-'*60}")
    for k in metrics_v1:
        old, new = metrics_v1[k], metrics_v2[k]
        diff = new - old
        arrow = "↑" if diff > 0 else ("↓" if diff < 0 else "→")
        print(f"  {k:<25} {old:<12.3f} {new:<12.3f} {arrow} {abs(diff):.3f}")


def print_top5(results, label):
    print(f"\n  {label} Top-5:")
    print(f"    {'#':<3} {'Score':>6} {'Role':>5} {'Skill':>5} {'Comp':>5} {'Sub':<12} 公司-岗位")
    print(f"    {'-'*70}")
    for i, r in enumerate(results[:5]):
        print(f"    {i+1:<3} {r['score']:>6.1f} {r['role_score']:>5.1f} {r['hard_skill_score']:>5.1f} "
              f"{r['competitiveness_score']:>5.1f} {r['job_subcategory']:<12} "
              f"{r['company_name']}-{r['position_title'][:15]}")


if __name__ == "__main__":
    print("=" * 70)
    print("  v2 优化量化测试")
    print("  v1: role gate=40, comp 无硬门槛, major 权重=0.10")
    print("  v2: role gate=60, comp<40→cap 50, major 权重=0.15")
    print("=" * 70)

    # ========== 场景 1: 会计专业 ==========
    print(f"\n{'#'*70}")
    print(f"  场景 1: 会计专业匹配")
    print(f"{'#'*70}")

    profile_acc = build_accounting_profile()
    jobs_acc = load_jobs_for_accounting()

    # v1
    results_acc_v1 = run_eval(jobs_acc, profile_acc)
    metrics_acc_v1 = compute_metrics(results_acc_v1, "accounting")
    print_top5(results_acc_v1, "v1")

    # v2
    state = apply_v2_optimizations()
    results_acc_v2 = run_eval(jobs_acc, profile_acc)
    metrics_acc_v2 = compute_metrics(results_acc_v2, "accounting")
    print_top5(results_acc_v2, "v2")
    restore_v1(state)

    print_comparison("场景1: 会计专业匹配", metrics_acc_v1, metrics_acc_v2)

    # ========== 场景 2: 保底候选人 ==========
    print(f"\n{'#'*70}")
    print(f"  场景 2: 保底候选人 vs 顶档岗位")
    print(f"{'#'*70}")

    profile_weak = build_weak_candidate()
    jobs_weak = load_jobs_for_weak()

    results_weak_v1 = run_eval(jobs_weak, profile_weak)
    metrics_weak_v1 = compute_metrics(results_weak_v1, "weak")
    print_top5(results_weak_v1, "v1")

    state = apply_v2_optimizations()
    results_weak_v2 = run_eval(jobs_weak, profile_weak)
    metrics_weak_v2 = compute_metrics(results_weak_v2, "weak")
    print_top5(results_weak_v2, "v2")
    restore_v1(state)

    print_comparison("场景2: 保底候选人", metrics_weak_v1, metrics_weak_v2)

    # ========== 场景 3: 嵌入式用户(泛技能刷分) ==========
    print(f"\n{'#'*70}")
    print(f"  场景 3: 嵌入式用户(泛技能刷分)")
    print(f"{'#'*70}")

    profile_emb = build_embedded_user()
    jobs_emb = load_jobs_for_embedded()

    results_emb_v1 = run_eval(jobs_emb, profile_emb)
    metrics_emb_v1 = compute_metrics(results_emb_v1, "embedded")
    print_top5(results_emb_v1, "v1")

    state = apply_v2_optimizations()
    results_emb_v2 = run_eval(jobs_emb, profile_emb)
    metrics_emb_v2 = compute_metrics(results_emb_v2, "embedded")
    print_top5(results_emb_v2, "v2")
    restore_v1(state)

    print_comparison("场景3: 泛技能刷分", metrics_emb_v1, metrics_emb_v2)

    # ========== 汇总 ==========
    print(f"\n{'='*70}")
    print(f"  v2 优化汇总")
    print(f"{'='*70}")
    print(f"\n  场景1 会计专业:")
    print(f"    分差区分度: {metrics_acc_v1['分差区分度']:.1f} → {metrics_acc_v2['分差区分度']:.1f} (目标>30)")
    print(f"    方向命中率@10: {metrics_acc_v1['方向命中率@10']:.0%} → {metrics_acc_v2['方向命中率@10']:.0%}")

    print(f"\n  场景2 保底候选人:")
    print(f"    档位错配率@10: {metrics_weak_v1['档位错配率@10']:.0%} → {metrics_weak_v2['档位错配率@10']:.0%} (目标0%)")
    print(f"    顶档岗平均分: {sum(r['score'] for r in results_weak_v1 if r['company_tier']=='顶')/6:.1f} → "
          f"{sum(r['score'] for r in results_weak_v2 if r['company_tier']=='顶')/6:.1f}")

    print(f"\n  场景3 泛技能刷分:")
    print(f"    泛技能刷分率@5: {metrics_emb_v1['泛技能刷分率@5']:.0%} → {metrics_emb_v2['泛技能刷分率@5']:.0%} (目标0%)")
    print(f"    方向命中率@5: {metrics_emb_v1['方向命中率@5']:.0%} → {metrics_emb_v2['方向命中率@5']:.0%}")
