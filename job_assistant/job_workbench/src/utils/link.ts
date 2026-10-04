// 链接工具：在 Tauri 中通过 shell 插件调用系统浏览器打开外部链接，
// Web 环境降级为 window.open。同时校验 URL 合法性。

// 检测是否在 Tauri 环境中运行
function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/**
 * 判断是否为可打开的 URL。
 * 规则：
 * - 必须有 http:// 或 https:// 前缀（没有则在 normalizeUrl 中补全）
 * - 允许中文、特殊字符（公司公告 URL 常含非 ASCII 字符）
 */
export function isValidUrl(url: string | null | undefined): boolean {
  if (!url) return false;
  const trimmed = url.trim();
  if (!trimmed) return false;
  // 简单判断：包含点号且不是纯空白
  return /^(https?:\/\/)?[^\s]+\.[^\s]+$/i.test(trimmed);
}

/**
 * 规范化 URL：
 * - 去除首尾空白
 * - 没有协议时补 https://
 * - 从可能含中文标点的文本中提取第一个 URL
 */
export function normalizeUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  const trimmed = url.trim();
  if (!trimmed) return null;

  // 如果已经是完整 URL，直接返回
  if (/^https?:\/\//i.test(trimmed)) {
    return trimmed;
  }

  // 尝试从文本中提取 URL
  const match = trimmed.match(/https?:\/\/[^\s，。、；"'<>]+/);
  if (match) {
    return match[0];
  }

  // 没有协议前缀，补 https://
  if (/^[^\s]+\.[^\s]+$/i.test(trimmed)) {
    return `https://${trimmed}`;
  }

  return null;
}

/**
 * 打开外部链接。
 * Tauri 环境用 shell 插件调用系统浏览器；Web 环境降级为 window.open。
 * @returns 是否成功打开（非法 URL 返回 false）
 */
export async function openExternalUrl(url: string | null | undefined): Promise<boolean> {
  const target = normalizeUrl(url);
  if (!target) return false;

  // Tauri 环境：动态加载 shell 插件，调用系统默认浏览器
  if (isTauri()) {
    try {
      const { open: shellOpen } = await import("@tauri-apps/plugin-shell");
      await shellOpen(target);
      return true;
    } catch {
      // shell 插件不可用，降级
    }
  }

  // Web 环境降级：window.open
  try {
    window.open(target, "_blank", "noopener,noreferrer");
    return true;
  } catch {
    // 最后兜底：修改当前窗口 location
    try {
      window.location.href = target;
      return true;
    } catch {
      return false;
    }
  }
}

/** 从可能含中文标点的文本中提取第一个 http(s) URL */
export function extractUrl(text: string | null | undefined): string | null {
  if (!text) return null;
  const match = text.match(/https?:\/\/[^\s，。、；"'<>]+/);
  return match ? match[0] : null;
}
