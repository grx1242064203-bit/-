import { create } from "zustand";
import {
  listApplications,
  updateApplication,
  deleteApplication,
  type Application,
  type AppStatus,
} from "../api/applications";

// 投递状态枚举（与后端 models/application.py 对齐）
export type ApplicationStatus = AppStatus;

export interface KanbanColumn {
  status: ApplicationStatus;
  label: string;
  columnBg: string;
  headerBg: string;
  dotColor: string;
  accentText: string;
}

// 5 列看板：收藏 → 已投递 → 面试中 → 已录用 → 已拒绝
export const KANBAN_COLUMNS: KanbanColumn[] = [
  {
    status: "favorite",
    label: "⭐ 收藏",
    columnBg: "bg-gray-50",
    headerBg: "bg-gray-100",
    dotColor: "bg-gray-400",
    accentText: "text-gray-600",
  },
  {
    status: "applied",
    label: "📮 已投递",
    columnBg: "bg-blue-50",
    headerBg: "bg-blue-100",
    dotColor: "bg-blue-500",
    accentText: "text-blue-600",
  },
  {
    status: "interview",
    label: "💬 面试中",
    columnBg: "bg-amber-50",
    headerBg: "bg-amber-100",
    dotColor: "bg-amber-500",
    accentText: "text-amber-700",
  },
  {
    status: "offer",
    label: "🎉 已录用",
    columnBg: "bg-green-50",
    headerBg: "bg-green-100",
    dotColor: "bg-green-500",
    accentText: "text-green-700",
  },
  {
    status: "rejected",
    label: "❌ 已拒绝",
    columnBg: "bg-red-50",
    headerBg: "bg-red-100",
    dotColor: "bg-red-500",
    accentText: "text-red-600",
  },
];

interface AppState {
  applications: Application[];
  isLoading: boolean;
  error: string | null;
  dragSource: Application | null;

  loadApplications: () => Promise<void>;
  updateApplicationStatus: (
    app: Application,
    status: ApplicationStatus
  ) => Promise<void>;
  removeApplication: (appId: number) => Promise<void>;
  setDragSource: (app: Application | null) => void;
  clearError: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  applications: [],
  isLoading: false,
  error: null,
  dragSource: null,

  loadApplications: async () => {
    set({ isLoading: true, error: null });
    try {
      const res = await listApplications();
      set({ applications: res.applications, isLoading: false });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ error: msg, isLoading: false });
    }
  },

  updateApplicationStatus: async (app, status) => {
    if (app.status === status) return;
    const prev = app;
    set((s) => ({
      applications: s.applications.map((a) =>
        a.id === app.id ? { ...a, status } : a
      ),
    }));
    try {
      await updateApplication(app.id, { status });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      set((s) => ({
        applications: s.applications.map((a) =>
          a.id === app.id ? prev : a
        ),
        error: msg,
      }));
      throw e;
    }
  },

  removeApplication: async (appId) => {
    try {
      await deleteApplication(appId);
      set((s) => ({
        applications: s.applications.filter((a) => a.id !== appId),
      }));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ error: msg });
    }
  },

  setDragSource: (app) => set({ dragSource: app }),
  clearError: () => set({ error: null }),
}));
