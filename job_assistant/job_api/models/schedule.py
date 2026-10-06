"""日程与提醒数据访问层。

表结构：
- schedules: id, user_id, application_id, company, job_title, schedule_type,
  event_time, duration_minutes, email_link, meeting_link, notes,
  created_at, verified_at
- reminders: id, schedule_id, user_id, remind_at, fired, fired_at

稳定性规则：
- 创建日程后必须回读验证（schedule_service 层执行）
- 不允许自动删除日程：只有显式 DELETE 接口，无定时清理
"""
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

from config import get_settings

SCHEDULE_TYPE_ASSESSMENT = "assessment"
SCHEDULE_TYPE_WRITTEN = "written"
SCHEDULE_TYPE_INTERVIEW = "interview"

DEFAULT_REMINDER_OFFSETS_MINUTES = [120, 30]  # 开始前 2h、30min


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
            CREATE TABLE IF NOT EXISTS schedules (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                application_id TEXT,
                company TEXT,
                job_title TEXT,
                schedule_type TEXT NOT NULL,
                event_time TEXT NOT NULL,
                duration_minutes INTEGER DEFAULT 60,
                email_link TEXT,
                meeting_link TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                verified_at TEXT
            );

            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY,
                schedule_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                remind_at TEXT NOT NULL,
                fired INTEGER NOT NULL DEFAULT 0,
                fired_at TEXT,
                FOREIGN KEY (schedule_id) REFERENCES schedules(id)
            );
            """
        )
        await conn.commit()
    finally:
        await conn.close()


def _row_to_schedule(row: aiosqlite.Row) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "application_id": row["application_id"],
        "company": row["company"],
        "job_title": row["job_title"],
        "schedule_type": row["schedule_type"],
        "event_time": row["event_time"],
        "duration_minutes": row["duration_minutes"],
        "email_link": row["email_link"],
        "meeting_link": row["meeting_link"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "verified_at": row["verified_at"],
    }


async def create_schedule(
    user_id: str,
    schedule_type: str,
    event_time: str,
    application_id: Optional[str] = None,
    company: Optional[str] = None,
    job_title: Optional[str] = None,
    duration_minutes: int = 60,
    email_link: Optional[str] = None,
    meeting_link: Optional[str] = None,
    notes: Optional[str] = None,
    reminder_offsets_minutes: Optional[list[int]] = None,
) -> dict:
    """创建日程并自动生成提醒。调用方负责回读验证。"""
    schedule_id = str(uuid.uuid4())
    now = _now_iso()
    offsets = reminder_offsets_minutes or DEFAULT_REMINDER_OFFSETS_MINUTES

    conn = await _connect()
    try:
        await conn.execute(
            "INSERT INTO schedules "
            "(id, user_id, application_id, company, job_title, schedule_type, "
            "event_time, duration_minutes, email_link, meeting_link, notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                schedule_id, user_id, application_id, company, job_title,
                schedule_type, event_time, duration_minutes, email_link,
                meeting_link, notes, now,
            ),
        )

        # 生成提醒
        try:
            event_dt = datetime.fromisoformat(event_time)
        except (ValueError, TypeError):
            event_dt = datetime.now(timezone.utc)

        for offset_min in offsets:
            remind_at = (event_dt - timedelta(minutes=offset_min)).isoformat()
            reminder_id = str(uuid.uuid4())
            await conn.execute(
                "INSERT INTO reminders (id, schedule_id, user_id, remind_at, fired) "
                "VALUES (?, ?, ?, ?, 0)",
                (reminder_id, schedule_id, user_id, remind_at),
            )

        await conn.commit()
    finally:
        await conn.close()

    return {"id": schedule_id, "created_at": now}


async def get_schedule(schedule_id: str, user_id: str) -> Optional[dict]:
    """回读验证用。"""
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "SELECT * FROM schedules WHERE id = ? AND user_id = ?",
            (schedule_id, user_id),
        )
        row = await cursor.fetchone()
        return _row_to_schedule(row) if row else None
    finally:
        await conn.close()


async def mark_verified(schedule_id: str) -> None:
    conn = await _connect()
    try:
        await conn.execute(
            "UPDATE schedules SET verified_at = ? WHERE id = ?",
            (_now_iso(), schedule_id),
        )
        await conn.commit()
    finally:
        await conn.close()


async def list_schedules(user_id: str) -> list[dict]:
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "SELECT * FROM schedules WHERE user_id = ? ORDER BY event_time ASC",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_schedule(r) for r in rows]
    finally:
        await conn.close()


async def list_schedules_with_reminders(user_id: str) -> list[dict]:
    """带提醒列表的日程查询（前端日程视图用）。"""
    conn = await _connect()
    try:
        schedules = await list_schedules(user_id)
        for s in schedules:
            cursor = await conn.execute(
                "SELECT id, remind_at, fired, fired_at FROM reminders "
                "WHERE schedule_id = ? ORDER BY remind_at ASC",
                (s["id"],),
            )
            s["reminders"] = [dict(r) for r in await cursor.fetchall()]
        return schedules
    finally:
        await conn.close()


async def delete_schedule(schedule_id: str, user_id: str) -> bool:
    """显式删除日程及其提醒。仅用户主动调用，无自动删除。"""
    conn = await _connect()
    try:
        await conn.execute(
            "DELETE FROM reminders WHERE schedule_id = ? AND user_id = ?",
            (schedule_id, user_id),
        )
        cursor = await conn.execute(
            "DELETE FROM schedules WHERE id = ? AND user_id = ?",
            (schedule_id, user_id),
        )
        await conn.commit()
        return cursor.rowcount > 0
    finally:
        await conn.close()


async def update_schedule(
    schedule_id: str,
    user_id: str,
    schedule_type: Optional[str] = None,
    event_time: Optional[str] = None,
    company: Optional[str] = None,
    job_title: Optional[str] = None,
    duration_minutes: Optional[int] = None,
    meeting_link: Optional[str] = None,
    notes: Optional[str] = None,
) -> Optional[dict]:
    """更新日程字段（仅传非 None 的字段）。返回更新后的日程，不存在则返回 None。

    若 event_time 变更，会删除旧提醒并按默认偏移重新生成。
    """
    conn = await _connect()
    try:
        existing = await conn.execute(
            "SELECT * FROM schedules WHERE id = ? AND user_id = ?",
            (schedule_id, user_id),
        )
        row = await existing.fetchone()
        if not row:
            return None

        sets: list[str] = []
        params: list = []
        if schedule_type is not None:
            sets.append("schedule_type = ?")
            params.append(schedule_type)
        if event_time is not None:
            sets.append("event_time = ?")
            params.append(event_time)
        if company is not None:
            sets.append("company = ?")
            params.append(company)
        if job_title is not None:
            sets.append("job_title = ?")
            params.append(job_title)
        if duration_minutes is not None:
            sets.append("duration_minutes = ?")
            params.append(duration_minutes)
        if meeting_link is not None:
            sets.append("meeting_link = ?")
            params.append(meeting_link)
        if notes is not None:
            sets.append("notes = ?")
            params.append(notes)

        if not sets:
            return _row_to_schedule(row)

        sql = f"UPDATE schedules SET {', '.join(sets)} WHERE id = ? AND user_id = ?"
        params.extend([schedule_id, user_id])
        await conn.execute(sql, params)

        # event_time 变更时重置提醒
        if event_time is not None:
            await conn.execute(
                "DELETE FROM reminders WHERE schedule_id = ? AND user_id = ?",
                (schedule_id, user_id),
            )
            try:
                event_dt = datetime.fromisoformat(event_time)
            except (ValueError, TypeError):
                event_dt = datetime.now(timezone.utc)
            for offset_min in DEFAULT_REMINDER_OFFSETS_MINUTES:
                remind_at = (event_dt - timedelta(minutes=offset_min)).isoformat()
                await conn.execute(
                    "INSERT INTO reminders (id, schedule_id, user_id, remind_at, fired) "
                    "VALUES (?, ?, ?, ?, 0)",
                    (str(uuid.uuid4()), schedule_id, user_id, remind_at),
                )

        await conn.commit()

        updated = await conn.execute(
            "SELECT * FROM schedules WHERE id = ? AND user_id = ?",
            (schedule_id, user_id),
        )
        new_row = await updated.fetchone()
        return _row_to_schedule(new_row) if new_row else None
    finally:
        await conn.close()


# ---- reminders ----

async def get_due_reminders(now_iso: Optional[str] = None) -> list[dict]:
    """获取到期未触发的提醒（Rust 调度器或轮询用）。"""
    now = now_iso or _now_iso()
    conn = await _connect()
    try:
        cursor = await conn.execute(
            "SELECT r.id, r.schedule_id, r.user_id, r.remind_at, "
            "s.company, s.job_title, s.schedule_type, s.event_time, "
            "s.meeting_link "
            "FROM reminders r JOIN schedules s ON r.schedule_id = s.id "
            "WHERE r.fired = 0 AND r.remind_at <= ?",
            (now,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def mark_reminder_fired(reminder_id: str) -> None:
    conn = await _connect()
    try:
        await conn.execute(
            "UPDATE reminders SET fired = 1, fired_at = ? WHERE id = ?",
            (_now_iso(), reminder_id),
        )
        await conn.commit()
    finally:
        await conn.close()
