"""
用户 Onboarding — 新用户安装飞书应用后,为其创建专属多维表格。

流程:
1. 用户安装商店应用 → 飞书回调推送 app_open 事件(含 tenant_key + open_id)
2. 本脚本接收回调,创建用户专属多维表格(岗位数据库 + 已关闭岗位)
3. 分享+转所有权给用户
4. 返回安装完成页(含 WxPusher 绑定二维码 + 背景表单)

注意:飞书商店应用的事件回调需要公网可访问的 HTTPS 地址。
MVP 阶段可用 ngrok/cloudflared 做内网穿透,或用云函数接收回调。
"""
import json
import logging
import time
from typing import Optional

from models import User, UserProfile, UserStore
from feishu_client import FeishuClient
from schema import JOB_FIELDS, CLOSED_JOB_FIELDS

logger = logging.getLogger(__name__)


def setup_user_feishu(tenant_key: str, open_id: str, client: FeishuClient = None) -> dict:
    """
    为用户创建专属飞书空间(多维表格+两个数据表)。
    返回 {base_token, table_id, closed_table_id}
    """
    client = client or FeishuClient()

    # 1. 创建多维表格
    base_token = client.create_bitable("金融招聘情报库")
    logger.info(f"创建多维表格: {base_token}")

    # 2. 创建岗位数据库表
    table_id = client.create_table(base_token, "岗位数据库")
    # 批量创建字段
    for f in JOB_FIELDS:
        kwargs = {}
        if "options" in f:
            kwargs["property"] = {"options": f["options"]}
        if "style" in f:
            kwargs["property"] = {**kwargs.get("property", {}), **f["style"]}
        if "multiple" in f:
            kwargs["property"] = {**kwargs.get("property", {}), "multiple": f["multiple"]}
        client.create_field(base_token, table_id, f["name"], f["type"], **kwargs)
        time.sleep(0.1)

    # 3. 创建已关闭岗位表
    closed_table_id = client.create_table(base_token, "已关闭岗位")
    for f in CLOSED_JOB_FIELDS:
        kwargs = {}
        if "options" in f:
            kwargs["property"] = {"options": f["options"]}
        if "style" in f:
            kwargs["property"] = {**kwargs.get("property", {}), **f["style"]}
        if "multiple" in f:
            kwargs["property"] = {**kwargs.get("property", {}), "multiple": f["multiple"]}
        client.create_field(base_token, closed_table_id, f["name"], f["type"], **kwargs)
        time.sleep(0.1)

    # 4. 分享给用户 + 转所有权
    client.transfer_owner(base_token, "bitable", open_id)

    return {
        "base_token": base_token,
        "table_id": table_id,
        "closed_table_id": closed_table_id,
    }


def onboard_user(user_id: str, tenant_key: str, open_id: str,
                 profile: dict = None, plan: str = "autumn",
                 expire_date: str = "", store: UserStore = None) -> User:
    """
    完整的用户 onboarding:
    1. 检查用户是否已存在
    2. 创建飞书空间
    3. 保存用户配置
    """
    store = store or UserStore()
    existing = store.get(user_id)
    if existing and existing.feishu_base_token:
        logger.info(f"用户 {user_id} 已存在,跳过飞书初始化")
        return existing

    feishu_info = setup_user_feishu(tenant_key, open_id)

    user = User(
        id=user_id,
        feishu_tenant_key=tenant_key,
        feishu_open_id=open_id,
        feishu_base_token=feishu_info["base_token"],
        feishu_table_id=feishu_info["table_id"],
        feishu_closed_table_id=feishu_info["closed_table_id"],
        profile=UserProfile(**(profile or {})),
        plan=plan,
        expire_date=expire_date,
    )
    store.upsert(user)
    logger.info(f"用户 {user_id} onboarding 完成")
    return user


def handle_feishu_callback(body: dict) -> dict:
    """
    处理飞书事件回调(app_open / app_install)。
    飞书会推送 JSON,需要解密(若开启加密)并校验。
    MVP:直接从 body 提取 tenant_key + open_id。
    """
    # 飞书 URL 验证(challenge)
    if "challenge" in body:
        return {"challenge": body["challenge"]}

    event = body.get("event", {})
    tenant_key = event.get("tenant_key", "")
    open_id = event.get("operator", {}).get("open_id", "") or \
              event.get("open_id", "")

    if not tenant_key or not open_id:
        logger.warning(f"回调缺少 tenant_key/open_id: {body}")
        return {"code": 0, "msg": "ignored"}

    # 用 tenant_key+open_id 作为用户 ID
    user_id = f"{tenant_key}_{open_id}"
    onboard_user(user_id, tenant_key, open_id)

    return {"code": 0, "msg": "ok"}
