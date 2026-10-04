// 岗位列表页面：字段对齐飞书「27届校招汇总表」。
// 功能：统计卡片、列筛选（多选）、列显隐（默认全显示）、首列固定、长文本截断、彩色标签、链接。
import { useEffect, useRef, useState, type ReactNode } from "react";
import { getStatsOverview, type StatsOverview } from "../api/companies";
import { useJobsStore } from "../stores/jobsStore";
import { useAppStore, type AppStatus } from "../stores/appStore";
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

  // 加载统计（含筛选选项）
  useEffect(() => {
    getStatsOverview().then(setStats).catch(() => {});
  }, []);

  // 首次加载
  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

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
      {/* 统计卡片 */}
      {stats && <JobsStatsCards stats={stats} />}

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
                <JobRow key={j.job_id} job={j} visibleKeys={visibleKeys} />
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

function JobRow({ job, visibleKeys }: { job: import("../api/jobs").Job; visibleKeys: string[] }) {
  const addApplication = useAppStore((s) => s.addApplication);
  const [busy, setBusy] = useState(false);

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

  const cells: Record<string, ReactNode> = {
    actions: (
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => void quickAdd("favorite")}
          disabled={busy}
          className="rounded bg-white/60 px-1.5 py-0.5 text-xs text-text-muted transition hover:bg-primary-soft hover:text-primary-dark disabled:opacity-50"
          title="加入收藏"
        >
          ⭐
        </button>
        <button
          type="button"
          onClick={() => void quickAdd("applied")}
          disabled={busy}
          className="rounded bg-primary-soft px-1.5 py-0.5 text-xs font-medium text-primary-dark transition hover:bg-primary hover:text-ink disabled:opacity-50"
          title="标记已投递"
        >
          📮
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
