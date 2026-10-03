// 同步状态 store：Zustand 单例，驱动 SyncIndicator 三态显示 + 进度。
//
// 状态机：idle → (syncJobs) → isSyncing → (success) → lastSyncAt 更新
//                                      ↘ (error)   → error 提示，SyncIndicator 显示重试
// getSyncStatus 单独拉本地 vs 远端对比，触发"是否需要同步"提示（不进入 isSyncing）。

import { create } from "zustand";
import {
  syncJobs as apiSyncJobs,
  getSyncStatus as apiGetSyncStatus,
  type SyncStatus,
  type SyncResult,
} from "../api/sync";

export interface SyncProgress {
  /** 已写入条数（同步进行中由 0 累加到 synced_count） */
  synced: number;
  /** 总条数（同步完成后等于 synced；进行中为 null，因 reqwest 流式分页无法预知总数） */
  total: number | null;
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

  /** 触发同步；since 缺省时全量拉取。返回 SyncResult 便于调用方链式处理。 */
  syncJobs: (since?: string | null) => Promise<SyncResult | null>;
  /** 拉本地 vs 远端对比；用于挂载时显示"落后云端，点击同步"提示。 */
  getSyncStatus: () => Promise<SyncStatus | null>;
  /** 重置状态（登出 / 切账号时调用） */
  reset: () => void;
}

export const useSyncStore = create<SyncState>((set, get) => ({
  isSyncing: false,
  lastSyncAt: null,
  syncProgress: null,
  error: null,
  status: null,

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
      set({ isSyncing: false, error: msg, syncProgress: null });
      return null;
    }
  },

  getSyncStatus: async () => {
    try {
      const s = await apiGetSyncStatus();
      set({ status: s, error: null });
      return s;
    } catch (e) {
      // 未登录或网络错误：不抛错打断 UI，落 error 让 SyncIndicator 显示重试。
      const msg = e instanceof Error ? e.message : String(e);
      set({ error: msg });
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
    }),
}));
