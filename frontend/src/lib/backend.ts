const BACKEND_URL_STORAGE_KEY = "backend_base_url";
const AUTH_TOKEN_KEY = "auth_token";
const AUTH_USER_KEY = "auth_user";

function forceLogoutAndRedirect(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_USER_KEY);
  if (typeof window !== "undefined" && window.location.pathname !== "/auth") {
    window.location.href = "/auth";
  }
}

export function getBackendBaseUrl(): string {
  const saved = localStorage.getItem(BACKEND_URL_STORAGE_KEY);
  if (saved && saved.trim()) return saved.trim().replace(/\/$/, "");

  const fromEnv = (import.meta.env.VITE_API_BASE_URL as string | undefined) || "http://localhost:8000";
  return fromEnv.replace(/\/$/, "");
}

export function setBackendBaseUrl(url: string): void {
  localStorage.setItem(BACKEND_URL_STORAGE_KEY, url.trim().replace(/\/$/, ""));
}

export function apiUrl(path: string): string {
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${getBackendBaseUrl()}${cleanPath}`;
}

export function wsUrl(path: string): string {
  const base = getBackendBaseUrl().replace(/^http/, "ws");
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${base}${cleanPath}`;
}

export function resolveAssetUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  const trimmed = url.trim();
  if (!trimmed) return null;

  const base = getBackendBaseUrl();
  if (trimmed.startsWith("/")) {
    return `${base}${trimmed}`;
  }

  try {
    const parsed = new URL(trimmed);
    const hostname = parsed.hostname.toLowerCase();
    const isLikelyInternal =
      hostname === "backend" ||
      hostname === "ielts_backend" ||
      hostname.startsWith("172.") ||
      hostname.startsWith("10.") ||
      hostname.startsWith("192.168.");

    if (isLikelyInternal) {
      const baseUrl = new URL(base);
      return `${baseUrl.protocol}//${baseUrl.host}${parsed.pathname}${parsed.search}`;
    }
    return trimmed;
  } catch {
    return trimmed;
  }
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem("auth_token");
  const authHeader = token ? { Authorization: `Token ${token}` } : {};
  const isFormData = init?.body instanceof FormData;

  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...init,
      headers: {
        ...(isFormData ? {} : { "Content-Type": "application/json" }),
        ...authHeader,
        ...(init?.headers || {}),
      },
    });
  } catch (error) {
    // Common after backend/container restarts while stale auth is still in localStorage.
    forceLogoutAndRedirect();
    throw error;
  }

  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      forceLogoutAndRedirect();
    }
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  if (response.status === 204) {
    return {} as T;
  }

  const text = await response.text();
  if (!text) {
    return {} as T;
  }

  return JSON.parse(text) as T;
}
