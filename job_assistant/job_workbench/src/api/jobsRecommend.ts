// 岗位推荐 API — 后端 /api/v1/jobs/recommend

import { apiClient } from "./client";

export interface RecommendedJob {
  job_id: string;
  title: string;
  company: string;
  industry: string;
  company_type: string;
  difficulty: string;
  city: string;
  min_education: string;
  category: string;
  subcategory: string;
  deadline: string | null;
  apply_url: string;
  announcement_url: string;
  score: number;
  recommend: string; // 强烈推荐 / 推荐 / 可申请 / 不建议
  recommend_level: "super_recommend" | "recommend" | "applyable" | "low" | string;
  reasons: string[];
  dims: Record<string, number>;
  // 补齐字段(与岗位总表对齐)
  recruit_type?: string;
  recruit_target?: string;
  is_mt?: boolean;
  major_category?: string;
  major_required?: string;
  jd_summary?: string;
  hard_skills?: string;
  keywords?: string;
  updated_at?: string;
  // 公司层级 × 用户层级 透明化
  company_tier?: string;          // 顶/中/保底
  candidate_score?: number;       // 候选人竞争力分 0-100
  company_score?: number;         // 公司/岗位竞争力分 0-100
  alignment_label?: string;       // 匹配/冲刺/保底/严重错配
}

export interface RecommendResponse {
  jobs: RecommendedJob[];
  total_matched: number;
  total_returned: number;
  top_n_requested: number;
}

export const jobsRecommendApi = {
  /** 基于当前 active 简历画像推荐岗位 */
  recommend(top_n: number = 200): Promise<RecommendResponse> {
    return apiClient.post<RecommendResponse>("/api/v1/jobs/recommend", { top_n });
  },

  /** 指定 profile_id 推荐 */
  recommendFor(profileId: string, top_n: number = 200): Promise<RecommendResponse> {
    return apiClient.post<RecommendResponse>("/api/v1/jobs/recommend", {
      profile_id: profileId,
      top_n,
    });
  },
};
