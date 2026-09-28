"""
LLM 岗位拆分器 — 从招聘公告正文用 DeepSeek 提取结构化岗位列表。

设计原则(对抗性审查):
1. LLM 唯一职责:公告正文 → 岗位列表(非结构化→结构化)
2. 缓存:内容 hash → LLM 结果文件,避免重复调用(成本控制)
3. 增量:只处理 crawl_status=success 且 llm_status=pending 的公告
4. 降级:LLM 失败时用公告标题作为单一岗位,不阻塞管线
5. 限速 + 重试上限 3 次,控制成本

数据流:
  announcement(crawl_status=success) → 读缓存正文
  → DeepSeek 拆岗 → 写 positions 表 → 更新 llm_status=success
"""
import hashlib
import json
import logging
import os
import time
from typing import Dict, List, Optional

from config import settings
from llm_client import LLMClient
import job_db
from content_fetcher import get_cached_content, fetch_content

logger = logging.getLogger(__name__)

LLM_CACHE_DIR = os.path.join(settings.DATA_DIR, "llm_cache")
MAX_RETRIES = 3
API_INTERVAL = 1.0  # 秒,LLM 调用间隔(控成本+避限流)

POSITION_EXTRACT_PROMPT = """你是校招信息解析专家。请从以下招聘公告正文中提取所有可独立投递的具体岗位信息。

公司: {company}
公告标题: {title}

公告正文:
\"\"\"{content}\"\"\"

请输出 JSON 数组(不要输出任何 JSON 以外的文字):
[
  {{
    "position_title": "岗位名称(如:产品经理/Java开发工程师/管培生)",
    "department": "部门或条线(如:技术中台/零售金融,无法确定则空字符串)",
    "location": "工作地点(如:北京/上海,多个用逗号分隔,无明确地点则空)",
    "education_req": "学历要求(本科/硕士/博士/大专/不限,取最高要求)",
    "major_req": "专业要求(如:计算机/金融相关/不限,提取关键专业方向)",
    "jd_summary": "该岗位的职责与要求摘要(80字内)",
    "is_management_trainee": false,
    "difficulty": "难度评估(最激烈/较为激烈/中等难度/较低难度)",
    "apply_url": "该岗位独立投递链接(无则空字符串)"
  }}
]

提取要求:
1. 识别公告中所有可独立投递的具体岗位(管培/技术/产品/运营/职能/金融等)
2. position_title 必须是具体岗位名,不要用"XX集团2027秋招"这种公告标题
3. 若公告只笼统面向各专业无具体岗位名,提取为1条 position_title="通用校招岗"
4. is_management_trainee: 管培生/管理培训生/MT/Management Trainee 标记为 true
5. difficulty: 头部互联网/金融/知名外企=最激烈;中型公司=较为激烈;普通企业=中等难度;冷门=较低难度
6. apply_url: 仅当公告中有该岗位独立投递链接时填写,否则空字符串(统一用公告网申链接)
7. 缺失字段填空字符串或 false,不要编造信息
"""


def _content_hash(content: str) -> str:
    """计算内容 hash,作为 LLM 缓存键。"""
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def _llm_cache_path(content_hash: str) -> str:
    return os.path.join(LLM_CACHE_DIR, f"{content_hash}.json")


def _get_cached_llm_result(content_hash: str) -> Optional[List[Dict]]:
    """读取 LLM 结果缓存。"""
    path = _llm_cache_path(content_hash)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _save_llm_result(content_hash: str, positions: List[Dict]):
    """缓存 LLM 结果。"""
    os.makedirs(LLM_CACHE_DIR, exist_ok=True)
    try:
        with open(_llm_cache_path(content_hash), "w", encoding="utf-8") as f:
            json.dump(positions, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"LLM 结果缓存失败: {e}")


class PositionEnricher:
    """LLM 岗位拆分器。"""

    def __init__(self, llm_client: LLMClient = None):
        self.llm = llm_client or LLMClient()

    def extract_positions(self, content: str, company: str = "",
                          title: str = "") -> List[Dict]:
        """
        从公告正文用 LLM 提取岗位列表。
        带缓存:相同内容 hash 不重复调用。
        失败返回空列表(由调用方降级处理)。
        """
        if not content or len(content.strip()) < 30:
            return []

        c_hash = _content_hash(content)

        # 1. 查缓存
        cached = _get_cached_llm_result(c_hash)
        if cached is not None:
            logger.debug(f"LLM 缓存命中: {company} ({len(cached)} 岗位)")
            return cached

        # 2. 调用 LLM(带重试)
        prompt = POSITION_EXTRACT_PROMPT.format(
            company=company or "未知",
            title=title or "",
            content=content[:4000],  # 截断控制成本
        )

        for attempt in range(MAX_RETRIES):
            try:
                result_text = self.llm._chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.1, max_tokens=2000,
                )
                if not result_text:
                    raise ValueError("LLM 返回空")

                positions = self._parse_positions(result_text)
                if positions:
                    _save_llm_result(c_hash, positions)
                    return positions
                # 解析为空,可能是 LLM 输出异常,重试
                logger.warning(f"LLM 输出解析为空(尝试 {attempt + 1}): {result_text[:200]}")
            except Exception as e:
                logger.warning(f"LLM 拆岗失败(尝试 {attempt + 1}/{MAX_RETRIES}) [{company}]: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                else:
                    logger.error(f"LLM 拆岗彻底失败 [{company}]")
                    return []

        return []

    @staticmethod
    def _parse_positions(text: str) -> List[Dict]:
        """解析 LLM 输出为岗位列表。"""
        if not text:
            return []
        text = text.strip()
        # 去除 markdown 包裹
        import re
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        # 找 JSON 数组
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end < start:
            # 尝试单对象 {}
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1:
                return []
            try:
                obj = json.loads(text[start:end + 1])
                return [obj] if isinstance(obj, dict) else []
            except json.JSONDecodeError:
                return []
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
            if isinstance(data, dict):
                return [data]
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败: {e}")
            return []
        return []

    def _degrade_to_single_position(self, announcement: Dict) -> List[Dict]:
        """
        降级:LLM 失败时,用公告标题作为单一岗位。
        保证管线不中断,后续可重试 LLM。
        """
        title = announcement.get("announcement_title", "") or "通用校招岗"
        return [{
            "position_title": title.strip()[:100] or "通用校招岗",
            "department": "",
            "location": announcement.get("location", ""),
            "education_req": announcement.get("education_req", ""),
            "major_req": "",
            "jd_summary": "",
            "is_management_trainee": False,
            "difficulty": "",
            "apply_url": announcement.get("apply_url", ""),
        }]

    def enrich_announcement(self, announcement: Dict) -> int:
        """
        处理单条公告:抓正文 → LLM 拆岗 → 写 positions → 更新状态。
        返回插入的岗位数。
        """
        ann_id = announcement["id"]
        company_name = announcement.get("company_name", "")
        ann_title = announcement.get("announcement_title", "")
        ann_url = announcement.get("announcement_url", "")

        # 1. 获取正文(优先缓存)
        content = get_cached_content(ann_url) or ""
        if not content:
            content = fetch_content(ann_url)

        # 对抗性优化:微信公众号反爬严重,正文常抓不到。
        # 但飞书源表的公告标题本身已包含岗位列表(如"投行经理助理,债券承做助理..."),
        # 因此正文为空时用标题作为 LLM 输入,仍可拆出岗位。
        if not content or len(content) < 30:
            logger.info(f"公告 {ann_id} [{company_name}] 正文缺失,用标题拆岗")
            content = ann_title  # 用标题作为拆岗输入

        # 2. LLM 拆岗
        positions = self.extract_positions(content, company=company_name, title=ann_title)
        c_hash = _content_hash(content)

        if not positions:
            # LLM 失败,降级
            positions = self._degrade_to_single_position(announcement)
            job_db.insert_positions(
                ann_id, announcement["company_id"], company_name,
                positions, source_url=ann_url,
            )
            job_db.update_llm_status(ann_id, "skipped", positions_count=len(positions),
                                     cache_hash="degraded")
            logger.warning(f"公告 {ann_id} [{company_name}] LLM 拆岗失败,降级")
            return len(positions)

        # 3. 写 positions 表
        # 补充投递链接(岗位无独立链接时用公告链接)
        ann_apply_url = announcement.get("apply_url", "")
        for pos in positions:
            if not pos.get("apply_url") and ann_apply_url:
                pos["apply_url"] = ann_apply_url

        inserted = job_db.insert_positions(
            ann_id, announcement["company_id"], company_name,
            positions, source_url=ann_url,
        )
        job_db.update_llm_status(ann_id, "success", positions_count=inserted,
                                 cache_hash=c_hash)
        logger.info(f"公告 {ann_id} [{company_name}] 拆出 {inserted} 个岗位")
        return inserted

    def run(self, limit: int = 100) -> Dict:
        """
        批量处理待 LLM 拆岗的公告。
        limit=100 用于试跑验证(首次全量前先验证效果)。

        Returns: {"total": N, "success": M, "degraded": K, "failed": L}
        """
        announcements = job_db.get_announcements_for_llm(limit=limit)
        total = len(announcements)
        success = 0
        degraded = 0
        failed = 0

        for ann in announcements:
            try:
                count = self.enrich_announcement(ann)
                if count > 0:
                    # 判断是成功还是降级
                    ann_after = job_db.get_announcement_by_id(ann["id"])
                    if ann_after and ann_after.get("llm_status") == "success":
                        success += 1
                    else:
                        degraded += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"公告 {ann['id']} 处理异常: {e}")
                job_db.update_llm_status(ann["id"], "failed", error=str(e)[:200])
                failed += 1
            time.sleep(API_INTERVAL)

        logger.info(
            f"LLM 拆岗完成: 总计={total} 成功={success} 降级={degraded} 失败={failed}"
        )
        return {"total": total, "success": success, "degraded": degraded, "failed": failed}


def run_enrichment(limit: int = 100) -> Dict:
    """便捷函数:批量 LLM 拆岗。limit 默认 100(试跑验证)。"""
    enricher = PositionEnricher()
    return enricher.run(limit=limit)
