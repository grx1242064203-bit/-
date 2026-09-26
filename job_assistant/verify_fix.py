#!/usr/bin/env python3
"""
生产环境验证脚本 — 验证 91402 NOTEXIST 修复是否生效。

使用方式(在生产服务器上执行):
    cd /opt/job_assistant
    source venv/bin/activate
    python verify_fix.py

验证项:
1. resolve_app_token 能正确解析 wiki node_token
2. 存量用户的 base_token 能被迁移(若为 wiki node_token)
3. 单用户每日任务能正常写入飞书表格
"""
import sys
import os
import json
import logging

# 加载 .env
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def step1_check_credentials():
    """检查飞书凭证是否配置"""
    app_id = os.getenv("FEISHU_APP_ID", "")
    app_secret = os.getenv("FEISHU_APP_SECRET", "")
    if not app_id or not app_secret:
        logger.error("FEISHU_APP_ID 或 FEISHU_APP_SECRET 未配置")
        return False
    logger.info(f"飞书凭证已配置: App ID = {app_id[:8]}...")
    return True


def step2_test_token_resolution():
    """测试 resolve_app_token 能正确解析 wiki node_token"""
    from feishu_client import FeishuClient

    client = FeishuClient()

    # 用一个已知的用户 base_token 测试(如果有)
    from models import UserStore
    store = UserStore()
    users_with_token = [u for u in store._users.values() if u.feishu_base_token]

    if not users_with_token:
        logger.warning("没有已配置 base_token 的用户,跳过 token 解析测试")
        return True

    user = users_with_token[0]
    logger.info(f"测试用户 {user.id} 的 base_token 解析: {user.feishu_base_token}")

    resolved = client.resolve_app_token(user.feishu_base_token)
    if resolved == user.feishu_base_token:
        logger.info("token 非 wiki node_token,无需解析(或解析后相同)")
    else:
        logger.info(f"token 已从 wiki node_token 解析为 obj_token: {resolved}")

    # 验证解析后的 token 能访问
    try:
        tables = client.list_tables(resolved)
        logger.info(f"token 验证通过,多维表格下有 {len(tables)} 张表")
        return True
    except RuntimeError as e:
        logger.error(f"token 验证失败: {e}")
        return False


def step3_migrate_tokens():
    """执行 token 迁移"""
    from onboarding import migrate_user_tokens

    logger.info("执行存量用户 token 迁移...")
    summary = migrate_user_tokens()
    logger.info(f"迁移结果: {json.dumps(summary, ensure_ascii=False)}")
    return len(summary.get("failed", [])) == 0


def step4_test_daily_run():
    """测试单用户每日任务(写入飞书表格)"""
    from models import UserStore
    from daily_runner import DailyRunner

    store = UserStore()
    active_users = store.list_active()

    if not active_users:
        logger.warning("没有活跃用户,跳过每日任务测试")
        return True

    user = active_users[0]
    if not user.feishu_base_token or not user.feishu_table_id:
        logger.warning(f"用户 {user.id} 未配置飞书表格,跳过每日任务测试")
        return True

    logger.info(f"测试用户 {user.id} 的每日任务...")
    try:
        runner = DailyRunner(user)
        result = runner.run()
        logger.info(f"每日任务结果: {json.dumps(result, ensure_ascii=False, default=str)[:500]}")
        if result.get("errors"):
            logger.error(f"每日任务有错误: {result['errors']}")
            return False
        logger.info("每日任务执行成功")
        return True
    except Exception as e:
        logger.exception(f"每日任务异常: {e}")
        return False


def main():
    logger.info("=" * 60)
    logger.info("招聘情报助手 — 91402 修复验证脚本")
    logger.info("=" * 60)

    results = {}

    steps = [
        ("凭证检查", step1_check_credentials),
        ("token 解析测试", step2_test_token_resolution),
        ("token 迁移", step3_migrate_tokens),
        ("每日任务测试", step4_test_daily_run),
    ]

    for name, func in steps:
        logger.info(f"\n--- 步骤: {name} ---")
        try:
            ok = func()
            results[name] = "PASS" if ok else "FAIL"
        except Exception as e:
            logger.exception(f"步骤异常: {e}")
            results[name] = "ERROR"

    logger.info("\n" + "=" * 60)
    logger.info("验证结果汇总:")
    all_pass = True
    for name, status in results.items():
        logger.info(f"  {name}: {status}")
        if status != "PASS":
            all_pass = False

    if all_pass:
        logger.info("\n✅ 所有验证通过!91402 修复已生效。")
        sys.exit(0)
    else:
        logger.error("\n❌ 部分验证未通过,请检查上方日志。")
        sys.exit(1)


if __name__ == "__main__":
    main()
