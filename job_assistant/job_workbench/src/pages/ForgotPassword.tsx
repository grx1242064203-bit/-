// 忘记密码页：分两步——输入邮箱发验证码 → 输入验证码+新密码重置。
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authApi } from "../api/auth";
import { extractErrorMessage } from "../api/client";
import logoImg from "../assets/logo.png";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type Step = "request" | "reset" | "done";

export default function ForgotPassword() {
  const [step, setStep] = useState<Step>("request");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const handleSendCode = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!EMAIL_RE.test(email)) {
      setError("请输入有效的邮箱地址");
      return;
    }
    setLoading(true);
    try {
      await authApi.forgotPassword(email);
      setStep("reset");
    } catch (e) {
      setError(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!/^\d{6}$/.test(code)) {
      setError("验证码为 6 位数字");
      return;
    }
    if (newPwd.length < 6) {
      setError("新密码至少 6 位");
      return;
    }
    if (newPwd !== confirmPwd) {
      setError("两次输入的新密码不一致");
      return;
    }
    setLoading(true);
    try {
      await authApi.resetPassword(email, code, newPwd);
      setStep("done");
    } catch (e) {
      setError(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4 sm:p-6">
      <div className="app-window flex w-full max-w-md flex-col items-center justify-center p-8 sm:p-10">
        <div className="mb-6 text-center">
          <img
            src={logoImg}
            alt="Offer搭子"
            className="mx-auto mb-3 h-16 w-16 rounded-2xl object-contain drop-shadow-md"
          />
          <h1 className="text-2xl font-bold text-text">重置密码</h1>
        </div>

        {error && (
          <div className="mb-4 w-full rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger">
            {error}
          </div>
        )}

        {step === "request" && (
          <form onSubmit={handleSendCode} className="w-full space-y-4" noValidate>
            <p className="text-center text-sm text-text-muted">
              输入注册邮箱，我们会发送 6 位验证码
            </p>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="glass-soft w-full rounded-xl px-4 py-3 text-text outline-none focus:ring-2 focus:ring-primary/30"
            />
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-primary px-4 py-3 font-semibold text-ink hover:bg-primary-dark disabled:opacity-60"
            >
              {loading ? "发送中..." : "发送验证码"}
            </button>
          </form>
        )}

        {step === "reset" && (
          <form onSubmit={handleReset} className="w-full space-y-4" noValidate>
            <p className="text-center text-sm text-text-muted">
              验证码已发送至 <span className="font-medium text-text">{email}</span>
            </p>
            <input
              type="text"
              required
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              placeholder="6 位验证码"
              className="glass-soft w-full rounded-xl px-4 py-3 text-center text-lg tracking-widest text-text outline-none focus:ring-2 focus:ring-primary/30"
            />
            <input
              type="password"
              required
              minLength={6}
              value={newPwd}
              onChange={(e) => setNewPwd(e.target.value)}
              placeholder="新密码（至少 6 位）"
              className="glass-soft w-full rounded-xl px-4 py-3 text-text outline-none focus:ring-2 focus:ring-primary/30"
            />
            <input
              type="password"
              required
              minLength={6}
              value={confirmPwd}
              onChange={(e) => setConfirmPwd(e.target.value)}
              placeholder="确认新密码"
              className="glass-soft w-full rounded-xl px-4 py-3 text-text outline-none focus:ring-2 focus:ring-primary/30"
            />
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-primary px-4 py-3 font-semibold text-ink hover:bg-primary-dark disabled:opacity-60"
            >
              {loading ? "重置中..." : "重置密码"}
            </button>
          </form>
        )}

        {step === "done" && (
          <div className="w-full space-y-4 text-center">
            <div className="text-4xl">✅</div>
            <p className="text-sm text-text">
              密码已重置，请用新密码登录
            </p>
            <button
              type="button"
              onClick={() => navigate("/login")}
              className="w-full rounded-xl bg-primary px-4 py-3 font-semibold text-ink hover:bg-primary-dark"
            >
              去登录
            </button>
          </div>
        )}

        <p className="mt-6 text-center text-sm text-text-muted">
          <Link
            to="/login"
            className="font-medium text-primary-dark transition hover:underline"
          >
            返回登录
          </Link>
        </p>
      </div>
    </div>
  );
}
