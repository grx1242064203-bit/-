
"""
岗位匹配评分器 — 分层加权 + 同义词归一化 + 匹配理由可解释。

重写背景:
原 scorer.py 使用硬编码 7 维度 + 纯字面字符串包含匹配,存在:
- 无同义词归一化(简历写"分布式缓存",岗位写"Redis" → 漏匹配)
- 无结构化关键词区分(硬技能/软技能/证书混在一起)
- 无权重差异化(Python 对后端岗 vs 数据岗同等对待)
- 无可解释输出(用户不知道为什么匹配/不匹配)

新引擎:
- 8 维度分层加权(skill/hard_skill/cert/education/major/city/role/soft_skill)
- 同义词归一化 + Jaccard overlap 匹配
- 结构化关键词支持(优先使用 UserProfile.structured_keywords,
  无则降级使用 core_skills + direction_keywords)
- 每个维度输出 match_reasons 列表

向后兼容:函数签名 score_job(job, profile, llm_client) 保持不变,
UserMatcher._score_and_rank() 中的调用代码无需修改。
"""
import logging
from typing import Dict, List, Tuple, Optional

from keyword_normalizer import keyword_set_overlap, normalize

logger = logging.getLogger(__name__)

DIMENSION_WEIGHTS = {
    "skill": 0.30,
    "hard_skill": 0.20,
    "cert": 0.10,
    "education": 0.15,
    "major": 0.05,
    "city": 0.10,
    "role": 0.05,
    "soft_skill": 0.05,
}

EDUCATION_LEVELS = {"大专": 1, "本科": 2, "硕士": 3, "博士": 4}


def _extract_job_keywords(job: Dict) -> Dict[str, List[str]]:
    """从岗位 dict 中按类别提取关键词集合"""
    return {
        "keywords": job.get("keywords", []) or [],
        "hard_skills": job.get("hard_skills", []) or [],
        "soft_skills": job.get("soft_skills", []) or [],
        "certifications": job.get("certifications", []) or [],
        "languages": job.get("languages", []) or [],
    }


def _extract_user_keywords(profile) -> Dict[str, List[str]]:
    """
    从 UserProfile 中按类别提取用户关键词集合。
    优先使用 structured_keywords(新版),降级使用 core_skills + direction_keywords(旧版)。
    """
    if getattr(profile, "structured_keywords", None):
        result: Dict[str, List[str]] = {
            "hard_skill": [], "soft_skill": [], "tool": [], "framework": [],
            "domain": [], "cert": [], "education": [], "city": [], "role": [],
            "project": [], "other": [], "skill_all": [],
        }
        for tag in profile.structured_keywords:
            kw = tag.get("standard") or tag.get("kw", "")
            category = tag.get("category", "other")
            if not kw:
                continue
            bucket = result.setdefault(category, [])
            bucket.append(kw)
            result["skill_all"].append(kw)
        return result

    old_kws = {
        "hard_skill": list(profile.core_skills or []),
        "skill_all": list(profile.core_skills or []),
        "role": [],
        "domain": [],
        "city": list(profile.target_cities or []),
        "cert": list(profile.target_certificates or []),
    }
    for role, kws in (profile.direction_keywords or {}).items():
        if role in ("role", "domain", "skill"):
            old_kws[role].extend(kws)
            old_kws["skill_all"].extend(kws)
    return old_kws


def _education_level(edu: str) -> int:
    if not edu:
        return 0
    for k, v in EDUCATION_LEVELS.items():
        if k in edu:
            return v
    return 0


def _match_education(profile, job: Dict) -> Tuple[float, List[str]]:
    """学历维度:候选人学历 >= 岗位最低学历 → 100,不达标 → 0,信息缺失 → 60"""
    reasons: List[str] = []
    user_edu = _education_level(profile.degree or "")
    job_min = _education_level(job.get("min_education", "") or job.get("education_req", ""))

    if not job_min:
        reasons.append("岗位无明确学历要求")
        return 60.0, reasons

    if not user_edu:
        reasons.append("候选人学历未明确")
        return 60.0, reasons

    if user_edu >= job_min:
        label = ["", "大专", "本科", "硕士", "博士"][user_edu]
        reasons.append(f"候选人{label}学历满足岗位最低要求")
        return 100.0, reasons

    reasons.append(f"候选人学历可能低于岗位要求(最低要求{list(EDUCATION_LEVELS.keys())[job_min - 1]})")
    return 0.0, reasons


def _match_city(profile, job: Dict) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    target = [c.lower() for c in (profile.target_cities or []) if c]
    job_city = (job.get("city", "") or job.get("location", "")).lower()

    if not target:
        reasons.append("候选人无城市偏好(不限)")
        return 100.0, reasons

    if not job_city:
        reasons.append("岗位地点未明确")
        return 50.0, reasons

    for tc in target:
        if tc in job_city or job_city in tc:
            reasons.append(f"岗位地点 {job_city} 在候选人目标城市 {tc} 内")
            return 100.0, reasons

    reasons.append(f"岗位地点 {job_city} 不在候选人目标城市")
    return 0.0, reasons


def _match_cert(profile, job: Dict, u: Dict) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    job_certs = job.get("certifications", []) or []
    job_certs_lower = [c.lower() for c in job_certs]

    if not job_certs:
        reasons.append("岗位无证书硬性要求")
        return 60.0, reasons

    user_certs = [c.lower() for c in (u.get("cert") or [])]
    hit = 0
    for jc in job_certs_lower:
        for uc in user_certs:
            if jc in uc or uc in jc:
                hit += 1
                break

    if hit >= len(job_certs):
        reasons.append(f"候选人持有岗位要求的全部证书: {', '.join(job_certs)}")
        return 100.0, reasons
    if hit > 0:
        reasons.append(f"候选人持有部分岗位要求的证书({hit}/{len(job_certs)})")
        return 60.0, reasons

    reasons.append(f"岗位要求证书但候选人未持有: {', '.join(job_certs)}")
    return 0.0, reasons


def _match_major(profile, job: Dict, u: Dict) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    job_major_cat = (job.get("major_category") or "").strip()
    job_major = (job.get("major_required") or "").strip()

    user_major = (profile.major or "").strip()
    user_edu_tags = u.get("education", [])

    if not job_major_cat or job_major_cat in ("不限", ""):
        reasons.append("岗位无专业大类限制")
        return 100.0, reasons

    edu_kw_lower = [t.lower() for t in user_edu_tags + [user_major]]
    if any(job_major_cat.lower() in kw or kw in job_major_cat.lower() for kw in edu_kw_lower):
        reasons.append(f"候选人专业属于{job_major_cat}大类")
        return 100.0, reasons

    if job_major and user_major and (job_major.lower() in user_major.lower() or user_major.lower() in job_major.lower()):
        reasons.append(f"候选人专业与岗位专业要求直接匹配({user_major})")
        return 100.0, reasons

    if "不限" in (job_major or "") or "相关" in (job_major or ""):
        reasons.append(f"岗位接受{job_major}专业")
        return 80.0, reasons

    reasons.append(f"岗位倾向{job_major_cat}大类/具体{job_major}专业")
    return 40.0, reasons


def _match_role(profile, job: Dict, u: Dict) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    job_title = (job.get("position_title") or "").lower()
    job_cat = (job.get("job_category") or "").lower()
    job_subcat = (job.get("job_subcategory") or "").lower()

    user_roles = [r.lower() for r in (u.get("role") or [])]
    if not user_roles:
        reasons.append("候选人未明确目标岗位方向")
        return 60.0, reasons

    job_roles_set = set(filter(None, [job_title, job_cat, job_subcat]))
    for ur in user_roles:
        for jr in job_roles_set:
            if ur and ur in jr or (jr and jr in ur):
                reasons.append(f"岗位方向{job_cat or job_subcat}与候选人目标{ur}匹配")
                return 100.0, reasons

    all_job_text = f"{job_title} {job_cat} {job_subcat}"
    _, _, hits = keyword_set_overlap(user_roles, [all_job_text])
    if hits:
        reasons.append(f"岗位方向与候选人目标有交集")
        return 80.0, reasons

    reasons.append(f"岗位方向{job_cat or job_title[:20]}与候选人目标方向不同")
    return 30.0, reasons


def _match_hard_skill(job: Dict, u: Dict) -> Tuple[float, List[str]]:
    """硬技能维度:岗位 hard_skills 的覆盖率"""
    reasons: List[str] = []
    job_hard = job.get("hard_skills", []) or []

    if not job_hard:
        reasons.append("岗位无明确硬技能要求")
        return 60.0, reasons

    user_hard = u.get("hard_skill") or []
    _, jaccard, hits = keyword_set_overlap(user_hard, job_hard)

    if len(job_hard) == 0:
        return 60.0, reasons

    coverage = len(hits) / len(job_hard)
    score = min(100.0, coverage * 100.0 + jaccard * 20.0)

    if hits:
        hit_kws = [f"{uk}↔{jk}" for uk, jk in hits[:5]]
        reasons.append(f"硬技能命中{len(hits)}/{len(job_hard)}: {', '.join(hit_kws)}")
    else:
        reasons.append(f"岗位要求硬技能 {', '.join(job_hard[:5])} 候选人均未命中")

    return score, reasons


def _match_soft_skill(job: Dict, u: Dict) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    job_soft = job.get("soft_skills", []) or []

    if not job_soft:
        return 60.0, ["岗位无明确软技能要求"]

    user_soft = u.get("soft_skill") or []
    _, _, hits = keyword_set_overlap(user_soft, job_soft)

    if hits:
        reasons.append(f"软技能命中{len(hits)}项")
        return min(100.0, len(hits) * 25.0)

    return 50.0, ["软技能无法从简历关键词中准确匹配"]


def _match_skill(job: Dict, u: Dict) -> Tuple[float, List[str]]:
    """综合技能维度:岗位 keywords + hard_skills 与用户全部关键词的 Jaccard overlap"""
    reasons: List[str] = []
    job_all = list(set(
        (job.get("keywords", []) or []) +
        (job.get("hard_skills", []) or [])
    ))

    if not job_all:
        return 60.0, ["岗位无可用关键词(拆岗质量不足)"]

    user_all = u.get("skill_all") or u.get("hard_skill") or []
    _, jaccard, hits = keyword_set_overlap(user_all, job_all)

    score = min(100.0, jaccard * 200.0)

    if hits:
        hit_kws = [f"{uk}↔{jk}" for uk, jk in hits[:6]]
        reasons.append(f"关键词命中{len(hits)}/{len(job_all)}: {', '.join(hit_kws)}")
    else:
        reasons.append(f"岗位关键词 {', '.join(job_all[:5])} 与候选人无交集")

    return score, reasons


def score_job(job: Dict, profile, llm_client=None) -> Dict:
    """
    为单个岗位打分。

    Args:
        job: 岗位 dict,字段与 llm_enricher.py 输出格式对齐
        profile: UserProfile dataclass 实例
        llm_client: 保留签名兼容性,新版评分器不使用 LLM

    Returns:
        {
            "相关性评分": float 0-100,
            "综合推荐度": "强烈推荐/推荐/可申请/不建议",
            "维度分": {dim: float},
            "匹配理由": List[str],
            "硬门槛通过": bool,
        }
    """
    u = _extract_user_keywords(profile)

    dim_scores: Dict[str, float] = {}
    all_reasons: List[str] = []

    for dim_name, (score, reasons) in [
        ("skill", _match_skill(job, u)),
        ("hard_skill", _match_hard_skill(job, u)),
        ("cert", _match_cert(profile, job, u)),
        ("education", _match_education(profile, job)),
        ("major", _match_major(profile, job, u)),
        ("city", _match_city(profile, job)),
        ("role", _match_role(profile, job, u)),
        ("soft_skill", _match_soft_skill(job, u)),
    ]:
        dim_scores[dim_name] = score
        all_reasons.extend([f"[{dim_name}] {r}" for r in reasons])

    total = sum(
        dim_scores.get(dim, 60.0) * weight
        for dim, weight in DIMENSION_WEIGHTS.items()
    )

    score = round(max(0.0, min(100.0, total)), 1)

    hard_gate = dim_scores.get("education", 100.0) > 0

    if score >= 75:
        recommend = "强烈推荐"
    elif score >= 55:
        recommend = "推荐"
    elif score >= 35:
        recommend = "可申请"
    else:
        recommend = "不建议"

    return {
        "相关性评分": score,
        "综合推荐度": recommend,
        "维度分": dim_scores,
        "匹配理由": all_reasons[:20],
        "硬门槛通过": hard_gate,
    }
