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
    # 候选人竞争力(实时计算,不存表;用于简历解析页展示用户层级)
    candidate_score: float | None = None
    candidate_tier: str | None = None


def _compute_candidate_competitiveness(profile: dict) -> tuple[float, str]:
    """实时计算候选人竞争力分数和层级标签(0-100)。

    调 competitiveness.candidate_competitiveness(profile) 返回 (score, breakdown, detail)。
    tier 按 score 分档:>=75 顶 / >=55 中 / >=35 保底 / <35 待提升。
    失败时返回 (0, "")。
    """
    try:
        from competitiveness import candidate_competitiveness

        score, _brk, _det = candidate_competitiveness(profile)
        if score >= 75:
            tier = "顶"
        elif score >= 55:
            tier = "中"
        elif score >= 35:
            tier = "保底"
        else:
            tier = "待提升"
        return float(score), tier
    except Exception:  # noqa: BLE001
        return 0.0, ""


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
    score, tier = _compute_candidate_competitiveness(profile)
    profile["candidate_score"] = score
    profile["candidate_tier"] = tier
    return profile


@router.get("/active", response_model=Optional[ProfileResponse])
def get_active_profile(user: dict = Depends(get_current_user)):
    uid = str(user["user_id"])
    profile = rp_model.get_active_profile(uid)
    if profile:
        score, tier = _compute_candidate_competitiveness(profile)
        profile["candidate_score"] = score
        profile["candidate_tier"] = tier
    return profile


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
    # 简历修改:清空该 profile 的推荐评分缓存,下次推荐重新计算
    try:
        from job_api.models import job_score as score_cache

        cleared = score_cache.clear_profile_cache(profile_id)
        logger.info(f"简历修改,清空推荐缓存: profile={profile_id}, 删除 {cleared} 条")
    except Exception as e:
        logger.warning(f"清空推荐缓存失败(不阻塞): {e}")
    score, tier = _compute_candidate_competitiveness(profile)
    profile["candidate_score"] = score
    profile["candidate_tier"] = tier
    return profile
