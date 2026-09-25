"""
评分引擎 — 基于 JD 正文与用户画像的匹配评分。

通用化设计(支持任意专业/职业阶段):
- 岗位类别由用户自定义的 direction_keywords 决定
- 技能匹配由用户的 core_skills 决定
- 不再硬编码任何行业关键词

第一原则:评分必须可解释,每个分数项有明确依据。
"""
import re
import hashlib
from typing import Dict, Any, List

from models import UserProfile


def _make_hash(company: str, title: str, location: str, jd_url: str = "") -> str:
    """
    生成岗位去重 hash。
    包含 公司+标题+地点+JD链接,确保同一岗位的不同抓取不会重复入库,
    同时不同岗位(即使同公司同城市)也不会误判为重复。
    使用 MD5 截断为 16 位,兼顾唯一性和存储长度。
    """
    raw = f"{company}|{title}|{location}|{jd_url}".lower().strip()
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def _has(text: str, keywords: List[str]) -> bool:
    text_lower = text.lower()
    return any(str(k).lower() in text_lower for k in keywords)


def classify_direction(jd_text: str, title: str,
                       direction_keywords: Dict[str, List[str]]) -> str:
    """
    基于用户自定义的方向关键词判断岗位类别。
    返回匹配度最高的方向名,无匹配返回"其他"。
    """
    combined = (title + " " + jd_text).lower()
    best_dir = "其他"
    best_count = 0
    for direction, keywords in direction_keywords.items():
        count = sum(1 for k in keywords if str(k).lower() in combined)
        if count > best_count:
            best_count = count
            best_dir = direction
    return best_dir if best_count > 0 else "其他"


def score_skills(jd_text: str, user_skills: List[str]) -> tuple:
    """
    技能匹配评分(0-15)。
    用户每有一个技能在 JD 中出现,得 3 分,上限 15。
    返回 (分数, 命中技能列表)
    """
    score = 0
    hits = []
    for skill in user_skills:
        if skill and skill.lower() in jd_text.lower():
            score += 3
            hits.append(skill)
            if score >= 15:
                break
    return min(score, 15), hits


def score_industry(jd_text: str, target_industries: List[str]) -> int:
    """行业匹配(0-10)"""
    if not target_industries:
        return 5  # 不限行业给中等分
    return 10 if _has(jd_text, target_industries) else 0


def score_company(company: str, target_companies: List[str]) -> tuple:
    """
    公司匹配(0-20)+ 平台层级。
    如果用户指定了目标公司,命中得 20 分;否则按公司名启发式判断层级。
    """
    if target_companies:
        for c in target_companies:
            if c.lower() in company.lower():
                return 20, "目标公司"
    # 无特定目标时,用通用启发式(知名企业加分)
    return 10, "其他"


def parse_experience(jd_text: str) -> str:
    """从 JD 提取经验要求"""
    patterns = [
        r"(\d+)[-~到](\d+)\s*年", r"(\d+)\s*年以上", r"(\d+)\s*年经验",
        r"(\d+)\s*years?", r"experience.*?(\d+)", r"应届", r"在校",
        r"无经验", r"fresh graduate", r"entry level",
    ]
    for p in patterns:
        m = re.search(p, jd_text, re.IGNORECASE)
        if m:
            return m.group(0)
    return "不限"


def parse_education(jd_text: str) -> str:
    if re.search(r"博士|phd|doctor", jd_text, re.IGNORECASE):
        return "博士"
    if re.search(r"硕士|master|研究生|mba", jd_text, re.IGNORECASE):
        return "硕士及以上"
    if re.search(r"本科|bachelor|学士", jd_text, re.IGNORECASE):
        return "本科及以上"
    return "不限"


def is_graduate_window(jd_text: str, title: str = "") -> tuple:
    """
    判断是否为应届/管培/校招窗口,返回 (是否窗口, 窗口说明)。
    通用:不限行业,识别graduate/管培/校招/应届等关键词。
    """
    combined = (title + " " + jd_text).lower()
    window_kw = [
        "graduate", "管培", "analyst program", "management trainee",
        "应届", "校招", "campus", "early career", "rotational",
        "class of 2024", "class of 2025", "within 12 months",
        "within 24 months", "2 years post-graduation", "recent graduate",
        "fresh graduate", "entry level", "internship", "实习",
    ]
    for kw in window_kw:
        if kw.lower() in combined:
            return True, f"窗口标识: {kw}"
    # 明确只限下一届的,不算窗口
    if re.search(r"class of 2026|2027届|2026届", combined):
        return False, "只限2026/2027届"
    return False, "社招岗位"


def score_job(job: Dict[str, str], profile: UserProfile) -> Dict[str, Any]:
    """
    对单条岗位评分(通用版)。
    job 需含: title, company, jd_text, location, salary, jd_url
    profile: 用户画像(direction_keywords 驱动分类)
    """
    title = job.get("title", "")
    company = job.get("company", "")
    jd_text = job.get("jd_text", "")
    location = job.get("location", "")
    salary = job.get("salary", "")
    jd_url = job.get("jd_url", "")
    posted = job.get("posted", "")

    # 1. 岗位类别(用户自定义方向)
    direction = classify_direction(jd_text, title, profile.direction_keywords)
    # 方向匹配分:命中用户目标方向=40,部分命中=25,未命中=10
    if direction != "其他" and direction in profile.direction_keywords:
        dir_score = 40
    elif direction != "其他":
        dir_score = 25
    else:
        dir_score = 10

    # 2. 平台/公司匹配
    platform_score, platform = score_company(company, profile.target_companies)

    # 3. 经验匹配
    exp = parse_experience(jd_text)
    user_exp = profile.experience_years
    if "应届" in exp or "在校" in exp or "fresh" in exp.lower() or "entry" in exp.lower():
        exp_score = 15
    elif re.search(r"(\d+)", exp):
        years = int(re.search(r"(\d+)", exp).group(1))
        if years <= user_exp + 1:
            exp_score = 15
        elif years <= user_exp + 3:
            exp_score = 10
        else:
            exp_score = 5
    else:
        exp_score = 12

    # 4. 技能匹配(用户自定义技能)
    skill_score, skill_hits = score_skills(jd_text, profile.core_skills)

    # 5. 学历匹配
    edu = parse_education(jd_text)
    user_degree = profile.degree
    if "博士" in edu:
        edu_score = 10 if user_degree == "博士" else (7 if user_degree == "硕士" else 3)
    elif "硕士" in edu:
        edu_score = 10 if user_degree in ["硕士", "博士"] else 5
    elif "本科" in edu:
        edu_score = 10
    else:
        edu_score = 8

    # 6. 行业匹配
    industry_score = score_industry(jd_text, profile.target_industries)

    relevance = dir_score + platform_score + exp_score + skill_score + edu_score + industry_score

    # 难度评分
    diff = 0
    if re.search(r"3年|5年|10年|3 years|5 years", exp):
        diff += 25
    elif re.search(r"1年|2年|1 year|2 years", exp):
        diff += 15
    else:
        diff += 5
    if "博士" in edu or "phd" in edu.lower():
        diff += 25
    elif "硕士" in edu or "mba" in edu.lower():
        diff += 15
    else:
        diff += 5
    if platform == "目标公司":
        diff += 20
    else:
        diff += 10
    # 证书要求
    cert_kw = ["cfa", "cpa", "frm", "法考", "律师", "注会", "保荐",
               "accenture", "pmp", "司法考试", "精算"]
    if _has(jd_text, cert_kw):
        diff += 10
        # 用户有证书则降低难度
        if any(c.lower() in jd_text.lower() for c in profile.target_certificates):
            diff -= 10

    # 综合推荐度
    if relevance >= 70:
        recommend = "优先申请"
    elif relevance >= 50:
        recommend = "可申请"
    elif relevance >= 30:
        recommend = "观望"
    else:
        recommend = "跳过"

    # 应届窗口
    in_window, window_note = is_graduate_window(jd_text, title)

    # 简评
    hit_desc = "、".join(skill_hits) if skill_hits else "无直接技能命中"
    summary = (f"岗位类别:{direction},平台:{platform}。"
               f"JD与用户匹配点: {hit_desc}。"
               f"经验要求:{exp}(用户{user_exp}年),学历要求:{edu}。")
    if in_window:
        summary += f" {window_note}。"

    # 申请建议
    advice_parts = []
    if skill_hits:
        advice_parts.append(f"突出以下匹配技能: {'、'.join(skill_hits[:3])}")
    if profile.school:
        advice_parts.append(f"强调{profile.school}{profile.degree}背景")
    if not advice_parts:
        advice_parts.append("结合自身背景挖掘与JD的交集")
    advice = "建议投递," + ";".join(advice_parts) + "。"

    return {
        "岗位标题": title,
        "公司": company,
        "部门": job.get("department", ""),
        "地点": location,
        "薪资范围": salary,
        "经验要求": exp,
        "学历要求": edu,
        "JD摘要": (job.get("jd_summary", "")[:200] + ("..." if len(job.get("jd_summary", "")) > 200 else "")),
        "JD链接": jd_url,
        "抓取日期": job.get("crawl_date", ""),
        "发布时间": posted,
        "岗位类别": direction,
        "平台层级": platform,
        "相关性评分": relevance,
        "难度评分": min(diff, 100),
        "综合推荐度": recommend,
        "简评": summary,
        "申请建议": advice,
        "申请状态": "未投递",
        "去重hash": _make_hash(company, title, location, jd_url),
        "应届窗口": "是" if in_window else "否",
        "是否在招": "是",
    }
