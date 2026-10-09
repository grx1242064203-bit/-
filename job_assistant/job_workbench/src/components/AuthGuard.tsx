import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore } from "../stores/authStore";

// 路由守卫：未登录用户访问受保护页面 → 跳 /login。
// token 过期场景由 ApiClient 在请求 401 时自动 refresh；refresh 失败则
// 清除 token 并重定向到 /login（见 client.ts::redirectToLogin），与守卫协同兜底。
//
// 开发模式绕过：设 VITE_DEV_BYPASS_AUTH=1 时，沙箱/CI 环境无需真实登录，
// AuthGuard 在 localStorage 注入 fake token，apiClient 会自动带 Bearer 头，
// 后端配合 DEV_BYPASS_AUTH=1 环境变量跳过 JWT 校验。
// 生产构建只要不设该环境变量即不生效。
const DEV_BYPASS =
  ((import.meta as { env?: Record<string, string | undefined> }).env ?? {})
    ?.VITE_DEV_BYPASS_AUTH === "1";

const DEV_TOKEN_KEY = "job_assistant_token";
const DEV_FAKE_TOKEN = "dev-bypass-token";

export default function AuthGuard({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const location = useLocation();

  if (DEV_BYPASS) {
    // dev 模式：localStorage 注入 fake token（apiClient 默认 accessor 读它）
    try {
      if (!localStorage.getItem(DEV_TOKEN_KEY)) {
        localStorage.setItem(DEV_TOKEN_KEY, DEV_FAKE_TOKEN);
      }
    } catch {
      /* localStorage 不可用时静默忽略 */
    }
    return <>{children}</>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}
