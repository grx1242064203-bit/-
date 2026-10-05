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
) -> dict[str, Any]:
    """基于画像推荐 top_n 岗位。

    流程：
    1. build_user_profile → UserProfile
    2. user_matcher.UserMatcher.match_jobs_for_user → 已排序的 top 岗位
    3. 补齐不足 top_n 的部分（scorer 全量排序取前 top_n）
    4. 标记 recommend_level（超级推荐/推荐/可申请）

    Returns:
        {"jobs": [...], "total_matched": int, "profile_snapshot": {...}}
        每个 job 含 score / recommend / dims / reasons
    """
    from user_matcher import UserMatcher
    import job_db

    user_profile = build_user_profile(profile_dict)

    # 先跑 matcher（DB 预筛 + 规则预筛 + AI 评分）
    matcher = UserMatcher(user_profile)
    try:
        top_jobs = matcher.match_jobs_for_user(
            user_profile,
            top_n=top_n,
            max_per_company=3,
        )
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
                    scored_remaining.append({**pos, **result})
                except Exception:
                    continue

            scored_remaining.sort(key=lambda x: -(x.get("score") or x.get("综合匹配度", 0) or 0))
            top_jobs.extend(scored_remaining[:need])
        except Exception as e:
            logger.error(f"补齐失败: {e}", exc_info=True)

    # 标记推荐等级
    for j in top_jobs:
        score = j.get("score") or j.get("综合匹配度", 0) or 0
        # recommend 字段已由 scorer 生成（强烈推荐/推荐/可申请/不建议）
        rec = j.get("recommend") or ""
        if rec == "强烈推荐":
            j["recommend_level"] = "super_recommend"  # 超级推荐
        elif rec == "推荐":
            j["recommend_level"] = "recommend"        # 推荐
        elif rec == "可申请":
            j["recommend_level"] = "applyable"        # 可申请
        else:
            j["recommend_level"] = "low"              # 不建议

    # 统一返回字段，前端用中文（和飞书 schema 对齐）
    formatted = []
    for j in top_jobs:
        formatted.append({
            "job_id": j.get("job_id") or j.get("position_id") or "",
            "title": j.get("position_title") or j.get("title") or "",
            "company": j.get("company_name") or j.get("company") or "",
            "industry": j.get("industry") or "",
            "company_type": j.get("company_type") or "",
            "difficulty": j.get("difficulty") or "",
            "city": j.get("city") or j.get("location") or "",
            "min_education": j.get("min_education") or j.get("education_req") or "",
            "category": j.get("job_category") or "",
            "subcategory": j.get("job_subcategory") or "",
            "deadline": j.get("deadline"),
            "apply_url": j.get("apply_url") or j.get("ann_apply_url") or "",
            "announcement_url": j.get("source_url") or "",
            "score": round(float(j.get("score") or j.get("综合匹配度", 0) or 0), 1),
            "recommend": j.get("recommend") or "",
            "recommend_level": j.get("recommend_level") or "",
            "reasons": j.get("reasons") or j.get("匹配理由") or [],
            "dims": j.get("dims") or {},
        })

    return {
        "jobs": formatted,
        "total_matched": total_matched,
        "total_returned": len(formatted),
        "top_n_requested": top_n,
    }
