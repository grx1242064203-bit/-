// 岗位 API：通过 HTTP 调用后端 /api/v1/sync/jobs/page 端点。
// Job 字段对齐飞书「27届校招汇总表」列顺序。

import { apiClient } from "./client";

export interface Job {
  job_id: string;
  title: string;
  company: string;
  industry: string;
  company_type: string;
  category: string;
  subcategory: string;
  city: string;
  min_education: string;
  is_mt: number;
  major_category: string;
  major_required: string;
  hard_skills: string;
  keywords: string;
  jd_summary: string;
  difficulty: string;
  /** 公告发布/更新时间（apply_update） */
  updated_at: string;
  deadline: string | null;
  apply_url: string;
  announcement_url: string;
}

export interface JobStats {
  total: number;
  updated_at: string | null;
}

export interface JobFilter {
  city?: string;
  category?: string;
  keyword?: string;
  industry?: string;
  company_type?: string;
  subcategory?: string;
  min_education?: string;
  is_mt?: string;
  major_category?: string;
  difficulty?: string;
  // 文本列模糊搜索（LIKE）：title / company / major_required / hard_skills / keywords / jd_summary 等
  [key: string]: string | undefined;
}

export function getJobs(
  filter?: JobFilter,
  limit?: number,
  offset?: number
): Promise<{ jobs: Job[]; total: number }> {
  const params: Record<string, unknown> = {
    limit: limit ?? 50,
    offset: offset ?? 0,
  };
  if (filter) {
    for (const [k, v] of Object.entries(filter)) {
      if (v && v !== "" && v !== "全国各地" && v !== "不限") {
        params[k] = v;
      }
    }
  }

  return apiClient
    .get<{ jobs: Job[]; total: number }>("/api/v1/sync/jobs/page", params)
    .then((res) => ({ jobs: res.jobs, total: res.total }));
}

export function getJobStats(): Promise<JobStats> {
  return apiClient.get<JobStats>("/api/v1/sync/stats");
}
