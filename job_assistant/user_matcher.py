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
        过滤维度:目标行业、偏好公司类型、目标城市、专业关键词。
        """
        target_industries = set(self.profile.target_industries or [])
        pref_types = set(self.profile.preferred_company_types or [])
        target_cities = set(self.profile.target_cities or [])
        # 收集用户所有方向关键词(用于专业/技能匹配)
        all_kws = []
        for kws in (self.profile.direction_keywords or {}).values():
            all_kws.extend(kws)
        all_kws_lower = [k.lower() for k in all_kws]

        filtered = []
        for job in jobs:
            # 行业匹配:用户选了行业则必须匹配,没选则全通过
            industry = job.get("industry", "")
            if target_industries and industry not in target_industries:
                continue
            # 公司类型匹配:用户选了类型则必须匹配
            ctype = job.get("company_type", "")
            if pref_types and ctype not in pref_types:
                continue
            # 城市匹配:用户选了城市则必须匹配(岗位地点字段可能为空,空则不排除)
            # 总数据库暂存地点信息不完整,这里放宽:有地点才检查
            # (城市匹配在 score_job 中也会做,这里不硬过滤)
            # 专业/技能关键词匹配:标题或摘要含用户关键词
            text = (job.get("job_title", "") + " " + job.get("jd_summary", "")).lower()
            if all_kws_lower and not any(kw in text for kw in all_kws_lower):
                # 没有关键词命中,但如果是管培/通用岗也保留
                if "管培" not in text and "mt" not in text:
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
                "location": "",
                "salary": "",
                "jd_url": job.get("jd_url", ""),
                "posted": job.get("publish_time", ""),
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
        # 1. 从总数据库获取所有在招岗位
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
