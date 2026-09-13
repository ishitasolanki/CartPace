/** Thin fetch wrapper: attaches the token, throws ApiError with the parsed
 * detail on any non-2xx so callers get a message worth showing rather than
 * a generic "request failed". */

import type {
  CertificateOut,
  CompareOut,
  DayStatOut,
  DecisionOut,
  Me,
  RunOut,
  ScenarioInfo,
  StratumHistoryPoint,
  StratumOffset,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
const TOKEN_KEY = "cartpace_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...init, headers });

  if (res.status === 401) {
    // The token is gone or expired -- there is no route back to a valid
    // session except logging in again, so drop it now rather than let every
    // subsequent call fail the same way.
    clearToken();
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) {
        // FastAPI's 422 shape: a list of {loc, msg, type}.
        detail = body.detail.map((d: { msg: string }) => d.msg).join("; ");
      }
    } catch {
      /* body wasn't JSON; fall back to statusText */
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string; role: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  me: () => request<Me>("/api/auth/me"),

  scenarios: () => request<Record<string, ScenarioInfo>>("/api/scenarios"),

  listRuns: () => request<RunOut[]>("/api/runs"),

  createRun: (scenario: string, seed: number, n_days: number) =>
    request<RunOut>("/api/runs", {
      method: "POST",
      body: JSON.stringify({ scenario, seed, n_days }),
    }),

  getRun: (id: number) => request<RunOut>(`/api/runs/${id}`),

  startRun: (id: number) =>
    request<{ status: string }>(`/api/runs/${id}/start`, { method: "POST" }),

  decisions: (id: number, offset = 0, limit = 200) =>
    request<DecisionOut[]>(
      `/api/runs/${id}/decisions?offset=${offset}&limit=${limit}`,
    ),

  certificate: (id: number) =>
    request<CertificateOut>(`/api/runs/${id}/certificate`),

  strata: (id: number, day?: number) =>
    request<StratumOffset[]>(
      `/api/runs/${id}/strata${day !== undefined ? `?day=${day}` : ""}`,
    ),

  dayStats: (id: number) => request<DayStatOut[]>(`/api/runs/${id}/daystats`),

  strataHistory: (id: number) =>
    request<StratumHistoryPoint[]>(`/api/runs/${id}/strata/history`),

  compare: (id: number) => request<CompareOut>(`/api/runs/${id}/compare`),
};

export function wsUrl(runId: number): string {
  const token = getToken() ?? "";
  const httpBase = new URL(BASE);
  const scheme = httpBase.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${httpBase.host}/api/runs/${runId}/ws?token=${encodeURIComponent(token)}`;
}
