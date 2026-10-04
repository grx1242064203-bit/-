// 投递记录 API：收藏/投递/测评/面试/offer 全流程。
import { apiClient } from "./client";

export type AppStatus =
  | "favorite"
  | "applied"
  | "assessment"
  | "interview"
  | "offer"
  | "rejected";

export type AppSource = "db_job" | "db_company" | "manual" | "email";

export interface Application {
  id: number;
  user_id: number;
  job_id: string;
  job_title: string;
  company_name: string;
  status: AppStatus;
  source: AppSource;
  link_type: "job" | "company" | null;
  link_id: string | null;
  interview_round: number;
  apply_url: string;
  announcement_url: string;
  notes: string | null;
  email_id: string | null;
  favorite_at: string | null;
  applied_at: string | null;
  assessment_at: string | null;
  interview_at: string | null;
  offer_at: string | null;
  created_at: string;
  updated_at: string;

  // ===== 后端 enrichment（关联岗位库/公司库后补充，可能为空）=====
  industry?: string;
  company_type?: string;
  publish_time?: string;
  deadline?: string;
  // 公司库专属
  recruit_type?: string;
  recruit_target?: string;
  location?: string;
  // 岗位库专属
  position_title?: string;
  job_category?: string;
  min_education?: string;
  is_mt?: boolean;
  jd_summary?: string;
  difficulty?: string;
  city?: string;
}

export function createApplication(data: {
  job_title?: string;
  company_name?: string;
  status?: AppStatus;
  source?: AppSource;
  link_type?: "job" | "company" | null;
  link_id?: string | null;
  apply_url?: string;
  announcement_url?: string;
  notes?: string;
  email_id?: string | null;
}): Promise<Application> {
  return apiClient.post<Application>("/api/v1/applications", data);
}

export function listApplications(
  status?: AppStatus
): Promise<{ applications: Application[]; total: number }> {
  return apiClient.get(
    "/api/v1/applications",
    status ? { status } : undefined
  );
}

export function getApplication(id: number): Promise<Application> {
  return apiClient.get<Application>(`/api/v1/applications/${id}`);
}

export function updateApplication(
  id: number,
  data: {
    status?: AppStatus;
    notes?: string | null;
    interview_round?: number;
    apply_url?: string;
    announcement_url?: string;
    job_title?: string;
    company_name?: string;
  }
): Promise<Application> {
  return apiClient.patch<Application>(`/api/v1/applications/${id}`, data);
}

export function deleteApplication(id: number): Promise<{ ok: boolean }> {
  return apiClient.delete<{ ok: boolean }>(`/api/v1/applications/${id}`);
}

// ===== 公司尽调 =====
export interface DueDiligence {
  company_name: string;
  intro: string;
  official_website: string;
  news_links: { title: string; url: string }[];
  why_company_questions: { question: string; hint: string }[];
  generated_at: string;
  cached: boolean;
}

export function getCompanyDueDiligence(
  company_name: string
): Promise<DueDiligence> {
  return apiClient.post<DueDiligence>(
    "/api/v1/llm/company-due-diligence",
    { company_name }
  );
}
