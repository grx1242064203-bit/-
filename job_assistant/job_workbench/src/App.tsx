import type { ReactNode } from "react";
import { NavLink, Routes, Route, useLocation } from "react-router-dom";
import Jobs from "./pages/Jobs";
import Companies from "./pages/Companies";
import Resume from "./pages/Resume";
import Applications from "./pages/Applications";
import Email from "./pages/Email";
import Schedules from "./pages/Schedules";
import AutoFill from "./pages/AutoFill";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ForgotPassword from "./pages/ForgotPassword";
import Welcome from "./pages/Welcome";
import Settings from "./pages/Settings";
import Admin from "./pages/Admin";
import AuthGuard from "./components/AuthGuard";
import OnboardingGuard from "./components/OnboardingGuard";
import { useAuthStore } from "./stores/authStore";
import SyncIndicator from "./components/SyncIndicator";
import ReminderPoller from "./components/ReminderPoller";
import logoImg from "./assets/logo.png";

// 顶部胶囊导航项
interface NavItem {
  to: string;
  label: string;
  icon: string;
  end?: boolean;
  adminOnly?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/companies", label: "公司总览", icon: "🏢" },
  { to: "/", label: "岗位列表", icon: "💼", end: true },
  { to: "/applications", label: "投递控制台", icon: "📋" },
  { to: "/autofill", label: "网申自动填写", icon: "⚡" },
  { to: "/email", label: "邮件同步", icon: "📧" },
  { to: "/schedules", label: "日程", icon: "📅" },
  { to: "/resume", label: "简历解析", icon: "📄" },
  { to: "/settings", label: "设置", icon: "⚙️" },
  { to: "/admin", label: "管理后台", icon: "🛡️", adminOnly: true },
];

// 管理员邮箱白名单（与后端 ADMIN_EMAIL 一致，仅用于在前端显示管理后台入口）
const ADMIN_EMAILS = (import.meta as { env?: Record<string, string | undefined> }).env
  ?.VITE_ADMIN_EMAILS?.split(",").map((s) => s.trim().toLowerCase()) ?? [];

function isAdminEmail(email?: string): boolean {
  if (!email) return false;
  if (ADMIN_EMAILS.length === 0) return false;
  return ADMIN_EMAILS.includes(email.toLowerCase());
}

function TopNav() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const location = useLocation();

  const handleLogout = () => {
    logout();
    window.location.href = "/login";
  };

  const visibleNavItems = NAV_ITEMS.filter(
    (item) => !item.adminOnly || isAdminEmail(user?.email),
  );

  return (
    <header className="glass-strong flex h-16 items-center justify-between border-b border-line px-6">
      {/* Logo */}
      <div className="flex items-center gap-3">
        <img
          src={logoImg}
          alt="Offer搭子"
          className="h-10 w-10 rounded-lg object-contain drop-shadow-sm"
        />
        <div>
          <div className="text-base font-semibold text-text">Offer搭子</div>
          <div className="text-[11px] text-text-muted">27届校招工作台</div>
        </div>
      </div>

      {/* 胶囊导航 */}
      <nav className="glass-soft flex items-center gap-1 rounded-pill p-1 shadow-sm">
        {visibleNavItems.map((item) => {
          const isActive = item.end
            ? location.pathname === item.to
            : location.pathname.startsWith(item.to);
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={`flex items-center gap-2 rounded-pill px-4 py-1.5 text-sm font-medium transition-all ${
                isActive
                  ? "bg-ink text-white shadow-sm"
                  : "text-text-muted hover:text-text"
              }`}
            >
              <span className="text-base">{item.icon}</span>
              {item.label}
            </NavLink>
          );
        })}
      </nav>

      {/* 右侧：用户 + 同步 + 退出 */}
      <div className="flex items-center gap-3">
        <SyncIndicator />
        {user?.email && (
          <div className="glass-soft flex items-center gap-2 rounded-pill px-3 py-1.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-pill bg-primary text-xs font-semibold text-ink">
              {user.email.slice(0, 1).toUpperCase()}
            </div>
            <span className="max-w-[120px] truncate text-xs text-text-muted">
              {user.email}
            </span>
          </div>
        )}
        <button
          type="button"
          onClick={handleLogout}
          className="glass-soft rounded-pill px-3 py-1.5 text-xs text-text-muted transition hover:text-text"
        >
          退出
        </button>
      </div>
    </header>
  );
}

function PageTitle() {
  const location = useLocation();
  const titleMap: Record<string, string> = {
    "/companies": "秋招公司总览",
    "/": "岗位列表",
    "/applications": "投递控制台",
    "/autofill": "网申自动填写",
    "/email": "邮件同步",
    "/schedules": "日程与提醒",
    "/resume": "简历解析",
    "/welcome": "欢迎",
    "/settings": "设置",
    "/admin": "管理后台",
  };
  const title = titleMap[location.pathname] ?? "Offer搭子";
  return (
    <div className="mb-5">
      <h1 className="text-2xl font-bold text-text">{title}</h1>
    </div>
  );
}

function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center p-3 sm:p-5">
      <div className="app-window flex h-[calc(100vh-1.5rem)] w-full max-w-[1440px] flex-col sm:h-[calc(100vh-2.5rem)]">
        <TopNav />
        <main className="flex-1 overflow-auto p-6">
          <PageTitle />
          {children}
        </main>
        <ReminderPoller />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route
        path="/welcome"
        element={
          <AuthGuard>
            <Layout>
              <Welcome />
            </Layout>
          </AuthGuard>
        }
      />
      <Route
        path="/companies"
        element={
          <AuthGuard>
            <OnboardingGuard>
              <Layout>
                <Companies />
              </Layout>
            </OnboardingGuard>
          </AuthGuard>
        }
      />
      <Route
        path="/"
        element={
          <AuthGuard>
            <OnboardingGuard>
              <Layout>
                <Jobs />
              </Layout>
            </OnboardingGuard>
          </AuthGuard>
        }
      />
      <Route
        path="/resume"
        element={
          <AuthGuard>
            <Layout>
              <Resume />
            </Layout>
          </AuthGuard>
        }
      />
      <Route
        path="/applications"
        element={
          <AuthGuard>
            <OnboardingGuard>
              <Layout>
                <Applications />
              </Layout>
            </OnboardingGuard>
          </AuthGuard>
        }
      />
      <Route
        path="/autofill"
        element={
          <AuthGuard>
            <OnboardingGuard>
              <Layout>
                <AutoFill />
              </Layout>
            </OnboardingGuard>
          </AuthGuard>
        }
      />
      <Route
        path="/email"
        element={
          <AuthGuard>
            <OnboardingGuard>
              <Layout>
                <Email />
              </Layout>
            </OnboardingGuard>
          </AuthGuard>
        }
      />
      <Route
        path="/schedules"
        element={
          <AuthGuard>
            <OnboardingGuard>
              <Layout>
                <Schedules />
              </Layout>
            </OnboardingGuard>
          </AuthGuard>
        }
      />
      <Route
        path="/settings"
        element={
          <AuthGuard>
            <Layout>
              <Settings />
            </Layout>
          </AuthGuard>
        }
      />
      <Route
        path="/admin"
        element={
          <AuthGuard>
            <Layout>
              <Admin />
            </Layout>
          </AuthGuard>
        }
      />
    </Routes>
  );
}
