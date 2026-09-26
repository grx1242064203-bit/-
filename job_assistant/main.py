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
import os

# 加载 .env 文件(不依赖 python-dotenv)
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            _k = _k.strip()
            _v = _v.strip().strip('"').strip("'")
            if _k and _k not in os.environ:
                os.environ[_k] = _v

from models import UserStore
from daily_runner import DailyRunner
from onboarding import migrate_user_tokens
from wxpusher_client import WxPusherClient
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _alert_admin(summary: dict, results: list):
    """每日任务有失败时,向管理员推送告警(需配置 ADMIN_WXPUSHER_UID)。"""
    failed = summary.get("failed", 0)
    if failed <= 0:
        return
    admin_uid = settings.ADMIN_WXPUSHER_UID
    if not admin_uid:
        logger.warning(f"每日任务有 {failed} 个用户失败,但未配置 ADMIN_WXPUSHER_UID,跳过告警推送")
        return
    failed_users = [r for r in results if r.get("errors")]
    detail_lines = []
    for r in failed_users[:10]:
        errs = "; ".join(r.get("errors", []))[:100]
        detail_lines.append(f"- {r.get('user_id')}: {errs}")
    content = (
        f"## ⚠️ 招聘情报助手每日任务告警\n\n"
        f"**失败用户数: {failed} / {summary.get('total_users', 0)}**\n\n"
        + "\n".join(detail_lines)
        + (f"\n\n_仅显示前 10 条,共 {len(failed_users)} 条_" if len(failed_users) > 10 else "")
    )
    try:
        ok = WxPusherClient().send(admin_uid, content)
        if ok:
            logger.info(f"已向管理员推送失败告警: {failed} 个用户失败")
        else:
            logger.error("管理员告警推送失败")
    except Exception as e:
        logger.exception(f"管理员告警推送异常: {e}")


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

    # 失败告警:有用户失败时推送给管理员
    _alert_admin(summary, results)

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


def run_migrate_tokens():
    """将所有用户的 wiki node_token 解析为真实 obj_token"""
    summary = migrate_user_tokens()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def run_weekly_ranking():
    """执行每周校招投递热度榜"""
    from weekly_rankings import run_weekly_ranking
    run_weekly_ranking()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python main.py [daily|single <user_id>|migrate-tokens|weekly-ranking]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "daily":
        run_daily_all()
    elif cmd == "single" and len(sys.argv) > 2:
        run_single(sys.argv[2])
    elif cmd == "migrate-tokens":
        run_migrate_tokens()
    elif cmd == "weekly-ranking":
        run_weekly_ranking()
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)
