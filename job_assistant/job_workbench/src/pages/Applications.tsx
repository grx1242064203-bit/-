import { useEffect, useState } from "react";
import { useAppStore } from "../stores/appStore";
import KanbanBoard from "../components/KanbanBoard";
import AddApplicationModal from "../components/AddApplicationModal";

// 同步指示器：加载中显橙色脉冲点 + "同步中…"，否则绿色 + "已同步"。
function SyncIndicator({ loading }: { loading: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1 text-xs text-slate-500 shadow-card">
      <span
        className={`h-2 w-2 rounded-full ${
          loading ? "animate-pulse bg-orange-500" : "bg-green-500"
        }`}
      />
      {loading ? "同步中…" : "已同步"}
    </span>
  );
}

export default function Applications() {
  const { applications, isLoading, error, loadApplications } = useAppStore();
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    loadApplications();
  }, [loadApplications]);

  const isEmpty = !isLoading && applications.length === 0;

  return (
    <div className="space-y-4">
      {/* 顶部：标题 + 投递数 + 同步状态 + 添加按钮 */}
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold text-slate-deep">投递看板</h1>
        <span className="text-sm text-slate-500">
          共 {applications.length} 条投递
        </span>
        <div className="ml-auto flex items-center gap-3">
          <SyncIndicator loading={isLoading} />
          <button
            type="button"
            onClick={() => setModalOpen(true)}
            className="rounded-xl bg-orange-500 px-4 py-2 text-sm font-medium text-white shadow-card hover:bg-orange-600"
          >
            + 添加投递
          </button>
        </div>
      </div>

      {/* 错误条 */}
      {error && (
        <div className="rounded-xl bg-red-50 px-4 py-2 text-sm text-red-600">
          {error}
        </div>
      )}

      {/* 主体：加载 spinner / 空状态引导 / 看板 */}
      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-orange-200 border-t-orange-500" />
        </div>
      ) : isEmpty ? (
        <div className="flex h-64 flex-col items-center justify-center rounded-2xl bg-white shadow-card">
          <div className="text-4xl">📭</div>
          <p className="mt-2 text-base font-medium text-slate-deep">
            开始记录你的投递吧！
          </p>
          <p className="mt-1 text-sm text-slate-500">
            点击右上角「添加投递」创建第一条记录
          </p>
          <button
            type="button"
            onClick={() => setModalOpen(true)}
            className="mt-4 rounded-xl bg-orange-500 px-4 py-2 text-sm font-medium text-white hover:bg-orange-600"
          >
            + 添加投递
          </button>
        </div>
      ) : (
        <KanbanBoard />
      )}

      <AddApplicationModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
      />
    </div>
  );
}
