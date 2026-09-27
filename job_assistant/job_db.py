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

-- 招聘公告表:每个公司的招聘链接一条(后台中间表,不直接给用户)
-- 存储原始链接 + 抓取状态 + 分析状态,LLM 拆分出的具体岗位写入 jobs 表
CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    job_title TEXT,                        -- 原始多岗位拼接标题(飞书导入)
    apply_url TEXT,                        -- 投递链接
    announcement_url TEXT,                 -- 公告链接
    industry TEXT,                         -- 行业(冗余)
    company_type TEXT,                     -- 公司类型(冗余)
    difficulty TEXT,
    recruitment_stage TEXT,
    target_min_grade INTEGER,
    target_max_grade INTEGER,
    source TEXT DEFAULT 'feishu',
    link_valid INTEGER DEFAULT 1,          -- 链接是否有效
    detail_analyzed INTEGER DEFAULT 0,     -- 是否已做 AI 分析
    analysis_status TEXT,                  -- 分析结果状态:success/fetch_blocked/fetch_failed/content_invalid/llm_parse_empty/not_current_grade
    status TEXT DEFAULT '在招',
    crawl_time TEXT,
    dedup_hash TEXT UNIQUE,
    jd_summary TEXT,
    publish_time TEXT,
    deadline TEXT
);

-- 岗位表:每个具体岗位一条(从公告 LLM 拆分,给用户的最终数据)
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    job_title TEXT NOT NULL,              -- 具体岗位名称
    department TEXT,                      -- 部门
    salary TEXT,                          -- 薪资范围
    education TEXT,                       -- 学历要求(原文)
    locations TEXT,                       -- 工作地点(原文)
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
    dedup_hash TEXT UNIQUE,
    -- ===== 精准匹配扩展字段(人岗匹配核心维度) =====
    -- 岗位分类
    job_category TEXT,                    -- 岗位大类:研发/产品/设计/运营/市场/销售/职能/供应链/生产制造/金融/咨询/其他
    job_subcategory TEXT,                 -- 岗位子类:如研发→前端/后端/算法/测试
    -- 技能维度(对应用户 core_skills)
    hard_skills TEXT,                     -- 硬技能标签(逗号分隔):Python,Java,SQL,Excel...
    soft_skills TEXT,                     -- 软技能标签(逗号分隔):沟通能力,团队协作,逻辑思维...
    certifications TEXT,                  -- 证书要求(逗号分隔):CFA,CPA,法律职业资格...
    languages TEXT,                       -- 语言要求(逗号分隔):CET4,CET6,雅思,托福...
    -- 专业维度(对应用户 major)
    major_required TEXT,                  -- 专业要求:计算机,机械,金融...
    major_category TEXT,                  -- 专业大类:工科/理科/商科/文科/医科/艺术/不限
    -- 学历维度(对应用户 degree)
    min_education TEXT,                   -- 最低学历:大专/本科/硕士/博士
    education_preference TEXT,            -- 学历偏好:不限/双一流/985/211/海外名校
    -- 地点维度(对应用户 target_cities)
    city TEXT,                            -- 工作城市
    province TEXT,                        -- 省份
    is_remote INTEGER DEFAULT 0,          -- 是否支持远程
    -- 职业发展
    career_track TEXT,                    -- 职业轨道:技术/管理/专业
    career_level TEXT,                    -- 岗位级别:初级/中级/高级/专家
    -- 工作性质
    travel_frequency TEXT,                -- 出差频率:无/偶尔/经常
    overtime_level TEXT,                  -- 加班强度:无/偶尔/经常/大小周/996
    -- 招聘流程
    recruitment_process TEXT,             -- 招聘流程描述
    has_written_test INTEGER DEFAULT 0,   -- 是否有笔试
    headcount TEXT,                       -- 招聘人数
    -- 岗位职责与要求(增强 jd_summary)
    responsibilities TEXT,                -- 岗位职责
    requirements TEXT,                    -- 任职要求
    bonus_points TEXT,                    -- 加分项
    -- 综合标签
    keywords TEXT                         -- 综合关键词标签(全文匹配用)
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
            "jd_url": "TEXT",
            # ===== 精准匹配扩展字段 =====
            "job_category": "TEXT", "job_subcategory": "TEXT",
            "hard_skills": "TEXT", "soft_skills": "TEXT",
            "certifications": "TEXT", "languages": "TEXT",
            "major_required": "TEXT", "major_category": "TEXT",
            "min_education": "TEXT", "education_preference": "TEXT",
            "city": "TEXT", "province": "TEXT",
            "is_remote": "INTEGER DEFAULT 0",
            "career_track": "TEXT", "career_level": "TEXT",
            "travel_frequency": "TEXT", "overtime_level": "TEXT",
            "recruitment_process": "TEXT",
            "has_written_test": "INTEGER DEFAULT 0",
            "headcount": "TEXT",
            "responsibilities": "TEXT", "requirements": "TEXT", "bonus_points": "TEXT",
            "keywords": "TEXT",
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
            CREATE INDEX IF NOT EXISTS idx_announcements_dedup ON announcements(dedup_hash);
            CREATE INDEX IF NOT EXISTS idx_announcements_analyzed ON announcements(detail_analyzed, link_valid);
            CREATE INDEX IF NOT EXISTS idx_announcements_company ON announcements(company);
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
                ai_verified, dedup_hash,
                job_category, job_subcategory, hard_skills, soft_skills,
                certifications, languages, major_required, major_category,
                min_education, education_preference, city, province, is_remote,
                career_track, career_level, travel_frequency, overtime_level,
                recruitment_process, has_written_test, headcount,
                responsibilities, requirements, bonus_points, keywords)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '在招', ?, 0, ?,
                       ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                # 精准匹配扩展字段
                job.get("job_category", ""),
                job.get("job_subcategory", ""),
                job.get("hard_skills", ""),
                job.get("soft_skills", ""),
                job.get("certifications", ""),
                job.get("languages", ""),
                job.get("major_required", ""),
                job.get("major_category", ""),
                job.get("min_education", ""),
                job.get("education_preference", ""),
                job.get("city", ""),
                job.get("province", ""),
                1 if job.get("is_remote", False) else 0,
                job.get("career_track", ""),
                job.get("career_level", ""),
                job.get("travel_frequency", ""),
                job.get("overtime_level", ""),
                job.get("recruitment_process", ""),
                1 if job.get("has_written_test", False) else 0,
                job.get("headcount", ""),
                job.get("responsibilities", ""),
                job.get("requirements", ""),
                job.get("bonus_points", ""),
                job.get("keywords", ""),
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
                        ai_verified, dedup_hash,
                        job_category, job_subcategory, hard_skills, soft_skills,
                        certifications, languages, major_required, major_category,
                        min_education, education_preference, city, province, is_remote,
                        career_track, career_level, travel_frequency, overtime_level,
                        recruitment_process, has_written_test, headcount,
                        responsibilities, requirements, bonus_points, keywords)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '在招', ?, 0, ?,
                               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                        # 精准匹配扩展字段
                        job.get("job_category", ""),
                        job.get("job_subcategory", ""),
                        job.get("hard_skills", ""),
                        job.get("soft_skills", ""),
                        job.get("certifications", ""),
                        job.get("languages", ""),
                        job.get("major_required", ""),
                        job.get("major_category", ""),
                        job.get("min_education", ""),
                        job.get("education_preference", ""),
                        job.get("city", ""),
                        job.get("province", ""),
                        1 if job.get("is_remote", False) else 0,
                        job.get("career_track", ""),
                        job.get("career_level", ""),
                        job.get("travel_frequency", ""),
                        job.get("overtime_level", ""),
                        job.get("recruitment_process", ""),
                        1 if job.get("has_written_test", False) else 0,
                        job.get("headcount", ""),
                        job.get("responsibilities", ""),
                        job.get("requirements", ""),
                        job.get("bonus_points", ""),
                        job.get("keywords", ""),
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
    """[兼容] 获取尚未分析的公告(已迁移到 announcements 表)
    新代码请使用 get_unanalyzed_announcements()"""
    return get_unanalyzed_announcements(limit)


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
    """获取总数据库统计(jobs 表=具体岗位,给用户的最终数据)"""
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


# ========== 招聘公告表操作(后台中间表,存原始链接) ==========

def insert_announcement(ann: Dict) -> bool:
    """
    插入一条招聘公告(原始链接)到 announcements 表。
    返回 True=新增成功, False=已存在(去重跳过)。
    """
    conn = _get_conn()
    try:
        dedup_hash = compute_dedup_hash(
            ann.get("company", ""),
            ann.get("job_title", ""),
            ann.get("apply_url", "") or ann.get("jd_url", ""),
        )
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        apply_url = ann.get("apply_url", "") or ann.get("jd_url", "")
        conn.execute(
            """INSERT OR IGNORE INTO announcements
               (company, job_title, apply_url, announcement_url, industry,
                company_type, difficulty, recruitment_stage, target_min_grade,
                target_max_grade, source, link_valid, detail_analyzed, status,
                crawl_time, dedup_hash, jd_summary, publish_time, deadline)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '在招', ?, ?, ?, ?, ?)""",
            (
                ann.get("company", ""),
                ann.get("job_title", ""),
                apply_url,
                ann.get("announcement_url", ""),
                ann.get("industry", ""),
                ann.get("company_type", ""),
                ann.get("difficulty", ""),
                ann.get("recruitment_stage", ""),
                ann.get("target_min_grade"),
                ann.get("target_max_grade"),
                ann.get("source", "feishu"),
                1 if ann.get("link_valid", True) else 0,
                now,
                dedup_hash,
                ann.get("jd_summary", ""),
                ann.get("publish_time", ""),
                ann.get("deadline", ""),
            ),
        )
        conn.commit()
        cur = conn.execute("SELECT changes() as cnt")
        return cur.fetchone()["cnt"] > 0
    except Exception as e:
        logger.exception(f"插入公告失败: {e}")
        return False
    finally:
        conn.close()


def batch_insert_announcements(anns: List[Dict]) -> Dict:
    """批量插入公告,返回 {"inserted": N, "skipped": M}"""
    conn = _get_conn()
    inserted = 0
    skipped = 0
    try:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        for ann in anns:
            dedup_hash = compute_dedup_hash(
                ann.get("company", ""),
                ann.get("job_title", ""),
                ann.get("apply_url", "") or ann.get("jd_url", ""),
            )
            apply_url = ann.get("apply_url", "") or ann.get("jd_url", "")
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO announcements
                       (company, job_title, apply_url, announcement_url, industry,
                        company_type, difficulty, recruitment_stage, target_min_grade,
                        target_max_grade, source, link_valid, detail_analyzed, status,
                        crawl_time, dedup_hash, jd_summary, publish_time, deadline)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '在招', ?, ?, ?, ?, ?)""",
                    (
                        ann.get("company", ""),
                        ann.get("job_title", ""),
                        apply_url,
                        ann.get("announcement_url", ""),
                        ann.get("industry", ""),
                        ann.get("company_type", ""),
                        ann.get("difficulty", ""),
                        ann.get("recruitment_stage", ""),
                        ann.get("target_min_grade"),
                        ann.get("target_max_grade"),
                        ann.get("source", "feishu"),
                        1 if ann.get("link_valid", True) else 0,
                        now,
                        dedup_hash,
                        ann.get("jd_summary", ""),
                        ann.get("publish_time", ""),
                        ann.get("deadline", ""),
                    ),
                )
                if conn.total_changes > 0:
                    inserted += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.warning(f"批量插入公告跳过 [{ann.get('company','')}]: {e}")
                skipped += 1
        conn.commit()
    except Exception as e:
        logger.exception(f"批量插入公告失败: {e}")
    finally:
        conn.close()
    return {"inserted": inserted, "skipped": skipped}


def get_unanalyzed_announcements(limit: int = 100) -> List[Dict]:
    """获取尚未做 AI 分析的公告(用于抓取流水线)"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM announcements WHERE detail_analyzed = 0 AND link_valid = 1 LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_announcement_analysis(dedup_hash: str, **fields):
    """更新公告的 AI 分析结果字段(analysis_status, jd_summary, link_valid, status 等)"""
    if not fields:
        fields = {}
    # 始终标记已分析
    fields["detail_analyzed"] = 1
    conn = _get_conn()
    try:
        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        values = list(fields.values()) + [dedup_hash]
        conn.execute(
            f"UPDATE announcements SET {set_clause} WHERE dedup_hash = ?",
            values,
        )
        conn.commit()
    finally:
        conn.close()


def get_announcement_stats() -> Dict:
    """获取公告表统计(流水线进度)"""
    conn = _get_conn()
    try:
        row = conn.execute(
            """SELECT
                COUNT(*) as total,
                SUM(CASE WHEN detail_analyzed=1 THEN 1 ELSE 0 END) as analyzed,
                SUM(CASE WHEN detail_analyzed=0 AND link_valid=1 THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN link_valid=0 THEN 1 ELSE 0 END) as invalid,
                SUM(CASE WHEN analysis_status='success' THEN 1 ELSE 0 END) as status_success,
                SUM(CASE WHEN analysis_status='fetch_blocked' THEN 1 ELSE 0 END) as status_blocked,
                SUM(CASE WHEN analysis_status='fetch_failed' THEN 1 ELSE 0 END) as status_fetch_failed,
                SUM(CASE WHEN analysis_status='content_invalid' THEN 1 ELSE 0 END) as status_content_invalid,
                SUM(CASE WHEN analysis_status='llm_parse_empty' THEN 1 ELSE 0 END) as status_llm_empty,
                SUM(CASE WHEN analysis_status='not_current_grade' THEN 1 ELSE 0 END) as status_not_grade
               FROM announcements"""
        ).fetchone()
        return dict(row)
    finally:
        conn.close()
