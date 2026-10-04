"""Offer搭子 云端 API 入口 (FastAPI)。

提供 /health 健康检查、CORS 中间件、配置加载、/api/v1 业务路由（auth）。
"""
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from config import get_settings
from models import init_all_db
from routers.auth import limiter as auth_limiter
from routers.auth import router as auth_router
from routers.db_sync import router as db_sync_router
from routers.emails import router as emails_router
from routers.health import router as health_router
from routers.llm import router as llm_router
from routers.schedules import router as schedules_router
from routers.sync import router as sync_router
from routers.applications import router as applications_router
from routers.jobs import router as jobs_router
from routers.resume_profiles import router as resume_profiles_router
from services.sync_service import DatabaseCorruptedError

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化所有数据表（幂等）
    await init_all_db()
    # 启动时打印配置摘要（脱敏：仅暴露非敏感字段与密钥是否已设置）
    summary = {
        "DEEPSEEK_BASE_URL": settings.DEEPSEEK_BASE_URL,
        "JWT_ALG": settings.JWT_ALG,
        "JWT_EXPIRE_HOURS": settings.JWT_EXPIRE_HOURS,
        "DATA_DIR": str(settings.DATA_DIR),
        "JOBS_DB_PATH": str(settings.JOBS_DB_PATH),
        "CORS_ORIGINS": settings.CORS_ORIGINS,
        "DEEPSEEK_API_KEY_SET": bool(settings.DEEPSEEK_API_KEY),
        "JWT_SECRET_SET": settings.JWT_SECRET != "change-me-in-prod",
        "RESEND_API_KEY_SET": bool(settings.RESEND_API_KEY),
    }
    print(f"[job_api] 启动配置摘要: {json.dumps(summary, ensure_ascii=False)}")
    yield


app = FastAPI(
    title="Offer搭子 API",
    version="0.1.0",
    description="Offer搭子桌面工作台云端 API",
    lifespan=lifespan,
)

# slowapi rate limit：注册 limiter 到 app.state + 挂全局中间件 + 异常处理
app.state.limiter = auth_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(DatabaseCorruptedError)
async def database_corrupted_handler(
    request: Request, exc: DatabaseCorruptedError
) -> JSONResponse:
    """本地 jobs.db 损坏时返回 503 + 清晰的修复提示。

    前端 SyncIndicator 检测到该状态码后，应引导用户点击「重新拉取数据库」
    （POST /api/v1/sync/pull-db），而非简单重试数据接口。
    """
    return JSONResponse(
        status_code=503,
        content={
            "error": exc.detail,
            "code": "DATABASE_CORRUPTED",
            "suggestion": "点击同步按钮重新从服务器拉取数据库",
        },
    )

# CORS 中间件：开发期允许所有来源时禁用 credentials（兼容 CORS 规范）
allow_credentials = "*" not in settings.CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 健康检查路由（根路径暴露，无前缀）
app.include_router(health_router)

# /api/v1 业务路由
app.include_router(auth_router, prefix="/api/v1")
app.include_router(llm_router, prefix="/api/v1")
app.include_router(sync_router, prefix="/api/v1")
app.include_router(db_sync_router, prefix="/api/v1")
app.include_router(applications_router, prefix="/api/v1")
app.include_router(emails_router, prefix="/api/v1")
app.include_router(schedules_router, prefix="/api/v1")
app.include_router(resume_profiles_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
