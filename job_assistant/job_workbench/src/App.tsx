import type { ReactNode } from "react";
import { NavLink, Routes, Route, useLocation } from "react-router-dom";
import Jobs from "./pages/Jobs";
import Companies from "./pages/Companies";
import Resume from "./pages/Resume";
import Applications from "./pages/Applications";
import Login from "./pages/Login";
import Register from "./pages/Register";
import AuthGuard from "./components/AuthGuard";
import { useAuthStore } from "./stores/authStore";
import SyncIndicator from "./components/SyncIndicator";

// 侧边栏导航项
interface NavItem {
  to: string;
  label: string;
  icon: string;
  end?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/companies", label: "公司总览", icon: "🏢" },
  { to: "/", label: "岗位列表", icon: "💼", end: true },
  { to: "/applications", label: "投递控制台", icon: "📋" },
  { to: "/resume", label: "简历解析", icon: "📄" },
];

function Sidebar() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const location = useLocation();

  const handleLogout = () => {
    logout();
    window.location.href = "/login";
  };

  return (
    <aside className="flex h-screen w-60 flex-shrink-0 flex-col bg-sidebar text-white">
      {/* Logo */}
      <div className="flex items-center gap-3 px-6 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent text-lg font-bold">
          搭
        </div>
        <div>
          <div className="text-base font-semibold">求职搭子</div>
          <div className="text-xs text-gray-400">27届校招工作台</div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {NAV_ITEMS.map((item) => {
          const isActive = item.end
            ? location.pathname === item.to
            : location.pathname.startsWith(item.to);
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={`flex items-center gap-3 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-primary text-white"
                  : "text-gray-300 hover:bg-white/5 hover:text-white"
              }`}
            >
              <span className="text-base">{item.icon}</span>
              {item.label}
            </NavLink>
          );
        })}
      </nav>

      {/* User */}
      <div className="border-t border-white/10 p-4">
        {user?.email && (
          <div className="mb-3 truncate text-xs text-gray-400">{user.email}</div>
        )}
        <button
          type="button"
          onClick={handleLogout}
          className="w-full rounded-lg border border-white/10 px-4 py-2 text-sm text-gray-300 transition hover:bg-white/5 hover:text-white"
        >
          退出登录
        </button>
      </div>
    </aside>
  );
}

function TopBar() {
  const location = useLocation();
  const titleMap: Record<string, string> = {
    "/companies": "秋招公司总览",
    "/": "岗位列表",
    "/applications": "投递控制台",
    "/resume": "简历解析",
  };
  const title = titleMap[location.pathname] ?? "求职搭子";
  return (
    <header className="flex h-14 items-center justify-between border-b border-gray-200 bg-surface px-6">
      <div className="flex items-center gap-4">
        <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
      </div>
      <div className="flex items-center gap-4">
        <SyncIndicator />
      </div>
    </header>
  );
}

function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/companies"
        element={
          <AuthGuard>
            <Layout>
              <Companies />
            </Layout>
          </AuthGuard>
        }
      />
      <Route
        path="/"
        element={
          <AuthGuard>
            <Layout>
              <Jobs />
            </Layout>
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
            <Layout>
              <Applications />
            </Layout>
          </AuthGuard>
        }
      />
    </Routes>
  );
}
