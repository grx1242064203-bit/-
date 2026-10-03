// 岗位筛选栏：城市 / 学历 / 管培 / 分类 / 公司 / 关键词 / 清除。
//
// 设计：
// - sticky top-0 + backdrop-blur：滚动岗位列表时筛选栏常驻可见。
// - 网格布局：mobile 1 列 / md 2 列 / lg 4 列；关键词搜索跨多列占满。
// - 即时触发：下拉/开关 onChange 立即 applyFilter；文本输入（公司 / 关键词）
//   300ms 防抖，避免每键一次 invoke（35K 数据下 DB LIKE 也要节流）。
// - 清除按钮：调用 store clearFilters() + 同步本地输入框 state。

import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { useJobsStore } from "../stores/jobsStore";
import type { JobFilter } from "../api/jobs";

const CITY_OPTIONS = [
  "全国各地",
  "北京",
  "上海",
  "广州",
  "深圳",
  "杭州",
  "成都",
  "南京",
  "武汉",
  "西安",
];

const EDUCATION_OPTIONS = ["不限", "大专", "本科", "硕士", "博士"];

const CATEGORY_OPTIONS = ["不限", "工科", "商科", "文科", "理科", "医科", "艺术", "农学"];

const inputClass =
  "w-full rounded-xl border border-orange-200 bg-orange-50/30 px-3 py-2 text-sm text-slate-deep placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-orange-400";

const labelClass = "mb-1 block text-xs font-medium text-slate-500";

export default function JobFilterBar() {
  const { filters, applyFilter, clearFilters: storeClearFilters } = useJobsStore();

  // 文本输入本地 state：避免受控组件每次 onChange 都触发 loadJobs。
  // 公司 / 关键词共享一个防抖 timer。
  const [keywordInput, setKeywordInput] = useState(filters.keyword ?? "");
  const [companyInput, setCompanyInput] = useState(filters.company ?? "");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 卸载时清掉未触发的防抖，避免 set state on unmounted。
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  function scheduleApply(patch: Partial<JobFilter>) {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => applyFilter(patch), 300);
  }

  function handleKeywordChange(e: ChangeEvent<HTMLInputElement>) {
    const v = e.target.value;
    setKeywordInput(v);
    scheduleApply({ keyword: v });
  }

  function handleCompanyChange(e: ChangeEvent<HTMLInputElement>) {
    const v = e.target.value;
    setCompanyInput(v);
    scheduleApply({ company: v });
  }

  function handleClear() {
    storeClearFilters();
    setKeywordInput("");
    setCompanyInput("");
  }

  return (
    <div className="sticky top-0 z-10 rounded-2xl border border-orange-100 bg-white/90 p-4 shadow-card backdrop-blur">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
        {/* 城市 */}
        <div>
          <label className={labelClass}>城市</label>
          <select
            value={filters.city ?? "全国各地"}
            onChange={(e) => applyFilter({ city: e.target.value })}
            className={inputClass}
          >
            {CITY_OPTIONS.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>

        {/* 学历 */}
        <div>
          <label className={labelClass}>学历</label>
          <select
            value={filters.education ?? "不限"}
            onChange={(e) => applyFilter({ education: e.target.value })}
            className={inputClass}
          >
            {EDUCATION_OPTIONS.map((ed) => (
              <option key={ed} value={ed}>
                {ed}
              </option>
            ))}
          </select>
        </div>

        {/* 分类 */}
        <div>
          <label className={labelClass}>分类</label>
          <select
            value={filters.category ?? "不限"}
            onChange={(e) => applyFilter({ category: e.target.value })}
            className={inputClass}
          >
            {CATEGORY_OPTIONS.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>

        {/* 管培开关 */}
        <div>
          <label className={labelClass}>管培</label>
          <button
            type="button"
            role="switch"
            aria-checked={filters.is_mt === true}
            onClick={() =>
              applyFilter({ is_mt: !filters.is_mt ? true : undefined })
            }
            className={`flex w-full items-center justify-between rounded-xl border px-3 py-2 text-sm transition ${
              filters.is_mt
                ? "border-orange-300 bg-orange-50 text-orange-700"
                : "border-orange-200 bg-orange-50/30 text-slate-500"
            }`}
          >
            <span>{filters.is_mt ? "仅看管培" : "不限"}</span>
            <span
              className={`relative h-5 w-9 rounded-full transition ${
                filters.is_mt ? "bg-orange-500" : "bg-slate-300"
              }`}
            >
              <span
                className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition ${
                  filters.is_mt ? "left-4" : "left-0.5"
                }`}
              />
            </span>
          </button>
        </div>

        {/* 公司名（防抖） */}
        <div>
          <label className={labelClass}>公司</label>
          <input
            type="text"
            value={companyInput}
            onChange={handleCompanyChange}
            placeholder="如：字节跳动"
            className={inputClass}
          />
        </div>

        {/* 关键词搜索（防抖，跨多列占满） */}
        <div className="md:col-span-2 lg:col-span-3">
          <label className={labelClass}>关键词搜索（公司名 + 岗位名）</label>
          <input
            type="text"
            value={keywordInput}
            onChange={handleKeywordChange}
            placeholder="如：前端、字节、Java…"
            className={inputClass}
          />
        </div>
      </div>

      {/* 清除筛选 */}
      <div className="mt-3 flex justify-end">
        <button
          type="button"
          onClick={handleClear}
          className="rounded-xl bg-slate-100 px-4 py-1.5 text-xs font-medium text-slate-500 transition hover:bg-slate-200"
        >
          清除筛选
        </button>
      </div>
    </div>
  );
}
