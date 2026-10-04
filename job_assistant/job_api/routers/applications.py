"""投递记录路由：收藏/投递/面试/offer 全流程管理。

- ``POST /api/v1/applications``      收藏或投递（创建记录）
- ``GET  /api/v1/applications``      列出投递记录（可按 status 筛选）
- ``PATCH /api/v1/applications/{id}`` 更新状态/备注
- ``DELETE /api/v1/applications/{id}`` 删除记录
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from deps import get_current_user
from models import application as app_model

router = APIRouter(prefix="/applications", tags=["applications"])


class CreateApplicationRequest(BaseModel):
    job_id: str
    job_title: str
    company_name: str = ""
    status: str = "favorite"  # favorite | applied | interview | offer | rejected
    apply_url: str = ""
    notes: str = ""


class UpdateApplicationRequest(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


@router.post("")
async def create_app(
    req: CreateApplicationRequest,
    user: dict = Depends(get_current_user),
):
    """收藏或投递一个岗位。"""
    app = await app_model.create_application(
        user_id=user["id"],
        job_id=req.job_id,
        job_title=req.job_title,
        company_name=req.company_name,
        status=req.status,
        apply_url=req.apply_url,
        notes=req.notes,
    )
    return app


@router.get("")
async def list_apps(
    status: str = Query("", description="按状态筛选：favorite/applied/interview/offer/rejected"),
    user: dict = Depends(get_current_user),
):
    """列出当前用户的投递记录。"""
    apps = await app_model.list_applications(user_id=user["id"], status=status)
    return {"applications": apps, "total": len(apps)}


@router.patch("/{app_id}")
async def update_app(
    app_id: int,
    req: UpdateApplicationRequest,
    user: dict = Depends(get_current_user),
):
    """更新投递记录的状态或备注。"""
    app = await app_model.update_application(
        app_id=app_id,
        user_id=user["id"],
        status=req.status,
        notes=req.notes,
    )
    if not app:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    return app


@router.delete("/{app_id}")
async def delete_app(
    app_id: int,
    user: dict = Depends(get_current_user),
):
    """删除投递记录。"""
    ok = await app_model.delete_application(app_id=app_id, user_id=user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    return {"ok": True}
