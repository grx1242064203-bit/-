
"""
高精度匹配引擎小范围测试 — 2-3 份模拟简历 + 约 18 条定制测试岗位。

测试目标:
1. 验证同义词归一化(简历写"分布式缓存" ↔ 岗位写"Redis")
2. 验证权重分层(硬技能缺失大幅拉低,软技能缺失影响较小)
3. 验证排序正确性(同方向岗位优先,明显不匹配的靠后)
4. 验证匹配理由可解释输出

设计决策:简历关键词不调用 LLM,直接硬编码模拟 structured_keywords,
聚焦匹配引擎(scorer.py + keyword_normalizer.py)逻辑验证,不混入 LLM 解析波动。

运行: python test_keyword_matching.py
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dataclasses import dataclass, field
from typing import Dict, List

from scorer import score_job
from keyword_normalizer import normalize, keyword_set_overlap


# ============================================================
# 3 份模拟简历的结构化关键词(硬编码,模拟 LLM 解析结果)
# ============================================================

RESUME_BACKEND = {
    "name": "张三 - 后端开发",
    "resume_text": "张三,清华大学计算机科学与技术硕士,2027届。"
                   "项目经历:美团外卖推荐系统(Python/FastAPI/Redis/MySQL/Docker),"
                   "蚂蚁金服风控系统(Java/Spring Boot/Kafka/Elasticsearch)。"
                   "实习:字节跳动后端开发实习生。技能:Python,Java,Go,Docker,Kubernetes,"
                   "分布式系统,微服务,Redis,MySQL,Kafka,Elasticsearch,CFA Level 1,英语 CET-6。",
    "structured_keywords": [
        {"kw": "Python", "standard": "Python", "category": "hard_skill", "weight": 5.0, "resume_section": "project", "source": "resume_llm"},
        {"kw": "Java", "standard": "Java", "category": "hard_skill", "weight": 5.0, "resume_section": "project", "source": "resume_llm"},
        {"kw": "Spring Boot", "standard": "spring", "category": "framework", "weight": 4.5, "resume_section": "project", "source": "resume_llm"},
        {"kw": "FastAPI", "standard": "fastapi", "category": "framework", "weight": 4.5, "resume_section": "project", "source": "resume_llm"},
        {"kw": "Redis", "standard": "redis", "category": "tool", "weight": 4.5, "resume_section": "project", "source": "resume_llm"},
        {"kw": "分布式缓存", "standard": "redis", "category": "skill", "weight": 4.0, "resume_section": "summary", "source": "resume_llm"},
        {"kw": "MySQL", "standard": "mysql", "category": "tool", "weight": 4.0, "resume_section": "project", "source": "resume_llm"},
        {"kw": "Kafka", "standard": "kafka", "category": "tool", "weight": 3.5, "resume_section": "project", "source": "resume_llm"},
        {"kw": "Elasticsearch", "standard": "elasticsearch", "category": "tool", "weight": 3.5, "resume_section": "project", "source": "resume_llm"},
        {"kw": "Docker", "standard": "docker", "category": "tool", "weight": 3.5, "resume_section": "skill", "source": "resume_llm"},
        {"kw": "Kubernetes", "standard": "kubernetes", "category": "tool", "weight": 3.0, "resume_section": "skill", "source": "resume_llm"},
        {"kw": "Go", "standard": "go", "category": "hard_skill", "weight": 2.5, "resume_section": "skill", "source": "resume_llm"},
        {"kw": "微服务", "standard": "distributed_systems", "category": "skill", "weight": 4.0, "resume_section": "project", "source": "resume_llm"},
        {"kw": "分布式系统", "standard": "distributed_systems", "category": "skill", "weight": 4.0, "resume_section": "summary", "source": "resume_llm"},
        {"kw": "CFA Level 1", "standard": "cfa", "category": "cert", "weight": 3.0, "resume_section": "other", "source": "resume_llm"},
        {"kw": "英语 CET-6", "standard": None, "category": "language", "weight": 2.0, "resume_section": "other", "source": "resume_llm"},
        {"kw": "清华大学", "standard": None, "category": "education", "weight": 3.0, "resume_section": "education", "source": "resume_llm"},
        {"kw": "计算机科学与技术", "standard": "computer_science", "category": "education", "weight": 4.0, "resume_section": "education", "source": "resume_llm"},
        {"kw": "硕士", "standard": "education", "category": "education", "weight": 3.5, "resume_section": "education", "source": "resume_llm"},
        {"kw": "后端开发", "standard": "backend_development", "category": "role", "weight": 5.0, "resume_section": "summary", "source": "resume_llm"},
        {"kw": "北京", "standard": "beijing", "category": "city", "weight": 3.0, "resume_section": "other", "source": "resume_llm"},
        {"kw": "上海", "standard": "shanghai", "category": "city", "weight": 2.5, "resume_section": "other", "source": "resume_llm"},
        {"kw": "金融科技", "standard": "finance", "category": "domain", "weight": 3.0, "resume_section": "project", "source": "resume_llm"},
    ],
    "degree": "硕士",
    "major": "计算机科学与技术",
    "target_cities": ["北京", "上海"],
    "target_certificates": ["CFA"],
    "target_industries": ["互联网", "金融科技"],
    "preferred_company_types": ["民企", "外企"],
}


RESUME_PRODUCT = {
    "name": "李四 - 产品经理",
    "resume_text": "李四,北京大学工商管理本科,2026届。"
                   "项目:小红书笔记推荐产品(PM/用户增长),美团到店业务改版。"
                   "实习:阿里巴巴产品经理实习生(淘宝直播)。"
                   "技能:产品设计,用户研究,数据分析,SQL,A/B测试,Figma,"
                   "敏捷开发,Scrum,PPT,Xmind,英语 CET-6。",
    "structured_keywords": [
        {"kw": "产品经理", "standard": "product_manager", "category": "role", "weight": 5.0, "resume_section": "summary", "source": "resume_llm"},
        {"kw": "产品设计", "standard": "ux_design", "category": "skill", "weight": 4.5, "resume_section": "project", "source": "resume_llm"},
        {"kw": "用户增长", "standard": "operation", "category": "skill", "weight": 4.0, "resume_section": "project", "source": "resume_llm"},
        {"kw": "用户研究", "standard": "skill", "category": "skill", "weight": 4.0, "resume_section": "skill", "source": "resume_llm"},
        {"kw": "数据分析", "standard": "data_analysis", "category": "skill", "weight": 3.5, "resume_section": "skill", "source": "resume_llm"},
        {"kw": "SQL", "standard": "mysql", "category": "tool", "weight": 3.0, "resume_section": "skill", "source": "resume_llm"},
        {"kw": "A/B测试", "standard": "skill", "category": "skill", "weight": 3.0, "resume_section": "skill", "source": "resume_llm"},
        {"kw": "Figma", "standard": "figma", "category": "tool", "weight": 3.0, "resume_section": "skill", "source": "resume_llm"},
        {"kw": "敏捷开发", "standard": "agile", "category": "skill", "weight": 3.0, "resume_section": "skill", "source": "resume_llm"},
        {"kw": "Scrum", "standard": "scrum", "category": "skill", "weight": 2.5, "resume_section": "skill", "source": "resume_llm"},
        {"kw": "北京大学", "standard": None, "category": "education", "weight": 3.5, "resume_section": "education", "source": "resume_llm"},
        {"kw": "工商管理", "standard": "business_administration", "category": "education", "weight": 4.0, "resume_section": "education", "source": "resume_llm"},
        {"kw": "本科", "standard": "education", "category": "education", "weight": 3.0, "resume_section": "education", "source": "resume_llm"},
        {"kw": "北京", "standard": "beijing", "category": "city", "weight": 3.0, "resume_section": "other", "source": "resume_llm"},
        {"kw": "上海", "standard": "shanghai", "category": "city", "weight": 2.5, "resume_section": "other", "source": "resume_llm"},
        {"kw": "互联网", "standard": None, "category": "domain", "weight": 3.0, "resume_section": "project", "source": "resume_llm"},
        {"kw": "社交", "standard": None, "category": "domain", "weight": 2.5, "resume_section": "project", "source": "resume_llm"},
    ],
    "degree": "本科",
    "major": "工商管理",
    "target_cities": ["北京", "上海"],
    "target_certificates": [],
    "target_industries": ["互联网"],
    "preferred_company_types": ["民企"],
}


RESUME_FINANCE = {
    "name": "王五 - 金融/CFA",
    "resume_text": "王五,复旦大学数学本科+CFA,2026届。"
                   "实习:中信证券投行部(债券承销),国泰君安研究所(行业研究)。"
                   "技能:Excel建模,VBA,SQL,Python数据分析,估值建模,"
                   "CFA Level 1,CPA 会计,英语 GMAT 720,日语 N2。",
    "structured_keywords": [
        {"kw": "CFA", "standard": "cfa", "category": "cert", "weight": 5.0, "resume_section": "summary", "source": "resume_llm"},
        {"kw": "CPA 会计", "standard": "cpa", "category": "cert", "weight": 3.0, "resume_section": "other", "source": "resume_llm"},
        {"kw": "投行", "standard": "investment_banking", "category": "role", "weight": 4.5, "resume_section": "project", "source": "resume_llm"},
        {"kw": "投资银行", "standard": "investment_banking", "category": "role", "weight": 4.5, "resume_section": "project", "source": "resume_llm"},
        {"kw": "行业研究", "standard": None, "category": "skill", "weight": 4.0, "resume_section": "project", "source": "resume_llm"},
        {"kw": "Excel建模", "standard": None, "category": "skill", "weight": 3.5, "resume_section": "skill", "source": "resume_llm"},
        {"kw": "估值建模", "standard": None, "category": "skill", "weight": 3.5, "resume_section": "skill", "source": "resume_llm"},
        {"kw": "VBA", "standard": None, "category": "tool", "weight": 2.5, "resume_section": "skill", "source": "resume_llm"},
        {"kw": "SQL", "standard": "mysql", "category": "tool", "weight": 2.5, "resume_section": "skill", "source": "resume_llm"},
        {"kw": "Python", "standard": "python", "category": "hard_skill", "weight": 2.5, "resume_section": "skill", "source": "resume_llm"},
        {"kw": "复旦大学", "standard": None, "category": "education", "weight": 3.5, "resume_section": "education", "source": "resume_llm"},
        {"kw": "数学", "standard": "mathematics", "category": "education", "weight": 4.0, "resume_section": "education", "source": "resume_llm"},
        {"kw": "本科", "standard": "education", "category": "education", "weight": 3.0, "resume_section": "education", "source": "resume_llm"},
        {"kw": "金融", "standard": "finance", "category": "domain", "weight": 4.5, "resume_section": "project", "source": "resume_llm"},
        {"kw": "北京", "standard": "beijing", "category": "city", "weight": 3.0, "resume_section": "other", "source": "resume_llm"},
        {"kw": "上海", "standard": "shanghai", "category": "city", "weight": 3.0, "resume_section": "other", "source": "resume_llm"},
        {"kw": "日语", "standard": "language", "category": "language", "weight": 2.0, "resume_section": "other", "source": "resume_llm"},
    ],
    "degree": "本科",
    "major": "数学",
    "target_cities": ["北京", "上海"],
    "target_certificates": ["CFA", "CPA"],
    "target_industries": ["金融"],
    "preferred_company_types": ["外企", "国央企"],
}


# ============================================================
# 18 条测试岗位(手工构造,字段与 llm_enricher.py 输出对齐)
# ============================================================

TEST_JOBS = [
    # --- 后端开发高匹配(预期 Top3) ---
    {
        "position_title": "后端开发工程师 - 推荐算法平台",
        "company_name": "美团",
        "job_category": "研发", "job_subcategory": "后端开发",
        "hard_skills": ["Python", "Go", "Redis", "MySQL", "Kafka"],
        "soft_skills": ["沟通", "团队协作"],
        "certifications": [], "languages": ["英语CET-6"],
        "major_required": "计算机相关", "major_category": "工科",
        "min_education": "本科", "city": "北京",
        "keywords": ["后端", "分布式", "微服务", "推荐系统", "高并发"],
        "jd_summary": "推荐平台后端,负责高并发接口和分布式缓存架构",
        "difficulty": "最激烈", "location": "北京",
    },
    {
        "position_title": "Java 后端开发工程师 - 风控中台",
        "company_name": "蚂蚁集团",
        "job_category": "研发", "job_subcategory": "后端开发",
        "hard_skills": ["Java", "Spring Boot", "Kafka", "Elasticsearch"],
        "soft_skills": ["沟通", "问题定位"],
        "certifications": [], "languages": ["英语"],
        "major_required": "计算机相关", "major_category": "工科",
        "min_education": "本科", "city": "上海",
        "keywords": ["Java", "微服务", "风控", "中台", "分布式"],
        "jd_summary": "Java 后端,风控中台架构",
        "difficulty": "最激烈", "location": "上海",
    },
    {
        "position_title": "后端开发实习生 - 基础架构",
        "company_name": "字节跳动",
        "job_category": "研发", "job_subcategory": "后端开发",
        "hard_skills": ["Go", "Redis", "MySQL", "Docker"],
        "soft_skills": [],
        "certifications": [], "languages": [],
        "major_required": "计算机相关", "major_category": "工科",
        "min_education": "本科", "city": "北京",
        "keywords": ["后端", "基础架构", "容器化"],
        "jd_summary": "基础架构后端,容器化基础设施",
        "difficulty": "较为激烈", "location": "北京",
    },

    # --- 后端开发中匹配(部分命中) ---
    {
        "position_title": "全栈工程师 - 内部工具",
        "company_name": "腾讯",
        "job_category": "研发", "job_subcategory": "全栈",
        "hard_skills": ["Python", "JavaScript", "React", "Redis"],
        "soft_skills": ["沟通"],
        "certifications": [], "languages": [],
        "major_required": "不限", "major_category": "不限",
        "min_education": "本科", "city": "深圳",
        "keywords": ["全栈", "前端", "后端"],
        "jd_summary": "全栈开发,内部工具产品",
        "difficulty": "中等难度", "location": "深圳",
    },

    # --- 后端开发低匹配(明显不匹配) ---
    {
        "position_title": "前端开发工程师 - 社区产品",
        "company_name": "小红书",
        "job_category": "研发", "job_subcategory": "前端",
        "hard_skills": ["React", "TypeScript", "Webpack"],
        "soft_skills": ["沟通"],
        "certifications": [], "languages": [],
        "major_required": "不限", "major_category": "不限",
        "min_education": "本科", "city": "上海",
        "keywords": ["前端", "React", "社区"],
        "jd_summary": "Web 前端,社区产品",
        "difficulty": "较为激烈", "location": "上海",
    },
    {
        "position_title": "算法工程师 - NLP",
        "company_name": "百度",
        "job_category": "研发", "job_subcategory": "算法",
        "hard_skills": ["Python", "PyTorch", "TensorFlow", "NLP"],
        "soft_skills": ["文献阅读"],
        "certifications": [], "languages": [],
        "major_required": "计算机/数学", "major_category": "工科",
        "min_education": "硕士", "city": "北京",
        "keywords": ["算法", "NLP", "大模型", "深度学习"],
        "jd_summary": "NLP 算法研究与落地",
        "difficulty": "最激烈", "location": "北京",
    },

    # --- 产品经理高匹配 ---
    {
        "position_title": "产品经理 - 用户增长",
        "company_name": "小红书",
        "job_category": "产品", "job_subcategory": "用户增长",
        "hard_skills": ["SQL", "数据分析", "A/B测试"],
        "soft_skills": ["沟通", "跨团队协作"],
        "certifications": [], "languages": [],
        "major_required": "不限", "major_category": "不限",
        "min_education": "本科", "city": "上海",
        "keywords": ["产品", "用户增长", "社交", "数据分析"],
        "jd_summary": "社区产品用户增长 PM",
        "difficulty": "较为激烈", "location": "上海",
    },
    {
        "position_title": "产品经理 - 电商业务",
        "company_name": "美团",
        "job_category": "产品", "job_subcategory": "商业产品",
        "hard_skills": ["SQL", "Figma"],
        "soft_skills": ["敏捷", "Scrum"],
        "certifications": [], "languages": [],
        "major_required": "不限", "major_category": "不限",
        "min_education": "本科", "city": "北京",
        "keywords": ["产品", "电商", "商家", "敏捷"],
        "jd_summary": "到店业务商家端产品",
        "difficulty": "较为激烈", "location": "北京",
    },
    {
        "position_title": "产品经理实习生 - 直播",
        "company_name": "阿里巴巴",
        "job_category": "产品", "job_subcategory": "直播",
        "hard_skills": ["数据分析"],
        "soft_skills": ["沟通"],
        "certifications": [], "languages": [],
        "major_required": "不限", "major_category": "不限",
        "min_education": "本科", "city": "杭州",
        "keywords": ["产品", "直播", "内容"],
        "jd_summary": "淘宝直播产品实习",
        "difficulty": "中等难度", "location": "杭州",
    },

    # --- 产品经理不匹配 ---
    {
        "position_title": "iOS 开发工程师",
        "company_name": "网易",
        "job_category": "研发", "job_subcategory": "移动端",
        "hard_skills": ["Swift", "Objective-C", "iOS"],
        "soft_skills": [],
        "certifications": [], "languages": [],
        "major_required": "不限", "major_category": "不限",
        "min_education": "本科", "city": "广州",
        "keywords": ["iOS", "移动端", "Swift"],
        "jd_summary": "网易云音乐 iOS 客户端",
        "difficulty": "中等难度", "location": "广州",
    },

    # --- 金融/CFA 高匹配 ---
    {
        "position_title": "投行部 - 债券承销岗",
        "company_name": "中信证券",
        "job_category": "金融", "job_subcategory": "投行",
        "hard_skills": ["Excel", "估值建模"],
        "soft_skills": ["抗压", "文字能力"],
        "certifications": ["CFA"], "languages": ["英语"],
        "major_required": "金融/经济/数学", "major_category": "商科",
        "min_education": "硕士", "city": "北京",
        "keywords": ["投行", "债券", "承销", "资本市场"],
        "jd_summary": "投行部债券承销业务",
        "difficulty": "最激烈", "location": "北京",
    },
    {
        "position_title": "研究所 - 行业研究员",
        "company_name": "国泰君安",
        "job_category": "金融", "job_subcategory": "研究",
        "hard_skills": ["Excel建模", "估值"],
        "soft_skills": ["文字能力", "逻辑"],
        "certifications": ["CFA", "CPA"], "languages": ["英语"],
        "major_required": "金融/经济/数学", "major_category": "商科",
        "min_education": "本科", "city": "上海",
        "keywords": ["研究", "行业", "深度报告"],
        "jd_summary": "行业研究覆盖互联网/消费",
        "difficulty": "较为激烈", "location": "上海",
    },
    {
        "position_title": "资产管理 - 买方研究员",
        "company_name": "易方达基金",
        "job_category": "金融", "job_subcategory": "资管",
        "hard_skills": ["Excel建模", "估值"],
        "soft_skills": [],
        "certifications": ["CFA"], "languages": [],
        "major_required": "金融相关", "major_category": "商科",
        "min_education": "本科", "city": "广州",
        "keywords": ["资管", "买方", "投研"],
        "jd_summary": "公募基金买方研究",
        "difficulty": "较为激烈", "location": "广州",
    },

    # --- 金融/CFA 不匹配 ---
    {
        "position_title": "后端开发工程师 - 基础架构",
        "company_name": "阿里巴巴",
        "job_category": "研发", "job_subcategory": "后端",
        "hard_skills": ["Java", "Spring", "Docker", "Kubernetes"],
        "soft_skills": [],
        "certifications": [], "languages": [],
        "major_required": "计算机相关", "major_category": "工科",
        "min_education": "本科", "city": "杭州",
        "keywords": ["后端", "基础架构"],
        "jd_summary": "阿里云基础架构后端",
        "difficulty": "最激烈", "location": "杭州",
    },

    # --- 通用/跨界岗位 ---
    {
        "position_title": "数据分析师",
        "company_name": "京东",
        "job_category": "数据分析", "job_subcategory": "商业分析",
        "hard_skills": ["SQL", "Python", "Excel"],
        "soft_skills": [],
        "certifications": [], "languages": [],
        "major_required": "不限", "major_category": "不限",
        "min_education": "本科", "city": "北京",
        "keywords": ["数据分析", "BI", "报表"],
        "jd_summary": "商业分析,业务数据洞察",
        "difficulty": "中等难度", "location": "北京",
    },
    {
        "position_title": "机器学习工程师",
        "company_name": "华为",
        "job_category": "研发", "job_subcategory": "算法",
        "hard_skills": ["Python", "PyTorch", "TensorFlow", "Distributed Training"],
        "soft_skills": [],
        "certifications": [], "languages": [],
        "major_required": "计算机/数学", "major_category": "工科",
        "min_education": "硕士", "city": "深圳",
        "keywords": ["AI", "大模型", "训练", "推理"],
        "jd_summary": "大模型训练与推理优化",
        "difficulty": "最激烈", "location": "深圳",
    },
    {
        "position_title": "管培生 - 技术方向",
        "company_name": "招商银行",
        "job_category": "管培", "job_subcategory": "MT",
        "hard_skills": ["Python", "SQL"],
        "soft_skills": ["领导力", "沟通"],
        "certifications": [], "languages": [],
        "major_required": "不限", "major_category": "不限",
        "min_education": "本科", "city": "上海",
        "keywords": ["管培", "金融科技", "银行"],
        "jd_summary": "银行技术方向管培,轮岗 2 年",
        "difficulty": "较为激烈", "location": "上海",
    },
    {
        "position_title": "运营实习生",
        "company_name": "拼多多",
        "job_category": "运营", "job_subcategory": "活动运营",
        "hard_skills": [],
        "soft_skills": ["沟通", "执行力"],
        "certifications": [], "languages": [],
        "major_required": "不限", "major_category": "不限",
        "min_education": "本科", "city": "上海",
        "keywords": ["运营", "活动", "商家"],
        "jd_summary": "电商活动运营实习",
        "difficulty": "较低难度", "location": "上海",
    },
]


def build_profile(resume_data: Dict):
    """把模拟简历数据转成 UserProfile dataclass"""
    from models import UserProfile
    p = UserProfile()
    p.degree = resume_data["degree"]
    p.major = resume_data["major"]
    p.target_cities = resume_data["target_cities"]
    p.target_certificates = resume_data["target_certificates"]
    p.target_industries = resume_data["target_industries"]
    p.preferred_company_types = resume_data["preferred_company_types"]
    p.structured_keywords = resume_data["structured_keywords"]
    p.resume_text = resume_data["resume_text"]
    return p


def print_result(name: str, profile, jobs: List[Dict]):
    print(f"\n{'='*70}")
    print(f"简历: {name}")
    print(f"学历: {profile.degree}  专业: {profile.major}  目标城市: {profile.target_cities}")
    print(f"关键词数量: {len(profile.structured_keywords)}  核心硬技能: ", end="")
    core = [t for t in profile.structured_keywords if t.get("category") in ("hard_skill", "framework")]
    print(f"{', '.join(t.get('standard', t.get('kw','')) for t in core[:8])}")
    print(f"{'='*70}")

    scored = []
    for job in jobs:
        result = score_job(job, profile)
        scored.append({**job, **result})

    scored.sort(key=lambda x: x["相关性评分"], reverse=True)

    for i, s in enumerate(scored):
        score = s["相关性评分"]
        rec = s["综合推荐度"]
        title = s["position_title"]
        company = s["company_name"]
        loc = s["location"]
        dims = s.get("维度分", {})
        reasons = s.get("匹配理由", [])

        bar = "█" * int(score / 5) + "░" * (20 - int(score / 5))

        print(f"\n#{i+1} [{score:5.1f}] {bar}  {rec}")
        print(f"    {company} | {title} | {loc}")
        print(f"    维度分: skill={dims.get('skill',0):.0f}  hard={dims.get('hard_skill',0):.0f}  "
              f"cert={dims.get('cert',0):.0f}  edu={dims.get('education',0):.0f}  "
              f"major={dims.get('major',0):.0f}  city={dims.get('city',0):.0f}  "
              f"role={dims.get('role',0):.0f}  soft={dims.get('soft_skill',0):.0f}")
        if reasons:
            for r in reasons[:3]:
                print(f"      · {r}")

    # --- 断言检查 ---
    scores = [(s["相关性评分"], s["position_title"]) for s in scored]
    top_score = scores[0][0]
    low_score = scores[-1][0]
    print(f"\n--- 排序校验 ---")
    print(f"最高分: {top_score:.1f} 岗位: {scores[0][1]}")
    print(f"最低分: {low_score:.1f} 岗位: {scores[-1][1]}")
    if top_score >= 70 and low_score <= 40:
        print("✓ PASS: 高分岗位靠前,低分岗位靠后")
    else:
        print("✗ FAIL: 排序不符合预期")
    return scored


def test_normalizer():
    print(f"\n{'='*70}")
    print("关键词标准化测试")
    print(f"{'='*70}")
    cases = [
        ("Redis", "redis", True),
        ("分布式缓存", "redis", True),
        ("微服务", "distributed_systems", True),
        ("敏捷开发", "agile", True),
        ("Scrum", "scrum", True),
        ("机器学习", "machine_learning", True),
        ("ML", "machine_learning", True),
        ("后端开发", "backend_development", True),
        ("Python专家", None, False),
        ("XYZ技术", None, False),
    ]
    all_pass = True
    for kw, expected_std, expected_hit in cases:
        std, hit = normalize(kw)
        status = "✓" if hit == expected_hit and (expected_std is None or std == expected_std) else "✗"
        if status == "✗":
            all_pass = False
        exp = f"[{expected_std}]" if expected_hit else "不命中"
        got = f"[{std}]" if hit else "不命中"
        print(f"  {status} normalize('{kw}') → {got} (预期: {exp})")

    # keyword_set_overlap 测试
    print(f"\n同义词归一化 overlap 测试:")
    u = ["分布式缓存", "微服务", "敏捷开发", "Python"]
    j = ["Redis", "微服务架构", "Scrum", "Python"]
    hits, jac, pairs = keyword_set_overlap(u, j)
    print(f"  用户: {u}")
    print(f"  岗位: {j}")
    print(f"  命中数: {hits}  Jaccard: {jac:.2f}  命中对: {pairs}")
    if hits >= 3:
        print("  ✓ PASS: 同义词归一化生效(分布式缓存↔Redis,敏捷开发↔Scrum 命中)")
    else:
        print("  ✗ FAIL: 同义词归一化未生效")

    return all_pass


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    ok = test_normalizer()

    profiles = [
        ("后端开发", build_profile(RESUME_BACKEND)),
        ("产品经理", build_profile(RESUME_PRODUCT)),
        ("金融/CFA", build_profile(RESUME_FINANCE)),
    ]

    all_results = {}
    for name, profile in profiles:
        all_results[name] = print_result(name, profile, TEST_JOBS)

    print(f"\n{'='*70}")
    print("跨简历排序交叉验证:同一岗位在不同简历下的排名差异")
    print(f"{'='*70}")
    for job_idx in [0, 6, 12]:
        title = TEST_JOBS[job_idx]["position_title"]
        print(f"\n  岗位: {title}")
        for name, results in all_results.items():
            s = results[job_idx]["相关性评分"]
            print(f"    {name:6s}: {s:5.1f}")
