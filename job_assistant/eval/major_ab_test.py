"""
Major 维度细分匹配 A/B 测试

v1(当前): 大类优先(100分) → major_required 精确匹配(100分) → "相关"(80分) → 不匹配(40分)
v2(优化): 不限(100分) → major_required 精确匹配(100分) → "相关"(85分) → 大类兜底(60分) → 不匹配(30分)

测试用户: 会计学专业本科生(双非财经类院校)
测试集: 53 岗位(财务8 + 金融6 + 市场5 + 人力4 + 不对口工科10 + 嵌入式/算法/后端20)

关键指标:
- Top-10 中财务/会计岗位占比(目标 v2 > v1)
- Top-10 中市场营销岗位占比(目标 v2 < v1)
- 财务岗平均分 vs 市场营销岗平均分的分差(目标 v2 分差 > v1)
"""
import json
import sys
import os
import re
import sqlite3
import copy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATA_DIR"] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

import scorer
from scorer import score_job, DIMENSION_WEIGHTS
from models import UserProfile, KeywordTag
import job_tree


# ============================================================
# 会计学用户画像
# ============================================================
def build_accounting_profile():
    """会计学本科生(双非财经类院校)"""
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
          "category_name": "职能", "weight": 0.95,
         "evidence": "会计学专业+财务分析实习"},
        {"direction": "审计", "cat_key": "corporate", "sub_key": "audit",
         "category_name": "职能", "weight": 0.85,
         "evidence": "审计课程+会计师事务所实习"},
        {"direction": "投行", "cat_key": "finance", "sub_key": "ibd",
         "category_name": "金融", "weight": 0.60,
         "evidence": "金融建模课程+券商投行部实习"},
        {"direction": "量化研究", "cat_key": "finance", "sub_key": "quant_research",
         "category_name": "金融", "weight": 0.40,
         "evidence": "Python+数据分析+统计学课程"},
    ]

    return UserProfile(
        role="财务/会计",
        degree="本科",
        major="会计学",
        graduation_year="2026",
        graduation_date="2026-06",
        target_cities=["上海", "北京", "深圳", "杭州"],
        resume_text="",
        structured_keywords=keywords,
        fit_directions=fit_dirs,
        core_skills=["会计", "财务分析", "Excel", "财务建模", "审计", "税务", "SQL", "Python", "数据分析"],
        direction_keywords={"skill": ["会计", "财务分析", "Excel", "财务建模", "审计", "税务", "SQL", "Python"]},
    )


# ============================================================
# v2 major 匹配逻辑(细分优先)
# ============================================================
MAJOR_KEYWORDS = {
    "会计": ["会计", "财务管理", "出纳"],
    "财务": ["财务", "会计", "出纳", "业财", "管理财务"],
    "审计": ["审计", "内审", "风控"],
    "税务": ["税务", "税收"],
    "金融": ["金融", "投资", "资管", "基金", "证券", "银行"],
    "经济": ["经济", "国际经济", "贸易"],
    "市场营销": ["市场营销", "市场推广", "营销策划", "品牌", "广告"],
    "人力资源": ["人力资源", "人资", "招聘", "人事", "HR"],
    "法学": ["法学", "法律"],
    "计算机": ["计算机", "软件工程", "人工智能", "数据科学"],
    "微电子": ["微电子", "集成电路", "芯片", "半导体"],
    "电子信息": ["电子信息", "电子工程", "通信"],
    "机械": ["机械", "机械工程", "制造"],
    "电气": ["电气", "电气工程", "自动化"],
    "材料": ["材料", "材料科学"],
    "数学": ["数学", "统计学", "统计"],
    "物理": ["物理", "光学"],
    "化学": ["化学", "化工"],
    "管理": ["管理", "工商管理", "企业管理", "供应链", "物流"],
    "设计": ["设计", "美术", "视觉", "工业设计"],
    "新闻": ["新闻", "传播", "广告"],
    "教育": ["教育", "师范", "教学"],
}


def extract_major_keywords(major_required: str) -> list:
    """从 major_required 字段提取专业关键词"""
    if not major_required or major_required in ("不限", ""):
        return []

    text = major_required.replace("、", " ").replace("/", " ").replace("，", " ").replace(",", " ")
    tokens = re.findall(r"[\u4e00-\u9fa5a-zA-Z]+", text)

    matched = set()
    for token in tokens:
        for key, aliases in MAJOR_KEYWORDS.items():
            for alias in aliases:
                if alias in token or token in alias:
                    matched.add(key)
                    break
    return list(matched)


def match_user_major_to_job(user_major: str, job_major_required: str) -> tuple:
    """用户专业 vs 岗位 major_required 细分匹配
    Returns: (score, reason)
    """
    if not job_major_required or job_major_required in ("不限", ""):
        return 100.0, "岗位无专业限制"

    job_kws = extract_major_keywords(job_major_required)
    user_kws = set()

    # 用户专业归一化
    user_major = user_major or ""
    for key, aliases in MAJOR_KEYWORDS.items():
        for alias in aliases:
            if alias in user_major:
                user_kws.add(key)
                break

    # 精确匹配:用户专业关键词命中岗位专业关键词
    if user_kws and job_kws:
        overlap = user_kws & set(job_kws)
        if overlap:
            return 100.0, f"精确匹配: {','.join(overlap)}"

    # "相关"类:岗位接受相关专业
    if "相关" in job_major_required:
        if user_kws:
            return 85.0, "岗位接受相关专业(含'相关'关键词)"
        return 80.0, "岗位接受相关专业"

    return None, None  # 未匹配,交给大类兜底


def _match_major_v2(profile, job, u):
    """v2: 细分优先,大类兜底"""
    reasons = []
    job_major_cat = (job.get("major_category") or "").strip()
    job_major = (job.get("major_required") or "").strip()
    user_major = (profile.major or "").strip()
    user_edu_tags = u.get("education", [])

    # 1. 不限 → 100
    if not job_major_cat or job_major_cat in ("不限", ""):
        reasons.append("岗位无专业大类限制")
        return 100.0, reasons

    # 2. major_required 细分匹配(优先)
    score, reason = match_user_major_to_job(user_major, job_major)
    if score is not None:
        reasons.append(f"[细分匹配] {reason}")
        return score, reasons

    # 3. 大类兜底(降为60分)
    edu_kw_lower = [t.lower() for t in user_edu_tags + [user_major]]
    if any(job_major_cat.lower() in kw or kw in job_major_cat.lower() for kw in edu_kw_lower):
        reasons.append(f"大类兜底: 候选人专业属于{job_major_cat}大类(细分未精确匹配)")
        return 60.0, reasons

    # 4. 都不匹配
    reasons.append(f"专业不匹配: 岗位倾向{job_major_cat}/{job_major}")
    return 30.0, reasons


# ============================================================
# 评测集构建
# ============================================================
def build_evalset():
    conn = sqlite3.connect("data/jobs.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    def select(sql):
        cursor.execute(sql)
        return [dict(r) for r in cursor.fetchall()]

    jobs = []

    # 财务/会计(8) - 应排前面
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory='财务'
        AND hard_skills != '[]' LIMIT 8
    """)

    # 金融(6) - 部分相关
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory IN ('投行','量化研究','风控')
        AND hard_skills != '[]' LIMIT 6
    """)

    # 市场营销(5) - 商科但方向不对
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory='市场营销'
        AND hard_skills != '[]' LIMIT 5
    """)

    # 人力资源(4) - 商科但方向不对
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory='人力资源' LIMIT 4
    """)

    # 不对口工科(10) - 方向完全不对
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory IN ('嵌入式软件','机器学习算法','后端开发')
        AND hard_skills != '[]' LIMIT 10
    """)

    # 法务(2) - 商科但完全不同方向
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory='法务' LIMIT 2
    """)

    # 管培生(5) - 不限专业
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory LIKE '%管培%' LIMIT 5
    """)

    conn.close()

    # 解析 JSON 字段
    for j in jobs:
        if isinstance(j.get("hard_skills"), str):
            try:
                j["hard_skills"] = json.loads(j["hard_skills"])
            except:
                j["hard_skills"] = []
        if isinstance(j.get("keywords"), str):
            try:
                j["keywords"] = json.loads(j["keywords"])
            except:
                j["keywords"] = []

    # 标注 ground truth
    finance_subs = {"财务", "审计"}
    related_subs = {"投行", "量化研究", "风控", "资管/投资"}
    business_subs = {"市场营销", "人力资源", "法务"}

    evalset = {"jobs": []}
    for i, job in enumerate(jobs):
        sub = job.get("job_subcategory", "")
        if sub in finance_subs:
            gt, label = 2, "强相关(财务/会计)"
        elif sub in related_subs:
            gt, label = 1, "部分相关(金融)"
        elif sub in business_subs:
            gt, label = 0, "不对口(商科但方向不同)"
        else:
            gt, label = 0, "完全不对口(工科/管培)"

        evalset["jobs"].append({
            "eval_id": f"MJ-{i+1:03d}",
            "job_id": job["id"],
            "company_name": job["company_name"],
            "position_title": job["position_title"],
            "job_subcategory": sub,
            "major_category": job.get("major_category", ""),
            "major_required": job.get("major_required", ""),
            "hard_skills": job.get("hard_skills", []),
            "min_education": job.get("min_education", ""),
            "city": job.get("city", ""),
            "company_tier": job.get("company_tier", ""),
            "ground_truth": gt,
            "ground_truth_label": label,
            "raw_job": job,
        })

    return evalset


# ============================================================
# 跑评测
# ============================================================
def run_eval(evalset, profile, label="v1"):
    results = []
    for job_meta in evalset["jobs"]:
        job = job_meta["raw_job"]
        job["hard_skills"] = job_meta["hard_skills"]
        job["keywords"] = job_meta["hard_skills"]
        job["soft_skills"] = ""
        job["certifications"] = []
        job["languages"] = []
        job["industry"] = "金融"
        job["company_type"] = "民企"

        r = score_job(job, profile)
        results.append({
            "eval_id": job_meta["eval_id"],
            "company_name": job_meta["company_name"],
            "position_title": job_meta["position_title"],
            "job_subcategory": job_meta["job_subcategory"],
            "major_category": job_meta["major_category"],
            "major_required": job_meta["major_required"][:40],
            "ground_truth": job_meta["ground_truth"],
            "ground_truth_label": job_meta["ground_truth_label"],
            "score": r["相关性评分"],
            "recommendation": r["综合推荐度"],
            "major_score": r["维度分"].get("major", 0),
            "role_score": r["维度分"].get("role", 0),
            "hard_skill_score": r["维度分"].get("hard_skill", 0),
            "competitiveness_score": r["维度分"].get("competitiveness", 0),
            "role_gated": r.get("方向门槛触发", False),
        })

    results.sort(key=lambda x: -x["score"])
    return results


def run_eval_v2(evalset, profile, label="v2"):
    """v2: 替换 _match_major 为细分优先版"""
    original_fn = scorer._match_major
    scorer._match_major = _match_major_v2

    results = run_eval(evalset, profile, label)

    scorer._match_major = original_fn
    return results


def print_report(results, metrics, label):
    print(f"\n{'='*80}")
    print(f"  Major 维度 A/B 测试 — {label}")
    print(f"{'='*80}")

    print(f"\n📊 核心指标:")
    print(f"  Top-10 财务岗占比:        {metrics['finance_in_top10']:.1%}  目标提升")
    print(f"  Top-10 市场营销岗占比:    {metrics['marketing_in_top10']:.1%}  目标下降")
    print(f"  财务岗平均分:             {metrics['finance_avg_score']:.1f}")
    print(f"  市场营销岗平均分:          {metrics['marketing_avg_score']:.1f}")
    print(f"  分差(财务-市场营销):      {metrics['score_gap']:.1f}  目标 v2 > v1")
    print(f"  Precision@10(财务):       {metrics['precision_at_10']:.1%}")
    print(f"  Recall@30:                {metrics['recall_at_30']:.1%}")

    print(f"\n🏆 Top-10 详情:")
    print(f"  {'#':<3} {'Score':>6} {'GT':<3} {'Major':>6} {'Role':>5} {'Cat':<6} {'MajorReq':<20} 公司-岗位")
    print(f"  {'-'*100}")
    for i, r in enumerate(results[:10]):
        gt = "✓" if r["ground_truth"] >= 2 else ("~" if r["ground_truth"] == 1 else "✗")
        print(f"  {i+1:<3} {r['score']:>6.1f} {gt:<3} {r['major_score']:>6.1f} {r['role_score']:>5.1f} "
              f"{r['major_category']:<6} {r['major_required']:<20} "
              f"{r['company_name']}-{r['position_title'][:20]}")

    # 按岗位类型看分数
    print(f"\n📋 按岗位类型看平均分:")
    categories = {}
    for r in results:
        sub = r["job_subcategory"]
        if sub not in categories:
            categories[sub] = []
        categories[sub].append(r)

    for sub, items in sorted(categories.items(), key=lambda x: -sum(i["score"] for i in x[1])/len(x[1])):
        avg = sum(i["score"] for i in items) / len(items)
        avg_major = sum(i["major_score"] for i in items) / len(items)
        print(f"  {sub:<12} avg_score={avg:.1f}  avg_major={avg_major:.1f}  n={len(items)}")


def compute_metrics(results):
    n = len(results)
    top10 = results[:10]
    top30 = results[:30] if n >= 30 else results

    finance_jobs = [r for r in results if r["job_subcategory"] == "财务"]
    marketing_jobs = [r for r in results if r["job_subcategory"] == "市场营销"]

    finance_in_top10 = sum(1 for r in top10 if r["job_subcategory"] == "财务")
    marketing_in_top10 = sum(1 for r in top10 if r["job_subcategory"] == "市场营销")

    finance_avg = sum(r["score"] for r in finance_jobs) / len(finance_jobs) if finance_jobs else 0
    marketing_avg = sum(r["score"] for r in marketing_jobs) / len(marketing_jobs) if marketing_jobs else 0

    total_finance = len(finance_jobs)
    top30_finance = sum(1 for r in top30 if r["job_subcategory"] == "财务")
    recall30 = top30_finance / total_finance if total_finance > 0 else 0

    precision10 = sum(1 for r in top10 if r["ground_truth"] >= 2) / 10

    return {
        "finance_in_top10": finance_in_top10 / 10,
        "marketing_in_top10": marketing_in_top10 / 10,
        "finance_avg_score": finance_avg,
        "marketing_avg_score": marketing_avg,
        "score_gap": finance_avg - marketing_avg,
        "precision_at_10": precision10,
        "recall_at_30": recall30,
    }


if __name__ == "__main__":
    print("=" * 80)
    print("  Major 维度细分匹配 A/B 测试")
    print("  用户: 会计学本科生(双非财经类院校)")
    print("  v1: 大类优先(100分) | v2: 细分优先(100分), 大类降为60分")
    print("=" * 80)

    profile = build_accounting_profile()
    evalset = build_evalset()

    dist = {0: 0, 1: 0, 2: 0}
    for j in evalset["jobs"]:
        dist[j["ground_truth"]] += 1
    print(f"\n评测集: {len(evalset['jobs'])} 岗位")
    print(f"  强相关(财务): {dist[2]}")
    print(f"  部分相关(金融): {dist[1]}")
    print(f"  不对口(市场/人资/法务/工科/管培): {dist[0]}")

    # v1
    results_v1 = run_eval(evalset, profile, "v1")
    metrics_v1 = compute_metrics(results_v1)
    print_report(results_v1, metrics_v1, "v1(大类优先)")

    # v2
    results_v2 = run_eval_v2(evalset, profile, "v2")
    metrics_v2 = compute_metrics(results_v2)
    print_report(results_v2, metrics_v2, "v2(细分优先)")

    # 对比
    print(f"\n{'='*80}")
    print(f"  v1 vs v2 对比")
    print(f"{'='*80}")
    print(f"  {'指标':<30} {'v1':<12} {'v2':<12} {'变化':<10}")
    print(f"  {'-'*65}")
    for k in metrics_v1:
        old, new = metrics_v1[k], metrics_v2[k]
        diff = new - old
        arrow = "↑" if diff > 0 else ("↓" if diff < 0 else "→")
        print(f"  {k:<30} {old:<12.3f} {new:<12.3f} {arrow} {abs(diff):.3f}")

    # 关键排名变化
    print(f"\n📋 关键排名变化:")
    v1_by_id = {r["eval_id"]: i+1 for i, r in enumerate(results_v1)}
    v2_by_id = {r["eval_id"]: i+1 for i, r in enumerate(results_v2)}
    for r in results_v1:
        eid = r["eval_id"]
        v1_rank = v1_by_id[eid]
        v2_rank = v2_by_id[eid]
        delta = v1_rank - v2_rank
        if abs(delta) >= 2 and r["job_subcategory"] in ("财务", "市场营销", "人力资源"):
            arrow = "↑" if delta > 0 else "↓"
            print(f"  {arrow} {r['job_subcategory']:<8} v1#{v1_rank}→v2#{v2_rank} (Δ{abs(delta)}) "
                  f"v1分={r['score']:.1f}→v2分={results_v2[v2_rank-1]['score']:.1f} "
                  f"{r['company_name']}-{r['position_title']}")
