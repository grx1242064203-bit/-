import { create } from "zustand";
import { extractErrorMessage } from "../api/client";
import {
  listApplications,
  updateApplication,
  deleteApplication,
  createApplication,
  type Application,
  type AppStatus,
  type AppSource,
} from "../api/applications";

// 重新导出类型，供 KanbanBoard / ApplicationCard 使用
export type { Application, AppStatus, AppSource };

export interface KanbanColumn {
  status: AppStatus;
  label: string;
  columnBg: string;
  headerBg: string;
  dotColor: string;
  accentText: string;
  expandable?: boolean; // 面试列可展开为轮次
}

// 6 列看板：收藏 → 投递 → 测评 → 面试(可展开轮次) → offer | 拒绝
export const KANBAN_COLUMNS: KanbanColumn[] = [
  {
    status: "favorite",
    label: "⭐ 收藏",
    columnBg: "",
    headerBg: "bg-white border-b border-line",
    dotColor: "bg-text-muted",
    accentText: "text-text",
  },
  {
    status: "applied",
    label: "📮 已投递",
    columnBg: "bg-primary-soft/50",
    headerBg: "bg-primary-soft",
    dotColor: "bg-primary-dark",
    accentText: "text-ink",
  },
  {
    status: "assessment",
    label: "📝 测评",
    columnBg: "bg-info/12",
    headerBg: "bg-info/20",
    dotColor: "bg-info",
    accentText: "text-ink",
  },
  {
    status: "interview",
    label: "💬 面试中",
    columnBg: "bg-warning/12",
    headerBg: "bg-warning/20",
    dotColor: "bg-warning",
    accentText: "text-ink",
    expandable: true,
  },
  {
    status: "offer",
    label: "🎉 已录用",
    columnBg: "bg-success-soft",
    headerBg: "bg-success/18",
    dotColor: "bg-success",
    accentText: "text-success",
  },
  {
    status: "rejected",
    label: "❌ 已拒绝",
    columnBg: "bg-danger-soft",
    headerBg: "bg-danger/12",
    dotColor: "bg-danger",
    accentText: "text-danger",
  },
];

// 面试轮次标签
export const INTERVIEW_ROUNDS = [
  { round: 1, label: "一面" },
  { round: 2, label: "二面" },
  { round: 3, label: "三面" },
  { round: 4, label: "终面" },
];

interface AppState {
  applications: Application[];
  isLoading: boolean;
  error: string | null;
  dragSource: Application | null;
  interviewExpanded: boolean;
  selectedAppId: number | null;
  // 推荐结果缓存:切页不丢失,简历修改或主动刷新才重新拉取
  recommendJobs: import("../api/jobsRecommend").RecommendedJob[];
  recommendLoading: boolean;
  recommendError: string | null;
  recommendLoadedAt: number | null; // 上次加载时间戳,用于判断是否需要刷新

  loadApplications: () => Promise<void>;
  addApplication: (data: {
    job_title?: string;
    company_name?: string;
    status?: AppStatus;
    source?: AppSource;
    link_type?: "job" | "company" | null;
    link_id?: string | null;
    apply_url?: string;
    announcement_url?: string;
    notes?: string;
  }) => Promise<Application | null>;
  updateApplicationStatus: (
    app: Application,
    status: AppStatus
  ) => Promise<void>;
  updateInterviewRound: (
    app: Application,
    round: number
  ) => Promise<void>;
  removeApplication: (appId: number) => Promise<void>;
  setDragSource: (app: Application | null) => void;
  setInterviewExpanded: (v: boolean) => void;
  setSelectedAppId: (id: number | null) => void;
  clearError: () => void;
  // 推荐缓存:force=true 强制刷新;否则有缓存就直接用
  loadRecommendJobs: (topN?: number, force?: boolean) => Promise<void>;
  clearRecommendJobs: () => void; // 简历修改后清空缓存
}

export const useAppStore = create<AppState>((set) => ({
  applications: [],
  isLoading: false,
  error: null,
  dragSource: null,
  interviewExpanded: false,
  selectedAppId: null,
  recommendJobs: [],
  recommendLoading: false,
  recommendError: null,
  recommendLoadedAt: null,

  loadApplications: async () => {
    set({ isLoading: true, error: null });
    try {
      const res = await listApplications();
      set({ applications: res.applications, isLoading: false });
    } catch (e) {
      const msg = extractErrorMessage(e);
      set({ error: msg, isLoading: false });
    }
  },

  addApplication: async (data) => {
    try {
      const app = await createApplication(data);
      set((s) => ({ applications: [app, ...s.applications] }));
      return app;
    } catch (e) {
      const msg = extractErrorMessage(e);
      set({ error: msg });
      return null;
    }
  },

  updateApplicationStatus: async (app, status) => {
    if (app.status === status) return;
    const prev = app;
    // 拖入面试列时，轮次默认设为 1（若已有轮次则保留）
    const nextRound =
      status === "interview" ? Math.max(app.interview_round || 0, 1) : 0;
    set((s) => ({
      applications: s.applications.map((a) =>
        a.id === app.id
          ? { ...a, status, interview_round: nextRound }
          : a
      ),
    }));
    try {
      const updateData: { status: AppStatus; interview_round?: number } = { status };
      if (status === "interview") updateData.interview_round = nextRound;
      await updateApplication(app.id, updateData);
    } catch (e) {
      const msg = extractErrorMessage(e);
      set((s) => ({
        applications: s.applications.map((a) =>
          a.id === app.id ? prev : a
        ),
        error: msg,
      }));
      throw e;
    }
  },

  updateInterviewRound: async (app, round) => {
    set((s) => ({
      applications: s.applications.map((a) =>
        a.id === app.id ? { ...a, interview_round: round } : a
      ),
    }));
    try {
      await updateApplication(app.id, { interview_round: round });
    } catch (e) {
      const msg = extractErrorMessage(e);
      set((s) => ({
        applications: s.applications.map((a) =>
          a.id === app.id ? { ...a, interview_round: app.interview_round } : a
        ),
        error: msg,
      }));
    }
  },

  removeApplication: async (appId) => {
    try {
      await deleteApplication(appId);
      set((s) => ({
        applications: s.applications.filter((a) => a.id !== appId),
        selectedAppId: s.selectedAppId === appId ? null : s.selectedAppId,
      }));
    } catch (e) {
      const msg = extractErrorMessage(e);
      set({ error: msg });
    }
  },

  setDragSource: (app) => set({ dragSource: app }),
  setInterviewExpanded: (v) => set({ interviewExpanded: v }),
  setSelectedAppId: (id) => set({ selectedAppId: id }),
  clearError: () => set({ error: null }),

  // 推荐缓存:有缓存且未强制刷新时直接返回,避免切页重新跑 7000 个岗位评分
  loadRecommendJobs: async (topN = 200, force = false) => {
    const s = useAppStore.getState();
    // 有缓存且非强制刷新:直接复用(切页场景)
    if (!force && s.recommendJobs.length > 0 && s.recommendLoadedAt) {
      return;
    }
    set({ recommendLoading: true, recommendError: null });
    try {
      const { jobsRecommendApi } = await import("../api/jobsRecommend");
      // force=true 跳过后端缓存,全量重算
      const res = await jobsRecommendApi.recommend(topN, force);
      set({
        recommendJobs: res.jobs,
        recommendLoading: false,
        recommendLoadedAt: Date.now(),
      });
    } catch (e) {
      set({
        recommendLoading: false,
        recommendError: extractErrorMessage(e),
      });
    }
  },

  clearRecommendJobs: () =>
    set({ recommendJobs: [], recommendLoadedAt: null, recommendError: null }),
}));
