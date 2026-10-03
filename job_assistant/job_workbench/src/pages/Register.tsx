import { useState, useRef, type FormEvent, type KeyboardEvent, type ClipboardEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/authStore";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Register() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [registered, setRegistered] = useState(false);
  const [code, setCode] = useState<string[]>(["", "", "", "", "", ""]);
  const inputs = useRef<(HTMLInputElement | null)[]>([]);
  const { register, verifyEmail, isLoading, error } = useAuthStore();
  const navigate = useNavigate();

  const validateRegister = () => {
    if (!EMAIL_RE.test(email)) {
      setFormError("请输入有效的邮箱地址");
      return false;
    }
    if (password.length < 6) {
      setFormError("密码至少 6 位");
      return false;
    }
    if (password !== confirm) {
      setFormError("两次输入的密码不一致");
      return false;
    }
    return true;
  };

  const handleRegister = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    if (!validateRegister()) return;
    const result = await register(email, password);
    if (result.needs_verify) {
      setRegistered(true);
      setTimeout(() => inputs.current[0]?.focus(), 0);
    } else {
      // 不需要验证（理论上不会出现），回登录页直接登录。
      navigate("/login");
    }
  };

  const handleCodeChange = (i: number, val: string) => {
    const digit = val.replace(/\D/g, "").slice(-1);
    setCode((prev) => {
      const next = [...prev];
      next[i] = digit;
      return next;
    });
    if (digit && i < 5) inputs.current[i + 1]?.focus();
  };

  const handleCodeKey = (i: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !code[i] && i > 0) {
      inputs.current[i - 1]?.focus();
    }
  };

  const handleCodePaste = (e: ClipboardEvent) => {
    e.preventDefault();
    const text = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (!text) return;
    const next = ["", "", "", "", "", ""];
    text.split("").forEach((c, idx) => {
      next[idx] = c;
    });
    setCode(next);
    inputs.current[Math.min(text.length, 5)]?.focus();
  };

  const handleVerify = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    const fullCode = code.join("");
    if (fullCode.length !== 6) {
      setFormError("请输入完整的 6 位验证码");
      return;
    }
    const ok = await verifyEmail(email, fullCode);
    if (ok) navigate("/");
  };

  const displayError = formError || error;

  const inputCls =
    "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-slate-deep outline-none transition focus:border-brand focus:ring-2 focus:ring-brand-100";

  return (
    <div className="flex min-h-screen items-center justify-center bg-cream px-4 py-10">
      <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-card">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50">
            <span className="text-lg font-semibold text-brand">求</span>
          </div>
          <h1 className="text-2xl font-semibold text-slate-deep">
            {registered ? "输入验证码" : "注册求职搭子"}
          </h1>
          <p className="mt-2 text-sm text-slate-500">
            {registered
              ? `验证码已发送至 ${email}`
              : "创建账号开启求职工作台"}
          </p>
        </div>

        {displayError && (
          <div className="mb-4 rounded-2xl bg-brand-50 px-4 py-3 text-sm text-brand-700">
            {displayError}
          </div>
        )}

        {!registered ? (
          <form onSubmit={handleRegister} className="space-y-4" noValidate>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-deep">
                邮箱
              </label>
              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className={inputCls}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-deep">
                密码
              </label>
              <input
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="至少 6 位"
                className={inputCls}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-deep">
                确认密码
              </label>
              <input
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="再次输入密码"
                className={inputCls}
              />
            </div>
            <button
              type="submit"
              disabled={isLoading}
              className="flex w-full items-center justify-center rounded-2xl bg-brand px-4 py-3 font-medium text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  注册中...
                </span>
              ) : (
                "注册"
              )}
            </button>
          </form>
        ) : (
          <form onSubmit={handleVerify} className="space-y-6" noValidate>
            <div
              className="flex items-center justify-between gap-2"
              onPaste={handleCodePaste}
            >
              {code.map((d, i) => (
                <input
                  key={i}
                  ref={(el) => {
                    inputs.current[i] = el;
                  }}
                  type="text"
                  inputMode="numeric"
                  maxLength={1}
                  value={d}
                  onChange={(e) => handleCodeChange(i, e.target.value)}
                  onKeyDown={(e) => handleCodeKey(i, e)}
                  className="h-14 w-12 rounded-2xl border border-slate-200 bg-white text-center text-2xl font-semibold text-slate-deep outline-none transition focus:border-brand focus:ring-2 focus:ring-brand-100"
                />
              ))}
            </div>
            <button
              type="submit"
              disabled={isLoading}
              className="flex w-full items-center justify-center rounded-2xl bg-brand px-4 py-3 font-medium text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  验证中...
                </span>
              ) : (
                "验证"
              )}
            </button>
          </form>
        )}

        <p className="mt-6 text-center text-sm text-slate-500">
          已有账号？{" "}
          <Link
            to="/login"
            className="font-medium text-brand transition hover:text-brand-600"
          >
            登录
          </Link>
        </p>
      </div>
    </div>
  );
}
