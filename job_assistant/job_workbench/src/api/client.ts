// API 客户端：封装 fetch，统一 baseURL、Bearer Token 注入、401 自动 refresh。
// 错误以 { error: string, status: number } 结构抛出（reject），调用方 try/catch 读取。

const ENV = (import.meta as { env?: Record<string, string | undefined> }).env ?? {};
const BASE_URL = ENV.VITE_API_URL || "http://localhost:8000";

const TOKEN_KEY = "job_assistant_token";

export interface ApiError {
  error: string;
  status: number;
}

type TokenAccessor = {
  get: () => string | null;
  set: (token: string | null) => void;
};

const defaultAccessor: TokenAccessor = {
  get: () => {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set: (token) => {
    try {
      if (token) localStorage.setItem(TOKEN_KEY, token);
      else localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* localStorage 不可用时静默忽略 */
    }
  },
};

function toQuery(params?: Record<string, unknown>): string {
  if (!params) return "";
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null) return;
    sp.set(k, String(v));
  });
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export class ApiClient {
  private baseUrl: string;
  private accessor: TokenAccessor = defaultAccessor;
  private refreshing = false;

  constructor(baseUrl: string = BASE_URL) {
    this.baseUrl = baseUrl;
  }

  /** 由 authStore 注入 store + localStorage 联动的 token 读写器。 */
  setTokenAccessor(accessor: TokenAccessor) {
    this.accessor = accessor;
  }

  private buildHeaders(init?: RequestInit): Record<string, string> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...((init?.headers as Record<string, string>) || {}),
    };
    const token = this.accessor.get();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return headers;
  }

  private async extractError(res: Response): Promise<string> {
    try {
      const data = await res.json();
      if (typeof data === "string") return data;
      return (
        data?.message || data?.error || data?.detail || `请求失败（${res.status}）`
      );
    } catch {
      return `请求失败（${res.status}）`;
    }
  }

  private redirectToLogin() {
    if (typeof window === "undefined") return;
    const path = window.location.pathname;
    if (path !== "/login" && path !== "/register") {
      window.location.href = "/login";
    }
  }

  private async tryRefresh(): Promise<boolean> {
    if (this.refreshing) return false;
    const token = this.accessor.get();
    if (!token) return false;
    this.refreshing = true;
    try {
      const res = await fetch(`${this.baseUrl}/api/v1/auth/refresh`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
      });
      if (!res.ok) return false;
      const data = await res.json();
      if (data?.token) {
        this.accessor.set(data.token as string);
        return true;
      }
      return false;
    } catch {
      return false;
    } finally {
      this.refreshing = false;
    }
  }

  private async request<T>(
    pathWithQuery: string,
    init?: RequestInit,
    allowRetry = true
  ): Promise<T> {
    const res = await fetch(`${this.baseUrl}${pathWithQuery}`, {
      ...init,
      headers: this.buildHeaders(init),
    });

    if (res.status === 401 && allowRetry) {
      const refreshed = await this.tryRefresh();
      if (refreshed) return this.request<T>(pathWithQuery, init, false);
      this.accessor.set(null);
      this.redirectToLogin();
      const err: ApiError = { error: "登录已过期，请重新登录", status: 401 };
      throw err;
    }

    if (!res.ok) {
      const message = await this.extractError(res);
      const err: ApiError = { error: message, status: res.status };
      throw err;
    }

    if (res.status === 204) return undefined as T;
    const text = await res.text();
    if (!text) return undefined as T;
    return JSON.parse(text) as T;
  }

  get<T>(path: string, params?: Record<string, unknown>): Promise<T> {
    return this.request<T>(`${path}${toQuery(params)}`, { method: "GET" });
  }

  post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  put<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "PUT",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  delete<T>(path: string, params?: Record<string, unknown>): Promise<T> {
    return this.request<T>(`${path}${toQuery(params)}`, { method: "DELETE" });
  }
}

export const apiClient = new ApiClient();
