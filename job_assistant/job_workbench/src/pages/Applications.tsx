import { useEffect } from "react";
import { useAppStore } from "../stores/appStore";
import KanbanBoard from "../components/KanbanBoard";

export default function Applications() {
  const { applications, isLoading, error, loadApplications } = useAppStore();

  useEffect(() => {
    void loadApplications();
  }, [loadApplications]);

  const isEmpty = !isLoading && applications.length === 0;

  return (
    <div className="space-y-5 animate-fade-in">
      {/* 顶部：标题 + 投递数 */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-text-muted">
          共 {applications.length} 条记录
        </span>
        <button
          type="button"
          onClick={() => void loadApplications()}
          className="glass-soft ml-auto rounded-pill px-4 py-1.5 text-sm text-text-muted transition hover:text-text"
        >
          刷新
        </button>
      </div>

      {/* 错误条 */}
      {error && (
        <div className="rounded-xl bg-danger-soft px-4 py-2 text-sm text-danger">
          {error}
        </div>
      )}

      {/* 主体：加载 / 空状态 / 看板 */}
      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-white/50 border-t-primary" />
        </div>
      ) : isEmpty ? (
        <div className="glass flex h-64 flex-col items-center justify-center rounded-xl shadow-sm">
          <div className="text-4xl">📭</div>
          <p className="mt-2 text-base font-medium text-text">
            还没有投递记录
          </p>
          <p className="mt-1 text-sm text-text-muted">
            去「岗位列表」或「公司总览」收藏/投递，记录会出现在这里
          </p>
        </div>
      ) : (
        <KanbanBoard />
      )}
    </div>
  );
}
