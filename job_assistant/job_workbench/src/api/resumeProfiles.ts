// 简历画像 API — 后端 /api/v1/resume-profiles CRUD

import { apiClient } from "./client";

export interface ResumeProfile {
  profile_id: string;
  user_id: string;
  resume_text?: string;
  keywords: any[];
  fit_directions: any[];
  degree: string;
  major: string;
  target_cities: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export const resumeProfilesApi = {
  /** 创建画像（新画像自动把同用户旧 active 设为 inactive） */
  create(data: {
    resume_text: string;
    keywords: any[];
    fit_directions: any[];
    degree?: string;
    major?: string;
    target_cities?: string[];
  }): Promise<ResumeProfile> {
    return apiClient.post<ResumeProfile>("/api/v1/resume-profiles", data);
  },

  /** 获取当前用户 active 画像 */
  getActive(): Promise<ResumeProfile | null> {
    return apiClient.get<ResumeProfile | null>("/api/v1/resume-profiles/active");
  },

  /** 列出所有画像 */
  list(): Promise<ResumeProfile[]> {
    return apiClient.get<ResumeProfile[]>("/api/v1/resume-profiles");
  },

  /** 删除画像 */
  delete(profileId: string): Promise<void> {
    return apiClient.delete(`/api/v1/resume-profiles/${profileId}`);
  },
};
