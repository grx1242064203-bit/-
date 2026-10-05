import { useEffect } from "react";
import { useResumeStore } from "../stores/resumeStore";
import ResumeUploader from "../components/ResumeUploader";
import ParsedProfileDisplay from "../components/ParsedProfileDisplay";

// 顶部状态徽章：上传中 / 解析中 / 已解析 / 未上传。
function StatusBadge() {
  const { isLoading, phase, activeResume, parsedProfile } = useResumeStore();

  let dot = "bg-slate-400";
  let text = "未上传";
  let pulse = false;
  if (isLoading && phase === "uploading") {
    dot = "bg-orange-500";
    text = "上传中";
    pulse = true;
  } else if (isLoading && phase === "parsing") {
    dot = "bg-orange-500";
    text = "解析中";
    pulse = true;
  } else if (activeResume && parsedProfile) {
    dot = "bg-green-500";
    text = "已解析";
  } else if (activeResume) {
    dot = "bg-amber-500";
    text = "已上传";
  }

  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1 text-xs text-slate-500 shadow-card">
      <span
        className={`h-2 w-2 rounded-full ${dot} ${pulse ? "animate-pulse" : ""}`}
      />
      {text}
    </span>
  );
}

export default function Resume() {
  const {
    activeResume,
    parsedProfile,
    isLoading,
    phase,
    error,
    getActiveResume,
    parseResume,
    clearResume,
    clearError,
  } = useResumeStore();

  // 挂载时拉本地 active resume，还原历史解析结果。
  useEffect(() => {
    getActiveResume();
  }, [getActiveResume]);

  const showUploader = !activeResume; // 空态 + 上传中（uploader 自带进度）
  const showParsingSpinner =
    !!activeResume && isLoading && phase === "parsing";
  const showParsed = !!activeResume && !!parsedProfile && !isLoading;
  const showUploadedNotParsed =
    !!activeResume && !parsedProfile && !isLoading && phase !== "parsing";
  // 解析失败（已上传简历但出错）：页面级 alert + 重新解析。
  const showPageError = !!error && !!activeResume;

  return (
    <div className="space-y-4">
      {/* 顶部：标题 + 状态 + 重新上传 */}
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold text-slate-deep">简历</h1>
        <StatusBadge />
        {showParsed && (
          <button
            type="button"
            onClick={() => {
              clearError();
              clearResume();
            }}
            className="ml-auto rounded-xl bg-orange-500 px-4 py-2 text-sm font-medium text-white shadow-card transition hover:bg-orange-600"
          >
            ↻ 重新上传
          </button>
        )}
      </div>

      {/* 页面级错误（解析失败）：暖橙 alert + 重新解析 / 重新上传 */}
      {showPageError && (
        <div className="flex items-start gap-2 rounded-2xl bg-orange-50 px-4 py-3 text-sm text-orange-700">
          <span className="mt-0.5">⚠️</span>
          <span className="flex-1">{error}</span>
          <div className="flex shrink-0 gap-2">
            <button
              type="button"
              onClick={() => {
                clearError();
                parseResume();
              }}
              className="rounded-lg bg-orange-500 px-3 py-1 text-xs font-medium text-white hover:bg-orange-600"
            >
              重新解析
            </button>
            <button
              type="button"
              onClick={() => {
                clearError();
                clearResume();
              }}
              className="rounded-lg border border-orange-300 bg-white px-3 py-1 text-xs font-medium text-orange-600 hover:bg-orange-50"
            >
              重新上传
            </button>
          </div>
        </div>
      )}

      {/* 主体：上传态 / 解析中 spinner / 画像展示 / 已上传未解析 */}
      {showUploader ? (
        <div className="flex min-h-[60vh] items-center justify-center">
          <ResumeUploader />
        </div>
      ) : showParsingSpinner ? (
        <div className="glass flex h-64 flex-col items-center justify-center rounded-2xl shadow-card">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-orange-200 border-t-orange-500" />
          <p className="mt-4 text-sm font-medium text-slate-deep">
            正在分析你的简历…
          </p>
          <p className="mt-1 text-xs text-slate-500">
            LLM 正在提取关键词与适配方向
          </p>
        </div>
      ) : showParsed ? (
        <div className="glass rounded-card p-6 shadow-card">
          <ParsedProfileDisplay profile={parsedProfile!} />
        </div>
      ) : showUploadedNotParsed ? (
        <div className="glass flex h-64 flex-col items-center justify-center rounded-2xl shadow-card">
          <div className="text-4xl">📝</div>
          <p className="mt-2 text-base font-medium text-slate-deep">
            简历已上传，尚未解析
          </p>
          <p className="mt-1 text-sm text-slate-500">
            点击下方按钮调用 LLM 提取关键词画像
          </p>
          <button
            type="button"
            onClick={() => {
              clearError();
              parseResume();
            }}
            className="mt-4 rounded-xl bg-orange-500 px-4 py-2 text-sm font-medium text-white hover:bg-orange-600"
          >
            立即解析
          </button>
        </div>
      ) : null}
    </div>
  );
}
