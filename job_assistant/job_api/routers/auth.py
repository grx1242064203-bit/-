"""认证路由：注册 / 邮箱验证 / 登录 / refresh。

- POST /api/v1/auth/register {email, password} → {user_id, needs_verify}
- POST /api/v1/auth/verify-email {email, code} → {token, expires_at}
- POST /api/v1/auth/login {email, password} → {token, expires_at}
- POST /api/v1/auth/refresh (Bearer) → {token, expires_at}
- slowapi rate limit：每 IP 每分钟 5 次注册/验证/登录尝试
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from deps import get_current_user
from services.auth_service import (
    ConflictError,
    InvalidCodeError,
    InvalidCredentialsError,
    NotVerifiedError,
    login as svc_login,
    refresh as svc_refresh,
    register as svc_register,
    verify_email as svc_verify_email,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# 每 IP 维度的限流器；在 main.py 注册到 app.state.limiter 并挂 SlowAPIMiddleware。
limiter = Limiter(key_func=get_remote_address)

# 简易邮箱格式校验，避免引入 email-validator 依赖。
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterRequest(BaseModel):
    email: str = Field(pattern=_EMAIL_PATTERN)
    password: str = Field(min_length=6, max_length=128)


class VerifyEmailRequest(BaseModel):
    email: str = Field(pattern=_EMAIL_PATTERN)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class LoginRequest(BaseModel):
    email: str = Field(pattern=_EMAIL_PATTERN)
    password: str = Field(min_length=1, max_length=128)


class RegisterResponse(BaseModel):
    user_id: str
    needs_verify: bool


class TokenResponse(BaseModel):
    token: str
    expires_at: int


@router.post("/register", response_model=RegisterResponse)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest) -> RegisterResponse:
    """注册新用户（未验证）或为未验证老用户重发验证码。"""
    try:
        result = await svc_register(body.email, body.password)
    except ConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    return RegisterResponse(**result)


@router.post("/verify-email", response_model=TokenResponse)
@limiter.limit("5/minute")
async def verify_email(request: Request, body: VerifyEmailRequest) -> TokenResponse:
    """校验验证码并签发 JWT。"""
    try:
        result = await svc_verify_email(body.email, body.code)
    except InvalidCodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    return TokenResponse(**result)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest) -> TokenResponse:
    """邮箱密码登录，签发 JWT。"""
    try:
        result = await svc_login(body.email, body.password)
    except NotVerifiedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(**result)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(current_user: dict = Depends(get_current_user)) -> TokenResponse:
    """刷新 token（需 Bearer）。"""
    result = await svc_refresh(current_user["id"])
    return TokenResponse(**result)
