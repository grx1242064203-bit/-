// 岗位列表页面：字段对齐飞书「27届校招汇总表」。
// 功能：统计卡片、列筛选（多选）、列显隐（默认全显示）、首列固定、长文本截断、彩色标签、链接。
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { getStatsOverview, type StatsOverview } from "../api/companies";
import { type RecommendedJob } from "../api/jobsRecommend";
import { useJobsStore } from "../stores/jobsStore";
import { useAppStore, type AppStatus, type Application } from "../stores/appStore";
import { useResumeStore } from "../stores/resumeStore";
import { colorMap, pillClass } from "../utils/colorMap";
import { openExternalUrl } from "../utils/link";
import Truncate from "../components/Truncate";
import ColumnFilter from "../components/ColumnFilter";
import ColumnSettings, { type ColumnDef } from "../components/ColumnSettings";

/** 列定义（对齐飞书源表顺序）
 * 操作 + 链接列固定在左侧,滚动时常驻可见 */
const COLUMNS: ColumnDef[] = [
  { key: "actions", label: "操作" },
  { key: "links", label: "链接" },
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
  // 推荐数据移到 appStore,切页不丢失
  const recommendJobs = useAppStore((s) => s.recommendJobs);
  const recommendLoading = useAppStore((s) => s.recommendLoading);
  const recommendError = useAppStore((s) => s.recommendError);
  const loadRecommendJobs = useAppStore((s) => s.loadRecommendJobs);
  const clearRecommendJobs = useAppStore((s) => s.clearRecommendJobs);
  // 推荐筛选: 行业/公司类型/招聘类型/学历/难度 多选 + 关键词 + 推荐等级 + 分数下限
  const [recFilterIndustry, setRecFilterIndustry] = useState<string[]>([]);
  const [recFilterCompanyType, setRecFilterCompanyType] = useState<string[]>([]);
  const [recFilterRecruitType, setRecFilterRecruitType] = useState<string[]>([]);
  const [recFilterEdu, setRecFilterEdu] = useState<string[]>([]);
  const [recFilterDifficulty, setRecFilterDifficulty] = useState<string[]>([]);
  const [recFilterKeyword, setRecFilterKeyword] = useState("");
  const [recFilterLevel, setRecFilterLevel] = useState<string>("all");
  const [recFilterMinScore, setRecFilterMinScore] = useState(0);
  const serverProfile = useResumeStore((s) => s.serverProfile);

  // 切到推荐 tab 时自动拉取(有缓存就直接复用,不重新跑评分)
  useEffect(() => {
    if (activeTab !== "recommend") return;
    if (!serverProfile) {
      clearRecommendJobs();
      return;
    }
    void loadRecommendJobs(200, false);
  }, [activeTab, serverProfile, loadRecommendJobs, clearRecommendJobs]);

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
            onClick={() => void loadRecommendJobs(200, true)}
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
          filterOptions={{
            // 公司维度筛选选项(行业/公司类型/招聘类型/学历)
            industry: stats?.companies.filter_options?.industry ?? [],
            company_type: stats?.companies.filter_options?.company_type ?? [],
            recruit_type: stats?.companies.filter_options?.recruit_type ?? [],
            education_req: stats?.companies.filter_options?.education_req ?? [],
            // 难度是岗位字段,从 jobs.filter_options 取
            difficulty: (stats?.jobs.filter_options?.difficulty ?? []) as string[],
          }}
          onCreateFavorite={async (job) => {
            const app = useAppStore.getState();
            const created = await app.addApplication({
              job_title: job.title,
              company_name: job.company,
              status: "favorite",
              source: "db_job",
              link_type: "job",
              link_id: job.job_id,
              apply_url: job.apply_url || "",
              announcement_url: job.announcement_url || "",
            });
            return created ?? undefined;
          }}
          onCreateApplied={async (job) => {
            const app = useAppStore.getState();
            const created = await app.addApplication({
              job_title: job.title,
              company_name: job.company,
              status: "applied",
              source: "db_job",
              link_type: "job",
              link_id: job.job_id,
              apply_url: job.apply_url || "",
              announcement_url: job.announcement_url || "",
            });
            return created ?? undefined;
          }}
          onRemoveApplication={async (appId) => {
            const app = useAppStore.getState();
            await app.removeApplication(appId);
          }}
          filters={{
            industry: recFilterIndustry,
            companyType: recFilterCompanyType,
            recruitType: recFilterRecruitType,
            minEducation: recFilterEdu,
            difficulty: recFilterDifficulty,
            keyword: recFilterKeyword,
            level: recFilterLevel,
            minScore: recFilterMinScore,
          }}
          onFilterChange={(patch) => {
            if (patch.industry !== undefined) setRecFilterIndustry(patch.industry);
            if (patch.companyType !== undefined) setRecFilterCompanyType(patch.companyType);
            if (patch.recruitType !== undefined) setRecFilterRecruitType(patch.recruitType);
            if (patch.minEducation !== undefined) setRecFilterEdu(patch.minEducation);
            if (patch.difficulty !== undefined) setRecFilterDifficulty(patch.difficulty);
            if (patch.keyword !== undefined) setRecFilterKeyword(patch.keyword);
            if (patch.level !== undefined) setRecFilterLevel(patch.level);
            if (patch.minScore !== undefined) setRecFilterMinScore(patch.minScore);
          }}
          onClearFilters={() => {
            setRecFilterIndustry([]);
            setRecFilterCompanyType([]);
            setRecFilterRecruitType([]);
            setRecFilterEdu([]);
            setRecFilterDifficulty([]);
            setRecFilterKeyword("");
            setRecFilterLevel("all");
            setRecFilterMinScore(0);
          }}
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
                // 与行级一致的固定列判断:actions 最左 + links 紧随其后
                // 注意:Tailwind JIT 只识别静态类名,w-[72px]/left-[72px] 必须字面量
                const isActionsSticky = col.key === "actions";
                const isLinksSticky = col.key === "links";
                const stickyClass = isActionsSticky
                  ? "sticky left-0 z-20 bg-white/85 backdrop-blur w-[72px] min-w-[72px] shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]"
                  : isLinksSticky
                  ? "sticky left-[72px] z-20 bg-white/85 backdrop-blur shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]"
                  : "";
                return (
                  <th
                    key={col.key}
                    className={`border-b border-line px-3 py-2.5 text-left font-medium text-ink ${stickyClass}`}
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
                ? "bg-primary-soft/60 text-primary-ink"
                : "bg-white/60 text-text-muted hover:bg-primary-soft hover:text-primary-ink"
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
                : "bg-primary-soft font-medium text-primary-ink hover:bg-primary hover:text-ink"
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
    title: (
      <Truncate
        text={job.company ? `${job.title} - ${job.company}` : job.title}
        className="font-medium"
      />
    ),
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
        // 操作列固定最左,链接列紧随其后固定,滚动时常驻可见
        // 注意:Tailwind JIT 只识别静态类名,所以 w-[72px]/left-[72px] 必须以字面量出现
        const isActionsSticky = col.key === "actions";
        const isLinksSticky = col.key === "links";
        const stickyClass = isActionsSticky
          ? "sticky left-0 z-[2] bg-white/85 backdrop-blur w-[72px] min-w-[72px]"
          : isLinksSticky
          ? "sticky left-[72px] z-[2] bg-white/85 backdrop-blur"
          : "";
        return (
          <td
            key={col.key}
            className={`px-3 py-2 align-middle ${stickyClass}`}
          >
            {cells[col.key]}
          </td>
        );
      })}
    </tr>
  );
}

function LinkButton({ url, label }: { url: string; label: string }) {
  // 投递=success 绿色,公告=info 蓝色,与暖橙背景对比鲜明
  const isApply = label === "投递";
  const colorClass = isApply
    ? "bg-success-soft text-success hover:bg-success hover:text-white"
    : "bg-info-soft text-info hover:bg-info hover:text-white";
  return (
    <button
      type="button"
      onClick={() => { void openExternalUrl(url); }}
      className={`rounded px-2 py-0.5 text-xs font-medium transition ${colorClass}`}
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
  onCreateFavorite,
  onCreateApplied,
  onRemoveApplication,
  filterOptions,
  filters,
  onFilterChange,
  onClearFilters,
}: {
  jobs: RecommendedJob[];
  loading: boolean;
  error: string | null;
  appByJob: (jobId: string) => Application | undefined;
  onOpenApply: (url: string) => void;
  onCreateFavorite: (job: RecommendedJob) => Promise<Application | undefined>;
  onCreateApplied: (job: RecommendedJob) => Promise<Application | undefined>;
  onRemoveApplication: (appId: number) => Promise<void>;
  filterOptions?: Record<string, string[]>;
  filters: {
    industry: string[];
    companyType: string[];
    recruitType: string[];
    minEducation: string[];
    difficulty: string[];
    keyword: string;
    level: string;
    minScore: number;
  };
  onFilterChange: (patch: Partial<{
    industry: string[];
    companyType: string[];
    recruitType: string[];
    minEducation: string[];
    difficulty: string[];
    keyword: string;
    level: string;
    minScore: number;
  }>) => void;
  onClearFilters: () => void;
}) {
  // 应用筛选
  const filteredJobs = jobs.filter((j) => {
    if (filters.industry.length && !filters.industry.includes(j.industry)) return false;
    if (filters.companyType.length && !filters.companyType.includes(j.company_type)) return false;
    if (filters.recruitType.length && !(j.recruit_type && filters.recruitType.includes(j.recruit_type))) return false;
    if (filters.minEducation.length && !filters.minEducation.includes(j.min_education)) return false;
    if (filters.difficulty.length && !filters.difficulty.includes(j.difficulty)) return false;
    if (filters.level !== "all" && j.recommend_level !== filters.level) return false;
    if (filters.minScore > 0 && j.score < filters.minScore) return false;
    if (filters.keyword.trim()) {
      const kw = filters.keyword.trim().toLowerCase();
      const haystack = `${j.title} ${j.company} ${j.city} ${j.industry} ${j.keywords || ""} ${j.jd_summary || ""}`.toLowerCase();
      if (!haystack.includes(kw)) return false;
    }
    return true;
  });

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
    超级推荐: filteredJobs.filter((j) => j.recommend_level === "super_recommend"),
    推荐: filteredJobs.filter((j) => j.recommend_level === "recommend"),
    其他: filteredJobs.filter((j) => j.recommend_level !== "super_recommend" && j.recommend_level !== "recommend"),
  };

  // 筛选选项
  const opts = filterOptions ?? {};
  const hasFilter =
    filters.industry.length ||
    filters.companyType.length ||
    filters.recruitType.length ||
    filters.minEducation.length ||
    filters.difficulty.length ||
    filters.keyword.trim() ||
    filters.level !== "all" ||
    filters.minScore > 0;

  return (
    <div className="flex flex-1 flex-col overflow-hidden rounded-xl border border-line bg-white/40">
      {/* 筛选工具栏 */}
      <div className="border-b border-line/50 p-2">
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={filters.keyword}
            onChange={(e) => onFilterChange({ keyword: e.target.value })}
            placeholder="搜索岗位/公司/技能/JD..."
            className="flex-1 min-w-[200px] rounded-lg border border-line bg-white/70 px-3 py-1.5 text-xs outline-none focus:border-primary"
          />
          <select
            value={filters.level}
            onChange={(e) => onFilterChange({ level: e.target.value })}
            className="rounded-lg border border-line bg-white/70 px-2 py-1.5 text-xs"
          >
            <option value="all">全部等级</option>
            <option value="super_recommend">超级推荐</option>
            <option value="recommend">推荐</option>
            <option value="applyable">可申请</option>
            <option value="low">不建议</option>
          </select>
          <label className="flex items-center gap-1 text-xs text-text-muted">
            最低分
            <input
              type="range"
              min={0}
              max={100}
              step={10}
              value={filters.minScore}
              onChange={(e) => onFilterChange({ minScore: Number(e.target.value) })}
              className="h-1.5 w-24"
            />
            <span className="w-8 tabular-nums">{filters.minScore}</span>
          </label>
          {hasFilter && (
            <button
              type="button"
              onClick={onClearFilters}
              className="rounded-lg border border-line bg-white/70 px-2 py-1 text-xs text-text-muted hover:bg-white"
            >
              清除
            </button>
          )}
        </div>

        {/* 分类下拉框筛选 */}
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
          {[
            { key: "industry" as const, label: "行业", options: opts.industry ?? [], cur: filters.industry },
            { key: "companyType" as const, label: "公司类型", options: opts.company_type ?? [], cur: filters.companyType },
            { key: "recruitType" as const, label: "招聘类型", options: opts.recruit_type ?? [], cur: filters.recruitType },
            { key: "minEducation" as const, label: "学历", options: opts.education_req ?? [], cur: filters.minEducation },
            { key: "difficulty" as const, label: "难度", options: opts.difficulty ?? [], cur: filters.difficulty },
          ].map((grp) => (
            <select
              key={grp.key}
              multiple
              value={grp.cur}
              onChange={(e) => {
                const next = Array.from(e.target.selectedOptions).map((o) => o.value);
                onFilterChange({ [grp.key]: next } as never);
              }}
              className="rounded-lg border border-line bg-white/70 px-2 py-1 text-[11px] outline-none focus:border-primary"
              size={1}
            >
              <option value="">{grp.label}▼</option>
              {grp.options.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          ))}
        </div>
      </div>

      <div className="px-3 py-2 text-xs text-text-muted">
        筛选后 {filteredJobs.length} / 共 {jobs.length} 个岗位：超级推荐 {groups["超级推荐"].length} · 推荐 {groups["推荐"].length}
      </div>

      <div className="flex-1 overflow-auto">

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
              const isFavorite = app?.status === "favorite";
              const scoreColor =
                job.score >= 80
                  ? "bg-success"
                  : job.score >= 60
                  ? "bg-primary"
                  : job.score >= 40
                  ? "bg-amber-500"
                  : "bg-slate-400";

              // 字段胶囊(行业/公司类型/招聘类型/岗位分类/学历/管培/难度/公司层级/对齐)
              const pills: { label: string; value: string; pair?: { bg: string; text: string } }[] = [];
              if (job.industry) pills.push({ label: "行业", value: job.industry, pair: colorMap.industry(job.industry) });
              if (job.company_type) pills.push({ label: "公司类型", value: job.company_type, pair: colorMap.companyType(job.company_type) });
              if (job.recruit_type) pills.push({ label: "招聘类型", value: job.recruit_type, pair: colorMap.recruitType(job.recruit_type) });
              if (job.category) pills.push({ label: "岗位分类", value: job.category, pair: colorMap.category(job.category) });
              if (job.min_education) pills.push({ label: "学历", value: job.min_education, pair: colorMap.education(job.min_education) });
              if (job.is_mt) pills.push({ label: "管培", value: "是", pair: colorMap.isMt(1) });
              if (job.difficulty) pills.push({ label: "难度", value: job.difficulty, pair: colorMap.difficulty(job.difficulty) });
              // 公司层级(顶/中/保底)
              if (job.company_tier) {
                const tierPair: Record<string, { bg: string; text: string }> = {
                  "顶": { bg: "bg-rose-100", text: "text-rose-700" },
                  "中": { bg: "bg-blue-100", text: "text-blue-700" },
                  "保底": { bg: "bg-emerald-100", text: "text-emerald-700" },
                };
                pills.push({
                  label: "公司层级",
                  value: job.company_tier,
                  pair: tierPair[job.company_tier] || { bg: "bg-gray-100", text: "text-gray-600" },
                });
              }
              // 对齐标签(匹配/冲刺/保底/严重错配)- 候选人 vs 公司层级
              if (job.alignment_label) {
                const alignPair: Record<string, { bg: string; text: string }> = {
                  "匹配": { bg: "bg-emerald-500", text: "text-white" },
                  "冲刺": { bg: "bg-amber-500", text: "text-white" },
                  "保底": { bg: "bg-blue-500", text: "text-white" },
                  "严重错配": { bg: "bg-rose-500", text: "text-white" },
                };
                pills.push({
                  label: "对齐",
                  value: job.alignment_label,
                  pair: alignPair[job.alignment_label] || { bg: "bg-gray-100", text: "text-gray-600" },
                });
              }

              // 长文本字段
              const longFields: { label: string; value: string }[] = [];
              if (job.recruit_target) longFields.push({ label: "招聘对象", value: job.recruit_target });
              if (job.city) longFields.push({ label: "城市", value: job.city });
              if (job.subcategory) longFields.push({ label: "岗位子类", value: job.subcategory });
              if (job.major_category) longFields.push({ label: "专业大类", value: job.major_category });
              if (job.major_required) longFields.push({ label: "专业要求", value: job.major_required });
              if (job.hard_skills) longFields.push({ label: "硬技能", value: job.hard_skills });
              if (job.keywords) longFields.push({ label: "关键词", value: job.keywords });
              if (job.deadline) longFields.push({ label: "截止", value: String(job.deadline).slice(0, 10) });
              if (job.updated_at) longFields.push({ label: "发布", value: String(job.updated_at).slice(0, 10) });

              return (
                <div
                  key={`${job.job_id}-${idx}`}
                  className={`border-b border-line/50 px-4 py-3 transition hover:bg-white/60 ${
                    isTop ? "bg-primary/5" : ""
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-text">
                          {job.title}
                        </span>
                        {isApplied && (
                          <span className="rounded-full bg-success-soft px-1.5 py-0.5 text-[10px] font-medium text-success">
                            📮 已投递
                          </span>
                        )}
                        {isFavorite && !isApplied && (
                          <span className="rounded-full bg-amber-200 px-1.5 py-0.5 text-[10px] font-medium text-amber-900">
                            ⭐ 已收藏
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 text-xs text-text-muted">
                        {job.company}
                      </div>

                      {/* 彩色胶囊字段 */}
                      {pills.length > 0 && (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {pills.map((p) => (
                            <span
                              key={p.label}
                              className={pillClass(p.pair || { bg: "bg-gray-100", text: "text-gray-600" })}
                              title={`${p.label}: ${p.value}`}
                            >
                              {p.value}
                            </span>
                          ))}
                        </div>
                      )}

                      {/* 长文本字段 */}
                      {longFields.length > 0 && (
                        <div className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px] text-text-muted">
                          {longFields.map((f) => (
                            <span key={f.label} className="truncate" title={f.value}>
                              <span className="text-text-faint">{f.label}:</span>
                              <span className="ml-1 text-text">{f.value}</span>
                            </span>
                          ))}
                        </div>
                      )}

                      {/* JD 摘要 */}
                      {job.jd_summary && (
                        <p className="mt-1.5 line-clamp-2 text-[11px] leading-relaxed text-text-muted">
                          {job.jd_summary}
                        </p>
                      )}

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

                    {/* 按钮组 */}
                    <div className="flex shrink-0 flex-col gap-1.5">
                      <button
                        type="button"
                        onClick={async () => {
                          const existing = appByJob(job.job_id);
                          if (existing && existing.status === "favorite") {
                            // 已收藏 → 取消收藏
                            await onRemoveApplication(existing.id);
                          } else if (!existing || existing.status === "rejected") {
                            // 未收藏 → 创建收藏
                            await onCreateFavorite(job);
                          }
                        }}
                        className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                          isFavorite
                            ? "bg-amber-500 text-white hover:bg-amber-600"
                            : "bg-amber-200 text-amber-900 hover:bg-amber-300"
                        }`}
                        title={isFavorite ? "点击取消收藏" : "收藏岗位"}
                      >
                        {isFavorite ? "⭐ 已收藏" : "⭐ 收藏"}
                      </button>
                      {job.apply_url && (
                        <button
                          type="button"
                          onClick={async () => {
                            const existing = appByJob(job.job_id);
                            if (existing && existing.status === "applied") {
                              // 已投递 → 取消投递
                              await onRemoveApplication(existing.id);
                            } else if (!existing || existing.status === "rejected") {
                              // 未投递 → 创建投递 + 打开链接
                              await onCreateApplied(job);
                              onOpenApply(job.apply_url);
                            } else if (existing.status === "favorite") {
                              // 已收藏 → 升级为投递
                              await onRemoveApplication(existing.id);
                              await onCreateApplied(job);
                              onOpenApply(job.apply_url);
                            }
                          }}
                          className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                            isApplied
                              ? "bg-success text-white hover:bg-success-dark"
                              : "bg-success-soft text-success hover:bg-success/15"
                          }`}
                          title={isApplied ? "点击取消投递" : "投递岗位"}
                        >
                          {isApplied ? "📮 已投递" : "📮 投递"}
                        </button>
                      )}
                      {job.announcement_url && (
                        <button
                          type="button"
                          onClick={() => onOpenApply(job.announcement_url)}
                          className="rounded-lg bg-info px-3 py-1.5 text-xs font-medium text-white hover:bg-info-dark"
                        >
                          📢 公告
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        );
      })}
      </div>
    </div>
  );
}
