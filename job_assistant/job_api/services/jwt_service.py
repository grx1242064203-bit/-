"""JWT 签发与校验（python-jose, HS256）。

- create_access_token(user_id) → JWT（sub=user_id，exp=JWT_EXPIRE_HOURS 后）
- verify_token(token) → payload dict 或 None
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

from config import get_settings


def create_access_token(user_id: str) -> str:
    """签发 JWT：sub=user_id，iat=now，exp=now+JWT_EXPIRE_HOURS。"""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.JWT_EXPIRE_HOURS)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def verify_token(token: str) -> Optional[dict]:
    """校验 JWT。返回 payload dict 或 None（任何失败均返回 None）。"""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
    except JWTError:
        return None


def get_expires_at() -> int:
    """返回当前签发 token 的过期 unix 时间戳（秒）。"""
    settings = get_settings()
    return int(
        (
            datetime.now(timezone.utc)
            + timedelta(hours=settings.JWT_EXPIRE_HOURS)
        ).timestamp()
    )
