"""
场景 2+3 测试：层级不匹配 + 泛技能刷分

场景2: 保底候选人(双非本科无实习无竞赛) vs 顶档岗位(拼多多/科大讯飞)
  期望: 顶档岗位 competitiveness 分低 → 总分被压低 → 不进 Top-5
  问题: competitiveness 权重只有 0.20, 没有 hard gate

场景3: 嵌入式用户 vs 后端开发岗(技能高度重叠: C++/Python/数据结构)
  期望: 后端岗因技能交集大 → hard_skill 分高 → 刷进 Top-5
  问题: role gate 应该压住, 但如果 role 部分匹配就会漏
"""
import json
import sys
import os
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATA_DIR"] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

import scorer
from scorer import score_job
from models import UserProfile, KeywordTag
import job_tree


# ============================================================
# 用户 A: 保底候选人(双非本科, 无实习, 无竞赛, 无论文)
# 目标: 看顶档岗位是否被压低
# ============================================================
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
        role="后端开发",
        degree="本科",
        major="计算机科学与技术",
        graduation_year="2026",
        graduation_date="2026-06",
        target_cities=["上海", "北京", "深圳", "杭州"],
        resume_text="",
        structured_keywords=keywords,
        fit_directions=fit_dirs,
        core_skills=["Python", "C++", "数据结构", "算法", "MySQL"],
        direction_keywords={"skill": ["Python", "C++", "数据结构", "算法", "MySQL"]},
    )


# ============================================================
# 用户 B: 嵌入式用户(技能和后端高度重叠)
# 目标: 看后端岗是否因泛技能刷分挤进 Top-5
# ============================================================
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
        role="嵌入式软件",
        degree="本科",
        major="电子信息工程",
        graduation_year="2026",
        graduation_date="2026-06",
        target_cities=["上海", "深圳", "北京", "杭州"],
        resume_text="",
        structured_keywords=keywords,
        fit_directions=fit_dirs,
        core_skills=["C++", "C", "嵌入式", "RTOS", "Linux", "Python", "数据结构", "算法", "STM32"],
        direction_keywords={"skill": ["C++", "C", "嵌入式", "RTOS", "Linux", "Python", "数据结构", "算法", "STM32"]},
    )


# ============================================================
# 评测集: 混合顶档/中档/保底岗位
# ============================================================
def build_evalset(profile_role):
    conn = sqlite3.connect("data/jobs.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    def select(sql):
        c.execute(sql)
        return [dict(r) for r in c.fetchall()]

    jobs = []

    if profile_role == "后端开发":
        # 顶档(大厂后端/算法) - 保底候选人应该够不着
        jobs += select("""
            SELECT * FROM positions WHERE company_tier='顶'
            AND job_subcategory IN ('后端开发','机器学习算法')
            AND hard_skills != '[]' LIMIT 6
        """)
        # 中档(独角兽后端)
        jobs += select("""
            SELECT * FROM positions WHERE company_tier='中'
            AND job_subcategory='后端开发' AND hard_skills != '[]' LIMIT 4
        """)
        # 保底(初创后端) - 保底候选人应该能匹配
        jobs += select("""
            SELECT * FROM positions WHERE company_tier='保底'
            AND job_subcategory='后端开发' AND hard_skills != '[]' LIMIT 4
        """)
    elif profile_role == "嵌入式软件":
        # 嵌入式岗位(方向对口)
        jobs += select("""
            SELECT * FROM positions WHERE job_subcategory='嵌入式软件'
            AND hard_skills != '[]' LIMIT 6
        """)
        # 后端岗位(技能重叠但方向不对) - F3 泛技能刷分测试
        jobs += select("""
            SELECT * FROM positions WHERE job_subcategory='后端开发'
            AND hard_skills != '[]' LIMIT 8
        """)
        # 机器学习算法(技能部分重叠)
        jobs += select("""
            SELECT * FROM positions WHERE job_subcategory='机器学习算法'
            AND hard_skills != '[]' LIMIT 4
        """)
        # 顶档后端(大厂)
        jobs += select("""
            SELECT * FROM positions WHERE company_tier='顶'
            AND job_subcategory='后端开发' AND hard_skills != '[]' LIMIT 4
        """)

    conn.close()

    for j in jobs:
        if isinstance(j.get("hard_skills"), str):
            try: j["hard_skills"] = json.loads(j["hard_skills"])
            except: j["hard_skills"] = []
        if isinstance(j.get("keywords"), str):
            try: j["keywords"] = json.loads(j["keywords"])
            except: j["keywords"] = []

    return jobs


def run_eval(jobs, profile, label):
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
            "min_education": job.get("min_education", ""),
            "hard_skills": job.get("hard_skills", [])[:5],
            "score": r["相关性评分"],
            "recommendation": r["综合推荐度"],
            "role_score": r["维度分"].get("role", 0),
            "hard_skill_score": r["维度分"].get("hard_skill", 0),
            "competitiveness_score": r["维度分"].get("competitiveness", 0),
            "education_score": r["维度分"].get("education", 0),
            "role_gated": r.get("方向门槛触发", False),
        })

    results.sort(key=lambda x: -x["score"])
    return results


def print_report(results, label, scenario):
    print(f"\n{'='*90}")
    print(f"  {scenario} — {label}")
    print(f"{'='*90}")

    print(f"\n🏆 排序结果:")
    print(f"  {'#':<3} {'Score':>6} {'Role':>5} {'Skill':>5} {'Comp':>5} {'Edu':>4} {'Gate':<5} {'Tier':<4} {'Sub':<12} 公司-岗位")
    print(f"  {'-'*100}")
    for i, r in enumerate(results):
        gate = "✗" if r["role_gated"] else "✓"
        print(f"  {i+1:<3} {r['score']:>6.1f} {r['role_score']:>5.1f} {r['hard_skill_score']:>5.1f} "
              f"{r['competitiveness_score']:>5.1f} {r['education_score']:>4.1f} {gate:<5} "
              f"{r['company_tier']:<4} {r['job_subcategory']:<12} "
              f"{r['company_name']}-{r['position_title'][:20]}")

    # 按 tier 看平均分
    print(f"\n📊 按公司档位看平均分:")
    tiers = {}
    for r in results:
        t = r["company_tier"] or "?"
        if t not in tiers: tiers[t] = []
        tiers[t].append(r)
    for t, items in sorted(tiers.items(), key=lambda x: -sum(i["score"] for i in x[1])/len(x[1])):
        avg = sum(i["score"] for i in items) / len(items)
        avg_comp = sum(i["competitiveness_score"] for i in items) / len(items)
        print(f"  {t:<6} avg_score={avg:.1f}  avg_comp={avg_comp:.1f}  n={len(items)}")

    # 按子类看平均分
    print(f"\n📊 按岗位子类看平均分:")
    subs = {}
    for r in results:
        s = r["job_subcategory"] or "?"
        if s not in subs: subs[s] = []
        subs[s].append(r)
    for s, items in sorted(subs.items(), key=lambda x: -sum(i["score"] for i in x[1])/len(x[1])):
        avg = sum(i["score"] for i in items) / len(items)
        avg_skill = sum(i["hard_skill_score"] for i in items) / len(items)
        avg_role = sum(i["role_score"] for i in items) / len(items)
        print(f"  {s:<14} avg_score={avg:.1f}  avg_role={avg_role:.1f}  avg_skill={avg_skill:.1f}  n={len(items)}")


if __name__ == "__main__":
    print("=" * 90)
    print("  场景 2+3 测试: 层级不匹配 + 泛技能刷分")
    print("=" * 90)

    # ========== 场景 2: 保底候选人 vs 顶档岗位 ==========
    print("\n" + "🔍" + "=" * 88)
    print("  场景 2: 保底候选人(双非本科无实习) vs 顶档/中档/保底岗位")
    print("  期望: 顶档岗位 competitiveness 分低 → 总分被压低")
    print("  问题: competitiveness 权重 0.20, 无 hard gate")
    print("=" * 89)

    profile_a = build_weak_candidate()
    jobs_a = build_evalset("后端开发")
    results_a = run_eval(jobs_a, profile_a, "保底候选人")
    print_report(results_a, "保底候选人", "场景2: 层级不匹配")

    # 检查: 顶档岗位是否进了 Top-5
    top5 = results_a[:5]
    top_tiers = [r["company_tier"] for r in top5]
    print(f"\n⚠️  诊断:")
    print(f"  Top-5 档位分布: {top_tiers}")
    if "顶" in top_tiers:
        print(f"  问题: 顶档岗位进了 Top-5! 保底候选人够不着但被推荐了")
        for r in top5:
            if r["company_tier"] == "顶":
                print(f"    → #{top5.index(r)+1} {r['company_name']}-{r['position_title']} "
                      f"comp={r['competitiveness_score']:.1f} role={r['role_score']:.1f} "
                      f"skill={r['hard_skill_score']:.1f}")
    else:
        print(f"  正常: 顶档岗位未进 Top-5, competitiveness 维度有效压低")

    # ========== 场景 3: 嵌入式用户 vs 后端岗(泛技能刷分) ==========
    print("\n" + "🔍" + "=" * 88)
    print("  场景 3: 嵌入式用户 vs 后端岗(技能高度重叠: C++/Python/数据结构)")
    print("  期望: 后端岗 hard_skill 分高 → 刷进 Top-5")
    print("  防线: role gate (role<40 → 总分 cap 45)")
    print("=" * 89)

    profile_b = build_embedded_user()
    jobs_b = build_evalset("嵌入式软件")
    results_b = run_eval(jobs_b, profile_b, "嵌入式用户")
    print_report(results_b, "嵌入式用户", "场景3: 泛技能刷分")

    # 检查: 后端岗是否进了 Top-5
    top5_b = results_b[:5]
    top_subs = [r["job_subcategory"] for r in top5_b]
    print(f"\n⚠️  诊断:")
    print(f"  Top-5 子类分布: {top_subs}")
    backend_in_top5 = sum(1 for s in top_subs if s == "后端开发")
    embedded_in_top5 = sum(1 for s in top_subs if s == "嵌入式软件")
    print(f"  Top-5 嵌入式岗: {embedded_in_top5}, 后端岗: {backend_in_top5}")
    if backend_in_top5 > 0:
        print(f"  问题: 后端岗刷进 Top-5! 泛技能刷分发生")
        for r in top5_b:
            if r["job_subcategory"] == "后端开发":
                print(f"    → #{top5_b.index(r)+1} {r['company_name']}-{r['position_title']} "
                      f"skill={r['hard_skill_score']:.1f} role={r['role_score']:.1f} "
                      f"gate={'✗' if r['role_gated'] else '✓'}")
    else:
        print(f"  正常: 后端岗未进 Top-5, role gate 有效防泛技能刷分")

    # 看后端岗的 role_score 分布
    print(f"\n  后端岗 role_score 分布:")
    backend_jobs = [r for r in results_b if r["job_subcategory"] == "后端开发"]
    for r in backend_jobs[:5]:
        print(f"    {r['company_name']}-{r['position_title'][:20]} "
              f"role={r['role_score']:.1f} skill={r['hard_skill_score']:.1f} "
              f"score={r['score']:.1f} gate={'✗' if r['role_gated'] else '✓'}")
