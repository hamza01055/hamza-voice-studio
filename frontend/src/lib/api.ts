// Thin API client. The per-session token arrives in the URL fragment (#token=...) from the
// launcher or through the Electron preload bridge, and is kept in sessionStorage only.

declare global {
  interface Window {
    hvsDesktop?: {
      token: () => Promise<string>;
      revealExport: (fileName: string) => Promise<boolean>;
      platform: string;
    };
  }
}

const TOKEN_KEY = "hvs.token";
let token: string | null = null;

export function readTokenFromLocation(): void {
  const m = window.location.hash.match(/token=([A-Za-z0-9_\-]+)/);
  if (m) {
    token = m[1];
    try {
      sessionStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* storage unavailable: keep in memory */
    }
    history.replaceState(null, "", window.location.pathname + "#/projects");
    return;
  }
  try {
    token = sessionStorage.getItem(TOKEN_KEY);
  } catch {
    token = null;
  }
}

export async function initToken(): Promise<string | null> {
  if (window.hvsDesktop) {
    token = await window.hvsDesktop.token();
    return token;
  }
  readTokenFromLocation();
  return token;
}

export function getToken(): string | null {
  return token;
}

export function setTokenForTests(t: string | null): void {
  token = t;
}

export class ApiError extends Error {
  code: string;
  status: number;
  details: Record<string, unknown>;
  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function request<T>(method: string, path: string, body?: unknown, isForm = false): Promise<T> {
  const headers: Record<string, string> = {};
  if (token) headers["X-HVS-Token"] = token;
  let payload: BodyInit | undefined;
  if (body !== undefined) {
    if (isForm) payload = body as FormData;
    else {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
  }
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { method, headers, body: payload });
  } catch {
    throw new ApiError(0, "backend_unreachable", "The studio service is not responding. Is it still running?");
  }
  if (!res.ok) {
    let err: { error?: { code?: string; message?: string; details?: Record<string, unknown> } } = {};
    try {
      err = await res.json();
    } catch {
      /* not JSON */
    }
    throw new ApiError(
      res.status,
      err.error?.code ?? "http_error",
      err.error?.message ?? `Request failed (${res.status}).`,
      err.error?.details ?? {},
    );
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(p: string) => request<T>("GET", p),
  post: <T>(p: string, body?: unknown) => request<T>("POST", p, body ?? {}),
  patch: <T>(p: string, body: unknown) => request<T>("PATCH", p, body),
  del: <T>(p: string) => request<T>("DELETE", p),
  form: <T>(p: string, fd: FormData) => request<T>("POST", p, fd, true),
};

/** URL usable by <audio>/<a download>; the token goes in a query param for these GET routes only. */
export function mediaUrl(path: string): string {
  const sep = path.includes("?") ? "&" : "?";
  return `/api${path}${sep}t=${encodeURIComponent(token ?? "")}`;
}

export function assetUrl(assetId: string): string {
  return mediaUrl(`/assets/${assetId}/audio`);
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "Something went wrong.";
}
