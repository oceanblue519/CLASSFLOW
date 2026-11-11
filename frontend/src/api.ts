const API_BASE_KEY = "classflow-api-base";
const SESSION_EXPIRY_GUARD_MS = 4_000;

export function markAuthSuccess(): void {
  (window as Window & { __classflowAuthAt?: number }).__classflowAuthAt = Date.now();
}

export function shouldDispatchSessionExpired(): boolean {
  const lastAuthAt = (window as Window & { __classflowAuthAt?: number }).__classflowAuthAt ?? 0;
  return Date.now() - lastAuthAt > SESSION_EXPIRY_GUARD_MS;
}

export function getConfiguredApiBase(): string {
  const saved = localStorage.getItem(API_BASE_KEY)?.trim();
  return saved || import.meta.env.VITE_API_BASE_URL?.trim() || "";
}

export function saveConfiguredApiBase(value: string): void {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) {
    localStorage.removeItem(API_BASE_KEY);
    return;
  }

  const parsed = new URL(trimmed);
  if (parsed.protocol !== "https:" && parsed.hostname !== "localhost" && parsed.hostname !== "127.0.0.1") {
    throw new Error("Use an HTTPS server address. HTTP is allowed only for localhost testing.");
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error("Enter only the API server address, without credentials, query, or fragment.");
  }

  localStorage.setItem(API_BASE_KEY, trimmed);
}

export function apiUrl(path: string): string {
  const endpoint = path.startsWith("/api/") ? path : "/api" + (path.startsWith("/") ? path : "/" + path);
  const localWebDevelopment = import.meta.env.DEV &&
    window.location.protocol.startsWith("http") &&
    ["localhost", "127.0.0.1"].includes(window.location.hostname);
  const configured = localWebDevelopment ? "" : getConfiguredApiBase();
  if (!configured) return endpoint;
  const base = configured.endsWith("/api") ? configured : configured + "/api";
  return base + endpoint.slice(4);
}

export function apiFetch(path: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(apiUrl(path), {
    ...options,
    credentials: "include",
    headers,
  });
}

export async function api(path: string, options: RequestInit = {}) {
  const response = await apiFetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/") && shouldDispatchSessionExpired()) {
      window.dispatchEvent(new Event("classflow:session-expired"));
    }
    throw new Error(data.detail || "Request failed");
  }
  return data;
}
