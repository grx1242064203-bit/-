"""
全量数据处理管线 — 循环执行: 抓取 → VL+拆岗 → 公司评级。
每批 100 条,直到无待处理公告。后台运行,监控看板实时查看进度。
"""
import logging
import os
import sys
import time

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "data", "full_pipeline.log")),
    ],
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 100
CRAWL_WORKERS = 5  # 多线程抓取提速,Tikhub 可承受
FEISHU_SYNC_INTERVAL = 5  # 每 5 轮同步一次飞书(避免 API 限流)


def run_once(batch: int = BATCH_SIZE) -> dict:
    """执行一轮:抓取→拆岗→评级。返回各阶段统计。"""
    from content_fetcher import fetch_announcement_contents
    from llm_enricher import run_enrichment
    import rate_company_tier

    result = {"crawl": {}, "enrich": {}, "rate": {}}

    # 1. 抓取正文
    try:
        result["crawl"] = fetch_announcement_contents(limit=batch, workers=CRAWL_WORKERS)
        logger.info(f"[抓取] {result['crawl']}")
    except Exception as e:
        logger.error(f"[抓取] 失败: {e}")
        result["crawl"] = {"error": str(e)}

    # 2. LLM 拆岗(含 VL),5 并发
    try:
        result["enrich"] = run_enrichment(limit=batch, max_workers=5)
        logger.info(f"[拆岗] {result['enrich']}")
    except Exception as e:
        logger.error(f"[拆岗] 失败: {e}")
        result["enrich"] = {"error": str(e)}

    # 3. 公司评级(增量)
    try:
        result["rate"] = {"rated": 0}
        # 复用 rate_company_tier 的逻辑,但只跑未评级的
        companies = rate_company_tier.fetch_companies()
        todo = [c for c in companies if not rate_company_tier._load_cached(c["id"])]
        if todo:
            from llm_client import LLMClient
            llm = LLMClient()
            rated = 0
            for i in range(0, len(todo), rate_company_tier.BATCH_SIZE):
                b = todo[i:i + rate_company_tier.BATCH_SIZE]
                try:
                    r = rate_company_tier.batch_rate(llm, b)
                    for cid, tier in r.items():
                        rate_company_tier.update_positions(cid, tier)
                    rated += len(r)
                except Exception as e:
                    logger.warning(f"[评级] 批次失败: {e}")
                time.sleep(0.5)
            result["rate"] = {"rated": rated, "total": len(todo)}
            logger.info(f"[评级] {result['rate']}")
        else:
            logger.info("[评级] 无新公司待评级")
    except Exception as e:
        logger.error(f"[评级] 失败: {e}")
        result["rate"] = {"error": str(e)}

    return result


def has_pending() -> bool:
    """检查是否还有待抓取或待拆岗的公告。"""
    import sqlite3
    from config import settings
    conn = sqlite3.connect(os.path.join(settings.DATA_DIR, "jobs.db"))
    try:
        crawl_pending = conn.execute(
            "SELECT COUNT(*) FROM announcements WHERE crawl_status != 'success' OR crawl_status IS NULL"
        ).fetchone()[0]
        llm_pending = conn.execute(
            "SELECT COUNT(*) FROM announcements WHERE (llm_status NOT IN ('success','skipped') OR llm_status IS NULL) AND crawl_status='success'"
        ).fetchone()[0]
        return crawl_pending > 0 or llm_pending > 0
    finally:
        conn.close()


def main():
    logger.info("=" * 60)
    logger.info("全量数据处理管线启动")
    logger.info("=" * 60)

    from git_persist import git_commit_and_push

    round_no = 0
    while has_pending():
        round_no += 1
        logger.info(f"--- 第 {round_no} 轮开始 ---")
        t0 = time.time()
        run_once(BATCH_SIZE)
        elapsed = time.time() - t0
        logger.info(f"--- 第 {round_no} 轮完成,耗时 {elapsed:.0f}s ---")

        # 防护1: 每轮自动 git commit + push(数据持久化)
        try:
            git_commit_and_push(message=f"auto: round {round_no} snapshot")
        except Exception as e:
            logger.warning(f"[git] 自动持久化失败: {e}")

        # 防护2: 每 N 轮同步到飞书(异地备份)
        if round_no % FEISHU_SYNC_INTERVAL == 0:
            try:
                from sync_to_feishu import sync_all
                sync_all()
            except Exception as e:
                logger.warning(f"[飞书同步] 失败: {e}")

        # 短暂休息,避免 API 限流
        time.sleep(2)

    # 最终持久化
    try:
        git_commit_and_push(message="auto: final snapshot")
    except Exception as e:
        logger.warning(f"[git] 最终持久化失败: {e}")

    logger.info("=" * 60)
    logger.info("全量处理完成!无待处理公告。")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
