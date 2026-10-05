import { useEffect, useMemo, useState } from "react";
import type { ParsedProfile, KeywordTag, FitDirection } from "../api/llm";
import { useResumeStore } from "../stores/resumeStore";

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
  { key: "soft_skill", label: "软技能", icon: "🤝", badge: "bg-amber-100", accent: "text-amber-900" },
  { key: "cert", label: "证书", icon: "🎓", badge: "bg-yellow-100", accent: "text-yellow-900" },
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
      <span className="text-xs text-slate-400">权重</span>
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-orange-400"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs tabular-nums text-slate-500">{weight}</span>
    </div>
  );
}

// 单个关键词：词 + 权重条 + 编辑模式下的删除按钮。
function KeywordItem({
  kw,
  maxWeight,
  editMode,
  onDelete,
}: {
  kw: KeywordTag;
  maxWeight: number;
  editMode: boolean;
  onDelete: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <span className="truncate text-sm text-slate-deep">
        {kw.standard && kw.standard !== kw.kw ? `${kw.standard}` : kw.kw}
        {kw.standard && kw.standard !== kw.kw && (
          <span className="ml-1 text-xs text-slate-400">/ {kw.kw}</span>
        )}
      </span>
      <div className="flex items-center gap-2">
        <WeightBar weight={kw.weight} maxWeight={maxWeight} />
        {editMode && (
          <button
            type="button"
            onClick={onDelete}
            className="flex h-5 w-5 items-center justify-center rounded-full text-xs text-red-400 transition hover:bg-red-50 hover:text-red-600"
            title="删除"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );
}

// 添加关键词行：kw 输入 + weight 输入 + 确认按钮
function AddKeywordRow({ onAdd }: { onAdd: (kw: KeywordTag) => void }) {
  const [kw, setKw] = useState("");
  const [weight, setWeight] = useState("3");
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="w-full rounded-lg border border-dashed border-slate-200 py-1.5 text-xs text-slate-400 transition hover:border-orange-300 hover:text-orange-500"
      >
        + 添加关键词
      </button>
    );
  }

  const confirm = () => {
    const trimmed = kw.trim();
    const w = Number(weight);
    if (!trimmed || !Number.isFinite(w)) return;
    onAdd({
      kw: trimmed,
      standard: undefined,
      category: "other",
      weight: Math.max(0.1, Math.min(5, w)),
    });
    setKw("");
    setWeight("3");
    setOpen(false);
  };

  return (
    <div className="flex items-center gap-2 rounded-lg bg-slate-50 px-2 py-1.5">
      <input
        autoFocus
        value={kw}
        onChange={(e) => setKw(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") confirm();
          if (e.key === "Escape") setOpen(false);
        }}
        placeholder="关键词"
        className="min-w-0 flex-1 rounded border border-slate-200 bg-white px-2 py-1 text-xs outline-none focus:border-orange-300"
      />
      <input
        value={weight}
        onChange={(e) => setWeight(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") confirm();
          if (e.key === "Escape") setOpen(false);
        }}
        placeholder="权重"
        type="number"
        step="0.1"
        min="0.1"
        max="5"
        className="w-14 rounded border border-slate-200 bg-white px-1.5 py-1 text-xs tabular-nums outline-none focus:border-orange-300"
      />
      <button
        type="button"
        onClick={confirm}
        className="rounded bg-orange-500 px-2 py-1 text-xs text-white hover:bg-orange-600"
      >
        确定
      </button>
      <button
        type="button"
        onClick={() => setOpen(false)}
        className="rounded px-2 py-1 text-xs text-slate-400 hover:bg-slate-100"
      >
        取消
      </button>
    </div>
  );
}

// 适配方向卡片：方向名 + 权重徽章 + 证据 + 编辑模式下的删除按钮。
function FitDirectionCard({
  dir,
  maxWeight,
  editMode,
  onDelete,
}: {
  dir: FitDirection;
  maxWeight: number;
  editMode: boolean;
  onDelete: () => void;
}) {
  const pct = maxWeight > 0 ? Math.min(100, Math.max(6, (dir.weight / maxWeight) * 100)) : 0;
  return (
    <div className="glass relative rounded-2xl p-4 shadow-card transition hover:-translate-y-0.5 hover:shadow-lg">
      {editMode && (
        <button
          type="button"
          onClick={onDelete}
          className="absolute right-3 top-3 flex h-6 w-6 items-center justify-center rounded-full bg-red-50 text-xs text-red-500 transition hover:bg-red-100 hover:text-red-600"
          title="删除方向"
        >
          ✕
        </button>
      )}
      <div className="flex items-start justify-between gap-3 pr-8">
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
          权重 {dir.weight}
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

// 添加方向行：direction + weight + evidence 输入
function AddDirectionRow({ onAdd }: { onAdd: (d: FitDirection) => void }) {
  const [direction, setDirection] = useState("");
  const [weight, setWeight] = useState("3");
  const [evidence, setEvidence] = useState("");
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="w-full rounded-xl border border-dashed border-slate-200 py-2 text-xs text-slate-400 transition hover:border-orange-300 hover:text-orange-500"
      >
        + 添加适配方向
      </button>
    );
  }

  const confirm = () => {
    const trimmed = direction.trim();
    const w = Number(weight);
    if (!trimmed || !Number.isFinite(w)) return;
    onAdd({
      direction: trimmed,
      weight: Math.max(0.1, Math.min(5, w)),
      evidence: evidence.trim() || undefined,
    });
    setDirection("");
    setWeight("3");
    setEvidence("");
    setOpen(false);
  };

  return (
    <div className="glass rounded-2xl p-3 shadow-card">
      <div className="flex items-center gap-2">
        <input
          autoFocus
          value={direction}
          onChange={(e) => setDirection(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") confirm();
            if (e.key === "Escape") setOpen(false);
          }}
          placeholder="方向名(如 后端开发)"
          className="min-w-0 flex-1 rounded border border-slate-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-orange-300"
        />
        <input
          value={weight}
          onChange={(e) => setWeight(e.target.value)}
          placeholder="权重"
          type="number"
          step="0.1"
          min="0.1"
          max="5"
          className="w-16 rounded border border-slate-200 bg-white px-1.5 py-1.5 text-xs tabular-nums outline-none focus:border-orange-300"
        />
      </div>
      <input
        value={evidence}
        onChange={(e) => setEvidence(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") confirm();
          if (e.key === "Escape") setOpen(false);
        }}
        placeholder="依据(可选)"
        className="mt-2 w-full rounded border border-slate-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-orange-300"
      />
      <div className="mt-2 flex justify-end gap-2">
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="rounded px-2 py-1 text-xs text-slate-400 hover:bg-slate-100"
        >
          取消
        </button>
        <button
          type="button"
          onClick={confirm}
          className="rounded bg-orange-500 px-3 py-1 text-xs text-white hover:bg-orange-600"
        >
          确定
        </button>
      </div>
    </div>
  );
}

interface Props {
  profile: ParsedProfile;
}

export default function ParsedProfileDisplay({ profile }: Props) {
  const [editMode, setEditMode] = useState(false);
  // 编辑中的临时画像;进入编辑模式时从 profile 复制,退出时丢弃
  const [draft, setDraft] = useState<ParsedProfile>(profile);
  const [saving, setSaving] = useState(false);
  const saveProfileEdits = useResumeStore((s) => s.saveProfileEdits);
  const serverProfile = useResumeStore((s) => s.serverProfile);
  const saveTargetCompanies = useResumeStore((s) => s.saveTargetCompanies);

  // 目标公司(公司意向):从 serverProfile 读取,本地编辑后保存到后端
  const [targetCompanies, setTargetCompanies] = useState<string[]>(
    serverProfile?.target_companies ?? []
  );
  const [companyInput, setCompanyInput] = useState("");
  const [savingCompanies, setSavingCompanies] = useState(false);

  // serverProfile 异步加载后同步目标公司到本地 state
  useEffect(() => {
    if (serverProfile?.target_companies) {
      setTargetCompanies(serverProfile.target_companies);
    }
  }, [serverProfile?.target_companies]);

  const addTargetCompany = () => {
    const name = companyInput.trim();
    if (!name) return;
    if (targetCompanies.includes(name)) {
      setCompanyInput("");
      return;
    }
    setTargetCompanies((prev) => [...prev, name]);
    setCompanyInput("");
  };

  const removeTargetCompany = (name: string) => {
    setTargetCompanies((prev) => prev.filter((c) => c !== name));
  };

  const handleSaveCompanies = async () => {
    setSavingCompanies(true);
    try {
      await saveTargetCompanies(targetCompanies);
    } finally {
      setSavingCompanies(false);
    }
  };

  // 进入编辑模式时把 profile 复制到 draft
  const enterEdit = () => {
    setDraft({
      keywords: profile.keywords.map((k) => ({ ...k })),
      fit_directions: profile.fit_directions.map((d) => ({ ...d })),
    });
    setEditMode(true);
  };

  // 完成编辑:保存到后端 + 本地,退出编辑模式
  const finishEdit = async () => {
    setSaving(true);
    try {
      await saveProfileEdits(draft);
      setEditMode(false);
    } finally {
      setSaving(false);
    }
  };

  // 当前展示的画像:编辑模式用 draft,否则用 props.profile
  const display: ParsedProfile = editMode ? draft : profile;

  // 删除关键词
  const removeKw = (idx: number) => {
    setDraft((d) => ({
      ...d,
      keywords: d.keywords.filter((_, i) => i !== idx),
    }));
  };

  // 添加关键词(分组内)
  const addKw = (category: string, kw: KeywordTag) => {
    setDraft((d) => ({
      ...d,
      keywords: [...d.keywords, { ...kw, category }],
    }));
  };

  // 删除方向
  const removeDir = (idx: number) => {
    setDraft((d) => ({
      ...d,
      fit_directions: d.fit_directions.filter((_, i) => i !== idx),
    }));
  };

  // 添加方向
  const addDir = (d: FitDirection) => {
    setDraft((prev) => ({
      ...prev,
      fit_directions: [...prev.fit_directions, d],
    }));
  };

  // 按 category 分组：保留 CATEGORY_META 顺序，未列入的归到"其他"。
  const groups = useMemo(() => {
    const map = new Map<string, KeywordTag[]>();
    for (const kw of display.keywords) {
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
  }, [display.keywords]);

  const directions = useMemo(
    () => [...display.fit_directions].sort((a, b) => b.weight - a.weight),
    [display.fit_directions]
  );
  const dirMax = directions.reduce((m, d) => Math.max(m, d.weight), 0);

  const hasKeywords = display.keywords.length > 0;
  const hasDirections = directions.length > 0;

  return (
    <div className="space-y-5">
      {/* 头部：标题 + 编辑切换 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-deep">简历画像</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            共 {display.keywords.length} 个关键词 · {directions.length} 个适配方向
          </p>
        </div>
        <button
          type="button"
          disabled={saving}
          onClick={() => (editMode ? finishEdit() : enterEdit())}
          className={`rounded-xl px-3 py-1.5 text-xs font-medium transition disabled:opacity-50 ${
            editMode
              ? "bg-orange-500 text-white hover:bg-orange-600"
              : "bg-slate-100 text-slate-deep hover:bg-slate-200"
          }`}
        >
          {saving ? "保存中…" : editMode ? "完成" : "✏️ 编辑"}
        </button>
      </div>

      {editMode && (
        <div className="rounded-2xl bg-orange-50 px-4 py-2.5 text-xs text-orange-700">
          编辑模式：可删除 / 新增 关键词与适配方向，权重 0.1-5。点击「完成」保存后生效，下次推荐将依据此版本匹配。
        </div>
      )}

      {/* 关键词分组 */}
      {hasKeywords || editMode ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {groups.map(({ meta, items, max }) => (
            <div
              key={meta.key}
              className="glass rounded-2xl p-4 shadow-card"
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
                  <KeywordItem
                    key={`${kw.kw}-${i}`}
                    kw={kw}
                    maxWeight={max}
                    editMode={editMode}
                    onDelete={() => {
                      // 找到在 display.keywords 中的真实 index
                      const realIdx = display.keywords.findIndex(
                        (k) => k.kw === kw.kw && k.category === kw.category
                      );
                      if (realIdx >= 0) removeKw(realIdx);
                    }}
                  />
                ))}
              </div>
              {editMode && (
                <div className="mt-2">
                  <AddKeywordRow
                    onAdd={(kw) => addKw(meta.key === "other" ? "other" : meta.key, kw)}
                  />
                </div>
              )}
            </div>
          ))}
          {/* 编辑模式下若关键词为空,显示空分组让用户能添加 */}
          {editMode && groups.length === 0 && (
            <div className="glass rounded-2xl p-4 shadow-card">
              <AddKeywordRow onAdd={(kw) => addKw("other", kw)} />
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-600">
          暂未提取到关键词
        </div>
      )}

      {/* 适配方向 */}
      {hasDirections || editMode ? (
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
                editMode={editMode}
                onDelete={() => {
                  const realIdx = display.fit_directions.findIndex(
                    (x) => x.direction === d.direction
                  );
                  if (realIdx >= 0) removeDir(realIdx);
                }}
              />
            ))}
            {editMode && <AddDirectionRow onAdd={addDir} />}
          </div>
        </div>
      ) : null}

      {/* 候选人竞争力(实时计算,展示用户层级) */}
      {profile.candidate_score != null && (
        <div className="rounded-2xl bg-gradient-to-br from-blue-50 to-violet-50 px-4 py-3 text-xs">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-medium text-slate-700">你的竞争力层级</div>
              <p className="mt-1 leading-relaxed text-slate-500">
                综合学校/学历/实习/竞赛/论文等信号实时计算,用于和公司层级(顶/中/保底)做对齐匹配。
              </p>
            </div>
            <div className="flex items-center gap-3">
              <div className="text-right">
                <div className="text-3xl font-bold tabular-nums text-blue-700">
                  {profile.candidate_score.toFixed(0)}
                </div>
                <div className="text-[10px] text-slate-400">/ 100</div>
              </div>
              {profile.candidate_tier && (
                <span className={`rounded-full px-3 py-1 text-sm font-semibold ${
                  profile.candidate_tier === "顶" ? "bg-rose-100 text-rose-700"
                  : profile.candidate_tier === "中" ? "bg-blue-100 text-blue-700"
                  : profile.candidate_tier === "保底" ? "bg-emerald-100 text-emerald-700"
                  : "bg-slate-100 text-slate-600"
                }`}>
                  {profile.candidate_tier}
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 目标公司(公司意向):影响 company_preference 维度,同行业/同类型/同地位公司加分 */}
      <div className="glass rounded-2xl p-4 shadow-card">
        <div className="mb-3 flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-50 text-sm">
            🎯
          </span>
          <span className="text-sm font-semibold text-slate-deep">目标公司</span>
          <span className="ml-auto text-xs text-slate-400">
            {targetCompanies.length} 家
          </span>
        </div>
        <p className="mb-3 text-xs leading-relaxed text-slate-500">
          填写你心仪的公司,推荐时会优先展示同行业、同类型、同地位的公司(直接命中加满分)。留空则不影响排序。
        </p>
        {/* 已添加的目标公司标签 */}
        {targetCompanies.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-2">
            {targetCompanies.map((c) => (
              <span
                key={c}
                className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-3 py-1 text-xs text-emerald-700"
              >
                {c}
                <button
                  type="button"
                  onClick={() => removeTargetCompany(c)}
                  className="ml-0.5 flex h-4 w-4 items-center justify-center rounded-full text-emerald-400 transition hover:bg-emerald-100 hover:text-emerald-600"
                  title="移除"
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
        )}
        {/* 输入框 + 添加按钮 */}
        <div className="flex items-center gap-2">
          <input
            value={companyInput}
            onChange={(e) => setCompanyInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addTargetCompany();
              }
            }}
            placeholder="输入公司名(如 字节跳动、腾讯、Google),回车添加"
            className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-emerald-300"
          />
          <button
            type="button"
            onClick={addTargetCompany}
            className="shrink-0 rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-600 transition hover:bg-slate-200"
          >
            添加
          </button>
          <button
            type="button"
            onClick={handleSaveCompanies}
            disabled={savingCompanies}
            className="shrink-0 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-medium text-white transition hover:bg-emerald-600 disabled:opacity-50"
          >
            {savingCompanies ? "保存中…" : "保存"}
          </button>
        </div>
      </div>

      {/* 计算与匹配逻辑说明 */}
      <div className="rounded-2xl bg-slate-50/80 px-4 py-3 text-xs text-slate-500">
        <div className="font-medium text-slate-600">匹配逻辑说明</div>
        <p className="mt-1.5 leading-relaxed">
          权重 0.1-5,反映该关键词在简历中的强度(项目经历 3-5 / 技能列表 2-3 / 其他 1-2)。
          推荐时按 8 个维度加权打分:方向对齐(15%) · 硬技能命中(15%) · 竞争力对齐(20%) ·
          学历门槛(15%) · 综合技能覆盖(10%) · 专业匹配(10%) · 公司意向(10%) · 城市(5%)。
          方向硬门槛:方向维度过低时总分受限,避免靠泛技能刷分挤进推荐。
        </p>
      </div>
    </div>
  );
}
