"""
匹配评测集构建: 1 用户(林叙言) × 50 真实岗位
标注方式: 二分(relevant/irrelevant) - 基于job_subcategory是否在fit_directions里
分层: 15强相关 + 15部分相关 + 10技能有交集 + 10完全不对口
"""
import sqlite3
import json

# 林叙言的 fit_directions (来自 resume_parser LLM 解析)
FIT_DIRS = {
    "edge_ai": {"direction": "边缘AI/嵌入式AI", "cat_key": "robotics", "sub_key": "edge_ai",
                 "category_name": "机器人与智能体", "weight": 0.95},
    "embedded_sw": {"direction": "嵌入式软件", "cat_key": "development", "sub_key": "embedded_sw",
                    "category_name": "开发", "weight": 0.90},
    "ml": {"direction": "机器学习算法", "cat_key": "algorithm", "sub_key": "ml",
           "category_name": "算法", "weight": 0.70},
    "cv": {"direction": "CV算法", "cat_key": "algorithm", "sub_key": "cv",
           "category_name": "算法", "weight": 0.60},
    "communication": {"direction": "通信算法", "cat_key": "algorithm", "sub_key": "communication",
                      "category_name": "算法", "weight": 0.40},
}

# 林叙言的画像 (来自 test_scorer_linxuyan.py)
USER_PROFILE = {
    "user_id": "linxuyan",
    "name": "林叙言",
    "degree": "硕士",
    "major": "电子信息(嵌入式AI方向)",
    "school": "西安交通大学",
    "structured_keywords": [
        {"keyword": "Python", "category": "hard_skill"},
        {"keyword": "C++", "category": "hard_skill"},
        {"keyword": "C", "category": "hard_skill"},
        {"keyword": "TensorFlow Lite Micro", "category": "hard_skill"},
        {"keyword": "ARM", "category": "hard_skill"},
        {"keyword": "模型量化", "category": "hard_skill"},
        {"keyword": "PyTorch", "category": "hard_skill"},
        {"keyword": "OpenCV", "category": "hard_skill"},
        {"keyword": "ResNet", "category": "hard_skill"},
        {"keyword": "Scikit-learn", "category": "hard_skill"},
        {"keyword": "XGBoost", "category": "hard_skill"},
        {"keyword": "信号处理", "category": "hard_skill"},
        {"keyword": "MATLAB", "category": "hard_skill"},
        {"keyword": "强化学习", "category": "hard_skill"},
        {"keyword": "深度学习", "category": "hard_skill"},
        {"keyword": "机器学习", "category": "hard_skill"},
        {"keyword": "计算机视觉", "category": "hard_skill"},
        {"keyword": "嵌入式", "category": "hard_skill"},
        {"keyword": "Linux", "category": "hard_skill"},
        {"keyword": "RTOS", "category": "hard_skill"},
    ],
    "fit_directions": list(FIT_DIRS.values()),
    "target_cities": ["深圳", "上海", "北京", "杭州", "西安", "成都"],
    "target_companies": ["DJI 大疆", "宇树科技", "拓竹科技", "百度"],
    "target_industries": ["机器人", "自动驾驶", "芯片", "AI"],
}


def fetch_jobs():
    """从数据库抽取 50 个真实岗位"""
    conn = sqlite3.connect("data/jobs.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    def select(sql, params=()):
        cursor.execute(sql, params)
        return [dict(r) for r in cursor.fetchall()]

    jobs = []

    # 15 强相关: edge_ai(5) + embedded_sw(10)
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory='边缘AI/嵌入式AI'
        AND hard_skills != '[]' LIMIT 5
    """)
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory='嵌入式软件'
        AND hard_skills != '[]' AND min_education != '硕士' LIMIT 10
    """)

    # 15 部分相关: ml(8) + cv(4) + communication(3)
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory='机器学习算法'
        AND hard_skills != '[]' LIMIT 8
    """)
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory='CV算法'
        AND hard_skills != '[]' LIMIT 4
    """)
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory='通信算法'
        AND hard_skills != '[]' LIMIT 3
    """)

    # 15 边界样本(技能有3+交集但方向不对口): 后端(4) + 数据分析(3) + 测试开发(3) + FPGA(2) + IC验证(2) + 大模型(1)
    # 这些是 F3 泛技能刷分的高发场景
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory='后端开发'
        AND (hard_skills LIKE '%Python%' OR hard_skills LIKE '%C++%' OR hard_skills LIKE '%Linux%')
        AND hard_skills != '[]' LIMIT 4
    """)
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory='数据分析'
        AND (hard_skills LIKE '%Python%' OR hard_skills LIKE '%SQL%')
        AND hard_skills != '[]' LIMIT 3
    """)
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory='测试开发'
        AND (hard_skills LIKE '%Python%' OR hard_skills LIKE '%C++%' OR hard_skills LIKE '%Linux%')
        AND hard_skills != '[]' LIMIT 3
    """)
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory='FPGA开发'
        AND hard_skills != '[]' LIMIT 2
    """)
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory='IC验证'
        AND hard_skills != '[]' LIMIT 2
    """)
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory='大模型应用开发'
        AND (hard_skills LIKE '%Python%' OR hard_skills LIKE '%PyTorch%')
        AND hard_skills != '[]' LIMIT 1
    """)

    # 10 完全不对口: 财务(3) + 市场营销(3) + 人力资源(2) + 销售(2)
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory='财务'
        AND hard_skills != '[]' LIMIT 3
    """)
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory='市场营销'
        AND hard_skills != '[]' LIMIT 3
    """)
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory='人力资源' LIMIT 2
    """)
    jobs += select("""
        SELECT * FROM positions WHERE job_subcategory='销售' LIMIT 2
    """)

    conn.close()
    return jobs


def build_evalset():
    """构建评测集 + 自动标注 ground truth"""
    jobs = fetch_jobs()
    print(f"抽取到 {len(jobs)} 个岗位")

    # 解析 hard_skills JSON
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

    # 分层 + 标注
    evalset = {
        "user": USER_PROFILE,
        "fit_directions_subkeys": list(FIT_DIRS.keys()),
        "jobs": [],
    }

    # 人工可读的标注规则:
    # - relevant(2): job_subcategory 在 fit_directions 的 sub_key 列表里
    # - partial(1): 技能有交集(Python/C++/机器学习等) 但方向不在 fit_directions
    # - irrelevant(0): 方向不对口且技能无交集
    fit_subs = {"边缘AI/嵌入式AI", "嵌入式软件", "机器学习算法", "CV算法", "通信算法"}
    partial_subs = {"后端开发", "数据分析", "大模型应用开发", "测试开发", "FPGA开发", "IC验证"}

    for i, job in enumerate(jobs):
        sub = job.get("job_subcategory", "")
        hard = set(job.get("hard_skills", []))
        user_hard = {k["keyword"] for k in USER_PROFILE["structured_keywords"]}

        if sub in fit_subs:
            relevance = 2  # relevant
            label = "强相关"
        elif sub in partial_subs:
            # 技能交集判断: 有 ≥1 个技能交集即为 partial(边界样本)
            overlap = hard & user_hard
            if len(overlap) >= 1:
                relevance = 1  # partial
                label = f"边界(技能交集{len(overlap)}个)"
            else:
                relevance = 0
                label = "方向不对且技能无交集"
        else:
            relevance = 0  # irrelevant
            label = "完全不对口"

        evalset["jobs"].append({
            "eval_id": f"MX-{i+1:03d}",
            "job_id": job["id"],
            "company_name": job["company_name"],
            "position_title": job["position_title"],
            "job_category": job.get("job_category", ""),
            "job_subcategory": sub,
            "hard_skills": job.get("hard_skills", []),
            "min_education": job.get("min_education", ""),
            "city": job.get("city", ""),
            "company_tier": job.get("company_tier", ""),
            "major_required": job.get("major_required", ""),
            "major_category": job.get("major_category", ""),
            "ground_truth_relevance": relevance,
            "ground_truth_label": label,
        })

    return evalset


if __name__ == "__main__":
    evalset = build_evalset()

    # 统计分层
    dist = {0: 0, 1: 0, 2: 0}
    for j in evalset["jobs"]:
        dist[j["ground_truth_relevance"]] += 1

    print(f"\n评测集构建完成:")
    print(f"  总岗位数: {len(evalset['jobs'])}")
    print(f"  relevant(2)  强相关: {dist[2]}")
    print(f"  partial(1)   部分相关: {dist[1]}")
    print(f"  irrelevant(0) 不对口: {dist[0]}")

    # 存盘
    with open("eval/evalset_matching.json", "w", encoding="utf-8") as f:
        json.dump(evalset, f, ensure_ascii=False, indent=2)
    print(f"\n已保存到 eval/evalset_matching.json")

    # 打印样本预览
    print("\n=== 样本预览 ===")
    for j in evalset["jobs"][:5]:
        print(f"  {j['eval_id']} [{j['ground_truth_label']}] {j['company_name']} - {j['position_title']}({j['job_subcategory']})")
    print("  ...")
    for j in evalset["jobs"][-5:]:
        print(f"  {j['eval_id']} [{j['ground_truth_label']}] {j['company_name']} - {j['position_title']}({j['job_subcategory']})")
