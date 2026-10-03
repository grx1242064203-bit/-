"""FastAPI 依赖注入：从 Authorization 头解析 JWT → 当前用户 dict。

- get_current_user：Bearer token → user dict（含 user_id/id/email/is_verified）
  - 返回字段同时包含 ``user_id`` 与 ``id``（同值），兼容 T4 路由的 ``user["user_id"]``
    访问模式与 T3 内部 ``user["id"]`` 访问模式
  - 不返回 password_hash（避免敏感字段泄漏到路由层）
- 订阅校验暂时跳过（后续 T 加）
"""
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from models.user import get_user_by_id
from services.jwt_service import verify_token

bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """从 Authorization: Bearer <token> 解析用户。失败 → 401。"""
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
    # 脱敏返回：不含 password_hash；同时暴露 user_id（T4 兼容）与 id（规范字段）
    return {
        "id": user["id"],
        "user_id": user["id"],
        "email": user["email"],
        "is_verified": user["is_verified"],
    }
