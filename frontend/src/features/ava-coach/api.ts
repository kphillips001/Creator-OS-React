import type { AvaCoachDashboard } from "./types";

async function request<T>(path = "", init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1/ava-coach${path}`, {
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const body = await response.json() as T & { detail?: string };
  if (!response.ok) throw new Error(body.detail || "Ava Coach request failed.");
  return body;
}

export const avaCoachApi = {
  dashboard: () => request<AvaCoachDashboard>(),
  analyze: () => request<AvaCoachDashboard>("/analyze", { method: "POST" }),
  transition: (id: string, action: "approve" | "reject" | "dismiss") =>
    request(`/recommendations/${id}/${action}`, { method: "POST" }),
  edit: (id: string, title: string, description: string) =>
    request(`/recommendations/${id}`, {
      method: "PATCH", body: JSON.stringify({ title, description }),
    }),
};
