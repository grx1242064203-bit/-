// 管理后台 API：封装 /api/v1/admin/* 端点调用。
import { apiClient } from "./client";

export interface AdminUser {
  id: string;
  email: string;
  is_verified: boolean;
  is_admin: boolean;
  is_active: boolean;
  notes: string | null;
  xhs_order_id: string | null;
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

export interface BulkUpdateBody {
  user_ids: string[];
  is_active: boolean;
}

export interface BulkUpdateResponse {
  message: string;
  affected: number;
  skipped_self: number;
}

export const adminApi = {
  /** 列出用户（支持搜索 email / notes / xhs_order_id）。 */
  listUsers(params?: {
    limit?: number;
    offset?: number;
    search?: string;
  }): Promise<UserListResponse> {
    return apiClient.get<UserListResponse>("/api/v1/admin/users", params);
  },

  /** 导出全部用户（无分页，审核时用）。 */
  exportAllUsers(): Promise<UserListResponse> {
    return apiClient.get<UserListResponse>("/api/v1/admin/export/users");
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

  /** 批量 启用/停用 用户（审核时用，自动过滤掉自己）。 */
  bulkUpdateUsers(body: BulkUpdateBody): Promise<BulkUpdateResponse> {
    return apiClient.post<BulkUpdateResponse>(
      "/api/v1/admin/users/bulk",
      body,
    );
  },
};
