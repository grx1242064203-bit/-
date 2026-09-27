"""
并行两阶段批量处理:抓取(阶段一) 和 分析(阶段二) 同时运行。

- 阶段一: fetch_announcements.py (并发 Playwright 抓取,写入 JSONL)
- 阶段二: analyze_daemon.py (持续消费 JSONL,调用 LLM 分析,写入 DB)

两个进程通过 fetch_results.jsonl 解耦,边抓边分析。
"""
import os
import sys
import time
import logging
import subprocess

os.environ["DATA_DIR"] = "/workspace/job_assistant/data"
os.environ["DEEPSEEK_API_KEY"] = "sk-b62b83d5c36d4e6aa87925c8b66b4ab3"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("/workspace/job_assistant/two_stage.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


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


def main():
    logger.info("=" * 60)
    logger.info("并行两阶段批量处理启动")
    logger.info("阶段一(抓取) 和 阶段二(分析) 同时运行")
    logger.info("=" * 60)

    cwd = "/workspace/job_assistant"

    # 启动阶段一:抓取
    logger.info(">>> 启动阶段一:并发抓取")
    fetch_proc = subprocess.Popen(
        [sys.executable, os.path.join(cwd, "fetch_announcements.py"),
         "--workers", "5"],
        cwd=cwd,
    )

    # 等待几秒让抓取先写入一些数据,然后启动阶段二
    time.sleep(3)

    # 启动阶段二:分析守护进程
    logger.info(">>> 启动阶段二:分析守护进程(持续消费)")
    analyze_proc = subprocess.Popen(
        [sys.executable, os.path.join(cwd, "analyze_daemon.py")],
        cwd=cwd,
    )

    # 定期同步数据库 + 监控
    sync_interval = 600  # 每 10 分钟同步一次
    last_sync = time.time()

    try:
        while True:
            fetch_alive = fetch_proc.poll() is None
            analyze_alive = analyze_proc.poll() is None

            if not fetch_alive:
                logger.info(f"阶段一已结束 (returncode={fetch_proc.returncode})")
            if not analyze_alive:
                logger.info(f"阶段二已结束 (returncode={analyze_proc.returncode})")

            # 两个都结束就退出
            if not fetch_alive and not analyze_alive:
                logger.info("两个阶段都已结束")
                break

            # 定期同步
            if time.time() - last_sync > sync_interval:
                sync_to_server()
                last_sync = time.time()

            time.sleep(10)
    except KeyboardInterrupt:
        logger.info("收到中断信号,终止子进程...")
        fetch_proc.terminate()
        analyze_proc.terminate()
        fetch_proc.wait()
        analyze_proc.wait()

    # 最终同步
    sync_to_server()
    logger.info("并行两阶段处理结束")


if __name__ == "__main__":
    main()
