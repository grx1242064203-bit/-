import { useState } from "react";
import { useDraggable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { useAppStore, type Application } from "../stores/appStore";
import { updateApplication } from "../api/applications";

interface Props {
  application: Application;
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
  onClick,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const [notes, setNotes] = useState(application.notes ?? "");
  const [saving, setSaving] = useState(false);
  const removeApplication = useAppStore((s) => s.removeApplication);

  // dnd-kit: 把卡片变成可拖拽元素,id 用 application.id(唯一)
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({
      id: `app-${application.id}`,
      data: { application },
    });

  const style = {
    transform: CSS.Translate.toString(transform),
    opacity: isDragging ? 0.4 : 1,
  };

  const updatedAt = application.updated_at
    ? application.updated_at.slice(0, 10)
    : null;
  const sourceLabel = SOURCE_LABEL[application.source] || application.source;

  // 截止日期徽标
  const deadlineInfo = (() => {
    const dl = application.deadline;
    if (!dl || /招满|即止|不限|未知/.test(dl)) return null;
    const s = dl.replace("/", "-").slice(0, 10);
    const m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(s);
    if (!m) return { text: dl, color: "bg-white/60 text-text-muted" };
    const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    if (isNaN(d.getTime())) return { text: dl, color: "bg-white/60 text-text-muted" };
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const days = Math.floor((d.getTime() - today.getTime()) / 86400000);
    if (days < 0) return { text: `已截止 ${dl}`, color: "bg-gray-200 text-gray-600" };
    if (days === 0) return { text: "今日截止", color: "bg-red-100 text-red-700" };
    if (days <= 3) return { text: `${days}天后截止`, color: "bg-orange-100 text-orange-700" };
    if (days <= 7) return { text: `${days}天后截止`, color: "bg-amber-100 text-amber-700" };
    return { text: `截止 ${dl}`, color: "bg-info-soft text-info" };
  })();

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
    if (expanded) return;
    if (isDragging) return; // 拖拽中不触发 click
    onClick?.();
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...listeners}
      {...attributes}
      onClick={handleCardClick}
      className="glass-soft group cursor-pointer rounded-xl p-3 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md touch-none"
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
              <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-900">
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
          onPointerDown={(e) => e.stopPropagation()}
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

      {deadlineInfo && (
        <div
          className={`mt-1 inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${deadlineInfo.color}`}
        >
          ⏰ {deadlineInfo.text}
        </div>
      )}

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
          onPointerDown={(e) => e.stopPropagation()}
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
