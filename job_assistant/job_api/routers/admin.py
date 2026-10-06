"""管理后台路由：用户列表 / 手动建号 / 吊销 / 恢复 / 改备注 / 设管理员 / 删除。

适用场景：私域获客——用户缴费后管理员直接建号，把邮箱+初始密码私聊发给用户，
用户用 /auth/login 接口登录即可（已验证状态，跳过邮箱验证码）。

所有路由都需要管理员权限（Depends(get_current_admin)）。
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from deps import get_current_admin
from models import user as user_model
from services.auth_service import hash_password

router = APIRouter(prefix="/admin", tags=["admin"])

_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class UserOut(BaseModel):
    """用户列表/详情返回模型（脱敏：不含 password_hash）。"""

    id: str
    email: str
    is_verified: bool
    is_admin: bool
    is_active: bool
    notes: Optional[str] = None
    xhs_order_id: Optional[str] = None
    created_at: str
    last_login_at: Optional[str] = None


class UserListResponse(BaseModel):
    users: List[UserOut]
    total: int
    limit: int
    offset: int


class CreateUserRequest(BaseModel):
    """管理员手动建号。

    私域获客场景：用户缴费后管理员建号，is_verified 直接设为 True（跳过邮箱验证码），
    把 email + password 私聊发给用户，用户用 /auth/login 登录。
    """

    email: str = Field(pattern=_EMAIL_PATTERN)
    password: str = Field(min_length=6, max_length=128)
    notes: Optional[str] = Field(default=None, max_length=500)


class UpdateUserRequest(BaseModel):
    """修改用户属性。所有字段可选，只更新传入的字段。"""

    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=500)


class AdminResetPasswordRequest(BaseModel):
    """管理员重置用户密码（兜底方案：用户邮箱收不到验证码时使用）。

    管理员设新密码后私聊发给用户，用户首次登录后可自行修改。
    """

    new_password: str = Field(min_length=6, max_length=128)


@router.get("/users", response_model=UserListResponse)
async def list_users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    search: Optional[str] = Query(default=None, max_length=100),
    _: dict = Depends(get_current_admin),
) -> UserListResponse:
    """分页列出用户（脱敏）。search 非空时按 email 或 notes 模糊匹配。"""
    users, total = await user_model.list_users(limit=limit, offset=offset, search=search)
    return UserListResponse(
        users=[UserOut(**u) for u in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    _: dict = Depends(get_current_admin),
) -> UserOut:
    """管理员手动建号（已验证状态，跳过邮箱验证码）。

    适用私域获客：用户缴费后建号，把 email+password 私聊发给用户。
    email 已存在则返回 409。
    """
    existing = await user_model.get_user_by_email(body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"邮箱 {body.email} 已存在",
        )
    password_hash = hash_password(body.password)
    user = await user_model.create_user(body.email, password_hash)
    # 直接标记为已验证（私域获客，管理员已确认身份）
    await user_model.set_verified(body.email)
    if body.notes:
        await user_model.update_notes(user["id"], body.notes)
    # 重新查询返回完整字段
    full_user = await user_model.get_user_by_id(user["id"])
    full_user.pop("password_hash", None)
    full_user.pop("device_fingerprint", None)
    return UserOut(**full_user)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    current_admin: dict = Depends(get_current_admin),
) -> UserOut:
    """修改用户属性（吊销/恢复/改备注/设管理员）。

    不允许把自己降级为非管理员或吊销自己（避免误操作锁死）。
    不允许把最后一个管理员降级（避免失去管理能力）。
    """
    target = await user_model.get_user_by_id(user_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    # 防误操作：不能吊销/降级自己
    is_self = target["id"] == current_admin["id"]
    if is_self and (body.is_active is False or body.is_admin is False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能停用或降级自己（避免锁死管理权限）",
        )

    # 不允许把最后一个管理员降级
    if body.is_admin is False and target.get("is_admin"):
        users, total = await user_model.list_users(limit=200, offset=0)
        admin_count = sum(1 for u in users if u["is_admin"])
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能降级最后一个管理员",
            )

    if body.is_active is not None:
        await user_model.set_active_status(user_id, body.is_active)
    if body.is_admin is not None:
        await user_model.set_admin_status(user_id, body.is_admin)
    if body.notes is not None:
        await user_model.update_notes(user_id, body.notes)

    # 重新查询返回完整字段
    full_user = await user_model.get_user_by_id(user_id)
    full_user.pop("password_hash", None)
    full_user.pop("device_fingerprint", None)
    return UserOut(**full_user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    current_admin: dict = Depends(get_current_admin),
) -> None:
    """删除用户。不允许删除自己，不允许删除最后一个管理员。"""
    target = await user_model.get_user_by_id(user_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    if target["id"] == current_admin["id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除自己",
        )
    ok = await user_model.delete_user(user_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="删除失败（可能是最后一个管理员）",
        )


@router.post(
    "/users/{user_id}/reset-password",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def admin_reset_password(
    user_id: str,
    body: AdminResetPasswordRequest,
    _: dict = Depends(get_current_admin),
) -> dict:
    """管理员重置用户密码（兜底方案）。

    适用场景：用户邮箱收不到 Resend 验证码（如 163/QQ 邮箱屏蔽），
    管理员用此接口设新密码，私聊发给用户，用户登录后可自行修改。
    """
    target = await user_model.get_user_by_id(user_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    await user_model.update_password_hash(user_id, hash_password(body.new_password))
    return {"message": "密码已重置", "user_id": user_id}


class BulkUpdateRequest(BaseModel):
    """批量操作请求体。"""

    user_ids: List[str]
    is_active: bool


@router.post("/users/bulk", response_model=dict)
async def bulk_update_users(
    body: BulkUpdateRequest,
    current_admin: dict = Depends(get_current_admin),
) -> dict:
    """批量 启用/停用 用户（管理员审核时用）。

    不允许批量停用自己（避免误操作锁死）。
    """
    if not body.user_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_ids 不能为空",
        )
    # 防误操作：过滤掉自己
    safe_ids = [uid for uid in body.user_ids if uid != current_admin["id"]]
    skipped = len(body.user_ids) - len(safe_ids)
    affected = await user_model.bulk_set_active_status(safe_ids, body.is_active)
    return {
        "message": f"已{'启用' if body.is_active else '停用'} {affected} 个用户",
        "affected": affected,
        "skipped_self": skipped,
    }


@router.get("/export/users", response_model=UserListResponse)
async def export_all_users(
    _: dict = Depends(get_current_admin),
) -> UserListResponse:
    """导出全部用户（无分页，审核时用）。"""
    users, total = await user_model.list_users(limit=10000, offset=0)
    return UserListResponse(
        users=[UserOut(**u) for u in users],
        total=total,
        limit=10000,
        offset=0,
    )
