"""
用户匹配器 — 从 positions 表(关联 announcements + companies)筛选匹配岗位。

校招专属设计(不再支持实习/社招):
1. DB 层预筛:届数 ∈ [min_grade, max_grade] + 行业 + 公司类型
2. 规则预筛:目标城市 + 专业关键词(岗位标题/JD摘要)
3. AI 评分:对预筛通过的岗位调用 score_job 生成匹配度评分

输出: 按匹配度排序的岗位列表,每公司最多 max_per_company 个。
"""
import logging
from typing import List, Dict
from collections import defaultdict

from models import UserProfile
from scorer import score_job
import job_db

logger = logging.getLogger(__name__)


def _graduation_year_to_grade(year: str) -> int:
    """毕业年份(如 "2026")转届数(如 26)。无法解析返回 0(不过滤)。"""
    if not year:
        return 0
    try:
        y = int(str(year).strip()[:4])
        if 2020 <= y <= 2030:
            return y % 100
    except (ValueError, TypeError):
        pass
    return 0


class UserMatcher:
    """校招用户岗位匹配器"""

    def __init__(self, profile: UserProfile, llm_client=None):
        self.profile = profile
        self.llm = llm_client
        self.user_grade = _graduation_year_to_grade(profile.graduation_year)

    def _rule_filter(self, positions: List[Dict]) -> List[Dict]:
        """
        规则预筛:基于用户画像的硬条件过滤。
        过滤维度:目标城市、专业/技能关键词。
        (届数/行业/公司类型已在 DB 层预筛)
        """
        target_cities = set(self.profile.target_cities or [])
        # 收集用户所有方向关键词(用于专业/技能匹配)
        all_kws = []
        for kws in (self.profile.direction_keywords or {}).values():
            all_kws.extend(kws)
        all_kws_lower = [k.lower() for k in all_kws]

        filtered = []
        for pos in positions:
            # 城市匹配:用户选了城市则必须匹配(岗位地点为空则不排除)
            location = pos.get("location", "")
            if target_cities and location:
                if not any(c in location for c in target_cities):
                    continue
            # 专业/技能关键词匹配:标题或摘要含用户关键词
            text = (pos.get("position_title", "") + " " + pos.get("jd_summary", "")).lower()
            if all_kws_lower and not any(kw in text for kw in all_kws_lower):
                # 没有关键词命中,但如果是管培/通用岗也保留
                if "管培" not in text and "通用" not in text:
                    continue
            filtered.append(pos)

        logger.info(f"规则预筛: {len(positions)} → {len(filtered)} 条")
        return filtered

    def _score_and_rank(self, positions: List[Dict]) -> List[Dict]:
        """AI 评分并排序"""
        scored = []
        for pos in positions:
            # 转换为 score_job 需要的格式
            # jd_summary 作为 jd_text 传入(岗位级摘要)
            # apply_url 优先岗位级,降级公告级
            apply_url = pos.get("apply_url", "") or pos.get("ann_apply_url", "")
            job_for_score = {
                "title": pos.get("position_title", ""),
                "company": pos.get("company_name", ""),
                "jd_text": pos.get("jd_summary", ""),
                "jd_summary": pos.get("jd_summary", ""),
                "industry": pos.get("industry", ""),
                "company_type": pos.get("company_type", ""),
                "difficulty": pos.get("difficulty", ""),
                "department": pos.get("department", ""),
                "location": pos.get("location", ""),
                "salary": "",
                "jd_url": apply_url,
                "posted": pos.get("publish_time", ""),
            }
            try:
                result = score_job(job_for_score, self.profile, llm_client=self.llm)
                # 保留 positions 表的 dedup_hash(用于去重写入用户表)
                result["_dedup_hash"] = pos.get("dedup_hash", "")
                result["source_url"] = pos.get("source_url", "")
                scored.append({**pos, **result})
            except Exception as e:
                logger.warning(f"评分失败 [{pos.get('company_name')}]: {e}")
                scored.append({**pos, "相关性评分": 50, "综合推荐度": "可申请"})

        # 按相关性评分降序
        scored.sort(key=lambda x: x.get("相关性评分", 0), reverse=True)
        return scored

    def _limit_per_company(self, jobs: List[Dict], max_per_company: int = 5) -> List[Dict]:
        """每公司最多保留 max_per_company 个岗位"""
        groups = defaultdict(list)
        for j in jobs:
            company = j.get("company_name", "未知")
            groups[company].append(j)

        result = []
        for company, group in groups.items():
            # 组内已按评分排序,取前 N
            result.extend(group[:max_per_company])

        # 重新按评分排序
        result.sort(key=lambda x: x.get("相关性评分", 0), reverse=True)
        logger.info(f"每公司限{max_per_company}: {len(jobs)} → {len(result)} 条")
        return result

    def match(self, max_per_company: int = 5, min_score: int = 55) -> List[Dict]:
        """
        执行完整匹配流程(校招专属)。

        Args:
            max_per_company: 每公司最多岗位数
            min_score: 最低匹配度评分(低于此值的过滤)

        Returns:
            匹配岗位列表(按评分降序)
        """
        # 1. DB 层预筛:届数 + 行业 + 公司类型
        all_positions = job_db.get_active_positions(
            user_grade=self.user_grade,
            industries=self.profile.target_industries or None,
            company_types=self.profile.preferred_company_types or None,
        )
        if not all_positions:
            logger.info("岗位库为空或无匹配岗位")
            return []

        logger.info(f"DB 预筛岗位(届数={self.user_grade}): {len(all_positions)} 条")

        # 2. 规则预筛(城市 + 关键词)
        filtered = self._rule_filter(all_positions)
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
    """便捷函数:为校招用户匹配岗位"""
    matcher = UserMatcher(profile, llm_client=llm_client)
    return matcher.match(max_per_company=max_per_company)
