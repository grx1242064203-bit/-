// 公司总览页面：表格形式，字段对齐飞书公司表。
import { useEffect, useState } from "react";
import {
  getCompanies,
  getCompanyStats,
  type Company,
  type CompanyStats,
} from "../api/companies";
import { createApplication, type AppStatus } from "../api/applications";

const PAGE_SIZE = 100;

export default function Companies() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [stats, setStats] = useState<CompanyStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [industry, setIndustry] = useState("");
  const [companyType, setCompanyType] = useState("");
  const [keyword, setKeyword] = useState("");

  const loadData = async (reset = true) => {
    setLoading(true);
    setError(null);
    try {
      const res = await getCompanies({
        limit: PAGE_SIZE,
        offset: reset ? 0 : offset,
        industry,
        company_type: companyType,
        keyword,
      });
      setCompanies(reset ? res.companies : [...companies, ...res.companies]);
      setTotal(res.total);
      if (reset) setOffset(res.companies.length);
      else setOffset((o) => o + res.companies.length);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData(true);
    void getCompanyStats().then(setStats).catch(() => {});
  }, []);

  const handleFilter = () => {
    setOffset(0);
    void loadData(true);
  };

  const handleLoadMore = () => {
    void loadData(false);
  };

  return (
    <div className="space-y-4 animate-fade-in">
      {/* 统计卡片 */}
      {stats && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="公司总数" value={stats.total} accent />
          <StatCard
            label="覆盖行业"
            value={stats.industries.length}
          />
          <StatCard
            label="国央企"
            value={stats.types.find((t) => t.name === "国央企")?.count ?? 0}
          />
          <StatCard
            label="外企"
            value={stats.types.find((t) => t.name === "外企")?.count ?? 0}
          />
        </div>
      )}

      {/* 筛选栏 */}
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-200 bg-surface p-4 shadow-sm">
        <input
          type="text"
          placeholder="搜索公司名称…"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleFilter()}
          className="w-48 rounded-md border border-gray-200 px-3 py-1.5 text-sm focus:border-primary focus:outline-none"
        />
        <select
          value={industry}
          onChange={(e) => setIndustry(e.target.value)}
          className="rounded-md border border-gray-200 px-3 py-1.5 text-sm focus:border-primary focus:outline-none"
        >
          <option value="">全部行业</option>
          {stats?.industries.map((i) => (
            <option key={i.name} value={i.name}>
              {i.name} ({i.count})
            </option>
          ))}
        </select>
        <select
          value={companyType}
          onChange={(e) => setCompanyType(e.target.value)}
          className="rounded-md border border-gray-200 px-3 py-1.5 text-sm focus:border-primary focus:outline-none"
        >
          <option value="">全部类型</option>
          {stats?.types.map((t) => (
            <option key={t.name} value={t.name}>
              {t.name} ({t.count})
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={handleFilter}
          className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-white transition hover:bg-primary-600"
        >
          筛选
        </button>
        <span className="ml-auto text-sm text-gray-500">
          共 {total} 家公司
        </span>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600">
          {error}
        </div>
      )}

      {/* 公司表格 */}
      <div className="overflow-hidden rounded-lg border border-gray-200 bg-surface shadow-sm">
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead className="border-b border-gray-200 bg-gray-50">
              <tr>
                <Th>公司名称</Th>
                <Th>行业</Th>
                <Th>类型</Th>
                <Th>招聘类型</Th>
                <Th>地点</Th>
                <Th>学历</Th>
                <Th>岗位数</Th>
                <Th>截止日期</Th>
                <Th>网申更新</Th>
                <Th className="text-right">操作</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading && companies.length === 0
                ? Array.from({ length: 8 }).map((_, i) => (
                    <tr key={i}>
                      {Array.from({ length: 10 }).map((_, j) => (
                        <td key={j} className="px-4 py-3">
                          <div className="h-4 w-full animate-pulse rounded bg-gray-100" />
                        </td>
                      ))}
                    </tr>
                  ))
                : companies.map((c) => (
                    <CompanyRow key={c.company_id} company={c} />
                  ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 加载更多 */}
      {companies.length < total && (
        <div className="flex justify-center pt-2">
          <button
            type="button"
            onClick={handleLoadMore}
            disabled={loading}
            className="rounded-lg border border-gray-200 bg-surface px-6 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50"
          >
            {loading ? "加载中…" : `加载更多（${companies.length}/${total}）`}
          </button>
        </div>
      )}
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
  accent?: boolean;
}) {
  return (
    <div
      className={`rounded-lg border p-4 shadow-sm ${
        accent
          ? "border-primary-100 bg-primary-50"
          : "border-gray-200 bg-surface"
      }`}
    >
      <div className="text-sm text-gray-500">{label}</div>
      <div
        className={`mt-1 text-2xl font-bold ${
          accent ? "text-primary" : "text-gray-900"
        }`}
      >
        {value.toLocaleString()}
      </div>
    </div>
  );
}

function Th({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      className={`whitespace-nowrap px-4 py-3 ${className}`}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <td className={`whitespace-nowrap px-4 py-3 text-sm ${className}`}>
      {children}
    </td>
  );
}

function CompanyRow({ company }: { company: Company }) {
  const [favStatus, setFavStatus] = useState<"idle" | "loading" | "done">("idle");

  const handleFavorite = async () => {
    if (favStatus === "loading") return;
    setFavStatus("loading");
    try {
      await createApplication({
        job_id: `company:${company.company_id}`,
        job_title: company.company_name,
        company_name: company.company_name,
        status: "favorite" as AppStatus,
        apply_url: company.apply_url,
      });
      setFavStatus("done");
    } catch {
      setFavStatus("idle");
    }
  };

  return (
    <tr className="transition-colors hover:bg-gray-50">
      <Td className="font-medium text-gray-900">{company.company_name}</Td>
      <Td>
        {company.industry && (
          <span className="rounded-full bg-primary-50 px-2 py-0.5 text-xs text-primary">
            {company.industry}
          </span>
        )}
      </Td>
      <Td className="text-gray-600">{company.company_type}</Td>
      <Td className="text-gray-600">{company.recruit_type}</Td>
      <Td className="text-gray-600">{company.location}</Td>
      <Td className="text-gray-600">{company.education_req}</Td>
      <Td className="text-gray-600">{company.positions_count}</Td>
      <Td className="text-gray-600">
        {company.deadline ? company.deadline.slice(0, 10) : "-"}
      </Td>
      <Td className="text-xs text-gray-400">
        {company.last_updated.slice(0, 10)}
      </Td>
      <Td className="text-right">
        <div className="flex justify-end gap-1.5">
          <button
            type="button"
            onClick={handleFavorite}
            disabled={favStatus === "loading"}
            className={`rounded-md border px-2 py-1 text-xs transition ${
              favStatus === "done"
                ? "border-accent bg-accent-100 text-accent-600"
                : "border-gray-200 text-gray-500 hover:bg-gray-50"
            }`}
            title="收藏"
          >
            {favStatus === "done" ? "★" : "☆"}
          </button>
          {company.apply_url && (
            <a
              href={company.apply_url}
              target="_blank"
              rel="noreferrer"
              className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-white transition hover:bg-accent-600"
            >
              网申
            </a>
          )}
          {company.announcement_url && (
            <a
              href={company.announcement_url}
              target="_blank"
              rel="noreferrer"
              className="rounded-md border border-gray-200 px-3 py-1 text-xs font-medium text-gray-600 transition hover:bg-gray-50"
            >
              公告
            </a>
          )}
        </div>
      </Td>
    </tr>
  );
}
