"""支付与权益路由（Vibe Pay 基础收款能力接入）。

两种付费模式：
  - trial_monthly: 月度试用 ¥9.9，到期可续费
  - lifetime:      一次性买断（永久），不可重复购买

数据模型（SQLite，建议与 llm_usage 同库 auth.db）：

    CREATE TABLE orders (
        order_id          TEXT PRIMARY KEY,       -- UUID, 服务端生成
        user_id           TEXT NOT NULL,
        product_code      TEXT NOT NULL,          -- 'trial_monthly' | 'lifetime'
        amount_cents      INTEGER NOT NULL,       -- 990=¥9.9, 9900=¥99
        status            TEXT NOT NULL DEFAULT 'pending',
                                                    -- pending/paid/delivered/cancelled
        alipay_trade_no   TEXT,                   -- 支付宝异步通知回传
        created_at        TEXT NOT NULL,          -- ISO8601
        paid_at           TEXT,
        delivered_at      TEXT,
        cancelled_at      TEXT,                    -- 24h 未付自动取消
        UNIQUE(order_id)
    );

    CREATE TABLE entitlements (
        user_id           TEXT PRIMARY KEY,       -- 每用户一行（v1 简化，不做历史）
        type              TEXT NOT NULL,           -- 'trial_monthly' | 'lifetime'
        expires_at        TEXT,                    -- NULL 表示 lifetime 永不过期
        source_order_id   TEXT NOT NULL,
        updated_at        TEXT NOT NULL
    );

权益发放语义：
  - trial_monthly 续费：expires_at = max(现有 expires_at, now) + 30 天
    —— 用户不会因提前续费损失剩余天数
  - lifetime 升级：直接置 type=lifetime, expires_at=NULL
    —— 已 lifetime 用户购买 trial 视为无意义，返回 409 Conflict
  - lifetime 升级前的 trial 历史保留在 orders 表（审计日志）

本文件当前为「卡点1 验证版本」：使用进程内 dict 模拟 DB，
不接真实 Alipay SDK，目的是验证 Tauri webview/系统浏览器 + 服务端轮询的架构是否成立。
真实接入时把 _ORDERS / _ENTITLEMENTS 替换为 SQLite 读写即可。
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from deps import get_current_user

router = APIRouter(prefix="/payments", tags=["payments"])

# ============================================================================
# 商品目录（两种付费模式）
# ============================================================================

PRODUCTS: Dict[str, Dict] = {
    "trial_monthly": {
        "code": "trial_monthly",
        "name": "月度试用",
        "price_cents": 990,            # ¥9.9
        "duration_days": 30,
        "lifetime": False,
    },
    "lifetime": {
        "code": "lifetime",
        "name": "永久买断",
        "price_cents": 9900,           # ¥99（默认 10× 月度，可在 .env 覆盖）
        "duration_days": None,
        "lifetime": True,
    },
}

# ============================================================================
# 进程内 mock 存储（验证用；真实接入替换为 SQLite）
# ============================================================================

_lock = threading.Lock()
_ORDERS: Dict[str, Dict] = {}             # order_id -> order dict
_ENTITLEMENTS: Dict[str, Dict] = {}       # user_id -> entitlement dict


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================================
# 请求 / 响应模型
# ============================================================================

class CreateOrderRequest(BaseModel):
    product_code: str = Field(..., description="trial_monthly | lifetime")


class CreateOrderResponse(BaseModel):
    order_id: str
    product_code: str
    amount_cents: int
    pay_url: str            # 用户在浏览器打开后进行支付（mock 阶段指向支付宝沙箱门户）
    status: str


class OrderStatusResponse(BaseModel):
    order_id: str
    status: str
    product_code: str
    amount_cents: int
    paid_at: Optional[str] = None
    delivered_at: Optional[str] = None


class EntitlementResponse(BaseModel):
    type: Optional[str] = None              # trial_monthly | lifetime | None
    active: bool
    expires_at: Optional[str] = None
    source_order_id: Optional[str] = None


# ============================================================================
# 真实接入时的端点（已留好 Alipay SDK 调用位置，本版本用 mock 填充）
# ============================================================================

@router.post("/create-order", response_model=CreateOrderResponse)
def create_order(
    req: CreateOrderRequest,
    user: dict = Depends(get_current_user),
) -> CreateOrderResponse:
    """创建支付订单。

    真实接入时流程：
      1. 校验 product_code 与用户当前权益（lifetime 用户不能再下单）
      2. 写入 orders 表（status=pending）
      3. 调用 Alipay SDK alipay.trade.create / alipay.trade.page.pay 拿到支付 URL
      4. 返回 pay_url 给前端，由前端 shell.open 或 webview 打开
    """
    product = PRODUCTS.get(req.product_code)
    if not product:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"未知商品: {req.product_code}")

    user_id = str(user["user_id"])

    # 已 lifetime 用户禁止再下单（含 trial 和 lifetime）
    with _lock:
        ent = _ENTITLEMENTS.get(user_id)
        if ent and ent["type"] == "lifetime":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "已购买永久版，无需再次付费",
            )

    order_id = str(uuid.uuid4())
    now = _now_iso()

    # mock pay_url：真实接入时由 Alipay SDK 返回。这里用支付宝沙箱门户占位，
    # 用户能看到页面即证明"系统浏览器能渲染支付宝域名"。
    pay_url = "https://openhome.alipay.com/develop/sandbox/app"

    with _lock:
        _ORDERS[order_id] = {
            "order_id": order_id,
            "user_id": user_id,
            "product_code": req.product_code,
            "amount_cents": product["price_cents"],
            "status": "pending",
            "alipay_trade_no": None,
            "created_at": now,
            "paid_at": None,
            "delivered_at": None,
            "cancelled_at": None,
        }

    return CreateOrderResponse(
        order_id=order_id,
        product_code=req.product_code,
        amount_cents=product["price_cents"],
        pay_url=pay_url,
        status="pending",
    )


@router.get("/orders/{order_id}", response_model=OrderStatusResponse)
def get_order_status(
    order_id: str,
    user: dict = Depends(get_current_user),
) -> OrderStatusResponse:
    """查询订单状态。前端支付后每 2s 轮询此端点。

    真实接入时数据来自 orders 表（由异步 notify 写入 paid 状态）。
    """
    with _lock:
        order = _ORDERS.get(order_id)
        if not order:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "订单不存在")
        if order["user_id"] != str(user["user_id"]):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "无权查看此订单")

    return OrderStatusResponse(
        order_id=order["order_id"],
        status=order["status"],
        product_code=order["product_code"],
        amount_cents=order["amount_cents"],
        paid_at=order["paid_at"],
        delivered_at=order["delivered_at"],
    )


@router.get("/entitlements", response_model=EntitlementResponse)
def get_entitlement(user: dict = Depends(get_current_user)) -> EntitlementResponse:
    """查询当前用户的权益状态。App 启动时调用，实现"关 app 后重启自愈"。

    active 判定：
      - lifetime: 永远 active
      - trial_monthly: expires_at 未过期则 active
    """
    user_id = str(user["user_id"])
    with _lock:
        ent = _ENTITLEMENTS.get(user_id)
    if not ent:
        return EntitlementResponse(type=None, active=False)
    if ent["type"] == "lifetime":
        return EntitlementResponse(
            type="lifetime", active=True, source_order_id=ent["source_order_id"]
        )
    # trial_monthly：检查过期
    expires_at = ent.get("expires_at")
    active = bool(expires_at) and datetime.fromisoformat(expires_at) > datetime.now(timezone.utc)
    return EntitlementResponse(
        type="trial_monthly",
        active=active,
        expires_at=expires_at,
        source_order_id=ent["source_order_id"],
    )


# ============================================================================
# 支付宝异步通知回调（真实接入时此端点由支付宝服务端 POST 调用）
# ============================================================================

@router.post("/notify")
async def alipay_notify() -> dict:
    """支付宝异步通知入口。

    真实接入时：
      1. 从 form 表单解析 trade_status / out_trade_no / total_amount / sign
      2. 用支付宝公钥验签（防伪造）
      3. 校验金额、订单号、app_id 一致
      4. 幂等：order.status 已是 paid 直接返回 success
      5. 写入 paid_at，调用 _deliver_entitlement 发放权益
      6. 必须返回字符串 "success"（支付宝约定）

    本验证版本不接受真实支付宝请求；用下面的 /test/simulate-notify 模拟。
    """
    return {"msg": "真实支付宝通知请走 /test/simulate-notify 模拟"}


# ============================================================================
# 验证用 mock 端点（仅开发期使用，真实接入时删除）
# ============================================================================

@router.post("/test/simulate-notify")
def test_simulate_notify(
    order_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """模拟支付宝异步通知：把指定订单标记为已支付并发放权益。

    真实接入时此端点删除；由 /notify 处理真实通知。
    本端点验证：客户端轮询能否独立发现"已支付"状态。
    """
    with _lock:
        order = _ORDERS.get(order_id)
        if not order:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "订单不存在")
        if order["user_id"] != str(user["user_id"]):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作此订单")
        if order["status"] != "pending":
            return {"msg": f"订单状态 {order['status']}，无需重复处理", "order_id": order_id}

        now = _now_iso()
        order["status"] = "paid"
        order["paid_at"] = now
        # 模拟发放权益
        _deliver_entitlement_locked(order["user_id"], order["product_code"], order_id, now)
        order["status"] = "delivered"
        order["delivered_at"] = now
    return {"msg": "ok", "order_id": order_id, "status": "delivered"}


def _deliver_entitlement_locked(
    user_id: str,
    product_code: str,
    order_id: str,
    now_iso: str,
) -> None:
    """发放权益（必须在 _lock 内调用）。

    真实接入时此函数由 /notify 验签通过后调用。
    """
    product = PRODUCTS[product_code]
    existing = _ENTITLEMENTS.get(user_id)

    if product["lifetime"]:
        _ENTITLEMENTS[user_id] = {
            "type": "lifetime",
            "expires_at": None,
            "source_order_id": order_id,
            "updated_at": now_iso,
        }
        return

    # trial_monthly：续费 = max(现有到期, now) + 30 天
    from datetime import timedelta
    base = datetime.now(timezone.utc)
    if existing and existing.get("expires_at"):
        try:
            existing_exp = datetime.fromisoformat(existing["expires_at"])
            if existing_exp > base:
                base = existing_exp
        except ValueError:
            pass
    new_exp = (base + timedelta(days=product["duration_days"])).isoformat()
    _ENTITLEMENTS[user_id] = {
        "type": "trial_monthly",
        "expires_at": new_exp,
        "source_order_id": order_id,
        "updated_at": now_iso,
    }
