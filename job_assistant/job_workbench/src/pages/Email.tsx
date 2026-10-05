// 邮箱同步页：账户管理 + 邮件分类任务确认
import { useEffect, useState } from "react";
import { useEmailStore } from "../stores/emailStore";
import { extractErrorMessage } from "../api/client";
import {
  type EmailTask,
  type EmailDetail,
  type ExtractStatus,
  type TaskType,
} from "../api/emails";

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

const EXTRACT_BADGE: Record<
  ExtractStatus,
  { label: string; className: string }
> = {
  pending: {
    label: "AI 提取中",
    className: "bg-amber-200 text-amber-900 animate-pulse",
  },
  llm_done: {
    label: "AI 提取",
    className: "bg-primary-soft text-primary-ink",
  },
  llm_failed: {
    label: "提取失败",
    className: "bg-red-50 text-red-600",
  },
  rule_fallback: {
    label: "规则提取",
    className: "bg-gray-100 text-text-muted",
  },
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

function ImapHelp() {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg bg-amber-100 p-3">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="text-xs font-medium text-amber-900">
          如何获取 IMAP 授权码？{open ? "收起" : "展开"}
        </span>
        <span className="text-amber-800">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="mt-2 space-y-2 text-[11px] leading-relaxed text-text-muted">
          <div>
            <a
              href="https://service.mail.qq.com/detail/0/75"
              target="_blank"
              rel="noreferrer"
              className="font-medium text-primary-dark hover:underline"
            >
              QQ 邮箱 / Foxmail
            </a>
            <p>设置 → 账户 → 开启「IMAP/SMTP服务」→ 点击「生成授权码」→ 短信验证后复制授权码</p>
          </div>
          <div>
            <a
              href="https://help.mail.163.com/faq.do?m=list&categoryID=171"
              target="_blank"
              rel="noreferrer"
              className="font-medium text-primary-dark hover:underline"
            >
              163 / 126 邮箱
            </a>
            <p>设置 → POP3/SMTP/IMAP → 开启 IMAP → 设置「客户端授权密码」</p>
          </div>
          <div>
            <a
              href="https://support.google.com/mail/answer/185833"
              target="_blank"
              rel="noreferrer"
              className="font-medium text-primary-dark hover:underline"
            >
              Gmail
            </a>
            <p>先开启「两步验证」→ Google 账号 → 安全 → 应用专用密码 → 生成 16 位密码</p>
          </div>
          <div>
            <a
              href="https://support.microsoft.com/zh-cn/account-billing/5896ed9b-4263-e681-128a-a6f2979a7944"
              target="_blank"
              rel="noreferrer"
              className="font-medium text-primary-dark hover:underline"
            >
              Outlook / Hotmail
            </a>
            <p>先开启「两步验证」→ 安全 → 高级安全选项 → 应用密码 → 创建并复制</p>
          </div>
          <p className="pt-1 text-amber-800">
            💡 授权码一般是一串字母，粘贴到上方「密码/授权码」框即可。
          </p>
        </div>
      )}
    </div>
  );
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
      setError(extractErrorMessage(e));
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
            <p className="mt-1 text-[11px] text-text-muted">
              ⚠️ 这里填的是 <b>IMAP 授权码</b>，不是邮箱登录密码。需要先在邮箱设置里开启 IMAP 并生成授权码。
            </p>
          </div>
          <ImapHelp />
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

function EmailDetailModal({
  emailId,
  onClose,
}: {
  emailId: string;
  onClose: () => void;
}) {
  const getEmail = useEmailStore((s) => s.getEmail);
  const [email, setEmail] = useState<EmailDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"text" | "html">("text");

  useEffect(() => {
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const detail = await getEmail(emailId);
        setEmail(detail);
        // 优先 html，没 html 用 text
        setViewMode(detail.body_html ? "html" : "text");
      } catch (e) {
        setError(extractErrorMessage(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [emailId, getEmail]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">📬 邮件原文</h3>
          <button
            onClick={onClose}
            className="rounded-lg px-3 py-1 text-sm text-text-muted hover:bg-gray-100"
          >
            关闭
          </button>
        </div>
        {loading ? (
          <p className="py-8 text-center text-sm text-text-muted">加载中...</p>
        ) : error ? (
          <p className="py-8 text-center text-sm text-red-500">{error}</p>
        ) : email ? (
          <div className="space-y-3">
            <div className="rounded-lg border border-line bg-gray-50 p-3 text-xs">
              <div className="grid grid-cols-[80px_1fr] gap-1">
                <div className="text-text-muted">主题</div>
                <div className="font-medium text-text">
                  {email.subject || "（无主题）"}
                </div>
                <div className="text-text-muted">发件人</div>
                <div className="text-text">{email.sender || "（无）"}</div>
                <div className="text-text-muted">收件时间</div>
                <div className="text-text">
                  {email.received_at
                    ? new Date(email.received_at).toLocaleString("zh-CN")
                    : "（无）"}
                </div>
              </div>
            </div>
            {email.body_html && email.body_text && (
              <div className="flex gap-2">
                <button
                  onClick={() => setViewMode("text")}
                  className={`rounded-lg px-3 py-1 text-xs ${
                    viewMode === "text"
                      ? "bg-primary text-ink"
                      : "bg-gray-100 text-text-muted"
                  }`}
                >
                  纯文本
                </button>
                <button
                  onClick={() => setViewMode("html")}
                  className={`rounded-lg px-3 py-1 text-xs ${
                    viewMode === "html"
                      ? "bg-primary text-ink"
                      : "bg-gray-100 text-text-muted"
                  }`}
                >
                  HTML
                </button>
              </div>
            )}
            <div className="max-h-[50vh] overflow-y-auto rounded-lg border border-line p-3 text-xs">
              {viewMode === "html" && email.body_html ? (
                <div
                  className="prose prose-sm max-w-none"
                  // eslint-disable-next-line react/no-danger
                  dangerouslySetInnerHTML={{ __html: email.body_html }}
                />
              ) : (
                <pre className="whitespace-pre-wrap break-words font-sans text-text">
                  {email.body_text || email.body_html || "（无正文）"}
                </pre>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function TaskCard({ task }: { task: EmailTask }) {
  const confirmTask = useEmailStore((s) => s.confirmTask);
  const ignoreTask = useEmailStore((s) => s.ignoreTask);
  const reextractTask = useEmailStore((s) => s.reextractTask);
  const error = useEmailStore((s) => s.error);
  const [busy, setBusy] = useState(false);
  const [showEmail, setShowEmail] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const handleConfirm = async () => {
    setBusy(true);
    setLocalError(null);
    try {
      await confirmTask(task.id);
    } catch (e) {
      setLocalError(extractErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const handleReextract = async () => {
    setBusy(true);
    try {
      await reextractTask(task.id);
    } finally {
      setBusy(false);
    }
  };

  // 时间显示：AI 提取中时可能为 null
  const time = task.event_time
    ? new Date(task.event_time).toLocaleString("zh-CN")
    : task.extract_status === "pending"
      ? "AI 提取中..."
      : "未识别时间";

  // 公司/岗位：AI 提取中时显示占位
  const companyLabel = task.company || (
    task.extract_status === "pending" ? "提取中..." : "未知公司"
  );
  const jobTitle = task.job_title || "";

  // 截图显示来源：邮件主题/发件人（list_tasks 接口已回填）
  const subject = task.email_subject || "";
  const sender = task.email_sender || "";

  const extractBadge = EXTRACT_BADGE[task.extract_status];

  return (
    <div className="rounded-xl border border-line bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${TYPE_COLOR[task.task_type]}`}
            >
              {TYPE_LABEL[task.task_type]}
            </span>
            <span className="text-sm font-semibold text-text">
              {companyLabel}
            </span>
            {jobTitle && (
              <span className="text-sm text-text-muted">· {jobTitle}</span>
            )}
            <span
              className={`rounded-full px-1.5 py-0.5 text-[10px] ${extractBadge.className}`}
            >
              {extractBadge.label}
            </span>
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
          {/* 邮件上下文预览 */}
          {(subject || sender) && (
            <div className="mt-2 rounded bg-gray-50 px-2 py-1 text-[11px] text-text-muted">
              {subject && <div className="truncate">📬 {subject}</div>}
              {sender && (
                <div className="truncate text-text-muted">
                  ↪ {sender} ·{" "}
                  {task.email_received_at
                    ? new Date(task.email_received_at).toLocaleString("zh-CN")
                    : ""}
                </div>
              )}
            </div>
          )}
        </div>
        <div className="flex flex-col gap-1">
          <button
            onClick={handleConfirm}
            disabled={busy || task.extract_status === "pending"}
            className="rounded-lg bg-success px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
            title={task.extract_status === "pending" ? "AI 提取完成后才能确认" : ""}
          >
            确认
          </button>
          <button
            onClick={() => setShowEmail(true)}
            className="rounded-lg bg-primary-soft px-3 py-1.5 text-xs font-medium text-primary-ink hover:bg-primary/20"
          >
            查看邮件
          </button>
          <button
            onClick={handleReextract}
            disabled={busy || task.extract_status === "pending"}
            className="rounded-lg bg-gray-100 px-3 py-1.5 text-xs text-text-muted hover:bg-gray-200 disabled:opacity-50"
            title="对提取结果不满意？点此用 AI 重新提取"
          >
            ✨ 重新提取
          </button>
          <button
            onClick={() => ignoreTask(task.id)}
            className="rounded-lg bg-gray-100 px-3 py-1.5 text-xs text-text-muted hover:bg-gray-200"
          >
            忽略
          </button>
        </div>
      </div>
      {(localError || (error && task.extract_status !== "pending")) && (
        <div className="mt-2 rounded-lg bg-red-50 px-3 py-1.5 text-[11px] text-red-700">
          ⚠️ {localError || error}
        </div>
      )}
      {showEmail && task.email_id && (
        <EmailDetailModal
          emailId={task.email_id}
          onClose={() => setShowEmail(false)}
        />
      )}
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
    // 每 30s 轮询一次 pending 任务，让异步 LLM 提取结果可见
    const timer = setInterval(() => {
      void loadTasks("pending");
    }, 30000);
    return () => clearInterval(timer);
  }, [loadAccounts, loadTasks]);

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600">{error}</div>
      )}

      {/* 自动化流程说明 */}
      <div className="rounded-xl border border-primary/30 bg-primary-soft/50 p-3 text-xs text-primary-ink">
        <div className="font-medium">✨ 邮件→日程全自动流程</div>
        <div className="mt-1 text-text-muted">
          ① 同步邮件 → ② 关键词初筛（测评/笔试/面试/一面/二面/终面） →
          ③ AI 异步提取公司/岗位/时间/链接 → ④ 你确认 →
          ⑤ 自动创建投递记录 + 日程 + 提醒
        </div>
      </div>

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
                    className="rounded-lg bg-primary-soft px-3 py-1.5 text-xs font-medium text-primary-ink disabled:opacity-50"
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
