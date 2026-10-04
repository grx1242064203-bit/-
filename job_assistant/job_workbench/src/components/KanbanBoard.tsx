import { useState, type DragEvent } from "react";
import {
  useAppStore,
  KANBAN_COLUMNS,
  type Application,
  type ApplicationStatus,
} from "../stores/appStore";
import ApplicationCard from "./ApplicationCard";

// 5 列看板：每列按 status 过滤卡片，顶部显示数量；卡片可拖拽到其他列。
export default function KanbanBoard() {
  const {
    applications,
    dragSource,
    updateApplicationStatus,
    setDragSource,
  } = useAppStore();

  const [dragOverStatus, setDragOverStatus] = useState<ApplicationStatus | null>(
    null
  );

  function handleDragOver(e: DragEvent, status: ApplicationStatus) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (dragOverStatus !== status) setDragOverStatus(status);
  }

  function handleDragLeave(e: DragEvent, status: ApplicationStatus) {
    const rt = e.relatedTarget as Node | null;
    if (!rt || !e.currentTarget.contains(rt)) {
      setDragOverStatus((cur) => (cur === status ? null : cur));
    }
  }

  function handleDrop(targetStatus: ApplicationStatus) {
    if (dragSource && dragSource.status !== targetStatus) {
      updateApplicationStatus(dragSource, targetStatus).catch(() => {});
    }
    setDragSource(null);
    setDragOverStatus(null);
  }

  return (
    <div className="grid grid-cols-5 gap-4">
      {KANBAN_COLUMNS.map((col) => {
        const items = applications.filter(
          (a: Application) => a.status === col.status
        );
        const isOver = dragOverStatus === col.status;
        return (
          <div
            key={col.status}
            onDragOver={(e) => handleDragOver(e, col.status)}
            onDragLeave={(e) => handleDragLeave(e, col.status)}
            onDrop={() => handleDrop(col.status)}
            className={`glass flex min-h-[60vh] flex-col rounded-xl p-3 shadow-sm ${col.columnBg} ${
              isOver ? "ring-2 ring-primary ring-offset-1" : ""
            }`}
          >
            <div
              className={`mb-3 flex items-center justify-between rounded-pill px-3 py-2 ${col.headerBg}`}
            >
              <span className={`text-sm font-semibold ${col.accentText}`}>
                {col.label}
              </span>
              <span className="rounded-pill bg-white/60 px-2 py-0.5 text-xs font-medium text-text-muted shadow-sm backdrop-blur-sm">
                {items.length}
              </span>
            </div>

            <div className="flex flex-1 flex-col gap-2 overflow-y-auto">
              {items.length === 0 ? (
                <div className="rounded-xl border border-dashed border-white/50 bg-white/20 p-3 text-center text-xs text-text-faint">
                  暂无
                </div>
              ) : (
                items.map((app) => (
                  <ApplicationCard
                    key={app.id}
                    application={app}
                    onDragStart={(a) => setDragSource(a)}
                    onDragEnd={() => setDragSource(null)}
                  />
                ))
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
