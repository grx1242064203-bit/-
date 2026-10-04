import { useEffect, useState } from "react";
import { useAppStore } from "../stores/appStore";
import KanbanBoard from "../components/KanbanBoard";

export default function Applications() {
  const { applications, isLoading, error, loadApplications } = useAppStore();

  useEffect(() => {
    void loadApplications();
  }, [loadApplications]);

  const isEmpty = !isLoading && applications.length === 0;

  return (
    <div className="space-y-4 animate-fade-in">
      {/* 顶部：标题 + 投递数 */}
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold text-gray-900">投递控制台</h1>
        <span className="text-sm text-gray-500">
          共 {applications.length} 条记录
        </span>
        <button
          type="button"
          onClick={() => void loadApplications()}
          className="ml-auto rounded-md border border-gray-200 bg-surface px-3 py-1.5 text-sm text-gray-600 transition hover:bg-gray-50"
        >
          刷新
        </button>
      </div>

      {/* 错误条 */}
      {error && (
        <div className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600">
          {error}
        </div>
      )}

      {/* 主体：加载 / 空状态 / 看板 */}
      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-primary" />
        </div>
      ) : isEmpty ? (
        <div className="flex h-64 flex-col items-center justify-center rounded-lg border border-gray-200 bg-surface">
          <div className="text-4xl">📭</div>
          <p className="mt-2 text-base font-medium text-gray-900">
            还没有投递记录
          </p>
          <p className="mt-1 text-sm text-gray-500">
            去「岗位列表」或「公司总览」收藏/投递，记录会出现在这里
          </p>
        </div>
      ) : (
        <KanbanBoard />
      )}
    </div>
  );
}
