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
    # 当前默认 -1 = 不限制,后续如需限制,通过环境变量 LLM_DAILY_LIMIT 设置正整数即可。
    LLM_DAILY_LIMIT: int = -1

    # JWT 鉴权
    JWT_SECRET: str = "change-me-in-prod"
    JWT_ALG: str = "HS256"
    JWT_EXPIRE_HOURS: int = 168

    # 邮件（Resend）
    RESEND_API_KEY: str = ""

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
