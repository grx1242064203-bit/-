"""公司尽调模型：缓存 LLM 生成的公司简介/官网/新闻/面试问题。

按 (user_id, company_name) 缓存——面试答案结合了用户简历，是个性化的，
所以每个用户独立缓存，避免串数据。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from config import get_settings

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS company_due_diligence (
    user_id INTEGER NOT NULL,
    company_name TEXT NOT NULL,
    intro TEXT DEFAULT '',
    official_website TEXT DEFAULT '',
    news_links TEXT DEFAULT '[]',
    why_company_questions TEXT DEFAULT '[]',
    generated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, company_name)
);
"""

# 旧表只有 company_name 主键，迁移时加 user_id 列
_MIGRATE_SQL = """
ALTER TABLE company_due_diligence ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0;
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_settings().AUTH_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA_SQL)
    # 迁移旧表：旧表 company_name 为主键且无 user_id 列
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(company_due_diligence)").fetchall()]
        if "user_id" not in cols:
            conn.executescript(_MIGRATE_SQL)
    except sqlite3.OperationalError:
        pass
    return conn


async def init_db() -> None:
    conn = _connect()
    conn.close()


def _row_to_dd(row: sqlite3.Row) -> dict:
    import json
    return {
        "company_name": row["company_name"],
        "intro": row["intro"],
        "official_website": row["official_website"],
        "news_links": json.loads(row["news_links"]) if row["news_links"] else [],
        "why_company_questions": (
            json.loads(row["why_company_questions"])
            if row["why_company_questions"]
            else []
        ),
        "generated_at": row["generated_at"],
    }


async def get_due_diligence(user_id: int, company_name: str) -> Optional[dict]:
    """获取公司尽调缓存。不存在返回 None。"""
    if not company_name:
        return None
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM company_due_diligence WHERE user_id=? AND company_name=?",
            (user_id, company_name),
        ).fetchone()
        return _row_to_dd(row) if row else None
    finally:
        conn.close()


def get_due_diligence_sync(user_id: int, company_name: str) -> Optional[dict]:
    """同步版本（供同步路由调用）。"""
    if not company_name:
        return None
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM company_due_diligence WHERE user_id=? AND company_name=?",
            (user_id, company_name),
        ).fetchone()
        return _row_to_dd(row) if row else None
    finally:
        conn.close()


async def upsert_due_diligence(
    user_id: int,
    company_name: str,
    intro: str = "",
    official_website: str = "",
    news_links: Optional[list] = None,
    why_company_questions: Optional[list] = None,
) -> dict:
    """写入/更新公司尽调缓存。"""
    import json
    now = datetime.now().isoformat(timespec="seconds")
    news_json = json.dumps(news_links or [], ensure_ascii=False)
    questions_json = json.dumps(why_company_questions or [], ensure_ascii=False)
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO company_due_diligence
               (user_id, company_name, intro, official_website, news_links, why_company_questions, generated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, company_name) DO UPDATE SET
                   intro=excluded.intro,
                   official_website=excluded.official_website,
                   news_links=excluded.news_links,
                   why_company_questions=excluded.why_company_questions,
                   generated_at=excluded.generated_at""",
            (user_id, company_name, intro, official_website, news_json, questions_json, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM company_due_diligence WHERE user_id=? AND company_name=?",
            (user_id, company_name),
        ).fetchone()
        return _row_to_dd(row)
    finally:
        conn.close()


def upsert_due_diligence_sync(
    user_id: int,
    company_name: str,
    intro: str = "",
    official_website: str = "",
    news_links: Optional[list] = None,
    why_company_questions: Optional[list] = None,
) -> dict:
    """同步版本（供同步路由调用）。"""
    import json
    now = datetime.now().isoformat(timespec="seconds")
    news_json = json.dumps(news_links or [], ensure_ascii=False)
    questions_json = json.dumps(why_company_questions or [], ensure_ascii=False)
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO company_due_diligence
               (user_id, company_name, intro, official_website, news_links, why_company_questions, generated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, company_name) DO UPDATE SET
                   intro=excluded.intro,
                   official_website=excluded.official_website,
                   news_links=excluded.news_links,
                   why_company_questions=excluded.why_company_questions,
                   generated_at=excluded.generated_at""",
            (user_id, company_name, intro, official_website, news_json, questions_json, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM company_due_diligence WHERE user_id=? AND company_name=?",
            (user_id, company_name),
        ).fetchone()
        return _row_to_dd(row)
    finally:
        conn.close()
