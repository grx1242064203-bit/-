// 岗位列表页面：表格形式 + 左侧岗位分类导航，字段对齐飞书岗位表。
import { useEffect, useState } from "react";
import { useJobsStore } from "../stores/jobsStore";
import { getCategories, type JobCategory } from "../api/categories";
import type { Job } from "../api/jobs";

export default function Jobs() {
  const { jobs, isLoading, error, hasMore, loadJobs, loadMore, loadStats } =
    useJobsStore();
  const [categories, setCategories] = useState<JobCategory[]>([]);
  const [activeCategory, setActiveCategory] = useState("");
  const [keyword, setKeyword] = useState("");
  const [city, setCity] = useState("");

  useEffect(() => {
    void loadJobs();
    void loadStats();
    void getCategories()
      .then((res) => setCategories(res.categories))
      .catch(() => {});
  }, [loadJobs, loadStats]);

  const handleCategoryClick = (cat: string) => {
    setActiveCategory(cat);
    void loadJobs({ category: cat || undefined });
  };

  const handleSearch = () => {
    void loadJobs({
      category: activeCategory || undefined,
      keyword: keyword || undefined,
      city: city === "全国各地" ? undefined : city,
    });
  };

  // 热门城市列表
  const CITIES = ["全国各地", "北京", "上海", "深圳", "广州", "杭州", "成都", "南京", "武汉", "西安"];

  return (
    <div className="flex h-full gap-4 animate-fade-in">
      {/* 左侧分类导航 */}
      <aside className="w-48 flex-shrink-0 overflow-y-auto rounded-lg border border-gray-200 bg-surface p-3 shadow-sm">
        <div className="mb-2 px-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
          岗位分类
        </div>
        <div className="space-y-0.5">
          <CategoryButton
            label="全部岗位"
            count={categories.reduce((s, c) => s + c.count, 0)}
            active={activeCategory === ""}
            onClick={() => handleCategoryClick("")}
          />
          {categories.map((c) => (
            <CategoryButton
              key={c.name}
              label={c.name}
              count={c.count}
              active={activeCategory === c.name}
              onClick={() => handleCategoryClick(c.name)}
            />
          ))}
        </div>
      </aside>

      {/* 右侧表格 */}
      <div className="flex-1 overflow-hidden space-y-3">
        {/* 筛选栏 */}
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-gray-200 bg-surface p-3 shadow-sm">
          <input
            type="text"
            placeholder="搜索岗位/公司…"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            className="w-44 rounded-md border border-gray-200 px-3 py-1.5 text-sm focus:border-primary focus:outline-none"
          />
          <select
            value={city}
            onChange={(e) => setCity(e.target.value)}
            className="rounded-md border border-gray-200 px-3 py-1.5 text-sm focus:border-primary focus:outline-none"
          >
            {CITIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={handleSearch}
            className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-white transition hover:bg-primary-600"
          >
            搜索
          </button>
          <span className="ml-auto text-sm text-gray-500">
            {jobs.length > 0 && `已加载 ${jobs.length} 条`}
          </span>
        </div>

        {/* 错误 */}
        {error && (
          <div className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600">
            {error}
          </div>
        )}

        {/* 岗位表格 */}
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-surface shadow-sm">
          <div className="overflow-x-auto overflow-y-auto" style={{ maxHeight: "calc(100vh - 280px)" }}>
            <table className="min-w-full">
              <thead className="sticky top-0 z-10 border-b border-gray-200 bg-gray-50">
                <tr>
                  <Th>岗位标题</Th>
                  <Th>公司</Th>
                  <Th>分类</Th>
                  <Th>城市</Th>
                  <Th>学历</Th>
                  <Th>管培</Th>
                  <Th>更新时间</Th>
                  <Th className="text-right">操作</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {isLoading && jobs.length === 0
                  ? Array.from({ length: 10 }).map((_, i) => (
                      <tr key={i}>
                        {Array.from({ length: 8 }).map((_, j) => (
                          <td key={j} className="px-4 py-3">
                            <div className="h-4 w-full animate-pulse rounded bg-gray-100" />
                          </td>
                        ))}
                      </tr>
                    ))
                  : jobs.map((job) => (
                      <JobRow key={job.job_id} job={job} />
                    ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 加载更多 */}
        {hasMore && (
          <div className="flex justify-center pt-1">
            <button
              type="button"
              onClick={() => void loadMore()}
              className="rounded-lg border border-gray-200 bg-surface px-6 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50"
            >
              加载更多
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function CategoryButton({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-sm transition-colors ${
        active
          ? "bg-primary-50 font-medium text-primary"
          : "text-gray-600 hover:bg-gray-50"
      }`}
    >
      <span className="truncate">{label}</span>
      <span
        className={`ml-2 shrink-0 rounded-full px-1.5 text-xs ${
          active ? "bg-primary text-white" : "bg-gray-100 text-gray-400"
        }`}
      >
        {count}
      </span>
    </button>
  );
}

function JobRow({ job }: { job: Job }) {
  return (
    <tr className="transition-colors hover:bg-gray-50">
      <td className="px-4 py-3">
        <div className="font-medium text-gray-900">{job.title}</div>
        {job.requirements && (
          <div className="mt-0.5 line-clamp-1 text-xs text-gray-400">
            {job.requirements}
          </div>
        )}
      </td>
      <td className="px-4 py-3 text-sm text-gray-600">{job.company}</td>
      <td className="px-4 py-3">
        {job.category && (
          <span className="rounded-full bg-primary-50 px-2 py-0.5 text-xs text-primary">
            {job.category}
          </span>
        )}
      </td>
      <td className="px-4 py-3 text-sm text-gray-600">{job.city || "-"}</td>
      <td className="px-4 py-3 text-sm text-gray-600">
        {job.graduation_match ? "应届" : "不限"}
      </td>
      <td className="px-4 py-3 text-sm">
        {job.is_mt ? (
          <span className="rounded-full bg-accent-100 px-2 py-0.5 text-xs text-accent-600">
            管培
          </span>
        ) : (
          <span className="text-gray-300">-</span>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-gray-400">
        {job.updated_at ? job.updated_at.slice(0, 10) : "-"}
      </td>
      <td className="px-4 py-3 text-right">
        <div className="flex justify-end gap-1.5">
          <button
            type="button"
            className="rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-500 transition hover:bg-gray-50"
            title="收藏"
          >
            ☆
          </button>
          {job.apply_url && (
            <a
              href={job.apply_url}
              target="_blank"
              rel="noreferrer"
              className="rounded-md bg-accent px-2.5 py-1 text-xs font-medium text-white transition hover:bg-accent-600"
            >
              投递
            </a>
          )}
        </div>
      </td>
    </tr>
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
    <th className={`whitespace-nowrap px-4 py-3 ${className}`}>{children}</th>
  );
}
