// 设置页：修改密码。
import { useState } from "react";
import { authApi } from "../api/auth";
import { extractErrorMessage } from "../api/client";

export default function Settings() {
  const [oldPwd, setOldPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPwd.length < 6) {
      setError("新密码至少 6 位");
      return;
    }
    if (newPwd !== confirmPwd) {
      setError("两次输入的新密码不一致");
      return;
    }
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      await authApi.changePassword(oldPwd, newPwd);
      setSuccess("密码已修改，下次登录请用新密码");
      setOldPwd("");
      setNewPwd("");
      setConfirmPwd("");
    } catch (e) {
      setError(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  const handleForgotPassword = async () => {
    const email = prompt("输入你的注册邮箱，将发送重置验证码：");
    if (!email) return;
    try {
      await authApi.forgotPassword(email);
      alert("如果该邮箱已注册，重置验证码已发送，请查收邮件（含垃圾箱）");
    } catch (e) {
      alert(extractErrorMessage(e));
    }
  };

  return (
    <div className="mx-auto max-w-md space-y-4">
      <form
        onSubmit={handleSubmit}
        className="glass-soft rounded-lg border border-line p-6 space-y-4"
      >
        <h2 className="text-lg font-semibold text-text">修改密码</h2>
        <div>
          <label className="mb-1 block text-xs text-text-muted">旧密码</label>
          <input
            type="password"
            required
            value={oldPwd}
            onChange={(e) => setOldPwd(e.target.value)}
            className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-text-muted">新密码（≥6位）</label>
          <input
            type="password"
            required
            minLength={6}
            value={newPwd}
            onChange={(e) => setNewPwd(e.target.value)}
            className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-text-muted">确认新密码</label>
          <input
            type="password"
            required
            minLength={6}
            value={confirmPwd}
            onChange={(e) => setConfirmPwd(e.target.value)}
            className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm"
          />
        </div>
        {error && <div className="text-sm text-red-600">{error}</div>}
        {success && <div className="text-sm text-green-600">{success}</div>}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-md bg-ink py-2 text-sm text-white hover:opacity-90 disabled:opacity-50"
        >
          {loading ? "提交中…" : "修改密码"}
        </button>
      </form>

      <div className="glass-soft rounded-lg border border-line p-4 text-center text-sm">
        <span className="text-text-muted">忘记密码？</span>
        <button
          type="button"
          onClick={handleForgotPassword}
          className="ml-2 text-primary hover:underline"
        >
          通过邮箱验证码重置
        </button>
      </div>
    </div>
  );
}
