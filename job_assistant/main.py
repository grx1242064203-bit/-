"""
调度器 — 遍历所有活跃用户,执行每日任务。

部署方式二选一:
1. 系统 cron: 0 9 * * * cd /path && python3 main.py daily
2. 云函数定时触发器(阿里云/腾讯云函数)
"""
import logging
import sys
import json
import time

from models import UserStore
from daily_runner import DailyRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run_daily_all():
    """为所有活跃用户执行每日任务"""
    store = UserStore()
    users = store.list_active()
    logger.info(f"开始每日任务,活跃用户数: {len(users)}")

    results = []
    for user in users:
        logger.info(f"处理用户: {user.id}")
        try:
            runner = DailyRunner(user)
            result = runner.run()
            results.append(result)
            logger.info(
                f"用户 {user.id} 完成: 新增{result['new_jobs']}条 "
                f"关闭{result['closed_jobs']}条 推送{'成功' if result['push_ok'] else '失败'}"
            )
        except Exception as e:
            logger.exception(f"用户 {user.id} 任务异常")
            results.append({"user_id": user.id, "errors": [str(e)]})
        # 用户间间隔,避免限流
        time.sleep(1)

    summary = {
        "total_users": len(users),
        "success": sum(1 for r in results if not r.get("errors")),
        "failed": sum(1 for r in results if r.get("errors")),
        "total_new_jobs": sum(r.get("new_jobs", 0) for r in results),
        "total_closed": sum(r.get("closed_jobs", 0) for r in results),
    }
    logger.info(f"每日任务结束: {json.dumps(summary, ensure_ascii=False)}")
    return summary


def run_single(user_id: str):
    """为单个用户执行(测试用)"""
    store = UserStore()
    user = store.get(user_id)
    if not user:
        logger.error(f"用户不存在: {user_id}")
        return
    runner = DailyRunner(user)
    result = runner.run()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python main.py [daily|single <user_id>]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "daily":
        run_daily_all()
    elif cmd == "single" and len(sys.argv) > 2:
        run_single(sys.argv[2])
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)
