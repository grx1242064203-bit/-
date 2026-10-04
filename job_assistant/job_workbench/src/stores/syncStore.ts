// 同步状态 store：Zustand 单例，驱动 SyncIndicator 多态显示 + 进度。
//
// 状态机：
//   idle → (syncJobs) → isSyncing → (success) → lastSyncAt 更新
//                              ↘ (error 503 DATABASE_CORRUPTED) → dbHealth 损坏 → 显示「重新拉取」
//   idle → (getSyncStatus) → status 更新 / 若 503 则 checkDbHealth
//   dbHealth.integrity_ok === false → (pullDb) → isPullingDb → (success) → 刷新 stats

import { create } from "zustand";
import {
  syncJobs as apiSyncJobs,
  getSyncStatus as apiGetSyncStatus,
  getDbHealth as apiGetDbHealth,
  pullDbFromServer as apiPullDb,
  type SyncStatus,
  type SyncResult,
  type DbHealth,
  type DbPullResult,
} from "../api/sync";
import type { ApiError } from "../api/client";

export interface SyncProgress {
  /** 已写入条数（同步进行中由 0 累加到 synced_count） */
  synced: number;
  /** 总条数（同步完成后等于 synced；进行中为 null，因 reqwest 流式分页无法预知总数） */
  total: number | null;
}

/** 判断错误是否为本地数据库损坏（后端 503 DATABASE_CORRUPTED）。 */
function isDbCorruptedError(e: unknown): boolean {
  const err = e as ApiError;
  return (
    err &&
    typeof err === "object" &&
    err.status === 503 &&
    (err.error?.includes("数据库损坏") || err.error?.includes("malformed"))
  );
}

export interface SyncState {
  /** 是否同步中（syncJobs 进行时为 true，禁止重复触发） */
  isSyncing: boolean;
  /** 最近一次同步完成时间（前端本地时间，非云端 updated_at） */
  lastSyncAt: string | null;
  /** 同步进度（null 表示未在同步） */
  syncProgress: SyncProgress | null;
  /** 错误信息（null 表示无错误） */
  error: string | null;
  /** 本地 vs 远端对比状态（getSyncStatus 拉取） */
  status: SyncStatus | null;

  /** 本地 jobs.db 健康状态（checkDbHealth 拉取） */
  dbHealth: DbHealth | null;
  /** 是否正在从服务器拉取数据库 */
  isPullingDb: boolean;

  /** 触发同步；since 缺省时全量拉取。返回 SyncResult 便于调用方链式处理。 */
  syncJobs: (since?: string | null) => Promise<SyncResult | null>;
  /** 拉本地 vs 远端对比；用于挂载时显示"落后云端，点击同步"提示。 */
  getSyncStatus: () => Promise<SyncStatus | null>;
  /** 查询本地 jobs.db 健康状态。 */
  checkDbHealth: () => Promise<DbHealth | null>;
  /** 从服务器重新拉取 jobs.db（数据库损坏时的修复路径）。 */
  pullDb: () => Promise<DbPullResult | null>;
  /** 重置状态（登出 / 切账号时调用） */
  reset: () => void;
}

export const useSyncStore = create<SyncState>((set, get) => ({
  isSyncing: false,
  lastSyncAt: null,
  syncProgress: null,
  error: null,
  status: null,
  dbHealth: null,
  isPullingDb: false,

  syncJobs: async (since) => {
    // 防重入：同步进行中再次触发直接返回。
    if (get().isSyncing) {
      return null;
    }
    set({
      isSyncing: true,
      error: null,
      syncProgress: { synced: 0, total: null },
    });
    try {
      const result = await apiSyncJobs(since ?? null);
      set({
        isSyncing: false,
        lastSyncAt: new Date().toISOString(),
        syncProgress: {
          synced: result.synced_count,
          total: result.synced_count,
        },
        // 同步完成后顺带刷新 status（need_sync 应为 false）。
        status: null,
      });
      // 后台异步刷新 status，不阻塞返回。
      void get().getSyncStatus();
      return result;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error("[syncStore] syncJobs failed:", e);
      set({ isSyncing: false, error: msg, syncProgress: null });
      // 若是数据库损坏，异步拉取健康状态以便 UI 显示「重新拉取」按钮。
      if (isDbCorruptedError(e)) {
        void get().checkDbHealth();
      }
      return null;
    }
  },

  getSyncStatus: async () => {
    try {
      const s = await apiGetSyncStatus();
      set({ status: s, error: null });
      return s;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error("[syncStore] getSyncStatus failed:", e);
      set({ error: msg });
      // 若是数据库损坏，异步拉取健康状态以便 UI 显示「重新拉取」按钮。
      if (isDbCorruptedError(e)) {
        void get().checkDbHealth();
      }
      return null;
    }
  },

  checkDbHealth: async () => {
    try {
      const health = await apiGetDbHealth();
      set({ dbHealth: health });
      return health;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error("[syncStore] checkDbHealth failed:", e);
      set({ dbHealth: { exists: false, size: 0, mtime: null, integrity: "unknown", integrity_ok: false, error: msg } });
      return null;
    }
  },

  pullDb: async () => {
    if (get().isPullingDb) {
      return null;
    }
    set({ isPullingDb: true, error: null });
    try {
      const result = await apiPullDb();
      set({
        isPullingDb: false,
        dbHealth: null,
        error: result.ok ? null : result.message,
      });
      if (result.ok) {
        // 拉取成功后刷新统计与状态。
        set({ lastSyncAt: new Date().toISOString() });
        void get().getSyncStatus();
      }
      return result;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error("[syncStore] pullDb failed:", e);
      set({ isPullingDb: false, error: msg });
      return null;
    }
  },

  reset: () =>
    set({
      isSyncing: false,
      lastSyncAt: null,
      syncProgress: null,
      error: null,
      status: null,
      dbHealth: null,
      isPullingDb: false,
    }),
}));
