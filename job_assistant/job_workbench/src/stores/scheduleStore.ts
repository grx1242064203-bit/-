// 日程与提醒状态管理
import { create } from "zustand";
import { extractErrorMessage } from "../api/client";
import {
  listSchedules,
  deleteSchedule,
  getDueReminders,
  markReminderFired,
  type Schedule,
  type DueReminder,
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
}

export const useScheduleStore = create<ScheduleState>((set) => ({
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
}));
