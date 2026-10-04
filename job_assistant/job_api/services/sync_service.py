"""岗位同步服务:从 jobs.db 增量读取岗位,供桌面端拉取。

设计要点
--------
- 数据源对齐 spec 的 ``jobs`` 表 schema,字段顺序固定(见 ``JOB_FIELDS``)。
- ``jobs.db`` 实际有三张物理表(companies/announcements/positions),
  并无 ``jobs`` 表。本服务在初始化时按需创建同名 ``jobs`` 视图,
  把三表 JOIN 后映射成 spec 字段;若调用方已自行建好 ``jobs`` 表
  (例如测试),则尊重既有对象,不覆盖。
- 增量查询基于 ``updated_at > since``;分页采用复合游标
  ``(updated_at, job_id)``,严格大于,避免同一时间戳漏行/重行。
- 仅使用标准库 ``sqlite3``,不引入额外 pip 依赖。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

# spec 的 jobs 表字段顺序(对外契约,不要随意调整)
JOB_FIELDS: tuple[str, ...] = (
    "job_id",
    "company",
    "title",
    "category",
    "city",
    "requirements",
    "jd_text",
    "apply_url",
    "deadline",
    "source",
    "graduation_match",
    "is_mt",
    "updated_at",
)

DEFAULT_PAGE_SIZE = 500
MAX_PAGE_SIZE = 1000

# 公司总表字段（对齐飞书 COMPANY_FIELDS）
COMPANY_FIELDS: tuple[str, ...] = (
    "company_id",
    "company_name",
    "industry",
    "company_type",
    "recruit_type",
    "recruit_target",
    "location",
    "education_req",
    "deadline",
    "positions_count",
    "apply_url",
    "announcement_url",
    "last_updated",
)

# 公司视图：companies + announcements 汇总（每个公司取最新公告）
_COMPANIES_VIEW_SQL = """
CREATE VIEW IF NOT EXISTS company_overview AS
SELECT
    CAST(c.id AS TEXT) AS company_id,
    c.name AS company_name,
    COALESCE(c.industry, '') AS industry,
    COALESCE(c.company_type, '') AS company_type,
    COALESCE(a.recruit_type, '') AS recruit_type,
    COALESCE(a.recruit_target, '') AS recruit_target,
    COALESCE(a.location, '') AS location,
    COALESCE(a.education_req, '') AS education_req,
    a.deadline AS deadline,
    COALESCE(a.positions_count, 0) AS positions_count,
    COALESCE(a.apply_url, '') AS apply_url,
    COALESCE(a.announcement_url, '') AS announcement_url,
    COALESCE(c.last_updated, '') AS last_updated
FROM companies c
LEFT JOIN (
    SELECT company_id, MAX(last_modified) AS max_modified
    FROM announcements
    GROUP BY company_id
) latest ON c.id = latest.company_id
LEFT JOIN announcements a ON a.company_id = c.id AND a.last_modified = latest.max_modified
"""

# jobs.db 没有物理 jobs 表时,从三表 JOIN 出 spec 字段的视图定义。
_JOBS_VIEW_SQL = """
CREATE VIEW IF NOT EXISTS jobs AS
SELECT
    CAST(p.id AS TEXT) AS job_id,
    p.company_name AS company,
    p.position_title AS title,
    COALESCE(p.job_category, '') AS category,
    COALESCE(p.city, p.location, '') AS city,
    COALESCE(p.requirements, '') AS requirements,
    COALESCE(p.jd_summary, p.responsibilities, '') AS jd_text,
    COALESCE(p.apply_url, a.apply_url, '') AS apply_url,
    a.deadline AS deadline,
    COALESCE(p.source_url, a.announcement_url, '') AS source,
    CASE WHEN a.min_grade IS NULL OR a.max_grade IS NULL
         THEN 1 ELSE 0 END AS graduation_match,
    p.is_management_trainee AS is_mt,
    p.created_at AS updated_at
FROM positions p
JOIN announcements a ON p.announcement_id = a.id
JOIN companies c ON p.company_id = c.id
"""


class SyncService:
    """岗位增量同步服务。

    Parameters
    ----------
    db_path:
        SQLite 数据库路径,默认取 ``settings.JOBS_DB_PATH``。
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is None:
            # 延迟导入:避免在仅做静态分析或单元测试(传 db_path)时
            # 强依赖 pydantic_settings。生产路径仍走 settings.JOBS_DB_PATH。
            from config import get_settings
            db_path = get_settings().JOBS_DB_PATH
        self.db_path = Path(db_path)
        self._ensure_schema()

    # ---------------- 内部 ----------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ensure_schema(self) -> None:
        """确保 ``jobs`` 表/视图存在。

        - 已存在物理表：直接复用，不覆盖。
        - 已存在视图：DROP 后重建（兼容旧版视图字段类型变更，如 job_id 需 CAST AS TEXT）。
        - 不存在：尝试从 positions+announcements+companies 创建同名视图。
        - 依赖表缺失（例如测试只建了 jobs 表）：忽略错误，留给调用方建表。
        """
        try:
            conn = self._connect()
        except sqlite3.Error:
            return
        try:
            row = conn.execute(
                "SELECT type FROM sqlite_master WHERE name = 'jobs'"
            ).fetchone()
            if row is not None:
                if row["type"] == "table":
                    # 物理表：尊重既有对象，不覆盖。
                    return
                # 视图：DROP 后重建，确保字段定义与当前 _JOBS_VIEW_SQL 一致。
                try:
                    conn.execute("DROP VIEW IF EXISTS jobs")
                except sqlite3.Error:
                    pass
            try:
                conn.execute(_JOBS_VIEW_SQL)
                conn.execute(_COMPANIES_VIEW_SQL)
                conn.commit()
            except sqlite3.Error:
                # 依赖表不存在等,忽略;调用方需自行保证 jobs 表存在
                pass
        finally:
            conn.close()

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> dict:
        return {f: row[f] for f in JOB_FIELDS}

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[str, int]:
        """``cursor = '{updated_at}|{job_id}'``,反解为 (updated_at, job_id)。

        空或损坏的 cursor 返回 ``("", 0)``,调用方据此走无游标分支。
        """
        if not cursor:
            return ("", 0)
        try:
            ts, jid = cursor.rsplit("|", 1)
            return (ts, int(jid))
        except (ValueError, AttributeError):
            return ("", 0)

    @staticmethod
    def _encode_cursor(updated_at: str, job_id: int) -> str:
        return f"{updated_at}|{job_id}"

    # ---------------- 公共 API ----------------

    def get_jobs_since(
        self,
        since: str = "",
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: Optional[str] = None,
    ) -> dict:
        """增量查询 ``updated_at > since`` 的岗位,游标分页。

        Parameters
        ----------
        since:
            增量时间戳,空串表示从头拉取。
        limit:
            每页大小,默认 500,上限 1000,小于 1 取默认值。
        cursor:
            上一页返回的 ``next_cursor``,格式 ``'{updated_at}|{job_id}'``。
            给定 cursor 时以 cursor 为准(隐含 since)。

        Returns
        -------
        dict
            ``{"jobs": [...], "next_cursor": str | None}``。
            ``next_cursor`` 为 ``None`` 表示无更多数据。
        """
        if limit is None or limit < 1:
            limit = DEFAULT_PAGE_SIZE
        if limit > MAX_PAGE_SIZE:
            limit = MAX_PAGE_SIZE

        cursor_ts, cursor_id = self._decode_cursor(cursor) if cursor else ("", 0)
        fields = ", ".join(JOB_FIELDS)

        if cursor and cursor_ts:
            # 游标分页:严格大于 (cursor_ts, cursor_id)
            sql = (
                f"SELECT {fields} FROM jobs "
                "WHERE (updated_at > ? OR (updated_at = ? AND job_id > ?)) "
                "ORDER BY updated_at ASC, job_id ASC LIMIT ?"
            )
            params: list = [cursor_ts, cursor_ts, cursor_id, limit + 1]
        else:
            sql = (
                f"SELECT {fields} FROM jobs "
                "WHERE updated_at > ? "
                "ORDER BY updated_at ASC, job_id ASC LIMIT ?"
            )
            params = [since or "", limit + 1]

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        jobs = [self._row_to_job(r) for r in rows[:limit]]
        next_cursor = None
        if len(rows) > limit:
            last = jobs[-1]
            next_cursor = self._encode_cursor(last["updated_at"], last["job_id"])
        return {"jobs": jobs, "next_cursor": next_cursor}

    def get_jobs_page(
        self,
        limit: int = 50,
        offset: int = 0,
        category: str = "",
        keyword: str = "",
        city: str = "",
    ) -> dict:
        """按 offset 分页查询岗位（供前端表格分页使用）。

        Parameters
        ----------
        limit: 每页条数，默认 50。
        offset: 偏移量。
        category: 岗位分类筛选（空串=不限）。
        keyword: 关键词搜索（标题/公司/JD）。
        city: 城市筛选（空串=不限）。
        """
        if limit < 1:
            limit = 50
        if limit > MAX_PAGE_SIZE:
            limit = MAX_PAGE_SIZE

        where = []
        params: list = []
        if category:
            where.append("category = ?")
            params.append(category)
        if city:
            where.append("city = ?")
            params.append(city)
        if keyword:
            where.append("(title LIKE ? OR company LIKE ? OR jd_text LIKE ?)")
            kw = f"%{keyword}%"
            params.extend([kw, kw, kw])

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        fields = ", ".join(JOB_FIELDS)

        conn = self._connect()
        try:
            total_row = conn.execute(
                f"SELECT COUNT(*) AS c FROM jobs {where_sql}", params
            ).fetchone()
            total = total_row["c"] if total_row else 0

            rows = conn.execute(
                f"SELECT {fields} FROM jobs {where_sql} "
                "ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        finally:
            conn.close()

        jobs = [self._row_to_job(r) for r in rows]
        return {"jobs": jobs, "total": total, "limit": limit, "offset": offset}

    def get_stats(self) -> dict:
        """返回 ``{"total": 岗位总数, "updated_at": 最新更新时间}``。"""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS total, MAX(updated_at) AS updated_at FROM jobs"
            ).fetchone()
        finally:
            conn.close()
        return {
            "total": row["total"] if row else 0,
            "updated_at": (row["updated_at"] if row and row["updated_at"] else ""),
        }

    def get_companies(
        self,
        limit: int = 200,
        offset: int = 0,
        industry: str = "",
        company_type: str = "",
        keyword: str = "",
    ) -> dict:
        """分页拉取公司总览（对齐飞书公司表字段）。

        Parameters
        ----------
        limit: 每页数量，默认 200。
        offset: 偏移量。
        industry: 行业筛选（空串=不限）。
        company_type: 公司类型筛选（空串=不限）。
        keyword: 公司名关键词搜索。
        """
        if limit < 1:
            limit = 200
        if limit > MAX_PAGE_SIZE:
            limit = MAX_PAGE_SIZE

        where = []
        params: list = []
        if industry:
            where.append("industry = ?")
            params.append(industry)
        if company_type:
            where.append("company_type = ?")
            params.append(company_type)
        if keyword:
            where.append("company_name LIKE ?")
            params.append(f"%{keyword}%")

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        fields = ", ".join(COMPANY_FIELDS)

        conn = self._connect()
        try:
            total_row = conn.execute(
                f"SELECT COUNT(*) AS c FROM company_overview {where_sql}", params
            ).fetchone()
            total = total_row["c"] if total_row else 0

            rows = conn.execute(
                f"SELECT {fields} FROM company_overview {where_sql} "
                "ORDER BY last_updated DESC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        finally:
            conn.close()

        companies = [{f: r[f] for f in COMPANY_FIELDS} for r in rows]
        return {"companies": companies, "total": total, "limit": limit, "offset": offset}

    def get_company_stats(self) -> dict:
        """公司维度统计：总数 + 行业分布 + 类型分布。"""
        conn = self._connect()
        try:
            total_row = conn.execute(
                "SELECT COUNT(*) AS c FROM company_overview"
            ).fetchone()
            total = total_row["c"] if total_row else 0

            industry_rows = conn.execute(
                "SELECT industry, COUNT(*) AS c FROM company_overview "
                "WHERE industry != '' GROUP BY industry ORDER BY c DESC LIMIT 12"
            ).fetchall()
            type_rows = conn.execute(
                "SELECT company_type, COUNT(*) AS c FROM company_overview "
                "WHERE company_type != '' GROUP BY company_type ORDER BY c DESC"
            ).fetchall()
        finally:
            conn.close()

        return {
            "total": total,
            "industries": [{"name": r["industry"], "count": r["c"]} for r in industry_rows],
            "types": [{"name": r["company_type"], "count": r["c"]} for r in type_rows],
        }

    def get_job_categories(self) -> dict:
        """岗位分类统计（用于侧边栏导航）。"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT category, COUNT(*) AS c FROM jobs "
                "WHERE category != '' GROUP BY category ORDER BY c DESC"
            ).fetchall()
        finally:
            conn.close()

        return {
            "categories": [{"name": r["category"], "count": r["c"]} for r in rows],
        }
