// 同步状态指示器：放在页面顶部，显示三态 + 进度。
//
// 三态：
// - 同步中：spinner + "正在同步岗位 N 条..."（syncProgress.synced 实时累加）
// - 已同步：✓ + "已同步（MM-DD HH:mm）"
// - 失败：⚠ + "同步失败，点击重试"
// 额外态：本地落后云端时显示 ⟳ + "本地落后云端，点击同步"。

import { useEffect } from "react";
import { useSyncStore } from "../stores/syncStore";

/**
 * 顶部同步状态指示器。
 * 挂载时自动调用 getSyncStatus 拉一次本地 vs 远端对比。
 */
export default function SyncIndicator() {
  const { isSyncing, lastSyncAt, syncProgress, error, status, syncJobs, getSyncStatus } =
    useSyncStore();

  // 挂载时拉一次状态（deps 只含稳定引用，不会循环）。
  useEffect(() => {
    void getSyncStatus();
  }, [getSyncStatus]);

  // 同步中：spinner + 进度。
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

  // 失败：⚠ + 点击重试。
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

  // 本地落后云端：⟳ + 点击同步。
  if (status?.need_sync) {
    return (
      <button
        type="button"
        onClick={() => void syncJobs()}
        className="flex items-center gap-2 rounded-pill bg-warning/20 px-3 py-1.5 text-sm text-ink transition hover:opacity-80"
      >
        <span aria-hidden="true">⟳</span>
        本地落后云端，点击同步
      </button>
    );
  }

  // 已同步：✓ + 最后同步时间。
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
