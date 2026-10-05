"""岗位推荐适配层 — 把 resume_profiles 画像 dict 转成 UserProfile，调 user_matcher 推荐。

第一性原则：适配层做格式转换 + 补齐默认值，业务逻辑全在下游（user_matcher / scorer）。
对抗性审查：画像缺字段时给合理默认，绝不能抛 NoneType。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_user_profile(profile_dict: dict) -> "UserProfile":
    """从 resume_profiles 表的画像 dict 构造 UserProfile。

    Args:
        profile_dict: resume_profile model 返回的 dict，含
            keywords / fit_directions / degree / major / target_cities / resume_text

    Returns:
        填充好的 UserProfile 实例
    """
    # 优先用 job_api/main.py 预加载的 jobseeker_models 别名(根目录 models.py),
    # 避免被 job_api/models/ 包遮蔽。直接运行测试时回退到 from models import。
    try:
        from jobseeker_models import UserProfile
    except ImportError:
        from models import UserProfile

    keywords = profile_dict.get("keywords") or []
    fit_dirs = profile_dict.get("fit_directions") or []

    # fit_directions 里权重最高的 direction 作为 role
    # 容错:fit_dirs 可能是 ["后端","全栈"] 字符串数组,也可能是 [{"direction":"后端","weight":3}] dict 数组
    role = ""
    if fit_dirs:
        dict_dirs = [d for d in fit_dirs if isinstance(d, dict)]
        if dict_dirs:
            sorted_dirs = sorted(dict_dirs, key=lambda x: -(x.get("weight") or 0))
            role = sorted_dirs[0].get("direction") or ""
        else:
            # 字符串数组:取第一个作为 role
            role = str(fit_dirs[0]) if fit_dirs[0] else ""

    # structured_keywords：直接透传（scorer 依赖）
    structured_keywords = keywords

    # 容错:keywords 可能是 ["Python","React"] 字符串数组,而非 [{"category":"skill","standard":"Python"}] dict 数组
    # 字符串场景下,全部归入 skill 类
    has_dict_kw = any(isinstance(k, dict) for k in keywords)
    if not has_dict_kw and keywords:
        str_keywords = [str(k) for k in keywords if k]
        core_skills_set = set(str_keywords)
        direction_keywords = {"skill": str_keywords}
    else:
        # core_skills：hard_skill/tool/framework 类关键词的 standard/kw
        core_skills_set = set()
        for tag in keywords:
            if not isinstance(tag, dict):
                continue
            cat = tag.get("category", "")
            if cat in ("hard_skill", "tool", "framework", "skill"):
                std = tag.get("standard") or tag.get("kw") or ""
                if std:
                    core_skills_set.add(std)

        # direction_keywords：按 category 分组
        direction_keywords: dict[str, list[str]] = {}
        for tag in keywords:
            if not isinstance(tag, dict):
                continue
            cat = tag.get("category", "")
            std = tag.get("standard") or tag.get("kw") or ""
            if not std:
                continue
            # scorer 用 role / domain / skill 三个 key
            if cat == "role":
                direction_keywords.setdefault("role", []).append(std)
            elif cat == "domain":
                direction_keywords.setdefault("domain", []).append(std)
            elif cat in ("hard_skill", "tool", "framework", "skill"):
                direction_keywords.setdefault("skill", []).append(std)

    target_cities = profile_dict.get("target_cities") or []

    return UserProfile(
        role=role,
        degree=profile_dict.get("degree") or "",
        major=profile_dict.get("major") or "",
        graduation_year="2027",  # 校招默认 27 届；可后续从 resume_text 提取
        graduation_date="2027-07",
        target_cities=target_cities,
        resume_text=profile_dict.get("resume_text") or "",
        structured_keywords=structured_keywords,
        fit_directions=fit_dirs,
        core_skills=list(core_skills_set),
        direction_keywords=direction_keywords,
    )


def recommend_jobs(
    profile_dict: dict,
    top_n: int = 200,
    use_cache: bool = True,
) -> dict[str, Any]:
    """基于画像推荐 top_n 岗位。

    流程：
    1. build_user_profile → UserProfile
    2. user_matcher.UserMatcher.match_jobs_for_user → 已排序的 top 岗位
    3. 补齐不足 top_n 的部分（scorer 全量排序取前 top_n）
    4. 标记 recommend_level（超级推荐/推荐/可申请）
    5. 写入 job_scores 缓存表(简历修改后清空,下次重新计算)

    缓存策略：
    - use_cache=True 且 job_scores 表有该 profile 的缓存 → 直接读缓存返回
    - use_cache=False (强制刷新) 或无缓存 → 全量计算并写缓存

    Returns:
        {"jobs": [...], "total_matched": int, "profile_snapshot": {...}}
        每个 job 含 score / recommend / reasons / dims (前端契约字段)
    """
    from user_matcher import UserMatcher
    import job_db
    from job_api.models import job_score as score_cache

    profile_id = profile_dict.get("profile_id") or ""

    # 1. 缓存命中:直接读 job_scores 表
    if use_cache and profile_id:
        cached = score_cache.get_cached_scores(profile_id, top_n)
        if cached:
            logger.info(
                f"推荐缓存命中: profile={profile_id}, {len(cached)} 条 (从 job_scores 表)"
            )
            # 把缓存里的评分结果合并到岗位原始数据上
            return _merge_cache_with_jobs(cached, top_n)

    user_profile = build_user_profile(profile_dict)

    # 先跑 matcher（DB 预筛 + 规则预筛 + AI 评分）
    matcher = UserMatcher(user_profile)
    try:
        # UserMatcher.match 签名: (max_per_company, min_score)
        # 返回按评分降序的所有匹配岗位,这里按 top_n 切片
        all_matched = matcher.match(max_per_company=3)
        top_jobs = all_matched[:top_n] if all_matched else []
    except Exception as e:
        logger.error(f"matcher 失败: {e}", exc_info=True)
        top_jobs = []

    total_matched = len(top_jobs)

    # 如果 matcher 返回不足 top_n，从全量岗位补齐（按分数从高到低）
    if len(top_jobs) < top_n:
        try:
            all_positions = job_db.get_active_positions()
            matched_ids = {j.get("job_id") or j.get("position_id") for j in top_jobs}
            remaining = [p for p in all_positions
                         if (p.get("job_id") or p.get("position_id")) not in matched_ids]

            # 补齐：用 scorer 评分取前 N 个
            from scorer import score_job
            need = top_n - len(top_jobs)
            scored_remaining = []
            for pos in remaining[:500]:  # 性能兜底：最多补 500 个再排序
                try:
                    job_for_score = {
                        "title": pos.get("position_title", ""),
                        "position_title": pos.get("position_title", ""),
                        "company": pos.get("company_name", ""),
                        "company_name": pos.get("company_name", ""),
                        "jd_text": pos.get("jd_summary", ""),
                        "jd_summary": pos.get("jd_summary", ""),
                        "industry": pos.get("industry", ""),
                        "company_type": pos.get("company_type", ""),
                        "difficulty": pos.get("difficulty", ""),
                        "location": pos.get("location", ""),
                        "city": pos.get("city", "") or pos.get("location", ""),
                        "keywords": pos.get("keywords", ""),
                        "hard_skills": pos.get("hard_skills", ""),
                        "soft_skills": pos.get("soft_skills", ""),
                        "certifications": pos.get("certifications", ""),
                        "languages": pos.get("languages", ""),
                        "job_category": pos.get("job_category", ""),
                        "job_subcategory": pos.get("job_subcategory", ""),
                        "major_category": pos.get("major_category", ""),
                        "major_required": pos.get("major_required", ""),
                        "min_education": pos.get("min_education", "") or pos.get("education_req", ""),
                        "education_req": pos.get("education_req", ""),
                    }
                    result = score_job(job_for_score, user_profile)
                    # scorer 返回中文键名,合并时统一规整成英文契约键
                    scored_remaining.append({
                        **pos,
                        "score": result.get("相关性评分", 0),
                        "recommend": result.get("综合推荐度", ""),
                        "reasons": result.get("匹配理由", []),
                        "dims": result.get("维度分", {}),
                    })
                except Exception:
                    continue

            # 兼容中英文键名排序
            scored_remaining.sort(
                key=lambda x: -(
                    x.get("score")
                    or x.get("相关性评分")
                    or x.get("综合匹配度", 0)
                    or 0
                )
            )
            top_jobs.extend(scored_remaining[:need])
        except Exception as e:
            logger.error(f"补齐失败: {e}", exc_info=True)

    # 标记推荐等级
    # 兼容 scorer 中文「综合推荐度」与英文「recommend」两种键名
    for j in top_jobs:
        score = (
            j.get("score")
            or j.get("相关性评分")
            or j.get("综合匹配度", 0)
            or 0
        )
        rec = j.get("recommend") or j.get("综合推荐度") or ""
        if rec == "强烈推荐":
            j["recommend_level"] = "super_recommend"  # 超级推荐
        elif rec == "推荐":
            j["recommend_level"] = "recommend"        # 推荐
        elif rec == "可申请":
            j["recommend_level"] = "applyable"        # 可申请
        else:
            j["recommend_level"] = "low"              # 不建议

    # 统一返回字段，前端用中文（和飞书 schema 对齐）
    # 修复:scorer 返回中文键名(相关性评分/综合推荐度/匹配理由/维度分),
    # adapter 必须同时兼容中英文键名读取,否则 score=0 / recommend="" / reasons=[] / dims={},
    # 前端按 recommend_level 分组时所有岗位都落到「其他」组,看不到推荐徽章。
    formatted = []
    for j in top_jobs:
        # 从飞书 schema 中文记录里读中文键,从未映射的 raw pos 里读英文键,二选一
        score_val = (
            j.get("score")
            or j.get("相关性评分")
            or j.get("综合匹配度", 0)
            or 0
        )
        recommend_val = j.get("recommend") or j.get("综合推荐度") or ""
        reasons_val = (
            j.get("reasons")
            or j.get("匹配理由")
            or (j.get("简评") and [j.get("简评")])
            or []
        )
        dims_val = j.get("dims") or j.get("维度分") or {}

        # 飞书 schema 把岗位库英文列名映射成了中文字段名,这里反向取值
        title_val = (
            j.get("title")
            or j.get("岗位标题")
            or j.get("position_title")
            or ""
        )
        company_val = (
            j.get("company")
            or j.get("公司")
            or j.get("company_name")
            or ""
        )
        industry_val = j.get("industry") or j.get("行业") or ""
        company_type_val = j.get("company_type") or j.get("公司类型") or ""
        difficulty_val = j.get("difficulty") or j.get("难度") or ""
        city_val = j.get("city") or j.get("地点") or j.get("location") or ""
        min_edu_val = (
            j.get("min_education")
            or j.get("学历要求")
            or j.get("education_req")
            or ""
        )
        category_val = j.get("category") or j.get("岗位类别") or j.get("job_category") or ""
        subcategory_val = (
            j.get("subcategory")
            or j.get("job_subcategory")
            or ""
        )
        deadline_val = j.get("deadline") or j.get("投递截止日期") or j.get("deadline_ms")
        apply_url_val = (
            j.get("apply_url")
            or j.get("JD链接")
            or j.get("ann_apply_url")
            or ""
        )
        # 飞书 URL 字段是 {"link":..., "text":...} 对象,需要解包
        if isinstance(apply_url_val, dict):
            apply_url_val = apply_url_val.get("link") or ""
        announcement_url_val = j.get("announcement_url") or j.get("source_url") or ""

        # 补齐岗位总表其余字段,前端推荐页与岗位总表字段对齐
        recruit_type_val = j.get("recruit_type") or j.get("招聘类型") or ""
        recruit_target_val = j.get("recruit_target") or j.get("招聘对象") or ""
        is_mt_val = j.get("is_mt")
        if is_mt_val is None:
            is_mt_val = j.get("is_management_trainee") or j.get("管培")
        major_category_val = j.get("major_category") or j.get("专业大类") or ""
        major_required_val = j.get("major_required") or j.get("专业要求") or ""
        jd_summary_val = j.get("jd_summary") or j.get("JD摘要") or ""
        hard_skills_val = j.get("hard_skills") or j.get("硬技能") or ""
        keywords_val = j.get("keywords") or j.get("关键词") or ""
        updated_at_val = (
            j.get("updated_at")
            or j.get("发布时间")
            or j.get("publish_time")
            or ""
        )

        # 公司层级 × 用户层级 透明化(competitiveness 信息)
        # scorer 返回中文键「竞争力信息」,内含 candidate_score/company_score/label
        comp_info = j.get("竞争力信息") or j.get("competitiveness_info") or {}
        company_tier_val = j.get("company_tier") or ""
        # 如果 job 本身没有 company_tier(公司库场景),从 comp_info.company_breakdown 取
        if not company_tier_val and comp_info:
            company_tier_val = (
                comp_info.get("company_breakdown", {}).get("company_position_label", "")
                or ""
            )
        candidate_score_val = comp_info.get("candidate_score", 0) if comp_info else 0
        company_score_val = comp_info.get("company_score", 0) if comp_info else 0
        alignment_label_val = comp_info.get("label", "") if comp_info else ""

        formatted.append({
            "job_id": j.get("job_id") or j.get("position_id") or "",
            "title": title_val,
            "company": company_val,
            "industry": industry_val,
            "company_type": company_type_val,
            "difficulty": difficulty_val,
            "city": city_val,
            "min_education": min_edu_val,
            "category": category_val,
            "subcategory": subcategory_val,
            "deadline": deadline_val,
            "apply_url": apply_url_val,
            "announcement_url": announcement_url_val,
            "score": round(float(score_val), 1),
            "recommend": recommend_val,
            "recommend_level": j.get("recommend_level") or "",
            "reasons": reasons_val,
            "dims": dims_val,
            # 补齐字段(与岗位总表对齐)
            "recruit_type": recruit_type_val,
            "recruit_target": recruit_target_val,
            "is_mt": bool(is_mt_val) if is_mt_val in (1, "1", True, "true", "True", "是") else False,
            "major_category": major_category_val,
            "major_required": major_required_val,
            "jd_summary": jd_summary_val,
            "hard_skills": hard_skills_val,
            "keywords": keywords_val,
            "updated_at": updated_at_val,
            # 公司层级 × 用户层级 透明化
            "company_tier": company_tier_val,
            "candidate_score": round(float(candidate_score_val), 1) if candidate_score_val else 0,
            "company_score": round(float(company_score_val), 1) if company_score_val else 0,
            "alignment_label": alignment_label_val,
        })

    # 5. 写入 job_scores 缓存表(下次切页直接读缓存,毫秒级返回)
    if profile_id and formatted:
        try:
            # 把 formatted 里已规整的字段转回缓存格式
            cache_jobs = []
            for j in formatted:
                comp_info = j.get("competitiveness_info") or {}
                if not comp_info and j.get("alignment_label"):
                    comp_info = {
                        "label": j.get("alignment_label", ""),
                        "candidate_score": j.get("candidate_score", 0),
                        "company_score": j.get("company_score", 0),
                    }
                cache_jobs.append({
                    "job_id": j.get("job_id", ""),
                    "score": j.get("score", 0),
                    "recommend_level": j.get("recommend_level", ""),
                    "recommend": j.get("recommend", ""),
                    "reasons": j.get("reasons", []),
                    "dims": j.get("dims", {}),
                    "company_tier": j.get("company_tier", ""),
                    "competitiveness_info": comp_info,
                })
            saved = score_cache.save_scores(profile_id, cache_jobs)
            logger.info(f"推荐结果已缓存: profile={profile_id}, {saved} 条")
        except Exception as e:
            logger.warning(f"写 job_scores 缓存失败(不阻塞主流程): {e}")

    return {
        "jobs": formatted,
        "total_matched": total_matched,
        "total_returned": len(formatted),
        "top_n_requested": top_n,
    }


def _merge_cache_with_jobs(cached_scores: list[dict], top_n: int) -> dict:
    """把 job_scores 缓存里的评分结果合并到岗位原始数据上。

    缓存只存评分字段(score/recommend_level/alignment_label/...),
    岗位原始字段(title/company/industry/...)需要从 jobs 表实时查。
    """
    import job_db

    if not cached_scores:
        return {
            "jobs": [],
            "total_matched": 0,
            "total_returned": 0,
            "top_n_requested": top_n,
        }

    # 批量查岗位原始数据
    job_ids = [c["job_id"] for c in cached_scores if c.get("job_id")]
    raw_jobs_map: dict[str, dict] = {}
    try:
        all_positions = job_db.get_active_positions()
        for p in all_positions:
            jid = str(p.get("job_id") or p.get("position_id") or "")
            if jid in job_ids:
                raw_jobs_map[jid] = p
    except Exception as e:
        logger.warning(f"读取岗位原始数据失败: {e}")

    # 合并
    formatted = []
    for c in cached_scores:
        jid = c.get("job_id", "")
        raw = raw_jobs_map.get(jid, {})
        comp_info = c.get("competitiveness_info") or {}

        # 从 raw(英文键) + cache 评分字段 构造 formatted 项
        formatted.append({
            "job_id": jid,
            "title": raw.get("position_title") or raw.get("title") or "",
            "company": raw.get("company_name") or raw.get("company") or "",
            "industry": raw.get("industry") or "",
            "company_type": raw.get("company_type") or "",
            "difficulty": raw.get("difficulty") or "",
            "city": raw.get("city") or raw.get("location") or "",
            "min_education": raw.get("min_education") or raw.get("education_req") or "",
            "category": raw.get("job_category") or "",
            "subcategory": raw.get("job_subcategory") or "",
            "deadline": raw.get("deadline") or "",
            "apply_url": raw.get("apply_url") or "",
            "announcement_url": raw.get("announcement_url") or "",
            "score": c.get("score", 0),
            "recommend": c.get("recommend", ""),
            "recommend_level": c.get("recommend_level", ""),
            "reasons": c.get("reasons", []),
            "dims": c.get("dims", {}),
            # 补齐字段
            "recruit_type": raw.get("recruit_type") or "",
            "recruit_target": raw.get("recruit_target") or "",
            "is_mt": bool(raw.get("is_management_trainee") in (1, "1", True, "是")),
            "major_category": raw.get("major_category") or "",
            "major_required": raw.get("major_required") or "",
            "jd_summary": raw.get("jd_summary") or "",
            "hard_skills": raw.get("hard_skills") or "",
            "keywords": raw.get("keywords") or "",
            "updated_at": raw.get("publish_time") or raw.get("updated_at") or "",
            # 公司层级 × 用户层级 透明化
            "company_tier": c.get("company_tier") or comp_info.get("company_tier") or "",
            "candidate_score": c.get("candidate_score", 0),
            "company_score": c.get("company_score", 0),
            "alignment_label": c.get("alignment_label") or comp_info.get("label", ""),
        })

    return {
        "jobs": formatted,
        "total_matched": len(formatted),
        "total_returned": len(formatted),
        "top_n_requested": top_n,
    }
