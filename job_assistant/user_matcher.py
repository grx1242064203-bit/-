"""
用户匹配器 — 从总数据库中筛选与用户画像匹配的岗位。

两阶段匹配:
1. 规则预筛:行业/公司类型/城市/专业关键词,快速过滤 70% 不相关岗位
2. AI 评分:对预筛通过的岗位调用 score_job 生成匹配度评分

输出: 按匹配度排序的岗位列表,每公司最多 max_per_company 个。
"""
import logging
from typing import List, Dict
from collections import defaultdict

from models import UserProfile
from scorer import score_job
import job_db

logger = logging.getLogger(__name__)


class UserMatcher:
    """用户岗位匹配器"""

    def __init__(self, profile: UserProfile, llm_client=None):
        self.profile = profile
        self.llm = llm_client

    def _rule_filter(self, jobs: List[Dict]) -> List[Dict]:
        """
        规则预筛:基于用户画像的硬条件过滤。
        过滤维度:届数范围、目标行业、偏好公司类型、学历、城市、专业、技能、证书。
        优先使用结构化字段(job_category/hard_skills/major_required等)做精准匹配,
        结构化字段为空时降级到全文关键词匹配。
        """
        target_industries = set(self.profile.target_industries or [])
        pref_types = set(self.profile.preferred_company_types or [])
        target_cities = set(self.profile.target_cities or [])
        # 用户毕业届数
        user_grade = None
        try:
            gy = (self.profile.graduation_year or "").strip()
            if gy:
                user_grade = int(gy)
        except (ValueError, TypeError):
            user_grade = None
        # 用户学历
        user_degree = (self.profile.degree or "").strip()
        degree_order = {"大专": 1, "本科": 2, "硕士": 3, "博士": 4}
        user_degree_level = degree_order.get(user_degree, 0)
        # 用户专业
        user_major = (self.profile.major or "").strip()
        # 用户技能
        user_skills = [s.lower() for s in (self.profile.core_skills or [])]
        # 用户证书
        user_certs = [c.lower() for c in (self.profile.target_certificates or [])]

        # 收集用户所有方向关键词
        all_kws = []
        for kws in (self.profile.direction_keywords or {}).values():
            all_kws.extend(kws)
        all_kws_lower = [k.lower() for k in all_kws]

        filtered = []
        for job in jobs:
            # 1. 届数匹配
            if user_grade is not None:
                min_g = job.get("target_min_grade")
                max_g = job.get("target_max_grade")
                if min_g is not None and user_grade < min_g:
                    continue
                if max_g is not None and user_grade > max_g:
                    continue

            # 2. 行业匹配
            industry = job.get("industry", "")
            if target_industries and industry not in target_industries:
                continue

            # 3. 公司类型匹配
            ctype = job.get("company_type", "")
            if pref_types and ctype not in pref_types:
                continue

            # 4. 学历匹配(优先用 min_education 结构化字段)
            job_min_edu = (job.get("min_education") or "").strip()
            job_edu_raw = (job.get("education") or "").strip()
            edu_to_check = job_min_edu or job_edu_raw
            if edu_to_check:
                job_min_level = degree_order.get(edu_to_check, 0)
                if job_min_level > 0 and user_degree_level > 0 and user_degree_level < job_min_level:
                    continue

            # 5. 城市匹配(优先用 city 结构化字段)
            job_city = (job.get("city") or "").lower()
            job_loc = (job.get("locations") or "").lower()
            city_text = job_city or job_loc
            if target_cities and city_text:
                if not any(c.lower() in city_text for c in target_cities):
                    continue

            # 6. 专业匹配(优先用 major_required 结构化字段)
            job_major = (job.get("major_required") or "").lower()
            if user_major and job_major:
                # 用户专业与岗位专业要求有交集(简单包含判断)
                if user_major not in job_major and not any(m in user_major for m in job_major.split(',')):
                    # 专业不匹配,但如果是管培/不限专业则保留
                    major_cat = (job.get("major_category") or "").strip()
                    if major_cat != "不限" and "管培" not in job.get("job_title", ""):
                        continue

            # 7. 技能匹配(优先用 hard_skills 结构化字段)
            job_hard_skills = (job.get("hard_skills") or "").lower()
            if user_skills and job_hard_skills:
                # 用户技能与岗位硬技能有交集
                skill_hit = any(s in job_hard_skills for s in user_skills)
                if not skill_hit:
                    # 降级:用全文关键词匹配
                    text = (job.get("job_title", "") + " " + job.get("jd_summary", "")).lower()
                    if all_kws_lower and not any(kw in text for kw in all_kws_lower):
                        if "管培" not in text and "mt" not in text:
                            continue
            elif user_skills and not job_hard_skills:
                # 岗位无结构化技能字段,降级到全文匹配
                text = (job.get("job_title", "") + " " + job.get("jd_summary", "")).lower()
                if all_kws_lower and not any(kw in text for kw in all_kws_lower):
                    if "管培" not in text and "mt" not in text:
                        continue

            # 8. 证书匹配(如果岗位有证书要求,用户需持有)
            job_certs = (job.get("certifications") or "").lower()
            if job_certs:
                job_cert_list = [c.strip() for c in job_certs.split(',') if c.strip()]
                # 岗位要求证书但用户一个都没有 → 过滤(除非是管培)
                if job_cert_list and not any(c in job_certs for c in user_certs):
                    if "管培" not in job.get("job_title", ""):
                        continue

            filtered.append(job)

        logger.info(f"规则预筛: {len(jobs)} → {len(filtered)} 条")
        return filtered

    def _score_and_rank(self, jobs: List[Dict]) -> List[Dict]:
        """AI 评分并排序"""
        scored = []
        for job in jobs:
            # 转换为 score_job 需要的格式
            # 注意:jd_summary 需透传,作为 LLM 分析失败时 JD摘要 的降级值
            # industry/company_type/difficulty 来自公司库,透传到飞书表
            job_for_score = {
                "title": job.get("job_title", ""),
                "company": job.get("company", ""),
                "jd_text": job.get("jd_summary", ""),
                "jd_summary": job.get("jd_summary", ""),
                "industry": job.get("industry", ""),
                "company_type": job.get("company_type", ""),
                "difficulty": job.get("difficulty", ""),
                "location": job.get("locations", ""),
                "salary": job.get("salary", ""),
                "jd_url": job.get("apply_url", "") or job.get("announcement_url", ""),
                "posted": job.get("publish_time", ""),
                "recruitment_stage": job.get("recruitment_stage", ""),
                "education": job.get("education", ""),
                "department": job.get("department", ""),
            }
            try:
                result = score_job(job_for_score, self.profile, llm_client=self.llm)
                scored.append({**job, **result})
            except Exception as e:
                logger.warning(f"评分失败 [{job.get('company')}]: {e}")
                scored.append({**job, "相关性评分": 50, "综合推荐度": "可申请"})

        # 按相关性评分降序
        scored.sort(key=lambda x: x.get("相关性评分", 0), reverse=True)
        return scored

    def _limit_per_company(self, jobs: List[Dict], max_per_company: int = 5) -> List[Dict]:
        """每公司最多保留 max_per_company 个岗位"""
        groups = defaultdict(list)
        for j in jobs:
            company = j.get("company", "未知")
            groups[company].append(j)

        result = []
        for company, group in groups.items():
            # 组内已按评分排序,取前 N
            result.extend(group[:max_per_company])

        # 重新按评分排序
        result.sort(key=lambda x: x.get("相关性评分", 0), reverse=True)
        logger.info(f"每公司限{max_per_company}: {len(jobs)} → {len(result)} 条")
        return result

    def match(self, max_per_company: int = 5, min_score: int = 30) -> List[Dict]:
        """
        执行完整匹配流程。

        Args:
            max_per_company: 每公司最多岗位数
            min_score: 最低匹配度评分(低于此值的过滤)

        Returns:
            匹配岗位列表(按评分降序)
        """
        # 1. 从总数据库获取匹配届数的在招岗位
        user_grade = None
        try:
            gy = (self.profile.graduation_year or "").strip()
            if gy:
                user_grade = int(gy)
        except (ValueError, TypeError):
            user_grade = None
        if user_grade:
            all_jobs = job_db.get_jobs_by_grade(user_grade)
        else:
            all_jobs = job_db.get_all_active_jobs()
        if not all_jobs:
            logger.info("总数据库为空,无匹配岗位")
            return []

        logger.info(f"总数据库在招岗位: {len(all_jobs)} 条")

        # 2. 规则预筛
        filtered = self._rule_filter(all_jobs)
        if not filtered:
            return []

        # 3. AI 评分
        scored = self._score_and_rank(filtered)

        # 4. 过滤低于最低分的
        scored = [j for j in scored if j.get("相关性评分", 0) >= min_score]
        logger.info(f"评分过滤(≥{min_score}): {len(scored)} 条")

        # 5. 每公司限制
        result = self._limit_per_company(scored, max_per_company)
        return result


def match_jobs_for_user(profile: UserProfile, llm_client=None,
                        max_per_company: int = 5) -> List[Dict]:
    """便捷函数:为用户匹配岗位"""
    matcher = UserMatcher(profile, llm_client=llm_client)
    return matcher.match(max_per_company=max_per_company)
