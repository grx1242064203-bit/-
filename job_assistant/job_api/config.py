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
        # 用模块所在目录的 .env(而非 CWD), 避免 uvicorn 启动目录不同导致 .env 找不到
        env_file=str(Path(__file__).resolve().parent / ".env"),
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
