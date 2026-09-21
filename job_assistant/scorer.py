"""
评分引擎 — 基于 JD 正文(非 title)与用户画像的匹配评分。

第一原则:评分必须可解释。每个分数项都有明确依据,简评引用 JD 要点。
对抗性审查:避免只看 title 评分,必须分析 JD 正文职责+要求。
"""
import re
from typing import Dict, Any, List

from models import UserProfile

# 岗位类别关键词
L1_KEYWORDS = ["fof", "基金研究", "基金筛选", "私募研究", "私募尽调", "自营投资",
               "组合管理", "portfolio", "fund research", "fund selection",
               "fund of fund", "due diligence"]
L2_KEYWORDS = ["资产配置", "大类资产", "asset allocation", "宏观策略", "宏观研究",
               "指数研究", "smart beta", "指数增强", "公募fof", "资产配置研究"]
L3_KEYWORDS = ["机构销售", "行业研究", "行业研究员", "ibd", "投行", "投资银行",
               "资管前台", "机构业务"]

# 技能匹配关键词
SKILL_FOF = ["fof", "基金筛选", "组合构建", "组合管理", "基金研究", "基金尽调",
             "portfolio", "fund selection", "fund research"]
SKILL_DD = ["尽调", "due diligence", "量化", "cta", "套利", "指增", "量化多头",
            "主观多头", "quant", "arbitrage"]
SKILL_ALLOC = ["资产配置", "asset allocation", "宏观策略", "宏观研究",
               "大类资产", "配置策略"]
SKILL_AI = ["ai", "人工智能", "数据分析", "python", "系统搭建", "vibecoding",
            "机器学习", "大模型", "数据平台"]
SKILL_OVERSEAS = ["海外", "跨境", "global", "offshore", "境外", "国际市场"]


def _has(text: str, keywords: List[str]) -> bool:
    text_lower = text.lower()
    return any(k.lower() in text_lower for k in keywords)


def classify_direction(jd_text: str, title: str = "") -> str:
    """基于 JD 正文+标题判断岗位类别"""
    combined = (title + " " + jd_text).lower()
    if _has(combined, L1_KEYWORDS):
        return "L1-私募研究FOF自营"
    if _has(combined, L2_KEYWORDS):
        return "L2-大类资产配置"
    if _has(combined, L3_KEYWORDS):
        return "L3-其他前台"
    return "L3-其他前台"


def score_skills(jd_text: str) -> tuple:
    """技能匹配评分(0-15)+ 命中技能列表"""
    score = 0
    hits = []
    if _has(jd_text, SKILL_FOF):
        score += 5; hits.append("FOF/基金筛选/组合管理")
    if _has(jd_text, SKILL_DD):
        score += 3; hits.append("私募尽调/量化/CTA/套利")
    if _has(jd_text, SKILL_ALLOC):
        score += 3; hits.append("资产配置/宏观策略")
    if _has(jd_text, SKILL_AI):
        score += 2; hits.append("AI/数据分析/系统")
    if _has(jd_text, SKILL_OVERSEAS):
        score += 2; hits.append("海外策略/跨境")
    return min(score, 15), hits


def parse_experience(jd_text: str) -> str:
    """从 JD 提取经验要求"""
    patterns = [
        r"(\d+)[-~到](\d+)\s*年", r"(\d+)\s*年以上", r"(\d+)\s*年经验",
        r"(\d+)\s*years?", r"experience.*?(\d+)", r"应届", r"在校",
    ]
    for p in patterns:
        m = re.search(p, jd_text, re.IGNORECASE)
        if m:
            return m.group(0)
    return "不限"


def parse_education(jd_text: str) -> str:
    if re.search(r"博士|phd|doctor", jd_text, re.IGNORECASE):
        return "博士"
    if re.search(r"硕士|master|研究生", jd_text, re.IGNORECASE):
        return "硕士及以上"
    if re.search(r"本科|bachelor|学士", jd_text, re.IGNORECASE):
        return "本科及以上"
    return "不限"


def is_graduate_window(jd_text: str, title: str = "") -> tuple:
    """判断是否为应届/管培窗口,返回 (是否窗口, 窗口说明)"""
    combined = (title + " " + jd_text).lower()
    window_kw = ["graduate", "管培", "analyst program", "management trainee",
                 "应届", "校招", "campus", "early career", "rotational",
                 "class of 2024", "class of 2025", "within 12 months",
                 "within 24 months", "2 years post-graduation", "recent graduate"]
    if _has(combined, window_kw):
        # 提取窗口说明
        for kw in window_kw:
            if kw.lower() in combined:
                return True, f"窗口标识: {kw}"
        return True, "管培/应届窗口"
    # 明确只限下一届的,不算窗口
    if re.search(r"class of 2026|2027届", combined):
        return False, "只限2026/2027届"
    return False, "社招岗位"


def score_job(job: Dict[str, str], profile: UserProfile) -> Dict[str, Any]:
    """
    对单条岗位评分。
    job 需含: title, company, jd_text, location, salary
    profile: 用户画像
    返回完整的评分结果 dict(直接可写入飞书表格)
    """
    title = job.get("title", "")
    company = job.get("company", "")
    jd_text = job.get("jd_text", "")
    location = job.get("location", "")
    salary = job.get("salary", "")
    jd_url = job.get("jd_url", "")
    posted = job.get("posted", "")

    # 1. 岗位类别
    direction = classify_direction(jd_text, title)
    dir_score = {"L1-私募研究FOF自营": 40, "L2-大类资产配置": 25,
                 "L3-其他前台": 10}[direction]

    # 2. 平台匹配
    from config import settings
    platform = "其他"
    for kw in ["中金", "中信", "华泰", "国泰海通", "广发", "招商"]:
        if kw in company:
            platform = "三中一华" if kw in ["中金", "中信", "中信建投", "华泰"] else "头部券商基金"
            break
    if platform == "其他":
        for kw in settings.TARGET_INSTITUTIONS:
            if kw.lower() in company.lower():
                platform = "外资头部" if any(
                    f.lower() in company.lower()
                    for f in ["goldman", "jpmorgan", "morgan", "hsbc", "standard chartered",
                              "ubs", "blackrock", "citi", "deutsche", "bnp", "nomura",
                              "barclays", "fidelity", "pimco", "vanguard"]) else "头部券商基金"
                break
    platform_score = {"三中一华": 20, "头部券商基金": 15, "外资头部": 20, "其他": 5}[platform]

    # 3. 经验匹配
    exp = parse_experience(jd_text)
    user_exp = profile.experience_years
    if "应届" in exp or "在校" in exp:
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

    # 4. 技能匹配
    skill_score, skill_hits = score_skills(jd_text)

    # 5. 学历匹配
    edu = parse_education(jd_text)
    edu_score = 10 if profile.degree in ["硕士", "博士"] else 5

    relevance = dir_score + platform_score + exp_score + skill_score + edu_score

    # 难度评分
    diff = 0
    if "3年" in exp or "5年" in exp or "10年" in exp:
        diff += 25
    elif "1" in exp or "2" in exp:
        diff += 15
    else:
        diff += 5
    if "博士" in edu or "mba" in edu.lower() or "phd" in edu.lower():
        diff += 25
    elif "硕士" in edu:
        diff += 15
    else:
        diff += 5
    if platform in ["三中一华", "外资头部"]:
        diff += 20
    else:
        diff += 10
    if re.search(r"cfa|cpa|frm", jd_text, re.IGNORECASE):
        diff += 15

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

    # 简评 — 必须引用 JD 要点
    hit_desc = "、".join(skill_hits) if skill_hits else "无直接技能命中"
    summary = (f"岗位类别{direction},平台{platform}。"
               f"JD职责与用户经验匹配点: {hit_desc}。"
               f"经验要求{exp}(用户{user_exp}年),学历要求{edu}。")
    if in_window:
        summary += f" {window_note},用户毕业1年符合窗口。"

    # 申请建议 — 针对 JD 要求具体化
    advice_parts = []
    if "FOF" in hit_desc or "基金筛选" in hit_desc:
        advice_parts.append("突出60+家私募尽调与20+专户组合管理经验")
    if "量化" in hit_desc or "CTA" in hit_desc:
        advice_parts.append("强调量化多头/CTA/套利全策略覆盖")
    if "AI" in hit_desc or "数据分析" in hit_desc:
        advice_parts.append("展示Vibecoding搭建私募基金信息平台的AI项目")
    if "资产配置" in hit_desc:
        advice_parts.append("将FOF组合经验转化为大类资产配置视角")
    if not advice_parts:
        advice_parts.append("结合自身FOF研究经验,挖掘与JD的交集点")
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
        "去重hash": f"{company}{title}{location}".replace(" ", ""),
        "应届窗口": "是" if in_window else "否",
        "是否在招": "是",
    }
