//! Tauri 应用主体：注册 invoke handlers + fs 插件 + setup() 初始化 SQLite。
//!
//! Tauri 2 命令注册：`#[tauri::command]` 宏 + `tauri::generate_handler![...]`。
//! State 通过 `State<'_, Db>` 注入；Db 在 `setup()` 中由 `app.manage()` 注册。

mod db;
mod models;
mod sidecar;
mod sync;

use tauri::Manager;

use db::{Db, ScoreSummary};
use models::{Application, Job, JobFilter, JobStats, Resume, UserConfig};
use serde::Serialize;
use serde_json::Value;
use sidecar::SidecarManager;
use sync::{SyncResult, SyncService, SyncStatus};

// ============================================================================
// Tauri commands（前端 invoke('xxx', { ... }) 调用）
// ============================================================================

#[tauri::command]
fn get_jobs(
    db_state: tauri::State<'_, Db>,
    filter: Option<JobFilter>,
    limit: Option<i64>,
    offset: Option<i64>,
) -> Result<Vec<Job>, String> {
    let filter = filter.unwrap_or_default();
    db_state
        .get_jobs(
            &filter,
            limit.unwrap_or(50).clamp(1, 1000),
            offset.unwrap_or(0),
        )
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn get_job_stats(db_state: tauri::State<'_, Db>) -> Result<JobStats, String> {
    db_state.get_job_stats().map_err(|e| e.to_string())
}

#[tauri::command]
fn upsert_job(db_state: tauri::State<'_, Db>, job: Job) -> Result<(), String> {
    db_state.upsert_job(&job).map_err(|e| e.to_string())
}

#[tauri::command]
fn get_user_config(db_state: tauri::State<'_, Db>) -> Result<Option<UserConfig>, String> {
    db_state.get_user_config().map_err(|e| e.to_string())
}

#[tauri::command]
fn save_user_config(db_state: tauri::State<'_, Db>, config: UserConfig) -> Result<(), String> {
    db_state
        .save_user_config(&config)
        .map_err(|e| e.to_string())
}

// ============================================================================
// 评分回写 + 简历 + 投递（M1 仅暴露 upsert_job / 评分 / 简历查询，
// 投递与简历的写入路径后续任务接入；先暴露最小可用集，避免空跑命令）
// ============================================================================

#[tauri::command]
fn update_job_score(
    db_state: tauri::State<'_, Db>,
    job_id: String,
    score: f64,
    reason: String,
) -> Result<(), String> {
    db_state
        .update_job_score(&job_id, score, &reason)
        .map_err(|e| e.to_string())
}

// ============================================================================
// T13：评分 + 推荐视图
// - score_all_jobs: 读全部岗位 → 分批调 sidecar.score_batch(每批 500) → 回写 SQLite。
// - get_scored_jobs: 取已评分岗位（按 llm_score DESC，可按分数区间过滤）。
// - get_score_summary: 评分分桶统计（Tab 数量）。
// ============================================================================

/// score_all_jobs 返回结构（前端用于刷新 Tab 数量 + 显示完成提示）。
#[derive(Debug, Clone, Serialize)]
pub struct ScoreAllResult {
    pub total: i64,
    pub scored: i64,
    pub strong_count: i64,
    pub recommend_count: i64,
}

/// 已评分岗位筛选：min_score 闭下界 / max_score 开上界，与 db.rs::get_scored_jobs 对齐。
#[derive(Debug, Clone, serde::Deserialize, Default)]
pub struct ScoredJobsFilter {
    pub min_score: Option<f64>,
    pub max_score: Option<f64>,
}

/// 触发全量评分：读全部岗位（含未删）→ 分批调 sidecar → 回写 SQLite。
/// 每批 500 条，避免一次性传太多 JSON 给 sidecar（单批几秒级，35K 条总耗时约分钟级）。
/// profile 由前端从 resumeStore.parsedProfile 传入。
#[tauri::command]
fn score_all_jobs(
    db_state: tauri::State<'_, Db>,
    sidecar_state: tauri::State<'_, SidecarManager>,
    profile: Value,
) -> Result<ScoreAllResult, String> {
    let db = db_state.inner();
    // 全量拉取（不限制 deleted=0，避免软删记录不评分导致下次重新进入评分流程）。
    let filter = JobFilter {
        not_deleted: false,
        ..Default::default()
    };
    let mut all_jobs: Vec<Job> = Vec::new();
    let batch_size = 500i64;
    let mut offset = 0i64;
    loop {
        let page = db
            .get_jobs(&filter, batch_size, offset)
            .map_err(|e| format!("db get_jobs: {e}"))?;
        if page.is_empty() {
            break;
        }
        let got = page.len() as i64;
        all_jobs.extend(page);
        offset += got;
        if got < batch_size {
            break;
        }
    }

    let total = all_jobs.len() as i64;
    if total == 0 {
        return Ok(ScoreAllResult {
            total: 0,
            scored: 0,
            strong_count: 0,
            recommend_count: 0,
        });
    }

    let mut scored: i64 = 0;
    let mut strong_count: i64 = 0;
    let mut recommend_count: i64 = 0;
    // 分批调 sidecar.score_batch：chunks 不会跨边界，每批 ≤500 条。
    for chunk in all_jobs.chunks(500) {
        let results = sidecar_state
            .score_batch(chunk, &profile)
            .map_err(|e| format!("score_batch failed at offset {}: {}", scored, e))?;
        for r in results {
            // score 为 None 表示单条评分失败（sidecar 已在响应里附 error），
            // 跳过即可：保留旧 llm_score 不覆盖，下次再试。
            if let Some(score) = r.score {
                // llm_reason 是 SQLite TEXT 单字段，把多条 reasons 合并成一行字符串。
                // 前端 MatchScore 组件仍能解析（按 ; 拆分），保持表 schema 不变。
                let reason = r.reasons.join("; ");
                let _ = db.update_job_score(&r.job_id, score, &reason);
                scored += 1;
                if score >= 75.0 {
                    strong_count += 1;
                } else if score >= 55.0 {
                    recommend_count += 1;
                }
            }
        }
    }

    Ok(ScoreAllResult {
        total,
        scored,
        strong_count,
        recommend_count,
    })
}

/// 取已评分岗位（按 llm_score DESC）。可选分数区间过滤（推荐 Tab 用）。
#[tauri::command]
fn get_scored_jobs(
    db_state: tauri::State<'_, Db>,
    filter: Option<ScoredJobsFilter>,
    limit: Option<i64>,
    offset: Option<i64>,
) -> Result<Vec<Job>, String> {
    let f = filter.unwrap_or_default();
    let limit = limit.unwrap_or(50).clamp(1, 1000);
    let offset = offset.unwrap_or(0).max(0);
    db_state
        .get_scored_jobs(f.min_score, f.max_score, limit, offset)
        .map_err(|e| e.to_string())
}

/// 评分分桶统计：Tab 数量 + 已评 / 未评计数。
#[tauri::command]
fn get_score_summary(db_state: tauri::State<'_, Db>) -> Result<ScoreSummary, String> {
    db_state.get_score_summary().map_err(|e| e.to_string())
}

#[tauri::command]
fn get_active_resume(db_state: tauri::State<'_, Db>) -> Result<Option<Resume>, String> {
    db_state.get_active_resume().map_err(|e| e.to_string())
}

#[tauri::command]
fn save_resume(db_state: tauri::State<'_, Db>, resume: Resume) -> Result<(), String> {
    db_state.save_resume(&resume).map_err(|e| e.to_string())
}

#[tauri::command]
fn upsert_application(db_state: tauri::State<'_, Db>, app: Application) -> Result<(), String> {
    db_state.upsert_application(&app).map_err(|e| e.to_string())
}

#[tauri::command]
fn get_applications(
    db_state: tauri::State<'_, Db>,
    status: Option<String>,
) -> Result<Vec<Application>, String> {
    db_state
        .get_applications(status.as_deref())
        .map_err(|e| e.to_string())
}

// ============================================================================
// 岗位同步（T9）：云端 /api/v1/sync/jobs → 本地 SQLite 增量 upsert。
// token + api_base_url 由前端从 authStore + env 读取后传入（避免 Rust 侧重复
// 实现 token 解密；M1 阶段 token 加密流程尚未落地，等 keychain 接入后统一收口）。
// ============================================================================

#[tauri::command]
async fn sync_jobs(
    db_state: tauri::State<'_, Db>,
    sync_state: tauri::State<'_, SyncService>,
    api_base_url: String,
    token: String,
    since: Option<String>,
) -> Result<SyncResult, String> {
    // .inner() 取 &'r T（生命周期绑定到 State 容器，可跨 .await 持有——
    // async command 直接用 db_state.upsert_job 会因 State<'r> 借用未续到 await 后而编译失败）。
    let db = db_state.inner();
    let svc = sync_state.inner();
    svc.sync_jobs(db, &api_base_url, &token, since)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn get_sync_status(
    db_state: tauri::State<'_, Db>,
    sync_state: tauri::State<'_, SyncService>,
    api_base_url: String,
    token: String,
) -> Result<SyncStatus, String> {
    let db = db_state.inner();
    let svc = sync_state.inner();
    let remote = svc
        .get_remote_stats(&api_base_url, &token)
        .await
        .map_err(|e| e.to_string())?;
    svc.compare_with_local(db, &remote)
        .map_err(|e| e.to_string())
}

// ============================================================================
// 入口
// ============================================================================

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // 初始化日志：env_logger 从 RUST_LOG 读过滤级别，默认 info。
    let _ = env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info"))
        .try_init();

    tauri::Builder::default()
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .setup(|app| {
            // app_data_dir 在 macOS 上是 ~/Library/Application Support/<identifier>/，
            // 在 Linux 上是 ~/.local/share/<identifier>/，Windows 上是 %APPDATA%/<identifier>/。
            // spec 的 ~/.jobassistant 路径由前端通过 fs 读，DB 路径用 app_data_dir 统一管理。
            let app_data_dir = app
                .path()
                .app_data_dir()
                .expect("failed to resolve app_data_dir");
            let db = db::init_db(&app_data_dir).map_err(|e| {
                log::error!("init_db failed: {e}");
                Box::new(e) as Box<dyn std::error::Error>
            })?;
            app.manage(db);
            // SyncService 注册为 State：reqwest::Client 连接池跨命令复用，
            // 30s 超时在 sync.rs::SyncService::new() 内配置。
            app.manage(SyncService::new());
            // SidecarManager 注册为 State：lazy 启动（首次 send_request 时 spawn 子进程），
            // 不在 setup() 阶段 spawn，避免开发期 python-sidecar/sidecar_server.py 路径不存在时
            // 直接 panic 阻塞应用启动。Drop 时 stop() 触发 kill + wait。
            app.manage(SidecarManager::new());
            log::info!(
                "workbench.db initialized at {}",
                db::get_db_path(&app_data_dir).display()
            );
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            greet,
            get_jobs,
            get_job_stats,
            upsert_job,
            get_user_config,
            save_user_config,
            update_job_score,
            get_active_resume,
            save_resume,
            upsert_application,
            get_applications,
            sync_jobs,
            get_sync_status,
            score_all_jobs,
            get_scored_jobs,
            get_score_summary,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

// 保留 T1 的示例命令，便于前端最小连通性自测。
#[tauri::command]
fn greet(name: &str) -> String {
    format!("你好，{}！Offer搭子已就绪。", name)
}
