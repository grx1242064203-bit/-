// 公司总览 API：直接调用后端 HTTP 接口（不经过 Tauri 本地同步）。
import { apiClient } from "./client";

export interface Company {
  company_id: string;
  company_name: string;
  industry: string;
  company_type: string;
  recruit_type: string;
  recruit_target: string;
  location: string;
  education_req: string;
  deadline: string | null;
  positions_count: number;
  /** 该公司招聘岗位标题列表（顿号分隔，最多 15 个） */
  position_titles: string | null;
  apply_url: string;
  announcement_url: string;
  /** 公告实际发布/更新时间（apply_update） */
  last_updated: string;
}

export interface CompanyStats {
  total: number;
  industries: { name: string; count: number }[];
  types: { name: string; count: number }[];
}

export interface FilterOption {
  value: string;
  label: string;
}

export interface StatsOverview {
  companies: {
    total: number;
    today_new: number;
    week_new: number;
    closing_soon: number;
    top_industries: { name: string; count: number }[];
    top_types: { name: string; count: number }[];
    filter_options: Record<string, string[]>;
  };
  jobs: {
    total: number;
    today_new: number;
    week_new: number;
    top_categories: { name: string; count: number }[];
    filter_options: Record<string, (string | FilterOption)[]>;
  };
}

export interface CompaniesResponse {
  companies: Company[];
  total: number;
  limit: number;
  offset: number;
}

export interface CompaniesParams {
  limit?: number;
  offset?: number;
  industry?: string;
  company_type?: string;
  keyword?: string;
  recruit_type?: string;
  education_req?: string;
  // 文本列模糊搜索（LIKE）：location / position_titles / deadline / last_updated 等
  [key: string]: number | string | undefined;
}

export function getCompanies(params: CompaniesParams): Promise<CompaniesResponse> {
  return apiClient.get<CompaniesResponse>(
    "/api/v1/sync/companies",
    params as Record<string, unknown>
  );
}

export function getCompanyStats(): Promise<CompanyStats> {
  return apiClient.get<CompanyStats>("/api/v1/sync/company-stats");
}

export function getStatsOverview(): Promise<StatsOverview> {
  return apiClient.get<StatsOverview>("/api/v1/sync/stats-overview");
}
