"""邮件抓取与分类任务数据访问层。

表结构：
- emails: id, user_id, account_id, message_id(唯一), subject, sender, from_addr,
  received_at, body_text, body_html, raw_headers, created_at
- email_tasks: id, user_id, email_id, task_type(assessment/written/interview),
  company, job_title, event_time, event_link, email_link, notes,
  status(pending/confirmed/ignored), created_at, confirmed_at,
  extract_status(pending/llm_done/llm_failed/rule_fallback) — AI 提取状态
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

# AI 提取状态枚举：
# - pending:        初筛命中后任务已创建，字段为空，等待 LLM 异步提取
# - llm_done:       LLM 提取成功，字段已回填
# - llm_failed:     LLM 调用失败（超时/配额/Key 无效）
# - rule_fallback:  LLM 失败后回退到规则提取
EXTRACT_STATUS_PENDING = "pending"
EXTRACT_STATUS_LLM_DONE = "llm_done"
EXTRACT_STATUS_LLM_FAILED = "llm_failed"
EXTRACT_STATUS_RULE_FALLBACK = "rule_fallback"


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
                extract_status TEXT NOT NULL DEFAULT 'pending',
                FOREIGN KEY (email_id) REFERENCES emails(id)
            );
            """
        )
        # 旧表迁移：补 extract_status 列（幂等）
        # 注意：aiosqlite 的 conn.execute() 是 coroutine，必须分两步 await
        # 错误写法：await conn.execute(...).fetchall()  ← .fetchall 在 coroutine 上不存在
        # 正确写法：先 await execute 拿 cursor，再 await cursor.fetchall()
        cursor = await conn.execute("PRAGMA table_info(email_tasks)")
        cols = {r[1] for r in await cursor.fetchall()}
        if "extract_status" not in cols:
            await conn.execute(
                "ALTER TABLE email_tasks ADD COLUMN extract_status "
                "TEXT NOT NULL DEFAULT 'pending'"
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
        "extract_status": row["extract_status"],
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
    extract_status: str = EXTRACT_STATUS_PENDING,
) -> dict:
    """创建任务。extract_status 默认 pending（字段为空，等待 LLM 回填）。

    异步 LLM 流程：
    1. 初筛命中 → create_task(extract_status="pending", company=None, ...)
    2. LLM 完成 → update_task_extract_status(llm_done, company=..., ...)
    3. LLM 失败 → update_task_extract_status(rule_fallback) + 规则提取回填
    """
    task_id = str(uuid.uuid4())
    now = _now_iso()
    conn = await _connect()
    try:
        await conn.execute(
            "INSERT INTO email_tasks "
            "(id, user_id, email_id, task_type, company, job_title, event_time, "
            "event_link, email_link, notes, status, created_at, extract_status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task_id, user_id, email_id, task_type, company, job_title,
                event_time, event_link, email_link, notes, TASK_STATUS_PENDING,
                now, extract_status,
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
        "schedule_id": None, "extract_status": extract_status,
    }


async def update_task_extract(
    task_id: str,
    user_id: str,
    company: Optional[str] = None,
    job_title: Optional[str] = None,
    event_time: Optional[str] = None,
    event_link: Optional[str] = None,
    notes: Optional[str] = None,
    extract_status: str = EXTRACT_STATUS_LLM_DONE,
) -> bool:
    """LLM/规则提取完成后回填任务字段。仅 pending 状态的任务可回填。

    confirmed/ignored 状态的任务不允许回填（用户已处理）。
    """
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "UPDATE email_tasks SET "
            "company = COALESCE(?, company), "
            "job_title = COALESCE(?, job_title), "
            "event_time = COALESCE(?, event_time), "
            "event_link = COALESCE(?, event_link), "
            "notes = COALESCE(?, notes), "
            "extract_status = ? "
            "WHERE id = ? AND user_id = ? AND status = ?",
            (
                company, job_title, event_time, event_link, notes,
                extract_status, task_id, user_id, TASK_STATUS_PENDING,
            ),
        )
        await conn.commit()
        return cursor.rowcount > 0
    finally:
        await conn.close()


async def update_task_extract_status(
    task_id: str, user_id: str, extract_status: str
) -> bool:
    """仅更新提取状态（不回填字段）。"""
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "UPDATE email_tasks SET extract_status = ? "
            "WHERE id = ? AND user_id = ? AND status = ?",
            (extract_status, task_id, user_id, TASK_STATUS_PENDING),
        )
        await conn.commit()
        return cursor.rowcount > 0
    finally:
        await conn.close()


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
