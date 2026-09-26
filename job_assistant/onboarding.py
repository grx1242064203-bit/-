"""
用户 Onboarding — 新用户安装飞书应用后,为其创建专属多维表格。

流程:
1. 用户安装商店应用 → 飞书回调推送 app_open 事件(含 tenant_key + open_id)
2. 本脚本接收回调,创建用户专属多维表格(岗位数据库 + 已关闭岗位)
3. 分享+转所有权给用户
4. 返回安装完成页(配置求职偏好,支持简历智能解析)

注意:飞书商店应用的事件回调需要公网可访问的 HTTPS 地址。
MVP 阶段可用 ngrok/cloudflared 做内网穿透,或用云函数接收回调。
"""
import json
import logging
import time
import threading
from typing import Optional

from models import User, UserProfile, UserStore
from feishu_client import FeishuClient
from schema import JOB_FIELDS, CLOSED_JOB_FIELDS
from config import settings

logger = logging.getLogger(__name__)

# onboarding 全局锁，防止并发回调创建多个多维表格（竞态条件）
_onboarding_lock = threading.Lock()


def _create_optimized_views(client: FeishuClient, base_token: str, table_id: str):
    """
    创建多维表格优化视图:
    1. 按推荐度排序(相关性评分降序)
    2. 按城市筛选(每个目标城市一个视图)

    视图属性 property 结构:
    - sort_info: 排序规则 [{field_name, desc}]
    - filter_info: 筛选规则 {conjunction, conditions: [{field_name, operator, value}]}
    """
    # 视图1: 按推荐度排序
    sort_property = {
        "sort_info": {
            "sort_conditions": [
                {"field_name": "相关性评分", "desc": True},
            ]
        }
    }
    client.create_view(base_token, table_id, "按推荐度排序",
                       view_type="grid", property_=sort_property)

    # 视图2: 优先申请(筛选综合推荐度=优先申请)
    priority_property = {
        "filter_info": {
            "conjunction": "and",
            "conditions": [
                {"field_name": "综合推荐度", "operator": "is",
                 "value": ["优先申请"]},
            ],
        }
    }
    client.create_view(base_token, table_id, "优先申请",
                       view_type="grid", property_=priority_property)

    # 视图3: 校招应届窗口
    campus_property = {
        "filter_info": {
            "conjunction": "and",
            "conditions": [
                {"field_name": "应届窗口", "operator": "is", "value": ["是"]},
            ],
        }
    }
    client.create_view(base_token, table_id, "校招应届窗口",
                       view_type="grid", property_=campus_property)


def setup_user_feishu(tenant_key: str, open_id: str, client: FeishuClient = None) -> dict:
    """
    为用户创建专属飞书空间(多维表格+两个数据表)。
    返回 {base_token, table_id, closed_table_id}
    """
    client = client or FeishuClient()

    # 1. 创建多维表格
    base_token = client.create_bitable("招聘情报库")
    # 防御性解析:若 create_bitable 返回的是 wiki node_token,解析为真实 obj_token
    base_token = client.resolve_app_token(base_token)
    logger.info(f"创建多维表格: {base_token}")

    # 1.5 验证 token 有效且应用有访问权限(防止 91402 NOTEXIST 等问题)
    client.verify_bitable_access(base_token)

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

    # 3.5 创建优化视图(按推荐度排序、按城市筛选)
    # 视图创建失败不阻塞 onboarding,用户可手动创建
    try:
        _create_optimized_views(client, base_token, table_id)
    except Exception as e:
        logger.warning(f"创建优化视图失败(不影响使用): {e}")

    # 4. 分享给用户 + 转所有权（失败不阻塞 onboarding，管理员可手动补分享）
    try:
        client.transfer_owner(base_token, "bitable", open_id)
    except Exception as e:
        logger.warning(f"分享/转所有权失败(不影响用户创建): {e}")

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

    # 加锁防止并发 onboarding（竞态条件导致创建多个多维表格）
    with _onboarding_lock:
        # 双重检查：加锁后再次确认用户不存在
        existing = store.get(user_id)
        if existing and existing.feishu_base_token:
            logger.info(f"用户 {user_id} 已存在,跳过飞书初始化")
            return existing

        client = FeishuClient()
        feishu_info = setup_user_feishu(tenant_key, open_id, client=client)

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

        # 自动发送飞书消息:引导客户打开配置页
        try:
            onboarding_url = f"{settings.SERVICE_BASE_URL}/onboarding?user_id={user_id}"
            msg = (
                "🎉 招聘情报助手已为您创建专属岗位库！\n\n"
                "请点击下方链接配置您的求职偏好（支持简历智能解析）：\n"
                f"{onboarding_url}\n\n"
                "配置完成后将立即为您采集第一批岗位，此后每天早上 9:00 推送岗位日报。"
            )
            client.send_message(open_id, msg)
        except Exception:
            logger.exception(f"发送 onboarding 通知消息失败: user_id={user_id}")

        return user


def handle_feishu_callback(body: dict) -> dict:
    """
    处理飞书事件回调。
    支持:
    - URL 验证(challenge)
    - v2.0 事件结构(header.tenant_key + event.sender.sender_id.open_id)
    - 旧版 v1 事件结构(event.tenant_key + event.operator.open_id)
    """
    # 飞书 URL 验证(challenge)
    if "challenge" in body:
        return {"challenge": body["challenge"]}

    # 兼容 v1.0 和 v2.0 事件结构
    header = body.get("header", {})
    event = body.get("event", {})
    event_type = header.get("event_type", "")

    # 提取 tenant_key
    tenant_key = header.get("tenant_key", "") or event.get("tenant_key", "")

    # 提取 open_id(v2.0: event.sender.sender_id.open_id; v1: event.operator.open_id)
    open_id = (
        event.get("sender", {}).get("sender_id", {}).get("open_id", "")
        or event.get("operator", {}).get("open_id", "")
        or event.get("open_id", "")
    )

    if not tenant_key or not open_id:
        logger.warning(f"回调缺少 tenant_key/open_id: {body}")
        return {"code": 0, "msg": "ignored"}

    # 用 tenant_key+open_id 作为用户 ID
    user_id = f"{tenant_key}_{open_id}"

    # 异步执行 onboarding(飞书要求3秒内返回)
    import threading
    def _onboard():
        try:
            onboard_user(user_id, tenant_key, open_id)
        except Exception:
            logger.exception(f"onboarding 失败: user_id={user_id}")

    threading.Thread(target=_onboard, daemon=True).start()

    return {"code": 0, "msg": "ok"}


def migrate_user_tokens(store: UserStore = None, client: FeishuClient = None) -> dict:
    """
    迁移:将用户存储的 base_token 解析为真实 obj_token。

    解决历史问题:如果用户的多维表格挂在知识库(wiki)下,
    存储的 base_token 可能是 wiki node_token,直接调用 bitable API
    会返回 91402 NOTEXIST。此函数将所有用户的 base_token 解析为真实 obj_token。
    """
    store = store or UserStore()
    client = client or FeishuClient()

    migrated = 0
    unchanged = 0
    failed = []

    for user in store._users.values():
        if not user.feishu_base_token:
            unchanged += 1
            continue
        try:
            resolved = client.resolve_app_token(user.feishu_base_token)
            if resolved != user.feishu_base_token:
                logger.info(
                    f"用户 {user.id} token 已迁移: "
                    f"{user.feishu_base_token} -> {resolved}"
                )
                user.feishu_base_token = resolved
                store.upsert(user)
                migrated += 1
            else:
                unchanged += 1
        except Exception as e:
            logger.error(f"用户 {user.id} token 迁移失败: {e}")
            failed.append({"user_id": user.id, "error": str(e)})

    summary = {"migrated": migrated, "unchanged": unchanged, "failed": failed}
    logger.info(f"token 迁移完成: {summary}")
    return summary
