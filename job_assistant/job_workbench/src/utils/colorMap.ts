// 分类字段颜色映射：与飞书源表 select 选项色系对齐。
// 每个值映射到 { bg, text } 的 Tailwind 类名，用于渲染彩色胶囊标签。
// 未命中的值走 defaultColor（中性灰）。

type ColorPair = { bg: string; text: string };

/** 行业 → 颜色 */
const INDUSTRY_COLORS: Record<string, ColorPair> = {
  "互联网/科技": { bg: "bg-blue-100", text: "text-blue-700" },
  金融: { bg: "bg-amber-100", text: "text-amber-900" },
  "制造/工业": { bg: "bg-orange-100", text: "text-orange-900" },
  "咨询/专业服务": { bg: "bg-violet-100", text: "text-violet-700" },
  房地产: { bg: "bg-rose-100", text: "text-rose-700" },
  "房地产/建筑": { bg: "bg-rose-100", text: "text-rose-700" },
  "快消/零售": { bg: "bg-pink-100", text: "text-pink-700" },
  医疗: { bg: "bg-emerald-100", text: "text-emerald-700" },
  "医疗/医药": { bg: "bg-emerald-100", text: "text-emerald-700" },
  教育: { bg: "bg-cyan-100", text: "text-cyan-700" },
  传媒: { bg: "bg-fuchsia-100", text: "text-fuchsia-700" },
  能源: { bg: "bg-yellow-100", text: "text-yellow-900" },
  汽车: { bg: "bg-slate-100", text: "text-slate-700" },
  其他: { bg: "bg-gray-100", text: "text-gray-600" },
};

/** 公司类型 → 颜色 */
const COMPANY_TYPE_COLORS: Record<string, ColorPair> = {
  民企: { bg: "bg-slate-100", text: "text-slate-700" },
  国央企: { bg: "bg-red-100", text: "text-red-700" },
  外企: { bg: "bg-blue-100", text: "text-blue-700" },
  "事业单位/政府": { bg: "bg-green-100", text: "text-green-700" },
  其他: { bg: "bg-gray-100", text: "text-gray-600" },
};

/** 招聘类型 → 颜色 */
const RECRUIT_TYPE_COLORS: Record<string, ColorPair> = {
  校招: { bg: "bg-blue-100", text: "text-blue-700" },
  实习: { bg: "bg-green-100", text: "text-green-700" },
  社招: { bg: "bg-gray-100", text: "text-gray-600" },
};

/** 最低学历 → 颜色（按学历层级） */
const EDUCATION_COLORS: Record<string, ColorPair> = {
  不限: { bg: "bg-gray-100", text: "text-gray-600" },
  专科: { bg: "bg-teal-100", text: "text-teal-700" },
  "专科起": { bg: "bg-teal-100", text: "text-teal-700" },
  本科: { bg: "bg-blue-100", text: "text-blue-700" },
  "本科起": { bg: "bg-blue-100", text: "text-blue-700" },
  硕士: { bg: "bg-violet-100", text: "text-violet-700" },
  "硕士起": { bg: "bg-violet-100", text: "text-violet-700" },
  博士: { bg: "bg-fuchsia-100", text: "text-fuchsia-700" },
  "博士起": { bg: "bg-fuchsia-100", text: "text-fuchsia-700" },
};

/** 岗位分类 → 颜色 */
const CATEGORY_COLORS: Record<string, ColorPair> = {
  开发: { bg: "bg-blue-100", text: "text-blue-700" },
  算法: { bg: "bg-violet-100", text: "text-violet-700" },
  产品: { bg: "bg-amber-100", text: "text-amber-900" },
  设计: { bg: "bg-pink-100", text: "text-pink-700" },
  运营: { bg: "bg-cyan-100", text: "text-cyan-700" },
  "运营与供应链": { bg: "bg-cyan-100", text: "text-cyan-700" },
  "商业(销售与市场)": { bg: "bg-rose-100", text: "text-rose-700" },
  职能: { bg: "bg-slate-100", text: "text-slate-700" },
  "制造与质量": { bg: "bg-orange-100", text: "text-orange-900" },
  "硬件电子": { bg: "bg-yellow-100", text: "text-yellow-900" },
  管培生: { bg: "bg-emerald-100", text: "text-emerald-700" },
  数据: { bg: "bg-indigo-100", text: "text-indigo-700" },
  市场: { bg: "bg-rose-100", text: "text-rose-700" },
  销售: { bg: "bg-red-100", text: "text-red-700" },
};

/** 难度 → 颜色 */
const DIFFICULTY_COLORS: Record<string, ColorPair> = {
  简单: { bg: "bg-green-100", text: "text-green-700" },
  easy: { bg: "bg-green-100", text: "text-green-700" },
  低: { bg: "bg-green-100", text: "text-green-700" },
  "1": { bg: "bg-green-100", text: "text-green-700" },
  "1星": { bg: "bg-green-100", text: "text-green-700" },
  "★": { bg: "bg-green-100", text: "text-green-700" },
  "⭐": { bg: "bg-green-100", text: "text-green-700" },
  中等: { bg: "bg-amber-100", text: "text-amber-900" },
  medium: { bg: "bg-amber-100", text: "text-amber-900" },
  中: { bg: "bg-amber-100", text: "text-amber-900" },
  "2": { bg: "bg-amber-100", text: "text-amber-900" },
  "2星": { bg: "bg-amber-100", text: "text-amber-900" },
  "★★": { bg: "bg-amber-100", text: "text-amber-900" },
  "⭐⭐": { bg: "bg-amber-100", text: "text-amber-900" },
  困难: { bg: "bg-red-100", text: "text-red-700" },
  hard: { bg: "bg-red-100", text: "text-red-700" },
  高: { bg: "bg-red-100", text: "text-red-700" },
  "3": { bg: "bg-red-100", text: "text-red-700" },
  "3星": { bg: "bg-red-100", text: "text-red-700" },
  "★★★": { bg: "bg-red-100", text: "text-red-700" },
  "⭐⭐⭐": { bg: "bg-red-100", text: "text-red-700" },
  非常困难: { bg: "bg-red-100", text: "text-red-700" },
  expert: { bg: "bg-red-100", text: "text-red-700" },
  "4": { bg: "bg-red-100", text: "text-red-700" },
  "4星": { bg: "bg-red-100", text: "text-red-700" },
  "★★★★": { bg: "bg-red-100", text: "text-red-700" },
  "⭐⭐⭐⭐": { bg: "bg-red-100", text: "text-red-700" },
};

/** 难度归一化:把后端实际取值映射到三档(简单/中等/困难)。
 * 实际数据样例:"中等难度" / "较为激烈" / "较低难度" / "最激烈" / "简单" / "中等" / "困难"。
 * 策略:用 includes 模糊匹配,而非严格相等,兼容"中等难度""较为激烈"等组合词。
 * 也支持英文(Easy/Medium/Hard)、星级(★/⭐)、数字(1-4)。 */
function normalizeDifficulty(v: string): string {
  const s = v.trim().toLowerCase();
  if (!s) return "";
  // 直接命中(已归一化或与 key 完全相等)
  if (DIFFICULTY_COLORS[s]) return s;
  // 简单/低档:简单 / 容易 / easy / 低 / 较低 / 1星 / ★
  if (/简单|容易|easy|较低|低难度|^低$|^1星?$|^[★⭐]$/.test(s)) return "简单";
  // 中等/中档:中等 / medium / 中 / 一般 / 2星 / ★★
  if (/中等|medium|一般|^中$|^2星?$|^[★⭐]{2}$/.test(s)) return "中等";
  // 困难/高档:困难 / hard / 高 / 激烈 / 3星 / ★★★
  if (/困难|hard|较高|激烈|^高$|^3星?$|^[★⭐]{3}$/.test(s)) return "困难";
  // 非常困难:非常困难 / expert / 4星 / ★★★★
  if (/非常|expert|最激烈|^4星?$|^[★⭐]{4}$/.test(s)) return "困难";
  // 数字 1-4
  const m = s.match(/^(\d)/);
  if (m) {
    const n = parseInt(m[1], 10);
    if (n === 1) return "简单";
    if (n === 2) return "中等";
    return "困难";
  }
  return s; // 未识别,返回原值让 pick 走 default
}

const DEFAULT_COLOR: ColorPair = { bg: "bg-gray-100", text: "text-gray-600" };

function pick(map: Record<string, ColorPair>, value: string | null | undefined): ColorPair {
  if (!value) return DEFAULT_COLOR;
  const v = value.trim();
  return map[v] ?? DEFAULT_COLOR;
}

export const colorMap = {
  industry: (v: string | null) => pick(INDUSTRY_COLORS, v),
  companyType: (v: string | null) => pick(COMPANY_TYPE_COLORS, v),
  recruitType: (v: string | null) => pick(RECRUIT_TYPE_COLORS, v),
  education: (v: string | null) => pick(EDUCATION_COLORS, v),
  category: (v: string | null) => pick(CATEGORY_COLORS, v),
  difficulty: (v: string | null) => pick(DIFFICULTY_COLORS, normalizeDifficulty(v || "")),
  /** 是否管培：1=是(绿), 0=否(灰) */
  isMt: (v: number | string | null) =>
    v === 1 || v === "1"
      ? { bg: "bg-emerald-100", text: "text-emerald-700" }
      : { bg: "bg-gray-100", text: "text-gray-600" },
};

/** 通用彩色标签组件用的 className 生成 */
export function pillClass(pair: ColorPair): string {
  return `inline-flex items-center rounded-pill px-2 py-0.5 text-xs font-medium ${pair.bg} ${pair.text}`;
}
