// 管理后台 API：封装 /api/v1/admin/* 端点调用。
import { apiClient } from "./client";

export interface AdminUser {
  id: string;
  email: string;
  is_verified: boolean;
  is_admin: boolean;
  is_active: boolean;
  notes: string | null;
  created_at: string;
  last_login_at: string | null;
}

export interface UserListResponse {
  users: AdminUser[];
  total: number;
  limit: number;
  offset: number;
}

export interface CreateUserBody {
  email: string;
  password: string;
  notes?: string;
}

export interface UpdateUserBody {
  is_active?: boolean;
  is_admin?: boolean;
  notes?: string;
}

export const adminApi = {
  /** 列出用户（支持搜索 email 或 notes）。 */
  listUsers(params?: {
    limit?: number;
    offset?: number;
    search?: string;
  }): Promise<UserListResponse> {
    return apiClient.get<UserListResponse>("/api/v1/admin/users", params);
  },

  /** 手动建号（已验证状态，跳过邮箱验证码）。 */
  createUser(body: CreateUserBody): Promise<AdminUser> {
    return apiClient.post<AdminUser>("/api/v1/admin/users", body);
  },

  /** 修改用户属性（吊销/恢复/改备注/设管理员）。 */
  updateUser(userId: string, body: UpdateUserBody): Promise<AdminUser> {
    return apiClient.patch<AdminUser>(`/api/v1/admin/users/${userId}`, body);
  },

  /** 删除用户。 */
  deleteUser(userId: string): Promise<void> {
    return apiClient.delete<void>(`/api/v1/admin/users/${userId}`);
  },

  /** 管理员重置用户密码（兜底方案）。 */
  resetUserPassword(
    userId: string,
    newPassword: string,
  ): Promise<{ message: string; user_id: string }> {
    return apiClient.post<{ message: string; user_id: string }>(
      `/api/v1/admin/users/${userId}/reset-password`,
      { new_password: newPassword },
    );
  },
};
