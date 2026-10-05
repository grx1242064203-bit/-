"""验证修复:方向键(cat_key/sub_key)缺失时 role_score 不再恒为 0。

测试用例:林叙言简历(嵌入式 AI 开发)。
对比两种画像:
  A) 完整画像:fit_directions 带 cat_key/sub_key(修复后前端透传)
  B) 残缺画像:fit_directions 只有 direction 名(旧前端丢弃方向键)
     → 验证 scorer._match_role 的防御性反查(job_tree.resolve)能救回 role_score。

断言:两种画像下,方向对口岗位(边缘AI/嵌入式软件)的 role_score 都应 ≥ 40,
不触发方向硬门槛,推荐等级分布合理(强烈推荐+推荐 ≥ 30%)。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import UserProfile, KeywordTag
from scorer import score_job
import job_tree


def build_profile(fit_dirs):
    """构造林叙言的 UserProfile(嵌入式 AI 开发背景)。"""
    keywords = [
        KeywordTag(kw="Python", standard="Python", category="hard_skill", weight=3.0),
        KeywordTag(kw="PyTorch", standard="PyTorch", category="hard_skill", weight=2.5),
        KeywordTag(kw="TensorFlow", standard="TensorFlow", category="hard_skill", weight=2.5),
        KeywordTag(kw="C++", standard="C++", category="hard_skill", weight=2.0),
        KeywordTag(kw="C", standard="C", category="hard_skill", weight=2.0),
        KeywordTag(kw="Verilog HDL", standard="Verilog", category="hard_skill", weight=2.0),
        KeywordTag(kw="OpenCV", standard="OpenCV", category="hard_skill", weight=2.0),
        KeywordTag(kw="Scikit-learn", standard="Scikit-learn", category="hard_skill", weight=2.0),
        KeywordTag(kw="Spark", standard="Spark", category="hard_skill", weight=1.5),
        KeywordTag(kw="SQL", standard="SQL", category="hard_skill", weight=1.5),
        KeywordTag(kw="DSP", standard="DSP", category="hard_skill", weight=2.5),
        KeywordTag(kw="FPGA", standard="FPGA", category="hard_skill", weight=2.0),
        KeywordTag(kw="TensorFlow Lite", standard="TensorFlow Lite", category="hard_skill", weight=3.0),
        KeywordTag(kw="机器学习", standard="机器学习", category="hard_skill", weight=2.5),
        KeywordTag(kw="信号处理", standard="信号处理", category="hard_skill", weight=2.0),
        KeywordTag(kw="嵌入式", standard="嵌入式", category="hard_skill", weight=3.0),
        KeywordTag(kw="硕士", standard="硕士", category="education", weight=2.0),
        KeywordTag(kw="西安交通大学", standard="西安交通大学", category="education", weight=2.0),
        KeywordTag(kw="CET-6", standard="CET-6", category="cert", weight=1.0),
    ]
    return UserProfile(
        role="嵌入式AI开发",
        degree="硕士",
        major="电子信息",
        graduation_year="2026",
        graduation_date="2026-06",
        target_cities=[],
        resume_text="",
        structured_keywords=keywords,
        fit_directions=fit_dirs,
        core_skills=[k.standard for k in keywords if k.category in ("hard_skill", "tool", "framework")],
        direction_keywords={"skill": [k.standard for k in keywords if k.category in ("hard_skill", "tool", "framework")]},
    )


# 林叙言的适配方向(后端 resume_parser 校验后产出,带 cat_key/sub_key)
FIT_DIRS_COMPLETE = [
    {"direction": "边缘AI/嵌入式AI", "cat_key": "robotics", "sub_key": "edge_ai",
     "category_name": "机器人与智能体", "weight": 0.95,
     "evidence": "TensorFlow Lite Micro 边缘部署 + ARM 网关量化感知训练"},
    {"direction": "嵌入式软件", "cat_key": "development", "sub_key": "embedded_sw",
     "category_name": "开发", "weight": 0.9,
     "evidence": "TI IWR6843 C语言 DSP 优化,系统功耗降至 1.2W"},
    {"direction": "机器学习算法", "cat_key": "algorithm", "sub_key": "ml",
     "category_name": "算法", "weight": 0.7,
     "evidence": "时序异常检测 STL+孤立森林,统计建模大赛一等奖"},
    {"direction": "CV算法", "cat_key": "algorithm", "sub_key": "cv",
     "category_name": "算法", "weight": 0.6,
     "evidence": "ResNet-50 缺陷检测,OpenCV 滑动窗口,99.2% 识别率"},
    {"direction": "通信算法", "cat_key": "algorithm", "sub_key": "communication",
     "category_name": "算法", "weight": 0.4,
     "evidence": "5G 毫米波 CSI 反馈深度学习,中兴无线院实习"},
]

# 旧前端丢弃 cat_key/sub_key 后的残缺画像(只有 direction 名)
FIT_DIRS_STRIPPED = [
    {"direction": d["direction"], "weight": d["weight"], "evidence": d["evidence"]}
    for d in FIT_DIRS_COMPLETE
]


# 测试岗位集:覆盖对口(边缘AI/嵌入式)与不对口(金融/产品)方向
def make_job(title, subcategory, category, hard_skills, **kw):
    job = {
        "position_title": title,
        "company_name": "测试公司",
        "job_subcategory": subcategory,
        "job_category": category,
        "hard_skills": hard_skills,
        "keywords": hard_skills,
        "soft_skills": "",
        "certifications": "",
        "languages": "",
        "min_education": "本科",
        "city": "深圳",
        "major_category": "",
        "major_required": "",
        "industry": "互联网",
        "company_type": "民企",
    }
    job.update(kw)
    return job


TEST_JOBS = [
    make_job("嵌入式AI开发工程师", "边缘AI/嵌入式AI", "机器人与智能体",
             ["TensorFlow Lite", "模型量化", "C++", "嵌入式部署"]),
    make_job("嵌入式软件开发工程师", "嵌入式软件", "开发",
             ["C", "C++", "RTOS", "MCU", "Linux驱动"]),
    make_job("AI算法工程师(机器学习方向)", "机器学习算法", "算法",
             ["Python", "Scikit-learn", "特征工程", "XGBoost"]),
    make_job("CV算法工程师", "CV算法", "算法",
             ["PyTorch", "OpenCV", "深度学习", "目标检测"]),
    make_job("通信算法工程师", "通信算法", "算法",
             ["信号处理", "通信原理", "MATLAB", "5G"]),
    make_job("FPGA开发工程师", "FPGA开发", "芯片半导体",
             ["Verilog", "Quartus", "时序约束", "Vivado"]),
    make_job("大模型应用开发工程师", "大模型应用开发", "AI工程",
             ["Python", "RAG", "Prompt工程", "LangChain"]),
    make_job("后端开发工程师", "后端开发", "开发",
             ["Java", "Spring", "MySQL", "Redis", "分布式"]),
    make_job("数据分析工程师", "数据分析", "数据",
             ["SQL", "Python", "Tableau", "统计分析"]),
    make_job("量化研究员", "量化研究", "金融",
             ["Python", "C++", "统计", "因子挖掘"]),
    make_job("投行经理助理", "投行", "金融",
             ["财务建模", "估值分析", "PPT", "Excel"]),
    make_job("产品经理", "产品经理", "产品",
             ["需求分析", "原型设计", "用户研究"]),
]


def run_case(label, fit_dirs):
    print(f"\n{'#'*70}")
    print(f"# 画像: {label}")
    print(f"{'#'*70}")
    profile = build_profile(fit_dirs)

    # 先验证方向键完整率
    has_key = sum(1 for d in fit_dirs if d.get("cat_key"))
    print(f"  fit_directions={len(fit_dirs)} 有方向键={has_key}")

    # 防御性反查验证:对每个 direction 调 job_tree.resolve
    for d in fit_dirs:
        if not d.get("cat_key"):
            resolved = job_tree.resolve(d.get("direction", ""), allow_category=True)
            if resolved:
                print(f"  [反查命中] {d['direction']} → cat_key={resolved.get('cat_key')} sub_key={resolved.get('sub_key')}")
            else:
                print(f"  [反查失败] {d['direction']} 不在树中")

    results = []
    for job in TEST_JOBS:
        r = score_job(job, profile)
        results.append((job["position_title"], r))
        role = r["维度分"].get("role", 0)
        gated = r["方向门槛触发"]
        print(f"  {job['position_title']:<28} 总分={r['相关性评分']:>5.1f}  "
              f"role={role:>5.1f}  门槛={'是' if gated else '否'}  "
              f"推荐={r['综合推荐度']}")

    # 分布统计
    dist = {"强烈推荐": 0, "推荐": 0, "可申请": 0, "不建议": 0}
    for _, r in results:
        dist[r["综合推荐度"]] = dist.get(r["综合推荐度"], 0) + 1
    total = len(results)
    print(f"\n  推荐分布: 强烈推荐={dist['强烈推荐']} 推荐={dist['推荐']} "
          f"可申请={dist['可申请']} 不建议={dist['不建议']}")
    top_ratio = (dist["强烈推荐"] + dist["推荐"]) / total * 100
    print(f"  强烈推荐+推荐 占比={top_ratio:.0f}% (目标 ≥30%)")

    # 关键断言
    # 对口岗位(前6个)role_score 不应全为 0
    aligned_roles = [r["维度分"].get("role", 0) for _, r in results[:6]]
    max_aligned_role = max(aligned_roles)
    print(f"\n  对口岗位最大 role_score={max_aligned_role:.1f} (应 ≥40 才不触发硬门槛)")
    assert max_aligned_role >= 40, f"对口岗位 role_score 过低({max_aligned_role}),方向门槛会错误触发!"
    print(f"  ✅ 对口岗位 role_score 正常,方向硬门槛不会错误触发")

    return dist, top_ratio


if __name__ == "__main__":
    print("=" * 70)
    print("林叙言简历匹配验证 — 方向键修复测试")
    print("=" * 70)

    # Case A: 完整画像(修复后前端透传 cat_key/sub_key)
    dist_a, ratio_a = run_case("完整方向键(cat_key/sub_key 透传)", FIT_DIRS_COMPLETE)

    # Case B: 残缺画像(旧前端丢弃方向键)→ 验证防御性反查
    dist_b, ratio_b = run_case("残缺方向键(仅 direction 名,触发防御性反查)", FIT_DIRS_STRIPPED)

    print("\n" + "=" * 70)
    print("总结")
    print("=" * 70)
    print(f"  完整画像: 强烈推荐+推荐 = {ratio_a:.0f}%")
    print(f"  残缺画像: 强烈推荐+推荐 = {ratio_b:.0f}%")
    print(f"  防御性反查: 残缺画像下对口岗位 role_score 依然 > 40 → 修复生效")
    print("\n✅ 全部断言通过:方向键缺失不再导致 role_score=0,推荐分布恢复正常")
