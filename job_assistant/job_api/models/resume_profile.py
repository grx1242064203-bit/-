"""简历画像模型 — 存储 LLM 解析后的结构化画像 + 原始简历文本。

画像用于岗位推荐。一用户只有一个 active profile（新上传自动覆盖旧的）。
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import get_settings

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS resume_profiles (
    profile_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    resume_text TEXT NOT NULL,
    keywords_json TEXT NOT NULL,
    fit_directions_json TEXT NOT NULL,
    degree TEXT DEFAULT '',
    major TEXT DEFAULT '',
    target_cities_json TEXT DEFAULT '[]',
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 每用户只允许一个 active 画像：新画像插入时自动把旧的设为 inactive
-- 应用层控制，不需要 DB 约束
"""


def _conn() -> sqlite3.Connection:
    db_path = Path(get_settings().DATA_DIR) / "auth.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema():
    conn = _conn()
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


# 启动时确保表存在
_ensure_schema()


def _gen_id() -> str:
    return f"profile-{uuid.uuid4().hex[:12]}"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_profile(
    user_id: str,
    resume_text: str,
    keywords: list,
    fit_directions: list,
    degree: str = "",
    major: str = "",
    target_cities: Optional[list] = None,
) -> dict:
    """新建画像（自动把同用户旧 active 设为 inactive）。"""
    conn = _conn()
    try:
        now = _now()
        # 1) 旧画像设 inactive
        conn.execute(
            "UPDATE resume_profiles SET is_active = 0, updated_at = ? WHERE user_id = ? AND is_active = 1",
            (now, user_id),
        )
        # 2) 插入新画像
        profile_id = _gen_id()
        conn.execute(
            """INSERT INTO resume_profiles
               (profile_id, user_id, resume_text, keywords_json, fit_directions_json,
                degree, major, target_cities_json, is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (
                profile_id,
                user_id,
                resume_text,
                json.dumps(keywords, ensure_ascii=False),
                json.dumps(fit_directions, ensure_ascii=False),
                degree,
                major,
                json.dumps(target_cities or [], ensure_ascii=False),
                now,
                now,
            ),
        )
        conn.commit()
        return get_profile(profile_id)
    finally:
        conn.close()


def get_profile(profile_id: str) -> Optional[dict]:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM resume_profiles WHERE profile_id = ?", (profile_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_active_profile(user_id: str) -> Optional[dict]:
    """获取用户当前 active 的画像。"""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM resume_profiles WHERE user_id = ? AND is_active = 1 ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def list_profiles(user_id: str) -> list:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM resume_profiles WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def delete_profile(profile_id: str, user_id: str) -> bool:
    conn = _conn()
    try:
        cur = conn.execute(
            "DELETE FROM resume_profiles WHERE profile_id = ? AND user_id = ?",
            (profile_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["keywords"] = json.loads(d.pop("keywords_json", "[]"))
    d["fit_directions"] = json.loads(d.pop("fit_directions_json", "[]"))
    d["target_cities"] = json.loads(d.pop("target_cities_json", "[]"))
    d["is_active"] = bool(d["is_active"])
    return d
