import type { ReactNode } from "react";
import { Routes, Route, Link } from "react-router-dom";
import Jobs from "./pages/Jobs";
import Resume from "./pages/Resume";
import Applications from "./pages/Applications";
import Login from "./pages/Login";
import Register from "./pages/Register";
import AuthGuard from "./components/AuthGuard";
import { useAuthStore } from "./stores/authStore";

// 受保护页面的统一布局：顶部导航 + 用户态 + 退出。
function Layout({ children }: { children: ReactNode }) {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const handleLogout = () => {
    logout();
    window.location.href = "/login";
  };

  return (
    <div className="min-h-screen bg-cream font-sans text-slate-deep">
      <nav className="flex items-center gap-6 bg-slate-deep px-6 py-4 text-cream">
        <span className="text-lg font-semibold text-brand">求职搭子</span>
        <Link to="/" className="transition hover:text-brand">
          岗位
        </Link>
        <Link to="/resume" className="transition hover:text-brand">
          简历
        </Link>
        <Link to="/applications" className="transition hover:text-brand">
          投递
        </Link>
        <div className="ml-auto flex items-center gap-4">
          {user?.email && (
            <span className="text-sm text-slate-300">{user.email}</span>
          )}
          <button
            type="button"
            onClick={handleLogout}
            className="text-sm text-cream transition hover:text-brand"
          >
            退出
          </button>
        </div>
      </nav>
      <main className="p-6">{children}</main>
    </div>
  );
}

// 路由配置：/login、/register 公开；/、/resume、/applications 受 AuthGuard 保护。
export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
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
