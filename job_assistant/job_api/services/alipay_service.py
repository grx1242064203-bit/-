"""支付宝 Vibe Pay 基础收款能力封装（基于 python-alipay-sdk）。

底层接口：alipay.trade.page.pay（PC 网页支付）
- 创单 → 返回跳转 URL（用户在浏览器打开 → 渲染支付宝收银台）
- 异步通知 → POST notify_url → RSA2 验签 → 写订单 paid → 发放权益
- 主动查询兜底 → alipay.trade.query（异步通知丢失时调用）

密钥获取优先级（第一性原理：能自动就不手动）：
1. .alipay-sandbox.json（由 alipay-cli sandbox_config.sh 自动获取，无需登录）
   → 沙箱环境，Python 用 appPrivatePkcsKey（PKCS1 格式）
2. .env 中的 ALIPAY_APP_ID/PRIVATE_KEY/PUBLIC_KEY（生产环境手动配置）
3. 都没有 → mock 模式（不阻断开发/测试）

密钥安全：
- 应用私钥只在服务端，绝不下发 Tauri 客户端
- .alipay-sandbox.json 已加入 .gitignore（由 sandbox_config.sh 确保）
- 不在日志/回复中输出密钥原文
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
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


def _load_sandbox_config() -> Optional[dict]:
    """读取 .alipay-sandbox.json（由 alipay-cli sandbox_config.sh 自动生成）。

    返回沙箱配置 dict 或 None（文件不存在时）。
    密钥值不输出到日志。
    """
    # 在 job_api 目录下查找
    config_path = Path(__file__).parent.parent / ".alipay-sandbox.json"
    if not config_path.exists():
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 沙箱配置结构：appIds[0] 含 appId/appPrivatePkcsKey/alipayPublicKey
        app_ids = data.get("appIds", [])
        if not app_ids:
            return None
        app = app_ids[0]
        app_id = app.get("appId", "")
        # Python 用 PKCS1 格式（appPrivatePkcsKey），Java 用 PKCS8（appPrivateKey）
        private_key = app.get("appPrivatePkcsKey") or app.get("appPrivateKey", "")
        public_key = app.get("alipayPublicKey", "")

        if not app_id or not private_key or not public_key:
            return None

        return {
            "app_id": str(app_id),
            # python-alipay-sdk 需要 PEM 格式头尾，沙箱返回的是原始密钥
            "private_key": _ensure_pem_header(private_key, is_private=True),
            "public_key": _ensure_pem_header(public_key, is_private=False),
            "sandbox_accounts": data.get("sandboxAccounts", {}),
            "sandbox_id": data.get("sandboxId", ""),
        }
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning(f"读取 .alipay-sandbox.json 失败: {e}")
        return None


def _ensure_pem_header(key: str, is_private: bool = True) -> str:
    """确保密钥有 PEM 头尾（python-alipay-sdk 需要 PEM 格式）。

    沙箱配置返回的密钥是原始字符串（无头尾），需要包装。
    已有头尾的密钥直接返回。
    """
    if "-----BEGIN" in key:
        return key.strip()
    if is_private:
        header = "-----BEGIN RSA PRIVATE KEY-----"
        footer = "-----END RSA PRIVATE KEY-----"
    else:
        header = "-----BEGIN PUBLIC KEY-----"
        footer = "-----END PUBLIC KEY-----"
    lines = [key[i:i + 64] for i in range(0, len(key), 64)]
    return f"{header}\n" + "\n".join(lines) + f"\n{footer}"


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

        # 优先级 1：尝试自动读取 .alipay-sandbox.json（沙箱自动配置）
        sandbox_config = _load_sandbox_config()

        if sandbox_config and self.settings.ALIPAY_ENV == "sandbox":
            self._app_id = sandbox_config["app_id"]
            self._private_key = sandbox_config["private_key"]
            self._public_key = sandbox_config["public_key"]
            self._sandbox_accounts = sandbox_config.get("sandbox_accounts", {})
            logger.info(
                f"AlipayService 从 .alipay-sandbox.json 自动加载沙箱配置"
                f"（appid={self._app_id[:8]}...）"
            )
        elif self.settings.ALIPAY_APP_ID and self.settings.ALIPAY_PRIVATE_KEY:
            # 优先级 2：使用 .env 中的配置（生产环境）
            self._app_id = self.settings.ALIPAY_APP_ID
            self._private_key = self.settings.ALIPAY_PRIVATE_KEY
            self._public_key = self.settings.ALIPAY_PUBLIC_KEY
            self._sandbox_accounts = {}
            logger.info(
                f"AlipayService 从 .env 加载配置"
                f"（env={self.settings.ALIPAY_ENV}, appid={self._app_id[:8]}...）"
            )
        else:
            # 优先级 3：mock 模式
            self._app_id = ""
            self._private_key = ""
            self._public_key = ""
            self._sandbox_accounts = {}
            logger.warning(
                "AlipayService 降级为 mock 模式："
                "未找到 .alipay-sandbox.json 且 .env 中 ALIPAY_APP_ID 未配置。"
                "运行 sandbox_config.sh ensure 可自动获取沙箱密钥。"
            )

        self.enabled = bool(
            _HAS_SDK and self._app_id and self._private_key and self._public_key
        )

        if self.enabled:
            self.client = AliPay(
                appid=self._app_id,
                app_notify_url=self.settings.ALIPAY_NOTIFY_URL,
                app_private_key_string=self._private_key,
                alipay_public_key_string=self._public_key,
                sign_type=self.settings.ALIPAY_SIGN_TYPE,
                debug=self.settings.ALIPAY_ENV == "sandbox",
            )
        else:
            self.client = None

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
            return "https://openhome.alipay.com/develop/sandbox/app"

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
            return True

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

    def get_sandbox_buyer_account(self) -> Optional[dict]:
        """获取沙箱买家测试账号信息（仅沙箱模式有值）。

        返回 {email, password, ...} 或 None。
        用户可用此账号在沙箱 APP 中完成测试支付。
        """
        if not self._sandbox_accounts:
            return None
        user_info = self._sandbox_accounts.get("user", {})
        if not user_info:
            return None
        return {
            "email": user_info.get("email", ""),
            "userName": user_info.get("userName", ""),
            "logonPassword": user_info.get("logonPassword", ""),
            "payPassword": user_info.get("payPassword", ""),
        }


# 模块级单例
alipay_service = AlipayService()
