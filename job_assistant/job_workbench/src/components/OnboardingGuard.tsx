import type { ReactNode } from "react";
import { useAuthStore } from "../stores/authStore";
import { useResumeStore } from "../stores/resumeStore";

// Onboarding 守卫(V2 简化版):
// 设计原则:不强制拦截,只在用户首次登录且无简历时,引导一次到 /welcome。
// 用 localStorage 标记 onboarding_completed,避免重复引导。
// 用户在 /welcome 选"稍后再说"或上传简历后,标记完成,永不再引导。
// 其他业务路由(//applications /email 等)不被拦截,用户可自由浏览岗位。
const ONBOARDING_KEY = "onboarding_completed";

export default function OnboardingGuard({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const activeResume = useResumeStore((s) => s.activeResume);

  if (!isAuthenticated) return <>{children}</>;

  // 已上传简历 → 标记完成,放行
  if (activeResume) {
    try {
      localStorage.setItem(ONBOARDING_KEY, "1");
    } catch {
      /* localStorage 不可用时静默 */
    }
    return <>{children}</>;
  }

  // 未上传简历,但已标记完成(用户曾选"稍后再说"或上传过又清空)→ 放行
  try {
    if (localStorage.getItem(ONBOARDING_KEY) === "1") {
      return <>{children}</>;
    }
  } catch {
    /* 静默 */
  }

  // 首次登录且无简历 → 不强制跳转,放行让用户自由浏览
  // Welcome 页作为 /welcome 可选路由,用户可主动访问
  return <>{children}</>;
}
