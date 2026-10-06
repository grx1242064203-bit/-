"""邮箱账户数据访问层（SQLite + aiosqlite）。

表结构：
- email_accounts: id, user_id, email, imap_server, imap_port, username,
  password_encrypted, created_at, last_sync_at

IMAP 密码使用 Fernet 对称加密存储，密钥来自 settings.EMAIL_ENCRYPTION_KEY。
若未配置密钥，自动生成一个临时密钥（仅进程内存，重启后需重填密码）。
"""
import base64
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite
from cryptography.fernet import Fernet, InvalidToken

from config import get_settings

# 内存缓存的 Fernet 实例（密钥未配置时用临时密钥）
_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    """获取 Fernet 实例。密钥未配置时生成临时密钥（仅当前进程有效）。

    警告：临时密钥模式下，进程重启后所有已存邮箱密码将无法解密。
    生产部署必须通过环境变量 EMAIL_ENCRYPTION_KEY 配置固定密钥。
    """
    global _fernet
    if _fernet is not None:
        return _fernet
    settings = get_settings()
    key = settings.EMAIL_ENCRYPTION_KEY.strip()
    if not key:
        # 开发模式：生成临时密钥，重启失效
        key = Fernet.generate_key().decode()
        print(
            "=" * 60 + "\n"
            "[email_account] ⚠️  EMAIL_ENCRYPTION_KEY 未配置，使用临时密钥。\n"
            "  ⚠️  进程重启后，所有已保存的邮箱账户密码将无法解密（功能失效）。\n"
            "  生产部署必须配置固定密钥，生成方法：\n"
            '    python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"\n'
            + "=" * 60
        )
    try:
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        # 密钥格式不对，降级为临时密钥
        key = Fernet.generate_key().decode()
        print(
            "[email_account] ⚠️ EMAIL_ENCRYPTION_KEY 格式无效，降级为临时密钥"
            "（重启后已存邮箱密码失效）"
        )
        _fernet = Fernet(key.encode())
    return _fernet


def encrypt_password(password: str) -> str:
    """加密密码，返回 base64 字符串。"""
    return _get_fernet().encrypt(password.encode("utf-8")).decode("utf-8")


def decrypt_password(token: str) -> str:
    """解密密码。失败返回空串。"""
    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        return ""


def _db_path() -> Path:
    return Path(get_settings().DATA_DIR) / "auth.db"


async def _connect() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(str(_db_path()))
    conn.row_factory = aiosqlite.Row
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_account(row: aiosqlite.Row) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "email": row["email"],
        "imap_server": row["imap_server"],
        "imap_port": row["imap_port"],
        "username": row["username"],
        # 不返回密码
        "created_at": row["created_at"],
        "last_sync_at": row["last_sync_at"],
    }


async def init_db() -> None:
    conn = await _connect()
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS email_accounts (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                email TEXT NOT NULL,
                imap_server TEXT NOT NULL,
                imap_port INTEGER NOT NULL DEFAULT 993,
                username TEXT NOT NULL,
                password_encrypted TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_sync_at TEXT,
                UNIQUE(user_id, email)
            );
            """
        )
        await conn.commit()
    finally:
        await conn.close()


async def create_account(
    user_id: str,
    email: str,
    imap_server: str,
    imap_port: int,
    username: str,
    password: str,
) -> dict:
    account_id = str(uuid.uuid4())
    now = _now_iso()
    enc = encrypt_password(password)
    conn = await _connect()
    try:
        await conn.execute(
            "INSERT INTO email_accounts "
            "(id, user_id, email, imap_server, imap_port, username, password_encrypted, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (account_id, user_id, email, imap_server, imap_port, username, enc, now),
        )
        await conn.commit()
    finally:
        await conn.close()
    return {
        "id": account_id,
        "user_id": user_id,
        "email": email,
        "imap_server": imap_server,
        "imap_port": imap_port,
        "username": username,
        "created_at": now,
        "last_sync_at": None,
    }


async def list_accounts(user_id: str) -> list[dict]:
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "SELECT id, user_id, email, imap_server, imap_port, username, "
            "created_at, last_sync_at FROM email_accounts WHERE user_id = ? "
            "ORDER BY created_at DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_account(r) for r in rows]
    finally:
        await conn.close()


async def get_account(account_id: str, user_id: str) -> Optional[dict]:
    """获取账户（含解密后的密码，供 IMAP 连接用）。"""
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "SELECT * FROM email_accounts WHERE id = ? AND user_id = ?",
            (account_id, user_id),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            **_row_to_account(row),
            "password": decrypt_password(row["password_encrypted"]),
        }
    finally:
        await conn.close()


async def delete_account(account_id: str, user_id: str) -> bool:
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "DELETE FROM email_accounts WHERE id = ? AND user_id = ?",
            (account_id, user_id),
        )
        await conn.commit()
        return cursor.rowcount > 0
    finally:
        await conn.close()


async def update_last_sync(account_id: str) -> None:
    conn = await _connect()
    try:
        await conn.execute(
            "UPDATE email_accounts SET last_sync_at = ? WHERE id = ?",
            (_now_iso(), account_id),
        )
        await conn.commit()
    finally:
        await conn.close()
