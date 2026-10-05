import { useMemo, useState } from "react";
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
    updateApplicationStatus,
    updateInterviewRound,
    setSelectedAppId,
  } = useAppStore();

  const [activeApp, setActiveApp] = useState<Application | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const [pendingReverse, setPendingReverse] = useState<{
    app: Application;
    target: AppStatus;
  } | null>(null);
  // 列扩展:点击标题拓宽某列,其他列缩到图标宽度
  const [expandedCol, setExpandedCol] = useState<AppStatus | null>(null);
  // 每列独立的搜索词
  const [colSearch, setColSearch] = useState<Record<AppStatus, string>>({
    favorite: "",
    applied: "",
    assessment: "",
    interview: "",
    offer: "",
    rejected: "",
  });

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

    // over.id 格式: "col-<status>"(面试轮次改用点击,不再有 round-<n>)
    const overId = String(e.over.id);
    if (overId.startsWith("col-")) {
      const targetStatus = overId.replace("col-", "") as AppStatus;
      if (src.status === targetStatus) return;
      if (isReverse(src.status, targetStatus)) {
        setPendingReverse({ app: src, target: targetStatus });
        return;
      }
      // 拖到面试列:轮次默认 1(一面)
      void updateApplicationStatus(src, targetStatus).then(() => {
        if (targetStatus === "interview" && src.interview_round !== 1) {
          void updateInterviewRound(src, 1);
        }
      }).catch(() => {});
    }
  }

  function confirmReverse() {
    if (pendingReverse) {
      void updateApplicationStatus(pendingReverse.app, pendingReverse.target).catch(() => {});
    }
    setPendingReverse(null);
  }

  // 点击页面其他地方收起列扩展
  function handleBoardClick() {
    if (expandedCol) setExpandedCol(null);
  }

  // 列宽计算: 用 24 列网格让折叠列更窄
  // 默认 6 列等宽: 每列 col-span-4 (24/6=4)
  // 扩展时: 扩展列 col-span-16, 折叠列 col-span-1 (只够放图标)
  function getColSpan(status: AppStatus): string {
    if (!expandedCol) return "col-span-4"; // 默认 6 列等宽
    if (expandedCol === status) return "col-span-16"; // 扩展列占 2/3
    return "col-span-1"; // 折叠列缩到 1/24 (极窄)
  }

  function renderColumn(col: (typeof KANBAN_COLUMNS)[number]) {
    const items = applications.filter((a) => a.status === col.status);
    const dropId = `col-${col.status}`;
    const isOver = dragOverId === dropId;
    const isExpanded = expandedCol === col.status;
    const isCollapsed = expandedCol && expandedCol !== col.status;

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
        isExpanded={isExpanded}
        isCollapsed={!!isCollapsed}
        colSpan={getColSpan(col.status)}
        searchText={colSearch[col.status]}
        onSearchChange={(t) => setColSearch((s) => ({ ...s, [col.status]: t }))}
        onTitleClick={() => {
          // 点击标题: 切换扩展状态
          setExpandedCol(expandedCol === col.status ? null : col.status);
        }}
        onSelectApp={(id) => setSelectedAppId(id)}
        onUpdateInterviewRound={(app, round) => void updateInterviewRound(app, round)}
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
      <div
        className="grid grid-cols-24 gap-2"
        onClick={handleBoardClick}
      >
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
          <div className="glass w-80 rounded-2xl p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
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

// ===== 子组件:可放置的列 =====
function DroppableColumn({
  dropId,
  isOver,
  onDragOverChange,
  columnBg,
  headerBg,
  accentText,
  label,
  items,
  isExpanded,
  isCollapsed,
  colSpan,
  searchText,
  onSearchChange,
  onTitleClick,
  onSelectApp,
  onUpdateInterviewRound,
}: {
  dropId: string;
  isOver: boolean;
  onDragOverChange: (over: boolean) => void;
  columnBg: string;
  headerBg: string;
  accentText: string;
  label: string;
  items: Application[];
  isExpanded: boolean;
  isCollapsed: boolean;
  colSpan: string;
  searchText: string;
  onSearchChange: (t: string) => void;
  onTitleClick: () => void;
  onSelectApp: (id: number) => void;
  onUpdateInterviewRound: (app: Application, round: number) => void;
}) {
  const { setNodeRef, isOver: dndOver } = useDroppable({ id: dropId });

  if (dndOver !== isOver) {
    onDragOverChange(dndOver);
  }

  // 搜索过滤
  const filtered = useMemo(() => {
    const q = searchText.trim().toLowerCase();
    if (!q) return items;
    return items.filter((a) =>
      (a.company_name || "").toLowerCase().includes(q) ||
      (a.job_title || "").toLowerCase().includes(q) ||
      (a.notes || "").toLowerCase().includes(q)
    );
  }, [items, searchText]);

  // 折叠状态:只显示图标宽度的列
  if (isCollapsed) {
    return (
      <div
        ref={setNodeRef}
        className={`flex min-h-[60vh] flex-col items-center rounded-xl p-1 shadow-sm ${columnBg} ${
          dndOver ? "ring-2 ring-primary ring-offset-1" : ""
        } ${colSpan}`}
      >
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onTitleClick();
          }}
          className={`sticky top-0 z-10 mb-2 flex h-10 w-10 items-center justify-center rounded-full ${headerBg} ${accentText} hover:scale-110 transition`}
          title={label}
        >
          {label.slice(0, 2)}
        </button>
        <div className="text-[10px] font-medium text-text-muted">
          {items.length}
        </div>
      </div>
    );
  }

  return (
    <div
      ref={setNodeRef}
      className={`glass flex min-h-[60vh] flex-col rounded-xl p-2 shadow-sm ${columnBg} ${
        dndOver ? "ring-2 ring-primary ring-offset-1" : ""
      } ${colSpan} ${isExpanded ? "max-h-[80vh]" : ""}`}
      onClick={(e) => e.stopPropagation()}
    >
      <div
        className={`mb-2 flex items-center justify-between rounded-pill px-3 py-1.5 ${headerBg} cursor-pointer hover:opacity-80`}
        onClick={(e) => {
          e.stopPropagation();
          onTitleClick();
        }}
        title={isExpanded ? "点击其他列标题或空白处恢复" : "点击拓宽此列"}
      >
        <span className={`text-sm font-semibold ${accentText}`}>
          {label} {isExpanded ? "▾" : "▸"}
        </span>
        <span className="rounded-pill bg-slate-100 px-2 py-0.5 text-xs font-medium text-text shadow-sm">
          {filtered.length}{searchText && filtered.length !== items.length ? `/${items.length}` : ""}
        </span>
      </div>

      {/* 搜索框 */}
      <input
        type="text"
        value={searchText}
        onChange={(e) => onSearchChange(e.target.value)}
        onClick={(e) => e.stopPropagation()}
        placeholder="搜索公司/岗位/备注"
        className="mb-2 w-full rounded-pill border border-line bg-white/80 px-3 py-1 text-xs text-text placeholder:text-text-faint focus:border-primary focus:outline-none"
      />

      <div className={`flex flex-1 flex-col gap-1.5 overflow-y-auto ${isExpanded ? "grid grid-cols-2 gap-2" : ""}`}>
        {filtered.length === 0 ? (
          <div className="rounded-xl border border-dashed border-line bg-slate-50 p-3 text-center text-xs text-text-muted">
            {searchText ? "无匹配结果" : "暂无"}
          </div>
        ) : (
          filtered.map((app) => (
            <ApplicationCard
              key={app.id}
              application={app}
              onClick={() => onSelectApp(app.id)}
              isExpanded={isExpanded}
              onUpdateInterviewRound={onUpdateInterviewRound}
            />
          ))
        )}
      </div>
    </div>
  );
}
