"""投递记录路由：收藏/投递/测评/面试/offer 全流程管理。

- ``POST /api/v1/applications``      创建投递记录（收藏/投递/自建/邮件）
- ``GET  /api/v1/applications``      列出投递记录（可按 status 筛选）
- ``GET  /api/v1/applications/{id}`` 获取单条投递记录
- ``PATCH /api/v1/applications/{id}`` 更新状态/备注/轮次等
- ``DELETE /api/v1/applications/{id}`` 删除记录
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from deps import get_current_user
from models import application as app_model

router = APIRouter(prefix="/applications", tags=["applications"])


class CreateApplicationRequest(BaseModel):
    job_title: str = ""
    company_name: str = ""
    status: str = "favorite"  # favorite|applied|assessment|interview|offer|rejected
    source: str = "manual"  # db_job|db_company|manual|email
    link_type: Optional[str] = None  # job|company|None
    link_id: Optional[str] = None
    apply_url: str = ""
    announcement_url: str = ""
    notes: str = ""
    email_id: Optional[str] = None


class UpdateApplicationRequest(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    interview_round: Optional[int] = None
    apply_url: Optional[str] = None
    announcement_url: Optional[str] = None
    job_title: Optional[str] = None
    company_name: Optional[str] = None


@router.post("")
async def create_app(
    req: CreateApplicationRequest,
    user: dict = Depends(get_current_user),
):
    """创建投递记录（收藏/投递/自建/邮件来源）。"""
    app = await app_model.create_application(
        user_id=user["id"],
        job_title=req.job_title,
        company_name=req.company_name,
        status=req.status,
        source=req.source,
        link_type=req.link_type,
        link_id=req.link_id,
        apply_url=req.apply_url,
        announcement_url=req.announcement_url,
        notes=req.notes,
        email_id=req.email_id,
    )
    return app


@router.get("")
async def list_apps(
    status: str = Query("", description="按状态筛选：favorite/applied/assessment/interview/offer/rejected"),
    user: dict = Depends(get_current_user),
):
    """列出当前用户的投递记录。"""
    apps = await app_model.list_applications(user_id=user["id"], status=status)
    return {"applications": apps, "total": len(apps)}


@router.get("/{app_id}")
async def get_app(
    app_id: int,
    user: dict = Depends(get_current_user),
):
    """获取单条投递记录详情。"""
    app = await app_model.get_application(app_id=app_id, user_id=user["id"])
    if not app:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    return app


@router.patch("/{app_id}")
async def update_app(
    app_id: int,
    req: UpdateApplicationRequest,
    user: dict = Depends(get_current_user),
):
    """更新投递记录的状态/备注/轮次等。"""
    app = await app_model.update_application(
        app_id=app_id,
        user_id=user["id"],
        status=req.status,
        notes=req.notes,
        interview_round=req.interview_round,
        apply_url=req.apply_url,
        announcement_url=req.announcement_url,
        job_title=req.job_title,
        company_name=req.company_name,
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
