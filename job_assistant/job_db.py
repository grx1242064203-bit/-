"""
校招总数据库 — 三表结构 (companies / announcements / positions)。

设计原则:
- companies: 公司维度去重,1 家公司 1 行,存行业/性质等稳定属性
- announcements: 公告维度,1 条飞书源表记录 = 1 行
- positions: 岗位维度,LLM 从公告正文拆出,匹配在此粒度进行
- 中心化同步一次,多用户复用
- 增量同步基于 feishu_record_id + last_modified_time

存储: SQLite (data/jobs.db),轻量且支持查询。
"""
import sqlite3
import os
import json
import hashlib
import time
import logging
from contextlib import contextmanager
from typing import List, Dict, Optional, Tuple

from config import settings

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(settings.DATA_DIR, "jobs.db")

# 三表建表语句
SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    name_raw TEXT,
    industry TEXT,
    industry_raw TEXT,
    company_type TEXT,
    company_type_raw TEXT,
    first_seen TEXT NOT NULL,
    last_updated TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_co_name ON companies(name);
CREATE INDEX IF NOT EXISTS idx_co_industry ON companies(industry);
CREATE INDEX IF NOT EXISTS idx_co_type ON companies(company_type);

CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feishu_record_id TEXT UNIQUE NOT NULL,
    company_id INTEGER NOT NULL,
    company_name TEXT NOT NULL,
    announcement_title TEXT,
    recruit_type TEXT,
    recruit_target TEXT,
    min_grade INTEGER,
    max_grade INTEGER,
    industry_raw TEXT,
    company_type_raw TEXT,
    location TEXT,
    education_req TEXT,
    apply_url TEXT,
    announcement_url TEXT,
    deadline TEXT,
    publish_time TEXT,
    apply_update TEXT,
    content TEXT DEFAULT '',
    content_images TEXT DEFAULT '',
    crawl_status TEXT DEFAULT 'pending',
    crawl_time TEXT,
    crawl_error TEXT,
    llm_status TEXT DEFAULT 'pending',
    llm_time TEXT,
    llm_cache_hash TEXT,
    vl_status TEXT DEFAULT 'pending',
    vl_error TEXT,
    positions_count INTEGER DEFAULT 0,
    last_modified TEXT NOT NULL,
    synced_at TEXT NOT NULL,
    FOREIGN KEY (company_id) REFERENCES companies(id)
);
CREATE INDEX IF NOT EXISTS idx_ann_company ON announcements(company_id);
CREATE INDEX IF NOT EXISTS idx_ann_type ON announcements(recruit_type);
CREATE INDEX IF NOT EXISTS idx_ann_grade ON announcements(min_grade, max_grade);
CREATE INDEX IF NOT EXISTS idx_ann_llm_status ON announcements(llm_status);
CREATE INDEX IF NOT EXISTS idx_ann_crawl_status ON announcements(crawl_status);
CREATE INDEX IF NOT EXISTS idx_ann_modified ON announcements(last_modified);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    announcement_id INTEGER NOT NULL,
    company_id INTEGER NOT NULL,
    company_name TEXT NOT NULL,
    position_title TEXT NOT NULL,
    department TEXT,
    -- 岗位分类
    job_category TEXT DEFAULT '',
    job_subcategory TEXT DEFAULT '',
    -- 技能要求
    hard_skills TEXT DEFAULT '',
    soft_skills TEXT DEFAULT '',
    certifications TEXT DEFAULT '',
    languages TEXT DEFAULT '',
    -- 专业要求
    major_required TEXT DEFAULT '',
    major_category TEXT DEFAULT '',
    -- 学历地点
    min_education TEXT DEFAULT '',
    city TEXT DEFAULT '',
    province TEXT DEFAULT '',
    -- 招聘流程
    recruitment_process TEXT DEFAULT '',
    has_written_test INTEGER DEFAULT 0,
    -- 职责要求
    responsibilities TEXT DEFAULT '',
    requirements TEXT DEFAULT '',
    bonus_points TEXT DEFAULT '',
    keywords TEXT DEFAULT '',
    -- 兼容旧字段
    location TEXT,
    education_req TEXT,
    major_req TEXT,
    jd_summary TEXT,
    is_management_trainee INTEGER DEFAULT 0,
    difficulty TEXT,
    apply_url TEXT,
    source_url TEXT,
    dedup_hash TEXT UNIQUE,
    status TEXT DEFAULT '在招',
    created_at TEXT NOT NULL,
    FOREIGN KEY (announcement_id) REFERENCES announcements(id),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);
CREATE INDEX IF NOT EXISTS idx_pos_company ON positions(company_id);
CREATE INDEX IF NOT EXISTS idx_pos_ann ON positions(announcement_id);
CREATE INDEX IF NOT EXISTS idx_pos_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_pos_mt ON positions(is_management_trainee);
"""


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库(建三表) + 迁移已有表结构。"""
    conn = _get_conn()
    try:
        conn.executescript(SCHEMA)
        # 迁移:为已有 announcements/positions 表添加新字段
        _migrate_table(conn, "announcements", [
            ("content", "TEXT DEFAULT ''"),
            ("content_images", "TEXT DEFAULT ''"),
            ("apply_update", "TEXT"),
            ("vl_status", "TEXT DEFAULT 'pending'"),
            ("vl_error", "TEXT"),
        ])
        _migrate_table(conn, "positions", [
            ("job_category", "TEXT DEFAULT ''"),
            ("job_subcategory", "TEXT DEFAULT ''"),
            ("hard_skills", "TEXT DEFAULT ''"),
            ("soft_skills", "TEXT DEFAULT ''"),
            ("certifications", "TEXT DEFAULT ''"),
            ("languages", "TEXT DEFAULT ''"),
            ("major_required", "TEXT DEFAULT ''"),
            ("major_category", "TEXT DEFAULT ''"),
            ("min_education", "TEXT DEFAULT ''"),
            ("city", "TEXT DEFAULT ''"),
            ("province", "TEXT DEFAULT ''"),
            ("recruitment_process", "TEXT DEFAULT ''"),
            ("has_written_test", "INTEGER DEFAULT 0"),
            ("responsibilities", "TEXT DEFAULT ''"),
            ("requirements", "TEXT DEFAULT ''"),
            ("bonus_points", "TEXT DEFAULT ''"),
            ("keywords", "TEXT DEFAULT ''"),
        ])
        conn.commit()
        logger.info(f"总数据库已初始化(三表): {DB_PATH}")
    finally:
        conn.close()


def _migrate_table(conn, table_name: str, columns: list):
    """为已有表添加缺失的列(SQLite 不支持 IF NOT EXISTS for ADD COLUMN)。"""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}
    for col_name, col_def in columns:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}")


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


# ==================== companies ====================

def upsert_company(name: str, industry: str = "", company_type: str = "",
                   industry_raw: str = "", company_type_raw: str = "") -> int:
    """
    插入或更新公司,返回 company_id。
    公司按归一化 name 去重;若已存在则更新行业/性质(有新值才覆盖)。
    """
    if not name or not name.strip():
        return 0
    name = name.strip()
    now = _now()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, industry, company_type, industry_raw, company_type_raw "
            "FROM companies WHERE name = ?", (name,)
        ).fetchone()
        if row:
            # 已存在:仅更新有新值的字段
            new_industry = industry or row["industry"]
            new_type = company_type or row["company_type"]
            conn.execute(
                """UPDATE companies SET industry=?, company_type=?, industry_raw=?,
                   company_type_raw=?, last_updated=? WHERE id=?""",
                (new_industry, new_type, industry_raw or row["industry_raw"],
                 company_type_raw or row["company_type_raw"], now, row["id"]),
            )
            conn.commit()
            return row["id"]
        else:
            cur = conn.execute(
                """INSERT INTO companies
                   (name, name_raw, industry, industry_raw, company_type,
                    company_type_raw, first_seen, last_updated)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, name, industry, industry_raw, company_type,
                 company_type_raw, now, now),
            )
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


def get_company_by_name(name: str) -> Optional[Dict]:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM companies WHERE name = ?", (name.strip(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ==================== announcements ====================

def upsert_announcement(data: Dict, company_id: int) -> Tuple[int, bool]:
    """
    插入或更新公告,返回 (announcement_id, is_new)。
    按 feishu_record_id 去重;已存在则更新变更字段。
    """
    record_id = data.get("feishu_record_id", "")
    if not record_id:
        return (0, False)
    now = _now()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM announcements WHERE feishu_record_id = ?", (record_id,)
        ).fetchone()
        if row:
            # 已存在:更新(源表记录可能被编辑)
            conn.execute(
                """UPDATE announcements SET
                   company_id=?, company_name=?, announcement_title=?, recruit_type=?,
                   recruit_target=?, min_grade=?, max_grade=?, industry_raw=?,
                   company_type_raw=?, location=?, education_req=?, apply_url=?,
                   announcement_url=?, deadline=?, publish_time=?, apply_update=?,
                   last_modified=?, synced_at=?
                   WHERE id=?""",
                (
                    company_id, data.get("company_name", ""),
                    data.get("announcement_title", ""), data.get("recruit_type", ""),
                    data.get("recruit_target", ""), data.get("min_grade"),
                    data.get("max_grade"), data.get("industry_raw", ""),
                    data.get("company_type_raw", ""), data.get("location", ""),
                    data.get("education_req", ""), data.get("apply_url", ""),
                    data.get("announcement_url", ""), data.get("deadline", ""),
                    data.get("publish_time", ""), data.get("apply_update", ""),
                    data.get("last_modified", ""), now, row["id"],
                ),
            )
            conn.commit()
            return (row["id"], False)
        else:
            cur = conn.execute(
                """INSERT INTO announcements
                   (feishu_record_id, company_id, company_name, announcement_title,
                    recruit_type, recruit_target, min_grade, max_grade, industry_raw,
                    company_type_raw, location, education_req, apply_url,
                    announcement_url, deadline, publish_time, apply_update, last_modified, synced_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record_id, company_id, data.get("company_name", ""),
                    data.get("announcement_title", ""), data.get("recruit_type", ""),
                    data.get("recruit_target", ""), data.get("min_grade"),
                    data.get("max_grade"), data.get("industry_raw", ""),
                    data.get("company_type_raw", ""), data.get("location", ""),
                    data.get("education_req", ""), data.get("apply_url", ""),
                    data.get("announcement_url", ""), data.get("deadline", ""),
                    data.get("publish_time", ""), data.get("apply_update", ""),
                    data.get("last_modified", ""), now,
                ),
            )
            conn.commit()
            return (cur.lastrowid, True)
    finally:
        conn.close()


def get_announcements_for_crawl(limit: int = 100) -> List[Dict]:
    """获取待抓取正文的公告(crawl_status=pending 且有 announcement_url)。"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM announcements
               WHERE crawl_status = 'pending'
                 AND announcement_url IS NOT NULL
                 AND announcement_url != ''
               ORDER BY id LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_announcements_for_llm(limit: int = 100) -> List[Dict]:
    """获取待 LLM 拆岗的公告(llm_status=pending)。

    不再限制 crawl_status:微信公众号反爬导致正文常抓不到,
    但公告标题本身已含岗位列表,可用标题做 LLM 拆岗。
    """
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM announcements
               WHERE llm_status = 'pending'
               ORDER BY id LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_crawl_status(announcement_id: int, status: str,
                        error: str = "", content: str = ""):
    """更新公告正文抓取状态,可选存储正文内容。status: success/failed/skipped。"""
    conn = _get_conn()
    try:
        if content:
            conn.execute(
                """UPDATE announcements SET crawl_status=?, crawl_time=?, crawl_error=?,
                   content=? WHERE id=?""",
                (status, _now(), error, content, announcement_id),
            )
        else:
            conn.execute(
                "UPDATE announcements SET crawl_status=?, crawl_time=?, crawl_error=? WHERE id=?",
                (status, _now(), error, announcement_id),
            )
        conn.commit()
    finally:
        conn.close()


def update_announcement_images(announcement_id: int, images_json: str):
    """更新公告的图片 URL 列表(JSON 字符串)。"""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE announcements SET content_images=? WHERE id=?",
            (images_json, announcement_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_llm_status(announcement_id: int, status: str,
                      positions_count: int = 0, cache_hash: str = ""):
    """更新公告 LLM 拆岗状态。status: success/failed/skipped。"""
    conn = _get_conn()
    try:
        conn.execute(
            """UPDATE announcements SET llm_status=?, llm_time=?, positions_count=?,
               llm_cache_hash=? WHERE id=?""",
            (status, _now(), positions_count, cache_hash, announcement_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_vl_status(announcement_id: int, status: str, error: str = ""):
    """更新公告 VL 识别状态。status: success/failed/not_needed。"""
    conn = _get_conn()
    try:
        conn.execute(
            """UPDATE announcements SET vl_status=?, vl_error=? WHERE id=?""",
            (status, error[:300], announcement_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_vl_failed_announcements() -> List[Dict]:
    """获取所有 VL 识别失败的公告(vl_status=failed),用于导出飞书失败记录表。"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT id, company_name, announcement_title, announcement_url,
                      apply_url, apply_update, vl_error, content_images,
                      length(content) as content_len
               FROM announcements
               WHERE vl_status = 'failed'
               ORDER BY id DESC"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_announcement_by_id(announcement_id: int) -> Optional[Dict]:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM announcements WHERE id = ?", (announcement_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_last_sync_time() -> str:
    """获取最近一次同步的 last_modified 最大值(增量同步游标)。"""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT MAX(last_modified) as lm FROM announcements"
        ).fetchone()
        return row["lm"] if row and row["lm"] else ""
    finally:
        conn.close()


# ==================== positions ====================

def compute_position_hash(company: str, position_title: str, location: str) -> str:
    """岗位去重 hash = md5(company + position_title + location)。"""
    raw = f"{company.strip()}|{position_title.strip()}|{(location or '').strip()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def insert_positions(announcement_id: int, company_id: int,
                     company_name: str, positions: List[Dict],
                     source_url: str = "") -> int:
    """
    批量插入岗位(从 LLM 拆出的岗位列表)。
    去重:company + position_title + location 相同则跳过。
    返回实际插入数。
    """
    if not positions:
        return 0
    conn = _get_conn()
    inserted = 0
    now = _now()
    try:
        for pos in positions:
            title = pos.get("position_title", "").strip()
            if not title:
                continue
            location = pos.get("location", "") or pos.get("city", "")
            dedup_hash = compute_position_hash(company_name, title, location)
            # 数组字段序列化为 JSON 字符串
            def _arr(key):
                val = pos.get(key, [])
                if isinstance(val, list):
                    return json.dumps(val, ensure_ascii=False)
                return str(val) if val else ""
            try:
                cur = conn.execute(
                    """INSERT OR IGNORE INTO positions
                       (announcement_id, company_id, company_name, position_title,
                        department, job_category, job_subcategory,
                        hard_skills, soft_skills, certifications, languages,
                        major_required, major_category,
                        min_education, city, province,
                        recruitment_process, has_written_test,
                        responsibilities, requirements, bonus_points, keywords,
                        location, education_req, major_req, jd_summary,
                        is_management_trainee, difficulty, apply_url, source_url,
                        dedup_hash, status, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'在招',?)""",
                    (
                        announcement_id, company_id, company_name, title,
                        pos.get("department", ""),
                        pos.get("job_category", ""), pos.get("job_subcategory", ""),
                        _arr("hard_skills"), _arr("soft_skills"),
                        _arr("certifications"), _arr("languages"),
                        pos.get("major_required", ""), pos.get("major_category", ""),
                        pos.get("min_education", ""), pos.get("city", ""), pos.get("province", ""),
                        pos.get("recruitment_process", ""),
                        1 if pos.get("has_written_test") else 0,
                        pos.get("responsibilities", ""), pos.get("requirements", ""),
                        pos.get("bonus_points", ""), _arr("keywords"),
                        location,
                        pos.get("education_req", "") or pos.get("min_education", ""),
                        pos.get("major_req", "") or pos.get("major_required", ""),
                        pos.get("jd_summary", ""),
                        1 if pos.get("is_management_trainee") else 0,
                        pos.get("difficulty", ""), pos.get("apply_url", ""),
                        source_url, dedup_hash, now,
                    ),
                )
                if cur.rowcount > 0:
                    inserted += 1
            except sqlite3.IntegrityError:
                pass
        conn.commit()
        logger.info(f"公告 {announcement_id}: 插入 {inserted}/{len(positions)} 个岗位")
        return inserted
    finally:
        conn.close()


# ==================== 导出查询(飞书总表) ====================

def get_all_companies() -> List[Dict]:
    """获取所有公司(含最新公告的网申链接,用于飞书总表导出)。"""
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT c.*,
                   (SELECT a.apply_url FROM announcements a
                    WHERE a.company_id = c.id AND a.apply_url != ''
                    ORDER BY a.id DESC LIMIT 1) as apply_url
            FROM companies c ORDER BY c.name
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_latest_announcement_by_company(company_id: int) -> Dict:
    """获取公司最新公告(用于公司总表展示源表字段)。"""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM announcements WHERE company_id=? ORDER BY id DESC LIMIT 1",
            (company_id,),
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def get_announcement_count_by_company(company_id: int) -> int:
    """获取公司的公告数量。"""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as c FROM announcements WHERE company_id=?",
            (company_id,),
        ).fetchone()
        return row["c"] if row else 0
    finally:
        conn.close()


def get_position_count_by_company(company_id: int) -> int:
    """获取公司的岗位数量。"""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as c FROM positions WHERE company_id=?",
            (company_id,),
        ).fetchone()
        return row["c"] if row else 0
    finally:
        conn.close()


def get_all_positions_for_export() -> List[Dict]:
    """获取所有岗位(含公司行业/类型、公告网申更新/链接,用于飞书总表导出)。"""
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT p.*, c.industry, c.company_type,
                   a.apply_update, a.announcement_url
            FROM positions p
            JOIN companies c ON p.company_id = c.id
            JOIN announcements a ON p.announcement_id = a.id
            ORDER BY p.company_name, p.id
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_active_positions(user_grade: int = 0,
                         industries: Optional[List[str]] = None,
                         company_types: Optional[List[str]] = None) -> List[Dict]:
    """
    获取在招岗位(JOIN announcements + companies),供 user_matcher 使用。

    Args:
        user_grade: 用户毕业届数(25/26/27),0 表示不按届数过滤
        industries: 目标行业列表,None 表示不过滤
        company_types: 目标公司类型列表,None 表示不过滤

    Returns: 岗位列表(含公司/公告关联字段)
    """
    conn = _get_conn()
    try:
        sql = """
            SELECT p.*, a.recruit_type, a.min_grade, a.max_grade, a.deadline,
                   a.publish_time, a.apply_url as ann_apply_url,
                   a.announcement_url, c.industry, c.company_type
            FROM positions p
            JOIN announcements a ON p.announcement_id = a.id
            JOIN companies c ON p.company_id = c.id
            WHERE p.status = '在招'
        """
        params: List = []
        if user_grade:
            sql += " AND a.min_grade <= ? AND a.max_grade >= ?"
            params.extend([user_grade, user_grade])
        if industries:
            placeholders = ",".join("?" * len(industries))
            sql += f" AND c.industry IN ({placeholders})"
            params.extend(industries)
        if company_types:
            placeholders = ",".join("?" * len(company_types))
            sql += f" AND c.company_type IN ({placeholders})"
            params.extend(company_types)
        sql += " ORDER BY p.id"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_positions_by_company(company_name: str) -> List[Dict]:
    """按公司获取在招岗位。"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT p.*, a.recruit_type, a.min_grade, a.max_grade, a.deadline,
                      c.industry, c.company_type
               FROM positions p
               JOIN announcements a ON p.announcement_id = a.id
               JOIN companies c ON p.company_id = c.id
               WHERE p.company_name = ? AND p.status = '在招'""",
            (company_name,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def close_position(dedup_hash: str):
    """将岗位标记为已关闭。"""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE positions SET status = '已关闭' WHERE dedup_hash = ?",
            (dedup_hash,),
        )
        conn.commit()
    finally:
        conn.close()


# ==================== 统计 ====================

def get_stats() -> Dict:
    """获取总数据库统计。"""
    conn = _get_conn()
    try:
        co = conn.execute("SELECT COUNT(*) as cnt FROM companies").fetchone()
        ann = conn.execute(
            "SELECT COUNT(*) as cnt, "
            "SUM(CASE WHEN crawl_status='success' THEN 1 ELSE 0 END) as crawled, "
            "SUM(CASE WHEN llm_status='success' THEN 1 ELSE 0 END) as enriched "
            "FROM announcements"
        ).fetchone()
        pos = conn.execute(
            "SELECT COUNT(*) as cnt, "
            "SUM(CASE WHEN status='在招' THEN 1 ELSE 0 END) as active, "
            "SUM(CASE WHEN is_management_trainee=1 THEN 1 ELSE 0 END) as mt "
            "FROM positions"
        ).fetchone()
        return {
            "companies": co["cnt"],
            "announcements": ann["cnt"],
            "announcements_crawled": ann["crawled"],
            "announcements_enriched": ann["enriched"],
            "positions": pos["cnt"],
            "positions_active": pos["active"],
            "positions_mt": pos["mt"],
        }
    finally:
        conn.close()
