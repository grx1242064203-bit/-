import { useState } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  useDroppable,
  type DragStartEvent,
  type DragEndEvent,
} from "@dnd-kit/core";
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
    setInterviewExpanded,
    setSelectedAppId,
  } = useAppStore();

  const [activeApp, setActiveApp] = useState<Application | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const [pendingReverse, setPendingReverse] = useState<{
    app: Application;
    target: AppStatus;
  } | null>(null);

  // PointerSensor: 鼠标 + 触屏全支持; activationConstraint.distance=6 防止误触
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor)
  );

  function isReverse(from: AppStatus, to: AppStatus): boolean {
    if (to === "rejected") return false;
    return STATUS_ORDER[to] < STATUS_ORDER[from];
  }

  function handleDragStart(e: DragStartEvent) {
    const app = (e.active.data.current as { application?: Application } | undefined)?.application;
    setActiveApp(app ?? null);
    setDragOverId(null);
  }

  function handleDragEnd(e: DragEndEvent) {
    setActiveApp(null);
    setDragOverId(null);
    if (!e.over) return;

    const src = (e.active.data.current as { application?: Application } | undefined)?.application;
    if (!src) return;

    // over.id 格式: "col-<status>" 或 "round-<n>"
    const overId = String(e.over.id);
    if (overId.startsWith("col-")) {
      const targetStatus = overId.replace("col-", "") as AppStatus;
      if (src.status === targetStatus) return;
      if (isReverse(src.status, targetStatus)) {
        setPendingReverse({ app: src, target: targetStatus });
        return;
      }
      void updateApplicationStatus(src, targetStatus).catch(() => {});
    } else if (overId.startsWith("round-")) {
      const round = Number(overId.replace("round-", ""));
      if (src.status === "interview" && src.interview_round !== round) {
        void updateInterviewRound(src, round);
      } else if (src.status !== "interview") {
        // 拖到面试轮次子列:同时改状态 + 轮次
        if (isReverse(src.status, "interview")) {
          setPendingReverse({ app: src, target: "interview" });
          return;
        }
        void updateApplicationStatus(src, "interview").then(() => {
          void updateInterviewRound(src, round);
        });
      }
    }
  }

  function confirmReverse() {
    if (pendingReverse) {
      void updateApplicationStatus(pendingReverse.app, pendingReverse.target).catch(() => {});
    }
    setPendingReverse(null);
  }

  function renderColumn(col: (typeof KANBAN_COLUMNS)[number]) {
    const items = applications.filter((a) => a.status === col.status);
    const dropId = `col-${col.status}`;
    const isOver = dragOverId === dropId;

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
            <span className="rounded-pill bg-slate-100 px-2 py-0.5 text-xs font-medium text-text">
              {items.length}
            </span>
          </div>

          <div className="grid grid-cols-4 gap-1.5 flex-1">
            {INTERVIEW_ROUNDS.map((r) => (
              <RoundSubColumn
                key={r.round}
                round={r.round}
                label={r.label}
                items={items.filter((a) => (a.interview_round || 1) === r.round)}
                isOver={dragOverId === `round-${r.round}`}
                onDragOverChange={(over) =>
                  setDragOverId(over ? `round-${r.round}` : null)
                }
                onSelectApp={(id) => setSelectedAppId(id)}
              />
            ))}
          </div>
        </div>
      );
    }

    return (
      <DroppableColumn
        key={col.status}
        dropId={dropId}
        isOver={isOver}
        onDragOverChange={(over) => setDragOverId(over ? dropId : null)}
        columnBg={col.columnBg}
        headerBg={col.headerBg}
        accentText={col.accentText}
        label={col.label}
        items={items}
        expandable={col.expandable}
        onExpand={() => setInterviewExpanded(true)}
        onSelectApp={(id) => setSelectedAppId(id)}
      />
    );
  }

  return (
    <DndContext
      sensors={sensors}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onDragCancel={() => {
        setActiveApp(null);
        setDragOverId(null);
      }}
    >
      <div className="grid grid-cols-6 gap-3">
        {KANBAN_COLUMNS.map(renderColumn)}
      </div>

      {/* 拖拽预览(跟随光标) */}
      <DragOverlay dropAnimation={null}>
        {activeApp ? (
          <div className="rotate-2 opacity-80">
            <div className="glass-soft rounded-xl p-3 shadow-xl">
              <div className="text-sm font-semibold text-text">
                {activeApp.company_name || "（未知公司）"}
              </div>
              <div className="truncate text-xs text-text-muted">
                {activeApp.job_title || "（未知岗位）"}
              </div>
            </div>
          </div>
        ) : null}
      </DragOverlay>

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
    </DndContext>
  );
}

// ===== 子组件:可放置的列(普通列) =====
function DroppableColumn({
  dropId,
  isOver,
  onDragOverChange,
  columnBg,
  headerBg,
  accentText,
  label,
  items,
  expandable,
  onExpand,
  onSelectApp,
}: {
  dropId: string;
  isOver: boolean;
  onDragOverChange: (over: boolean) => void;
  columnBg: string;
  headerBg: string;
  accentText: string;
  label: string;
  items: Application[];
  expandable?: boolean;
  onExpand?: () => void;
  onSelectApp: (id: number) => void;
}) {
  const { setNodeRef, isOver: dndOver } = useDroppable({ id: dropId });

  // 同步外部 hover 状态(用于 ring 高亮)
  if (dndOver !== isOver) {
    onDragOverChange(dndOver);
  }

  return (
    <div
      ref={setNodeRef}
      className={`glass flex min-h-[60vh] flex-col rounded-xl p-3 shadow-sm ${columnBg} ${
        dndOver ? "ring-2 ring-primary ring-offset-1" : ""
      }`}
    >
      <div
        className={`mb-3 flex items-center justify-between rounded-pill px-3 py-2 ${headerBg}`}
      >
        {expandable ? (
          <button
            type="button"
            onClick={onExpand}
            className={`text-sm font-semibold ${accentText} hover:underline`}
          >
            {label} ▸
          </button>
        ) : (
          <span className={`text-sm font-semibold ${accentText}`}>{label}</span>
        )}
        <span className="rounded-pill bg-slate-100 px-2 py-0.5 text-xs font-medium text-text shadow-sm">
          {items.length}
        </span>
      </div>

      <div className="flex flex-1 flex-col gap-2 overflow-y-auto">
        {items.length === 0 ? (
          <div className="rounded-xl border border-dashed border-line bg-slate-50 p-3 text-center text-xs text-text-muted">
            暂无
          </div>
        ) : (
          items.map((app) => (
            <ApplicationCard
              key={app.id}
              application={app}
              onClick={() => onSelectApp(app.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ===== 子组件:面试轮次子列 =====
function RoundSubColumn({
  round,
  label,
  items,
  isOver,
  onDragOverChange,
  onSelectApp,
}: {
  round: number;
  label: string;
  items: Application[];
  isOver: boolean;
  onDragOverChange: (over: boolean) => void;
  onSelectApp: (id: number) => void;
}) {
  const { setNodeRef, isOver: dndOver } = useDroppable({ id: `round-${round}` });

  if (dndOver !== isOver) {
    onDragOverChange(dndOver);
  }

  return (
    <div
      ref={setNodeRef}
      className={`flex min-h-[50vh] flex-col rounded-lg p-1.5 ${
        dndOver ? "ring-2 ring-warning bg-warning/10" : "bg-slate-50"
      }`}
    >
      <div className="mb-1 text-center text-xs font-medium text-text-muted">
        {label}
        <span className="ml-1 text-text-faint">({items.length})</span>
      </div>
      <div className="flex flex-1 flex-col gap-1.5 overflow-y-auto">
        {items.length === 0 ? (
          <div className="rounded border border-dashed border-line p-2 text-center text-[10px] text-text-muted">
            拖到此处
          </div>
        ) : (
          items.map((app) => (
            <ApplicationCard
              key={app.id}
              application={app}
              onClick={() => onSelectApp(app.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}
