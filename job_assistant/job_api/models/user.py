"""用户与验证码数据访问层（SQLite + aiosqlite）。

表结构：
- users: id(UUID str), email(unique), password_hash, is_verified, device_fingerprint?,
        is_admin(0/1), is_active(0/1), notes(TEXT), xhs_order_id(unique?), created_at, last_login_at?
- verification_codes: email, code(6位), expires_at, used

所有函数均幂等可重入；init_db 使用 CREATE TABLE IF NOT EXISTS。
对已存在的旧 users 表（缺 is_admin/is_active/notes/xhs_order_id 列），_migrate_users_table 会幂等补列。
"""
from __future__ import annotations

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
        "is_admin": bool(row["is_admin"]),
        "is_active": bool(row["is_active"]),
        "notes": row["notes"],
        "xhs_order_id": row["xhs_order_id"] if "xhs_order_id" in row.keys() else None,
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
    }


async def _migrate_users_table(conn: aiosqlite.Connection) -> None:
    """对已存在的旧 users 表幂等补列（is_admin / is_active / notes / xhs_order_id）。

    SQLite 的 ALTER TABLE ADD COLUMN 不幂等（重复加会报错），
    所以先用 PRAGMA table_info 查现有列，缺哪补哪。
    """
    cursor = await conn.execute("PRAGMA table_info(users)")
    existing_cols = {row[1] for row in await cursor.fetchall()}
    new_columns = [
        ("is_admin", "INTEGER NOT NULL DEFAULT 0"),
        ("is_active", "INTEGER NOT NULL DEFAULT 1"),
        ("notes", "TEXT"),
        ("xhs_order_id", "TEXT"),
    ]
    for col_name, col_def in new_columns:
        if col_name not in existing_cols:
            await conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")
    # 对 xhs_order_id 加唯一索引（同一订单号只能注册一次）
    # 用 IF NOT EXISTS 让重复执行不报错
    try:
        await conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_xhs_order_id "
            "ON users(xhs_order_id) WHERE xhs_order_id IS NOT NULL"
        )
    except Exception:
        # 老版本 SQLite 不支持部分索引，退化为普通唯一索引
        pass


async def init_db() -> None:
    """幂等建表（CREATE TABLE IF NOT EXISTS）+ 旧表迁移。"""
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
                is_admin INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                notes TEXT,
                xhs_order_id TEXT,
                created_at TEXT NOT NULL,
                last_login_at TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_xhs_order_id
                ON users(xhs_order_id) WHERE xhs_order_id IS NOT NULL;
            CREATE TABLE IF NOT EXISTS verification_codes (
                email TEXT NOT NULL,
                code TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (email, code)
            );
            """
        )
        # 对旧版 users 表（缺 is_admin/is_active/notes 列）幂等补列
        await _migrate_users_table(conn)
        await conn.commit()
    finally:
        await conn.close()


async def create_user(
    email: str, password_hash: str, xhs_order_id: Optional[str] = None
) -> dict:
    """创建未验证用户，返回用户 dict。email/xhs_order_id 唯一冲突时抛 IntegrityError。"""
    user_id = str(uuid.uuid4())
    now = _now_iso()
    conn = await _connect()
    try:
        await conn.execute(
            "INSERT INTO users (id, email, password_hash, is_verified, xhs_order_id, created_at) "
            "VALUES (?, ?, ?, 0, ?, ?)",
            (user_id, email, password_hash, xhs_order_id, now),
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
        "xhs_order_id": xhs_order_id,
        "created_at": now,
        "last_login_at": None,
    }


async def get_user_by_email(email: str) -> Optional[dict]:
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "SELECT id, email, password_hash, is_verified, device_fingerprint, "
            "is_admin, is_active, notes, xhs_order_id, created_at, last_login_at "
            "FROM users WHERE email = ?",
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
            "is_admin, is_active, notes, xhs_order_id, created_at, last_login_at "
            "FROM users WHERE id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        return _row_to_user(row) if row else None
    finally:
        await conn.close()


async def get_user_by_xhs_order_id(xhs_order_id: str) -> Optional[dict]:
    """按 XHS 订单号查用户（注册时校验唯一性用）。"""
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "SELECT id, email, password_hash, is_verified, device_fingerprint, "
            "is_admin, is_active, notes, xhs_order_id, created_at, last_login_at "
            "FROM users WHERE xhs_order_id = ?",
            (xhs_order_id,),
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


# ====== 管理后台用 ======


async def list_users(
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
) -> tuple[list[dict], int]:
    """分页列出用户（脱敏：不含 password_hash），返回 (users, total)。

    search 非空时按 email / notes / xhs_order_id 模糊匹配。
    """
    where_clause = ""
    params: list = []
    if search:
        where_clause = "WHERE email LIKE ? OR notes LIKE ? OR xhs_order_id LIKE ?"
        like = f"%{search}%"
        params = [like, like, like]
    conn = await _connect()
    try:
        # 总数
        cursor = await conn.execute(f"SELECT COUNT(*) FROM users {where_clause}", params)
        total = (await cursor.fetchone())[0]
        # 列表（脱敏：不查 password_hash）
        cursor = await conn.execute(
            f"SELECT id, email, is_verified, device_fingerprint, is_admin, "
            f"is_active, notes, xhs_order_id, created_at, last_login_at "
            f"FROM users {where_clause} "
            f"ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
        rows = await cursor.fetchall()
        users = [
            {
                "id": r["id"],
                "email": r["email"],
                "is_verified": bool(r["is_verified"]),
                "device_fingerprint": r["device_fingerprint"],
                "is_admin": bool(r["is_admin"]),
                "is_active": bool(r["is_active"]),
                "notes": r["notes"],
                "xhs_order_id": r["xhs_order_id"],
                "created_at": r["created_at"],
                "last_login_at": r["last_login_at"],
            }
            for r in rows
        ]
        return users, total
    finally:
        await conn.close()


async def bulk_set_active_status(user_ids: list[str], is_active: bool) -> int:
    """批量 启用/停用 用户，返回受影响行数。管理员批量审核时用。"""
    if not user_ids:
        return 0
    conn = await _connect()
    try:
        placeholders = ",".join("?" * len(user_ids))
        cursor = await conn.execute(
            f"UPDATE users SET is_active = ? WHERE id IN ({placeholders})",
            [1 if is_active else 0] + user_ids,
        )
        await conn.commit()
        return cursor.rowcount
    finally:
        await conn.close()


async def set_admin_status(user_id: str, is_admin: bool) -> None:
    """设置/取消管理员标记。"""
    conn = await _connect()
    try:
        await conn.execute(
            "UPDATE users SET is_admin = ? WHERE id = ?",
            (1 if is_admin else 0, user_id),
        )
        await conn.commit()
    finally:
        await conn.close()


async def set_active_status(user_id: str, is_active: bool) -> None:
    """吊销 (is_active=0) 或恢复 (is_active=1) 用户。被吊销的用户登录会被拒绝。"""
    conn = await _connect()
    try:
        await conn.execute(
            "UPDATE users SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, user_id),
        )
        await conn.commit()
    finally:
        await conn.close()


async def update_notes(user_id: str, notes: Optional[str]) -> None:
    """更新管理员备注（如微信昵称、付费时间、退款原因等）。"""
    conn = await _connect()
    try:
        await conn.execute(
            "UPDATE users SET notes = ? WHERE id = ?",
            (notes, user_id),
        )
        await conn.commit()
    finally:
        await conn.close()


async def delete_user(user_id: str) -> bool:
    """删除用户。返回是否删除成功（用户存在且非最后一个管理员）。"""
    conn = await _connect()
    try:
        # 不允许删除最后一个管理员（避免失去管理能力）
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM users WHERE is_admin = 1"
        )
        admin_count = (await cursor.fetchone())[0]
        cursor = await conn.execute(
            "SELECT is_admin FROM users WHERE id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return False
        if bool(row["is_admin"]) and admin_count <= 1:
            return False  # 拒绝删除最后一个管理员
        await conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await conn.execute(
            "DELETE FROM verification_codes WHERE email IN "
            "(SELECT email FROM users WHERE id = ?)",  # 已被删，空操作
            (user_id,),
        )
        await conn.commit()
        return True
    finally:
        await conn.close()


async def mark_admin_by_email(email: str) -> bool:
    """把指定邮箱的用户标记为管理员（启动时由 ADMIN_EMAIL 调用）。

    返回是否标记成功（用户必须已存在）。建议管理员先正常注册一次再启用此机制。
    """
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "UPDATE users SET is_admin = 1 WHERE email = ?", (email,)
        )
        await conn.commit()
        return cursor.rowcount > 0
    finally:
        await conn.close()
