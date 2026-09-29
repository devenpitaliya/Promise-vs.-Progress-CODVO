import axios, { AxiosError } from 'axios';

const TOKEN_KEY = 'pvp_token';
export const SESSION_EXPIRED_EVENT = 'pvp:session-expired';

export const tokenStore = {
  get: (): string | null => {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set: (token: string) => {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      // storage unavailable (private mode): session lasts until reload
    }
  },
  clear: () => {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      // ignore
    }
  },
};

// Configured from the project `.env`: VITE_API_URL (optional), API_PREFIX, VITE_API_TIMEOUT_MS.
const API_BASE_URL = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_PREFIX || '/api/v1';
const API_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS) || 60_000;

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: API_TIMEOUT_MS,
});

api.interceptors.request.use((config) => {
  const token = tokenStore.get();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const isAuthCall = error.config?.url?.startsWith('/auth/');
    if (error.response?.status === 401 && !isAuthCall && tokenStore.get()) {
      tokenStore.clear();
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
    return Promise.reject(error);
  },
);

interface ValidationIssue {
  loc?: (string | number)[];
  msg?: string;
}

/** Human-readable message for any API error, including FastAPI validation errors. */
export function errorMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) return 'Cannot reach the server. Check your connection and try again.';
    const detail = (error.response.data as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      return (detail as ValidationIssue[])
        .map((issue) => {
          const field = issue.loc?.filter((part) => part !== 'body').join('.');
          const msg = (issue.msg ?? 'Invalid value').replace(/^Value error, /, '');
          return field ? `${field}: ${msg}` : msg;
        })
        .join(' ');
    }
    if (error.response.status >= 500) return 'The server hit an error. Please try again shortly.';
  }
  return fallback;
}
