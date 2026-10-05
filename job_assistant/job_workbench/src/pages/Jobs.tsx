// 岗位列表页面：字段对齐飞书「27届校招汇总表」。
// 功能：统计卡片、列筛选（多选）、列显隐（默认全显示）、首列固定、长文本截断、彩色标签、链接。
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { getStatsOverview, type StatsOverview } from "../api/companies";
import { jobsRecommendApi, type RecommendedJob } from "../api/jobsRecommend";
import { extractErrorMessage } from "../api/client";
import { useJobsStore } from "../stores/jobsStore";
import { useAppStore, type AppStatus, type Application } from "../stores/appStore";
import { useResumeStore } from "../stores/resumeStore";
import { colorMap, pillClass } from "../utils/colorMap";
import { openExternalUrl } from "../utils/link";
import Truncate from "../components/Truncate";
import ColumnFilter from "../components/ColumnFilter";
import ColumnSettings, { type ColumnDef } from "../components/ColumnSettings";

/** 列定义（对齐飞书源表顺序） */
const COLUMNS: ColumnDef[] = [
  { key: "actions", label: "操作" },
  { key: "title", label: "岗位标题" },
  { key: "company", label: "公司" },
  { key: "industry", label: "行业" },
  { key: "company_type", label: "公司类型" },
  { key: "category", label: "岗位分类" },
  { key: "subcategory", label: "岗位子类" },
  { key: "city", label: "城市" },
  { key: "min_education", label: "最低学历" },
  { key: "is_mt", label: "管培" },
  { key: "major_category", label: "专业大类" },
  { key: "major_required", label: "专业要求" },
  { key: "hard_skills", label: "硬技能" },
  { key: "keywords", label: "关键词" },
  { key: "jd_summary", label: "JD摘要" },
  { key: "difficulty", label: "难度" },
  { key: "updated_at", label: "发布时间" },
  { key: "deadline", label: "截止时间" },
  { key: "links", label: "链接" },
];

/** 分类列（有筛选选项，多选 IN）；其余列为文本搜索列（LIKE） */
const CATEGORY_COLUMNS = new Set([
  "industry",
  "company_type",
  "category",
  "subcategory",
  "min_education",
  "is_mt",
  "major_category",
  "difficulty",
]);

export default function Jobs() {
  const navigate = useNavigate();
  const {
    jobs,
    isLoading,
    isLoadingMore,
    error,
    keyword,
    columnFilters,
    total,
    hasMore,
    loadJobs,
    setKeyword,
    setColumnFilter,
    clearAllFilters,
    loadMore,
  } = useJobsStore();

  const [stats, setStats] = useState<StatsOverview | null>(null);
  const [visibleKeys, setVisibleKeys] = useState<string[]>(COLUMNS.map((c) => c.key));
  const scrollRef = useRef<HTMLDivElement>(null);
  const [kwInput, setKwInput] = useState("");

  // === 推荐视图状态 ===
  const [activeTab, setActiveTab] = useState<"all" | "recommend">("all");
  const [recommendJobs, setRecommendJobs] = useState<RecommendedJob[]>([]);
  const [recommendLoading, setRecommendLoading] = useState(false);
  const [recommendError, setRecommendError] = useState<string | null>(null);
  const serverProfile = useResumeStore((s) => s.serverProfile);

  // 切到推荐 tab 时自动拉取
  useEffect(() => {
    if (activeTab !== "recommend") return;
    if (!serverProfile) {
      setRecommendJobs([]);
      setRecommendError(null);
      return;
    }
    let cancelled = false;
    setRecommendLoading(true);
    setRecommendError(null);
    jobsRecommendApi
      .recommend(200)
      .then((res) => {
        if (cancelled) return;
        setRecommendJobs(res.jobs);
      })
      .catch((e) => {
        if (cancelled) return;
        setRecommendError(extractErrorMessage(e));
      })
      .finally(() => {
        if (!cancelled) setRecommendLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeTab, serverProfile]);

  const applications = useAppStore((s) => s.applications);
  const loadApplications = useAppStore((s) => s.loadApplications);

  // 加载统计（含筛选选项）
  useEffect(() => {
    getStatsOverview().then(setStats).catch(() => {});
  }, []);

  // 加载投递记录（用于按钮状态反馈）
  useEffect(() => {
    void loadApplications();
  }, [loadApplications]);

  // 首次加载
  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  // 按岗位查匹配的投递记录
  const appByJob = (jobId: string): Application | undefined =>
    applications.find((a) => a.link_type === "job" && a.link_id === jobId);

  // 滚动加载更多
  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 200) {
      void loadMore();
    }
  };

  const hasFilter =
    keyword.trim() !== "" || Object.values(columnFilters).some((v) => v.length);

  const filterOptions = stats?.jobs.filter_options ?? {};

  /** 把后端 filter_options 的值统一转成 {label, value} */
  const getOptions = (key: string) => {
    const raw = filterOptions[key] ?? [];
    return raw.map((o) =>
      typeof o === "string" ? { label: o, value: o } : { label: o.label, value: o.value }
    );
  };

  return (
    <div className="flex h-full flex-col gap-4">
      {/* 统计卡片（仅全部岗位视图显示） */}
      {activeTab === "all" && stats && <JobsStatsCards stats={stats} />}

      {/* Tab 切换 */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setActiveTab("all")}
          className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
            activeTab === "all"
              ? "bg-ink text-white shadow-sm"
              : "bg-white/60 text-text-muted hover:text-text"
          }`}
        >
          📋 全部岗位 <span className="opacity-60">({total})</span>
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("recommend")}
          className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
            activeTab === "recommend"
              ? "bg-ink text-white shadow-sm"
              : "bg-white/60 text-text-muted hover:text-text"
          }`}
        >
          🎯 为我推荐
          {serverProfile && <span className="ml-1 text-xs opacity-60">({recommendJobs.length}/200)</span>}
        </button>
        {activeTab === "recommend" && recommendJobs.length > 0 && (
          <button
            type="button"
            onClick={() => setRecommendLoading(true)}
            className="ml-auto rounded-lg border border-line bg-white/60 px-3 py-1.5 text-xs text-text-muted hover:bg-white"
          >
            🔄 刷新推荐
          </button>
        )}
      </div>

      {activeTab === "recommend" && !serverProfile && (
        <div className="flex flex-col items-center gap-3 rounded-xl bg-warning-soft/50 p-8 text-center">
          <div className="text-4xl">📄</div>
          <div className="text-base font-medium text-warning-dark">
            还没有简历画像,无法为你推荐岗位
          </div>
          <div className="text-sm text-warning-dark/80">
            上传简历后,AI 会按匹配度为你打分推荐
          </div>
          <button
            type="button"
            onClick={() => navigate("/resume")}
            className="rounded-pill bg-primary px-5 py-2 text-sm font-semibold text-ink hover:bg-primary-dark"
          >
            去上传简历 →
          </button>
        </div>
      )}

      {activeTab === "recommend" && (
        <RecommendJobsList
          jobs={recommendJobs}
          loading={recommendLoading}
          error={recommendError}
          appByJob={appByJob}
          onOpenApply={(url) => url && openExternalUrl(url)}
        />
      )}

      {activeTab !== "recommend" && (
        <>
      {/* 工具栏 */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <input
            type="text"
            value={kwInput}
            onChange={(e) => setKwInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") setKeyword(kwInput);
            }}
            placeholder="搜索岗位 / 公司 / JD（回车确认）..."
            className="w-full rounded-lg border border-line bg-white/60 px-3 py-2 text-sm outline-none focus:border-primary"
          />
        </div>
        {hasFilter && (
          <button
            type="button"
            onClick={() => {
              clearAllFilters();
              setKwInput("");
            }}
            className="rounded-lg border border-line bg-white/60 px-3 py-2 text-sm text-text-muted hover:bg-white"
          >
            清除筛选
          </button>
        )}
        <ColumnSettings
          columns={COLUMNS}
          tableKey="jobs"
          visibleKeys={visibleKeys}
          onChange={setVisibleKeys}
        />
      </div>

      {/* 已选筛选 chip */}
      {hasFilter && (
        <div className="flex flex-wrap gap-2">
          {keyword.trim() && (
            <FilterChip label={`搜索: ${keyword}`} onClose={() => setKeyword("")} />
          )}
          {Object.entries(columnFilters).map(([col, vals]) =>
            vals.map((v) => (
              <FilterChip
                key={`${col}-${v}`}
                label={`${COLUMNS.find((c) => c.key === col)?.label}: ${v}`}
                onClose={() =>
                  setColumnFilter(
                    col,
                    (columnFilters[col] ?? []).filter((x) => x !== v)
                  )
                }
              />
            ))
          )}
        </div>
      )}

      {error && (
        <div className="rounded-lg bg-danger-soft px-4 py-2 text-sm text-danger">{error}</div>
      )}

      {/* 表格 */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-auto rounded-xl border border-line bg-white/40 backdrop-blur"
      >
        <table className="w-full min-w-[1400px] border-collapse text-sm">
          <thead className="sticky top-0 z-10">
            <tr className="bg-white/85 backdrop-blur-md">
              {COLUMNS.filter((c) => visibleKeys.includes(c.key)).map((col) => {
                const isFirst = col.key === "title";
                return (
                  <th
                    key={col.key}
                    className={`border-b border-line px-3 py-2.5 text-left font-medium text-ink ${
                      isFirst
                        ? "sticky left-0 z-20 bg-white/85 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]"
                        : ""
                    }`}
                    style={{ minWidth: jobColWidth(col.key) }}
                  >
                    <div className="flex items-center">
                      <span>{col.label}</span>
                      <ColumnFilter
                        columnName={col.label}
                        value={columnFilters[col.key] ?? []}
                        options={
                          CATEGORY_COLUMNS.has(col.key) ? getOptions(col.key) : undefined
                        }
                        onChange={(vals) => setColumnFilter(col.key, vals)}
                      />
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={visibleKeys.length} className="px-3 py-8 text-center text-text-faint">
                  加载中...
                </td>
              </tr>
            ) : jobs.length === 0 ? (
              <tr>
                <td colSpan={visibleKeys.length} className="px-3 py-8 text-center text-text-faint">
                  暂无数据
                </td>
              </tr>
            ) : (
              jobs.map((j) => (
                <JobRow key={j.job_id} job={j} visibleKeys={visibleKeys} application={appByJob(j.job_id)} />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 加载更多 */}
      <div className="flex items-center justify-between text-xs text-text-muted">
        <span>
          共 {total} 个岗位，已加载 {jobs.length} 条
        </span>
        {isLoadingMore ? (
          <span>加载更多...</span>
        ) : hasMore ? (
          <button
            type="button"
            onClick={() => void loadMore()}
            className="text-primary-dark hover:underline"
          >
            加载更多
          </button>
        ) : (
          <span>已加载全部</span>
        )}
      </div>
        </>
      )}
    </div>
  );
}

function jobColWidth(key: string): string {
  switch (key) {
    case "actions":
      return "70px";
    case "title":
      return "200px";
    case "company":
      return "140px";
    case "industry":
    case "company_type":
    case "category":
    case "subcategory":
    case "min_education":
    case "is_mt":
    case "major_category":
    case "difficulty":
      return "100px";
    case "city":
      return "120px";
    case "major_required":
      return "120px";
    case "hard_skills":
    case "keywords":
      return "140px";
    case "jd_summary":
      return "240px";
    case "updated_at":
    case "deadline":
      return "100px";
    case "links":
      return "120px";
    default:
      return "120px";
  }
}

function JobRow({
  job,
  visibleKeys,
  application,
}: {
  job: import("../api/jobs").Job;
  visibleKeys: string[];
  application?: Application;
}) {
  const addApplication = useAppStore((s) => s.addApplication);
  const removeApplication = useAppStore((s) => s.removeApplication);
  const [busy, setBusy] = useState(false);

  const status = application?.status;
  const isFavorited = status === "favorite";
  const isApplied = status === "applied";
  const inPipeline = !!application && !isFavorited && !isApplied;

  async function quickAdd(status: AppStatus) {
    if (busy) return;
    setBusy(true);
    try {
      await addApplication({
        source: "db_job",
        link_type: "job",
        link_id: job.job_id,
        company_name: job.company,
        job_title: job.title,
        status,
        apply_url: job.apply_url || undefined,
        announcement_url: job.announcement_url || undefined,
      });
    } finally {
      setBusy(false);
    }
  }

  // 点击收藏：已收藏则取消，否则设为收藏
  const handleFavorite = () => {
    if (isFavorited && application) {
      void removeApplication(application.id);
    } else {
      void quickAdd("favorite");
    }
  };

  // 点击投递：已投递则取消，否则设为已投递并打开投递链接
  const handleApply = async () => {
    if (isApplied && application) {
      await removeApplication(application.id);
    } else {
      await quickAdd("applied");
      // 投递成功后自动打开投递链接，用户用牛客插件填表
      if (job.apply_url) {
        openExternalUrl(job.apply_url);
      }
    }
  };

  const cells: Record<string, ReactNode> = {
    actions: (
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={handleFavorite}
          disabled={busy}
          className={`relative rounded px-1.5 py-0.5 text-xs transition disabled:opacity-50 ${
            isFavorited
              ? "bg-primary text-ink"
              : inPipeline
                ? "bg-primary-soft/60 text-primary-dark"
                : "bg-white/60 text-text-muted hover:bg-primary-soft hover:text-primary-dark"
          }`}
          title={isFavorited ? "取消收藏" : "加入收藏"}
        >
          {isFavorited ? "⭐" : "☆"}
          {inPipeline && (
            <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-success" />
          )}
        </button>
        <button
          type="button"
          onClick={handleApply}
          disabled={busy}
          className={`relative rounded px-1.5 py-0.5 text-xs transition disabled:opacity-50 ${
            isApplied
              ? "bg-success text-white"
              : inPipeline
                ? "bg-success-soft text-success"
                : "bg-primary-soft font-medium text-primary-dark hover:bg-primary hover:text-ink"
          }`}
          title={isApplied ? "取消投递" : "标记已投递"}
        >
          📮
          {inPipeline && (
            <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-success" />
          )}
        </button>
      </div>
    ),
    title: <Truncate text={job.title} className="font-medium" />,
    company: <Truncate text={job.company} />,
    industry: job.industry ? (
      <span className={pillClass(colorMap.industry(job.industry))}>{job.industry}</span>
    ) : (
      <span className="text-text-faint">—</span>
    ),
    company_type: job.company_type ? (
      <span className={pillClass(colorMap.companyType(job.company_type))}>{job.company_type}</span>
    ) : (
      <span className="text-text-faint">—</span>
    ),
    category: job.category ? (
      <span className={pillClass(colorMap.category(job.category))}>{job.category}</span>
    ) : (
      <span className="text-text-faint">—</span>
    ),
    subcategory: (
      <Truncate text={job.subcategory} className="text-ink-soft" />
    ),
    city: <Truncate text={job.city} className="text-ink-soft" />,
    min_education: job.min_education ? (
      <span className={pillClass(colorMap.education(job.min_education))}>{job.min_education}</span>
    ) : (
      <span className="text-text-faint">—</span>
    ),
    is_mt: (
      <span className={pillClass(colorMap.isMt(job.is_mt))}>
        {job.is_mt ? "是" : "否"}
      </span>
    ),
    major_category: job.major_category ? (
      <span className="text-ink-soft">{job.major_category}</span>
    ) : (
      <span className="text-text-faint">—</span>
    ),
    major_required: (
      <Truncate text={job.major_required} className="text-ink-soft" />
    ),
    hard_skills: (
      <Truncate text={job.hard_skills} className="text-ink-soft" />
    ),
    keywords: (
      <Truncate text={job.keywords} className="text-ink-soft" />
    ),
    jd_summary: (
      <Truncate text={job.jd_summary} maxLines={2} className="text-ink-soft" />
    ),
    difficulty: job.difficulty ? (
      <span className={pillClass(colorMap.difficulty(job.difficulty))}>{job.difficulty}</span>
    ) : (
      <span className="text-text-faint">—</span>
    ),
    updated_at: <span className="text-ink-soft">{job.updated_at || "—"}</span>,
    deadline: <span className="text-ink-soft">{job.deadline ?? "—"}</span>,
    links: (
      <div className="flex gap-1">
        {job.apply_url && <LinkButton url={job.apply_url} label="投递" />}
        {job.announcement_url && <LinkButton url={job.announcement_url} label="公告" />}
        {!job.apply_url && !job.announcement_url && <span className="text-text-faint">—</span>}
      </div>
    ),
  };

  return (
    <tr className="border-b border-line/60 hover:bg-white/40">
      {COLUMNS.filter((c) => visibleKeys.includes(c.key)).map((col) => {
        const isFirst = col.key === "title";
        return (
          <td
            key={col.key}
            className={`px-3 py-2 align-middle ${
              isFirst ? "sticky left-0 z-[1] bg-white/70 backdrop-blur" : ""
            }`}
          >
            {cells[col.key]}
          </td>
        );
      })}
    </tr>
  );
}

function LinkButton({ url, label }: { url: string; label: string }) {
  return (
    <button
      type="button"
      onClick={() => { void openExternalUrl(url); }}
      className="rounded bg-primary-soft px-2 py-0.5 text-xs text-primary-dark transition hover:bg-primary-light"
      title={url}
    >
      {label}
    </button>
  );
}

function FilterChip({ label, onClose }: { label: string; onClose: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-primary-soft px-2.5 py-1 text-xs text-ink">
      {label}
      <button type="button" onClick={onClose} className="text-text-muted hover:text-ink">
        ✕
      </button>
    </span>
  );
}

function JobsStatsCards({ stats }: { stats: StatsOverview }) {
  const j = stats.jobs;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-5">
      <StatCard label="岗位总数" value={j.total} accent="primary" />
      <StatCard label="今日新增" value={j.today_new} accent="success" />
      <StatCard label="近7日新增" value={j.week_new} accent="info" />
      <CategoryBar items={j.top_categories} />
      <div className="rounded-xl border border-line bg-white/50 px-4 py-3 backdrop-blur">
        <div className="text-xs text-text-muted">数据更新</div>
        <div className="mt-1 text-sm font-medium text-ink">每日 08:00 同步</div>
        <div className="mt-1 text-xs text-text-faint">来源：服务器主库</div>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: "primary" | "success" | "info";
}) {
  const color = {
    primary: "text-primary-dark",
    success: "text-success",
    info: "text-blue-600",
  }[accent];
  return (
    <div className="rounded-xl border border-line bg-white/50 px-4 py-3 backdrop-blur">
      <div className="text-xs text-text-muted">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${color}`}>{value.toLocaleString()}</div>
    </div>
  );
}

function CategoryBar({ items }: { items: { name: string; count: number }[] }) {
  const max = items[0]?.count ?? 1;
  return (
    <div className="rounded-xl border border-line bg-white/50 px-4 py-3 backdrop-blur sm:col-span-2 lg:col-span-2">
      <div className="mb-2 text-xs text-text-muted">岗位分类 Top8</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        {items.map((it) => (
          <div key={it.name} className="flex items-center gap-2 text-xs">
            <span className="w-20 shrink-0 truncate text-ink-soft">{it.name}</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded bg-gray-100">
              <div
                className="h-full rounded bg-primary"
                style={{ width: `${(it.count / max) * 100}%` }}
              />
            </div>
            <span className="w-8 text-right text-text-muted">{it.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RecommendJobsList({
  jobs,
  loading,
  error,
  appByJob,
  onOpenApply,
}: {
  jobs: RecommendedJob[];
  loading: boolean;
  error: string | null;
  appByJob: (jobId: string) => Application | undefined;
  onOpenApply: (url: string) => void;
}) {
  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center rounded-xl border border-line bg-white/40 py-16">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-primary-soft border-t-primary" />
        <p className="ml-3 text-sm text-text-muted">AI 正在匹配你的简历…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-danger-soft bg-danger-soft/30 px-4 py-3 text-sm text-danger">
        ⚠️ 推荐失败：{error}
      </div>
    );
  }

  if (jobs.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center rounded-xl border border-line bg-white/40 py-16 text-text-faint">
        暂无推荐岗位，请先上传简历解析
      </div>
    );
  }

  // 按 recommend_level 分组：超级推荐 / 推荐 / 其他
  const groups: Record<string, RecommendedJob[]> = {
    超级推荐: jobs.filter((j) => j.recommend_level === "super_recommend"),
    推荐: jobs.filter((j) => j.recommend_level === "recommend"),
    其他: jobs.filter((j) => j.recommend_level !== "super_recommend" && j.recommend_level !== "recommend"),
  };

  return (
    <div className="flex-1 overflow-auto rounded-xl border border-line bg-white/40">
      <div className="p-3 text-xs text-text-muted">
        共 {jobs.length} 个岗位：超级推荐 {groups["超级推荐"].length} · 推荐 {groups["推荐"].length}
      </div>

      {Object.entries(groups).map(([groupName, groupJobs]) => {
        if (groupJobs.length === 0) return null;
        const isTop = groupName === "超级推荐";
        return (
          <div key={groupName} className={isTop ? "border-t-2 border-primary/30 bg-primary/5" : ""}>
            <div className="flex items-center gap-2 px-4 py-2">
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                  isTop
                    ? "bg-primary text-ink"
                    : groupName === "推荐"
                    ? "bg-success-soft text-success"
                    : "bg-white/60 text-text-muted"
                }`}
              >
                {groupName}
              </span>
              <span className="text-xs text-text-muted">{groupJobs.length} 个岗位</span>
            </div>

            {groupJobs.map((job, idx) => {
              const app = appByJob(job.job_id);
              const isApplied = app?.status === "applied";
              const scoreColor =
                job.score >= 80
                  ? "bg-success"
                  : job.score >= 60
                  ? "bg-primary"
                  : job.score >= 40
                  ? "bg-warning"
                  : "bg-slate-400";

              return (
                <div
                  key={job.job_id}
                  className={`border-b border-line/50 px-4 py-3 transition hover:bg-white/60 ${
                    isTop && idx === 0 ? "" : ""
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-text">
                          {job.title}
                        </span>
                        {app && (
                          <span className="rounded-full bg-success-soft px-1.5 py-0.5 text-[10px] text-success">
                            已投递
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 text-xs text-text-muted">
                        {job.company}
                        {job.city && ` · ${job.city}`}
                        {job.min_education && ` · ${job.min_education}`}
                        {job.industry && ` · ${job.industry}`}
                      </div>

                      {/* 匹配度条 */}
                      <div className="mt-2 flex items-center gap-2">
                        <div className="h-1.5 w-28 overflow-hidden rounded bg-gray-200">
                          <div
                            className={`h-full rounded ${scoreColor}`}
                            style={{ width: `${Math.min(100, job.score)}%` }}
                          />
                        </div>
                        <span className="text-xs font-medium text-text">
                          {job.score.toFixed(0)}%
                        </span>
                        <span className="text-xs text-text-faint">
                          {job.recommend || ""}
                        </span>
                      </div>

                      {/* 前 2 条推荐理由 */}
                      {job.reasons && job.reasons.length > 0 && (
                        <div className="mt-1.5 space-y-0.5 text-[11px] text-text-muted">
                          {job.reasons.slice(0, 2).map((r, i) => {
                            // 去掉 [skill] [hard_skill] 这种前缀标签的括号
                            const clean = r.replace(/^\[([^\]]+)\]\s*/, "");
                            return (
                              <div key={i} className="truncate" title={r}>
                                <span className="mr-1 text-text-faint">•</span>
                                {clean}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>

                    {/* 投递按钮 */}
                    {job.apply_url && (
                      <button
                        type="button"
                        onClick={() => onOpenApply(job.apply_url)}
                        className={`shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                          isApplied
                            ? "bg-success-soft text-success hover:bg-success/10"
                            : "bg-primary text-ink hover:bg-primary-light"
                        }`}
                      >
                        {isApplied ? "📮 已投递" : "📮 投递"}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
