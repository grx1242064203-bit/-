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
  apply_url: string;
  announcement_url: string;
  last_updated: string;
}

export interface CompanyStats {
  total: number;
  industries: { name: string; count: number }[];
  types: { name: string; count: number }[];
}

export interface CompaniesResponse {
  companies: Company[];
  total: number;
  limit: number;
  offset: number;
}

export function getCompanies(params: {
  limit?: number;
  offset?: number;
  industry?: string;
  company_type?: string;
  keyword?: string;
}): Promise<CompaniesResponse> {
  return apiClient.get<CompaniesResponse>("/api/v1/sync/companies", params);
}

export function getCompanyStats(): Promise<CompanyStats> {
  return apiClient.get<CompanyStats>("/api/v1/sync/company-stats");
}
