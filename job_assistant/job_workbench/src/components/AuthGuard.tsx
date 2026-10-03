import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore } from "../stores/authStore";

// 路由守卫：未登录用户访问受保护页面 → 跳 /login。
// token 过期场景由 ApiClient 在请求 401 时自动 refresh；refresh 失败则
// 清除 token 并重定向到 /login（见 client.ts::redirectToLogin），与守卫协同兜底。
export default function AuthGuard({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}
