// 岗位列表 store：Zustand 单例，承接 Jobs 页面状态。
//
// 筛选结构：
//   keyword: 全局关键词搜索（标题/公司/JD）
//   columnFilters: Record<列key, 选中值数组> — 多选筛选
// 多值在请求时用逗号拼接，后端 IN 子句匹配。

import { create } from "zustand";
import { extractErrorMessage } from "../api/client";
import { getJobs, type Job, type JobFilter } from "../api/jobs";

const PAGE_SIZE = 50;

/** 把 keyword + columnFilters 转成后端 JobFilter（多值逗号拼接） */
function buildFilter(keyword: string, columnFilters: Record<string, string[]>): JobFilter {
  const filter: JobFilter = {};
  if (keyword.trim()) filter.keyword = keyword.trim();
  for (const [k, vals] of Object.entries(columnFilters)) {
    if (vals.length > 0) {
      (filter as Record<string, string>)[k] = vals.join(",");
    }
  }
  return filter;
}

export interface JobsState {
  jobs: Job[];
  isLoading: boolean;
  isLoadingMore: boolean;
  error: string | null;
  keyword: string;
  columnFilters: Record<string, string[]>;
  total: number;
  hasMore: boolean;

  loadJobs: () => Promise<void>;
  setKeyword: (kw: string) => void;
  setColumnFilter: (key: string, values: string[]) => void;
  clearAllFilters: () => void;
  loadMore: () => Promise<void>;
}

// 关键词搜索防抖定时器(模块级,多次 setKeyword 复用同一个 timer)
let keywordDebounceTimer: ReturnType<typeof setTimeout> | null = null;

let loadSeq = 0;

export const useJobsStore = create<JobsState>((set, get) => ({
  jobs: [],
  isLoading: false,
  isLoadingMore: false,
  error: null,
  keyword: "",
  columnFilters: {},
  total: 0,
  hasMore: true,

  loadJobs: async () => {
    const seq = ++loadSeq;
    set({
      isLoading: true,
      error: null,
      jobs: [],
      hasMore: true,
      isLoadingMore: false,
    });
    try {
      const { keyword, columnFilters } = get();
      const res = await getJobs(buildFilter(keyword, columnFilters), PAGE_SIZE, 0);
      if (seq !== loadSeq) return;
      set({
        jobs: res.jobs,
        total: res.total,
        isLoading: false,
        hasMore: res.jobs.length >= PAGE_SIZE,
      });
    } catch (e) {
      if (seq !== loadSeq) return;
      const msg = extractErrorMessage(e);
      set({ error: msg, isLoading: false, jobs: [] });
    }
  },

  setKeyword: (kw) => {
    set({ keyword: kw });
    // 防抖:300ms 内连续输入只发最后一次请求,避免每个字符都打后端
    if (keywordDebounceTimer) clearTimeout(keywordDebounceTimer);
    keywordDebounceTimer = setTimeout(() => {
      void get().loadJobs();
    }, 300);
  },

  setColumnFilter: (key, values) => {
    set((s) => ({
      columnFilters: { ...s.columnFilters, [key]: values },
    }));
    void get().loadJobs();
  },

  clearAllFilters: () => {
    set({ keyword: "", columnFilters: {} });
    void get().loadJobs();
  },

  loadMore: async () => {
    if (get().isLoadingMore || !get().hasMore) return;
    const seq = loadSeq;
    set({ isLoadingMore: true });
    try {
      const { keyword, columnFilters } = get();
      const res = await getJobs(buildFilter(keyword, columnFilters), PAGE_SIZE, get().jobs.length);
      if (seq !== loadSeq) return;
      set((s) => ({
        jobs: [...s.jobs, ...res.jobs],
        isLoadingMore: false,
        hasMore: res.jobs.length >= PAGE_SIZE,
      }));
    } catch (e) {
      if (seq !== loadSeq) return;
      const msg = extractErrorMessage(e);
      set({ error: msg, isLoadingMore: false });
    }
  },
}));
