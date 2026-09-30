"""
竞争力评级模块 — 候选人竞争力 + 企业/岗位竞争力 + 对齐标签。

第一性原理:
- 候选人竞争力 = 这个候选人在求职市场上有多抢手(学校/学历/实习/竞赛/论文)
- 企业竞争力 = 这个岗位有多难进(公司牌子/岗位热度/学历门槛)
- 对齐 = 候选人档位 vs 岗位档位 → 冲刺/匹配/保底

设计约束(对抗性审查):
1. 软信号,不淘汰 — 只影响排序和标注,不做硬门槛
2. 学校占比≤40%,避免唯学历论误杀(211+强竞赛 应 > 985+无亮点)
3. 信号缺失有默认值 — 不因缺实习/论文就把人打太低
4. 企业侧先用 company_type+industry+job_category 规则粗分,LLM 精修留后续
"""
import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


def _tag_get(tag, key, default=""):
    """兼容 KeywordTag(属性访问)和 dict(键访问)两种结构化关键词类型。

    structured_keywords 在内存中是 KeywordTag 对象(无 .get 方法),
    从 JSON 反序列化后是 dict。统一用此函数取值,避免 AttributeError。
    """
    if isinstance(tag, dict):
        return tag.get(key, default)
    return getattr(tag, key, default)


# ============================================================
# 学校 tier 表
# ============================================================
C9_SCHOOLS = {
    "北京大学", "清华大学", "复旦大学", "上海交通大学", "浙江大学",
    "南京大学", "中国科学技术大学", "哈尔滨工业大学", "西安交通大学",
}

_985_SCHOOLS = C9_SCHOOLS | {
    "中国人民大学", "北京师范大学", "北京理工大学", "北京航空航天大学",
    "中央民族大学", "南开大学", "天津大学", "大连理工大学", "东北大学",
    "吉林大学", "同济大学", "华东师范大学", "东南大学", "厦门大学",
    "山东大学", "中国海洋大学", "武汉大学", "华中科技大学", "湖南大学",
    "中南大学", "中山大学", "华南理工大学", "四川大学", "电子科技大学",
    "重庆大学", "西北工业大学", "西北农林科技大学", "兰州大学", "国防科技大学",
}

# 211 非985 中的知名院校(代表性子集,其余 211 靠别名补)
_211_SCHOOLS = {
    "北京交通大学", "北京工业大学", "北京科技大学", "北京化工大学",
    "北京邮电大学", "北京林业大学", "北京中医药大学", "北京外国语大学",
    "中国传媒大学", "中央财经大学", "对外经济贸易大学", "北京体育大学",
    "中央音乐学院", "中国政法大学", "华北电力大学", "中国矿业大学",
    "中国石油大学", "中国地质大学", "天津医科大学", "河北工业大学",
    "太原理工大学", "内蒙古大学", "辽宁大学", "大连海事大学",
    "东北师范大学", "延边大学", "东北农业大学", "东北林业大学",
    "华东理工大学", "东华大学", "上海外国语大学", "上海财经大学",
    "上海大学", "苏州大学", "南京航空航天大学", "南京理工大学",
    "中国矿业大学", "河海大学", "江南大学", "南京农业大学",
    "南京师范大学", "安徽大学", "合肥工业大学", "福州大学",
    "南昌大学", "郑州大学", "武汉理工大学", "华中农业大学",
    "华中师范大学", "中南财经政法大学", "湖南师范大学", "暨南大学",
    "华南师范大学", "广西大学", "海南大学", "西南交通大学",
    "西南大学", "西南财经大学", "贵州大学", "云南大学",
    "西藏大学", "西北大学", "西安电子科技大学", "长安大学",
    "陕西师范大学", "青海大学", "宁夏大学", "新疆大学",
    "石河子大学", "中国矿业大学(北京)", "中国石油大学(北京)",
    "中国地质大学(北京)", "哈尔滨工程大学", "南京邮电大学",
    "杭州电子科技大学", "南京信息工程大学", "首都经济贸易大学",
}

# 海外名校(QS/USNews Top 约前60,代表性子集)
OVERSEAS_TOP = {
    "麻省理工学院", "MIT", "斯坦福大学", "Stanford", "哈佛大学", "Harvard",
    "加州大学伯克利分校", "UC Berkeley", "加州理工学院", "Caltech",
    "牛津大学", "Oxford", "剑桥大学", "Cambridge", "普林斯顿大学",
    "Princeton", "哥伦比亚大学", "Columbia", "芝加哥大学", "Chicago",
    "耶鲁大学", "Yale", "康奈尔大学", "Cornell", "宾夕法尼亚大学",
    "UPenn", "杜克大学", "Duke", "密歇根大学", "Michigan",
    "卡内基梅隆大学", "CMU", "卡耐基梅隆大学", "约翰霍普金斯大学",
    "JHU", "西北大学", "Northwestern", "华盛顿大学", "UW",
    "加州大学洛杉矶分校", "UCLA", "加州大学圣地亚哥分校", "UCSD",
    "帝国理工学院", "Imperial", "伦敦大学学院", "UCL", "爱丁堡大学",
    "多伦多大学", "University of Toronto", "麦吉尔大学", "McGill",
    "墨尔本大学", "墨尔本", "悉尼大学", "悉尼", "新南威尔士大学",
    "UNSW", "新加坡国立大学", "NUS", "南洋理工大学", "NTU",
    "香港大学", "港大", "香港科技大学", "港科大", "香港中文大学",
    "港中文", "苏黎世联邦理工", "ETH", "洛桑联邦理工", "EPFL",
    "慕尼黑工业大学", "TUM", "代尔夫特理工", "TU Delft",
}

SCHOOL_TIER_SCORE = {
    "c9": 40,
    "overseas_top": 38,
    "985": 32,
    "211": 24,
    "double_first_class": 20,
    "bendike": 10,  # 普通本科
    "zhuanke": 5,
    "unknown": 10,  # 未知默认按普通本科
}

DEGREE_SCORE = {"博士": 15, "硕士": 10, "本科": 5, "大专": 0, "专科": 0}

# 大厂关键词(用于实习加分)
BIG_COMPANY_KEYWORDS = [
    "字节跳动", "字节", "腾讯", "阿里", "阿里巴巴", "美团", "京东",
    "百度", "华为", "小米", "网易", "快手", "滴滴", "拼多多",
    "大疆", "DJI", "蚂蚁", "蚂蚁集团", "微软", "Microsoft", "谷歌",
    "Google", "亚马逊", "Amazon", "苹果", "Apple", "Meta",
    "高盛", "Goldman", "摩根", "Morgan", "中信", "中金",
    "宁德时代", "比亚迪", "隆基", "中芯国际", "联发科",
]

COMPETITION_KEYWORDS = {
    "国际级": ["ICPC", "国际大学生程序设计", "ACM-ICPC", "数学建模美赛", "MCM", "ICM",
                "国际数学奥林匹克", "IMO", "国际物理奥林匹克", "IPhO"],
    "国家级": ["ACM", "全国大学生数学建模", "国赛", "蓝桥杯", "挑战杯",
               "全国大学生电子设计", "中国大学生计算机设计", "RoboMaster",
               "数学建模国赛", "互联网+"],
    "省级": ["省赛", "省级", "江苏省赛", "浙江省赛", "广东省赛", "上海市赛",
              "山东省赛", "北京市赛", "四川省赛", "湖北省赛"],
}

PAPER_KEYWORDS = {
    "top_conf": ["CVPR", "ICCV", "NeurIPS", "ICML", "ACL", "EMNLP", "AAAI",
                 "IJCAI", "KDD", "SIGIR", "WWW", "ICLR", "FOCS", "STOC",
                 "ISCA", "MICRO", "HPCA", "ASPLOS"],
    "sci": ["SCI", "IEEE", "Science", "Nature", "Cell"],
}


def _school_tier(school: str) -> str:
    """判断学校 tier。"""
    if not school:
        return "unknown"
    s = school.strip()
    # 精确匹配优先
    if s in C9_SCHOOLS:
        return "c9"
    if s in OVERSEAS_TOP:
        return "overseas_top"
    if s in _985_SCHOOLS:
        return "985"
    if s in _211_SCHOOLS:
        return "211"
    # 包含匹配(处理"XX大学"简写或带校区)
    for name in C9_SCHOOLS:
        if name in s:
            return "c9"
    for name in OVERSEAS_TOP:
        if name in s or s in name:
            return "overseas_top"
    for name in _985_SCHOOLS:
        if name in s:
            return "985"
    for name in _211_SCHOOLS:
        if name in s:
            return "211"
    if any(k in s for k in ("大学", "学院")):
        return "bendike"
    return "unknown"


def _detect_big_internship(keywords: List[Dict]) -> bool:
    """从关键词中检测是否有大厂实习。"""
    for tag in keywords:
        std = (_tag_get(tag, "standard") or _tag_get(tag, "kw") or "")
        for kw in BIG_COMPANY_KEYWORDS:
            if kw in std:
                return True
    return False


def _detect_competition(keywords: List[Dict]) -> str:
    """检测竞赛级别: 国际级/国家级/省级/无。"""
    text = " ".join((_tag_get(t, "standard") or _tag_get(t, "kw") or "") for t in keywords)
    for level, kws in COMPETITION_KEYWORDS.items():
        for kw in kws:
            if kw in text:
                return level
    return "none"


def _detect_paper(keywords: List[Dict]) -> str:
    """检测论文级别: top_conf/sci/无。"""
    text = " ".join((_tag_get(t, "standard") or _tag_get(t, "kw") or "") for t in keywords)
    for level, kws in PAPER_KEYWORDS.items():
        for kw in kws:
            if kw in text:
                return level
    return "none"


def candidate_competitiveness(profile) -> Tuple[float, Dict[str, float], Dict]:
    """计算候选人竞争力得分(0-100)。

    Returns: (score, breakdown_dict, detail_dict)
    breakdown: {school, degree, internship, competition, paper}
    """
    keywords = getattr(profile, "structured_keywords", []) or []
    degree = getattr(profile, "degree", "") or ""
    schools = [_tag_get(t, "standard") or _tag_get(t, "kw", "") for t in keywords
               if _tag_get(t, "category") == "education"
               and not any(lv in (_tag_get(t, "standard") or "") for lv in ("学士", "硕士", "博士", "大专", "本科"))]

    # 1. 学校(取最高 tier)
    best_tier = "unknown"
    best_score = -1
    for sch in schools:
        tier = _school_tier(sch)
        if SCHOOL_TIER_SCORE[tier] > best_score:
            best_tier = tier
            best_score = SCHOOL_TIER_SCORE[tier]
    if best_score < 0:
        best_score = SCHOOL_TIER_SCORE["unknown"]
    school_score = best_score

    # 2. 学历
    degree_score = DEGREE_SCORE.get(degree, 0)

    # 3. 实习(大厂 +20, 有实习+8, 无+0)
    has_internship = any(
        _tag_get(t, "resume_section") in ("experience", "project")
        and _tag_get(t, "category") in ("hard_skill", "tool", "framework", "skill", "domain")
        for t in keywords
    )
    if _detect_big_internship(keywords):
        internship_score = 20
    elif has_internship:
        internship_score = 8
    else:
        internship_score = 0

    # 4. 竞赛
    comp_level = _detect_competition(keywords)
    comp_score = {"国际级": 15, "国家级": 10, "省级": 6, "none": 0}.get(comp_level, 0)

    # 5. 论文
    paper_level = _detect_paper(keywords)
    paper_score = {"top_conf": 10, "sci": 7, "none": 0}.get(paper_level, 0)

    total = school_score + degree_score + internship_score + comp_score + paper_score
    total = max(0.0, min(100.0, total))

    breakdown = {
        "school": school_score,
        "degree": degree_score,
        "internship": internship_score,
        "competition": comp_score,
        "paper": paper_score,
    }
    detail = {
        "school_tier": best_tier,
        "degree": degree,
        "internship_level": "大厂" if internship_score == 20 else ("有" if internship_score > 0 else "无"),
        "competition_level": comp_level,
        "paper_level": paper_level,
    }
    return round(total, 1), breakdown, detail


# ============================================================
# 企业/岗位竞争力
# ============================================================
# 公司地位分(0-60):由 enricher 阶段 LLM 分析公司行业地位后输出 company_tier 字段(顶/中/保底)。
# 不用公司性质(外企/国营/民营)推断 — 同性质内公司地位差异巨大(字节 vs 小厂都是民企),
# 必须靠 LLM 对真实行业地位做判断。无 company_tier 时此项为 0,不参与对齐。
COMPANY_TIER_SCORE = {
    "顶": 60,
    "中": 40,
    "保底": 25,
}

# 岗位热度分(0-25):岗位方向本身的竞争激烈程度(岗位属性,与公司性质无关)
JOB_HEAT_BY_CATEGORY = {
    "算法": 25,
    "AI工程": 24,
    "机器人与智能体": 23,
    "芯片半导体": 22,
    "数据": 16,
    "开发": 15,
    "产品": 12,
    "金融": 14,
    "设计与内容": 8,
    "硬件电子": 10,
    "管培生": 10,
    "运营与供应链": 6,
    "职能": 5,
    "制造与质量": 5,
    "商业": 7,
}

EDUCATION_BARRIER_SCORE = {"博士": 15, "硕士": 10, "本科": 5, "大专": 2, "不限": 0}


def company_competitiveness(job: Dict) -> Tuple[float, Dict[str, float], Dict]:
    """计算企业/岗位竞争力得分(0-100)。

    组成:
    1. 公司地位分(0-60):读 job['company_tier'](LLM 输出,顶/中/保底),无则 0
    2. 岗位热度分(0-25):岗位方向的竞争激烈程度
    3. 学历门槛分(0-15):岗位要求的学历

    不使用 company_type(外企/国营/民营) — 同性质公司地位差异巨大,
    必须靠 LLM 判断真实行业地位。
    """
    # 1. 公司地位(LLM 输出顶/中/保底;未评级时默认"中"作为中性基线,后续 LLM 覆盖)
    company_tier = (job.get("company_tier") or "").strip()
    if not company_tier:
        company_tier = "中"
    company_pos_score = COMPANY_TIER_SCORE.get(company_tier, COMPANY_TIER_SCORE["中"])

    # 2. 岗位热度
    import job_tree
    entry = job_tree.resolve_job(job)
    cat_name = entry.get("category_name") if entry else (job.get("job_category") or "")
    heat_score = JOB_HEAT_BY_CATEGORY.get(cat_name, 10)

    # 3. 学历门槛
    min_edu = (job.get("min_education") or "").strip()
    edu_barrier = EDUCATION_BARRIER_SCORE.get(min_edu, 0)

    total = company_pos_score + heat_score + edu_barrier
    total = max(0.0, min(100.0, total))

    breakdown = {
        "company_position": round(company_pos_score, 1),
        "job_heat": heat_score,
        "education_barrier": edu_barrier,
    }
    detail = {
        "company_tier": company_tier if job.get("company_tier") else "(未评级,默认中)",
        "job_category": cat_name,
        "min_education": min_edu or "不限",
    }
    return round(total, 1), breakdown, detail


# ============================================================
# 对齐标签
# ============================================================
def alignment(candidate_score: float, company_score: float) -> Tuple[str, float]:
    """候选人分 vs 企业分 → (标签, 对齐分0-100)。

    diff = company_score - candidate_score
    - diff > 60: 严重错配(企业远高于候选人,完全够不着)
    - 25 < diff <= 60: 冲刺(企业高于候选人,有挑战但够得着)
    - -10 <= diff <= 25: 匹配(档位接近,最优投递)
    - diff < -10: 保底(候选人高于企业,overqualified)

    对齐分:匹配=100(满分)、冲刺=85(高,有上升空间)、保底=60(可投但非最优)、
    严重错配=30(不建议)。让匹配/冲刺自然排到前面。
    """
    diff = company_score - candidate_score

    if diff > 60:
        return "严重错配", 30.0
    elif diff > 25:
        return "冲刺", 85.0
    elif diff < -10:
        return "保底", 60.0
    else:
        return "匹配", 100.0
