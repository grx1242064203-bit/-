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
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

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
app.include_router(admin_router, prefix="/api/v1")


# ====== 桌面端安装包下载页 ======
# 用户把 .dmg / .exe / .msi 上传到 data/downloads/ 目录后，
# 访问 /download 即可看到下载页。
# 不需要鉴权（任何人都能下载，但需要管理员上传文件）。

from pathlib import Path  # noqa: E402

from fastapi.responses import HTMLResponse, FileResponse  # noqa: E402

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
    """Offer搭子营销+下载页（像素漫画风，无需鉴权）。"""
    installers = _list_installers()

    PLATFORM_META = {
        "macOS ARM": {"icon": "🍎", "arch": "Apple Silicon · M1/M2/M3", "audience": "2020 年及以后买的 Mac", "tip": "近 4 年的 Mac 选这个"},
        "macOS Intel": {"icon": "🍎", "arch": "Intel 芯片", "audience": "2020 年以前买的 Mac", "tip": "「关于本机」看芯片是 Apple 还是 Intel"},
        "Windows": {"icon": "🪟", "arch": "x64 · 64 位", "audience": "Windows 10 / Windows 11", "tip": "优先下 .exe 安装包"},
        "Linux": {"icon": "🐧", "arch": "x64 · 64 位", "audience": "Ubuntu / Debian / Fedora", "tip": ".AppImage 无需安装，双击即用"},
        "未知": {"icon": "📦", "arch": "", "audience": "", "tip": "联系管理员"},
    }

    def _classify(name: str) -> str:
        n = name.lower()
        if n.endswith(".dmg"):
            if "aarch64" in n or "arm64" in n or "arm" in n:
                return "macOS ARM"
            return "macOS Intel"
        if n.endswith((".exe", ".msi")):
            return "Windows"
        if n.endswith((".appimage", ".deb", ".rpm")):
            return "Linux"
        return "未知"

    if installers:
        items = []
        for it in installers:
            plat = _classify(it["name"])
            meta = PLATFORM_META[plat]
            tip_html = f'<div class="dl-tip">💡 {meta["tip"]}</div>' if meta["tip"] else ""
            audience_html = f'<div class="dl-audience">适用：{meta["audience"]}</div>' if meta["audience"] else ""
            arch_html = f'<div class="dl-arch">{meta["arch"]}</div>' if meta["arch"] else ""
            items.append(
                f'<a href="{it["url"]}" class="dl-card">'
                f'<div class="dl-head"><span class="dl-icon">{meta["icon"]}</span>'
                f'<span class="dl-title">{plat}</span>'
                f'<span class="dl-size">{it["size_mb"]} MB</span></div>'
                f'<div class="dl-filename">{it["name"]}</div>'
                f'{arch_html}{audience_html}{tip_html}'
                '<div class="dl-btn">⬇ 点击下载</div></a>'
            )
        items_html = "".join(items)
    else:
        items_html = '<div style="text-align:center;padding:60px 20px;color:#888;"><p style="font-size:18px;margin-bottom:8px;">安装包还在准备中</p><p>请稍后再访问</p></div>'

    return DOWNLOAD_PAGE_HTML.replace("{items_html}", items_html)


DOWNLOAD_PAGE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Offer搭子 — 全网最自动化的秋招工具</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #FFF8E7; --bg-alt: #FFF3D6; --dark: #1A1A2E;
  --gold: #FFD700; --orange: #FF6B35; --pink: #E94560;
  --green: #4CAF50; --card: #FFFFFF; --muted: #6B7280;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif; background:var(--bg); color:var(--dark); overflow-x:hidden; line-height:1.6; }

nav { position:fixed; top:0; left:0; right:0; z-index:100; background:var(--dark); border-bottom:4px solid var(--gold); padding:0 24px; display:flex; align-items:center; justify-content:space-between; height:64px; }
.nav-logo { display:flex; align-items:center; gap:12px; }
.nav-logo svg { width:36px; height:36px; }
.nav-logo span { font-family:'Press Start 2P',monospace; font-size:14px; color:var(--gold); letter-spacing:1px; }
.nav-links { display:flex; gap:28px; align-items:center; }
.nav-links a { color:#FFF; text-decoration:none; font-size:14px; font-weight:500; transition:color 0.2s; }
.nav-links a:hover { color:var(--gold); }
.nav-download { background:var(--gold); color:var(--dark); padding:8px 20px; border:3px solid var(--dark); font-weight:700; font-size:13px; text-decoration:none; box-shadow:3px 3px 0 var(--dark); transition:all 0.15s; }
.nav-download:hover { transform:translate(1px,1px); box-shadow:2px 2px 0 var(--dark); }
@media(max-width:768px) { .nav-links { display:none; } }

.hero { min-height:calc(100svh - 64px); margin-top:64px; display:flex; align-items:center; justify-content:center; background:var(--bg); position:relative; overflow:hidden; padding:40px 24px; }
.hero::before { content:''; position:absolute; inset:0; background-image:radial-gradient(circle at 20% 50%, rgba(255,215,0,0.08) 0%, transparent 50%),radial-gradient(circle at 80% 30%, rgba(255,107,53,0.06) 0%, transparent 50%); pointer-events:none; }
.hero::after { content:''; position:absolute; inset:0; background-image:linear-gradient(rgba(26,26,46,0.03) 1px, transparent 1px),linear-gradient(90deg, rgba(26,26,46,0.03) 1px, transparent 1px); background-size:32px 32px; pointer-events:none; }
.hero-content { max-width:720px; text-align:center; position:relative; z-index:1; }
.hero-logo { width:120px; height:120px; margin:0 auto 24px; filter:drop-shadow(0 8px 0 var(--dark)) drop-shadow(0 0 20px rgba(255,215,0,0.3)); animation:bounce 3s ease-in-out infinite; }
@keyframes bounce { 0%,100% { transform:translateY(0); } 50% { transform:translateY(-8px); } }
.hero-tag { display:inline-block; background:var(--dark); color:var(--gold); font-family:'Press Start 2P',monospace; font-size:10px; padding:8px 16px; margin-bottom:20px; letter-spacing:1px; }
.hero h1 { font-size:clamp(36px,7vw,64px); font-weight:900; line-height:1.1; margin-bottom:20px; letter-spacing:-1px; }
.hero h1 .accent { color:var(--orange); position:relative; display:inline-block; }
.hero h1 .accent::after { content:''; position:absolute; bottom:4px; left:0; right:0; height:8px; background:var(--gold); z-index:-1; opacity:0.5; }
.hero p { font-size:clamp(15px,2.5vw,18px); color:var(--muted); margin-bottom:32px; max-width:480px; margin-left:auto; margin-right:auto; }
.hero-cta { display:flex; gap:16px; justify-content:center; flex-wrap:wrap; }
.btn-primary { background:var(--gold); color:var(--dark); border:4px solid var(--dark); padding:14px 36px; font-size:16px; font-weight:700; text-decoration:none; box-shadow:6px 6px 0 var(--dark); transition:all 0.15s; display:inline-flex; align-items:center; gap:8px; }
.btn-primary:hover { transform:translate(3px,3px); box-shadow:3px 3px 0 var(--dark); }
.btn-secondary { background:var(--dark); color:#FFF; border:4px solid var(--dark); padding:14px 36px; font-size:16px; font-weight:700; text-decoration:none; box-shadow:6px 6px 0 var(--orange); transition:all 0.15s; display:inline-flex; align-items:center; gap:8px; }
.btn-secondary:hover { transform:translate(3px,3px); box-shadow:3px 3px 0 var(--orange); }
.hero-stats { display:flex; gap:40px; justify-content:center; margin-top:48px; flex-wrap:wrap; }
.hero-stat { text-align:center; }
.hero-stat .num { font-family:'Press Start 2P',monospace; font-size:24px; color:var(--dark); }
.hero-stat .label { font-size:12px; color:var(--muted); margin-top:6px; }

section { position:relative; }
.section-pad { padding:80px 24px; }
.section-inner { max-width:1080px; margin:0 auto; }
.section-label { display:inline-block; background:var(--dark); color:var(--gold); font-family:'Press Start 2P',monospace; font-size:10px; padding:6px 14px; margin-bottom:16px; letter-spacing:1px; }
.section-title { font-size:clamp(28px,5vw,44px); font-weight:900; line-height:1.15; margin-bottom:16px; letter-spacing:-0.5px; }
.section-title .accent { color:var(--orange); }
.section-sub { font-size:16px; color:var(--muted); max-width:600px; margin-bottom:48px; }

.features { background:var(--bg-alt); border-top:4px solid var(--dark); border-bottom:4px solid var(--dark); }
.feature-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:24px; }
@media(max-width:900px) { .feature-grid { grid-template-columns:repeat(2,1fr); } }
@media(max-width:600px) { .feature-grid { grid-template-columns:1fr; } }
.feature-card { background:var(--card); border:4px solid var(--dark); padding:28px 24px; position:relative; box-shadow:6px 6px 0 var(--dark); transition:all 0.2s; }
.feature-card:hover { transform:translate(3px,3px); box-shadow:3px 3px 0 var(--dark); }
.feature-card .icon { width:48px; height:48px; display:flex; align-items:center; justify-content:center; margin-bottom:16px; font-size:28px; }
.feature-card h3 { font-size:18px; font-weight:800; margin-bottom:8px; }
.feature-card p { font-size:14px; color:var(--muted); line-height:1.5; }
.feature-card .tag { position:absolute; top:-12px; right:16px; background:var(--gold); color:var(--dark); font-family:'Press Start 2P',monospace; font-size:8px; padding:4px 8px; border:3px solid var(--dark); }

.data-strip { background:var(--dark); padding:48px 24px; border-bottom:4px solid var(--gold); }
.data-inner { max-width:1080px; margin:0 auto; display:grid; grid-template-columns:repeat(4,1fr); gap:32px; }
@media(max-width:700px) { .data-inner { grid-template-columns:repeat(2,1fr); gap:24px; } }
.data-item { text-align:center; }
.data-item .num { font-family:'Press Start 2P',monospace; font-size:clamp(20px,4vw,32px); color:var(--gold); margin-bottom:8px; }
.data-item .label { color:rgba(255,255,255,0.6); font-size:13px; }

.story { background:var(--bg); }
.story-content { display:grid; grid-template-columns:1fr 1fr; gap:48px; align-items:center; }
@media(max-width:768px) { .story-content { grid-template-columns:1fr; } }
.story-text h2 { font-size:clamp(24px,4vw,36px); font-weight:900; line-height:1.2; margin-bottom:20px; }
.story-text .accent { color:var(--orange); }
.story-text p { font-size:15px; color:var(--dark); margin-bottom:16px; line-height:1.7; }
.story-text .quote { border-left:4px solid var(--gold); padding:16px 20px; background:var(--bg-alt); margin:24px 0; font-style:italic; color:var(--dark); font-size:14px; }
.timeline { position:relative; padding-left:24px; }
.timeline::before { content:''; position:absolute; left:8px; top:0; bottom:0; width:3px; background:var(--dark); }
.timeline-item { position:relative; padding-bottom:28px; }
.timeline-item::before { content:''; position:absolute; left:-20px; top:4px; width:12px; height:12px; background:var(--gold); border:3px solid var(--dark); }
.timeline-item .time { font-family:'Press Start 2P',monospace; font-size:9px; color:var(--orange); margin-bottom:4px; }
.timeline-item .text { font-size:14px; color:var(--dark); font-weight:600; }

.compare { background:var(--bg-alt); border-top:4px solid var(--dark); }
.compare-table { max-width:800px; margin:0 auto; border:4px solid var(--dark); background:var(--card); box-shadow:8px 8px 0 var(--dark); }
.compare-row { display:grid; grid-template-columns:2fr 1.5fr 1.5fr; border-bottom:2px solid var(--dark); }
.compare-row:last-child { border-bottom:none; }
.compare-row.header { background:var(--dark); }
.compare-row.header > div { color:var(--gold); font-family:'Press Start 2P',monospace; font-size:10px; padding:14px 12px; text-align:center; }
.compare-row > div { padding:14px 16px; font-size:13px; border-right:2px solid var(--dark); }
.compare-row > div:last-child { border-right:none; }
.compare-row > div:first-child { font-weight:700; }
.compare-row.highlight { background:rgba(255,215,0,0.1); }
.compare-row .yes { color:var(--green); font-weight:700; }
.compare-row .no { color:var(--pink); font-weight:700; }
@media(max-width:600px) { .compare-row { grid-template-columns:1.5fr 1fr 1fr; } .compare-row > div { padding:10px 8px; font-size:11px; } }

/* XHS 购买区 */
.xhs-section { background:var(--bg); border-top:4px solid var(--dark); }
.xhs-content { display:grid; grid-template-columns:1fr 1fr; gap:48px; align-items:center; max-width:800px; margin:0 auto; }
@media(max-width:768px) { .xhs-content { grid-template-columns:1fr; text-align:center; } }
.xhs-qr { width:240px; height:auto; margin:0 auto; border:4px solid var(--dark); box-shadow:6px 6px 0 var(--dark); }
.xhs-info h3 { font-size:clamp(20px,3vw,28px); font-weight:900; margin-bottom:12px; }
.xhs-info .price { font-size:36px; font-weight:900; color:var(--orange); margin-bottom:8px; }
.xhs-info .price .unit { font-size:16px; color:var(--muted); }
.xhs-info .desc { font-size:14px; color:var(--dark); margin-bottom:16px; line-height:1.7; }
.xhs-info .warning { background:rgba(255,107,53,0.1); border:3px solid var(--orange); padding:16px; font-size:14px; color:var(--orange); font-weight:700; margin-bottom:16px; }
.xhs-info .steps { font-size:13px; color:var(--muted); line-height:1.8; }
.xhs-info .steps b { color:var(--dark); }

/* 下载区 */
.download-sec { background:var(--dark); border-top:4px solid var(--gold); }
.download-sec .section-label { background:var(--gold); color:var(--dark); }
.download-sec .section-title { color:#FFF; }
.download-sec .section-title .accent { color:var(--gold); }
.download-sec .section-sub { color:rgba(255,255,255,0.6); }
.dl-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:24px; margin-bottom:48px; }
.dl-card { background:#FFF; border:4px solid var(--gold); padding:24px 20px; text-decoration:none; color:var(--dark); box-shadow:6px 6px 0 var(--gold); transition:all 0.2s; display:block; }
.dl-card:hover { transform:translate(3px,3px); box-shadow:3px 3px 0 var(--gold); }
.dl-head { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
.dl-icon { font-size:22px; }
.dl-title { font-size:17px; font-weight:700; flex:1; }
.dl-size { color:#888; font-size:12px; font-weight:500; background:#f1f1f4; padding:3px 10px; border-radius:12px; }
.dl-filename { color:#999; font-size:11px; word-break:break-all; margin-bottom:8px; font-family:ui-monospace,monospace; }
.dl-arch { color:#666; font-size:12px; margin-bottom:4px; font-weight:500; }
.dl-audience { color:#555; font-size:12px; margin-bottom:6px; line-height:1.5; }
.dl-tip { color:#7a5a8a; font-size:11px; padding:6px 10px; background:#f6f3fa; border-radius:6px; margin-bottom:8px; line-height:1.5; }
.dl-btn { color:var(--dark); font-size:14px; margin-top:4px; font-weight:700; text-align:center; padding:8px; border-top:1px solid #f0f0f3; }

.warning-box { max-width:800px; margin:0 auto; background:rgba(255,107,53,0.1); border:3px solid var(--orange); padding:28px; }
.warning-box h3 { font-size:16px; font-weight:800; color:var(--orange); margin-bottom:16px; }
.warning-step { margin-bottom:20px; padding-bottom:20px; border-bottom:1px solid rgba(255,255,255,0.1); }
.warning-step:last-child { border-bottom:none; margin-bottom:0; padding-bottom:0; }
.warning-step .platform-name { font-size:14px; font-weight:700; color:var(--gold); margin-bottom:8px; }
.warning-step p { font-size:13px; color:rgba(255,255,255,0.7); line-height:1.6; margin-bottom:8px; }
.warning-step ol { padding-left:20px; }
.warning-step ol li { font-size:13px; color:rgba(255,255,255,0.8); margin-bottom:6px; line-height:1.5; }
.warning-step .note { font-size:12px; color:var(--orange); margin-top:8px; padding:8px 12px; background:rgba(255,107,53,0.1); border-left:3px solid var(--orange); }

footer { background:var(--dark); border-top:4px solid var(--gold); padding:48px 24px 32px; text-align:center; }
footer .footer-logo { width:64px; height:64px; margin:0 auto 16px; }
footer h4 { font-family:'Press Start 2P',monospace; font-size:14px; color:var(--gold); margin-bottom:12px; }
footer p { font-size:13px; color:rgba(255,255,255,0.5); margin-bottom:20px; }
footer .copyright { font-size:12px; color:rgba(255,255,255,0.3); padding-top:20px; border-top:1px solid rgba(255,255,255,0.1); }
.fade-in { opacity:0; transform:translateY(20px); transition:opacity 0.6s, transform 0.6s; }
.fade-in.visible { opacity:1; transform:translateY(0); }
</style>
</head>
<body>

<nav>
  <div class="nav-logo">
    <svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" shape-rendering="crispEdges">
      <rect x="3" y="2" width="8" height="11" fill="#FFFFFF"/><rect x="2" y="3" width="1" height="9" fill="#FFFFFF"/><rect x="11" y="3" width="1" height="9" fill="#FFFFFF"/>
      <rect x="3" y="1" width="8" height="1" fill="#1A1A2E"/><rect x="2" y="2" width="1" height="1" fill="#1A1A2E"/><rect x="11" y="2" width="1" height="1" fill="#1A1A2E"/>
      <rect x="1" y="3" width="1" height="9" fill="#1A1A2E"/><rect x="12" y="3" width="1" height="9" fill="#1A1A2E"/><rect x="3" y="13" width="8" height="1" fill="#1A1A2E"/>
      <rect x="2" y="12" width="1" height="1" fill="#1A1A2E"/><rect x="11" y="12" width="1" height="1" fill="#1A1A2E"/>
      <rect x="5" y="5" width="1" height="2" fill="#1A1A2E"/><rect x="8" y="5" width="1" height="2" fill="#1A1A2E"/>
      <rect x="4" y="8" width="1" height="1" fill="#FF9999"/><rect x="9" y="8" width="1" height="1" fill="#FF9999"/>
      <rect x="6" y="8" width="2" height="1" fill="#1A1A2E"/><rect x="7" y="9" width="1" height="1" fill="#1A1A2E"/>
      <rect x="5" y="10" width="4" height="3" fill="#FFD700"/><rect x="5" y="10" width="4" height="1" fill="#1A1A2E"/>
      <rect x="5" y="10" width="1" height="3" fill="#1A1A2E"/><rect x="8" y="10" width="1" height="3" fill="#1A1A2E"/>
      <rect x="5" y="12" width="4" height="1" fill="#1A1A2E"/><rect x="6" y="11" width="2" height="1" fill="#FF6B35"/>
      <rect x="10" y="8" width="3" height="4" fill="#FFD700"/><rect x="10" y="8" width="3" height="1" fill="#1A1A2E"/>
      <rect x="10" y="8" width="1" height="4" fill="#1A1A2E"/><rect x="12" y="8" width="1" height="4" fill="#1A1A2E"/>
      <rect x="10" y="11" width="3" height="1" fill="#1A1A2E"/><rect x="11" y="9" width="1" height="1" fill="#1A1A2E"/>
      <rect x="13" y="1" width="1" height="1" fill="#FFD700"/><rect x="12" y="2" width="1" height="1" fill="#FFD700"/>
      <rect x="14" y="2" width="1" height="1" fill="#FFD700"/><rect x="13" y="3" width="1" height="1" fill="#FFD700"/>
    </svg>
    <span>Offer搭子</span>
  </div>
  <div class="nav-links"><a href="#features">功能</a><a href="#story">故事</a><a href="#compare">对比</a><a href="#xhs">购买</a><a href="#download-section">下载</a></div>
  <a href="#download-section" class="nav-download">立即下载</a>
</nav>

<section class="hero">
  <div class="hero-content">
    <svg class="hero-logo" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" shape-rendering="crispEdges">
      <rect x="3" y="2" width="8" height="11" fill="#FFFFFF"/><rect x="2" y="3" width="1" height="9" fill="#FFFFFF"/><rect x="11" y="3" width="1" height="9" fill="#FFFFFF"/>
      <rect x="3" y="1" width="8" height="1" fill="#1A1A2E"/><rect x="2" y="2" width="1" height="1" fill="#1A1A2E"/><rect x="11" y="2" width="1" height="1" fill="#1A1A2E"/>
      <rect x="1" y="3" width="1" height="9" fill="#1A1A2E"/><rect x="12" y="3" width="1" height="9" fill="#1A1A2E"/><rect x="3" y="13" width="8" height="1" fill="#1A1A2E"/>
      <rect x="2" y="12" width="1" height="1" fill="#1A1A2E"/><rect x="11" y="12" width="1" height="1" fill="#1A1A2E"/>
      <rect x="5" y="5" width="1" height="2" fill="#1A1A2E"/><rect x="8" y="5" width="1" height="2" fill="#1A1A2E"/>
      <rect x="4" y="8" width="1" height="1" fill="#FF9999"/><rect x="9" y="8" width="1" height="1" fill="#FF9999"/>
      <rect x="6" y="8" width="2" height="1" fill="#1A1A2E"/><rect x="7" y="9" width="1" height="1" fill="#1A1A2E"/>
      <rect x="5" y="10" width="4" height="3" fill="#FFD700"/><rect x="5" y="10" width="4" height="1" fill="#1A1A2E"/>
      <rect x="5" y="10" width="1" height="3" fill="#1A1A2E"/><rect x="8" y="10" width="1" height="3" fill="#1A1A2E"/>
      <rect x="5" y="12" width="4" height="1" fill="#1A1A2E"/><rect x="6" y="11" width="2" height="1" fill="#FF6B35"/>
      <rect x="10" y="8" width="3" height="4" fill="#FFD700"/><rect x="10" y="8" width="3" height="1" fill="#1A1A2E"/>
      <rect x="10" y="8" width="1" height="4" fill="#1A1A2E"/><rect x="12" y="8" width="1" height="4" fill="#1A1A2E"/>
      <rect x="10" y="11" width="3" height="1" fill="#1A1A2E"/><rect x="11" y="9" width="1" height="1" fill="#1A1A2E"/>
      <rect x="13" y="1" width="1" height="1" fill="#FFD700"/><rect x="12" y="2" width="1" height="1" fill="#FFD700"/>
      <rect x="14" y="2" width="1" height="1" fill="#FFD700"/><rect x="13" y="3" width="1" height="1" fill="#FFD700"/>
    </svg>
    <div class="hero-tag">★ 全网最自动化的秋招工具 ★</div>
    <h1>投秋招<span class="accent">不用再手忙脚乱</span></h1>
    <p>6万+岗位自动同步 · 简历AI解析 · 面试日程自动提取 · 投递进度一站管理<br>一个人干了整个秋招辅导团队的活</p>
    <div class="hero-cta">
      <a href="#xhs" class="btn-primary">购买激活</a>
      <a href="#features" class="btn-secondary">了解功能</a>
    </div>
    <div class="hero-stats">
      <div class="hero-stat"><div class="num">6.3万+</div><div class="label">在招岗位</div></div>
      <div class="hero-stat"><div class="num">5,900</div><div class="label">覆盖公司</div></div>
      <div class="hero-stat"><div class="num">每日</div><div class="label">自动更新</div></div>
    </div>
  </div>
</section>

<section id="features" class="features section-pad">
  <div class="section-inner">
    <div class="section-label">核心功能</div>
    <h2 class="section-title">六个功能 <span class="accent">全自动</span></h2>
    <p class="section-sub">从找岗位到投递到面试提醒，每个环节都自动化。你只管准备，剩下的交给搭子。</p>
    <div class="feature-grid">
      <div class="feature-card fade-in"><div class="tag">自动</div><div class="icon">📡</div><h3>每日岗位自动同步</h3><p>每日8点自动抓取全网校招公告，AI拆成独立岗位入库。6万+岗位持续更新到春招结束。</p></div>
      <div class="feature-card fade-in"><div class="tag">AI</div><div class="icon">📄</div><h3>简历AI解析</h3><p>上传简历照片或PDF，AI自动提取信息。专业、技能、学历、项目经历一步到位。</p></div>
      <div class="feature-card fade-in"><div class="tag">AI</div><div class="icon">📅</div><h3>面试日程自动提取</h3><p>粘贴邮件内容，AI自动提取面试时间、地点、公司。日程日历一键管理，到期自动提醒。</p></div>
      <div class="feature-card fade-in"><div class="tag">核心</div><div class="icon">📊</div><h3>投递控制台</h3><p>一站式管理所有投递。按公司分组，按阶段追踪（网申→笔试→面试→Offer），状态一目了然。</p></div>
      <div class="feature-card fade-in"><div class="tag">AI</div><div class="icon">🔍</div><h3>公司深度尽调</h3><p>AI分析每家公司：业务模式、薪酬水平、发展前景、面试难度。投之前先摸底。</p></div>
      <div class="feature-card fade-in"><div class="tag">自动</div><div class="icon">🔔</div><h3>智能提醒系统</h3><p>面试前一天提醒，截止投递前3天预警。不会再因为忘了时间而错过机会。</p></div>
    </div>
  </div>
</section>

<section class="data-strip">
  <div class="data-inner">
    <div class="data-item"><div class="num">62,639</div><div class="label">在招岗位总数</div></div>
    <div class="data-item"><div class="num">5,900</div><div class="label">覆盖启动公司</div></div>
    <div class="data-item"><div class="num">8</div><div class="label">专业分表</div></div>
    <div class="data-item"><div class="num">每日</div><div class="label">更新至春招结束</div></div>
  </div>
</section>

<section id="story" class="story section-pad">
  <div class="section-inner">
    <div class="story-content">
      <div class="story-text">
        <div class="section-label">作者的话</div>
        <h2>一个人 <span class="accent">从零到一</span><br>把秋招全链路自动化了</h2>
        <p>这个工具没有团队，没有融资。只有一个经历过秋招的人，觉得"找岗位-盯投递-记日程"这件事不该这么累。</p>
        <p>从飞书源表同步、公告爬取、AI拆岗、简历解析、日程提取、投递管理、公司尽调、智能提醒——每一个模块都是一行一行代码写出来的。</p>
        <div class="quote">"秋招已经很累了，不该再花时间在机械重复的事情上。岗位自己排队，日程自动提取，投递一目了然——这才是2026年该有的秋招方式。"</div>
        <p>全网最具性价比：一个秋招季 <span style="font-weight:800;color:var(--orange)">¥49.9</span>，岗位数据每日自动更新，覆盖秋招+春招全周期。</p>
      </div>
      <div>
        <div class="timeline">
          <div class="timeline-item"><div class="time">STEP 01</div><div class="text">飞书源表自动同步 → 岗位数据库</div></div>
          <div class="timeline-item"><div class="time">STEP 02</div><div class="text">公告正文自动爬取（多线程）</div></div>
          <div class="timeline-item"><div class="time">STEP 03</div><div class="text">AI拆岗：1篇公告 → N个独立岗位</div></div>
          <div class="timeline-item"><div class="time">STEP 04</div><div class="text">结构化入库：专业·技能·学历·JD</div></div>
          <div class="timeline-item"><div class="time">STEP 05</div><div class="text">每日清理过期岗位，只留在招</div></div>
          <div class="timeline-item"><div class="time">STEP 06</div><div class="text">桌面端：简历解析 + 日程提取 + 投递管理</div></div>
        </div>
      </div>
    </div>
  </div>
</section>

<section id="compare" class="compare section-pad">
  <div class="section-inner">
    <div class="section-label">对比</div>
    <h2 class="section-title">为什么选 <span class="accent">Offer搭子</span></h2>
    <p class="section-sub">同类工具要么收费贵，要么功能散。Offer搭子把全链路打包成一个桌面应用。</p>
    <div class="compare-table">
      <div class="compare-row header"><div>功能</div><div>Offer搭子</div><div>其他工具</div></div>
      <div class="compare-row highlight"><div>每日岗位自动同步</div><div class="yes">每日8点自动</div><div class="no">手动刷新/无</div></div>
      <div class="compare-row"><div>AI简历解析</div><div class="yes">照片+PDF</div><div class="no">仅手动填写</div></div>
      <div class="compare-row highlight"><div>AI面试日程提取</div><div class="yes">粘贴邮件自动提取</div><div class="no">手动录入</div></div>
      <div class="compare-row"><div>投递进度管理</div><div class="yes">一站式控制台</div><div class="no">Excel/备忘录</div></div>
      <div class="compare-row highlight"><div>公司深度尽调</div><div class="yes">AI自动分析</div><div class="no">自己搜</div></div>
      <div class="compare-row"><div>智能面试提醒</div><div class="yes">自动到期提醒</div><div class="no">手动设闹钟</div></div>
      <div class="compare-row highlight"><div>价格</div><div class="yes">¥49.9/秋招季</div><div class="no">99-399元/季</div></div>
    </div>
  </div>
</section>

<!-- XHS 购买区 -->
<section id="xhs" class="xhs-section section-pad">
  <div class="section-inner">
    <div class="section-label">购买激活</div>
    <h2 class="section-title">扫码购买 <span class="accent">激活使用</span></h2>
    <p class="section-sub">扫描下方小红书二维码，在小红书完成购买后，使用订单号注册激活。</p>
    <div class="xhs-content">
      <div>
        <img src="/download/file/xhs_qr.jpg" alt="小红书二维码" class="xhs-qr">
      </div>
      <div class="xhs-info">
        <h3>紫紫大师兄_</h3>
        <div class="price">¥49.9 <span class="unit">/ 秋招季</span></div>
        <div class="warning">⚠️ 未在小红书购买无法使用！<br>注册时必须填写小红书订单号，否则账号将被清理。</div>
        <div class="steps">
          <b>第一步：</b>扫描二维码 → 在小红书完成购买<br>
          <b>第二步：</b>下载安装 Offer搭子 桌面端<br>
          <b>第三步：</b>注册时填写小红书订单号激活<br>
          <b>第四步：</b>开始使用全部功能，覆盖秋招+春招全周期
        </div>
      </div>
    </div>
  </div>
</section>

<!-- 下载区 -->
<section id="download-section" class="download-sec section-pad">
  <div class="section-inner">
    <div class="section-label">立即下载</div>
    <h2 class="section-title">选择你的 <span class="accent">平台</span></h2>
    <p class="section-sub">支持 macOS (Intel/Apple Silicon)、Windows、Linux。桌面应用，数据本地存储，安全可靠。</p>
    <div class="dl-grid">
      {items_html}
    </div>
    <div class="warning-box">
      <h3>⚠️ 首次打开提示（非认证开发者）</h3>
      <div class="warning-step">
        <div class="platform-name">🍎 macOS 用户</div>
        <p>由于应用未经 Apple 开发者认证，首次打开会被系统拦截提示"无法验证开发者"。这是正常的，请按以下步骤操作：</p>
        <ol>
          <li>下载 .dmg 文件后，双击打开，将 Offer搭子 拖入「应用程序」文件夹</li>
          <li>在「访达」→「应用程序」中找到 Offer搭子</li>
          <li><b>按住 Control 键</b>，点击 Offer搭子 图标，选择「打开」</li>
          <li>弹出安全提示框，点击「打开」即可</li>
          <li>如果仍然无法打开：进入「系统设置」→「隐私与安全性」，在底部找到"已阻止 Offer搭子"，点击「仍要打开」</li>
        </ol>
        <div class="note">💡 此操作只需执行一次，之后可正常双击打开</div>
      </div>
      <div class="warning-step">
        <div class="platform-name">🪟 Windows 用户</div>
        <p>Windows SmartScreen 会提示"已保护你的电脑"。这是正常的，因为应用没有代码签名证书。</p>
        <ol>
          <li>下载 .exe 安装包后双击运行</li>
          <li>弹出蓝色 SmartScreen 窗口，点击「更多信息」</li>
          <li>点击「仍要运行」即可继续安装</li>
          <li>如果 Edge 浏览器拦截下载：点击下载栏的「…」→「保留」→「仍然保留」</li>
        </ol>
        <div class="note">💡 安装后即可正常使用，后续打开不再提示</div>
      </div>
    </div>
  </div>
</section>

<footer>
  <svg class="footer-logo" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" shape-rendering="crispEdges">
    <rect x="3" y="2" width="8" height="11" fill="#FFFFFF"/><rect x="2" y="3" width="1" height="9" fill="#FFFFFF"/><rect x="11" y="3" width="1" height="9" fill="#FFFFFF"/>
    <rect x="3" y="1" width="8" height="1" fill="#1A1A2E"/><rect x="2" y="2" width="1" height="1" fill="#1A1A2E"/><rect x="11" y="2" width="1" height="1" fill="#1A1A2E"/>
    <rect x="1" y="3" width="1" height="9" fill="#1A1A2E"/><rect x="12" y="3" width="1" height="9" fill="#1A1A2E"/><rect x="3" y="13" width="8" height="1" fill="#1A1A2E"/>
    <rect x="2" y="12" width="1" height="1" fill="#1A1A2E"/><rect x="11" y="12" width="1" height="1" fill="#1A1A2E"/>
    <rect x="5" y="5" width="1" height="2" fill="#1A1A2E"/><rect x="8" y="5" width="1" height="2" fill="#1A1A2E"/>
    <rect x="4" y="8" width="1" height="1" fill="#FF9999"/><rect x="9" y="8" width="1" height="1" fill="#FF9999"/>
    <rect x="6" y="8" width="2" height="1" fill="#1A1A2E"/><rect x="7" y="9" width="1" height="1" fill="#1A1A2E"/>
    <rect x="5" y="10" width="4" height="3" fill="#FFD700"/><rect x="5" y="10" width="4" height="1" fill="#1A1A2E"/>
    <rect x="5" y="10" width="1" height="3" fill="#1A1A2E"/><rect x="8" y="10" width="1" height="3" fill="#1A1A2E"/>
    <rect x="5" y="12" width="4" height="1" fill="#1A1A2E"/><rect x="6" y="11" width="2" height="1" fill="#FF6B35"/>
    <rect x="10" y="8" width="3" height="4" fill="#FFD700"/><rect x="10" y="8" width="3" height="1" fill="#1A1A2E"/>
    <rect x="10" y="8" width="1" height="4" fill="#1A1A2E"/><rect x="12" y="8" width="1" height="4" fill="#1A1A2E"/>
    <rect x="10" y="11" width="3" height="1" fill="#1A1A2E"/><rect x="11" y="9" width="1" height="1" fill="#1A1A2E"/>
  </svg>
  <h4>Offer搭子</h4>
  <p>全网最自动化的秋招工具 · ¥49.9/秋招季 · 数据每日更新</p>
  <div class="copyright">© 2026 Offer搭子 · 一个人做的秋招工具 · 把时间省下来准备面试</div>
</footer>

<script>
var obs = new IntersectionObserver(function(entries) {
  entries.forEach(function(e) { if (e.isIntersecting) e.target.classList.add('visible'); });
}, { threshold: 0.1 });
document.querySelectorAll('.fade-in').forEach(function(el) { obs.observe(el); });
document.querySelectorAll('a[href^="#"]').forEach(function(a) {
  a.addEventListener('click', function(e) {
    var t = document.querySelector(a.getAttribute('href'));
    if (t) { e.preventDefault(); t.scrollIntoView({ behavior: 'smooth' }); }
  });
});
</script>
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
