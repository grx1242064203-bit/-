import { useState, type DragEvent } from "react";
import {
  useAppStore,
  KANBAN_COLUMNS,
  nowIso,
  type Application,
  type ApplicationStatus,
} from "../stores/appStore";
import ApplicationCard from "./ApplicationCard";

// 6 列看板：每列按 status 过滤卡片，顶部显示数量；卡片可拖拽到其他列。
// 拖拽用原生 HTML5 API：dragstart 设置 dragSource，dragover 阻止默认 + 高亮列，drop 调 updateApplicationStatus。
export default function KanbanBoard() {
  const {
    applications,
    jobs,
    dragSource,
    addApplication,
    updateApplicationStatus,
    setDragSource,
  } = useAppStore();

  const [dragOverStatus, setDragOverStatus] = useState<ApplicationStatus | null>(
    null
  );

  // 用 Map 加速 job_id → Job 查找（卡片显示公司名/岗位名用）
  const jobsMap = new Map(jobs.map((j) => [j.job_id, j]));

  function handleDragOver(e: DragEvent, status: ApplicationStatus) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (dragOverStatus !== status) setDragOverStatus(status);
  }

  function handleDragLeave(e: DragEvent, status: ApplicationStatus) {
    // 仅当真正离开列容器时清状态，避免子元素切换闪烁。
    const rt = e.relatedTarget as Node | null;
    if (!rt || !e.currentTarget.contains(rt)) {
      setDragOverStatus((cur) => (cur === status ? null : cur));
    }
  }

  function handleDrop(targetStatus: ApplicationStatus) {
    if (dragSource && dragSource.status !== targetStatus) {
      updateApplicationStatus(dragSource, targetStatus).catch(() => {
        // 错误已在 store 内回滚 + 设置 error，此处静默
      });
    }
    setDragSource(null);
    setDragOverStatus(null);
  }

  return (
    <div className="grid grid-cols-6 gap-3">
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
            className={`flex min-h-[60vh] flex-col rounded-2xl p-2 ${col.columnBg} ${
              isOver ? "ring-2 ring-orange-400 ring-offset-1" : ""
            }`}
          >
            {/* 列头：标签 + 数量 */}
            <div
              className={`mb-2 flex items-center justify-between rounded-xl px-3 py-2 ${col.headerBg}`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`h-2 w-2 rounded-full ${col.dotColor}`}
                />
                <span
                  className={`text-sm font-semibold ${col.accentText}`}
                >
                  {col.label}
                </span>
              </div>
              <span className="rounded-full bg-white/70 px-2 py-0.5 text-xs font-medium text-slate-deep">
                {items.length}
              </span>
            </div>

            {/* 卡片区 */}
            <div className="flex flex-1 flex-col gap-2 overflow-y-auto">
              {items.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-300 bg-white/40 p-3 text-center text-xs text-slate-400">
                  暂无
                </div>
              ) : (
                items.map((app) => (
                  <ApplicationCard
                    key={app.app_id}
                    application={app}
                    job={jobsMap.get(app.job_id)}
                    onDragStart={(a) => setDragSource(a)}
                    onDragEnd={() => setDragSource(null)}
                    onSaveNotes={(a, notes) => {
                      // 复用 addApplication（upsert 幂等）：同 app_id 替换，notes 与 updated_at 更新。
                      addApplication({ ...a, notes, updated_at: nowIso() }).catch(
                        () => {}
                      );
                    }}
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
