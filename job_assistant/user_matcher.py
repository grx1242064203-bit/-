"""
用户匹配器 — 从 positions 表(关联 announcements + companies)筛选匹配岗位。

校招专属设计(不再支持实习/社招):
1. DB 层预筛:届数 ∈ [min_grade, max_grade] + 行业 + 公司类型
2. 规则预筛:目标城市 + 专业关键词(岗位标题/JD摘要)
3. AI 评分:对预筛通过的岗位调用 score_job 生成匹配度评分
4. 字段映射:DB 英文列名 → 飞书中文字段名(与 schema.py JOB_FIELDS 对齐)

输出: 按匹配度排序的岗位列表,每公司最多 max_per_company 个,字段名为飞书 schema 中文名。
"""
import logging
import time
from typing import List, Dict, Optional
from collections import defaultdict

from models import UserProfile
from scorer import score_job
import job_db

logger = logging.getLogger(__name__)


def _date_to_ms(date_str: Optional[str]) -> Optional[int]:
    """将日期字符串(YYYY-MM-DD / YYYY-MM-DD HH:MM:SS / YYYY.MM.DD)转为毫秒时间戳。
    无法解析时返回 None(不写入该字段,避免飞书日期字段写入失败)。"""
    if not date_str:
        return None
    s = str(date_str).strip().replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y.%m.%d"):
        try:
            return int(time.mktime(time.strptime(s, fmt)) * 1000)
        except (ValueError, TypeError):
            continue
    # 兜底:截取前 10 位(YYYY-MM-DD)再试
    try:
        return int(time.mktime(time.strptime(s[:10], "%Y-%m-%d")) * 1000)
    except (ValueError, TypeError):
        return None


def _url_field(url: str) -> Optional[Dict]:
    """飞书 URL 字段(type=15)需要对象格式 {"link": url, "text": 显示文本}。
    空值返回 None(不写入该字段)。"""
    if not url:
        return None
    return {"link": str(url), "text": str(url)[:50]}


def to_feishu_job_record(pos: Dict, score_result: Dict) -> Dict:
    """将 DB 岗位 dict + scorer 评分结果映射为飞书 JOB_FIELDS 中文 schema 的记录。

    第一性原则:只输出 schema.py JOB_FIELDS 中定义的字段,避免未知字段导致写入异常。
    去重 hash 从 pos['dedup_hash'] 映射到 飞书字段「去重hash」。

    Args:
        pos: job_db.get_active_positions 返回的岗位 dict(英文列名)
        score_result: scorer.score_job 返回的评分 dict(含 相关性评分/综合推荐度/匹配理由)

    Returns:
        飞书可直接写入的 dict(中文字段名)
    """
    # 日期字段转毫秒时间戳
    deadline_ms = _date_to_ms(pos.get("deadline"))
    created_ms = _date_to_ms(pos.get("created_at"))
    publish_ms = _date_to_ms(pos.get("publish_time"))

    # 地点:优先 city,降级 location
    location = pos.get("city") or pos.get("location") or ""
    # 学历要求:优先 min_education,降级 education_req
    education = pos.get("min_education") or pos.get("education_req") or ""
    # JD 链接:优先岗位级 apply_url,降级公告级 ann_apply_url,再降级 source_url
    apply_url = pos.get("apply_url") or pos.get("ann_apply_url") or pos.get("source_url") or ""

    # 管培项目标记:is_management_trainee 为真时填项目名,否则空
    is_mt = bool(pos.get("is_management_trainee"))
    mt_name = f"{pos.get('company_name','')}管培生" if is_mt else ""

    # 简评:取匹配理由前 3 条拼成一句话
    reasons = score_result.get("匹配理由") or []
    brief = "；".join(r.replace("[", "").replace("]", " ", 1) for r in reasons[:3]) if reasons else ""

    # 申请建议:基于综合推荐度
    recommend = score_result.get("综合推荐度", "")
    suggestion_map = {
        "强烈推荐": "高度匹配，建议优先投递",
        "推荐": "匹配度较高，建议尽快投递",
        "可申请": "基本匹配，可尝试投递",
        "不建议": "匹配度较低，建议观望",
    }
    suggestion = suggestion_map.get(recommend, "")

    record = {
        "岗位标题": pos.get("position_title", "") or "",
        "公司": pos.get("company_name", "") or "",
        "行业": pos.get("industry", "") or "",
        "公司类型": pos.get("company_type", "") or "",
        "难度": pos.get("difficulty", "") or "",
        "地点": location,
        "学历要求": education,
        "JD摘要": (pos.get("jd_summary", "") or "")[:500],
        "JD链接": _url_field(apply_url),
        "岗位类别": pos.get("job_category", "") or "",
        "相关性评分": score_result.get("相关性评分", 0),
        "综合推荐度": recommend,
        "简评": brief,
        "申请建议": suggestion,
        "申请状态": "未投递",
        "去重hash": pos.get("dedup_hash", "") or "",
        "是否在招": "是",
        "管培项目": mt_name,
    }

    # 部门字段可选:仅当岗位有部门信息时才写入(避免大量空字段)
    department = pos.get("department", "") or ""
    if department:
        record["部门"] = department

    # 日期字段:有值才写入(飞书日期字段不接受 None/空)
    if deadline_ms:
        record["投递截止日期"] = deadline_ms
    if created_ms:
        record["抓取日期"] = created_ms
    if publish_ms:
        record["发布时间"] = pos.get("publish_time", "") or ""

    return record


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
                "position_title": pos.get("position_title", ""),
                "company": pos.get("company_name", ""),
                "company_name": pos.get("company_name", ""),
                "company_tier": pos.get("company_tier", ""),
                "jd_text": pos.get("jd_summary", ""),
                "jd_summary": pos.get("jd_summary", ""),
                "industry": pos.get("industry", ""),
                "company_type": pos.get("company_type", ""),
                "difficulty": pos.get("difficulty", ""),
                "department": pos.get("department", ""),
                "location": pos.get("location", ""),
                "city": pos.get("city", "") or pos.get("location", ""),
                "salary": "",
                "jd_url": apply_url,
                "posted": pos.get("publish_time", ""),
                # 评分引擎依赖的岗位侧关键词与分类字段(必须透传,否则 skill/role 维度为 0)
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
            try:
                result = score_job(job_for_score, self.profile, llm_client=self.llm)
                scored.append({**pos, **result})
            except Exception as e:
                logger.warning(f"评分失败 [{pos.get('company_name')}]: {e}")
                scored.append({**pos, "相关性评分": 50, "综合推荐度": "可申请",
                               "匹配理由": [], "维度分": {}, "硬门槛通过": True,
                               "方向门槛触发": [], "竞争力信息": {}})

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
        limited = self._limit_per_company(scored, max_per_company)

        # 6. 字段映射:DB 列名 → 飞书 JOB_FIELDS 中文 schema(含 去重hash)
        #    分离 pos 字段与 scorer 字段后交给 to_feishu_job_record
        feishu_records = []
        scorer_keys = {"相关性评分", "综合推荐度", "匹配理由", "维度分",
                       "硬门槛通过", "方向门槛触发", "竞争力信息"}
        for j in limited:
            score_result = {k: v for k, v in j.items() if k in scorer_keys}
            pos = {k: v for k, v in j.items() if k not in scorer_keys}
            feishu_records.append(to_feishu_job_record(pos, score_result))

        logger.info(f"输出飞书记录: {len(feishu_records)} 条")
        return feishu_records


def match_jobs_for_user(profile: UserProfile, llm_client=None,
                        max_per_company: int = 5) -> List[Dict]:
    """便捷函数:为校招用户匹配岗位"""
    matcher = UserMatcher(profile, llm_client=llm_client)
    return matcher.match(max_per_company=max_per_company)
