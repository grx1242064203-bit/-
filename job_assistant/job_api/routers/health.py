"""健康检查路由（从 main.py 抽离）。"""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """健康检查端点，返回服务状态与版本号。"""
    return {"status": "ok", "version": "0.1.0"}
