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


class UpdateProfileRequest(BaseModel):
    """部分更新画像字段;None 字段保持原值。Phase 1 纯人工编辑,不调 LLM。"""
    keywords: Optional[list] = None
    fit_directions: Optional[list] = None
    degree: Optional[str] = None
    major: Optional[str] = None
    target_cities: Optional[list] = None


@router.patch("/{profile_id}", response_model=ProfileResponse)
def update_profile(
    profile_id: str,
    req: UpdateProfileRequest,
    user: dict = Depends(get_current_user),
):
    """更新画像字段(用户在简历解析页手动编辑后保存)。

    - 仅更新传入字段;未传字段保持原值
    - 不调用 LLM,纯人工编辑
    - 保存后立即生效:推荐接口下次读取 active 画像时用新值
    """
    uid = str(user["user_id"])
    profile = rp_model.update_profile(
        profile_id=profile_id,
        user_id=uid,
        keywords=req.keywords,
        fit_directions=req.fit_directions,
        degree=req.degree,
        major=req.major,
        target_cities=req.target_cities,
    )
    if not profile:
        raise HTTPException(status_code=404, detail="画像不存在或无权修改")
    return profile
