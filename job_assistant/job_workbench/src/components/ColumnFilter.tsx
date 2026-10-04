// 列筛选器：表头下拉面板。
// - 分类列（传入 options）：可搜索的多选列表
// - 文本列（不传 options）：关键词搜索框，回车或失焦时应用
//
// 筛选状态由父组件管理（受控组件）。
// 分类列：value 为选中值数组；文本列：value[0] 为搜索关键词。

import { useEffect, useRef, useState } from "react";

export interface ColumnFilterOption {
  label: string;
  value: string;
  count?: number;
}

interface ColumnFilterProps {
  value: string[];
  options?: ColumnFilterOption[];
  onChange: (value: string[]) => void;
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
  const isTextMode = !options;
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

  // 文本模式：回车应用搜索
  const applyTextSearch = () => {
    if (search.trim()) {
      onChange([search.trim()]);
    } else {
      onChange([]);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => {
          setOpen((o) => !o);
          if (isTextMode) setSearch(value[0] ?? "");
        }}
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
            value={isTextMode ? search : search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && isTextMode) {
                applyTextSearch();
                setOpen(false);
              }
            }}
            placeholder={isTextMode ? "输入关键词搜索..." : "搜索选项..."}
            className="mb-2 w-full rounded border border-line px-2 py-1 text-xs outline-none focus:border-primary"
          />

          {!isTextMode && (
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
          )}

          {isTextMode && (
            <div className="text-xs text-text-faint">输入后按回车应用，支持模糊匹配</div>
          )}

          {hasFilter && (
            <button
              type="button"
              onClick={() => {
                onChange([]);
                setSearch("");
              }}
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
