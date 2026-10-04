// Zustand resume store：简历上传 / LLM 解析 / 本地持久化的状态中枢。
//
// 设计：
// - activeResume / parsedProfile 双轨：activeResume 是简历数据镜像（含 raw_text / parsed_profile_json），
//   parsedProfile 是 parsed_profile_json 反序列化后的结构化对象，供组件直接消费。
// - phase 字段精确反馈"上传中 / 解析中 / 完成"三阶段，UI spinner 文案据此切换。
// - 文件读取走浏览器 FileReader；简历数据持久化到 localStorage。
// - LLM 解析通过 llmApi 调用后端 /api/v1/llm 端点。

import { create } from "zustand";

import { llmApi, type ParsedProfile } from "../api/llm";

// Resume struct（与 src-tauri/src/models.rs::Resume 字段严格对齐；snake_case JSON 直通 invoke）
export interface Resume {
  resume_id: string;
  file_path: string;
  raw_text: string | null;
  parsed_profile_json: string | null;
  created_at: string;
  is_active: number;
}

export type ResumePhase = "idle" | "uploading" | "parsing" | "done";

const ACCEPTED_TEXT_EXT = [".txt", ".md", ".markdown", ".text"];

// localStorage 存储键
const RESUME_STORAGE_KEY = "job_assistant_active_resume";

// 从 localStorage 读取 active resume
function loadResumeFromStorage(): Resume | null {
  try {
    const raw = localStorage.getItem(RESUME_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Resume) : null;
  } catch {
    return null;
  }
}

// 保存 resume 到 localStorage
function saveResumeToStorage(resume: Resume): void {
  try {
    localStorage.setItem(RESUME_STORAGE_KEY, JSON.stringify(resume));
  } catch {
    /* localStorage 不可用时静默忽略 */
  }
}

// 与 appStore.nowIso 同实现：ISO8601 → "YYYY-MM-DD HH:mm:ss"，对齐 SQLite TEXT 字段。
function nowIso(): string {
  return new Date().toISOString().replace("T", " ").slice(0, 19);
}

// resume_id 生成：时间戳 + 短随机后缀，避免与既有行撞号（参考 T14 genAppId）。
function genResumeId(): string {
  return `resume-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

// 浏览器 FileReader 读文本文件（Promise 封装）。
function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const text = typeof reader.result === "string" ? reader.result : "";
      resolve(text);
    };
    reader.onerror = () => reject(new Error("文件读取失败"));
    reader.readAsText(file);
  });
}

// 简单文件大小格式化：< 1KB 显示 B，< 1MB 显示 KB，否则 MB。
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function isPdfFile(file: File): boolean {
  return (
    file.type === "application/pdf" ||
    file.name.toLowerCase().endsWith(".pdf")
  );
}

function isTextFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return ACCEPTED_TEXT_EXT.some((ext) => name.endsWith(ext));
}

interface ResumeState {
  activeResume: Resume | null;
  parsedProfile: ParsedProfile | null;
  isLoading: boolean;
  phase: ResumePhase;
  error: string | null;
  lastFileName: string | null;

  uploadResume: (file: File) => Promise<Resume>;
  parseResume: (resumeText?: string) => Promise<ParsedProfile>;
  getActiveResume: () => Promise<void>;
  clearResume: () => void;
  clearError: () => void;
}

export const useResumeStore = create<ResumeState>((set, get) => ({
  activeResume: null,
  parsedProfile: null,
  isLoading: false,
  phase: "idle",
  error: null,
  lastFileName: null,

  // 上传：读取文本 → save_resume（is_active=1，新上传覆盖旧的 active）。
  // PDF 暂以"即将支持"拦截，避免乱码文本污染 LLM 解析。
  uploadResume: async (file) => {
    set({ isLoading: true, phase: "uploading", error: null, lastFileName: file.name });

    if (isPdfFile(file)) {
      const msg = "PDF 解析即将支持，请先用 .txt 或 .md 格式简历";
      set({ isLoading: false, phase: "idle", error: msg });
      throw new Error(msg);
    }
    if (!isTextFile(file)) {
      const msg = "暂不支持的文件类型，请上传 .txt 或 .md";
      set({ isLoading: false, phase: "idle", error: msg });
      throw new Error(msg);
    }

    try {
      const rawText = await readFileAsText(file);
      if (!rawText.trim()) {
        const msg = "文件内容为空，请确认简历非空";
        set({ isLoading: false, phase: "idle", error: msg });
        throw new Error(msg);
      }
      const resume: Resume = {
        resume_id: genResumeId(),
        file_path: file.name,
        raw_text: rawText,
        parsed_profile_json: null,
        created_at: nowIso(),
        is_active: 1,
      };
      saveResumeToStorage(resume);
      set({ activeResume: resume, isLoading: false });
      return resume;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ isLoading: false, phase: "idle", error: msg });
      throw e;
    }
  },

  // 解析：调云端 LLM → 把 parsed_profile_json 回写本地 resume。
  // resumeText 缺省取 activeResume.raw_text；都为空则报错。
  parseResume: async (resumeText) => {
    const current = get().activeResume;
    const text = resumeText?.trim() || current?.raw_text?.trim() || "";
    if (!text) {
      const msg = "没有可解析的简历文本，请先上传简历";
      set({ error: msg });
      throw new Error(msg);
    }

    set({ isLoading: true, phase: "parsing", error: null });
    try {
      const profile = await llmApi.parseResume(text);
      const profileJson = JSON.stringify(profile);

      // 回写本地 resume（parsed_profile_json 持久化，刷新 / 重启后 getActiveResume 可还原）
      if (current) {
        const updated: Resume = { ...current, parsed_profile_json: profileJson };
        saveResumeToStorage(updated);
        set({ activeResume: updated });
      }
      set({ parsedProfile: profile, isLoading: false, phase: "done" });
      return profile;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ isLoading: false, phase: "idle", error: msg });
      throw e;
    }
  },

  // 从 localStorage 拉 active resume（页面挂载时调用，还原历史解析结果）。
  getActiveResume: async () => {
    set({ isLoading: true, error: null });
    try {
      const resume = loadResumeFromStorage();
      if (resume) {
        let profile: ParsedProfile | null = null;
        if (resume.parsed_profile_json) {
          try {
            profile = JSON.parse(resume.parsed_profile_json) as ParsedProfile;
          } catch {
            profile = null; // 解析失败静默忽略，UI 回退到上传态
          }
        }
        set({
          activeResume: resume,
          parsedProfile: profile,
          isLoading: false,
          phase: profile ? "done" : "idle",
          lastFileName: resume.file_path,
        });
      } else {
        set({
          activeResume: null,
          parsedProfile: null,
          isLoading: false,
          phase: "idle",
          lastFileName: null,
        });
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ isLoading: false, phase: "idle", error: msg });
    }
  },

  // 清除本地状态和 localStorage 中的简历数据。
  // 用于"重新上传"按钮：UI 切回上传态，等待用户选新文件。
  clearResume: () => {
    try {
      localStorage.removeItem(RESUME_STORAGE_KEY);
    } catch {
      /* 忽略 */
    }
    set({
      activeResume: null,
      parsedProfile: null,
      phase: "idle",
      error: null,
      lastFileName: null,
    });
  },

  clearError: () => set({ error: null }),
}));
