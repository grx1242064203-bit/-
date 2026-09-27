"""
评分引擎 — 基于 JD 正文与用户画像的匹配评分。

通用化设计(支持任意专业/职业阶段):
- 岗位类别由用户自定义的 direction_keywords 决定
- 技能匹配由用户的 core_skills 决定
- 不再硬编码任何行业关键词

第一原则:评分必须可解释,每个分数项有明确依据。
"""
import re
import time
import hashlib
from datetime import datetime
from typing import Dict, Any, List

from models import UserProfile


def _build_url_field(url: str) -> dict:
    """构造飞书 URL 字段(type=15)的值。

    飞书 URL 字段只接受 {"text": str, "link": str} 对象。
    空字符串或非法 URL 会触发 1254068 URLFieldDetailFail。
    空值时返回 None(调用方需在写入前剔除 None 值字段)。
    """
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url:
        return None
    # 确保 URL 带协议前缀,否则飞书可能判定为非法
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return {"text": url, "link": url}


def _to_timestamp_ms(date_str: str) -> int:
    """将日期字符串转为飞书日期字段(type=5)所需的 Unix 毫秒时间戳。

    飞书日期字段只接受数字(毫秒时间戳),传入字符串会触发 1254064 DatetimeFieldConvFail。
    解析失败时返回当前时间戳,避免空值导致写入失败。
    """
    if not date_str or not isinstance(date_str, str):
        return int(time.time() * 1000)
    date_str = date_str.strip()
    # 尝试多种常见格式
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    # 解析失败,返回当前时间戳
    return int(time.time() * 1000)


def _normalize_for_hash(text: str) -> str:
    """
    归一化文本用于去重 hash:
    - 去除括号及括号内内容(如 "产品经理(北京)" → "产品经理")
    - 去除所有空白字符
    - 转小写
    - 去除常见后缀词(如 "招聘", "急招", "热招")
    """
    if not text:
        return ""
    text = text.lower()
    # 去除括号及内容: (...) 【...】 [...] （...）
    text = re.sub(r"[\(\)（）\[\]【】][^\(\)（）\[\]【】]*[\(\)（）\[\]【】]", "", text)
    # 去除空白
    text = re.sub(r"\s+", "", text)
    # 去除常见招聘后缀
    for suffix in ["招聘", "急招", "热招", "校招", "社招", "实习", "应届"]:
        text = text.replace(suffix, "")
    return text.strip()


def _make_hash(company: str, title: str, location: str = "", jd_url: str = "") -> str:
    """
    生成岗位去重 hash。

    第一原则:同一公司同一岗位只显示一次(聚类去重)。
    因此 hash 仅基于 公司+岗位标题(归一化),不包含地点和 URL。
    - 归一化:去除括号、空白、招聘后缀,避免"产品经理(北京)"与"产品经理"被判为不同
    - 不同地点的同一岗位视为同一岗位聚类,保留先入的那条
    """
    norm_company = _normalize_for_hash(company)
    norm_title = _normalize_for_hash(title)
    raw = f"{norm_company}|{norm_title}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def extract_deadline_from_jd(jd_text: str) -> str:
    """
    从 JD 文本中用正则提取投递截止日期(校招岗位常用)。
    返回 YYYY-MM-DD 格式字符串,提取失败返回空字符串。
    兜底:若正则未命中,返回空(后续可由 LLM 提取,但正则优先避免 API 开销)。
    """
    if not jd_text:
        return ""
    # 匹配 "截止日期: 2026-10-31" / "截止到 2026/10/31" / "投递截止 2026年10月31日"
    patterns = [
        r"截止[日期时间到为]*\s*[:：]?\s*(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})",
        r"投递截止[日期时间到为]*\s*[:：]?\s*(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})",
        r"网申截止[日期时间到为]*\s*[:：]?\s*(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})",
        r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})\s*[日号]?\s*截止",
    ]
    for p in patterns:
        m = re.search(p, jd_text)
        if m:
            try:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
                    return f"{y:04d}-{mo:02d}-{d:02d}"
            except (ValueError, IndexError):
                continue
    return ""


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


def score_skills(jd_text: str, user_skills: List[str], hard_skills: str = "") -> tuple:
    """
    技能匹配评分(0-15)。
    优先用结构化字段 hard_skills 做精准匹配,降级到 jd_text 全文匹配。
    用户每有一个技能在岗位要求中出现,得 3 分,上限 15。
    返回 (分数, 命中技能列表)
    """
    score = 0
    hits = []
    # 优先用结构化 hard_skills 字段
    search_text = (hard_skills or "").lower()
    if not search_text:
        search_text = jd_text.lower()
    for skill in user_skills:
        if skill and skill.lower() in search_text:
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
    判断是否为应届/管培/校招窗口。

    严格判断:必须在 JD 正文(含标题)中找到明确的"接受/要求应届生"的表述,
    不能仅因为出现"graduate"等英文词就判定。

    年份动态计算:当前年份和下一年份(如 2026年→匹配 2026届/2027届)。

    返回 (是否窗口, 窗口说明)。
    """
    from datetime import datetime
    cur_year = datetime.now().year
    next_year = cur_year + 1
    cur_year_short = str(cur_year)[2:]  # 26
    next_year_short = str(next_year)[2:]  # 27

    combined = (title + "\n" + jd_text)
    combined_lower = combined.lower()

    # 明确的应届/校招/管培信号(中文优先,最可靠)
    explicit_campus_kw = [
        "应届毕业生", "应届生", "校园招聘", "校招", "管培生", "管理培训生",
        "接受应届生", "招收应届", "面向应届", "仅限应届",
        "应届可投", "应届生优先",
        "秋招", "春招", "提前批",
        # 动态年份届数
        f"{cur_year}届", f"{next_year}届",
    ]
    for kw in explicit_campus_kw:
        if kw in combined:
            return True, f"窗口标识: {kw}"

    # 英文明确信号
    explicit_english_kw = [
        "graduate program", "management trainee", "analyst program",
        "campus recruiting", "early career", "rotational program",
        "fresh graduate", "entry level", "new graduate",
        f"class of {cur_year}", f"class of {next_year}",
    ]
    for kw in explicit_english_kw:
        if kw in combined_lower:
            return True, f"窗口标识: {kw}"

    # 明确只限更远届的,不算窗口(如现在 2026 年,只限 2028 届的不算)
    far_year = next_year + 1
    if re.search(rf"{far_year}届|class of {far_year}", combined_lower):
        return False, f"只限{far_year}届"

    return False, "社招岗位"


def is_management_trainee(jd_text: str, title: str = "") -> str:
    """
    判断是否为管培生项目,返回管培项目类别标签(空字符串表示非管培)。
    用于校招用户的管培项目跟踪。
    """
    combined = (title + " " + jd_text).lower()
    mt_signals = [
        ("管培生", "管培生"), ("管理培训生", "管培生"),
        ("management trainee", "管培生"), ("mt program", "管培生"),
        ("graduate program", "管培生"), ("analyst program", "管培生"),
        ("rotational program", "管培生"),
    ]
    for signal, label in mt_signals:
        if signal in combined:
            return label
    return ""


def score_job(job: Dict[str, str], profile: UserProfile,
              llm_client=None) -> Dict[str, Any]:
    """
    对单条岗位评分(通用版)。
    job 需含: title, company, jd_text, location, salary, jd_url
    profile: 用户画像(direction_keywords 驱动分类)
    llm_client: 可选,传入则用 LLM 深度分析 JD 正文生成摘要和建议
    """
    title = job.get("title", "")
    company = job.get("company", "")
    jd_text = job.get("jd_text", "")
    location = job.get("location", "")
    salary = job.get("salary", "")
    jd_url = job.get("jd_url", "")
    posted = job.get("posted", "")

    # 应届窗口 + 管培项目标记(提前计算,供经验评分使用)
    in_window, window_note = is_graduate_window(jd_text, title)
    mt_label = is_management_trainee(jd_text, title)

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

    # 3. 经验匹配 — 校招用户不看经验,统一给满分;社招用户保留经验匹配
    exp = parse_experience(jd_text)
    user_role = getattr(profile, "role", "") or ""
    if user_role == "campus":
        # 校招:不考虑经验要求,直接满分
        exp_score = 15
    else:
        # 社招:保留经验匹配逻辑
        user_exp = profile.experience_years
        if in_window:
            exp_score = 5  # 社招用户不适合校招窗口岗位
        elif "应届" in exp or "在校" in exp or "fresh" in exp.lower() or "entry" in exp.lower():
            exp_score = 5
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

    # 4. 技能匹配(优先用结构化 hard_skills 字段)
    job_hard_skills = job.get("hard_skills", "")
    skill_score, skill_hits = score_skills(jd_text, profile.core_skills, hard_skills=job_hard_skills)

    # 5. 学历匹配(优先用结构化 min_education 字段)
    edu = job.get("min_education") or parse_education(jd_text)
    user_degree = profile.degree
    if "博士" in edu:
        edu_score = 10 if user_degree == "博士" else (7 if user_degree == "硕士" else 3)
    elif "硕士" in edu:
        edu_score = 10 if user_degree in ["硕士", "博士"] else 5
    elif "本科" in edu:
        edu_score = 10
    else:
        edu_score = 8

    # 6. 专业匹配(用结构化 major_required 字段)
    job_major = (job.get("major_required") or "").lower()
    user_major = (profile.major or "").lower()
    if user_major and job_major:
        if user_major in job_major or any(m in user_major for m in job_major.split(',')):
            major_score = 10
        else:
            major_score = 0
    else:
        major_score = 5  # 专业信息不足,给中等分

    # 7. 行业匹配
    industry_score = score_industry(jd_text, profile.target_industries)

    # 8. 证书匹配加分
    job_certs = (job.get("certifications") or "").lower()
    user_certs = [c.lower() for c in (profile.target_certificates or [])]
    cert_score = 0
    if job_certs and user_certs:
        if any(c in job_certs for c in user_certs):
            cert_score = 5  # 用户持有岗位要求的证书,加分

    relevance = (dir_score + platform_score + exp_score + skill_score
                 + edu_score + major_score + industry_score + cert_score)

    # 难度评分 — 校招用户不按经验年限打分,只看学历+平台
    diff = 0
    if user_role != "campus" and re.search(r"3年|5年|10年|3 years|5 years", exp):
        diff += 25
    elif user_role != "campus" and re.search(r"1年|2年|1 year|2 years", exp):
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

    # JD 深度分析:优先用 LLM(基于 JD 正文),降级用正则
    jd_summary = job.get("jd_summary", "") or ""
    llm_summary = ""
    llm_advice = ""
    if llm_client and jd_text and len(jd_text.strip()) >= 50:
        try:
            from dataclasses import asdict
            profile_dict = asdict(profile) if hasattr(profile, "__dataclass_fields__") else {}
            analysis = llm_client.analyze_jd(jd_text, title, profile_dict)
            if analysis.get("jd_summary"):
                llm_summary = analysis["jd_summary"]
            if analysis.get("application_advice"):
                llm_advice = analysis["application_advice"]
        except Exception as e:
            logger.debug(f"LLM JD 分析失败,使用降级方案: {e}")

    # 简评:优先 LLM 深度分析,降级用正则匹配
    if llm_summary:
        summary = llm_summary
        if in_window:
            summary += f" (应届窗口:{window_note})"
    else:
        hit_desc = "、".join(skill_hits) if skill_hits else "无直接技能命中"
        if user_role == "campus":
            summary = (f"岗位类别:{direction},平台:{platform}。"
                       f"JD与用户匹配点: {hit_desc}。"
                       f"学历要求:{edu}。")
        else:
            summary = (f"岗位类别:{direction},平台:{platform}。"
                       f"JD与用户匹配点: {hit_desc}。"
                       f"经验要求:{exp}(用户{user_exp}年),学历要求:{edu}。")
        if in_window:
            summary += f" {window_note}。"

    # 申请建议:优先 LLM,降级用通用建议
    if llm_advice:
        advice = llm_advice
    else:
        advice_parts = []
        if skill_hits:
            advice_parts.append(f"突出以下匹配技能: {'、'.join(skill_hits[:3])}")
        if profile.school:
            advice_parts.append(f"强调{profile.school}{profile.degree}背景")
        if not advice_parts:
            advice_parts.append("结合自身背景挖掘与JD的交集")
        advice = "建议投递," + ";".join(advice_parts) + "。"

    # 截止日期(校招岗位常用,正则提取;失败则为空)
    deadline = extract_deadline_from_jd(jd_text)
    deadline_ts = _to_timestamp_ms(deadline) if deadline else None

    return {
        "岗位标题": title,
        "公司": company,
        "行业": job.get("industry", ""),
        "公司类型": job.get("company_type", ""),
        "难度": job.get("difficulty", ""),
        "部门": job.get("department", ""),
        "地点": location,
        "薪资范围": salary,
        "学历要求": edu,
        # JD摘要:优先 LLM 深度分析,降级用主库预生成的 jd_summary
        "JD摘要": (llm_summary or job.get("jd_summary", "") or "")[:300],
        # JD链接 是飞书 URL 字段(type=15),必须传 {"text","link"} 对象。
        # 空字符串会触发 1254068 URLFieldDetailFail,所以空值时省略该字段。
        "JD链接": _build_url_field(jd_url),
        # 抓取日期 是飞书日期字段(type=5),必须传 Unix 毫秒时间戳,不能传字符串。
        "抓取日期": _to_timestamp_ms(job.get("crawl_date", "")),
        "发布时间": posted,
        # 投递截止日期:校招截止提醒用;空值时省略(None 会被 _sanitize_fields 剔除)
        "投递截止日期": deadline_ts,
        "岗位类别": direction,
        "平台层级": platform,
        # 数字字段必须传 int,否则飞书返回 1254061 NumberFieldConvFail
        "相关性评分": int(relevance),
        "难度评分": int(min(diff, 100)),
        "综合推荐度": recommend,
        "简评": summary,
        "申请建议": advice,
        "申请状态": "未投递",
        # 投递日期:用户标记"已投递"时由更新逻辑写入,初始为空
        "投递日期": None,
        "去重hash": _make_hash(company, title, location, jd_url),
        "应届窗口": "是" if in_window else "否",
        "是否在招": "是",
        "管培项目": mt_label,
    }
