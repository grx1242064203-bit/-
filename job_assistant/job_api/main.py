"""Offer搭子 云端 API 入口 (FastAPI)。

提供 /health 健康检查、CORS 中间件、配置加载、/api/v1 业务路由（auth）。
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from contextlib import asynccontextmanager

# 项目根目录的 user_matcher.py / scorer.py / job_db.py / models.py 提供
# 岗位推荐核心算法。但根目录 models.py 与 job_api/models/ 包同名,直接把根目录
# 加 sys.path 会遮蔽 job_api/models 包(导致 `from models import init_all_db` 失败)。
# 解决方案:把根目录 models.py 单独加载为别名 `jobseeker_models`,user_matcher.py
# 和 scorer.py 用 `from jobseeker_models import UserProfile` 引用。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.append(_PROJECT_ROOT)  # append 末尾,不抢占 job_api/models/ 包

# 把根目录 models.py 显式加载为 jobseeker_models 别名,避免与 job_api/models/ 包冲突
_root_models_path = os.path.join(_PROJECT_ROOT, "models.py")
if os.path.exists(_root_models_path) and "jobseeker_models" not in sys.modules:
    _spec = importlib.util.spec_from_file_location("jobseeker_models", _root_models_path)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    sys.modules["jobseeker_models"] = _mod

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from config import get_settings
from models import init_all_db
from models.user import mark_admin_by_email
from routers.admin import router as admin_router
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
from routers.payments import router as payments_router
from routers.resume_profiles import router as resume_profiles_router
from services.sync_service import DatabaseCorruptedError

settings = get_settings()


def _warn_config_issues(s) -> None:
    """启动时检查关键配置，缺失项打印警告（不阻断启动，兼容测试版）。

    生产部署必须通过环境变量覆盖所有 ⚠️ 项；测试版可继续运行但功能受限。
    """
    issues = []
    if s.JWT_SECRET == "change-me-in-prod":
        issues.append(
            "JWT_SECRET 仍是默认值，任何人可伪造登录令牌。"
            '生成方法：python -c "import secrets;print(secrets.token_urlsafe(32))"'
        )
    if not s.EMAIL_ENCRYPTION_KEY:
        issues.append(
            "EMAIL_ENCRYPTION_KEY 未配置，IMAP 邮箱密码将用进程临时密钥加密，"
            "重启后无法解密（邮箱账户功能失效）。"
            '生成方法：python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"'
        )
    if s.LLM_DAILY_LIMIT < 0:
        issues.append(
            f"LLM_DAILY_LIMIT={s.LLM_DAILY_LIMIT}（不限制），"
            "用户可无限触发 DeepSeek 调用，账单可能失控。建议设为 5-20。"
        )
    if not s.REMOTE_DB_BASE_URL.startswith("https://"):
        issues.append(
            f"REMOTE_DB_BASE_URL={s.REMOTE_DB_BASE_URL} 非 HTTPS，"
            "远程库同步可被中间人投毒。生产必须改 HTTPS。"
        )
    if not s.DEEPSEEK_API_KEY:
        issues.append("DEEPSEEK_API_KEY 未配置，简历解析/公司尽调功能不可用。")
    if not s.RESEND_API_KEY:
        issues.append("RESEND_API_KEY 未配置，邮箱验证码无法发送（注册/登录功能不可用）。")
    if issues:
        print("=" * 60)
        print("[job_api] ⚠️ 配置健康检查发现问题（测试版可继续，生产部署必须修复）：")
        for i, msg in enumerate(issues, 1):
            print(f"  {i}. {msg}")
        print("=" * 60)


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
    # 启动配置健康检查（警告级别，不阻断启动）
    _warn_config_issues(settings)
    # 启动时把 ADMIN_EMAIL 对应用户标记为管理员（私域获客场景：管理员先正常注册一次）
    if settings.ADMIN_EMAIL:
        ok = await mark_admin_by_email(settings.ADMIN_EMAIL)
        if ok:
            print(f"[job_api] 已将 {settings.ADMIN_EMAIL} 标记为管理员")
        else:
            print(
                f"[job_api] ⚠️ ADMIN_EMAIL={settings.ADMIN_EMAIL} 尚未注册，"
                "请先用该邮箱注册一次再重启服务以获得管理员权限"
            )
    yield


app = FastAPI(
    title="Offer搭子 API",
    version="0.1.0",
    description="Offer搭子桌面工作台云端 API",
    lifespan=lifespan,
)

# ============================================================================
# 开发模式鉴权绕过（仅沙箱/dev 环境用，绝不可进生产）
# 设 DEV_BYPASS_AUTH=1 时，所有 Depends(get_current_user) 返回固定 mock user，
# 跳过 JWT 校验。用于沙箱/CI 环境无 Resend 邮箱验证码时的端到端测试。
# 生产部署只要不设此环境变量即完全不生效（dependency_overrides 为空 dict）。
# ============================================================================
import os as _os

if _os.environ.get("DEV_BYPASS_AUTH") == "1":
    from deps import get_current_user as _get_current_user

    async def _mock_current_user() -> dict:
        return {
            "id": "dev-user-1",
            "user_id": "dev-user-1",
            "email": "dev@sandbox.local",
            "is_verified": True,
            "is_admin": True,
        }

    app.dependency_overrides[_get_current_user] = _mock_current_user
    print("=" * 60)
    print("[job_api] ⚠️ DEV_BYPASS_AUTH=1 已启用：所有请求跳过 JWT 校验")
    print("         仅沙箱/CI 环境；生产部署切勿设置此环境变量")
    print("=" * 60)


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

# ProxyHeadersMiddleware：从 X-Forwarded-Proto 等头还原真实 scheme/host/port。
# 否则 FastAPI 的 redirect_slashes 会把 https://.../download/ 重定向到 http://.../download。
app.add_middleware(ProxyHeadersMiddleware)

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
app.include_router(payments_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")


# ====== 网页版管理后台 ======
# /admin 提供用户管理界面（登录、列表、建号、停用、删除等）。
# 所有数据操作走 /api/v1/admin/* 接口，需要管理员 JWT。
from admin_console import ADMIN_CONSOLE_HTML  # noqa: E402


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_console_page() -> str:
    """网页版管理后台（HTML，前端自行调 /api/v1/auth/login 和 /api/v1/admin/*）。"""
    return ADMIN_CONSOLE_HTML


# ====== 桌面端安装包下载页 ======
# 用户把 .dmg / .exe / .msi 上传到 data/downloads/ 目录后，
# 访问 /download 即可看到下载页。
# 不需要鉴权（任何人都能下载，但需要管理员上传文件）。

from pathlib import Path  # noqa: E402

from fastapi.responses import FileResponse  # noqa: E402

DOWNLOADS_DIR = Path(settings.DATA_DIR) / "downloads"


def _list_installers() -> list[dict]:
    """扫描 data/downloads/ 目录下所有安装包文件。"""
    if not DOWNLOADS_DIR.exists():
        return []
    installers = []
    for f in sorted(DOWNLOADS_DIR.iterdir(), key=lambda x: -x.stat().st_mtime):
        if f.is_file() and f.suffix.lower() in {".dmg", ".exe", ".msi", ".appimage", ".deb"}:
            size_mb = f.stat().st_size / (1024 * 1024)
            installers.append({
                "name": f.name,
                "size_mb": round(size_mb, 1),
                "mtime": f.stat().st_mtime,
                "url": f"/download/file/{f.name}",
            })
    return installers


@app.get("/download", response_class=HTMLResponse, include_in_schema=False)
async def download_page() -> str:
    """桌面端安装包下载页（HTML，无需鉴权）。"""
    installers = _list_installers()
    if not installers:
        items_html = (
            '<div style="text-align:center;padding:60px 20px;color:#888;">'
            '<p style="font-size:18px;margin-bottom:8px;">安装包还在准备中</p>'
            "<p>请稍后再访问，或联系管理员</p></div>"
        )
    else:
        # 平台元信息：图标、适用人群、CPU 架构
        # arch 含义: arm = Apple Silicon (M1/M2/M3), x64 = Intel/AMD
        PLATFORM_META = {
            "macOS ARM": {
                "icon": "",
                "arch": "Apple Silicon · M1/M2/M3 芯片",
                "audience": "2020 年及以后买的 Mac（M 系列芯片）",
                "tip": "如果你是近 4 年的 Mac，选这个",
            },
            "macOS Intel": {
                "icon": "",
                "arch": "Intel 芯片",
                "audience": "2020 年以前买的 Mac，或老款 MacBook/Air",
                "tip": "不清楚自己 Mac 是哪种？右键「访达 → 关于本机」看芯片",
            },
            "Windows": {
                "icon": "🪟",
                "arch": "x64 · 64 位",
                "audience": "Windows 10 / Windows 11 的电脑（绝大多数 PC）",
                "tip": "32 位老电脑不支持，请升级系统或换设备",
            },
            "Linux": {
                "icon": "🐧",
                "arch": "x64 · 64 位",
                "audience": "Ubuntu / Debian / Fedora 等主流 Linux 发行版",
                "tip": ".deb 适合 Ubuntu/Debian；.AppImage 适合所有 Linux（无需安装）",
            },
            "未知": {
                "icon": "📦",
                "arch": "",
                "audience": "",
                "tip": "联系管理员确认",
            },
        }

        def _classify(name: str) -> str:
            n = name.lower()
            # Mac ARM vs Intel: 文件名里通常含 aarch64 / arm64
            if n.endswith(".dmg"):
                if "aarch64" in n or "arm64" in n or "arm" in n:
                    return "macOS ARM"
                return "macOS Intel"
            if n.endswith((".exe", ".msi")):
                return "Windows"
            if n.endswith((".appimage", ".deb", ".rpm")):
                return "Linux"
            return "未知"

        items = []
        for it in installers:
            plat = _classify(it["name"])
            meta = PLATFORM_META[plat]
            tip_html = (
                f'<div class="tip">💡 {meta["tip"]}</div>'
                if meta["tip"] else ""
            )
            audience_html = (
                f'<div class="audience">适用：{meta["audience"]}</div>'
                if meta["audience"] else ""
            )
            arch_html = (
                f'<div class="arch">{meta["arch"]}</div>'
                if meta["arch"] else ""
            )
            items.append(
                f'<a href="{it["url"]}" class="card card-{plat.lower().replace(" ", "-")}">'
                f'<div class="card-head">'
                f'<span class="icon">{meta["icon"]}</span>'
                f'<span class="title">{plat}</span>'
                f'<span class="size">{it["size_mb"]} MB</span>'
                "</div>"
                f'<div class="filename">{it["name"]}</div>'
                f'{arch_html}{audience_html}{tip_html}'
                '<div class="dl">⬇ 点击下载</div>'
                "</a>"
            )
        items_html = "".join(items)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Offer搭子 - 下载</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif;
       background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
       min-height: 100vh; margin: 0; padding: 20px;
       display: flex; align-items: center; justify-content: center; }}
.container {{ max-width: 720px; width: 100%; }}
h1 {{ color: white; text-align: center; margin-bottom: 8px;
     font-size: 32px; font-weight: 600; }}
.subtitle {{ color: rgba(255,255,255,0.8); text-align: center;
           margin-bottom: 8px; font-size: 14px; }}
.hint {{ background: rgba(255,255,255,0.15); border-radius: 8px;
        padding: 12px 16px; margin: 0 auto 28px; max-width: 560px;
        color: rgba(255,255,255,0.95); font-size: 13px; line-height: 1.6; }}
.hint b {{ color: #ffe88a; }}
.grid {{ display: grid; gap: 14px; }}
.card {{ display: block; background: white; border-radius: 12px;
        padding: 18px 20px; text-decoration: none; color: #333;
        transition: transform 0.15s, box-shadow 0.15s;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
.card:hover {{ transform: translateY(-2px); box-shadow: 0 8px 20px rgba(0,0,0,0.2); }}
.card-head {{ display: flex; align-items: center; gap: 10px;
            margin-bottom: 8px; }}
.card .icon {{ font-size: 22px; }}
.card .title {{ font-size: 17px; font-weight: 600; color: #1a1a1a; flex: 1; }}
.card .size {{ color: #888; font-size: 13px; font-weight: 500;
             background: #f1f1f4; padding: 3px 10px; border-radius: 12px; }}
.card .filename {{ color: #999; font-size: 12px; word-break: break-all;
                  margin-bottom: 8px; font-family: ui-monospace, "SF Mono", monospace; }}
.card .arch {{ color: #666; font-size: 13px; margin-bottom: 4px; font-weight: 500; }}
.card .audience {{ color: #555; font-size: 13px; margin-bottom: 6px; line-height: 1.5; }}
.card .tip {{ color: #7a5a8a; font-size: 12px; padding: 6px 10px;
            background: #f6f3fa; border-radius: 6px; margin-bottom: 8px; line-height: 1.5; }}
.card .dl {{ color: #667eea; font-size: 14px; margin-top: 4px; font-weight: 600;
           text-align: center; padding: 8px; border-top: 1px solid #f0f0f3; }}
.empty {{ text-align: center; color: #888; padding: 60px 20px; }}
</style>
</head>
<body>
<div class="container">
<h1>Offer搭子</h1>
<p class="subtitle">27 届校招工作台 · 桌面端下载</p>
<div class="hint">
  📌 <b>不知道选哪个？</b> Mac 用户先看「关于本机 → 芯片」是 Apple 还是 Intel；
  Windows 用户直接下 <b>.exe</b>；Linux 用户优先 <b>.AppImage</b>（无需安装，双击即用）。
</div>
<div class="grid">
{items_html}
</div>
</div>
</body>
</html>"""


@app.get("/download/file/{filename}", include_in_schema=False)
async def download_file(filename: str) -> FileResponse:
    """下载具体安装包文件。防目录穿越攻击。"""
    # 防 ../../etc/passwd 等路径穿越
    if "/" in filename or "\\" in filename or ".." in filename:
        from fastapi import HTTPException, status as _st
        raise HTTPException(_st.HTTP_400_BAD_REQUEST, "非法文件名")
    file_path = DOWNLOADS_DIR / filename
    if not file_path.is_file():
        from fastapi import HTTPException, status as _st
        raise HTTPException(_st.HTTP_404_NOT_FOUND, "文件不存在")
    return FileResponse(file_path, filename=filename)
