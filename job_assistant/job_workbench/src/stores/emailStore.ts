// 邮箱与邮件任务状态管理
import { create } from "zustand";
import { extractErrorMessage } from "../api/client";
import {
  listEmailAccounts,
  createEmailAccount,
  deleteEmailAccount,
  syncEmailAccount,
  listEmailTasks,
  getEmailDetail,
  confirmEmailTask,
  ignoreEmailTask,
  reextractEmailTask,
  type EmailAccount,
  type EmailTask,
  type EmailDetail,
  type TaskStatus,
} from "../api/emails";
import { useAppStore } from "./appStore";

interface EmailState {
  accounts: EmailAccount[];
  tasks: EmailTask[];
  loading: boolean;
  syncing: boolean;
  error: string | null;
  loadAccounts: () => Promise<void>;
  addAccount: (data: {
    email: string;
    imap_server: string;
    imap_port: number;
    username: string;
    password: string;
  }) => Promise<EmailAccount>;
  removeAccount: (id: string) => Promise<void>;
  syncAccount: (id: string) => Promise<void>;
  loadTasks: (status?: TaskStatus) => Promise<void>;
  getEmail: (emailId: string) => Promise<EmailDetail>;
  confirmTask: (id: string) => Promise<void>;
  ignoreTask: (id: string) => Promise<void>;
  reextractTask: (id: string) => Promise<void>;
}

export const useEmailStore = create<EmailState>((set, get) => ({
  accounts: [],
  tasks: [],
  loading: false,
  syncing: false,
  error: null,

  loadAccounts: async () => {
    set({ loading: true, error: null });
    try {
      const accounts = await listEmailAccounts();
      set({ accounts });
    } catch (e) {
      set({ error: extractErrorMessage(e) });
    } finally {
      set({ loading: false });
    }
  },

  addAccount: async (data) => {
    const account = await createEmailAccount(data);
    set((s) => ({ accounts: [account, ...s.accounts] }));
    return account;
  },

  removeAccount: async (id) => {
    await deleteEmailAccount(id);
    set((s) => ({ accounts: s.accounts.filter((a) => a.id !== id) }));
  },

  syncAccount: async (id) => {
    set({ syncing: true, error: null });
    try {
      await syncEmailAccount(id);
      // 同步后立即刷新任务列表（异步 LLM 提取进行中，pending 任务先出现）
      await get().loadTasks("pending");
      // 等 5s 再刷一次，让 LLM 提取结果可见
      setTimeout(() => {
        void get().loadTasks("pending");
      }, 5000);
    } catch (e) {
      set({ error: extractErrorMessage(e) });
    } finally {
      set({ syncing: false });
    }
  },

  loadTasks: async (status) => {
    set({ loading: true, error: null });
    try {
      const tasks = await listEmailTasks(status);
      set({ tasks });
    } catch (e) {
      set({ error: extractErrorMessage(e) });
    } finally {
      set({ loading: false });
    }
  },

  getEmail: async (emailId) => {
    return await getEmailDetail(emailId);
  },

  confirmTask: async (id) => {
    await confirmEmailTask(id);
    // 从待确认列表移除
    set((s) => ({
      tasks: s.tasks.filter((t) => t.id !== id),
    }));
    // 触发投递记录刷新（已有）
    void useAppStore.getState().loadApplications();
    // 触发日程列表刷新（修复：之前日程页不刷新）
    // 用动态 import 避免循环依赖
    const { useScheduleStore } = await import("./scheduleStore");
    void useScheduleStore.getState().loadSchedules();
  },

  ignoreTask: async (id) => {
    await ignoreEmailTask(id);
    set((s) => ({ tasks: s.tasks.filter((t) => t.id !== id) }));
  },

  reextractTask: async (id) => {
    await reextractEmailTask(id);
    // 标记当前任务为 pending（前端立即反馈"AI 提取中"）
    set((s) => ({
      tasks: s.tasks.map((t) =>
        t.id === id ? { ...t, extract_status: "pending" as const } : t
      ),
    }));
    // 5s 后刷新看结果
    setTimeout(() => {
      void get().loadTasks("pending");
    }, 5000);
  },
}));
