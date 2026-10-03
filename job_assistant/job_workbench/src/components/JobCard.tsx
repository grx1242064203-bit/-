// 单个岗位卡片：公司名 / 岗位名 / 城市 / 学历 / 管培徽章 / 截止日期 / 评分 / 操作按钮。
//
// 设计：
// - 暖橙色调（border-orange-100 / bg-orange-50/40）+ rounded-2xl + shadow-card + hover 微交互。
// - 评分区域：llm_score 有值显示分数 + 理由（line-clamp 截断），无值显示"未匹配"灰徽章。
//   分数 ≥80 高亮橙色实底，≥60 浅橙，<60 灰色。
// - "投递"按钮：跳 apply_url（apply_url 为 null 时禁用按钮）。
//   Tauri 2 webview 默认 window.open(_blank) 由 OS 处理，未启用 shell 插件时也能跳外链。
// - "记录投递"按钮：react-router navigate("/applications", { state: { job } })
//   投递页 T14 已建 AddApplicationModal，可后续接入 location.state 预填（T15+ 范围）。

import { useNavigate } from "react-router-dom";
import type { Job } from "../api/jobs";
import MatchScore from "./MatchScore";

interface Props {
  job: Job;
  /** 推荐视图模式：true 时隐藏 llm_score<35 的卡片由调用方负责（这里仅切换评分区域呈现形态）。
   *  - true：JobCard 用紧凑 MatchScore（仅分数环 + 徽章，无理由列表），列表 Tab 信息密度更高。
   *  - false（默认）：用完整 MatchScore（含理由列表前 3 条 + 展开全部）。 */
  recommendMode?: boolean;
}

// 评分徽章：有分显示分数，无分显示"未匹配"。
function ScoreBadge({ job }: { job: Job }) {
  if (job.llm_score == null) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-500">
        未匹配
      </span>
    );
  }
  const score = Math.round(job.llm_score);
  const tone =
    score >= 80
      ? "bg-orange-500 text-white"
      : score >= 60
      ? "bg-orange-100 text-orange-700"
      : "bg-slate-100 text-slate-600";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${tone}`}
      title={job.llm_reason ?? undefined}
    >
      🤖 {score} 分
    </span>
  );
}

/**
 * 把 ISO8601 / SQLite 风格的日期字符串格式化为 "YYYY-MM-DD"。
 * 兼容 "2026-10-03 10:00:00"（SQLite 风格）与 "2026-10-03T10:00:00"（ISO8601）。
 * 失败时原样返回，避免 UI 抛错。
 */
function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  const normalized = iso.includes("T") ? iso : iso.replace(" ", "T");
  const d = new Date(normalized);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export default function JobCard({ job, recommendMode = false }: Props) {
  const navigate = useNavigate();
  const isMt = job.is_mt === 1;
  const applyUrl = job.apply_url ?? null;
  const deadline = formatDate(job.deadline);
  const hasScore = job.llm_score != null;

  function handleApply() {
    if (!applyUrl) return;
    // Tauri 2 webview：window.open(_blank) 由 OS 默认浏览器接管（未启用 shell 插件时的兜底）。
    try {
      window.open(applyUrl, "_blank", "noopener,noreferrer");
    } catch {
      window.location.href = applyUrl;
    }
  }

  function handleRecord() {
    // 携带 job 信息跳投递页；AddApplicationModal 后续可读 location.state 预填。
    navigate("/applications", { state: { job } });
  }

  return (
    <div className="group flex flex-col gap-3 rounded-2xl border border-orange-100 bg-white p-4 shadow-card transition hover:-translate-y-0.5 hover:shadow-lg">
      {/* 顶部：公司 + 管培徽章 */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-base font-semibold text-slate-deep">
            {job.company}
          </div>
          <div className="truncate text-sm text-slate-600">{job.title}</div>
        </div>
        {isMt && (
          <span className="shrink-0 rounded-full bg-orange-500 px-2.5 py-0.5 text-xs font-medium text-white">
            管培
          </span>
        )}
      </div>

      {/* 元信息：城市 / 学历要求 / 截止日期 */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
        {job.city && <span>📍 {job.city}</span>}
        {job.requirements && <span>🎓 {job.requirements}</span>}
        {deadline && <span>⏰ 截止 {deadline}</span>}
      </div>

      {/* 评分区域：
        - 有评分（llm_score != null）：用 MatchScore 组件（推荐模式紧凑 / 默认完整带理由列表）。
        - 无评分：显示灰底"未匹配"徽章（推荐 Tab 下不会出现，因为推荐 Tab 已按 llm_score 区间过滤）。
        - 推荐 Tab 下默认隐藏 llm_score<35 的卡片由调用方 Jobs.tsx 控制（filter by min_score），
          这里在 recommendMode 下仍按真实分数渲染（不会出现 <35 的情况）。 */}
      {hasScore ? (
        <MatchScore
          score={job.llm_score as number}
          reason={job.llm_reason}
          compact={recommendMode}
        />
      ) : (
        <div className="flex items-center gap-2">
          <ScoreBadge job={job} />
          {job.llm_reason && (
            <span
              className="line-clamp-1 text-xs text-slate-500"
              title={job.llm_reason}
            >
              {job.llm_reason}
            </span>
          )}
        </div>
      )}

      {/* 操作按钮 */}
      <div className="mt-1 flex items-center gap-2">
        <button
          type="button"
          onClick={handleApply}
          disabled={!applyUrl}
          className="flex-1 rounded-xl bg-orange-500 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-orange-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          投递
        </button>
        <button
          type="button"
          onClick={handleRecord}
          className="flex-1 rounded-xl border border-orange-200 bg-orange-50/40 px-3 py-1.5 text-sm font-medium text-orange-700 transition hover:bg-orange-100"
        >
          记录投递
        </button>
      </div>
    </div>
  );
}
