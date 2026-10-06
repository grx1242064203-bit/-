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

export interface MessageResponse {
  message: string;
}

export const authApi = {
  register(
    email: string,
    password: string,
    xhsOrderId: string,
  ): Promise<RegisterResponse> {
    return apiClient.post<RegisterResponse>("/api/v1/auth/register", {
      email,
      password,
      xhs_order_id: xhsOrderId,
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

  /** 忘记密码：向邮箱发送重置验证码（即使邮箱不存在也返回成功以防枚举）。 */
  forgotPassword(email: string): Promise<MessageResponse> {
    return apiClient.post<MessageResponse>("/api/v1/auth/forgot-password", {
      email,
    });
  },

  /** 重置密码：用邮箱验证码设置新密码（不需要登录）。 */
  resetPassword(
    email: string,
    code: string,
    newPassword: string,
  ): Promise<MessageResponse> {
    return apiClient.post<MessageResponse>("/api/v1/auth/reset-password", {
      email,
      code,
      new_password: newPassword,
    });
  },

  /** 修改密码：需登录，校验旧密码后设新密码。 */
  changePassword(
    oldPassword: string,
    newPassword: string,
  ): Promise<MessageResponse> {
    return apiClient.post<MessageResponse>("/api/v1/auth/change-password", {
      old_password: oldPassword,
      new_password: newPassword,
    });
  },
};
