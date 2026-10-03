// 桌面端同步 API 封装：调用 Tauri command（sync_jobs / get_sync_status）。
//
// 设计：
// - token + apiBaseUrl 由本层从 authStore + env 读取后注入 invoke，
//   上层（syncStore / SyncIndicator）只关心 (since?) 即可，不必感知鉴权细节。
// - 鉴权缺失时直接抛错，由 syncStore 捕获后落 error 状态，SyncIndicator 显示"点击重试"。
// - 字段命名与 Rust 侧 SyncResult / SyncStatus 对齐（snake_case），通过 invoke 反序列化得到。

import { invoke } from "@tauri-apps/api/core";
import { useAuthStore } from "../stores/authStore";

const DEFAULT_API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export interface SyncResult {
  /** 本次同步写入条数（含覆盖更新） */
  synced_count: number;
  /** 本次见到的最新 updated_at；空批时为传入的 since */
  last_updated_at: string | null;
}

export interface SyncStatus {
  /** 本地是否落后远端，需要触发同步 */
  need_sync: boolean;
  /** 本地未删岗位数 */
  local_count: number;
  /** 远端总数（拉取失败时为 null，由 syncStore 兜底） */
  remote_count: number | null;
  /** 本地最近一次同步游标（jobs 表 MAX(updated_at)） */
  last_sync: string | null;
}

export interface RemoteStats {
  total: number;
  updated_at: string | null;
}

/**
 * 触发岗位增量同步：调用 Tauri sync_jobs 命令。
 * @param since 增量起点（ISO8601 字符串）；undefined/null 时全量拉取
 * @throws 未登录（authStore.token 为空）或网络/数据库错误
 */
export async function syncJobs(since?: string | null): Promise<SyncResult> {
  const token = useAuthStore.getState().token;
  if (!token) {
    throw new Error("[sync] 未登录：authStore.token 为空，请先登录");
  }
  return invoke<SyncResult>("sync_jobs", {
    apiBaseUrl: DEFAULT_API_BASE_URL,
    token,
    since: since ?? null,
  });
}

/**
 * 查询本地 vs 远端对比状态：驱动 SyncIndicator 显示"已同步 / 落后 / 失败"。
 * @throws 未登录或网络错误（syncStore 兜底为 error 状态）
 */
export async function getSyncStatus(): Promise<SyncStatus> {
  const token = useAuthStore.getState().token;
  if (!token) {
    throw new Error("[sync] 未登录：authStore.token 为空，请先登录");
  }
  return invoke<SyncStatus>("get_sync_status", {
    apiBaseUrl: DEFAULT_API_BASE_URL,
    token,
  });
}
