"""
校招总数据库 — 公司表 + 岗位表,作为用户分发的唯一数据源。

数据源:飞书秋招汇总表(主)+ Tavily 搜索(降级备选)

设计原则:
- 中心化采集一次,多用户复用
- 公司表存公司元数据(行业/性质/地点),岗位表存具体岗位
- 去重 hash 唯一约束,避免重复入库
- 按目标届数范围(target_min_grade ~ target_max_grade)匹配用户毕业年份
- AI 分析标记确保岗位详情质量
"""
import sqlite3
import os
import hashlib
import time
import logging
from typing import List, Dict, Optional

from config import settings

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(settings.DATA_DIR, "jobs.db")

# 建表语句
SCHEMA = """
-- 公司表:每家公司一条,存公司级元数据
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,           -- 公司名称
    industry TEXT,                        -- 归一化行业(18类)
    company_type TEXT,                    -- 归一化企业性质(5类)
    locations TEXT,                       -- 工作地点(逗号分隔)
    has_announcement INTEGER DEFAULT 1,   -- 是否有校招公告
    announcement_url TEXT,                -- 公告链接(取最新)
    last_sync_time TEXT,                  -- 最近同步时间
    source TEXT DEFAULT 'feishu'          -- 数据来源
);

-- 岗位表:每个具体岗位一条(从公告拆分)
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    job_title TEXT NOT NULL,              -- 具体岗位名称
    department TEXT,                      -- 部门
    salary TEXT,                          -- 薪资范围
    education TEXT,                       -- 学历要求
    locations TEXT,                       -- 工作地点
    industry TEXT,                        -- 行业(冗余,便于查询)
    company_type TEXT,                    -- 公司类型(冗余)
    difficulty TEXT,                      -- 难度
    recruitment_stage TEXT,               -- 招聘阶段:秋招/秋招提前批/春招/春招补招/春招补录
    target_min_grade INTEGER,             -- 目标届数下限(如 2025)
    target_max_grade INTEGER,             -- 目标届数上限(如 2027)
    apply_url TEXT,                       -- 投递链接
    announcement_url TEXT,                -- 公告链接
    jd_summary TEXT,                      -- JD 摘要
    publish_time TEXT,                    -- 发布时间
    deadline TEXT,                        -- 投递截止日期
    is_fresh_graduate INTEGER DEFAULT 1,  -- 是否应届岗
    mt_program INTEGER DEFAULT 0,         -- 是否管培项目
    source TEXT NOT NULL,                 -- 数据来源
    link_valid INTEGER DEFAULT 1,         -- 链接是否有效
    detail_analyzed INTEGER DEFAULT 0,    -- 是否已做 AI 详情分析
    status TEXT DEFAULT '在招',            -- 在招/已关闭
    crawl_time TEXT NOT NULL,
    ai_verified INTEGER DEFAULT 0,
    dedup_hash TEXT UNIQUE
);

"""


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """初始化数据库(建表 + 迁移旧表字段 + 建索引)"""
    conn = _get_conn()
    try:
        conn.executescript(SCHEMA)
        # 迁移:旧 jobs 表可能缺字段,逐个补建
        existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        new_cols = {
            "department": "TEXT", "salary": "TEXT", "education": "TEXT",
            "locations": "TEXT", "recruitment_stage": "TEXT",
            "target_min_grade": "INTEGER", "target_max_grade": "INTEGER",
            "apply_url": "TEXT", "announcement_url": "TEXT",
            "is_fresh_graduate": "INTEGER DEFAULT 1", "mt_program": "INTEGER DEFAULT 0",
            "link_valid": "INTEGER DEFAULT 1", "detail_analyzed": "INTEGER DEFAULT 0",
        }
        for col, ctype in new_cols.items():
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {ctype}")
                logger.info(f"迁移:jobs 表新增字段 {col}")
        # 索引必须在字段存在后创建(旧表迁移场景)
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_industry ON jobs(industry);
            CREATE INDEX IF NOT EXISTS idx_jobs_grade ON jobs(target_min_grade, target_max_grade);
            CREATE INDEX IF NOT EXISTS idx_jobs_stage ON jobs(recruitment_stage);
            CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(name);
        """)
        conn.commit()
        logger.info(f"总数据库已初始化: {DB_PATH}")
    finally:
        conn.close()


def compute_dedup_hash(company: str, job_title: str, apply_url: str = "") -> str:
    """计算去重 hash = md5(company + job_title + apply_url)"""
    company = (company or "").strip()
    job_title = (job_title or "").strip()
    apply_url = (apply_url or "").strip()
    raw = f"{company}|{job_title}|{apply_url}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ========== 公司表操作 ==========

def upsert_company(name: str, industry: str = "", company_type: str = "",
                   locations: str = "", announcement_url: str = "",
                   source: str = "feishu") -> bool:
    """插入或更新公司记录"""
    conn = _get_conn()
    try:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """INSERT INTO companies (name, industry, company_type, locations,
               announcement_url, last_sync_time, source)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
               industry=excluded.industry, company_type=excluded.company_type,
               locations=excluded.locations, announcement_url=excluded.announcement_url,
               last_sync_time=excluded.last_sync_time, source=excluded.source""",
            (name, industry, company_type, locations, announcement_url, now, source),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.exception(f"upsert_company 失败 [{name}]: {e}")
        return False
    finally:
        conn.close()


def get_company(name: str) -> Optional[Dict]:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM companies WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ========== 岗位表操作 ==========

def insert_job(job: Dict) -> bool:
    """
    插入一条岗位到总数据库。
    返回 True=新增成功, False=已存在(去重跳过)。
    """
    conn = _get_conn()
    try:
        dedup_hash = compute_dedup_hash(
            job.get("company", ""),
            job.get("job_title", ""),
            job.get("apply_url", "") or job.get("jd_url", ""),
        )
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        apply_url = job.get("apply_url", "") or job.get("jd_url", "")
        conn.execute(
            """INSERT OR IGNORE INTO jobs
               (company, job_title, department, salary, education, locations,
                industry, company_type, difficulty, recruitment_stage,
                target_min_grade, target_max_grade, apply_url, announcement_url,
                jd_summary, publish_time, deadline, is_fresh_graduate, mt_program,
                source, link_valid, detail_analyzed, jd_url, status, crawl_time,
                ai_verified, dedup_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '在招', ?, 0, ?)""",
            (
                job.get("company", ""),
                job.get("job_title", ""),
                job.get("department", ""),
                job.get("salary", ""),
                job.get("education", ""),
                job.get("locations", ""),
                job.get("industry", ""),
                job.get("company_type", ""),
                job.get("difficulty", ""),
                job.get("recruitment_stage", ""),
                job.get("target_min_grade"),
                job.get("target_max_grade"),
                apply_url,
                job.get("announcement_url", ""),
                job.get("jd_summary", ""),
                job.get("publish_time", ""),
                job.get("deadline", ""),
                1 if job.get("is_fresh_graduate", True) else 0,
                1 if job.get("mt_program", False) else 0,
                job.get("source", ""),
                1 if job.get("link_valid", True) else 0,
                1 if job.get("detail_analyzed", False) else 0,
                apply_url,  # jd_url (兼容旧表 NOT NULL 约束)
                now,
                dedup_hash,
            ),
        )
        conn.commit()
        cur = conn.execute("SELECT changes() as cnt")
        return cur.fetchone()["cnt"] > 0
    except Exception as e:
        logger.exception(f"插入岗位失败: {e}")
        return False
    finally:
        conn.close()


def batch_insert_jobs(jobs: List[Dict]) -> Dict:
    """批量插入岗位,返回 {"inserted": N, "skipped": M}"""
    conn = _get_conn()
    inserted = 0
    skipped = 0
    try:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        for job in jobs:
            dedup_hash = compute_dedup_hash(
                job.get("company", ""),
                job.get("job_title", ""),
                job.get("apply_url", "") or job.get("jd_url", ""),
            )
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO jobs
                       (company, job_title, department, salary, education, locations,
                        industry, company_type, difficulty, recruitment_stage,
                        target_min_grade, target_max_grade, apply_url, announcement_url,
                        jd_summary, publish_time, deadline, is_fresh_graduate, mt_program,
                        source, link_valid, detail_analyzed, jd_url, status, crawl_time,
                        ai_verified, dedup_hash)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '在招', ?, 0, ?)""",
                    (
                        job.get("company", ""),
                        job.get("job_title", ""),
                        job.get("department", ""),
                        job.get("salary", ""),
                        job.get("education", ""),
                        job.get("locations", ""),
                        job.get("industry", ""),
                        job.get("company_type", ""),
                        job.get("difficulty", ""),
                        job.get("recruitment_stage", ""),
                        job.get("target_min_grade"),
                        job.get("target_max_grade"),
                        job.get("apply_url", "") or job.get("jd_url", ""),
                        job.get("announcement_url", ""),
                        job.get("jd_summary", ""),
                        job.get("publish_time", ""),
                        job.get("deadline", ""),
                        1 if job.get("is_fresh_graduate", True) else 0,
                        1 if job.get("mt_program", False) else 0,
                        job.get("source", ""),
                        1 if job.get("link_valid", True) else 0,
                        1 if job.get("detail_analyzed", False) else 0,
                        job.get("apply_url", "") or job.get("jd_url", ""),  # jd_url
                        now,
                        dedup_hash,
                    ),
                )
                cur = conn.execute("SELECT changes() as cnt")
                if cur.fetchone()["cnt"] > 0:
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


def update_job_analysis(dedup_hash: str, **fields):
    """更新岗位的 AI 分析结果字段"""
    if not fields:
        return
    conn = _get_conn()
    try:
        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        values = list(fields.values()) + [dedup_hash]
        conn.execute(
            f"UPDATE jobs SET {set_clause}, detail_analyzed = 1 WHERE dedup_hash = ?",
            values,
        )
        conn.commit()
    finally:
        conn.close()


def mark_ai_verified(dedup_hash: str, verified: bool = True):
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
    """获取所有在招岗位"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = '在招'"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_jobs_by_grade(graduation_year: int) -> List[Dict]:
    """按用户毕业届数获取匹配的在招岗位(届数在 target_min~max 范围内)"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM jobs WHERE status = '在招'
               AND (target_min_grade IS NULL OR target_min_grade <= ?)
               AND (target_max_grade IS NULL OR target_max_grade >= ?)""",
            (graduation_year, graduation_year),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_unanalyzed_jobs(limit: int = 100) -> List[Dict]:
    """获取尚未做 AI 详情分析的岗位"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE detail_analyzed = 0 AND link_valid = 1 LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def close_job(dedup_hash: str):
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
                COUNT(*) as total_jobs,
                SUM(CASE WHEN status='在招' THEN 1 ELSE 0 END) as active_jobs,
                SUM(CASE WHEN detail_analyzed=1 THEN 1 ELSE 0 END) as analyzed_jobs,
                COUNT(DISTINCT company) as companies
               FROM jobs"""
        ).fetchone()
        return dict(row)
    finally:
        conn.close()
