// 公司总览页面：表格形式，字段对齐飞书公司表。
// 功能：统计卡片、列筛选（多选）、列显隐、首列固定、长文本截断、彩色标签、链接安全打开。
import { useEffect, useRef, useState, type ReactNode } from "react";
import { extractErrorMessage } from "../api/client";
import {
  getCompanies,
  getStatsOverview,
  type Company,
  type StatsOverview,
} from "../api/companies";
import { useAppStore, type AppStatus, type Application } from "../stores/appStore";
import { colorMap, pillClass } from "../utils/colorMap";
import { openExternalUrl } from "../utils/link";
import Truncate from "../components/Truncate";
import ColumnFilter from "../components/ColumnFilter";
import ColumnSettings, { type ColumnDef } from "../components/ColumnSettings";

const PAGE_SIZE = 100;

/** 列定义（顺序即默认显示顺序）
 * 操作 + 公司名 + 链接 三列固定在左侧,与岗位表对齐,滚动时常驻可见 */
const COLUMNS: ColumnDef[] = [
  { key: "actions", label: "操作" },
  { key: "company_name", label: "公司名称" },
  { key: "links", label: "链接" },
  { key: "industry", label: "行业" },
  { key: "company_type", label: "公司类型" },
  { key: "recruit_type", label: "招聘类型" },
  { key: "position_titles", label: "招聘岗位" },
  { key: "location", label: "工作地点" },
  { key: "education_req", label: "学历" },
  { key: "deadline", label: "截止时间" },
  { key: "last_updated", label: "发布时间" },
];

/** 分类列（有后端筛选选项，多选 IN）；其余列为文本搜索列（LIKE） */
const CATEGORY_COLUMNS = new Set(["industry", "company_type", "recruit_type", "education_req"]);

export default function Companies() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [keyword, setKeyword] = useState("");
  const [debouncedKeyword, setDebouncedKeyword] = useState("");
  const [columnFilters, setColumnFilters] = useState<Record<string, string[]>>({});
  const [stats, setStats] = useState<StatsOverview | null>(null);
  const [visibleKeys, setVisibleKeys] = useState<string[]>(COLUMNS.map((c) => c.key));
  const scrollRef = useRef<HTMLDivElement>(null);

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

  // keyword 防抖:用户停止输入 300ms 后才同步到 debouncedKeyword,触发请求
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedKeyword(keyword), 300);
    return () => clearTimeout(timer);
  }, [keyword]);

  // 构建请求参数
  const buildParams = (offset: number) => {
    const params: Record<string, string | number> = { limit: PAGE_SIZE, offset };
    if (debouncedKeyword.trim()) params.keyword = debouncedKeyword.trim();
    for (const [k, vals] of Object.entries(columnFilters)) {
      if (vals.length) params[k] = vals.join(",");
    }
    return params;
  };

  // 加载公司列表（重置）
  useEffect(() => {
    setLoading(true);
    setError(null);
    getCompanies(buildParams(0))
      .then((res) => {
        setCompanies(res.companies);
        setTotal(res.total);
        setHasMore(res.companies.length >= PAGE_SIZE);
      })
      .catch((e) => setError(extractErrorMessage(e)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedKeyword, columnFilters]);

  // 加载更多
  const loadMore = async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const res = await getCompanies(buildParams(companies.length));
      setCompanies((prev) => [...prev, ...res.companies]);
      setHasMore(res.companies.length >= PAGE_SIZE);
    } catch (e) {
      setError(extractErrorMessage(e));
    } finally {
      setLoadingMore(false);
    }
  };

  // 滚动到底加载更多
  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 200) {
      void loadMore();
    }
  };

  const hasFilter = keyword.trim() !== "" || Object.values(columnFilters).some((v) => v.length);

  const filterOptions = stats?.companies.filter_options ?? {};

  // 按公司查匹配的投递记录
  const appByCompany = (companyId: string): Application | undefined =>
    applications.find((a) => a.link_type === "company" && a.link_id === companyId);

  return (
    <div className="flex h-full flex-col gap-4">
      {/* 统计卡片 */}
      {stats && <CompanyStatsCards stats={stats} />}

      {/* 工具栏：搜索 + 列设置 */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <input
            type="text"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索公司名称..."
            className="w-full rounded-lg border border-line bg-white/60 px-3 py-2 text-sm outline-none focus:border-primary"
          />
        </div>
        {hasFilter && (
          <button
            type="button"
            onClick={() => {
              setKeyword("");
              setColumnFilters({});
            }}
            className="rounded-lg border border-line bg-white/60 px-3 py-2 text-sm text-text-muted hover:bg-white"
          >
            清除筛选
          </button>
        )}
        <ColumnSettings
          columns={COLUMNS}
          tableKey="companies"
          visibleKeys={visibleKeys}
          onChange={setVisibleKeys}
        />
      </div>

      {/* 已选筛选条件 chip */}
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
                onClose={() => {
                  setColumnFilters((prev) => ({
                    ...prev,
                    [col]: prev[col].filter((x) => x !== v),
                  }));
                }}
              />
            ))
          )}
        </div>
      )}

      {/* 错误提示 */}
      {error && (
        <div className="rounded-lg bg-danger-soft px-4 py-2 text-sm text-danger">{error}</div>
      )}

      {/* 表格 */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-auto rounded-xl border border-line bg-white/40 backdrop-blur"
      >
        <table className="w-full min-w-[900px] border-collapse text-sm">
          <thead className="sticky top-0 z-10">
            <tr className="bg-white/85 backdrop-blur-md">
              {COLUMNS.filter((c) => visibleKeys.includes(c.key)).map((col) => {
                // 三列固定:actions(left-0) + company_name(left-[72px]) + links(left-[272px])
                // Tailwind JIT 只识别字面量类名,所以 left-[272px] 必须以字面量出现
                const isActionsSticky = col.key === "actions";
                const isNameSticky = col.key === "company_name";
                const isLinksSticky = col.key === "links";
                const stickyClass = isActionsSticky
                  ? "sticky left-0 z-20 bg-white/85 backdrop-blur w-[72px] min-w-[72px] shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]"
                  : isNameSticky
                  ? "sticky left-[72px] z-20 bg-white/85 backdrop-blur min-w-[200px] shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]"
                  : isLinksSticky
                  ? "sticky left-[272px] z-20 bg-white/85 backdrop-blur shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]"
                  : "";
                return (
                  <th
                    key={col.key}
                    className={`border-b border-line px-3 py-2.5 text-left font-medium text-ink ${stickyClass}`}
                    style={{ minWidth: colWidth(col.key) }}
                  >
                    <div className="flex items-center">
                      <span>{col.label}</span>
                      <ColumnFilter
                        columnName={col.label}
                        value={columnFilters[col.key] ?? []}
                        options={
                          CATEGORY_COLUMNS.has(col.key)
                            ? (filterOptions[col.key] ?? []).map((v) => ({
                                label: v,
                                value: v,
                              }))
                            : undefined
                        }
                        onChange={(vals) =>
                          setColumnFilters((prev) => ({ ...prev, [col.key]: vals }))
                        }
                      />
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={visibleKeys.length} className="px-3 py-8 text-center text-text-faint">
                  加载中...
                </td>
              </tr>
            ) : companies.length === 0 ? (
              <tr>
                <td colSpan={visibleKeys.length} className="px-3 py-8 text-center text-text-faint">
                  暂无数据
                </td>
              </tr>
            ) : (
              companies.map((c) => (
                <CompanyRow
                  key={c.company_id}
                  company={c}
                  visibleKeys={visibleKeys}
                  application={appByCompany(c.company_id)}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 分页信息 */}
      <div className="flex items-center justify-between text-xs text-text-muted">
        <span>
          共 {total} 家公司，已加载 {companies.length} 条
        </span>
        {loadingMore ? (
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

function colWidth(key: string): string {
  switch (key) {
    case "actions":
      return "70px";
    case "company_name":
      return "180px";
    case "industry":
    case "company_type":
    case "recruit_type":
    case "education_req":
      return "110px";
    case "position_titles":
      return "280px";
    case "location":
      return "120px";
    case "deadline":
    case "last_updated":
      return "110px";
    case "links":
      return "120px";
    default:
      return "120px";
  }
}

function CompanyRow({
  company,
  visibleKeys,
  application,
}: {
  company: Company;
  visibleKeys: string[];
  application?: Application;
}) {
  const addApplication = useAppStore((s) => s.addApplication);
  const removeApplication = useAppStore((s) => s.removeApplication);
  const [modal, setModal] = useState<{ status: AppStatus } | null>(null);

  const status = application?.status;
  const isFavorited = status === "favorite";
  const isApplied = status === "applied";
  const inPipeline = !!application && !isFavorited && !isApplied;

  // 点击收藏：已收藏则取消，否则弹窗填岗位名后收藏
  const handleFavorite = () => {
    if (isFavorited && application) {
      void removeApplication(application.id);
    } else {
      setModal({ status: "favorite" });
    }
  };

  // 点击投递：已投递则取消，否则弹窗填岗位名后投递
  const handleApply = () => {
    if (isApplied && application) {
      void removeApplication(application.id);
    } else {
      setModal({ status: "applied" });
    }
  };

  const cells: Record<string, ReactNode> = {
    actions: (
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={handleFavorite}
          className={`relative rounded px-1.5 py-0.5 text-xs transition ${
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
          className={`relative rounded px-1.5 py-0.5 text-xs transition ${
            isApplied
              ? "bg-success text-white"
              : inPipeline
                ? "bg-success-soft text-success"
                : "bg-primary-soft px-1.5 py-0.5 font-medium text-primary-dark hover:bg-primary hover:text-ink"
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
    company_name: (
      <Truncate text={company.company_name} className="font-medium" />
    ),
    industry: company.industry ? (
      <span className={pillClass(colorMap.industry(company.industry))}>{company.industry}</span>
    ) : (
      <span className="text-text-faint">—</span>
    ),
    company_type: company.company_type ? (
      <span className={pillClass(colorMap.companyType(company.company_type))}>
        {company.company_type}
      </span>
    ) : (
      <span className="text-text-faint">—</span>
    ),
    recruit_type: company.recruit_type ? (
      <span className={pillClass(colorMap.recruitType(company.recruit_type))}>
        {company.recruit_type}
      </span>
    ) : (
      <span className="text-text-faint">—</span>
    ),
    position_titles: (
      <Truncate
        text={company.position_titles ?? ""}
        maxLines={2}
        title={company.position_titles ?? ""}
        className="text-ink-soft"
      />
    ),
    location: (
      <Truncate text={company.location} title={company.location} className="text-ink-soft" />
    ),
    education_req: company.education_req ? (
      <span className={pillClass(colorMap.education(company.education_req))}>
        {company.education_req}
      </span>
    ) : (
      <span className="text-text-faint">—</span>
    ),
    deadline: <span className="text-ink-soft">{company.deadline ?? "—"}</span>,
    last_updated: <span className="text-ink-soft">{company.last_updated || "—"}</span>,
    links: (
      <div className="flex gap-1">
        {company.apply_url && (
          <LinkButton url={company.apply_url} label="投递" />
        )}
        {company.announcement_url && (
          <LinkButton url={company.announcement_url} label="公告" />
        )}
        {!company.apply_url && !company.announcement_url && (
          <span className="text-text-faint">—</span>
        )}
      </div>
    ),
  };

  return (
    <>
      <tr className="border-b border-line/60 hover:bg-white/40">
        {COLUMNS.filter((c) => visibleKeys.includes(c.key)).map((col) => {
          // 与表头一致的三列固定:actions + company_name + links
          const isActionsSticky = col.key === "actions";
          const isNameSticky = col.key === "company_name";
          const isLinksSticky = col.key === "links";
          const stickyClass = isActionsSticky
            ? "sticky left-0 z-[2] bg-white/85 backdrop-blur w-[72px] min-w-[72px]"
            : isNameSticky
            ? "sticky left-[72px] z-[2] bg-white/85 backdrop-blur min-w-[200px]"
            : isLinksSticky
            ? "sticky left-[272px] z-[2] bg-white/85 backdrop-blur"
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
      {modal && (
        <CompanyQuickModal
          company={company}
          status={modal.status}
          onClose={() => setModal(null)}
          onSubmit={async (jobTitle) => {
            await addApplication({
              source: "db_company",
              link_type: "company",
              link_id: company.company_id,
              company_name: company.company_name,
              job_title: jobTitle,
              status: modal.status,
              apply_url: company.apply_url || undefined,
              announcement_url: company.announcement_url || undefined,
            });
            setModal(null);
          }}
        />
      )}
    </>
  );
}

/** 公司维度快速收藏/投递小表单：仅填岗位名（可选）。 */
function CompanyQuickModal({
  company,
  status,
  onClose,
  onSubmit,
}: {
  company: Company;
  status: AppStatus;
  onClose: () => void;
  onSubmit: (jobTitle: string) => void | Promise<void>;
}) {
  const [jobTitle, setJobTitle] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const statusLabel = status === "favorite" ? "收藏" : "已投递";

  async function handleSubmit() {
    setSubmitting(true);
    try {
      await onSubmit(jobTitle.trim());
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="glass w-80 rounded-2xl p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-base font-semibold text-text">
          {status === "favorite" ? "⭐ 加入收藏" : "📮 标记已投递"}
        </h3>
        <p className="mt-1 text-xs text-text-muted">{company.company_name}</p>

        <div className="mt-4 space-y-3">
          <div>
            <label className="text-xs font-medium text-text-muted">
              岗位名称（可选，不填仅按公司匹配）
            </label>
            <input
              value={jobTitle}
              onChange={(e) => setJobTitle(e.target.value)}
              placeholder="如：后端开发工程师"
              className="mt-1 w-full rounded-lg border border-white/60 bg-white/40 px-3 py-2 text-sm focus:border-primary-dark focus:outline-none focus:ring-2 focus:ring-primary/30"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleSubmit();
              }}
            />
          </div>
          <p className="text-[11px] text-text-faint">
            已存在同公司{jobTitle.trim() ? "+岗位" : ""}记录时仅更新状态为「{statusLabel}」，否则新建。
          </p>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="glass-soft rounded-pill px-4 py-1.5 text-sm text-text-muted hover:text-text"
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={submitting}
            className="rounded-pill bg-primary px-4 py-1.5 text-sm font-semibold text-ink hover:bg-primary-dark disabled:opacity-50"
          >
            {submitting ? "处理中…" : statusLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

function LinkButton({ url, label }: { url: string; label: string }) {
  // 与岗位表(Jobs.tsx) LinkButton 配色一致:投递=success 绿,公告=info 蓝
  // 暖橙背景下用强对比色,避免按钮和背景太相近
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

function CompanyStatsCards({ stats }: { stats: StatsOverview }) {
  const c = stats.companies;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-5">
      <StatCard label="公司总数" value={c.total} accent="primary" />
      <StatCard label="今日新增" value={c.today_new} accent="success" />
      <StatCard label="近7日新增" value={c.week_new} accent="info" />
      <StatCard label="7日内截止" value={c.closing_soon} accent="danger" />
      <IndustryBar items={c.top_industries} />
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
  accent: "primary" | "success" | "info" | "danger";
}) {
  const color = {
    primary: "text-primary-dark",
    success: "text-success",
    info: "text-blue-600",
    danger: "text-danger",
  }[accent];
  return (
    <div className="rounded-xl border border-line bg-white/50 px-4 py-3 backdrop-blur">
      <div className="text-xs text-text-muted">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${color}`}>{value.toLocaleString()}</div>
    </div>
  );
}

function IndustryBar({ items }: { items: { name: string; count: number }[] }) {
  const max = items[0]?.count ?? 1;
  return (
    <div className="rounded-xl border border-line bg-white/50 px-4 py-3 backdrop-blur sm:col-span-2 lg:col-span-1">
      <div className="mb-2 text-xs text-text-muted">行业 Top5</div>
      <div className="space-y-1">
        {items.map((it) => (
          <div key={it.name} className="flex items-center gap-2 text-xs">
            <span className="w-16 shrink-0 truncate text-ink-soft">{it.name}</span>
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
