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
import { resumeProfilesApi, type ResumeProfile } from "../api/resumeProfiles";

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

const ACCEPTED_EXT = [".txt", ".md", ".markdown", ".pdf"];

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

function isAcceptedFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return ACCEPTED_EXT.some((ext) => name.endsWith(ext));
}

function isPdfFile(file: File): boolean {
  return (
    file.type === "application/pdf" ||
    file.name.toLowerCase().endsWith(".pdf")
  );
}

interface ResumeState {
  activeResume: Resume | null;
  parsedProfile: ParsedProfile | null;
  serverProfile: ResumeProfile | null; // 后端简历画像（用于推荐）
  isLoading: boolean;
  phase: ResumePhase;
  error: string | null;
  lastFileName: string | null;

  uploadResume: (file: File) => Promise<Resume>;
  parseResume: (resumeText?: string, file?: File) => Promise<ParsedProfile>;
  getActiveResume: () => Promise<void>;
  clearResume: () => void;
  clearError: () => void;
}

export const useResumeStore = create<ResumeState>((set, get) => ({
  activeResume: null,
  parsedProfile: null,
  serverProfile: null,
  isLoading: false,
  phase: "idle",
  error: null,
  lastFileName: null,

  // 上传：接受 PDF / .txt / .md，PDF 走后端 parse-resume-file 提取文本
  uploadResume: async (file) => {
    set({ isLoading: true, phase: "uploading", error: null, lastFileName: file.name });

    if (!isAcceptedFile(file)) {
      const msg = "暂不支持的文件类型，请上传 .pdf / .txt / .md";
      set({ isLoading: false, phase: "idle", error: msg });
      throw new Error(msg);
    }

    if (file.size > 15 * 1024 * 1024) {
      const msg = "文件超过 15MB，请压缩后再上传";
      set({ isLoading: false, phase: "idle", error: msg });
      throw new Error(msg);
    }

    try {
      // 先创建本地 resume 记录
      const rawText = isPdfFile(file) ? "" : await readFileAsText(file);
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

  // 解析：PDF 走 parseResumeFile（后端提取），文本走 parseResume
  // 解析成功后自动存后端 resume_profiles 用于岗位推荐
  parseResume: async (resumeText, file) => {
    const current = get().activeResume;
    set({ isLoading: true, phase: "parsing", error: null });
    try {
      let profile: ParsedProfile;
      let textForProfile = "";

      if (file && isPdfFile(file)) {
        // PDF：上传到后端 parse-resume-file
        profile = await llmApi.parseResumeFile(file);
        textForProfile = ""; // PDF 原文不在前端，后端解析时已使用
      } else {
        const text = resumeText?.trim() || current?.raw_text?.trim() || "";
        if (!text) {
          const msg = "没有可解析的简历文本，请先上传简历";
          set({ error: msg, isLoading: false, phase: "idle" });
          throw new Error(msg);
        }
        profile = await llmApi.parseResume(text);
        textForProfile = text;
      }

      // 回写本地 resume
      const profileJson = JSON.stringify(profile);
      if (current) {
        const updated: Resume = { ...current, parsed_profile_json: profileJson };
        saveResumeToStorage(updated);
        set({ activeResume: updated });
      }

      // 存后端 resume_profiles（用于岗位推荐）
      let serverProfile: ResumeProfile | null = null;
      try {
        serverProfile = await resumeProfilesApi.create({
          resume_text: textForProfile || (current?.raw_text || ""),
          keywords: profile.keywords,
          fit_directions: profile.fit_directions,
        });
      } catch (e) {
        console.warn("存后端画像失败（不阻塞主流程）:", e);
      }

      set({ parsedProfile: profile, serverProfile, isLoading: false, phase: "done" });
      return profile;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ isLoading: false, phase: "idle", error: msg });
      throw e;
    }
  },

  // 从 localStorage 拉 active resume + 同步后端画像
  getActiveResume: async () => {
    set({ isLoading: true, error: null });
    try {
      const resume = loadResumeFromStorage();
      let serverProfile: ResumeProfile | null = null;
      try {
        serverProfile = await resumeProfilesApi.getActive();
      } catch {
        /* 用户未登录或后端不可用时静默 */
      }

      if (resume) {
        let profile: ParsedProfile | null = null;
        if (resume.parsed_profile_json) {
          try {
            profile = JSON.parse(resume.parsed_profile_json) as ParsedProfile;
          } catch {
            profile = null;
          }
        }
        set({
          activeResume: resume,
          parsedProfile: profile,
          serverProfile,
          isLoading: false,
          phase: profile ? "done" : "idle",
          lastFileName: resume.file_path,
        });
      } else {
        set({
          activeResume: null,
          parsedProfile: null,
          serverProfile,
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

  clearResume: () => {
    try {
      localStorage.removeItem(RESUME_STORAGE_KEY);
    } catch {
      /* 忽略 */
    }
    set({
      activeResume: null,
      parsedProfile: null,
      serverProfile: null,
      phase: "idle",
      error: null,
      lastFileName: null,
    });
  },

  clearError: () => set({ error: null }),
}));
