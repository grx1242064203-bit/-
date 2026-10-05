"""岗位评分缓存模型 — 缓存 scorer 对每个 (profile, job) 的评分结果。

设计目的:
- 避免每次切页都重跑 7000+ 岗位评分(scorer.score_job 全量计算很慢)
- 新岗位入库时,后台任务对新增岗位增量评分,追加到本表
- 简历修改时,删除该 profile 的所有缓存,下次推荐重新计算

表结构:
- (profile_id, job_id) 联合主键
- 缓存 score / recommend_level / alignment_label / candidate_score / company_score
- reasons_json / dims_json / comp_info_json 全量存储,前端展示用
- computed_at 时间戳,用于判断是否需要刷新
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config import get_settings

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS job_scores (
    profile_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    score REAL NOT NULL DEFAULT 0,
    recommend_level TEXT NOT NULL DEFAULT '',
    recommend_label TEXT NOT NULL DEFAULT '',
    alignment_label TEXT NOT NULL DEFAULT '',
    candidate_score REAL NOT NULL DEFAULT 0,
    company_score REAL NOT NULL DEFAULT 0,
    company_tier TEXT NOT NULL DEFAULT '',
    reasons_json TEXT NOT NULL DEFAULT '[]',
    dims_json TEXT NOT NULL DEFAULT '{}',
    comp_info_json TEXT NOT NULL DEFAULT '{}',
    computed_at TEXT NOT NULL,
    PRIMARY KEY (profile_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_job_scores_profile_score
    ON job_scores(profile_id, score DESC);
"""


def _conn() -> sqlite3.Connection:
    db_path = Path(get_settings().DATA_DIR) / "auth.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema() -> None:
    conn = _conn()
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


# 启动时确保表存在
_ensure_schema()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_cached_scores(profile_id: str, top_n: int = 200) -> list[dict]:
    """读取缓存的 Top N 评分结果。

    返回结构: [{job_id, score, recommend_level, recommend_label, alignment_label,
              candidate_score, company_score, company_tier, reasons, dims, comp_info}]
    无缓存时返回空列表。
    """
    conn = _conn()
    try:
        rows = conn.execute(
            """SELECT job_id, score, recommend_level, recommend_label,
                      alignment_label, candidate_score, company_score,
                      company_tier, reasons_json, dims_json, comp_info_json
               FROM job_scores
               WHERE profile_id = ?
               ORDER BY score DESC
               LIMIT ?""",
            (profile_id, top_n),
        ).fetchall()
        return [
            {
                "job_id": r["job_id"],
                "score": r["score"],
                "recommend_level": r["recommend_level"],
                "recommend": r["recommend_label"],
                "alignment_label": r["alignment_label"],
                "candidate_score": r["candidate_score"],
                "company_score": r["company_score"],
                "company_tier": r["company_tier"],
                "reasons": json.loads(r["reasons_json"] or "[]"),
                "dims": json.loads(r["dims_json"] or "{}"),
                "competitiveness_info": json.loads(r["comp_info_json"] or "{}"),
            }
            for r in rows
        ]
    finally:
        conn.close()


def save_scores(profile_id: str, scored_jobs: list[dict]) -> int:
    """批量保存评分结果(覆盖该 profile 的旧缓存)。

    scored_jobs 结构: [{job_id, score, recommend_level, recommend, reasons,
                       dims, competitiveness_info, ...}]
    返回插入/更新条数。
    """
    if not scored_jobs:
        return 0
    now = _now()
    conn = _conn()
    try:
        # 先清空该 profile 的旧缓存
        conn.execute(
            "DELETE FROM job_scores WHERE profile_id = ?", (profile_id,)
        )
        # 批量插入
        rows = []
        for j in scored_jobs:
            comp_info = j.get("competitiveness_info") or {}
            rows.append(
                (
                    profile_id,
                    str(j.get("job_id") or j.get("position_id") or ""),
                    float(j.get("score") or 0),
                    j.get("recommend_level") or "",
                    j.get("recommend") or j.get("综合推荐度") or "",
                    comp_info.get("label", "") if comp_info else "",
                    float(comp_info.get("candidate_score", 0) if comp_info else 0),
                    float(comp_info.get("company_score", 0) if comp_info else 0),
                    j.get("company_tier") or "",
                    json.dumps(j.get("reasons") or [], ensure_ascii=False),
                    json.dumps(j.get("dims") or {}, ensure_ascii=False),
                    json.dumps(comp_info, ensure_ascii=False),
                    now,
                )
            )
        conn.executemany(
            """INSERT OR REPLACE INTO job_scores
               (profile_id, job_id, score, recommend_level, recommend_label,
                alignment_label, candidate_score, company_score, company_tier,
                reasons_json, dims_json, comp_info_json, computed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def clear_profile_cache(profile_id: str) -> int:
    """删除该 profile 的所有缓存(简历修改后调用)。

    返回删除条数。
    """
    conn = _conn()
    try:
        cur = conn.execute(
            "DELETE FROM job_scores WHERE profile_id = ?", (profile_id,)
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def add_incremental_scores(profile_id: str, new_job_ids: list[str], scored_jobs: list[dict]) -> int:
    """增量追加新岗位的评分(不删除旧缓存)。

    用于新岗位入库时,只对新岗位评分并追加。
    """
    if not scored_jobs:
        return 0
    now = _now()
    conn = _conn()
    try:
        rows = []
        for j in scored_jobs:
            jid = str(j.get("job_id") or j.get("position_id") or "")
            if jid not in new_job_ids:
                continue
            comp_info = j.get("competitiveness_info") or {}
            rows.append(
                (
                    profile_id,
                    jid,
                    float(j.get("score") or 0),
                    j.get("recommend_level") or "",
                    j.get("recommend") or "",
                    comp_info.get("label", "") if comp_info else "",
                    float(comp_info.get("candidate_score", 0) if comp_info else 0),
                    float(comp_info.get("company_score", 0) if comp_info else 0),
                    j.get("company_tier") or "",
                    json.dumps(j.get("reasons") or [], ensure_ascii=False),
                    json.dumps(j.get("dims") or {}, ensure_ascii=False),
                    json.dumps(comp_info, ensure_ascii=False),
                    now,
                )
            )
        if rows:
            conn.executemany(
                """INSERT OR REPLACE INTO job_scores
                   (profile_id, job_id, score, recommend_level, recommend_label,
                    alignment_label, candidate_score, company_score, company_tier,
                    reasons_json, dims_json, comp_info_json, computed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            conn.commit()
        return len(rows)
    finally:
        conn.close()


def get_cache_info(profile_id: str) -> Optional[dict]:
    """返回缓存元信息:条数 + 最近计算时间。"""
    conn = _conn()
    try:
        row = conn.execute(
            """SELECT COUNT(*) AS cnt, MAX(computed_at) AS latest
               FROM job_scores WHERE profile_id = ?""",
            (profile_id,),
        ).fetchone()
        if not row or row["cnt"] == 0:
            return None
        return {"count": row["cnt"], "latest_computed_at": row["latest"]}
    finally:
        conn.close()
