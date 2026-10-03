//! SQLite 数据层：所有本地数据 CRUD（岗位 / 用户配置 / 简历 / 投递）。
//!
//! 架构：
//! - `Db(Mutex<Connection>)` 由 Tauri State 跨命令共享，单连接 + 互斥锁在桌面端单用户场景下足够（读多写少，毫秒级查询）。
//! - `init_db_with_conn(&Connection)` 接收任意连接（含 `:memory:`），用 `include_str!` 把 migrations/001_init.sql 编进二进制一次性 `execute_batch`，幂等可重入；生产与测试同一路径，避免 schema 漂移。
//! - `init_db(&Path)` 在 `app_data_dir` 下建 `~/.jobassistant/workbench.db`（与 spec "本地 SQLite 自动备份" 路径同根）。
//! - 所有 CRUD 用 `ON CONFLICT(...) DO UPDATE` 实现幂等 upsert，同步任务可重放。

use std::path::{Path, PathBuf};
use std::sync::Mutex;

use rusqlite::{params, Connection, OptionalExtension};

use crate::models::{Application, Job, JobFilter, JobStats, Resume, UserConfig};

/// 编译期把 migrations/001_init.sql 嵌入二进制，运行时不依赖文件系统。
const SCHEMA_SQL: &str = include_str!("../migrations/001_init.sql");

/// Tauri State 持有的 DB 句柄。
/// Mutex 包装保证多 invoke 命令并发安全（rusqlite::Connection 本身非 Sync）。
pub struct Db(pub Mutex<Connection>);

impl Db {
    /// 测试 / 显式注入连接入口（不依赖文件系统）。
    pub fn from_conn(conn: Connection) -> Self {
        Self(Mutex::new(conn))
    }

    /// 锁连接（持有期短，避免长事务阻塞 UI）。
    fn lock(&self) -> std::sync::MutexGuard<'_, Connection> {
        self.0.lock().expect("DB mutex poisoned")
    }
}

// ============================================================================
// 初始化与路径
// ============================================================================

/// 返回 ~/.jobassistant/workbench.db 的绝对路径（app_data_dir 由调用方传入，Tauri 在 setup() 中解析）。
pub fn get_db_path(app_data_dir: &Path) -> PathBuf {
    app_data_dir.join("workbench.db")
}

/// 在 Tauri setup() 中调用：建目录 + 打开文件 DB + 建表。
pub fn init_db(app_data_dir: &Path) -> Result<Db, rusqlite::Error> {
    std::fs::create_dir_all(app_data_dir).ok();
    let db_path = get_db_path(app_data_dir);
    let conn = Connection::open(db_path)?;
    init_db_with_conn(&conn)?;
    Ok(Db::from_conn(conn))
}

/// 在已打开的连接上执行 schema 落库（生产文件 DB / 测试内存 DB 共用）。
pub fn init_db_with_conn(conn: &Connection) -> Result<(), rusqlite::Error> {
    conn.execute_batch(SCHEMA_SQL)?;
    Ok(())
}

// ============================================================================
// 岗位 CRUD
// ============================================================================

impl Db {
    /// 插入或更新岗位：以 job_id 为主键幂等 upsert。
    /// 岗位更新时 updated_at 由调用方传入（来自云端 /sync/jobs 的游标字段）。
    pub fn upsert_job(&self, job: &Job) -> Result<(), rusqlite::Error> {
        let conn = self.lock();
        conn.execute(
            "INSERT INTO jobs (
                job_id, company, title, category, city, requirements, jd_text,
                apply_url, deadline, source, graduation_match, is_mt,
                llm_score, llm_reason, updated_at, deleted
            ) VALUES (
                ?1, ?2, ?3, ?4, ?5, ?6, ?7,
                ?8, ?9, ?10, ?11, ?12,
                ?13, ?14, ?15, ?16
            )
            ON CONFLICT(job_id) DO UPDATE SET
                company           = excluded.company,
                title             = excluded.title,
                category          = excluded.category,
                city              = excluded.city,
                requirements      = excluded.requirements,
                jd_text           = excluded.jd_text,
                apply_url         = excluded.apply_url,
                deadline          = excluded.deadline,
                source            = excluded.source,
                graduation_match  = excluded.graduation_match,
                is_mt             = excluded.is_mt,
                llm_score         = excluded.llm_score,
                llm_reason        = excluded.llm_reason,
                updated_at        = excluded.updated_at,
                deleted           = excluded.deleted",
            params![
                job.job_id,
                job.company,
                job.title,
                job.category,
                job.city,
                job.requirements,
                job.jd_text,
                job.apply_url,
                job.deadline,
                job.source,
                job.graduation_match,
                job.is_mt,
                job.llm_score,
                job.llm_reason,
                job.updated_at,
                job.deleted,
            ],
        )?;
        Ok(())
    }

    /// 分页 + 多条件筛选岗位列表，按 updated_at 倒序。
    /// 动态拼 WHERE 子句（rusqlite 没有原生QueryBuilder，手动拼 + params_from_iter）。
    pub fn get_jobs(
        &self,
        filter: &JobFilter,
        limit: i64,
        offset: i64,
    ) -> Result<Vec<Job>, rusqlite::Error> {
        let mut where_clauses: Vec<String> = Vec::new();
        let mut binds: Vec<Box<dyn rusqlite::ToSql>> = Vec::new();

        if filter.not_deleted {
            where_clauses.push("deleted = 0".to_string());
        }
        if let Some(city) = &filter.city {
            where_clauses.push("city = ?".to_string());
            binds.push(Box::new(city.clone()));
        }
        if let Some(category) = &filter.category {
            where_clauses.push("category = ?".to_string());
            binds.push(Box::new(category.clone()));
        }
        if let Some(company) = &filter.company {
            where_clauses.push("company = ?".to_string());
            binds.push(Box::new(company.clone()));
        }
        if let Some(gm) = filter.graduation_match {
            where_clauses.push("graduation_match = ?".to_string());
            binds.push(Box::new(if gm { 1i64 } else { 0i64 }));
        }
        if let Some(mt) = filter.is_mt {
            where_clauses.push("is_mt = ?".to_string());
            binds.push(Box::new(if mt { 1i64 } else { 0i64 }));
        }
        if let Some(min) = filter.min_score {
            where_clauses.push("llm_score >= ?".to_string());
            binds.push(Box::new(min));
        }
        if let Some(search) = &filter.search {
            where_clauses.push("(company LIKE ? OR title LIKE ? OR jd_text LIKE ?)".to_string());
            let like = format!("%{}%", search);
            binds.push(Box::new(like.clone()));
            binds.push(Box::new(like.clone()));
            binds.push(Box::new(like));
        }

        let where_sql = if where_clauses.is_empty() {
            String::new()
        } else {
            format!("WHERE {}", where_clauses.join(" AND "))
        };

        let sql = format!(
            "SELECT job_id, company, title, category, city, requirements, jd_text,
                    apply_url, deadline, source, graduation_match, is_mt,
                    llm_score, llm_reason, updated_at, deleted
             FROM jobs {}
             ORDER BY updated_at DESC NULLS LAST
             LIMIT ? OFFSET ?",
            where_sql
        );

        let conn = self.lock();
        let mut stmt = conn.prepare(&sql)?;
        let bind_refs: Vec<&dyn rusqlite::ToSql> = binds.iter().map(|b| b.as_ref()).collect();
        let mut bind_all: Vec<&dyn rusqlite::ToSql> = bind_refs;
        bind_all.push(&limit);
        bind_all.push(&offset);

        let rows = stmt.query_map(bind_all.as_slice(), |row| {
            Ok(Job {
                job_id: row.get(0)?,
                company: row.get(1)?,
                title: row.get(2)?,
                category: row.get(3)?,
                city: row.get(4)?,
                requirements: row.get(5)?,
                jd_text: row.get(6)?,
                apply_url: row.get(7)?,
                deadline: row.get(8)?,
                source: row.get(9)?,
                graduation_match: row.get(10)?,
                is_mt: row.get(11)?,
                llm_score: row.get(12)?,
                llm_reason: row.get(13)?,
                updated_at: row.get(14)?,
                deleted: row.get(15)?,
            })
        })?;
        rows.collect::<Result<Vec<_>, _>>()
    }

    /// 取单个岗位（按 job_id）。M1 暂未挂为 Tauri command，留给 sync 流程与详情页使用。
    #[allow(dead_code)]
    pub fn get_job_by_id(&self, job_id: &str) -> Result<Option<Job>, rusqlite::Error> {
        let conn = self.lock();
        let mut stmt = conn.prepare(
            "SELECT job_id, company, title, category, city, requirements, jd_text,
                    apply_url, deadline, source, graduation_match, is_mt,
                    llm_score, llm_reason, updated_at, deleted
             FROM jobs WHERE job_id = ?",
        )?;
        let job = stmt
            .query_row(params![job_id], |row| {
                Ok(Job {
                    job_id: row.get(0)?,
                    company: row.get(1)?,
                    title: row.get(2)?,
                    category: row.get(3)?,
                    city: row.get(4)?,
                    requirements: row.get(5)?,
                    jd_text: row.get(6)?,
                    apply_url: row.get(7)?,
                    deadline: row.get(8)?,
                    source: row.get(9)?,
                    graduation_match: row.get(10)?,
                    is_mt: row.get(11)?,
                    llm_score: row.get(12)?,
                    llm_reason: row.get(13)?,
                    updated_at: row.get(14)?,
                    deleted: row.get(15)?,
                })
            })
            .optional()?;
        Ok(job)
    }

    /// 本地岗位统计：总数（仅未删）+ 最近更新时间（含软删行，反映最近一次同步游标）。
    /// 与云端 /sync/jobs/stats 字段对齐：total 用于 UI "在招岗位 N 条"，updated_at 用于 "数据停止于 X" 提示。
    pub fn get_job_stats(&self) -> Result<JobStats, rusqlite::Error> {
        let conn = self.lock();
        let total: i64 =
            conn.query_row("SELECT COUNT(*) FROM jobs WHERE deleted = 0", [], |row| {
                row.get(0)
            })?;
        let updated_at: Option<String> =
            conn.query_row("SELECT MAX(updated_at) FROM jobs", [], |row| row.get(0))?;
        Ok(JobStats { total, updated_at })
    }

    /// 评分回写：本地算法（scorer sidecar）算完后批量更新。
    pub fn update_job_score(
        &self,
        job_id: &str,
        score: f64,
        reason: &str,
    ) -> Result<(), rusqlite::Error> {
        let conn = self.lock();
        conn.execute(
            "UPDATE jobs SET llm_score = ?, llm_reason = ? WHERE job_id = ?",
            params![score, reason, job_id],
        )?;
        Ok(())
    }

    /// 取已评分岗位（llm_score IS NOT NULL），按分数倒序。
    /// 可选分数区间过滤：min_score 闭下界，max_score 开上界（与 T13 推荐分桶对齐：
    /// 强烈推荐 = [75, +∞)；推荐 = [55, 75)；可申请 = [35, 55)；不建议 = [0, 35)）。
    /// 单方法查询避免前端拉全量再筛（35K 行下不友好），分页 limit/offset 由调用方拼。
    pub fn get_scored_jobs(
        &self,
        min_score: Option<f64>,
        max_score: Option<f64>,
        limit: i64,
        offset: i64,
    ) -> Result<Vec<Job>, rusqlite::Error> {
        let mut where_clauses: Vec<&'static str> = vec!["llm_score IS NOT NULL", "deleted = 0"];
        let mut binds: Vec<Box<dyn rusqlite::ToSql>> = Vec::new();
        if let Some(min) = min_score {
            where_clauses.push("llm_score >= ?");
            binds.push(Box::new(min));
        }
        if let Some(max) = max_score {
            where_clauses.push("llm_score < ?");
            binds.push(Box::new(max));
        }
        let where_sql = where_clauses.join(" AND ");
        let sql = format!(
            "SELECT job_id, company, title, category, city, requirements, jd_text,
                    apply_url, deadline, source, graduation_match, is_mt,
                    llm_score, llm_reason, updated_at, deleted
             FROM jobs WHERE {where_sql}
             ORDER BY llm_score DESC
             LIMIT ? OFFSET ?"
        );
        let conn = self.lock();
        let mut stmt = conn.prepare(&sql)?;
        let bind_refs: Vec<&dyn rusqlite::ToSql> = binds.iter().map(|b| b.as_ref()).collect();
        let mut bind_all: Vec<&dyn rusqlite::ToSql> = bind_refs;
        bind_all.push(&limit);
        bind_all.push(&offset);
        let rows = stmt.query_map(bind_all.as_slice(), |row| {
            Ok(Job {
                job_id: row.get(0)?,
                company: row.get(1)?,
                title: row.get(2)?,
                category: row.get(3)?,
                city: row.get(4)?,
                requirements: row.get(5)?,
                jd_text: row.get(6)?,
                apply_url: row.get(7)?,
                deadline: row.get(8)?,
                source: row.get(9)?,
                graduation_match: row.get(10)?,
                is_mt: row.get(11)?,
                llm_score: row.get(12)?,
                llm_reason: row.get(13)?,
                updated_at: row.get(14)?,
                deleted: row.get(15)?,
            })
        })?;
        rows.collect::<Result<Vec<_>, _>>()
    }

    /// 评分分桶统计（T13 推荐视图 Tab 数量）。
    /// 对齐 scorer.py 的评分等级：≥75 强烈推荐 / ≥55 推荐 / ≥35 可申请 / <35 不建议。
    /// 未评分（llm_score IS NULL）单列 `unscored`，方便前端区分"刚同步完还没评"vs"评分过低"。
    pub fn get_score_summary(&self) -> Result<ScoreSummary, rusqlite::Error> {
        let conn = self.lock();
        let total: i64 = conn.query_row(
            "SELECT COUNT(*) FROM jobs WHERE deleted = 0",
            [],
            |row| row.get(0),
        )?;
        let scored: i64 = conn.query_row(
            "SELECT COUNT(*) FROM jobs WHERE deleted = 0 AND llm_score IS NOT NULL",
            [],
            |row| row.get(0),
        )?;
        let strong_recommend: i64 = conn.query_row(
            "SELECT COUNT(*) FROM jobs WHERE deleted = 0 AND llm_score >= 75.0",
            [],
            |row| row.get(0),
        )?;
        let recommend: i64 = conn.query_row(
            "SELECT COUNT(*) FROM jobs WHERE deleted = 0 AND llm_score >= 55.0 AND llm_score < 75.0",
            [],
            |row| row.get(0),
        )?;
        let can_apply: i64 = conn.query_row(
            "SELECT COUNT(*) FROM jobs WHERE deleted = 0 AND llm_score >= 35.0 AND llm_score < 55.0",
            [],
            |row| row.get(0),
        )?;
        let not_recommended: i64 = conn.query_row(
            "SELECT COUNT(*) FROM jobs WHERE deleted = 0 AND llm_score < 35.0",
            [],
            |row| row.get(0),
        )?;
        let unscored: i64 = conn.query_row(
            "SELECT COUNT(*) FROM jobs WHERE deleted = 0 AND llm_score IS NULL",
            [],
            |row| row.get(0),
        )?;
        Ok(ScoreSummary {
            total,
            scored,
            strong_recommend,
            recommend,
            can_apply,
            not_recommended,
            unscored,
        })
    }
}

/// 评分分桶统计返回结构（Tauri command get_score_summary 直接序列化回前端）。
/// 对齐前端 `src/api/scoring.ts::ScoreSummary` interface。
#[derive(Debug, Clone, serde::Serialize)]
pub struct ScoreSummary {
    pub total: i64,
    pub scored: i64,
    pub strong_recommend: i64,
    pub recommend: i64,
    pub can_apply: i64,
    pub not_recommended: i64,
    pub unscored: i64,
}

// ============================================================================
// 用户配置 CRUD
// ============================================================================

impl Db {
    /// 单行记录：返回最近一条 user_config（MVP 单用户）；空表返回 Ok(None)。
    pub fn get_user_config(&self) -> Result<Option<UserConfig>, rusqlite::Error> {
        let conn = self.lock();
        let mut stmt = conn.prepare(
            "SELECT user_id, email, token_encrypted, subscription_plan,
                    subscription_expires_at, llm_quota_today, llm_used_today, last_sync_at
             FROM user_config LIMIT 1",
        )?;
        let cfg = stmt
            .query_row([], |row| {
                Ok(UserConfig {
                    user_id: row.get(0)?,
                    email: row.get(1)?,
                    token_encrypted: row.get(2)?,
                    subscription_plan: row.get(3)?,
                    subscription_expires_at: row.get(4)?,
                    llm_quota_today: row.get(5)?,
                    llm_used_today: row.get(6)?,
                    last_sync_at: row.get(7)?,
                })
            })
            .optional()?;
        Ok(cfg)
    }

    /// upsert 单行用户配置：单用户场景以 user_id 为主键覆盖写。
    pub fn save_user_config(&self, config: &UserConfig) -> Result<(), rusqlite::Error> {
        let conn = self.lock();
        conn.execute(
            "INSERT INTO user_config (
                user_id, email, token_encrypted, subscription_plan,
                subscription_expires_at, llm_quota_today, llm_used_today, last_sync_at
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)
            ON CONFLICT(user_id) DO UPDATE SET
                email                    = excluded.email,
                token_encrypted          = excluded.token_encrypted,
                subscription_plan        = excluded.subscription_plan,
                subscription_expires_at  = excluded.subscription_expires_at,
                llm_quota_today          = excluded.llm_quota_today,
                llm_used_today           = excluded.llm_used_today,
                last_sync_at             = excluded.last_sync_at",
            params![
                config.user_id,
                config.email,
                config.token_encrypted,
                config.subscription_plan,
                config.subscription_expires_at,
                config.llm_quota_today,
                config.llm_used_today,
                config.last_sync_at,
            ],
        )?;
        Ok(())
    }
}

// ============================================================================
// 简历 CRUD
// ============================================================================

impl Db {
    /// upsert 简历：以 resume_id 为主键。
    pub fn save_resume(&self, resume: &Resume) -> Result<(), rusqlite::Error> {
        let conn = self.lock();
        conn.execute(
            "INSERT INTO resumes (
                resume_id, file_path, raw_text, parsed_profile_json, created_at, is_active
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6)
            ON CONFLICT(resume_id) DO UPDATE SET
                file_path             = excluded.file_path,
                raw_text              = excluded.raw_text,
                parsed_profile_json   = excluded.parsed_profile_json,
                created_at            = excluded.created_at,
                is_active             = excluded.is_active",
            params![
                resume.resume_id,
                resume.file_path,
                resume.raw_text,
                resume.parsed_profile_json,
                resume.created_at,
                resume.is_active,
            ],
        )?;
        Ok(())
    }

    /// 取当前生效简历（is_active = 1）；无生效简历返回 Ok(None)。
    pub fn get_active_resume(&self) -> Result<Option<Resume>, rusqlite::Error> {
        let conn = self.lock();
        let resume = conn
            .query_row(
                "SELECT resume_id, file_path, raw_text, parsed_profile_json, created_at, is_active
                 FROM resumes WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1",
                [],
                |row| {
                    Ok(Resume {
                        resume_id: row.get(0)?,
                        file_path: row.get(1)?,
                        raw_text: row.get(2)?,
                        parsed_profile_json: row.get(3)?,
                        created_at: row.get(4)?,
                        is_active: row.get(5)?,
                    })
                },
            )
            .optional()?;
        Ok(resume)
    }
}

// ============================================================================
// 投递记录 CRUD
// ============================================================================

impl Db {
    /// upsert 投递记录：以 app_id 为主键。
    pub fn upsert_application(&self, app: &Application) -> Result<(), rusqlite::Error> {
        let conn = self.lock();
        conn.execute(
            "INSERT INTO applications (
                app_id, job_id, status, applied_at, updated_at, notes, source
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
            ON CONFLICT(app_id) DO UPDATE SET
                job_id     = excluded.job_id,
                status     = excluded.status,
                applied_at = excluded.applied_at,
                updated_at = excluded.updated_at,
                notes      = excluded.notes,
                source     = excluded.source",
            params![
                app.app_id,
                app.job_id,
                app.status,
                app.applied_at,
                app.updated_at,
                app.notes,
                app.source,
            ],
        )?;
        Ok(())
    }

    /// 查询投递记录，可按 status 过滤（draft|applied|test|interview|offer|rejected）。
    pub fn get_applications(
        &self,
        status_filter: Option<&str>,
    ) -> Result<Vec<Application>, rusqlite::Error> {
        let conn = self.lock();
        let mut stmt;
        let rows = if let Some(status) = status_filter {
            stmt = conn.prepare(
                "SELECT app_id, job_id, status, applied_at, updated_at, notes, source
                 FROM applications WHERE status = ? ORDER BY COALESCE(updated_at, applied_at) DESC",
            )?;
            let bind: Vec<&dyn rusqlite::ToSql> = vec![&status];
            stmt.query_map(bind.as_slice(), map_application_row)?
        } else {
            stmt = conn.prepare(
                "SELECT app_id, job_id, status, applied_at, updated_at, notes, source
                 FROM applications ORDER BY COALESCE(updated_at, applied_at) DESC",
            )?;
            stmt.query_map([], map_application_row)?
        };
        rows.collect::<Result<Vec<_>, _>>()
    }
}

fn map_application_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<Application> {
    Ok(Application {
        app_id: row.get(0)?,
        job_id: row.get(1)?,
        status: row.get(2)?,
        applied_at: row.get(3)?,
        updated_at: row.get(4)?,
        notes: row.get(5)?,
        source: row.get(6)?,
    })
}

// ============================================================================
// 测试：内存 SQLite 验证 CRUD / 筛选 / upsert 幂等
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn open_test_db() -> Db {
        let conn = Connection::open_in_memory().expect("open in-memory db");
        init_db_with_conn(&conn).expect("init schema");
        Db::from_conn(conn)
    }

    fn make_job(job_id: &str, company: &str, city: &str, score: Option<f64>, updated: &str) -> Job {
        Job {
            job_id: job_id.to_string(),
            company: company.to_string(),
            title: format!("{}岗位", company),
            category: Some("技术".to_string()),
            city: Some(city.to_string()),
            requirements: Some("本科".to_string()),
            jd_text: Some(format!("JD of {}", company)),
            apply_url: None,
            deadline: None,
            source: Some("feishu".to_string()),
            graduation_match: 1,
            is_mt: 0,
            llm_score: score,
            llm_reason: score.map(|_| "matched".to_string()),
            updated_at: Some(updated.to_string()),
            deleted: 0,
        }
    }

    #[test]
    fn test_init_creates_all_tables() {
        let conn = Connection::open_in_memory().unwrap();
        init_db_with_conn(&conn).unwrap();
        for table in [
            "user_config",
            "jobs",
            "resumes",
            "applications",
            "email_accounts",
            "emails",
            "schedules",
        ] {
            let count: i64 = conn
                .query_row(
                    &format!(
                        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='{}'",
                        table
                    ),
                    [],
                    |row| row.get(0),
                )
                .unwrap();
            assert_eq!(count, 1, "table {} should exist", table);
        }
    }

    #[test]
    fn test_init_db_is_idempotent() {
        let conn = Connection::open_in_memory().unwrap();
        init_db_with_conn(&conn).unwrap();
        // 再调一次不应报错（CREATE TABLE IF NOT EXISTS）
        init_db_with_conn(&conn).unwrap();
    }

    #[test]
    fn test_upsert_job_is_idempotent() {
        let db = open_test_db();
        let mut job = make_job("j-1", "ACME", "上海", None, "2026-10-01 10:00:00");
        db.upsert_job(&job).unwrap();

        let got = db.get_job_by_id("j-1").unwrap().unwrap();
        assert_eq!(got.company, "ACME");
        assert_eq!(got.city.as_deref(), Some("上海"));

        // 同一 job_id 覆盖写：city 改北京、score 写 80
        job.city = Some("北京".to_string());
        job.llm_score = Some(80.0);
        db.upsert_job(&job).unwrap();

        let got2 = db.get_job_by_id("j-1").unwrap().unwrap();
        assert_eq!(got2.city.as_deref(), Some("北京"));
        assert_eq!(got2.llm_score, Some(80.0));

        // 总数仍为 1（不是 INSERT 新行）
        let stats = db.get_job_stats().unwrap();
        assert_eq!(stats.total, 1);
    }

    #[test]
    fn test_get_jobs_filter_city_and_mt() {
        let db = open_test_db();
        // j-1: 上海 管培；j-2: 上海 普通岗；j-3: 北京 管培
        let mut j1 = make_job("j-1", "A", "上海", None, "2026-10-01 10:00:00");
        j1.is_mt = 1;
        let j2 = make_job("j-2", "B", "上海", None, "2026-10-02 10:00:00");
        let mut j3 = make_job("j-3", "C", "北京", None, "2026-10-03 10:00:00");
        j3.is_mt = 1;
        db.upsert_job(&j1).unwrap();
        db.upsert_job(&j2).unwrap();
        db.upsert_job(&j3).unwrap();

        // 仅上海 → 2 条（按 updated_at 倒序：j-2 在前）
        let filter = JobFilter {
            city: Some("上海".to_string()),
            ..Default::default()
        };
        let jobs = db.get_jobs(&filter, 50, 0).unwrap();
        assert_eq!(jobs.len(), 2);
        assert_eq!(jobs[0].job_id, "j-2");

        // 上海 + 管培 → 1 条（j-1）
        let filter = JobFilter {
            city: Some("上海".to_string()),
            is_mt: Some(true),
            ..Default::default()
        };
        let jobs = db.get_jobs(&filter, 50, 0).unwrap();
        assert_eq!(jobs.len(), 1);
        assert_eq!(jobs[0].job_id, "j-1");
    }

    #[test]
    fn test_get_jobs_search_and_min_score() {
        let db = open_test_db();
        let j1 = make_job("j-1", "字节跳动", "上海", Some(80.0), "2026-10-01 10:00:00");
        let j2 = make_job("j-2", "美团", "北京", Some(50.0), "2026-10-02 10:00:00");
        let j3 = make_job("j-3", "字节教育", "杭州", Some(30.0), "2026-10-03 10:00:00");
        db.upsert_job(&j1).unwrap();
        db.upsert_job(&j2).unwrap();
        db.upsert_job(&j3).unwrap();

        // 搜索"字节" → 2 条
        let filter = JobFilter {
            search: Some("字节".to_string()),
            ..Default::default()
        };
        let jobs = db.get_jobs(&filter, 50, 0).unwrap();
        assert_eq!(jobs.len(), 2);

        // 评分下限 50 → 2 条（80 与 50；30 不入）
        let filter = JobFilter {
            min_score: Some(50.0),
            ..Default::default()
        };
        let jobs = db.get_jobs(&filter, 50, 0).unwrap();
        assert_eq!(jobs.len(), 2);
        assert!(jobs.iter().all(|j| j.llm_score.unwrap() >= 50.0));
    }

    #[test]
    fn test_get_jobs_pagination() {
        let db = open_test_db();
        for i in 0..15 {
            let j = make_job(
                &format!("j-{:02}", i),
                &format!("C{}", i),
                "上海",
                None,
                &format!("2026-10-{:02} 10:00:00", i + 1),
            );
            db.upsert_job(&j).unwrap();
        }
        // page 1：limit=10 offset=0
        let p1 = db.get_jobs(&JobFilter::default(), 10, 0).unwrap();
        assert_eq!(p1.len(), 10);
        // page 2：limit=10 offset=10
        let p2 = db.get_jobs(&JobFilter::default(), 10, 10).unwrap();
        assert_eq!(p2.len(), 5);
        // 倒序：page1 第一个应该是最新 updated_at = 2026-10-15
        assert_eq!(p1[0].job_id, "j-14");
    }

    #[test]
    fn test_get_job_stats() {
        let db = open_test_db();
        db.upsert_job(&make_job("j-1", "A", "上海", None, "2026-10-01 10:00:00"))
            .unwrap();
        db.upsert_job(&make_job("j-2", "B", "上海", None, "2026-10-02 10:00:00"))
            .unwrap();
        // 软删一条
        let mut j3 = make_job("j-3", "C", "北京", None, "2026-10-03 10:00:00");
        j3.deleted = 1;
        db.upsert_job(&j3).unwrap();

        let stats = db.get_job_stats().unwrap();
        assert_eq!(stats.total, 2); // j-3 软删不计入
        assert_eq!(stats.updated_at.as_deref(), Some("2026-10-03 10:00:00"));
    }

    #[test]
    fn test_update_job_score() {
        let db = open_test_db();
        db.upsert_job(&make_job("j-1", "A", "上海", None, "2026-10-01 10:00:00"))
            .unwrap();
        db.update_job_score("j-1", 88.5, "硬技能+方向命中").unwrap();
        let got = db.get_job_by_id("j-1").unwrap().unwrap();
        assert_eq!(got.llm_score, Some(88.5));
        assert_eq!(got.llm_reason.as_deref(), Some("硬技能+方向命中"));
    }

    #[test]
    fn test_user_config_crud() {
        let db = open_test_db();
        // 空表 → None
        assert!(db.get_user_config().unwrap().is_none());

        let cfg = UserConfig {
            user_id: "u-1".to_string(),
            email: "u1@example.com".to_string(),
            token_encrypted: Some("enc-token".to_string()),
            subscription_plan: Some("pro".to_string()),
            subscription_expires_at: Some("2026-12-31".to_string()),
            llm_quota_today: 5,
            llm_used_today: 1,
            last_sync_at: Some("2026-10-01 10:00:00".to_string()),
        };
        db.save_user_config(&cfg).unwrap();
        let got = db.get_user_config().unwrap().unwrap();
        assert_eq!(got.email, "u1@example.com");
        assert_eq!(got.llm_quota_today, 5);

        // upsert：plan 升 max，used_today 加 1
        let mut cfg2 = cfg.clone();
        cfg2.subscription_plan = Some("max".to_string());
        cfg2.llm_used_today = 2;
        db.save_user_config(&cfg2).unwrap();
        let got2 = db.get_user_config().unwrap().unwrap();
        assert_eq!(got2.subscription_plan.as_deref(), Some("max"));
        assert_eq!(got2.llm_used_today, 2);
    }

    #[test]
    fn test_resume_crud() {
        let db = open_test_db();
        let r1 = Resume {
            resume_id: "r-1".to_string(),
            file_path: "/tmp/a.pdf".to_string(),
            raw_text: Some("resume text".to_string()),
            parsed_profile_json: Some(r#"{"keywords":[],"fit_directions":[]}"#.to_string()),
            created_at: "2026-10-01 10:00:00".to_string(),
            is_active: 1,
        };
        db.save_resume(&r1).unwrap();
        let got = db.get_active_resume().unwrap().unwrap();
        assert_eq!(got.resume_id, "r-1");

        // 再存一份非 active，确认 get_active_resume 仍返回 r-1
        let r2 = Resume {
            resume_id: "r-2".to_string(),
            file_path: "/tmp/b.pdf".to_string(),
            raw_text: None,
            parsed_profile_json: None,
            created_at: "2026-10-02 10:00:00".to_string(),
            is_active: 0,
        };
        db.save_resume(&r2).unwrap();
        let got2 = db.get_active_resume().unwrap().unwrap();
        assert_eq!(got2.resume_id, "r-1");

        // r-2 切换为 active → 返回 r-2（按 created_at DESC 取最新 active）
        let mut r2b = r2.clone();
        r2b.is_active = 1;
        db.save_resume(&r2b).unwrap();
        let got3 = db.get_active_resume().unwrap().unwrap();
        assert_eq!(got3.resume_id, "r-2");
    }

    #[test]
    fn test_application_crud_and_status_filter() {
        let db = open_test_db();
        // 先放一个岗位（FK 约束 applications.job_id → jobs.job_id）
        db.upsert_job(&make_job("j-1", "A", "上海", None, "2026-10-01 10:00:00"))
            .unwrap();

        let a1 = Application {
            app_id: "a-1".to_string(),
            job_id: "j-1".to_string(),
            status: "draft".to_string(),
            applied_at: None,
            updated_at: Some("2026-10-01 11:00:00".to_string()),
            notes: None,
            source: Some("manual".to_string()),
        };
        let a2 = Application {
            app_id: "a-2".to_string(),
            job_id: "j-1".to_string(),
            status: "interview".to_string(),
            applied_at: Some("2026-10-02 11:00:00".to_string()),
            updated_at: Some("2026-10-03 11:00:00".to_string()),
            notes: Some("一面".to_string()),
            source: Some("manual".to_string()),
        };
        db.upsert_application(&a1).unwrap();
        db.upsert_application(&a2).unwrap();

        let all = db.get_applications(None).unwrap();
        assert_eq!(all.len(), 2);

        let interviews = db.get_applications(Some("interview")).unwrap();
        assert_eq!(interviews.len(), 1);
        assert_eq!(interviews[0].app_id, "a-2");

        // upsert：a-1 状态推进到 applied
        let mut a1b = a1.clone();
        a1b.status = "applied".to_string();
        db.upsert_application(&a1b).unwrap();
        let drafts = db.get_applications(Some("draft")).unwrap();
        assert!(drafts.is_empty());
        let applied = db.get_applications(Some("applied")).unwrap();
        assert_eq!(applied.len(), 1);
    }

    #[test]
    fn test_get_job_by_id_missing_returns_ok_none() {
        let db = open_test_db();
        // 不存在的 job_id：返回 Ok(None)，便于上层用 ? + match 链式处理
        let res = db.get_job_by_id("does-not-exist").unwrap();
        assert!(res.is_none());
    }
}
