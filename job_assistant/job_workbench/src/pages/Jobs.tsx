// 岗位列表首页（T10+T13）：Tab 切换 + SyncIndicator + JobFilterBar + 岗位列表。
//
// 结构：
//   ┌ 顶部：标题 + StatsBar（总数 + 最后同步时间） + SyncIndicator + 评分进度提示
//   ├ Tab：全部岗位（默认）/ 🔥 强烈推荐(N) / ✅ 推荐(N) / ➖ 可申请(N)
//   ├ JobFilterBar（sticky top，即时筛选；推荐 Tab 下隐藏，因为推荐 Tab 自带区间过滤）
//   ├ 岗位列表（grid 1/2/3 列响应式）
//   │   ├ 加载中：6 个 SkeletonCard
//   │   ├ 空状态：引导文案 + 提示调筛选 / 同步 / 上传简历
//   │   └ 数据：JobCard 列表 + "加载更多" 按钮（每次 +50 条）
//   └ 错误条（红色）
//
// 35K 条岗位用分页加载（loadMore），暂不接虚拟滚动（T15+ 范围）。
//
// T13 集成：
// - 简历解析后（resumeStore.parsedProfile 有值）→ 自动触发 scoreStore.scoreAll
//   + 自动切换到"🔥 强烈推荐"Tab
// - 推荐 Tab 激活时 → loadScoredJobs(filter by score range)
// - 默认隐藏 <35 的岗位（不显示"❌ 不建议"Tab）

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useJobsStore } from "../stores/jobsStore";
import { useScoreStore } from "../stores/scoreStore";
import { useResumeStore } from "../stores/resumeStore";
import SyncIndicator from "../components/SyncIndicator";
import JobFilterBar from "../components/JobFilterBar";
import JobCard from "../components/JobCard";

// 顶部统计：总数 + 最后同步时间（数据停止于 X）。
function StatsBar() {
  const stats = useJobsStore((s) => s.stats);
  const total = stats?.total ?? 0;
  const updatedAt = stats?.updated_at ?? null;
  // SQLite 风格 "YYYY-MM-DD HH:MM:SS" 截前 16 位 → "YYYY-MM-DD HH:MM"；ISO8601 兼容。
  const updatedShort = updatedAt
    ? updatedAt.slice(0, 16).replace("T", " ")
    : null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
      <span className="rounded-full bg-white px-3 py-1 shadow-card">
        共 <strong className="text-orange-600">{total}</strong> 个岗位
      </span>
      {updatedShort && (
        <span className="rounded-full bg-white px-3 py-1 shadow-card">
          数据停止于 {updatedShort}
        </span>
      )}
    </div>
  );
}

// 加载骨架卡片：animate-pulse 占位，避免首屏空白跳跃。
function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-2xl border border-orange-100 bg-white p-4 shadow-card">
      <div className="h-4 w-2/3 rounded bg-orange-100" />
      <div className="mt-2 h-3 w-1/2 rounded bg-orange-50" />
      <div className="mt-3 flex gap-2">
        <div className="h-3 w-12 rounded bg-slate-100" />
        <div className="h-3 w-12 rounded bg-slate-100" />
      </div>
      <div className="mt-3 h-8 w-full rounded bg-orange-50" />
    </div>
  );
}

// Tab 按键。T13 新增 can_apply；hot/recommend 从禁用变激活。
type TabKey = "all" | "hot" | "recommend" | "can_apply";

interface TabDef {
  key: TabKey;
  label: string;
  count?: number;
}

function TabButton({
  active,
  disabled,
  children,
  onClick,
}: {
  active: boolean;
  disabled?: boolean;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
        active
          ? "bg-orange-500 text-white shadow-card"
          : disabled
          ? "cursor-not-allowed bg-slate-100 text-slate-400"
          : "bg-white text-slate-500 hover:bg-orange-50"
      }`}
    >
      {children}
    </button>
  );
}

// 评分阈值（与 scorer.py / Rust db.rs 对齐）
const THRESHOLD_STRONG = 75;
const THRESHOLD_RECOMMEND = 55;
const THRESHOLD_CAN_APPLY = 35;

export default function Jobs() {
  const {
    jobs,
    isLoading,
    isLoadingMore,
    error: jobsError,
    hasMore,
    loadJobs,
    loadMore,
    loadStats,
  } = useJobsStore();
  const {
    isScoring,
    scoringProgress,
    scoreSummary,
    scoredJobs,
    isLoading: isScoredLoading,
    isLoadingMore: isScoredLoadingMore,
    error: scoreError,
    hasMore: scoredHasMore,
    loadScoredJobs,
    loadScoredJobsMore,
    loadSummary,
    scoreAll,
  } = useScoreStore();
  const { parsedProfile } = useResumeStore();
  const [activeTab, setActiveTab] = useState<TabKey>("all");

  // 挂载时拉首屏 + stats。deps 只含稳定函数引用，不会循环。
  useEffect(() => {
    void loadJobs();
    void loadStats();
    void loadSummary();
  }, [loadJobs, loadStats, loadSummary]);

  // 简历解析完成 → 自动触发全量评分 + 切到"强烈推荐"Tab。
  // 监听 parsedProfile 从 null→object 的转变，避免重复触发（ref 记录上次值）。
  const lastProfileRef = useRef<unknown>(null);
  useEffect(() => {
    if (parsedProfile && parsedProfile !== lastProfileRef.current) {
      lastProfileRef.current = parsedProfile;
      void scoreAll(parsedProfile).then((result) => {
        if (result && result.strong_count > 0) {
          setActiveTab("hot");
        } else if (result && result.recommend_count > 0) {
          setActiveTab("recommend");
        }
      });
    }
  }, [parsedProfile, scoreAll]);

  // Tab 切换：推荐 Tab 触发 loadScoredJobs（按区间过滤）
  function handleTabClick(tab: TabKey) {
    setActiveTab(tab);
    if (tab === "hot") {
      void loadScoredJobs({ min_score: THRESHOLD_STRONG });
    } else if (tab === "recommend") {
      void loadScoredJobs({
        min_score: THRESHOLD_RECOMMEND,
        max_score: THRESHOLD_STRONG,
      });
    } else if (tab === "can_apply") {
      void loadScoredJobs({
        min_score: THRESHOLD_CAN_APPLY,
        max_score: THRESHOLD_RECOMMEND,
      });
    }
  }

  // 推荐 Tab 下的列表数据来源
  const isRecommendTab = activeTab !== "all";
  const visibleJobs = isRecommendTab ? scoredJobs : jobs;
  const visibleIsLoading = isRecommendTab ? isScoredLoading : isLoading;
  const visibleIsLoadingMore = isRecommendTab ? isScoredLoadingMore : isLoadingMore;
  const visibleHasMore = isRecommendTab ? scoredHasMore : hasMore;
  const visibleError = isRecommendTab ? scoreError : jobsError;
  const handleLoadMore = isRecommendTab ? loadScoredJobsMore : loadMore;

  const isEmpty = !visibleIsLoading && visibleJobs.length === 0;

  // Tab 数量：scoreSummary 已加载时显示，未加载时不显示数字
  const tabs: TabDef[] = [
    { key: "all", label: "全部岗位" },
    {
      key: "hot",
      label: "🔥 强烈推荐",
      count: scoreSummary?.strong_recommend,
    },
    {
      key: "recommend",
      label: "✅ 推荐",
      count: scoreSummary?.recommend,
    },
    {
      key: "can_apply",
      label: "➖ 可申请",
      count: scoreSummary?.can_apply,
    },
  ];

  return (
    <div className="space-y-4">
      {/* 顶部：标题 + 统计 + 同步指示器 */}
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold text-slate-deep">岗位</h1>
        <StatsBar />
        <div className="ml-auto">
          <SyncIndicator />
        </div>
      </div>

      {/* 评分进度提示：评分中显示 scored / total */}
      {isScoring && scoringProgress && (
        <div className="rounded-xl bg-orange-50 px-4 py-2 text-sm text-orange-700">
          🤖 正在评分岗位… 已评 {scoringProgress.scored} / {scoringProgress.total}
        </div>
      )}

      {/* Tab 切换 */}
      <div className="flex flex-wrap items-center gap-2">
        {tabs.map((t) => (
          <TabButton
            key={t.key}
            active={activeTab === t.key}
            onClick={() => handleTabClick(t.key)}
            disabled={isScoring && t.key !== "all"}
          >
            {t.label}
            {t.count != null && t.count > 0 && (
              <span className="ml-1 rounded-full bg-orange-100 px-1.5 text-xs font-semibold text-orange-700">
                {t.count}
              </span>
            )}
          </TabButton>
        ))}
      </div>

      {/* 筛选栏（sticky；推荐 Tab 隐藏，因为推荐 Tab 已按分数区间过滤） */}
      {activeTab === "all" && <JobFilterBar />}

      {/* 错误条 */}
      {visibleError && (
        <div className="rounded-xl bg-red-50 px-4 py-2 text-sm text-red-600">
          {visibleError}
        </div>
      )}

      {/* 主体：skeleton / 空状态 / 列表 + 加载更多 */}
      {visibleIsLoading ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : isEmpty ? (
        <div className="flex h-64 flex-col items-center justify-center rounded-2xl bg-white shadow-card">
          <div className="text-4xl">🔍</div>
          <p className="mt-2 text-base font-medium text-slate-deep">
            {isRecommendTab ? "暂无此区间的岗位" : "暂无匹配的岗位"}
          </p>
          <p className="mt-1 text-sm text-slate-500">
            {isRecommendTab
              ? parsedProfile
                ? "试试切换到其他推荐 Tab，或先在全部岗位里查找"
                : "请先上传简历并完成 LLM 解析，系统会自动评分并推荐匹配岗位"
              : "试试调整筛选条件，或先同步岗位数据"}
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {visibleJobs.map((job) => (
              <JobCard
                key={job.job_id}
                job={job}
                recommendMode={isRecommendTab}
              />
            ))}
          </div>

          {visibleHasMore && (
            <div className="flex justify-center pt-2">
              <button
                type="button"
                onClick={() => void handleLoadMore()}
                disabled={visibleIsLoadingMore}
                className="rounded-xl border border-orange-200 bg-white px-6 py-2 text-sm font-medium text-orange-700 transition hover:bg-orange-50 disabled:opacity-50"
              >
                {visibleIsLoadingMore ? "加载中…" : "加载更多"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
