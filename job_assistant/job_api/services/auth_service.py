"""认证业务编排：注册、邮箱验证、登录、token 刷新。

- 密码 hash：passlib bcrypt
- 验证码：6 位随机数字（models.user.generate_code）
- 重复注册：已存在未验证 → 重发验证码；已存在已验证 → ConflictError
- 数据库建表：首次调用时幂等初始化（init_db / CREATE TABLE IF NOT EXISTS）
"""

from __future__ import annotations

from typing import Optional

from passlib.context import CryptContext

from models import user as user_model
from services import email_service, jwt_service

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_init_done = False


class AuthError(Exception):
    """认证业务错误基类。"""


class ConflictError(AuthError):
    """重复注册已验证用户。"""


class InvalidCredentialsError(AuthError):
    """邮箱/密码不匹配。"""


class NotVerifiedError(AuthError):
    """邮箱未验证。"""


class InvalidCodeError(AuthError):
    """验证码无效或已过期。"""


async def _ensure_init() -> None:
    """首次调用时建表（CREATE TABLE IF NOT EXISTS）。"""
    global _init_done
    if not _init_done:
        await user_model.init_db()
        _init_done = True


def _hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def hash_password(password: str) -> str:
    """公开的密码哈希接口，供管理后台等模块复用（不要直接用 _pwd_context）。"""
    return _pwd_context.hash(password)


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return _pwd_context.verify(password, password_hash)
    except Exception:  # noqa: BLE001 passlib 抛 ValueError 等均视作校验失败
        return False


async def register(email: str, password: str, xhs_order_id: str) -> dict:
    """注册：邮箱未占用 → 创建未验证用户 + 发验证码；已存在未验证 → 重发验证码；已验证 → ConflictError。

    xhs_order_id 必填且唯一（私域获客场景：用户必须填小红书订单号才能注册）。
    """
    await _ensure_init()
    # 1. 校验 XHS 订单号未被使用
    existing_by_order = await user_model.get_user_by_xhs_order_id(xhs_order_id)
    if existing_by_order:
        raise ConflictError(
            f"XHS 订单号 {xhs_order_id} 已被使用，请联系卖家"
        )

    existing = await user_model.get_user_by_email(email)
    if existing:
        if existing["is_verified"]:
            raise ConflictError("该邮箱已注册并验证，请直接登录")
        # 未验证：把订单号补上 + 重发验证码（覆盖旧码）
        # （同一邮箱未验证时再次注册，可能是用户忘了密码或没收到码）
        if not existing.get("xhs_order_id"):
            await user_model.update_notes(
                existing["id"], f"XHS: {xhs_order_id}"
            )
        code = user_model.generate_code()
        await user_model.create_verification_code(email, code)
        await email_service.send_verification_code(email, code)
        return {"user_id": existing["id"], "needs_verify": True}

    user = await user_model.create_user(
        email, _hash_password(password), xhs_order_id
    )
    code = user_model.generate_code()
    await user_model.create_verification_code(email, code)
    await email_service.send_verification_code(email, code)
    return {"user_id": user["id"], "needs_verify": True}


async def verify_email(email: str, code: str) -> dict:
    """校验验证码 → 标记已验证 → 签发 JWT。"""
    await _ensure_init()
    user = await user_model.get_user_by_email(email)
    if not user:
        raise InvalidCodeError("验证码无效或已过期")
    if not await user_model.verify_code(email, code):
        raise InvalidCodeError("验证码无效或已过期")
    await user_model.set_verified(email)
    token = jwt_service.create_access_token(user["id"])
    return {"token": token, "expires_at": jwt_service.get_expires_at()}


async def login(email: str, password: str) -> dict:
    """登录：校验密码 + 已验证 → 签发 JWT。"""
    await _ensure_init()
    user = await user_model.get_user_by_email(email)
    if not user or not _verify_password(password, user["password_hash"]):
        raise InvalidCredentialsError("邮箱或密码错误")
    if not user["is_verified"]:
        raise NotVerifiedError("邮箱未验证，请先完成验证")
    await user_model.update_last_login(email)
    token = jwt_service.create_access_token(user["id"])
    return {"token": token, "expires_at": jwt_service.get_expires_at()}


async def refresh(user_id: str) -> dict:
    """刷新 token（依赖外部已校验过旧 token，仅重新签发）。"""
    await _ensure_init()
    token = jwt_service.create_access_token(user_id)
    return {"token": token, "expires_at": jwt_service.get_expires_at()}


async def forgot_password(email: str) -> None:
    """忘记密码：向已注册邮箱发送重置验证码。

    邮箱不存在时静默不报错（防止枚举用户邮箱），但也不发送邮件。
    重置验证码与注册验证码共用 verification_codes 表（同 email 主键唯一）。
    """
    await _ensure_init()
    user = await user_model.get_user_by_email(email)
    if not user:
        # 静默返回，不暴露邮箱是否注册
        return
    # 复用注册验证码表（同 email 主键唯一，新码会覆盖旧码）
    code = user_model.generate_code()
    await user_model.create_verification_code(email, code)
    await email_service.send_verification_code(email, code)


async def reset_password(email: str, code: str, new_password: str) -> None:
    """重置密码：用邮箱验证码设新密码（不需要登录）。"""
    await _ensure_init()
    user = await user_model.get_user_by_email(email)
    if not user:
        raise InvalidCodeError("验证码无效或已过期")
    # 复用 verify_code 校验逻辑（验证码存在 + 未过期 + 未使用 → 标记 used）
    if not await user_model.verify_code(email, code):
        raise InvalidCodeError("验证码无效或已过期")
    # 更新密码哈希
    await user_model.update_password_hash(user["id"], _hash_password(new_password))


async def change_password(user_id: str, old_password: str, new_password: str) -> None:
    """修改密码：需登录，校验旧密码后设新密码。"""
    await _ensure_init()
    user = await user_model.get_user_by_id(user_id)
    if not user or not _verify_password(old_password, user["password_hash"]):
        raise InvalidCredentialsError("旧密码错误")
    await user_model.update_password_hash(user_id, _hash_password(new_password))


def reset_init_flag() -> None:
    """测试辅助：重置建表标志，便于在临时库上重新触发 init_db。"""
    global _init_done
    _init_done = False
