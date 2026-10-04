// 同步状态 API：通过 HTTP 调用后端 /api/v1/sync/stats 获取远端数据统计。
//
// 说明：数据已集中存储在后端 SQLite，前端直接通过 HTTP API 读取，
// 无需 Tauri 本地同步。本模块仅用于顶部 SyncIndicator 显示数据状态。

import { apiClient } from "./client";

export interface SyncResult {
  synced_count: number;
  last_updated_at: string | null;
}

export interface SyncStatus {
  need_sync: boolean;
  local_count: number;
  remote_count: number | null;
  last_sync: string | null;
}

export interface RemoteStats {
  total: number;
  updated_at: string | null;
}

/**
 * 获取远端岗位统计（总数 + 最新更新时间）。
 */
export async function getRemoteStats(): Promise<RemoteStats> {
  return apiClient.get<RemoteStats>("/api/v1/sync/stats");
}

/**
 * 触发同步（占位：数据已在后端，直接返回远端统计作为同步结果）。
 */
export async function syncJobs(_since?: string | null): Promise<SyncResult> {
  const stats = await getRemoteStats();
  return {
    synced_count: stats.total,
    last_updated_at: stats.updated_at,
  };
}

/**
 * 查询同步状态：数据始终在后端，need_sync 恒为 false。
 */
export async function getSyncStatus(): Promise<SyncStatus> {
  const stats = await getRemoteStats();
  return {
    need_sync: false,
    local_count: stats.total,
    remote_count: stats.total,
    last_sync: stats.updated_at,
  };
}
