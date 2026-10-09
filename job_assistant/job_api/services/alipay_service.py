"""支付宝 Vibe Pay 基础收款能力封装（基于 python-alipay-sdk）。

底层接口：alipay.trade.page.pay（PC 网页支付）
- 创单 → 返回跳转 URL（用户在浏览器打开 → 渲染支付宝收银台）
- 异步通知 → POST notify_url → RSA2 验签 → 写订单 paid → 发放权益
- 主动查询兜底 → alipay.trade.query（异步通知丢失时调用）

密钥安全（第一性原理）：
- 应用私钥只在服务端 .env，绝不下发 Tauri 客户端
- 支付宝公钥也只在服务端，用于验签异步通知
- 前端只调后端 /api/v1/payments/create-order，后端组装签名后返回支付 URL

降级模式：
- 沙箱密钥未配置时（ALIPAY_APP_ID 为空），自动降级为 mock 模式
  返回支付宝沙箱门户 URL 作为 pay_url，不阻断开发/测试
- 真实密钥配置后，自动切换为真实 SDK 调用
"""
from __future__ import annotations

import logging
from typing import Optional

from config import get_settings

logger = logging.getLogger(__name__)

# python-alipay-sdk 是可选依赖：未安装时降级到 mock 模式
try:
    from alipay import AliPay  # type: ignore
    _HAS_SDK = True
except ImportError:
    _HAS_SDK = False
    logger.warning("python-alipay-sdk 未安装，支付能力降级为 mock 模式")


class AlipayService:
    """支付宝服务封装（单例，进程内复用 AliPay 客户端）。

    线程安全：python-alipay-sdk 的 AliPay 对象是无状态的（每次调用重新签名），
    可在 FastAPI 同进程多线程场景下复用。
    """

    _instance: "AlipayService | None" = None

    def __new__(cls) -> "AlipayService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self) -> None:
        self.settings = get_settings()
        self.enabled = bool(
            _HAS_SDK
            and self.settings.ALIPAY_APP_ID
            and self.settings.ALIPAY_PRIVATE_KEY
            and self.settings.ALIPAY_PUBLIC_KEY
        )

        if self.enabled:
            self.client = AliPay(
                appid=self.settings.ALIPAY_APP_ID,
                app_notify_url=self.settings.ALIPAY_NOTIFY_URL,
                app_private_key_string=self.settings.ALIPAY_PRIVATE_KEY,
                alipay_public_key_string=self.settings.ALIPAY_PUBLIC_KEY,
                sign_type=self.settings.ALIPAY_SIGN_TYPE,
                debug=self.settings.ALIPAY_ENV == "sandbox",
            )
            logger.info(
                f"AlipayService 已启用（env={self.settings.ALIPAY_ENV}, "
                f"appid={self.settings.ALIPAY_APP_ID[:8]}...）"
            )
        else:
            self.client = None
            logger.warning(
                "AlipayService 降级为 mock 模式：ALIPAY_APP_ID/PRIVATE_KEY/PUBLIC_KEY "
                "未配置或 python-alipay-sdk 未安装"
            )

    def create_page_pay_url(
        self,
        out_trade_no: str,
        total_amount: str,
        subject: str,
        return_url: Optional[str] = None,
    ) -> str:
        """调用 alipay.trade.page.pay 生成支付 URL。

        参数：
        - out_trade_no: 商户订单号（UUID，与 orders.order_id 一致）
        - total_amount: 金额，字符串，单位元，如 "9.90"（两位小数）
        - subject: 订单标题（256 字符内，不可含 / = & 等特殊字符）
        - return_url: 同步回跳 URL（不可信，仅 UX）

        返回：支付 URL（用户在浏览器打开 → 渲染支付宝收银台）

        mock 模式：返回支付宝沙箱门户 URL（不真实创单）
        """
        if not self.enabled:
            # 降级：返回沙箱门户占位，让用户能验证"浏览器能否打开支付宝域名"
            return "https://openhome.alipay.com/develop/sandbox/app"

        # 真实 SDK 调用：alipay.trade.page.pay
        # python-alipay-sdk 的 page_pay 返回跳转 URL（GET 方式）
        from alipay import AliPay  # type: ignore  # 重新导入以通过类型检查

        order_string = self.client.api_alipay_trade_page_pay(
            out_trade_no=out_trade_no,
            total_amount=total_amount,
            subject=subject,
            return_url=return_url or self.settings.ALIPAY_RETURN_URL,
            notify_url=self.settings.ALIPAY_NOTIFY_URL,
        )
        # 沙箱和生产网关不同
        if self.settings.ALIPAY_ENV == "sandbox":
            gateway = "https://openapi-sandbox.dl.alipaydev.com/gateway.do"
        else:
            gateway = "https://openapi.alipay.com/gateway.do"
        return f"{gateway}?{order_string}"

    def verify_notify(self, data: dict) -> bool:
        """验签支付宝异步通知。

        参数 data 是支付宝 POST 过来的表单参数（已转为 dict）。
        返回 True 表示验签通过，False 表示验签失败（可能是伪造通知）。

        mock 模式：永远返回 True（仅开发测试用，生产必须配置真实密钥）
        """
        if not self.enabled:
            return True  # mock 模式不验签

        return self.client.verify(
            data,
            signature=data.get("sign", ""),
            sign_type=self.settings.ALIPAY_SIGN_TYPE,
        )

    def query_trade(self, out_trade_no: str) -> Optional[dict]:
        """调用 alipay.trade.query 主动查询交易状态。

        用于异步通知丢失时的兜底：客户端轮询 /orders/{id}/status 时，
        若订单仍 pending，后端可调此方法主动查支付宝。

        返回 dict（含 trade_status / total_amount / trade_no 等）或 None。

        mock 模式：返回 None（不真实查询）
        """
        if not self.enabled:
            return None

        result = self.client.api_alipay_trade_query(out_trade_no=out_trade_no)
        return result


# 模块级单例
alipay_service = AlipayService()
