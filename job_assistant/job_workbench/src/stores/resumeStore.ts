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

const ACCEPTED_TEXT_EXT = [".txt", ".md", ".markdown", ".text"];
const ACCEPTED_IMAGE_EXT = [".jpg", ".jpeg", ".png", ".webp", ".bmp"];
const ACCEPTED_PDF_EXT = [".pdf"];

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

/** 从结构化关键词中提取最高学历(博士>硕士>本科>大专),用于存入后端 degree 字段。 */
function extractDegreeFromKeywords(keywords: any[]): string {
  const eduWords = keywords
    .filter((k) => k && k.category === "education")
    .map((k) => k.standard || k.kw || "");
  for (const lv of ["博士", "硕士", "本科", "大专"]) {
    if (eduWords.some((w) => w.includes(lv))) return lv;
  }
  return "";
}

function isPdfFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return (
    file.type === "application/pdf" ||
    ACCEPTED_PDF_EXT.some((ext) => name.endsWith(ext))
  );
}

function isTextFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return ACCEPTED_TEXT_EXT.some((ext) => name.endsWith(ext));
}

function isImageFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return (
    file.type.startsWith("image/") ||
    ACCEPTED_IMAGE_EXT.some((ext) => name.endsWith(ext))
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
  parseResume: (resumeText?: string) => Promise<ParsedProfile>;
  getActiveResume: () => Promise<void>;
  /** 保存用户手动编辑后的画像(Phase 1 纯人工编辑,不调 LLM)。
   * 后端画像存在 → PATCH 后端 + 同步本地;不存在 → 仅同步本地。
   * 推荐接口下次读取 active 画像时用新值。 */
  saveProfileEdits: (edited: ParsedProfile) => Promise<void>;
  /** 保存用户目标公司(公司意向),用于 company_preference 维度加分 */
  saveTargetCompanies: (companies: string[]) => Promise<void>;
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

  // 上传简历：
  // - 纯文本(.txt/.md)：浏览器 FileReader 直读 → 存本地（后续 parseResume 走 LLM）
  // - PDF / 图片：直接调后端 /parse-resume-file，后端提取文本 + LLM 解析一次完成
  // 错误信息包含具体原因，UI 可据此展示。
  uploadResume: async (file) => {
    set({ isLoading: true, phase: "uploading", error: null, lastFileName: file.name });

    const supported = isTextFile(file) || isPdfFile(file) || isImageFile(file);
    if (!supported) {
      const msg = "暂不支持的文件类型，请上传 .txt / .md / .pdf / .jpg / .png 等格式";
      set({ isLoading: false, phase: "idle", error: msg });
      throw new Error(msg);
    }

    // 纯文本：本地读取后存简历（解析由用户点"立即解析"触发）
    if (isTextFile(file)) {
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
    }

    // PDF / 图片：后端一次性提取文本 + LLM 解析
    try {
      set({ phase: "parsing" });
      const { profile, rawText } = await llmApi.parseResumeFile(file);
      const resume: Resume = {
        resume_id: genResumeId(),
        file_path: file.name,
        raw_text: rawText,
        parsed_profile_json: JSON.stringify(profile),
        created_at: nowIso(),
        is_active: 1,
      };
      saveResumeToStorage(resume);

      // 存后端 resume_profiles（用于岗位推荐）
      let serverProfile: ResumeProfile | null = null;
      try {
        serverProfile = await resumeProfilesApi.create({
          resume_text: rawText,
          keywords: profile.keywords,
          fit_directions: profile.fit_directions,
          degree: extractDegreeFromKeywords(profile.keywords),
        });
      } catch (e) {
        console.warn("存后端画像失败（不阻塞主流程）:", e);
      }

      set({
        activeResume: resume,
        parsedProfile: profile,
        serverProfile,
        isLoading: false,
        phase: "done",
      });
      return resume;
    } catch (e) {
      // 后端 400 错误 detail 含具体原因（如"PDF 未提取到文本"、"图片中未识别到文字"）
      const msg = e instanceof Error ? e.message : String(e);
      set({ isLoading: false, phase: "idle", error: msg });
      throw e;
    }
  },

  // 解析：调云端 LLM → 把 parsed_profile_json 回写本地 resume。
  // resumeText 缺省取 activeResume.raw_text；都为空则报错。
  // 仅用于纯文本简历（PDF / 图片已在 uploadResume 中一步完成）。
  parseResume: async (resumeText) => {
    const current = get().activeResume;
    const text = resumeText?.trim() || current?.raw_text?.trim() || "";
    if (!text) {
      const msg = "没有可解析的简历文本，请先上传简历";
      set({ error: msg, isLoading: false, phase: "idle" });
      throw new Error(msg);
    }

    set({ isLoading: true, phase: "parsing", error: null });
    try {
      const profile = await llmApi.parseResume(text);

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
          resume_text: text,
          keywords: profile.keywords,
          fit_directions: profile.fit_directions,
          degree: extractDegreeFromKeywords(profile.keywords),
        });
      } catch (e) {
        console.warn("存后端画像失败（不阻塞主流程）:", e);
      }

      set({ parsedProfile: profile, serverProfile, isLoading: false, phase: "done" });

      // 解析完成后立即触发岗位推荐匹配（不阻塞主流程，失败仅告警）
      // 之前需要用户切到「为我推荐」tab 才开始匹配，现改为自动后台预热
      try {
        const { useAppStore } = await import("./appStore");
        // force=true 强制重新跑评分，避免命中旧缓存
        void useAppStore.getState().loadRecommendJobs(200, true);
      } catch (e) {
        console.warn("触发岗位推荐匹配失败（不阻塞主流程）:", e);
      }

      return profile;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ isLoading: false, phase: "idle", error: msg });
      throw e;
    }
  },

  // 从 localStorage 拉 active resume + 同步后端画像
  // 修复:localStorage 在新浏览器/换设备时为空,即使后端 serverProfile 存在也显示"未上传"。
  // 当 localStorage 空 但 serverProfile 存在时,从 serverProfile 重建 activeResume,
  // 并把 keywords/fit_directions 转成 ParsedProfile 让 Resume 页正确展示画像内容。
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
        // 透传后端实时计算的候选人竞争力分到 parsedProfile,供解析页展示
        if (profile && serverProfile?.candidate_score != null) {
          profile.candidate_score = serverProfile.candidate_score;
          profile.candidate_tier = serverProfile.candidate_tier;
        }
        set({
          activeResume: resume,
          parsedProfile: profile,
          serverProfile,
          isLoading: false,
          phase: profile ? "done" : "idle",
          lastFileName: resume.file_path,
        });
      } else if (serverProfile) {
        // localStorage 空但后端有画像:从 serverProfile 重建本地 resume
        const keywords = Array.isArray(serverProfile.keywords)
          ? serverProfile.keywords
          : [];
        const fitDirs = Array.isArray(serverProfile.fit_directions)
          ? serverProfile.fit_directions
          : [];
        const profile: ParsedProfile = {
          keywords: keywords as any,
          fit_directions: fitDirs as any,
          candidate_score: serverProfile.candidate_score,
          candidate_tier: serverProfile.candidate_tier,
        };
        const rebuilt: Resume = {
          resume_id: `server-${serverProfile.profile_id}`,
          file_path: "(已上传简历)",
          raw_text: serverProfile.resume_text || null,
          parsed_profile_json: JSON.stringify(profile),
          created_at: serverProfile.created_at,
          is_active: 1,
        };
        saveResumeToStorage(rebuilt);
        set({
          activeResume: rebuilt,
          parsedProfile: profile,
          serverProfile,
          isLoading: false,
          phase: "done",
          lastFileName: rebuilt.file_path,
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

  // 用户手动编辑后保存(Phase 1 纯人工编辑,不调 LLM):
  // - 后端画像存在 → PATCH /resume-profiles/{id} 更新 keywords/fit_directions
  // - 同步更新本地 localStorage 的 parsed_profile_json,保证刷新后仍为编辑后版本
  // - 推荐接口下次调用时读后端 active 画像,自动用新值匹配
  saveProfileEdits: async (edited) => {
    const current = get().activeResume;
    // 1) 本地同步(无论后端是否成功都先同步,避免编辑成果丢失)
    if (current) {
      const updated: Resume = {
        ...current,
        parsed_profile_json: JSON.stringify(edited),
      };
      saveResumeToStorage(updated);
      set({ activeResume: updated, parsedProfile: edited });
    } else {
      set({ parsedProfile: edited });
    }

    // 2) 后端画像存在则 PATCH(同时传 degree,保持后端 degree 字段与关键词一致)
    const sp = get().serverProfile;
    if (sp) {
      try {
        const updated = await resumeProfilesApi.update(sp.profile_id, {
          keywords: edited.keywords,
          fit_directions: edited.fit_directions,
          degree: extractDegreeFromKeywords(edited.keywords),
        });
        set({ serverProfile: updated });
      } catch (e) {
        // 后端保存失败时不阻塞 UI(本地已保存),控制台告警
        console.warn("后端画像保存失败(本地已保存):", e);
      }
    }
  },

  /** 保存用户目标公司(公司意向),用于 company_preference 维度加分。 */
  saveTargetCompanies: async (companies: string[]) => {
    const sp = get().serverProfile;
    if (!sp) {
      console.warn("无后端画像,无法保存目标公司");
      return;
    }
    try {
      const updated = await resumeProfilesApi.update(sp.profile_id, {
        target_companies: companies,
      });
      set({ serverProfile: updated });
    } catch (e) {
      console.warn("保存目标公司失败:", e);
    }
  },

  clearError: () => set({ error: null }),
}));
