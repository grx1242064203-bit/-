"""认证路由：注册 / 邮箱验证 / 登录 / refresh。

- POST /api/v1/auth/register {email, password} → {user_id, needs_verify}
- POST /api/v1/auth/verify-email {email, code} → {token, expires_at}
- POST /api/v1/auth/login {email, password} → {token, expires_at}
- POST /api/v1/auth/refresh (Bearer) → {token, expires_at}
- slowapi rate limit：每 IP 每分钟限流(通过环境变量 AUTH_RATE_LIMIT_* 配置)。
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from slowapi import Limiter

from config import get_settings
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

_settings = get_settings()


def _get_client_ip(request: Request) -> str:
    """提取客户端 IP 作为限流 key。

    优先 X-Forwarded-For(反向代理场景),其次 request.client.host,
    都拿不到时兜底 "unknown"(避免 request.client 为 None 时崩溃)。
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        # X-Forwarded-For 可能含多个 IP,取第一个(真实客户端)
        return xff.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


# 每 IP 维度的限流器；在 main.py 注册到 app.state.limiter 并挂 SlowAPIMiddleware。
limiter = Limiter(key_func=_get_client_ip)

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
@limiter.limit(_settings.AUTH_RATE_LIMIT_REGISTER)
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
@limiter.limit(_settings.AUTH_RATE_LIMIT_VERIFY)
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
@limiter.limit(_settings.AUTH_RATE_LIMIT_LOGIN)
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
