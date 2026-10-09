"""支付与权益路由（Vibe Pay 基础收款能力完整接入）。

两种付费模式：
  - trial_monthly: 月度试用 ¥9.9，到期可续费（不损失剩余天数）
  - lifetime:      一次性买断（永久），不可重复购买

数据流（应用外付款 · 真相源 = 异步 notify + 主动 query 双保险）：
  1. 客户端 POST /create-order → 服务端写 pending 订单 + 调 alipay.trade.page.pay → 返回 pay_url
  2. 客户端 shell.open(pay_url) → 系统浏览器渲染支付宝收银台
  3. 用户在浏览器付款 → 支付宝 POST /notify（验签 + 二次校验 + 幂等 + 发权益）
  4. 客户端轮询 GET /orders/{id} → 服务端读 SQLite（异步通知已写入 paid/delivered）
  5. 兜底：轮询时若仍 pending，后端可调 alipay.trade.query 主动查

对抗性审查防御：
  - 验签：notify 必须用支付宝公钥 RSA2 验签，防伪造
  - 二次校验：验签后校验 out_trade_no/total_amount/app_id 一致
  - 幂等：order_id UNIQUE + 状态机 pending→paid→delivered，重复通知不重发权益
  - 私钥安全：只在服务端 .env，绝不下发客户端
  - 主动查询：notify 丢失时，轮询触发 alipay.trade.query 兜底
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from config import get_settings
from deps import get_current_user
from models import payment as payment_db
from models.payment import get_products, is_entitlement_active
from services.alipay_service import alipay_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])


# ============================================================================
# 请求 / 响应模型
# ============================================================================

class CreateOrderRequest(BaseModel):
    product_code: str = Field(..., description="trial_monthly | lifetime")


class CreateOrderResponse(BaseModel):
    order_id: str
    product_code: str
    amount_cents: int
    pay_url: str
    status: str


class OrderStatusResponse(BaseModel):
    order_id: str
    status: str
    product_code: str
    amount_cents: int
    paid_at: Optional[str] = None
    delivered_at: Optional[str] = None


class EntitlementResponse(BaseModel):
    type: Optional[str] = None
    active: bool
    expires_at: Optional[str] = None
    source_order_id: Optional[str] = None


# ============================================================================
# 端点
# ============================================================================

@router.post("/create-order", response_model=CreateOrderResponse)
async def create_order(
    req: CreateOrderRequest,
    user: dict = Depends(get_current_user),
) -> CreateOrderResponse:
    """创建支付订单。

    真实接入流程：
    1. 校验 product_code 与用户当前权益（lifetime 用户不能再下单）
    2. 写 orders 表（status=pending）
    3. 调 alipay.trade.page.pay 拿到支付 URL
    4. 返回 pay_url 给前端，由前端 shell.open 或 webview 打开
    """
    products = get_products()
    product = products.get(req.product_code)
    if not product:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"未知商品: {req.product_code}")

    user_id = str(user["user_id"])

    # 已 lifetime 用户禁止再下单（含 trial 和 lifetime）
    existing_ent = await payment_db.get_entitlement(user_id)
    if existing_ent and existing_ent["type"] == "lifetime":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "已购买永久版，无需再次付费",
        )

    # 写 pending 订单
    order = await payment_db.create_order(
        user_id=user_id,
        product_code=req.product_code,
        amount_cents=product["price_cents"],
    )

    # 调 alipay.trade.page.pay 生成支付 URL
    total_amount = f"{product['price_cents'] / 100:.2f}"  # 分 → 元，两位小数
    subject = product["name"]
    pay_url = alipay_service.create_page_pay_url(
        out_trade_no=order["order_id"],
        total_amount=total_amount,
        subject=subject,
    )

    return CreateOrderResponse(
        order_id=order["order_id"],
        product_code=req.product_code,
        amount_cents=product["price_cents"],
        pay_url=pay_url,
        status="pending",
    )


@router.get("/orders/{order_id}", response_model=OrderStatusResponse)
async def get_order_status(
    order_id: str,
    user: dict = Depends(get_current_user),
) -> OrderStatusResponse:
    """查询订单状态。前端支付后每 2s 轮询此端点。

    兜底机制：若订单仍 pending 且超过 10 秒，主动调 alipay.trade.query
    查询支付宝侧状态（异步通知可能延迟或丢失）。
    """
    order = await payment_db.get_order(order_id)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "订单不存在")
    if order["user_id"] != str(user["user_id"]):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权查看此订单")

    # 兜底：仍 pending 时主动查支付宝
    if order["status"] == "pending":
        created_at = datetime.fromisoformat(order["created_at"])
        if (datetime.now(timezone.utc) - created_at).total_seconds() > 10:
            trade_info = alipay_service.query_trade(order_id)
            if trade_info:
                trade_status = trade_info.get("trade_status", "")
                if trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED"):
                    alipay_trade_no = trade_info.get("trade_no", "")
                    await payment_db.mark_paid(order_id, alipay_trade_no)
                    await payment_db.deliver_entitlement(
                        order["user_id"], order["product_code"], order_id
                    )
                    await payment_db.mark_delivered(order_id)
                    # 重新读取更新后的订单
                    order = await payment_db.get_order(order_id)

    return OrderStatusResponse(
        order_id=order["order_id"],
        status=order["status"],
        product_code=order["product_code"],
        amount_cents=order["amount_cents"],
        paid_at=order["paid_at"],
        delivered_at=order["delivered_at"],
    )


@router.get("/entitlements", response_model=EntitlementResponse)
async def get_entitlement(user: dict = Depends(get_current_user)) -> EntitlementResponse:
    """查询当前用户的权益状态。App 启动时调用，实现"关 app 后重启自愈"。"""
    user_id = str(user["user_id"])
    ent = await payment_db.get_entitlement(user_id)
    active = is_entitlement_active(ent)
    if not ent:
        return EntitlementResponse(type=None, active=False)
    return EntitlementResponse(
        type=ent["type"],
        active=active,
        expires_at=ent.get("expires_at"),
        source_order_id=ent.get("source_order_id"),
    )


# ============================================================================
# 支付宝异步通知回调（公网 HTTPS，由支付宝服务端 POST 调用）
# ============================================================================

@router.post("/notify", response_class=PlainTextResponse)
async def alipay_notify(request: Request) -> str:
    """支付宝异步通知入口。

    真实接入时流程：
    1. 从 form 表单解析所有参数（trade_status / out_trade_no / total_amount / sign 等）
    2. 用支付宝公钥 RSA2 验签（防伪造）
    3. 二次校验：out_trade_no 存在、total_amount 一致、app_id 一致
    4. 幂等：order.status 已是 paid/delivered 直接返回 success
    5. 写入 paid_at，调用 deliver_entitlement 发放权益
    6. 必须返回字符串 "success"（支付宝约定，否则重试）

    重试策略：4m/10m/10m/1h/2h/6h/15h
    """
    # 解析 form 表单参数
    form = await request.form()
    data = {k: v for k, v in form.items()}

    # 1. 验签
    if not alipay_service.verify_notify(data):
        logger.warning(f"支付宝异步通知验签失败: {data.get('out_trade_no', 'unknown')}")
        return "fail"

    # 2. 二次校验
    out_trade_no = data.get("out_trade_no", "")
    total_amount = data.get("total_amount", "")
    trade_status = data.get("trade_status", "")
    trade_no = data.get("trade_no", "")
    app_id = data.get("app_id", "")

    settings = get_settings()
    if settings.ALIPAY_APP_ID and app_id != settings.ALIPAY_APP_ID:
        logger.warning(f"异步通知 app_id 不匹配: expected={settings.ALIPAY_APP_ID}, got={app_id}")
        return "fail"

    order = await payment_db.get_order(out_trade_no)
    if not order:
        logger.warning(f"异步通知订单不存在: {out_trade_no}")
        return "fail"

    expected_amount = f"{order['amount_cents'] / 100:.2f}"
    if total_amount and total_amount != expected_amount:
        logger.warning(
            f"异步通知金额不匹配: expected={expected_amount}, got={total_amount}, "
            f"order_id={out_trade_no}"
        )
        return "fail"

    # 3. 幂等：已 paid/delivered 直接返回 success
    if order["status"] in ("paid", "delivered"):
        return "success"

    # 4. 只有 TRADE_SUCCESS / TRADE_FINISHED 才认定付款成功
    if trade_status not in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        return "success"  # 其他状态（如 WAIT_BUYER_PAY）不处理但返回 success 避免重试

    # 5. 写入 paid + 发放权益
    updated = await payment_db.mark_paid(out_trade_no, trade_no)
    if updated:
        await payment_db.deliver_entitlement(
            order["user_id"], order["product_code"], out_trade_no
        )
        await payment_db.mark_delivered(out_trade_no)
        logger.info(f"权益已发放: order_id={out_trade_no}, user={order['user_id']}")

    # 6. 返回 success（支付宝约定）
    return "success"


# ============================================================================
# 验证用 mock 端点（仅开发期使用，真实接入时删除）
# ============================================================================

@router.post("/test/simulate-notify")
async def test_simulate_notify(
    order_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """模拟支付宝异步通知：把指定订单标记为已支付并发放权益。

    真实接入时此端点删除；由 /notify 处理真实通知。
    本端点验证：客户端轮询能否独立发现"已支付"状态。
    """
    order = await payment_db.get_order(order_id)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "订单不存在")
    if order["user_id"] != str(user["user_id"]):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作此订单")
    if order["status"] != "pending":
        return {"msg": f"订单状态 {order['status']}，无需重复处理", "order_id": order_id}

    fake_trade_no = f"MOCK_{order_id[:16]}"
    updated = await payment_db.mark_paid(order_id, fake_trade_no)
    if updated:
        await payment_db.deliver_entitlement(
            order["user_id"], order["product_code"], order_id
        )
        await payment_db.mark_delivered(order_id)
    return {"msg": "ok", "order_id": order_id, "status": "delivered"}
