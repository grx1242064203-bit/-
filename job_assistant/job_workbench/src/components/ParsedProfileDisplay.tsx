import { useMemo, useState } from "react";
import type { ParsedProfile, KeywordTag, FitDirection } from "../api/llm";

// 关键词分类元数据：按 category 分组渲染。
// 顺序即展示顺序；未匹配到的 category 统一兜底到"其他"。
interface CategoryMeta {
  key: string;
  label: string;
  icon: string;
  // 分组卡片的浅色背景 + 强调文字色
  badge: string;
  accent: string;
}

const CATEGORY_META: CategoryMeta[] = [
  { key: "hard_skill", label: "硬技能", icon: "⚙️", badge: "bg-orange-50", accent: "text-orange-700" },
  { key: "soft_skill", label: "软技能", icon: "🤝", badge: "bg-amber-50", accent: "text-amber-700" },
  { key: "cert", label: "证书", icon: "🎓", badge: "bg-yellow-50", accent: "text-yellow-700" },
  { key: "education", label: "教育", icon: "🏫", badge: "bg-blue-50", accent: "text-blue-700" },
  { key: "city", label: "城市", icon: "📍", badge: "bg-green-50", accent: "text-green-700" },
  { key: "role", label: "方向", icon: "💼", badge: "bg-purple-50", accent: "text-purple-700" },
];

const OTHER_META: CategoryMeta = {
  key: "other",
  label: "其他",
  icon: "✨",
  badge: "bg-slate-50",
  accent: "text-slate-600",
};

// 关键词权重条：以组内最大权重为 100% 做相对条形图，数字始终显示原值。
function WeightBar({ weight, maxWeight }: { weight: number; maxWeight: number }) {
  const pct = maxWeight > 0 ? Math.min(100, Math.max(6, (weight / maxWeight) * 100)) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-orange-400"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs tabular-nums text-slate-500">{weight}</span>
    </div>
  );
}

// 单个关键词：词 + 权重条。
function KeywordItem({ kw, maxWeight }: { kw: KeywordTag; maxWeight: number }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <span className="truncate text-sm text-slate-deep">
        {kw.standard && kw.standard !== kw.kw ? `${kw.standard}` : kw.kw}
        {kw.standard && kw.standard !== kw.kw && (
          <span className="ml-1 text-xs text-slate-400">/ {kw.kw}</span>
        )}
      </span>
      <WeightBar weight={kw.weight} maxWeight={maxWeight} />
    </div>
  );
}

// 适配方向卡片：方向名 + 权重徽章 + 证据。
function FitDirectionCard({ dir, maxWeight }: { dir: FitDirection; maxWeight: number }) {
  const pct = maxWeight > 0 ? Math.min(100, Math.max(6, (dir.weight / maxWeight) * 100)) : 0;
  return (
    <div className="rounded-2xl border border-orange-100 bg-white p-4 shadow-card transition hover:-translate-y-0.5 hover:shadow-lg">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-slate-deep">
            {dir.direction}
          </div>
          {dir.description && (
            <div className="mt-0.5 line-clamp-2 text-xs text-slate-500">
              {dir.description}
            </div>
          )}
        </div>
        <span className="shrink-0 rounded-full bg-orange-500 px-2.5 py-0.5 text-xs font-medium text-white tabular-nums">
          {dir.weight}
        </span>
      </div>
      {/* 权重条 */}
      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-orange-400"
          style={{ width: `${pct}%` }}
        />
      </div>
      {dir.evidence && (
        <div className="mt-3 rounded-xl bg-orange-50/60 px-3 py-2 text-xs text-orange-700">
          <span className="font-medium">依据：</span>
          {dir.evidence}
        </div>
      )}
    </div>
  );
}

interface Props {
  profile: ParsedProfile;
}

export default function ParsedProfileDisplay({ profile }: Props) {
  const [editMode, setEditMode] = useState(false);

  // 按 category 分组：保留 CATEGORY_META 顺序，未列入的归到"其他"。
  const groups = useMemo(() => {
    const map = new Map<string, KeywordTag[]>();
    for (const kw of profile.keywords) {
      const cat = (kw.category || "other").toLowerCase();
      const arr = map.get(cat) ?? [];
      arr.push(kw);
      map.set(cat, arr);
    }
    const result: { meta: CategoryMeta; items: KeywordTag[]; max: number }[] = [];
    for (const meta of CATEGORY_META) {
      const items = (map.get(meta.key) ?? []).sort((a, b) => b.weight - a.weight);
      if (items.length === 0) continue;
      const max = items.reduce((m, k) => Math.max(m, k.weight), 0);
      result.push({ meta, items, max });
    }
    // 任何未匹配已知 6 个主分类的 category（含 "other"/"tool"/"framework"/
    // "domain"/"project" 等）统一归入"其他"组，避免与 others 重复收集。
    const known = new Set(CATEGORY_META.map((m) => m.key));
    const otherItems = [...map.entries()]
      .filter(([k]) => !known.has(k))
      .flatMap(([, v]) => v)
      .sort((a, b) => b.weight - a.weight);
    if (otherItems.length > 0) {
      const max = otherItems.reduce((m, k) => Math.max(m, k.weight), 0);
      result.push({ meta: OTHER_META, items: otherItems, max });
    }
    return result;
  }, [profile.keywords]);

  const directions = useMemo(
    () => [...profile.fit_directions].sort((a, b) => b.weight - a.weight),
    [profile.fit_directions]
  );
  const dirMax = directions.reduce((m, d) => Math.max(m, d.weight), 0);

  const hasKeywords = profile.keywords.length > 0;
  const hasDirections = directions.length > 0;

  return (
    <div className="space-y-5">
      {/* 头部：标题 + 编辑切换（编辑功能后续任务接入，当前仅切换占位态） */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-deep">简历画像</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            共 {profile.keywords.length} 个关键词 · {directions.length} 个适配方向
          </p>
        </div>
        <button
          type="button"
          onClick={() => setEditMode((v) => !v)}
          className={`rounded-xl px-3 py-1.5 text-xs font-medium transition ${
            editMode
              ? "bg-orange-500 text-white hover:bg-orange-600"
              : "bg-slate-100 text-slate-deep hover:bg-slate-200"
          }`}
        >
          {editMode ? "完成" : "✏️ 编辑"}
        </button>
      </div>

      {editMode && (
        <div className="rounded-2xl bg-orange-50 px-4 py-2.5 text-xs text-orange-700">
          编辑模式为预览态，关键词 / 方向的增删改将在后续任务接入。
        </div>
      )}

      {/* 关键词分组 */}
      {hasKeywords ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {groups.map(({ meta, items, max }) => (
            <div
              key={meta.key}
              className="rounded-2xl border border-orange-100 bg-white p-4 shadow-card"
            >
              <div className="mb-3 flex items-center gap-2">
                <span
                  className={`flex h-7 w-7 items-center justify-center rounded-lg ${meta.badge} text-sm`}
                >
                  {meta.icon}
                </span>
                <span className="text-sm font-semibold text-slate-deep">
                  {meta.label}
                </span>
                <span className={`ml-auto text-xs ${meta.accent}`}>
                  {items.length}
                </span>
              </div>
              <div className="divide-y divide-slate-50">
                {items.map((kw, i) => (
                  <KeywordItem key={`${kw.kw}-${i}`} kw={kw} maxWeight={max} />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-slate-200 bg-white/60 p-6 text-center text-sm text-slate-500">
          暂未提取到关键词
        </div>
      )}

      {/* 适配方向 */}
      {hasDirections ? (
        <div>
          <h3 className="mb-3 text-sm font-semibold text-slate-deep">
            适配方向
          </h3>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {directions.map((d, i) => (
              <FitDirectionCard
                key={`${d.direction}-${i}`}
                dir={d}
                maxWeight={dirMax}
              />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
