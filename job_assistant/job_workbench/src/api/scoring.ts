// 评分 API：封装 Tauri invoke("score_all_jobs") / invoke("get_scored_jobs") / invoke("get_score_summary")。
//
// 设计：
// - 类型与 src-tauri/src/lib.rs::ScoreAllResult / src-tauri/src/sidecar.rs::ScoreResult
//   以及 src-tauri/src/db.rs::ScoreSummary 严格对齐（snake_case JSON 直通 invoke）。
// - ScoredJobsFilter 的 min_score / max_score 与 db.rs::get_scored_jobs 同语义：闭下界 + 开上界。
// - scoreAllJobs 由 scoreStore.scoreAll 调用：完成后前端调 loadSummary + loadScoredJobs 刷新 Tab。
// - profile 参数是 resumeStore.parsedProfile 直接序列化（snake_case keywords/fit_directions
//   与 sidecar 的 _build_profile 兼容，SimpleNamespace 接收任意字段）。

import { invoke } from "@tauri-apps/api/core";
import type { Job } from "./jobs";

// score_all_jobs 返回结构（与 src-tauri/src/lib.rs::ScoreAllResult 对齐）
export interface ScoreAllResult {
  total: number;
  scored: number;
  strong_count: number;
  recommend_count: number;
}

// 评分分桶统计（与 src-tauri/src/db.rs::ScoreSummary 对齐）
export interface ScoreSummary {
  total: number;
  scored: number;
  strong_recommend: number;
  recommend: number;
  can_apply: number;
  not_recommended: number;
  unscored: number;
}

// 已评分岗位筛选：min_score 闭下界 / max_score 开上界（与 Rust ScoredJobsFilter 对齐）
export interface ScoredJobsFilter {
  min_score?: number;
  max_score?: number;
}

/**
 * 触发全量评分：Rust 端读全部岗位 → 分批调 sidecar.score_batch(每批 500) → 回写 SQLite。
 * profile 由调用方从 resumeStore.parsedProfile 传入；空 profile 时 sidecar 会回退到
 * 全 60.0 默认分（scorer 内部 dim_scores.get(dim, 60.0) 兜底）。
 * 全量 35K 条总耗时约分钟级，调用方需把 isScoring=true 标记 + 进度反馈串起来。
 */
export function scoreAllJobs(profile: unknown): Promise<ScoreAllResult> {
  return invoke<ScoreAllResult>("score_all_jobs", { profile });
}

/**
 * 取已评分岗位（按 llm_score DESC）。可选分数区间过滤——
 *   - 强烈推荐：{ min_score: 75 }（max_score 不传，开上界到 +∞）
 *   - 推荐：{ min_score: 55, max_score: 75 }
 *   - 可申请：{ min_score: 35, max_score: 55 }
 * 与 db.rs::get_scored_jobs 同语义：min_score 闭下界，max_score 开上界。
 * @param filter 分数区间；undefined 时返回全部已评分岗位。
 * @param limit 每页条数，默认 50；Rust 端 clamp(1, 1000)。
 * @param offset 偏移量，默认 0。
 */
export function getScoredJobs(
  filter?: ScoredJobsFilter,
  limit?: number,
  offset?: number
): Promise<Job[]> {
  return invoke<Job[]>("get_scored_jobs", {
    filter: filter ?? null,
    limit: limit ?? 50,
    offset: offset ?? 0,
  });
}

/**
 * 评分分桶统计（Tab 数量）。Rust 端单次 SELECT COUNT，毫秒级，可频繁刷新。
 */
export function getScoreSummary(): Promise<ScoreSummary> {
  return invoke<ScoreSummary>("get_score_summary");
}
