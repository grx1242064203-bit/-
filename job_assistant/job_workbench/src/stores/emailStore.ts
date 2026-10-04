// 邮箱与邮件任务状态管理
import { create } from "zustand";
import { extractErrorMessage } from "../api/client";
import {
  listEmailAccounts,
  createEmailAccount,
  deleteEmailAccount,
  syncEmailAccount,
  listEmailTasks,
  confirmEmailTask,
  ignoreEmailTask,
  type EmailAccount,
  type EmailTask,
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
  confirmTask: (id: string) => Promise<void>;
  ignoreTask: (id: string) => Promise<void>;
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
      // 同步后刷新任务列表
      await get().loadTasks("pending");
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

  confirmTask: async (id) => {
    await confirmEmailTask(id);
    // 刷新任务列表和投递记录
    set((s) => ({
      tasks: s.tasks.filter((t) => t.id !== id),
    }));
    // 触发投递记录刷新
    void useAppStore.getState().loadApplications();
  },

  ignoreTask: async (id) => {
    await ignoreEmailTask(id);
    set((s) => ({ tasks: s.tasks.filter((t) => t.id !== id) }));
  },
}));
