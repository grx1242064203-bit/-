// 同步状态 API：通过 HTTP 调用后端获取数据统计与数据库同步。
//
// 数据链路：
//   服务器主库（每日 08:00 更新）→ 本地 jobs.db → 前端
// 当本地 jobs.db 损坏时，/stats 等接口返回 503 DATABASE_CORRUPTED，
// 前端应调用 pullDbFromServer() 重新拉取主库。

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

/** 本地 jobs.db 健康状态。 */
export interface DbHealth {
  exists: boolean;
  size: number;
  mtime: number | null;
  integrity: string;
  integrity_ok: boolean;
  error: string | null;
}

/** 从服务器拉取 jobs.db 的结果。 */
export interface DbPullResult {
  ok: boolean;
  message: string;
  remote_info?: Record<string, unknown>;
  downloaded_bytes: number;
  md5_match: boolean;
  integrity_ok: boolean;
  backup_path: string | null;
}

/**
 * 获取远端岗位统计（总数 + 最新更新时间）。
 * 若本地数据库损坏，后端返回 503 DATABASE_CORRUPTED，此时应调用 pullDbFromServer。
 */
export async function getRemoteStats(): Promise<RemoteStats> {
  return apiClient.get<RemoteStats>("/api/v1/sync/stats");
}

/**
 * 触发同步（数据已在后端，直接返回远端统计作为同步结果）。
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

/**
 * 查询本地 jobs.db 健康状态（完整性、大小、mtime）。
 */
export async function getDbHealth(): Promise<DbHealth> {
  return apiClient.get<DbHealth>("/api/v1/sync/db-health");
}

/**
 * 从服务器重新拉取 jobs.db 并替换本地副本。
 * 后端会校验大小、MD5、PRAGMA integrity_check，全部通过才原子替换。
 */
export async function pullDbFromServer(): Promise<DbPullResult> {
  return apiClient.post<DbPullResult>("/api/v1/sync/pull-db");
}
