// 链接工具：安全打开外部链接，校验 URL 合法性。
// 非法 URL（如 "邮箱:xxx"、"电话:xxx"）返回 false，由调用方降级为文本展示。

const URL_REGEX = /^https?:\/\/[^\s/$.?#].[^\s]*$/i;

/** 判断是否为合法的 http(s) URL */
export function isValidUrl(url: string | null | undefined): boolean {
  if (!url) return false;
  return URL_REGEX.test(url.trim());
}

/**
 * 打开外部链接（Tauri webview 与浏览器通用）。
 * @returns 是否成功打开（非法 URL 返回 false）
 */
export function openExternalUrl(url: string | null | undefined): boolean {
  if (!isValidUrl(url)) return false;
  const target = url!.trim();
  try {
    window.open(target, "_blank", "noopener,noreferrer");
    return true;
  } catch {
    return false;
  }
}

/** 从可能含中文标点的文本中提取第一个 http(s) URL */
export function extractUrl(text: string | null | undefined): string | null {
  if (!text) return null;
  const match = text.match(/https?:\/\/[^\s，。、；]+/);
  return match ? match[0] : null;
}
