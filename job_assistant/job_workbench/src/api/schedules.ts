// 日程与提醒 API
import { apiClient } from "./client";

// 用户自建日程允许的类型（在邮件三大类基础上增加 other）
export type ScheduleType = "assessment" | "written" | "interview" | "other";

export interface Reminder {
  id: string;
  remind_at: string;
  fired: number;
  fired_at: string | null;
}

export interface Schedule {
  id: string;
  application_id: string | null;
  company: string | null;
  job_title: string | null;
  schedule_type: ScheduleType;
  event_time: string;
  duration_minutes: number;
  email_link: string | null;
  meeting_link: string | null;
  notes: string | null;
  created_at: string;
  verified_at: string | null;
  reminders: Reminder[];
}

export interface DueReminder {
  id: string;
  schedule_id: string;
  user_id: string;
  remind_at: string;
  company: string | null;
  job_title: string | null;
  schedule_type: ScheduleType;
  event_time: string;
  meeting_link: string | null;
}

// 用户自建日程请求体
export interface CreateScheduleRequest {
  schedule_type: ScheduleType;
  event_time: string;
  company?: string;
  job_title?: string;
  duration_minutes?: number;
  meeting_link?: string;
  notes?: string;
  reminder_offsets_minutes?: number[];
}

// AI 提取返回的结构化信息（前端用于预填表单）
export interface ExtractedSchedule {
  task_type: ScheduleType;
  company: string;
  job_title: string;
  event_time: string | null;
  duration_minutes: number;
  meeting_link: string | null;
  notes: string;
  confidence: "high" | "medium" | "low";
}

const PREFIX = "/api/v1/schedules";

export async function listSchedules(): Promise<Schedule[]> {
  const res = await apiClient.get<{ schedules: Schedule[] }>(PREFIX);
  return res.schedules;
}

export async function createSchedule(
  req: CreateScheduleRequest
): Promise<Schedule> {
  const res = await apiClient.post<{ schedule: Schedule; verified: boolean }>(
    PREFIX,
    req
  );
  return res.schedule;
}

export async function aiExtractSchedule(
  subject: string,
  body: string
): Promise<ExtractedSchedule> {
  const res = await apiClient.post<{ extracted: ExtractedSchedule }>(
    `${PREFIX}/ai-extract`,
    { subject, body }
  );
  return res.extracted;
}

export async function deleteSchedule(id: string): Promise<void> {
  await apiClient.delete(`${PREFIX}/${id}`);
}

export async function getDueReminders(): Promise<DueReminder[]> {
  const res = await apiClient.get<{ reminders: DueReminder[] }>(
    `${PREFIX}/reminders/due`
  );
  return res.reminders;
}

export async function markReminderFired(id: string): Promise<void> {
  await apiClient.post(`${PREFIX}/reminders/${id}/fire`);
}
