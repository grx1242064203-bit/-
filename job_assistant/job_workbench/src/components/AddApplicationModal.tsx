import { useEffect, useState } from "react";
import {
  useAppStore,
  KANBAN_COLUMNS,
  nowIso,
  type Application,
  type ApplicationStatus,
} from "../stores/appStore";

interface Props {
  open: boolean;
  onClose: () => void;
}

// 生成 app_id：时间戳 + 短随机后缀，避免与现有记录撞号。
function genAppId(): string {
  return `app-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

// 手动输入场景的占位 job_id（无关联岗位）：时间戳 + 随机后缀，保留可追溯。
function genManualJobId(): string {
  return `manual-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

// 添加投递记录的模态框：选择岗位（从已有岗位列表选，或手动输入公司+岗位）+ 状态 + 备注。
// 用 fixed inset-0 + backdrop-blur 实现。
export default function AddApplicationModal({ open, onClose }: Props) {
  const { jobs, addApplication } = useAppStore();

  const [jobId, setJobId] = useState<string>("");
  const [company, setCompany] = useState("");
  const [title, setTitle] = useState("");
  const [status, setStatus] = useState<ApplicationStatus>("draft");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 模态打开时重置表单
  useEffect(() => {
    if (open) {
      setJobId("");
      setCompany("");
      setTitle("");
      setStatus("draft");
      setNotes("");
      setError(null);
    }
  }, [open]);

  // ESC 关闭
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  function handleJobPick(id: string) {
    setJobId(id);
    if (!id) {
      // 选"— 手动输入 —"清空预填
      setCompany("");
      setTitle("");
      return;
    }
    const job = jobs.find((j) => j.job_id === id);
    if (job) {
      setCompany(job.company);
      setTitle(job.title);
    }
  }

  async function handleSubmit() {
    setError(null);
    if (!company.trim() || !title.trim()) {
      setError("请填写公司名与岗位名");
      return;
    }
    setSubmitting(true);
    const now = nowIso();
    const app: Application = {
      app_id: genAppId(),
      job_id: jobId || genManualJobId(),
      status,
      applied_at: status === "draft" ? null : now,
      updated_at: now,
      notes: notes.trim() || null,
      source: "manual",
    };
    try {
      await addApplication(app);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-deep/40 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-[min(92vw,560px)] rounded-2xl bg-white p-6 shadow-card"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-deep">
            添加投递记录
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-deep"
            aria-label="关闭"
          >
            ✕
          </button>
        </div>

        <div className="space-y-3">
          {/* 关联岗位（可选） */}
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">
              关联岗位（可选）
            </label>
            <select
              value={jobId}
              onChange={(e) => handleJobPick(e.target.value)}
              className="w-full rounded-xl border border-orange-200 bg-orange-50/30 px-3 py-2 text-sm text-slate-deep focus:outline-none focus:ring-2 focus:ring-orange-400"
            >
              <option value="">— 手动输入公司+岗位 —</option>
              {jobs.map((j) => (
                <option key={j.job_id} value={j.job_id}>
                  {j.company} · {j.title}
                </option>
              ))}
            </select>
          </div>

          {/* 公司名 */}
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">
              公司名 <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder="如：字节跳动"
              className="w-full rounded-xl border border-orange-200 bg-orange-50/30 px-3 py-2 text-sm text-slate-deep placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-orange-400"
            />
          </div>

          {/* 岗位名 */}
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">
              岗位名 <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="如：前端工程师"
              className="w-full rounded-xl border border-orange-200 bg-orange-50/30 px-3 py-2 text-sm text-slate-deep placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-orange-400"
            />
          </div>

          {/* 状态：默认 draft */}
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">
              状态
            </label>
            <div className="flex flex-wrap gap-2">
              {KANBAN_COLUMNS.map((c) => (
                <button
                  key={c.status}
                  type="button"
                  onClick={() => setStatus(c.status)}
                  className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                    status === c.status
                      ? `${c.dotColor} text-white`
                      : "bg-slate-100 text-slate-500 hover:bg-slate-200"
                  }`}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>

          {/* 备注 */}
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">
              备注
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder="如：HR 微信、内推人、面试时间"
              className="w-full resize-none rounded-xl border border-orange-200 bg-orange-50/30 px-3 py-2 text-sm text-slate-deep placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-orange-400"
            />
          </div>

          {error && (
            <div className="rounded-xl bg-red-50 px-3 py-2 text-xs text-red-600">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl bg-slate-100 px-4 py-2 text-sm font-medium text-slate-deep hover:bg-slate-200"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={submitting}
              className="rounded-xl bg-orange-500 px-4 py-2 text-sm font-medium text-white hover:bg-orange-600 disabled:opacity-50"
            >
              {submitting ? "保存中…" : "保存"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
