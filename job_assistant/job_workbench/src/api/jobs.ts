// 岗位 API：封装 Tauri invoke("get_jobs") + invoke("get_job_stats")。
//
// 设计：
// - Job / JobStats interface 与 src-tauri/src/models.rs::Job / JobStats 字段严格对齐
//   （snake_case JSON 直通，前端 invoke 收发无需转换）。
// - 用户面 JobFilter（education / keyword / sort…）贴近产品语义，由 toRustFilter
//   映射到 Rust 端 JobFilter struct（graduation_match / search…）。Rust struct 字段
//   名与 UI 概念不完全一致，故本层做一次显式转换，避免上层感知后端细节。
// - getJobs 支持分页（limit / offset），与 db.rs::get_jobs(limit, offset) 对齐。
//   limit 在 Rust 端被 clamp(1, 1000)，超出范围不会报错，自动收敛。

import { invoke } from "@tauri-apps/api/core";

// Job struct（与 src-tauri/src/models.rs::Job 对齐）
export interface Job {
  job_id: string;
  company: string;
  title: string;
  category: string | null;
  city: string | null;
  requirements: string | null;
  jd_text: string | null;
  apply_url: string | null;
  deadline: string | null;
  source: string | null;
  graduation_match: number;
  is_mt: number;
  llm_score: number | null;
  llm_reason: string | null;
  updated_at: string | null;
  deleted: number;
}

// JobStats（与 Rust JobStats 对齐）
export interface JobStats {
  total: number;
  updated_at: string | null;
}

/**
 * 用户面 JobFilter：UI 层使用。字段名贴近产品语义（education / keyword / sort）。
 * - city: 下拉值（北京/上海/.../全国各地）；"全国各地"视为不筛选。
 * - education: 下拉值（不限/大专/本科/硕士/博士）；"不限"视为不筛选。
 *   后端无独立学历筛选字段，本层在 toRustFilter 内映射为 search（jd_text 多含"本科"等字符串，
 *   LIKE %本科% 可命中），与 keyword 合流；同时有 keyword 时 keyword 优先。
 * - is_mt: 管培开关；true=仅看管培，undefined=不限。
 * - category: 下拉值（工科/.../不限）；"不限"视为不筛选。
 * - company: 公司名精确匹配（Rust 端 company = ?）。
 * - keyword: 关键词，映射为 Rust search（company / title / jd_text LIKE）。
 * - sort: 排序；Rust 端固定 ORDER BY updated_at DESC NULLS LAST，本字段当前未使用，
 *   预留供 T13 推荐视图按 llm_score 排序时扩展。
 */
export interface JobFilter {
  city?: string;
  education?: string;
  is_mt?: boolean;
  category?: string;
  company?: string;
  keyword?: string;
  sort?: string;
}

// Rust 端 JobFilter：与 src-tauri/src/models.rs::JobFilter 字段对齐。
// not_deleted 默认 true（Rust 端 #[serde(default = "default_true")]），此处保持默认不传。
interface RustJobFilter {
  city?: string;
  graduation_match?: boolean;
  is_mt?: boolean;
  category?: string;
  company?: string;
  search?: string;
  not_deleted?: boolean;
  min_score?: number;
}

/**
 * 用户面 filter → Rust 面 filter。
 * 注意：Rust struct 无 #[serde(deny_unknown_fields)]，多余字段会被静默忽略，
 * 但本层显式只构造 Rust 认识的字段，避免歧义。
 */
function toRustFilter(filter?: JobFilter): RustJobFilter {
  const f: RustJobFilter = {};
  if (!filter) return f;

  if (filter.city && filter.city !== "全国各地") f.city = filter.city;

  // 学历：后端无独立字段，用 search 兜底（jd_text 多含学历字符串）。
  // 与 keyword 合流：两者同时有值时 keyword 优先（search 是单 LIKE 模式，无法 OR）。
  const hasKeyword = !!(filter.keyword && filter.keyword.trim());
  if (hasKeyword) {
    f.search = filter.keyword!.trim();
  } else if (filter.education && filter.education !== "不限") {
    f.search = filter.education;
  }

  if (filter.is_mt !== undefined) f.is_mt = filter.is_mt;
  if (filter.category && filter.category !== "不限") f.category = filter.category;
  if (filter.company && filter.company.trim()) f.company = filter.company.trim();

  return f;
}

/**
 * 拉取岗位列表（分页）。
 * @param filter 用户面筛选；undefined 时 Rust 端使用默认 JobFilter（not_deleted=true，其余 None）。
 * @param limit 每页条数，默认 50；Rust 端 clamp(1, 1000)。
 * @param offset 偏移量，默认 0。
 */
export function getJobs(
  filter?: JobFilter,
  limit?: number,
  offset?: number
): Promise<Job[]> {
  return invoke<Job[]>("get_jobs", {
    filter: toRustFilter(filter),
    limit: limit ?? 50,
    offset: offset ?? 0,
  });
}

/**
 * 拉取岗位统计：总数（未删）+ 最近 updated_at（同步游标）。
 */
export function getJobStats(): Promise<JobStats> {
  return invoke<JobStats>("get_job_stats");
}
