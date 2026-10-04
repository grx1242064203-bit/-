"""岗位推荐路由 — 基于简历画像推荐 top N 岗位。

端点：POST /api/v1/jobs/recommend { profile_id?, top_n? } → { jobs, total_matched, ... }
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import get_current_user
from models import resume_profile as rp_model
from services.job_matcher_adapter import recommend_jobs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


class RecommendRequest(BaseModel):
    profile_id: str | None = None
    top_n: int = Field(default=200, ge=10, le=500, description="返回岗位数量上限")


@router.post("/recommend")
def recommend(
    req: RecommendRequest,
    user: dict = Depends(get_current_user),
):
    """基于简历画像推荐岗位。

    - 没传 profile_id → 用用户当前 active 画像
    - 画像不存在 → 400
    - 推荐不足 top_n 时自动从全量岗位按分数补齐
    """
    uid = int(user["user_id"])

    # 1) 取画像
    if req.profile_id:
        profile = rp_model.get_profile(req.profile_id)
        if not profile or profile["user_id"] != uid:
            raise HTTPException(status_code=404, detail="画像不存在或无权访问")
    else:
        profile = rp_model.get_active_profile(uid)
        if not profile:
            raise HTTPException(
                status_code=400,
                detail="尚未创建简历画像，请先上传并解析简历",
            )

    # 2) 调推荐
    try:
        result = recommend_jobs(profile, top_n=req.top_n)
    except Exception as e:
        logger.error(f"recommend 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"推荐失败: {e}",
        )

    return result
