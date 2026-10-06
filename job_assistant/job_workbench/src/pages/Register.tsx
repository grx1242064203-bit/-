import { useState, useRef, type FormEvent, type KeyboardEvent, type ClipboardEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/authStore";
import logoImg from "../assets/logo.png";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Register() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [xhsOrderId, setXhsOrderId] = useState("");
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
    if (xhsOrderId.trim().length < 4) {
      setFormError("请输入小红书订单号（至少 4 位）");
      return false;
    }
    return true;
  };

  const handleRegister = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    if (!validateRegister()) return;
    const result = await register(email, password, xhsOrderId.trim());
    if (result.needs_verify) {
      setRegistered(true);
      setTimeout(() => inputs.current[0]?.focus(), 0);
    } else {
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
    "glass-soft w-full rounded-xl px-4 py-3 text-text outline-none transition focus:ring-2 focus:ring-primary/30";

  return (
    <div className="flex min-h-screen items-center justify-center p-4 sm:p-6">
      <div className="app-window w-full max-w-md p-8 sm:p-10">
        <div className="mb-8 text-center">
          <img
            src={logoImg}
            alt="Offer搭子"
            className="mx-auto mb-3 h-16 w-16 rounded-2xl object-contain drop-shadow-md"
          />
          <h1 className="text-2xl font-bold text-text">
            {registered ? "输入验证码" : "注册 Offer搭子"}
          </h1>
          <p className="mt-2 text-sm text-text-muted">
            {registered
              ? `验证码已发送至 ${email}`
              : "创建账号开启求职工作台"}
          </p>
        </div>

        {displayError && (
          <div className="mb-4 rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger">
            {displayError}
          </div>
        )}

        {!registered ? (
          <form onSubmit={handleRegister} className="space-y-4" noValidate>
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
                className={inputCls}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-text">
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
              <label className="mb-1 block text-sm font-medium text-text">
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
            <div>
              <label className="mb-1 block text-sm font-medium text-text">
                小红书订单号
              </label>
              <input
                type="text"
                value={xhsOrderId}
                onChange={(e) => setXhsOrderId(e.target.value)}
                placeholder="付款后获得，作为支付凭证（唯一）"
                className={inputCls}
              />
              <p className="mt-1 text-xs text-text-muted">
                每个订单号只能注册一次，退款会立即停用账号
              </p>
            </div>
            <button
              type="submit"
              disabled={isLoading}
              className="flex w-full items-center justify-center rounded-xl bg-primary px-4 py-3 font-semibold text-ink transition hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-ink border-t-transparent" />
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
                  className="glass-soft h-14 w-12 rounded-xl text-center text-2xl font-semibold text-text outline-none transition focus:ring-2 focus:ring-primary/30"
                />
              ))}
            </div>
            <button
              type="submit"
              disabled={isLoading}
              className="flex w-full items-center justify-center rounded-xl bg-primary px-4 py-3 font-semibold text-ink transition hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-ink border-t-transparent" />
                  验证中...
                </span>
              ) : (
                "验证"
              )}
            </button>
          </form>
        )}

        <p className="mt-6 text-center text-sm text-text-muted">
          已有账号？{" "}
          <Link
            to="/login"
            className="font-medium text-primary-dark transition hover:underline"
          >
            登录
          </Link>
        </p>
      </div>
    </div>
  );
}
