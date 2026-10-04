// 公司总览页面：表格形式，字段对齐飞书公司表。
// 功能：统计卡片、列筛选（多选）、列显隐、首列固定、长文本截断、彩色标签、链接安全打开。
import { useEffect, useState, type ReactNode } from "react";
import {
  getCompanies,
  getStatsOverview,
  type Company,
  type StatsOverview,
} from "../api/companies";
import { colorMap, pillClass } from "../utils/colorMap";
import { openExternalUrl } from "../utils/link";
import Truncate from "../components/Truncate";
import ColumnFilter from "../components/ColumnFilter";
import ColumnSettings, { type ColumnDef } from "../components/ColumnSettings";

const PAGE_SIZE = 100;

/** 列定义（顺序即默认显示顺序） */
const COLUMNS: ColumnDef[] = [
  { key: "company_name", label: "公司名称" },
  { key: "industry", label: "行业" },
  { key: "company_type", label: "公司类型" },
  { key: "recruit_type", label: "招聘类型" },
  { key: "position_titles", label: "招聘岗位" },
  { key: "location", label: "工作地点" },
  { key: "education_req", label: "学历" },
  { key: "deadline", label: "截止时间" },
  { key: "last_updated", label: "发布时间" },
  { key: "links", label: "链接" },
];

/** 需要列筛选的分类列 */
const FILTER_COLUMNS = new Set(["industry", "company_type", "recruit_type", "education_req"]);

export default function Companies() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [keyword, setKeyword] = useState("");
  const [columnFilters, setColumnFilters] = useState<Record<string, string[]>>({});
  const [stats, setStats] = useState<StatsOverview | null>(null);
  const [visibleKeys, setVisibleKeys] = useState<string[]>(COLUMNS.map((c) => c.key));

  // 加载统计（含筛选选项）
  useEffect(() => {
    getStatsOverview().then(setStats).catch(() => {});
  }, []);

  // 加载公司列表
  useEffect(() => {
    setLoading(true);
    setError(null);
    const params: Record<string, string> = {};
    if (keyword.trim()) params.keyword = keyword.trim();
    for (const [k, vals] of Object.entries(columnFilters)) {
      if (vals.length) params[k] = vals.join(",");
    }
    getCompanies({ ...params, limit: PAGE_SIZE, offset: 0 })
      .then((res) => {
        setCompanies(res.companies);
        setTotal(res.total);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [keyword, columnFilters]);

  const hasFilter = keyword.trim() !== "" || Object.values(columnFilters).some((v) => v.length);

  const filterOptions = stats?.companies.filter_options ?? {};

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
      <div className="flex-1 overflow-auto rounded-xl border border-line bg-white/40 backdrop-blur">
        <table className="w-full min-w-[900px] border-collapse text-sm">
          <thead className="sticky top-0 z-10">
            <tr className="bg-white/85 backdrop-blur-md">
              {COLUMNS.filter((c) => visibleKeys.includes(c.key)).map((col) => {
                const isFirst = col.key === "company_name";
                return (
                  <th
                    key={col.key}
                    className={`border-b border-line px-3 py-2.5 text-left font-medium text-ink ${
                      isFirst ? "sticky left-0 z-20 bg-white/85 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]" : ""
                    }`}
                    style={{ minWidth: colWidth(col.key) }}
                  >
                    <div className="flex items-center">
                      <span>{col.label}</span>
                      {FILTER_COLUMNS.has(col.key) && (
                        <ColumnFilter
                          columnName={col.label}
                          value={columnFilters[col.key] ?? []}
                          options={(filterOptions[col.key] ?? []).map((v) => ({
                            label: v,
                            value: v,
                          }))}
                          onChange={(vals) =>
                            setColumnFilters((prev) => ({ ...prev, [col.key]: vals }))
                          }
                        />
                      )}
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
                <CompanyRow key={c.company_id} company={c} visibleKeys={visibleKeys} />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 分页信息 */}
      <div className="text-xs text-text-muted">
        共 {total} 家公司，当前显示 {companies.length} 条
        {total > PAGE_SIZE && "（更多请使用搜索或筛选）"}
      </div>
    </div>
  );
}

function colWidth(key: string): string {
  switch (key) {
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
      return "160px";
    case "deadline":
    case "last_updated":
      return "110px";
    case "links":
      return "120px";
    default:
      return "120px";
  }
}

function CompanyRow({ company, visibleKeys }: { company: Company; visibleKeys: string[] }) {
  const cells: Record<string, ReactNode> = {
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
          <LinkButton url={company.apply_url} label="网申" />
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
    <tr className="border-b border-line/60 hover:bg-white/40">
      {COLUMNS.filter((c) => visibleKeys.includes(c.key)).map((col) => {
        const isFirst = col.key === "company_name";
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
      onClick={() => openExternalUrl(url)}
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
