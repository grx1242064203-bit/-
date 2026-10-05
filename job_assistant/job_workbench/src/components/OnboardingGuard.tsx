import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore } from "../stores/authStore";
import { useResumeStore } from "../stores/resumeStore";

// Onboarding 守卫:已登录但未上传简历,且当前在岗位列表 / 时 → 跳 /welcome 引导。
// 设计原则:
// 1. 只拦截 / (登录后默认落地页),其他业务页面(公司/投递/邮件/日程)不强制引导,
//    避免用户在多个页面间跳转时反复触发跳转。
// 2. /welcome / /resume / /login / /register 自身放行,避免循环。
// 3. 已上传简历的用户直接放行。
const ONBOARDING_TRIGGER_PATH = "/";
const ONBOARDING_FREE_PATHS = new Set(["/welcome", "/resume", "/login", "/register"]);

export default function OnboardingGuard({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const activeResume = useResumeStore((s) => s.activeResume);
  const location = useLocation();

  if (!isAuthenticated) return <>{children}</>;
  if (ONBOARDING_FREE_PATHS.has(location.pathname)) return <>{children}</>;
  // 仅在登录后默认落地页 / 触发引导,其他页面放行
  if (location.pathname !== ONBOARDING_TRIGGER_PATH) return <>{children}</>;

  if (!activeResume) {
    return <Navigate to="/welcome" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}
