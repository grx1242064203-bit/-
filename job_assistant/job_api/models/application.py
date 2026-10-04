"""投递记录模型：收藏/投递/面试/offer 全流程管理。"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from config import get_settings

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    job_id TEXT NOT NULL,
    job_title TEXT NOT NULL,
    company_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'favorite',
    apply_url TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, job_id)
);
CREATE INDEX IF NOT EXISTS idx_app_user ON applications(user_id);
CREATE INDEX IF NOT EXISTS idx_app_status ON applications(status);
"""

VALID_STATUSES = ("favorite", "applied", "interview", "offer", "rejected")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_settings().AUTH_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA_SQL)
    return conn


async def init_db() -> None:
    """建表（幂等）。"""
    conn = _connect()
    conn.close()


def _row_to_app(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "job_id": row["job_id"],
        "job_title": row["job_title"],
        "company_name": row["company_name"],
        "status": row["status"],
        "apply_url": row["apply_url"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def create_application(
    user_id: int,
    job_id: str,
    job_title: str,
    company_name: str = "",
    status: str = "favorite",
    apply_url: str = "",
    notes: str = "",
) -> dict:
    """创建投递记录（收藏或投递）。已存在则更新状态。"""
    if status not in VALID_STATUSES:
        status = "favorite"
    now = datetime.now().isoformat(timespec="seconds")
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO applications
               (user_id, job_id, job_title, company_name, status, apply_url, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, job_id) DO UPDATE SET
                   status=excluded.status,
                   apply_url=excluded.apply_url,
                   notes=excluded.notes,
                   updated_at=excluded.updated_at""",
            (user_id, job_id, job_title, company_name, status, apply_url, notes, now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM applications WHERE user_id=? AND job_id=?",
            (user_id, job_id),
        ).fetchone()
        return _row_to_app(row) if row else {}
    finally:
        conn.close()


async def update_application(
    app_id: int,
    user_id: int,
    status: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict | None:
    """更新投递记录状态或备注。"""
    now = datetime.now().isoformat(timespec="seconds")
    conn = _connect()
    try:
        sets = ["updated_at=?"]
        params: list = [now]
        if status and status in VALID_STATUSES:
            sets.append("status=?")
            params.append(status)
        if notes is not None:
            sets.append("notes=?")
            params.append(notes)
        params.extend([app_id, user_id])
        conn.execute(
            f"UPDATE applications SET {', '.join(sets)} WHERE id=? AND user_id=?",
            params,
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM applications WHERE id=? AND user_id=?", (app_id, user_id)
        ).fetchone()
        return _row_to_app(row) if row else None
    finally:
        conn.close()


async def delete_application(app_id: int, user_id: int) -> bool:
    """删除投递记录。"""
    conn = _connect()
    try:
        cur = conn.execute(
            "DELETE FROM applications WHERE id=? AND user_id=?", (app_id, user_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


async def list_applications(user_id: int, status: str = "") -> list[dict]:
    """列出用户的投递记录。status 为空时返回全部。"""
    conn = _connect()
    try:
        if status and status in VALID_STATUSES:
            rows = conn.execute(
                "SELECT * FROM applications WHERE user_id=? AND status=? ORDER BY updated_at DESC",
                (user_id, status),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM applications WHERE user_id=? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        return [_row_to_app(r) for r in rows]
    finally:
        conn.close()
