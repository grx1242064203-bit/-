// 邮箱账户与邮件任务 API
import { apiClient } from "./client";

export interface EmailAccount {
  id: string;
  email: string;
  imap_server: string;
  imap_port: number;
  username: string;
  created_at: string;
  last_sync_at: string | null;
}

export type TaskType = "assessment" | "written" | "interview";
export type TaskStatus = "pending" | "confirmed" | "ignored";

export interface EmailTask {
  id: string;
  email_id: string;
  task_type: TaskType;
  company: string | null;
  job_title: string | null;
  event_time: string | null;
  event_link: string | null;
  email_link: string | null;
  notes: string | null;
  status: TaskStatus;
  created_at: string;
  confirmed_at: string | null;
  application_id: string | null;
  schedule_id: string | null;
}

export interface SyncResult {
  fetched: number;
  tasks_created: number;
  skipped: number;
  error: string;
}

export interface ConfirmResult {
  application_id: string;
  application_status: string;
  schedule_id: string;
  verified: boolean;
}

const PREFIX = "/api/v1/email";

export async function listEmailAccounts(): Promise<EmailAccount[]> {
  const res = await apiClient.get<{ accounts: EmailAccount[] }>(`${PREFIX}/accounts`);
  return res.accounts;
}

export async function createEmailAccount(data: {
  email: string;
  imap_server: string;
  imap_port: number;
  username: string;
  password: string;
}): Promise<EmailAccount> {
  return apiClient.post<EmailAccount>(`${PREFIX}/accounts`, data);
}

export async function deleteEmailAccount(id: string): Promise<void> {
  await apiClient.delete(`${PREFIX}/accounts/${id}`);
}

export async function testEmailAccount(id: string): Promise<{ ok: boolean; error: string }> {
  return apiClient.post(`${PREFIX}/accounts/${id}/test`);
}

export async function syncEmailAccount(id: string): Promise<SyncResult> {
  return apiClient.post(`${PREFIX}/accounts/${id}/sync`);
}

export async function listEmailTasks(status?: TaskStatus): Promise<EmailTask[]> {
  const res = await apiClient.get<{ tasks: EmailTask[] }>(
    `${PREFIX}/tasks`,
    status ? { status } : undefined
  );
  return res.tasks;
}

export async function confirmEmailTask(id: string): Promise<ConfirmResult> {
  return apiClient.post(`${PREFIX}/tasks/${id}/confirm`);
}

export async function ignoreEmailTask(id: string): Promise<void> {
  await apiClient.post(`${PREFIX}/tasks/${id}/ignore`);
}
