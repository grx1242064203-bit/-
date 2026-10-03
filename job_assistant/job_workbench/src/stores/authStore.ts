// Zustand auth store：维护登录态，token 持久化到 localStorage。
import { create } from "zustand";
import { authApi } from "../api/auth";
import { apiClient } from "../api/client";

const TOKEN_KEY = "job_assistant_token";

function readToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function persistToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* localStorage 不可用时静默忽略 */
  }
}

export interface AuthUser {
  email: string;
  user_id?: string;
}

export interface AuthState {
  token: string | null;
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<boolean>;
  register: (
    email: string,
    password: string
  ) => Promise<{ needs_verify: boolean; user_id?: string }>;
  verifyEmail: (email: string, code: string) => Promise<boolean>;
  logout: () => void;
  loadFromStorage: () => void;
}

const initialToken = readToken();

export const useAuthStore = create<AuthState>((set) => ({
  token: initialToken,
  user: null,
  isAuthenticated: !!initialToken,
  isLoading: false,
  error: null,

  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      const data = await authApi.login(email, password);
      persistToken(data.token);
      set({
        token: data.token,
        user: { email },
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });
      return true;
    } catch (e) {
      const err = e as { error?: string; status?: number };
      set({ isLoading: false, error: err?.error || "登录失败，请稍后重试" });
      return false;
    }
  },

  register: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      const data = await authApi.register(email, password);
      set({
        isLoading: false,
        user: { email, user_id: data.user_id },
        error: null,
      });
      return { needs_verify: data.needs_verify, user_id: data.user_id };
    } catch (e) {
      const err = e as { error?: string; status?: number };
      set({ isLoading: false, error: err?.error || "注册失败，请稍后重试" });
      return { needs_verify: false };
    }
  },

  verifyEmail: async (email, code) => {
    set({ isLoading: true, error: null });
    try {
      const data = await authApi.verifyEmail(email, code);
      persistToken(data.token);
      set({
        token: data.token,
        user: { email },
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });
      return true;
    } catch (e) {
      const err = e as { error?: string; status?: number };
      set({ isLoading: false, error: err?.error || "验证失败，请检查验证码" });
      return false;
    }
  },

  logout: () => {
    persistToken(null);
    set({ token: null, user: null, isAuthenticated: false, error: null });
  },

  loadFromStorage: () => {
    const token = readToken();
    set({
      token,
      isAuthenticated: !!token,
    });
  },
}));

// 把 ApiClient 的 token 读写器接到 store + localStorage，避免循环依赖。
// （client.ts 不 import authStore，由这里单向注入回调）
apiClient.setTokenAccessor({
  get: () => useAuthStore.getState().token || readToken(),
  set: (token) => {
    persistToken(token);
    useAuthStore.setState({
      token,
      isAuthenticated: !!token,
    });
  },
});
