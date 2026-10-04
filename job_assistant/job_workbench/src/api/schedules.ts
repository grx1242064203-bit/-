// 日程与提醒 API
import { apiClient } from "./client";

export type ScheduleType = "assessment" | "written" | "interview";

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

const PREFIX = "/api/v1/schedules";

export async function listSchedules(): Promise<Schedule[]> {
  const res = await apiClient.get<{ schedules: Schedule[] }>(PREFIX);
  return res.schedules;
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
