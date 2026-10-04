// LLM API：封装 /api/v1/llm/* 端点（简历解析 / 画像补充）。
//
// 设计：
// - 复用 T8 的 apiClient（Bearer Token 自动注入 + 401 自动 refresh），与 auth.ts / sync.ts 同层。
// - 云端 parse-resume 契约：POST /api/v1/llm/parse-resume { resume_text } → { keywords: [...], fit_directions: [...] }。
// - LLM 输出 JSON 字段名可能漂移（kw / keyword / word；direction / direction_name / name），
//   normalizeParsedProfile 在边界做一次归一化，store / 组件只消费稳定的 KeywordTag / FitDirection。
// - 环境变量名 VITE_API_URL（与 client.ts 一致；sync.ts 用的 VITE_API_BASE_URL 仅作 invoke 透传，不在此层）。

import { apiClient } from "./client";

// 与 docs/staging/specs/2026-09-29-resume-keyword-matching.md 的 KeywordTag dataclass 对齐。
export interface KeywordTag {
  /** 原始关键词 */
  kw: string;
  /** 标准化后关键词（归一化 canonical form，可选） */
  standard?: string;
  /** 分类：hard_skill / soft_skill / tool / framework / domain / cert / education / city / role / project / other */
  category: string;
  /** 权重 0.1-5.0（项目经历 3-5，技能列表 2-3，其他 1-2） */
  weight: number;
  source?: string;
  resume_section?: string;
}

// 适配方向：LLM 推断的候选职业方向 + 权重 + 证据。
export interface FitDirection {
  direction: string;
  weight: number;
  evidence?: string;
  description?: string;
}

// 简历画像：解析结果根结构，存入 resumes.parsed_profile_json。
export interface ParsedProfile {
  keywords: KeywordTag[];
  fit_directions: FitDirection[];
}

export interface ParseResumeResponse {
  keywords?: unknown[];
  fit_directions?: unknown[];
}

/** 把 LLM 返回的任意形状归一化为稳定的 ParsedProfile。 */
export function normalizeParsedProfile(raw: unknown): ParsedProfile {
  const obj = (raw ?? {}) as ParseResumeResponse;
  const keywordsRaw = Array.isArray(obj.keywords) ? obj.keywords : [];
  const dirsRaw = Array.isArray(obj.fit_directions) ? obj.fit_directions : [];

  const keywords: KeywordTag[] = keywordsRaw.map((item) => {
    const k = (item ?? {}) as Record<string, unknown>;
    return {
      kw: String(k.kw ?? k.keyword ?? k.word ?? k.name ?? "").trim(),
      standard: k.standard != null ? String(k.standard) : undefined,
      category: String(k.category ?? "other").toLowerCase(),
      weight: numOr(k.weight, 1),
      source: k.source != null ? String(k.source) : undefined,
      resume_section: k.resume_section != null ? String(k.resume_section) : undefined,
    };
  });

  const fit_directions: FitDirection[] = dirsRaw.map((item) => {
    const d = (item ?? {}) as Record<string, unknown>;
    return {
      direction: String(d.direction ?? d.direction_name ?? d.name ?? "").trim(),
      weight: numOr(d.weight, 0),
      evidence: d.evidence != null ? String(d.evidence) : d.reason != null ? String(d.reason) : undefined,
      description: d.description != null ? String(d.description) : undefined,
    };
  });

  return { keywords, fit_directions };
}

function numOr(v: unknown, fallback: number): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

export const llmApi = {
  /** 解析简历文本 → 结构化关键词 + 适配方向。 */
  parseResume(resumeText: string): Promise<ParsedProfile> {
    return apiClient
      .post<ParseResumeResponse>("/api/v1/llm/parse-resume", {
        resume_text: resumeText,
      })
      .then(normalizeParsedProfile);
  },

  /** 上传简历文件（PDF / .txt / .md）→ 后端提取文本 → LLM 解析。 */
  async parseResumeFile(file: File): Promise<ParsedProfile> {
    const formData = new FormData();
    formData.append("file", file);

    const token = (() => {
      try {
        return localStorage.getItem("job_assistant_token") || "";
      } catch {
        return "";
      }
    })();

    const res = await fetch(`${import.meta.env.VITE_API_URL || ""}/api/v1/llm/parse-resume-file`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      const msg = data?.detail || data?.message || data?.error || `上传失败 (${res.status})`;
      throw new Error(msg);
    }

    const json = await res.json();
    return normalizeParsedProfile(json);
  },

  /** 用户编辑后请求 LLM 补充画像（合并用户已编辑 + 原文重新解析）。 */
  supplementProfile(
    userEdited: ParsedProfile,
    resumeText: string
  ): Promise<ParsedProfile> {
    return apiClient
      .post<ParseResumeResponse>("/api/v1/llm/supplement", {
        user_edited: userEdited,
        resume_text: resumeText,
      })
      .then(normalizeParsedProfile);
  },
};
