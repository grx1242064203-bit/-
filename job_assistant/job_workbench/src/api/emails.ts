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

// AI 提取状态枚举（与后端 email_model.EXTRACT_STATUS_* 对齐）
export type ExtractStatus =
  | "pending" // 初筛命中后任务已创建，字段为空，等待 LLM 异步提取
  | "llm_done" // LLM 提取成功，字段已回填
  | "llm_failed" // LLM 调用失败（超时/配额/Key 无效）
  | "rule_fallback"; // LLM 失败后回退到规则提取

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
  extract_status: ExtractStatus;
  // 由 list_tasks 接口 join emails 表后回填的冗余字段（仅列表场景有值）
  email_subject?: string;
  email_sender?: string;
  email_received_at?: string;
}

// 邮件原文（GET /emails/{id} 返回）
export interface EmailDetail {
  id: string;
  message_id: string;
  subject: string | null;
  sender: string | null;
  from_addr: string | null;
  received_at: string | null;
  body_text: string | null;
  body_html: string | null;
  raw_headers: string | null;
  created_at: string;
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

export async function testEmailAccount(
  id: string
): Promise<{ ok: boolean; error: string }> {
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

export async function getEmailDetail(emailId: string): Promise<EmailDetail> {
  const res = await apiClient.get<{ email: EmailDetail }>(
    `${PREFIX}/emails/${emailId}`
  );
  return res.email;
}

export async function confirmEmailTask(id: string): Promise<ConfirmResult> {
  return apiClient.post(`${PREFIX}/tasks/${id}/confirm`);
}

export async function ignoreEmailTask(id: string): Promise<void> {
  await apiClient.post(`${PREFIX}/tasks/${id}/ignore`);
}

export async function reextractEmailTask(id: string): Promise<void> {
  await apiClient.post(`${PREFIX}/tasks/${id}/reextract`);
}
