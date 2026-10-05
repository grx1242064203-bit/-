
"""
岗位匹配评分器 v2 — 分层加权 + 同义词归一化 + 匹配理由可解释。

修复 v1 bug:
- hard_skill bucket 只收 category=hard_skill,遗漏 tool/framework/skill
- skill_all 被 education/city/cert 污染,Jaccard 分母膨胀
- role 维度用 standard form 匹配中文原始词,永远 30 分
- 所有维度统一对岗位侧关键词做 normalize,避免 standard vs raw 不匹配
"""
import json
import logging
from typing import Dict, List, Tuple, Optional, Any, Set

from keyword_normalizer import keyword_set_overlap, normalize as _norm
import job_tree
from competitiveness import candidate_competitiveness, company_competitiveness, alignment

logger = logging.getLogger(__name__)

# 权重重新分配(第一性原理:方向对齐 > 技能命中 > 竞争力对齐 > 公司意向 > 硬门槛)
# - role 0.15:求职方向核心偏好
# - hard_skill 0.15:真实硬技能命中
# - skill 0.10:综合技能覆盖
# - education 0.15 / major 0.10:硬门槛
# - competitiveness 0.10:候选人档位 vs 岗位档位对齐
# - company_preference 0.10:用户目标公司及同行业/同类型/同地位公司优先
# - cert 0.05 / city 0.05 / soft_skill 0.05:辅助
DIMENSION_WEIGHTS = {
    "skill": 0.10,
    "hard_skill": 0.15,
    "cert": 0.05,
    "education": 0.15,
    "major": 0.10,
    "city": 0.05,
    "role": 0.15,
    "soft_skill": 0.05,
    "competitiveness": 0.10,
    "company_preference": 0.10,
}

# 方向硬门槛:role 维度 < ROLE_GATE_THRESHOLD 时,总分上限 = ROLE_GATE_CAP
# 解决"方向错配但靠技能假命中/泛技能刷分"挤进 Top 的问题
#
# 阈值校准:同大类匹配系数 0.6,role_score = weight × 0.6 × 100。
# - 阈值 40 → 需 weight ≥ 0.67 才不触发,会误杀大量同大类弱匹配(weight 0.5-0.6)
# - 阈值 30 → 需 weight ≥ 0.5 才不触发,同大类次要方向(0.5-0.6)不再被误封,
#   跨大类(0分)仍被正确封顶。
ROLE_GATE_THRESHOLD = 30.0
ROLE_GATE_CAP = 45.0


def _parse_list_field(v: Any) -> List[str]:
    """统一反序列化岗位侧 JSON 字符串字段。

    job_db 返回的 keywords/hard_skills/certifications 等字段是 JSON 字符串
    (如 '["Python","Java"]'),scorer 必须先反序列化为 list 才能遍历,
    否则会逐字符拆分('['、'"'、'P'...)导致 match_score 子串假命中。
    """
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return []
        # 尝试 JSON 反序列化
        try:
            obj = json.loads(s)
            if isinstance(obj, list):
                return [str(x).strip() for x in obj if str(x).strip()]
        except json.JSONDecodeError:
            pass
        # 兜底:逗号分隔(非 JSON 格式的边缘情况)
        return [x.strip() for x in s.split(",") if x.strip()]
    return []

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
    """提取岗位侧关键词,统一用 _parse_list_field 反序列化 JSON 字符串字段。

    P0 修复:job_db 返回的 keywords/hard_skills 等是 JSON 字符串,
    必须先 json.loads 成 list 再 normalize,否则逐字符遍历导致子串假命中。
    """
    return {
        "keywords": _norm_list(_parse_list_field(job.get("keywords"))),
        "hard_skills": _norm_list(_parse_list_field(job.get("hard_skills"))),
        "soft_skills": _norm_list(_parse_list_field(job.get("soft_skills"))),
        "certifications": _norm_list(_parse_list_field(job.get("certifications"))),
        "languages": _norm_list(_parse_list_field(job.get("languages"))),
        "job_category": _norm_list([job.get("job_category", "")] if job.get("job_category") else []),
        "job_subcategory": _norm_list([job.get("job_subcategory", "")] if job.get("job_subcategory") else []),
        "position_title_norm": _norm_list([job.get("position_title", "")] if job.get("position_title") else []),
    }


def _tag_get(tag, key, default=""):
    """兼容 KeywordTag(属性访问)和 dict(键访问)两种结构化关键词类型。"""
    if isinstance(tag, dict):
        return tag.get(key, default)
    return getattr(tag, key, default)


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
            kw = (_tag_get(tag, "standard") or _tag_get(tag, "kw") or "").strip()
            category = _tag_get(tag, "category", "other")
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
    """城市匹配:无偏好时给中性分 50(而非 100),避免该维度对所有岗位无区分度。"""
    reasons: List[str] = []
    target = [c.lower() for c in (profile.target_cities or []) if c]
    job_city = (job.get("city", "") or job.get("location", "")).lower()

    if not target:
        reasons.append("候选人无城市偏好(中性)")
        return 50.0, reasons

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

    reasons.append(f"岗位要求证书 {', '.join(job_certs)} 候选人均未持有")
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
    """角色方向匹配 v2:基于候选人适配方向(fit_directions) × 岗位树归属。

    第一性原理:方向对齐靠"候选人适配的岗位子类"与"岗位实际归属"的层级匹配,
    而不是泛化的关键词交集(后者导致 IC验证 因单"证"字假命中)。

    规则:
    - 岗位子类命中候选人适配子类 → 系数 1.0
    - 同大类(岗位是大类或同大类其他子类) → 系数 0.6
    - 跨大类 → 0
    得分 = max(权重 × 系数) × 100,归到 0-100。

    降级链:
    1. 有 fit_directions 且岗位能解析归属 → 新逻辑
    2. 无 fit_directions 但有旧 role 关键词 → 旧关键词交集逻辑
    3. 啥都没有 → 中性 50

    防御性:fit_direction 缺 cat_key/sub_key 时(前端手动添加方向或旧数据),
    用 direction 名反查 job_tree.resolve 恢复归属,避免 role 恒为 0 触发方向门槛。
    """
    reasons: List[str] = []

    # 1. 解析岗位树归属
    job_entry = job_tree.resolve_job(job)

    # 2. 取候选人适配方向
    fit_dirs = getattr(profile, "fit_directions", None) or []

    if fit_dirs and job_entry:
        best_factor = 0.0
        best_fit = None
        for fd in fit_dirs:
            # 防御性:cat_key/sub_key 缺失时用 direction 名反查树恢复归属
            cat_key = fd.get("cat_key")
            sub_key = fd.get("sub_key")
            direction = (fd.get("direction") or "").strip()
            if (cat_key is None or sub_key is None) and direction:
                resolved = job_tree.resolve(direction, allow_category=True)
                if resolved:
                    cat_key = resolved.get("cat_key")
                    sub_key = resolved.get("sub_key")
                    # 回填到 fd(避免后续岗位重复解析)
                    try:
                        fd["cat_key"] = cat_key
                        fd["sub_key"] = sub_key
                        if "category_name" not in fd or not fd.get("category_name"):
                            fd["category_name"] = resolved.get("category_name", "")
                    except (TypeError, KeyError):
                        pass  # fd 可能不是可变 dict

            fit_entry = {
                "type": "subcategory" if sub_key else "category",
                "cat_key": cat_key,
                "sub_key": sub_key,
            }
            factor = job_tree.score_fit(fit_entry, job_entry)
            w = float(fd.get("weight") or 0.0)
            contribution = w * factor
            if contribution > best_factor:
                best_factor = contribution
                best_fit = fd
        score = round(best_factor * 100.0, 1)
        if best_fit:
            factor_label = {1.0: "精确子类命中", 0.6: "同大类匹配", 0.0: "跨大类"}.get(
                job_tree.score_fit(
                    {"type": "subcategory", "cat_key": best_fit.get("cat_key"),
                     "sub_key": best_fit.get("sub_key")}, job_entry
                ), "跨大类"
            )
            reasons.append(
                f"[role] 方向 {factor_label}:岗位「{job_entry.get('sub_name') or job_entry.get('category_name')}」"
                f"↔ 候选人适配「{best_fit.get('direction')}」(权重{best_fit.get('weight')})"
                f" — {best_fit.get('evidence', '')}"
            )
        else:
            reasons.append("[role] 候选人适配方向与岗位跨大类")
        return score, reasons

    # 3. 降级:无 fit_directions,用旧 role 关键词
    user_roles = u.get("role") or []
    if user_roles:
        jk = _extract_job_keywords(job)
        job_roles = list(set(jk["job_category"] + jk["job_subcategory"] + jk["position_title_norm"]))
        _, _, hits = keyword_set_overlap(user_roles, job_roles)
        if hits:
            return 70.0, [f"[role] (降级匹配)方向有交集: {', '.join(f'{a}↔{b}' for a, b in hits[:2])}"]
        return 30.0, ["[role] (降级匹配)方向差异较大"]

    reasons.append("[role] 候选人未明确目标岗位方向")
    return 50.0, reasons


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
            f"岗位要求硬技能 {', '.join(job_hard[:5])} 候选人均未命中"
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


def _match_competitiveness(profile, job: Dict) -> Tuple[float, List[str], Dict]:
    """竞争力对齐:候选人档位 vs 企业/岗位档位 → 冲刺/匹配/保底。

    软信号,不淘汰。对齐分 = 100 - |diff|×1.5,diff=企业分-候选人分。
    返回 (score, reasons, info) info 含候选人分/企业分/标签。
    """
    reasons: List[str] = []
    cand_score, cand_brk, cand_det = candidate_competitiveness(profile)
    comp_score, comp_brk, comp_det = company_competitiveness(job)
    label, align_score = alignment(cand_score, comp_score)

    diff = comp_score - cand_score
    reasons.append(
        f"竞争力对齐「{label}」:候选人{cand_score:.0f}分(学校{cand_det['school_tier']}/"
        f"{cand_det['degree']}/实习{cand_det['internship_level']}/竞赛{cand_det['competition_level']}) "
        f"↔ 岗位{comp_score:.0f}分(公司地位{comp_det['company_tier']}/"
        f"{comp_det['job_category']}/门槛{comp_det['min_education']}) 差值{diff:+.0f}"
    )
    info = {
        "candidate_score": cand_score,
        "company_score": comp_score,
        "label": label,
        "candidate_breakdown": cand_brk,
        "company_breakdown": comp_brk,
    }
    return align_score, reasons, info


def _resolve_target_company_features(target_companies: List[str]) -> Tuple[Set[str], Set[Tuple[str, str, str]]]:
    """把用户目标公司名解析成 (公司名集合, (行业,类型,地位)特征集合)。

    公司名做子串模糊匹配(用户写"腾讯",库中"腾讯科技(深圳)有限公司"可命中)。
    行业/类型来自 companies 表,地位(company_tier)取该公司在招岗位中最常见的 tier。
    查不到的公司只保留名字,用于直接命中判断。
    """
    import job_db
    names: Set[str] = set()
    features: Set[Tuple[str, str, str]] = set()

    all_companies = job_db.get_all_companies() if hasattr(job_db, "get_all_companies") else []
    name_row_map = {}
    for c in all_companies:
        cname = (c.get("name") or "").strip()
        if cname:
            name_row_map[cname] = c

    for raw in target_companies:
        name = (raw or "").strip()
        if not name:
            continue
        names.add(name)
        # 精确匹配优先,否则子串模糊
        comp = name_row_map.get(name)
        if comp is None:
            for cname, c in name_row_map.items():
                if name in cname or cname in name:
                    comp = c
                    break
        if comp is None:
            continue
        industry = (comp.get("industry") or "").strip()
        ctype = (comp.get("company_type") or "").strip()
        # company_tier 在 positions 表,取该公司最常见 tier
        tier = ""
        try:
            conn = job_db._get_conn()
            row = conn.execute(
                "SELECT company_tier, COUNT(*) as cnt FROM positions "
                "WHERE company_id = ? AND company_tier IS NOT NULL AND company_tier != '' "
                "GROUP BY company_tier ORDER BY cnt DESC LIMIT 1",
                (comp.get("id"),),
            ).fetchone()
            conn.close()
            if row:
                tier = (row[0] or "").strip()
        except Exception:
            pass
        if industry or ctype or tier:
            features.add((industry, ctype, tier))

    return names, features


def _match_company_preference(profile, job: Dict) -> Tuple[float, List[str]]:
    """公司意向优先:用户写了目标公司,则同行业/同类型/同地位的公司加分。

    评分规则:
      - 直接命中目标公司 → 100
      - 同行业 + 同类型 + 同地位 → 80
      - 同行业 + 同类型 → 60
      - 同行业 → 40
      - 同类型 → 20
      - 都不沾 → 0
    用户未填目标公司时返回 50(中性,不影响排序)。
    解析结果缓存到 profile,避免每个岗位都查库。
    """
    reasons: List[str] = []
    target_companies = getattr(profile, "target_companies", []) or []
    if not target_companies:
        return 50.0, []

    cache = getattr(profile, "_company_pref_cache", None)
    if cache is None:
        cache = _resolve_target_company_features(target_companies)
        try:
            setattr(profile, "_company_pref_cache", cache)
        except Exception:
            pass

    target_names, target_features = cache
    job_company = (job.get("company") or job.get("company_name") or "").strip()
    job_industry = (job.get("industry") or "").strip()
    job_type = (job.get("company_type") or "").strip()
    job_tier = (job.get("company_tier") or "").strip()

    if job_company:
        for tn in target_names:
            if job_company == tn or tn in job_company or job_company in tn:
                reasons.append(f"公司意向:「{job_company}」命中用户目标公司")
                return 100.0, reasons

    best = 0.0
    best_desc = ""
    for t_industry, t_type, t_tier in target_features:
        score = 0.0
        parts = []
        if job_industry and t_industry and job_industry == t_industry:
            score += 40
            parts.append(f"同行业({t_industry})")
        if job_type and t_type and job_type == t_type:
            score += 20
            parts.append(f"同类型({t_type})")
        if job_tier and t_tier and job_tier == t_tier:
            score += 20
            parts.append(f"同地位({t_tier})")
        if score > best:
            best = score
            best_desc = "、".join(parts)

    if best > 0:
        reasons.append(f"公司意向:与目标公司{best_desc} → {best:.0f}分")
    return best, reasons


def _match_skill(job: Dict, u: Dict) -> Tuple[float, List[str]]:
    """综合技能:岗位 keywords + hard_skills 的并集与用户 skill_all 做覆盖度匹配。

    第一性原理:skill 维度应衡量"岗位要求的技能,候选人覆盖了多少"。
    用 coverage(命中数/岗位技能数) 为主,Jaccard 为辅(防止乱命中刷分)。
    旧版用 jaccard×200 会导致用户关键词多时 Jaccard 被严重稀释
    (39 个用户词 vs 3 个岗位词,命中 1 个 → jaccard=1/41 → 仅 4.8 分),
    使真实命中岗位的 skill 维度反常低分,拖垮整体分。

    空岗位关键词直接给 0 分,避免降级岗位靠无技能要求混上排行榜。
    """
    jk = _extract_job_keywords(job)
    job_all = list(set(jk["keywords"] + jk["hard_skills"]))
    reasons: List[str] = []

    if not job_all:
        return 0.0, ["岗位无可用关键词(拆岗质量不足)"]

    user_all = u.get("skill_all") or []
    _, jaccard, hits = keyword_set_overlap(user_all, job_all)

    coverage = len(hits) / len(job_all) if job_all else 0
    # coverage 为主(岗位技能覆盖率),jaccard 为辅(奖励高重合度)
    score = min(100.0, coverage * 100.0 + jaccard * 30.0)

    if hits:
        hit_kws = [f"{uk}↔{jk2}" for uk, jk2 in hits[:6]]
        reasons.append(f"关键词命中{len(hits)}/{len(job_all)}: {', '.join(hit_kws)}")
    else:
        reasons.append(
            f"岗位关键词 {', '.join(job_all[:5])} 与候选人无交集"
        )

    return score, reasons


def score_job(job: Dict, profile, llm_client=None) -> Dict:
    u = _extract_user_keywords(profile)

    dim_scores: Dict[str, float] = {}
    all_reasons: List[str] = []
    comp_info: Dict = {}

    for dim_name, result in [
        ("skill", _match_skill(job, u)),
        ("hard_skill", _match_hard_skill(job, u)),
        ("cert", _match_cert(profile, job, u)),
        ("education", _match_education(profile, job)),
        ("major", _match_major(profile, job, u)),
        ("city", _match_city(profile, job)),
        ("role", _match_role(profile, job, u)),
        ("soft_skill", _match_soft_skill(job, u)),
        ("competitiveness", _match_competitiveness(profile, job)),
        ("company_preference", _match_company_preference(profile, job)),
    ]:
        # competitiveness 返回 (score, reasons, info),其余返回 (score, reasons)
        if dim_name == "competitiveness":
            score, reasons, comp_info = result
        else:
            score, reasons = result
        dim_scores[dim_name] = score
        all_reasons.extend([f"[{dim_name}] {r}" for r in reasons])

    total = sum(
        dim_scores.get(dim, 60.0) * weight
        for dim, weight in DIMENSION_WEIGHTS.items()
    )

    score = max(0.0, min(100.0, total))

    # 方向硬门槛:role 维度 < ROLE_GATE_THRESHOLD 表示方向明显错配,
    # 无论技能分多高,总分上限 = ROLE_GATE_CAP(压到"不建议"档)。
    # 第一性原理:求职方向是用户最核心偏好,方向不对的岗位对用户无价值,
    # 不应靠泛技能/字符级假命中挤进 Top 排行。
    role_score = dim_scores.get("role", 0.0)
    role_gated = False
    if role_score < ROLE_GATE_THRESHOLD:
        if score > ROLE_GATE_CAP:
            score = ROLE_GATE_CAP
        role_gated = True
        all_reasons.append(
            f"[role] 方向硬门槛触发:role维度{role_score:.0f}<{ROLE_GATE_THRESHOLD:.0f},"
            f"总分上限{ROLE_GATE_CAP:.0f}"
        )

    score = round(score, 1)

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
        "方向门槛触发": role_gated,
        "竞争力信息": comp_info,
    }
