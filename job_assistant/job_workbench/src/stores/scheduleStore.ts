// 日程与提醒状态管理
import { create } from "zustand";
import { extractErrorMessage } from "../api/client";
import {
  listSchedules,
  deleteSchedule,
  getDueReminders,
  markReminderFired,
  createSchedule,
  aiExtractSchedule,
  type Schedule,
  type DueReminder,
  type CreateScheduleRequest,
  type ExtractedSchedule,
} from "../api/schedules";

interface ScheduleState {
  schedules: Schedule[];
  loading: boolean;
  error: string | null;
  dueReminders: DueReminder[];
  loadSchedules: () => Promise<void>;
  removeSchedule: (id: string) => Promise<void>;
  pollDueReminders: () => Promise<DueReminder[]>;
  fireReminder: (id: string) => Promise<void>;
  addSchedule: (req: CreateScheduleRequest) => Promise<Schedule>;
  extractFromEmail: (subject: string, body: string) => Promise<ExtractedSchedule>;
}

export const useScheduleStore = create<ScheduleState>((set, get) => ({
  schedules: [],
  loading: false,
  error: null,
  dueReminders: [],

  loadSchedules: async () => {
    set({ loading: true, error: null });
    try {
      const schedules = await listSchedules();
      set({ schedules });
    } catch (e) {
      set({ error: extractErrorMessage(e) });
    } finally {
      set({ loading: false });
    }
  },

  removeSchedule: async (id) => {
    await deleteSchedule(id);
    set((s) => ({ schedules: s.schedules.filter((x) => x.id !== id) }));
  },

  pollDueReminders: async () => {
    try {
      const reminders = await getDueReminders();
      set({ dueReminders: reminders });
      return reminders;
    } catch {
      return [];
    }
  },

  fireReminder: async (id) => {
    await markReminderFired(id);
    set((s) => ({
      dueReminders: s.dueReminders.filter((r) => r.id !== id),
    }));
  },

  addSchedule: async (req) => {
    const created = await createSchedule(req);
    // 防御性：后端可能因 list_schedules_with_reminders 时序问题返回 null schedule
    // 此时不能直接 push null（会让 sort 拿 null.event_time 报 TypeError 静默失败）
    if (!created || !created.event_time) {
      console.warn("addSchedule: 后端返回 schedule 为空或 event_time 缺失，触发全量重拉", created);
      // 全量重拉一次，保证 UI 反映真实数据库状态
      await get().loadSchedules();
      return created;
    }
    // 按时间升序插入新日程（保持列表有序，无需重新拉取整张表）
    const next = [...get().schedules, created].sort(
      (a, b) =>
        new Date(a.event_time).getTime() - new Date(b.event_time).getTime()
    );
    set({ schedules: next });
    return created;
  },

  extractFromEmail: async (subject, body) => {
    return await aiExtractSchedule(subject, body);
  },
}));
