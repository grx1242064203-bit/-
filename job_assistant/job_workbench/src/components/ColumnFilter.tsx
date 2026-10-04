// 列筛选器：表头下拉面板。
// - 文本列：显示搜索框（模糊匹配）
// - 分类列：显示可搜索的多选列表（选项由调用方传入）
//
// 筛选状态由父组件管理（受控组件），onChange 回传选中值数组。
// 支持多选，空数组 = 不筛选。

import { useEffect, useRef, useState } from "react";

export interface ColumnFilterOption {
  label: string;
  value: string;
  count?: number;
}

interface ColumnFilterProps {
  /** 当前选中的值 */
  value: string[];
  /** 选项列表（分类列必传；文本列不传则仅显示搜索框） */
  options?: ColumnFilterOption[];
  /** 变更回调 */
  onChange: (value: string[]) => void;
  /** 列名，显示在面板顶部 */
  columnName: string;
}

export default function ColumnFilter({
  value,
  options,
  onChange,
  columnName,
}: ColumnFilterProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  // 点击外部关闭
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const hasFilter = value.length > 0;
  const filteredOptions = (options ?? []).filter((o) =>
    o.label.toLowerCase().includes(search.toLowerCase())
  );

  const toggle = (v: string) => {
    if (value.includes(v)) {
      onChange(value.filter((x) => x !== v));
    } else {
      onChange([...value, v]);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`ml-1 inline-flex h-4 w-4 items-center justify-center rounded text-[10px] transition ${
          hasFilter
            ? "bg-primary text-ink"
            : "text-text-faint hover:text-text-muted"
        }`}
        title={`筛选${columnName}`}
      >
        ▾
      </button>

      {open && (
        <div className="absolute left-0 top-6 z-50 w-56 rounded-lg border border-line bg-white/95 p-2 shadow-lg backdrop-blur">
          <div className="mb-2 text-xs font-medium text-text-muted">{columnName}</div>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={options ? "搜索选项..." : "输入关键词..."}
            className="mb-2 w-full rounded border border-line px-2 py-1 text-xs outline-none focus:border-primary"
          />

          {options ? (
            <div className="max-h-56 overflow-y-auto">
              {filteredOptions.map((o) => {
                const checked = value.includes(o.value);
                return (
                  <label
                    key={o.value}
                    className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-xs hover:bg-surface-soft"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggle(o.value)}
                      className="h-3 w-3 accent-primary"
                    />
                    <span className="flex-1 truncate">{o.label}</span>
                    {o.count !== undefined && (
                      <span className="text-text-faint">{o.count}</span>
                    )}
                  </label>
                );
              })}
              {filteredOptions.length === 0 && (
                <div className="py-2 text-center text-xs text-text-faint">无匹配项</div>
              )}
            </div>
          ) : (
            <div className="text-xs text-text-faint">输入后按回车或点击外部应用</div>
          )}

          {hasFilter && (
            <button
              type="button"
              onClick={() => onChange([])}
              className="mt-2 w-full rounded bg-surface-soft py-1 text-xs text-text-muted hover:bg-gray-100"
            >
              清除筛选
            </button>
          )}
        </div>
      )}
    </div>
  );
}
