"""投递记录模型：收藏/投递/测评/面试/offer 全流程管理。

支持多来源：
- db_job     : 关联岗位数据库（jobs 表）
- db_company : 关联公司数据库（companies 表）
- manual     : 用户自建，不关联 DB
- email      : 邮件同步，不关联 DB
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from config import get_settings

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    job_id TEXT DEFAULT '',
    job_title TEXT NOT NULL DEFAULT '',
    company_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'favorite',
    source TEXT NOT NULL DEFAULT 'manual',
    link_type TEXT,
    link_id TEXT,
    interview_round INTEGER NOT NULL DEFAULT 0,
    apply_url TEXT DEFAULT '',
    announcement_url TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    email_id TEXT,
    favorite_at TEXT,
    applied_at TEXT,
    assessment_at TEXT,
    interview_at TEXT,
    offer_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_app_user ON applications(user_id);
CREATE INDEX IF NOT EXISTS idx_app_status ON applications(status);
"""

# 依赖迁移列的索引（必须在 _migrate 补完列后再创建）
_INDEX_AFTER_MIGRATE = """
CREATE INDEX IF NOT EXISTS idx_app_link ON applications(link_type, link_id);
"""

# 投递状态枚举：收藏 → 投递 → 测评 → 面试 → offer | 拒绝
VALID_STATUSES = ("favorite", "applied", "assessment", "interview", "offer", "rejected")

# 新增列迁移（旧表升级用）
_MIGRATION_COLUMNS = [
    ("source", "TEXT NOT NULL DEFAULT 'manual'"),
    ("link_type", "TEXT"),
    ("link_id", "TEXT"),
    ("interview_round", "INTEGER NOT NULL DEFAULT 0"),
    ("announcement_url", "TEXT DEFAULT ''"),
    ("email_id", "TEXT"),
    ("favorite_at", "TEXT"),
    ("applied_at", "TEXT"),
    ("assessment_at", "TEXT"),
    ("interview_at", "TEXT"),
    ("offer_at", "TEXT"),
]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_settings().AUTH_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA_SQL)
    _migrate(conn)
    # 补列完成后再创建依赖新列的索引（旧表升级时 link_type/link_id 还不存在）
    conn.executescript(_INDEX_AFTER_MIGRATE)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """为旧表补充新增列（幂等）。"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(applications)").fetchall()}
    for col_name, col_def in _MIGRATION_COLUMNS:
        if col_name not in cols:
            conn.execute(f"ALTER TABLE applications ADD COLUMN {col_name} {col_def}")
    conn.commit()


async def init_db() -> None:
    """建表（幂等）。"""
    conn = _connect()
    conn.close()


def _row_to_app(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "job_id": row["job_id"] or "",
        "job_title": row["job_title"],
        "company_name": row["company_name"],
        "status": row["status"],
        "source": row["source"],
        "link_type": row["link_type"],
        "link_id": row["link_id"],
        "interview_round": row["interview_round"] or 0,
        "apply_url": row["apply_url"] or "",
        "announcement_url": row["announcement_url"] or "",
        "notes": row["notes"],
        "email_id": row["email_id"],
        "favorite_at": row["favorite_at"],
        "applied_at": row["applied_at"],
        "assessment_at": row["assessment_at"],
        "interview_at": row["interview_at"],
        "offer_at": row["offer_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _status_timestamp_field(status: str) -> Optional[str]:
    """状态对应的时间戳字段名。"""
    return {
        "favorite": "favorite_at",
        "applied": "applied_at",
        "assessment": "assessment_at",
        "interview": "interview_at",
        "offer": "offer_at",
    }.get(status)


async def create_application(
    user_id: int,
    job_title: str,
    company_name: str = "",
    status: str = "favorite",
    source: str = "manual",
    link_type: Optional[str] = None,
    link_id: Optional[str] = None,
    apply_url: str = "",
    announcement_url: str = "",
    notes: str = "",
    email_id: Optional[str] = None,
    job_id: str = "",
) -> dict:
    """创建投递记录。

    - link_type='job' / 'company' 时 link_id 必填（关联 DB）
    - manual / email 来源 link_type/link_id 为 NULL
    - 同一 (user_id, link_type, link_id) 若已存在则更新状态
    """
    if status not in VALID_STATUSES:
        status = "favorite"
    now = datetime.now().isoformat(timespec="seconds")
    ts_field = _status_timestamp_field(status)

    conn = _connect()
    try:
        # 查找已有记录：
        # - DB 关联记录按 (link_type, link_id) 去重
        # - 手动/邮件来源按 (company_name, job_title) 精确匹配；
        #   若仅 company_name 有值则按 company_name 匹配（一个公司仅一条）
        existing = None
        if link_type and link_id:
            existing = conn.execute(
                "SELECT id FROM applications WHERE user_id=? AND link_type=? AND link_id=?",
                (user_id, link_type, link_id),
            ).fetchone()
        elif company_name and job_title:
            existing = conn.execute(
                "SELECT id FROM applications WHERE user_id=? AND company_name=? AND job_title=?",
                (user_id, company_name, job_title),
            ).fetchone()
        elif company_name:
            existing = conn.execute(
                "SELECT id FROM applications WHERE user_id=? AND company_name=?",
                (user_id, company_name),
            ).fetchone()

        if existing:
            # 匹配到已有记录：仅更新状态（及对应阶段时间戳、链接）
            sets = ["status=?", "updated_at=?"]
            params: list = [status, now]
            if ts_field:
                sets.append(f"{ts_field}=?")
                params.append(now)
            if status == "interview":
                sets.append("interview_round=COALESCE(NULLIF(interview_round, 0), 1)")
            elif status != "interview":
                sets.append("interview_round=0")
            if apply_url:
                sets.append("apply_url=?")
                params.append(apply_url)
            if announcement_url:
                sets.append("announcement_url=?")
                params.append(announcement_url)
            if job_title:
                sets.append("job_title=?")
                params.append(job_title)
            params.append(existing["id"])
            conn.execute(
                f"UPDATE applications SET {', '.join(sets)} WHERE id=?",
                params,
            )
            app_id = existing["id"]
        else:
            ts_value = now if ts_field else None
            interview_round = 1 if status == "interview" else 0
            conn.execute(
                """INSERT INTO applications
                   (user_id, job_id, job_title, company_name, status, source, link_type, link_id,
                    interview_round, apply_url, announcement_url, notes, email_id,
                    favorite_at, applied_at, assessment_at, interview_at, offer_at,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id, job_id or link_id or "", job_title, company_name, status, source,
                    link_type, link_id, interview_round, apply_url, announcement_url, notes, email_id,
                    now if status == "favorite" else None,
                    now if status == "applied" else None,
                    now if status == "assessment" else None,
                    now if status == "interview" else None,
                    now if status == "offer" else None,
                    now, now,
                ),
            )
            app_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()

        row = conn.execute(
            "SELECT * FROM applications WHERE id=?", (app_id,)
        ).fetchone()
        app = _row_to_app(row) if row else {}
    finally:
        conn.close()
    return _enrich_linked_data(app) if app else app


async def update_application(
    app_id: int,
    user_id: int,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    interview_round: Optional[int] = None,
    apply_url: Optional[str] = None,
    announcement_url: Optional[str] = None,
    job_title: Optional[str] = None,
    company_name: Optional[str] = None,
) -> dict | None:
    """更新投递记录。状态变更时自动写入对应阶段时间戳。"""
    now = datetime.now().isoformat(timespec="seconds")
    conn = _connect()
    try:
        sets = ["updated_at=?"]
        params: list = [now]
        if status and status in VALID_STATUSES:
            sets.append("status=?")
            params.append(status)
            ts_field = _status_timestamp_field(status)
            if ts_field:
                sets.append(f"{ts_field}=COALESCE({ts_field}, ?)")
                params.append(now)
            if status != "interview":
                sets.append("interview_round=0")
        if interview_round is not None:
            sets.append("interview_round=?")
            params.append(interview_round)
        if notes is not None:
            sets.append("notes=?")
            params.append(notes)
        if apply_url is not None:
            sets.append("apply_url=?")
            params.append(apply_url)
        if announcement_url is not None:
            sets.append("announcement_url=?")
            params.append(announcement_url)
        if job_title is not None:
            sets.append("job_title=?")
            params.append(job_title)
        if company_name is not None:
            sets.append("company_name=?")
            params.append(company_name)
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
        apps = [_row_to_app(r) for r in rows]
    finally:
        conn.close()
    return [_enrich_linked_data(a) for a in apps]


async def get_application(app_id: int, user_id: int) -> dict | None:
    """获取单条投递记录。"""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM applications WHERE id=? AND user_id=?", (app_id, user_id)
        ).fetchone()
        if not row:
            return None
        app = _row_to_app(row)
    finally:
        conn.close()
    return _enrich_linked_data(app)


def _enrich_linked_data(app: dict) -> dict:
    """根据 link_type / link_id 关联岗位库/公司库，补充行业、公司类型、发布时间、截止时间等字段。

    - link_type='company' → 查 companies + 最新公告：industry, company_type, publish_time, deadline
    - link_type='job'    → 查 positions + 公告 + 公司：industry, company_type, job_category,
                            min_education, is_mt, jd_summary, difficulty, publish_time, deadline
    - 其他来源不补充，返回原 dict
    """
    link_type = app.get("link_type")
    link_id = app.get("link_id")
    if not link_type or not link_id:
        return app

    try:
        import sqlite3 as _sqlite3
        from job_db import DB_PATH as _JOBS_DB_PATH

        jobs_conn = _sqlite3.connect(_JOBS_DB_PATH)
        jobs_conn.row_factory = _sqlite3.Row
        try:
            if link_type == "company":
                row = jobs_conn.execute(
                    """SELECT c.industry, c.company_type,
                              a.publish_time, a.deadline,
                              a.recruit_type, a.recruit_target,
                              a.location AS location,
                              a.positions_count,
                              (SELECT GROUP_CONCAT(position_title, '、')
                                 FROM (SELECT position_title FROM positions
                                        WHERE company_id = c.id ORDER BY id LIMIT 15)
                              ) AS position_titles,
                              a.apply_url, a.announcement_url
                       FROM companies c
                       LEFT JOIN announcements a
                         ON a.company_id = c.id
                        AND a.last_modified = (
                            SELECT MAX(last_modified) FROM announcements WHERE company_id = c.id
                        )
                       WHERE c.id = ?""",
                    (int(link_id),),
                ).fetchone()
                # 公司层级:companies 表无 company_tier 字段,
                # 从 positions 表取该公司所有岗位里最常见的 tier
                tier_row = jobs_conn.execute(
                    """SELECT company_tier, COUNT(*) AS cnt
                       FROM positions
                       WHERE company_id = ? AND company_tier != ''
                       GROUP BY company_tier
                       ORDER BY cnt DESC
                       LIMIT 1""",
                    (int(link_id),),
                ).fetchone()
                if row:
                    app.update({
                        "industry": row["industry"] or "",
                        "company_type": row["company_type"] or "",
                        "publish_time": row["publish_time"] or "",
                        "deadline": row["deadline"] or "",
                        "recruit_type": row["recruit_type"] or "",
                        "recruit_target": row["recruit_target"] or "",
                        "location": row["location"] or "",
                        "positions_count": row["positions_count"] or 0,
                        "position_titles": row["position_titles"] or "",
                        "apply_url": app.get("apply_url") or (row["apply_url"] or ""),
                        "announcement_url": app.get("announcement_url") or (row["announcement_url"] or ""),
                        "company_tier": tier_row["company_tier"] if tier_row else "",
                    })
            elif link_type == "job":
                row = jobs_conn.execute(
                    """SELECT p.position_title, p.job_category, p.job_subcategory,
                              p.min_education, p.is_management_trainee,
                              p.jd_summary, p.difficulty,
                              p.city, p.major_category, p.major_required,
                              p.hard_skills, p.keywords,
                              c.industry, c.company_type,
                              a.publish_time, a.deadline,
                              a.recruit_type, a.recruit_target, a.location
                       FROM positions p
                       LEFT JOIN companies c ON c.id = p.company_id
                       LEFT JOIN announcements a ON a.id = p.announcement_id
                       WHERE p.id = ?""",
                    (int(link_id),),
                ).fetchone()
                if row:
                    app.update({
                        "position_title": row["position_title"] or "",
                        "job_category": row["job_category"] or "",
                        "job_subcategory": row["job_subcategory"] or "",
                        "min_education": row["min_education"] or "",
                        "is_mt": bool(row["is_management_trainee"]),
                        "jd_summary": row["jd_summary"] or "",
                        "difficulty": row["difficulty"] or "",
                        "city": row["city"] or "",
                        "major_category": row["major_category"] or "",
                        "major_required": row["major_required"] or "",
                        "hard_skills": row["hard_skills"] or "",
                        "keywords": row["keywords"] or "",
                        "industry": row["industry"] or "",
                        "company_type": row["company_type"] or "",
                        "publish_time": row["publish_time"] or "",
                        "deadline": row["deadline"] or "",
                        "recruit_type": row["recruit_type"] or "",
                        "recruit_target": row["recruit_target"] or "",
                        "location": row["location"] or (row["city"] or ""),
                    })
        finally:
            jobs_conn.close()
    except Exception as e:  # noqa: BLE001 enrichment 失败不影响主记录展示
        import logging
        logging.getLogger(__name__).warning(f"enrich linked data failed: {e!r}")
    return app
