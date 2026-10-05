"""简历画像路由 — 存储 LLM 解析后的画像 + CRUD。

画像用于岗位推荐。一用户只有一个 active 画像。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional

from deps import get_current_user
from models import resume_profile as rp_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resume-profiles", tags=["resume-profiles"])


class CreateProfileRequest(BaseModel):
    resume_text: str = Field(..., min_length=10, description="原始简历文本")
    keywords: list = []
    fit_directions: list = []
    degree: str = ""
    major: str = ""
    target_cities: list = []


class ProfileResponse(BaseModel):
    profile_id: str
    user_id: str
    resume_text: str = ""
    keywords: list
    fit_directions: list
    degree: str = ""
    major: str = ""
    target_cities: list = []
    is_active: bool = True
    created_at: str
    updated_at: str


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile(
    req: CreateProfileRequest,
    user: dict = Depends(get_current_user),
):
    """新建画像（自动把同用户旧 active 设为 inactive）。"""
    uid = str(user["user_id"])
    profile = rp_model.create_profile(
        user_id=uid,
        resume_text=req.resume_text,
        keywords=req.keywords,
        fit_directions=req.fit_directions,
        degree=req.degree,
        major=req.major,
        target_cities=req.target_cities,
    )
    return profile


@router.get("/active", response_model=Optional[ProfileResponse])
def get_active_profile(user: dict = Depends(get_current_user)):
    uid = str(user["user_id"])
    return rp_model.get_active_profile(uid)


@router.get("", response_model=list)
def list_profiles(user: dict = Depends(get_current_user)):
    uid = str(user["user_id"])
    return rp_model.list_profiles(uid)


@router.delete("/{profile_id}")
def delete_profile(
    profile_id: str,
    user: dict = Depends(get_current_user),
):
    uid = str(user["user_id"])
    ok = rp_model.delete_profile(profile_id, uid)
    if not ok:
        raise HTTPException(status_code=404, detail="画像不存在或无权删除")
    return {"ok": True}
