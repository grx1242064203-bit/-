// 同步状态指示器：放在页面顶部，显示多态 + 进度。
//
// 状态优先级（从上到下）：
// 1. 正在拉取数据库：spinner + "正在从服务器拉取数据库..."
// 2. 数据库损坏：⚠ + "数据库损坏，点击重新拉取" → pullDb()
// 3. 同步中：spinner + "正在同步..."
// 4. 同步失败：⚠ + "同步失败，点击重试" → syncJobs()
// 5. 本地落后云端：⟳ + "本地落后云端，点击同步" → syncJobs()
// 6. 已同步：✓ + "已同步（MM-DD HH:mm）"

import { useEffect } from "react";
import { useSyncStore } from "../stores/syncStore";

/**
 * 顶部同步状态指示器。
 * 挂载时自动调用 getSyncStatus 拉一次本地 vs 远端对比。
 */
export default function SyncIndicator() {
  const {
    isSyncing,
    lastSyncAt,
    syncProgress,
    error,
    status,
    dbHealth,
    isPullingDb,
    syncJobs,
    getSyncStatus,
    pullDb,
  } = useSyncStore();

  // 挂载时拉一次状态（deps 只含稳定引用，不会循环）。
  useEffect(() => {
    void getSyncStatus();
  }, [getSyncStatus]);

  // 1. 正在从服务器拉取数据库：spinner。
  if (isPullingDb) {
    return (
      <div className="flex items-center gap-2 rounded-pill bg-primary-soft px-3 py-1.5 text-sm text-ink">
        <span
          className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-primary-dark border-t-transparent"
          aria-hidden="true"
        />
        正在从服务器拉取数据库...
      </div>
    );
  }

  // 2. 数据库损坏：⚠ + 点击重新拉取（修复路径，优先于通用 error 态）。
  if (dbHealth && !dbHealth.integrity_ok) {
    return (
      <button
        type="button"
        onClick={() => void pullDb()}
        className="flex items-center gap-2 rounded-pill bg-danger-soft px-3 py-1.5 text-sm text-danger transition hover:opacity-80"
        title={dbHealth.error || "本地数据库损坏，需从服务器重新拉取"}
      >
        <span aria-hidden="true">⚠</span>
        数据库损坏，点击重新拉取
      </button>
    );
  }

  // 3. 同步中：spinner + 进度。
  if (isSyncing) {
    const synced = syncProgress?.synced ?? 0;
    return (
      <div className="flex items-center gap-2 rounded-pill bg-primary-soft px-3 py-1.5 text-sm text-ink">
        <span
          className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-primary-dark border-t-transparent"
          aria-hidden="true"
        />
        {synced > 0 ? `正在同步...（已写入 ${synced} 条）` : "正在同步..."}
      </div>
    );
  }

  // 4. 失败：⚠ + 点击重试。
  if (error) {
    return (
      <button
        type="button"
        onClick={() => void syncJobs()}
        className="flex items-center gap-2 rounded-pill bg-danger-soft px-3 py-1.5 text-sm text-danger transition hover:opacity-80"
        title={error}
      >
        <span aria-hidden="true">⚠</span>
        同步失败，点击重试
      </button>
    );
  }

  // 5. 本地落后云端：⟳ + 点击同步（触发 pull 从服务器拉取最新 jobs.db）。
  if (status?.need_sync) {
    return (
      <button
        type="button"
        onClick={() => void pullDb()}
        className="flex items-center gap-2 rounded-pill bg-warning/20 px-3 py-1.5 text-sm text-ink transition hover:opacity-80"
      >
        <span aria-hidden="true">⟳</span>
        本地数据落后，点击同步最新
      </button>
    );
  }

  // 6. 已同步：✓ + 最后同步时间。
  return (
    <div className="flex items-center gap-2 rounded-pill bg-success-soft px-3 py-1.5 text-sm text-success">
      <span aria-hidden="true">✓</span>
      {lastSyncAt ? `已同步（${formatTime(lastSyncAt)}）` : "已同步"}
    </div>
  );
}

/**
 * 格式化时间：兼容 "2026-10-01 10:00:00"（SQLite 风格）与 ISO8601 两种格式。
 * 失败时原样返回，避免 UI 抛错。
 */
function formatTime(iso: string): string {
  // SQLite 风格的 "YYYY-MM-DD HH:MM:SS" 在 new Date() 下解析不稳，替换为 T 分隔。
  const normalized = iso.includes("T") ? iso : iso.replace(" ", "T");
  const d = new Date(normalized);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
