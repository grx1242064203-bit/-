"""
为测试用户 u1 创建飞书多维表格并写入 users.json。

⚠️ 重要说明(第一性原则审查):
真实 onboarding 流程由飞书 app_open 回调驱动,回调中携带 open_id,
系统据此调用 transfer_owner 将多维表格所有权转给用户。

本脚本用于"无飞书回调"的手动测试场景,u1 没有 feishu_open_id,
因此 transfer_owner 必然失败,多维表格归应用所有。
应用身份(tenant_access_token)仍可读写该表格,但用户无法在飞书中看到。

若需完整验证用户体验,必须走真实 onboarding 流程(在飞书中打开应用)。
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
from feishu_client import FeishuClient

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
        # 验证应用仍可访问该表格
        try:
            client = FeishuClient()
            tables = client.list_tables(user.feishu_base_token)
            print(f"✅ 应用可访问该多维表格,共 {len(tables)} 张表")
        except Exception as e:
            print(f"❌ 应用无法访问该多维表格: {e}")
            print("   可能原因: 表格已被删除 / token 无效 / 应用权限不足")
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

    # 创建后立即验证应用可访问
    try:
        client = FeishuClient()
        tables = client.list_tables(user.feishu_base_token)
        print(f"✅ 多维表格创建并验证通过,共 {len(tables)} 张表")
    except Exception as e:
        print(f"❌ 多维表格创建后无法访问: {e}")

    print(f"\n✅ 用户 {USER_ID} onboarding 完成")
    print(f"  base_token: {user.feishu_base_token}")
    print(f"  table_id: {user.feishu_table_id}")
    print(f"  closed_table_id: {user.feishu_closed_table_id}")
    print(f"\n⚠️ 注意: u1 无 feishu_open_id,多维表格所有权未转移给用户。")
    print(f"   应用身份可读写表格,但用户无法在飞书中查看。")
    print(f"   如需用户访问,请走真实 onboarding 流程(飞书中打开应用)。")


if __name__ == "__main__":
    main()
