// 投递记录 API：收藏/投递/面试/offer 全流程。
import { apiClient } from "./client";

export type AppStatus = "favorite" | "applied" | "interview" | "offer" | "rejected";

export interface Application {
  id: number;
  user_id: number;
  job_id: string;
  job_title: string;
  company_name: string;
  status: AppStatus;
  apply_url: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export function createApplication(data: {
  job_id: string;
  job_title: string;
  company_name?: string;
  status?: AppStatus;
  apply_url?: string;
  notes?: string;
}): Promise<Application> {
  return apiClient.post<Application>("/api/v1/applications", data);
}

export function listApplications(status?: AppStatus): Promise<{ applications: Application[]; total: number }> {
  return apiClient.get("/api/v1/applications", status ? { status } : undefined);
}

export function updateApplication(
  id: number,
  data: { status?: AppStatus; notes?: string }
): Promise<Application> {
  return apiClient.patch<Application>(`/api/v1/applications/${id}`, data);
}

export function deleteApplication(id: number): Promise<{ ok: boolean }> {
  return apiClient.delete<{ ok: boolean }>(`/api/v1/applications/${id}`);
}
