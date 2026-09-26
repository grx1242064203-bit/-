"""
为测试用户 u1 创建飞书多维表格并写入 users.json。

用途: u1 是手动创建的测试用户,未经过飞书应用安装回调,
缺少 feishu_base_token / feishu_table_id / feishu_closed_table_id。
此脚本用应用身份(tenant_access_token)为 u1 创建专属多维表格,
跳过所有权转移(u1 无 feishu_open_id),仅创建表结构。

用法:
    venv/bin/python3 onboard_user_u1.py
"""
import json
import os
import sys
import time

# 加载 .env
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

from models import UserStore, User
from onboarding import setup_user_feishu

USER_ID = "u1"


def main():
    store = UserStore()
    user = store.get(USER_ID)
    if not user:
        print(f"❌ 用户 {USER_ID} 不存在")
        sys.exit(1)

    if user.feishu_base_token and user.feishu_table_id:
        print(f"用户 {USER_ID} 已有飞书配置,跳过创建")
        print(f"  base_token: {user.feishu_base_token}")
        print(f"  table_id: {user.feishu_table_id}")
        return

    print(f"开始为用户 {USER_ID} 创建飞书多维表格...")

    # u1 无 feishu_open_id,传空字符串(setup_user_feishu 中 transfer_owner 会失败但被捕获)
    feishu_info = setup_user_feishu(
        tenant_key="",
        open_id="",
    )

    user.feishu_base_token = feishu_info["base_token"]
    user.feishu_table_id = feishu_info["table_id"]
    user.feishu_closed_table_id = feishu_info["closed_table_id"]
    store.upsert(user)

    print(f"✅ 用户 {USER_ID} onboarding 完成")
    print(f"  base_token: {user.feishu_base_token}")
    print(f"  table_id: {user.feishu_table_id}")
    print(f"  closed_table_id: {user.feishu_closed_table_id}")
    print(f"\n⚠️ 注意: u1 无 feishu_open_id,多维表格所有权未转移给用户。")
    print(f"   如需用户访问,请在飞书中手动分享该多维表格。")


if __name__ == "__main__":
    main()
