
"""
岗位匹配评分器 v2 — 分层加权 + 同义词归一化 + 匹配理由可解释。

修复 v1 bug:
- hard_skill bucket 只收 category=hard_skill,遗漏 tool/framework/skill
- skill_all 被 education/city/cert 污染,Jaccard 分母膨胀
- role 维度用 standard form 匹配中文原始词,永远 30 分
- 所有维度统一对岗位侧关键词做 normalize,避免 standard vs raw 不匹配
"""
import logging
from typing import Dict, List, Tuple, Optional

from keyword_normalizer import keyword_set_overlap, normalize as _norm

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

_SKILL_CATEGORIES = {"hard_skill", "skill", "tool", "framework"}


def _norm_list(kws: List[str]) -> List[str]:
    """批量归一化关键词,未命中词典的保留原始值。"""
    out = []
    for k in kws or []:
        std, hit = _norm(k)
        out.append(std)
    return out


def _extract_job_keywords(job: Dict) -> Dict[str, List[str]]:
    return {
        "keywords": _norm_list(job.get("keywords", []) or []),
        "hard_skills": _norm_list(job.get("hard_skills", []) or []),
        "soft_skills": _norm_list(job.get("soft_skills", []) or []),
        "certifications": _norm_list(job.get("certifications", []) or []),
        "languages": _norm_list(job.get("languages", []) or []),
        "job_category": _norm_list([job.get("job_category", "")] if job.get("job_category") else []),
        "job_subcategory": _norm_list([job.get("job_subcategory", "")] if job.get("job_subcategory") else []),
        "position_title_norm": _norm_list([job.get("position_title", "")] if job.get("position_title") else []),
    }


def _extract_user_keywords(profile) -> Dict[str, List[str]]:
    """
    从 UserProfile 提取结构化关键词,优先 structured_keywords,降级 core_skills。

    BUCKET 设计关键约束:
    - hard_skill 包含所有技能/工具/框架/领域类 category(LLM 解析可能标成不同类别)
    - soft_skill 只收 category=soft_skill
    - cert/education/city/role 各归其位
    - skill_all 只含技能类,排除 education/city/cert/role 等非技能词
    """
    if getattr(profile, "structured_keywords", None):
        hard_skill: List[str] = []
        soft_skill: List[str] = []
        cert: List[str] = []
        education: List[str] = []
        city: List[str] = []
        role: List[str] = []
        skill_all: List[str] = []
        domain: List[str] = []

        seen = set()
        for tag in profile.structured_keywords:
            kw = (tag.get("standard") or tag.get("kw") or "").strip()
            category = tag.get("category", "other")
            if not kw or kw in seen:
                continue
            seen.add(kw)

            if category in _SKILL_CATEGORIES:
                hard_skill.append(kw)
                skill_all.append(kw)
            elif category == "domain":
                domain.append(kw)
            elif category == "soft_skill":
                soft_skill.append(kw)
            elif category == "cert":
                cert.append(kw)
            elif category == "education":
                education.append(kw)
            elif category == "city":
                city.append(kw)
            elif category == "role":
                role.append(kw)

        return {
            "hard_skill": hard_skill, "soft_skill": soft_skill,
            "cert": cert, "education": education, "city": city,
            "role": role, "skill_all": skill_all, "domain": domain,
        }

    old_hard = list(profile.core_skills or [])
    old_roles: List[str] = []
    old_certs = list(profile.target_certificates or [])
    old_cities = list(profile.target_cities or [])
    for role, kws in (profile.direction_keywords or {}).items():
        if role in ("role",):
            old_roles.extend(kws)
        if role in ("skill", "domain"):
            old_hard.extend(kws)

    return {
        "hard_skill": _norm_list(old_hard),
        "soft_skill": [],
        "cert": _norm_list(old_certs),
        "education": [],
        "city": _norm_list(old_cities),
        "role": _norm_list(old_roles),
        "skill_all": _norm_list(old_hard),
        "domain": [],
    }


def _education_level(edu: str) -> int:
    if not edu:
        return 0
    for k, v in EDUCATION_LEVELS.items():
        if k in edu:
            return v
    return 0


def _match_education(profile, job: Dict) -> Tuple[float, List[str]]:
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

    reasons.append(
        f"候选人学历低于岗位要求(最低要求{list(EDUCATION_LEVELS.keys())[job_min - 1]})"
    )
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
    jk = _extract_job_keywords(job)
    job_certs = jk["certifications"]

    if not job_certs:
        reasons.append("岗位无证书硬性要求")
        return 60.0, reasons

    user_certs = u.get("cert") or []
    _, _, hits = keyword_set_overlap(user_certs, job_certs)

    if len(hits) >= len(job_certs):
        hit_names = [f"{uk}↔{jk2}" for uk, jk2 in hits]
        reasons.append(f"候选人持有岗位要求的全部证书: {', '.join(hit_names)}")
        return 100.0, reasons
    if hits:
        reasons.append(f"候选人持有部分岗位证书({len(hits)}/{len(job_certs)})")
        return 60.0, reasons

    reasons.append(f"岗位要求证书 {', '.join(job.get('certifications', []))} 候选人均未持有")
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

    if job_major and user_major and (
        job_major.lower() in user_major.lower()
        or user_major.lower() in job_major.lower()
    ):
        reasons.append(f"候选人专业与岗位直接匹配({user_major})")
        return 100.0, reasons

    if "不限" in (job_major or "") or "相关" in (job_major or ""):
        reasons.append(f"岗位接受{job_major}专业")
        return 80.0, reasons

    reasons.append(f"岗位倾向{job_major_cat}大类/具体{job_major}专业")
    return 40.0, reasons


def _match_role(profile, job: Dict, u: Dict) -> Tuple[float, List[str]]:
    """角色匹配:两边都 normalize 后用 keyword_set_overlap,解决 standard vs raw 不匹配问题。"""
    reasons: List[str] = []
    jk = _extract_job_keywords(job)
    job_roles = list(set(
        jk["job_category"] + jk["job_subcategory"] + jk["position_title_norm"]
    ))

    user_roles = u.get("role") or []
    if not user_roles:
        reasons.append("候选人未明确目标岗位方向")
        return 60.0, reasons

    _, _, hits = keyword_set_overlap(user_roles, job_roles)

    if len(hits) >= 2 or (hits and jk["job_category"] and _norm(job.get("job_category", ""))[0] in user_roles):
        hit_names = [f"{uk}↔{jk2}" for uk, jk2 in hits]
        reasons.append(f"岗位方向与候选人目标强匹配: {', '.join(hit_names)}")
        return 100.0, reasons
    if hits:
        hit_names = [f"{uk}↔{jk2}" for uk, jk2 in hits[:2]]
        reasons.append(f"岗位方向与候选人目标有交集: {', '.join(hit_names)}")
        return 80.0, reasons

    reasons.append(f"岗位方向与候选人目标方向差异较大")
    return 30.0, reasons


def _match_hard_skill(job: Dict, u: Dict) -> Tuple[float, List[str]]:
    jk = _extract_job_keywords(job)
    job_hard = jk["hard_skills"]
    reasons: List[str] = []

    if not job_hard:
        return 0.0, ["岗位无明确硬技能要求(拆岗质量不足)"]

    user_hard = u.get("hard_skill") or []
    _, jaccard, hits = keyword_set_overlap(user_hard, job_hard)

    coverage = len(hits) / len(job_hard) if job_hard else 0
    score = min(100.0, coverage * 100.0 + jaccard * 15.0)

    if hits:
        hit_kws = [f"{uk}↔{jk2}" for uk, jk2 in hits[:5]]
        reasons.append(f"硬技能命中{len(hits)}/{len(job_hard)}: {', '.join(hit_kws)}")
    else:
        reasons.append(
            f"岗位要求硬技能 {', '.join(job.get('hard_skills', [])[:5])} 候选人均未命中"
        )

    return score, reasons


def _match_soft_skill(job: Dict, u: Dict) -> Tuple[float, List[str]]:
    jk = _extract_job_keywords(job)
    job_soft = jk["soft_skills"]
    reasons: List[str] = []

    if not job_soft:
        return 60.0, ["岗位无明确软技能要求"]

    user_soft = u.get("soft_skill") or []
    _, _, hits = keyword_set_overlap(user_soft, job_soft)

    if hits:
        reasons.append(f"软技能命中{len(hits)}项")
        return min(100.0, len(hits) * 25.0)

    return 50.0, ["软技能无法从简历关键词中准确匹配"]


def _match_skill(job: Dict, u: Dict) -> Tuple[float, List[str]]:
    """综合技能:岗位 keywords + hard_skills 的并集与用户 skill_all 做 Jaccard overlap。

    空岗位关键词直接给 0 分(而非默认 60),避免降级岗位靠无技能要求混上排行榜。
    """
    jk = _extract_job_keywords(job)
    job_all = list(set(jk["keywords"] + jk["hard_skills"]))
    reasons: List[str] = []

    if not job_all:
        return 0.0, ["岗位无可用关键词(拆岗质量不足)"]

    user_all = u.get("skill_all") or []
    _, jaccard, hits = keyword_set_overlap(user_all, job_all)

    score = min(100.0, jaccard * 200.0)

    if hits:
        hit_kws = [f"{uk}↔{jk2}" for uk, jk2 in hits[:6]]
        reasons.append(f"关键词命中{len(hits)}/{len(job_all)}: {', '.join(hit_kws)}")
    else:
        reasons.append(
            f"岗位关键词 {', '.join(job.get('keywords', [])[:5])} 与候选人无交集"
        )

    return score, reasons


def score_job(job: Dict, profile, llm_client=None) -> Dict:
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
