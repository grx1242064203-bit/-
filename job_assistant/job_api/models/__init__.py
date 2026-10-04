"""Offer搭子 API 数据访问层（SQLite + aiosqlite）。"""
from models import (
    application,
    company_due_diligence,
    email,
    email_account,
    schedule,
    user,
)


async def init_all_db() -> None:
    """初始化所有表（幂等，CREATE TABLE IF NOT EXISTS）。"""
    await user.init_db()
    await application.init_db()
    await company_due_diligence.init_db()
    await email_account.init_db()
    await email.init_db()
    await schedule.init_db()
