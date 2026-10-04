// 岗位 API：通过 HTTP 调用后端 /api/v1/sync/jobs/page 端点。
//
// 设计：
// - Job interface 与后端 JOB_FIELDS 字段对齐
// - JobFilter 贴近产品语义（city / category / keyword…）
// - getJobs 支持分页（limit / offset），与后端 get_jobs_page 对齐

import { apiClient } from "./client";

// Job struct（与后端 JOB_FIELDS 对齐）
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
  updated_at: string | null;
}

// JobStats
export interface JobStats {
  total: number;
  updated_at: string | null;
}

/**
 * 用户面 JobFilter：UI 层使用。
 * - city: 下拉值；"全国各地"视为不筛选。
 * - category: 下拉值；"不限"视为不筛选。
 * - keyword: 关键词搜索（标题/公司/JD）。
 */
export interface JobFilter {
  city?: string;
  category?: string;
  keyword?: string;
}

/**
 * 拉取岗位列表（offset 分页）。
 * @param filter 用户面筛选。
 * @param limit 每页条数，默认 50。
 * @param offset 偏移量，默认 0。
 */
export function getJobs(
  filter?: JobFilter,
  limit?: number,
  offset?: number
): Promise<Job[]> {
  const params: Record<string, unknown> = {
    limit: limit ?? 50,
    offset: offset ?? 0,
  };
  if (filter?.city && filter.city !== "全国各地") params.city = filter.city;
  if (filter?.category && filter.category !== "不限") params.category = filter.category;
  if (filter?.keyword && filter.keyword.trim()) params.keyword = filter.keyword.trim();

  return apiClient
    .get<{ jobs: Job[] }>("/api/v1/sync/jobs/page", params)
    .then((res) => res.jobs);
}

/**
 * 拉取岗位统计：总数 + 最近 updated_at。
 */
export function getJobStats(): Promise<JobStats> {
  return apiClient.get<JobStats>("/api/v1/sync/stats");
}
