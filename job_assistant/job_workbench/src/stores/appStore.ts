import { create } from "zustand";
import { invoke } from "@tauri-apps/api/core";

// 投递状态枚举（与 src-tauri/src/models.rs::Application.status 对齐）
export type ApplicationStatus =
  | "draft"
  | "applied"
  | "test"
  | "interview"
  | "offer"
  | "rejected";

// Application struct（与 src-tauri/src/models.rs::Application 对齐）
export interface Application {
  app_id: string;
  job_id: string;
  status: string;
  applied_at: string | null;
  updated_at: string | null;
  notes: string | null;
  source: string | null;
}

// Job struct（与 src-tauri/src/models.rs::Job 对齐；卡片只用 company/title，
// 其余字段保留以与 invoke 返回 JSON 形状一致，避免运行时丢字段）
export interface Job {
  job_id: string;
  company: string;
  title: string;
  category: string | null;
  city: string | null;
  requirements: string | null;
  jd_text: string | null;
  apply_url: string | null;
  deadline: string | null;
  source: string | null;
  graduation_match: number;
  is_mt: number;
  llm_score: number | null;
  llm_reason: string | null;
  updated_at: string | null;
  deleted: number;
}

// 6 列定义：status → 中文标签 + 列背景色 + 头部色 + 圆点色（暖橙主题）。
// 颜色用 Tailwind 现成类：bg-slate-100 / bg-blue-50 / bg-yellow-50 / bg-orange-50 / bg-green-50 / bg-red-50。
export interface KanbanColumn {
  status: ApplicationStatus;
  label: string;
  columnBg: string;
  headerBg: string;
  dotColor: string;
  accentText: string;
}

export const KANBAN_COLUMNS: KanbanColumn[] = [
  {
    status: "draft",
    label: "待投递",
    columnBg: "bg-slate-100",
    headerBg: "bg-slate-200/80",
    dotColor: "bg-slate-500",
    accentText: "text-slate-600",
  },
  {
    status: "applied",
    label: "已投递",
    columnBg: "bg-blue-50",
    headerBg: "bg-blue-100/80",
    dotColor: "bg-blue-500",
    accentText: "text-blue-600",
  },
  {
    status: "test",
    label: "笔试中",
    columnBg: "bg-yellow-50",
    headerBg: "bg-yellow-100/80",
    dotColor: "bg-yellow-500",
    accentText: "text-yellow-700",
  },
  {
    status: "interview",
    label: "面试中",
    columnBg: "bg-orange-50",
    headerBg: "bg-orange-100/80",
    dotColor: "bg-orange-500",
    accentText: "text-orange-600",
  },
  {
    status: "offer",
    label: "已录用",
    columnBg: "bg-green-50",
    headerBg: "bg-green-100/80",
    dotColor: "bg-green-500",
    accentText: "text-green-700",
  },
  {
    status: "rejected",
    label: "已拒绝",
    columnBg: "bg-red-50",
    headerBg: "bg-red-100/80",
    dotColor: "bg-red-500",
    accentText: "text-red-600",
  },
];

// 把 ISO 时间格式化为 "YYYY-MM-DD HH:mm:ss"，与 SQLite TEXT 字段对齐。
export function nowIso(): string {
  return new Date().toISOString().replace("T", " ").slice(0, 19);
}

interface AppState {
  applications: Application[];
  jobs: Job[];
  isLoading: boolean;
  error: string | null;
  dragSource: Application | null;

  loadApplications: () => Promise<void>;
  addApplication: (app: Application) => Promise<void>;
  updateApplicationStatus: (
    app: Application,
    status: ApplicationStatus
  ) => Promise<void>;
  removeApplication: (appId: string) => void;
  setDragSource: (app: Application | null) => void;
  clearError: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  applications: [],
  jobs: [],
  isLoading: false,
  error: null,
  dragSource: null,

  // 拉取投递记录 + 关联岗位（岗位用于卡片显示公司名/岗位名）。
  // 不传 status → Rust 端 status: None → 返回全部状态。
  loadApplications: async () => {
    set({ isLoading: true, error: null });
    try {
      const [applications, jobs] = await Promise.all([
        invoke<Application[]>("get_applications"),
        invoke<Job[]>("get_jobs", { filter: null, limit: 200, offset: 0 }),
      ]);
      set({ applications, jobs, isLoading: false });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ error: msg, isLoading: false });
    }
  },

  // 新增投递：upsert_application 在 Rust 端返回 ()，前端用入参 app 直接更新本地状态。
  // 若同 app_id 已存在（重复保存）则替换，否则前置插入。
  addApplication: async (app) => {
    set({ error: null });
    try {
      await invoke("upsert_application", { app });
      set((s) => {
        const exists = s.applications.some((a) => a.app_id === app.app_id);
        const applications = exists
          ? s.applications.map((a) => (a.app_id === app.app_id ? app : a))
          : [app, ...s.applications];
        return { applications };
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ error: msg });
      throw e;
    }
  },

  // 拖拽换列：乐观更新本地状态 → 调 invoke upsert → 失败回滚 + 设置 error。
  updateApplicationStatus: async (app, status) => {
    if (app.status === status) return;
    const next: Application = { ...app, status, updated_at: nowIso() };
    const prev = app;
    set((s) => ({
      applications: s.applications.map((a) =>
        a.app_id === app.app_id ? next : a
      ),
    }));
    try {
      await invoke("upsert_application", { app: next });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      set((s) => ({
        applications: s.applications.map((a) =>
          a.app_id === app.app_id ? prev : a
        ),
        error: msg,
      }));
      throw e;
    }
  },

  // 仅本地移除（暂无 delete_application Tauri command；后续接入时改为先调 invoke 再移除）。
  removeApplication: (appId) => {
    set((s) => ({
      applications: s.applications.filter((a) => a.app_id !== appId),
    }));
  },

  setDragSource: (app) => set({ dragSource: app }),
  clearError: () => set({ error: null }),
}));
