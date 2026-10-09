"""Offer搭子 API 配置 (Pydantic Settings)。

环境变量通过 .env / 进程注入，缺失项回退到默认值。
密钥类字段默认留空或占位，生产部署必须通过环境变量覆盖。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM（简历解析 / JD 评分）
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    # 每用户每日 LLM 调用配额上限(含简历解析 / 补充分析 / 公司尽调)。
    # 设为 0 表示禁用(不允许任何调用);设为负数(-1)表示不限制。
    # 生产部署通过环境变量 LLM_DAILY_LIMIT 覆盖,默认 -1 不限制。
    LLM_DAILY_LIMIT: int = -1

    # 认证接口限流(每 IP 每分钟),slowapi 字符串格式如 "20/minute"。
    # 原 5/min 过严,正常使用(多设备登录/token 刷新/重试)会触发。
    # 生产部署通过环境变量覆盖。
    AUTH_RATE_LIMIT_LOGIN: str = "20/minute"
    AUTH_RATE_LIMIT_REGISTER: str = "10/minute"
    AUTH_RATE_LIMIT_VERIFY: str = "10/minute"

    # JWT 鉴权
    JWT_SECRET: str = "change-me-in-prod"
    JWT_ALG: str = "HS256"
    JWT_EXPIRE_HOURS: int = 168

    # 邮件（Resend）
    RESEND_API_KEY: str = ""
    # 发件人地址：生产环境用自有域名（如 noreply@yourdomain.com），需在 Resend 控制台验证域名
    # 未验证域名时用 Resend 沙箱地址 onboarding@resend.dev（仅能发到注册 Resend 的邮箱）
    RESEND_FROM_EMAIL: str = "onboarding@resend.dev"

    # 管理员邮箱：启动时自动把这个邮箱的用户标记为 is_admin=1
    # 用于私域获客场景：你用自己的邮箱注册一次后，从此能访问管理后台
    ADMIN_EMAIL: str = ""

    # 邮箱密码加密密钥（Fernet），生产环境必须通过环境变量覆盖
    EMAIL_ENCRYPTION_KEY: str = ""

    # 数据存储
    DATA_DIR: Path = Path("../data")
    JOBS_DB_PATH: Path = Path("../data/jobs.db")
    AUTH_DB_PATH: Path = Path("../data/auth.db")

    # 远程主数据库（服务器）：用于从服务器拉取最新 jobs.db
    REMOTE_DB_BASE_URL: str = "http://47.250.216.165"
    REMOTE_DB_INFO_PATH: str = "/api/db/info"
    REMOTE_DB_DOWNLOAD_PATH: str = "/api/db/download"

    # CORS 允许源（开发期默认允许所有来源）
    CORS_ORIGINS: List[str] = ["*"]

    # ====================================================================
    # Vibe Pay 基础收款能力（支付宝 alipay.trade.page.pay 网页支付）
    # 个人开发者可用，有沙箱环境。
    # 沙箱网关: https://openapi-sandbox.dl.alipaydev.com/gateway.do
    # 生产网关: https://openapi.alipay.com/gateway.do
    # ====================================================================
    # 环境开关: "sandbox"（沙箱，默认）/ "production"（生产）
    ALIPAY_ENV: str = "sandbox"
    # 应用 ID（沙箱/生产不同，由开放平台分配）
    ALIPAY_APP_ID: str = ""
    # 应用私钥（PKCS1 格式，非 Java；用支付宝官方密钥工具生成）
    ALIPAY_PRIVATE_KEY: str = ""
    # 支付宝公钥（由开放平台分配，用于验签异步通知）
    ALIPAY_PUBLIC_KEY: str = ""
    # 异步通知 URL（公网 HTTPS，由支付宝服务端 POST 调用）
    # 沙箱可先用 https://zhaopin-helper.xyz/api/v1/payments/notify
    ALIPAY_NOTIFY_URL: str = "https://zhaopin-helper.xyz/api/v1/payments/notify"
    # 同步回跳 URL（GET，不可信，仅用于 UX；前端路由接管）
    ALIPAY_RETURN_URL: str = "https://zhaopin-helper.xyz/pay-verify"
    # 签名算法：固定 RSA2（RSA-SHA256）
    ALIPAY_SIGN_TYPE: str = "RSA2"
    # 商品目录（可被 .env 覆盖；默认两种付费模式）
    # 月度试用 ¥9.9 / 永久买断 ¥99（10× 月度，可在 .env 调整）
    ALIPAY_PRODUCT_TRIAL_CENTS: int = 990
    ALIPAY_PRODUCT_TRIAL_DAYS: int = 30
    ALIPAY_PRODUCT_LIFETIME_CENTS: int = 9900

    @property
    def sqlite_url(self) -> str:
        return f"sqlite:///{self.JOBS_DB_PATH}"


@lru_cache
def get_settings() -> Settings:
    """单例 Settings 工厂，进程内缓存（FastAPI 依赖注入与启动钩子共用同一实例）。"""
    return Settings()


# 兼容旧入口：导入即用实例
settings = get_settings()

# 启动时确保数据目录存在（best-effort，不阻断导入）。
try:
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass
