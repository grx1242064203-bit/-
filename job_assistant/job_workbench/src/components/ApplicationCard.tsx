import { useState } from "react";
import { useAppStore, type Application } from "../stores/appStore";
import { updateApplication } from "../api/applications";

interface Props {
  application: Application;
  onDragStart: (app: Application) => void;
  onDragEnd: () => void;
}

export default function ApplicationCard({
  application,
  onDragStart,
  onDragEnd,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const [notes, setNotes] = useState(application.notes ?? "");
  const [saving, setSaving] = useState(false);
  const removeApplication = useAppStore((s) => s.removeApplication);

  const updatedAt = application.updated_at
    ? application.updated_at.slice(0, 10)
    : null;

  function handleSaveNotes() {
    setSaving(true);
    updateApplication(application.id, { notes: notes.trim() || null })
      .then(() => {
        // 更新本地 store
        useAppStore.setState((s) => ({
          applications: s.applications.map((a) =>
            a.id === application.id ? { ...a, notes: notes.trim() || null } : a
          ),
        }));
        setExpanded(false);
      })
      .catch(() => {})
      .finally(() => setSaving(false));
  }

  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", String(application.id));
        e.dataTransfer.effectAllowed = "move";
        onDragStart(application);
      }}
      onDragEnd={onDragEnd}
      onClick={() => setExpanded((v) => !v)}
      className="group cursor-pointer rounded-xl border border-border bg-surface p-3.5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-text">
            {application.company_name || "（未知公司）"}
          </div>
          <div className="truncate text-xs text-text-muted">
            {application.job_title || "（未知岗位）"}
          </div>
        </div>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            void removeApplication(application.id);
          }}
          className="text-xs text-text-faint opacity-0 transition hover:text-danger group-hover:opacity-100"
          title="删除"
        >
          ✕
        </button>
      </div>

      {updatedAt && (
        <div className="mt-1 text-xs text-text-faint">更新：{updatedAt}</div>
      )}

      {!expanded && application.notes && (
        <div className="mt-1 line-clamp-2 text-xs text-text-muted">
          {application.notes}
        </div>
      )}

      {expanded && (
        <div className="mt-2 space-y-2" onClick={(e) => e.stopPropagation()}>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="添加备注（如 HR 联系方式、面试反馈）…"
            rows={3}
            className="w-full resize-none rounded-lg border border-border bg-surface-soft p-2 text-xs text-text placeholder:text-text-faint focus:border-primary-dark focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setExpanded(false)}
              className="rounded-pill bg-surface-soft px-3 py-1 text-xs font-medium text-text-muted hover:bg-line"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleSaveNotes}
              disabled={saving}
              className="rounded-pill bg-primary px-3 py-1 text-xs font-semibold text-ink hover:bg-primary-dark disabled:opacity-50"
            >
              {saving ? "保存中…" : "保存备注"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
