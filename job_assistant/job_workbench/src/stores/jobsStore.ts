// 岗位列表 store：Zustand 单例，承接 Jobs 页面状态。
//
// 状态机：
//   挂载 → loadJobs()（用默认 filters）→ jobs[] 渲染 + hasMore 标记
//   筛选变更 → applyFilter(patch) → loadJobs(next) 重置 offset=0
//   滚动到底 → loadMore() → offset += PAGE_SIZE 累加到 jobs[]
//   同步完成 → loadStats() 刷新顶部"共 N 个岗位"
// 错误落 error，UI 显示红色提示条；isLoading 控制 skeleton 渲染。

import { create } from "zustand";
import {
  getJobs,
  getJobStats,
  type Job,
  type JobFilter,
  type JobStats,
} from "../api/jobs";

/** 单页条数：与 db.rs::get_jobs 默认 limit 一致；35K 条用分页加载。 */
const PAGE_SIZE = 50;

export interface JobsState {
  /** 当前已加载的岗位列表（loadMore 累加） */
  jobs: Job[];
  /** 首屏加载中（loadJobs 进行时为 true，控制 skeleton） */
  isLoading: boolean;
  /** 加载更多中（loadMore 进行时为 true，控制按钮文案） */
  isLoadingMore: boolean;
  /** 错误信息（null 表示无错误） */
  error: string | null;
  /** 当前筛选条件（驱动 applyFilter / clearFilters） */
  filters: JobFilter;
  /** 岗位统计（顶部 StatsBar 用） */
  stats: JobStats | null;
  /** 是否还有更多（loadJobs/loadMore 返回 < PAGE_SIZE 时置 false） */
  hasMore: boolean;

  /** 拉取首屏（重置 offset=0）。filters 缺省时使用当前 filters。 */
  loadJobs: (filters?: JobFilter) => Promise<void>;
  /** 增量更新 filters 并触发 loadJobs（patch 合并到当前 filters）。 */
  applyFilter: (patch: Partial<JobFilter>) => void;
  /** 清空所有筛选条件 → 用默认 filters 重新 loadJobs。 */
  clearFilters: () => void;
  /** 加载下一页（offset = jobs.length）。hasMore=false 或 isLoadingMore=true 时防重入。 */
  loadMore: () => Promise<void>;
  /** 刷新顶部统计（同步完成后调用）。 */
  loadStats: () => Promise<void>;
}

/** 默认 filters：与 JobFilterBar 的下拉默认值对齐。 */
const DEFAULT_FILTERS: JobFilter = {
  city: "全国各地",
  category: "不限",
  keyword: "",
};

/** 自增序号：loadJobs 并发时丢弃过期响应，避免快速切筛选时旧响应覆盖新结果。 */
let loadSeq = 0;

export const useJobsStore = create<JobsState>((set, get) => ({
  jobs: [],
  isLoading: false,
  isLoadingMore: false,
  error: null,
  filters: { ...DEFAULT_FILTERS },
  stats: null,
  hasMore: true,

  loadJobs: async (filters) => {
    const nextFilters = filters ?? get().filters;
    const seq = ++loadSeq;
    set({
      isLoading: true,
      error: null,
      filters: nextFilters,
      hasMore: true,
      // 重置 jobs（首屏加载期间显示 skeleton，不需要旧数据残留）
      jobs: [],
      // 取消正在进行的 loadMore（loadMore 会因 seq 不匹配而提前 return）
      isLoadingMore: false,
    });
    try {
      const jobs = await getJobs(nextFilters, PAGE_SIZE, 0);
      // 过期响应丢弃：用户在 await 期间又改了筛选
      if (seq !== loadSeq) return;
      set({
        jobs,
        isLoading: false,
        hasMore: jobs.length >= PAGE_SIZE,
      });
    } catch (e) {
      if (seq !== loadSeq) return;
      const msg = e instanceof Error ? e.message : String(e);
      set({ error: msg, isLoading: false, jobs: [] });
    }
  },

  applyFilter: (patch) => {
    const next = { ...get().filters, ...patch };
    void get().loadJobs(next);
  },

  clearFilters: () => {
    const next = { ...DEFAULT_FILTERS };
    void get().loadJobs(next);
  },

  loadMore: async () => {
    if (get().isLoadingMore || !get().hasMore) return;
    // 捕获当前 loadSeq；若 await 期间触发了 loadJobs（会 ++loadSeq），本响应作废。
    const seq = loadSeq;
    set({ isLoadingMore: true });
    try {
      const more = await getJobs(get().filters, PAGE_SIZE, get().jobs.length);
      // 过期响应丢弃：loadJobs 已重置 jobs/isLoadingMore，这里不要再覆盖
      if (seq !== loadSeq) return;
      set((s) => ({
        // 累加，不去重（db.rs ORDER BY updated_at DESC，分页不会重叠）
        jobs: [...s.jobs, ...more],
        isLoadingMore: false,
        hasMore: more.length >= PAGE_SIZE,
      }));
    } catch (e) {
      if (seq !== loadSeq) return;
      const msg = e instanceof Error ? e.message : String(e);
      set({ error: msg, isLoadingMore: false });
    }
  },

  loadStats: async () => {
    try {
      const stats = await getJobStats();
      set({ stats });
    } catch (e) {
      // 静默：stats 仅用于顶部 StatsBar，失败不阻塞列表
      const msg = e instanceof Error ? e.message : String(e);
      set({ error: msg });
    }
  },
}));
