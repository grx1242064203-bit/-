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
from schema import JOB_FIELDS, CLOSED_JOB_FIELDS, MT_TABLE_FIELDS
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


def _create_fields_and_views(client: FeishuClient, base_token: str,
                             table_id: str, closed_table_id: str):
    """后台创建字段和视图(耗时操作,不阻塞用户拿到消息)"""
    try:
        # 关键修复:建表后第一个字段是主字段(记录名),默认名不是"岗位标题",
        # 会导致所有记录显示"未命名记录"。这里先找到主字段并重命名为"岗位标题"。
        for tid in (table_id, closed_table_id):
            try:
                fields = client.list_fields(base_token, tid)
                for f in fields:
                    if f.get("is_primary"):
                        client.update_field(base_token, tid, f["field_id"],
                                            field_name="岗位标题")
                        break
            except Exception as e:
                logger.warning(f"重命名主字段失败 table={tid}: {e}")

        # 创建其余字段(跳过"岗位标题",因为它已是主字段)
        for f in JOB_FIELDS:
            if f["name"] == "岗位标题":
                continue  # 主字段已重命名,无需再创建
            kwargs = {}
            if "options" in f:
                kwargs["property"] = {"options": f["options"]}
            if "style" in f:
                kwargs["property"] = {**kwargs.get("property", {}), **f["style"]}
            if "multiple" in f:
                kwargs["property"] = {**kwargs.get("property", {}), "multiple": f["multiple"]}
            try:
                client.create_field(base_token, table_id, f["name"], f["type"], **kwargs)
                time.sleep(0.1)
            except Exception as e:
                logger.warning(f"创建字段失败 {f['name']}: {e}")

        for f in CLOSED_JOB_FIELDS:
            if f["name"] == "岗位标题":
                continue
            kwargs = {}
            if "options" in f:
                kwargs["property"] = {"options": f["options"]}
            if "style" in f:
                kwargs["property"] = {**kwargs.get("property", {}), **f["style"]}
            if "multiple" in f:
                kwargs["property"] = {**kwargs.get("property", {}), "multiple": f["multiple"]}
            try:
                client.create_field(base_token, closed_table_id, f["name"], f["type"], **kwargs)
                time.sleep(0.1)
            except Exception as e:
                logger.warning(f"创建字段失败 {f['name']}: {e}")

        try:
            _create_optimized_views(client, base_token, table_id)
        except Exception as e:
            logger.warning(f"创建优化视图失败(不影响使用): {e}")

        logger.info(f"后台字段/视图创建完成: base={base_token}")
    except Exception:
        logger.exception("后台字段/视图创建异常")


def setup_user_feishu(tenant_key: str, open_id: str, client: FeishuClient = None) -> dict:
    """
    为用户创建专属飞书空间(多维表格+两个数据表)。
    只创建表格骨架,字段和视图放后台异步创建,确保用户快速收到消息。
    返回 {base_token, table_id, closed_table_id}
    """
    client = client or FeishuClient()

    # 1. 创建多维表格
    base_token = client.create_bitable("招聘情报库")
    base_token = client.resolve_app_token(base_token)
    logger.info(f"创建多维表格: {base_token}")

    # 2. 验证 token 有效
    client.verify_bitable_access(base_token)

    # 3. 创建两个数据表(骨架,字段后台创建)
    table_id = client.create_table(base_token, "岗位数据库")
    closed_table_id = client.create_table(base_token, "已关闭岗位")

    return {
        "base_token": base_token,
        "table_id": table_id,
        "closed_table_id": closed_table_id,
    }


def ensure_mt_table(user: User, client: FeishuClient = None) -> str:
    """
    为校招用户确保管培生项目表存在。
    如果用户已有 mt_table_id 则直接返回;否则创建新表+字段。
    返回 mt_table_id。
    """
    client = client or FeishuClient()
    base_token = user.feishu_base_token
    if not base_token:
        return ""

    # 已有管培表,直接返回
    if user.feishu_mt_table_id:
        return user.feishu_mt_table_id

    # 仅校招用户创建管培表
    profile = getattr(user, "profile", None)
    role = getattr(profile, "role", "") or ""
    if role != "campus":
        return ""

    try:
        # 创建管培项目表
        mt_table_id = client.create_table(base_token, "管培生项目")
        logger.info(f"创建管培项目表: {mt_table_id}")

        # 重命名主字段为"项目名称"
        try:
            fields = client.list_fields(base_token, mt_table_id)
            for f in fields:
                if f.get("is_primary"):
                    client.update_field(base_token, mt_table_id, f["field_id"],
                                        field_name="项目名称")
                    break
        except Exception as e:
            logger.warning(f"重命名管培表主字段失败: {e}")

        # 创建管培表字段(跳过"项目名称"主字段)
        for f in MT_TABLE_FIELDS:
            if f["name"] == "项目名称":
                continue
            kwargs = {}
            if "options" in f:
                kwargs["property"] = {"options": f["options"]}
            if "style" in f:
                kwargs["property"] = {**kwargs.get("property", {}), **f["style"]}
            if "multiple" in f:
                kwargs["property"] = {**kwargs.get("property", {}), "multiple": f["multiple"]}
            try:
                client.create_field(base_token, mt_table_id, f["name"], f["type"], **kwargs)
                time.sleep(0.1)
            except Exception as e:
                logger.warning(f"创建管培表字段失败 {f['name']}: {e}")

        # 保存 mt_table_id 到用户
        from store import UserStore
        store = UserStore()
        user.feishu_mt_table_id = mt_table_id
        store.upsert(user)
        logger.info(f"管培项目表创建完成: user={user.id} mt_table={mt_table_id}")
        return mt_table_id

    except Exception as e:
        logger.exception(f"创建管培项目表失败: {e}")
        return ""


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

        # 立即发送飞书卡片消息(带配置页按钮),不等所有权转移
        onboarding_url = f"{settings.SERVICE_BASE_URL}/onboarding?user_id={user_id}"
        try:
            card = {
                "config": {"wide_screen_mode": True},
                "header": {
                    "template": "blue",
                    "title": {"tag": "plain_text", "content": "🎉 招聘情报助手已就绪"},
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": (
                            "已为您创建专属岗位数据库！\n\n"
                            "请点击下方按钮配置求职偏好（支持简历智能解析），"
                            "配置完成后立即采集第一批岗位，此后每天 9:00 推送岗位日报。"
                        ),
                    },
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": "配置求职偏好"},
                                "type": "primary",
                                "url": onboarding_url,
                            }
                        ],
                    },
                ],
            }
            client.send_card_message(open_id, card)
        except Exception:
            logger.exception(f"发送 onboarding 卡片消息失败: user_id={user_id}")

        # 后台异步:创建字段/视图 + 转移所有权(耗时操作,不阻塞用户)
        def _post_setup():
            _create_fields_and_views(
                client, feishu_info["base_token"],
                feishu_info["table_id"], feishu_info["closed_table_id"],
            )
            try:
                client.transfer_owner(feishu_info["base_token"], "bitable", open_id)
            except Exception as e:
                logger.warning(f"所有权转移失败(已降级为分享): {e}")

        threading.Thread(target=_post_setup, daemon=True).start()

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
