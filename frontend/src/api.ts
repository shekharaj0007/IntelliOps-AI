import type { Incident, Overview, RcaResult, ServiceDetail } from "./types";

const TOKEN_KEY = "intelliops_token";
const EMAIL_KEY = "intelliops_email";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getEmail(): string | null {
  return localStorage.getItem(EMAIL_KEY);
}

export function setSession(token: string, email: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(EMAIL_KEY, email);
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EMAIL_KEY);
}

async function readDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    return response.statusText || "Request failed";
  } catch {
    return response.statusText || "Request failed";
  }
}

export async function login(email: string, password: string): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
  } catch {
    throw new ApiError(0, "Cannot reach the API. Start the backend on 127.0.0.1:8000.");
  }
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response));
  }
  const body = (await response.json()) as { access_token: string; email: string };
  setSession(body.access_token, body.email);
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the API. Start the backend on 127.0.0.1:8000.");
  }
  if (response.status === 401) {
    clearSession();
    window.location.assign("/login");
    throw new ApiError(401, "Not authenticated");
  }
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response));
  }
  return (await response.json()) as T;
}

export const loadOverview = () => api<Overview>("/api/overview");
export const loadService = (id: number) => api<ServiceDetail>(`/api/services/${id}`);
export const loadServices = () => api<{ data_origin: string; services: Overview["fleet"] }>("/api/services");
export const loadIncidents = () => api<{ data_origin: string; incidents: Incident[] }>("/api/incidents");
export const ackAnomaly = (id: number) => api(`/api/anomalies/${id}/ack`, { method: "POST" });

export function createIncident(body: {
  title: string;
  severity: string;
  service_id: number;
  summary: string;
}): Promise<Incident> {
  return api<Incident>("/api/incidents", { method: "POST", body: JSON.stringify(body) });
}

export function generateRca(id: number): Promise<RcaResult> {
  return api<RcaResult>(`/api/incidents/${id}/rca`, { method: "POST" });
}

export function searchSimilar(query: string): Promise<{ results: Incident[] }> {
  return api<{ results: Incident[] }>(`/api/incidents/similar?q=${encodeURIComponent(query)}`);
}
