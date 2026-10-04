// 岗位列表页面：表格形式 + 左侧岗位分类导航，字段对齐飞书岗位表。Crextio 暖主题。
import { useEffect, useState } from "react";
import { useJobsStore } from "../stores/jobsStore";
import { getCategories, type JobCategory } from "../api/categories";
import { createApplication, type AppStatus } from "../api/applications";
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
    <div className="flex h-full gap-5 animate-fade-in">
      {/* 左侧分类导航 */}
      <aside className="w-52 flex-shrink-0 overflow-y-auto rounded-xl border border-border bg-surface p-4 shadow-sm">
        <div className="mb-3 px-2 text-xs font-semibold uppercase tracking-wide text-text-faint">
          岗位分类
        </div>
        <div className="space-y-1">
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
      <div className="flex flex-1 flex-col overflow-hidden space-y-4">
        {/* 筛选栏 */}
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-surface p-3.5 shadow-sm">
          <input
            type="text"
            placeholder="搜索岗位/公司…"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            className="w-44 rounded-pill border border-border bg-surface-soft px-4 py-1.5 text-sm text-text placeholder:text-text-faint focus:border-primary-dark focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
          <select
            value={city}
            onChange={(e) => setCity(e.target.value)}
            className="rounded-pill border border-border bg-surface-soft px-4 py-1.5 text-sm text-text focus:border-primary-dark focus:outline-none"
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
            className="rounded-pill bg-primary px-5 py-1.5 text-sm font-semibold text-ink transition hover:bg-primary-dark"
          >
            搜索
          </button>
          <span className="ml-auto text-sm text-text-muted">
            {jobs.length > 0 && `已加载 ${jobs.length} 条`}
          </span>
        </div>

        {/* 错误 */}
        {error && (
          <div className="rounded-xl bg-danger-soft px-4 py-2 text-sm text-danger">
            {error}
          </div>
        )}

        {/* 岗位表格 */}
        <div className="flex-1 overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
          <div className="overflow-x-auto overflow-y-auto" style={{ maxHeight: "calc(100vh - 300px)" }}>
            <table className="min-w-full">
              <thead className="sticky top-0 z-10 border-b border-border bg-surface-soft">
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
              <tbody className="divide-y divide-line">
                {isLoading && jobs.length === 0
                  ? Array.from({ length: 10 }).map((_, i) => (
                      <tr key={i}>
                        {Array.from({ length: 8 }).map((_, j) => (
                          <td key={j} className="px-4 py-3">
                            <div className="h-4 w-full animate-pulse rounded bg-line" />
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
              className="rounded-pill border border-border bg-surface px-6 py-2 text-sm font-medium text-text-muted transition hover:border-border-strong hover:text-text"
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
      className={`flex w-full items-center justify-between rounded-pill px-3.5 py-2 text-sm transition-colors ${
        active
          ? "bg-primary font-semibold text-ink shadow-sm"
          : "text-text-muted hover:bg-surface-soft hover:text-text"
      }`}
    >
      <span className="truncate">{label}</span>
      <span
        className={`ml-2 shrink-0 rounded-pill px-1.5 text-xs ${
          active ? "bg-ink/10 text-ink/70" : "bg-surface-soft text-text-faint"
        }`}
      >
        {count}
      </span>
    </button>
  );
}

function JobRow({ job }: { job: Job }) {
  const [favStatus, setFavStatus] = useState<"idle" | "loading" | "done">("idle");
  const [applyStatus, setApplyStatus] = useState<"idle" | "loading" | "done">("idle");

  const handleFavorite = async () => {
    if (favStatus === "loading") return;
    setFavStatus("loading");
    try {
      await createApplication({
        job_id: job.job_id,
        job_title: job.title,
        company_name: job.company,
        status: "favorite" as AppStatus,
        apply_url: job.apply_url || "",
      });
      setFavStatus("done");
    } catch {
      setFavStatus("idle");
    }
  };

  const handleApply = async () => {
    if (applyStatus === "loading") return;
    setApplyStatus("loading");
    try {
      await createApplication({
        job_id: job.job_id,
        job_title: job.title,
        company_name: job.company,
        status: "applied" as AppStatus,
        apply_url: job.apply_url || "",
      });
      setApplyStatus("done");
      if (job.apply_url) {
        window.open(job.apply_url, "_blank");
      }
    } catch {
      setApplyStatus("idle");
    }
  };

  return (
    <tr className="transition-colors hover:bg-primary-soft/50">
      <td className="px-4 py-3">
        <div className="font-medium text-text">{job.title}</div>
        {job.requirements && (
          <div className="mt-0.5 line-clamp-1 text-xs text-text-faint">
            {job.requirements}
          </div>
        )}
      </td>
      <td className="px-4 py-3 text-sm text-text-muted">{job.company}</td>
      <td className="px-4 py-3">
        {job.category && (
          <span className="rounded-pill bg-primary-soft px-2.5 py-0.5 text-xs font-medium text-ink/80">
            {job.category}
          </span>
        )}
      </td>
      <td className="px-4 py-3 text-sm text-text-muted">{job.city || "-"}</td>
      <td className="px-4 py-3 text-sm text-text-muted">
        {job.graduation_match ? "应届" : "不限"}
      </td>
      <td className="px-4 py-3 text-sm">
        {job.is_mt ? (
          <span className="rounded-pill bg-primary-soft px-2.5 py-0.5 text-xs font-medium text-ink/80">
            管培
          </span>
        ) : (
          <span className="text-text-faint">-</span>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-text-faint">
        {job.updated_at ? job.updated_at.slice(0, 10) : "-"}
      </td>
      <td className="px-4 py-3 text-right">
        <div className="flex justify-end gap-1.5">
          <button
            type="button"
            onClick={handleFavorite}
            disabled={favStatus === "loading"}
            className={`rounded-pill border px-2.5 py-1 text-xs transition ${
              favStatus === "done"
                ? "border-primary bg-primary text-ink"
                : "border-border text-text-muted hover:border-primary hover:text-ink"
            }`}
            title="收藏"
          >
            {favStatus === "done" ? "★" : "☆"}
          </button>
          <button
            type="button"
            onClick={handleApply}
            disabled={applyStatus === "loading"}
            className={`rounded-pill px-3 py-1 text-xs font-semibold transition ${
              applyStatus === "done"
                ? "bg-success text-white"
                : "bg-primary text-ink hover:bg-primary-dark"
            }`}
          >
            {applyStatus === "done" ? "已投递" : "投递"}
          </button>
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
