import { useRef, useState } from "react";
import {
  useAppStore,
  KANBAN_COLUMNS,
  INTERVIEW_ROUNDS,
  type Application,
  type AppStatus,
} from "../stores/appStore";
import ApplicationCard from "./ApplicationCard";

// 状态顺序，用于判断是否逆向拖拽
const STATUS_ORDER: Record<AppStatus, number> = {
  favorite: 0,
  applied: 1,
  assessment: 2,
  interview: 3,
  offer: 4,
  rejected: 5,
};

export default function KanbanBoard() {
  const {
    applications,
    interviewExpanded,
    updateApplicationStatus,
    updateInterviewRound,
    setDragSource,
    setInterviewExpanded,
    setSelectedAppId,
  } = useAppStore();

  // 拖拽源用 useRef 同步保存,避免 React state 异步更新导致 drop 时拿不到 source
  // (HTML5 drag 事件 dragstart → dragover → drop 之间可能没时间让 React 完成 state 更新)
  const dragSourceRef = useRef<Application | null>(null);
  const [dragOverStatus, setDragOverStatus] = useState<AppStatus | null>(null);
  const [dragOverRound, setDragOverRound] = useState<number | null>(null);
  const [pendingReverse, setPendingReverse] = useState<{
    app: Application;
    target: AppStatus;
  } | null>(null);

  // 包装 setDragSource:同步更新 ref + state(ref 给 handleDrop 用,state 给 UI 重渲染用)
  function setDragSourceSync(app: Application | null) {
    dragSourceRef.current = app;
    setDragSource(app);
  }

  function isReverse(from: AppStatus, to: AppStatus): boolean {
    // rejected 不参与逆向判断；offer→任何非终态算逆向
    if (to === "rejected") return false;
    return STATUS_ORDER[to] < STATUS_ORDER[from];
  }

  function handleDrop(targetStatus: AppStatus, targetRound?: number) {
    // 用 ref 同步读取,避免 state 异步导致的"快速拖拽失效"
    const src = dragSourceRef.current;
    if (!src) return;
    const from = src.status;

    // 同列内：面试轮次调整
    if (from === targetStatus && targetStatus === "interview" && targetRound != null) {
      if (src.interview_round !== targetRound) {
        void updateInterviewRound(src, targetRound);
      }
      setDragSourceSync(null);
      setDragOverStatus(null);
      setDragOverRound(null);
      return;
    }

    if (from === targetStatus) {
      setDragSourceSync(null);
      setDragOverStatus(null);
      setDragOverRound(null);
      return;
    }

    // 逆向拖拽：弹确认框
    if (isReverse(from, targetStatus)) {
      setPendingReverse({ app: src, target: targetStatus });
      setDragSourceSync(null);
      setDragOverStatus(null);
      setDragOverRound(null);
      return;
    }

    void updateApplicationStatus(src, targetStatus).catch(() => {});
    setDragSourceSync(null);
    setDragOverStatus(null);
    setDragOverRound(null);
  }

  function confirmReverse() {
    if (pendingReverse) {
      void updateApplicationStatus(pendingReverse.app, pendingReverse.target).catch(() => {});
    }
    setPendingReverse(null);
  }

  function renderColumn(col: (typeof KANBAN_COLUMNS)[number]) {
    const items = applications.filter((a) => a.status === col.status);
    const isOver = dragOverStatus === col.status;

    // 面试列展开为轮次子列
    if (col.expandable && interviewExpanded) {
      return (
        <div
          key={col.status}
          className="glass flex min-h-[60vh] flex-col rounded-xl p-2 shadow-sm"
        >
          <div
            className={`mb-2 flex items-center justify-between rounded-pill px-3 py-1.5 ${col.headerBg}`}
          >
            <button
              type="button"
              onClick={() => setInterviewExpanded(false)}
              className={`text-sm font-semibold ${col.accentText} hover:underline`}
            >
              {col.label} ▾
            </button>
            <span className="rounded-pill bg-white/60 px-2 py-0.5 text-xs font-medium text-text-muted">
              {items.length}
            </span>
          </div>

          <div className="grid grid-cols-4 gap-1.5 flex-1">
            {INTERVIEW_ROUNDS.map((r) => {
              const roundItems = items.filter(
                (a) => (a.interview_round || 1) === r.round
              );
              const roundOver = dragOverRound === r.round && dragOverStatus === "interview";
              return (
                <div
                  key={r.round}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragOverStatus("interview");
                    setDragOverRound(r.round);
                  }}
                  onDragLeave={() => setDragOverRound(null)}
                  onDrop={(e) => {
                    e.preventDefault();
                    handleDrop("interview", r.round);
                  }}
                  className={`flex min-h-[50vh] flex-col rounded-lg p-1.5 ${
                    roundOver ? "ring-2 ring-warning bg-warning/10" : "bg-white/20"
                  }`}
                >
                  <div className="mb-1 text-center text-xs font-medium text-text-muted">
                    {r.label}
                    <span className="ml-1 text-text-faint">({roundItems.length})</span>
                  </div>
                  <div className="flex flex-1 flex-col gap-1.5 overflow-y-auto">
                    {roundItems.length === 0 ? (
                      <div className="rounded border border-dashed border-white/50 p-2 text-center text-[10px] text-text-faint">
                        拖到此处
                      </div>
                    ) : (
                      roundItems.map((app) => (
                        <ApplicationCard
                          key={app.id}
                          application={app}
                          onDragStart={(a) => setDragSourceSync(a)}
                          onDragEnd={() => setDragSourceSync(null)}
                          onClick={() => setSelectedAppId(app.id)}
                        />
                      ))
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      );
    }

    return (
      <div
        key={col.status}
        onDragOver={(e) => {
          e.preventDefault();
          e.dataTransfer.dropEffect = "move";
          if (dragOverStatus !== col.status) setDragOverStatus(col.status);
        }}
        onDragLeave={(e) => {
          const rt = e.relatedTarget as Node | null;
          if (!rt || !e.currentTarget.contains(rt)) {
            setDragOverStatus((cur) => (cur === col.status ? null : cur));
          }
        }}
        onDrop={(e) => {
          e.preventDefault();
          handleDrop(col.status);
        }}
        className={`glass flex min-h-[60vh] flex-col rounded-xl p-3 shadow-sm ${col.columnBg} ${
          isOver ? "ring-2 ring-primary ring-offset-1" : ""
        }`}
      >
        <div
          className={`mb-3 flex items-center justify-between rounded-pill px-3 py-2 ${col.headerBg}`}
        >
          {col.expandable ? (
            <button
              type="button"
              onClick={() => setInterviewExpanded(true)}
              className={`text-sm font-semibold ${col.accentText} hover:underline`}
            >
              {col.label} ▸
            </button>
          ) : (
            <span className={`text-sm font-semibold ${col.accentText}`}>
              {col.label}
            </span>
          )}
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
                onDragStart={(a) => setDragSourceSync(a)}
                onDragEnd={() => setDragSourceSync(null)}
                onClick={() => setSelectedAppId(app.id)}
              />
            ))
          )}
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-6 gap-3">
        {KANBAN_COLUMNS.map(renderColumn)}
      </div>

      {/* 逆向拖拽确认弹窗 */}
      {pendingReverse && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="glass w-80 rounded-2xl p-5 shadow-xl">
            <h3 className="text-base font-semibold text-text">确认状态变更</h3>
            <p className="mt-2 text-sm text-text-muted">
              将「{pendingReverse.app.company_name || pendingReverse.app.job_title}」
              从「{KANBAN_COLUMNS.find((c) => c.status === pendingReverse.app.status)?.label}」
              移至「{KANBAN_COLUMNS.find((c) => c.status === pendingReverse.target)?.label}」
              ，这是逆向操作，确认继续？
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setPendingReverse(null)}
                className="glass-soft rounded-pill px-4 py-1.5 text-sm text-text-muted hover:text-text"
              >
                取消
              </button>
              <button
                type="button"
                onClick={confirmReverse}
                className="rounded-pill bg-primary px-4 py-1.5 text-sm font-semibold text-ink hover:bg-primary-dark"
              >
                确认
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
