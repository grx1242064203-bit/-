import { useState } from "react";
import { useAppStore, type Application } from "../stores/appStore";
import { updateApplication } from "../api/applications";

interface Props {
  application: Application;
  onDragStart: (app: Application) => void;
  onDragEnd: () => void;
  onClick?: () => void;
}

const SOURCE_LABEL: Record<string, string> = {
  db_job: "岗位库",
  db_company: "公司库",
  manual: "自建",
  email: "邮件",
};

const SOURCE_COLOR: Record<string, string> = {
  db_job: "bg-primary-soft text-primary-dark",
  db_company: "bg-info-soft text-info",
  manual: "bg-white/60 text-text-muted",
  email: "bg-success/15 text-success",
};

export default function ApplicationCard({
  application,
  onDragStart,
  onDragEnd,
  onClick,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const [notes, setNotes] = useState(application.notes ?? "");
  const [saving, setSaving] = useState(false);
  // 标记是否正在/刚刚完成拖拽，用于抑制拖拽后的 click 事件
  // （浏览器在 dragend 后会同步触发 click，导致误开详情弹窗）
  const [dragged, setDragged] = useState(false);
  const removeApplication = useAppStore((s) => s.removeApplication);

  const updatedAt = application.updated_at
    ? application.updated_at.slice(0, 10)
    : null;
  const sourceLabel = SOURCE_LABEL[application.source] || application.source;

  function handleSaveNotes() {
    setSaving(true);
    updateApplication(application.id, { notes: notes.trim() || null })
      .then(() => {
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

  function handleCardClick() {
    if (expanded) return; // 编辑备注时不触发打开详情
    if (dragged) return; // 拖拽刚结束，抑制误触发的 click
    onClick?.();
  }

  return (
    <div
      draggable
      onDragStart={(e) => {
        setDragged(true);
        e.dataTransfer.setData("text/plain", String(application.id));
        e.dataTransfer.effectAllowed = "move";
        onDragStart(application);
      }}
      onDragEnd={() => {
        onDragEnd();
        // dragend 后浏览器同步触发 click，延迟重置让 click 处理器能看到 dragged=true
        setTimeout(() => setDragged(false), 0);
      }}
      onClick={handleCardClick}
      className="glass-soft group cursor-pointer rounded-xl p-3 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${SOURCE_COLOR[application.source] || "bg-white/60 text-text-muted"}`}
            >
              {sourceLabel}
            </span>
            {application.status === "interview" && application.interview_round > 0 && (
              <span className="rounded bg-warning/20 px-1.5 py-0.5 text-[10px] font-medium text-ink">
                {application.interview_round}面
              </span>
            )}
          </div>
          <div className="mt-1 truncate text-sm font-semibold text-text">
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
            className="w-full resize-none rounded-lg border border-white/60 bg-white/40 p-2 text-xs text-text placeholder:text-text-faint backdrop-blur-sm focus:border-primary-dark focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setExpanded(false)}
              className="glass-soft rounded-pill px-3 py-1 text-xs font-medium text-text-muted hover:text-text"
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

      {!expanded && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setExpanded(true);
          }}
          className="mt-1 text-[11px] text-text-faint opacity-0 transition hover:text-text-muted group-hover:opacity-100"
        >
          {application.notes ? "编辑备注" : "添加备注"}
        </button>
      )}
    </div>
  );
}
