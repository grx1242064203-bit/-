"""
调度器入口 — V4 简化后已无独立命令。

新方案下:
- 中心化每日管线由 scripts/daily_update.sh 直接调用 daily_runner.run_daily_pipeline
- 飞书源表全量校验由 crontab 直接调用 FeishuSourceSync().sync(full=True)
- 桌面端通过 job_api (FastAPI :8000) 消费数据

本入口保留作为说明文档,无可用命令。如需扩展任务,在此添加。
"""
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    print("Offer搭子 调度入口(V4 简化后无独立命令)")
    print("")
    print("日常任务入口:")
    print("  每日管线:    bash scripts/daily_update.sh")
    print("  源表全量:    python3 -c 'from feishu_source import FeishuSourceSync; FeishuSourceSync().sync(full=True)'")
    print("  桌面端 API:  cd job_api && uvicorn main:app --port 8000")
    print("")
    print("详见 scripts/crontab.example")
    sys.exit(0)
