"""
批量岗位分析脚本 — 持续运行,每批处理 50 条,自动同步到服务器。

运行方式: nohup python3 batch_analyze.py > batch_analyze.log 2>&1 &
"""
import os
import sys
import time
import logging
import subprocess

# 设置环境变量
os.environ["DATA_DIR"] = "/workspace/job_assistant/data"
os.environ["DEEPSEEK_API_KEY"] = "sk-b62b83d5c36d4e6aa87925c8b66b4ab3"

sys.path.insert(0, "/workspace/job_assistant")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("/workspace/job_assistant/batch_analyze.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

import job_db
job_db.init_db()
from job_detail_analyzer import run_analysis

BATCH_SIZE = 50
MAX_BATCHES = 120  # 最多处理 120 批 = 6000 条

def sync_to_server():
    """把本地数据库同步到服务器"""
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
    r = conn.execute("SELECT COUNT(*) FROM jobs WHERE detail_analyzed = 0 AND link_valid = 1").fetchone()
    conn.close()
    return r[0]

def main():
    logger.info("=" * 60)
    logger.info("批量岗位分析启动")
    logger.info(f"每批 {BATCH_SIZE} 条, 最多 {MAX_BATCHES} 批")
    logger.info("=" * 60)

    for batch_num in range(1, MAX_BATCHES + 1):
        remaining = get_unanalyzed_count()
        logger.info(f"\n--- 第 {batch_num} 批开始, 剩余待分析: {remaining} 条 ---")

        if remaining == 0:
            logger.info("所有岗位已分析完成!")
            break

        try:
            stats = run_analysis(batch_size=BATCH_SIZE)
            logger.info(f"第 {batch_num} 批完成: {stats}")
        except Exception as e:
            logger.exception(f"第 {batch_num} 批出错: {e}")

        # 每批结束后同步到服务器
        sync_to_server()

        # 短暂休息
        time.sleep(2)

    logger.info("\n批量分析结束")
    sync_to_server()

if __name__ == "__main__":
    main()
