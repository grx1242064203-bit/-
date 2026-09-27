"""
两阶段批量处理主入口:先抓取(阶段一),再分析(阶段二),定期同步服务器。

运行: nohup python3 run_two_stage.py > two_stage.log 2>&1 &
"""
import os
import sys
import time
import logging
import subprocess

os.environ["DATA_DIR"] = "/workspace/job_assistant/data"
os.environ["DEEPSEEK_API_KEY"] = "sk-b62b83d5c36d4e6aa87925c8b66b4ab3"
sys.path.insert(0, "/workspace/job_assistant")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("/workspace/job_assistant/two_stage.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

WORKERS = 5  # 阶段一并发数
SYNC_INTERVAL = 300  # 每 5 分钟同步一次服务器


def sync_to_server():
    try:
        subprocess.run(
            ["scp", "/workspace/job_assistant/data/jobs.db",
             "prod:/opt/job_assistant/data/jobs.db"],
            check=True, timeout=60,
        )
        logger.info("数据库已同步到服务器")
    except Exception as e:
        logger.error(f"同步到服务器失败: {e}")


def get_unanalyzed_count():
    import sqlite3
    conn = sqlite3.connect("/workspace/job_assistant/data/jobs.db")
    r = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE detail_analyzed = 0 AND link_valid = 1"
    ).fetchone()
    conn.close()
    return r[0]


def main():
    logger.info("=" * 60)
    logger.info("两阶段批量处理启动")
    logger.info("=" * 60)

    remaining = get_unanalyzed_count()
    logger.info(f"初始待分析: {remaining} 条")

    # ===== 阶段一:抓取 =====
    logger.info("\n>>> 阶段一:并发抓取公告")
    t0 = time.time()
    ret = subprocess.run(
        [sys.executable, "/workspace/job_assistant/fetch_announcements.py",
         "--workers", str(WORKERS)],
        cwd="/workspace/job_assistant",
    )
    logger.info(f"阶段一完成,耗时 {time.time()-t0:.0f}s,返回码 {ret.returncode}")

    # ===== 阶段二:分析 =====
    logger.info("\n>>> 阶段二:批量分析公告")
    t0 = time.time()
    ret = subprocess.run(
        [sys.executable, "/workspace/job_assistant/analyze_announcements.py"],
        cwd="/workspace/job_assistant",
    )
    logger.info(f"阶段二完成,耗时 {time.time()-t0:.0f}s,返回码 {ret.returncode}")

    # 最终同步
    sync_to_server()

    remaining = get_unanalyzed_count()
    logger.info(f"\n两阶段处理结束,剩余待分析: {remaining} 条")


if __name__ == "__main__":
    main()
