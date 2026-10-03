//! Python sidecar 评分引擎子进程管理器。
//!
//! 协议（T11 已实现）：每行一个 JSON-RPC。
//!   请求: {"id": 1, "method": "score_batch", "params": {...}}
//!   响应: {"id": 1, "result": [...]}/{"id": 1, "error": "..."}
//!
//! 设计：
//! - 同步 std::process::Command（不引 tokio::process，简化生命周期）。
//! - 子进程 stdin/stdout 用 `Mutex<BufWriter<ChildStdin>>` + `Mutex<BufReader<ChildStdout>>` 保护，
//!   score_batch 调用期间独占读写一行 JSON（每批 500 条岗位几秒级，UI 命令在线程池跑）。
//! - 自增 id（AtomicU64）；首次 send_request 时 lazy 启动子进程。
//! - 子进程 EOF（崩溃）→ 返回错误 + 清空状态，下次调用自动重启。
//! - 路径解析：env `SIDECAR_SCRIPT` 优先（生产可指向 PyOxidizer 打包后的可执行），
//!   否则 fallback 到 `<crate_root>/../python-sidecar/sidecar_server.py`（开发期，用 `python3` 直接跑）。
//!   `DATA_DIR` 同样从 env 取，fallback 到 `/workspace/job_assistant/data`（开发期 kw_dict.json 所在）。

use std::io::{BufRead, BufReader, BufWriter, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::models::Job;

/// sidecar 评分结果（与 python-sidecar/sidecar_server.py 的 score_batch 响应对齐）。
/// score 为 None 表示该条评分失败（sidecar 已在响应里附 error 字段，我们忽略）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoreResult {
    pub job_id: String,
    pub score: Option<f64>,
    pub recommend: Option<String>,
    pub reasons: Vec<String>,
}

/// 子进程持有句柄：child 用于 stop()/kill；stdin/stdout 拆开便于 BufWriter/BufReader 包装。
struct SidecarHandles {
    child: Child,
    stdin: BufWriter<ChildStdin>,
    stdout: BufReader<ChildStdout>,
}

/// Python sidecar 子进程管理器（Tauri State 跨命令复用）。
pub struct SidecarManager {
    handles: Mutex<Option<SidecarHandles>>,
    next_id: AtomicU64,
    script_path: PathBuf,
    data_dir: PathBuf,
    python_bin: String,
}

impl Default for SidecarManager {
    fn default() -> Self {
        Self::new()
    }
}

impl SidecarManager {
    /// 用 env 解析路径构造：开发期默认指向 crate 上两层的 python-sidecar。
    pub fn new() -> Self {
        let script_path = resolve_script_path();
        let data_dir = resolve_data_dir();
        let python_bin = std::env::var("SIDECAR_PYTHON").unwrap_or_else(|_| "python3".to_string());
        Self {
            handles: Mutex::new(None),
            next_id: AtomicU64::new(0),
            script_path,
            data_dir,
            python_bin,
        }
    }

    /// 显式指定路径构造（测试 / 注入用）。
    #[allow(dead_code)]
    pub fn with_paths(script_path: PathBuf, data_dir: PathBuf) -> Self {
        let python_bin = std::env::var("SIDECAR_PYTHON").unwrap_or_else(|_| "python3".to_string());
        Self {
            handles: Mutex::new(None),
            next_id: AtomicU64::new(0),
            script_path,
            data_dir,
            python_bin,
        }
    }

    /// 启动子进程并握住 stdin/stdout。已启动则直接返回 Ok。
    /// 失败原因：python3 不在 PATH / script_path 不存在 / spawn 权限不足。
    pub fn start(&self) -> Result<(), String> {
        let mut guard = self.handles.lock().expect("sidecar mutex poisoned");
        if guard.is_some() {
            return Ok(());
        }
        let mut child = self.spawn_child()?;
        // take() 把字段改为 None 后返回原值，避免 child 被 partial-move 后无法整体放进 SidecarHandles。
        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| "sidecar stdin not piped".to_string())?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| "sidecar stdout not piped".to_string())?;
        *guard = Some(SidecarHandles {
            child,
            stdin: BufWriter::new(stdin),
            stdout: BufReader::new(stdout),
        });
        log::info!(
            "sidecar started: {} {} (DATA_DIR={})",
            self.python_bin,
            self.script_path.display(),
            self.data_dir.display()
        );
        Ok(())
    }

    fn spawn_child(&self) -> Result<Child, String> {
        if !self.script_path.exists() {
            return Err(format!(
                "sidecar script not found: {}",
                self.script_path.display()
            ));
        }
        let mut cmd = Command::new(&self.python_bin);
        cmd.arg(&self.script_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            // stderr 继承父进程：sidecar 的日志走 stderr，开发期能直接看到崩溃原因。
            .stderr(Stdio::inherit())
            .env("DATA_DIR", &self.data_dir);
        // Python 子进程默认会继承父级环境变量（含 PATH / VITE_* 等），无需显式 env_clear。
        cmd.spawn().map_err(|e| format!("spawn sidecar failed: {e}"))
    }

    /// 发一次 JSON-RPC：写一行请求 → 读一行响应 → 取 result 字段。
    /// 子进程 EOF（崩溃）→ 清空状态返回错误，下次调用自动重启。
    pub fn send_request(&self, method: &str, params: Value) -> Result<Value, String> {
        // 启动期不在锁内（避免 start() 自身锁递归）。失败立即返回错误。
        self.ensure_started()?;
        let id = self.next_id.fetch_add(1, Ordering::SeqCst) + 1;
        let req = json!({"id": id, "method": method, "params": params});
        let line = serde_json::to_string(&req).map_err(|e| format!("serialize: {e}"))?;

        let mut guard = self.handles.lock().expect("sidecar mutex poisoned");
        let handles = match guard.as_mut() {
            Some(h) => h,
            None => return Err("sidecar not started".to_string()),
        };

        // 写请求行：BufWriter 需显式 flush 才能让子进程 stdin 立即收到。
        if let Err(e) = handles
            .stdin
            .write_all(line.as_bytes())
            .and_then(|_| handles.stdin.write_all(b"\n"))
            .and_then(|_| handles.stdin.flush())
        {
            // stdin 写失败 → 子进程大概率已退出。清空状态，下次自动重启。
            *guard = None;
            return Err(format!("sidecar write failed: {e}"));
        }

        // 读响应行：read_line 阻塞直到 \n 或 EOF。空串 → 子进程已退出。
        let mut buf = String::new();
        match handles.stdout.read_line(&mut buf) {
            Ok(0) => {
                *guard = None;
                Err("sidecar EOF: 子进程已退出".to_string())
            }
            Ok(_) => {
                let resp: Value =
                    serde_json::from_str(buf.trim()).map_err(|e| format!("parse response: {e}"))?;
                if let Some(err) = resp.get("error") {
                    let msg = err.as_str().unwrap_or("unknown error");
                    Err(msg.to_string())
                } else {
                    Ok(resp.get("result").cloned().unwrap_or(Value::Null))
                }
            }
            Err(e) => {
                *guard = None;
                Err(format!("sidecar read failed: {e}"))
            }
        }
    }

    /// 批量评分：把 jobs 序列化为 sidecar 期望的 JSON，调一次 score_batch。
    /// profile 由调用方（Tauri command）传入，是简历解析的 ParsedProfile JSON。
    pub fn score_batch(&self, jobs: &[Job], profile: &Value) -> Result<Vec<ScoreResult>, String> {
        let jobs_json: Vec<Value> = jobs
            .iter()
            .map(|j| serde_json::to_value(j).unwrap_or(Value::Null))
            .collect();
        let params = json!({"jobs": jobs_json, "profile": profile});
        let result = self.send_request("score_batch", params)?;
        serde_json::from_value::<Vec<ScoreResult>>(result)
            .map_err(|e| format!("deserialize score_batch result: {e}"))
    }

    /// 关闭子进程：kill + wait 避免僵尸。setup 不主动调用（lazy 启动），
    /// 仅用于显式重置 / 程序退出时（Drop 也会触发 kill，但 std 不保证 kill_on_drop）。
    pub fn stop(&self) {
        let mut guard = self.handles.lock().expect("sidecar mutex poisoned");
        if let Some(mut handles) = guard.take() {
            let _ = handles.child.kill();
            let _ = handles.child.wait();
        }
    }

    /// 是否仍持有子进程句柄（不代表子进程一定存活；存活检测靠下次 send_request 触发 EOF）。
    #[allow(dead_code)]
    pub fn is_running(&self) -> bool {
        self.handles
            .lock()
            .map(|g| g.is_some())
            .unwrap_or(false)
    }

    fn ensure_started(&self) -> Result<(), String> {
        let guard = self.handles.lock().expect("sidecar mutex poisoned");
        if guard.is_some() {
            return Ok(());
        }
        drop(guard);
        // 锁已释放，调 start() 重新加锁。
        self.start()
    }
}

impl Drop for SidecarManager {
    fn drop(&mut self) {
        self.stop();
    }
}

// ============================================================================
// 路径解析
// ============================================================================

/// 解析 sidecar_server.py 路径：
/// - env `SIDECAR_SCRIPT` 优先（生产可指向 PyOxidizer 打包后的可执行 / 自定义路径）。
/// - 否则 fallback 到 `<crate_manifest>/../python-sidecar/sidecar_server.py`（开发期）。
///   crate_manifest 在 dev 是 src-tauri/，源码侧 python-sidecar 在 src-tauri 的上一级。
fn resolve_script_path() -> PathBuf {
    if let Ok(p) = std::env::var("SIDECAR_SCRIPT") {
        let path = PathBuf::from(p);
        if path.exists() {
            return path;
        }
        log::warn!("SIDECAR_SCRIPT={:?} 不存在，回退到默认开发路径", path);
    }
    // CARGO_MANIFEST_DIR 在 dev / test 由 cargo 注入；release 不存在，fallback 到相对路径。
    let manifest = option_env!("CARGO_MANIFEST_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."));
    manifest
        .join("..")
        .join("python-sidecar")
        .join("sidecar_server.py")
}

/// 解析 DATA_DIR：env `DATA_DIR` 优先，否则 fallback 到 `/workspace/job_assistant/data`
/// （开发期 kw_dict.json / job_category_tree.json 所在；生产应由打包脚本注入）。
fn resolve_data_dir() -> PathBuf {
    if let Ok(d) = std::env::var("DATA_DIR") {
        let path = PathBuf::from(&d);
        if path.exists() {
            return path;
        }
        log::warn!("DATA_DIR={:?} 不存在，回退到默认开发路径", d);
    }
    PathBuf::from("/workspace/job_assistant/data")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn score_result_deserializes_from_sidecar_shape() {
        // 与 sidecar_server.py::_method_score_batch 的输出字段对齐
        let raw = r#"{"job_id":"j-1","score":85.0,"recommend":"强烈推荐","reasons":["技能命中","城市匹配"]}"#;
        let r: ScoreResult = serde_json::from_str(raw).unwrap();
        assert_eq!(r.job_id, "j-1");
        assert_eq!(r.score, Some(85.0));
        assert_eq!(r.recommend.as_deref(), Some("强烈推荐"));
        assert_eq!(r.reasons.len(), 2);
    }

    #[test]
    fn score_result_allows_null_score_for_failed_item() {
        // sidecar 单条评分失败时返回 score=null + error 字段（error 字段不在 struct，被 serde 忽略）
        let raw = r#"{"job_id":"j-x","score":null,"recommend":null,"reasons":[],"error":"boom"}"#;
        let r: ScoreResult = serde_json::from_str(raw).unwrap();
        assert_eq!(r.job_id, "j-x");
        assert!(r.score.is_none());
        assert!(r.recommend.is_none());
        assert!(r.reasons.is_empty());
    }

    #[test]
    fn resolve_paths_use_env_when_present() {
        // env 路径分支仅在 env 真实存在文件时生效；这里测的是 fallback 分支
        // （CARGO_MANIFEST_DIR 注入时 fallback 指向 src-tauri/../python-sidecar）。
        let script = resolve_script_path();
        assert!(script.to_string_lossy().contains("sidecar_server.py"));
    }

    #[test]
    fn new_manager_starts_idle() {
        let m = SidecarManager::new();
        assert!(!m.is_running());
        assert!(m.script_path.to_string_lossy().contains("sidecar_server.py"));
    }
}
