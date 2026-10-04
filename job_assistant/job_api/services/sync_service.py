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


class DatabaseCorruptedError(Exception):
    """本地 jobs.db 损坏时抛出，路由层捕获后返回清晰的 503 + 修复提示。"""

    def __init__(self, detail: str = "本地数据库损坏，请点击同步重新从服务器拉取") -> None:
        super().__init__(detail)
        self.detail = detail

# spec 的 jobs 表字段顺序(对外契约,不要随意调整)
# 对齐飞书「27届校招汇总表」列顺序
JOB_FIELDS: tuple[str, ...] = (
    "job_id",
    "title",
    "company",
    "industry",
    "company_type",
    "category",
    "subcategory",
    "city",
    "min_education",
    "is_mt",
    "major_category",
    "major_required",
    "hard_skills",
    "keywords",
    "jd_summary",
    "difficulty",
    "updated_at",
    "deadline",
    "apply_url",
    "announcement_url",
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
    "position_titles",
    "apply_url",
    "announcement_url",
    "last_updated",
)

# 公司视图：companies + announcements 汇总（每个公司取最新公告）
# last_updated 取公告的 apply_update（实际发布/更新时间），而非公司同步时间
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
    (SELECT GROUP_CONCAT(position_title, '、')
       FROM (SELECT position_title FROM positions
              WHERE company_id = c.id ORDER BY id LIMIT 15)) AS position_titles,
    COALESCE(a.apply_url, '') AS apply_url,
    COALESCE(a.announcement_url, '') AS announcement_url,
    COALESCE(a.apply_update, '') AS last_updated
FROM companies c
LEFT JOIN (
    SELECT company_id, MAX(last_modified) AS max_modified
    FROM announcements
    GROUP BY company_id
) latest ON c.id = latest.company_id
LEFT JOIN announcements a ON a.company_id = c.id AND a.last_modified = latest.max_modified
"""

# jobs.db 没有物理 jobs 表时,从三表 JOIN 出 spec 字段的视图定义。
# updated_at 取公告 apply_update（发布时间），与公司表口径一致
_JOBS_VIEW_SQL = """
CREATE VIEW IF NOT EXISTS jobs AS
SELECT
    CAST(p.id AS TEXT) AS job_id,
    p.position_title AS title,
    p.company_name AS company,
    COALESCE(c.industry, '') AS industry,
    COALESCE(c.company_type, '') AS company_type,
    COALESCE(p.job_category, '') AS category,
    COALESCE(p.job_subcategory, '') AS subcategory,
    COALESCE(p.city, p.location, '') AS city,
    COALESCE(p.min_education, p.education_req, '') AS min_education,
    p.is_management_trainee AS is_mt,
    COALESCE(p.major_category, '') AS major_category,
    COALESCE(p.major_required, p.major_req, '') AS major_required,
    COALESCE(p.hard_skills, '') AS hard_skills,
    COALESCE(p.keywords, '') AS keywords,
    COALESCE(p.jd_summary, p.responsibilities, '') AS jd_summary,
    COALESCE(p.difficulty, '') AS difficulty,
    COALESCE(a.apply_update, '') AS updated_at,
    a.deadline AS deadline,
    COALESCE(p.apply_url, a.apply_url, '') AS apply_url,
    COALESCE(p.source_url, a.announcement_url, '') AS announcement_url
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
                # 视图：DROP 后重建，确保字段定义与当前 SQL 一致。
                for _v in ("jobs", "company_overview"):
                    try:
                        conn.execute(f"DROP VIEW IF EXISTS {_v}")
                    except sqlite3.Error:
                        pass
            else:
                # jobs 不存在时，也确保 company_overview 旧视图被清掉再重建
                try:
                    conn.execute("DROP VIEW IF EXISTS company_overview")
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
        except sqlite3.DatabaseError as e:
            raise DatabaseCorruptedError(f"数据库损坏: {e}") from e
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
        industry: str = "",
        company_type: str = "",
        subcategory: str = "",
        min_education: str = "",
        is_mt: str = "",
        major_category: str = "",
        difficulty: str = "",
    ) -> dict:
        """按 offset 分页查询岗位（供前端表格分页使用）。

        Parameters
        ----------
        limit: 每页条数，默认 50。
        offset: 偏移量。
        category: 岗位分类筛选（空串=不限）。
        keyword: 关键词搜索（标题/公司/JD）。
        city: 城市筛选（空串=不限）。
        industry: 行业筛选。
        company_type: 公司类型筛选。
        subcategory: 岗位子类筛选。
        min_education: 最低学历筛选。
        is_mt: 是否管培筛选（"1"/"0"）。
        major_category: 专业大类筛选。
        difficulty: 难度筛选。
        """
        if limit < 1:
            limit = 50
        if limit > MAX_PAGE_SIZE:
            limit = MAX_PAGE_SIZE

        where = []
        params: list = []

        def _add_multi(field: str, raw: str) -> None:
            """支持逗号分隔多值：category=a,b → category IN (?, ?)。"""
            vals = [v.strip() for v in raw.split(",") if v.strip()]
            if not vals:
                return
            placeholders = ", ".join(["?"] * len(vals))
            where.append(f"{field} IN ({placeholders})")
            params.extend(vals)

        if category:
            _add_multi("category", category)
        if city:
            _add_multi("city", city)
        if industry:
            _add_multi("industry", industry)
        if company_type:
            _add_multi("company_type", company_type)
        if subcategory:
            _add_multi("subcategory", subcategory)
        if min_education:
            _add_multi("min_education", min_education)
        if is_mt:
            _add_multi("is_mt", is_mt)
        if major_category:
            _add_multi("major_category", major_category)
        if difficulty:
            _add_multi("difficulty", difficulty)
        if keyword:
            where.append("(title LIKE ? OR company LIKE ? OR jd_summary LIKE ?)")
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
        except sqlite3.DatabaseError as e:
            raise DatabaseCorruptedError(f"数据库损坏: {e}") from e
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
        except sqlite3.DatabaseError as e:
            raise DatabaseCorruptedError(f"数据库损坏: {e}") from e
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
        recruit_type: str = "",
        education_req: str = "",
    ) -> dict:
        """分页拉取公司总览（对齐飞书公司表字段）。

        Parameters
        ----------
        limit: 每页数量，默认 200。
        offset: 偏移量。
        industry: 行业筛选（空串=不限）。
        company_type: 公司类型筛选（空串=不限）。
        keyword: 公司名关键词搜索。
        recruit_type: 招聘类型筛选。
        education_req: 学历要求筛选。
        """
        if limit < 1:
            limit = 200
        if limit > MAX_PAGE_SIZE:
            limit = MAX_PAGE_SIZE

        where = []
        params: list = []

        def _add_multi_c(field: str, raw: str) -> None:
            vals = [v.strip() for v in raw.split(",") if v.strip()]
            if not vals:
                return
            placeholders = ", ".join(["?"] * len(vals))
            where.append(f"{field} IN ({placeholders})")
            params.extend(vals)

        if industry:
            _add_multi_c("industry", industry)
        if company_type:
            _add_multi_c("company_type", company_type)
        if recruit_type:
            _add_multi_c("recruit_type", recruit_type)
        if education_req:
            _add_multi_c("education_req", education_req)
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
        except sqlite3.DatabaseError as e:
            raise DatabaseCorruptedError(f"数据库损坏: {e}") from e
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
        except sqlite3.DatabaseError as e:
            raise DatabaseCorruptedError(f"数据库损坏: {e}") from e
        finally:
            conn.close()

        return {
            "total": total,
            "industries": [{"name": r["industry"], "count": r["c"]} for r in industry_rows],
            "types": [{"name": r["company_type"], "count": r["c"]} for r in type_rows],
        }

    def get_stats_overview(self) -> dict:
        """公司页 + 岗位页上方统计卡片所需的汇总数据。

        返回：
        - 公司/岗位 总数
        - 今日新增、近7日新增（按 apply_update 日期）
        - 行业分布 Top5、公司类型分布、岗位分类分布
        - 近7日将截止的公司数（deadline 非空且在未来 7 天内）
        """
        import datetime as _dt

        today = _dt.date.today()
        today_str = today.strftime("%Y-%m-%d")
        week_ago = (today - _dt.timedelta(days=7)).strftime("%Y-%m-%d")
        in_7_days = (today + _dt.timedelta(days=7)).strftime("%Y-%m-%d")

        conn = self._connect()
        try:
            # ---- 公司统计 ----
            c_total = conn.execute("SELECT COUNT(*) AS c FROM company_overview").fetchone()["c"]
            c_today = conn.execute(
                "SELECT COUNT(*) AS c FROM company_overview WHERE last_updated >= ?",
                (today_str,),
            ).fetchone()["c"]
            c_week = conn.execute(
                "SELECT COUNT(*) AS c FROM company_overview WHERE last_updated >= ?",
                (week_ago,),
            ).fetchone()["c"]

            c_industries = conn.execute(
                "SELECT industry, COUNT(*) AS c FROM company_overview "
                "WHERE industry != '' GROUP BY industry ORDER BY c DESC LIMIT 5"
            ).fetchall()
            c_types = conn.execute(
                "SELECT company_type, COUNT(*) AS c FROM company_overview "
                "WHERE company_type != '' GROUP BY company_type ORDER BY c DESC LIMIT 5"
            ).fetchall()

            # 近7日将截止的公司（deadline 非空、格式为日期、在 today..today+7 之间）
            # deadline 可能为 "2026/5/21" 或 "2026-05-21"，统一替换 / 为 - 后比较
            closing = conn.execute(
                "SELECT COUNT(*) AS c FROM company_overview "
                "WHERE deadline IS NOT NULL AND deadline != '' "
                "  AND substr(REPLACE(deadline, '/', '-'), 1, 10) >= ? "
                "  AND substr(REPLACE(deadline, '/', '-'), 1, 10) <= ?",
                (today_str, in_7_days),
            ).fetchone()["c"]

            # ---- 岗位统计 ----
            j_total = conn.execute("SELECT COUNT(*) AS c FROM jobs").fetchone()["c"]
            j_today = conn.execute(
                "SELECT COUNT(*) AS c FROM jobs WHERE updated_at >= ?",
                (today_str,),
            ).fetchone()["c"]
            j_week = conn.execute(
                "SELECT COUNT(*) AS c FROM jobs WHERE updated_at >= ?",
                (week_ago,),
            ).fetchone()["c"]

            j_categories = conn.execute(
                "SELECT category, COUNT(*) AS c FROM jobs "
                "WHERE category != '' GROUP BY category ORDER BY c DESC LIMIT 8"
            ).fetchall()

            # ---- 公司筛选选项（各列去重值） ----
            c_industries_all = conn.execute(
                "SELECT DISTINCT industry FROM company_overview WHERE industry != '' ORDER BY industry"
            ).fetchall()
            c_types_all = conn.execute(
                "SELECT DISTINCT company_type FROM company_overview WHERE company_type != '' ORDER BY company_type"
            ).fetchall()
            c_recruit_all = conn.execute(
                "SELECT DISTINCT recruit_type FROM company_overview WHERE recruit_type != '' ORDER BY recruit_type"
            ).fetchall()
            c_edu_all = conn.execute(
                "SELECT DISTINCT education_req FROM company_overview WHERE education_req != '' ORDER BY education_req"
            ).fetchall()

            # ---- 岗位筛选选项（各列去重值） ----
            j_industry_all = conn.execute(
                "SELECT DISTINCT industry FROM jobs WHERE industry != '' ORDER BY industry"
            ).fetchall()
            j_type_all = conn.execute(
                "SELECT DISTINCT company_type FROM jobs WHERE company_type != '' ORDER BY company_type"
            ).fetchall()
            j_cat_all = conn.execute(
                "SELECT DISTINCT category FROM jobs WHERE category != '' ORDER BY category"
            ).fetchall()
            j_subcat_all = conn.execute(
                "SELECT DISTINCT subcategory FROM jobs WHERE subcategory != '' ORDER BY subcategory"
            ).fetchall()
            j_edu_all = conn.execute(
                "SELECT DISTINCT min_education FROM jobs WHERE min_education != '' ORDER BY min_education"
            ).fetchall()
            j_major_all = conn.execute(
                "SELECT DISTINCT major_category FROM jobs WHERE major_category != '' ORDER BY major_category"
            ).fetchall()
            j_diff_all = conn.execute(
                "SELECT DISTINCT difficulty FROM jobs WHERE difficulty != '' ORDER BY difficulty"
            ).fetchall()
        except sqlite3.DatabaseError as e:
            raise DatabaseCorruptedError(f"数据库损坏: {e}") from e
        finally:
            conn.close()

        return {
            "companies": {
                "total": c_total,
                "today_new": c_today,
                "week_new": c_week,
                "closing_soon": closing,
                "top_industries": [
                    {"name": r["industry"], "count": r["c"]} for r in c_industries
                ],
                "top_types": [
                    {"name": r["company_type"], "count": r["c"]} for r in c_types
                ],
                "filter_options": {
                    "industry": [r["industry"] for r in c_industries_all],
                    "company_type": [r["company_type"] for r in c_types_all],
                    "recruit_type": [r["recruit_type"] for r in c_recruit_all],
                    "education_req": [r["education_req"] for r in c_edu_all],
                },
            },
            "jobs": {
                "total": j_total,
                "today_new": j_today,
                "week_new": j_week,
                "top_categories": [
                    {"name": r["category"], "count": r["c"]} for r in j_categories
                ],
                "filter_options": {
                    "industry": [r["industry"] for r in j_industry_all],
                    "company_type": [r["company_type"] for r in j_type_all],
                    "category": [r["category"] for r in j_cat_all],
                    "subcategory": [r["subcategory"] for r in j_subcat_all],
                    "min_education": [r["min_education"] for r in j_edu_all],
                    "major_category": [r["major_category"] for r in j_major_all],
                    "difficulty": [r["difficulty"] for r in j_diff_all],
                    "is_mt": [{"value": "1", "label": "是"}, {"value": "0", "label": "否"}],
                },
            },
        }

    def get_job_categories(self) -> dict:
        """岗位分类统计（用于侧边栏导航）。"""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT category, COUNT(*) AS c FROM jobs "
                "WHERE category != '' GROUP BY category ORDER BY c DESC"
            ).fetchall()
        except sqlite3.DatabaseError as e:
            raise DatabaseCorruptedError(f"数据库损坏: {e}") from e
        finally:
            conn.close()

        return {
            "categories": [{"name": r["category"], "count": r["c"]} for r in rows],
        }
