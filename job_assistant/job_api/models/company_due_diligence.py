"""公司尽调模型：缓存 LLM 生成的公司简介/官网/新闻/面试问题。

按 (user_id, company_name) 缓存——面试答案结合了用户简历，是个性化的，
所以每个用户独立缓存，避免串数据。
"""
from __future__ import annotations

import json
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
    _migrate_legacy_schema(conn)
    return conn


def _migrate_legacy_schema(conn: sqlite3.Connection) -> None:
    """检测并迁移旧 schema 的 company_due_diligence 表。

    背景:旧表 PRIMARY KEY 仅 (company_name),没有 user_id 列。
    CREATE TABLE IF NOT EXISTS 不会重建已存在的表,导致
    upsert_due_diligence_sync 中的 ON CONFLICT(user_id, company_name)
    抛 OperationalError → 500。

    迁移策略(检测到旧 schema 时执行):
    1. rename 旧表为 company_due_diligence_legacy
    2. 用新 schema 建表(PRIMARY KEY (user_id, company_name))
    3. 把旧数据迁移过来(user_id 用 0 占位,company_name/intro/... 保留)
    4. drop 旧表
    迁移失败时只记日志不抛,保持调用层不崩溃。
    """
    try:
        cols = [r[1] for r in conn.execute(
            "PRAGMA table_info(company_due_diligence)"
        ).fetchall()]
        if not cols:
            # 表不存在(首次建表),无需迁移
            return
        # 检测 PRIMARY KEY:用 PRAGMA 拿 pk 列
        pk_cols = [
            r[1] for r in conn.execute(
                "PRAGMA table_info(company_due_diligence)"
            ).fetchall()
            if r[5] > 0  # pk 字段,>0 表示是主键的一部分
        ]
        # 已有 user_id 列且主键含 user_id → 新 schema,无需迁移
        if "user_id" in cols and "user_id" in pk_cols:
            return
        # 缺 user_id 列 → 旧 schema,需要迁移
        logger = __import__("logging").getLogger(__name__)
        logger.warning(
            "检测到 company_due_diligence 旧 schema(pk=%s, cols=%s),"
            "开始迁移到新 schema(user_id+company_name 联合主键)",
            pk_cols, cols,
        )
        # 1) rename 旧表
        conn.execute(
            "ALTER TABLE company_due_diligence RENAME TO company_due_diligence_legacy"
        )
        # 2) 用新 schema 建表
        conn.executescript(_SCHEMA_SQL)
        # 3) 迁移旧数据:列名按旧表实际有的列取值,user_id 用 0
        legacy_cols = cols  # 旧表已有的列
        select_cols = []
        for c in ["company_name", "intro", "official_website",
                  "news_links", "why_company_questions", "generated_at"]:
            if c in legacy_cols:
                select_cols.append(c)
        if select_cols:
            select_sql = ", ".join(select_cols)
            placeholder = ", ".join(["?"] * (len(select_cols) + 1))
            insert_sql = (
                f"INSERT INTO company_due_diligence "
                f"(user_id, {select_sql}) VALUES ({placeholder})"
            )
            for row in conn.execute(
                f"SELECT {select_sql} FROM company_due_diligence_legacy"
            ).fetchall():
                conn.execute(insert_sql, (0, *[row[c] for c in select_cols]))
        # 4) drop 旧表
        conn.execute("DROP TABLE company_due_diligence_legacy")
        conn.commit()
        logger.warning("company_due_diligence schema 迁移完成")
    except sqlite3.OperationalError as e:
        # 迁移失败:只记日志,不阻塞调用(可能下次启动再试)
        try:
            conn.rollback()
        except Exception:
            pass
        __import__("logging").getLogger(__name__).warning(
            f"company_due_diligence schema 迁移失败: {e!r}", exc_info=True
        )
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        __import__("logging").getLogger(__name__).warning(
            f"company_due_diligence schema 迁移异常: {e!r}", exc_info=True
        )


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


async def get_due_diligence(user_id, company_name: str) -> Optional[dict]:
    """获取公司尽调缓存。不存在返回 None。

    user_id 接受 str 或 int:SQLite 是弱类型,路由层统一传 str(与 resume_profiles 对齐),
    旧缓存表里 INTEGER 列也能写入/查询。
    """
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


def get_due_diligence_sync(user_id, company_name: str) -> Optional[dict]:
    """同步版本（供同步路由调用）。user_id 接受 str 或 int。"""
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
    user_id,
    company_name: str,
    intro: str = "",
    official_website: str = "",
    news_links: Optional[list] = None,
    why_company_questions: Optional[list] = None,
) -> dict:
    """写入/更新公司尽调缓存。user_id 接受 str 或 int。"""
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
    user_id,
    company_name: str,
    intro: str = "",
    official_website: str = "",
    news_links: Optional[list] = None,
    why_company_questions: Optional[list] = None,
) -> dict:
    """同步版本（供同步路由调用）。user_id 接受 str 或 int。"""
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
