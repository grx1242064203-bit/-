// 列显隐设置：齿轮按钮 + 下拉面板，可勾选显示哪些列。
// 偏好持久化到 localStorage（key 由 tableKey 区分）。
// 默认所有列可见。

import { useEffect, useRef, useState } from "react";

export interface ColumnDef {
  key: string;
  label: string;
}

interface ColumnSettingsProps {
  columns: ColumnDef[];
  tableKey: string;
  visibleKeys: string[];
  onChange: (keys: string[]) => void;
}

const STORAGE_PREFIX = "col_visibility:";

export default function ColumnSettings({
  columns,
  tableKey,
  visibleKeys,
  onChange,
}: ColumnSettingsProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // 初始化：从 localStorage 读取，没有则全部可见
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_PREFIX + tableKey);
    if (stored) {
      try {
        const arr = JSON.parse(stored) as string[];
        const valid = arr.filter((k) => columns.some((c) => c.key === k));
        if (valid.length > 0) {
          onChange(valid);
          return;
        }
      } catch {
        /* ignore */
      }
    }
    onChange(columns.map((c) => c.key));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tableKey]);

  // 持久化
  useEffect(() => {
    if (visibleKeys.length > 0) {
      localStorage.setItem(STORAGE_PREFIX + tableKey, JSON.stringify(visibleKeys));
    }
  }, [visibleKeys, tableKey]);

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

  const toggle = (key: string) => {
    if (visibleKeys.includes(key)) {
      // 至少保留一列
      if (visibleKeys.length <= 1) return;
      onChange(visibleKeys.filter((k) => k !== key));
    } else {
      onChange([...visibleKeys, key]);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex h-7 w-7 items-center justify-center rounded border border-line bg-white text-text-muted transition hover:bg-slate-50"
        title="列设置"
      >
        ⚙
      </button>

      {open && (
        <div className="absolute right-0 top-8 z-50 w-52 rounded-lg border border-line bg-white/95 p-2 shadow-lg backdrop-blur">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-medium text-text-muted">显示列</span>
            <button
              type="button"
              onClick={() => onChange(columns.map((c) => c.key))}
              className="text-xs text-primary-dark hover:underline"
            >
              全部显示
            </button>
          </div>
          <div className="max-h-72 overflow-y-auto">
            {columns.map((c) => {
              const checked = visibleKeys.includes(c.key);
              return (
                <label
                  key={c.key}
                  className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-xs hover:bg-surface-soft"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(c.key)}
                    className="h-3 w-3 accent-primary"
                  />
                  <span className="truncate">{c.label}</span>
                </label>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
