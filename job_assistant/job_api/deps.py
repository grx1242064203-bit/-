"""FastAPI 依赖注入：从 Authorization 头解析 JWT → 当前用户 dict。

- get_current_user：Bearer token → user dict（含 user_id/id/email/is_verified）
  - 返回字段同时包含 ``user_id`` 与 ``id``（同值），兼容 T4 路由的 ``user["user_id"]``
    访问模式与 T3 内部 ``user["id"]`` 访问模式
  - 不返回 password_hash（避免敏感字段泄漏到路由层）
  - 检查 is_active：被管理员吊销 (is_active=0) 的用户即使 token 未过期也拒绝访问
- get_current_admin：在 get_current_user 基础上额外要求 is_admin=1，否则 403
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from models.user import get_user_by_id, init_db
from services.jwt_service import verify_token

bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """从 Authorization: Bearer <token> 解析用户。失败 → 401。"""
    # 确保 users 表存在（首次启动或切换数据目录时兜底）。
    await init_db()
    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的访问令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="访问令牌缺少用户标识",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被删除",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 吊销检查：被管理员 is_active=0 的用户拒绝访问
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被停用，请联系管理员",
        )
    # 脱敏返回：不含 password_hash；同时暴露 user_id（T4 兼容）与 id（规范字段）
    return {
        "id": user["id"],
        "user_id": user["id"],
        "email": user["email"],
        "is_verified": user["is_verified"],
        "is_admin": user.get("is_admin", False),
    }


async def get_current_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """要求当前用户是管理员（is_admin=1），否则 403。

    用于管理后台路由的鉴权。
    """
    if not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user
