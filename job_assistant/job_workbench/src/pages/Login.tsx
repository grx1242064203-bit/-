import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/authStore";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const { login, isLoading, error } = useAuthStore();
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    if (!EMAIL_RE.test(email)) {
      setFormError("请输入有效的邮箱地址");
      return;
    }
    if (password.length < 6) {
      setFormError("密码至少 6 位");
      return;
    }
    const ok = await login(email, password);
    if (ok) navigate("/");
  };

  const displayError = formError || error;

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4 py-10">
      <div className="w-full max-w-md rounded-2xl bg-surface p-8 shadow-lg">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary">
            <span className="text-lg font-bold text-ink">求</span>
          </div>
          <h1 className="text-2xl font-bold text-text">登录求职搭子</h1>
          <p className="mt-2 text-sm text-text-muted">
            输入邮箱与密码，开启你的求职工作台
          </p>
        </div>

        {displayError && (
          <div className="mb-4 rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger">
            {displayError}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div>
            <label className="mb-1 block text-sm font-medium text-text">
              邮箱
            </label>
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full rounded-xl border border-border bg-surface-soft px-4 py-3 text-text outline-none transition focus:border-primary-dark focus:ring-2 focus:ring-primary/30"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-text">
              密码
            </label>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="至少 6 位"
              className="w-full rounded-xl border border-border bg-surface-soft px-4 py-3 text-text outline-none transition focus:border-primary-dark focus:ring-2 focus:ring-primary/30"
            />
          </div>
          <button
            type="submit"
            disabled={isLoading}
            className="flex w-full items-center justify-center rounded-xl bg-primary px-4 py-3 font-semibold text-ink transition hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isLoading ? (
              <span className="flex items-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-ink border-t-transparent" />
                登录中...
              </span>
            ) : (
              "登录"
            )}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-text-muted">
          还没账号？{" "}
          <Link
            to="/register"
            className="font-medium text-primary-dark transition hover:underline"
          >
            注册
          </Link>
        </p>
      </div>
    </div>
  );
}
