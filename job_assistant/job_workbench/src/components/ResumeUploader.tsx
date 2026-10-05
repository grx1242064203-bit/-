import { useRef, useState, type DragEvent } from "react";
import {
  useResumeStore,
  formatFileSize,
} from "../stores/resumeStore";

// 简历拖拽 / 点击上传区域：
// - 支持 .txt / .md / .pdf / .jpg / .png 等
// - 纯文本：浏览器直读 → 点"立即解析"走 LLM
// - PDF / 图片：上传即走后端提取文本 + LLM 解析（一步完成）
// - 错误：暖橙 alert + 具体原因 + "重新上传"按钮
export default function ResumeUploader() {
  const { uploadResume, parseResume, phase, error, isLoading, clearError } =
    useResumeStore();
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function pickFile(f: File | null | undefined) {
    if (!f) return;
    clearError();
    setFile(f);
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    pickFile(e.dataTransfer.files?.[0]);
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    if (!isLoading) setDragOver(true);
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
  }

  function resetUpload() {
    clearError();
    setFile(null);
    inputRef.current?.click();
  }

  async function handleUploadAndParse() {
    if (!file || isLoading) return;
    try {
      await uploadResume(file);
      // PDF / 图片：uploadResume 已完成解析（phase=done），无需再调 parseResume
      // 纯文本：uploadResume 只存文本，需手动调 parseResume
      if (useResumeStore.getState().phase !== "done") {
        await parseResume();
      }
    } catch {
      // error 已写入 store，此处无需再处理
    }
  }

  const busy = isLoading;
  const phaseLabel =
    phase === "uploading"
      ? "上传中…"
      : phase === "parsing"
      ? "解析中…"
      : phase === "done"
      ? "完成"
      : "上传并解析";

  // input 放在 dropzone 外作兄弟节点，避免 input.click() 合成事件冒泡回
  // dropzone 重复触发 onClick（否则会循环打开文件对话框）。
  return (
    <div className="mx-auto w-full max-w-xl">
      <input
        ref={inputRef}
        type="file"
        accept=".txt,.md,.markdown,.text,.pdf,.jpg,.jpeg,.png,.webp,.bmp"
        className="hidden"
        onChange={(e) => pickFile(e.target.files?.[0])}
      />
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => {
          if (!busy) inputRef.current?.click();
        }}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && !busy) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed bg-white/50 px-6 py-12 text-center shadow-card backdrop-blur-md transition ${
          dragOver
            ? "border-orange-400 bg-orange-50/60 ring-4 ring-orange-100"
            : "border-orange-200 hover:border-orange-300 hover:bg-orange-50/30"
        } ${busy ? "pointer-events-none opacity-80" : ""}`}
      >
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-orange-50 text-3xl">
          📄
        </div>
        <p className="mt-4 text-base font-medium text-slate-deep">
          拖拽简历到此处，或点击选择文件
        </p>
        <p className="mt-1 text-xs text-slate-500">
          支持 .txt / .md / .pdf / .jpg / .png 等格式
        </p>
      </div>

      {/* 已选文件卡片（出错时隐藏，由错误区接管） */}
      {file && !error && (
        <div className="glass mt-4 flex items-center gap-3 rounded-2xl px-4 py-3 shadow-card">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-orange-50 text-lg">
            📝
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-slate-deep">
              {file.name}
            </div>
            <div className="text-xs text-slate-500">
              {formatFileSize(file.size)}
            </div>
          </div>
          {!busy && (
            <button
              type="button"
              onClick={() => setFile(null)}
              className="rounded-full p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-deep"
              aria-label="移除文件"
            >
              ✕
            </button>
          )}
        </div>
      )}

      {/* 错误提示 + 重新上传 */}
      {error && (
        <div className="mt-4 rounded-2xl bg-orange-50 px-4 py-3 text-sm text-orange-700">
          <div className="flex items-start gap-2">
            <span className="mt-0.5">⚠️</span>
            <span className="flex-1">{error}</span>
          </div>
          <div className="mt-3 flex justify-end">
            <button
              type="button"
              onClick={resetUpload}
              className="rounded-xl bg-orange-500 px-4 py-1.5 text-xs font-medium text-white transition hover:bg-orange-600"
            >
              重新上传
            </button>
          </div>
        </div>
      )}

      {/* 操作按钮 */}
      {file && !error && (
        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={handleUploadAndParse}
            disabled={busy || !file}
            className="flex items-center gap-2 rounded-2xl bg-orange-500 px-5 py-2.5 text-sm font-medium text-white shadow-card transition hover:bg-orange-600 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                {phaseLabel}
              </>
            ) : (
              <>🚀 {phaseLabel}</>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
