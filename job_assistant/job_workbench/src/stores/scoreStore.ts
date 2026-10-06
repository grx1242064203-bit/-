// 评分 store：Zustand 单例，承接 T13 推荐视图的状态中枢。
//
// 状态机：
//   resumeStore.parsedProfile 出值 → scoreAll(profile)（isScoring=true）
//     → scoreAllJobs API（Rust 端分批调 sidecar）
//     → 完成后 loadSummary() 刷新 Tab 数量 + loadScoredJobs() 刷新当前 Tab 列表
//   Tab 切换 → loadScoredJobs(filter) 按 [min, max) 区间过滤
// 错误落 error，UI 显示红色提示条；isScoring 控制 Tab 加载态 + 进度提示。
// scoreAll 重入保护：进行中再调直接 return；profile 为 null 时返回错误。

import { create } from "zustand";
import {
  getScoredJobs,
  getScoreSummary,
  scoreAllJobs,
  type ScoreAllResult,
  type ScoredJobsFilter,
  type ScoreSummary,
} from "../api/scoring";
import type { Job } from "../api/jobs";

/** 单页条数：与 db.rs::get_scored_jobs 默认 limit 一致；35K 已评分岗位分页加载。 */
const SCORED_PAGE_SIZE = 50;

export interface ScoreState {
  /** 是否正在执行全量评分（scoreAll 进行时为 true，UI 显示"评分中…"并禁用按钮） */
  isScoring: boolean;
  /** 评分进度（已评 / 总数）；scoreAll 完成后回填 */
  scoringProgress: { scored: number; total: number } | null;
  /** 评分分桶统计（Tab 数量） */
  scoreSummary: ScoreSummary | null;
  /** 当前推荐 Tab 已加载的岗位列表（按 llm_score DESC） */
  scoredJobs: Job[];
  /** 推荐 Tab 首屏加载中（loadScoredJobs 进行时为 true，控制 skeleton） */
  isLoading: boolean;
  /** 加载更多中（loadScoredJobsMore 进行时为 true） */
  isLoadingMore: boolean;
  /** 错误信息（null 表示无错误） */
  error: string | null;
  /** 当前推荐 Tab 的过滤区间（min_score 闭下界 / max_score 开上界） */
  scoredFilter: ScoredJobsFilter;
  /** 是否还有更多（loadScoredJobs/loadMore 返回 < PAGE_SIZE 时置 false） */
  hasMore: boolean;

  /** 触发全量评分。profile 来自 resumeStore.parsedProfile。
   * 完成后自动 loadSummary + loadScoredJobs（用当前 scoredFilter）。 */
  scoreAll: (profile: unknown) => Promise<ScoreAllResult | null>;
  /** 加载推荐 Tab 的首屏岗位（重置 offset=0）。filter 缺省时使用当前 scoredFilter。 */
  loadScoredJobs: (filter?: ScoredJobsFilter) => Promise<void>;
  /** 加载下一页（offset = scoredJobs.length）。hasMore=false 或 isLoadingMore=true 时防重入。 */
  loadScoredJobsMore: () => Promise<void>;
  /** 刷新评分分桶统计（Tab 数量；scoreAll 完成后调用）。 */
  loadSummary: () => Promise<void>;
  /** 清空错误。 */
  clearError: () => void;
}

/** 自增序号：loadScoredJobs 并发时丢弃过期响应，避免快速切 Tab 时旧响应覆盖新结果。 */
let loadSeq = 0;

export const useScoreStore = create<ScoreState>((set, get) => ({
  isScoring: false,
  scoringProgress: null,
  scoreSummary: null,
  scoredJobs: [],
  isLoading: false,
  isLoadingMore: false,
  error: null,
  scoredFilter: {},
  hasMore: true,

  scoreAll: async (profile) => {
    if (get().isScoring) {
      // 重入保护：避免用户连点"重新评分"导致 sidecar 并发拉数据。
      return null;
    }
    if (!profile || (typeof profile === "object" && Object.keys(profile as object).length === 0)) {
      const msg = "缺少简历画像，请先上传简历并完成 LLM 解析";
      set({ error: msg });
      return null;
    }
    set({ isScoring: true, error: null, scoringProgress: { scored: 0, total: 0 } });
    try {
      const result = await scoreAllJobs(profile);
      set({
        scoringProgress: { scored: result.scored, total: result.total },
        isScoring: false,
      });
      // 完成后刷新 Tab 数量 + 当前 Tab 列表
      await get().loadSummary();
      await get().loadScoredJobs();
      return result;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ isScoring: false, error: msg });
      return null;
    }
  },

  loadScoredJobs: async (filter) => {
    const nextFilter = filter ?? get().scoredFilter;
    const seq = ++loadSeq;
    set({
      error: null,
      scoredFilter: nextFilter,
      hasMore: true,
      scoredJobs: [],
      isLoading: true,
      isLoadingMore: false,
    });
    try {
      const jobs = await getScoredJobs(nextFilter, SCORED_PAGE_SIZE, 0);
      if (seq !== loadSeq) return;
      set({
        scoredJobs: jobs,
        hasMore: jobs.length >= SCORED_PAGE_SIZE,
        isLoading: false,
      });
    } catch (e) {
      if (seq !== loadSeq) return;
      const msg = e instanceof Error ? e.message : String(e);
      set({ error: msg, scoredJobs: [], isLoading: false });
    }
  },

  loadScoredJobsMore: async () => {
    // 防御：全屏重新加载(筛选变更)进行中时禁止 loadMore，避免第一页被重复追加
    if (get().isLoading || get().isLoadingMore || !get().hasMore) return;
    const seq = loadSeq;
    const filter = get().scoredFilter;
    set({ isLoadingMore: true });
    try {
      const more = await getScoredJobs(filter, SCORED_PAGE_SIZE, get().scoredJobs.length);
      if (seq !== loadSeq) return;
      set((s) => ({
        scoredJobs: [...s.scoredJobs, ...more],
        isLoadingMore: false,
        hasMore: more.length >= SCORED_PAGE_SIZE,
      }));
    } catch (e) {
      if (seq !== loadSeq) return;
      const msg = e instanceof Error ? e.message : String(e);
      set({ error: msg, isLoadingMore: false });
    }
  },

  loadSummary: async () => {
    try {
      const summary = await getScoreSummary();
      set({ scoreSummary: summary });
    } catch (e) {
      // 静默：summary 仅用于 Tab 数量，失败不阻塞列表
      const msg = e instanceof Error ? e.message : String(e);
      set({ error: msg });
    }
  },

  clearError: () => set({ error: null }),
}));
