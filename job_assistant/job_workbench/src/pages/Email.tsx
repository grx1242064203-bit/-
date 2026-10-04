// 邮箱同步页：账户管理 + 邮件分类任务确认
import { useEffect, useState } from "react";
import { useEmailStore } from "../stores/emailStore";
import type { EmailTask, TaskType } from "../api/emails";

const TYPE_LABEL: Record<TaskType, string> = {
  assessment: "测评",
  written: "笔试",
  interview: "面试",
};

const TYPE_COLOR: Record<TaskType, string> = {
  assessment: "bg-info text-info-foreground",
  written: "bg-warning text-warning-foreground",
  interview: "bg-success text-success-foreground",
};

const IMAP_PRESETS: Record<string, { server: string; port: number }> = {
  qq: { server: "imap.qq.com", port: 993 },
  "163": { server: "imap.163.com", port: 993 },
  "126": { server: "imap.126.com", port: 993 },
  gmail: { server: "imap.gmail.com", port: 993 },
  outlook: { server: "outlook.office365.com", port: 993 },
  foxmail: { server: "imap.qq.com", port: 993 },
};

function guessImap(email: string): { server: string; port: number } {
  const domain = email.split("@")[1]?.toLowerCase() ?? "";
  for (const key of Object.keys(IMAP_PRESETS)) {
    if (domain.includes(key)) return IMAP_PRESETS[key];
  }
  return { server: `imap.${domain}`, port: 993 };
}

function AddAccountModal({ onClose }: { onClose: () => void }) {
  const addAccount = useEmailStore((s) => s.addAccount);
  const [email, setEmail] = useState("");
  const [imapServer, setImapServer] = useState("");
  const [imapPort, setImapPort] = useState(993);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleEmailBlur = () => {
    if (email && !imapServer) {
      const preset = guessImap(email);
      setImapServer(preset.server);
      setImapPort(preset.port);
    }
    if (email && !username) setUsername(email);
  };

  const handleSubmit = async () => {
    if (!email || !imapServer || !username || !password) {
      setError("请填写完整");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await addAccount({ email, imap_server: imapServer, imap_port: imapPort, username, password });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "添加失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <h3 className="mb-4 text-lg font-semibold">添加邮箱账户</h3>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-text-muted">邮箱地址</label>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onBlur={handleEmailBlur}
              placeholder="your@email.com"
              className="w-full rounded-lg border border-line px-3 py-2 text-sm"
            />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div className="col-span-2">
              <label className="mb-1 block text-xs text-text-muted">IMAP 服务器</label>
              <input
                value={imapServer}
                onChange={(e) => setImapServer(e.target.value)}
                placeholder="imap.example.com"
                className="w-full rounded-lg border border-line px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-text-muted">端口</label>
              <input
                type="number"
                value={imapPort}
                onChange={(e) => setImapPort(Number(e.target.value))}
                className="w-full rounded-lg border border-line px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-text-muted">用户名</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg border border-line px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-text-muted">密码 / 授权码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="IMAP 授权码（非登录密码）"
              className="w-full rounded-lg border border-line px-3 py-2 text-sm"
            />
          </div>
          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-text-muted hover:bg-gray-100"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={busy}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-ink disabled:opacity-50"
          >
            {busy ? "测试连接中..." : "添加"}
          </button>
        </div>
      </div>
    </div>
  );
}

function TaskCard({ task }: { task: EmailTask }) {
  const confirmTask = useEmailStore((s) => s.confirmTask);
  const ignoreTask = useEmailStore((s) => s.ignoreTask);
  const [busy, setBusy] = useState(false);

  const handleConfirm = async () => {
    setBusy(true);
    try {
      await confirmTask(task.id);
    } finally {
      setBusy(false);
    }
  };

  const time = task.event_time
    ? new Date(task.event_time).toLocaleString("zh-CN")
    : "未识别时间";

  return (
    <div className="rounded-xl border border-line bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="mb-1 flex items-center gap-2">
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${TYPE_COLOR[task.task_type]}`}
            >
              {TYPE_LABEL[task.task_type]}
            </span>
            <span className="text-sm font-semibold text-text">
              {task.company || "未知公司"}
            </span>
            {task.job_title && (
              <span className="text-sm text-text-muted">· {task.job_title}</span>
            )}
          </div>
          <div className="text-xs text-text-muted">⏰ {time}</div>
          {task.event_link && (
            <a
              href={task.event_link}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-block max-w-full truncate text-xs text-primary-dark hover:underline"
            >
              🔗 {task.event_link}
            </a>
          )}
        </div>
        <div className="flex gap-1">
          <button
            onClick={handleConfirm}
            disabled={busy}
            className="rounded-lg bg-success px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
          >
            确认
          </button>
          <button
            onClick={() => ignoreTask(task.id)}
            className="rounded-lg bg-gray-100 px-3 py-1.5 text-xs text-text-muted hover:bg-gray-200"
          >
            忽略
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Email() {
  const { accounts, tasks, loading, syncing, error, loadAccounts, loadTasks, syncAccount, removeAccount } =
    useEmailStore();
  const [showAdd, setShowAdd] = useState(false);

  useEffect(() => {
    void loadAccounts();
    void loadTasks("pending");
  }, [loadAccounts, loadTasks]);

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600">{error}</div>
      )}

      {/* 邮箱账户 */}
      <section className="rounded-2xl border border-line bg-white/60 p-5 backdrop-blur">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold">邮箱账户</h2>
          <button
            onClick={() => setShowAdd(true)}
            className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-ink"
          >
            + 添加邮箱
          </button>
        </div>

        {accounts.length === 0 ? (
          <p className="py-8 text-center text-sm text-text-muted">
            还没有绑定邮箱。添加邮箱后可自动抓取测评/笔试/面试邀请。
          </p>
        ) : (
          <div className="space-y-2">
            {accounts.map((a) => (
              <div
                key={a.id}
                className="flex items-center justify-between rounded-lg border border-line bg-white px-4 py-3"
              >
                <div>
                  <div className="text-sm font-medium text-text">{a.email}</div>
                  <div className="text-xs text-text-muted">
                    {a.imap_server}:{a.imap_port} · 上次同步{" "}
                    {a.last_sync_at
                      ? new Date(a.last_sync_at).toLocaleString("zh-CN")
                      : "未同步"}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => syncAccount(a.id)}
                    disabled={syncing}
                    className="rounded-lg bg-primary-soft px-3 py-1.5 text-xs font-medium text-primary-dark disabled:opacity-50"
                  >
                    {syncing ? "同步中..." : "同步邮件"}
                  </button>
                  <button
                    onClick={() => removeAccount(a.id)}
                    className="rounded-lg bg-red-50 px-3 py-1.5 text-xs text-red-500 hover:bg-red-100"
                  >
                    删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* 待确认任务 */}
      <section className="rounded-2xl border border-line bg-white/60 p-5 backdrop-blur">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold">
            待确认任务 <span className="text-sm text-text-muted">({tasks.length})</span>
          </h2>
          <button
            onClick={() => loadTasks("pending")}
            className="text-xs text-primary-dark hover:underline"
          >
            刷新
          </button>
        </div>

        {loading ? (
          <p className="py-8 text-center text-sm text-text-muted">加载中...</p>
        ) : tasks.length === 0 ? (
          <p className="py-8 text-center text-sm text-text-muted">
            暂无待确认任务。同步邮件后，测评/笔试/面试邀请会出现在这里。
          </p>
        ) : (
          <div className="space-y-3">
            {tasks.map((t) => (
              <TaskCard key={t.id} task={t} />
            ))}
          </div>
        )}
      </section>

      {showAdd && <AddAccountModal onClose={() => setShowAdd(false)} />}
    </div>
  );
}
