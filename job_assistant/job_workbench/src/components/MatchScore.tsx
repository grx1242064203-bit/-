// 评分展示组件：分数环 + 推荐等级徽章 + 评分理由列表。
//
// 设计：
// - 分数环用 SVG circle + stroke-dasharray 实现（不需要图表库），暖橙→绿色渐变：
//   ≥75 绿色（强烈推荐，#16a34a），55-74 橙色（推荐，#f97316），35-54 灰色（可申请，#64748b），
//   <35 红灰（不建议，#94a3b8 暗示"不建议"但保留可见性）。
// - 推荐等级徽章与分数环同色系：🔥 强烈推荐 / ✅ 推荐 / ➖ 可申请 / ❌ 不建议。
// - 评分理由列表：前 3 条直接显示，超过 3 条折叠 + "展开全部(N)" 链接。
//   llm_reason 在 Rust 端按 "; " 拼接（参考 score_all_jobs 实现），这里按 "; " 拆分还原。
// - props.score / props.reason：Job.llm_score / Job.llm_reason 直接传入；无评分不渲染本组件。

import { useState } from "react";

interface Props {
  score: number;
  reason: string | null;
  /** 紧凑模式（仅徽章，无理由列表；列表 Tab 用紧凑模式以提升信息密度） */
  compact?: boolean;
}

// 评分阈值（与 scorer.py / Rust 端 db.rs::get_score_summary 对齐）
const THRESHOLD_STRONG = 75;
const THRESHOLD_RECOMMEND = 55;
const THRESHOLD_CAN_APPLY = 35;

interface Tone {
  color: string;
  bg: string;
  text: string;
  ring: string;
  badge: string;
  label: string;
  emoji: string;
}

/** 按分数选色系：≥75 绿色 / 55-74 橙色 / 35-54 灰色 / <35 灰红。 */
function getTone(score: number): Tone {
  if (score >= THRESHOLD_STRONG) {
    return {
      color: "#16a34a",
      bg: "bg-green-50",
      text: "text-green-700",
      ring: "stroke-green-500",
      badge: "bg-green-500 text-white",
      label: "强烈推荐",
      emoji: "🔥",
    };
  }
  if (score >= THRESHOLD_RECOMMEND) {
    return {
      color: "#f97316",
      bg: "bg-orange-50",
      text: "text-orange-700",
      ring: "stroke-orange-500",
      badge: "bg-orange-500 text-white",
      label: "推荐",
      emoji: "✅",
    };
  }
  if (score >= THRESHOLD_CAN_APPLY) {
    return {
      color: "#64748b",
      bg: "bg-slate-100",
      text: "text-slate-600",
      ring: "stroke-slate-400",
      badge: "bg-slate-200 text-slate-700",
      label: "可申请",
      emoji: "➖",
    };
  }
  return {
    color: "#94a3b8",
    bg: "bg-slate-100",
    text: "text-slate-500",
    ring: "stroke-slate-300",
    badge: "bg-slate-200 text-slate-500",
    label: "不建议",
    emoji: "❌",
  };
}

/** 圆环分数可视化：SVG circle + stroke-dasharray 实现进度环。
 *  直径 56px，环宽 4，score 0-100 映射到周长比例。 */
function ScoreRing({ score, tone }: { score: number; tone: Tone }) {
  const size = 56;
  const stroke = 4;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  // 满分 100 → 满环；score / 100 比例覆盖
  const dash = (Math.max(0, Math.min(100, score)) / 100) * c;
  const rounded = Math.round(score);
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        {/* 背景环（淡灰） */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          className="text-slate-100"
        />
        {/* 进度环 */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={tone.color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c}`}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-sm font-semibold text-slate-deep">{rounded}</span>
      </div>
    </div>
  );
}

/** 解析 llm_reason 字符串：Rust 端按 "; " 拼接，这里还原成列表。
 *  失败兜底为单元素列表，避免空列表导致组件无内容。 */
function parseReasons(reason: string | null): string[] {
  if (!reason || !reason.trim()) return [];
  const parts = reason
    .split("; ")
    .map((s) => s.trim())
    .filter(Boolean);
  return parts.length > 0 ? parts : [reason.trim()];
}

export default function MatchScore({ score, reason, compact = false }: Props) {
  const [expanded, setExpanded] = useState(false);
  const tone = getTone(score);
  const reasons = parseReasons(reason);

  // 紧凑模式：仅徽章 + 分数，无理由列表（列表 Tab 用）
  if (compact) {
    return (
      <div className="flex items-center gap-2">
        <ScoreRing score={score} tone={tone} />
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${tone.badge}`}
        >
          {tone.emoji} {tone.label}
        </span>
      </div>
    );
  }

  // 完整模式：分数环 + 徽章 + 理由列表
  const visibleReasons = expanded ? reasons : reasons.slice(0, 3);
  const hiddenCount = reasons.length - visibleReasons.length;

  return (
    <div className={`rounded-xl ${tone.bg} p-3`}>
      <div className="flex items-center gap-3">
        <ScoreRing score={score} tone={tone} />
        <div className="min-w-0">
          <div
            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${tone.badge}`}
          >
            {tone.emoji} {tone.label}
          </div>
          <div className={`mt-1 text-xs ${tone.text}`}>
            匹配分 <strong className="text-sm font-semibold">{Math.round(score)}</strong> / 100
          </div>
        </div>
      </div>

      {reasons.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs text-slate-600">
          {visibleReasons.map((r, i) => (
            <li key={i} className="flex gap-1.5">
              <span className={`shrink-0 ${tone.text}`}>•</span>
              <span className="leading-relaxed">{r}</span>
            </li>
          ))}
        </ul>
      )}

      {hiddenCount > 0 && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-2 text-xs font-medium text-orange-700 hover:underline"
        >
          {expanded ? "收起理由" : `展开全部(${reasons.length})`}
        </button>
      )}
    </div>
  );
}
