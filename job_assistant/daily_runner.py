"""
中心化数据管线执行器 — 每日定时拉取飞书源表 → 抓正文 → LLM 拆岗 → 回写飞书总表。

架构(V4 简化后,飞书机器人/用户分发已下线):
1. 飞书源表增量同步 → companies + announcements
2. Playwright 正文抓取 → 更新 crawl_status
3. LLM 岗位拆分 → positions 表
4. 同步到飞书总表「27届校招汇总表」(base J8qtbBvPdatotysARtbc2XcinDJ)

设计原则:
- 中心化管线每日执行一次,产物被 job_api (FastAPI) 读取供桌面端消费
- 任意阶段失败不阻塞其他阶段,错误记入 result 返回
- 飞书侧仅保留"源表读取 + 总表回写"两个职责,不再有用户级飞书表/机器人推送
"""
import logging
from typing import Dict

logger = logging.getLogger(__name__)


def run_daily_pipeline(sync_full: bool = False, crawl_limit: int = 200,
                       enrich_limit: int = 200, crawl_workers: int = 1) -> Dict:
    """
    中心化数据管线(每日执行一次):
    1. 飞书源表增量同步 → companies + announcements
    2. Playwright 正文抓取 → 更新 crawl_status
    3. LLM 岗位拆分 → positions 表
    4. 同步到飞书总表「27届校招汇总表」

    Args:
        sync_full: True=全量同步(首次或周一校验), False=增量
        crawl_limit: 本次抓取正文上限
        enrich_limit: 本次 LLM 拆岗上限
        crawl_workers: 正文抓取并发数

    Returns: 各阶段统计 {sync, crawl, enrich, master_sync}
    """
    import job_db
    from feishu_source import FeishuSourceSync
    from content_fetcher import fetch_announcement_contents
    from llm_enricher import run_enrichment
    from feishu_master_tables import sync_to_existing_master_table

    job_db.init_db()
    result = {"sync": {}, "crawl": {}, "enrich": {}, "master_sync": {}}

    # 1. 飞书源表同步
    try:
        syncer = FeishuSourceSync()
        result["sync"] = syncer.sync(full=sync_full)
        logger.info(f"源表同步完成: {result['sync']}")
    except Exception as e:
        logger.error(f"源表同步失败: {e}")
        result["sync"] = {"error": str(e)}

    # 2. 正文抓取
    try:
        result["crawl"] = fetch_announcement_contents(
            limit=crawl_limit, workers=crawl_workers)
        logger.info(f"正文抓取完成: {result['crawl']}")
    except Exception as e:
        logger.error(f"正文抓取失败: {e}")
        result["crawl"] = {"error": str(e)}

    # 3. LLM 岗位拆分
    try:
        result["enrich"] = run_enrichment(limit=enrich_limit)
        logger.info(f"LLM 拆岗完成: {result['enrich']}")
    except Exception as e:
        logger.error(f"LLM 拆岗失败: {e}")
        result["enrich"] = {"error": str(e)}

    # 4. 同步到飞书总表(公司+岗位),写入「27届校招汇总表」
    try:
        result["master_sync"] = sync_to_existing_master_table()
        logger.info(f"飞书总表同步完成: {result['master_sync']}")
    except Exception as e:
        logger.error(f"飞书总表同步失败: {e}")
        result["master_sync"] = {"error": str(e)}

    return result
