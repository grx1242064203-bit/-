// 认证 API：封装 /api/v1/auth/* 端点调用。
import { apiClient } from "./client";

export interface RegisterResponse {
  user_id: string;
  needs_verify: boolean;
}

export interface TokenResponse {
  token: string;
  expires_at: string;
}

export const authApi = {
  register(email: string, password: string): Promise<RegisterResponse> {
    return apiClient.post<RegisterResponse>("/api/v1/auth/register", {
      email,
      password,
    });
  },

  verifyEmail(email: string, code: string): Promise<TokenResponse> {
    return apiClient.post<TokenResponse>("/api/v1/auth/verify-email", {
      email,
      code,
    });
  },

  login(email: string, password: string): Promise<TokenResponse> {
    return apiClient.post<TokenResponse>("/api/v1/auth/login", {
      email,
      password,
    });
  },

  refreshToken(): Promise<TokenResponse> {
    return apiClient.post<TokenResponse>("/api/v1/auth/refresh");
  },
};
