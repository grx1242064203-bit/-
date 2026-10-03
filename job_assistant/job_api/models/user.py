"""用户与验证码数据访问层（SQLite + aiosqlite）。

表结构：
- users: id(UUID str), email(unique), password_hash, is_verified, device_fingerprint?, created_at, last_login_at?
- verification_codes: email, code(6位), expires_at, used

所有函数均幂等可重入；init_db 使用 CREATE TABLE IF NOT EXISTS。
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

from config import get_settings

# 验证码有效期：6 小时
CODE_TTL_SECONDS = 6 * 3600


def _db_path() -> Path:
    """返回 auth.db 文件路径，并确保父目录存在。"""
    settings = get_settings()
    data_dir = Path(settings.DATA_DIR)
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return data_dir / "auth.db"


async def _connect() -> aiosqlite.Connection:
    """打开一个新连接，行工厂设为 Row 以便按字段名访问。"""
    conn = await aiosqlite.connect(str(_db_path()))
    conn.row_factory = aiosqlite.Row
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_user(row: aiosqlite.Row) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "password_hash": row["password_hash"],
        "is_verified": bool(row["is_verified"]),
        "device_fingerprint": row["device_fingerprint"],
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
    }


async def init_db() -> None:
    """幂等建表（CREATE TABLE IF NOT EXISTS）。"""
    conn = await _connect()
    try:
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_verified INTEGER NOT NULL DEFAULT 0,
                device_fingerprint TEXT,
                created_at TEXT NOT NULL,
                last_login_at TEXT
            );
            CREATE TABLE IF NOT EXISTS verification_codes (
                email TEXT NOT NULL,
                code TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (email, code)
            );
            """
        )
        await conn.commit()
    finally:
        await conn.close()


async def create_user(email: str, password_hash: str) -> dict:
    """创建未验证用户，返回用户 dict。email 唯一冲突时抛 IntegrityError。"""
    user_id = str(uuid.uuid4())
    now = _now_iso()
    conn = await _connect()
    try:
        await conn.execute(
            "INSERT INTO users (id, email, password_hash, is_verified, created_at) "
            "VALUES (?, ?, ?, 0, ?)",
            (user_id, email, password_hash, now),
        )
        await conn.commit()
    finally:
        await conn.close()
    return {
        "id": user_id,
        "email": email,
        "password_hash": password_hash,
        "is_verified": False,
        "device_fingerprint": None,
        "created_at": now,
        "last_login_at": None,
    }


async def get_user_by_email(email: str) -> Optional[dict]:
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "SELECT id, email, password_hash, is_verified, device_fingerprint, "
            "created_at, last_login_at FROM users WHERE email = ?",
            (email,),
        )
        row = await cursor.fetchone()
        return _row_to_user(row) if row else None
    finally:
        await conn.close()


async def get_user_by_id(user_id: str) -> Optional[dict]:
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "SELECT id, email, password_hash, is_verified, device_fingerprint, "
            "created_at, last_login_at FROM users WHERE id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        return _row_to_user(row) if row else None
    finally:
        await conn.close()


async def update_password_hash(user_id: str, password_hash: str) -> None:
    conn = await _connect()
    try:
        await conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (password_hash, user_id),
        )
        await conn.commit()
    finally:
        await conn.close()


async def set_verified(email: str) -> None:
    """将指定邮箱的用户标记为已验证。"""
    conn = await _connect()
    try:
        await conn.execute(
            "UPDATE users SET is_verified = 1 WHERE email = ?",
            (email,),
        )
        await conn.commit()
    finally:
        await conn.close()


async def update_last_login(email: str) -> None:
    conn = await _connect()
    try:
        await conn.execute(
            "UPDATE users SET last_login_at = ? WHERE email = ?",
            (_now_iso(), email),
        )
        await conn.commit()
    finally:
        await conn.close()


async def create_verification_code(
    email: str, code: str, expires_in_seconds: int = CODE_TTL_SECONDS
) -> dict:
    """为 email 写入一条新的验证码（先清掉该邮箱的旧码，避免主键冲突）。"""
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
    ).isoformat()
    conn = await _connect()
    try:
        await conn.execute(
            "DELETE FROM verification_codes WHERE email = ?",
            (email,),
        )
        await conn.execute(
            "INSERT INTO verification_codes (email, code, expires_at, used) "
            "VALUES (?, ?, ?, 0)",
            (email, code, expires_at),
        )
        await conn.commit()
    finally:
        await conn.close()
    return {"email": email, "code": code, "expires_at": expires_at, "used": False}


async def get_verification_code(email: str, code: str) -> Optional[dict]:
    """读取验证码记录（不修改 used 标志）。"""
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "SELECT email, code, expires_at, used FROM verification_codes "
            "WHERE email = ? AND code = ?",
            (email, code),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "email": row["email"],
            "code": row["code"],
            "expires_at": row["expires_at"],
            "used": bool(row["used"]),
        }
    finally:
        await conn.close()


async def verify_code(email: str, code: str) -> bool:
    """校验验证码：存在 + 未过期 + 未使用 → 标记 used=True 并返回 True；否则 False。"""
    now = datetime.now(timezone.utc)
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "SELECT expires_at, used FROM verification_codes WHERE email = ? AND code = ?",
            (email, code),
        )
        row = await cursor.fetchone()
        if not row:
            return False
        if bool(row["used"]):
            return False
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at < now:
            return False
        await conn.execute(
            "UPDATE verification_codes SET used = 1 WHERE email = ? AND code = ?",
            (email, code),
        )
        await conn.commit()
        return True
    finally:
        await conn.close()


def generate_code() -> str:
    """生成 6 位随机数字验证码（zero-padded，secrets 保证加密学随机）。"""
    return f"{secrets.randbelow(1000000):06d}"
