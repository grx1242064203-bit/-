//! 数据模型：所有 SQLite 表对应的 Rust struct（serde + rusqlite 友好）。
//!
//! 设计原则：
//! - 字段命名与 spec schema 严格对齐（snake_case，前端 invoke 收发 JSON 直接互通）。
//! - SQLite 没有真正的 BOOL / BIGINT，统一用 i64 承载 0/1 标记与计数；time 字段用 ISO8601 字符串（与 chrono 协同）。
//! - Option 表示可空列；NOT NULL 列用非 Option 类型，写入时 SQLite 隐式转换。
//! - 这些 struct 同时作为 Tauri command 的入参 / 返回值（#[derive(Serialize, Deserialize)]）。

use serde::{Deserialize, Serialize};

// ============================================================================
// 岗位（jobs 表）
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Job {
    pub job_id: String,
    pub company: String,
    pub title: String,
    pub category: Option<String>,
    pub city: Option<String>,
    pub requirements: Option<String>,
    pub jd_text: Option<String>,
    pub apply_url: Option<String>,
    pub deadline: Option<String>,
    pub source: Option<String>,
    pub graduation_match: i64,
    pub is_mt: i64,
    pub llm_score: Option<f64>,
    pub llm_reason: Option<String>,
    pub updated_at: Option<String>,
    pub deleted: i64,
}

impl Default for Job {
    fn default() -> Self {
        Self {
            job_id: String::new(),
            company: String::new(),
            title: String::new(),
            category: None,
            city: None,
            requirements: None,
            jd_text: None,
            apply_url: None,
            deadline: None,
            source: None,
            graduation_match: 1,
            is_mt: 0,
            llm_score: None,
            llm_reason: None,
            updated_at: None,
            deleted: 0,
        }
    }
}

// ============================================================================
// 岗位筛选 / 统计
// ============================================================================

/// 岗位列表筛选参数：所有字段可空，None 表示不筛选。
/// 前端 invoke('get_jobs', { filter: {...}, limit: 50, offset: 0 })。
#[derive(Debug, Clone, Deserialize, Default)]
pub struct JobFilter {
    pub city: Option<String>,
    pub graduation_match: Option<bool>,
    pub is_mt: Option<bool>,
    pub category: Option<String>,
    pub company: Option<String>,
    /// 关键词搜索：模糊匹配 company / title / jd_text（LIKE %search%）
    pub search: Option<String>,
    /// 仅看未删岗位（默认 true；同步任务软删时仍需查询 deleted=1 的记录可显式传 false）
    #[serde(default = "default_true")]
    pub not_deleted: bool,
    /// 评分下限：>0 时过滤 llm_score >= min_score
    pub min_score: Option<f64>,
}

fn default_true() -> bool {
    true
}

/// 岗位统计：与云端 /sync/jobs/stats 字段对齐，便于本地"数据停止于 X 日"提示。
#[derive(Debug, Clone, Serialize)]
pub struct JobStats {
    pub total: i64,
    pub updated_at: Option<String>,
}

// ============================================================================
// 用户配置（user_config 表）
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UserConfig {
    pub user_id: String,
    pub email: String,
    pub token_encrypted: Option<String>,
    pub subscription_plan: Option<String>,
    pub subscription_expires_at: Option<String>,
    pub llm_quota_today: i64,
    pub llm_used_today: i64,
    pub last_sync_at: Option<String>,
}

impl Default for UserConfig {
    fn default() -> Self {
        Self {
            user_id: String::new(),
            email: String::new(),
            token_encrypted: None,
            subscription_plan: None,
            subscription_expires_at: None,
            llm_quota_today: 0,
            llm_used_today: 0,
            last_sync_at: None,
        }
    }
}

// ============================================================================
// 简历（resumes 表）
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Resume {
    pub resume_id: String,
    pub file_path: String,
    pub raw_text: Option<String>,
    pub parsed_profile_json: Option<String>,
    pub created_at: String,
    /// 0/1（i64 承载，与 SQLite 布尔约定一致）
    pub is_active: i64,
}

// ============================================================================
// 投递记录（applications 表）
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Application {
    pub app_id: String,
    pub job_id: String,
    /// draft|applied|test|interview|offer|rejected
    pub status: String,
    pub applied_at: Option<String>,
    pub updated_at: Option<String>,
    pub notes: Option<String>,
    pub source: Option<String>,
}

impl Default for Application {
    fn default() -> Self {
        Self {
            app_id: String::new(),
            job_id: String::new(),
            status: "draft".to_string(),
            applied_at: None,
            updated_at: None,
            notes: None,
            source: None,
        }
    }
}
