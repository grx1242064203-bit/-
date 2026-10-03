//! 岗位同步服务：从云端 `/api/v1/sync/jobs` 增量拉取岗位写入本地 SQLite。
//!
//! 设计要点
//! --------
//! - `SyncService` 持有 `reqwest::Client`（连接池复用 + 30s 超时），跨命令注册为 Tauri State。
//! - `sync_jobs` 循环分页：`?since=&limit=500&cursor=`，每页 `.json()` 反序列化到 `SyncJobsResponse`，
//!   逐条 `RemoteJob → Job → Db::upsert_job` 落库，`next_cursor` 为 `None` 时停止。
//! - 网络失败立即返回错误；已 upsert 的数据保留（`ON CONFLICT` 幂等可重放，下次 `since` 从上次 `last_updated_at` 继续）。
//! - `compare_with_local` 用本地 `get_job_stats` 与远端 stats 对比，驱动 UI"是否需要同步"提示。
//! - token + api_base_url 由调用方（Tauri command）传入，前端从 authStore + env 读取——避免在 Rust 侧
//!   重复实现 token 解密（T6/T7 的 token 加密流程尚未落地，由后续任务统一接入 keychain）。

use std::time::Duration;

use serde::{Deserialize, Serialize};

use crate::db::Db;
use crate::models::Job;

/// 每页拉取条数：与云端 `DEFAULT_PAGE_SIZE` 对齐（500 条/页）。
const PAGE_SIZE: i64 = 500;
/// 分页安全上限：200 页 × 500 = 10 万条，超过则视为远端游标异常，主动跳出避免死循环。
const MAX_PAGES: usize = 200;

/// 远端 `/sync/jobs` 返回的岗位（13 字段，对齐云端 `JOB_FIELDS` 常量）。
/// 与本地 `Job` 区别：无 `llm_score` / `llm_reason` / `deleted`（本地独有，
/// 由评分 sidecar 与软删流程写入；同步时强制 `deleted=0`、`llm_*` 留空——
/// 已有评分会被 `ON CONFLICT DO UPDATE SET llm_score = excluded.llm_score` 覆盖为 None，
/// 评分需在同步后由 sidecar 重算；M1 阶段同步不触发改评分，先保留这一行为契约）。
#[derive(Debug, Deserialize)]
struct RemoteJob {
    job_id: String,
    company: String,
    title: String,
    category: Option<String>,
    city: Option<String>,
    requirements: Option<String>,
    jd_text: Option<String>,
    apply_url: Option<String>,
    deadline: Option<String>,
    source: Option<String>,
    graduation_match: i64,
    is_mt: i64,
    updated_at: Option<String>,
}

impl From<RemoteJob> for Job {
    fn from(r: RemoteJob) -> Self {
        Job {
            job_id: r.job_id,
            company: r.company,
            title: r.title,
            category: r.category,
            city: r.city,
            requirements: r.requirements,
            jd_text: r.jd_text,
            apply_url: r.apply_url,
            deadline: r.deadline,
            source: r.source,
            graduation_match: r.graduation_match,
            is_mt: r.is_mt,
            llm_score: None,
            llm_reason: None,
            updated_at: r.updated_at,
            deleted: 0,
        }
    }
}

/// `/sync/jobs` 响应：岗位列表 + 下一页游标（`None` 表示最后一页）。
#[derive(Debug, Deserialize)]
struct SyncJobsResponse {
    jobs: Vec<RemoteJob>,
    next_cursor: Option<String>,
}

/// `/sync/stats` 响应：总数 + 最新更新时间。
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct RemoteStats {
    pub total: i64,
    pub updated_at: Option<String>,
}

/// 同步结果：本次同步写入条数 + 本次见到的最新 `updated_at`（前端可作为下次 `since` 增量起点，
/// 亦可写回 `user_config.last_sync_at`）。
#[derive(Debug, Serialize)]
pub struct SyncResult {
    pub synced_count: i64,
    pub last_updated_at: Option<String>,
}

/// 本地 vs 远端对比：驱动 UI"是否需要同步"提示。
#[derive(Debug, Serialize)]
pub struct SyncStatus {
    pub need_sync: bool,
    pub local_count: i64,
    pub remote_count: Option<i64>,
    pub last_sync: Option<String>,
}

/// SyncService 错误：网络 / HTTP 状态 / 反序列化 / 数据库四类合一，前端按 `to_string()` 提示。
/// 不直接 `impl From<rusqlite::Error>`：避免暴露 rusqlite 类型给上层，统一收敛为 `db: {e}` 文本。
#[derive(Debug)]
pub struct SyncError(pub String);

impl std::fmt::Display for SyncError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for SyncError {}

impl From<reqwest::Error> for SyncError {
    fn from(e: reqwest::Error) -> Self {
        SyncError(format!("network: {e}"))
    }
}

impl From<serde_json::Error> for SyncError {
    fn from(e: serde_json::Error) -> Self {
        SyncError(format!("deserialize: {e}"))
    }
}

/// 同步服务：持有 `reqwest::Client` 跨命令复用连接池。
pub struct SyncService {
    client: reqwest::Client,
}

impl Default for SyncService {
    fn default() -> Self {
        Self::new()
    }
}

impl SyncService {
    /// 构建 client：30s 超时（每页 ≤1000 条，单次拉取通常 < 1s；30s 容忍弱网）。
    /// 失败仅可能因 TLS 后端初始化异常——桌面端启动期失败直接 panic 可接受（与 db::init_db 同等级处理）。
    pub fn new() -> Self {
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .expect("failed to build reqwest client");
        Self { client }
    }

    /// 增量同步岗位：循环分页拉取并 upsert 到本地 SQLite。
    ///
    /// - `since` 为 `None` 或空串时从头拉取（全量）；非空时按 `updated_at > since` 增量拉取。
    /// - 失败立即返回错误；已 upsert 的数据保留（幂等可重放，下次 `since` 取上次 `last_updated_at` 继续）。
    /// - `last_updated_at` 取本批所有 jobs 的 `max(updated_at)`，作为下次增量起点；空批保持 `since` 不变。
    /// - token 由调用方传入（前端从 authStore 读，invoke 时附在参数里——避免 Rust 侧重复实现 token 解密）。
    pub async fn sync_jobs(
        &self,
        db: &Db,
        api_base_url: &str,
        token: &str,
        since: Option<String>,
    ) -> Result<SyncResult, SyncError> {
        let base = api_base_url.trim_end_matches('/');
        let since_query = since.clone().unwrap_or_default();
        let mut cursor: Option<String> = None;
        let mut synced_count: i64 = 0;
        // last_updated_at 初始取 since：空批（远端无新数据）时保持不变，下次仍以同一 since 拉取。
        let mut last_updated_at = since;

        for _ in 0..MAX_PAGES {
            let mut params: Vec<(&str, String)> = vec![
                ("since", since_query.clone()),
                ("limit", PAGE_SIZE.to_string()),
            ];
            if let Some(c) = &cursor {
                params.push(("cursor", c.clone()));
            }

            let resp = self
                .client
                .get(format!("{base}/api/v1/sync/jobs"))
                .bearer_auth(token)
                .query(&params)
                .send()
                .await?;

            if !resp.status().is_success() {
                let status = resp.status();
                let body = resp.text().await.unwrap_or_default();
                // 401 时给前端更友好的提示，便于 authStore 触发跳登录。
                if status == reqwest::StatusCode::UNAUTHORIZED {
                    return Err(SyncError(
                        "unauthorized: token 已失效，请重新登录".to_string(),
                    ));
                }
                return Err(SyncError(format!("http {status}: {body}")));
            }

            let page: SyncJobsResponse = resp.json().await?;

            for rj in page.jobs {
                // 推进游标：取本批 max(updated_at)（与云端 (updated_at, job_id) 复合排序一致——
                // 云端按 updated_at 升序返回，但保留 max 兜底非严格排序）。
                if let Some(u) = &rj.updated_at {
                    last_updated_at = Some(match &last_updated_at {
                        Some(prev) if prev.as_str() >= u.as_str() => prev.clone(),
                        _ => u.clone(),
                    });
                }
                let job: Job = rj.into();
                db.upsert_job(&job)
                    .map_err(|e| SyncError(format!("db: {e}")))?;
                synced_count += 1;
            }

            match page.next_cursor {
                Some(next) => {
                    // 游标未推进视为远端异常：避免死循环（同一 cursor 反复返回）。
                    if cursor.as_deref() == Some(next.as_str()) {
                        log::warn!("sync_jobs: cursor not advancing, breaking early");
                        break;
                    }
                    cursor = Some(next);
                }
                None => break,
            }
        }

        Ok(SyncResult {
            synced_count,
            last_updated_at,
        })
    }

    /// 拉远端 `/sync/stats`：用于 `compare_with_local` 判断是否需要同步。
    pub async fn get_remote_stats(
        &self,
        api_base_url: &str,
        token: &str,
    ) -> Result<RemoteStats, SyncError> {
        let base = api_base_url.trim_end_matches('/');
        let resp = self
            .client
            .get(format!("{base}/api/v1/sync/stats"))
            .bearer_auth(token)
            .send()
            .await?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            if status == reqwest::StatusCode::UNAUTHORIZED {
                return Err(SyncError(
                    "unauthorized: token 已失效，请重新登录".to_string(),
                ));
            }
            return Err(SyncError(format!("http {status}: {body}")));
        }
        let stats: RemoteStats = resp.json().await?;
        Ok(stats)
    }

    /// 本地 vs 远端对比：本地 stats 与 `remote_stats.total` 比对。
    /// - `need_sync`：本地为空（首次同步）或本地 `MAX(updated_at)` < 远端 `updated_at` 时为 true。
    /// - `local_count`：本地未删岗位数（与 `get_job_stats.total` 同口径）。
    /// - `remote_count`：远端总数（拉取失败时调用方传 None，这里强制 Some——失败已在上游返回错误）。
    /// - `last_sync`：本地 `jobs` 表 `MAX(updated_at)`（反映最近一次同步游标）。
    ///
    /// ISO8601 字符串字典序比较与时间序一致（固定宽度、零填充）；本地与远端格式同源（云端 jobs.db），
    /// 故字典序比较等价于时间序比较。
    pub fn compare_with_local(
        &self,
        db: &Db,
        remote_stats: &RemoteStats,
    ) -> Result<SyncStatus, SyncError> {
        let local = db
            .get_job_stats()
            .map_err(|e| SyncError(format!("db: {e}")))?;
        let need_sync = local.total == 0
            || match (remote_stats.updated_at.as_ref(), local.updated_at.as_ref()) {
                (Some(remote), Some(loc)) => remote.as_str() > loc.as_str(),
                // 远端有 updated_at 而本地无（空表）→ 需同步；两边都无 → 兜底保守触发同步。
                _ => true,
            };
        Ok(SyncStatus {
            need_sync,
            local_count: local.total,
            remote_count: Some(remote_stats.total),
            last_sync: local.updated_at,
        })
    }
}

// ============================================================================
// 测试：内存 SQLite 验证 RemoteJob 映射 / compare_with_local 三态判定。
// 不测网络：reqwest 实际请求由集成测试覆盖，单元测试聚焦纯函数逻辑。
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::Connection;

    fn open_test_db() -> Db {
        let conn = Connection::open_in_memory().expect("open in-memory db");
        crate::db::init_db_with_conn(&conn).expect("init schema");
        Db::from_conn(conn)
    }

    #[test]
    fn test_remote_job_to_job_preserves_fields() {
        let rj = RemoteJob {
            job_id: "j-1".to_string(),
            company: "ACME".to_string(),
            title: "Eng".to_string(),
            category: Some("技术".to_string()),
            city: Some("上海".to_string()),
            requirements: Some("本科".to_string()),
            jd_text: Some("JD".to_string()),
            apply_url: Some("https://x".to_string()),
            deadline: None,
            source: Some("feishu".to_string()),
            graduation_match: 1,
            is_mt: 0,
            updated_at: Some("2026-10-01 10:00:00".to_string()),
        };
        let job: Job = rj.into();
        assert_eq!(job.job_id, "j-1");
        assert_eq!(job.company, "ACME");
        assert_eq!(job.graduation_match, 1);
        assert_eq!(job.is_mt, 0);
        assert_eq!(job.updated_at.as_deref(), Some("2026-10-01 10:00:00"));
        // 本地独有字段为默认
        assert!(job.llm_score.is_none());
        assert!(job.llm_reason.is_none());
        assert_eq!(job.deleted, 0);
    }

    #[test]
    fn test_sync_error_display_and_from() {
        let e = SyncError("network: timeout".to_string());
        assert_eq!(format!("{e}"), "network: timeout");

        // From<reqwest::Error>：构造一个 reqwest 错误比较麻烦，这里只验证 Display 链路。
        let e2: SyncError = serde_json::from_str::<String>("bad").unwrap_err().into();
        assert!(format!("{e2}").starts_with("deserialize:"));
    }

    #[test]
    fn test_compare_with_local_empty_local_needs_sync() {
        let db = open_test_db();
        let svc = SyncService::new();
        let remote = RemoteStats {
            total: 500,
            updated_at: Some("2026-10-03 10:00:00".to_string()),
        };
        let status = svc.compare_with_local(&db, &remote).unwrap();
        assert!(status.need_sync);
        assert_eq!(status.local_count, 0);
        assert_eq!(status.remote_count, Some(500));
        assert!(status.last_sync.is_none());
    }

    #[test]
    fn test_compare_with_local_up_to_date_no_sync() {
        let db = open_test_db();
        let job = Job {
            job_id: "j-1".to_string(),
            company: "A".to_string(),
            title: "T".to_string(),
            updated_at: Some("2026-10-03 10:00:00".to_string()),
            graduation_match: 1,
            is_mt: 0,
            deleted: 0,
            ..Default::default()
        };
        db.upsert_job(&job).unwrap();
        let svc = SyncService::new();
        let remote = RemoteStats {
            total: 1,
            updated_at: Some("2026-10-03 10:00:00".to_string()),
        };
        let status = svc.compare_with_local(&db, &remote).unwrap();
        assert!(!status.need_sync);
        assert_eq!(status.local_count, 1);
        assert_eq!(status.last_sync.as_deref(), Some("2026-10-03 10:00:00"));
    }

    #[test]
    fn test_compare_with_local_remote_newer_needs_sync() {
        let db = open_test_db();
        let job = Job {
            job_id: "j-1".to_string(),
            company: "A".to_string(),
            title: "T".to_string(),
            updated_at: Some("2026-10-01 10:00:00".to_string()),
            graduation_match: 1,
            is_mt: 0,
            deleted: 0,
            ..Default::default()
        };
        db.upsert_job(&job).unwrap();
        let svc = SyncService::new();
        let remote = RemoteStats {
            total: 1,
            updated_at: Some("2026-10-03 10:00:00".to_string()),
        };
        let status = svc.compare_with_local(&db, &remote).unwrap();
        assert!(status.need_sync);
        assert_eq!(status.local_count, 1);
    }

    #[test]
    fn test_compare_with_local_remote_no_updated_at_falls_back_to_sync() {
        // 远端 updated_at 为 None（极端情况）：保守触发同步，避免漏拉。
        let db = open_test_db();
        let job = Job {
            job_id: "j-1".to_string(),
            company: "A".to_string(),
            title: "T".to_string(),
            updated_at: Some("2026-10-01 10:00:00".to_string()),
            graduation_match: 1,
            is_mt: 0,
            deleted: 0,
            ..Default::default()
        };
        db.upsert_job(&job).unwrap();
        let svc = SyncService::new();
        let remote = RemoteStats {
            total: 1,
            updated_at: None,
        };
        let status = svc.compare_with_local(&db, &remote).unwrap();
        assert!(status.need_sync);
    }
}
