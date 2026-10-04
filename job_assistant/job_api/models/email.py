"""邮件抓取与分类任务数据访问层。

表结构：
- emails: id, user_id, account_id, message_id(唯一), subject, sender, from_addr,
  received_at, body_text, body_html, raw_headers, created_at
- email_tasks: id, user_id, email_id, task_type(assessment/written/interview),
  company, job_title, event_time, event_link, email_link, notes,
  status(pending/confirmed/ignored), created_at, confirmed_at
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

from config import get_settings

TASK_TYPE_ASSESSMENT = "assessment"
TASK_TYPE_WRITTEN = "written"
TASK_TYPE_INTERVIEW = "interview"

TASK_STATUS_PENDING = "pending"
TASK_STATUS_CONFIRMED = "confirmed"
TASK_STATUS_IGNORED = "ignored"


def _db_path() -> Path:
    return Path(get_settings().DATA_DIR) / "auth.db"


async def _connect() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(str(_db_path()))
    conn.row_factory = aiosqlite.Row
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    conn = await _connect()
    try:
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS emails (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                subject TEXT,
                sender TEXT,
                from_addr TEXT,
                received_at TEXT,
                body_text TEXT,
                body_html TEXT,
                raw_headers TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, message_id)
            );

            CREATE TABLE IF NOT EXISTS email_tasks (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                email_id TEXT NOT NULL,
                task_type TEXT NOT NULL,
                company TEXT,
                job_title TEXT,
                event_time TEXT,
                event_link TEXT,
                email_link TEXT,
                notes TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                confirmed_at TEXT,
                application_id TEXT,
                schedule_id TEXT,
                FOREIGN KEY (email_id) REFERENCES emails(id)
            );
            """
        )
        await conn.commit()
    finally:
        await conn.close()


# ---- emails ----

async def insert_email(
    user_id: str,
    account_id: str,
    message_id: str,
    subject: str,
    sender: str,
    from_addr: str,
    received_at: str,
    body_text: str,
    body_html: str,
    raw_headers: str,
) -> Optional[dict]:
    """插入一封邮件。message_id 冲突时返回 None（已存在）。"""
    email_id = str(uuid.uuid4())
    now = _now_iso()
    conn = await _connect()
    try:
        await conn.execute(
            "INSERT INTO emails "
            "(id, user_id, account_id, message_id, subject, sender, from_addr, "
            "received_at, body_text, body_html, raw_headers, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                email_id, user_id, account_id, message_id, subject, sender,
                from_addr, received_at, body_text, body_html, raw_headers, now,
            ),
        )
        await conn.commit()
        return {"id": email_id, "message_id": message_id}
    except aiosqlite.IntegrityError:
        return None
    finally:
        await conn.close()


async def get_email(email_id: str, user_id: str) -> Optional[dict]:
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "SELECT * FROM emails WHERE id = ? AND user_id = ?",
            (email_id, user_id),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        await conn.close()


# ---- email_tasks ----

def _row_to_task(row: aiosqlite.Row) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "email_id": row["email_id"],
        "task_type": row["task_type"],
        "company": row["company"],
        "job_title": row["job_title"],
        "event_time": row["event_time"],
        "event_link": row["event_link"],
        "email_link": row["email_link"],
        "notes": row["notes"],
        "status": row["status"],
        "created_at": row["created_at"],
        "confirmed_at": row["confirmed_at"],
        "application_id": row["application_id"],
        "schedule_id": row["schedule_id"],
    }


async def create_task(
    user_id: str,
    email_id: str,
    task_type: str,
    company: Optional[str] = None,
    job_title: Optional[str] = None,
    event_time: Optional[str] = None,
    event_link: Optional[str] = None,
    email_link: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    task_id = str(uuid.uuid4())
    now = _now_iso()
    conn = await _connect()
    try:
        await conn.execute(
            "INSERT INTO email_tasks "
            "(id, user_id, email_id, task_type, company, job_title, event_time, "
            "event_link, email_link, notes, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task_id, user_id, email_id, task_type, company, job_title,
                event_time, event_link, email_link, notes, TASK_STATUS_PENDING, now,
            ),
        )
        await conn.commit()
    finally:
        await conn.close()
    return {
        "id": task_id, "user_id": user_id, "email_id": email_id,
        "task_type": task_type, "company": company, "job_title": job_title,
        "event_time": event_time, "event_link": event_link,
        "email_link": email_link, "notes": notes, "status": TASK_STATUS_PENDING,
        "created_at": now, "confirmed_at": None, "application_id": None,
        "schedule_id": None,
    }


async def list_tasks(
    user_id: str, status: Optional[str] = None
) -> list[dict]:
    conn = await _connect()
    try:
        if status:
            cursor = await conn.execute(
                "SELECT * FROM email_tasks WHERE user_id = ? AND status = ? "
                "ORDER BY created_at DESC",
                (user_id, status),
            )
        else:
            cursor = await conn.execute(
                "SELECT * FROM email_tasks WHERE user_id = ? "
                "ORDER BY created_at DESC",
                (user_id,),
            )
        rows = await cursor.fetchall()
        return [_row_to_task(r) for r in rows]
    finally:
        await conn.close()


async def get_task(task_id: str, user_id: str) -> Optional[dict]:
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "SELECT * FROM email_tasks WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        )
        row = await cursor.fetchone()
        return _row_to_task(row) if row else None
    finally:
        await conn.close()


async def confirm_task(
    task_id: str, user_id: str, application_id: str, schedule_id: str
) -> bool:
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "UPDATE email_tasks SET status = ?, confirmed_at = ?, "
            "application_id = ?, schedule_id = ? WHERE id = ? AND user_id = ?",
            (TASK_STATUS_CONFIRMED, _now_iso(), application_id, schedule_id,
             task_id, user_id),
        )
        await conn.commit()
        return cursor.rowcount > 0
    finally:
        await conn.close()


async def ignore_task(task_id: str, user_id: str) -> bool:
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "UPDATE email_tasks SET status = ? WHERE id = ? AND user_id = ?",
            (TASK_STATUS_IGNORED, task_id, user_id),
        )
        await conn.commit()
        return cursor.rowcount > 0
    finally:
        await conn.close()
