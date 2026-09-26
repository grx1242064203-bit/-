"""
校招总数据库 — 存储所有 2027 届校招岗位,作为用户分发的唯一数据源。

设计原则:
- 中心化采集一次,多用户复用
- 去重 hash 唯一约束,避免重复入库
- 只存 2027 届在招岗位,关闭的归档
- AI 检视标记确保数据质量

存储: SQLite (data/jobs.db),轻量且支持查询。
"""
import sqlite3
import os
import hashlib
import time
import logging
from contextlib import contextmanager
from typing import List, Dict, Optional

from config import settings

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(settings.DATA_DIR, "jobs.db")

# 建表语句
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    job_title TEXT NOT NULL,
    cohort TEXT DEFAULT '2027',
    source TEXT NOT NULL,
    jd_url TEXT NOT NULL,
    jd_summary TEXT,
    industry TEXT,
    company_type TEXT,
    difficulty TEXT,
    deadline TEXT,
    publish_time TEXT,
    status TEXT DEFAULT '在招',
    crawl_time TEXT NOT NULL,
    ai_verified INTEGER DEFAULT 0,
    dedup_hash TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_cohort ON jobs(cohort);
CREATE INDEX IF NOT EXISTS idx_industry ON jobs(industry);
"""


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """初始化数据库(建表)"""
    conn = _get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        logger.info(f"总数据库已初始化: {DB_PATH}")
    finally:
        conn.close()


def compute_dedup_hash(company: str, job_title: str, jd_url: str) -> str:
    """计算去重 hash = md5(company + job_title + jd_url)"""
    raw = f"{company.strip()}|{job_title.strip()}|{jd_url.strip()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def insert_job(job: Dict) -> bool:
    """
    插入一条岗位到总数据库。
    返回 True=新增成功, False=已存在(去重跳过)。

    job 字段: company, job_title, source, jd_url, jd_summary,
              industry, company_type, difficulty, deadline, publish_time
    """
    conn = _get_conn()
    try:
        dedup_hash = compute_dedup_hash(
            job.get("company", ""),
            job.get("job_title", ""),
            job.get("jd_url", ""),
        )
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """INSERT OR IGNORE INTO jobs
               (company, job_title, cohort, source, jd_url, jd_summary,
                industry, company_type, difficulty, deadline, publish_time,
                status, crawl_time, ai_verified, dedup_hash)
               VALUES (?, ?, '2027', ?, ?, ?, ?, ?, ?, ?, ?, '在招', ?, 0, ?)""",
            (
                job.get("company", ""),
                job.get("job_title", ""),
                job.get("source", ""),
                job.get("jd_url", ""),
                job.get("jd_summary", ""),
                job.get("industry", ""),
                job.get("company_type", ""),
                job.get("difficulty", ""),
                job.get("deadline", ""),
                job.get("publish_time", ""),
                now,
                dedup_hash,
            ),
        )
        conn.commit()
        # 检查是否真的插入了(INSERT OR IGNORE 不报错但可能跳过)
        cur = conn.execute(
            "SELECT changes() as cnt"
        )
        inserted = cur.fetchone()["cnt"] > 0
        return inserted
    except Exception as e:
        logger.exception(f"插入岗位失败: {e}")
        return False
    finally:
        conn.close()


def batch_insert_jobs(jobs: List[Dict]) -> Dict:
    """
    批量插入岗位。
    返回 {"inserted": N, "skipped": M}
    """
    conn = _get_conn()
    inserted = 0
    skipped = 0
    try:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        for job in jobs:
            dedup_hash = compute_dedup_hash(
                job.get("company", ""),
                job.get("job_title", ""),
                job.get("jd_url", ""),
            )
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO jobs
                       (company, job_title, cohort, source, jd_url, jd_summary,
                        industry, company_type, difficulty, deadline, publish_time,
                        status, crawl_time, ai_verified, dedup_hash)
                       VALUES (?, ?, '2027', ?, ?, ?, ?, ?, ?, ?, ?, '在招', ?, 0, ?)""",
                    (
                        job.get("company", ""),
                        job.get("job_title", ""),
                        job.get("source", ""),
                        job.get("jd_url", ""),
                        job.get("jd_summary", ""),
                        job.get("industry", ""),
                        job.get("company_type", ""),
                        job.get("difficulty", ""),
                        job.get("deadline", ""),
                        job.get("publish_time", ""),
                        now,
                        dedup_hash,
                    ),
                )
                if conn.total_changes > 0:
                    inserted += 1
                else:
                    skipped += 1
            except sqlite3.IntegrityError:
                skipped += 1
        conn.commit()
    except Exception as e:
        logger.exception(f"批量插入失败: {e}")
    finally:
        conn.close()
    return {"inserted": inserted, "skipped": skipped}


def mark_ai_verified(dedup_hash: str, verified: bool = True):
    """标记岗位 AI 检视是否通过"""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE jobs SET ai_verified = ? WHERE dedup_hash = ?",
            (1 if verified else 0, dedup_hash),
        )
        conn.commit()
    finally:
        conn.close()


def get_all_active_jobs() -> List[Dict]:
    """获取所有在招的 2027 届岗位"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = '在招' AND cohort = '2027'"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_jobs_by_company(company: str) -> List[Dict]:
    """按公司获取在招岗位"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE company = ? AND status = '在招'",
            (company,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_unverified_jobs() -> List[Dict]:
    """获取尚未 AI 检视的岗位"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE ai_verified = 0"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def close_job(dedup_hash: str):
    """将岗位标记为已关闭"""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE jobs SET status = '已关闭' WHERE dedup_hash = ?",
            (dedup_hash,),
        )
        conn.commit()
    finally:
        conn.close()


def get_stats() -> Dict:
    """获取总数据库统计"""
    conn = _get_conn()
    try:
        row = conn.execute(
            """SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status='在招' THEN 1 ELSE 0 END) as active,
                SUM(CASE WHEN ai_verified=1 THEN 1 ELSE 0 END) as verified,
                COUNT(DISTINCT company) as companies
               FROM jobs WHERE cohort = '2027'"""
        ).fetchone()
        return dict(row)
    finally:
        conn.close()
