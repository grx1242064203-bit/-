import { useState } from "react";
import type { Application, Job } from "../stores/appStore";

interface Props {
  application: Application;
  job: Job | undefined;
  onDragStart: (app: Application) => void;
  onDragEnd: () => void;
  onSaveNotes: (app: Application, notes: string) => void;
}

// 来源图标：手动 = ✋，邮箱自动 = ✉️（用 emoji 不依赖图标库）。
function SourceIcon({ source }: { source: string | null }) {
  const isEmail = source === "email" || source === "auto";
  const label = isEmail ? "邮箱自动" : "手动";
  const emoji = isEmail ? "✉️" : "✋";
  return (
    <span
      title={`来源：${label}`}
      aria-label={`来源：${label}`}
      className="text-xs"
    >
      {emoji}
    </span>
  );
}

// 单个投递卡片：可拖拽 + 点击展开编辑备注；暖橙色调 + 大圆角 + 阴影。
export default function ApplicationCard({
  application,
  job,
  onDragStart,
  onDragEnd,
  onSaveNotes,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const [notes, setNotes] = useState(application.notes ?? "");

  const company = job?.company ?? "（未知公司）";
  const title = job?.title ?? "（未知岗位）";

  // 仅显示日期部分，避免 "2026-10-03 11:00:00" 太长。
  const appliedAt = application.applied_at
    ? application.applied_at.slice(0, 10)
    : null;

  function handleSaveNotes() {
    onSaveNotes(application, notes.trim() || null);
    setExpanded(false);
  }

  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", application.app_id);
        e.dataTransfer.effectAllowed = "move";
        onDragStart(application);
      }}
      onDragEnd={onDragEnd}
      onClick={() => setExpanded((v) => !v)}
      className="group cursor-pointer rounded-2xl border border-orange-100 bg-white p-3 shadow-card transition hover:-translate-y-0.5 hover:shadow-lg"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-deep">
            {company}
          </div>
          <div className="truncate text-xs text-slate-500">{title}</div>
        </div>
        <SourceIcon source={application.source} />
      </div>

      {appliedAt && (
        <div className="mt-2 text-xs text-slate-400">投递：{appliedAt}</div>
      )}

      {!expanded && application.notes && (
        <div className="mt-1 line-clamp-2 text-xs text-slate-500">
          {application.notes}
        </div>
      )}

      {expanded && (
        <div
          className="mt-2 space-y-2"
          onClick={(e) => e.stopPropagation()}
        >
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="添加备注（如 HR 联系方式、面试反馈）…"
            rows={3}
            className="w-full resize-none rounded-xl border border-orange-200 bg-orange-50/30 p-2 text-xs text-slate-deep placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-orange-400"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setExpanded(false)}
              className="rounded-lg bg-slate-100 px-3 py-1 text-xs font-medium text-slate-500 hover:bg-slate-200"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleSaveNotes}
              className="rounded-lg bg-orange-500 px-3 py-1 text-xs font-medium text-white hover:bg-orange-600"
            >
              保存备注
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
