"""订单与权益数据访问层（SQLite + aiosqlite）。

表结构（与 auth.db 同库，与现有 user.py / quota_service.py 模式一致）：
- orders: 订单流水（pending/paid/delivered/cancelled 状态机）
- entitlements: 用户当前权益（每用户一行，v1 简化，历史在 orders 表）

权益发放语义：
- trial_monthly 续费: expires_at = max(现有 expires_at, now) + ALIPAY_PRODUCT_TRIAL_DAYS 天
  —— 用户不会因提前续费损失剩余天数
- lifetime 升级: 直接置 type=lifetime, expires_at=NULL
  —— 已 lifetime 用户购买 trial 视为无意义，返回 409 Conflict

幂等设计：
- orders.order_id 是 UUID，主键约束保证重复插入失败
- orders.status 状态机：pending → paid → delivered（同向不回退）
- 异步通知重复到达时，已 paid/delivered 的订单直接返回 success 不重发权益
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

from config import get_settings


def _db_path() -> Path:
    """返回 auth.db 文件路径，与 user.py / quota_service.py 同库。"""
    settings = get_settings()
    return Path(settings.DATA_DIR) / "auth.db"


async def _connect() -> aiosqlite.Connection:
    """打开一个新连接，行工厂设为 Row 以便按字段名访问。

    用完调用方需手动 await conn.close()（与 user.py 模式一致）。
    """
    conn = await aiosqlite.connect(str(_db_path()))
    conn.row_factory = aiosqlite.Row
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    """幂等建表（CREATE TABLE IF NOT EXISTS）。"""
    conn = await _connect()
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id          TEXT PRIMARY KEY,
                user_id           TEXT NOT NULL,
                product_code      TEXT NOT NULL,
                amount_cents      INTEGER NOT NULL,
                status            TEXT NOT NULL DEFAULT 'pending',
                alipay_trade_no   TEXT,
                created_at        TEXT NOT NULL,
                paid_at           TEXT,
                delivered_at      TEXT,
                cancelled_at      TEXT,
                UNIQUE(order_id)
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entitlements (
                user_id           TEXT PRIMARY KEY,
                type              TEXT NOT NULL,
                expires_at        TEXT,
                source_order_id   TEXT NOT NULL,
                updated_at        TEXT NOT NULL
            )
            """
        )
        # 订单状态机迁移：旧表可能没有 cancelled_at 列，幂等补列
        cursor = await conn.execute("PRAGMA table_info(orders)")
        existing_cols = {row[1] for row in await cursor.fetchall()}
        if "cancelled_at" not in existing_cols:
            await conn.execute("ALTER TABLE orders ADD COLUMN cancelled_at TEXT")
        await conn.commit()
    finally:
        await conn.close()


# ============================================================================
# 商品目录（从 Settings 注入，可被 .env 覆盖）
# ============================================================================

def get_products() -> dict:
    """返回商品目录 dict[code -> {code, name, price_cents, duration_days, lifetime}]。"""
    s = get_settings()
    return {
        "trial_monthly": {
            "code": "trial_monthly",
            "name": "月度试用",
            "price_cents": s.ALIPAY_PRODUCT_TRIAL_CENTS,
            "duration_days": s.ALIPAY_PRODUCT_TRIAL_DAYS,
            "lifetime": False,
        },
        "lifetime": {
            "code": "lifetime",
            "name": "永久买断",
            "price_cents": s.ALIPAY_PRODUCT_LIFETIME_CENTS,
            "duration_days": None,
            "lifetime": True,
        },
    }


# ============================================================================
# Orders CRUD
# ============================================================================

async def create_order(
    user_id: str,
    product_code: str,
    amount_cents: int,
) -> dict:
    """创建 pending 订单。返回订单 dict。"""
    order_id = str(uuid.uuid4())
    now = _now_iso()
    conn = await _connect()
    try:
        await conn.execute(
            """
            INSERT INTO orders (order_id, user_id, product_code, amount_cents,
                                status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (order_id, user_id, product_code, amount_cents, now),
        )
        await conn.commit()
    finally:
        await conn.close()
    return {
        "order_id": order_id,
        "user_id": user_id,
        "product_code": product_code,
        "amount_cents": amount_cents,
        "status": "pending",
        "alipay_trade_no": None,
        "created_at": now,
        "paid_at": None,
        "delivered_at": None,
        "cancelled_at": None,
    }


async def get_order(order_id: str) -> Optional[dict]:
    """按 order_id 查订单，返回 dict 或 None。"""
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "SELECT * FROM orders WHERE order_id=?",
            (order_id,),
        )
        row = await cursor.fetchone()
    finally:
        await conn.close()
    if not row:
        return None
    return dict(row)


async def mark_paid(order_id: str, alipay_trade_no: str) -> bool:
    """标记订单为 paid 并记录支付宝交易号。

    幂等：已 paid/delivered 的订单不会被重复更新（状态机不回退）。
    返回 True 表示本次更新生效（首次 paid），False 表示已是终态。
    """
    now = _now_iso()
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "SELECT status FROM orders WHERE order_id=?",
            (order_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return False
        if row["status"] in ("paid", "delivered"):
            return False  # 幂等：已 paid，不重复处理
        await conn.execute(
            """
            UPDATE orders SET status='paid', alipay_trade_no=?, paid_at=?
            WHERE order_id=? AND status='pending'
            """,
            (alipay_trade_no, now, order_id),
        )
        await conn.commit()
    finally:
        await conn.close()
    return True


async def mark_delivered(order_id: str) -> None:
    """标记订单为 delivered（权益已发放）。"""
    now = _now_iso()
    conn = await _connect()
    try:
        await conn.execute(
            "UPDATE orders SET status='delivered', delivered_at=? WHERE order_id=?",
            (now, order_id),
        )
        await conn.commit()
    finally:
        await conn.close()


async def cancel_expired_orders(timeout_minutes: int = 30) -> int:
    """把超过 timeout_minutes 仍 pending 的订单标记为 cancelled。

    支付宝订单默认超时 15d，这里用 30min 是业务侧提前收尾：
    用户创建订单后 30 分钟未付，前端轮询应停止并提示重新下单。
    返回取消的订单数。
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)).isoformat()
    now = _now_iso()
    conn = await _connect()
    try:
        cursor = await conn.execute(
            """
            UPDATE orders SET status='cancelled', cancelled_at=?
            WHERE status='pending' AND created_at < ?
            """,
            (now, cutoff),
        )
        await conn.commit()
    finally:
        await conn.close()
    return cursor.rowcount


# ============================================================================
# Entitlements CRUD
# ============================================================================

async def get_entitlement(user_id: str) -> Optional[dict]:
    """查用户当前权益。返回 dict 或 None（未购买）。"""
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "SELECT * FROM entitlements WHERE user_id=?",
            (user_id,),
        )
        row = await cursor.fetchone()
    finally:
        await conn.close()
    return dict(row) if row else None


async def deliver_entitlement(
    user_id: str,
    product_code: str,
    order_id: str,
) -> dict:
    """发放权益（幂等：重复调用不会叠加）。

    - trial_monthly 续费: expires_at = max(现有 expires_at, now) + duration_days
    - lifetime 升级: expires_at = NULL, type = lifetime
    """
    products = get_products()
    product = products[product_code]
    now = datetime.now(timezone.utc)

    existing = await get_entitlement(user_id)

    if product["lifetime"]:
        # lifetime 升级：直接覆盖
        conn = await _connect()
        try:
            await conn.execute(
                """
                INSERT INTO entitlements (user_id, type, expires_at, source_order_id, updated_at)
                VALUES (?, 'lifetime', NULL, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    type='lifetime', expires_at=NULL,
                    source_order_id=excluded.source_order_id,
                    updated_at=excluded.updated_at
                """,
                (user_id, order_id, now.isoformat()),
            )
            await conn.commit()
        finally:
            await conn.close()
        return {
            "type": "lifetime",
            "expires_at": None,
            "source_order_id": order_id,
            "updated_at": now.isoformat(),
        }

    # trial_monthly 续费：max(现有到期, now) + duration_days
    duration_days: int = product["duration_days"]
    base = now
    if existing and existing.get("expires_at"):
        try:
            existing_exp = datetime.fromisoformat(existing["expires_at"])
            if existing_exp > base:
                base = existing_exp
        except ValueError:
            pass
    new_exp = (base + timedelta(days=duration_days)).isoformat()

    conn = await _connect()
    try:
        await conn.execute(
            """
            INSERT INTO entitlements (user_id, type, expires_at, source_order_id, updated_at)
            VALUES (?, 'trial_monthly', ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                type='trial_monthly', expires_at=excluded.expires_at,
                source_order_id=excluded.source_order_id,
                updated_at=excluded.updated_at
            """,
            (user_id, new_exp, order_id, now.isoformat()),
        )
        await conn.commit()
    finally:
        await conn.close()
    return {
        "type": "trial_monthly",
        "expires_at": new_exp,
        "source_order_id": order_id,
        "updated_at": now.isoformat(),
    }


def is_entitlement_active(ent: Optional[dict]) -> bool:
    """判断权益是否有效。

    - lifetime: 永远 active
    - trial_monthly: expires_at 未过期
    - None: 未购买
    """
    if not ent:
        return False
    if ent["type"] == "lifetime":
        return True
    expires_at = ent.get("expires_at")
    if not expires_at:
        return False
    try:
        return datetime.fromisoformat(expires_at) > datetime.now(timezone.utc)
    except ValueError:
        return False
